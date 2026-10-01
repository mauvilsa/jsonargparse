import inspect
from collections.abc import Callable, Sequence
from functools import partial

from ._common import (
    ClassType,
    InstantiatorCallable,
    InstantiatorsDictType,
    InstantiatorsType,
    applied_instantiation_links,
    class_instantiators,
    get_parsing_setting,
    is_subclass,
    parser_context,
    scoped_class_instantiators,
)
from ._namespace import Namespace, get_value_and_parent, split_key

__all__ = ["add_instantiator"]

_global_class_instantiators: InstantiatorsDictType = {}


class InstantiateMethod:
    def instantiate(
        self,
        namespace: Namespace,
        instantiate_groups: bool = True,
        *,
        instantiators: InstantiatorsType | None = None,
    ) -> Namespace:
        """Instantiates all signature components in a configuration namespace.

        Processes the configuration recursively, converting each signature
        component registered with the parser into its corresponding Python
        object:

        - **Class/subclass type arguments** (``add_argument`` with a class type
          or ``add_class_arguments``/``add_subclass_arguments``): An object with
          ``class_path`` and optionally ``init_args`` is replaced by an instance
          of the referenced class, created by calling
          ``class_type(**init_args)``. For the case of classes with disabled
          subclasses, the namespace can have directly the init args without the
          ``class_path`` + ``init_args`` wrapper.

        - **Callable type arguments**: A dot-import string pointing to a
          function or method is resolved to the callable object. When
          ``class_path``/``init_args`` is given instead and the class
          instantiates into a callable (or is a subclass of the callable's
          return type), the result is either a class instance or — when not all
          call arguments are provided yet — a :func:`functools.partial` bound to
          the given ``init_args``.

        - **Instantiation order**: Components are processed in the order
          determined by argument links applied on instantiation.

        Args:
            namespace: The configuration object to use. Must have been produced
                by one of the ``parse_*`` methods and not modified in a way that
                breaks the structure expected by the parser.
            instantiate_groups: Whether class groups should be instantiated.
            instantiators: Custom instantiators for this call, a list of ``(instantiator, class_type,
                subclasses)`` tuples, see :func:`.add_instantiator`. The first match is used, before any
                others.

        Returns:
            A new configuration object where every registered signature
            component has been replaced by its corresponding Python object.
        """
        from ._actions import _ActionConfigLoad, filter_non_parsing_actions
        from ._core import ArgumentGroup
        from ._deprecated import deprecation_warning_function_groups_instantiate
        from ._link_arguments import ActionLink
        from ._subcommands import get_subcommand
        from ._typehints import ActionTypeHint

        if instantiators is None:  # a nested instantiate keeps the ones of the enclosing call
            scoped = scoped_class_instantiators.get()
        else:
            scoped = validate_instantiators(instantiators)

        components: list[ActionTypeHint | _ActionConfigLoad | ArgumentGroup] = []
        for action in filter_non_parsing_actions(self._actions):  # type: ignore[attr-defined]
            if isinstance(action, ActionTypeHint):
                components.append(action)
            elif isinstance(action, ActionLink) and isinstance(action.target[1], ActionTypeHint):
                components.append(action.target[1])

        if instantiate_groups:
            deprecation_warning_function_groups_instantiate(self, stacklevel=2)
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
                            class_instantiators=get_class_instantiators(self, scoped),
                            scoped_class_instantiators=scoped,
                            applied_instantiation_links=get_applied_instantiation_links(cfg),
                        ):
                            parent[key] = component.instantiate_classes(value)
            elif hasattr(component, "instantiate_class"):
                with parser_context(
                    load_value_mode=self.parser_mode,  # type: ignore[attr-defined]
                    class_instantiators=get_class_instantiators(self, scoped),
                    scoped_class_instantiators=scoped,
                    applied_instantiation_links=get_applied_instantiation_links(cfg),
                ):
                    component.instantiate_class(component, cfg)

        ActionLink.apply_instantiation_links(self, cfg, order=order)

        subcommand, subparser = get_subcommand(self, cfg, fail_no_subcommand=False)  # type: ignore[arg-type]
        if subcommand is not None and subparser is not None:
            # given by context, since a subparser could override instantiate without the instantiators parameter
            with parser_context(scoped_class_instantiators=scoped):
                cfg[subcommand] = subparser.instantiate(cfg[subcommand], instantiate_groups=instantiate_groups)

        return cfg


