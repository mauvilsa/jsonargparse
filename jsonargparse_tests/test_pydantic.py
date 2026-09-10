from __future__ import annotations

import abc
import dataclasses
import json
import pathlib
from copy import deepcopy
from typing import Dict, List, Literal, Optional, Union
from unittest.mock import patch

import pytest

from jsonargparse import ArgumentError, ArgumentParser, Namespace, set_parsing_settings
from jsonargparse._optionals import (
    docstring_parser_support,
    get_pydantic_path_type,
    pydantic_support,
    pydantic_supports_field_init,
    typing_extensions_import,
)
from jsonargparse._signatures import convert_to_dict
from jsonargparse_tests.conftest import (
    capture_logs,
    get_parse_args_stdout,
    get_parser_help,
    json_or_yaml_dump,
    json_or_yaml_load,
    skip_if_docstring_parser_unavailable,
)

if pydantic_support:
    import pydantic

annotated = typing_extensions_import("Annotated")

pydantic_v1_on_v2 = bool(pydantic_support) and pydantic is getattr(__import__("pydantic"), "v1", None)

skip_if_pydantic_v1_on_v2 = pytest.mark.skipif(pydantic_v1_on_v2, reason="Not supported for pydantic.v1")

skip_if_pydantic_v1 = pytest.mark.skipif(
    pydantic_support < 2 or pydantic_v1_on_v2,
    reason="Not supported for pydantic v1",
)


@pytest.fixture(autouse=True, scope="module")
def missing_pydantic():
    if not pydantic_support:
        pytest.skip("pydantic package is required")


@pytest.fixture
def enable_subclasses(subclass_behavior):
    set_parsing_settings(subclasses_enabled=["is_pydantic_model"])
    yield


@skip_if_pydantic_v1_on_v2
def test_pydantic_secret_str(parser):
    parser.add_argument("--password", type=pydantic.SecretStr)
    cfg = parser.parse_args(["--password=secret"])
    assert isinstance(cfg.password, pydantic.SecretStr)
    assert cfg.password.get_secret_value() == "secret"
    assert "secret" not in parser.dump(cfg)


@skip_if_pydantic_v1_on_v2
def test_pydantic_secret_str_mask_not_parsed(parser):
    parser.add_argument("--password", type=pydantic.SecretStr)
    dumped = parser.dump(parser.parse_args(["--password=secret"]))
    with pytest.raises(ArgumentError, match="Refusing to parse the mask"):
        parser.parse_string(dumped)


if annotated and pydantic_support > 1:

    @pydantic.dataclasses.dataclass(frozen=True)
    class InnerDataClass:
        a2: int = 1

    @pydantic.dataclasses.dataclass(frozen=True)
    class NestedAnnotatedDataClass:
        a1: annotated[InnerDataClass, 1]  # type: ignore[valid-type]

    @pydantic.dataclasses.dataclass(frozen=True)
    class NestedAnnotatedDataClassWithDefault:
        a1: annotated[InnerDataClass, 1] = pydantic.fields.Field(default=InnerDataClass())  # type: ignore[valid-type]

    @pydantic.dataclasses.dataclass(frozen=True)
    class NestedAnnotatedDataClassWithDefaultFactory:
        a1: annotated[InnerDataClass, 1] = pydantic.fields.Field(default_factory=InnerDataClass)  # type: ignore[valid-type]

    class PingTask(pydantic.BaseModel):
        type: Literal["ping"] = "ping"
        attr: str = ""

    class PongTask(pydantic.BaseModel):
        type: Literal["pong"] = "pong"

    PingPongTask = annotated[
        Union[PingTask, PongTask],
        pydantic.Field(discriminator="type"),
    ]

    class PydanticAnnotatedField(pydantic.BaseModel):
        p1: annotated[int, pydantic.Field(default=2, ge=1, le=8)]  # type: ignore[valid-type]


@pytest.mark.skipif(not (annotated and pydantic_support > 1), reason="Annotated is required")
class TestPydantic2Annotated:
    def test_pydantic_nested_annotated_dataclass(self, parser: ArgumentParser):
        parser.add_class_arguments(NestedAnnotatedDataClass, "n")
        cfg = parser.parse_args(["--n", "{}"])
        assert cfg.n == Namespace(a1=Namespace(a2=1))

    def test_pydantic_annotated_nested_annotated_dataclass(self, parser: ArgumentParser):
        parser.add_class_arguments(annotated[NestedAnnotatedDataClass, 1], "n")
        cfg = parser.parse_args(["--n", "{}"])
        assert cfg.n == Namespace(a1=Namespace(a2=1))

    def test_pydantic_annotated_nested_annotated_dataclass_with_default(self, parser: ArgumentParser):
        parser.add_class_arguments(annotated[NestedAnnotatedDataClassWithDefault, 1], "n")
        cfg = parser.parse_args(["--n", "{}"])
        assert cfg.n == Namespace(a1=Namespace(a2=1))

    def test_pydantic_annotated_nested_annotated_dataclass_with_default_factory(self, parser: ArgumentParser):
        parser.add_class_arguments(annotated[NestedAnnotatedDataClassWithDefaultFactory, 1], "n")
        cfg = parser.parse_args(["--n", "{}"])
        assert cfg.n == Namespace(a1=Namespace(a2=1))

    def test_annotated_field(self, parser):
        parser.add_argument("--model", type=PydanticAnnotatedField)
        cfg = parser.parse_args([])
        assert cfg.model.p1 == 2
        with pytest.raises(ArgumentError) as ctx:
            parser.parse_args(["--model.p1=0"])
        ctx.match("model.p1")

    def test_field_union_discriminator_dot_syntax(self, parser):
        parser.add_argument("--model", type=PingPongTask)
        cfg = parser.parse_args(["--model.type=pong"])
        assert cfg.model == Namespace(type="pong")
        init = parser.instantiate(cfg)
        assert isinstance(init.model, PongTask)
        cfg = parser.parse_args(["--model.type=ping", "--model.attr=abc"])
        assert cfg.model == Namespace(type="ping", attr="abc")
        init = parser.instantiate(cfg)
        assert isinstance(init.model, PingTask)


