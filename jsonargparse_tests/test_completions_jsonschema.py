from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import uuid
from abc import ABC, abstractmethod
from calendar import Calendar
from enum import Enum
from importlib.util import find_spec
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple, Type, TypedDict, TypeVar, Union
from unittest.mock import patch

import pytest

from jsonargparse import SUPPRESS, ActionParser, ActionYesNo, ArgumentParser, lazy_instance, set_parsing_settings
from jsonargparse._typehints import NotRequired
from jsonargparse.typing import (
    ClosedUnitInterval,
    Email,
    Path_fr,
    PositiveInt,
    register_type,
    restricted_number_type,
)
from jsonargparse_tests.conftest import (
    capture_logs,
    get_parse_args_stdout,
    skip_if_docstring_parser_unavailable,
    skip_if_jsonschema_unavailable,
)

schema_uri = "https://json-schema.org/draft/2020-12/schema"


def get_schema(parser) -> dict:
    return json.loads(parser.get_completion_script("jsonschema"))


def validate(schema: dict, instance) -> None:
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(instance)


def iter_errors(schema: dict, instance) -> list:
    from jsonschema import Draft202012Validator

    return list(Draft202012Validator(schema).iter_errors(instance))


# print_completion argument


def test_print_completion_choices_without_shtab(parser, parsing_settings_patch):
    parser.add_argument("--val", type=int)
    set_parsing_settings(add_print_completion_argument=True)

    def find_spec_patch(module):
        return None if module == "shtab" else find_spec(module)

    with patch("jsonargparse._completions.find_spec", side_effect=find_spec_patch):
        help_str = get_parse_args_stdout(parser, ["--help"])
    assert "--print_completion" in help_str
    assert "jsonschema" in help_str
    assert "shtab-" not in help_str


def test_print_completion_jsonschema(parser, parsing_settings_patch):
    parser.add_argument("--num", type=int, required=True)
    set_parsing_settings(add_print_completion_argument=True)
    schema = json.loads(get_parse_args_stdout(parser, ["--print_completion=jsonschema"]))
    assert schema["properties"]["num"] == {"type": "integer"}


def test_get_completion_script_jsonschema_keeps_parser_usable(parser):
    parser.add_argument("--num", type=int)
    get_schema(parser)
    assert parser.parse_args(["--num=1"]).num == 1
    assert get_schema(parser)["properties"]["num"] == {"type": "integer"}


def test_get_completion_script_unsupported_type(parser):
    with pytest.raises(ValueError, match="Unsupported completion_type"):
        parser.get_completion_script("unsupported")


# basics


def test_schema_root(parser):
    parser.add_argument("--num", type=int, required=True)
    parser.add_argument("--opt", type=str, default="x")
    schema = get_schema(parser)
    assert schema["$schema"] == schema_uri
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["num"]
    assert schema["properties"]["opt"] == {"type": "string", "default": "x"}


def test_schema_key_in_root(parser):
    parser.add_argument("--num", type=int)
    properties = get_schema(parser)["properties"]
    assert list(properties) == ["$schema", "num"]
    assert properties["$schema"]["type"] == "string"
    assert properties["$schema"]["format"] == "uri-reference"
    assert "editors" in properties["$schema"]["description"]


def test_schema_key_only_in_root(parser):
    parser.add_argument("--group.num", type=int)
    schema = get_schema(parser)
    assert list(schema["properties"]["group"]["properties"]) == ["num"]


@skip_if_jsonschema_unavailable
def test_schema_key_validation(parser):
    parser.add_argument("--num", type=int)
    schema = get_schema(parser)
    validate(schema, {"$schema": "./schema.json", "num": 1})
    assert iter_errors(schema, {"$schema": 1})


