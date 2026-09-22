import inspect

from ._common import (
    ClassType,
    InstantiatorCallable,
    InstantiatorsDictType,
    applied_instantiation_links,
    class_instantiators,
    get_parsing_setting,
    is_subclass,
    parser_context,
)
from ._namespace import Namespace, get_value_and_parent, split_key

__all__ = ["add_instantiator"]

_global_class_instantiators: InstantiatorsDictType = {}


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
                            class_instantiators=get_class_instantiators(self),
                            applied_instantiation_links=cfg.get("__applied_instantiation_links__"),
                        ):
                            parent[key] = component.instantiate_classes(value)
            elif hasattr(component, "instantiate_class"):
                with parser_context(
                    load_value_mode=self.parser_mode,  # type: ignore[attr-defined]
                    class_instantiators=get_class_instantiators(self),
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
    def __init__(self, instantiators: InstantiatorsDictType) -> None:
        self.instantiators = instantiators

    def __call__(self, class_type: type[ClassType], *args, **kwargs) -> ClassType:
        for (cls, subclasses), instantiator in self.instantiators.items():
            if class_type is cls or (subclasses and is_subclass(class_type, cls)):
                param_names = set(inspect.signature(instantiator).parameters)
                if "applied_instantiation_links" in param_names:
                    applied_links = applied_instantiation_links.get() or set()
                    kwargs["applied_instantiation_links"] = {
                        action.target[0]: action.applied_value for action in applied_links
                    }
                return instantiator(class_type, *args, **kwargs)
        return default_class_instantiator(class_type, *args, **kwargs)


def get_class_instantiator() -> InstantiatorCallable:
    instantiators = class_instantiators.get()
    if not instantiators:
        return default_class_instantiator
    return ClassInstantiator(instantiators)


def get_class_instantiators(parser) -> InstantiatorsDictType:
    """Gathers all instantiators applicable to the given parser."""
    instantiators = parser._get_parser_instantiators()
    context_instantiators = class_instantiators.get()
    if context_instantiators:
        instantiators = instantiators.copy()
        instantiators.update({k: v for k, v in context_instantiators.items() if k not in instantiators})
    global_instantiators = _get_global_class_instantiators()
    if global_instantiators:
        instantiators = instantiators.copy()
        instantiators.update({k: v for k, v in global_instantiators.items() if k not in instantiators})
    return instantiators
