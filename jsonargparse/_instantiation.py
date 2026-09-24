import dataclasses
import functools
import inspect
import sys
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any, Protocol

from ._common import ClassType, applied_instantiation_links, get_parsing_setting, is_subclass, parser_context
from ._namespace import Namespace, get_value_and_parent, split_key

__all__ = ["add_instantiator"]

kinds = inspect._ParameterKind


@dataclasses.dataclass(frozen=True)
class CallLayout:
    """How the values of the parameters of a signature are given in a call."""

    # parameters that can be given positionally, in order, i.e. positional-only ones and the ones
    # before a *args
    positional: tuple[str, ...] = ()
    # number of leading positional ones that are always given positionally, i.e. up to the last
    # positional-only one. The rest are only given positionally when *args is not empty.
    always_positional: int = 0
    var_positional: str | None = None
    # defaults of the positional ones, used when one was not given, e.g. because it was skipped
    defaults: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    # number of leading positionals that are not bound, but given when calling, e.g. by the
    # caller of a callable that returns a class
    open_positionals: int = 0


def get_call_layout(params: list, open_positionals: int = 0) -> CallLayout:
    """Gets the call layout for a list of resolved parameters."""
    var_idx = next((n for n, p in enumerate(params) if p.kind == kinds.VAR_POSITIONAL), None)
    positional_only_idxs = [n for n, p in enumerate(params) if p.kind == kinds.POSITIONAL_ONLY]
    end = var_idx if var_idx is not None else (positional_only_idxs[-1] + 1 if positional_only_idxs else 0)
    positional = [p for p in params[:end] if p.kind in {kinds.POSITIONAL_ONLY, kinds.POSITIONAL_OR_KEYWORD}]
    always = [n for n, p in enumerate(positional) if p.kind == kinds.POSITIONAL_ONLY]
    return CallLayout(
        positional=tuple(p.name for p in positional),
        always_positional=always[-1] + 1 if always else 0,
        var_positional=None if var_idx is None else params[var_idx].name,
        defaults={p.name: p.default for p in positional if p.default is not inspect._empty},
        open_positionals=open_positionals,
    )


def get_call_arguments(layout: CallLayout, values: Mapping[str, Any], component: Any) -> tuple[list, dict]:
    """Splits values into the positional and keyword arguments with which to call a component."""
    kwargs = dict(values)
    var_positional = list(kwargs.pop(layout.var_positional, ())) if layout.var_positional else []
    num_positional = len(layout.positional) if var_positional else layout.always_positional
    args = []
    for num, name in enumerate(layout.positional[:num_positional]):
        if name in kwargs:
            args.append(kwargs.pop(name))
        elif name in layout.defaults:
            args.append(layout.defaults[name])
        else:
            following = layout.var_positional if var_positional else layout.positional[num_positional - 1]
            raise ValueError(
                f'Calling {component} requires a value for parameter "{name}", since it precedes "{following}" '
                "which is given positionally."
            )
    return args + var_positional, kwargs


def bind_call(func: Callable, layout: CallLayout, values: Mapping[str, Any], component: Any = None) -> Callable:
    """Binds values to func according to a call layout, returning a callable that makes the call."""
    args, kwargs = get_call_arguments(layout, values, component or func)
    if layout.open_positionals and args:
        # the open positionals are given on call, before the bound ones
        if sys.version_info < (3, 14):
            raise ValueError(
                f"Binding values to positionals of {component or func} that follow {layout.open_positionals} "
                "positionals given on call is only supported in Python 3.14 or later."
            )
        args = [functools.Placeholder] * layout.open_positionals + args
    return partial(func, *args, **kwargs)


class InstantiatorCallable(Protocol):
    def __call__(self, class_type: type[ClassType], *args, **kwargs) -> ClassType:
        pass  # pragma: no cover


InstantiatorsDictType = dict[tuple[type, bool], InstantiatorCallable]

_class_instantiators: InstantiatorsDictType = {}


