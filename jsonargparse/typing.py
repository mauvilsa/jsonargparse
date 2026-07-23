"""Collection of types and type generators."""

import inspect
import operator
import os
import pathlib
import re
import sys
from collections.abc import Callable
from typing import Any, TypeAlias, get_type_hints

from ._common import ClassType, is_final_class, is_subclass, path_dump_preserve_relative
from ._namespace import Namespace
from ._optionals import final, is_alias_type, pydantic_support
from ._paths import Path, change_to_path_dir
from ._util import ClassFromFunctionBase, get_import_path, import_object

__all__ = [
    "final",
    "is_final_class",
    "register_type",
    "extend_base_type",
    "restricted_number_type",
    "restricted_string_type",
    "path_type",
    "class_from_function",
    "lazy_instance",
    "PositiveInt",
    "NonNegativeInt",
    "PositiveFloat",
    "NonNegativeFloat",
    "ClosedUnitInterval",
    "OpenUnitInterval",
    "SecretStr",
    "NotEmptyStr",
    "Email",
    "Path",
    "Path_fr",
    "Path_fc",
    "Path_dw",
    "Path_dc",
    "Path_drw",
]


_operators1 = {
    operator.gt: ">",
    operator.ge: ">=",
    operator.lt: "<",
    operator.le: "<=",
    operator.eq: "==",
    operator.ne: "!=",
}
_operators2 = {v: k for k, v in _operators1.items()}

if sys.version_info >= (3, 12):
    from typing import TypeAliasType as TypeAliasType

    _TypeClass = type | TypeAliasType
else:
    _TypeClass = type

registered_types: dict[tuple, _TypeClass] = {}
registered_type_handlers: dict[_TypeClass, "RegisteredType"] = {}
registration_pending: dict[str, Callable] = {}


def class_from_function(
    func: Callable[..., ClassType],
    func_return: type[ClassType] | None = None,
    name: str | None = None,
) -> type[ClassType]:
    """Creates a dynamic class which if instantiated is equivalent to calling func.

    Args:
        func: A function that returns an instance of a class.
        func_return: The return type of the function. Required if func does not have a return type annotation.
        name: The name of the class. Defaults to function name suffixed with ``_class``.
    """
    from functools import wraps

    if func_return is None:
        func_return = inspect.signature(func).return_annotation
    if func_return is inspect.Signature.empty:
        raise ValueError(f"{func} does not have a return type annotation")
    if isinstance(func_return, str):
        try:
            func_return = get_type_hints(func)["return"]
        except Exception as ex:
            func_return = inspect.signature(func).return_annotation
            raise ValueError(f"Unable to dereference {func_return}, the return type of {func}: {ex}") from ex

    if not name:
        name = func.__qualname__.replace(".", "__") + "_class"

    caller_module = inspect.getmodule(inspect.stack()[1][0]) or inspect.getmodule(class_from_function)
    assert caller_module
    if hasattr(caller_module, name):
        cls = getattr(caller_module, name)
        mro = inspect.getmro(cls) if inspect.isclass(cls) else ()
        if (
            len(mro) > 1
            and mro[1] is func_return
            and is_subclass(cls, ClassFromFunctionBase)
            and cls.wrapped_function is func
            and cls.__name__ == name
        ):
            return cls
        raise ValueError(f"{caller_module.__name__} already defines {name!r}, please use a different name")

    @wraps(func)
    def __new__(cls, *args, **kwargs):
        return func(*args, **kwargs)

    class ClassFromFunction(func_return, ClassFromFunctionBase):  # type: ignore[valid-type,misc]
        pass

    setattr(caller_module, name, ClassFromFunction)
    ClassFromFunction.wrapped_function = func
    ClassFromFunction.__new__ = __new__  # type: ignore[method-assign]
    ClassFromFunction.__doc__ = func.__doc__
    ClassFromFunction.__module__ = caller_module.__name__
    ClassFromFunction.__name__ = name
    ClassFromFunction.__qualname__ = name
    return ClassFromFunction


