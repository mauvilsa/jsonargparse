"""Collection of general functions and classes."""

import functools
import inspect
import os
import textwrap
import warnings
import weakref
from argparse import ArgumentError
from collections import namedtuple
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from importlib import import_module
from types import BuiltinFunctionType, FunctionType, ModuleType
from typing import (
    Any,
    Type,
    Union,
)

from ._common import (
    check_import_path,
    config_schema_key,
    get_generic_origin,
    get_parsing_setting,
    get_partial_method,
    parser_capture,
    parser_context,
)
from ._loaders_dumpers import json_compact_dump, load_value
from ._namespace import Namespace, value_source_context
from ._optionals import _get_config_read_mode
from ._paths import Path
from ._type_checking import ArgumentParser

__all__ = [
    "capture_parser",
    "register_unresolvable_import_paths",
]


NoneType = type(None)


default_config_option_help = "Path to a configuration file."
config_load_stack: ContextVar[tuple[tuple[str, str], ...]] = ContextVar("config_load_stack", default=())


def argument_error(message: str, default_config_file: str | None = None) -> ArgumentError:
    ex = ArgumentError(None, message)
    if default_config_file:
        ex.default_config_file = default_config_file  # type: ignore[attr-defined]
    return ex


def merge_config(parser, source: Namespace, target: Namespace) -> Namespace:
    """Merges the first configuration into the second configuration.

    Args:
        parser: The parser object.
        source: The configuration from which to merge.
        target: The configuration into which to merge.

    Returns:
        A new object with the merged configuration.
    """
    from ._typehints import ActionTypeHint

    with value_source_context(None):  # merging does not change where the values came from
        source = source.clone()
        target = target.clone()
        with parser_context(parent_parser=parser):
            ActionTypeHint.discard_init_args_on_class_path_change(parser, target, source)
        target.update(source)
    return target


def _config_path_id(cfg_path: Path) -> tuple[str, str]:
    path_id = cfg_path.absolute
    if not (cfg_path.is_url or cfg_path.is_fsspec):
        path_id = os.path.realpath(path_id)
    return path_id, str(cfg_path)


def _format_config_load_chain(stack: tuple[tuple[str, str], ...], path_id: tuple[str, str]) -> str:
    chain = list(stack) + [path_id]
    for num, (stack_path, _) in enumerate(chain):
        if stack_path == path_id[0]:
            chain = chain[num:]
            break
    return " -> ".join(display for _, display in chain)


@contextmanager
def load_config_path_context(cfg_path: Path | None) -> Iterator[None]:
    if cfg_path is None:
        yield
        return
    path_id = _config_path_id(cfg_path)
    stack = config_load_stack.get()
    if path_id[0] in {path for path, _ in stack}:
        chain = _format_config_load_chain(stack, path_id)
        raise TypeError(f"Config file loop detected: {chain}")
    token = config_load_stack.set(stack + (path_id,))
    try:
        yield
    finally:
        config_load_stack.reset(token)


class JsonargparseWarning(UserWarning):
    pass


def warning(message, category=JsonargparseWarning, stacklevel=1):
    message = textwrap.fill(textwrap.dedent(message), 110).strip()
    warnings.warn(
        "\n" + textwrap.indent(message, "    ") + "\n",
        category=category,
        stacklevel=stacklevel + 1,
    )


class CaptureParserException(Exception):
    def __init__(self, parser: ArgumentParser | None):
        self.parser = parser
        super().__init__("" if parser else "No parse_args call to capture the parser.")


def capture_parser(function: Callable, *args, **kwargs) -> ArgumentParser:
    """Returns the parser object used within the execution of a function.

    The function execution is stopped on the start of the call to
    :meth:`parse_args <.ArgumentParser.parse_args>`. No parsing is done or
    execution of instructions after the :meth:`parse_args
    <.ArgumentParser.parse_args>`.

    Args:
        function: A callable that internally creates a parser and calls :meth:`parse_args <.ArgumentParser.parse_args>`.
        *args: Positional arguments used to run the function.
        **kwargs: Keyword arguments used to run the function.

    Raises:
        CaptureParserException: If the function does not call :meth:`parse_args <.ArgumentParser.parse_args>`.
    """
    try:
        with parser_context(parser_capture=True):
            function(*args, **kwargs)
    except CaptureParserException as ex:
        return ex.parser  # type: ignore[return-value]
    raise CaptureParserException(None)


