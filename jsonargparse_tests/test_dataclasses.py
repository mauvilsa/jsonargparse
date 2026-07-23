from __future__ import annotations

import dataclasses
import json
import sys
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, Union
from unittest.mock import patch

import pytest

from jsonargparse import (
    ArgumentError,
    ArgumentParser,
    Namespace,
    set_parsing_settings,
)
from jsonargparse._common import subclasses_disabled_selectors
from jsonargparse._namespace import NSKeyError
from jsonargparse._optionals import (
    docstring_parser_support,
    type_alias_type,
    typing_extensions_import,
)
from jsonargparse._signatures import convert_to_dict
from jsonargparse.typing import PositiveFloat, PositiveInt, restricted_number_type
from jsonargparse_tests.conftest import (
    get_parse_args_stdout,
    get_parser_help,
    json_or_yaml_load,
    skip_if_docstring_parser_unavailable,
)

annotated = typing_extensions_import("Annotated")


@pytest.fixture
def enable_subclasses(subclass_behavior):
    set_parsing_settings(subclasses_enabled=["is_pure_dataclass"])
    yield


BetweenThreeAndNine = restricted_number_type("BetweenThreeAndNine", float, [(">=", 3), ("<=", 9)])
ListPositiveInt = List[PositiveInt]


@dataclasses.dataclass
class DifferentModuleBaseData:
    """
    Args:
        count: between 3 and 9
        numbers: list of positive ints
    """

    count: Optional[BetweenThreeAndNine] = None  # type: ignore[valid-type]
    numbers: ListPositiveInt = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class DataClassA:
    """DataClassA description

    Args:
        a1: a1 help
        a2: a2 help
    """

    a1: PositiveInt = PositiveInt(1)
    a2: str = "2"


@dataclasses.dataclass
class DataClassB:
    """DataClassB description

    Args:
        b1: b1 help
        b2: b2 help
    """

    b1: PositiveFloat = PositiveFloat(3.0)
    b2: DataClassA = DataClassA(a2="x")


def test_add_class_arguments(parser, subtests):
    parser.add_class_arguments(DataClassA, "a", default=DataClassA(), help="CustomA title")
    parser.add_class_arguments(DataClassB, "b", default=DataClassB())

    with subtests.test("get_defaults"):
        cfg = parser.get_defaults()
        assert dataclasses.asdict(DataClassA()) == cfg["a"].as_dict()
        assert dataclasses.asdict(DataClassB()) == cfg["b"].as_dict()
        dump = json_or_yaml_load(parser.dump(cfg))
        assert dataclasses.asdict(DataClassA()) == dump["a"]
        assert dataclasses.asdict(DataClassB()) == dump["b"]

    with subtests.test("instantiate"):
        init = parser.instantiate(cfg)
        assert isinstance(init["a"], DataClassA)
        assert isinstance(init["b"], DataClassB)
        assert isinstance(init["b"].b2, DataClassA)

    with subtests.test("parse_args"):
        assert 5 == parser.parse_args(["--b.b2.a1=5"]).b.b2.a1
        with pytest.raises(ArgumentError, match="Not of type PositiveInt"):
            parser.parse_args(["--b.b2.a1=x"])

    with subtests.test("docstrings in help"):
        help_str = get_parser_help(parser)
        if docstring_parser_support:
            assert "CustomA title:" in help_str
            assert "DataClassB description:" in help_str
            assert "b2 help:" in help_str

    with subtests.test("add failures"):
        with pytest.raises(ValueError, match="Expected 'class_type' parameter to be a class type"):
            parser.add_class_arguments(1, "c")
        with pytest.raises(NSKeyError, match='No action for key "c.b2.b1" to set its default'):
            parser.add_class_arguments(DataClassB, "c", default=DataClassB(b2=DataClassB()))


@dataclasses.dataclass
class NestedDefaultsA:
    x: list = dataclasses.field(default_factory=list)
    v: int = 1


@dataclasses.dataclass
class NestedDefaultsB:
    a: List[NestedDefaultsA]


def test_add_dataclass_nested_defaults(parser):
    parser.add_class_arguments(NestedDefaultsB, "data")
    cfg = parser.parse_args(["--data.a=[{}]"])
    assert cfg.data == Namespace(a=[Namespace(x=[], v=1)])


@dataclasses.dataclass
class NestedDefaultsC:
    field_with_dash: int = 5


@dataclasses.dataclass
class NestedDefaultsD:
    c_with_dash: NestedDefaultsC = dataclasses.field(default_factory=NestedDefaultsC)


def test_dashes_in_nested_dataclass():
    class UnderscoresToDashesParser(ArgumentParser):
        def add_argument(self, *args, **kwargs):
            args = [arg.replace("_", "-") for arg in args]
            return super().add_argument(*args, **kwargs)

    parser = UnderscoresToDashesParser(default_env=True)
    parser.add_class_arguments(NestedDefaultsD)
    ns = parser.parse_args([])
    cfg = parser.instantiate(ns)
    assert cfg.c_with_dash.field_with_dash == 5