def _check_lazy_kwargs(class_type: type, lazy_kwargs: dict):
    if lazy_kwargs:
        from argparse import ArgumentError

        from ._core import ArgumentParser

        parser = ArgumentParser(exit_on_error=False)
        parser.add_class_arguments(class_type)
        try:
            parser.parse_object(lazy_kwargs)
        except ArgumentError as ex:
            raise ValueError(str(ex)) from ex


class _LazyInitBaseClass:
    def __init__(self, class_type: type, lazy_kwargs: dict):
        assert not issubclass(class_type, _LazyInitBaseClass)
        _check_lazy_kwargs(class_type, lazy_kwargs)
        self._lazy = type(self)
        self._lazy_class_type = class_type
        self._lazy_kwargs = lazy_kwargs
        self._lazy_methods = {}
        seen_methods: dict = {}
        for name, member in inspect.getmembers(class_type, predicate=inspect.isfunction):
            method = getattr(self, name)
            if not inspect.ismethod(method) or name == "__init__":
                continue
            assert name not in self.__dict__
            self._lazy_methods[name] = method
            if id(member) in seen_methods:
                self.__dict__[name] = seen_methods[id(member)]
            else:
                from functools import partial

                lazy_method = partial(self._lazy_init_then_call_method, name)
                if name == "__call__":
                    lazy_method = staticmethod(lazy_method)
                    self._lazy.__call__ = lazy_method  # type: ignore[method-assign]
                self.__dict__[name] = lazy_method
                seen_methods[id(member)] = lazy_method

    def _lazy_init(self):
        for name in self._lazy_methods:
            if name == "__call__":
                self._lazy.__call__ = self._lazy_methods[name]
            del self.__dict__[name]
        super().__init__(**self._lazy_kwargs)

    def _lazy_init_then_call_method(self, method_name, *args, **kwargs):
        self._lazy_init()
        return self._lazy_methods[method_name](*args, **kwargs)

    def lazy_get_init_args(self) -> Namespace:
        return Namespace(self._lazy_kwargs)

    def lazy_get_init_data(self):
        init_args = self.lazy_get_init_args()
        init = Namespace(class_path=get_import_path(self._lazy_class_type))
        if len(self._lazy_kwargs) > 0:
            init["init_args"] = init_args
        return init


def lazy_instance(class_type: type[ClassType], **kwargs) -> ClassType:
    """Instantiates a lazy instance of the given type.

    By lazy it is meant that the ``__init__`` is delayed until the first time that a
    method of the instance is called. It also provides a `lazy_get_init_data` method
    useful for serializing.

    Args:
        class_type: The class to instantiate.
        **kwargs: Any keyword arguments to use for instantiation.
    """
    caller_module = inspect.getmodule(inspect.stack()[1][0])
    class_name = f"LazyInstance_{class_type.__name__}"
    if hasattr(caller_module, class_name):
        lazy_init_class = getattr(caller_module, class_name)
        assert is_subclass(lazy_init_class, _LazyInitBaseClass) and is_subclass(lazy_init_class, class_type)
    else:
        lazy_init_class = type(
            class_name,
            (_LazyInitBaseClass, class_type),
            {"__doc__": f"Class for lazy instances of {class_type}"},
        )
        if caller_module is not None:
            lazy_init_class.__module__ = getattr(caller_module, "__name__", __name__)
            setattr(caller_module, lazy_init_class.__qualname__, lazy_init_class)
    return lazy_init_class(class_type, kwargs)


