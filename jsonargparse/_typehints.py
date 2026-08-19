"""Action to support type hints."""

import ast
import builtins
import inspect
import os
import re
import sys
import typing
from argparse import ArgumentError
from collections import OrderedDict, abc, defaultdict, deque
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from copy import deepcopy
from enum import Enum
from functools import partial, reduce
from importlib import import_module
from importlib.util import find_spec
from operator import or_
from types import FunctionType, GenericAlias, MappingProxyType, ModuleType, UnionType
from typing import (
    AbstractSet,
    Any,
    Callable,
    Collection,
    Container,
    Deque,
    Dict,
    ForwardRef,
    FrozenSet,
    Iterable,
    List,
    Literal,
    Mapping,
    MutableMapping,
    MutableSequence,
    MutableSet,
    NoReturn,
    Reversible,
    Sequence,
    Set,
    Tuple,
    Type,
    TypedDict,
    TypeVar,
    Union,
    get_args,
)

from ._actions import (
    Action,
    ActionConfigFile,
    ActionFail,
    _ActionHelpClassPath,
    _ActionPrintConfig,
    _is_action_value_list,
    remove_actions,
)
from ._common import (
    get_generic_origin,
    get_parsing_setting,
    get_unaliased_type,
    is_generic_class,
    is_instance,
    is_subclass,
    is_subclasses_disabled,
    lenient_check,
    nested_links,
    parent_parser,
    parse_logger,
    parser_context,
    validating_defaults,
)
from ._instantiation import get_class_instantiator
from ._loaders_dumpers import (
    basic_json_or_yaml_load,
    get_loader_exceptions,
    json_or_yaml_loader_exceptions,
    load_value,
)
from ._namespace import Namespace, subclasses_disabled_meta_key
from ._optionals import (
    capture_typing_extension_shadows,
    get_alias_target,
    is_alias_type,
    is_annotated,
    is_annotated_validator,
    typing_extensions_import,
    validate_annotated,
)
from ._paths import Path, PathError, change_to_path_dir
from ._required import clear_required
from ._subcommands import find_action, find_parent_action, parse_kwargs
from ._type_checking import ArgumentParser
from ._util import (
    NestedArg,
    NoneType,
    get_import_path,
    get_typehint_origin,
    import_object,
    indent_text,
    iter_to_set_str,
    load_config_path_context,
    object_path_serializer,
    parse_value_or_config,
    warning,
)
from .typing import _LazyInitBaseClass, get_registered_type, is_pydantic_type

NotRequired = typing_extensions_import("NotRequired")
Required = typing_extensions_import("Required")
_TypedDictMeta = typing_extensions_import("_TypedDictMeta")
Unpack = typing_extensions_import("Unpack")
get_type_hints = typing_extensions_import("get_type_hints")


def _capture_typing_extension_shadows(name: str, *collections) -> None:
    """
    Ensure different origins for types in typing_extensions are captured.
    """
    current_module = sys.modules[__name__]
    typehint = getattr(current_module, name)
    return capture_typing_extension_shadows(typehint, name, *collections)


root_types = {
    str,
    int,
    float,
    bool,
    Any,
    object,
    Literal,
    Type,
    type,
    Union,
    List,
    list,
    FrozenSet,
    Deque,
    deque,
    Collection,
    Container,
    Iterable,
    Reversible,
    Sequence,
    MutableSequence,
    abc.Collection,
    abc.Container,
    abc.Iterable,
    abc.Reversible,
    abc.Sequence,
    abc.MutableSequence,
    Tuple,
    tuple,
    Set,
    FrozenSet,
    set,
    frozenset,
    AbstractSet,
    MutableSet,
    abc.Set,
    abc.MutableSet,
    Dict,
    dict,
    Mapping,
    MutableMapping,
    abc.Mapping,
    abc.MutableMapping,
    OrderedDict,
    Callable,
    abc.Callable,
    ModuleType,
    UnionType,
    GenericAlias,
    NotRequired,
    Required,
    Unpack,
}

leaf_types = {
    str,
    int,
    float,
    bool,
    NoneType,
}

leaf_or_root_types = leaf_types.union(root_types)

tuple_set_origin_types = {Tuple, tuple, Set, set, frozenset, AbstractSet, MutableSet, abc.Set, abc.MutableSet}
sequence_origin_types = {
    List,
    list,
    Deque,
    deque,
    Collection,
    Container,
    Iterable,
    Reversible,
    Sequence,
    MutableSequence,
    abc.Collection,
    abc.Container,
    abc.Iterable,
    abc.Reversible,
    abc.Sequence,
    abc.MutableSequence,
}
mapping_origin_types = {
    Dict,
    dict,
    Mapping,
    MappingProxyType,
    MutableMapping,
    abc.Mapping,
    abc.MutableMapping,
    OrderedDict,
}
sequence_or_mapping_origin_types = sequence_origin_types.union(mapping_origin_types)
callable_origin_types = {Callable, abc.Callable}

literal_types = {Literal}
_capture_typing_extension_shadows("Literal", root_types, literal_types)

not_required_types = {NotRequired}
_capture_typing_extension_shadows("NotRequired", root_types, not_required_types)

required_types = {Required}
_capture_typing_extension_shadows("Required", root_types, required_types)
not_required_required_types = not_required_types.union(required_types)

typed_dict_types = {TypedDict}
_capture_typing_extension_shadows("TypedDict", typed_dict_types)

typed_dict_meta_types = {_TypedDictMeta}
_capture_typing_extension_shadows("_TypedDictMeta", typed_dict_meta_types)

unpack_types = {Unpack}
_capture_typing_extension_shadows("Unpack", unpack_types)

subclass_arg_parser: ContextVar = ContextVar("subclass_arg_parser")
allow_default_instance: ContextVar = ContextVar("allow_default_instance", default=False)
sub_defaults: ContextVar = ContextVar("sub_defaults", default=False)


def get_parse_optional_num_return() -> int:
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--test")
    arg_parsed = parser._parse_optional("--test=x")
    return len(arg_parsed)


parse_optional_num_return = get_parse_optional_num_return()


