"""Deprecated code."""

import functools
import inspect
import os
import sys
from argparse import ArgumentError
from enum import Enum
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Optional, Set, Union, overload

from ._common import Action, InstantiatorsDictType, null_logger
from ._common import LoggerProperty as InternalLoggerProperty
from ._instantiation import _register_instantiator
from ._namespace import Namespace
from ._type_checking import ArgumentParser, ruamelCommentedMap

__all__ = [
    "ActionEnum",
    "ActionJsonnetExtVars",
    "ActionOperators",
    "ActionPath",
    "ActionPathList",
    "HelpFormatterDeprecations",
    "LoggerProperty",
    "PathDeprecations",
    "ParserDeprecations",
    "ParserError",
    "compose_dataclasses",
    "get_config_read_mode",
    "dict_to_namespace",
    "namespace_to_dict",
    "null_logger",
    "set_docstring_parse_options",
    "set_config_read_mode",
    "set_url_support",
    "strip_meta",
    "usage_and_exit_error_handler",
]

_message_add_argument_enable_path = """
    ``enable_path`` parameter of ``add_argument`` was deprecated in v4.49.0 and will be removed in v5.0.0.
    Use ``sub_configs`` instead.
"""

_message_action_json_schema_enable_path = """
    ``enable_path`` parameter of ``ActionJsonSchema`` was deprecated in v4.49.0 and will be removed in v5.0.0.
    Use ``sub_config`` instead.
"""


shown_deprecation_warnings: Set[Any] = set()


class JsonargparseDeprecationWarning(DeprecationWarning):
    pass


def deprecation_warning(component, message, stacklevel=1):
    env_var = os.environ.get("JSONARGPARSE_DEPRECATION_WARNINGS", "").lower()
    show_warnings = env_var != "off"
    all_warnings = env_var == "all"
    if show_warnings and (component not in shown_deprecation_warnings or all_warnings):
        from ._util import warning

        if len(shown_deprecation_warnings) == 0 and not all_warnings:
            warning(
                """
                By default only one JsonargparseDeprecationWarning per type is shown. To see
                all warnings set environment variable JSONARGPARSE_DEPRECATION_WARNINGS=all
                and to disable the warnings set JSONARGPARSE_DEPRECATION_WARNINGS=off.
                """,
                JsonargparseDeprecationWarning,
                stacklevel=stacklevel + 2,
            )
        warning(message, JsonargparseDeprecationWarning, stacklevel=stacklevel + 2)
        shown_deprecation_warnings.add(component)


def deprecated(message):
    def deprecated_decorator(component):
        warning = "\n\n.. warning::\n    " + message + "\n"
        component.__doc__ = ("" if component.__doc__ is None else component.__doc__) + warning

        if inspect.isclass(component):

            @functools.wraps(component.__init__)
            def init_wrap(self, *args, **kwargs):
                deprecation_warning(component, message)
                self._original_init(*args, **kwargs)

            component._original_init = component.__init__
            component.__init__ = init_wrap
            decorated = component

        else:

            @functools.wraps(component)
            def decorated(*args, **kwargs):
                deprecation_warning(component, message)
                return component(*args, **kwargs)

        return decorated

    return deprecated_decorator


def add_argument_enable_path_deprecation(kwargs: dict, stacklevel: int = 1) -> Optional[bool]:
    """Handle deprecated ``enable_path`` parameter in ``add_argument``.

    If ``enable_path`` is present in kwargs, emit a deprecation warning and
    return its value (popping it from kwargs). Returns ``None`` if not present.
    """
    if "enable_path" in kwargs:
        deprecation_warning(
            add_argument_enable_path_deprecation,
            _message_add_argument_enable_path,
            stacklevel=stacklevel + 1,
        )
        return kwargs.pop("enable_path")
    return None


def action_json_schema_enable_path_deprecation(kwargs: dict, stacklevel: int = 1) -> Optional[bool]:
    """Handle deprecated ``enable_path`` parameter in ``ActionJsonSchema``.

    If ``enable_path`` is present in kwargs, emit a deprecation warning and
    return its value (popping it from kwargs). Returns ``None`` if not present.
    """
    if "enable_path" in kwargs:
        deprecation_warning(
            action_json_schema_enable_path_deprecation,
            _message_action_json_schema_enable_path,
            stacklevel=stacklevel + 1,
        )
        return kwargs.pop("enable_path")
    return None