class ClassDataAttributes:
    def __init__(
        self,
        a1: DataClassA = DataClassA(),
        a2: DataClassB = DataClassB(),
    ):
        self.a1 = a1
        self.a2 = a2


def test_add_class_with_dataclass_attributes(parser):
    parser.add_class_arguments(ClassDataAttributes, "g")

    cfg = parser.get_defaults()
    assert dataclasses.asdict(DataClassA()) == cfg.g.a1.as_dict()
    assert dataclasses.asdict(DataClassB()) == cfg.g.a2.as_dict()
    dump = json_or_yaml_load(parser.dump(cfg))
    assert dataclasses.asdict(DataClassA()) == dump["g"]["a1"]
    assert dataclasses.asdict(DataClassB()) == dump["g"]["a2"]

    init = parser.instantiate(cfg)
    assert isinstance(init.g.a1, DataClassA)
    assert isinstance(init.g.a2, DataClassB)
    assert isinstance(init.g.a2.b2, DataClassA)


class SubBaseClass:
    def __init__(self, a1: DataClassB = DataClassB()):
        """SubBaseClass description"""
        self.a1 = a1


class RootClass:
    def __init__(self, c1: SubBaseClass):  # pragma: no cover
        """RootClass description"""
        self.c1 = c1


def test_add_class_dataclass_typehint_in_subclass(parser):
    parser.add_class_arguments(RootClass)
    class_path = f'"class_path": "{__name__}.SubBaseClass"'
    init_args = '"init_args": {"a1": {"b2": {"a1": 7}}}'

    cfg = parser.parse_args(["--c1={" + class_path + ", " + init_args + "}"])
    assert cfg.c1.class_path == f"{__name__}.SubBaseClass"
    assert cfg.c1.init_args.a1.b2.a1 == 7
    assert isinstance(cfg.c1.init_args.a1.b2.a1, PositiveInt)

    init = parser.instantiate(cfg)
    assert isinstance(init.c1, SubBaseClass)
    assert isinstance(init.c1.a1, DataClassB)
    assert isinstance(init.c1.a1.b2, DataClassA)
    assert isinstance(init.c1.a1.b1, PositiveFloat)


@dataclasses.dataclass
class OptionalWithDefault:
    param: Optional[str]


def test_add_class_optional_without_default(parser):
    parser.add_class_arguments(OptionalWithDefault)
    assert parser.get_defaults() == Namespace(param=None)
    with pytest.raises(ArgumentError, match="the following arguments are required: param"):
        parser.parse_args([])
    with pytest.raises(ArgumentError, match="the following arguments are required: param"):
        parser.parse_args(["--param=null"])


@dataclasses.dataclass
class ListOptionalA:
    x: int


@dataclasses.dataclass
class ListOptionalB:
    a: Optional[ListOptionalA] = None


def test_list_nested_optional_dataclass(parser):
    parser.add_argument("--b", type=List[ListOptionalB])
    cfg = parser.parse_args(['--b=[{"a":{"x":1}}]'])
    assert cfg.b == [Namespace(a=Namespace(x=1))]


@dataclasses.dataclass
class ItemData:
    x: int = 1
    y: str = "one"


def test_list_append_defaults(parser):
    parser.add_argument("--list", type=List[ItemData])
    cfg = parser.parse_args(["--list+={}", '--list+={"x":2,"y":"two"}', '--list+={"x":3}'])
    assert cfg.list == [Namespace(x=1, y="one"), Namespace(x=2, y="two"), Namespace(x=3, y="one")]


def test_add_argument_dataclass_type(parser):
    parser.add_argument("--b", type=DataClassB, default=DataClassB(b1=7.0))
    cfg = parser.get_defaults()
    assert Namespace(b1=7.0, b2=Namespace(a1=1, a2="x")) == cfg.b
    init = parser.instantiate(cfg)
    assert isinstance(init.b, DataClassB)
    assert isinstance(init.b.b2, DataClassA)


def test_add_argument_dataclass_unexpected_keys(parser):
    parser.add_argument("--b", type=DataClassB)
    invalid = {
        "class_path": f"{__name__}.DataClassB",
    }
    with pytest.raises(ArgumentError, match="Group 'b' does not accept option 'class_path'"):
        parser.parse_args([f"--b={json.dumps(invalid)}"])


@dataclasses.dataclass
class DataRequiredAttr:
    a1: str
    a2: float = 1.2


def test_add_argument_dataclass_type_required_attr(parser):
    parser.add_argument("--b", type=DataRequiredAttr)
    assert Namespace(a1="v", a2=1.2) == parser.parse_args(["--b.a1=v"]).b
    with pytest.raises(ArgumentError, match=r"the following arguments are required: b\.a1"):
        parser.parse_args([])