def return_parser_if_captured(parser: ArgumentParser):
    if parser_capture.get():
        raise CaptureParserException(parser)


def identity(value):
    return value


NestedArg = namedtuple("NestedArg", "key val")

config_include_key = "__include__"


class ComposedConfig:
    """A config that has an ``__include__``, kept unmerged until reaching the code that merges its value.

    Merging depends on what a key is, e.g. a class type discards the ``init_args`` that a new
    ``class_path`` does not accept, which is only known once the key is matched to an argument.
    So the included configs are not merged when loaded, but where configs given one after the
    other are merged, making an include behave exactly the same.
    """

    __slots__ = ("includes", "own")

    def __init__(self, includes: list, own: Any):
        self.includes = includes  # the included configs and the paths they were loaded from
        self.own = own  # what the config sets itself, which overrides the included configs


def resolve_config_includes(value: Any) -> Any:
    """Replaces in a loaded config each mapping that has an ``__include__`` with a ComposedConfig.

    Only done when ``config_include_enabled``. An ``__include__`` accepts a config path or a list
    of them, relative to the config that has the key, and is accepted at any level. It must be
    the first key, since what follows overrides what the included configs set.

    Args:
        value: The loaded config, which is not modified.

    Returns:
        The config with its includes loaded.
    """
    if not get_parsing_setting("config_include_enabled"):
        return value
    if isinstance(value, list):
        return [resolve_config_includes(item) for item in value]
    if not isinstance(value, dict):
        return value
    includes = []
    if config_include_key in value:
        keys = [k for k in value if k != config_schema_key]  # the schema key is only meant for editors
        if keys[0] != config_include_key:
            raise TypeError(
                f'"{config_include_key}" must be the first key where it is given, since what follows '
                f"overrides the included configs. Got keys: {keys}"
            )
        includes = [_load_included(path) for path in _include_paths(value[config_include_key])]
    value = {name: resolve_config_includes(item) for name, item in value.items() if name != config_include_key}
    return ComposedConfig(includes, value) if includes else value


def _include_paths(value: Any) -> list:
    paths = value if isinstance(value, list) else [value]
    if not all(isinstance(path, str) for path in paths):
        raise TypeError(f'"{config_include_key}" expects a config path or a list of config paths. Got value: {value}')
    return paths


def _load_included(path_str: str) -> tuple[Any, Path]:
    """Loads a config to be included, together with the path it was loaded from."""
    from ._loaders_dumpers import get_loader_exceptions

    try:
        path = Path(path_str, mode=_get_config_read_mode())
    except TypeError as ex:
        raise TypeError(f'"{config_include_key}" value "{path_str}": {ex}') from ex
    with load_config_path_context(path), path.relative_path_context():
        try:
            value = load_value(path.read_text())
        except get_loader_exceptions() as ex:
            raise TypeError(f'Problems parsing config included from "{path_str}": {ex}') from ex
        if not isinstance(value, dict):
            raise TypeError(f'Expected config included from "{path_str}" to be a mapping. Got value: {value}')
        value.pop(config_schema_key, None)  # only meant for editors, also when included into a plain dict
        return resolve_config_includes(value), path


def check_no_composed_config(value: Any, key: str = "") -> None:
    """Fails if an include reached a value that has nothing to merge it, e.g. an untyped argument."""
    if isinstance(value, ComposedConfig):
        raise TypeError(f'Key "{key}": "{config_include_key}" is not supported for this argument')
    if isinstance(value, (dict, Namespace)):
        for name, item in value.items():
            check_no_composed_config(item, f"{key}.{name}" if key else name)
    elif isinstance(value, list):
        for num, item in enumerate(value):
            check_no_composed_config(item, f"{key}[{num}]")