def parse_as_dict_patch():
    """Adds parse_as_dict support to ArgumentParser as a patch.

    This is a temporal backward compatible support for parse_as_dict to have
    cleaner code in v4.0.0 and warn users about the deprecation and future
    removal.
    """
    from ._core import ArgumentParser

    assert not hasattr(ArgumentParser, "_unpatched_init")

    message_parse_as_dict = """
    ``parse_as_dict`` parameter was deprecated in v4.0.0 and will be removed in
    v5.0.0. After removal, the parse_*, dump, save and instantiate_classes
    methods will only return Namespace and/or accept Namespace objects. If
    needed for some use case, config objects can be converted to a nested dict
    using the Namespace.as_dict method.
    """
    message_with_meta = """
    ``with_meta`` parameter was deprecated in v4.44.0 and will be removed in
    v5.0.0. After removal, config objects will always include metadata. To
    remove metadata from a config object, do ``.clone(with_meta=False)``.
    """

    # Patch __init__
    def patched_init(self, *args, parse_as_dict: bool = False, **kwargs):
        self._parse_as_dict = parse_as_dict
        if parse_as_dict:
            deprecation_warning(patched_init, message_parse_as_dict)
        self._unpatched_init(*args, **kwargs)

    ArgumentParser._unpatched_init = ArgumentParser.__init__
    ArgumentParser.__init__ = patched_init

    # Patch parse methods
    def patch_parse_method(method_name):
        unpatched_method_name = "_unpatched_" + method_name

        def patched_parse(
            self,
            *args,
            with_meta: Optional[bool] = None,
            _skip_validation: bool = False,
            **kwargs,
        ) -> Union[Namespace, Dict[str, Any]]:
            parse_method = getattr(self, unpatched_method_name)
            cfg = parse_method(*args, _skip_validation=_skip_validation, **kwargs)

            if isinstance(with_meta, bool):
                deprecation_warning(patched_parse, message_with_meta)
            if not (with_meta or (with_meta is None and self._default_meta)):
                cfg = cfg.clone(with_meta=False)

            return cfg.as_dict() if self._parse_as_dict and not _skip_validation else cfg

        patched_parse.__name__ = method_name
        patched_parse.__qualname__ = f"ArgumentParser.{method_name}"

        setattr(ArgumentParser, unpatched_method_name, getattr(ArgumentParser, method_name))
        setattr(ArgumentParser, method_name, patched_parse)

    patch_parse_method("parse_args")
    patch_parse_method("parse_object")
    patch_parse_method("parse_env")
    patch_parse_method("parse_string")

    # Patch dump
    def patched_dump(self, cfg: Union[Namespace, Dict[str, Any]], *args, **kwargs) -> str:
        if isinstance(cfg, dict):
            cfg = self.parse_object(cfg, _skip_validation=True)
        return self._unpatched_dump(cfg, *args, **kwargs)

    ArgumentParser._unpatched_dump = ArgumentParser.dump
    ArgumentParser.dump = patched_dump

    # Patch save
    def patched_save(self, cfg: Union[Namespace, Dict[str, Any]], *args, multifile: bool = True, **kwargs) -> None:
        if multifile and isinstance(cfg, dict):
            cfg = self.parse_object(cfg, _skip_validation=True)
        return self._unpatched_save(cfg, *args, multifile=multifile, **kwargs)

    ArgumentParser._unpatched_save = ArgumentParser.save
    ArgumentParser.save = patched_save


@deprecated("""
    ActionEnum was deprecated in v3.9.0 and will be removed in v5.0.0. Enums now
    should be given directly as a type as explained in :ref:`enums`.
""")
class ActionEnum:
    """An action based on an Enum that maps to-from strings and enum values."""

    def __init__(self, **kwargs):
        if "enum" in kwargs:
            from ._common import is_subclass

            if not is_subclass(kwargs["enum"], Enum):
                raise ValueError("Expected enum to be an subclass of Enum.")
            self._type = kwargs["enum"]
        else:
            raise ValueError("Expected enum keyword argument.")

    def __call__(self, *args, **kwargs):
        if kwargs.get("type"):
            raise ValueError("ActionEnum doesn't allow a type.")

        from ._typehints import ActionTypeHint

        return ActionTypeHint(typehint=self._type)(**kwargs)


@deprecated("""
    ActionOperators was deprecated in v3.0.0 and will be removed in v5.0.0. Now
    types should be used as explained in :ref:`restricted-numbers`.
""")
class ActionOperators:
    """Action to restrict a value with comparison operators."""

    def __init__(self, **kwargs):
        if "expr" in kwargs:
            restrictions = [kwargs["expr"]] if isinstance(kwargs["expr"], tuple) else kwargs["expr"]
            register_key = (tuple(sorted(restrictions)), kwargs.get("type", int), kwargs.get("join", "and"))
            from .typing import registered_types, restricted_number_type

            if register_key in registered_types:
                self._type = registered_types[register_key]
            else:
                self._type = restricted_number_type(
                    None, kwargs.get("type", int), kwargs["expr"], kwargs.get("join", "and")
                )
        else:
            raise ValueError("Expected expr keyword argument.")

    def __call__(self, *args, **kwargs):
        if kwargs.get("type"):
            raise ValueError("ActionOperators doesn't allow a type.")

        from ._typehints import ActionTypeHint

        return ActionTypeHint(typehint=self._type)(**kwargs)