@dataclasses.dataclass
class DataInitFalse:
    p1: str = dataclasses.field(init=False)


def test_dataclass_field_init_false(parser):
    added = parser.add_class_arguments(DataInitFalse, "data")
    assert added == []
    assert parser.get_defaults() == Namespace()
    cfg = parser.parse_args([])
    assert cfg == Namespace()
    init = parser.instantiate(cfg)
    assert isinstance(init.data, DataInitFalse)


@dataclasses.dataclass
class NestedDataInitFalse:
    x: bool = dataclasses.field(default=False, init=False)


@dataclasses.dataclass
class ParentDataInitFalse:
    y: NestedDataInitFalse = dataclasses.field(default_factory=NestedDataInitFalse)


def test_nested_dataclass_field_init_false(parser):
    parser.add_class_arguments(ParentDataInitFalse, "data")
    assert parser.get_defaults() == Namespace()
    cfg = parser.parse_args([])
    assert cfg == Namespace()
    init = parser.instantiate(cfg)
    assert isinstance(init.data, ParentDataInitFalse)
    assert isinstance(init.data.y, NestedDataInitFalse)
    assert init.data.y.x is False


@dataclasses.dataclass
class DataFieldFactory:
    a1: List[int] = dataclasses.field(default_factory=lambda: [1, 2, 3])
    a2: Dict[str, float] = dataclasses.field(default_factory=lambda: {"a": 1.2, "b": 3.4})


def test_dataclass_field_default_factory(parser):
    parser.add_class_arguments(DataFieldFactory)
    cfg = parser.get_defaults()
    assert [1, 2, 3] == cfg.a1
    assert {"a": 1.2, "b": 3.4} == cfg.a2


class UntypedClass:
    def __init__(self, c1):
        self.c1 = c1


@dataclasses.dataclass
class DataUntypedAttribute:
    a1: UntypedClass
    a2: str = "a2"
    a3: str = "a3"


