"""Methods to add arguments based on class/method/function signatures."""

import dataclasses
import inspect
import os
import re
from argparse import SUPPRESS, ArgumentParser
from collections.abc import Callable
from typing import Any, Optional, Union

from ._actions import _ActionConfigLoad
from ._common import (
    LoggerProperty,
    get_generic_origin,
    get_parsing_setting,
    get_unaliased_type,
    is_final_class,
    is_subclass,
    is_subclasses_disabled,
)
from ._deprecated import deprecation_warning, renamed_parameter_warning
from ._instantiation import get_class_instantiator
from ._namespace import Namespace, get_value_and_parent
from ._optionals import attrs_support, get_doc_short_description, is_attrs_class, is_pydantic_model
from ._parameter_resolvers import ParamData, get_parameter_origins, get_signature_parameters
from ._required import set_required
from ._typehints import (
    ActionTypeHint,
    callable_instances,
    get_subclass_names,
    is_list_pathlike,
    is_optional,
    not_required_types,
    sequence_origin_types,
)
from ._util import NoneType, get_import_path, get_private_kwargs, get_typehint_origin, iter_to_set_str
from .typing import _LazyInitBaseClass, register_pydantic_type

kinds = inspect._ParameterKind
inspect_empty = inspect._empty


class SignatureArguments(LoggerProperty):
    """Methods to add arguments based on signatures to an :class:`ArgumentParser` instance."""

    @renamed_parameter_warning({"theclass": "class_type"})
    def add_class_arguments(
        self,
        class_type: type,
        nested_key: str | None = None,
        as_group: bool = True,
        as_positional: bool = False,
        default: dict | Namespace | type | None = None,
        skip: set[str | int] | None = None,
        instantiate: bool = True,
        fail_untyped: bool = True,
        sub_configs: bool = False,
        **kwargs,
    ) -> list[str]:
        """Adds arguments from a class based on its type hints and docstrings.

        Note: Keyword arguments without at least one valid type are ignored.

        Args:
            class_type: Class from which to add arguments.
            nested_key: Key for nested namespace.
            as_group: Whether arguments should be added to a new argument group.
            as_positional: Whether to add required parameters as positional arguments.
            default: Default value used to override parameter defaults.
            skip: Names of parameters or number of positionals that should be skipped.
            instantiate: Whether the class group should be instantiated by
                :meth:`instantiate <.ArgumentParser.instantiate>`.
            fail_untyped: Whether to raise exception if a required parameter does not have a type.
            sub_configs: Whether subclass type hints should be loadable from inner config file.

        Returns:
            The list of arguments added.

        Raises:
            ValueError: When not given a class.
            ValueError: When there are required parameters without at least one valid type.
        """
        unaliased_class_type = get_unaliased_type(class_type)
        if not inspect.isclass(get_generic_origin(unaliased_class_type)):
            raise ValueError(f"Expected 'class_type' parameter to be a class type, got: {class_type}")
        if not (
            isinstance(default, (NoneType, dict, Namespace))
            or (isinstance(default, _LazyInitBaseClass) and isinstance(default, unaliased_class_type))
            or (
                not is_final_class(default.__class__)
                and is_subclasses_disabled(default.__class__)
                and isinstance(default, unaliased_class_type)
            )
        ):
            raise ValueError(
                f"Expected 'default' to be dict, Namespace, lazy instance or dataclass-like, got: {default}"
            )
        linked_targets, help_, _ = get_private_kwargs(
            kwargs,
            linked_targets=None,
            help=None,
            required=None,  # Ignored because provided when adding signatures, remove with dataclass inheritance support
        )

        added_args = self._add_signature_arguments(
            class_type,
            None,
            nested_key,
            as_group,
            as_positional,
            skip,
            fail_untyped,
            sub_configs=sub_configs,
            instantiate=instantiate,
            linked_targets=linked_targets,
            help=help_,
        )

        if default:
            skip = skip or set()
            prefix = nested_key + "." if nested_key else ""
            defaults = default
            if isinstance(default, _LazyInitBaseClass):
                defaults = default.lazy_get_init_args().as_dict()
            elif is_convertible_to_dict(default.__class__):
                defaults = convert_to_dict(default)
                args = {k[len(prefix) :] for k in added_args}
                skip_not_added = [k for k in defaults if k not in args]
                if skip_not_added:
                    skip.update(skip_not_added)  # skip init=False
            if defaults:
                defaults = {prefix + k: v for k, v in defaults.items() if k not in skip}  # type: ignore[union-attr]
                self.set_defaults(**defaults)  # type: ignore[attr-defined]

        return added_args

    @renamed_parameter_warning({"theclass": "class_type", "themethod": "method_name"})
    def add_method_arguments(
        self,
        class_type: type,
        method_name: str,
        nested_key: str | None = None,
        as_group: bool = True,
        as_positional: bool = False,
        skip: set[str | int] | None = None,
        fail_untyped: bool = True,
        sub_configs: bool = False,
    ) -> list[str]:
        """Adds arguments from a class based on its type hints and docstrings.

        Note: Keyword arguments without at least one valid type are ignored.

        Args:
            class_type: Class which includes the method.
            method_name: Name of the method for which to add arguments.
            nested_key: Key for nested namespace.
            as_group: Whether arguments should be added to a new argument group.
            as_positional: Whether to add required parameters as positional arguments.
            skip: Names of parameters or number of positionals that should be skipped.
            fail_untyped: Whether to raise exception if a required parameter does not have a type.
            sub_configs: Whether subclass type hints should be loadable from inner config file.

        Returns:
            The list of arguments added.

        Raises:
            ValueError: When not given a class or the name of a method of the class.
            ValueError: When there are required parameters without at least one valid type.
        """
        unaliased_type = get_unaliased_type(class_type)
        if not inspect.isclass(get_generic_origin(unaliased_type)):
            raise ValueError('Expected "class_type" argument to be a class object.')
        if not hasattr(unaliased_type, method_name) or not callable(getattr(unaliased_type, method_name)):
            raise ValueError('Expected "method_name" argument to be a callable member of the class.')

        return self._add_signature_arguments(
            class_type,
            method_name,
            nested_key,
            as_group,
            as_positional,
            skip,
            fail_untyped,
            sub_configs=sub_configs,
        )

    def add_function_arguments(
        self,
        function: Callable,
        nested_key: str | None = None,
        as_group: bool = True,
        as_positional: bool = False,
        skip: set[str | int] | None = None,
        fail_untyped: bool = True,
        sub_configs: bool = False,
    ) -> list[str]:
        """Adds arguments from a function based on its type hints and docstrings.

        Note: Keyword arguments without at least one valid type are ignored.

        Args:
            function: Function from which to add arguments.
            nested_key: Key for nested namespace.
            as_group: Whether arguments should be added to a new argument group.
            as_positional: Whether to add required parameters as positional arguments.
            skip: Names of parameters or number of positionals that should be skipped.
            fail_untyped: Whether to raise exception if a required parameter does not have a type.
            sub_configs: Whether subclass type hints should be loadable from inner config file.

        Returns:
            The list of arguments added.

        Raises:
            ValueError: When not given a callable.
            ValueError: When there are required parameters without at least one valid type.
        """
        if not callable(function):
            raise ValueError('Expected "function" argument to be a callable object.')

        method_name = None
        if hasattr(function, "__class__") and callable_instances(function.__class__):
            function = function.__class__
            method_name = "__call__"

        return self._add_signature_arguments(
            function,
            method_name,
            nested_key,
            as_group,
            as_positional,
            skip,
            fail_untyped,
            sub_configs=sub_configs,
        )

    def _add_signature_arguments(
        self,
        function_or_class,
        method_name,
        nested_key: str | None,
        as_group: bool = True,
        as_positional: bool = False,
        skip: set[str | int] | None = None,
        fail_untyped: bool = True,
        sub_configs: bool = False,
        instantiate: bool = True,
        linked_targets: set[str] | None = None,
        help: str | None = None,
    ) -> list[str]:
        """Adds arguments from parameters of objects based on signatures and docstrings.

        Args:
            function_or_class: Object from which to add arguments.
            method_name: Class method from which to add arguments.
            nested_key: Key for nested namespace.
            as_group: Whether arguments should be added to a new argument group.
            as_positional: Whether to add required parameters as positional arguments.
            skip: Names of parameters or number of positionals that should be skipped.
            fail_untyped: Whether to raise exception if a required parameter does not have a type.
            sub_configs: Whether subclass type hints should be loadable from inner config file.
            instantiate: Whether the class group should be instantiated.

        Returns:
            The list of arguments added.

        Raises:
            ValueError: When there are required parameters without at least one valid type.
        """
        params = get_signature_parameters(function_or_class, method_name, logger=self.logger)

        skip_positionals = [s for s in (skip or []) if isinstance(s, int) and s != 0]
        if skip_positionals:
            if len(skip_positionals) > 1 or any(p <= 0 for p in skip_positionals):
                raise ValueError(f"Unexpected number of positionals to skip: {skip_positionals}")
            names = {p.name for p in params[: skip_positionals[0]]}
            params = params[skip_positionals[0] :]
            self.logger.debug(
                f"Skipping parameters {names} because {skip_positionals[0]} positionals requested to be skipped."
            )

        prefix = "--" + (nested_key + "." if nested_key else "")
        for param in params:
            if skip and param.name in skip:
                continue
            if prefix + param.name in self._option_string_actions:  # type: ignore[attr-defined]
                raise ValueError(
                    f"Unable to add parameter '{param.name}' from {function_or_class} because "
                    f"argument '{prefix + param.name}' already exists."
                )

        ## Create group if requested ##
        if help is not None:
            doc_group = help
        else:
            doc_group = get_doc_short_description(function_or_class, method_name, logger=self.logger)
        component = getattr(function_or_class, method_name) if method_name else function_or_class
        container = self._create_group_if_requested(
            component,
            nested_key,
            as_group,
            doc_group,
            config_load=len(params) > 0,
            instantiate=instantiate,
        )

        ## Add parameter arguments ##
        added_args: list[str] = []
        for param in params:
            self._add_signature_parameter(
                container,
                nested_key,
                param,
                added_args,
                skip={s for s in (skip or []) if isinstance(s, str)},
                fail_untyped=fail_untyped,
                sub_configs=sub_configs,
                linked_targets=linked_targets,
                as_positional=as_positional,
            )

        return added_args

    def _add_signature_parameter(
        self,
        container,
        nested_key: str | None,
        param,
        added_args: list[str],
        skip: set[str] | None = None,
        fail_untyped: bool = True,
        as_positional: bool = False,
        sub_configs: bool = False,
        instantiate: bool = True,
        linked_targets: set[str] | None = None,
        default: Any = inspect_empty,
        **kwargs,
    ):
        name = param.name
        kind = param.kind
        annotation = param.annotation
        if default == inspect_empty:
            default = param.default
            if default == inspect_empty:
                if is_optional(annotation):
                    if os.environ.get("JSONARGPARSE_DEPRECATION_WARNINGS", "").lower() == "all":
                        deprecation_warning(
                            "signature_optional_parameter_without_default",
                            "Optional type parameters without a default are currently not required. "
                            "In v5 they will be required.",
                            stacklevel=4,
                        )
                    unset_sentinel = get_parsing_setting("unset_sentinel")
                    default = unset_sentinel if unset_sentinel is not None else None
                elif get_typehint_origin(annotation) in not_required_types:
                    default = SUPPRESS
        # Determine argument characteristics based on parameter kind and default value
        if kind == kinds.POSITIONAL_ONLY:
            is_required = True  # Always required
            is_non_positional = False  # Can be positional
        elif kind == kinds.KEYWORD_ONLY:
            is_required = default == inspect_empty  # Required if no default
            is_non_positional = True  # Must use --flag style
        elif kind in {kinds.POSITIONAL_OR_KEYWORD, None}:
            # POSITIONAL_OR_KEYWORD or programmatically created parameters without kind
            is_required = default == inspect_empty  # Required if no default
            is_non_positional = False  # Can be positional
        else:
            raise RuntimeError(f"The code should never reach here: kind={kind}")  # pragma: no cover
        src = get_parameter_origins(param.component, param.parent)
        skip_message = f'Skipping parameter "{name}" from "{src}" because of: '
        if not fail_untyped and annotation == inspect_empty:
            if is_required and os.environ.get("JSONARGPARSE_DEPRECATION_WARNINGS", "").lower() == "all":
                deprecation_warning(
                    "fail_untyped_false_required_parameter",
                    "With fail_untyped=False, required parameters without a type annotation are currently "
                    "set to optional with default None. In v5 the type will be set to Any but the parameter "
                    "will remain required.",
                    stacklevel=4,
                )
            annotation = Any
            default = None if is_required else default
            is_required = False
        is_required_link_target = False
        if is_required and linked_targets is not None and name in linked_targets:
            default = None
            is_required = False
            is_required_link_target = True
        if not is_required and name[0] == "_":
            return
        elif skip and name in skip:
            self.logger.debug(skip_message + "Parameter requested to be skipped.")
            return
        if is_factory_class(default):
            default = param.parent.__dataclass_fields__[name].default_factory()
        if annotation == inspect_empty and not is_required:
            annotation = Union[type(default), Any]
        if "help" not in kwargs:
            kwargs["help"] = param.doc
        if not is_required:
            kwargs["default"] = default
            if default is None and not is_optional(annotation, object) and not is_required_link_target:
                annotation = Optional[annotation]
        elif not as_positional or is_non_positional:
            kwargs["required"] = True
        is_subclass_typehint = False
        nested_skip: set[str] = set()
        subclasses_disabled = is_subclasses_disabled(annotation)
        dest = (nested_key + "." if nested_key else "") + name
        args = [dest if is_required and as_positional and not is_non_positional else "--" + dest]
        if param.origin:
            parser = container
            if not isinstance(container, ArgumentParser):
                parser = getattr(container, "parser")
            group_name = "; ".join(str(o) for o in param.origin)
            if group_name in parser.groups:
                container = parser.groups[group_name]
            else:
                container = parser.add_argument_group(
                    f"Conditional arguments [origins: {group_name}]",
                    name=group_name,
                )
        if annotation in {str, int, float, bool} or is_subclass(annotation, (str, int, float)) or subclasses_disabled:
            kwargs["type"] = annotation
            register_pydantic_type(annotation)
        elif annotation != inspect_empty:
            try:
                is_subclass_typehint = ActionTypeHint.is_subclass_typehint(annotation, all_subtypes=False)
                is_return_subclass_typehint = ActionTypeHint.is_return_subclass_typehint(annotation)
                kwargs["type"] = annotation
                sub_add_kwargs: dict = {"fail_untyped": fail_untyped, "sub_configs": sub_configs}
                if is_subclass_typehint or is_return_subclass_typehint:
                    prefix = f"{name}.init_args."
                    nested_skip = {s[len(prefix) :] for s in skip or [] if s.startswith(prefix)}
                    sub_add_kwargs["skip"] = nested_skip
                else:
                    register_pydantic_type(annotation)
                enable_path = sub_configs and (
                    is_subclass_typehint or is_return_subclass_typehint or is_list_pathlike(annotation)
                )
                args = ActionTypeHint.prepare_add_argument(
                    args=args,
                    kwargs=kwargs,
                    enable_path=enable_path,
                    container=container,
                    logger=self.logger,
                    sub_add_kwargs=sub_add_kwargs,
                )
            except ValueError as ex:
                self.logger.debug(skip_message + str(ex))
        if "type" in kwargs or "action" in kwargs:
            sub_add_kwargs = {
                "fail_untyped": fail_untyped,
                "sub_configs": sub_configs,
                "instantiate": instantiate,
            }
            if subclasses_disabled:
                kwargs.update(sub_add_kwargs)
            with ActionTypeHint.allow_default_instance_context():
                action = container.add_argument(*args, **kwargs)
            if action is not None:  # None when class without any parameters
                action.sub_add_kwargs = sub_add_kwargs
                if nested_skip:
                    action.sub_add_kwargs["skip"] = nested_skip
            added_args.append(dest)
        elif is_required and fail_untyped:
            raise ValueError(
                "With fail_untyped=True, all mandatory parameters must have a supported"
                f" type. Parameter '{name}' from '{src}' does not specify a type."
            )

    def add_subclass_arguments(
        self,
        baseclass: type | tuple[type, ...],
        nested_key: str,
        as_group: bool = True,
        skip: set[str] | None = None,
        instantiate: bool = True,
        required: bool = False,
        metavar: str = "CONFIG | CLASS_PATH_OR_NAME | .INIT_ARG_NAME VALUE",
        help: str = (
            'One or more arguments specifying "class_path" and "init_args" for any subclass of %(baseclass_name)s.'
        ),
        **kwargs,
    ):
        """Adds arguments to allow specifying any subclass of the given base class.

        This adds an argument that requires a dictionary with a ``class_path``
        entry which must be a import dot notation expression. Optionally any
        init arguments for the class can be given in the ``init_args`` entry.
        Since subclasses can have different init arguments, the help does not
        show the details of the arguments of the base class. Instead a help
        argument is added that will print the details for a given class path.

        Args:
            baseclass: Base class or classes to use to check subclasses.
            nested_key: Key for nested namespace.
            as_group: Whether arguments should be added to a new argument group.
            skip: Names of parameters that should be skipped.
            required: Whether the argument group is required.
            metavar: Variable string to show in the argument's help.
            help: Description of argument to show in the help.
            **kwargs: Additional parameters like in :meth:`add_class_arguments`.

        Raises:
            ValueError: When given an invalid base class.
        """
        if type(baseclass) is not tuple:
            baseclass = (baseclass,)
        assert isinstance(baseclass, tuple)
        if not baseclass or not all(ActionTypeHint.is_subclass_typehint(c, also_lists=True) for c in baseclass):
            raise ValueError(f"Expected 'baseclass' to be a subclass type or a tuple of subclass types: {baseclass}")

        doc_group = None
        if len(baseclass) == 1:
            doc_group = get_doc_short_description(baseclass[0], logger=self.logger)
        group = self._create_group_if_requested(
            baseclass,
            nested_key,
            as_group,
            doc_group,
            config_load=False,
            required=required,
            instantiate=False,
        )

        added_args: list[str] = []
        if skip is not None:
            skip = {f"{nested_key}.init_args." + s for s in skip}
        param = ParamData(name=nested_key, annotation=Union[baseclass], component=baseclass)
        str_baseclass = iter_to_set_str(get_subclass_names(param.annotation))
        kwargs.update(
            {
                "metavar": metavar,
                "help": (help % {"baseclass_name": str_baseclass}),
            }
        )
        if "default" not in kwargs:
            kwargs["default"] = None
        self._add_signature_parameter(
            group, None, param, added_args, skip, sub_configs=True, instantiate=instantiate, **kwargs
        )

    def _create_group_if_requested(
        self,
        obj,
        nested_key,
        as_group,
        doc_group,
        config_load=True,
        config_load_type=None,
        required=False,
        instantiate=True,
    ):
        if required:
            if nested_key is None:
                raise ValueError("A nested_key is mandatory to make required.")
            set_required(self, nested_key)

        group = self
        if as_group:
            if doc_group is None:
                if isinstance(obj, tuple) and len(obj) == 1:
                    doc_group = str(obj[0])
                else:
                    doc_group = str(obj)
            name = obj.__name__ if nested_key is None else nested_key
            group = self.add_argument_group(strip_title(doc_group), name=name)
            if config_load and nested_key is not None:
                group.add_argument("--" + nested_key, action=_ActionConfigLoad(basetype=config_load_type))
            if inspect.isclass(obj) and nested_key is not None and instantiate:
                group.dest = nested_key.replace("-", "_")
                group.group_class = obj
                group.instantiate_class = group_instantiate_class
        return group