def extend_base_type(
    name: str,
    base_type: type,
    validation_fn: Callable,
    docstring: str | None = None,
    extra_attrs: dict | None = None,
    register_key: tuple | None = None,
) -> TypeAlias:
    """Creates and registers an extension of base type.

    Args:
        name: How the new type will be called.
        base_type: The type from which the created type is extended.
        validation_fn: Function that validates the value on instantiation/casting. Gets two arguments: ``class_type``
            and ``value``.
        docstring: The ``__doc__`` attribute value for the created type.
        extra_attrs: Attributes set to the type class that the ``validation_fn`` can access.
        register_key: Used to determine the uniqueness of registered types.

    Raises:
        ValueError: If the type has already been registered with a different name.
    """
    if register_key in registered_types:
        registered_type = registered_types[register_key]
        if registered_type.__name__ != name:
            raise ValueError(f"Same type already registered with a different name: {registered_type.__name__}.")
        return registered_type

    class TypeCore:
        _validation_fn = validation_fn
        _type = base_type

        def __new__(cls, v):
            cls._validation_fn(cls, v)
            return super().__new__(cls, cls._type(v))

    if extra_attrs is not None:
        for key, value in extra_attrs.items():
            setattr(TypeCore, key, value)

    created_type = type(name, (TypeCore, base_type), {"__doc__": docstring})
    add_type(created_type, register_key)

    return created_type


def restricted_number_type(
    name: str | None,
    base_type: type,
    restrictions: tuple | list[tuple],
    join: str = "and",
    docstring: str | None = None,
) -> TypeAlias:
    """Creates or returns an already registered restricted number type class.

    Args:
        name: Name for the type or ``None`` for an automatic name.
        base_type: One of ``{int, float}``.
        restrictions: Tuples of pairs (comparison, reference), e.g. ``('>', 0)``.
        join: How to combine multiple comparisons, one of ``{'or', 'and'}``.
        docstring: Docstring for the type class.

    Returns:
        The created or retrieved type class.
    """
    if base_type not in {int, float}:
        raise ValueError("Expected base_type to be one of {int, float}.")
    if join not in {"or", "and"}:
        raise ValueError("Expected join to be one of {'or', 'and'}.")

    restrictions = [restrictions] if isinstance(restrictions, tuple) else restrictions
    if (
        not isinstance(restrictions, list)
        or not all(isinstance(x, tuple) and len(x) == 2 for x in restrictions)
        or not all(x[0] in _operators2 and x[1] == base_type(x[1]) for x in restrictions)
    ):
        raise ValueError(
            "Expected restrictions to be a list of tuples each with a comparison operator "
            f"(> >= < <= == !=) and a reference value of type {base_type.__name__}."
        )

    register_key = (tuple(sorted(restrictions)), base_type, join)

    restrictions = [(_operators2[x[0]], x[1]) for x in restrictions]
    expression = (" " + join + " ").join(["v" + _operators1[op] + str(ref) for op, ref in restrictions])

    if name is None:
        name = base_type.__name__
        for num, (comparison, ref) in enumerate(restrictions):
            name += "_" + join + "_" if num > 0 else "_"
            name += comparison.__name__ + str(ref).replace(".", "")

    extra_attrs = {
        "_restrictions": restrictions,
        "_expression": expression,
        "_join": join,
        "_type": base_type,
    }

    def validation_fn(cls, v):
        if isinstance(v, bool):
            raise ValueError(f"{v} not a number")
        if cls._type == int and isinstance(v, float) and not float.is_integer(v):
            raise ValueError(f"{v} not an integer")
        vv = cls._type(v)
        check = [comparison(vv, ref) for comparison, ref in cls._restrictions]
        if (cls._join == "and" and not all(check)) or (cls._join == "or" and not any(check)):
            raise ValueError(f"{v} does not conform to restriction {cls._expression}")

    return extend_base_type(
        name=name,
        base_type=base_type,
        validation_fn=validation_fn,
        register_key=register_key,
        docstring=docstring,
        extra_attrs=extra_attrs,
    )


def restricted_string_type(
    name: str,
    regex: str | re.Pattern,
    docstring: str | None = None,
) -> TypeAlias:
    """Creates or returns an already registered restricted string type class.

    Args:
        name: Name for the type or ``None`` for an automatic name.
        regex: Regular expression that the string must match.
        docstring: Docstring for the type class.

    Returns:
        The created or retrieved type class.
    """
    if isinstance(regex, str):
        regex = re.compile(regex)
    expression = "matching " + regex.pattern

    extra_attrs = {
        "_regex": regex,
        "_expression": expression,
        "_type": str,
    }

    def validation_fn(cls, v):
        if not cls._regex.match(v):
            raise ValueError(f"{v} does not match regular expression {cls._regex.pattern}")

    return extend_base_type(
        name=name,
        base_type=str,
        validation_fn=validation_fn,
        register_key=(expression, str),
        docstring=docstring,
        extra_attrs=extra_attrs,
    )


