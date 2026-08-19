"""Code related to optional dependencies."""

import inspect
import os
import re
import sys
from contextlib import contextmanager
from copy import deepcopy
from importlib.metadata import version
from importlib.util import find_spec
from typing import Any, Union

pyyaml_available = bool(find_spec("yaml"))
toml_load_available = bool(find_spec("toml") or find_spec("tomllib"))
toml_dump_available = bool(find_spec("toml"))
typing_extensions_support = find_spec("typing_extensions") is not None
typeshed_client_support = find_spec("typeshed_client") is not None
jsonschema_support = find_spec("jsonschema") is not None
jsonnet_support = find_spec("_jsonnet") is not None
url_support = find_spec("requests") is not None
docstring_parser_support = find_spec("docstring_parser") is not None
fsspec_support = find_spec("fsspec") is not None
ruamel_support = bool(find_spec("ruamel") and find_spec("ruamel.yaml"))
omegaconf_support = find_spec("omegaconf") is not None
attrs_support = find_spec("attrs") is not None

_config_read_mode = "fr"
_docstring_parse_options = {
    "style": None,
    "attribute_docstrings": False,
}


def typing_extensions_import(name):
    if typing_extensions_support:
        return getattr(__import__("typing_extensions"), name, False)
    else:
        return getattr(__import__("typing"), name, False)


def capture_typing_extension_shadows(typehint, name: str, *collections) -> None:
    """
    Ensure different origins for types in typing_extensions are captured.
    """
    if (typehint is False or getattr(typehint, "__module__", None) == "typing_extensions") and hasattr(
        __import__("typing"), name
    ):
        for collection in collections:
            collection.add(getattr(__import__("typing"), name))


def final(cls):
    """Decorator to make a class ``final``, i.e., it shouldn't be subclassed.

    It is the same as ``typing.final`` or an equivalent implementation
    depending on the python version and whether typing-extensions is
    installed.
    """
    setattr(cls, "__final__", True)
    return cls


def is_compatible_final(final) -> bool:
    @final
    class FinalClass:
        pass

    return getattr(FinalClass, "__final__", False)  # __final__ available in stdlib from python 3.11


fallback_final = final
stdlib_final = typing_extensions_import("final")
if stdlib_final and is_compatible_final(stdlib_final) and "SPHINX_BUILD" not in os.environ:
    final = stdlib_final


def import_typeshed_client():
    if typeshed_client_support:
        import typeshed_client

        return typeshed_client
    else:
        return __import__("argparse").Namespace(ImportedInfo=object, ModulePath=object, Resolver=object)


class UndefinedException(Exception):
    pass


def get_jsonschema_exceptions():
    from jsonschema.exceptions import ValidationError

    return (ValidationError,)


@contextmanager
def missing_package_raise(package, importer):
    try:
        yield None
    except ImportError as ex:
        raise ImportError(f"{package} package is required by {importer} :: {ex}") from ex


def import_toml_loads(importer):
    if find_spec("tomllib"):
        import tomllib

        return tomllib.loads, tomllib.TOMLDecodeError
    else:
        with missing_package_raise("toml", importer):
            import toml

        return toml.loads, toml.TomlDecodeError


def import_toml_dumps(importer):
    with missing_package_raise("toml", importer):
        import toml
    return toml.dumps


def import_jsonschema(importer):
    with missing_package_raise("jsonschema", importer):
        import jsonschema
    return jsonschema, jsonschema.Draft7Validator


def import_jsonnet(importer):
    with missing_package_raise("jsonnet", importer):
        import _jsonnet
    return _jsonnet


def import_requests(importer):
    with missing_package_raise("requests", importer):
        import requests
    return requests


def import_docstring_parser(importer):
    with missing_package_raise("docstring-parser", importer):
        import docstring_parser
    return docstring_parser


def import_fsspec(importer):
    with missing_package_raise("fsspec", importer):
        import fsspec
    return fsspec