def group_instantiate_class(group, cfg):
    try:
        value, parent, key = get_value_and_parent(cfg, group.dest)
    except KeyError:
        value = {}
        parent = cfg
        key = group.dest
    instantiator_fn = get_class_instantiator()
    parent[key] = instantiator_fn(group.group_class, **value)


def strip_title(value):
    if value is not None:
        value = re.sub(r"\.$", "", value.strip())
    return value


def is_factory_class(value):
    return value.__class__ == dataclasses._HAS_DEFAULT_FACTORY_CLASS


def is_convertible_to_dict(value):
    return dataclasses.is_dataclass(value) or is_attrs_class(value) or is_pydantic_model(value)


def convert_to_dict(value) -> dict:
    if attrs_support:
        import attrs

        if attrs.has(type(value)):
            return attrs.asdict(value)

    value_type = type(value)
    init_args = {}
    for name, attr in vars(value).items():
        attr_type = type(attr)
        if is_convertible_to_dict(attr_type):
            attr = convert_to_dict(attr)
        elif attr_type in sequence_origin_types:
            attr = attr.copy()
            for num, item in enumerate(attr):
                if is_convertible_to_dict(type(item)):
                    attr[num] = convert_to_dict(item)
        init_args[name] = attr

    if is_subclasses_disabled(value_type):
        return init_args
    return {"class_path": get_import_path(value_type), "init_args": init_args}