length = "items" if pydantic_support == 1 else "length"

if pydantic_support:

    @pydantic.dataclasses.dataclass
    class PydanticData:
        p1: float = 0.1
        p2: str = "-"

    @pydantic.dataclasses.dataclass
    class PydanticDataNested:
        p3: PydanticData

    if pydantic_supports_field_init:
        from pydantic.dataclasses import dataclass as pydantic_v2_dataclass
        from pydantic.fields import Field as PydanticV2Field

        @pydantic_v2_dataclass
        class PydanticDataFieldInitFalse:
            p1: str = PydanticV2Field("-", init=False)

        @pydantic_v2_dataclass
        class ParentPydanticDataFieldInitFalse:
            y: PydanticDataFieldInitFalse = PydanticV2Field(default_factory=PydanticDataFieldInitFalse)

    @pydantic.dataclasses.dataclass
    class PydanticDataStdlibField:
        p1: str = dataclasses.field(default="-")

    @pydantic.dataclasses.dataclass
    class PydanticDataStdlibFieldWithFactory:
        p1: str = dataclasses.field(default_factory=lambda: "-")

    class PydanticModel(pydantic.BaseModel):
        p1: str
        p2: int = 3

    class PydanticSubModel(PydanticModel):
        p3: float = 0.1

    class PydanticFieldFactory(pydantic.BaseModel):
        p1: List[int] = pydantic.Field(default_factory=lambda: [1, 2])

    class PydanticHelp(pydantic.BaseModel):
        """
        Args:
            p1: p1 help
        """

        p1: str
        p2: int = pydantic.Field(2, description="p2 help")

    class OptionalPydantic:
        def __init__(self, a: Optional[PydanticModel] = None):
            self.a = a  # pragma: no cover

    class NestedModel(pydantic.BaseModel):
        inputs: List[str]
        outputs: List[str]

    class PydanticNestedDict(pydantic.BaseModel):
        nested: Optional[Dict[str, NestedModel]] = None

    class PydanticPaths(pydantic.BaseModel):
        file: pydantic.FilePath
        dir: pydantic.DirectoryPath


def none(x):
    return x


