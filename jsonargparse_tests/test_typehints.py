from __future__ import annotations

import json
import pickle
import random
import sys
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    Type,
    TypedDict,
    Union,
)
from unittest import mock
from warnings import catch_warnings

import pytest

from jsonargparse import ArgumentError, Namespace, lazy_instance
from jsonargparse._optionals import pyyaml_available
from jsonargparse._typehints import (
    ActionTypeHint,
    NotRequired,
    Required,
    Unpack,
    get_all_subclass_paths,
    get_subclass_types,
    is_optional,
)
from jsonargparse._util import get_import_path
from jsonargparse.typing import (
    NotEmptyStr,
    Path_fc,
    Path_fr,
    PositiveFloat,
    PositiveInt,
)
from jsonargparse_tests.conftest import (
    capture_logs,
    get_parse_args_stdout,
    get_parser_help,
    json_or_yaml_dump,
    json_or_yaml_load,
    parser_modes,
)


def test_add_argument_given_type_and_null_action(parser):
    parser.add_argument("--op1", type=Optional[bool], action=None)
    assert parser.get_defaults().op1 is None


@pytest.mark.parametrize("typehint", [Namespace, Optional[Namespace], Union[int, Namespace], List[Namespace]])
def test_namespace_unsupported_as_type(parser, typehint):
    with pytest.raises(ValueError, match="Namespace .* not supported as a type"):
        parser.add_argument("--ns", type=typehint)


# basic types tests


@parser_modes
def test_str_no_strip(parser):
    parser.add_argument("--op", type=Optional[str])
    assert "  " == parser.parse_args(["--op", "  "]).op
    assert "" == parser.parse_args(["--op", ""]).op
    assert " abc " == parser.parse_args(["--op= abc "]).op
    assert "xyz: " == parser.parse_args(["--op=xyz: "]).op
    assert None is parser.parse_args(["--op=null"]).op
    if parser.parser_mode != "toml":
        parser.add_argument("--cfg", action="config")
        assert " " == parser.parse_args(['--cfg={"op":" "}']).op


@pytest.mark.parametrize("value", ["2022-04-12", "2022-04-32"])
def test_str_not_timestamp(parser, value):
    parser.add_argument("foo", type=str)
    assert value == parser.parse_args([value]).foo


@parser_modes
@pytest.mark.parametrize("value", ["1", "02", "3.40", "5.7e-8"])
def test_str_number_value(parser, value):
    parser.add_argument("--val", type=str)
    assert value == parser.parse_args([f"--val={value}"]).val


@parser_modes
@pytest.mark.parametrize("value", ["{{something}}", "{foo"])
def test_str_yaml_constructor_error(parser, value):
    parser.add_argument("--val", type=str)
    assert value == parser.parse_args([f"--val={value}"]).val


@parser_modes
def test_str_edge_cases(parser):
    parser.add_argument("--val", type=str)
    assert parser.parse_args(["--val=e123"]).val == "e123"
    assert parser.parse_args(["--val=123e"]).val == "123e"
    val = "1" * 5000
    assert parser.parse_args([f"--val={val}"]).val == val


def test_str_union_default_comment_like(parser):
    parser.add_argument("--val", type=Union[str, int], default="#default")
    assert "#default" == parser.get_defaults().val
    assert "#default" == parser.parse_args([]).val


def test_bool_parse(parser):
    parser.add_argument("--val", type=bool)
    assert None is parser.get_defaults().val
    assert True is parser.parse_args(["--val", "true"]).val
    if pyyaml_available:
        assert True is parser.parse_args(["--val", "TRUE"]).val
    assert False is parser.parse_args(["--val", "false"]).val
    if pyyaml_available:
        assert False is parser.parse_args(["--val", "FALSE"]).val
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--val", "1"]))


@pytest.mark.parametrize("num_type", [int, float, PositiveInt, PositiveFloat])
def test_bool_not_a_number(parser, num_type):
    parser.add_argument("--num", type=num_type)
    for value in [True, False]:
        with pytest.raises(ArgumentError):
            parser.parse_object({"num": value})


@parser_modes
def test_float_scientific_notation(parser):
    parser.add_argument("--num", type=float)
    assert 1e-3 == parser.parse_args(["--num=1e-3"]).num


@parser_modes
def test_float_implicit_leading_zero(parser):
    parser.parser_mode = "yaml"
    parser.add_argument("--num", type=float)
    assert 0.5 == parser.parse_args(["--num=.5"]).num
    assert -0.5 == parser.parse_args(["--num=-.5"]).num


def test_complex_number(parser):
    parser.add_argument("--complex", type=complex)
    cfg = parser.parse_args(["--complex=(2+3j)"])
    assert cfg.complex == 2 + 3j
    assert json_or_yaml_load(parser.dump(cfg)) == {"complex": "(2+3j)"}


@parser_modes
def test_literal(parser):
    parser.add_argument("--str", type=Literal["a", "b", None])
    parser.add_argument("--int", type=Literal[3, 4])
    parser.add_argument("--true", type=Literal[True])
    parser.add_argument("--false", type=Literal[False])
    assert "a" == parser.parse_args(["--str=a"]).str
    assert "b" == parser.parse_args(["--str=b"]).str
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--str=x"]))
    assert None is parser.parse_args(["--str=null"]).str
    assert 4 == parser.parse_args(["--int=4"]).int
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--int=5"]))
    assert True is parser.parse_args(["--true=true"]).true
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--true=false"]))
    assert False is parser.parse_args(["--false=false"]).false
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--false=true"]))
    help_str = get_parser_help(parser)
    for value in ["--str {a,b,null}", "--int {3,4}", "--true True", "--false False"]:
        assert value in help_str


def test_union_of_literals(parser):
    parser.add_argument("--literal", type=Union[Literal[1, 2], Literal["a", "b"]])
    assert "a" == parser.parse_args(["--literal=a"]).literal
    assert 2 == parser.parse_args(["--literal=2"]).literal
    with pytest.raises(ArgumentError, match=r"Expected a typing.Literal\['a', 'b']"):
        parser.parse_args(["--literal=x"])


@parser_modes
def test_type_any(parser):
    parser.add_argument("--any", type=Any)
    assert "abc" == parser.parse_args(["--any=abc"]).any
    assert 123 == parser.parse_args(["--any=123"]).any
    assert 5.6 == parser.parse_args(["--any=5.6"]).any
    assert [7, 8] == parser.parse_args(["--any=[7, 8]"]).any
    assert {"a": 0, "b": 1} == parser.parse_args(['--any={"a":0, "b":1}']).any
    assert True is parser.parse_args(["--any=true"]).any
    assert False is parser.parse_args(["--any=false"]).any
    assert None is parser.parse_args(["--any=null"]).any
    assert " " == parser.parse_args(["--any= "]).any
    assert " xyz " == parser.parse_args(["--any= xyz "]).any
    assert "[[[" == parser.parse_args(["--any=[[["]).any


def test_type_any_dump(parser):
    parser.add_argument("--any", type=Any, default=EnumABC.B)
    cfg = parser.parse_args([])
    assert {"any": "B"} == json_or_yaml_load(parser.dump(cfg))


def test_type_typehint_without_arg(parser):
    parser.add_argument("--type", type=type)
    cfg = parser.parse_args(["--type=uuid.UUID"])
    assert cfg.type is uuid.UUID
    assert json_or_yaml_load(parser.dump(cfg)) == {"type": "uuid.UUID"}


class BaseC:
    def __init__(self, p: int = 0):
        self.p = p

    def get_p(self):
        return self.p


class SubC(BaseC):
    pass


def test_type_typehint_with_arg(parser):
    parser.add_argument("--cls", type=type[BaseC])
    cfg = parser.parse_args([f"--cls={__name__}.BaseC"])
    assert cfg.cls is BaseC
    assert json_or_yaml_load(parser.dump(cfg)) == {"cls": f"{__name__}.BaseC"}
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--cls=uuid.UUID"]))


def test_type_typehint_help_known_subclasses(parser):
    parser.add_argument("--cls", type=Type[BaseC])
    help_str = get_parser_help(parser)
    assert f"known subclasses: {__name__}.BaseC," in help_str


# enum tests


class EnumABC(Enum):
    A = 1
    B = 2
    C = 3


@parser_modes
def test_enum_parse(parser):
    parser.add_argument("--enum", type=EnumABC)
    for val in ["A", "B", "C"]:
        assert EnumABC[val] == parser.parse_args([f"--enum={val}"]).enum
    for val in ["X", "b", 2]:
        pytest.raises(ArgumentError, lambda: parser.parse_args([f"--enum={val}"]))