@deprecated("""
    ActionPath was deprecated in v3.11.0 and will be removed in v5.0.0. Paths
    now should be given directly as a type as explained in :ref:`parsing-paths`.
""")
class ActionPath:
    """Action to check and store a path."""

    def __init__(
        self,
        mode: str,
        skip_check: bool = False,
    ):
        from .typing import path_type

        self._type = path_type(mode, skip_check=skip_check)

    def __call__(self, *args, **kwargs):
        if kwargs.get("type"):
            raise ValueError("ActionPath doesn't allow a type.")

        from ._typehints import ActionTypeHint

        return ActionTypeHint(typehint=self._type)(**kwargs)


@deprecated("""
    ActionPathList was deprecated in v4.20.0 and will be removed in v5.0.0. Instead
    use as type ``List[<path_type>]`` with ``sub_configs=True``.
""")
class ActionPathList(Action):
    """Action to check and store a list of file paths read from a plain text file or stream."""

    def __init__(self, mode: Optional[str] = None, rel: str = "cwd", **kwargs):
        """Initializer for ActionPathList instance.

        Args:
            mode: The required type and access permissions among [fdrwxcuFDRWX] as a keyword argument (uppercase means
                not), e.g. ActionPathList(mode='fr').
            rel: Whether relative paths are with respect to current working directory 'cwd' or the list's parent
                directory 'list'.

        Raises:
            ValueError: If any of the parameters (mode or rel) are invalid.
        """
        if mode is not None:
            from .typing import path_type

            self._type = path_type(mode)
            self._rel = rel
            if self._rel not in {"cwd", "list"}:
                raise ValueError(f'rel must be either "cwd" or "list", got {self._rel}.')
        elif "_type" not in kwargs:
            raise ValueError("Expected mode keyword argument.")
        else:
            self._type = kwargs.pop("_type")
            self._rel = kwargs.pop("_rel")
            super().__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        """Parses an argument as a PathList and if valid sets the parsed value to the corresponding key.

        Raises:
            TypeError: If the argument is not a valid PathList.
        """
        if len(args) == 0:
            if "nargs" in kwargs and kwargs["nargs"] not in {"+", 1}:
                raise ValueError('ActionPathList only supports nargs of 1 or "+".')
            kwargs["_type"] = self._type
            kwargs["_rel"] = self._rel
            return ActionPathList(**kwargs)
        setattr(args[1], self.dest, self._check_type(args[2]))
        return None

    def _check_type(self, value):
        if value == []:
            return value
        from ._actions import _is_action_value_list

        islist = _is_action_value_list(self)
        if not islist and not isinstance(value, list):
            value = [value]
        if isinstance(value, list) and all(not isinstance(v, self._type) for v in value):
            path_list_files = value
            value = []
            for path_list_file in path_list_files:
                try:
                    with sys.stdin if path_list_file == "-" else open(path_list_file) as f:
                        path_list = [x.strip() for x in f.readlines()]
                except FileNotFoundError as ex:
                    raise TypeError(f"Problems reading path list: {path_list_file} :: {ex}") from ex
                cwd = os.getcwd()
                if self._rel == "list" and path_list_file != "-":
                    os.chdir(os.path.abspath(os.path.join(path_list_file, os.pardir)))
                try:
                    for num, val in enumerate(path_list):
                        try:
                            path_list[num] = self._type(val)
                        except TypeError as ex:
                            raise TypeError(f"Path number {num + 1} in list {path_list_file}, {ex}") from ex
                finally:
                    os.chdir(cwd)
                value += path_list
        return value


@deprecated("""
    set_url_support was deprecated in v3.12.0 and will be removed in v5.0.0.
    Optional config read modes should now be set using function
    set_parsing_settings.
""")
def set_url_support(enabled: bool):
    """Enables/disables URL support for config read mode."""
    from ._optionals import _get_config_read_mode, _set_config_read_mode

    _set_config_read_mode(
        urls_enabled=enabled,
        fsspec_enabled=True if "s" in _get_config_read_mode() else False,
    )


@deprecated("""
    set_config_read_mode was deprecated in v4.39.0 and will be removed in
    v5.0.0. Optional config read modes should now be set using function
    set_parsing_settings.
""")
def set_config_read_mode(
    urls_enabled: bool = False,
    fsspec_enabled: bool = False,
):
    """Enables/disables optional config read modes."""
    from ._optionals import _set_config_read_mode

    _set_config_read_mode(
        urls_enabled=urls_enabled,
        fsspec_enabled=fsspec_enabled,
    )