class TestPydanticBasics:
    num_models = 0

    def test_dataclass(self, parser):
        parser.add_argument("--data", type=PydanticData)
        defaults = parser.get_defaults()
        assert Namespace(p1=0.1, p2="-") == defaults.data
        cfg = parser.parse_args(["--data.p1=0.2", "--data.p2=x"])
        assert Namespace(p1=0.2, p2="x") == cfg.data

    def test_basemodel(self, parser):
        parser.add_argument("--model", type=PydanticModel, default=PydanticModel(p1="a"))
        cfg = parser.parse_args(["--model.p2=5"])
        assert Namespace(p1="a", p2=5) == cfg.model

    def test_subclass(self, parser):
        parser.add_argument("--model", type=PydanticSubModel, default=PydanticSubModel(p1="a"))
        cfg = parser.parse_args(["--model.p3=0.2"])
        assert Namespace(p1="a", p2=3, p3=0.2) == cfg.model
        init = parser.instantiate(cfg)
        assert isinstance(init.model, PydanticSubModel)

    def test_field_default_factory(self, parser):
        parser.add_argument("--model", type=PydanticFieldFactory)
        cfg1 = parser.parse_args([])
        cfg2 = parser.parse_args([])
        assert cfg1.model.p1 == [1, 2]
        assert cfg1.model.p1 == cfg2.model.p1
        assert cfg1.model.p1 is not cfg2.model.p1

    def test_field_description(self, parser):
        parser.add_argument("--model", type=PydanticHelp)
        help_str = get_parser_help(parser)
        if docstring_parser_support:
            assert "p1 help (required, type: str)" in help_str
        assert "p2 help (type: int, default: 2)" in help_str

    @pytest.mark.parametrize(
        ["valid_value", "invalid_value", "cast", "type_str"],
        [
            ("abc", "a", none, "constr(min_length=2, max_length=4)"),
            (2, 0, none, "conint(ge=1)"),
            (-1.0, 1.0, none, "confloat(lt=0.0)"),
            ([1], [], none, f"conlist(int, min_{length}=1)"),
            ([], [3, 4], none, f"conlist(int, max_{length}=1)"),
            ([1], "x", list, f"conset(int, min_{length}=1)"),
            ("http://abc.es/", "-", str, "HttpUrl"),
            ("127.0.0.1", "0", str, "IPvAnyAddress"),
        ],
    )
    @skip_if_pydantic_v1_on_v2
    def test_pydantic_types(self, valid_value, invalid_value, cast, type_str, monkeypatch):
        pydantic_type = eval(f"pydantic.{type_str}")
        self.num_models += 1
        Model = pydantic.create_model(f"Model{self.num_models}", param=(pydantic_type, ...))

        parser = ArgumentParser(exit_on_error=False)
        parser.add_argument("--model", type=Model)
        cfg = parser.parse_args([f"--model.param={valid_value}"])
        assert cast(cfg.model.param) == valid_value
        dump = json_or_yaml_load(parser.dump(cfg))
        assert dump == {"model": {"param": valid_value}}
        with pytest.raises(ArgumentError, match='Parser key "model.param"'):
            parser.parse_args([f"--model.param={invalid_value}"])

    @skip_if_pydantic_v1_on_v2
    def test_pydantic_type_as_subtype(self, parser):
        self.num_models += 1
        Model = pydantic.create_model(f"Model{self.num_models}", param=(List[pydantic.HttpUrl], ...))

        parser.add_argument("--model", type=Model)
        cfg = parser.parse_args(['--model.param=["http://abc.es/"]'])
        assert [str(v) for v in cfg.model.param] == ["http://abc.es/"]
        with pytest.raises(ArgumentError, match='Parser key "model.param"'):
            parser.parse_args(["--model.param=[-]"])

    @pytest.mark.skipif(not pydantic_supports_field_init, reason="Field.init is required")
    def test_dataclass_field_init_false(self, parser):
        parser.add_argument("--data", type=PydanticDataFieldInitFalse)
        help_str = get_parser_help(parser)
        assert "--data.p1" not in help_str
        cfg = parser.parse_args([])
        assert cfg == Namespace()

        init = parser.instantiate(cfg)
        assert init.data.p1 == "-"

    @pytest.mark.skipif(not pydantic_supports_field_init, reason="Field.init is required")
    def test_nested_dataclass_field_init_false(self, parser):
        parser.add_class_arguments(ParentPydanticDataFieldInitFalse, "data")
        assert parser.get_defaults() == Namespace()
        cfg = parser.parse_args([])
        assert cfg == Namespace()
        init = parser.instantiate(cfg)
        assert isinstance(init.data, ParentPydanticDataFieldInitFalse)
        assert isinstance(init.data.y, PydanticDataFieldInitFalse)
        assert init.data.y.p1 == "-"

    def test_dataclass_stdlib_field(self, parser):
        parser.add_argument("--data", type=PydanticDataStdlibField)
        cfg = parser.parse_args(["--data", "{}"])
        assert cfg.data == Namespace(p1="-")

    def test_dataclass_stdlib_field_init_with_factory(self, parser):
        parser.add_argument("--data", type=PydanticDataStdlibFieldWithFactory)
        cfg = parser.parse_args(["--data", "{}"])
        assert cfg.data == Namespace(p1="-")

    def test_dataclass_nested(self, parser):
        parser.add_argument("--data", type=PydanticDataNested)
        cfg = parser.parse_args(["--data", '{"p3": {"p1": 1.0}}'])
        assert cfg.data == Namespace(p3=Namespace(p1=1.0, p2="-"))

    def test_optional_pydantic_model(self, parser):
        parser.add_argument("--b", type=OptionalPydantic)
        parser.add_argument("--cfg", action="config")
        cfg = parser.parse_args([f"--b={__name__}.OptionalPydantic"])
        assert cfg.b.class_path == f"{__name__}.OptionalPydantic"
        assert cfg.b.init_args == Namespace(a=None)
        config = {
            "b": {
                "class_path": f"{__name__}.OptionalPydantic",
                "init_args": {"a": {"p1": "x"}},
            }
        }
        cfg = parser.parse_args([f"--cfg={json.dumps(config)}"])
        assert cfg.b.class_path == f"{__name__}.OptionalPydantic"
        assert cfg.b.init_args == Namespace(a=Namespace(p1="x", p2=3))

    def test_nested_dict(self, parser):
        parser.add_argument("--config", action="config")
        parser.add_argument("--model", type=PydanticNestedDict)
        model = {
            "nested": {
                "key": {
                    "inputs": ["a", "b"],
                    "outputs": ["x", "y"],
                }
            }
        }
        cfg = parser.parse_args(["--model", json.dumps(model)])
        assert cfg.model.nested["key"] == Namespace(inputs=["a", "b"], outputs=["x", "y"])
        init = parser.instantiate(cfg)
        assert isinstance(init.model, PydanticNestedDict)
        assert isinstance(init.model.nested["key"], NestedModel)