def test_schema_key_ignored_when_parsing(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--num", type=int)
    cfg = parser.parse_args(['--cfg={"$schema": "./schema.json", "num": 1}'])
    assert cfg.num == 1
    assert "$schema" not in cfg


def test_required_argument_has_no_default(parser):
    parser.add_argument("--num", type=int, required=True)
    assert get_schema(parser)["properties"]["num"] == {"type": "integer"}


def test_non_parsing_actions_not_in_schema(parser, parsing_settings_patch):
    set_parsing_settings(add_print_completion_argument=True)
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--num", type=int)
    properties = get_schema(parser)["properties"]
    assert list(properties) == ["$schema", "num"]


def test_nested_key_groups(parser):
    parser.add_argument("--group.opt", type=str, default="x")
    parser.add_argument("--group.req", type=int, required=True)
    schema = get_schema(parser)
    group = schema["properties"]["group"]
    assert group["type"] == "object"
    assert group["additionalProperties"] is False
    assert group["properties"]["opt"] == {"type": "string", "default": "x"}
    assert group["required"] == ["req"]
    assert schema["required"] == ["group"]


def test_positional_argument(parser):
    parser.add_argument("pos", type=int)
    assert get_schema(parser)["properties"]["pos"] == {"type": "integer"}


def test_action_parser(parser, subparser):
    subparser.add_argument("--sub", type=int, default=1)
    parser.add_argument("--nest", action=ActionParser(parser=subparser))
    properties = get_schema(parser)["properties"]
    assert properties["nest"]["properties"]["sub"] == {"type": "integer", "default": 1}


# descriptions


class DocumentedClass:
    """Short description of the class.

    Args:
        num: Description of num.
        name: Description of name.
    """

    def __init__(self, num: int = 1, name: str = "x"):
        pass  # pragma: no cover


@skip_if_docstring_parser_unavailable
def test_description_from_docstrings(parser):
    parser.add_class_arguments(DocumentedClass, "cls")
    schema = get_schema(parser)
    group = schema["properties"]["cls"]
    assert group["description"] == "Short description of the class"
    assert group["properties"]["num"]["description"] == "Description of num."
    assert group["properties"]["name"]["description"] == "Description of name."


def test_description_from_help(parser):
    parser.add_argument("--num", type=int, help="Description of num.")
    assert get_schema(parser)["properties"]["num"]["description"] == "Description of num."


def test_description_suppressed_help(parser):
    parser.add_argument("--num", type=int, help="==SUPPRESS==")
    assert get_schema(parser)["properties"]["num"] == {"type": "integer"}


def test_description_percent_formatting(parser):
    parser.add_argument("--num", type=int, default=2, help="Number, default %(default)s.")
    assert get_schema(parser)["properties"]["num"]["description"] == "Number, default 2."


def test_parser_description(parser):
    parser.description = "The tool description."
    parser.add_argument("--num", type=int)
    assert get_schema(parser)["description"] == "The tool description."


# simple types


def test_basic_types(parser):
    parser.add_argument("--bool", type=bool)
    parser.add_argument("--int", type=int)
    parser.add_argument("--float", type=float)
    parser.add_argument("--str", type=str)
    parser.add_argument("--any", type=Any)
    properties = get_schema(parser)["properties"]
    assert properties["bool"] == {"type": "boolean"}
    assert properties["int"] == {"type": "integer"}
    assert properties["float"] == {"type": "number"}
    assert properties["str"] == {"type": "string"}
    assert properties["any"] == {}


def test_container_types(parser):
    parser.add_argument("--dict", type=dict)
    parser.add_argument("--dict_str", type=Dict[str, int])
    parser.add_argument("--dict_any", type=Dict[str, Any])
    parser.add_argument("--list", type=List[Union[float, bool]])
    parser.add_argument("--tuple", type=Tuple[int, str])
    parser.add_argument("--tuple_ellipsis", type=Tuple[int, ...])
    parser.add_argument("--set", type=set)
    properties = get_schema(parser)["properties"]
    assert properties["dict"] == {"type": "object"}
    assert properties["dict_str"] == {"type": "object", "additionalProperties": {"type": "integer"}}
    assert properties["dict_any"] == {"type": "object"}
    assert properties["list"] == {"type": "array", "items": {"type": ["number", "boolean"]}}
    assert properties["tuple"] == {
        "type": "array",
        "prefixItems": [{"type": "integer"}, {"type": "string"}],
        "items": False,
        "minItems": 2,
    }
    assert properties["tuple_ellipsis"] == {"type": "array", "items": {"type": "integer"}}
    assert properties["set"] == {"type": "array", "uniqueItems": True}


def test_union_simple_types_merged(parser):
    parser.add_argument("--val", type=Union[int, str, None])
    assert get_schema(parser)["properties"]["val"] == {"type": ["integer", "string", "null"]}


def test_union_with_any_keeps_informative_subschemas(parser):
    # the Any member accepts anything, but the others are kept so that editors can complete them
    parser.add_argument("--val", type=Union[str, Any])
    parser.add_argument("--nums", type=Union[int, float, Any])
    properties = get_schema(parser)["properties"]
    assert properties["val"] == {"anyOf": [{"type": "string"}, {}]}
    assert properties["nums"] == {"anyOf": [{"type": ["integer", "number"]}, {}]}


@skip_if_jsonschema_unavailable
def test_union_with_any_validates_anything(parser):
    parser.add_argument("--val", type=Union[str, Any])
    schema = get_schema(parser)
    for value in ["x", 1, None, {"a": 1}, [1, 2]]:
        validate(schema, {"val": value})


def test_literal_type(parser):
    parser.add_argument("--val", type=Literal["a", "b", 1, None])
    assert get_schema(parser)["properties"]["val"] == {"enum": ["a", "b", 1, None]}


class Fruit(Enum):
    apple = 1
    banana = 2


def test_enum_type(parser):
    parser.add_argument("--val", type=Fruit, default=Fruit.banana)
    assert get_schema(parser)["properties"]["val"] == {"enum": ["apple", "banana"], "default": "banana"}


def test_choices(parser):
    parser.add_argument("--val", choices=["a", "b"], default="a")
    assert get_schema(parser)["properties"]["val"] == {"enum": ["a", "b"], "default": "a"}


def test_uuid_type(parser):
    parser.add_argument("--uid", type=uuid.UUID)
    schema = get_schema(parser)["properties"]["uid"]
    assert schema["type"] == "string"
    assert schema["format"] == "uuid"
    assert re.match(schema["pattern"], str(uuid.uuid4()))


def test_path_type(parser):
    parser.add_argument("--path", type=Path_fr)
    assert get_schema(parser)["properties"]["path"] == {"type": "string"}


def test_registered_type_serialized_as_basic_type(parser):
    parser.add_argument("--data", type=bytes)
    assert get_schema(parser)["properties"]["data"] == {"type": "string"}


def test_restricted_number_types(parser):
    bounded_int = restricted_number_type("BoundedInt", int, [("<=", 10), (">", 2)])
    const_int = restricted_number_type("ConstInt", int, ("==", 5))
    non_zero_int = restricted_number_type("NonZeroInt", int, ("!=", 0))
    outside_int = restricted_number_type("OutsideInt", int, [("<", 0), (">", 10)], join="or")
    parser.add_argument("--positive_int", type=PositiveInt)
    parser.add_argument("--unit_interval", type=ClosedUnitInterval)
    parser.add_argument("--bounded_int", type=bounded_int)
    parser.add_argument("--const_int", type=const_int)
    parser.add_argument("--non_zero_int", type=non_zero_int)
    parser.add_argument("--outside_int", type=outside_int)
    properties = get_schema(parser)["properties"]
    assert properties["positive_int"] == {"type": "integer", "exclusiveMinimum": 0}
    assert properties["unit_interval"] == {"type": "number", "minimum": 0.0, "maximum": 1.0}
    assert properties["bounded_int"] == {"type": "integer", "maximum": 10, "exclusiveMinimum": 2}
    assert properties["const_int"] == {"type": "integer", "const": 5}
    # restrictions without a json schema equivalent are not described
    assert properties["non_zero_int"] == {"type": "integer"}
    assert properties["outside_int"] == {"type": "integer"}


def test_restricted_string_type(parser):
    parser.add_argument("--email", type=Email)
    assert get_schema(parser)["properties"]["email"] == {
        "type": "string",
        "pattern": "^[^@ ]+@[^@ ]+\\.[^@ ]+$",
    }


def test_nargs_list(parser):
    parser.add_argument("--nums", type=int, nargs="+", default=[1])
    assert get_schema(parser)["properties"]["nums"] == {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 1,
        "default": [1],
    }


def test_nargs_fixed(parser):
    parser.add_argument("--nums", type=int, nargs=2)
    assert get_schema(parser)["properties"]["nums"] == {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 2,
        "maxItems": 2,
    }


# dataclasses


@dataclasses.dataclass
class Data:
    """A dataclass.

    Args:
        num: Description of num.
    """

    num: int = 1
    name: str = "x"


@skip_if_docstring_parser_unavailable
def test_dataclass_as_type(parser):
    parser.add_argument("--data", type=Optional[Data])
    schema = get_schema(parser)
    assert schema["properties"]["data"] == {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/Data"}]}
    assert schema["$defs"]["Data"] == {
        "type": "object",
        "additionalProperties": False,
        "description": "A dataclass.",
        "properties": {
            "num": {"type": "integer", "description": "Description of num.", "default": 1},
            "name": {"type": "string", "default": "x"},
        },
    }


def test_dataclass_added_as_group(parser):
    parser.add_class_arguments(Data, "data")
    schema = get_schema(parser)
    assert schema["properties"]["data"]["properties"]["num"]["default"] == 1
    assert "$defs" not in schema


@dataclasses.dataclass
class NestedData:
    data: Data
    items: List[Data] = dataclasses.field(default_factory=list)


def test_dataclass_nested_expanded_and_defs_reused(parser):
    parser.add_argument("--nested", type=NestedData)
    schema = get_schema(parser)
    nested = schema["properties"]["nested"]
    assert nested["properties"]["data"]["properties"]["num"]["default"] == 1
    assert nested["properties"]["items"] == {"type": "array", "items": {"$ref": "#/$defs/Data"}, "default": []}
    assert list(schema["$defs"]) == ["Data"]


# subclass types


class Base:
    """Base description.

    Args:
        base: Description of base.
    """

    def __init__(self, base: str = "base"):
        pass  # pragma: no cover


class Sub(Base):
    """Sub description."""

    def __init__(self, sub: int = 1):
        pass  # pragma: no cover


class OtherSub(Base):
    def __init__(self, flag: bool = False):
        pass  # pragma: no cover


class RequiredSub(Base):
    def __init__(self, req: int):
        pass  # pragma: no cover


base_paths = [f"{__name__}.{n}" for n in ["Base", "Sub", "OtherSub", "RequiredSub"]]


def class_path_entries(definition: dict) -> dict:
    """The subschemas of a subclass definition that describe one specific class path."""
    entries = {}
    for entry in definition.get("anyOf", [definition]):
        class_path = entry.get("properties", {}).get("class_path", {})
        if "const" in class_path:
            entries[class_path["const"]] = entry
    return entries


def test_subclass_type(parser):
    parser.add_argument("--cls", type=Base)
    schema = get_schema(parser)
    assert schema["properties"]["cls"] == {"$ref": "#/$defs/Base"}
    entries = class_path_entries(schema["$defs"]["Base"])
    assert list(entries) == base_paths
    for entry in entries.values():
        assert entry["type"] == "object"
        assert entry["additionalProperties"] is False
        assert entry["properties"]["dict_kwargs"] == {"type": "object"}
    init_args = {path: entry["properties"]["init_args"] for path, entry in entries.items()}
    assert set(init_args[base_paths[0]]["properties"]) == {"base"}
    assert set(init_args[base_paths[1]]["properties"]) == {"sub"}
    assert set(init_args[base_paths[2]]["properties"]) == {"flag"}


def test_subclass_init_args_required_only_when_a_parameter_is_required(parser):
    parser.add_argument("--cls", type=Base)
    entries = class_path_entries(get_schema(parser)["$defs"]["Base"])
    assert entries[f"{__name__}.Base"]["required"] == ["class_path"]
    assert entries[f"{__name__}.Sub"]["required"] == ["class_path"]
    assert entries[f"{__name__}.RequiredSub"]["required"] == ["class_path", "init_args"]
    assert entries[f"{__name__}.RequiredSub"]["properties"]["init_args"]["required"] == ["req"]


def test_subclass_unknown_class_path_entry(parser):
    parser.add_argument("--cls", type=Base)
    definition = get_schema(parser)["$defs"]["Base"]
    assert {"type": "string"} in definition["anyOf"]
    unknown = [e for e in definition["anyOf"] if e.get("properties", {}).get("class_path", {}).get("not")]
    assert len(unknown) == 1
    assert unknown[0]["properties"] == {
        "class_path": {"type": "string", "not": {"enum": base_paths}},
        "init_args": {"type": "object"},
        "dict_kwargs": {"type": "object"},
    }
    assert unknown[0]["required"] == ["class_path"]


@skip_if_docstring_parser_unavailable
def test_subclass_descriptions(parser):
    parser.add_argument("--cls", type=Base)
    entries = class_path_entries(get_schema(parser)["$defs"]["Base"])
    assert entries[f"{__name__}.Base"]["description"] == "Base description."
    assert entries[f"{__name__}.Sub"]["description"] == "Sub description."
    assert "description" not in entries[f"{__name__}.OtherSub"]
    assert entries[f"{__name__}.Base"]["properties"]["init_args"]["properties"]["base"] == {
        "type": "string",
        "description": "Description of base.",
        "default": "base",
    }


@skip_if_jsonschema_unavailable
def test_subclass_type_validation(parser):
    parser.add_argument("--cls", type=Base)
    schema = get_schema(parser)
    # all forms that the parser accepts
    validate(schema, {"cls": {"class_path": f"{__name__}.Sub", "init_args": {"sub": 2}}})
    validate(schema, {"cls": {"class_path": f"{__name__}.Sub"}})
    validate(schema, {"cls": {"class_path": f"{__name__}.Sub", "dict_kwargs": {"extra": 1}}})
    validate(schema, {"cls": f"{__name__}.Sub"})
    validate(schema, {"cls": "Sub"})
    validate(schema, {"cls": {"class_path": "not_imported.Class", "init_args": {"anything": 1}}})
    # what the parser rejects
    assert iter_errors(schema, {"cls": {"class_path": f"{__name__}.Sub", "init_args": {"flag": True}}})
    assert iter_errors(schema, {"cls": {"class_path": f"{__name__}.RequiredSub"}})
    assert iter_errors(schema, {"cls": {"class_path": f"{__name__}.Sub", "bogus": 1}})
    assert iter_errors(schema, {"cls": {"init_args": {"sub": 2}}})


def test_defs_discarded_when_unreachable(parser):
    # the nested key turns the --cls schema into an object, so the Base def must not be kept
    parser.add_argument("--cls", type=Optional[Base])
    parser.add_argument("--cls.num", type=int)
    schema = get_schema(parser)
    assert schema["properties"]["cls"]["properties"] == {"num": {"type": "integer"}}
    assert "$defs" not in schema


def test_subclass_defs_reused(parser):
    parser.add_argument("--cls1", type=Base)
    parser.add_argument("--cls2", type=Optional[Base])
    schema = get_schema(parser)
    assert schema["properties"]["cls1"]["$ref"] == "#/$defs/Base"
    assert schema["properties"]["cls2"]["anyOf"][1]["$ref"] == "#/$defs/Base"
    assert list(schema["$defs"]) == ["Base"]


class Recursive:
    def __init__(self, child: Optional["Recursive"] = None):
        pass  # pragma: no cover


def test_subclass_recursive_type(parser):
    parser.add_argument("--rec", type=Recursive)
    schema = get_schema(parser)
    entry = class_path_entries(schema["$defs"]["Recursive"])[f"{__name__}.Recursive"]
    child = entry["properties"]["init_args"]["properties"]["child"]
    assert child == {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/Recursive"}]}


def test_subclass_in_list(parser):
    parser.add_argument("--items", type=List[Base])
    schema = get_schema(parser)
    assert schema["properties"]["items"] == {"type": "array", "items": {"$ref": "#/$defs/Base"}}


def test_callable_returning_subclass(parser):
    parser.add_argument("--fn", type=Callable[[int], Base])
    schema = get_schema(parser)
    assert schema["properties"]["fn"] == {"anyOf": [{"type": "string"}, {"$ref": "#/$defs/Base"}]}


def test_callable_without_return_type(parser):
    parser.add_argument("--fn", type=Callable)
    assert get_schema(parser)["properties"]["fn"] == {"type": "string"}


def test_type_from_another_package(parser):
    parser.add_argument("--cal", type=Calendar)
    schema = get_schema(parser)
    class_paths = set(class_path_entries(schema["$defs"]["Calendar"]))
    assert {"calendar.Calendar", "calendar.TextCalendar", "calendar.HTMLCalendar"} <= class_paths


# subcommands


def test_subcommands(parser, subparser, subsubparser):
    subparser.description = "The first command."
    subparser.add_argument("--num", type=int, required=True)
    subsubparser.add_argument("--opt", type=int, default=1)
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("cmd1", subparser)
    subcommands.add_subcommand("cmd2", subsubparser)
    schema = get_schema(parser)
    assert schema["properties"]["subcommand"]["enum"] == ["cmd1", "cmd2"]
    assert "can be omitted" in schema["properties"]["subcommand"]["description"]
    assert schema["properties"]["cmd1"]["description"] == "The first command."
    assert schema["properties"]["cmd1"]["properties"]["num"] == {"type": "integer"}
    assert schema["properties"]["cmd1"]["required"] == ["num"]
    # the subcommand key is optional, so nothing is required in the root
    assert "required" not in schema
    # only cmd1 has required keys, so only for it giving the subcommand key implies giving a block
    assert schema["allOf"] == [
        {
            "if": {"properties": {"subcommand": {"const": "cmd1"}}, "required": ["subcommand"]},
            "then": {"required": ["cmd1"]},
        }
    ]


@skip_if_jsonschema_unavailable
def test_subcommands_validation(parser, subparser, subsubparser):
    subparser.add_argument("--num", type=int, required=True)
    subsubparser.add_argument("--opt", type=int, default=1)
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("cmd1", subparser)
    subcommands.add_subcommand("cmd2", subsubparser)
    schema = get_schema(parser)
    validate(schema, {"subcommand": "cmd1", "cmd1": {"num": 1}})
    validate(schema, {"subcommand": "cmd2"})
    # the subcommand key can be omitted, be it a single block or several of them
    validate(schema, {"cmd1": {"num": 1}})
    validate(schema, {"cmd1": {"num": 1}, "cmd2": {"opt": 2}})
    validate(schema, {})
    assert iter_errors(schema, {"subcommand": "cmd1"})
    assert iter_errors(schema, {"subcommand": "cmd3"})
    assert iter_errors(schema, {"subcommand": "cmd1", "cmd1": {}})
    assert iter_errors(schema, {"cmd1": {"bogus": 1}})


# ActionJsonSchema


@skip_if_jsonschema_unavailable
def test_action_jsonschema_argument(parser):
    from jsonargparse import ActionJsonSchema

    item_schema = {"type": "array", "items": {"type": "integer"}}
    parser.add_argument("--op", action=ActionJsonSchema(schema=item_schema))
    assert get_schema(parser)["properties"]["op"] == item_schema


# defaults


def test_defaults_json_representation(parser):
    parser.add_argument("--dict", type=Dict[str, Fruit], default={"a": Fruit.apple})
    parser.add_argument("--set", type=Set[int], default={2, 1})
    parser.add_argument("--tuple", type=Tuple[int, str], default=(1, "x"))
    parser.add_argument("--cls", type=Base, default=lazy_instance(Sub, sub=3))
    parser.add_argument("--any", type=Any, default=Calendar())
    properties = get_schema(parser)["properties"]
    assert properties["dict"]["default"] == {"a": "apple"}
    assert properties["set"]["default"] == [1, 2]
    assert properties["tuple"]["default"] == [1, "x"]
    assert properties["cls"]["default"] == {"class_path": f"{__name__}.Sub", "init_args": {"sub": 3}}
    assert properties["any"]["default"].startswith("<calendar.Calendar")


def test_default_given_as_dict_subclass_spec(parser):
    # add_subclass_arguments normalizes such a default into a Namespace
    parser.add_subclass_arguments(Base, "cls", default={"class_path": f"{__name__}.Sub"})
    assert get_schema(parser)["properties"]["cls"]["default"] == {"class_path": f"{__name__}.Sub"}


def test_description_percent_formatting_failure(parser):
    parser.add_argument("--num", type=int, help="Uses %(unknown)s.")
    assert get_schema(parser)["properties"]["num"]["description"] == "Uses %(unknown)s."


def test_action_yes_no(parser):
    parser.add_argument("--flag", nargs="?", action=ActionYesNo)
    assert get_schema(parser)["properties"]["flag"] == {"type": "boolean", "default": False}


# other type hints


class Movie(TypedDict):
    """A movie."""

    title: str
    year: int


def test_typed_dict(parser):
    parser.add_argument("--movie", type=Movie)
    schema = get_schema(parser)["properties"]["movie"]
    assert schema["properties"] == {"title": {"type": "string"}, "year": {"type": "integer"}}
    assert schema["required"] == ["title", "year"]


@pytest.mark.skipif(not NotRequired, reason="NotRequired introduced in python 3.11 or backported in typing_extensions")
def test_typed_dict_not_required(parser):
    parser.add_argument("--movie", type=TypedDict("Movie", {"title": str, "year": NotRequired[int]}))
    schema = get_schema(parser)["properties"]["movie"]
    assert schema["properties"] == {"title": {"type": "string"}, "year": {"type": "integer"}}
    assert schema["required"] == ["title"]


# unions mixing structured and unvalidated types


def test_union_of_structured_and_unvalidated_excludes_unvalidated(parser):
    parser.add_argument("--cls", type=Union[Base, dict])
    parser.add_argument("--data", type=Union[Data, Any, None])
    parser.add_argument("--movie", type=Union[Movie, Dict[str, Any]])
    properties = get_schema(parser)["properties"]
    assert properties["cls"] == {"$ref": "#/$defs/Base"}
    assert properties["data"] == {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/Data"}]}
    assert properties["movie"]["properties"] == {"title": {"type": "string"}, "year": {"type": "integer"}}


def test_union_of_structured_and_constrained_dict_kept(parser):
    parser.add_argument("--val", type=Union[Data, Dict[str, int]])
    assert get_schema(parser)["properties"]["val"] == {
        "anyOf": [{"$ref": "#/$defs/Data"}, {"type": "object", "additionalProperties": {"type": "integer"}}]
    }


def test_union_of_unvalidated_types_unchanged(parser):
    parser.add_argument("--val", type=Union[dict, Any])
    assert get_schema(parser)["properties"]["val"] == {"anyOf": [{"type": "object"}, {}]}


@skip_if_jsonschema_unavailable
def test_union_of_structured_and_unvalidated_validation(parser):
    parser.add_argument("--cls", type=Union[Base, dict])
    schema = get_schema(parser)
    validate(schema, {"cls": {"class_path": f"{__name__}.Sub", "init_args": {"sub": 2}}})
    assert iter_errors(schema, {"cls": {"class_path": f"{__name__}.Sub", "init_args": {"bogus": 2}}})


def test_class_type(parser):
    parser.add_argument("--cls", type=Type[Base])
    assert get_schema(parser)["properties"]["cls"] == {"type": "string"}


def test_unsubscripted_tuple(parser):
    parser.add_argument("--items", type=tuple)
    assert get_schema(parser)["properties"]["items"] == {"type": "array"}


UnsupportedVar = TypeVar("UnsupportedVar")


def function_unvalidated_types(
    p1: UnsupportedVar = 1,  # type: ignore[assignment]
    p2: List[UnsupportedVar] = [2],  # type: ignore[list-item]
):
    pass  # pragma: no cover


def test_unvalidated_types_accept_anything(parser):
    parser.add_function_arguments(function_unvalidated_types, "fn")
    properties = get_schema(parser)["properties"]["fn"]["properties"]
    assert properties["p1"] == {"default": 1}
    assert properties["p2"] == {"type": "array", "default": [2]}


class AbstractBase(ABC):
    @abstractmethod
    def method(self):
        """No concrete subclass, so no class path is known."""


def test_subclass_type_without_known_class_paths(parser):
    parser.add_argument("--cls", type=AbstractBase)
    assert get_schema(parser)["$defs"]["AbstractBase"] == {
        "anyOf": [
            {"type": "string"},
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "class_path": {"type": "string"},
                    "init_args": {"type": "object"},
                    "dict_kwargs": {"type": "object"},
                },
                "required": ["class_path"],
            },
        ]
    }


class UntypedBase:
    pass


class UntypedSub(UntypedBase):
    def __init__(self, param, num: int = 1):  # untyped required param, so a parser for the init args fails
        pass  # pragma: no cover


def test_class_without_resolvable_init_args(logger):
    parser = ArgumentParser(exit_on_error=False, logger=logger)
    parser.add_argument("--cls", type=UntypedBase)
    with capture_logs(logger) as logs:
        entries = class_path_entries(get_schema(parser)["$defs"]["UntypedBase"])
    assert entries[f"{__name__}.UntypedSub"]["properties"]["init_args"] == {"type": "object"}
    assert "Unable to get schema for init args" in logs.getvalue()


@pytest.fixture
def module_with_colliding_class(tmp_path):
    content = "class Base:\n    def __init__(self, other: int = 1):\n        pass\n"
    (tmp_path / "colliding_module.py").write_text(content)
    sys.path.insert(0, str(tmp_path))
    try:
        yield
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("colliding_module", None)


def test_defs_name_collision(parser, module_with_colliding_class):
    import colliding_module

    parser.add_argument("--cls1", type=Base)
    parser.add_argument("--cls2", type=colliding_module.Base)
    defs = get_schema(parser)["$defs"]
    assert list(defs) == ["Base", "colliding_module_Base"]
    entry = class_path_entries(defs["colliding_module_Base"])["colliding_module.Base"]
    assert entry["properties"]["init_args"]["properties"] == {"other": {"type": "integer", "default": 1}}


# plain argparse actions


class KeepLast(argparse.Action):
    """A custom action, which is what keeps an argument from becoming an ActionTypeHint."""

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)  # pragma: no cover


class Duration:
    """A registered type whose string representation is not its serialization."""

    def __init__(self, spec: str):
        self.spec = spec


register_type(Duration, serializer=lambda duration: duration.spec)


def test_store_true_and_store_false_actions(parser):
    parser.add_argument("--yes", action="store_true", help="Enable it.")
    parser.add_argument("--no", action="store_false")
    properties = get_schema(parser)["properties"]
    assert properties["yes"] == {"type": "boolean", "description": "Enable it.", "default": False}
    assert properties["no"] == {"type": "boolean", "default": True}


def test_count_action(parser):
    parser.add_argument("-v", "--verbose", action="count", default=0)
    assert get_schema(parser)["properties"]["verbose"] == {"type": "integer", "default": 0}


def test_store_const_actions_sharing_dest(parser):
    for level in ["warning", "info", "debug"]:
        parser.add_argument(f"--{level}", dest="log_level", action="store_const", const=level, default="warning")
    assert get_schema(parser)["properties"]["log_level"] == {
        "enum": ["warning", "info", "debug"],
        "default": "warning",
    }


def test_append_action(parser):
    parser.add_argument("--topic", dest="topics", action="append", default=[], help="A topic.")
    parser.add_argument("--name", dest="names", action="append", type=str)
    properties = get_schema(parser)["properties"]
    assert properties["topics"] == {"type": "array", "items": {}, "description": "A topic.", "default": []}
    assert properties["names"] == {"type": "array", "items": {"type": "string"}}


def test_append_const_action(parser):
    parser.add_argument("--fast", dest="flags", action="append_const", const="fast", default=[])
    parser.add_argument("--safe", dest="flags", action="append_const", const="safe", default=[])
    assert get_schema(parser)["properties"]["flags"] == {
        "type": "array",
        "items": {"enum": ["fast", "safe"]},
        "default": [],
    }


def test_extend_action_is_a_flat_array(parser):
    parser.add_argument("--paths", action="extend", nargs="+", type=str, default=[])
    assert get_schema(parser)["properties"]["paths"] == {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
        "default": [],
    }


def test_registered_type_in_argparse_action(parser):
    parser.add_argument("--keep", type=Duration, action=KeepLast, default=Duration("7d"))
    assert get_schema(parser)["properties"]["keep"] == {"type": "string", "default": "7d"}


def test_argparse_action_with_unknown_type(parser):
    parser.add_argument("--opt", type=lambda value: value, action=KeepLast, default="x")
    assert get_schema(parser)["properties"]["opt"] == {"default": "x"}


# suppressed defaults


def test_suppressed_default_not_in_schema(parser):
    parser.add_argument("--num", type=int, default=SUPPRESS)
    parser.add_argument("--flag", action="store_true", default=SUPPRESS)
    properties = get_schema(parser)["properties"]
    assert properties["num"] == {"type": "integer"}
    assert properties["flag"] == {"type": "boolean"}


def test_suppressed_default_from_parent_parser(parser, subparser):
    subparser.add_argument("--lock_wait", type=int, default=SUPPRESS)
    parser.add_argument("--lock_wait", type=int, default=10)
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("run", subparser)
    properties = get_schema(parser)["properties"]
    assert properties["lock_wait"] == {"type": "integer", "default": 10}
    assert properties["run"]["properties"]["lock_wait"] == {"type": "integer"}


# defaults that are None


def test_none_default_is_unset_so_not_described(parser):
    # a None default means unset, see :ref:`unset-values`, so there is no default and null is not a value
    parser.add_argument("--num", type=int)
    parser.add_argument("--nums", type=int, nargs="+")
    parser.add_argument("--choice", choices=["a", "b"])
    parser.add_argument("--keep", type=Duration, action=KeepLast)
    properties = get_schema(parser)["properties"]
    assert properties["num"] == {"type": "integer"}
    assert properties["nums"] == {"type": "array", "items": {"type": "integer"}, "minItems": 1}
    assert properties["choice"] == {"enum": ["a", "b"]}
    assert properties["keep"] == {"type": "string"}


def test_unset_sentinel_defaults(parser, parsing_settings_patch):
    set_parsing_settings(unset_sentinel=True)
    parser.add_argument("--implicit", type=Optional[int])  # no default given, so Unset
    parser.add_argument("--explicit", type=Optional[int], default=None)
    parser.add_argument("--info", dest="level", action="store_const", const="info")
    properties = get_schema(parser)["properties"]
    assert properties["implicit"] == {"type": ["integer", "null"]}
    assert properties["explicit"] == {"type": ["integer", "null"], "default": None}
    assert properties["level"] == {"enum": ["info"]}  # the unset default is not one of the values


def test_unset_sentinel_none_default_described_only_when_type_accepts_null(parser, parsing_settings_patch):
    set_parsing_settings(unset_sentinel=True)
    parser.add_argument("--literal", type=Literal["a", None], default=None)
    parser.add_argument("--any", type=Any, default=None)
    parser.add_argument("--opt_cls", type=Optional[Base], default=None)
    parser.add_argument("--cls", type=Base, default=None)
    parser.add_argument("--num", type=int, default=None)
    properties = get_schema(parser)["properties"]
    assert properties["literal"] == {"enum": ["a", None], "default": None}
    assert properties["any"] == {"default": None}
    assert properties["opt_cls"]["default"] is None
    assert properties["cls"] == {"$ref": "#/$defs/Base"}  # the definition has no null subschema
    assert properties["num"] == {"type": "integer"}


@skip_if_jsonschema_unavailable
def test_none_default_null_not_accepted(parser, parsing_settings_patch):
    parser.add_argument("--num", type=int)
    assert iter_errors(get_schema(parser), {"num": None})
    # without the Unset sentinel a config null is taken as unset, which is why the parser lets it through
    set_parsing_settings(unset_sentinel=True)
    unset_parser = ArgumentParser(exit_on_error=False)
    unset_parser.add_argument("--num", type=int)
    with pytest.raises(argparse.ArgumentError, match="Expected a <class 'int'>"):
        unset_parser.parse_string('{"num": null}')


@skip_if_jsonschema_unavailable
def test_defaults_are_accepted_by_their_own_subschema(parser):
    parser.add_argument("--opt_num", type=Optional[int], default=3)
    parser.add_argument("--fruit", type=Fruit, default=Fruit.apple)
    parser.add_argument("--cls", type=Base, default=lazy_instance(Sub, sub=3))
    parser.add_argument("--keep", type=Duration, action=KeepLast, default=Duration("7d"))
    parser.add_argument("--lock_wait", type=int, default=SUPPRESS)
    parser.add_argument("--flag", action="store_true")
    parser.add_argument("--topic", dest="topics", action="append", default=[])
    parser.add_argument("--verbose", action="count", default=0)
    parser.add_argument("--debug", dest="log_level", action="store_const", const="debug", default="warning")
    schema = get_schema(parser)
    defaults = {name: sub for name, sub in schema["properties"].items() if "default" in sub}
    assert list(defaults) == ["opt_num", "fruit", "cls", "keep", "flag", "topics", "verbose", "log_level"]
    for subschema in defaults.values():
        validate({**subschema, "$defs": schema.get("$defs", {})}, subschema["default"])
