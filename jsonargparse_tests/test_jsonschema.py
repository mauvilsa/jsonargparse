from __future__ import annotations

import json
import re
from importlib.util import find_spec

import pytest

from jsonargparse import ActionJsonSchema, ArgumentError
from jsonargparse_tests.conftest import get_parser_help, json_or_yaml_dump


@pytest.fixture(autouse=True, scope="module")
def skip_if_jsonschema_unavailable():
    if not find_spec("jsonschema"):
        pytest.skip("jsonschema package is required")


# test schema array

schema_array = {
    "type": "array",
    "items": {"type": "integer"},
}


@pytest.fixture
def parser_schema_array(parser):
    parser.add_argument(
        "--op1",
        action=ActionJsonSchema(schema=schema_array),
        help="schema: %s",
    )
    return parser


@pytest.mark.usefixtures("parser_schema_array")
def test_schema_in_help(parser):
    help_str = get_parser_help(parser)
    help_schema = re.sub(
        "^.*schema:([^()]+)[^{}]*$",
        r"\1",
        help_str.replace("\n", " "),
    )
    assert schema_array == json.loads(help_schema)


@pytest.mark.usefixtures("parser_schema_array")
def test_schema_array_parse_args(parser):
    assert [0, 1, 2] == parser.parse_args(["--op1", "[0, 1, 2]"]).op1
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--op1", '[1, "two"]']))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--op1", "[1.5, 2]"]))


@pytest.mark.usefixtures("parser_schema_array")
def test_schema_array_parse_string(parser):
    cfg = parser.parse_string(json_or_yaml_dump({"op1": [3, 7]}))
    assert [3, 7] == cfg["op1"]


@pytest.mark.usefixtures("parser_schema_array")
def test_schema_array_parse_path(parser, tmp_path):
    path = tmp_path / "op1.json"
    path.write_text('{"op1": [-1, 1, 0]}')
    cfg = parser.parse_path(path)
    assert [-1, 1, 0] == cfg["op1"]


# test schema object


@pytest.fixture
def parser_schema_object(parser):
    schema_object = {
        "type": "object",
        "properties": {
            "k1": {"type": "string"},
            "k2": {"type": "integer"},
            "k3": {
                "type": "number",
                "default": 17,
            },
        },
        "additionalProperties": False,
    }
    parser.add_argument("--op2", action=ActionJsonSchema(schema=schema_object))
    parser.add_argument("--cfg", action="config")
    return parser


@pytest.mark.usefixtures("parser_schema_object")
def test_schema_object_parse_args(parser):
    op2_val = {"k1": "one", "k2": 2, "k3": 3.3}
    assert op2_val == parser.parse_args(["--op2", json_or_yaml_dump(op2_val)]).op2
    assert 17 == parser.parse_args(["--op2", '{"k2": 2}']).op2["k3"]
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--op2", '{"k1": 1}']))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--op2", '{"k2": "2"}']))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--op2", '{"k4": 4}']))


@pytest.mark.usefixtures("parser_schema_object")
def test_schema_object_parse_string(parser):
    op2_val = {"k1": "two", "k2": 7, "k3": 2.4}
    cfg = parser.parse_string(json_or_yaml_dump({"op2": op2_val}))
    assert op2_val == cfg["op2"]


@pytest.mark.usefixtures("parser_schema_object")
def test_schema_object_parse_config(parser, tmp_path):
    op2_val = {"k1": "three", "k2": -3, "k3": 0.4}
    path = tmp_path / "op2.json"
    path.write_text(json_or_yaml_dump({"op2": op2_val}))
    cfg = parser.parse_args([f"--cfg={path}"])
    assert op2_val == cfg["op2"]


def test_schema_oneof_add_defaults(parser):
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["x"]},
                    "pc": {"type": "integer", "default": 1},
                    "px": {"type": "string", "default": "dx"},
                },
            },
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["y"]},
                    "pc": {"type": "integer", "default": 2},
                    "py": {"type": "string", "default": "dy"},
                },
            },
        ]
    }
    parser.add_argument("--data", action=ActionJsonSchema(schema=schema))
    parser.add_argument("--cfg", action="config")

    cfg = parser.parse_args(['--data={"kind": "x"}'])
    assert cfg.data == {"kind": "x", "pc": 1, "px": "dx"}

    cfg = parser.parse_args(['--data={"kind": "y", "pc": 3}'])
    assert cfg.data == {"kind": "y", "pc": 3, "py": "dy"}


# other tests


def test_action_jsonschema_schema_dict_or_str():
    action1 = ActionJsonSchema(schema=schema_array)
    action2 = ActionJsonSchema(schema=json.dumps(schema_array))
    assert action1._validator.schema == action2._validator.schema


def test_action_jsonschema_init_failures():
    pytest.raises(ValueError, ActionJsonSchema)
    from jsonschema.exceptions import SchemaError

    pytest.raises((ValueError, SchemaError), lambda: ActionJsonSchema(schema=":"))
    pytest.raises((ValueError, SchemaError), lambda: ActionJsonSchema(schema="."))
    with pytest.raises(ValueError, match="does not accept the following parameters: {'unexpected'}"):
        ActionJsonSchema(schema=schema_array, unexpected=True)