def test_enum_dump(parser):
    parser.add_argument("--enum", type=EnumABC)
    cfg = parser.parse_args(["--enum=C"])
    assert {"enum": "C"} == json_or_yaml_load(parser.dump(cfg))
    with pytest.raises(TypeError):
        parser.dump(Namespace(enum="x"))


def test_enum_help(parser):
    parser.add_argument("--enum", type=EnumABC, default=EnumABC.B, help="Help")
    assert EnumABC.B == parser.get_defaults().enum
    help_str = get_parser_help(parser)
    assert "--enum {A,B,C}" in help_str
    assert "Help (type: EnumABC, default: B)" in help_str


def test_enum_optional(parser):
    parser.add_argument("--enum", type=Optional[EnumABC])
    assert EnumABC.B == parser.parse_args(["--enum=B"]).enum
    assert None is parser.parse_args(["--enum=null"]).enum
    help_str = get_parser_help(parser)
    assert "--enum {A,B,C,null}" in help_str


class EnumStr(str, Enum):
    A = "A"
    B = "B"


def test_enum_str_optional(parser):
    parser.add_argument("--enum", type=Optional[EnumStr])
    assert "B" == parser.parse_args(["--enum=B"]).enum
    assert None is parser.parse_args(["--enum=null"]).enum


def test_literal_enum_values(parser):
    parser.add_argument("--enum", type=Literal[EnumABC.A, EnumABC.C, "X"])
    assert EnumABC.A == parser.parse_args(["--enum=A"]).enum
    assert EnumABC.C == parser.parse_args(["--enum=C"]).enum
    assert "X" == parser.parse_args(["--enum=X"]).enum
    with pytest.raises(ArgumentError, match="Expected a typing.*.Literal"):
        parser.parse_args(["--enum=B"])


# set tests


@parser_modes
def test_set(parser):
    parser.add_argument("--set", type=Set[int])
    assert {1, 2} == parser.parse_args(["--set=[1, 2]"]).set
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--set=["a", "b"]'])
    ctx.match("Expected a <class 'int'>")


def test_frozenset(parser):
    parser.add_argument("--frozen", type=FrozenSet[int])
    cfg = parser.parse_args(["--frozen=[1, 2]"])
    assert frozenset([1, 2]) == cfg.frozen
    assert parser.dump(cfg, format="json") == '{"frozen":[1,2]}'
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--frozen=["a", "b"]'])
    ctx.match("Expected a <class 'int'>")


# tuple tests


@parser_modes
def test_tuple_without_arg(parser):
    parser.add_argument("--tuple", type=tuple)
    cfg = parser.parse_args(['--tuple=[1, "a", true]'])
    assert (1, "a", True) == cfg.tuple
    help_str = get_parser_help(parser, strip=True)
    assert "--tuple [ITEM,...] (type: tuple, default: null)" in help_str


@parser_modes
def test_tuples_nested(parser):
    parser.add_argument("--tuple", type=Tuple[Tuple[str, str], Tuple[Tuple[int, float], Tuple[int, float]]])
    cfg = parser.parse_args(['--tuple=[["foo", "bar"], [[1, 2.02], [3, 3.09]]]'])
    assert (("foo", "bar"), ((1, 2.02), (3, 3.09))) == cfg.tuple


@parser_modes
def test_tuple_ellipsis(parser):
    parser.add_argument("--tuple", type=Tuple[float, ...])
    assert (1.2,) == parser.parse_args(["--tuple=[1.2]"]).tuple
    assert (1.2, 3.4) == parser.parse_args(["--tuple=[1.2, 3.4]"]).tuple
    assert () == parser.parse_args(["--tuple=[]"]).tuple
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--tuple=[2, "a"]']))


def test_tuples_nested_ellipsis(parser):
    parser.add_argument("--tuple", type=Tuple[Tuple[str, str], Tuple[Tuple[int, float], ...]])
    cfg = parser.parse_args(['--tuple=[["foo", "bar"], [[1, 2.02], [3, 3.09]]]'])
    assert (("foo", "bar"), ((1, 2.02), (3, 3.09))) == cfg.tuple


def test_tuple_union(parser, tmp_cwd):
    parser.add_argument("--tuple", type=Tuple[Union[int, EnumABC], Path_fc, NotEmptyStr])
    cfg = parser.parse_args(['--tuple=[2, "a", "b"]'])
    assert (2, "a", "b") == cfg.tuple
    assert isinstance(cfg.tuple[1], Path_fc)
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--tuple=[]"]))
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--tuple=[2, "a", "b", 5]']))
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--tuple=[2, "a"]']))
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--tuple={"a":1, "b":"2"}']))
    help_str = get_parser_help(parser, strip=True)
    if sys.version_info < (3, 14):
        assert "--tuple [ITEM,...] (type: Tuple[Union[int, EnumABC], Path_fc, NotEmptyStr], default: null)" in help_str
    else:
        assert "--tuple [ITEM,...] (type: Tuple[int | EnumABC, Path_fc, NotEmptyStr], default: null)" in help_str


# list tests


@parser_modes
@pytest.mark.parametrize("list_type", [Iterable, List, Sequence], ids=str)
def test_list_variants(parser, list_type):
    parser.add_argument("--list", type=list_type[int])
    cfg = parser.parse_args(["--list=[1, 2]"])
    assert [1, 2] == cfg.list


def test_deque(parser):
    parser.add_argument("--deque", type=Deque[int])
    cfg = parser.parse_args(["--deque=[1, 2]"])
    assert isinstance(cfg.deque, deque)
    assert deque([1, 2]) == cfg.deque
    assert parser.dump(cfg, format="json") == '{"deque":[1,2]}'


def test_list_dump(parser):
    parser.add_argument("--list", type=Union[PositiveInt, List[PositiveInt]])
    dump = json_or_yaml_load(parser.dump(Namespace(list=[1, 2])))
    assert [1, 2] == dump["list"]
    with pytest.raises(TypeError):
        parser.dump(Namespace(list=[1, -2]))


def test_list_enum(parser):
    parser.add_argument("--list", type=List[EnumABC])
    assert [EnumABC.B, EnumABC.A] == parser.parse_args(['--list=["B", "A"]']).list


@parser_modes
def test_list_tuple(parser):
    parser.add_argument("--list", type=List[Tuple[int, float]])
    cfg = parser.parse_args(["--list=[[1, 2.02], [3, 3.09]]"])
    assert [(1, 2.02), (3, 3.09)] == cfg.list


def test_list_union(parser):
    parser.add_argument("--list1", type=List[Union[float, str, type(None)]])
    parser.add_argument("--list2", type=List[Union[int, EnumABC]])
    assert [1.2, "B"] == parser.parse_args(['--list1=[1.2, "B"]']).list1
    assert [3, EnumABC.B] == parser.parse_args(['--list2=[3, "B"]']).list2
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--list1={"a":1, "b":"2"}']))


def test_list_str_positional(parser):
    parser.add_argument("list", type=List[str])
    cfg = parser.parse_args(['["a", "b"]'])
    assert cfg.list == ["a", "b"]


@parser_modes
def test_sequence_default_tuple(parser):
    parser.add_argument("--seq", type=Sequence[str], default=("one", "two"))
    cfg = parser.parse_args([])
    assert cfg == parser.get_defaults()


# list append tests


@parser_modes
def test_list_append(parser):
    parser.add_argument("--val", type=Union[int, float, List[int]])
    assert 0 == parser.parse_args(["--val=0"]).val
    assert [0] == parser.parse_args(["--val+=0"]).val
    assert [1, 2, 3] == parser.parse_args(["--val=1", "--val+=2", "--val+=3"]).val
    assert [1, 2, 3] == parser.parse_args(["--val=[1,2]", "--val+=3"]).val
    assert [1] == parser.parse_args(["--val=0.1", "--val+=1"]).val
    assert 3 == parser.parse_args(["--val=[1,2]", "--val=3"]).val
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--val=a", "--val+=1"]))


@parser_modes
def test_list_append_default_empty(parser):
    parser.add_argument("--list", type=List[str], default=[])
    assert [] == parser.get_defaults().list
    assert ["a"] == parser.parse_args(['--list=["a"]']).list
    assert [] == parser.get_defaults().list
    assert ["b", "c"] == parser.parse_args(['--list+=["b", "c"]']).list
    assert [] == parser.get_defaults().list


@parser_modes
def test_list_append_config(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--val", type=List[int], default=[1, 2])
    assert [3, 4] == parser.parse_args(["--cfg", '{"val": [3, 4]}']).val
    assert [1, 2, 3] == parser.parse_args(["--cfg", '{"val+": 3}']).val
    assert [1, 2, 3, 4] == parser.parse_args(["--cfg", '{"val+": [3, 4]}']).val
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--cfg", '{"val+": "a"}']))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--val=2", "--cfg", '{"val+": 3}']))


