import argparse
import dataclasses
import inspect
import logging
import os
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import (  # type: ignore[attr-defined]
    Generic,
    TypeVar,
    _GenericAlias,
)

from ._namespace import Namespace
from ._optionals import (
    _set_config_read_mode,
    _set_docstring_parse_options,
    capture_typing_extension_shadows,
    get_alias_target,
    get_annotated_base_type,
    is_alias_type,
    is_annotated,
    is_attrs_class,
    is_pydantic_model,
    typing_extensions_import,
)
from ._type_checking import ActionsContainer, ArgumentParser, docstring_parser

__all__ = [
    "Unset",
    "set_parsing_settings",
]

ClassType = TypeVar("ClassType")

_UnpackGenericAlias = typing_extensions_import("_UnpackAlias")

unpack_meta_types = set()
if _UnpackGenericAlias:
    unpack_meta_types.add(_UnpackGenericAlias)
capture_typing_extension_shadows(_UnpackGenericAlias, "_UnpackGenericAlias", unpack_meta_types)


class _UnsetType:
    """Sentinel class for unset argument values."""

    _instance = None
    _SERIALIZED = "==UNSET=="

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "Unset"

    def __bool__(self):
        return False


Unset = _UnsetType()


parent_parser: ContextVar[ArgumentParser | None] = ContextVar("parent_parser", default=None)
parser_capture: ContextVar[bool] = ContextVar("parser_capture", default=False)
defaults_cache: ContextVar[Namespace | None] = ContextVar("defaults_cache", default=None)
lenient_check: ContextVar[bool | str] = ContextVar("lenient_check", default=False)
parsing_defaults: ContextVar[bool] = ContextVar("parsing_defaults", default=False)
single_subcommand: ContextVar[bool] = ContextVar("single_subcommand", default=True)
validating_defaults: ContextVar[bool] = ContextVar("validating_defaults", default=False)
load_value_mode: ContextVar[str | None] = ContextVar("load_value_mode", default=None)
nested_links: ContextVar[list[dict]] = ContextVar("nested_links", default=[])
applied_instantiation_links: ContextVar[set | None] = ContextVar("applied_instantiation_links", default=None)
path_dump_preserve_relative: ContextVar[bool] = ContextVar("path_dump_preserve_relative", default=False)


parser_context_vars = {
    "parent_parser": parent_parser,
    "parser_capture": parser_capture,
    "defaults_cache": defaults_cache,
    "lenient_check": lenient_check,
    "parsing_defaults": parsing_defaults,
    "single_subcommand": single_subcommand,
    "validating_defaults": validating_defaults,
    "load_value_mode": load_value_mode,
    "nested_links": nested_links,
    "applied_instantiation_links": applied_instantiation_links,
    "path_dump_preserve_relative": path_dump_preserve_relative,
}


@contextmanager
def parser_context(**kwargs):
    context_var_tokens = []
    for name, value in kwargs.items():
        context_var = parser_context_vars[name]
        token = context_var.set(value)
        context_var_tokens.append((context_var, token))
    try:
        yield
    finally:
        for context_var, token in context_var_tokens:
            context_var.reset(token)


parsing_settings: dict = {
    "validate_defaults": False,
    "parse_optionals_as_positionals": False,
    "add_print_completion_argument": False,
    "stubs_resolver_allow_py_files": False,
    "omegaconf_absolute_to_relative_paths": False,
    "unset_sentinel": None,
}


def get_env_var_bool(name: str) -> bool:
    raw_value = os.getenv(name, "")
    value = raw_value.lower()
    if value not in {"true", "false", ""}:
        raise ValueError(f"Invalid boolean value for environment variable {name}: {raw_value}")
    return value == "true"