def parse_value_or_config(value: Any, enable_path: bool = True, simple_types: bool = False) -> tuple[Any, Path | None]:
    """Parses yaml/json config in a string or a path"""
    nested_arg: bool | NestedArg = False
    if isinstance(value, NestedArg):
        nested_arg = value
        value = nested_arg.val
    cfg_path = None
    if enable_path and type(value) is str and value != "-":
        try:
            cfg_path = Path(value, mode=_get_config_read_mode())
        except TypeError:
            pass
        else:
            with load_config_path_context(cfg_path), cfg_path.relative_path_context():
                value = load_value(cfg_path.read_text(), simple_types=simple_types)
                value = resolve_config_includes(value)
    if type(value) is str and value.strip() != "":
        parsed_val = load_value(value, simple_types=simple_types)
        if type(parsed_val) is not str:
            value = resolve_config_includes(parsed_val)
    if isinstance(value, dict) and cfg_path is not None:
        value["__path__"] = cfg_path
    if nested_arg:
        value = NestedArg(key=nested_arg.key, val=value)  # type: ignore[union-attr]
    return value, cfg_path


code_given_classes: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def get_code_given_class_path(cls: type) -> str:
    """Returns the import path of a class given in code, e.g. as a type.

    A class that can't be imported from its path, like one defined in a
    function, is remembered so that :func:`import_object` resolves its path.
    """
    cls = get_generic_origin(cls)
    path = get_import_path(cls)
    try:
        importable = import_object(path, check_path=False) is cls
    except (ValueError, ImportError, AttributeError):
        importable = False
    if not importable:
        code_given_classes[path] = cls
    return path


def import_object(name: str, check_path: bool = True):
    """Returns an object in a module given its dot import path.

    ``check_path`` must only be false when the path comes from code, e.g. a type
    annotation, instead of from a parsed value.
    """
    if isinstance(name, str) and name in code_given_classes:
        return code_given_classes[name]
    if not isinstance(name, str) or "." not in name:
        raise ValueError(f"Expected a dot import path string: {name}")
    if not all(x.isidentifier() for x in name.split(".")):
        raise ValueError(f"Unexpected import path format: {name}")
    if check_path:
        check_import_path(name)
    name_module, name_object = name.rsplit(".", 1)
    try:
        parent = __import__(name_module, fromlist=[name_object])
    except ModuleNotFoundError as ex:
        if "." not in name_module:
            raise ex
        name_module, name_object1 = name_module.rsplit(".", 1)
        parent = getattr(__import__(name_module, fromlist=[name_object1]), name_object1)
    obj = getattr(parent, name_object)
    if check_path:
        for canonical in canonical_import_paths(obj):
            if canonical != name:
                check_import_path(canonical)
    if not (inspect.isclass(obj) or inspect.ismodule(obj)):
        # an instance doesn't know where it was imported from, so it is remembered to make it serializable
        resolved_import_paths.add(obj, name)
    return obj


def canonical_import_path(obj) -> str | None:
    """Returns where an object is defined, which can differ from the path used to import it.

    Modules commonly import others, e.g. ``import os``, so ``some.module.os.system``
    imports and gives the same object as ``os.system``. Not ``get_import_path``
    because that gives the shortest path, which can be a re-export that hides where
    the object is defined, and it fails for objects that have no import path.
    """
    if inspect.ismodule(obj):
        return obj.__name__
    if not (inspect.isclass(obj) or inspect.isroutine(obj)):
        return None
    module = getattr(obj, "__module__", None)
    qualname = getattr(obj, "__qualname__", None)
    return f"{module}.{qualname}" if module and qualname else None