@deprecated("""
    get_config_read_mode was deprecated in v4.39.0 and will be removed in
    v5.0.0. The config read mode is internal and thus shouldn't be used.
""")
def get_config_read_mode() -> str:
    """Returns the current config reading mode."""
    from ._optionals import _get_config_read_mode

    return _get_config_read_mode()


@deprecated("""
    set_docstring_parse_options was deprecated in v4.39.0 and will be removed in
    v5.0.0. Docstring parse options should now be set using function
    set_parsing_settings.
""")
def set_docstring_parse_options(style=None, attribute_docstrings: Optional[bool] = None):
    """Sets options for docstring parsing."""
    from ._optionals import _set_docstring_parse_options

    _set_docstring_parse_options(
        style=style,
        attribute_docstrings=attribute_docstrings,
    )


cli_return_parser_message = """
    The return_parser parameter was deprecated in v4.5.0 and will be removed in
    v5.0.0. Instead of this use function capture_parser.
"""

auto_cli_implicit_components_message = """
    Implicit components discovery in auto_cli was deprecated in v4.49.0 and
    will be removed in v5.0.0. Pass components explicitly, explicit is better
    than implicit.
"""


def get_implicit_auto_cli_components(stacklevel):
    deprecation_warning("auto_cli.components", auto_cli_implicit_components_message, stacklevel=stacklevel + 1)
    caller = inspect.stack()[stacklevel][0]
    module = inspect.getmodule(caller)
    components = [
        v for v in vars(module).values() if ((inspect.isclass(v) or callable(v)) and inspect.getmodule(v) is module)
    ]
    if len(components) == 0:
        raise ValueError(
            "Either components parameter must be given or there must be at least one "
            "function or class among the locals in the context where CLI is called."
        )
    return components


def deprecation_warning_cli_return_parser(stacklevel):
    deprecation_warning("CLI.__init__.return_parser", cli_return_parser_message, stacklevel=stacklevel)


logger_property_none_message = """
    Setting the logger property to None was deprecated in v4.10.0 and will raise
    an exception in v5.0.0. Use False instead.
"""

env_prefix_property_none_message = """
    Setting the env_prefix property to None was deprecated in v4.11.0 and will raise
    an exception in v5.0.0. Use True instead.
"""


path_skip_check_message = """
    The skip_check parameter of Path was deprecated in v4.20.0 and will be
    removed in v5.0.0. There is no reason to use a Path type if its checks are
    disabled. Instead use a type such as str or os.PathLike.
"""


def path_skip_check_deprecation(stacklevel=2):
    deprecation_warning("Path.__init__", path_skip_check_message, stacklevel=stacklevel)


path_immutable_attrs_message = """
    Path objects are not meant to be mutable. To make this more explicit,
    attributes have been renamed and changed into properties without setters.
    Please update your code to use the new property names and don't modify path
    attributes. The changes are: ``rel_path`` -> ``relative`` and ``abs_path``
    -> ``absolute``, ``cwd`` no name change, ``skip_check`` will be removed.
"""

path_call_message = """
    Calling Path objects is deprecated and will be removed in v5.0.0. Use the
    ``absolute`` or ``relative`` properties instead.
"""

path_get_content_message = """
    ``Path.get_content`` was deprecated in v4.49.0 and will be removed in
    v5.0.0. Instead use ``Path.read_text`` for text and ``Path.open`` for binary
    data.
"""


class PathDeprecations:
    """Deprecated methods for Path."""

    @property
    def rel_path(self):
        deprecation_warning("Path attr get", path_immutable_attrs_message)
        return self._relative

    @rel_path.setter
    def rel_path(self, rel_path):
        deprecation_warning("Path attr set", path_immutable_attrs_message)
        self._relative = rel_path

    @property
    def abs_path(self):
        deprecation_warning("Path attr get", path_immutable_attrs_message)
        return self._absolute

    @abs_path.setter
    def abs_path(self, abs_path):
        deprecation_warning("Path attr set", path_immutable_attrs_message)
        self._absolute = abs_path

    @property
    def cwd(self):
        return self._cwd

    @cwd.setter
    def cwd(self, cwd):
        deprecation_warning("Path attr set", path_immutable_attrs_message)
        self._cwd = cwd

    def _deprecated_kwargs(self, kwargs):
        from ._util import get_private_kwargs

        self._skip_check = get_private_kwargs(kwargs, skip_check=False)
        if self._skip_check:
            path_skip_check_deprecation()

    def _repr_skip_check(self, name):
        if self._skip_check:
            name += "_skip_check"
        return name

    @property
    def skip_check(self):
        return self._skip_check

    @skip_check.setter
    def skip_check(self, skip_check):
        deprecation_warning("Path attr set", path_immutable_attrs_message)
        self._skip_check = skip_check

    @deprecated(path_call_message)
    def __call__(self, absolute: bool = True) -> str:
        return self._absolute if absolute else self._relative

    def get_content(self, mode: str = "r"):
        deprecation_warning("Path.get_content", path_get_content_message)
        if self._std_io:  # type: ignore[attr-defined]
            from ._paths import _read_cached_stdin

            return _read_cached_stdin()
        elif self._is_url:  # type: ignore[attr-defined]
            from ._optionals import import_requests

            assert mode == "r"
            requests = import_requests("Path.get_content")
            response = requests.get(self._absolute)
            response.raise_for_status()
            return response.text
        elif self._is_fsspec:  # type: ignore[attr-defined]
            from ._optionals import import_fsspec

            fsspec = import_fsspec("Path.get_content")
            with fsspec.open(self._absolute, mode) as handle:
                with handle as input_file:
                    return input_file.read()
        else:
            with open(self._absolute, mode) as input_file:
                return input_file.read()