class InstantiateMethod:
    def instantiate(
        self,
        namespace: Namespace,
        instantiate_groups: bool = True,
    ) -> Namespace:
        """Instantiates all signature components in a configuration namespace.

        Processes the configuration recursively, converting each signature
        component registered with the parser into its corresponding Python
        object:

        - **Class/subclass type arguments** (``add_argument`` with a class type
          or ``add_class_arguments``/``add_subclass_arguments``): An object with
          ``class_path`` and optionally ``init_args`` is replaced by an instance
          of the referenced class, created by calling the class with the
          ``init_args``. For the case of classes with disabled
          subclasses, the namespace can have directly the init args without the
          ``class_path`` + ``init_args`` wrapper.

        - **Callable type arguments**: A dot-import string pointing to a
          function or method is resolved to the callable object. When
          ``class_path``/``init_args`` is given instead and the class
          instantiates into a callable (or is a subclass of the callable's
          return type), the result is either a class instance or — when not all
          call arguments are provided yet — a :func:`functools.partial` bound to
          the given ``init_args``.

        - **Function and method groups** (``add_function_arguments`` or
          ``add_method_arguments`` with a ``nested_key``): Replaced by a
          :func:`functools.partial` with the arguments bound, or by an
          :func:`operator.methodcaller` for a method that is called with an
          instance.

        - **Instantiation order**: Components are processed in the order
          determined by argument links applied on instantiation.

        Args:
            namespace: The configuration object to use. Must have been produced
                by one of the ``parse_*`` methods and not modified in a way that
                breaks the structure expected by the parser.
            instantiate_groups: Whether class, function and method groups should be instantiated.

        Returns:
            A new configuration object where every registered signature
            component has been replaced by its corresponding Python object.
        """
        from ._actions import _ActionConfigLoad, filter_non_parsing_actions
        from ._core import ArgumentGroup
        from ._link_arguments import ActionLink
        from ._subcommands import get_subcommand
        from ._typehints import ActionTypeHint

        components: list[ActionTypeHint | _ActionConfigLoad | ArgumentGroup] = []
        for action in filter_non_parsing_actions(self._actions):  # type: ignore[attr-defined]
            if isinstance(action, ActionTypeHint):
                components.append(action)
            elif isinstance(action, ActionLink) and isinstance(action.target[1], ActionTypeHint):
                components.append(action.target[1])

        if instantiate_groups:
            skip = {c.dest for c in components}
            groups = [
                g
                for g in self._action_groups  # type: ignore[attr-defined]
                if hasattr(g, "instantiate_class") and g.dest not in skip
            ]
            components.extend(groups)

        components.sort(key=lambda x: -len(split_key(x.dest)))  # type: ignore[arg-type]
        order = ActionLink.instantiation_order(self)
        components = ActionLink.reorder(order, components)

        cfg = namespace.clone(with_meta=False)
        unset_sentinel = get_parsing_setting("unset_sentinel")
        for component in components:
            ActionLink.apply_instantiation_links(self, cfg, target=component.dest)
            if isinstance(component, ActionTypeHint):
                try:
                    value, parent, key = get_value_and_parent(cfg, component.dest)
                except (KeyError, AttributeError):
                    pass
                else:
                    if value is not unset_sentinel:
                        with parser_context(
                            parent_parser=self,
                            nested_links=ActionLink.get_nested_links(self, component),
                            applied_instantiation_links=cfg.get("__applied_instantiation_links__"),
                        ):
                            parent[key] = component.instantiate_classes(value)
            elif hasattr(component, "instantiate_class"):
                with parser_context(
                    load_value_mode=self.parser_mode,  # type: ignore[attr-defined]
                    applied_instantiation_links=cfg.get("__applied_instantiation_links__"),
                ):
                    component.instantiate_class(component, cfg)

        ActionLink.apply_instantiation_links(self, cfg, order=order)

        subcommand, subparser = get_subcommand(self, cfg, fail_no_subcommand=False)  # type: ignore[arg-type]
        if subcommand is not None and subparser is not None:
            cfg[subcommand] = subparser.instantiate(cfg[subcommand], instantiate_groups=instantiate_groups)

        return cfg


def add_instantiator(
    instantiator: InstantiatorCallable,
    class_type: type[ClassType],
    subclasses: bool = True,
    prepend: bool = False,
) -> None:
    """Adds a custom instantiator for a class type. Used by ``ArgumentParser.instantiate``.

    Instantiator functions are expected to have as signature ``(class_type:
    Type[ClassType], *args, **kwargs) -> ClassType``.

    For reference, the default instantiator is ``return class_type(*args,
    **kwargs)``.

    In some use cases, the instantiator function might need access to values
    applied by instantiation links. For this, the instantiator function can
    have an additional keyword parameter ``applied_instantiation_links:
    dict``. This parameter will be populated with a dictionary having as
    keys the targets of the instantiation links and corresponding values
    that were applied.

    Args:
        instantiator: Function that instantiates a class.
        class_type: The class type to instantiate.
        subclasses: Whether to instantiate subclasses of ``class_type``.
        prepend: Whether to prepend the instantiator to the existing instantiators.
    """
    key = (class_type, subclasses)
    _class_instantiators.pop(key, None)
    if prepend:
        existing = dict(_class_instantiators)
        _class_instantiators.clear()
        _class_instantiators[key] = instantiator
        _class_instantiators.update(existing)
    else:
        _class_instantiators[key] = instantiator


def dynamic_class_instantiator(class_type: type[ClassType], *args, **kwargs) -> ClassType:
    for (cls, subclasses), instantiator in _class_instantiators.items():
        if class_type is cls or (subclasses and is_subclass(class_type, cls)):
            param_names = set(inspect.signature(instantiator).parameters)
            if "applied_instantiation_links" in param_names:
                applied_links = applied_instantiation_links.get() or set()
                kwargs["applied_instantiation_links"] = {
                    action.target[0]: action.applied_value for action in applied_links
                }
            return instantiator(class_type, *args, **kwargs)
    return class_type(*args, **kwargs)