def freeze(value):
    if isinstance(value, dict):
        return tuple(sorted(((k, freeze(v)) for k, v in value.items()), key=lambda item: repr(item[0])))
    if isinstance(value, set):
        return tuple(sorted((freeze(v) for v in value), key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


_cached_class_parsers: dict[tuple, ArgumentParser] = {}


def cached_get_class_parser(*, val_class, sub_add_kwargs, skip_args, parent_parser, nested_links):
    if isinstance(val_class, str):
        val_class = import_object(val_class)
    parser_class = type(parent_parser)
    cache_key = (
        val_class,
        parser_class,
        parent_parser.parser_mode,
        freeze(sub_add_kwargs),
        freeze(skip_args),
        freeze(nested_links),
        get_parsing_setting("unset_sentinel"),
    )
    if cache_key in _cached_class_parsers:
        parser = _cached_class_parsers[cache_key]
        parser.logger = parent_parser.logger
        return parser

    kwargs = dict(sub_add_kwargs) if sub_add_kwargs else {}
    if skip_args:
        kwargs.setdefault("skip", set()).update(skip_args)

    parser = parser_class(exit_on_error=False, logger=parent_parser.logger, parser_mode=parent_parser.parser_mode)
    remove_actions(parser, (ActionConfigFile, _ActionPrintConfig))
    if inspect.isclass(val_class) or inspect.isclass(get_typehint_origin(val_class)):
        parser.add_class_arguments(val_class, **kwargs)
    else:
        kwargs = {k: v for k, v in kwargs.items() if k != "instantiate"}
        parser.add_function_arguments(val_class, **kwargs)

    if "linked_targets" in kwargs:
        for key in kwargs["linked_targets"]:
            clear_required(parser, key)

    for link_kwargs in nested_links:
        parser.link_arguments(**link_kwargs)

    parser._inner_parser = True

    _cached_class_parsers[cache_key] = parser
    return parser


def strip_required_typehint(typehint, is_required: bool, source: str):
    """Removes a top level Required/NotRequired wrapper, failing if it disagrees with the requiredness.

    The requiredness of an argument is already given by the argument itself, thus the wrappers are
    only accepted as a redundant specification and not included in the type shown in the help.
    """
    typehint_origin = get_typehint_origin(typehint)
    if typehint_origin not in not_required_required_types:
        return typehint
    expect_required = typehint_origin in required_types
    if is_required != expect_required:
        wrapper = "Required" if expect_required else "NotRequired"
        raise ValueError(
            f"Type {type_to_str(typehint)} given for {source}, but the argument is "
            f"{'required' if is_required else 'not required'}. {wrapper} is only accepted when the "
            f"argument is {'required' if expect_required else 'not required'}."
        )
    assert len(typehint.__args__) == 1, "(Not)Required requires a single type argument"
    return typehint.__args__[0]


class ActionTypeHint(Action):
    """Action to parse a type hint."""

    def __init__(self, typehint: type | None = None, enable_path: bool = False, **kwargs):
        """Initializer for ActionTypeHint instance.

        Args:
            typehint: The type hint to use for parsing.
            enable_path: Whether to try to load parsed value from path.

        Raises:
            ValueError: If a parameter is invalid.
        """
        if typehint is not None:
            typehint = replace_type_vars(typehint)
            if not self.is_supported_typehint(typehint, full=True):
                raise ValueError(f"Unsupported type hint {typehint}.")
            if get_typehint_origin(typehint) == Union:
                assert hasattr(typehint, "__args__")
                subtype_supported = [
                    subtype is NoneType or self.is_supported_typehint(subtype, full=True)
                    for subtype in typehint.__args__
                ]
                if sum(subtype_supported) < len(subtype_supported):
                    discard = {typehint.__args__[n] for n, s in enumerate(subtype_supported) if not s}
                    kwargs["logger"].debug(f"Discarding unsupported subtypes {discard} from {typehint}")
                    subtypes = tuple(t for t, s in zip(typehint.__args__, subtype_supported) if s)
                    typehint = Union[subtypes]
            self._typehint = sort_unions_in_typehint(typehint)
            self._enable_path = False if is_pathlike(typehint) else enable_path
        elif "_typehint" not in kwargs:
            raise ValueError("Expected typehint keyword argument.")
        else:
            self._typehint = kwargs.pop("_typehint")
            self._enable_path = kwargs.pop("_enable_path")
            self.sub_add_kwargs: dict = {}
            if "metavar" not in kwargs:
                kwargs["metavar"] = typehint_metavar(self._typehint)
            super().__init__(**kwargs)
            self._supports_append = self.supports_append(self._typehint)
            self.default = self.normalize_default(self.default)

    def normalize_default(self, default):
        from ._signatures import convert_to_dict, is_convertible_to_dict

        is_subclass_type = self.is_subclass_typehint(self._typehint, all_subtypes=False)
        if isinstance(default, _LazyInitBaseClass):
            default = default.lazy_get_init_data().as_dict()
        elif is_convertible_to_dict(default.__class__):
            default = convert_to_dict(default)
        elif is_subclass_type and isinstance(default, dict) and "class_path" in default:
            default = subclass_spec_as_namespace(default)
            default.class_path = normalize_import_path(default.class_path, self._typehint)
        elif is_enum_type(self._typehint) and isinstance(default, Enum):
            default = default.name
        elif is_module_type(self._typehint) and isinstance(default, ModuleType):
            default = default.__name__
        elif is_callable_type(self._typehint) and callable(default) and not inspect.isclass(default):
            default = get_import_path(default)
        elif ActionTypeHint.is_return_subclass_typehint(self._typehint) and inspect.isclass(default):
            default = {"class_path": get_import_path(default)}
        elif is_subclass_type and not allow_default_instance.get():
            from ._parameter_resolvers import UnknownDefault

            default_type = type(default)
            if not is_subclass(default_type, UnknownDefault) and self.is_subclass_typehint(default_type):
                raise ValueError("Subclass types require as default either a dict with class_path or a lazy instance.")
        return default

    @staticmethod
    def prepare_add_argument(args, kwargs, enable_path, container, logger, sub_add_kwargs=None):
        if kwargs.get("action") is not None:
            return args
        typehint = kwargs.pop("type")
        if args[0].startswith("--") and ActionTypeHint.supports_append(typehint):
            args = tuple(list(args) + [f"{a}+" for a in args if a.startswith("--")])
        if get_registered_type(typehint) is None and get_help_types(typehint):
            help_option = f"--{args[0]}.help" if args[0][0] != "-" else f"{args[0]}.help"
            help_action = container.add_argument(help_option, action=_ActionHelpClassPath(typehint=typehint))
            if sub_add_kwargs:
                help_action.sub_add_kwargs = sub_add_kwargs
        kwargs["action"] = ActionTypeHint(typehint=typehint, enable_path=enable_path, logger=logger)
        if kwargs.get("choices"):
            kwargs["type"] = lambda v: adapt_typehints(v, typehint)
        return args

    @staticmethod
    def is_supported_typehint(typehint, full=False):
        """Whether the given type hint is supported."""
        if get_registered_type(typehint) is not None:
            return True
        typehint = get_unaliased_type(typehint)

        if is_subclass(typehint, Namespace):
            raise ValueError("jsonargparse.Namespace is only intended for parsing results and not supported as a type.")

        supported = (
            typehint in root_types
            or isinstance(typehint, UnvalidatedType)
            or get_typehint_origin(typehint) in root_types
            or get_registered_type(typehint) is not None
            or is_subclass(typehint, Enum)
            or is_subclasses_disabled(typehint)
            or is_typed_dict(typehint)
            or ActionTypeHint.is_subclass_typehint(typehint)
        )
        if full and supported:
            typehint_origin = get_typehint_origin(typehint) or typehint
            if typehint not in root_types and typehint_origin in root_types and typehint_origin not in literal_types:
                num_supported_args = 0
                subtypes = getattr(typehint, "__args__", [])
                subtypes = [s for s in subtypes if s is not NoneType]
                for subtype in subtypes:
                    if (
                        subtype == Ellipsis
                        or (typehint_origin == type and isinstance(subtype, TypeVar))
                        or subtype in leaf_types
                        or ActionTypeHint.is_supported_typehint(subtype, full=True)
                    ):
                        num_supported_args += 1
                    elif typehint_origin != Union:
                        return False
                if typehint_origin == Union and subtypes and num_supported_args == 0:
                    return False
        return supported

    @staticmethod
    def is_subclass_typehint(typehint, all_subtypes=True, also_lists=False, also_closed=False):
        """Whether the type expects a class. also_closed includes types that have subclasses disabled."""
        typehint = typehint_from_action(typehint)
        if typehint is None:
            return False
        typehint = get_unaliased_type(typehint)
        typehint_origin = get_typehint_origin(typehint)
        if typehint_origin == Union or (also_lists and typehint_origin in sequence_origin_types):
            subtypes = [a for a in typehint.__args__ if a != NoneType]
            test = all if all_subtypes else any
            k = {"also_lists": also_lists, "also_closed": also_closed}
            return test(ActionTypeHint.is_subclass_typehint(s, **k) for s in subtypes)
        if also_closed:
            return is_single_subclass_or_closed_type(typehint, typehint_origin)
        return is_single_subclass_type(typehint, typehint_origin)

    @staticmethod
    def is_return_subclass_typehint(typehint):
        typehint = get_unaliased_type(get_optional_arg(get_unaliased_type(typehint)))
        typehint_origin = get_typehint_origin(typehint)
        if typehint_origin in callable_origin_types or is_instance_factory_protocol(typehint):
            return_type = get_callable_return_type(typehint)
            if ActionTypeHint.is_subclass_typehint(return_type):
                return True
        return False

    @staticmethod
    def is_mapping_typehint(typehint):
        typehint = get_unaliased_type(typehint)
        typehint_origin = get_typehint_origin(typehint) or typehint
        if (
            typehint in mapping_origin_types
            or typehint_origin in mapping_origin_types
            or is_optional(typehint, tuple(mapping_origin_types))
        ):
            return True
        return False

    @staticmethod
    def is_module_typehint(typehint):
        typehint = typehint_from_action(typehint)
        return typehint is not None and is_module_type(typehint)

    @staticmethod
    def is_callable_typehint(typehint):
        typehint = typehint_from_action(typehint)
        typehint_origin = get_typehint_origin(get_optional_arg(get_unaliased_type(typehint)))
        return typehint_origin in callable_origin_types

    def is_init_arg_mapping_typehint(self, key, cfg):
        result = False
        class_path = cfg.get(f"{self.dest}.class_path")
        if (
            isinstance(class_path, str)
            and key.startswith(f"{self.dest}.init_args.")
            and self.is_subclass_typehint(self)
        ):
            sub_add_kwargs = dict(self.sub_add_kwargs)
            sub_add_kwargs.pop("linked_targets", None)
            parser = ActionTypeHint.get_class_parser(class_path, sub_add_kwargs=sub_add_kwargs)
            key = re.sub(f"^{self.dest}.init_args.", "", key)
            typehint = getattr(find_action(parser, key), "_typehint", None)
            result = self.is_mapping_typehint(typehint)
        return result

    @staticmethod
    def parse_argv_item(arg_string):
        parser = subclass_arg_parser.get()
        action = None
        sep = None
        if arg_string.startswith("--"):
            arg_base, explicit_arg = (arg_string, None)
            if "=" in arg_string:
                arg_base, sep, explicit_arg = arg_string.partition("=")
            if "." in arg_base and arg_base not in parser._option_string_actions:
                action = find_parent_action(parser, arg_base[2:])

        typehint = typehint_from_action(action)
        if typehint or isinstance(action, ActionFail):
            if parse_optional_num_return == 4:
                return action, arg_base, sep, explicit_arg
            elif parse_optional_num_return == 1:
                return [(action, arg_base, sep, explicit_arg)]
            return action, arg_base, explicit_arg
        return None

    @staticmethod
    def discard_init_args_on_class_path_change(parser_or_action, prev_cfg, cfg):
        if isinstance(prev_cfg, dict):
            return
        keys = list(prev_cfg.keys(branches=True))
        num = 0
        while num < len(keys):
            key = keys[num]
            prev_val = prev_cfg.get(key)
            val = cfg.get(key)
            if is_subclass_spec(prev_val) and is_subclass_spec(val):
                action = parser_or_action
                if not isinstance(parser_or_action, ActionTypeHint):
                    action = find_action(parser_or_action, key)
                if isinstance(action, ActionTypeHint):
                    discard_init_args_on_class_path_change(action, prev_val, val)
                    prev_sub_cfg = prev_val.get("init_args")
                    if prev_sub_cfg:
                        sub_add_kwargs = getattr(action, "sub_add_kwargs", {})
                        subparser = ActionTypeHint.get_class_parser(val["class_path"], sub_add_kwargs)
                        sub_cfg = val.get("init_args", Namespace())
                        ActionTypeHint.discard_init_args_on_class_path_change(subparser, prev_sub_cfg, sub_cfg)
                    keys = keys[: num + 1] + [k for k in keys[num + 1 :] if not k.startswith(key + ".")]
            num += 1

    @staticmethod
    @contextmanager
    def subclass_arg_context(parser):
        subclass_arg_parser.set(parser)
        yield

    @staticmethod
    @contextmanager
    def allow_default_instance_context():
        token = allow_default_instance.set(True)
        try:
            yield
        finally:
            allow_default_instance.reset(token)

    @staticmethod
    @contextmanager
    def sub_defaults_context():
        t = sub_defaults.set(True)
        try:
            yield
        finally:
            sub_defaults.reset(t)

    @staticmethod
    def add_sub_defaults(parser, cfg):
        def skip_sub_defaults_apply(v):
            return not (
                isinstance(v, (str, Namespace, dict))
                or is_subclass_spec(v)
                or (isinstance(v, list) and any(is_subclass_spec(e) for e in v))
                or (isinstance(v, dict) and any(is_subclass_spec(e) for e in v.values()))
            )

        with ActionTypeHint.sub_defaults_context():
            parser._apply_actions(cfg, skip_fn=skip_sub_defaults_apply, prev_cfg=cfg.clone())

    @staticmethod
    def supports_append(action):
        typehint = typehint_from_action(action)
        typehint_origin = get_typehint_origin(typehint)
        return typehint and (
            typehint_origin in sequence_origin_types
            or (
                typehint_origin == Union
                and any(get_typehint_origin(x) in sequence_origin_types for x in typehint.__args__)
            )
        )

    def serialize(self, value, dump_kwargs=None):
        sub_add_kwargs = getattr(self, "sub_add_kwargs", {})
        with dump_kwargs_context(dump_kwargs):
            if _is_action_value_list(self):
                return [
                    adapt_typehints(
                        v,
                        self._typehint,
                        default=self.default,
                        serialize=True,
                        sub_add_kwargs=sub_add_kwargs,
                        logger=self.logger,
                    )
                    for v in value
                ]
            return adapt_typehints(
                value,
                self._typehint,
                default=self.default,
                serialize=True,
                sub_add_kwargs=sub_add_kwargs,
                logger=self.logger,
            )

    def __call__(self, *args, **kwargs):
        """Parses an argument validating against the corresponding type hint.

        Raises:
            TypeError: If the argument is not valid.
        """
        if len(args) == 0:
            kwargs["_typehint"] = self._typehint
            kwargs["_enable_path"] = self._enable_path
            if "nargs" in kwargs and kwargs["nargs"] == 0:
                raise ValueError("ActionTypeHint does not allow nargs=0.")
            return ActionTypeHint(**kwargs)
        parser, cfg, val, opt_str = args
        if not (self.nargs == "?" and val is None):
            # the option string can be an alias of the dest, i.e. another accepted name for it
            option = self.get_option_string_base(opt_str)
            if option:
                if opt_str.startswith(f"{option}.init_args."):
                    sub_opt = opt_str[len(f"{option}.init_args.") :]
                else:
                    sub_opt = opt_str[len(f"{option}.") :]
                val = NestedArg(key=sub_opt, val=val)
            append = isinstance(opt_str, str) and opt_str.endswith("+") and opt_str[:-1] in self.option_strings
            val = self._check_type_(val, append=append, cfg=cfg, mode=parser.parser_mode)
            if is_subclass_spec(val):
                prev_val = cfg.get(self.dest)
                if is_subclass_spec(prev_val) and "init_args" in prev_val:
                    ActionTypeHint.discard_init_args_on_class_path_change(
                        self,
                        prev_val.init_args,
                        val.get("init_args"),
                    )
        cfg.update(val, self.dest)
        return None

    def get_option_string_base(self, opt_str) -> str | None:
        """Returns the option string of which opt_str is a sub-option, e.g. '--x' for '--x.y'."""
        if not isinstance(opt_str, str):
            return None
        return next((o for o in self.option_strings if opt_str.startswith(f"{o}.")), None)

    def _check_type(self, value, append=False, cfg=None, mode=None):
        islist = _is_action_value_list(self)
        if not islist:
            value = [value]
        for num, val in enumerate(value):
            try:
                orig_val = val
                enable_path = self._enable_path and not isinstance(val, NestedArg)
                try:
                    val, config_path = parse_value_or_config(val, enable_path=enable_path)
                except get_loader_exceptions():
                    config_path = None
                path_meta = val.pop("__path__", None) if isinstance(val, dict) else None
                # a single sub-config appended to a list becomes one more list item
                appended_subconfig = append and config_path is not None and not isinstance(val, list)

                unset_sentinel = get_parsing_setting("unset_sentinel")
                prev_val = cfg.get(self.dest) if cfg else unset_sentinel
                if prev_val is unset_sentinel and not sub_defaults.get() and is_subclass_spec(self.default):
                    prev_val = Namespace(class_path=self.default["class_path"])

                kwargs = {
                    "sub_add_kwargs": getattr(self, "sub_add_kwargs", {}),
                    "prev_val": prev_val,
                    "orig_val": orig_val,
                    "append": append,
                    "enable_path": enable_path,
                    "logger": self.logger,
                }
                try:
                    with load_config_path_context(config_path), change_to_path_dir(config_path):
                        val = adapt_typehints(val, self._typehint, **kwargs)
                except ValueError as ex:
                    if orig_val == "-" and isinstance(getattr(ex, "parent", None), PathError):
                        raise ex
                    try:
                        if isinstance(orig_val, str):
                            with load_config_path_context(config_path), change_to_path_dir(config_path):
                                val = adapt_typehints(orig_val, self._typehint, default=self.default, **kwargs)
                            ex = None
                    except ValueError:
                        if (
                            lenient_check.get()
                            and mode == "omegaconf+"
                            and isinstance(orig_val, str)
                            and "${" in orig_val
                        ):
                            ex = None
                        elif self._enable_path and config_path is None and isinstance(orig_val, str):
                            msg = f"\n- Expected a path but {orig_val} either not accessible or invalid\n- "
                            raise type(ex)(msg + str(ex)) from ex
                    if ex:
                        raise ex

                if isinstance(val, (Namespace, dict)):
                    if path_meta is not None:
                        val["__path__"] = path_meta
                    if config_path is not None:
                        val["__path__"] = config_path
                elif appended_subconfig and isinstance(val, list) and isinstance(val[-1], (Namespace, dict)):
                    val[-1]["__path__"] = config_path
                value[num] = val
            except (TypeError, ValueError) as ex:
                if self._is_valid_string(val):
                    value[num] = val
                else:
                    elem = "" if not islist else f" element {num + 1}"
                    error = indent_text(str(ex))
                    raise TypeError(f'Parser key "{self.dest}"{elem}:\n{error}') from ex
        return value if islist else value[0]

    def _is_valid_string(self, value):
        typehint = self._typehint
        return isinstance(value, str) and (
            typehint is str or (get_typehint_origin(typehint) == Union and str in typehint.__args__)
        )

    def instantiate_classes(self, value):
        islist = _is_action_value_list(self)
        if not islist:
            value = [value]
        sub_add_kwargs = getattr(self, "sub_add_kwargs", {})
        for num, val in enumerate(value):
            value[num] = adapt_typehints(
                val,
                self._typehint,
                default=self.default,
                instantiate_classes=True,
                sub_add_kwargs=sub_add_kwargs,
                logger=self.logger,
            )
        return value if islist else value[0]

    @staticmethod
    def get_class_parser(val_class, sub_add_kwargs=None, skip_args=None):
        return cached_get_class_parser(
            val_class=val_class,
            sub_add_kwargs=sub_add_kwargs,
            skip_args=skip_args,
            parent_parser=parent_parser.get(),
            nested_links=nested_links.get(),
        )

    def extra_help(self):
        extra = ""
        typehint = get_optional_arg(self._typehint)
        typehint = get_callable_return_type(typehint) or typehint
        if get_typehint_origin(typehint) is type:
            typehint = typehint.__args__[0]
        if self.is_subclass_typehint(typehint, all_subtypes=False):
            class_paths = get_all_subclass_paths(typehint)
            if class_paths:
                extra = ", known subclasses: " + ", ".join(class_paths)
        return extra

    def completer(self, prefix, **kwargs):
        """Used by argcomplete, validates value and shows expected type."""
        from ._completions import argcomplete_warn_redraw_prompt, get_files_completer

        if self.choices:
            return [str(c) for c in self.choices]
        elif self._typehint == bool:
            return ["true", "false"]
        elif is_optional(self._typehint, bool):
            return ["true", "false", "null"]
        elif is_subclass(self._typehint, Enum):
            enum = self._typehint
            return list(enum.__members__)
        elif is_optional(self._typehint, Enum):
            enum = get_optional_arg(self._typehint)
            return list(enum.__members__) + ["null"]
        elif is_optional(self._typehint, Path):
            files_completer = get_files_completer()
            return ["null"] + sorted(files_completer(prefix, **kwargs))
        elif chr(int(os.environ["COMP_TYPE"])) == "?":
            try:
                if prefix.strip() == "":
                    raise ValueError()
                self._check_type(prefix)
                msg = "value already valid, "
            except (TypeError, ValueError) + get_loader_exceptions():
                msg = "value not yet valid, "
            msg += "expected type " + type_to_str(self._typehint)
            return argcomplete_warn_redraw_prompt(prefix, msg)


def is_pathlike(typehint) -> bool:
    if get_typehint_origin(typehint) == Union:
        return any(is_pathlike(t) for t in typehint.__args__)
    return is_subclass(typehint, os.PathLike)


def is_list_pathlike(typehint) -> bool:
    typehint_origin = get_typehint_origin(typehint)
    if typehint_origin in sequence_origin_types:
        subtype = typehint.__args__[0]
        return is_pathlike(subtype)
    return False


def is_subclass_container_typehint(typehint, also_closed: bool = False) -> bool:
    """Whether a container type, e.g. list or dict, has classes as items."""
    typehint = get_unaliased_type(typehint)
    subtypehints = getattr(typehint, "__args__", None)
    if not subtypehints:
        return False
    typehint_origin = get_typehint_origin(typehint)
    if typehint_origin == Union:
        return any(is_subclass_container_typehint(s, also_closed) for s in subtypehints)
    if typehint_origin in sequence_or_mapping_origin_types:
        return any(
            ActionTypeHint.is_subclass_typehint(s, all_subtypes=False, also_closed=also_closed)
            or ActionTypeHint.is_return_subclass_typehint(s)
            or is_subclass_container_typehint(s, also_closed)
            for s in subtypehints
        )
    return False


# sentinel returned by adapt_subconfig_path when the value is not a path to a config file
not_a_subconfig_path = object()


def adapt_subconfig_path(val, typehint, adapt_kwargs):
    """Loads and adapts a sub-config when val is a path to a config file.

    Only relevant for types that expect a class, since for these a string is
    otherwise interpreted as a class path. Makes it possible for items in a
    list or dict of classes to be given as paths to sub-config files.
    """
    if not adapt_kwargs.get("enable_path") or not isinstance(val, str):
        return not_a_subconfig_path
    from ._optionals import _get_config_read_mode

    try:
        path = Path(val, mode=_get_config_read_mode())
    except TypeError:
        return not_a_subconfig_path
    try:
        with load_config_path_context(path), path.relative_path_context():
            subconfig = load_value(path.read_text())
    except get_loader_exceptions() as ex:
        raise_unexpected_value(f"Invalid content in sub-config file {val}: {ex}", exception=ex)
    with load_config_path_context(path), change_to_path_dir(path):
        val = adapt_typehints(subconfig, typehint, **adapt_kwargs)
    if isinstance(val, (Namespace, dict)):
        val["__path__"] = path
    return val


def raise_unexpected_value(message: str, val: Any = inspect._empty, exception: Exception | None = None) -> NoReturn:
    if val is not inspect._empty:
        message += f". Got value: {val}"
    raise ValueError(message) from exception


def raise_union_unexpected_value(subtypes, val: Any, exceptions: list[Exception]) -> NoReturn:
    str_exceptions = [indent_text(str(e), first_line=False) for e in exceptions]
    errors = indent_text("- " + "\n- ".join(str_exceptions))
    errors = errors.replace(f". Got value: {val}", "").replace(f" {val} ", " ")
    raise ValueError(
        f"Does not validate against any of the Union subtypes\nSubtypes: {subtypes}"
        f"\nErrors:\n{errors}\nGiven value type: {type(val)}\nGiven value: {val}"
    ) from exceptions[0]


def resolve_forward_ref(ref, global_vars=None):
    if not isinstance(ref, ForwardRef) or not ref.__forward_module__:
        return ref

    aliases = __builtins__.copy()
    aliases.update(vars(import_module(ref.__forward_module__)))
    if global_vars:
        aliases.update(global_vars)
    return aliases.get(ref.__forward_arg__, ref)


unresolved_reason = "failed to resolve, e.g. a missing import or a typo"
unsupported_reason = "not a supported type"
unrebuildable_reason = "could not be rebuilt with its unvalidatable subtypes replaced"


class UnvalidatedType:
    """Type hint that stands in for one that can't be validated, accepting any value.

    A type hint can't be validated when it fails to resolve, e.g. a missing
    import or a typo in a postponed annotation, or an unsupported type.
    Instances are used as the type hint, keeping what the source code has, such
    that the help shows it as Unvalidated<...>.
    """

    def __init__(self, typehint, reason: str = unresolved_reason):
        self.reason = reason
        if isinstance(typehint, ForwardRef):
            self.name = typehint.__forward_arg__
        elif isinstance(typehint, str):
            self.name = typehint
        elif isinstance(typehint, TypeVar):
            self.name = typehint.__name__  # the str of a TypeVar has a ~ prefix
        elif inspect.isclass(typehint):
            self.name = f"{typehint.__module__}.{typehint.__qualname__}"  # the str of a class has a <class ...> wrap
        else:
            # unresolved subtypes are kept as ForwardRef or str, named here as in the source code
            name = re.sub(r"ForwardRef\('([^']*)'\)", r"\1", str(typehint))
            self.name = re.sub(r"'([^']*)'", r"\1", name)

    def __call__(self):
        """Not called, only needed because python<3.11 requires the args of e.g. Optional to be callable."""

    def __repr__(self):
        # module names stripped as done by type_to_str, which otherwise would mangle this repr
        return f"Unvalidated<{strip_module_names(self.name)}>"

    def __eq__(self, other):
        return isinstance(other, UnvalidatedType) and other.name == self.name

    def __hash__(self):
        return hash((UnvalidatedType, self.name))


def accepts_any_value(typehint) -> bool:
    """Whether a type hint accepts any value, i.e. it does not validate."""
    return typehint is object or typehint == Any or isinstance(typehint, UnvalidatedType)


def keep_subtype_as_is(subtype, typehint_origin) -> bool:
    """Whether a subtype is never replaced, mirroring the exceptions that is_supported_typehint makes."""
    return (
        subtype is NoneType
        or subtype is Ellipsis
        or (typehint_origin is type and isinstance(subtype, TypeVar))
        or (isinstance(subtype, type) and subtype in leaf_types)
    )


def replace_unvalidatable_typehints(typehint, unvalidated: list | None = None, replace_unsupported: bool = True):
    """Replaces the parts of a type hint that can't be validated with UnvalidatedType.

    A type hint can't be validated when it fails to resolve, i.e. a postponed
    annotation that remains a string or a ForwardRef, or when it is not
    supported. Replacing only these parts with a type hint that accepts any
    value keeps the parameter usable, though without validation. What can't be
    validated is kept so that the help shows it, making it evident that the
    value is not validated as the type in the code. The instances that replace
    it are appended to the given unvalidated list.
    """

    def replaced(typehint, reason):
        unvalidatable = UnvalidatedType(typehint, reason)
        if unvalidated is not None:
            unvalidated.append(unvalidatable)
        return unvalidatable

    if isinstance(typehint, (str, ForwardRef)):
        return replaced(typehint, unresolved_reason)
    typehint_origin = get_typehint_origin(typehint)
    if typehint_origin in literal_types:
        return typehint  # the args of a Literal are values, not types
    args = getattr(typehint, "__args__", None)
    # only a tuple, since e.g. types.UnionType and types.GenericAlias have __args__ as a
    # class level slot descriptor, which is truthy but not the subtypes of an instance
    if isinstance(args, tuple) and args:
        # Subtypes are only validated when the origin is a supported container type. For the
        # others, e.g. a user defined generic, the subtypes are not used for validation, so
        # only the unresolved ones are replaced, keeping the type hint as in the source code.
        sub_replace_unsupported = replace_unsupported and typehint_origin in root_types
        new_args = tuple(
            a
            if keep_subtype_as_is(a, typehint_origin)
            else replace_unvalidatable_typehints(a, unvalidated, sub_replace_unsupported)
            for a in args
        )
        if new_args != args:
            rebuilt = rebuild_typehint_args(typehint, new_args)
            if rebuilt is typehint:
                return replaced(typehint, unrebuildable_reason)
            return rebuilt
    if replace_unsupported and not ActionTypeHint.is_supported_typehint(typehint, full=True):
        return replaced(typehint, unsupported_reason)
    return typehint


def resolve_module_annotations(module: str, annotations: dict, global_vars: dict, logger=None) -> dict:
    # A holder class is used so that only the given annotations are resolved, and with the
    # names of a single module, which are given as localns to take precedence over the ones
    # that get_type_hints takes from the module of each forward reference.
    holder = type("holder", (), {"__annotations__": annotations, "__module__": module})
    try:
        # Resolves forward references (e.g. from "from __future__ import annotations"),
        # while include_extras keeps the Required/NotRequired wrappers.
        return get_type_hints(holder, None, global_vars, include_extras=True)
    except Exception as ex:
        if logger:
            logger.debug(f"Failed to resolve the annotations {list(annotations)} from {module}", exc_info=ex)
    # A single annotation failing (e.g. a missing import or a typo) makes the resolution
    # of all of them fail. Thus, resolve one by one to keep the ones that do work.
    return {k: resolve_forward_ref(v, global_vars) for k, v in annotations.items()}


def is_typed_dict(typehint) -> bool:
    """Whether a type hint is a TypedDict, including a subscripted generic one."""
    return type(get_typed_dict_type(typehint)) in typed_dict_meta_types


def get_typed_dict_type(typehint):
    """Returns the TypedDict that a subscripted generic TypedDict stands for, or the type hint unchanged.

    A subscripted generic TypedDict, is a generic alias through which the keys
    can't be looked up. Its type parameters don't change the keys, only the
    types of the ones annotated with a TypeVar, see get_typed_dict_type_var_maps.
    """
    # __origin__ used directly, since get_typehint_origin is more costly and only
    # differs for types that are never a TypedDict, e.g. it maps one to dict
    origin = getattr(typehint, "__origin__", None)
    return origin if type(origin) in typed_dict_meta_types else typehint


def get_type_var_map(typehint, generic) -> dict:
    """Returns the map from the TypeVars of a generic to the types that it is subscripted with."""
    if generic is typehint:
        return {}
    parameters = getattr(generic, "__parameters__", None) or ()
    args = getattr(typehint, "__args__", None) or ()
    return dict(zip(parameters, args))


def get_typed_dict_type_var_maps(typehint) -> dict:
    """Returns the map from each key of a generic TypedDict to the TypeVar substitutions that apply to it.

    A key inherited from a base is substituted with what the base is
    subscripted with, e.g. ``class Sub(Base[int])``, composed with the
    substitutions of the subclass, e.g. ``class Sub(Base[T])`` used as
    ``Sub[int]``. Thus, the same TypeVar can stand for a different type
    depending on the key in which it is used, so a map per key is needed.
    """
    typed_dict = get_typed_dict_type(typehint)
    type_var_map = get_type_var_map(typehint, typed_dict)
    type_var_maps = {}
    for base in getattr(typed_dict, "__orig_bases__", ()):
        if is_typed_dict(base):
            for key, base_map in get_typed_dict_type_var_maps(base).items():
                base_map = {var: substitute_type_vars(sub, type_var_map) for var, sub in base_map.items()}
                type_var_maps[key] = base_map
    for key in typed_dict.__annotations__:
        type_var_maps.setdefault(key, type_var_map)
    return type_var_maps


def substitute_type_vars(typehint, type_var_map: dict):
    """Returns the type hint with the given TypeVars replaced by the types that they stand for."""
    if not type_var_map:
        return typehint
    if isinstance(typehint, TypeVar):
        return type_var_map.get(typehint, typehint)
    args = getattr(typehint, "__args__", None)
    # only a tuple, since e.g. types.UnionType and types.GenericAlias have __args__ as a
    # class level slot descriptor, which is truthy but not the subtypes of an instance
    if not isinstance(args, tuple) or not args:
        return typehint
    new_args = tuple(substitute_type_vars(a, type_var_map) for a in args)
    if all(new is old for new, old in zip(new_args, args)):
        return typehint
    return rebuild_typehint_args(typehint, new_args)


def get_typed_dict_annotations(typed_dict, logger=None) -> dict:
    from ._postponed_annotations import get_global_vars, update_module_global_vars

    type_var_maps = get_typed_dict_type_var_maps(typed_dict)
    typed_dict = get_typed_dict_type(typed_dict)

    # Keys can be inherited from bases defined in other modules, and each key must resolve
    # with the names of the module in which it was defined, including its TYPE_CHECKING
    # blocks. Thus, the keys are grouped by module and resolved one group at a time, such
    # that the names of one module never shadow the names of another. The modules are taken
    # from the forward references because a TypedDict does not keep its bases in __mro__,
    # and __orig_bases__ is not available in all supported python versions.
    keys_per_module: dict[str, dict] = {}
    for key, annotation in typed_dict.__annotations__.items():
        module = getattr(annotation, "__forward_module__", None)
        module = getattr(module, "__name__", module)
        if not isinstance(module, str):
            module = typed_dict.__module__
        keys_per_module.setdefault(module, {})[key] = annotation

    annotations: dict = {}
    for module, module_annotations in keys_per_module.items():
        if module == typed_dict.__module__:
            global_vars = get_global_vars(typed_dict, logger)
        else:
            global_vars = {}
            update_module_global_vars(module, global_vars, logger)
        annotations.update(resolve_module_annotations(module, module_annotations, global_vars, logger))
    return {k: resolve_typed_dict_key_type_vars(annotations[k], type_var_maps[k]) for k in typed_dict.__annotations__}


def resolve_typed_dict_key_type_vars(annotation, type_var_map: dict):
    """Returns the annotation of a TypedDict key with the TypeVars in it resolved.

    First the TypeVars that the subscript binds are substituted, then the ones
    that it doesn't are replaced by what they stand for, i.e. their default,
    constraints or bound. A TypeVar that stands for nothing is left as is, so
    that it becomes an Unvalidated<...>, the same as for a signature parameter.
    """
    return replace_type_vars(substitute_type_vars(annotation, type_var_map))


def get_typed_dict_required_keys(typed_dict, annotations: dict) -> set:
    typed_dict = get_typed_dict_type(typed_dict)
    # The totality of each class (including inheritance) is reflected in __required_keys__,
    # even when the annotations are postponed. Required and NotRequired instead may not be
    # reflected there (e.g. below Python 3.11 or with postponed annotations), so they are
    # adjusted based on the resolved annotations.
    required_keys = set(getattr(typed_dict, "__required_keys__", set(annotations)))
    required_keys.update({k for k, v in annotations.items() if get_typehint_origin(v) in required_types})
    required_keys.difference_update({k for k, v in annotations.items() if get_typehint_origin(v) in not_required_types})
    return required_keys


def get_typed_dict_key_type(annotation):
    # Required and NotRequired only change the requiredness of a key, not its type
    if get_typehint_origin(annotation) in not_required_required_types:
        return annotation.__args__[0]
    return annotation


def is_typed_dict_subtype(subtype, typed_dict, logger=None) -> bool:
    # TypedDicts don't support issubclass, so as specified in PEP 589 the check is done
    # structurally, i.e. the subtype must have all keys of the typed dict, with the same
    # types and requiredness.
    if not is_typed_dict(subtype):
        return False
    if subtype is typed_dict:
        return True
    annotations = get_typed_dict_annotations(typed_dict, logger)
    sub_annotations = get_typed_dict_annotations(subtype, logger)
    for key, annotation in annotations.items():
        if key not in sub_annotations:
            return False
        if get_typed_dict_key_type(sub_annotations[key]) != get_typed_dict_key_type(annotation):
            return False
    required_keys = get_typed_dict_required_keys(typed_dict, annotations)
    sub_required_keys = get_typed_dict_required_keys(subtype, sub_annotations)
    return required_keys == sub_required_keys & annotations.keys()


def is_importable_module_path(val) -> bool:
    """Whether a value is the import path of a module, checked without importing it.

    Only the parent packages of the module get imported, which is unavoidable
    since they are the ones that know how to find their submodules.
    """
    if not isinstance(val, str) or not all(p.isidentifier() for p in val.split(".")):
        return False
    if val in sys.modules:
        return True
    try:
        return find_spec(val) is not None
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


type_expression_types = {UnionType: "UnionType", GenericAlias: "GenericAlias"}


def resolve_type_expression_node(node):
    """Returns the type that an ast node of a type expression represents."""
    if isinstance(node, ast.Constant):
        return NoneType if node.value is None else node.value
    if isinstance(node, ast.Name):
        for namespace in (builtins, typing):
            if hasattr(namespace, node.id):
                return getattr(namespace, node.id)
        raise ValueError(f"Not a builtin or typing name: {node.id}")
    if isinstance(node, ast.Attribute):
        return import_object(ast.unparse(node))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return resolve_type_expression_node(node.left) | resolve_type_expression_node(node.right)
    if isinstance(node, ast.Subscript):
        return resolve_type_expression_node(node.value)[resolve_type_expression_node(node.slice)]
    if isinstance(node, ast.Tuple):
        return tuple(resolve_type_expression_node(e) for e in node.elts)
    if isinstance(node, ast.List):
        return [resolve_type_expression_node(e) for e in node.elts]
    raise ValueError(f"Unsupported type expression: {ast.unparse(node)}")


def str_to_type_expression(val: str):
    """Returns the type that a string type expression represents, e.g. ``"int | str"``.

    The expression is resolved from its ast instead of being evaluated, such that only
    names, dot import paths, unions and subscripts are accepted, i.e. no arbitrary code.
    """
    if not isinstance(val, str):
        raise ValueError(f"Expected a string, got {type(val)}")
    return resolve_type_expression_node(ast.parse(val, mode="eval").body)


def adapt_typehints(
    val,
    typehint,
    serialize=False,
    instantiate_classes=False,
    prev_val=None,
    orig_val=None,
    append=False,
    enable_path=False,
    sub_add_kwargs=None,
    default=None,
    logger=None,
):
    # A module import path equal to the default still needs to be imported on instantiation
    if type(val) in {str, bool, int, float} and val == default and not (instantiate_classes and typehint is ModuleType):
        return val

    adapt_kwargs = {
        "serialize": serialize,
        "instantiate_classes": instantiate_classes,
        "prev_val": prev_val,
        "orig_val": orig_val,
        "append": append,
        "enable_path": enable_path,
        "sub_add_kwargs": sub_add_kwargs or {},
        "logger": logger,
    }
    subtypehints = getattr(typehint, "__args__", None)
    typehint_origin = get_typehint_origin(typehint) or typehint
    if type(typehint_origin) in typed_dict_meta_types:
        # a subscripted generic TypedDict is validated as its unsubscripted form, see get_typed_dict_type
        subtypehints = None
        typehint_origin = dict
    unset_sentinel = get_parsing_setting("unset_sentinel")

    # Any, object and unvalidated, i.e. no validation
    if accepts_any_value(typehint):
        type_val = type(val)
        if get_registered_type(type_val) or is_subclass(type_val, Enum):
            if not serialize:  # when serializing this is done by serialize_unvalidated
                val = adapt_typehints(val, type_val, **adapt_kwargs)
        elif isinstance(val, str):
            with suppress(*get_loader_exceptions()):
                val, _ = parse_value_or_config(val, enable_path=False, simple_types=True)
        val = adapt_classes_any(val, typehint, serialize, instantiate_classes, sub_add_kwargs, logger)
        if serialize:
            val = serialize_unvalidated(val, adapt_kwargs)

    # Literal
    elif typehint_origin in literal_types:
        if val not in subtypehints and isinstance(val, str):
            subtypes = tuple(type(v) for v in subtypehints if type(v) is not str)
            if subtypes:
                val = adapt_typehints(val, Union[subtypes], **adapt_kwargs)
        if val not in subtypehints:
            raise_unexpected_value(f"Expected a {typehint}", val)

    # Basic types
    elif typehint in leaf_types:
        if isinstance(val, str) and typehint is not str:
            with suppress(*json_or_yaml_loader_exceptions):
                val = basic_json_or_yaml_load(val)
        if typehint is float and isinstance(val, int) and not isinstance(val, bool):
            val = float(val)
        if not isinstance(val, typehint) or (typehint in (int, float) and isinstance(val, bool)):
            raise_unexpected_value(f"Expected a {typehint}", val)

    # Annotated
    elif is_annotated(typehint):
        if not serialize and is_annotated_validator(typehint):
            try:
                val = validate_annotated(val, typehint)
            except Exception as ex:
                raise_unexpected_value(str(ex), val, ex)
        else:
            val = adapt_typehints(val, typehint_origin, **adapt_kwargs)

    # Registered types
    elif get_registered_type(typehint):
        registered_type = get_registered_type(typehint)
        if serialize:
            val = registered_type.serializer(val)
        elif not serialize and not registered_type.is_value_of_type(val):
            val = registered_type.deserializer(val)

    # Enum
    elif is_subclass(typehint, Enum):
        if serialize:
            if isinstance(val, typehint):
                val = val.name
        elif not isinstance(val, typehint):
            try:
                val = typehint[val]
            except KeyError as ex:
                raise_unexpected_value(
                    f"Expected a member of {typehint}: {iter_to_set_str(typehint.__members__)}", val, ex
                )

    # Type
    elif typehint in {Type, type} or typehint_origin in {Type, type}:
        if serialize:
            val = object_path_serializer(val)
        elif not serialize and not isinstance(val, type):
            path = val
            val = import_object(val)
            if typehint in {Type, type} or accepts_any_value(subtypehints[0]):
                valid = isinstance(val, type)
            elif is_typed_dict(subtypehints[0]):
                valid = is_typed_dict_subtype(val, subtypehints[0], logger)
            else:
                valid = is_subclass(val, subtypehints[0])
            if not valid:
                raise_unexpected_value(f"Expected an import path corresponding to a {typehint}", path)

    # Module
    elif typehint is ModuleType:
        if isinstance(val, ModuleType):
            if serialize:
                val = val.__name__
        elif not is_importable_module_path(val):
            raise_unexpected_value("Expected an import path corresponding to a module", val)
        elif instantiate_classes:
            val = import_module(val)

    # UnionType and GenericAlias
    elif typehint in type_expression_types:
        if isinstance(val, typehint):
            if serialize:
                val = str(val)
        else:
            expected = f"Expected a string with a {type_expression_types[typehint]} type expression"
            try:
                type_expression = str_to_type_expression(val)
            except Exception as ex:
                raise_unexpected_value(expected, val, ex)
            if not isinstance(type_expression, typehint):
                raise_unexpected_value(expected, val)
            if not serialize:
                val = type_expression

    # Union
    elif typehint_origin == Union:
        vals = []
        sorted_subtypes = sort_subtypes_for_union(subtypehints, val, prev_val, append)
        for subtype in sorted_subtypes:
            try:
                vals.append(adapt_typehints(val, subtype, **adapt_kwargs))
                break
            except Exception as ex:
                if subtype is str and not isinstance(val, str) and isinstance(orig_val, str):
                    vals.append(orig_val)
                    continue
                vals.append(ex)
        if all(isinstance(v, Exception) for v in vals):
            raise_union_unexpected_value(sorted_subtypes, val, vals)
        val = next((v for v in reversed(vals) if not isinstance(v, Exception)))

    # Tuple or Set
    elif typehint_origin in tuple_set_origin_types:
        if not isinstance(val, (list, tuple, set, frozenset)):
            raise_unexpected_value(f"Expected a {typehint_origin}", val)
        val = list(val)
        if subtypehints is not None:
            is_tuple = typehint_origin in {Tuple, tuple}
            is_ellipsis = is_ellipsis_tuple(typehint)
            if is_tuple and not is_ellipsis and len(val) != len(subtypehints):
                raise_unexpected_value(f"Expected a tuple with {len(subtypehints)} elements", val)
            for n, v in enumerate(val):
                subtypehint = subtypehints[0 if is_ellipsis or not is_tuple else n]
                val[n] = adapt_typehints(v, subtypehint, **adapt_kwargs)
        if not serialize:
            if typehint_origin in {Tuple, tuple}:
                val = tuple(val)
            elif typehint_origin is frozenset:
                val = frozenset(val)
            else:
                val = set(val)

    # List, Iterable or Sequence
    elif typehint_origin in sequence_origin_types:
        if append:
            adapt_kwargs.pop("prev_val")
            if prev_val is unset_sentinel:
                prev_val = []
            elif not isinstance(prev_val, list):
                try:
                    prev_val = [adapt_typehints(prev_val, subtypehints[0], **adapt_kwargs)]
                except Exception:
                    prev_val = []
            val_is_list = isinstance(val, list)
            val = prev_val + (val if val_is_list else [val])
            prev_val = prev_val + [None] * (len(val) - len(prev_val) if val_is_list else 1)
        list_path = None
        if enable_path and type(val) is str:
            if validating_defaults.get():
                return val
            with suppress(TypeError):
                from ._optionals import _get_config_read_mode

                list_path = Path(val, mode=_get_config_read_mode())
                val = list_path.read_text().splitlines()
        if isinstance(val, NestedArg) and subtypehints is not None:
            val = (prev_val[:-1] if isinstance(prev_val, list) else []) + [val]
        elif isinstance(val, Iterable) and not isinstance(val, (list, str)) and type(val) not in mapping_origin_types:
            val = list(val)
        elif not isinstance(val, list):
            raise_unexpected_value(f"Expected a {typehint_origin}", val)
        if subtypehints is not None:
            for n, v in enumerate(val):
                if isinstance(prev_val, list) and len(prev_val) == len(val):
                    adapt_kwargs_n = {**deepcopy(adapt_kwargs), "prev_val": prev_val[n]}
                else:
                    adapt_kwargs_n = deepcopy(adapt_kwargs)
                with change_to_path_dir(list_path):
                    val[n] = adapt_typehints(v, subtypehints[0], **adapt_kwargs_n)
        if typehint_origin is deque:
            val = list(val) if serialize else deque(val)

    # Dict, Mapping
    elif typehint_origin in mapping_origin_types:
        if not serialize and not instantiate_classes:
            validate_subclass_spec_in_mapping(val, typehint, subtypehints, sub_add_kwargs, logger)
        if isinstance(val, NestedArg):
            if isinstance(prev_val, dict):
                if isinstance(val.key, str) and "." in val.key:
                    key_prefix, key_suffix = val.key.split(".", 1)
                    val = {**prev_val, key_prefix: {key_suffix: val.val}}
                else:
                    val = {**prev_val, val.key: val.val}
            else:
                val = {val.key: val.val}
        elif isinstance(val, MappingProxyType):
            val = dict(val)
        elif not isinstance(val, dict):
            raise_unexpected_value(f"Expected a {typehint_origin}", val)
        if subtypehints is not None:
            if subtypehints[0] == int:
                cast = str if serialize else int
                val = {cast(k): v for k, v in val.items()}
            for k, v in val.items():
                if "linked_targets" in adapt_kwargs["sub_add_kwargs"]:
                    kwargs = deepcopy(adapt_kwargs)
                    sub_add_kwargs = kwargs["sub_add_kwargs"]
                    sub_add_kwargs["linked_targets"] = {
                        t[len(k + ".") :] for t in sub_add_kwargs["linked_targets"] if t.startswith(k + ".")
                    }
                    sub_add_kwargs["linked_targets"] = {
                        t[len("init_args.") :] if t.startswith("init_args.") else t
                        for t in sub_add_kwargs["linked_targets"]
                    }
                else:
                    kwargs = adapt_kwargs.copy()
                if kwargs.get("prev_val"):
                    if isinstance(kwargs["prev_val"], dict):
                        kwargs["prev_val"] = kwargs["prev_val"].get(k)
                    else:
                        kwargs["prev_val"] = None
                val[k] = adapt_typehints(v, subtypehints[1], **kwargs)
        if is_typed_dict(typehint):
            dict_annotations = get_typed_dict_annotations(typehint, logger)
            required_keys = get_typed_dict_required_keys(typehint, dict_annotations)
            missing_keys = required_keys - val.keys()
            if missing_keys:
                raise_unexpected_value(f"Missing required keys: {missing_keys}", val)
            extra_keys = val.keys() - dict_annotations.keys()
            if extra_keys:
                raise_unexpected_value(f"Unexpected keys: {extra_keys}", val)
            for k, v in val.items():
                # what can't be validated accepts any value, as the help shows it
                val[k] = adapt_typehints(v, replace_unvalidatable_typehints(dict_annotations[k]), **adapt_kwargs)
        if typehint_origin is MappingProxyType and not serialize:
            val = MappingProxyType(val)
        elif typehint_origin is OrderedDict:
            val = dict(val) if serialize else OrderedDict(val)

    # TypedDict NotRequired and Required
    elif typehint_origin in not_required_required_types:
        assert len(subtypehints) == 1, "(Not)Required requires a single type argument"
        val = adapt_typehints(val, subtypehints[0], **adapt_kwargs)

    # Callable
    elif (
        typehint_origin in callable_origin_types
        or typehint in callable_origin_types
        or is_instance_factory_protocol(typehint, logger)
    ):
        if serialize:
            if is_subclass_spec(val):
                val, partial_skip_args = adapt_partial_callable_class(typehint, val)
                val = adapt_class_type(val, True, False, sub_add_kwargs, partial_skip_args=partial_skip_args)
            else:
                val = object_path_serializer(val)
        else:
            adapted = adapt_subconfig_path(val, typehint, adapt_kwargs)
            if adapted is not not_a_subconfig_path:
                return adapted
            try:
                val_input = val
                if isinstance(val, str):
                    class_path = val
                    return_type = get_callable_return_type(typehint)
                    if "." not in val and return_type:
                        class_path = resolve_class_path_by_name(return_type, val)
                    val_obj = import_object(class_path)
                    if inspect.isclass(val_obj):
                        val = Namespace(class_path=class_path)
                    elif callable(val_obj):
                        val = val_obj
                    else:
                        raise ImportError(f"Unexpected import object {val_obj}")
                if isinstance(val, (dict, Namespace, NestedArg)):
                    if prev_val is unset_sentinel:
                        return_type = get_callable_return_type(typehint)
                        if return_type and not inspect.isabstract(return_type):
                            with suppress(ValueError):
                                prev_val = Namespace(class_path=get_import_path(return_type))
                    val = subclass_spec_as_namespace(val, prev_val)
                    if not is_subclass_spec(val):
                        raise ImportError(
                            f"Dict must include a class_path and optionally init_args, but got {val_input}"
                        )
                    val, partial_skip_args = adapt_partial_callable_class(typehint, val)
                    val_class = import_object(val["class_path"])
                    if inspect.isclass(val_class) and not (partial_skip_args or callable_instances(val_class)):
                        base_type = get_callable_return_type(typehint) or typehint
                        raise ImportError(
                            f"Expected '{val['class_path']}' to be a class that instantiates into callable "
                            f"or a subclass of {base_type}."
                        )
                    val["class_path"] = get_import_path(val_class)
                    val = adapt_class_type(
                        val,
                        False,
                        instantiate_classes,
                        sub_add_kwargs,
                        partial_skip_args=partial_skip_args,
                        prev_val=prev_val,
                    )
                elif not callable(val):
                    # e.g. a list, which without this would be accepted unchanged, silently
                    # preventing the resolution by other subtypes when part of a union
                    raise ImportError(f"Expected an import path or a subclass spec, but got {val_input}")
            except (ImportError, AttributeError, ArgumentError) as ex:
                raise_unexpected_value(f"Type {typehint} expects a function or a callable class: {ex}", val, ex)

    # Subclass
    elif inspect.isclass(typehint_origin):
        if is_instance_or_supports_protocol(val, typehint):
            if serialize:
                val = serialize_class_instance(val)
            return val
        if serialize and isinstance(val, str):
            return val

        adapted = adapt_subconfig_path(val, typehint, adapt_kwargs)
        if adapted is not not_a_subconfig_path:
            return adapted

        prev_implicit_defaults = False
        if prev_val is unset_sentinel and not inspect.isabstract(typehint) and not is_protocol(typehint):
            with suppress(ValueError):
                # implicit prev_val class_path
                prev_val = Namespace(class_path=get_import_path(typehint))
                if parse_kwargs.get().get("defaults") is True:
                    prev_implicit_defaults = True

        if isinstance(prev_val, (dict, Namespace)) and "class_path" not in prev_val:
            # implicit prev_val init_args
            prev_val = Namespace(class_path=None, init_args=Namespace(prev_val))

        val_input = val
        if (isinstance(prev_val, (dict, Namespace)) and prev_val["class_path"] is None) or (
            isinstance(val, NestedArg) and is_subclasses_disabled(typehint)
        ):
            class_type_path = Namespace(class_path=get_import_path(typehint))
            val = subclass_spec_as_namespace(val, class_type_path)
        else:
            val = subclass_spec_as_namespace(val, prev_val)
        if val and not is_subclass_spec(val) and "init_args" not in val:
            # implicit val class_path
            val = Namespace(class_path=get_import_path(typehint), init_args=val)

        if not is_subclass_spec(val):
            msg = "Does not implement protocol" if is_protocol(typehint) else "Not a valid subclass of"
            raise_unexpected_value(
                f"{msg} {typehint.__name__}. Got value: {val_input}\n"
                "Subclass types expect one of:\n"
                "- a class path (str)\n"
                "- a dict with class_path entry\n"
                "- a dict without class_path but with init_args entry (class path given previously)\n"
                "- a dict with parameters accepted by the base class (implicit class_path)"
            )

        try:
            class_path = resolve_class_path_by_name(typehint, val["class_path"])
            val_class = import_object(class_path)
            if is_instance_or_supports_protocol(val_class, typehint):
                return val_class  # importable instance
            if is_protocol(val_class):
                raise_unexpected_value(f"Expected an instantiatable class, but {val['class_path']} is a protocol")
            if inspect.isabstract(val_class):
                raise_unexpected_value(f"Expected an instantiatable class, but {val['class_path']} is abstract")
            if (
                is_subclasses_disabled(typehint)
                and inspect.isclass(val_class)
                and val_class is not get_generic_origin(typehint)
            ):
                raise_unexpected_value(subclasses_disabled_message(typehint, val["class_path"]))
            subclass = True
            if not is_subclass_or_implements_protocol(val_class, typehint):
                subclass = False
                if not inspect.isclass(val_class) and callable(val_class):
                    from ._postponed_annotations import get_return_type

                    return_type = get_return_type(val_class, logger)
                    if is_subclass_or_implements_protocol(return_type, typehint):
                        subclass = True
            elif prev_implicit_defaults:
                inner_parser = ActionTypeHint.get_class_parser(typehint, sub_add_kwargs)
                prev_val.init_args = inner_parser.get_defaults()
                if prev_val.class_path != class_path:
                    inner_parser = ActionTypeHint.get_class_parser(val_class, sub_add_kwargs)
                    for key in inner_parser.get_defaults().keys():
                        prev_val.init_args.pop(key, None)
            if not subclass:
                msg = "implement protocol" if is_protocol(typehint) else "correspond to a subclass of"
                raise_unexpected_value(f"Import path {val['class_path']} does not {msg} {typehint.__name__}")
            val["class_path"] = class_path
            val = adapt_class_type(
                val,
                serialize,
                instantiate_classes,
                sub_add_kwargs,
                prev_val=prev_val,
                typehint=typehint,
            )
        except (ImportError, AttributeError, AssertionError, ArgumentError) as ex:
            class_path = val if isinstance(val, str) else val["class_path"]
            error = indent_text(str(ex))
            raise_unexpected_value(f"Problem with given class_path {class_path!r}:\n{error}", exception=ex)

    # TypeAliasType -- 3.12 `type x = y` or manually via typing_extensions
    elif is_alias_type(typehint):
        return adapt_typehints(val, get_alias_target(typehint), **adapt_kwargs)

    else:
        raise RuntimeError(f"The code should never reach here: typehint={typehint}")  # pragma: no cover

    return val


protocol_irrelevant_dunder_methods = {
    "__init__",
    "__new__",
    "__del__",
    "__getattr__",
    "__getattribute__",
    "__setattr__",
    "__delattr__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
    "__subclasshook__",
}


def get_protocol_method_signature(class_type, name, logger):
    """Returns the parameters (excluding self) and return type of a method, with annotations resolved.

    In contrast to get_signature_parameters, the signature is taken as declared, i.e. ``*args`` and
    ``**kwargs`` are not resolved into the parameters that they might accept, since for protocols
    what matters is how the method can be called.
    """
    from jsonargparse._parameter_resolvers import ParamData, parameter_attributes
    from jsonargparse._postponed_annotations import evaluate_postponed_annotations, get_return_type

    method = inspect.getattr_static(class_type, name)
    skip_self = not isinstance(method, staticmethod)
    if isinstance(method, (staticmethod, classmethod)):
        method = method.__func__
    if not inspect.isfunction(method):
        raise ValueError(f"Expected {class_type.__name__}.{name} to be a function, but got {method}.")

    signature = inspect.signature(method)
    params = [ParamData(**{a: getattr(p, a) for a in parameter_attributes}) for p in signature.parameters.values()]
    evaluate_postponed_annotations(params, method, None, logger)
    return (params[1:] if skip_self else params), get_return_type(method, logger)


def type_var_wildcard_matches(proto_annotation, value_annotation) -> bool:
    """Whether two types are equal, a TypeVar in either of them matching any type.

    A generic protocol is written in terms of its own TypeVars and an
    implementation in terms of its own or of concrete types, so a TypeVar is
    compared as a wildcard, like a static type checker does. Otherwise a generic
    protocol could never be implemented.
    """
    if isinstance(proto_annotation, TypeVar) or isinstance(value_annotation, TypeVar):
        return True
    if proto_annotation == value_annotation:
        return True
    proto_origin = get_typehint_origin(proto_annotation)
    if proto_origin is None or proto_origin != get_typehint_origin(value_annotation):
        return False
    proto_args = getattr(proto_annotation, "__args__", None)
    value_args = getattr(value_annotation, "__args__", None)
    if not isinstance(proto_args, tuple) or not isinstance(value_args, tuple) or len(proto_args) != len(value_args):
        return False
    if proto_origin is Union:
        # the subtypes of a union are unordered, so each one must match some unmatched other one
        unmatched = list(value_args)
        for proto_arg in proto_args:
            match = next((v for v in unmatched if type_var_wildcard_matches(proto_arg, v)), None)
            if match is None:
                return False
            unmatched.remove(match)
        return True
    return all(type_var_wildcard_matches(p, v) for p, v in zip(proto_args, value_args))


def protocol_type_matches(proto_annotation, value_annotation, value_any_accepted: bool = False) -> bool:
    """Whether a type in an implementation is accepted for the corresponding type in a protocol."""
    if proto_annotation is inspect.Parameter.empty or proto_annotation == Any:
        return True
    if value_any_accepted and (value_annotation is inspect.Parameter.empty or value_annotation == Any):
        return True
    return type_var_wildcard_matches(proto_annotation, value_annotation)


def protocol_var_param_matches(proto_param, value_var_param) -> bool:
    """Whether an implementation *args/**kwargs can stand in for a protocol parameter."""
    return value_var_param is not None and protocol_type_matches(
        proto_param.annotation, value_var_param.annotation, value_any_accepted=True
    )


def split_signature_params(params):
    kinds = inspect.Parameter
    positional = [p for p in params if p.kind in (kinds.POSITIONAL_ONLY, kinds.POSITIONAL_OR_KEYWORD)]
    keyword_only = {p.name: p for p in params if p.kind is kinds.KEYWORD_ONLY}
    var_positional = next((p for p in params if p.kind is kinds.VAR_POSITIONAL), None)
    var_keyword = next((p for p in params if p.kind is kinds.VAR_KEYWORD), None)
    return positional, keyword_only, var_positional, var_keyword


def protocol_params_match(proto_params, value_params) -> bool:
    """Whether a method can be called in all the ways that a protocol method can be called.

    Types are required to match exactly, except when the protocol has no annotation or ``Any``, in
    which case any type in the implementation is accepted.
    """
    proto_pos, proto_kw, proto_args, proto_kwargs = split_signature_params(proto_params)
    value_pos, value_kw, value_args, value_kwargs = split_signature_params(value_params)
    empty = inspect.Parameter.empty

    # arbitrary extra arguments accepted by the protocol must also be accepted by the implementation
    if proto_args and not protocol_var_param_matches(proto_args, value_args):
        return False
    if proto_kwargs and not protocol_var_param_matches(proto_kwargs, value_kwargs):
        return False

    matched: set = set()  # indexes of value_pos already accounted for

    # parameters that the protocol accepts positionally
    for num, proto_param in enumerate(proto_pos):
        if num >= len(value_pos):
            # only *args, or *args and **kwargs when also accepted by keyword, can stand in
            if not protocol_var_param_matches(proto_param, value_args):
                return False
            if proto_param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and not protocol_var_param_matches(
                proto_param, value_kwargs
            ):
                return False
            continue
        value_param = value_pos[num]
        if proto_param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and (
            value_param.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD or value_param.name != proto_param.name
        ):
            return False  # names only irrelevant when the protocol accepts the parameter positionally only
        if not protocol_type_matches(proto_param.annotation, value_param.annotation):
            return False
        if proto_param.default is not empty and value_param.default is empty:
            return False
        matched.add(num)

    # parameters that the protocol only accepts by keyword
    for name, proto_param in proto_kw.items():
        value_param = value_kw.get(name)
        if value_param is None:
            # a parameter accepted both positionally and by keyword also works
            num = next(
                (
                    n
                    for n, p in enumerate(value_pos)
                    if p.name == name and n not in matched and p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
                ),
                None,
            )
            if num is None:
                if not protocol_var_param_matches(proto_param, value_kwargs):
                    return False
                continue
            value_param = value_pos[num]
            matched.add(num)
        if not protocol_type_matches(proto_param.annotation, value_param.annotation):
            return False
        if proto_param.default is not empty and value_param.default is empty:
            return False

    # parameters only in the implementation must be optional and accept what the protocol might give
    for num, value_param in enumerate(value_pos):
        if num in matched:
            continue
        if value_param.default is empty:
            return False
        if proto_args and not protocol_type_matches(proto_args.annotation, value_param.annotation):
            return False
    return all(p.default is not empty for n, p in value_kw.items() if n not in proto_kw)


def implements_protocol(value, protocol) -> bool:
    if not inspect.isclass(value) or value is object or not is_protocol(protocol):
        return False
    origin = get_protocol_origin(protocol)
    type_var_map = get_type_var_map(protocol, origin)
    protocol = origin

    logger = parse_logger(True, "implements_protocol")
    members = 0
    for name, _ in inspect.getmembers(protocol, predicate=inspect.isfunction):
        is_dunder = name.startswith("__") and name.endswith("__")
        if (not is_dunder and name.startswith("_")) or (is_dunder and name in protocol_irrelevant_dunder_methods):
            continue
        if not hasattr(value, name):
            return False
        members += 1
        try:
            value_params, value_return = get_protocol_method_signature(value, name, logger)
        except (ValueError, TypeError):
            return False
        proto_params, proto_return = get_protocol_method_signature(protocol, name, logger)
        # a subscripted generic protocol is implemented by what its type arguments say,
        # e.g. Proto[int] by a run(self, x: int), the same as static type checkers do
        for param in proto_params:
            param.annotation = substitute_type_vars(param.annotation, type_var_map)
        proto_return = substitute_type_vars(proto_return, type_var_map)
        if not protocol_params_match(proto_params, value_params):
            return False
        if not protocol_type_matches(proto_return, value_return):
            return False
    return True if members else False


def is_protocol(class_type) -> bool:
    return getattr(class_type, "_is_protocol", False)


def get_protocol_origin(protocol):
    """Returns the protocol that a subscripted generic protocol stands for.

    A subscripted generic protocol, e.g. ``Proto[int]``, is a generic alias
    through which the members can't be looked up. What it is subscripted with
    is given by get_type_var_map, see implements_protocol.
    """
    origin = getattr(protocol, "__origin__", None)
    return origin if is_protocol(origin) else protocol


def is_subclass_or_implements_protocol(value, class_type) -> bool:
    if is_protocol(class_type):
        return implements_protocol(value, class_type)
    return is_subclass(value, class_type)


def is_instance_or_supports_protocol(value, class_type):
    if is_protocol(class_type):
        return is_subclass_or_implements_protocol(value.__class__, class_type)
    return is_instance(value, class_type)


def get_protocol_call_return_type(protocol, logger=None):
    """Returns the return type of the ``__call__`` of a protocol, with its TypeVars substituted."""
    from ._postponed_annotations import get_return_type

    origin = get_protocol_origin(protocol)
    # the __call__ of the origin, since for a subscripted generic protocol the alias has its own
    return_type = get_return_type(origin.__call__, logger)
    return substitute_type_vars(return_type, get_type_var_map(protocol, origin))


def is_instance_factory_protocol(class_type, logger=None):
    if not is_protocol(class_type) or not callable_instances(get_protocol_origin(class_type)):
        return False
    return ActionTypeHint.is_subclass_typehint(get_protocol_call_return_type(class_type, logger))


_subclass_spec_keys = {"class_path", "init_args", "dict_kwargs", "__path__", subclasses_disabled_meta_key}


def is_subclass_spec(val):
    if isinstance(val, Namespace):
        keys = val.__dict__.keys()  # only the top level keys of the namespace
    elif isinstance(val, dict):
        keys = val.keys()
    else:
        return False
    return "class_path" in keys and len(set(keys) - _subclass_spec_keys) == 0


def subclass_spec_as_namespace(val, prev_val=None):
    if not isinstance(val, (str, dict, Namespace, NestedArg)):
        return None
    if isinstance(val, str):
        return Namespace(class_path=val)
    if isinstance(val, NestedArg):
        key, val = val
        if "." not in key:
            root_key = key
        else:
            if key.startswith("dict_kwargs."):
                root_key = "dict_kwargs"
                key = key[len("dict_kwargs.") :]
                val = {key: val}
            else:
                root_key = "init_args"
                val = NestedArg(key=key, val=val)
        val = Namespace({root_key: val})
        if isinstance(prev_val, str):
            prev_val = Namespace(class_path=prev_val)
    if isinstance(val, dict):
        val = Namespace(val)
    if "init_args" in val and isinstance(val["init_args"], dict):
        val["init_args"] = Namespace(val["init_args"])
    if not is_subclass_spec(val) and isinstance(prev_val, (Namespace, dict)) and "class_path" in prev_val:
        if "init_args" in val or "dict_kwargs" in val:
            val["class_path"] = prev_val["class_path"]
        else:
            val = Namespace(class_path=prev_val["class_path"], init_args=val)
    return val


def get_callable_return_type(typehint):
    return_type = None
    if is_instance_factory_protocol(typehint):
        return_type = get_protocol_call_return_type(typehint)
    elif get_typehint_origin(typehint) in callable_origin_types:
        args = getattr(typehint, "__args__", None)
        if isinstance(args, tuple) and len(args) > 0:
            return_type = args[-1]
    return return_type


def is_single_class_type(typehint, typehint_origin, closed_class):
    if not (
        (
            (inspect.isclass(typehint) and typehint_origin is None)
            or (is_generic_class(typehint) and inspect.isclass(typehint.__origin__))
        )
        and typehint not in leaf_or_root_types
        and not is_typed_dict(typehint)
        and not get_registered_type(typehint)
        and not is_pydantic_type(typehint)
        and not is_subclass(typehint, (Path, Enum))
        and getattr(typehint_origin, "__module__", "") != "builtins"
    ):
        return False
    if not closed_class:
        return not is_subclasses_disabled(typehint)
    return True


is_single_subclass_type = partial(is_single_class_type, closed_class=False)
is_single_subclass_or_closed_type = partial(is_single_class_type, closed_class=True)


def yield_class_types(typehint, is_single, also_lists=False, callable_return=False):
    typehint = typehint_from_action(typehint)
    if typehint is None:
        return
    typehint = get_unaliased_type(get_optional_arg(get_unaliased_type(typehint)))
    typehint_origin = get_typehint_origin(typehint)
    kwargs = {"is_single": is_single, "also_lists": also_lists, "callable_return": callable_return}
    if callable_return and (typehint_origin in callable_origin_types or is_instance_factory_protocol(typehint)):
        return_type = get_callable_return_type(typehint)
        if return_type:
            yield from yield_class_types(return_type, **kwargs)
    elif typehint_origin == Union or (also_lists and typehint_origin in sequence_origin_types):
        for subtype in typehint.__args__:
            yield from yield_class_types(subtype, **kwargs)
    if is_single(typehint, typehint_origin):
        if is_typed_dict(typehint):
            # a subscripted generic TypedDict is yielded as is, since its keys are
            # resolved from it, substituting what it is subscripted with
            yield typehint
        else:
            # a subscripted user defined generic, e.g. Strategy[T], is yielded as its origin
            # class, since the consumers use the class itself, e.g. to look up its subclasses
            yield get_generic_origin(typehint)


def get_subclass_types(typehint, also_lists=False, callable_return=False):
    types = tuple(
        yield_class_types(
            typehint, is_single=is_single_subclass_type, also_lists=also_lists, callable_return=callable_return
        )
    )
    return types or None


def get_subclass_or_closed_types(typehint, also_lists=False, callable_return=False):
    types = tuple(
        yield_class_types(
            typehint,
            is_single=is_single_subclass_or_closed_type,
            also_lists=also_lists,
            callable_return=callable_return,
        )
    )
    return types or None


def is_single_help_type(typehint, typehint_origin):
    return is_typed_dict(typehint) or is_single_subclass_or_closed_type(typehint, typehint_origin)


def get_help_types(typehint):
    """Types in a type hint for which a --*.help option shows the accepted arguments."""
    types = tuple(yield_class_types(typehint, is_single=is_single_help_type, also_lists=True, callable_return=True))
    return types or None


def get_subclass_names(typehint, callable_return=False):
    return tuple(
        t.__name__
        for t in yield_class_types(typehint, is_single=is_single_subclass_type, callable_return=callable_return)
    )


def adapt_partial_callable_class(callable_type, subclass_spec):
    partial_skip_args = None
    return_type = get_callable_return_type(callable_type)
    if return_type:
        subclass_types = get_subclass_types(return_type)
        class_type = import_object(resolve_class_path_by_name(return_type, subclass_spec.class_path))
        if subclass_types and is_subclass(class_type, subclass_types):
            subclass_spec = subclass_spec.clone()
            subclass_spec["class_path"] = get_import_path(class_type)
            if is_protocol(callable_type):
                from ._parameter_resolvers import get_signature_parameters

                params = get_signature_parameters(callable_type, "__call__")
                partial_skip_args = set()
                positionals = [p for p in params if "POSITIONAL_ONLY" in str(p.kind)]
                if positionals:
                    partial_skip_args.add(len(positionals))
                partial_skip_args.update(p.name for p in params if "POSITIONAL_ONLY" not in str(p.kind))
            else:
                partial_skip_args = {len(callable_type.__args__) - 1}
    return subclass_spec, partial_skip_args


def get_all_subclass_paths(cls: type, include_abstract: bool = False) -> list[str]:
    subclass_list = []

    def is_local(cl):
        return ".<locals>." in getattr(cl, "__qualname__", ".<locals>.")

    def is_private(class_path):
        return "._" in class_path

    def add_subclasses(cl):
        if hasattr(cl, "__args__") and get_typehint_origin(cl) in sequence_origin_types.union({Union}):
            for arg in cl.__args__:
                add_subclasses(arg)
            return
        try:
            class_path = get_import_path(cl)
        except (ImportError, AttributeError) as err:  # Attribute is added in case of dot notation imports
            warning(f"Hit failing import with following error: {err}")
            return
        if is_local(cl) or is_subclass(cl, _LazyInitBaseClass):
            return
        if not ((inspect.isabstract(cl) and not include_abstract) or is_private(class_path) or is_protocol(cl)):
            if class_path in subclass_list:
                return
            subclass_list.append(class_path)
        for subclass in cl.__subclasses__() if hasattr(cl, "__subclasses__") else []:
            add_subclasses(subclass)

    if get_typehint_origin(cls) in callable_origin_types:
        cls = cls.__args__[-1]  # type: ignore[attr-defined]

    if get_typehint_origin(cls) in {Union, Type, type}:
        for arg in cls.__args__:  # type: ignore[union-attr]
            if ActionTypeHint.is_subclass_typehint(arg, also_lists=True) and arg not in {object, type}:
                add_subclasses(arg)
    else:
        add_subclasses(cls)

    return subclass_list


def resolve_class_path_by_name(cls: type | tuple[type], name: str) -> str:
    class_path = name
    if "." not in class_path:
        if isinstance(cls, tuple):
            for cls_n in cls:
                class_path = resolve_class_path_by_name(cls_n, name)
                if "." in class_path:
                    break
            return class_path

        def get_subclass_dict(include_abstract: bool) -> dict:
            subclass_dict = defaultdict(list)
            for subclass in get_all_subclass_paths(cls, include_abstract=include_abstract):
                subclass_name = subclass.rsplit(".", 1)[1]
                subclass_dict[subclass_name].append(subclass)
            return subclass_dict

        subclass_dict = get_subclass_dict(include_abstract=False)
        if name not in subclass_dict:
            # abstract classes are not valid choices, but resolving them gives a more informative error
            subclass_dict = get_subclass_dict(include_abstract=True)
        if name in subclass_dict:
            name_subclasses = subclass_dict[name]
            if len(name_subclasses) > 1:
                raise ValueError(
                    f"Multiple subclasses with name {name}. Give the full class path to "
                    f"avoid ambiguity: {', '.join(name_subclasses)}."
                )
            class_path = name_subclasses[0]
    return class_path


def normalize_import_path(class_path, typehint):
    if "." not in class_path:
        class_path = resolve_class_path_by_name(typehint, class_path)
    return get_import_path(import_object(class_path))


dump_kwargs: ContextVar = ContextVar("dump_kwargs", default={})


@contextmanager
def dump_kwargs_context(kwargs):
    dump_kwargs.set(kwargs if kwargs else {})
    yield


def discard_init_args_on_class_path_change(parser_or_action, prev_val, value):
    if prev_val and "init_args" in prev_val and prev_val["class_path"] != value["class_path"]:
        parser = parser_or_action
        if isinstance(parser_or_action, ActionTypeHint):
            sub_add_kwargs = getattr(parser_or_action, "sub_add_kwargs", {})
            parser = ActionTypeHint.get_class_parser(value["class_path"], sub_add_kwargs)
        del_args = {}
        prev_val = subclass_spec_as_namespace(prev_val)
        for key, val in list(prev_val.init_args.items(branches=True, nested=False)):
            action = find_action(parser, key)
            if action:
                with parser_context(lenient_check=False, load_value_mode=parser.parser_mode):
                    try:
                        parser._check_value_key(action, val, key, Namespace())
                    except Exception:
                        action = None
            if not action:
                del_args[key] = prev_val.init_args.pop(key)
        if del_args:
            parser_or_action.logger.debug(
                f"Due to class_path change from {prev_val['class_path']!r} to {value['class_path']!r}, "
                f"discarding init_args: {del_args}."
            )


def adapt_class_type(
    value,
    serialize,
    instantiate_classes,
    sub_add_kwargs,
    prev_val=None,
    partial_skip_args=None,
    typehint=None,
):
    prev_val = subclass_spec_as_namespace(prev_val)
    value = subclass_spec_as_namespace(value)
    if is_generic_class(typehint) and not is_protocol(typehint):
        val_class = typehint
    else:
        val_class = import_object(value.class_path)
    parser = ActionTypeHint.get_class_parser(val_class, sub_add_kwargs, skip_args=partial_skip_args)

    # No need to re-create the linked arg but just "inform" the corresponding parser actions that it exists upstream.
    for target in sub_add_kwargs.get("linked_targets", []):
        split_index = target.find(".")
        if split_index != -1:
            split = ".init_args." if target[split_index:].startswith(".init_args.") else "."

            parent_key, key = target.split(split, maxsplit=1)

            try:
                action = next(a for a in parser._actions if a.dest == parent_key)
            except StopIteration:
                continue

            sub_add_kwargs = getattr(action, "sub_add_kwargs")
            sub_add_kwargs.setdefault("linked_targets", set())
            sub_add_kwargs["linked_targets"].add(key)

    discard_init_args_on_class_path_change(parser, prev_val, value)

    dict_kwargs = value.pop("dict_kwargs", {})
    init_args = value.get("init_args", Namespace())

    if instantiate_classes:
        init_args = parser.instantiate(init_args)
        if not sub_add_kwargs.get("instantiate", True):
            if init_args:
                value["init_args"] = init_args
            return value

        instantiator_fn = get_class_instantiator()
        # only the top level keys, since a value can be a namespace, e.g. a subclass spec
        # kept as is for an Any typed parameter, which must not be expanded into kwargs
        init_kwargs = dict(init_args.items(branches=True, nested=False))

        if partial_skip_args:
            return partial(
                instantiator_fn,
                val_class,
                **{**init_kwargs, **dict_kwargs},
            )
        return instantiator_fn(val_class, **{**init_kwargs, **dict_kwargs})

    prev_init_args = prev_val.get("init_args") if isinstance(prev_val, Namespace) else None

    if isinstance(init_args, NestedArg):
        value["init_args"] = parser.parse_args(
            [f"--{init_args.key}={init_args.val}"],
            namespace=prev_init_args,
            defaults=sub_defaults.get(),
        )
        return _subclasses_disabled_mark(value, typehint)

    if serialize:
        if init_args:
            value["init_args"] = load_value(parser.dump(init_args, **dump_kwargs.get()))
    else:
        if isinstance(dict_kwargs, dict):
            for key in list(dict_kwargs):
                if find_action(parser, key):
                    init_args[key] = dict_kwargs.pop(key)
        elif dict_kwargs:
            init_args["dict_kwargs"] = dict_kwargs
            dict_kwargs = None
        init_args = parser.parse_object(init_args, namespace=prev_init_args, defaults=sub_defaults.get())
        if init_args:
            value["init_args"] = init_args
    if dict_kwargs:
        if prev_val and prev_val.get("class_path") == value["class_path"] and prev_val.get("dict_kwargs"):
            dict_kwargs = {**prev_val.get("dict_kwargs"), **dict_kwargs}
        value["dict_kwargs"] = {}
        for key, val in dict_kwargs.items():
            if isinstance(val, str):
                with suppress(get_loader_exceptions()):
                    val = load_value(val, simple_types=True)
            value["dict_kwargs"][key] = val

    return _subclasses_disabled_mark(value, typehint)


def subclasses_disabled_message(typehint, class_path) -> str:
    name = getattr(typehint, "__name__", str(typehint))
    return (
        f"Subclasses are disabled for {name}, thus {class_path!r} is not accepted as class_path. "
        f"Only the class_path of {name} itself is accepted, or its init args given directly. "
        f"To accept subclasses use set_parsing_settings(subclasses_enabled=[{name}])."
    )


def _subclasses_disabled_mark(value, typehint):
    if is_subclasses_disabled(typehint) and value.class_path == get_import_path(typehint):
        value[subclasses_disabled_meta_key] = True
    return value


def subclasses_disabled_remove_class_path(value):
    if not isinstance(value, (Namespace, dict)):
        return value

    items = vars(value).items() if isinstance(value, Namespace) else value.items()
    for key, val in items:
        if isinstance(val, (Namespace, dict)):
            value[key] = subclasses_disabled_remove_class_path(val)
        elif isinstance(val, list):
            value[key] = [subclasses_disabled_remove_class_path(item) for item in val]
        elif isinstance(val, tuple):
            value[key] = tuple(subclasses_disabled_remove_class_path(item) for item in val)

    if value.pop(subclasses_disabled_meta_key, False):
        init_args = Namespace({**value.get("init_args", {}), **value.get("dict_kwargs", {})})
        if "__path__" in value:  # the value came from a sub-config file
            init_args["__path__"] = value["__path__"]
        return init_args
    return value


def instantiate_subclass_spec_in_any() -> bool:
    """Whether a subclass spec given as value for a type that accepts any value is instantiated."""
    setting = get_parsing_setting("instantiate_subclass_spec_in_any")
    if setting is None:  # remove in v5.0.0, when the setting default becomes False
        from ._deprecated import unset_instantiate_subclass_spec_in_any

        setting = unset_instantiate_subclass_spec_in_any()
    return setting


def adapt_classes_any(val, typehint, serialize, instantiate_classes, sub_add_kwargs, logger=None):
    if is_subclass_spec(val):
        if instantiate_classes and not instantiate_subclass_spec_in_any():
            return val
        orig_val = val
        val = subclass_spec_as_namespace(val)
        init_args = val.get("init_args")
        if init_args and not instantiate_classes:
            for subkey, subval in init_args.items(branches=True, nested=False):
                init_args[subkey] = adapt_classes_any(
                    subval, typehint, serialize, instantiate_classes, sub_add_kwargs, logger
                )
            val["init_args"] = init_args
        try:
            val = adapt_class_type(val, serialize, instantiate_classes, sub_add_kwargs)
        except Exception as ex:
            type_str = type_to_str(typehint)
            if get_parsing_setting("validate_subclass_spec_in_any"):
                raise ValueError(f"Invalid subclass spec given as value for type {type_str}: {ex}") from ex
            if logger:
                logger.debug(f"Ignoring invalid subclass spec given as value for type {type_str}: {ex}", exc_info=ex)
            return orig_val
    elif isinstance(val, list):
        for num, subval in enumerate(val):
            val[num] = adapt_classes_any(subval, typehint, serialize, instantiate_classes, sub_add_kwargs, logger)
    elif isinstance(val, dict):
        for key, subval in val.items():
            val[key] = adapt_classes_any(subval, typehint, serialize, instantiate_classes, sub_add_kwargs, logger)
    return val


def validate_subclass_spec_in_mapping(val, typehint, subtypehints, sub_add_kwargs, logger) -> None:
    """Raises if the value of a mapping that doesn't validate its values is an invalid subclass spec.

    Only done when the ``validate_subclass_spec_in_any`` setting is enabled.
    Unlike for ``Any``, the value is only validated and kept as a mapping, since
    an instance would not correspond to the type. Building the class is the
    responsibility of a class type, e.g. a member of the union that the mapping
    is part of.
    """
    if not get_parsing_setting("validate_subclass_spec_in_any") or not is_subclass_spec(val):
        return
    if is_typed_dict(typehint):
        return
    if subtypehints is not None and not accepts_any_value(subtypehints[1]):
        return
    adapt_classes_any(deepcopy(val), typehint, False, False, sub_add_kwargs, logger)


def union_subtype_sort_key(subtype) -> int:
    """Rank of a union subtype, sorted by which is attempted first when parsing.

    The subtypes that accept the most values get a higher rank, so that sorting
    moves them to the end and the ones that validate more strictly get a chance
    of being used. Sorting is stable, thus subtypes with the same rank keep the
    relative order in which they are given.
    """
    if accepts_any_value(subtype):
        return 2  # accept any value, so nothing after them would ever be attempted
    if subtype is NoneType:
        return 1  # only accepts null, second to last so that Optional[<type>] reads as in the source code
    return 0


def get_type_var_default(type_var):
    """Returns the PEP 696 default of a TypeVar, or None when it has none."""
    if getattr(type_var, "has_default", lambda: False)():
        default = resolve_type_var_ref(type_var, type_var.__default__)
        if default is not None:
            return default
    return None


def resolve_type_var_ref(type_var, ref):
    """Resolves a forward reference given as bound, constraint or PEP 696 default of a TypeVar.

    The reference is resolved with the names of the module in which the TypeVar
    is defined, since that is the scope in which it was written. An unresolvable
    reference becomes an ``Unvalidated<...>``, i.e. it accepts any value and the
    help shows it as in the source code.
    """
    if not isinstance(ref, (str, ForwardRef)):
        return ref
    from ._postponed_annotations import get_global_vars

    resolved = ref
    module = getattr(type_var, "__module__", None)
    if isinstance(module, str):
        name = ref.__forward_arg__ if isinstance(ref, ForwardRef) else ref
        global_vars = get_global_vars(type_var, None)
        resolved = resolve_module_annotations(module, {"ref": name}, global_vars).get("ref", ref)
    return UnvalidatedType(ref) if isinstance(resolved, (str, ForwardRef)) else resolved


def replace_type_var(type_var, in_type_subtype: bool):
    """Returns the type that a TypeVar stands for, or the TypeVar when there is none.

    What a TypeVar stands for is given by its PEP 696 default, its constraints
    or its bound. As the subtype of a ``type[...]`` it additionally stands for
    ``object``, i.e. any class, since there a TypeVar is always a class.
    """
    default = get_type_var_default(type_var)
    if default is not None:
        return default
    if type_var.__constraints__:
        return Union[tuple(resolve_type_var_ref(type_var, c) for c in type_var.__constraints__)]
    if type_var.__bound__:
        return resolve_type_var_ref(type_var, type_var.__bound__)
    return object if in_type_subtype else type_var


def replace_type_vars(typehint):
    """Returns the type hint with all its TypeVars replaced, including nested ones.

    Done when an argument is added, since a TypeVar can't be used to validate.
    The help then shows what is accepted, e.g. ``type[object]`` instead of
    ``type[~T]``. A TypeVar that stands for nothing is left as is, so that it
    becomes an ``Unvalidated<...>``.
    """
    if isinstance(typehint, TypeVar):
        return replace_type_var(typehint, in_type_subtype=False)
    if get_typehint_origin(typehint) in literal_types:
        return typehint  # the args of a Literal are values, not types
    args = getattr(typehint, "__args__", None)
    # only a tuple, since e.g. types.UnionType and types.GenericAlias have __args__ as a
    # class level slot descriptor, which is truthy but not the subtypes of an instance
    if not isinstance(args, tuple) or not args:
        return typehint
    if get_typehint_origin(typehint) in {Type, type} and isinstance(args[0], TypeVar):
        new_args = (replace_type_var(args[0], in_type_subtype=True),)
    else:
        new_args = tuple(replace_type_vars(a) for a in args)
        if all(new is old for new, old in zip(new_args, args)):
            return typehint
    return rebuild_typehint_args(typehint, new_args)


def sort_unions_in_typehint(typehint):
    """Returns the type hint with the subtypes of all its unions sorted, including nested ones.

    Done when an argument is added, such that the help shows the type hint with
    the subtypes of unions in the order in which they are attempted when
    parsing, see union_subtype_sort_key.
    """
    if get_typehint_origin(typehint) in literal_types:
        return typehint  # the args of a Literal are values, not types
    args = getattr(typehint, "__args__", None)
    # only a tuple, since e.g. types.UnionType and types.GenericAlias have __args__ as a
    # class level slot descriptor, which is truthy but not the subtypes of an instance
    if not isinstance(args, tuple) or not args:
        return typehint
    new_args = tuple(sort_unions_in_typehint(a) for a in args)
    if get_typehint_origin(typehint) == Union:
        new_args = tuple(sorted(new_args, key=union_subtype_sort_key))
    # compared by identity, since typing considers Union[int, str] and Union[str, int] equal
    if all(new is old for new, old in zip(new_args, args)):
        return typehint
    return rebuild_typehint_args(typehint, new_args)


def rebuild_typehint_args(typehint, new_args):
    """Returns the given type hint with its subtypes replaced, or unchanged if not possible."""
    try:
        if isinstance(typehint, UnionType):
            try:
                return reduce(or_, new_args)
            except TypeError:
                return Union[new_args]  # e.g. an UnvalidatedType subtype doesn't support |
        if get_typehint_origin(typehint) == Union:
            # neither Union[...] nor its copy_with are used because typing caches unions and
            # considers two of them equal independent of the order of the subtypes, thus a
            # previously created union with the same subtypes in a different order would be
            # returned, silently undoing the sorting
            return type(typehint)(Union, tuple(new_args), name=getattr(typehint, "_name", None))
        if hasattr(typehint, "copy_with"):
            return typehint.copy_with(new_args)
        subscript_args = get_args(typehint)
        if subscript_args and isinstance(subscript_args[0], list):
            # a Callable that has its parameters flattened in __args__, e.g. the __args__ of
            # Callable[[int], str] are (int, str), while subscripting needs them as a list
            return get_typehint_origin(typehint)[[*new_args[:-1]], new_args[-1]]
        return get_typehint_origin(typehint)[new_args]
    except Exception:
        return typehint


def sort_subtypes_for_union(subtypes, val, prev_val, append):
    """Sorts the subtypes of a union for the parsing of a given value.

    The sort that does not depend on the value is applied first, which is a
    no-op for the type hint of an added argument, since it is already sorted,
    see sort_unions_in_typehint. It is still needed for type hints resolved
    while parsing, e.g. the types of the keys of a TypedDict. Then, only when
    appending to a list, the sequence subtypes are moved to the front, since
    the value must extend the previous list instead of replacing it.
    """
    if len(subtypes) > 1:
        subtypes = sorted(subtypes, key=union_subtype_sort_key)
        if append or (isinstance(prev_val, list) and isinstance(val, NestedArg)):
            subtypes = sorted(subtypes, key=lambda x: get_typehint_origin(x) not in sequence_origin_types)
    return subtypes


def is_ellipsis_tuple(typehint):
    return typehint.__origin__ in {Tuple, tuple} and len(typehint.__args__) > 1 and typehint.__args__[1] == Ellipsis


def is_optional(annotation, ref_type=None):
    """Checks whether a type annotation is an optional for one type class."""
    return (
        get_typehint_origin(annotation) == Union
        and len(annotation.__args__) == 2
        and any(NoneType == a for a in annotation.__args__)
        and (ref_type is None or all(is_subclass(a, ref_type) for a in annotation.__args__ if a != NoneType))
    )


def get_optional_arg(annotation, ref_type=None):
    if is_optional(annotation, ref_type):
        annotation = next(a for a in annotation.__args__ if a != NoneType)
    return annotation


def is_enum_type(annotation):
    return is_subclass(annotation, Enum) or (
        get_typehint_origin(annotation) == Union and any(is_subclass(a, Enum) for a in annotation.__args__)
    )


def is_module_type(annotation):
    annotation = get_unaliased_type(annotation)
    return annotation is ModuleType or (
        get_typehint_origin(annotation) == Union and any(a is ModuleType for a in annotation.__args__)
    )


def is_callable_type(annotation):
    def is_callable(a):
        return (get_typehint_origin(a) or a) in callable_origin_types or a in callable_origin_types

    return is_callable(annotation) or (
        get_typehint_origin(annotation) == Union and any(is_callable(a) for a in annotation.__args__)
    )


def typehint_from_action(action_or_typehint):
    if isinstance(action_or_typehint, Action):
        action_or_typehint = getattr(action_or_typehint, "_typehint", None)
    return action_or_typehint


module_prefix_pattern = re.compile(r"(?<![\w.])(?:[A-Za-z_][A-Za-z0-9_]*\.)+")
none_type_pattern = re.compile(r"\bNone(Type)?\b")
type_arg_prefix = "jsonargparseTypeArg"
type_arg_pattern = re.compile(rf"\b{type_arg_prefix}\d+\b")


def strip_module_names(string: str) -> str:
    return module_prefix_pattern.sub("", string)


def type_to_str(obj):
    if obj is ModuleType:
        return "ModuleType"
    if obj in type_expression_types:
        return type_expression_types[obj]
    # is_subclass not used, since in python<3.12 it considers an Annotated a subclass of its origin type
    if obj in {bool, tuple, object} or (isinstance(obj, type) and issubclass(obj, (int, float, str, Path, Enum))):
        return obj.__name__
    return typehint_to_str(obj)


def typehint_to_str(typehint) -> str:
    """Type hint as a string, recreating it with subtypes replaced by their string form.

    Only the outermost level goes through ``strip_module_names``, such that literal
    values and metadata, e.g. floats and dotted strings, are never mangled by it.
    """
    if get_typehint_origin(typehint) is Literal:
        values = ", ".join(repr_to_str(v) for v in typehint.__args__)
        return f"Literal[{values}]"
    if hasattr(typehint, "__metadata__"):
        subtypes = [subtypehint_to_str(typehint.__origin__)] + [repr(m) for m in typehint.__metadata__]
        return f"Annotated[{', '.join(subtypes)}]"

    args = getattr(typehint, "__args__", None)
    if isinstance(args, tuple) and args:
        arg_subtypes = {}
        new_args = []
        for num, arg in enumerate(args):
            if arg is NoneType or arg is Ellipsis:
                new_args.append(arg)
                continue
            name = f"{type_arg_prefix}{num}"
            arg_subtypes[name] = subtypehint_to_str(arg)
            new_args.append(type(name, (), {}))
        shallow = replace_typehint_args(typehint, new_args)
        if shallow is not None:
            string = none_type_pattern.sub("null", strip_module_names(str(shallow)))
            return type_arg_pattern.sub(lambda match: arg_subtypes[match.group()], string)

    return none_type_pattern.sub("null", strip_module_names(str(typehint)))


def subtypehint_to_str(typehint) -> str:
    if isinstance(typehint, type) and not getattr(typehint, "__args__", None):
        return typehint.__name__  # the str of a class has a <class ...> wrap and the module name
    return typehint_to_str(typehint)


def replace_typehint_args(typehint, args):
    """Same type hint but with its subtypes replaced, or None if not possible."""
    if isinstance(typehint, UnionType):
        return reduce(or_, args)
    if isinstance(typehint, GenericAlias):
        origin = typehint.__origin__
        if origin in callable_origin_types:
            # the input types of a callable are given as a list, e.g. Callable[[int], str]
            return origin[args[0] if args[0] is Ellipsis else list(args[:-1]), args[-1]]
        return GenericAlias(origin, tuple(args))
    try:
        return typehint.copy_with(tuple(args))
    except Exception:
        # no copy_with, e.g. a parameterized type that is a class, or it rejects the given subtypes
        return None


def repr_to_str(val):
    return "null" if val is None else repr(val)


def literal_to_str(val):
    return "null" if val is None else str(val)


def typehint_metavar(typehint):
    """Generates a metavar for some types."""
    metavar = None
    typehint_origin = get_typehint_origin(typehint) or typehint
    if typehint == bool:
        metavar = "{true,false}"
    elif is_optional(typehint, bool):
        metavar = "{true,false,null}"
    elif typehint_origin in literal_types:
        args = typehint.__args__
        metavar = iter_to_set_str(literal_to_str(a) for a in args)
    elif is_subclass(typehint, Enum):
        enum = typehint
        metavar = iter_to_set_str(enum.__members__)
    elif is_optional(typehint, Enum):
        enum = typehint.__args__[0]
        metavar = iter_to_set_str(list(enum.__members__) + ["null"])
    elif is_list_pathlike(typehint):
        metavar = "'[\"PATH1\",...]' | LIST_OF_PATHS_FILE | -"
    elif typehint_origin in tuple_set_origin_types or typehint_origin in sequence_origin_types:
        metavar = "[ITEM,...]"
    return metavar


def serialize_class_instance(val):
    with suppress(Exception):
        import_path = get_import_path(val)
        if import_path and import_object(import_path) is val:
            return import_path
    val = f"Unable to serialize instance {val}"
    warning(val)
    return val


def typehint_from_value(val):
    """Derives a type hint from a value, so that adapt_typehints is able to serialize it.

    Containers are derived as a type hint of ``Any`` items, so that the items are
    serialized the same as the value itself. ``None`` is returned for the values
    that no supported or registered type represents.
    """
    if isinstance(val, dict):
        return Dict[Any, Any]
    if isinstance(val, list):
        return List[Any]
    if isinstance(val, tuple):
        return Tuple[Any, ...]
    if isinstance(val, (set, frozenset)):
        return Set[Any]
    type_val = type(val)
    if type_val in leaf_types or get_registered_type(type_val) or is_subclass(type_val, Enum):
        return type_val
    return None


def serialize_unvalidated(val, adapt_kwargs):
    """Serializes the value of a type that is not validated.

    Values of an Any or Unvalidated type don't have a type hint to serialize
    them with, so one is derived from the value itself and the serialization is
    delegated to adapt_typehints. Values that no type represents are serialized
    the same as the instances given for a subclass type, i.e. as an import path
    when the value can be imported back, otherwise as a message that says that it
    was not serializable.

    Parsing back has no type hint either, thus a value only round-trips when the
    config format represents its type. A warning is given when it doesn't.
    """
    if isinstance(val, Namespace):
        # e.g. a subclass spec that adapt_classes_any already serialized
        for key, subval in val.items(branches=True, nested=False):
            val[key] = serialize_unvalidated(subval, adapt_kwargs)
        return val
    typehint = typehint_from_value(val)
    if typehint is None:
        return serialize_class_instance(val)
    if isinstance(val, dict):
        adapt_val = dict(val)  # adapt_typehints serializes the items in place, so give it a copy
    elif isinstance(val, list):
        adapt_val = list(val)
    else:
        adapt_val = val
    serialized = adapt_typehints(adapt_val, typehint, **adapt_kwargs)
    if type(serialized) is not type(val):
        warning(
            f"Dump of a value that does not round-trip: a {type(val).__name__} is serialized as "
            f"{type(serialized).__name__} and, since the type is not validated, parsing it back "
            f"gives a {type(serialized).__name__}. Value: {val}"
        )
    return serialized


def callable_instances(cls: type):
    # https://stackoverflow.com/a/71568161/2732151
    return isinstance(getattr(cls, "__call__", None), FunctionType)