@skip_if_pydantic_v1
class TestPydanticPathTypes:
    def test_get_pydantic_path_type(self):
        assert get_pydantic_path_type(pydantic.FilePath) == "file"
        assert get_pydantic_path_type(pydantic.DirectoryPath) == "dir"
        assert get_pydantic_path_type(pathlib.Path) is None
        assert get_pydantic_path_type(str) is None

    def test_file_path(self, parser, file_r):
        parser.add_argument("--path", type=pydantic.FilePath)
        cfg = parser.parse_args([f"--path={file_r}"])
        assert cfg.path == pathlib.Path(file_r)
        assert json_or_yaml_load(parser.dump(cfg)) == {"path": file_r}

    def test_file_path_not_exists(self, parser, tmp_cwd):
        parser.add_argument("--path", type=pydantic.FilePath)
        with pytest.raises(ArgumentError, match='Parser key "path"'):
            parser.parse_args(["--path=not_exist"])

    def test_file_path_is_directory(self, parser, tmp_cwd):
        parser.add_argument("--path", type=pydantic.FilePath)
        pathlib.Path("sub_dir").mkdir()
        with pytest.raises(ArgumentError, match='Parser key "path"'):
            parser.parse_args(["--path=sub_dir"])

    def test_directory_path(self, parser, tmp_cwd):
        parser.add_argument("--path", type=pydantic.DirectoryPath)
        pathlib.Path("sub_dir").mkdir()
        cfg = parser.parse_args(["--path=sub_dir"])
        assert cfg.path == pathlib.Path("sub_dir")
        assert json_or_yaml_load(parser.dump(cfg)) == {"path": "sub_dir"}

    def test_directory_path_not_exists(self, parser, tmp_cwd):
        parser.add_argument("--path", type=pydantic.DirectoryPath)
        with pytest.raises(ArgumentError, match='Parser key "path"'):
            parser.parse_args(["--path=not_exist"])

    def test_directory_path_is_file(self, parser, file_r):
        parser.add_argument("--path", type=pydantic.DirectoryPath)
        with pytest.raises(ArgumentError, match='Parser key "path"'):
            parser.parse_args([f"--path={file_r}"])

    def test_optional_file_path(self, parser, file_r):
        parser.add_argument("--path", type=Optional[pydantic.FilePath])
        assert parser.parse_args([f"--path={file_r}"]).path == pathlib.Path(file_r)
        assert parser.parse_args(["--path=null"]).path is None
        with pytest.raises(ArgumentError, match='Parser key "path"'):
            parser.parse_args(["--path=not_exist"])


@skip_if_pydantic_v1_on_v2
def test_pydantic_model_path_fields(parser, file_r):
    parser.add_argument("--model", type=PydanticPaths)
    cfg = parser.parse_args([f"--model.file={file_r}", "--model.dir=."])
    assert cfg.model == Namespace(file=pathlib.Path(file_r), dir=pathlib.Path("."))
    with pytest.raises(ArgumentError, match='Parser key "model.file"'):
        parser.parse_args(["--model.file=not_exist", "--model.dir=."])
    with pytest.raises(ArgumentError, match='Parser key "model.dir"'):
        parser.parse_args([f"--model.file={file_r}", "--model.dir=not_exist"])


if pydantic_support:

    class ModelAttrDocsBase(pydantic.BaseModel):
        """Base model description."""

        p1: str = "-"
        """p1 description"""

    class ModelAttrDocsMid(ModelAttrDocsBase):
        p2: int = 2
        """p2 description"""

    class ModelAttrDocsSub(ModelAttrDocsMid):
        p3: float = 0.3
        """p3 description"""

    class ModelWithoutDocs(pydantic.BaseModel):
        p1: str = "-"


@skip_if_docstring_parser_unavailable
@patch.dict("jsonargparse._optionals._docstring_parse_options")
def test_pydantic_attribute_docstrings_inherited(parser):
    set_parsing_settings(docstring_parse_attribute_docstrings=True)
    parser.add_class_arguments(ModelAttrDocsSub, "s")
    help_str = get_parser_help(parser)
    assert "p1 description (type: str, default: -)" in help_str
    assert "p2 description (type: int, default: 2)" in help_str
    assert "p3 description (type: float, default: 0.3)" in help_str


def test_pydantic_group_description_from_base(parser):
    parser.add_class_arguments(ModelAttrDocsSub, "s")
    help_str = get_parser_help(parser)
    assert "Create a new model by parsing" not in help_str
    if docstring_parser_support:
        assert "Base model description:" in help_str


def test_pydantic_group_description_without_docstrings(parser):
    parser.add_class_arguments(ModelWithoutDocs, "n")
    help_str = get_parser_help(parser)
    assert "Create a new model by parsing" not in help_str
    assert "A base class for creating Pydantic models" not in help_str
    assert f"<class '{__name__}.ModelWithoutDocs'>:" in help_str