def set_parsing_settings(
    *,
    validate_defaults: bool | None = None,
    config_read_mode_urls_enabled: bool | None = None,
    config_read_mode_fsspec_enabled: bool | None = None,
    docstring_parse_style: "docstring_parser.DocstringStyle | None" = None,
    docstring_parse_attribute_docstrings: bool | None = None,
    parse_optionals_as_positionals: bool | None = None,
    add_print_completion_argument: bool | None = None,
    stubs_resolver_allow_py_files: bool | None = None,
    omegaconf_absolute_to_relative_paths: bool | None = None,
    unset_sentinel: bool | None = None,
    subclasses_disabled: list[type | Callable[[type], bool]] | None = None,
    subclasses_enabled: list[type | str] | None = None,
) -> None:
    """
    Modify global parser settings that affect parser creation and parsing behavior.

    Args:
        validate_defaults: Whether default values must be valid according to the
            argument type. The default is ``False``, meaning no default
            validation, like in argparse.
        config_read_mode_urls_enabled: Whether to read config files from URLs
            using requests package. Default is ``False``.
        config_read_mode_fsspec_enabled: Whether to read config files from
            fsspec supported file systems. Default is ``False``.
        docstring_parse_style: The docstring style to expect. Default is
            ``DocstringStyle.AUTO``.
        docstring_parse_attribute_docstrings: Whether to parse attribute
            docstrings (slower). Default is ``False``.
        parse_optionals_as_positionals: If ``True``, the parser will take extra
            positional command line arguments as values for optional arguments.
            This means that optional arguments can be given by name
            ``--key=value`` as usual, but also as positional. The extra
            positionals are applied to optionals in the order that they were
            added to the parser. By default, this is ``False``.
        add_print_completion_argument: If ``True``, top-level parsers
            automatically include ``--print_completion`` argument when
            ``shtab`` is installed.
        stubs_resolver_allow_py_files: Whether the stubs resolver should search
            in ``.py`` files in addition to ``.pyi`` files.
        omegaconf_absolute_to_relative_paths: If ``True``, when loading configs
            with ``omegaconf+`` parser mode, absolute interpolation paths are
            converted to relative. This is only intended for backward
            compatibility with ``omegaconf`` parser mode.
        unset_sentinel: If ``True``, parsers will use the :obj:`.Unset` sentinel
            for arguments that have not been given a value (instead of
            ``None``). This allows distinguishing between ``None`` as an
            explicitly given value and an argument that was not provided at
            all. If ``False``, uses ``None`` (the default, argparse-compatible
            behavior) unless overridden by ``argument_default``.
        subclasses_disabled: List of types or functions, so that when parsing
            only the exact type hints (not their subclasses) are accepted.
            Descendants of the configured types are also disabled. Functions
            should return ``True`` for types to disable.
        subclasses_enabled: List of types or disable function names, so that
            subclasses are accepted. Types given here have precedence over those
            in ``subclasses_disabled``. Giving a function name removes the
            corresponding function from ``subclasses_disabled``. By default, the
            following disable functions are registered: ``is_pure_dataclass``,
            ``is_pydantic_model``, ``is_attrs_class`` and ``is_final_class``.
    """
    # validate_defaults
    if isinstance(validate_defaults, bool):
        parsing_settings["validate_defaults"] = validate_defaults
    elif validate_defaults is not None:
        raise ValueError(f"validate_defaults must be a boolean, but got {validate_defaults}.")
    # config_read_mode
    if config_read_mode_urls_enabled is not None:
        _set_config_read_mode(urls_enabled=config_read_mode_urls_enabled)
    if config_read_mode_fsspec_enabled is not None:
        _set_config_read_mode(fsspec_enabled=config_read_mode_fsspec_enabled)
    # docstring_parse
    if docstring_parse_style is not None:
        _set_docstring_parse_options(style=docstring_parse_style)
    if docstring_parse_attribute_docstrings is not None:
        _set_docstring_parse_options(attribute_docstrings=docstring_parse_attribute_docstrings)
    # parse_optionals_as_positionals
    if isinstance(parse_optionals_as_positionals, bool):
        parsing_settings["parse_optionals_as_positionals"] = parse_optionals_as_positionals
    elif parse_optionals_as_positionals is not None:
        raise ValueError(f"parse_optionals_as_positionals must be a boolean, but got {parse_optionals_as_positionals}.")
    # add_print_completion_argument
    if isinstance(add_print_completion_argument, bool):
        parsing_settings["add_print_completion_argument"] = add_print_completion_argument
    elif add_print_completion_argument is not None:
        raise ValueError(f"add_print_completion_argument must be a boolean, but got {add_print_completion_argument}.")
    # stubs resolver
    if isinstance(stubs_resolver_allow_py_files, bool):
        parsing_settings["stubs_resolver_allow_py_files"] = stubs_resolver_allow_py_files
    elif stubs_resolver_allow_py_files is not None:
        raise ValueError(f"stubs_resolver_allow_py_files must be a boolean, but got {stubs_resolver_allow_py_files}.")
    # omegaconf_absolute_to_relative_paths
    if isinstance(omegaconf_absolute_to_relative_paths, bool):
        parsing_settings["omegaconf_absolute_to_relative_paths"] = omegaconf_absolute_to_relative_paths
    elif omegaconf_absolute_to_relative_paths is not None:
        raise ValueError(
            f"omegaconf_absolute_to_relative_paths must be a boolean, but got {omegaconf_absolute_to_relative_paths}."
        )
    # unset_sentinel
    if isinstance(unset_sentinel, bool):
        parsing_settings["unset_sentinel"] = Unset if unset_sentinel else None
    elif unset_sentinel is not None:
        raise ValueError(f"unset_sentinel must be a boolean, but got {unset_sentinel}.")
    # subclass behavior
    if subclasses_disabled or subclasses_enabled:
        subclass_type_behavior(
            subclasses_disabled=subclasses_disabled,
            subclasses_enabled=subclasses_enabled,
        )