def test_list_append_default_config_files(parser, tmp_cwd, subtests):
    config_path = tmp_cwd / "config.yaml"
    parser.default_config_files = [config_path]
    parser.add_argument("--nums", type=List[int], default=[0])

    with subtests.test("replace"):
        config_path.write_text(json_or_yaml_dump({"nums": [1]}))
        cfg = parser.parse_args(["--nums+=2"])
        assert cfg.nums == [1, 2]
        cfg = parser.parse_args(["--nums+=[2, 3]"])
        assert cfg.nums == [1, 2, 3]

    with subtests.test("append"):
        config_path.write_text(json_or_yaml_dump({"nums+": [1]}))
        cfg = parser.get_defaults()
        assert cfg.nums == [0, 1]
        cfg = parser.parse_args(["--nums+=2"])
        assert cfg.nums == [0, 1, 2]
        cfg = parser.parse_args(["--nums+=[2, 3]"])
        assert cfg.nums == [0, 1, 2, 3]
        assert str(cfg.__default_config__) == str(config_path)

    with subtests.test("append in second default config"):
        config_path2 = tmp_cwd / "config2.yaml"
        config_path2.write_text(json_or_yaml_dump({"nums+": [2]}))
        parser.default_config_files += [str(config_path2)]
        cfg = parser.get_defaults()
        assert cfg.nums == [0, 1, 2]
        assert [str(c) for c in cfg.__default_config__] == parser.default_config_files


def test_list_append_subcommand_global_default_config_files(parser, subparser, tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    parser.default_config_files = [config_path]
    subcommands = parser.add_subcommands()
    subparser.add_argument("--nums", type=List[int], default=[0])
    subcommands.add_subcommand("sub", subparser)
    config_path.write_text(json_or_yaml_dump({"sub": {"nums": [1]}}))

    cfg = parser.parse_args(["sub", "--nums+=2"])
    assert cfg.sub.nums == [1, 2]
    assert str(cfg.__default_config__) == str(config_path)
    cfg = parser.parse_args(["sub", "--nums+=2"], defaults=False)
    assert cfg.sub.nums == [2]


def test_list_append_subcommand_subparser_default_config_files(parser, subparser, tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    subcommands = parser.add_subcommands()
    subparser.default_config_files = [config_path]
    subparser.add_argument("--nums", type=List[int], default=[0])
    subcommands.add_subcommand("sub", subparser)
    config_path.write_text(json_or_yaml_dump({"nums": [1]}))

    cfg = parser.parse_args(["sub", "--nums+=2"])
    assert cfg.sub.nums == [1, 2]
    assert str(cfg.sub.__default_config__) == str(config_path)
    cfg = parser.parse_args(["sub", "--nums+=2"], defaults=False)
    assert cfg.sub.nums == [2]


class NestedList:
    def __init__(
        self,
        nested: List[Dict[str, str]] = [{"a": "random_crop"}, {"b": "random_blur"}],
    ) -> None:
        self.nested = nested  # pragma: no cover


def test_list_append_dicts_nested_with_default(parser):
    parser.add_argument("--cls", type=NestedList, default={"class_path": "NestedList"})
    cfg = parser.parse_args(['--cls.nested+={"d":"random_perspective"}'])
    assert cfg.cls.class_path == f"{__name__}.NestedList"
    assert cfg.cls.init_args == Namespace(
        nested=[{"a": "random_crop"}, {"b": "random_blur"}, {"d": "random_perspective"}]
    )


def test_list_append_dicts_nested_without_default(parser):
    parser.add_argument("--cls", type=NestedList)
    cfg = parser.parse_args(["--cls=NestedList", '--cls.nested+={"d":"random_perspective"}'])
    assert cfg.cls.class_path == f"{__name__}.NestedList"
    assert cfg.cls.init_args == Namespace(
        nested=[{"a": "random_crop"}, {"b": "random_blur"}, {"d": "random_perspective"}]
    )


# dict tests


@parser_modes
def test_dict_without_arg(parser):
    parser.add_argument("--dict", type=dict)
    assert {} == parser.parse_args(["--dict={}"])["dict"]
    assert {"a": 1, "b": "2"} == parser.parse_args(['--dict={"a":1, "b":"2"}'])["dict"]
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--dict=1"]))


@parser_modes
def test_dict_int_keys(parser):
    parser.add_argument("--d", type=Dict[int, str])
    parser.add_argument("--cfg", action="config")
    cfg = {"d": {1: "val1", 2: "val2"}}
    assert cfg["d"] == parser.parse_args(["--cfg", json.dumps(cfg)]).d
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--cfg={"d": {"a": "b"}}']))


def test_dict_union(parser, tmp_cwd):
    parser.add_argument("--dict1", type=Dict[int, Optional[Union[float, EnumABC]]])
    parser.add_argument("--dict2", type=Dict[str, Union[bool, Path_fc]])
    cfg = parser.parse_args(['--dict1={"2":4.5, "6":"C"}', '--dict2={"a":true, "b":"f"}'])
    assert {2: 4.5, 6: EnumABC.C} == cfg.dict1
    assert {"a": True, "b": "f"} == cfg.dict2
    assert isinstance(cfg.dict2["b"], Path_fc)
    assert {5: None} == parser.parse_args(['--dict1={"5":null}']).dict1
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--dict1=["a", "b"]']))
    cfg = json_or_yaml_load(parser.dump(cfg))
    assert {"dict1": {"2": 4.5, "6": "C"}, "dict2": {"a": True, "b": "f"}} == cfg


def test_dict_union_int_keys(parser):
    parser.add_argument("--dict", type=Union[int, Dict[int, int]], default=1)
    assert 1 == parser.get_defaults().dict
    assert {2: 7, 4: 9} == parser.parse_args(['--dict={"2": 7, "4": 9}']).dict


def test_dict_command_line_set_items(parser):
    parser.add_argument("--dict", type=Dict[str, int])
    cfg = parser.parse_args(["--dict.one=1", "--dict.two=2"])
    assert cfg.dict == {"one": 1, "two": 2}


@dataclass
class _Vals:
    val_0: int = 0
    val_1: int = 0


@dataclass
class _Cfg:
    """Needs to be defined outside of test_nested_dict_command_line_set_items"""

    vals: dict[str, _Vals] = field(default_factory=dict)


def test_nested_dict_command_line_set_items(parser):
    parser.add_class_arguments(_Cfg, nested_key="cfg")

    # works before #824
    args = ["--cfg", '{"vals": {"a": {"val_0": 0, "val_1": 1}}}', "--cfg.vals.a", '{"val_0": 100}']
    cfg = parser.parse_args(args).cfg
    assert (cfg.vals["a"].val_0, cfg.vals["a"].val_1) == (100, 1)

    # does not work before #824
    args = ["--cfg", '{"vals": {"a": {"val_0": 0, "val_1": 1}}}', "--cfg.vals.a.val_0", "100"]
    cfg = parser.parse_args(args).cfg
    assert (cfg.vals["a"].val_0, cfg.vals["a"].val_1) == (100, 1)


def test_dict_command_line_set_items_with_space(parser):
    parser.add_argument("--dict", type=dict)
    cfg = parser.parse_args(["--dict.a=x y"])
    assert {"a": "x y"} == cfg.dict


@parser_modes
def test_mapping_nested_without_args(parser):
    parser.add_argument("--map", type=Mapping[str, Union[int, Mapping]])
    assert {"a": 1} == parser.parse_args(['--map={"a": 1}']).map
    assert {"b": {"c": 2}} == parser.parse_args(['--map={"b": {"c": 2}}']).map


@parser_modes
def test_typeddict_without_arg(parser):
    parser.add_argument("--typeddict", type=TypedDict("MyDict", {}))
    assert {} == parser.parse_args(["--typeddict={}"])["typeddict"]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":1}'])
    ctx.match("Unexpected keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--typeddict=1"])
    ctx.match("Expected a <class 'dict'>")


def test_typeddict_with_args(parser):
    parser.add_argument("--typeddict", type=TypedDict("MyDict", {"a": int}))
    assert {"a": 1} == parser.parse_args(['--typeddict={"a": 1}'])["typeddict"]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":1, "b":2}'])
    ctx.match("Unexpected keys")
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--typeddict={"a":1, "b":2}']))
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--typeddict={}"])
    ctx.match("Missing required keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":"x"}'])
    ctx.match("Expected a <class 'int'>")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--typeddict=1"])
    ctx.match("Expected a <class 'dict'>")


def test_typeddict_with_args_ntotal(parser):
    parser.add_argument("--typeddict", type=TypedDict("MyDict", {"a": int}, total=False))
    assert {"a": 1} == parser.parse_args(['--typeddict={"a": 1}'])["typeddict"]
    assert {} == parser.parse_args(["--typeddict={}"])["typeddict"]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":1, "b":2}'])
    ctx.match("Unexpected keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":"x"}'])
    ctx.match("Expected a <class 'int'>")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--typeddict=1"])
    ctx.match("Expected a <class 'dict'>")


@pytest.mark.skipif(not NotRequired, reason="NotRequired introduced in python 3.11 or backported in typing_extensions")
def test_not_required_support():
    assert ActionTypeHint.is_supported_typehint(NotRequired[Any])


@pytest.mark.skipif(not NotRequired, reason="NotRequired introduced in python 3.11 or backported in typing_extensions")
def test_typeddict_with_not_required_arg(parser):
    parser.add_argument("--typeddict", type=TypedDict("MyDict", {"a": int, "b": NotRequired[int]}))
    assert {"a": 1} == parser.parse_args(['--typeddict={"a": 1}'])["typeddict"]
    assert {"a": 1, "b": 2} == parser.parse_args(['--typeddict={"a": 1, "b": 2}'])["typeddict"]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":1, "b":2, "c": 3}'])
    ctx.match("Unexpected keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"b":2}'])
    ctx.match("Missing required keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--typeddict={}"])
    ctx.match("Missing required keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":"x"}'])
    ctx.match("Expected a <class 'int'>")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":1, "b":"x"}'])
    ctx.match("Expected a <class 'int'>")


@pytest.mark.skipif(not Required, reason="Required introduced in python 3.11 or backported in typing_extensions")
def test_required_support():
    assert ActionTypeHint.is_supported_typehint(Required[Any])


@pytest.mark.skipif(not Required, reason="Required introduced in python 3.11 or backported in typing_extensions")
def test_typeddict_with_required_arg(parser):
    parser.add_argument("--typeddict", type=TypedDict("MyDict", {"a": Required[int], "b": int}, total=False))
    assert {"a": 1} == parser.parse_args(['--typeddict={"a": 1}'])["typeddict"]
    assert {"a": 1, "b": 2} == parser.parse_args(['--typeddict={"a": 1, "b": 2}'])["typeddict"]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":1, "b":2, "c": 3}'])
    ctx.match("Unexpected keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"b":2}'])
    ctx.match("Missing required keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--typeddict={}"])
    ctx.match("Missing required keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":"x"}'])
    ctx.match("Expected a <class 'int'>")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--typeddict={"a":1, "b":"x"}'])
    ctx.match("Expected a <class 'int'>")


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
def test_unpack_support(parser):
    assert ActionTypeHint.is_supported_typehint(Unpack[Any])


if Unpack:  # and Required and NotRequired
    MyTestUnpackDict = TypedDict("MyTestUnpackDict", {"a": Required[int], "b": NotRequired[int]}, total=True)

    class UnpackClass:
        def __init__(self, **kwargs: Unpack[MyTestUnpackDict]) -> None:  # pragma: no cover
            self.a = kwargs["a"]
            self.b = kwargs.get("b")

    @dataclass
    class MyTestUnpackClass:
        test: UnpackClass

    class MyTestInheritedUnpackClass(UnpackClass):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)  # pragma: no cover


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
@pytest.mark.parametrize(["init_args"], [({"a": 1},), ({"a": 2, "b": None},), ({"a": 3, "b": 1},)])
def test_valid_unpack_typeddict(parser, init_args):
    parser.add_argument("--testclass", type=MyTestUnpackClass)
    test_config = {"test": {"class_path": f"{__name__}.UnpackClass", "init_args": init_args}}
    cfg = parser.parse_args([f"--testclass={json.dumps(test_config)}"])
    assert test_config == cfg["testclass"].as_dict()
    # also assert no issues with dumping
    if test_config["test"]["init_args"].get("b") is None:
        # parser.dump does not dump null b
        test_config["test"]["init_args"].pop("b", None)
    assert test_config == json.loads(parser.dump(cfg, format="json"))["testclass"]


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
@pytest.mark.parametrize(["init_args"], [({},), ({"b": None},), ({"b": 1},)])
def test_invalid_unpack_typeddict(parser, init_args):
    parser.add_argument("--testclass", type=MyTestUnpackClass)
    test_config = {"test": {"class_path": f"{__name__}.UnpackClass", "init_args": init_args}}
    with pytest.raises(ArgumentError):
        parser.parse_args([f"--testclass={json.dumps(test_config)}"])


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
@pytest.mark.parametrize(["init_args"], [({"a": 1},), ({"a": 2, "b": None},), ({"a": 3, "b": 1},)])
def test_valid_inherited_unpack_typeddict(parser, init_args):
    parser.add_argument("--testclass", type=MyTestInheritedUnpackClass)
    test_config = {"class_path": f"{__name__}.MyTestInheritedUnpackClass", "init_args": init_args}
    cfg = parser.parse_args([f"--testclass={json.dumps(test_config)}"])
    assert test_config == cfg["testclass"].as_dict()
    # also assert no issues with dumping
    if test_config["init_args"].get("b") is None:
        # parser.dump does not dump null b
        test_config["init_args"].pop("b", None)
    assert test_config == json.loads(parser.dump(cfg, format="json"))["testclass"]


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
@pytest.mark.parametrize(["init_args"], [({},), ({"b": None},), ({"b": 1},)])
def test_invalid_inherited_unpack_typeddict(parser, init_args):
    parser.add_argument("--testclass", type=MyTestInheritedUnpackClass)
    test_config = {"class_path": f"{__name__}.MyTestInheritedUnpackClass", "init_args": init_args}
    with pytest.raises(ArgumentError):
        parser.parse_args([f"--testclass={json.dumps(test_config)}"])