def import_ruamel(importer):
    with missing_package_raise("ruamel.yaml", importer):
        import ruamel.yaml
    return ruamel.yaml


def _set_config_read_mode(
    urls_enabled: bool = False,
    fsspec_enabled: bool = False,
):
    """Enables/disables optional config read modes.

    Args:
        urls_enabled: Whether to read config files from URLs using requests package.
        fsspec_enabled: Whether to read config files from fsspec supported file systems.
    """
    imports = {
        "u": import_requests,
        "s": import_fsspec,
    }

    def update_mode(flag, enabled):
        global _config_read_mode
        if enabled:
            imports[flag]("_set_config_read_mode")
            if flag not in _config_read_mode:
                _config_read_mode = _config_read_mode.replace("f", "f" + flag)
        else:
            _config_read_mode = _config_read_mode.replace(flag, "")

    update_mode("u", urls_enabled)
    update_mode("s", fsspec_enabled)


def _get_config_read_mode() -> str:
    """Returns the current config reading mode."""
    return _config_read_mode


def _set_docstring_parse_options(style=None, attribute_docstrings: bool | None = None):
    """Sets options for docstring parsing.

    Args:
        style (docstring_parser.DocstringStyle): The docstring style to expect.
        attribute_docstrings: Whether to parse attribute docstrings (slower).
    """
    global _docstring_parse_options
    dp = import_docstring_parser("_set_docstring_parse_options")
    if style is not None:
        if not isinstance(style, dp.DocstringStyle):
            raise ValueError(f"Expected style to be of type {dp.DocstringStyle}.")
        _docstring_parse_options["style"] = style
    if attribute_docstrings is not None:
        if not isinstance(attribute_docstrings, bool):
            raise ValueError("Expected attribute_docstrings to be boolean.")
        _docstring_parse_options["attribute_docstrings"] = attribute_docstrings


def get_docstring_parse_options():
    if _docstring_parse_options["style"] is None:
        dp = import_docstring_parser("get_docstring_parse_options")
        _docstring_parse_options["style"] = dp.DocstringStyle.AUTO
    return _docstring_parse_options


def parse_docstring(component, params=False, logger=None):
    dp = import_docstring_parser("parse_docstring")
    options = get_docstring_parse_options()
    try:
        if params and options["attribute_docstrings"]:
            return dp.parse_from_object(component, style=options["style"])
        else:
            return dp.parse(component.__doc__, style=options["style"])
    except (ValueError, dp.ParseError) as ex:
        if logger:
            logger.debug(f"Failed parsing docstring for {component}: {ex}")
    return None


# modules of base classes that only provide machinery, e.g. object, abc.ABC,
# typing.Generic, enum.Enum, pydantic.BaseModel, whose docstrings describe
# themselves instead of the parameters of the derived classes
docstring_skip_modules = {"abc", "attr", "attrs", "builtins", "enum", "pydantic", "typing", "typing_extensions"}


def is_docstring_base_source(cls) -> bool:
    """Whether a base class can have docstrings that document the parameters of its subclasses."""
    return cls.__module__.split(".", 1)[0] not in docstring_skip_modules


def get_mro_doc_sources(cls) -> list:
    """Docstring sources for a class, from the most base class to the class itself."""
    bases = [b for b in inspect.getmro(cls)[1:] if is_docstring_base_source(b)]
    return bases[::-1] + [cls]


def parse_docs(component, parent, logger):
    from ._common import get_generic_origin

    # a subscripted generic, e.g. Strategy[int], is documented by the class that it stands for
    component = get_generic_origin(component)
    parent = get_generic_origin(parent)
    docs = {}
    if docstring_parser_support:
        if inspect.isclass(parent) and component.__name__ == "__init__":
            # base classes first, so that descriptions in derived classes take precedence
            doc_sources = get_mro_doc_sources(parent)[:-1] + [component, parent]
        elif inspect.isclass(component):
            doc_sources = get_mro_doc_sources(component)
        else:
            doc_sources = [component]
        for src in doc_sources:
            doc = parse_docstring(src, params=True, logger=logger)
            if doc:
                for param in doc.params:
                    if param.description:
                        docs[param.arg_name] = param.description
    return docs