def get_parsing_setting(name: str):
    if name not in parsing_settings:
        raise ValueError(f"Unknown parsing setting {name}.")
    if name == "add_print_completion_argument":
        var_name = "JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT"
        if var_name in os.environ:
            return get_env_var_bool(var_name)
    return parsing_settings[name]


def validate_default(container: ActionsContainer, action: argparse.Action):
    if (
        action.default is get_parsing_setting("unset_sentinel")
        or not get_parsing_setting("validate_defaults")
        or not hasattr(action, "_check_type")
    ):
        return
    try:
        from ._core import ArgumentGroup

        if isinstance(container, ArgumentGroup):
            container = container.parser
        with parser_context(parent_parser=container, validating_defaults=True):
            default = action.default
            action.default = None
            action.default = action._check_type_(default)  # type: ignore[attr-defined]
    except Exception as ex:
        raise ValueError(f"Default value is not valid: {ex}") from ex


def get_optionals_as_positionals_actions(parser, include_positionals=False):
    from jsonargparse._actions import ActionConfigFile, ActionFail, _ActionConfigLoad, filter_non_parsing_actions
    from jsonargparse._completions import PrintCompletionAction
    from jsonargparse._typehints import ActionTypeHint

    actions = []
    for action in filter_non_parsing_actions(parser._actions):
        if isinstance(action, (_ActionConfigLoad, ActionConfigFile, ActionFail, PrintCompletionAction)):
            continue
        if ActionTypeHint.is_subclass_typehint(action, all_subtypes=False):
            continue
        if action.nargs not in {1, None}:
            continue
        if not include_positionals and action.option_strings == []:
            continue
        actions.append(action)

    return actions


def supports_optionals_as_positionals(parser):
    return (
        get_parsing_setting("parse_optionals_as_positionals")
        and not parser._subcommands_action
        and not getattr(parser, "_inner_parser", False)
    )


def is_subclass(cls, class_or_tuple) -> bool:
    """Extension of issubclass that supports non-class arguments and generics."""
    try:
        class_or_tuple = get_generic_origins(class_or_tuple)
        if inspect.isclass(cls):
            return issubclass(cls, class_or_tuple)
        elif is_generic_class(cls):
            return issubclass(cls.__origin__, class_or_tuple)
    except TypeError:
        pass  # TypeError means that cls is not a class
    return False


def is_instance(obj, class_or_tuple) -> bool:
    """Extension of isinstance that supports generics."""
    class_or_tuple = get_generic_origins(class_or_tuple)
    return isinstance(obj, class_or_tuple)


def is_final_class(cls) -> bool:
    """Checks whether a class is final, i.e. decorated with ``typing.final``."""
    return getattr(cls, "__final__", False)


def is_generic_class(cls) -> bool:
    return isinstance(cls, _GenericAlias) and getattr(cls, "__module__", "") != "typing"


def is_unpack_typehint(cls) -> bool:
    return any(isinstance(cls, unpack_type) for unpack_type in unpack_meta_types)


def get_generic_origin(cls):
    return cls.__origin__ if is_generic_class(cls) else cls


def get_generic_origins(class_or_tuple):
    if isinstance(class_or_tuple, tuple):
        return tuple(get_generic_origin(cls) for cls in class_or_tuple)
    return get_generic_origin(class_or_tuple)


def get_unaliased_type(cls):
    new_cls = cls
    while True:
        cur_cls = new_cls
        if is_annotated(new_cls):
            new_cls = get_annotated_base_type(new_cls)
        if is_alias_type(new_cls):
            new_cls = get_alias_target(new_cls)
        if new_cls == cur_cls:
            break
    return cur_cls


def is_pure_dataclass(cls) -> bool:
    classes = [c for c in inspect.getmro(cls) if c not in {object, Generic}]
    return all(dataclasses.is_dataclass(c) for c in classes)


subclasses_enabled_types: set[type] = set()
subclasses_disabled_types: set[type] = set()
subclasses_disabled_selectors: dict[str, Callable[[type], bool | int]] = {
    "is_pure_dataclass": is_pure_dataclass,
    "is_pydantic_model": is_pydantic_model,
    "is_attrs_class": is_attrs_class,
    "is_final_class": is_final_class,
}