if Unpack:
    TotalFalseDict = TypedDict(
        "TotalFalseDict",
        {"a": int, "b": str, "c": Required[float]},
        total=False,
    )

    class TotalFalseUnpackClass:
        def __init__(self, **kwargs: Unpack[TotalFalseDict]) -> None:  # pragma: no cover
            self.a = kwargs.get("a")
            self.b = kwargs.get("b")
            self.c = kwargs["c"]


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
def test_unpack_total_false_typeddict_optionality(parser):
    added = parser.add_class_arguments(TotalFalseUnpackClass, "cls")
    assert set(added) == {"cls.a", "cls.b", "cls.c"}
    required = {action.dest for action in parser._actions if getattr(action, "required", False)}
    # total=False keys without Required are optional
    assert "cls.a" not in required
    assert "cls.b" not in required
    # keys wrapped in Required stay required even when total=False
    assert "cls.c" in required


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
def test_unpack_total_false_typeddict_parse(parser):
    parser.add_class_arguments(TotalFalseUnpackClass, "cls")
    # only the Required key needs to be provided
    cfg = parser.parse_args(["--cls.c=1.5"])
    assert cfg.cls.c == 1.5
    cfg = parser.parse_args(["--cls.c=1.5", "--cls.a=2", "--cls.b=x"])
    assert cfg.cls == Namespace(a=2, b="x", c=1.5)
    # the Required key is still required
    with pytest.raises(ArgumentError, match="the following arguments are required: cls.c"):
        parser.parse_args([])


class BottomDict(TypedDict, total=True):
    a: int  # total=True -> required


class MiddleDict(BottomDict, total=False):
    b: int  # total=False -> optional


class TopDict(MiddleDict, total=True):
    c: int  # total=True -> required


