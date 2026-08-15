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
    get_parse_args_stdout,
    get_parser_help,
    json_or_yaml_load,
    skip_if_docstring_parser_unavailable,
)

if pydantic_support:
    import pydantic

annotated = typing_extensions_import("Annotated")

skip_if_pydantic_v1_on_v2 = pytest.mark.skipif(
    pydantic_support and pydantic is getattr(__import__("pydantic"), "v1", None),
    reason="Not supported for pydantic.v1",
)

skip_if_pydantic_v1 = pytest.mark.skipif(
    pydantic_support < 2 or pydantic is getattr(__import__("pydantic"), "v1", None),
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