def get_doc_short_description(function_or_class, method_name=None, logger=None):
    from ._common import get_generic_origin

    function_or_class = get_generic_origin(function_or_class)  # e.g. Strategy[int] documented by Strategy
    if docstring_parser_support:
        if inspect.isclass(function_or_class) and not method_name:
            # nearest short description in the mro, since a derived class often inherits the constructor
            for cls in get_mro_doc_sources(function_or_class)[::-1]:
                docstring = parse_docstring(cls, params=False, logger=logger)
                if docstring and docstring.short_description:
                    return docstring.short_description
                init = cls.__dict__.get("__init__")
                if init is not None:
                    # the class defines its own constructor, so base classes don't describe it
                    docstring = parse_docstring(init, params=False, logger=logger)
                    return docstring.short_description if docstring else None
            return None
        component = function_or_class
        if inspect.isclass(function_or_class):
            component = getattr(function_or_class, method_name)
        docstring = parse_docstring(component, params=False, logger=logger)
        if docstring:
            return docstring.short_description
    return None


def get_omegaconf_loader(mode):
    """Returns a yaml loader function based on OmegaConf which supports variable interpolation."""
    import io

    from ._loaders_dumpers import yaml_load

    with missing_package_raise("omegaconf", "get_omegaconf_loader"):
        from omegaconf import OmegaConf

    assert mode in {"omegaconf", "omegaconf+"}

    if mode == "omegaconf+":
        from ._common import get_parsing_setting

        def omegaconf_plus_load(value):
            value = yaml_load(value)
            if isinstance(value, dict) and get_parsing_setting("omegaconf_absolute_to_relative_paths"):
                value = omegaconf_absolute_to_relative_paths(value)
            return value

        return omegaconf_plus_load

    def omegaconf_load(value):
        value_pyyaml = yaml_load(value)
        if isinstance(value_pyyaml, (str, int, float, bool)) or value_pyyaml is None:
            return value_pyyaml
        value_omegaconf = OmegaConf.to_object(OmegaConf.load(io.StringIO(value)))
        str_ref = dict.fromkeys([value], None)
        return value_pyyaml if value_omegaconf == str_ref else value_omegaconf

    return omegaconf_load


def omegaconf_apply(parser, cfg):
    if "${" not in str(cfg):
        return cfg

    with missing_package_raise("omegaconf", "omegaconf_apply"):
        from omegaconf import OmegaConf

    from ._common import parser_context

    with parser_context(path_dump_preserve_relative=True):
        cfg_dict = parser.dump(cfg, skip_validation=True, skip_unset=False, skip_link_targets=False)
    cfg_omegaconf = OmegaConf.create(cfg_dict)
    cfg_dict = OmegaConf.to_container(cfg_omegaconf, resolve=True)
    return parser._apply_actions(cfg_dict)


def omegaconf_tokenize(path: str) -> list[str]:
    """Very small tokenizer: 'a.b[0].c' -> ['a','b','0','c']."""
    return [t for t in path.replace("]", "").replace("[", ".").split(".") if t]


def omegaconf_tokens_to_path(tokens: list[str]) -> str:
    """Render tokens back to a normalized path: ['a','0','b'] -> 'a[0].b'."""
    s = ""
    for t in tokens:
        if t.isdigit():
            s += f"[{t}]"
        else:
            s += ("" if s == "" else ".") + t
    return s