def test_typeddict_totality_inheritance(parser):
    parser.add_argument("--middledict", type=MiddleDict, required=False)
    parser.add_argument("--topdict", type=TopDict, required=False)
    assert {"a": 1} == parser.parse_args(['--middledict={"a": 1}'])["middledict"]
    assert {"a": 1, "b": 2} == parser.parse_args(['--middledict={"a": 1, "b": 2}'])["middledict"]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--middledict={}"])
    ctx.match("Missing required keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--middledict={"b": 2}'])
    ctx.match("Missing required keys")
    assert {"a": 1, "c": 2} == parser.parse_args(['--topdict={"a": 1, "c": 2}'])["topdict"]
    assert {"a": 1, "b": 2, "c": 3} == parser.parse_args(['--topdict={"a": 1, "b": 2, "c": 3}'])["topdict"]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--topdict={"a": 1, "b": 2}'])
    ctx.match("Missing required keys")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--topdict={"b":2, "c": 3}'])
    ctx.match("Missing required keys")


if Unpack:

    class TotalityInheritanceUnpackClass:
        def __init__(self, **kwargs: Unpack[TopDict]) -> None:  # pragma: no cover
            self.a = kwargs["a"]
            self.b = kwargs.get("b")
            self.c = kwargs["c"]


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
def test_unpack_typeddict_totality_inheritance(parser):
    parser.add_class_arguments(TotalityInheritanceUnpackClass, "cls")
    required = {action.dest for action in parser._actions if getattr(action, "required", False)}
    # requiredness follows each class' own totality: a (total=True), b (total=False), c (total=True)
    assert required == {"cls.a", "cls.c"}
    cfg = parser.parse_args(["--cls.a=1", "--cls.c=3"])
    # the optional key (total=False) is omitted when not provided
    assert cfg.cls == Namespace(a=1, c=3)
    cfg = parser.parse_args(["--cls.a=1", "--cls.b=2", "--cls.c=3"])
    assert cfg.cls == Namespace(a=1, b=2, c=3)
    with pytest.raises(ArgumentError, match="the following arguments are required: cls.c"):
        parser.parse_args(["--cls.a=1", "--cls.b=2"])
    with pytest.raises(ArgumentError, match="the following arguments are required: cls.a"):
        parser.parse_args(["--cls.b=2", "--cls.c=3"])


# Required/NotRequired overriding the class totality, across totality-flipping inheritance.
# The test module uses "from __future__ import annotations" so these are postponed annotations.
if Required and NotRequired:

    class OverrideBaseDict(TypedDict, total=True):
        a: int  # total=True -> required
        x: NotRequired[str]  # override -> optional

    class OverrideMiddleDict(OverrideBaseDict, total=False):
        b: int  # total=False -> optional
        y: Required[str]  # override -> required

    class OverrideTopDict(OverrideMiddleDict, total=True):
        c: int  # total=True -> required

    if Unpack:

        class OverrideUnpackClass:
            def __init__(self, **kwargs: Unpack[OverrideTopDict]) -> None:  # pragma: no cover
                self.kwargs = kwargs


@pytest.mark.skipif(not (Required and NotRequired), reason="Required/NotRequired required")
def test_typeddict_required_notrequired_totality_type(parser):
    parser.add_argument("--top", type=OverrideTopDict, required=False)
    # all required keys provided, optional (b, x) omitted
    cfg = parser.parse_args(['--top={"a": 1, "c": 3, "y": "z"}'])
    assert cfg.top == {"a": 1, "c": 3, "y": "z"}
    # Required override in a total=False class is required
    with pytest.raises(ArgumentError, match="Missing required keys: {'y'}"):
        parser.parse_args(['--top={"a": 1, "c": 3}'])
    # NotRequired override in a total=True class is optional (no error for missing x)
    with pytest.raises(ArgumentError, match="Missing required keys: {'c'}"):
        parser.parse_args(['--top={"a": 1, "y": "z"}'])


@pytest.mark.skipif(not (Unpack and Required and NotRequired), reason="Unpack/Required/NotRequired required")
def test_typeddict_required_notrequired_totality_unpack(parser):
    added = parser.add_class_arguments(OverrideUnpackClass, "cls")
    assert set(added) == {"cls.a", "cls.b", "cls.c", "cls.x", "cls.y"}
    required = {action.dest for action in parser._actions if getattr(action, "required", False)}
    assert required == {"cls.a", "cls.c", "cls.y"}


def test_mapping_proxy_type(parser):
    parser.add_argument("--mapping", type=MappingProxyType)
    cfg = parser.parse_args(['--mapping={"x":1}'])
    assert isinstance(cfg.mapping, MappingProxyType)
    assert cfg.mapping == {"x": 1}
    assert parser.dump(cfg, format="json") == '{"mapping":{"x":1}}'


def test_mapping_default_mapping_proxy_type(parser):
    mapping_proxy = MappingProxyType({"x": 1})
    parser.add_argument("--mapping", type=Mapping[str, int], default=mapping_proxy)
    cfg = parser.parse_args([])
    assert isinstance(cfg.mapping, Mapping)
    assert mapping_proxy == cfg.mapping
    assert parser.dump(cfg, format="json") == '{"mapping":{"x":1}}'


def test_ordered_dict(parser):
    parser.add_argument("--odict", type=OrderedDict[str, int])
    cfg = parser.parse_args(['--odict={"a":1, "b":2}'])
    assert isinstance(cfg.odict, OrderedDict)
    assert OrderedDict([("a", 1), ("b", 2)]) == cfg.odict
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--odict={"x":"-"}'])
    ctx.match("Expected a <class 'int'>")
    assert parser.dump(cfg, format="json") == '{"odict":{"a":1,"b":2}}'
    if pyyaml_available:
        assert parser.dump(cfg, format="yaml") == "odict:\n  a: 1\n  b: 2\n"


def test_dict_default_ordered_dict(parser):
    parser.add_argument("--dict", type=dict, default=OrderedDict({"a": 1}))
    defaults = parser.get_defaults()
    assert isinstance(defaults.dict, OrderedDict)
    assert defaults.dict == {"a": 1}


# union tests


@pytest.mark.parametrize(
    ["subtypes", "arg", "expected"],
    [
        ((bool, str), "=true", True),
        ((str, bool), "=true", "true"),
        ((int, str), "=1", 1),
        ((str, int), "=2", "2"),
        ((float, int), "=3", 3.0),
        ((int, float), "=4", 4),
        ((int, List[int]), "=5", 5),
        ((List[int], int), "=6", 6),
        ((int, List[int]), "+=7", [7]),
        ((List[int], int), "+=8", [8]),
    ],
    ids=str,
)
def test_union_subtypes_order(parser, subtypes, arg, expected):
    parser.add_argument("--val", type=Union[subtypes])
    val = parser.parse_args([f"--val{arg}"]).val
    assert isinstance(val, type(expected))
    assert val == expected


def test_union_unsupported_subtype(parser, logger):
    parser.logger = logger
    with capture_logs(logger) as logs:
        parser.add_argument("--union", type=Union[int, str, "unsupported"])  # noqa: F821
    assert "Discarding unsupported subtypes" in logs.getvalue()


def test_union_new_syntax_simple_types(parser):
    parser.add_argument("--val", type=int | None)
    assert 123 == parser.parse_args(["--val=123"]).val
    assert None is parser.parse_args(["--val=null"]).val
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--val=abc"]))


def test_union_new_syntax_subclass_type(parser):
    parser.add_argument("--op", type=BaseC | bool)
    help_str = get_parse_args_stdout(parser, [f"--op.help={__name__}.SubC"])
    assert "--op.p" in help_str


# callable tests


def test_callable_function_path(parser):
    parser.add_argument("--callable", type=Callable, default=time.time)

    cfg = parser.get_defaults()
    assert cfg.callable is time.time
    assert json_or_yaml_load(parser.dump(cfg)) == {"callable": "time.time"}

    cfg = parser.parse_args(["--callable=random.randint"])
    assert cfg.callable is random.randint
    assert json_or_yaml_load(parser.dump(cfg)) == {"callable": "random.randint"}

    help_str = get_parser_help(parser)
    assert "(type: Callable, default: time.time)" in help_str

    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--callable=jsonargparse.not_exist"])
    ctx.match("Callable expects a function or a callable class")


def test_callable_list_of_function_paths(parser):
    parser.add_argument("--callables", type=List[Callable])

    cfg = parser.parse_args(['--callables=["random.randint", "time.time"]'])
    assert [random.randint, time.time] == cfg.callables

    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--callables=["jsonargparse.not_exist"]'])
    ctx.match("Callable expects a function or a callable class")


class CallableClassPath:
    def __init__(self, p1: int = 1):
        self.p1 = p1

    def __call__(self):
        return self.p1


def test_callable_class_path_simple(parser):
    parser.add_argument("--callable", type=Callable)

    value = {"class_path": f"{__name__}.CallableClassPath", "init_args": {"p1": 2}}
    cfg = parser.parse_args([f"--callable={json.dumps(value)}"])
    assert value == cfg.callable.as_dict()
    assert value == json_or_yaml_load(parser.dump(cfg))["callable"]
    init = parser.instantiate(cfg)
    assert isinstance(init.callable, CallableClassPath)
    assert 2 == init.callable()

    pytest.raises(ArgumentError, lambda: parser.parse_args(["--callable={}"]))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--callable=jsonargparse.SUPPRESS"]))
    pytest.raises(ArgumentError, lambda: parser.parse_args([f"--callable={__name__}.BaseC"]))
    value = {"class_path": f"{__name__}.CallableClassPath", "key": "val"}
    pytest.raises(ArgumentError, lambda: parser.parse_args([f"--callable={json.dumps(value)}"]))


class CallableParent(CallableClassPath):
    pass


def test_callable_class_path_parent(parser):
    parser.add_argument("--callable", type=Callable)
    value = {"class_path": f"{__name__}.CallableParent", "init_args": {"p1": 1}}
    cfg = parser.parse_args([f"--callable={__name__}.CallableParent"])
    assert value == cfg.callable.as_dict()


class CallableGiveName:
    def __init__(self, name: str):
        self.name = name

    def __call__(self):
        return self.name


@pytest.mark.parametrize("callable_type", [Callable, Optional[Callable], Union[int, Callable]])
def test_callable_class_path_short_init_args(parser, callable_type):
    parser.add_argument("--call", type=callable_type)
    cfg = parser.parse_args([f"--call={__name__}.CallableGiveName", "--call.name=Bob"])
    assert cfg.call.class_path == f"{__name__}.CallableGiveName"
    assert cfg.call.init_args == Namespace(name="Bob")
    init = parser.instantiate(cfg)
    assert init.call() == "Bob"


def int_to_str(p: int) -> str:
    return str(p)  # pragma: no cover


def str_to_int(p: str) -> int:
    return int(p)  # pragma: no cover


def test_callable_args_function_path(parser):
    parser.add_argument("--callable", type=Callable[[int], str])
    cfg = parser.parse_args([f"--callable={__name__}.int_to_str"])
    assert int_to_str is cfg.callable
    cfg = parser.parse_args([f"--callable={__name__}.str_to_int"])
    assert str_to_int is cfg.callable  # Currently callable args are ignored


class Optimizer:
    def __init__(self, params: List[float], lr: float = 1e-3, momentum: float = 0.0):
        self.params = params
        self.lr = lr
        self.momentum = momentum


class SGD(Optimizer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class Adam(Optimizer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


@pytest.mark.parametrize(
    ["typehint", "expected"],
    [
        (None, None),
        (Union[int, float], None),
        (Optimizer, (Optimizer,)),
        (Union[SGD, Adam, str], (SGD, Adam)),
        (Optional[Union[SGD, Adam]], (SGD, Adam)),
        (Callable[[int], Optimizer], (Optimizer,)),
        (Callable[[int], Union[Adam, SGD]], (Adam, SGD)),
        (Optional[Callable[[int], Union[Adam, SGD]]], (Adam, SGD)),
        (Union[Optimizer, Callable[[int], Union[Adam, SGD]]], (Optimizer, Adam, SGD)),
    ],
)
def test_get_subclass_types(typehint, expected):
    assert expected == get_subclass_types(typehint, callable_return=True)


def test_callable_args_return_type_class(parser, subtests):
    parser.add_argument("--optimizer", type=Callable[[List[float]], Optimizer], default=SGD)

    with subtests.test("default"):
        cfg = parser.get_defaults()
        assert cfg.optimizer.class_path == f"{__name__}.SGD"
        init = parser.instantiate(cfg)
        optimizer = init.optimizer([0.1, 2, 3])
        assert isinstance(optimizer, SGD)
        assert [0.1, 2, 3] == optimizer.params
        assert 1e-3 == optimizer.lr
        assert 0.0 == optimizer.momentum

    with subtests.test("parse dict"):
        value = {
            "class_path": "Adam",
            "init_args": {
                "lr": 0.01,
            },
        }
        cfg = parser.parse_args([f"--optimizer={json.dumps(value)}"])
        assert f"{__name__}.Adam" == cfg.optimizer.class_path
        assert Namespace(lr=0.01, momentum=0.0) == cfg.optimizer.init_args
        init = parser.instantiate(cfg)
        optimizer = init.optimizer([4.5, 6.7])
        assert isinstance(optimizer, Adam)
        assert [4.5, 6.7] == optimizer.params
        assert 0.01 == optimizer.lr
        assert 0.0 == optimizer.momentum
        dump = parser.dump(cfg)
        assert json_or_yaml_load(dump) == cfg.as_dict()

    with subtests.test("short notation"):
        assert cfg == parser.parse_args(["--optimizer=Adam", "--optimizer.lr=0.01"])

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "--optimizer.help" in help_str
        assert "Show the help for the given subclass of Optimizer" in help_str
        for name in ["Optimizer", "SGD", "Adam"]:
            assert f"{__name__}.{name}" in help_str
        help_str = get_parse_args_stdout(parser, ["--optimizer.help=Adam"])
        assert f"Help for --optimizer.help={__name__}.Adam" in help_str
        assert "--optimizer.lr" in help_str
        assert "--optimizer.params" not in help_str


class OptimizerFactory(Protocol):
    def __call__(self, params: List[float]) -> Optimizer: ...


class DifferentParamsOrder(Optimizer):
    def __init__(self, lr: float, params: List[float], momentum: float = 0.0):
        super().__init__(lr=lr, params=params, momentum=momentum)


def test_callable_protocol_instance_factory(parser, subtests):
    parser.add_argument("--optimizer", type=OptimizerFactory, default=SGD)

    with subtests.test("default"):
        cfg = parser.get_defaults()
        assert cfg.optimizer.class_path == f"{__name__}.SGD"
        init = parser.instantiate(cfg)
        optimizer = init.optimizer(params=[1, 2])
        assert isinstance(optimizer, SGD)
        assert optimizer.params == [1, 2]
        assert optimizer.lr == 1e-3
        assert optimizer.momentum == 0.0

    with subtests.test("parse dict"):
        value = {
            "class_path": "Adam",
            "init_args": {
                "lr": 0.01,
                "momentum": 0.9,
            },
        }
        cfg = parser.parse_args([f"--optimizer={json.dumps(value)}"])
        init = parser.instantiate(cfg)
        optimizer = init.optimizer(params=[3, 2, 1])
        assert isinstance(optimizer, Adam)
        assert optimizer.params == [3, 2, 1]
        assert optimizer.lr == 0.01
        assert optimizer.momentum == 0.9

    with subtests.test("params order"):
        value = {
            "class_path": "DifferentParamsOrder",
            "init_args": {
                "lr": 0.1,
                "momentum": 0.8,
            },
        }
        cfg = parser.parse_args([f"--optimizer={json.dumps(value)}"])
        init = parser.instantiate(cfg)
        optimizer = init.optimizer(params=[3, 2])
        assert isinstance(optimizer, DifferentParamsOrder)
        assert optimizer.params == [3, 2]
        assert optimizer.lr == 0.1
        assert optimizer.momentum == 0.8
        dump = parser.dump(cfg)
        assert json_or_yaml_load(dump) == cfg.as_dict()

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "--optimizer.help" in help_str
        assert "Show the help for the given subclass or implementer of protocol {Optimizer,OptimizerFactory" in help_str
        help_str = get_parse_args_stdout(parser, [f"--optimizer.help={__name__}.DifferentParamsOrder"])
        assert f"Help for --optimizer.help={__name__}.DifferentParamsOrder" in help_str
        assert "--optimizer.lr" in help_str
        assert "--optimizer.params" not in help_str


class OptimizerFactoryPositionalAndKeyword(Protocol):
    def __call__(self, lr: float, /, params: List[float]) -> Optimizer: ...


def test_callable_protocol_instance_factory_with_positional(parser):
    parser.add_argument("--optimizer", type=OptimizerFactoryPositionalAndKeyword)

    value = {
        "class_path": "DifferentParamsOrder",
        "init_args": {
            "momentum": 0.9,
        },
    }
    cfg = parser.parse_args([f"--optimizer={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    optimizer = init.optimizer(0.2, params=[0, 1])
    assert optimizer.lr == 0.2
    assert optimizer.params == [0, 1]
    assert optimizer.momentum == 0.9
    assert isinstance(optimizer, DifferentParamsOrder)


def test_optional_callable_return_type_help(parser):
    parser.add_argument("--optimizer", type=Optional[Callable[[List[float]], Optimizer]])
    help_str = get_parser_help(parser)
    assert "--optimizer.help" in help_str
    assert f"known subclasses: {__name__}.Optimizer," in help_str
    help_str = get_parse_args_stdout(parser, ["--optimizer.help=Adam"])
    assert f"Help for --optimizer.help={__name__}.Adam" in help_str
    assert "--optimizer.lr" in help_str


def test_callable_return_type_class_implicit_class_path(parser):
    parser.add_argument("--optimizer", type=Callable[[List[float]], Optimizer])
    cfg = parser.parse_args(['--optimizer={"lr": 0.5}'])
    assert cfg.optimizer.class_path == f"{__name__}.Optimizer"
    assert cfg.optimizer.init_args == Namespace(lr=0.5, momentum=0.0)
    cfg = parser.parse_args(["--optimizer.momentum=0.2"])
    assert cfg.optimizer.class_path == f"{__name__}.Optimizer"
    assert cfg.optimizer.init_args == Namespace(lr=0.001, momentum=0.2)


def test_callable_multiple_args_return_type_class(parser, subtests):
    parser.add_argument("--optimizer", type=Callable[[List[float], float], Optimizer], default=SGD)

    with subtests.test("default"):
        cfg = parser.get_defaults()
        init = parser.instantiate(cfg)
        optimizer = init.optimizer([0.1, 2, 3], 1e-3)
        assert isinstance(optimizer, SGD)
        assert [0.1, 2, 3] == optimizer.params
        assert 1e-3 == optimizer.lr
        assert 0.0 == optimizer.momentum

    with subtests.test("parse dict"):
        value = {
            "class_path": "Adam",
            "init_args": {"momentum": 0.9},
        }
        cfg = parser.parse_args([f"--optimizer={json.dumps(value)}"])
        assert f"{__name__}.Adam" == cfg.optimizer.class_path
        assert Namespace(momentum=0.9) == cfg.optimizer.init_args
        init = parser.instantiate(cfg)
        optimizer = init.optimizer([4.5, 6.7], 0.01)
        assert isinstance(optimizer, Adam)
        assert [4.5, 6.7] == optimizer.params
        assert 0.01 == optimizer.lr
        assert 0.9 == optimizer.momentum
        dump = parser.dump(cfg)
        assert json_or_yaml_load(dump) == cfg.as_dict()

    with subtests.test("short notation"):
        assert cfg == parser.parse_args(["--optimizer=Adam", "--optimizer.momentum=0.9"])

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "Show the help for the given subclass of Optimizer" in help_str
        for name in ["Optimizer", "SGD", "Adam"]:
            assert f"{__name__}.{name}" in help_str


def test_callable_return_class_default_class_override_init_arg(parser):
    parser.add_argument("--optimizer", type=Callable[[List[float]], Optimizer], default=SGD)
    cfg = parser.parse_args(["--optimizer.momentum=0.5", "--optimizer.lr=0.05"])
    assert cfg.optimizer.class_path == f"{__name__}.SGD"
    assert cfg.optimizer.init_args == Namespace(lr=0.05, momentum=0.5)


class SkipCallableInitArg:
    def __init__(self, optimizer: Callable[[List[float]], Optimizer] = SGD):
        self.optimizer = optimizer  # pragma: no cover


def test_add_class_arguments_skip_callable_init_arg(parser):
    parser.add_class_arguments(SkipCallableInitArg, skip={"optimizer.init_args.lr"})

    help_str = get_parse_args_stdout(parser, ["--optimizer.help=Adam"])
    assert "--optimizer.lr" not in help_str
    assert "--optimizer.momentum" in help_str

    cfg = parser.parse_args(["--optimizer=Adam", "--optimizer.momentum=0.5"])
    assert cfg.optimizer.class_path == f"{__name__}.Adam"
    assert cfg.optimizer.init_args == Namespace(momentum=0.5)

    with pytest.raises(ArgumentError):
        parser.parse_args(["--optimizer=Adam", "--optimizer.lr=0.05"])


class SkipCallableMergedWithPartial:
    def __init__(self, optimizer: Callable[[List[float], float], Optimizer] = SGD):
        self.optimizer = optimizer  # pragma: no cover


def test_add_class_arguments_skip_callable_init_arg_and_partial_skip(parser):
    parser.add_class_arguments(SkipCallableMergedWithPartial, skip={"optimizer.init_args.momentum"})

    help_str = get_parse_args_stdout(parser, ["--optimizer.help=Adam"])
    assert "--optimizer.params" not in help_str
    assert "--optimizer.lr" not in help_str
    assert "--optimizer.momentum" not in help_str

    with pytest.raises(ArgumentError):
        parser.parse_args(["--optimizer=Adam", "--optimizer.momentum=0.9"])

    init = parser.instantiate(parser.parse_args(["--optimizer=Adam"]))
    optimizer = init.optimizer([1.2], 0.2)
    assert isinstance(optimizer, Adam)
    assert optimizer.params == [1.2]
    assert optimizer.lr == 0.2
    assert optimizer.momentum == 0.0


class StepLR:
    def __init__(self, optimizer: Optimizer, last_epoch: int = -1):
        self.optimizer = optimizer
        self.last_epoch = last_epoch


class ReduceLROnPlateau:
    def __init__(self, optimizer: Optimizer, monitor: str, factor: float = 0.1):
        self.optimizer = optimizer
        self.monitor = monitor
        self.factor = factor


def test_callable_args_return_type_union_of_classes(parser, subtests):
    parser.add_argument(
        "--scheduler",
        type=Callable[[Optimizer], Union[StepLR, ReduceLROnPlateau]],
        default=StepLR,
    )
    optimizer = Optimizer([])

    with subtests.test("default"):
        cfg = parser.get_defaults()
        init = parser.instantiate(cfg)
        scheduler = init.scheduler(optimizer)
        assert isinstance(scheduler, StepLR)
        assert scheduler.optimizer is optimizer
        assert -1 == scheduler.last_epoch

    with subtests.test("parse"):
        value = {
            "class_path": "ReduceLROnPlateau",
            "init_args": {
                "monitor": "loss",
            },
        }
        cfg = parser.parse_args([f"--scheduler={json.dumps(value)}"])
        assert f"{__name__}.ReduceLROnPlateau" == cfg.scheduler.class_path
        assert Namespace(monitor="loss", factor=0.1) == cfg.scheduler.init_args
        init = parser.instantiate(cfg)
        scheduler = init.scheduler(optimizer)
        assert isinstance(scheduler, ReduceLROnPlateau)
        assert scheduler.optimizer is optimizer
        assert "loss" == scheduler.monitor

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "Show the help for the given subclass of {StepLR,ReduceLROnPlateau}" in help_str
        for name in ["StepLR", "ReduceLROnPlateau"]:
            assert f"{__name__}.{name}" in help_str


def optional_callable_args_return_type_class(
    scheduler: Optional[Callable[[Optimizer], StepLR]] = lambda o: StepLR(o, last_epoch=1),
):
    return scheduler  # pragma: no cover


def test_optional_callable_args_return_type_class(parser, subtests):
    parser.add_function_arguments(optional_callable_args_return_type_class)
    optimizer = Optimizer([])

    with subtests.test("default"):
        cfg = parser.get_defaults()
        init = parser.instantiate(cfg)
        scheduler = init.scheduler(optimizer)
        assert isinstance(scheduler, StepLR)
        assert scheduler.last_epoch == 1
        assert scheduler.optimizer is optimizer

    with subtests.test("parse"):
        value = {
            "class_path": "StepLR",
            "init_args": {
                "last_epoch": 2,
            },
        }
        cfg = parser.parse_args([f"--scheduler={json.dumps(value)}"])
        init = parser.instantiate(cfg)
        scheduler = init.scheduler(optimizer)
        assert isinstance(scheduler, StepLR)
        assert scheduler.last_epoch == 2
        assert scheduler.optimizer is optimizer

    with subtests.test("parse null"):
        cfg = parser.parse_args(["--scheduler=null"])
        assert cfg.scheduler is None

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "Show the help for the given subclass of StepLR" in help_str


class CallableSubconfig:
    def __init__(self, o: Callable[[int], Optimizer]):
        self.o = o


def test_callable_args_return_type_class_subconfig(parser, tmp_cwd):
    config = {
        "class_path": "Adam",
        "init_args": {"momentum": 0.8},
    }
    Path("optimizer.yaml").write_text(json_or_yaml_dump(config))

    parser.add_class_arguments(CallableSubconfig, "m", sub_configs=True)
    cfg = parser.parse_args(["--m.o=optimizer.yaml"])
    assert cfg.m.o.class_path == f"{__name__}.Adam"
    init = parser.instantiate(cfg)
    optimizer = init.m.o(1)
    assert isinstance(optimizer, Adam)
    assert optimizer.momentum == 0.8


def test_callable_args_pickleable(parser, tmp_cwd):
    config = {
        "class_path": "Adam",
        "init_args": {"momentum": 0.8},
    }
    Path("optimizer.yaml").write_text(json_or_yaml_dump(config))
    parser.add_class_arguments(CallableSubconfig, "m", sub_configs=True)
    cfg = parser.parse_args(["--m.o=optimizer.yaml"])
    init = parser.instantiate(cfg)

    filepath = str(tmp_cwd) + "/pickled.pkl"
    with open(filepath, "wb") as f:
        pickle.dump(init, f)


class Module:
    pass


class LeakyReLU(Module):
    def __init__(self, negative_slope: float = 0.01):
        self.negative_slope = negative_slope


class Model(Module):
    def __init__(
        self,
        activation: Callable[[], Module] = lambda: LeakyReLU(negative_slope=0.05),
    ):
        self.activation = activation


def test_callable_zero_args_return_type_class(parser):
    parser.add_class_arguments(Model, "model")
    cfg = parser.parse_args([])
    assert cfg.model.activation == Namespace(
        class_path=f"{__name__}.LeakyReLU", init_args=Namespace(negative_slope=0.05)
    )
    init = parser.instantiate(cfg)
    assert isinstance(init.model, Model)
    assert not isinstance(init.model.activation, Module)
    activation = init.model.activation()
    assert isinstance(activation, LeakyReLU)
    assert activation.negative_slope == 0.05


class ModelRequiredCallableArg:
    def __init__(
        self,
        scheduler: Callable[[Optimizer], ReduceLROnPlateau] = lambda o: ReduceLROnPlateau(o, monitor="acc"),
    ):
        self.scheduler = scheduler  # pragma: no cover


def test_callable_return_class_required_arg_from_default(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--model", type=ModelRequiredCallableArg)

    cfg = parser.parse_args(["--model=ModelRequiredCallableArg"])
    assert cfg.model.init_args.scheduler.class_path == f"{__name__}.ReduceLROnPlateau"
    assert cfg.model.init_args.scheduler.init_args == Namespace(monitor="acc", factor=0.1)

    config = {
        "model": {
            "class_path": f"{__name__}.ModelRequiredCallableArg",
            "init_args": {
                "scheduler": {
                    "class_path": f"{__name__}.ReduceLROnPlateau",
                    "init_args": {
                        "factor": 0.5,
                    },
                },
            },
        }
    }
    cfg = parser.parse_args([f"--cfg={json.dumps(config)}"])
    assert cfg.model.init_args.scheduler.class_path == f"{__name__}.ReduceLROnPlateau"
    assert cfg.model.init_args.scheduler.init_args == Namespace(monitor="acc", factor=0.5)


class ModelListCallableReturnClass:
    def __init__(
        self,
        schedulers: List[Callable[[Optimizer], Union[StepLR, ReduceLROnPlateau]]] = [],
    ):
        self.schedulers = schedulers  # pragma: no cover


def test_list_callable_return_class(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--model", type=ModelListCallableReturnClass)

    config = {
        "model": {
            "class_path": f"{__name__}.ModelListCallableReturnClass",
            "init_args": {
                "schedulers": [
                    {
                        "class_path": f"{__name__}.StepLR",
                    },
                    {
                        "class_path": f"{__name__}.ReduceLROnPlateau",
                        "init_args": {
                            "factor": 0.5,
                        },
                    },
                ],
            },
        },
    }

    cfg = parser.parse_args([f"--cfg={json.dumps(config)}", "--model.schedulers.monitor=val/mAP50"])
    assert cfg.model.init_args.schedulers[1].class_path == f"{__name__}.ReduceLROnPlateau"
    assert cfg.model.init_args.schedulers[1].init_args == Namespace(monitor="val/mAP50", factor=0.5)


# lazy_instance tests


def test_lazy_instance_init_postponed():
    class Sub(BaseC):
        init_called = False
        also_get_p = BaseC.get_p

        def __init__(self, *args, **kwargs):
            self.init_called = True
            super().__init__(*args, **kwargs)

    lazy_inst = lazy_instance(Sub, p=3)
    assert isinstance(lazy_inst, Sub)
    assert lazy_inst.init_called is False
    assert lazy_inst.also_get_p() == 3
    assert lazy_inst.init_called is True


class IntParam:
    def __init__(self, param: int = 1):
        pass  # pragma: no cover


def test_lazy_instance_invalid_init_value():
    with pytest.raises(ValueError) as ctx:
        lazy_instance(IntParam, param="not an int")
    ctx.match("Expected a <class 'int'>")


def test_lazy_instance_pickleable():
    instance1 = lazy_instance(SubC, p=2)
    instance2 = lazy_instance(SubC, p=3)
    assert instance1.__class__.__module__ == __name__
    assert instance1.__class__ is instance2.__class__
    reloaded = pickle.loads(pickle.dumps(instance1))
    assert reloaded.__class__ is instance1.__class__
    assert reloaded.lazy_get_init_data() == instance1.lazy_get_init_data()


class OptimizerCallable:
    def __init__(self, lr: float = 0.1):
        self.lr = lr

    def __call__(self, params) -> SGD:
        return SGD(params, lr=self.lr)


def test_lazy_instance_callable():
    lazy_optimizer = lazy_instance(OptimizerCallable, lr=0.2)
    optimizer = lazy_optimizer([1, 2])
    assert optimizer.lr == 0.2
    assert optimizer.params == [1, 2]
    optimizer = lazy_optimizer([3, 4])
    assert optimizer.params == [3, 4]


# other tests


@pytest.mark.parametrize(
    "typehint",
    [
        lambda: None,
        "unsupported",
        Optional["unsupported"],  # noqa: F821
        Tuple[int, "unsupported"],  # noqa: F821
        Union["unsupported1", "unsupported2"],  # noqa: F821
    ],
    ids=lambda x: "lambda" if getattr(x, "__name__", "") == "<lambda>" else str(x),
)
def test_action_typehint_unsupported_type(typehint):
    with pytest.raises(ValueError, match="Unsupported type hint"):
        ActionTypeHint(typehint=typehint)


def test_action_typehint_none_type_error():
    with pytest.raises(ValueError) as ctx:
        ActionTypeHint(typehint=None)
    ctx.match("Expected typehint keyword argument")


@pytest.mark.parametrize(
    ["typehint", "ref_type", "expected"],
    [
        (Optional[bool], bool, True),
        (Union[type(None), bool], bool, True),
        (Dict[bool, type(None)], bool, False),  # type: ignore[misc]
        (Optional[Path_fr], Path_fr, True),
        (Union[type(None), Path_fr], Path_fr, True),
        (Dict[Path_fr, type(None)], Path_fr, False),  # type: ignore[misc]
        (Optional[EnumABC], Enum, True),
        (Union[type(None), EnumABC], Enum, True),
        (Dict[EnumABC, type(None)], Enum, False),  # type: ignore[misc]
    ],
    ids=str,
)
def test_is_optional(typehint, ref_type, expected):
    assert expected == is_optional(typehint, ref_type)


class SkipDefault(BaseC):
    def __init__(self, *args, param: str = "0", **kwargs):
        super().__init__(*args, **kwargs)  # pragma: no cover


def test_dump_skip_default(parser):
    parser.add_argument("--g1.op1", default=1)
    parser.add_argument("--g1.op2", default="abc")
    parser.add_argument("--g2.op1", type=Callable, default=uuid.uuid4)
    parser.add_argument("--g2.op2", type=BaseC, default=lazy_instance(BaseC, p=2))

    cfg = parser.get_defaults()
    dump = parser.dump(cfg, skip_default=True)
    assert dump.strip() == "{}"

    cfg.g2.op2.class_path = f"{__name__}.SkipDefault"
    dump = json_or_yaml_load(parser.dump(cfg, skip_default=True))
    assert dump == {"g2": {"op2": {"class_path": f"{__name__}.SkipDefault", "init_args": {"p": 2}}}}

    cfg.g2.op2.init_args.p = 0
    dump = json_or_yaml_load(parser.dump(cfg, skip_default=True))
    assert dump == {"g2": {"op2": {"class_path": f"{__name__}.SkipDefault"}}}

    parser.link_arguments("g1.op1", "g2.op2.init_args.p")
    parser.link_arguments("g1.op2", "g2.op2.init_args.param")
    del cfg["g2.op2.init_args"]
    dump = json_or_yaml_load(parser.dump(cfg, skip_default=True))
    assert dump == {"g2": {"op2": {"class_path": f"{__name__}.SkipDefault"}}}


class ImportClass:
    pass


def test_get_all_subclass_paths_import_error():
    def mocked_get_import_path(cls):
        if cls is ImportClass:
            raise ImportError("Failed to import ImportClass")
        return get_import_path(cls)  # pragma: no cover

    with mock.patch("jsonargparse._typehints.get_import_path", mocked_get_import_path):
        with catch_warnings(record=True) as w:
            subclass_paths = get_all_subclass_paths(ImportClass)
    assert "Failed to import ImportClass" in str(w[0].message)
    assert subclass_paths == []


def test_non_path_dump(parser):
    parser.add_argument("--data", type=Union[Path_fr, Dict[str, List[str]]])
    cfg = parser.parse_args(['--data={"key": ["value"]}'])
    assert json_or_yaml_load(parser.dump(cfg)) == {"data": {"key": ["value"]}}