def test_dataclass_fail_untyped_false(parser):
    parser.add_argument("--data", type=DataUntypedAttribute, fail_untyped=False)
    class_path = f'"class_path": "{__name__}.UntypedClass"'
    init_args = '"init_args": {"c1": 1}'

    cfg = parser.parse_args(["--data.a1={" + class_path + ", " + init_args + "}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.data, DataUntypedAttribute)
    assert isinstance(init.data.a1, UntypedClass)
    assert isinstance(init.data.a2, str)
    assert isinstance(init.data.a3, str)


@dataclasses.dataclass
class NestedData:
    name: str = "name"


class MainClass:
    def __init__(self, data: NestedData):
        self.data = data


def test_instantiate_dataclass_within_classes(parser):
    parser.add_class_arguments(MainClass, "class")
    cfg = parser.parse_args([])
    assert cfg["class.data.name"] == "name"
    init = parser.instantiate(cfg)
    assert isinstance(init["class"], MainClass)
    assert isinstance(init["class"].data, NestedData)


@dataclasses.dataclass
class RequiredAttr:
    an_int: int


@dataclasses.dataclass
class NestedRequiredAttr:
    b: RequiredAttr


def test_list_nested_dataclass_required_attr(parser):
    parser.add_argument("--a", type=List[NestedRequiredAttr])
    cfg = parser.parse_args(['--a=[{"b": {"an_int": 3}}]'])
    assert cfg == Namespace(a=[Namespace(b=Namespace(an_int=3))])
    init = parser.instantiate(cfg)
    assert isinstance(init.a[0].b, RequiredAttr)
    assert isinstance(init.a[0], NestedRequiredAttr)


@dataclasses.dataclass
class WithAttrDocs:
    attr_str: str = "a"
    "attr_str description"
    attr_int: int = 1
    "attr_int description"


@skip_if_docstring_parser_unavailable
@patch.dict("jsonargparse._optionals._docstring_parse_options")
def test_attribute_docstrings(parser):
    set_parsing_settings(docstring_parse_attribute_docstrings=True)
    parser.add_class_arguments(WithAttrDocs)
    help_str = get_parser_help(parser)
    assert "attr_str description (type: str, default: a)" in help_str
    assert "attr_int description (type: int, default: 1)" in help_str


@dataclasses.dataclass
class Data:
    p1: str
    p2: int = 0


@pytest.fixture
def parser_optional_data() -> ArgumentParser:
    parser = ArgumentParser(exit_on_error=False)
    parser.add_argument("--data", type=Optional[Data])
    return parser


def test_optional_dataclass_help(parser_optional_data):
    help_str = get_parser_help(parser_optional_data)
    assert "--data.help" in help_str
    assert "CLASS_PATH_OR_NAME" not in help_str
    help_str = get_parse_args_stdout(parser_optional_data, ["--data.help"])
    assert "--data.p1" in help_str
    assert "--data.p2" in help_str


def test_optional_dataclass_type_all_fields(parser_optional_data):
    cfg = parser_optional_data.parse_args(['--data={"p1": "x", "p2": 1}'])
    assert cfg == Namespace(data=Namespace(p1="x", p2=1))


def test_optional_dataclass_type_single_field(parser_optional_data):
    cfg = parser_optional_data.parse_args(['--data={"p1": "y"}'])
    assert cfg == Namespace(data=Namespace(p1="y", p2=0))


def test_optional_dataclass_type_invalid_field(parser_optional_data):
    with pytest.raises(ArgumentError, match="Expected a <class 'str'>. Got value: 1"):
        parser_optional_data.parse_args(['--data={"p1": 1}'])


def test_optional_dataclass_type_instantiate(parser_optional_data):
    cfg = parser_optional_data.parse_args(['--data={"p1": "y", "p2": 2}'])
    init = parser_optional_data.instantiate(cfg)
    assert isinstance(init.data, Data)
    assert init.data.p1 == "y"
    assert init.data.p2 == 2


def test_optional_dataclass_type_dump(parser_optional_data):
    cfg = parser_optional_data.parse_args(['--data={"p1": "z"}'])
    assert json_or_yaml_load(parser_optional_data.dump(cfg)) == {"data": {"p1": "z", "p2": 0}}


def test_optional_dataclass_type_missing_required_field(parser_optional_data):
    with pytest.raises(ArgumentError):
        parser_optional_data.parse_args(['--data={"p2": 2}'])


def test_optional_dataclass_type_null_value(parser_optional_data):
    cfg = parser_optional_data.parse_args(["--data=null"])
    assert cfg == Namespace(data=None)
    assert cfg == parser_optional_data.instantiate(cfg)


@dataclasses.dataclass
class DataWithOptionalB:
    c: int = 3


@dataclasses.dataclass
class DataWithOptionalA:
    b: Optional[DataWithOptionalB] = dataclasses.field(default_factory=DataWithOptionalB)


def data_with_optional(a: DataWithOptionalA):
    pass  # pragma: no cover


def test_dataclass_with_optional_default(parser):
    parser.add_function_arguments(data_with_optional, "data")
    cfg = parser.parse_args([])
    assert cfg.data == Namespace(a=Namespace(b=Namespace(c=3)))
    init = parser.instantiate(cfg)
    assert init.data.a == DataWithOptionalA()


@dataclasses.dataclass
class SingleParamChange:
    p1: int = 0
    p2: int = 0


def test_optional_dataclass_single_param_change(parser):
    parser.add_argument("--config", action="config")
    parser.add_argument("--data", type=Optional[SingleParamChange])
    config = {"data": {"p1": 1}}
    cfg = parser.parse_args([f"--config={json.dumps(config)}", "--data.p2=2"])
    assert cfg.data == Namespace(p1=1, p2=2)


@dataclasses.dataclass
class ModelConfig:
    data: Optional[Dict[str, Any]] = None


def test_dataclass_optional_dict_attribute(parser):
    parser.add_argument("--model", type=Optional[ModelConfig], default=ModelConfig(data={"A": 1, "B": 2}))
    cfg = parser.parse_args(["--model.data.A=4"])
    assert cfg.model["data"] == {"A": 4, "B": 2}
    init = parser.instantiate(cfg)
    assert init.model == ModelConfig(data={"A": 4, "B": 2})


def test_dataclass_in_union_type(parser):
    parser.add_argument("--union", type=Optional[Union[Data, int]])
    cfg = parser.parse_args(["--union=1"])
    assert cfg == Namespace(union=1)
    assert cfg == parser.instantiate(cfg)
    help_str = get_parser_help(parser)
    assert "--union.help" in help_str
    help_str = get_parse_args_stdout(parser, ["--union.help"])
    assert f"Help for --union.help={__name__}.Data" in help_str


def test_dataclass_in_list_type(parser):
    parser.add_argument("--list", type=List[Data])
    cfg = parser.parse_args(['--list=[{"p1": "a"},{"p1": "b"}]'])
    init = parser.instantiate(cfg)
    assert ["a", "b"] == [d.p1 for d in init.list]
    assert isinstance(init.list[0], Data)
    assert isinstance(init.list[1], Data)


T = TypeVar("T", int, float)


@dataclasses.dataclass
class GenericData(Generic[T]):
    g1: T
    g2: Tuple[T, T]
    g3: Union[str, T]
    g4: Dict[str, Union[T, bool]]


def test_generic_dataclass(parser):
    parser.add_argument("--data", type=GenericData[int])
    help_str = get_parser_help(parser).lower()
    assert "--data.g1 g1          (required, type: int)" in help_str
    assert "--data.g2 [item,...]  (required, type: tuple[int, int])" in help_str
    if sys.version_info < (3, 14):
        assert "--data.g3 g3          (required, type: union[str, int])" in help_str
        assert "--data.g4 g4          (required, type: dict[str, union[int, bool]])" in help_str
    else:
        assert "--data.g3 g3          (required, type: str | int)" in help_str
        assert "--data.g4 g4          (required, type: dict[str, int | bool])" in help_str


@dataclasses.dataclass
class SpecificData:
    y: GenericData[float]


def test_nested_generic_dataclass(parser):
    parser.add_class_arguments(SpecificData, "x")
    help_str = get_parser_help(parser).lower()
    assert "--x.y.g1 g1          (required, type: float)" in help_str
    assert "--x.y.g2 [item,...]  (required, type: tuple[float, float])" in help_str
    if sys.version_info < (3, 14):
        assert "--x.y.g3 g3          (required, type: union[str, float])" in help_str
        assert "--x.y.g4 g4          (required, type: dict[str, union[float, bool]])" in help_str
    else:
        assert "--x.y.g3 g3          (required, type: str | float)" in help_str
        assert "--x.y.g4 g4          (required, type: dict[str, float | bool])" in help_str


V = TypeVar("V")


@dataclasses.dataclass(frozen=True)
class GenericChild(Generic[V]):
    value: V


@dataclasses.dataclass(frozen=True)
class GenericBase(Generic[V]):
    children: tuple[GenericChild[V], ...]


@dataclasses.dataclass(frozen=True)
class GenericSubclass(GenericBase[str]):
    children: tuple[GenericChild[str], ...]


def test_generic_dataclass_subclass(parser):
    parser.add_class_arguments(GenericSubclass, "x")
    cfg = parser.parse_args(['--x.children=[{"value": "a"}, {"value": "b"}]'])
    init = parser.instantiate(cfg)
    assert cfg.x.children == (Namespace(value="a"), Namespace(value="b"))
    assert isinstance(init.x, GenericSubclass)
    assert isinstance(init.x.children[0], GenericChild)
    assert isinstance(init.x.children[1], GenericChild)


@dataclasses.dataclass
class UnionData:
    data_a: int = 1
    data_b: Optional[str] = None


class UnionClass:
    def __init__(self, prm_1: float, prm_2: bool):
        self.prm_1 = prm_1
        self.prm_2 = prm_2


@pytest.mark.parametrize(
    "union_type",
    [
        Union[UnionData, UnionClass],
        Union[UnionClass, UnionData],
    ],
)
def test_class_path_union_mixture_dataclass_and_class(parser, union_type):
    parser.add_argument("--union", type=union_type)

    value = {"class_path": f"{__name__}.UnionData", "init_args": {"data_a": 2, "data_b": "x"}}
    cfg = parser.parse_args([f"--union={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.union, UnionData)
    assert dataclasses.asdict(init.union) == {"data_a": 2, "data_b": "x"}
    assert json_or_yaml_load(parser.dump(cfg))["union"] == value["init_args"]

    value = {"class_path": f"{__name__}.UnionClass", "init_args": {"prm_1": 1.2, "prm_2": False}}
    cfg = parser.parse_args([f"--union={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.union, UnionClass)
    assert init.union.prm_1 == 1.2
    assert json_or_yaml_load(parser.dump(cfg))["union"] == value

    help_str = get_parser_help(parser)
    assert "--union.help" in help_str
    help_str = [x for x in help_str.split("\n") if "help for the given subclass" in x][0]
    assert "UnionData" in help_str
    assert "UnionClass" in help_str
    help_str = get_parse_args_stdout(parser, ["--union.help=UnionData"])
    assert f"Help for --union.help={__name__}.UnionData" in help_str
    help_str = get_parse_args_stdout(parser, ["--union.help=UnionClass"])
    assert f"Help for --union.help={__name__}.UnionClass" in help_str


def test_class_path_union_dataclasses(parser):
    parser.add_argument("--union", type=Union[Data, SingleParamChange, UnionData])

    value = {"class_path": f"{__name__}.UnionData", "init_args": {"data_a": 2, "data_b": "x"}}
    cfg = parser.parse_args([f"--union={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.union, UnionData)
    assert dataclasses.asdict(init.union) == {"data_a": 2, "data_b": "x"}
    assert json_or_yaml_load(parser.dump(cfg))["union"] == value["init_args"]

    value = {"class_path": f"{__name__}.SingleParamChange", "init_args": {"p1": 2}}
    cfg = parser.parse_args([f"--union={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.union, SingleParamChange)
    assert dataclasses.asdict(init.union) == {"p1": 2, "p2": 0}
    assert json_or_yaml_load(parser.dump(cfg))["union"] == {"p1": 2, "p2": 0}

    value = {"class_path": f"{__name__}.Data", "init_args": {"p1": "x"}}
    cfg = parser.parse_args([f"--union={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.union, Data)
    assert dataclasses.asdict(init.union) == {"p1": "x", "p2": 0}
    assert json_or_yaml_load(parser.dump(cfg))["union"] == {"p1": "x", "p2": 0}


@dataclasses.dataclass
class SubA:
    a: int = 2


@dataclasses.dataclass
class SubB:
    b: float = 3.4


@dataclasses.dataclass
class SubAorB:
    a_or_b: Union[SubA, SubB] = dataclasses.field(default_factory=SubA)


def test_union_dataclasses(parser):
    parser.add_class_arguments(SubAorB, "data")

    cfg = parser.parse_args([])
    init = parser.instantiate(cfg)
    assert isinstance(init.data, SubAorB)
    assert isinstance(init.data.a_or_b, SubA)

    cfg = parser.parse_args(["--data.a_or_b.b=4"])
    assert cfg.data.a_or_b == Namespace(b=4.0)
    init = parser.instantiate(cfg)
    assert isinstance(init.data, SubAorB)
    assert isinstance(init.data.a_or_b, SubB)


@dataclasses.dataclass
class File:
    name: str


@dataclasses.dataclass
class FilePath:
    folder: str
    file: File


@dataclasses.dataclass
class PathParent:
    path: Union[FilePath, bool]


def test_deeply_nested_dataclass_in_union(parser):
    parser.add_class_arguments(PathParent, "parent")
    cfg = parser.parse_args(["--parent.path.folder=/tmp", "--parent.path.file.name=data.txt"])
    assert cfg.parent.path == Namespace(folder="/tmp", file=Namespace(name="data.txt"))


if type_alias_type:
    IntOrString = type_alias_type("IntOrString", Union[int, str])

    @dataclasses.dataclass
    class DataClassWithAliasType:
        p1: IntOrString  # type: ignore[valid-type]

    if annotated:

        @dataclasses.dataclass
        class DataClassWithAnnotatedAliasType:
            p1: annotated[IntOrString, 1]  # type: ignore[valid-type]


@pytest.mark.skipif(not type_alias_type, reason="TypeAliasType is required")
class TestTypeAliasType:
    def test_bare_alias_type(self, parser):
        parser.add_argument("--data", type=IntOrString)
        help_str = get_parser_help(parser)
        help_str_lines = [line for line in help_str.split("\n") if "type: IntOrString" in line]
        assert len(help_str_lines) == 1
        assert "--data DATA" in help_str_lines[0]
        cfg = parser.parse_args(["--data=MyString"])
        assert cfg.data == "MyString"
        cfg = parser.parse_args(["--data=3"])
        assert cfg.data == 3

    def test_dataclass_with_alias_type(self, parser):
        parser.add_argument("--data", type=DataClassWithAliasType)
        help_str = get_parser_help(parser)
        help_str_lines = [line for line in help_str.split("\n") if "type: IntOrString" in line]
        assert len(help_str_lines) == 1
        assert "--data.p1 P1" in help_str_lines[0]
        cfg = parser.parse_args(["--data.p1=MyString"])
        assert cfg.data.p1 == "MyString"
        cfg = parser.parse_args(["--data.p1=3"])
        assert cfg.data.p1 == 3

    @pytest.mark.skipif(not annotated, reason="Annotated is required")
    def test_annotated_alias_type(self, parser):
        parser.add_argument("--data", type=annotated[IntOrString, 1])
        help_str = get_parser_help(parser)
        help_str_lines = [line for line in help_str.split("\n") if "type: Annotated[IntOrString, 1]" in line]
        assert len(help_str_lines) == 1
        assert "--data DATA" in help_str_lines[0]
        cfg = parser.parse_args(["--data=MyString"])
        assert cfg.data == "MyString"
        cfg = parser.parse_args(["--data=3"])
        assert cfg.data == 3

    @pytest.mark.skipif(not annotated, reason="Annotated is required")
    def test_dataclass_with_annotated_alias_type(self, parser):
        parser.add_argument("--data", type=DataClassWithAnnotatedAliasType)
        help_str = get_parser_help(parser)
        # The printable field datatype is not uniform across versions.
        help_str_lines = [line for line in help_str.split("\n") if "type:" in line and "IntOrString" in line]
        assert len(help_str_lines) == 1
        assert "--data.p1 P1" in help_str_lines[0]
        cfg = parser.parse_args(["--data.p1=MyString"])
        assert cfg.data.p1 == "MyString"
        cfg = parser.parse_args(["--data.p1=3"])
        assert cfg.data.p1 == 3


@dataclasses.dataclass
class DataMain:
    p1: int = 1


@dataclasses.dataclass
class DataSub(DataMain):
    p2: str = "-"


def test_dataclass_subclasses_disabled(parser):
    parser.add_argument("--data", type=DataMain, default=DataMain(p1=2))

    help_str = get_parser_help(parser)
    assert "--data.help" not in help_str

    config = {"class_path": f"{__name__}.DataSub", "init_args": {"p2": "y"}}
    with pytest.raises(ArgumentError, match="Group 'data' does not accept option 'init_args.p2'"):
        parser.parse_args([f"--data={json.dumps(config)}"])


def test_add_subclass_dataclass_subclasses_disabled(parser):
    with pytest.raises(ValueError, match="Expected .* a subclass type or a tuple of subclass types"):
        parser.add_subclass_arguments(DataMain, "data")


@pytest.mark.parametrize("default", [None, DataMain()])
def test_add_subclass_dataclass_subclasses_enabled(parser, default, enable_subclasses):
    parser.add_subclass_arguments(DataMain, "data", default=default)

    config = {"class_path": f"{__name__}.DataMain", "init_args": {"p1": 2}}
    cfg = parser.parse_args([f"--data={json.dumps(config)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.data, DataMain)
    assert dataclasses.asdict(init.data) == {"p1": 2}
    dump = json_or_yaml_load(parser.dump(cfg))["data"]
    assert dump == {"class_path": f"{__name__}.DataMain", "init_args": {"p1": 2}}

    config = {"class_path": f"{__name__}.DataSub", "init_args": {"p2": "y"}}
    cfg = parser.parse_args([f"--data={json.dumps(config)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.data, DataSub)
    assert dataclasses.asdict(init.data) == {"p1": 1, "p2": "y"}
    dump = json_or_yaml_load(parser.dump(cfg))["data"]
    assert dump == {"class_path": f"{__name__}.DataSub", "init_args": {"p1": 1, "p2": "y"}}


def test_add_argument_dataclass_subclasses_enabled(parser, subtests, enable_subclasses):
    parser.add_argument("--data", type=DataMain, default=DataMain(p1=2))

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "--data.help [CLASS_PATH_OR_NAME]" in help_str
        assert f"{__name__}.DataMain" in help_str
        assert f"{__name__}.DataSub" in help_str

    with subtests.test("defaults"):
        defaults = parser.get_defaults()
        dump = json_or_yaml_load(parser.dump(defaults))["data"]
        assert dump == {"class_path": f"{__name__}.DataMain", "init_args": {"p1": 2}}

    with subtests.test("sub-param"):
        config = {"class_path": f"{__name__}.DataSub", "init_args": {"p2": "y"}}
        cfg = parser.parse_args([f"--data={json.dumps(config)}"])
        init = parser.instantiate(cfg)
        assert isinstance(init.data, DataSub)
        assert dataclasses.asdict(init.data) == {"p1": 2, "p2": "y"}
        dump = json_or_yaml_load(parser.dump(cfg))["data"]
        assert dump == {"class_path": f"{__name__}.DataSub", "init_args": {"p1": 2, "p2": "y"}}

    with subtests.test("sub-default"):
        config = {"class_path": "DataSub", "init_args": {"p1": 4}}
        cfg = parser.parse_args([f"--data={json.dumps(config)}"])
        init = parser.instantiate(cfg)
        assert isinstance(init.data, DataSub)
        assert dataclasses.asdict(init.data) == {"p1": 4, "p2": "-"}

    with subtests.test("mixed params"):
        config = {"class_path": f"{__name__}.DataSub", "init_args": {"p1": 3, "p2": "x"}}
        cfg = parser.parse_args([f"--data={json.dumps(config)}"])
        assert cfg.data == Namespace(class_path=f"{__name__}.DataSub", init_args=Namespace(p1=3, p2="x"))
        assert cfg.data.init_args.p1 == 3
        init = parser.instantiate(cfg)
        assert isinstance(init.data, DataSub)
        assert dataclasses.asdict(init.data) == {"p1": 3, "p2": "x"}

    with subtests.test("empty init_args"):
        config = {"class_path": f"{__name__}.DataSub", "init_args": {}}
        cfg = parser.parse_args([f"--data={json.dumps(config)}"])
        init = parser.instantiate(cfg)
        assert isinstance(init.data, DataSub)
        assert dataclasses.asdict(init.data) == {"p1": 2, "p2": "-"}

    with subtests.test("class_path"):
        cfg = parser.parse_args(["--data=DataSub"])
        init = parser.instantiate(cfg)
        assert isinstance(init.data, DataSub)
        assert dataclasses.asdict(init.data) == {"p1": 2, "p2": "-"}


def test_add_argument_dataclass_single_type_subclasses_enabled(parser, subclass_behavior):
    set_parsing_settings(subclasses_enabled=[DataMain])
    assert "is_pure_dataclass" in subclasses_disabled_selectors

    parser.add_argument("--data", type=DataMain, default=DataMain(p1=2))

    config = {"class_path": f"{__name__}.DataSub", "init_args": {"p2": "y"}}
    cfg = parser.parse_args([f"--data={json.dumps(config)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.data, DataSub)
    assert dataclasses.asdict(init.data) == {"p1": 2, "p2": "y"}
    dump = json_or_yaml_load(parser.dump(cfg))["data"]
    assert dump == {"class_path": f"{__name__}.DataSub", "init_args": {"p1": 2, "p2": "y"}}


def test_add_argument_dataclass_single_type_subclasses_disabled(parser, enable_subclasses):
    set_parsing_settings(subclasses_disabled=[DataMain])
    assert "is_pure_dataclass" not in subclasses_disabled_selectors

    parser.add_argument("--data", type=DataMain, default=DataMain(p1=2))

    config = {"class_path": f"{__name__}.DataSub", "init_args": {"p2": "y"}}
    with pytest.raises(ArgumentError, match="Group 'data' does not accept option 'init_args.p2'"):
        parser.parse_args([f"--data={json.dumps(config)}"])


def test_add_argument_dataclass_subclasses_disabled_function(parser, enable_subclasses):
    def is_data_main(obj):
        return obj is DataMain

    set_parsing_settings(subclasses_disabled=[is_data_main])
    assert "is_pure_dataclass" not in subclasses_disabled_selectors

    parser.add_argument("--data", type=DataMain, default=DataMain(p1=2))

    config = {"class_path": f"{__name__}.DataSub", "init_args": {"p2": "y"}}
    with pytest.raises(ArgumentError, match="Group 'data' does not accept option 'init_args.p2'"):
        parser.parse_args([f"--data={json.dumps(config)}"])


class ParentData:
    def __init__(self, data: DataMain = DataMain(p1=2)):
        self.data = data


def test_dataclass_nested_subclasses_disabled(parser):
    parser.add_argument("--parent", type=ParentData)

    help_str = get_parse_args_stdout(parser, ["--parent.help"])
    assert "--parent.data.help [CLASS_PATH_OR_NAME]" not in help_str

    config = {
        "class_path": f"{__name__}.ParentData",
        "init_args": {
            "data": {
                "class_path": f"{__name__}.DataSub",
                "init_args": {"p1": 3, "p2": "x"},
            }
        },
    }
    with pytest.raises(ArgumentError, match="Group 'data' does not accept option 'init_args.p1'"):
        parser.parse_args([f"--parent={json.dumps(config)}"])


def test_dataclass_nested_subclasses_enabled(parser, enable_subclasses):
    parser.add_argument("--parent", type=ParentData)

    help_str = get_parse_args_stdout(parser, ["--parent.help"])
    assert "--parent.data.help [CLASS_PATH_OR_NAME]" in help_str

    config = {
        "class_path": f"{__name__}.ParentData",
        "init_args": {
            "data": {
                "class_path": f"{__name__}.DataSub",
                "init_args": {"p1": 3, "p2": "x"},
            }
        },
    }

    cfg = parser.parse_args([f"--parent={json.dumps(config)}"])
    assert cfg.parent.init_args.data == Namespace(class_path=f"{__name__}.DataSub", init_args=Namespace(p1=3, p2="x"))

    dump = json_or_yaml_load(parser.dump(cfg))["parent"]
    assert dump["class_path"] == f"{__name__}.ParentData"
    assert dump["init_args"]["data"] == {"class_path": f"{__name__}.DataSub", "init_args": {"p1": 3, "p2": "x"}}

    init = parser.instantiate(cfg)
    assert isinstance(init.parent, ParentData)
    assert isinstance(init.parent.data, DataSub)
    assert dataclasses.asdict(init.parent.data) == {"p1": 3, "p2": "x"}


@dataclasses.dataclass
class Pet:
    name: str


@dataclasses.dataclass
class Cat(Pet):
    meows: int


@dataclasses.dataclass
class SpecialCat(Cat):
    number_of_tails: int


@dataclasses.dataclass
class Dog(Pet):
    barks: float
    friend: Pet


@dataclasses.dataclass
class Person(Pet):
    name: str
    pets: list[Pet]


person = Person(
    name="jt",
    pets=[
        SpecialCat(name="sc", number_of_tails=2, meows=3),
        Dog(name="dog", barks=2, friend=Cat(name="cc", meows=2)),
    ],
)


def test_convert_to_dict_subclasses_disabled():
    person_dict = convert_to_dict(person)
    assert person_dict == {
        "name": "jt",
        "pets": [
            {"name": "sc", "meows": 3, "number_of_tails": 2},
            {
                "name": "dog",
                "barks": 2.0,
                "friend": {"name": "cc", "meows": 2},
            },
        ],
    }


def test_convert_to_dict_subclasses_enabled(enable_subclasses):
    person_dict = convert_to_dict(person)
    assert person_dict == {
        "class_path": f"{__name__}.Person",
        "init_args": {
            "name": "jt",
            "pets": [
                {"class_path": f"{__name__}.SpecialCat", "init_args": {"name": "sc", "meows": 3, "number_of_tails": 2}},
                {
                    "class_path": f"{__name__}.Dog",
                    "init_args": {
                        "name": "dog",
                        "barks": 2.0,
                        "friend": {"class_path": f"{__name__}.Cat", "init_args": {"name": "cc", "meows": 2}},
                    },
                },
            ],
        },
    }