def canonical_import_paths(obj) -> set:
    """Returns the canonical paths that must be allowed for an object to be usable.

    A class, routine or module has a single defining path. An object that instead
    wraps or exposes a callable without an import path of its own, e.g. a
    ``functools.partial`` or a callable instance, is denied by the callable it
    reaches: the bound function for a partial and the defining class for an
    instance. Otherwise binding or instancing a denied callable under an allowed
    name would evade the denylist.
    """
    paths: set = set()
    stack = [obj]
    while stack:
        current = stack.pop()
        partial_method = get_partial_method(current)
        if partial_method:
            current = partial_method.func  # a method from a partialmethod is denied by the callable it binds
        canonical = canonical_import_path(current)
        if canonical:
            paths.add(canonical)
        if isinstance(current, functools.partial):
            stack.append(current.func)  # a partial is denied by the callable it binds
        elif not (inspect.isclass(current) or inspect.ismodule(current) or inspect.isroutine(current)):
            stack.append(type(current))  # a callable instance is denied by its class
    return paths


unresolvable_import_paths: dict[Any, str] = {}


def register_unresolvable_import_paths(*modules: ModuleType):
    """Saves import paths of module objects for which its import path is unresolvable from the object alone.

    Objects with unresolvable import paths have the ``__module__`` attribute set to ``None``.
    """
    for module in modules:
        for val in vars(module).values():
            if (
                getattr(val, "__module__", None) is None
                and getattr(val, "__name__", None)
                and type(val) in {BuiltinFunctionType, FunctionType, Type, type}
            ):
                unresolvable_import_paths[val] = f"{module.__name__}.{val.__name__}"


def get_partial_method_path(partial_method: functools.partialmethod) -> str:
    """Import path of a partialmethod, found in the classes of the module that defines the function it binds."""
    module = import_module(partial_method.func.__module__)
    for cls in [v for v in vars(module).values() if inspect.isclass(v)]:
        name = next((k for k, v in vars(cls).items() if v is partial_method), None)
        if name:
            return f"{get_import_path(cls)}.{name}"
    raise ValueError(f"Not possible to determine the import path for partialmethod {partial_method}.")


def get_module_var_path(module_path: str, value: Any) -> str | None:
    module = import_module(module_path)
    for name, var in vars(module).items():
        if var is value:
            return module_path + "." + name
    return None


class ResolvedImportPaths:
    """Remembers the import path that instances were resolved from.

    The import path of an instance can't be derived from the object itself, so
    without this a value given as an import path to an instance would not be
    serializable, even though it came from an import path. Entries are keyed by
    id, weak references being used to discard an entry when its instance is
    garbage collected, thus avoiding that an id is reused for another object.
    """

    def __init__(self) -> None:
        self._paths: dict[int, tuple[Any, str]] = {}

    def add(self, instance: Any, import_path: str) -> None:
        key = id(instance)
        try:
            ref = weakref.ref(instance, lambda _: self._paths.pop(key, None))
        except TypeError:
            return  # instance doesn't support weak references
        self._paths[key] = (ref, import_path)

    def get(self, instance: Any) -> str | None:
        entry = self._paths.get(id(instance))
        if entry and entry[0]() is instance:
            return entry[1]
        return None


resolved_import_paths = ResolvedImportPaths()


def get_import_path(value: Any) -> str:
    """Returns the shortest dot import path for the given object."""
    remembered = resolved_import_paths.get(value)
    if remembered:
        return remembered
    partial_method = get_partial_method(value)
    if partial_method:
        return get_partial_method_path(partial_method)
    path = None
    value = get_generic_origin(value)
    if hasattr(value, "__self__") and inspect.isclass(value.__self__) and inspect.ismethod(value):
        module_path = getattr(value.__self__, "__module__", None)
        qualname = f"{value.__self__.__name__}.{value.__name__}"
    else:
        module_path = getattr(value, "__module__", None)
        qualname = getattr(value, "__qualname__", "")

    if module_path is None:
        path = unresolvable_import_paths.get(value)
        if path:
            module_path, _ = path.rsplit(".", 1)
    elif (not qualname and not inspect.isclass(value)) or (
        inspect.ismethod(value) and not inspect.isclass(value.__self__)
    ):
        path = get_module_var_path(module_path, value)
    elif qualname:
        path = module_path + "." + qualname

    if not path:
        raise ValueError(f"Not possible to determine the import path for object {value}.")

    if qualname and module_path and ("." in qualname or "." in module_path):
        module_parts = module_path.split(".")
        for num in range(len(module_parts)):
            module_path = ".".join(module_parts[: num + 1])
            module = import_module(module_path)
            if "." in qualname:
                obj_name, attr = qualname.rsplit(".", 1)
                obj = getattr(module, obj_name, None)
                if getattr(module, attr, None) is value:
                    path = module_path + "." + attr
                    break
                elif getattr(obj, attr, None) == value:
                    path = module_path + "." + qualname
                    break
            elif getattr(module, qualname, None) is value:
                path = module_path + "." + qualname
                break
    return path