def _is_path_type(value, class_type):
    return isinstance(value, Path)


def _serialize_path(path: Path):
    if not isinstance(path, Path):
        raise ValueError("Expected a Path instance.")
    if path_dump_preserve_relative.get() and path.relative != path.absolute:
        return {
            "relative": path._relative,
            "cwd": path._cwd,
        }
    return str(path)


def path_type(mode: str, docstring: str | None = None) -> TypeAlias:
    """Creates or returns an already registered path type class.

    Args:
        mode: The required type and access permissions among ``[fdrwxcuFDRWX]``.
        docstring: Docstring for the type class.

    Returns:
        The created or retrieved type class.
    """
    Path._check_mode(mode)
    name = "Path_" + mode
    key_name = "path " + "".join(sorted(mode))

    register_key = (key_name, str)
    if register_key in registered_types:
        return registered_types[register_key]

    class PathType(Path):
        _expression = name
        _mode = mode
        _type = _serialize_path

        def __init__(self, v, **k):
            if isinstance(v, dict) and set(v) == {"cwd", "relative"}:
                with change_to_path_dir(v["cwd"]):
                    super().__init__(v["relative"], mode=self._mode, **k)
            else:
                super().__init__(v, mode=self._mode, **k)

    restricted_type = type(name, (PathType,), {"__doc__": docstring})
    add_type(restricted_type, register_key, type_check=_is_path_type)

    return restricted_type


class RegisteredType:
    def __init__(
        self,
        class_type: _TypeClass,
        serializer: Callable,
        deserializer: Callable | None,
        deserializer_exceptions: type[Exception] | tuple[type[Exception], ...],
        type_check: Callable,
    ):
        self.class_type = class_type
        self.serializer = serializer
        self.base_deserializer = class_type if deserializer is None else deserializer
        self.deserializer_exceptions = deserializer_exceptions
        self.type_check = type_check

    def __eq__(self, other):
        return all(getattr(self, k) == getattr(other, k) for k in ["class_type", "serializer", "base_deserializer"])

    def is_value_of_type(self, value):
        return self.type_check(value, self.class_type)

    def deserializer(self, value):
        try:
            return self.base_deserializer(value)
        except self.deserializer_exceptions as ex:
            class_type_name = getattr(self.class_type, "__name__", str(self.class_type))
            ex2 = ValueError(f"Not of type {class_type_name}: {ex}")
            ex2.parent = ex
            raise ex2 from ex


def register_type(
    class_type: _TypeClass,
    serializer: Callable = str,
    deserializer: Callable | None = None,
    deserializer_exceptions: type[Exception] | tuple[type[Exception], ...] = (
        ValueError,
        TypeError,
        AttributeError,
    ),
    type_check: Callable = lambda v, t: v.__class__ == t,
    fail_already_registered: bool = True,
    uniqueness_key: tuple | None = None,
) -> None:
    """Registers a new type for use in jsonargparse parsers.

    Args:
        class_type: The class to be registered. Python 3.12+ also supports
            ``TypeAliasType`` aliases.
        serializer: Function that converts an instance of the class to a basic type.
        deserializer: Function that converts a basic type to an instance of the
            class. Default instantiates ``class_type``.
        deserializer_exceptions: Exceptions that deserializer raises when it fails.
        type_check: Function to check if a value is of ``class_type``. Gets as arguments the value and ``class_type``.
        fail_already_registered: Whether to fail if type has already been registered.
        uniqueness_key: Key to determine uniqueness of type.
    """
    if sys.version_info[:2] < (3, 12) and not inspect.isclass(class_type):
        raise ValueError(f"Expected class_type to be a class, got {type(class_type)}")
    elif sys.version_info[:2] >= (3, 12) and not (inspect.isclass(class_type) or is_alias_type(class_type)):
        raise ValueError(f"Expected class_type to be a class or a type alias, got {type(class_type)}")
    type_handler = RegisteredType(class_type, serializer, deserializer, deserializer_exceptions, type_check)
    fail_already_registered = globals().get("_fail_already_registered", fail_already_registered)
    if not uniqueness_key and fail_already_registered and get_registered_type(class_type):
        if type_handler == registered_type_handlers[class_type]:
            return
        raise ValueError(f'Type "{class_type}" already registered with different serializer and/or deserializer.')
    registered_type_handlers[class_type] = type_handler
    if uniqueness_key is not None:
        registered_types[uniqueness_key] = class_type