def add_instantiator(
    instantiator: InstantiatorCallable,
    class_type: type[ClassType],
    subclasses: bool = True,
    prepend: bool = False,
) -> None:
    """Adds a custom instantiator for a class type, globally for all ``ArgumentParser.instantiate`` calls.

    Prefer the ``instantiators`` parameter of ``instantiate``, which is limited to that call.

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
    _register_instantiator(
        _global_class_instantiators, instantiator, class_type, subclasses=subclasses, prepend=prepend
    )


def _register_instantiator(
    registry: InstantiatorsDictType,
    instantiator: InstantiatorCallable,
    class_type: type[ClassType],
    subclasses: bool = True,
    prepend: bool = False,
) -> None:
    """Registers an instantiator in the given registry dict (in-place)."""
    key = (class_type, subclasses)
    items = {k: v for k, v in registry.items() if k != key}
    if prepend:
        registry.clear()
        registry.update({key: instantiator, **items})
    else:
        items[key] = instantiator
        registry.clear()
        registry.update(items)


def _get_global_class_instantiators() -> InstantiatorsDictType:
    """Returns the global instantiators registry."""
    return _global_class_instantiators


def default_class_instantiator(class_type: type[ClassType], *args, **kwargs) -> ClassType:
    return class_type(*args, **kwargs)


class ClassInstantiator:
    def __init__(self, instantiators: InstantiatorsDictType, applied_links: set | None = None) -> None:
        self.instantiators = instantiators
        # the values are taken now, since applied_value changes when the parser instantiates again
        self.applied_links = {action.target[0]: action.applied_value for action in applied_links or ()}

    def __call__(self, class_type: type[ClassType], *args, **kwargs) -> ClassType:
        for (cls, subclasses), instantiator in self.instantiators.items():
            if class_type is cls or (subclasses and is_subclass(class_type, cls)):
                param_names = set(inspect.signature(instantiator).parameters)
                if "applied_instantiation_links" in param_names:
                    kwargs["applied_instantiation_links"] = dict(self.applied_links)
                return instantiator(class_type, *args, **kwargs)
        return default_class_instantiator(class_type, *args, **kwargs)


def get_class_instantiator() -> InstantiatorCallable:
    """Gets the instantiator of the current context.

    The applied instantiation links are taken at this point, so that a deferred call, e.g. a partial given by
    ``instantiate``, gets them even though it happens outside of the ``instantiate`` call.
    """
    instantiators = class_instantiators.get()
    instantiator: InstantiatorCallable = default_class_instantiator
    if instantiators:
        instantiator = ClassInstantiator(instantiators, applied_instantiation_links.get())
    return partial(call_without_instantiate_context, instantiator)


def call_without_instantiate_context(func: Callable[..., ClassType], /, *args, **kwargs) -> ClassType:
    """Calls func without the context of the enclosing ``instantiate``, so that it doesn't affect other parsers."""
    with parser_context(class_instantiators=None, scoped_class_instantiators=None, applied_instantiation_links=None):
        return func(*args, **kwargs)


def get_class_instantiators(parser, scoped: tuple | None = None) -> InstantiatorsDictType:
    """Gathers all instantiators applicable to the given parser, the first ones having precedence."""
    instantiators = get_scoped_instantiators_dict(scoped)
    for source in [parser._get_parser_instantiators(), class_instantiators.get(), _get_global_class_instantiators()]:
        for key, instantiator in (source or {}).items():
            instantiators.setdefault(key, instantiator)
    return instantiators


def get_scoped_instantiators_dict(scoped: tuple | None) -> InstantiatorsDictType:
    """Converts validated call-scoped instantiators into a dict, the first one of each key having precedence."""
    instantiators: InstantiatorsDictType = {}
    for instantiator, class_type, subclasses in scoped or ():
        instantiators.setdefault((class_type, subclasses), instantiator)
    return instantiators


def get_applied_instantiation_links(cfg: Namespace) -> set:
    """Gets the links applied so far, for a nested ``instantiate`` including the ones of the enclosing call."""
    return (cfg.get("__applied_instantiation_links__") or set()) | (applied_instantiation_links.get() or set())


def validate_instantiators(instantiators: InstantiatorsType) -> tuple:
    if (
        not isinstance(instantiators, Sequence)
        or isinstance(instantiators, str)
        or not all(
            isinstance(item, tuple)
            and len(item) == 3
            and callable(item[0])
            and inspect.isclass(item[1])
            and isinstance(item[2], bool)
            for item in instantiators
        )
    ):
        raise ValueError(
            "Expected instantiators to be a list of tuples (instantiator, class_type, subclasses), "
            f"got {instantiators!r}"
        )
    return tuple(instantiators)