def object_path_serializer(value):
    try:
        path = get_import_path(value)
        reimported = import_object(path, check_path=False)
        if (get_partial_method(value) or value) is not (get_partial_method(reimported) or reimported):
            raise ValueError
        return path
    except Exception as ex:
        raise ValueError(f"Only possible to serialize an importable object, given {value}: {ex}") from ex


def get_typehint_origin(typehint):
    if not hasattr(typehint, "__origin__"):
        typehint_class = get_import_path(typehint.__class__)
        if typehint_class == "types.UnionType":
            return Union
        if typehint_class in {"typing._TypedDictMeta", "typing_extensions._TypedDictMeta"}:
            return dict
    return getattr(typehint, "__origin__", None)


def hash_item(item):
    try:
        if isinstance(item, (dict, list)):
            item_hash = hash(json_compact_dump(item))
        else:
            item_hash = hash(item)
    except Exception:
        item_hash = hash(repr(item))
    return item_hash


def unique(iterable):
    unique_items = []
    seen = set()
    for item in iterable:
        key = hash_item(item)
        if key not in seen:
            unique_items.append(item)
            seen.add(key)
    return unique_items


def iter_to_or_str(val) -> str:
    """Joins the given strings into an enumeration, e.g. "a, b or c"."""
    val = unique(val)
    if len(val) == 1:
        return str(val[0])
    return ", ".join(str(x) for x in val[:-1]) + f" or {val[-1]}"


def iter_to_set_str(val, sep=","):
    val = unique(val)
    if len(val) == 1:
        return str(val[0])
    return "{" + sep.join(str(x) for x in val) + "}"


def indent_text(text: str, first_line: bool = True) -> str:
    if first_line:
        return textwrap.indent(text, "  ")
    lines = text.splitlines()
    if len(lines) == 1:
        return text
    return lines[0] + os.linesep + textwrap.indent(os.linesep.join(lines[1:]), "  ")


def get_private_kwargs(data, **kwargs):
    extracted = [data.pop(name, default) for name, default in kwargs.items()]
    if data:
        raise ValueError(f"Unexpected keyword parameters: {set(data)}")
    return extracted[0] if len(extracted) == 1 else extracted


class ClassFromFunctionBase:
    wrapped_function: Callable


def get_argument_group_class(parser):
    import ast

    from ._core import ActionsContainer, ArgumentGroup

    if parser.__class__.add_argument != ActionsContainer.add_argument:
        try:
            add_argument = parser.__class__.add_argument
            source = inspect.getsource(add_argument)
            source = "class _ArgumentGroupAutoSubclass(ArgumentGroup):\n" + source
            class_ast = ast.parse(source)
            code = compile(class_ast, filename="<ast>", mode="exec")
            namespace = {**add_argument.__globals__, "ArgumentGroup": ArgumentGroup}
            exec(code, namespace)
            group_class = namespace["_ArgumentGroupAutoSubclass"]
            group_class.__module__ = parser.__class__.__module__
            add_argument.__globals__[group_class.__name__] = group_class
            return group_class
        except Exception as ex:
            parser.logger.debug(
                f"Failed to create ArgumentGroup subclass based on {parser.__class__.__name__}: {ex}", exc_info=ex
            )
    return ArgumentGroup