if pydantic_support:

    class Pet(pydantic.BaseModel):
        name: str

    class Cat(Pet):
        meows: int

    class SpecialCat(Cat):
        number_of_tails: int

    class Dog(Pet):
        barks: float
        friend: Pet

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

    person_expected_dict = {
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

    person_expected_subclass_dict = {
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


def test_model_argument_subclasses_enabled(parser, subtests, enable_subclasses):
    parser.add_argument("--person", type=Person, default=person)

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "--person.help [CLASS_PATH_OR_NAME]" in help_str
        assert f"{__name__}.Person" in help_str
        help_str = get_parse_args_stdout(parser, ["--person.help"])
        assert f"Help for --person.help={__name__}.Person" in help_str
        assert "--person.pets.help [CLASS_PATH_OR_NAME]" in help_str

    with subtests.test("defaults"):
        defaults = parser.get_defaults()
        dump = json_or_yaml_load(parser.dump(defaults))["person"]
        assert dump == person_expected_subclass_dict

    with subtests.test("sub-param"):
        cfg = parser.parse_args(["--person.pets.name=lucky"])
        init = parser.instantiate(cfg)
        assert isinstance(init.person, Person)
        assert isinstance(init.person.pets[0], SpecialCat)
        assert isinstance(init.person.pets[1], Dog)
        assert init.person.pets[1].name == "lucky"
        dump = json_or_yaml_load(parser.dump(cfg))["person"]
        expected = deepcopy(person_expected_subclass_dict)
        expected["init_args"]["pets"][1]["init_args"]["name"] = "lucky"
        assert dump == expected


@pytest.mark.parametrize("optional", [False, True])
def test_model_argument_symmetry_subclasses_disabled(parser, optional):
    parser.add_argument("--cat", type=Optional[Cat] if optional else Cat)

    value = {"class_path": f"{__name__}.Cat", "init_args": {"name": "cc", "meows": 2}}
    cfg = parser.parse_args([f"--cat={json.dumps(value)}"])
    assert cfg.cat == Namespace(name="cc", meows=2)

    value["class_path"] = f"{__name__}.SpecialCat"
    with pytest.raises(ArgumentError, match="Subclasses are disabled for Cat"):
        parser.parse_args([f"--cat={json.dumps(value)}"])


# abstract models


if pydantic_support:

    class AbstractModel(pydantic.BaseModel, abc.ABC):
        name: str = "n"

        @abc.abstractmethod
        def run(self): ...

    class AbstractModelImpl(AbstractModel):
        extra: int = 1

        def run(self):
            return 1  # pragma: no cover

    class DeclaredAbstractModel(pydantic.BaseModel, abc.ABC):
        name: str = "n"

    class DeclaredAbstractModelImpl(DeclaredAbstractModel):
        extra: int = 1


def test_abstract_model_subclasses_enabled_by_default(parser, subtests):
    parser.add_argument("--model", type=AbstractModel)

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "--model.help [CLASS_PATH_OR_NAME]" in help_str
        assert f"known subclasses: {__name__}.AbstractModelImpl" in help_str

    with subtests.test("subclass class_path"):
        value = {"class_path": f"{__name__}.AbstractModelImpl", "init_args": {"name": "a"}}
        cfg = parser.parse_args([f"--model={json.dumps(value)}"])
        init = parser.instantiate(cfg)
        assert isinstance(init.model, AbstractModelImpl)
        assert init.model.name == "a"

    with subtests.test("own class_path"):
        with pytest.raises(ArgumentError, match="Expected an instantiatable class, but .*AbstractModel is abstract"):
            parser.parse_args([f"--model={__name__}.AbstractModel"])

    with subtests.test("unrelated class_path"):
        with pytest.raises(ArgumentError, match="does not correspond to a subclass of AbstractModel"):
            parser.parse_args(["--model=calendar.Calendar"])


def test_abstract_model_optional_subclasses_enabled_by_default(parser):
    parser.add_argument("--model", type=Optional[AbstractModel])

    value = {"class_path": f"{__name__}.AbstractModelImpl", "init_args": {"extra": 2}}
    cfg = parser.parse_args([f"--model={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.model, AbstractModelImpl)
    assert init.model.extra == 2
    assert parser.parse_args(["--model=null"]).model is None


def test_add_subclass_arguments_abstract_model(parser):
    parser.add_subclass_arguments(AbstractModel, "model")

    cfg = parser.parse_args([f"--model={__name__}.AbstractModelImpl", "--model.extra=4"])
    init = parser.instantiate(cfg)
    assert isinstance(init.model, AbstractModelImpl)
    assert init.model.extra == 4


def test_abstract_model_subclasses_explicitly_disabled(parser, subclass_behavior):
    set_parsing_settings(subclasses_disabled=[AbstractModel])
    parser.add_argument("--model", type=AbstractModel)

    value = {"class_path": f"{__name__}.AbstractModelImpl"}
    with pytest.raises(ArgumentError, match="Subclasses are disabled for AbstractModel"):
        parser.parse_args([f"--model={json.dumps(value)}"])


def test_abc_declared_model_subclasses_enabled_by_default(parser):
    parser.add_argument("--model", type=DeclaredAbstractModel)

    value = {"class_path": f"{__name__}.DeclaredAbstractModelImpl", "init_args": {"extra": 2}}
    cfg = parser.parse_args([f"--model={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.model, DeclaredAbstractModelImpl)
    assert init.model.extra == 2

    cfg = parser.parse_args([f"--model={__name__}.DeclaredAbstractModel"])
    init = parser.instantiate(cfg)
    assert type(init.model) is DeclaredAbstractModel


def test_convert_to_dict_closed_to_subclasses():
    converted = convert_to_dict(person)
    assert converted == person_expected_dict


def test_convert_to_dict_subclasses_enabled(enable_subclasses):
    converted = convert_to_dict(person)
    assert converted == person_expected_subclass_dict


if pydantic_support > 1:

    class AliasByName(pydantic.BaseModel):
        """Both the attribute name and the alias are accepted."""

        model_config = pydantic.ConfigDict(populate_by_name=True)
        attr_name: str = pydantic.Field("", alias="alias_name")

    class AliasOnly(pydantic.BaseModel):
        """Only the alias is accepted."""

        attr_name: str = pydantic.Field("", alias="alias_name")

    class TakesAliasByName:
        def __init__(self, model: AliasByName = AliasByName(alias_name="")):
            self.model = model  # pragma: no cover

    class AliasInner(pydantic.BaseModel):
        a: int = 1

    class AliasVariants(pydantic.BaseModel):
        model_config = pydantic.ConfigDict(populate_by_name=True)
        elems: Optional[List[str]] = pydantic.Field(None, alias="el")
        inner: Optional[AliasInner] = pydantic.Field(None, alias="in_")
        p1: int = pydantic.Field(1, alias="p2")
        p2: int = 2
        nested: AliasByName = pydantic.Field(default_factory=lambda: AliasByName(alias_name=""), alias="nest")


@skip_if_pydantic_v1
def test_pydantic_alias_as_additional_name(parser, subtests):
    parser.add_class_arguments(AliasByName, "m", instantiate=True)

    with subtests.test("parse alias"):
        assert parser.parse_args(["--m.alias_name=abc"]).m == Namespace(attr_name="abc")

    with subtests.test("parse attribute name"):
        assert parser.parse_args(["--m.attr_name=abc"]).m == Namespace(attr_name="abc")

    with subtests.test("parse config"):
        assert parser.parse_string('{"m": {"alias_name": "abc"}}').m == Namespace(attr_name="abc")

    with subtests.test("parse object"):
        assert parser.parse_object({"m": {"alias_name": "abc"}}).m == Namespace(attr_name="abc")

    with subtests.test("instantiate"):
        init = parser.instantiate(parser.parse_args(["--m.alias_name=abc"]))
        assert isinstance(init.m, AliasByName)
        assert init.m.attr_name == "abc"

    with subtests.test("dump uses the attribute name"):
        dump = json_or_yaml_load(parser.dump(parser.parse_args(["--m.alias_name=abc"])))
        assert dump == {"m": {"attr_name": "abc"}}

    with subtests.test("help shows both names"):
        help_str = get_parser_help(parser)
        assert "--m.attr_name" in help_str
        assert "--m.alias_name" in help_str


@skip_if_pydantic_v1
def test_pydantic_alias_env_vars(subtests):
    parser = ArgumentParser(exit_on_error=False, env_prefix="APP", default_env=True)
    parser.add_class_arguments(AliasByName, "m")

    with subtests.test("attribute name"):
        assert parser.parse_env({"APP_M__ATTR_NAME": "abc"}).m == Namespace(attr_name="abc")

    with subtests.test("alias has no env var"):
        assert parser.parse_env({"APP_M__ALIAS_NAME": "abc"}).m == Namespace(attr_name="")


@skip_if_pydantic_v1
def test_pydantic_alias_in_signature_parameter(parser, subtests):
    parser.add_class_arguments(TakesAliasByName, "r")
    parser.add_argument("--cls", type=TakesAliasByName)

    with subtests.test("class arguments"):
        assert parser.parse_args(["--r.model.alias_name=abc"]).r.model == Namespace(attr_name="abc")

    with subtests.test("subclass init args"):
        value = {"class_path": f"{__name__}.TakesAliasByName", "init_args": {"model": {"alias_name": "abc"}}}
        cfg = parser.parse_args([f"--cls={json.dumps(value)}"])
        assert cfg.cls.init_args.model == Namespace(attr_name="abc")


@skip_if_pydantic_v1
def test_pydantic_alias_replaces_name(parser, subtests):
    parser.add_class_arguments(AliasOnly, "m", instantiate=True)

    with subtests.test("parse alias"):
        assert parser.parse_args(["--m.alias_name=abc"]).m == Namespace(alias_name="abc")

    with subtests.test("attribute name not accepted"):
        with pytest.raises(ArgumentError, match="unrecognized arguments: --m.attr_name=abc"):
            parser.parse_args(["--m.attr_name=abc"])

    with subtests.test("instantiate"):
        init = parser.instantiate(parser.parse_args(["--m.alias_name=abc"]))
        assert isinstance(init.m, AliasOnly)
        assert init.m.attr_name == "abc"


@skip_if_pydantic_v1
def test_pydantic_validation_alias(parser, subtests):
    Model = pydantic.create_model(
        "ModelValidationAlias",
        __config__=pydantic.ConfigDict(populate_by_name=True),
        p1=(str, pydantic.Field("", validation_alias="v1")),
        p2=(str, pydantic.Field("", validation_alias=pydantic.AliasChoices("c1", "c2"))),
    )
    parser.add_class_arguments(Model, "m")

    with subtests.test("validation_alias string"):
        assert parser.parse_args(["--m.v1=x"]).m.p1 == "x"
        assert parser.parse_args(["--m.p1=x"]).m.p1 == "x"

    with subtests.test("validation_alias AliasChoices"):
        for option in ["--m.c1=x", "--m.c2=x", "--m.p2=x"]:
            assert parser.parse_args([option]).m.p2 == "x"


@skip_if_pydantic_v1
def test_pydantic_validate_by_alias_false(parser):
    Model = pydantic.create_model(
        "ModelValidateByAliasFalse",
        __config__=pydantic.ConfigDict(validate_by_name=True, validate_by_alias=False),
        p1=(str, pydantic.Field("", alias="a1")),
    )
    parser.add_class_arguments(Model, "m")
    assert parser.parse_args(["--m.p1=x"]).m == Namespace(p1="x")
    with pytest.raises(ArgumentError, match="unrecognized arguments: --m.a1=x"):
        parser.parse_args(["--m.a1=x"])


@skip_if_pydantic_v1
def test_pydantic_dataclass_alias_as_additional_name(parser):
    @pydantic.dataclasses.dataclass(config=pydantic.ConfigDict(populate_by_name=True))
    class DataAliasByName:
        attr_name: str = pydantic.Field("", alias="alias_name")

    parser.add_class_arguments(DataAliasByName, "d", instantiate=True)
    cfg = parser.parse_args(["--d.alias_name=abc"])
    assert cfg.d == Namespace(attr_name="abc")
    assert parser.instantiate(cfg).d.attr_name == "abc"


@skip_if_pydantic_v1
def test_pydantic_dataclass_alias_replaces_name(parser):
    @pydantic.dataclasses.dataclass
    class DataAliasOnly:
        attr_name: str = pydantic.Field("", alias="alias_name")

    parser.add_class_arguments(DataAliasOnly, "d", instantiate=True)
    cfg = parser.parse_args(["--d.alias_name=abc"])
    assert cfg.d == Namespace(alias_name="abc")
    assert parser.instantiate(cfg).d.attr_name == "abc"


@skip_if_pydantic_v1
def test_pydantic_alias_variants(parser, subtests):
    parser.add_class_arguments(AliasVariants, "m", sub_configs=True)

    with subtests.test("append to a list through the alias"):
        cfg = parser.parse_args(['--m.el=["a"]', "--m.el+=b"])
        assert cfg.m.elems == ["a", "b"]

    with subtests.test("nested arg through the alias"):
        cfg = parser.parse_args(["--m.in_.a=3"])
        assert cfg.m.inner == Namespace(a=3)

    with subtests.test("alias equal to another field name is skipped"):
        cfg = parser.parse_args(["--m.p2=7"])
        assert cfg.m.p1 == 1
        assert cfg.m.p2 == 7


@skip_if_pydantic_v1
def test_pydantic_alias_of_group_field_skipped(parser, logger):
    parser.logger = logger
    with capture_logs(logger) as logs:
        parser.add_class_arguments(AliasVariants, "m", sub_configs=True)
    assert 'Skipping aliases of parameter "nested"' in logs.getvalue()
    assert "not supported for subclasses-disabled types added as a group" in logs.getvalue()

    with capture_logs(logger) as logs:
        cfg = parser.parse_args(["--m.nested.alias_name=abc"])
    assert cfg.m.nested == Namespace(attr_name="abc")
    assert "Parsed command line arguments" in logs.getvalue()

    with capture_logs(logger) as logs:
        with pytest.raises(ArgumentError, match="unrecognized arguments: --m.nest.alias_name=abc"):
            parser.parse_args(["--m.nest.alias_name=abc"])
    assert "unrecognized arguments: --m.nest.alias_name=abc" in logs.getvalue()


@skip_if_pydantic_v1
def test_pydantic_alias_conflicting_with_added_argument_skipped(parser, logger):
    parser.logger = logger
    parser.add_argument("--m.el", type=int, default=0)
    with capture_logs(logger) as logs:
        parser.add_class_arguments(AliasVariants, "m", sub_configs=True)
    assert 'Skipping aliases of parameter "elems"' in logs.getvalue()
    assert "conflicts with an already added argument" in logs.getvalue()

    with capture_logs(logger) as logs:
        cfg = parser.parse_args(["--m.el=3"])
    assert cfg.m.el == 3
    assert "Parsed command line arguments" in logs.getvalue()


if pydantic_support:

    class PydanticExtraAllow(pydantic.BaseModel, extra="allow"):  # type: ignore[call-arg]
        p1: str
        p2: int = 3

    class PydanticExtraIgnore(pydantic.BaseModel, extra="ignore"):  # type: ignore[call-arg]
        p1: str
        p2: int = 3

    class PydanticExtraForbid(pydantic.BaseModel, extra="forbid"):  # type: ignore[call-arg]
        p1: str

    class RequiresExtraAllow:
        def __init__(self, model: PydanticExtraAllow):
            self.model = model

    class PydanticNestedExtraAllow(pydantic.BaseModel, extra="allow"):  # type: ignore[call-arg]
        nested: PydanticModel = PydanticModel(p1="a")

    class PydanticNestingExtraAllow(pydantic.BaseModel):
        nested: PydanticExtraAllow = PydanticExtraAllow(p1="a")


def test_pydantic_extra_allow_group_argument(parser):
    parser.add_argument("--model", type=PydanticExtraAllow, default=PydanticExtraAllow(p1="a"))
    cfg = parser.parse_object({"model": {"p1": "x", "p3": "y"}})
    assert cfg.model == Namespace(p1="x", p2=3, p3="y")
    init = parser.instantiate(cfg)
    assert isinstance(init.model, PydanticExtraAllow)
    assert init.model.p3 == "y"
    assert json_or_yaml_load(parser.dump(cfg))["model"] == {"p1": "x", "p2": 3, "p3": "y"}


def test_pydantic_extra_allow_add_class_arguments(parser, subtests):
    parser.add_class_arguments(PydanticExtraAllow, "model")

    with subtests.test("value with extras"):
        cfg = parser.parse_args(['--model={"p1": "x", "p3": {"a": 1}}'])
        assert cfg.model == Namespace(p1="x", p2=3, p3={"a": 1})
        init = parser.instantiate(cfg)
        assert init.model.p3 == {"a": 1}

    with subtests.test("extras not added as options"):
        with pytest.raises(ArgumentError, match="unrecognized arguments: --model.p3=y"):
            parser.parse_args(["--model.p1=x", "--model.p3=y"])


def test_pydantic_extra_allow_optional_model(parser):
    parser.add_argument("--model", type=Optional[PydanticExtraAllow])
    cfg = parser.parse_args(['--model={"p1": "x"}', "--model.p3=y"])
    assert cfg.model == Namespace(p1="x", p2=3, p3="y")
    init = parser.instantiate(cfg)
    assert isinstance(init.model, PydanticExtraAllow)
    assert init.model.p3 == "y"


def test_pydantic_extra_allow_nested_in_class(parser):
    parser.add_class_arguments(RequiresExtraAllow, "cls")
    cfg = parser.parse_args(['--cls.model={"p1": "x", "p3": [1, 2]}'])
    assert cfg.cls.model == Namespace(p1="x", p2=3, p3=[1, 2])
    init = parser.instantiate(cfg)
    assert init.cls.model.p3 == [1, 2]


def test_pydantic_extra_allow_in_subclass_init_args(parser):
    parser.add_argument("--cls", type=RequiresExtraAllow)
    value = {"class_path": f"{__name__}.RequiresExtraAllow", "init_args": {"model": {"p1": "x", "p3": "y"}}}
    cfg = parser.parse_args([f"--cls={json.dumps(value)}"])
    assert cfg.cls.init_args.model == Namespace(p1="x", p2=3, p3="y")
    init = parser.instantiate(cfg)
    assert init.cls.model.p3 == "y"


def test_pydantic_extra_ignore_group_argument(parser):
    parser.add_argument("--model", type=PydanticExtraIgnore, default=PydanticExtraIgnore(p1="a"))
    cfg = parser.parse_object({"model": {"p1": "x", "p3": "y"}})
    assert cfg.model == Namespace(p1="x", p2=3, p3="y")
    init = parser.instantiate(cfg)
    assert isinstance(init.model, PydanticExtraIgnore)
    assert not hasattr(init.model, "p3")
    assert json_or_yaml_load(parser.dump(cfg))["model"] == {"p1": "x", "p2": 3, "p3": "y"}


def test_pydantic_extra_not_accepted(subtests):
    for model in [PydanticExtraForbid, PydanticModel]:
        with subtests.test(model.__name__):
            parser = ArgumentParser(exit_on_error=False)
            parser.add_class_arguments(model, "model")
            with pytest.raises(ArgumentError, match="Group 'model' does not accept option 'p3'"):
                parser.parse_object({"model": {"p1": "x", "p3": "y"}})


def test_pydantic_extra_allow_default_with_extras(subtests):
    for name, model_type in [("group", PydanticExtraAllow), ("optional", Optional[PydanticExtraAllow])]:
        with subtests.test(name):
            parser = ArgumentParser(exit_on_error=False)
            parser.add_argument("--model", type=model_type, default=PydanticExtraAllow(p1="a", p3="y"))
            cfg = parser.parse_args([])
            assert cfg.model.p3 == "y"
            assert json_or_yaml_load(parser.dump(cfg))["model"]["p3"] == "y"
            init = parser.instantiate(cfg)
            assert init.model.p3 == "y"


def test_pydantic_extra_allow_jsonschema(parser):
    parser.add_argument("--model", type=PydanticExtraAllow)
    parser.add_argument("--ignore", type=PydanticExtraIgnore)
    parser.add_argument("--other", type=PydanticExtraForbid)
    parser.add_argument("--optional", type=Optional[PydanticExtraAllow])
    schema = json.loads(parser.get_completion_script("jsonschema"))
    assert schema["properties"]["model"]["additionalProperties"] is True
    assert schema["properties"]["ignore"]["additionalProperties"] is True
    assert schema["properties"]["other"]["additionalProperties"] is False
    assert schema["$defs"]["PydanticExtraAllow"]["additionalProperties"] is True
    assert schema["additionalProperties"] is False


def test_pydantic_extra_allow_only_direct_fields(parser, subtests):
    parser.add_argument("--outer", type=PydanticNestedExtraAllow)
    parser.add_argument("--inner", type=PydanticNestingExtraAllow)

    with subtests.test("nested model not accepting extras"):
        with pytest.raises(ArgumentError, match="Group 'outer' does not accept option 'nested.p3'"):
            parser.parse_object({"outer": {"nested": {"p3": "y"}}})

    with subtests.test("model accepting extras only nested"):
        with pytest.raises(ArgumentError, match="Group 'inner' does not accept option 'p3'"):
            parser.parse_object({"inner": {"p3": "y"}})
        cfg = parser.parse_object({"inner": {"nested": {"p3": "y"}}})
        assert cfg.inner.nested == Namespace(p1="a", p2=3, p3="y")

    with subtests.test("nested model still parsed as a group"):
        cfg = parser.parse_object({"outer": {"nested": {"p1": "x"}, "p3": {"a": 1}}})
        assert cfg.outer == Namespace(nested=Namespace(p1="x", p2=3), p3={"a": 1})
        init = parser.instantiate(cfg)
        assert isinstance(init.outer.nested, PydanticModel)
        assert init.outer.p3 == {"a": 1}


def test_pydantic_extra_allow_config_file(parser, tmp_cwd):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--model", type=PydanticExtraAllow)
    pathlib.Path("config.yaml").write_text(json_or_yaml_dump({"model": {"p1": "x", "p3": "y"}}))
    cfg = parser.parse_args(["--cfg=config.yaml"])
    assert cfg.model == Namespace(p1="x", p2=3, p3="y")
    assert parser.instantiate(cfg).model.p3 == "y"


def test_pydantic_extra_allow_in_subcommand(parser, subparser):
    subparser.add_argument("--model", type=PydanticExtraAllow)
    parser.add_subcommands().add_subcommand("fit", subparser)
    cfg = parser.parse_args(["fit", '--model={"p1": "x", "p3": "y"}'])
    assert cfg.fit.model == Namespace(p1="x", p2=3, p3="y")
    assert parser.instantiate(cfg).fit.model.p3 == "y"
    with pytest.raises(ArgumentError, match="Subcommand 'fit' does not accept option 'p3'"):
        parser.parse_object({"fit": {"p3": "y"}})