def is_subclasses_disabled(cls) -> bool:
    if is_generic_class(cls):
        return is_subclasses_disabled(cls.__origin__)
    if not inspect.isclass(cls):
        return False
    subclass_disabled = any(selector(cls) for selector in subclasses_disabled_selectors.values())
    if not subclass_disabled:
        subclass_disabled = any(issubclass(cls, disable_type) for disable_type in subclasses_disabled_types)
    if subclass_disabled:
        subclass_disabled = not any(issubclass(cls, enable_type) for enable_type in subclasses_enabled_types)
    return subclass_disabled


def subclass_type_behavior(
    subclasses_disabled: list[type | Callable[[type], bool]] | None = None,
    subclasses_enabled: list[type | str] | None = None,
) -> None:
    """Configures whether class types accept or not subclasses."""
    for enable_item in subclasses_enabled or []:
        if isinstance(enable_item, str):
            if enable_item not in subclasses_disabled_selectors:
                raise ValueError(f"There is no function '{enable_item}' registered in subclasses_disabled")
            subclasses_disabled_selectors.pop(enable_item)
        elif inspect.isclass(enable_item):
            subclasses_enabled_types.add(enable_item)
        else:
            raise ValueError(
                f"Expected 'subclasses_enabled' list items to be types or strings, but got {enable_item!r}"
            )

    for disable_item in subclasses_disabled or []:
        if inspect.isclass(disable_item):
            subclasses_disabled_types.add(disable_item)
        elif inspect.isfunction(disable_item):
            subclasses_disabled_selectors[disable_item.__name__] = disable_item
        else:
            raise ValueError(
                f"Expected 'subclasses_disabled' list items to be types or functions, but got {disable_item!r}"
            )


# logging

logging_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
null_logger = logging.getLogger("jsonargparse_null_logger")
null_logger.addHandler(logging.NullHandler())
null_logger.parent = None


def setup_default_logger(data, level, caller):
    name = caller
    if isinstance(data, str):
        name = data
    elif isinstance(data, dict) and "name" in data:
        name = data["name"]
    logger = logging.getLogger(name)
    logger.parent = None
    if len(logger.handlers) == 0:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)
    level = getattr(logging, level)
    for handler in logger.handlers:
        handler.setLevel(level)
    return logger


def parse_logger(logger: bool | str | dict | logging.Logger, caller):
    if not isinstance(logger, (bool, str, dict, logging.Logger)):
        raise ValueError(f"Expected logger to be an instance of (bool, str, dict, logging.Logger), but got {logger}.")
    if isinstance(logger, dict) and len(set(logger) - {"name", "level"}) > 0:
        value = {k: v for k, v in logger.items() if k not in {"name", "level"}}
        raise ValueError(f"Unexpected data to configure logger: {value}.")
    if logger is False:
        return null_logger
    level = "WARNING"
    if isinstance(logger, dict) and "level" in logger:
        level = logger["level"]
    if level not in logging_levels:
        raise ValueError(f"Got logger level {level!r} but must be one of {logging_levels}.")
    if not isinstance(logger, logging.Logger):
        logger = setup_default_logger(logger, level, caller)
    return logger


class LoggerProperty:
    """Class designed to be inherited by other classes to add a logger property."""

    def __init__(self, *args, logger: bool | str | dict | logging.Logger = False, **kwargs):
        self.logger = logger
        super().__init__(*args, **kwargs)

    @property
    def logger(self) -> logging.Logger:
        """The logger property for the class.

        :getter: Returns the current logger.
        :setter: Sets the given logging.Logger as logger or sets the default logger
                 if given True/str(logger name)/dict(name, level), or disables logging
                 if given False.

        Raises:
            ValueError: If an invalid logger value is given.
        """
        return self._logger

    @logger.setter
    def logger(self, logger: bool | str | dict | logging.Logger):
        if not logger and debug_mode_active():
            logger = {"level": "DEBUG"}
        self._logger = parse_logger(logger, type(self).__name__)


def debug_mode_active() -> bool:
    return get_env_var_bool("JSONARGPARSE_DEBUG")


# base classes


class Action(LoggerProperty, argparse.Action):
    """Base for jsonargparse Action classes."""

    def _check_type_(self, value, **kwargs):
        if not hasattr(self, "_check_type_kwargs"):
            self._check_type_kwargs = set(inspect.signature(self._check_type).parameters)
        kwargs = {k: v for k, v in kwargs.items() if k in self._check_type_kwargs}
        return self._check_type(value, **kwargs)


class NonParsingAction(Action):
    """Base for jsonargparse utility Action classes."""