def register_type_on_first_use(import_path: str, *args, **kwargs):
    registration_pending[import_path] = lambda: register_type(
        import_object(import_path),
        *args,
        **kwargs,
    )


def get_registered_type(class_type) -> RegisteredType | None:
    if class_type not in registered_type_handlers:
        from contextlib import suppress

        with suppress(AttributeError, ValueError):
            import_path = get_import_path(class_type)
            if import_path in registration_pending:
                registration_pending.pop(import_path)()
    return registered_type_handlers.get(class_type)


def add_type(class_type: type, uniqueness_key: tuple | None, type_check: Callable | None = None):
    assert uniqueness_key not in registered_types
    if class_type.__name__ in globals():
        raise ValueError(f'Type name "{class_type.__name__}" clashes with name already defined in jsonargparse.typing.')
    globals()[class_type.__name__] = class_type
    kwargs: dict = {"uniqueness_key": uniqueness_key}
    if type_check is not None:
        kwargs["type_check"] = type_check
    register_type(class_type, class_type._type, **kwargs)  # type: ignore[attr-defined]


_fail_already_registered = False

PositiveInt = restricted_number_type("PositiveInt", int, (">", 0), docstring="int restricted to be >0")
NonNegativeInt = restricted_number_type("NonNegativeInt", int, (">=", 0), docstring="int restricted to be ≥0")
PositiveFloat = restricted_number_type("PositiveFloat", float, (">", 0), docstring="float restricted to be >0")
NonNegativeFloat = restricted_number_type("NonNegativeFloat", float, (">=", 0), docstring="float restricted to be ≥0")
ClosedUnitInterval = restricted_number_type(
    "ClosedUnitInterval", float, [(">=", 0), ("<=", 1)], docstring="float restricted to be ≥0 and ≤1"
)
OpenUnitInterval = restricted_number_type(
    "OpenUnitInterval", float, [(">", 0), ("<", 1)], docstring="float restricted to be >0 and <1"
)

NotEmptyStr = restricted_string_type(
    "NotEmptyStr", r"^.*[^ ].*$", docstring=r"str restricted to not-empty pattern ``^.*[^ ].*$``"
)
Email = restricted_string_type(
    "Email", r"^[^@ ]+@[^@ ]+\.[^@ ]+$", docstring=r"str restricted to the email pattern ``^[^@ ]+@[^@ ]+\.[^@ ]+$``"
)

Path_fr = path_type("fr", docstring="path to a file that exists and is readable")
Path_fc = path_type("fc", docstring="path to a file that can be created if it does not exist")
Path_dw = path_type("dw", docstring="path to a directory that exists and is writable")
Path_dc = path_type("dc", docstring="path to a directory that can be created if it does not exist")
Path_drw = path_type("drw", docstring="path to a directory that exists and is readable and writable")

register_type(os.PathLike, str, str)
register_type(complex)
register_type_on_first_use("decimal.Decimal", float)
register_type_on_first_use("uuid.UUID")

for _path in [pathlib.Path, pathlib.PosixPath, pathlib.WindowsPath]:
    register_type(_path, str, _path, type_check=isinstance)