@deprecated("""
    usage_and_exit_error_handler was deprecated in v4.20.0 and will be removed
    in v5.0.0. With the removal of error_handler, there is no longer a need for
    this function.
""")
def usage_and_exit_error_handler(parser: ArgumentParser, message: str) -> None:
    """Prints the usage and exits with error code 2 (same behavior as argparse).

    Args:
        parser: The parser object.
        message: The message describing the error being handled.
    """
    parser.print_usage(sys.stderr)
    args = {"prog": parser.prog, "message": message}
    sys.stderr.write("%(prog)s: error: %(message)s\n" % args)
    parser.exit(2)


error_handler_message = """
    ArgumentParser's error_handler was deprecated in v4.20.0 and will be removed
    in v5.0.0. Instead use the new exit_on_error parameter from argparse.
"""


def deprecation_warning_error_handler(stacklevel):
    deprecation_warning("ArgumentParser.error_handler", error_handler_message, stacklevel=stacklevel)


default_meta_message = """
    ``default_meta`` property was deprecated in v4.44.0 and will be removed in
    v5.0.0. After removal, config objects will always include metadata. To
    remove metadata from a config object, do ``.clone(with_meta=False)``.
"""


class ParserDeprecations:
    """Helper class for ArgumentParser deprecations. Will be removed in v5.0.0."""

    _instantiators: Optional[InstantiatorsDictType] = None

    def __init__(self, *args, error_handler=False, default_meta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_handler = error_handler
        if default_meta is None:
            self._default_meta = True
        else:
            self.default_meta = default_meta

    @property
    @deprecated("error_handler property is deprecated and will be removed in v5.0.0.")
    def error_handler(self) -> Optional[Callable[[ArgumentParser, str], None]]:
        """Property for the error_handler function that is called when there are parsing errors.

        :getter: Returns the current error_handler function.
        :setter: Sets a new error_handler function (Callable[self, message:str] or None).

        Raises:
            ValueError: If an invalid value is given.
        """
        return self._error_handler

    @error_handler.setter
    def error_handler(self, error_handler):
        if error_handler is not False:
            stacklevel = 2
            stack = inspect.stack()[1]
            if stack.filename.endswith(os.fspath(Path("jsonargparse", "_deprecated.py"))):
                stacklevel = 5
            deprecation_warning_error_handler(stacklevel)
        if callable(error_handler) or error_handler in {None, False}:
            self._error_handler = error_handler
        else:
            raise ValueError("error_handler can be either a Callable or None.")

    @property
    @deprecated(default_meta_message)
    def default_meta(self) -> bool:
        """Whether by default metadata is included in config objects.

        :getter: Returns the current default metadata setting.
        :setter: Sets the default metadata setting.

        Raises:
            ValueError: If an invalid value is given.
        """
        return self._default_meta

    @default_meta.setter
    def default_meta(self, default_meta: bool):
        if isinstance(default_meta, bool):
            deprecation_warning("ArgumentParser.default_meta", default_meta_message)
            self._default_meta = default_meta
        else:
            raise ValueError("default_meta expects a boolean.")

    @deprecated("""
        ``instantiate_classes`` was deprecated in v4.49.0 and will be removed in v5.0.0.
        Instead use ``instantiate``.
    """)
    def instantiate_classes(self, cfg: Union[Namespace, Dict[str, Any]], **kwargs) -> Union[Namespace, Dict[str, Any]]:
        if isinstance(cfg, dict):
            cfg = self._apply_actions(cfg)  # type: ignore[attr-defined]
        cfg = self.instantiate(cfg, **kwargs)  # type: ignore[attr-defined]
        return cfg.as_dict() if self._parse_as_dict else cfg  # type: ignore[attr-defined]

    @deprecated("""
        instantiate_subclasses was deprecated in v4.0.0 and will be removed in v5.0.0.
        Instead use instantiate.
    """)
    def instantiate_subclasses(self, cfg: Namespace) -> Namespace:
        return self.instantiate(cfg, instantiate_groups=False)  # type: ignore[attr-defined]

    @deprecated("""
        add_dataclass_arguments was deprecated in v4.35.0 and will be removed in
        v5.0.0. Instead use add_class_arguments.
    """)
    def add_dataclass_arguments(self, *args, **kwargs):
        if "title" in kwargs:
            kwargs["help"] = kwargs.pop("title")
        return self.add_class_arguments(*args, **kwargs)

    @deprecated("""
        ArgumentParser.check_config was deprecated in v4.35.0 and will be removed in
        v5.0.0. Instead use validate.
    """)
    def check_config(self, *args, **kwargs):
        return self.validate(*args, **kwargs)

    @deprecated("""
        ``ArgumentParser.add_instantiator`` was deprecated in v4.49.0 and will be
        removed in v5.0.0. Use the global function ``jsonargparse.add_instantiator``
        instead.
    """)
    def add_instantiator(
        self,
        instantiator,
        class_type,
        subclasses: bool = True,
        prepend: bool = False,
    ) -> None:
        if self._instantiators is None:
            self._instantiators = {}
        _register_instantiator(self._instantiators, instantiator, class_type, subclasses=subclasses, prepend=prepend)

    def _get_parser_instantiators(self) -> InstantiatorsDictType:
        instantiators = self._instantiators or {}
        if hasattr(self, "parent_parser"):
            parent_instantiators = self.parent_parser._get_parser_instantiators()
            instantiators = instantiators.copy()
            instantiators.update({k: v for k, v in parent_instantiators.items() if k not in instantiators})
        return instantiators

    @deprecated("""
        ``ArgumentParser.merge_config`` was deprecated in v4.50.0 and will be
        removed in v5.0.0. There is no replacement since this is for internal use.
    """)
    def merge_config(self, cfg_from: Namespace, cfg_to: Namespace) -> Namespace:
        from ._util import merge_config

        return merge_config(self, cfg_from, cfg_to)


def deprecated_skip_check(component, kwargs: dict, skip_validation: bool, stacklevel: int = 3) -> bool:
    skip_check = kwargs.pop("skip_check", None)
    if skip_check is not None:
        skip_validation = skip_check
        deprecation_warning(
            component,
            (
                "skip_check parameter was deprecated in v4.35.0 and will be removed in "
                "v5.0.0. Instead use skip_validation."
            ),
            stacklevel=stacklevel,
        )
    return skip_validation


deprecated_valid_flags = {"skip_null": "skip_null"}


def deprecated_skip_none(component, kwargs: dict, skip_unset: bool, stacklevel: int = 3) -> bool:
    skip_none = kwargs.pop("skip_none", None)
    if skip_none is not None:
        skip_unset = skip_none
        deprecation_warning(
            component,
            ("skip_none parameter was deprecated in v4.49.0 and will be removed in v5.0.0. Instead use skip_unset."),
            stacklevel=stacklevel,
        )
    return skip_unset


def deprecated_skip_null(flag: str) -> bool:
    if flag == "skip_null":
        deprecation_warning(
            "skip_null",
            (
                "skip_null flag for --print_config was deprecated in v4.49.0 and will be removed in "
                "v5.0.0. Instead use skip_unset."
            ),
        )
        return True
    return False


def deprecated_yaml_comments(kwargs: dict, with_comments: bool, stacklevel: int = 3) -> bool:
    yaml_comments = kwargs.pop("yaml_comments", None)
    if yaml_comments is not None:
        deprecation_warning(
            deprecated_yaml_comments,
            (
                "yaml_comments parameter was deprecated in v4.44.0 and will be removed in "
                "v5.0.0. Instead use with_comments."
            ),
            stacklevel=stacklevel,
        )
        return yaml_comments
    return with_comments


ParserError = ArgumentError


def deprecated_module(module_name, mappings=None):
    module_path = f"jsonargparse.{module_name}"
    module = ModuleType(module_path, f"deprecated {module_path}")
    sys.modules[module_path] = module

    @deprecated(f"""
        Only use the public API as described in
        https://jsonargparse.readthedocs.io/en/stable/#api-reference. Importing
        from {module_path} is kept only to avoid breaking code that does not
        correctly use the public API. It will no longer be available from v5.0.0.
    """)
    def __getattr__(name):
        new_module = f"_{module_name}"
        if mappings and name in mappings:
            new_module, name = mappings[name]
        if module_name == "typehints" and name == "lazy_instance":
            from jsonargparse.typing import lazy_instance

            return lazy_instance
        return getattr(import_module(f"jsonargparse.{new_module}"), name)

    module.__getattr__ = __getattr__
    module.__dict__["__file__"] = str(Path(__file__).parent / f"{module_name}.py")
    module.__dict__["__path__"] = module_path


deprecated_module("actions")
deprecated_module("cli")
deprecated_module("core")
deprecated_module("deprecated")
deprecated_module("formatters")
deprecated_module("jsonnet")
deprecated_module("jsonschema")
deprecated_module("link_arguments")
deprecated_module("loaders_dumpers")
deprecated_module("namespace")
deprecated_module("parameter_resolvers")
deprecated_module("signatures")
deprecated_module("typehints")
deprecated_module("util")
deprecated_module(
    "optionals",
    {
        "import_docstring_parse": ("_optionals", "import_docstring_parser"),
    },
)


@deprecated("""
    ActionJsonnetExtVars was deprecated in v4.24.0 and will be removed in
    v5.0.0. Instead use ``type=dict``.
""")
class ActionJsonnetExtVars:
    """Action to add argument to provide ext_vars for jsonnet parsing."""

    def __call__(self, *args, **kwargs):
        from ._typehints import ActionTypeHint

        action = ActionTypeHint(typehint=dict)(**kwargs)
        action.jsonnet_ext_vars = True
        return action


@deprecated("""
    LoggerProperty was deprecated in v4.40.0 and will be removed from the public
    API in v5.0.0. There is no replacement since jsonargparse is not a logging
    library. A similar class can be found in reconplogger package.
""")
class LoggerProperty(InternalLoggerProperty):
    """Adds a logger property, intended for internal use."""


@deprecated("""
    namespace_to_dict was deprecated in v4.40.0 and will be removed in v5.0.0.
    Instead you can use ``.clone().as_dict()`` or ``.as_dict()``.
""")
def namespace_to_dict(namespace: Namespace) -> Dict[str, Any]:
    """Returns a copy of a nested namespace converted into a nested dictionary."""
    return namespace.clone().as_dict()


@deprecated("""
    dict_to_namespace was deprecated in v4.43.0 and will be removed in v5.0.0.
    No replacement is provided because blindly converting a dictionary to a
    namespace may not yield the same results as using a parser, which could lead
    to confusion.
""")
def dict_to_namespace(cfg_dict: dict[str, Any]) -> Namespace:
    """Converts a nested dictionary into a nested namespace."""
    from ._namespace import dict_to_namespace as _dict_to_namespace

    return _dict_to_namespace(cfg_dict)


@overload
def strip_meta(cfg: "Namespace") -> "Namespace": ...  # pragma: no cover


@overload
def strip_meta(cfg: Dict[str, Any]) -> Dict[str, Any]: ...  # pragma: no cover


@deprecated("""
    strip_meta was deprecated in v4.43.0 and will be removed in v5.0.0.
    Instead use ``.clone(with_meta=False)``.
""")
def strip_meta(cfg):
    """Removes all metadata keys from a configuration object."""
    from ._namespace import remove_meta

    return remove_meta(cfg)


def is_meta_key(key: str) -> bool:
    from ._namespace import meta_keys, split_key_leaf

    leaf_key = split_key_leaf(key)[-1]
    return leaf_key in meta_keys


class NamespaceDeprecations:
    """Helper class for Namespace deprecations. Will be removed in v5.0.0."""

    @deprecated("""
        get_sorted_keys method was deprecated in v4.49.0 and will be removed in
        v5.0.0. There is no replacement since this is for internal use and
        developers can call .keys() and then sort.
    """)
    def get_sorted_keys(self, branches: bool = True, key_filter: Callable = is_meta_key) -> list[str]:
        """Deprecated method"""
        from ._namespace import split_key

        keys = [k for k in self.keys() if not key_filter(k)]  # type: ignore[attr-defined]
        if branches:
            for key in [k for k in keys if "." in k]:
                key_split = split_key(key)
                for num in range(len(key_split) - 1):
                    parent_key = ".".join(key_split[: num + 1])
                    if parent_key not in keys:
                        keys.append(parent_key)
        keys.sort(key=lambda x: -len(split_key(x)))
        return keys

    @deprecated("""
        get_value_and_parent method was deprecated in v4.49.0 and will be
        removed in v5.0.0. There is no replacement since this is for internal
        use and developers can get the parent and leaf separately.
    """)
    def get_value_and_parent(self, key: str) -> tuple[Any, Namespace, str]:
        """Deprecated method"""
        leaf_key, parent_ns, _ = self._parse_required_key(key)  # type: ignore[attr-defined]
        return parent_ns[leaf_key], parent_ns, leaf_key


def _patch_namespace_deprecations() -> None:
    Namespace.get_sorted_keys = NamespaceDeprecations.get_sorted_keys  # type: ignore[attr-defined]
    Namespace.get_value_and_parent = NamespaceDeprecations.get_value_and_parent  # type: ignore[attr-defined]


_patch_namespace_deprecations()


class HelpFormatterDeprecations:
    """Helper class for DefaultHelpFormatter deprecations. Will be removed in v5.0.0."""

    def __init__(self, *args, **kwargs):
        from jsonargparse._formatters import YAMLCommentFormatter

        super().__init__(*args, **kwargs)
        self._yaml_formatter = YAMLCommentFormatter(self)

    @deprecated("The add_yaml_comments method is deprecated and will be removed in v5.0.0.")
    def add_yaml_comments(self, cfg: str) -> str:
        """Adds help text as yaml comments."""
        return self._yaml_formatter.add_yaml_comments(cfg)

    @deprecated("The set_yaml_start_comment method is deprecated and will be removed in v5.0.0.")
    def set_yaml_start_comment(self, text: str, cfg: ruamelCommentedMap):
        """Sets the start comment to a ruamel.yaml object.

        Args:
            text: The content to use for the comment.
            cfg: The ruamel.yaml object.
        """
        self._yaml_formatter.set_yaml_start_comment(text, cfg)

    @deprecated("The set_yaml_group_comment method is deprecated and will be removed in v5.0.0.")
    def set_yaml_group_comment(self, text: str, cfg: ruamelCommentedMap, key: str, depth: int):
        """Sets the comment for a group to a ruamel.yaml object.

        Args:
            text: The content to use for the comment.
            cfg: The parent ruamel.yaml object.
            key: The key of the group.
            depth: The nested level of the group.
        """
        self._yaml_formatter.set_yaml_group_comment(text, cfg, key, depth)

    @deprecated("The set_yaml_argument_comment method is deprecated and will be removed in v5.0.0.")
    def set_yaml_argument_comment(self, text: str, cfg: ruamelCommentedMap, key: str, depth: int):
        """Sets the comment for an argument to a ruamel.yaml object.

        Args:
            text: The content to use for the comment.
            cfg: The parent ruamel.yaml object.
            key: The key of the argument.
            depth: The nested level of the argument.
        """
        self._yaml_formatter.set_yaml_argument_comment(text, cfg, key, depth)


@deprecated("""
    compose_dataclasses is deprecated and will be removed in v5.0.0. There is
    no direct replacement, whoever is interested can copy the code from an old
    release.
""")
def compose_dataclasses(*args):
    """Returns a dataclass inheriting all given dataclasses and properly handling __post_init__."""

    import dataclasses

    @dataclasses.dataclass
    class ComposedDataclass(*args):
        def __post_init__(self):
            for arg in args:
                if hasattr(arg, "__post_init__"):
                    arg.__post_init__(self)

    return ComposedDataclass


def deprecated_implicit_subcommand(component, subcommand_keys: list[str], subcommand: str, dest: str):
    stack = inspect.stack()
    deprecation_warning(
        component,
        (
            f"Multiple subcommand settings provided ({', '.join(subcommand_keys)}) without an "
            f"explicit '{dest}' key. Subcommand '{subcommand}' will be used. From v5.0.0 "
            "providing an explicit subcommand will be required."
        ),
        stacklevel=7 if Path(stack[6].filename).name == "_deprecated.py" else 6,
    )


instantiate_subclass_spec_in_any_message = """
    Instantiating a subclass spec given as value for a type that accepts any value, i.e. ``Any``,
    ``object`` or ``Unvalidated<...>``, was deprecated in v4.51.0. From v5.0.0 these values will no
    longer be instantiated, the subclass spec being kept as is, so that the code that receives it
    decides whether to instantiate it. Set ``instantiate_subclass_spec_in_any=False`` in
    ``set_parsing_settings`` to get the future behavior now and silence this warning. Setting it to
    ``True`` keeps the current behavior, but it is discouraged since it means that a config is able
    to instantiate any class, which can be a security risk.
"""


def unset_instantiate_subclass_spec_in_any() -> bool:
    """Value used for the ``instantiate_subclass_spec_in_any`` setting when it is unset.

    Remove in v5.0.0, changing the default of the setting from ``None`` to
    ``False``, and thus making ``_typehints.instantiate_subclass_spec_in_any``
    only get the setting.
    """
    deprecation_warning("instantiate_subclass_spec_in_any", instantiate_subclass_spec_in_any_message)
    return True


def renamed_parameter_warning(renames: dict[str, str], stacklevel: int = 1):

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for old_name, new_name in renames.items():
                if old_name in kwargs:
                    deprecation_warning(
                        func,
                        (
                            f"Parameter '{old_name}' was renamed to '{new_name}' in v4.50.0. "
                            "The old name will stop working in v5.0.0."
                        ),
                        stacklevel=stacklevel,
                    )
                    if new_name not in kwargs:
                        kwargs[new_name] = kwargs.pop(old_name)
            return func(*args, **kwargs)

        return wrapper

    return decorator