def omegaconf_absolute_to_relative_paths(data: dict) -> dict:
    """
    Return a new nested dict/list where absolute ${...} interpolations
    are rewritten to relative form from the node where they appear.
    """
    data = deepcopy(data)

    regex_absolute_path = re.compile(r"\$\{([a-zA-Z][a-zA-Z0-9[\]_.]*)\}")

    def _walk(node, current_path: list[str | int]):
        if isinstance(node, dict):
            return {k: _walk(v, current_path + [k]) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v, current_path + [i]) for i, v in enumerate(node)]

        if isinstance(node, str):

            def _replace(m: re.Match) -> str:
                dst_tokens = omegaconf_tokenize(m.group(1))
                # compute common prefix length
                i = 0
                while i < len(current_path) and i < len(dst_tokens) and str(current_path[i]) == dst_tokens[i]:
                    i += 1
                up = max(1, len(current_path) - i)
                dots = "." * up
                down = omegaconf_tokens_to_path(dst_tokens[i:])
                return "${" + dots + down + "}"

            return regex_absolute_path.sub(_replace, node)

        return node

    return _walk(data, [])


annotated_alias = typing_extensions_import("_AnnotatedAlias")


def is_annotated(typehint: type) -> bool:
    return annotated_alias and isinstance(typehint, annotated_alias)


def get_annotated_base_type(typehint: type) -> type:
    return typehint.__origin__  # type: ignore[attr-defined]


type_alias_type = typing_extensions_import("TypeAliasType")
if sys.version_info >= (3, 12):
    from typing import TypeAliasType as typing_type_alias_type
else:
    typing_type_alias_type = None


def is_alias_type(typehint: Any) -> bool:
    return (type_alias_type and isinstance(typehint, type_alias_type)) or (
        typing_type_alias_type and isinstance(typehint, typing_type_alias_type)  # type: ignore[truthy-function]
    )


def get_alias_target(typehint: type) -> bool:
    return typehint.__value__  # type: ignore[attr-defined]


def get_pydantic_support() -> int:
    support = "0"
    if find_spec("pydantic"):
        support = version("pydantic")
    return int(support.split(".", 1)[0])


pydantic_support = get_pydantic_support()


def get_pydantic_supports_field_init() -> bool:
    if find_spec("pydantic"):
        support = version("pydantic")
        major, minor = tuple(int(x) for x in support.split(".")[:2])
        return major > 2 or (major == 2 and minor >= 6)
    return False


pydantic_supports_field_init = get_pydantic_supports_field_init()


def is_pydantic_model(class_type) -> int:
    if pydantic_support:
        classes = inspect.getmro(class_type) if pydantic_support and inspect.isclass(class_type) else []
        for cls in classes:
            if getattr(cls, "__module__", "").startswith("pydantic") and getattr(cls, "__name__", "") == "BaseModel":
                import pydantic

                if issubclass(cls, pydantic.BaseModel):
                    return pydantic_support
                elif pydantic_support > 1 and issubclass(cls, pydantic.v1.BaseModel):
                    return 1
    return 0


def is_attrs_class(class_type) -> bool:
    if attrs_support:
        import attrs

        if attrs.has(class_type):
            return True
    return False


def get_module(value):
    return getattr(type(value), "__module__", "").split(".", 1)[0]


def is_annotated_validator(typehint: type) -> bool:
    from ._util import get_typehint_origin

    return (
        pydantic_support > 1
        and is_annotated(typehint)
        and any(get_module(m) in {"pydantic", "annotated_types"} for m in typehint.__metadata__)  # type: ignore[attr-defined]
        and get_typehint_origin(typehint.__origin__) != Union  # type: ignore[attr-defined]
    )


def validate_annotated(value, typehint: type):
    from pydantic import TypeAdapter

    return TypeAdapter(typehint).validate_python(value)


def get_pydantic_path_type(typehint) -> Union[str, None]:
    """Returns the path type of pydantic's ``FilePath`` ("file"), ``DirectoryPath`` ("dir") and
    ``NewPath`` ("new") types, or None if the typehint is not one of them."""
    if is_annotated_validator(typehint):
        for metadata in typehint.__metadata__:
            metadata_class = type(metadata)
            if metadata_class.__module__ == "pydantic.types" and metadata_class.__name__ == "PathType":
                return metadata.path_type
    return None