def timedelta_deserializer(value):
    def raise_error():
        raise ValueError(f'Expected a string with form "h:m:s" or "d days, h:m:s" but got "{value}"')

    if not isinstance(value, str):
        raise_error()
    pattern = r"(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d[\.\d+]*)"
    if "day" in value:
        pattern = r"(?P<days>[-\d]+) day[s]*, " + pattern
    match = re.match(pattern, value)
    if not match:
        raise_error()
    kwargs = {key: float(val) for key, val in match.groupdict().items()}
    from datetime import timedelta

    return timedelta(**kwargs)


register_type_on_first_use("datetime.timedelta", deserializer=timedelta_deserializer)


def bytes_serializer(value: bytes | bytearray) -> str:
    from base64 import b64encode

    return b64encode(value).decode()


def bytes_deserializer(value: str) -> bytes:
    from base64 import b64decode

    return b64decode(value)


def bytearray_deserializer(value: str) -> bytearray:
    from base64 import b64decode

    return bytearray(b64decode(value))


register_type_on_first_use("builtins.bytes", serializer=bytes_serializer, deserializer=bytes_deserializer)
register_type_on_first_use("builtins.bytearray", serializer=bytes_serializer, deserializer=bytearray_deserializer)


def range_serializer(value):
    if value.step == 1:
        if value.start == 0:
            return f"range({value.stop})"
        return f"range({value.start}, {value.stop})"
    return f"range({value.start}, {value.stop}, {value.step})"


re_range_stop = re.compile(r"^(-?\d+)$")
re_range_start_stop = re.compile(r"^(-?\d+),(-?\d+)$")
re_range_start_stop_step = re.compile(r"^(-?\d+),(-?\d+),(-?\d+)$")


def range_deserializer(value):
    value = value.strip()
    if value.startswith("range(") and value.endswith(")"):
        value = value[6:-1].replace(" ", "")
        match = re_range_stop.match(value)
        if match:
            return range(int(match[1]))
        match = re_range_start_stop.match(value)
        if match:
            return range(int(match[1]), int(match[2]))
        match = re_range_start_stop_step.match(value)
        if match:
            return range(int(match[1]), int(match[2]), int(match[3]))
    raise ValueError("Expected 'range(<stop>)' or 'range(<start>, <stop>)' or 'range(<start>, <stop>, <step>)'")


register_type(range, serializer=range_serializer, deserializer=range_deserializer)


class SecretStr:
    """Holds a secret string that serializes to ``**********``."""

    def __init__(self, value: str):
        self._value = value

    def __str__(self) -> str:
        return "**********"

    def __len__(self) -> int:
        return len(self._value)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def get_secret_value(self) -> str:
        """Returns the actual secret value."""
        return self._value


register_type(SecretStr)
register_type_on_first_use("pydantic.SecretStr")


def pydantic_deserializer(class_type):
    from pydantic import create_model  # pylint: disable=no-name-in-module

    pydantic_model = create_model("pydantic_model", pydantic_field=(class_type, ...))

    def deserialize(value):
        return pydantic_model(pydantic_field=value).pydantic_field

    return deserialize


def pydantic_serializer(class_type):
    serializer = str
    for base in [int, float, bool, list, dict, (set, list)]:
        if not isinstance(base, tuple):
            base = (base, base)
        if issubclass(class_type, base[0]):
            serializer = base[1]
            break
    return serializer


pydantic_type_modules = {
    "pydantic_core._pydantic_core",
    "pydantic.types",
    "pydantic.networks",
    "pydantic_extra_types",
}


def is_pydantic_type(class_type):
    return (
        pydantic_support
        and inspect.isclass(class_type)
        and any(getattr(t, "__module__", "") in pydantic_type_modules for t in inspect.getmro(class_type))
    )


def register_pydantic_type(class_type):
    from ._optionals import is_annotated

    if is_annotated(class_type):
        class_type = class_type.__origin__
    if not is_pydantic_type(class_type):
        return
    if not get_registered_type(class_type):
        from pydantic import ValidationError

        register_type(
            class_type=class_type,
            serializer=pydantic_serializer(class_type),
            deserializer=pydantic_deserializer(class_type),
            deserializer_exceptions=(ValidationError, TypeError),
        )


del _fail_already_registered
