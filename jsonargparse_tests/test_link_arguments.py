from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Optional, Union

import pytest

from jsonargparse import (
    ArgumentError,
    ArgumentParser,
    Namespace,
    add_instantiator,
    lazy_instance,
)
from jsonargparse._optionals import docstring_parser_support
from jsonargparse_tests.conftest import get_parse_args_stdout, get_parser_help, json_or_yaml_dump, json_or_yaml_load

# tests for links applied on parse


def test_on_parse_help_target_lacking_type_and_help(parser):
    parser.add_argument("--a")
    parser.add_argument("--b")
    parser.link_arguments("a", "b")
    help_str = get_parser_help(parser)
    assert "Target 'b' lacks type and help" in help_str


def test_on_parse_shallow_print_config(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=str)
    parser.link_arguments("a", "b")
    out = get_parse_args_stdout(parser, ["--print_config"])
    assert json_or_yaml_load(out) == {"a": 0}


def _to_str_empty_error(value):
    if not value:
        raise ValueError("value is empty")
    return str(value)  # pragma: no cover


def test_on_parse_subcommand_failing_compute_fn(parser, subparser, subtests):
    subparser.add_argument("--a", type=int, default=0)
    subparser.add_argument("--b", type=str)
    subparser.link_arguments("a", "b", _to_str_empty_error)
    subparser.add_argument("--config", action="config")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("sub", subparser)

    with subtests.test("parse_args"):
        with pytest.raises(ArgumentError) as ctx:
            parser.parse_args(["sub"])
        ctx.match("Call to compute_fn of link '_to_str_empty_error.*failed: value is empty")

    with subtests.test("print_config"):
        out = get_parse_args_stdout(parser, ["sub", "--print_config"])
        assert json_or_yaml_load(out) == {"a": 0}


def test_on_parse_compute_fn_single_arguments(parser, subtests):
    def a_prod(a):
        return a["v1"] * a["v2"]

    parser.add_argument("--a.v1", default=2)
    parser.add_argument("--a.v2", type=int, default=3)
    parser.add_argument("--b.v2", type=int, default=4)
    parser.link_arguments("a", "b.v2", a_prod)

    with subtests.test("parse_args"):
        cfg = parser.parse_args(["--a.v2=-5"])
        assert cfg.b.v2 == cfg.a.v1 * cfg.a.v2

    with subtests.test("dump removal of target"):
        dump = json_or_yaml_load(parser.dump(cfg))
        assert dump == {"a": {"v1": 2, "v2": -5}}

    with subtests.test("dump keep target"):
        dump = json_or_yaml_load(parser.dump(cfg, skip_link_targets=False))
        assert dump == {"a": {"v1": 2, "v2": -5}, "b": {"v2": -10}}

    with subtests.test("invalid compute_fn result type"):
        with pytest.raises(ArgumentError) as ctx:
            parser.parse_args(["--a.v1=x"])
        ctx.match('Parser key "b.v2"')


class BaseC:
    def __init__(self, p: int = 0):
        self.p = p


class SubC(BaseC):
    pass


def test_on_parse_compute_fn_subclass_spec(parser, subtests):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--obj1", type=BaseC, default=lazy_instance(SubC))
    parser.add_argument("--obj2", type=BaseC, default=lazy_instance(BaseC))
    parser.link_arguments(
        "obj1",
        "obj2.init_args.p",
        compute_fn=lambda c: c.init_args.p + 1,
    )

    with subtests.test("from config and default init_args"):
        cfg = parser.parse_args(['--cfg={"obj1": "BaseC"}'])
        assert cfg.obj1.init_args.p == 0
        assert cfg.obj2.init_args.p == 1

    with subtests.test("from given init_args"):
        cfg = parser.parse_args(["--obj1.init_args.p=2"])
        assert cfg.obj1.init_args.p == 2
        assert cfg.obj2.init_args.p == 3

    with subtests.test("invalid init parameter"):
        parser.set_defaults(obj1=None)
        with pytest.raises(ArgumentError, match='Parser key "obj1"'):
            parser.parse_args(["--obj1.p=-"])


class ClassA:
    def __init__(self, v1: int = 2, v2: int = 3):
        pass  # pragma: no cover


class ClassB:
    def __init__(self, v1: int = -1, v2: int = 4, v3: int = 2):
        pass  # pragma: no cover


def _parser_classes_links_on_parse():
    def add(*args):
        return sum(args)

    parser = ArgumentParser(exit_on_error=False)
    parser.add_class_arguments(ClassA, "a")
    parser.add_class_arguments(ClassB, "b")
    parser.link_arguments("a.v2", "b.v1")
    parser.link_arguments(("a.v1", "a.v2"), "b.v2", add)
    return parser


def test_on_parse_add_class_arguments(subtests):
    parser = _parser_classes_links_on_parse()

    with subtests.test("without defaults"):
        with pytest.raises(ArgumentError) as ctx:
            parser.parse_args([], defaults=False)
        ctx.match('Key "a.v2" not found')

    with subtests.test("no arguments"):
        cfg = parser.parse_args([])
        assert cfg.b.v1 == cfg.a.v2
        assert cfg.b.v2 == cfg.a.v1 + cfg.a.v2

    with subtests.test("dump removal of targets"):
        cfg = parser.parse_args(["--a.v1=11", "--a.v2=7"])
        assert 7 == cfg.b.v1
        assert 11 + 7 == cfg.b.v2
        dump = json_or_yaml_load(parser.dump(cfg))
        assert dump == {"a": {"v1": 11, "v2": 7}, "b": {"v3": 2}}

    with subtests.test("dump keep targets"):
        cfg = parser.parse_args(["--a.v1=11", "--a.v2=7"])
        dump = json_or_yaml_load(parser.dump(cfg, skip_link_targets=False))
        assert dump == {"a": {"v1": 11, "v2": 7}, "b": {"v3": 2, "v1": 7, "v2": 18}}

    with subtests.test("argument error"):
        pytest.raises(ArgumentError, lambda: parser.parse_args(["--b.v1=5"]))


class ClassS1:
    def __init__(
        self,
        v1: Union[int, str] = 1,
        v2: Union[int, str] = 2,
    ):
        pass  # pragma: no cover


class ClassS2:
    def __init__(self, v3: int):
        self.v3 = v3  # pragma: no cover


def test_on_parse_add_subclass_arguments(parser, subtests):
    def add(v1, v2):
        return v1 + v2

    parser.add_subclass_arguments(ClassS1, "s1")
    parser.add_subclass_arguments(ClassS2, "s2")
    parser.link_arguments(("s1.init_args.v1", "s1.init_args.v2"), "s2.init_args.v3", add)

    s1_value = {
        "class_path": f"{__name__}.ClassS1",
        "init_args": {"v2": 3},
    }

    with subtests.test("compute_fn result"):
        cfg = parser.parse_args([f"--s1={json.dumps(s1_value)}", f"--s2={__name__}.ClassS2"])
        assert cfg.s2.init_args.v3 == 4
        assert cfg.s2.init_args.v3 == cfg.s1.init_args.v1 + cfg.s1.init_args.v2

    with subtests.test("dump removal of target"):
        cfg = parser.parse_args([f"--s1={json.dumps(s1_value)}", f"--s2={__name__}.ClassS2"])
        dump = json_or_yaml_load(parser.dump(cfg))
        assert dump["s2"] == {"class_path": f"{__name__}.ClassS2"}

    with subtests.test("dump keep target"):
        dump = json_or_yaml_load(parser.dump(cfg, skip_link_targets=False))
        assert dump["s2"] == {"class_path": f"{__name__}.ClassS2", "init_args": {"v3": 4}}

    with subtests.test("compute_fn invalid result type"):
        s1_value["init_args"] = {"v1": "a", "v2": "b"}
        with pytest.raises(ArgumentError):
            parser.parse_args([f"--s1={s1_value}", f"--s2={__name__}.ClassS2"])


class Logger:
    def __init__(self, save_dir: Optional[str] = None):
        pass  # pragma: no cover


class TrainerLoggerUnion:
    def __init__(
        self,
        save_dir: Optional[str] = None,
        logger: Union[bool, Logger] = False,
    ):
        pass  # pragma: no cover


def test_on_parse_subclass_target_in_union(parser):
    parser.add_class_arguments(TrainerLoggerUnion, "trainer")
    parser.link_arguments("trainer.save_dir", "trainer.logger.init_args.save_dir")
    cfg = parser.parse_args([])
    assert cfg.trainer == Namespace(logger=False, save_dir=None)
    cfg = parser.parse_args(["--trainer.save_dir=logs", "--trainer.logger=Logger"])
    assert cfg.trainer.save_dir == "logs"
    assert cfg.trainer.logger.init_args == Namespace(save_dir="logs")


class TrainerLoggerList:
    def __init__(
        self,
        save_dir: Optional[str] = None,
        logger: List[Logger] = [],
    ):
        pass  # pragma: no cover


def test_on_parse_subclass_target_in_list(parser):
    parser.add_class_arguments(TrainerLoggerList, "trainer")
    parser.link_arguments("trainer.save_dir", "trainer.logger.init_args.save_dir")
    cfg = parser.parse_args([])
    assert cfg.trainer == Namespace(logger=[], save_dir=None)
    cfg = parser.parse_args(["--trainer.save_dir=logs", '--trainer.logger=["Logger"]'])
    assert cfg.trainer.save_dir == "logs"
    assert len(cfg.trainer.logger) == 1
    assert cfg.trainer.logger[0].init_args == Namespace(save_dir="logs")
    cfg = parser.parse_args(["--trainer.save_dir=logs", '--trainer.logger=["Logger", "Logger"]'])
    assert len(cfg.trainer.logger) == 2
    assert all(x.init_args == Namespace(save_dir="logs") for x in cfg.trainer.logger)


class TrainerLoggerUnionList:
    def __init__(
        self,
        save_dir: Optional[str] = None,
        logger: Union[bool, Logger, List[Logger]] = False,
    ):
        pass  # pragma: no cover


def test_on_parse_subclass_target_in_union_list(parser):
    parser.add_class_arguments(TrainerLoggerUnionList, "trainer")
    parser.link_arguments("trainer.save_dir", "trainer.logger.init_args.save_dir")
    cfg = parser.parse_args([])
    assert cfg.trainer == Namespace(logger=False, save_dir=None)
    cfg = parser.parse_args(["--trainer.save_dir=logs", "--trainer.logger=Logger"])
    assert cfg.trainer.save_dir == "logs"
    assert cfg.trainer.logger.init_args == Namespace(save_dir="logs")
    cfg = parser.parse_args(["--trainer.save_dir=logs", '--trainer.logger=["Logger", "Logger"]'])
    assert len(cfg.trainer.logger) == 2
    assert all(x.init_args == Namespace(save_dir="logs") for x in cfg.trainer.logger)


class TrainerLoggerOptionalList:
    def __init__(
        self,
        save_dir: Optional[str] = None,
        logger: Optional[List[Logger]] = None,
    ):
        pass  # pragma: no cover


def test_on_parse_subclass_target_in_optional_list(parser):
    parser.add_class_arguments(TrainerLoggerOptionalList, "trainer")
    parser.link_arguments("trainer.save_dir", "trainer.logger.init_args.save_dir")
    cfg = parser.parse_args([])
    assert cfg.trainer == Namespace(logger=None, save_dir=None)
    cfg = parser.parse_args(["--trainer.save_dir=logs", "--trainer.logger+=Logger"])
    assert cfg.trainer.save_dir == "logs"
    assert cfg.trainer.logger[0].init_args == Namespace(save_dir="logs")
    cfg = parser.parse_args(["--trainer.save_dir=logs", '--trainer.logger=["Logger", "Logger"]'])
    assert len(cfg.trainer.logger) == 2
    assert all(x.init_args == Namespace(save_dir="logs") for x in cfg.trainer.logger)


class ClassF:
    def __init__(
        self,
        v: Union[int, str] = 1,
        c: Optional[BaseC] = None,
    ):
        self.c = c


def test_on_parse_add_subclass_arguments_with_instantiate_false(parser, subtests):
    parser.add_subclass_arguments(ClassF, "f")
    parser.add_subclass_arguments(BaseC, "c", instantiate=False)
    parser.link_arguments("c", "f.init_args.c")

    f_value = {"class_path": f"{__name__}.ClassF"}
    c_value = {
        "class_path": f"{__name__}.BaseC",
        "init_args": {
            "p": 3,
        },
    }

    with subtests.test("parse_args"):
        cfg = parser.parse_args([f"--f={json.dumps(f_value)}", f"--c={json.dumps(c_value)}"])
        assert cfg.c.as_dict() == {
            "class_path": f"{__name__}.BaseC",
            "init_args": {"p": 3},
        }
        assert cfg.c == cfg.f.init_args.c

    with subtests.test("class instantiation"):
        init = parser.instantiate(cfg)
        assert isinstance(init.c, Namespace)
        assert isinstance(init.f, ClassF)
        assert isinstance(init.f.c, BaseC)
        assert init.f.c.p == 3

    with subtests.test("dump removal of target"):
        dump = json_or_yaml_load(parser.dump(cfg))
        assert "c" not in dump["f"]["init_args"]

    with subtests.test("dump keep target"):
        dump = json_or_yaml_load(parser.dump(cfg, skip_link_targets=False))
        assert dump["f"]["init_args"]["c"] == {"class_path": f"{__name__}.BaseC", "init_args": {"p": 3}}


class ClassD:
    def __init__(
        self,
        a1: dict,
        a2: Optional[dict] = None,
        a3: Any = None,
    ):
        """ClassD title"""


def test_on_parse_add_subclass_arguments_compute_fn_return_dict(parser):
    def return_dict(value: dict):
        return value

    parser.add_subclass_arguments(ClassD, "d")
    parser.add_subclass_arguments(BaseC, "c")
    parser.link_arguments("c", "d.init_args.a1", compute_fn=return_dict)
    parser.link_arguments("c", "d.init_args.a2")
    parser.link_arguments("c", "d.init_args.a3")

    d_value = {"class_path": f"{__name__}.ClassD"}
    c_value = {
        "class_path": f"{__name__}.BaseC",
        "init_args": {
            "p": 3,
        },
    }

    cfg = parser.parse_args([f"--d={json.dumps(d_value)}", f"--c={json.dumps(c_value)}"])
    assert cfg.d.init_args.a1 == c_value
    assert cfg.d.init_args.a2 == c_value

    init = parser.instantiate(cfg)
    assert isinstance(init.d, ClassD)
    assert isinstance(init.c, BaseC)


def test_on_parse_add_subclass_help_group_title(parser):
    parser.add_subclass_arguments(ClassF, "f")
    parser.add_subclass_arguments(ClassD, "d")
    help_str = get_parser_help(parser)
    assert f"<class '{__name__}.ClassF'>:" in help_str
    if docstring_parser_support:
        assert "ClassD title:" in help_str


class Foo:
    def __init__(self, a: int):
        self.a = a


def test_on_parse_within_subcommand(parser, subparser):
    subparser.add_class_arguments(Foo, nested_key="foo")
    subparser.add_argument("--b", type=int)
    subparser.link_arguments("b", "foo.a")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("cmd", subparser)

    cfg = parser.parse_args(["cmd", "--b=2"])
    assert cfg["cmd"]["foo"].as_dict() == {"a": 2}

    init = parser.instantiate(cfg)
    assert isinstance(init["cmd"]["foo"], Foo)


class RequiredTargetA:
    def __init__(self, a: int):
        pass  # pragma: no cover


@dataclass
class RequiredTargetB:
    a: int


class RequiredTargetC:
    def __init__(self, b: RequiredTargetB):
        pass  # pragma: no cover


def test_on_parse_save_required_target_subclass_param(parser, tmp_cwd):
    parser.add_class_arguments(RequiredTargetA, "a")
    parser.add_subclass_arguments(RequiredTargetC, "c")
    parser.link_arguments("a.a", "c.init_args.b.a")
    cfg = parser.parse_args(["--a.a=1", f"--c={__name__}.RequiredTargetC"])
    parser.save(cfg, "config.yaml")
    saved = json_or_yaml_load((tmp_cwd / "config.yaml").read_text())
    assert saved == {"a": {"a": 1}, "c": {"class_path": f"{__name__}.RequiredTargetC", "init_args": {}}}


def test_on_parse_save_required_target_entire_dataclass(parser, tmp_cwd):
    parser.add_class_arguments(RequiredTargetA, "a")
    parser.add_subclass_arguments(RequiredTargetC, "c")
    parser.link_arguments("a", "c.init_args.b")
    cfg = parser.parse_args(["--a.a=1", f"--c={__name__}.RequiredTargetC"])
    expected = {"a": {"a": 1}, "c": {"class_path": f"{__name__}.RequiredTargetC"}}
    parser.save(cfg, "config.yaml", multifile=False)
    saved = json_or_yaml_load((tmp_cwd / "config.yaml").read_text())
    assert saved == expected
    (tmp_cwd / "config.yaml").unlink()
    parser.save(cfg, "config.yaml", multifile=True)
    saved = json_or_yaml_load((tmp_cwd / "config.yaml").read_text())
    assert saved == expected


class Optimizer:
    def __init__(self, params: List[int], lr: float):  # pragma: no cover
        self.params = params
        self.lr = lr


class Model:
    def __init__(self, label: str, optimizer: Callable[[List[int]], Optimizer] = lambda p: Optimizer(p, lr=0.01)):
        self.label = label
        self.optimizer = optimizer


def get_model_label(model):
    return model.init_args.label


def test_on_parse_nested_callable(parser):
    parser.add_subclass_arguments(Model, "model")
    parser.add_argument("--data.label", type=str)
    parser.link_arguments("model", "data.label", compute_fn=get_model_label)
    cfg = parser.parse_args([f"--model={__name__}.Model", "--model.label=value"])
    assert cfg.data == Namespace(label="value")
    assert cfg.model.init_args.optimizer.init_args == Namespace(lr=0.01)


def test_on_parse_type_skip_link_targets_dump(parser):
    parser.add_argument("--t1", type=type)
    parser.add_argument("--t2", type=type)
    parser.link_arguments("t1", "t2")

    cfg = parser.parse_args([f"--t1={__name__}.Model"])
    dump = json_or_yaml_load(parser.dump(cfg, skip_link_targets=False))
    assert dump["t2"] == f"{__name__}.Model"


class Field:
    def __init__(self, name: str):
        self.name = name


class Data:
    def __init__(self, param: int = 0, fields: List[Field] = []):
        self.fields = fields


def test_on_parse_list_of_instances_target(parser):
    parser.add_class_arguments(Model, "model")
    parser.add_class_arguments(Data, "data")

    def link_model_to_data_fields(model):
        return [
            {
                "class_path": f"{__name__}.Field",
                "init_args": {"name": "f1"},
            },
            {
                "class_path": f"{__name__}.Field",
                "init_args": {"name": "f2"},
            },
        ]

    parser.link_arguments("model", "data.fields", compute_fn=link_model_to_data_fields, apply_on="parse")

    cfg = parser.parse_args(["--model.label=test"])
    assert cfg.data.fields == [
        Namespace(class_path=f"{__name__}.Field", init_args=Namespace(name="f1")),
        Namespace(class_path=f"{__name__}.Field", init_args=Namespace(name="f2")),
    ]

    init = parser.instantiate(cfg)
    assert isinstance(init.data.fields, list)
    assert len(init.data.fields) == 2
    assert all(isinstance(f, Field) for f in init.data.fields)
    assert [f.name for f in init.data.fields] == ["f1", "f2"]


# tests for links applied on instantiate


class ClassX:
    def __init__(self, x1: int, x2: float = 2.3):
        self.x1 = x1
        self.x2 = x2


class ClassY:
    def __init__(self, y1: float = 4.5, y2: int = 6, y3: str = "7"):
        self.y1 = y1
        self.y2 = y2
        self.y3 = y3


class ClassZ:
    def __init__(self, z1: int = 7, z2: str = "8"):
        self.z1 = z1
        self.z2 = z2


def get_parser_classes_links_on_instantiate():
    parser = ArgumentParser(exit_on_error=False)
    parser.add_class_arguments(ClassX, "x")
    parser.add_class_arguments(ClassY, "y")
    parser.add_class_arguments(ClassZ, "z")
    parser.add_argument("--d", type=int, default=-1)
    parser.link_arguments("y.y2", "x.x1", apply_on="instantiate")
    parser.link_arguments("z.z1", "y.y1", apply_on="instantiate")
    return parser


def get_parser_subclasses_link_on_instantiate():
    def get_y2(obj_y):
        return obj_y.y2

    parser = ArgumentParser(exit_on_error=False)
    parser.add_subclass_arguments(ClassX, "x")
    parser.add_subclass_arguments(ClassY, "y")
    parser.link_arguments("y", "x.init_args.x1", get_y2, apply_on="instantiate")
    return parser


def test_on_instantiate_link_instance_attribute():
    parser = get_parser_classes_links_on_instantiate()
    parser.link_arguments("z.z2", "y.y3", compute_fn=lambda v: f'"{v}"', apply_on="instantiate")
    cfg = parser.parse_args([])
    assert "x1" not in cfg.x
    assert "y3" not in cfg.y
    init = parser.instantiate(cfg)
    assert init.x.x1 == 6
    assert init.y.y3 == '"8"'


def test_on_instantiate_link_all_group_arguments():
    parser = get_parser_classes_links_on_instantiate()
    parser.link_arguments("y.y1", "x.x2", apply_on="instantiate")
    cfg = parser.parse_args([])
    assert "x" not in cfg
    init = parser.instantiate(cfg)
    assert init["x"].x1 == 6
    assert init["x"].x2 == 7
    help_str = get_parser_help(parser)
    assert "Group 'x': All arguments are derived from links" in help_str


class FailingComputeFn1:
    def __init__(self, a: int = 0):
        self.a = a


class FailingComputeFn2:
    def __init__(self, b: str):
        self.b = b  # pragma: no cover


def test_on_instantiate_failing_compute_fn(parser):
    parser.add_class_arguments(FailingComputeFn1, "c1")
    parser.add_class_arguments(FailingComputeFn2, "c2")
    parser.link_arguments("c1.a", "c2.b", compute_fn=_to_str_empty_error, apply_on="instantiate")

    with pytest.raises(ValueError) as ctx:
        cfg = parser.parse_args([])
        parser.instantiate(cfg)
    ctx.match("Call to compute_fn of link '_to_str_empty_error.*failed: value is empty")


def test_on_instantiate_link_from_subclass_with_compute_fn():
    parser = get_parser_subclasses_link_on_instantiate()
    cfg = parser.parse_args(
        [
            f"--x={__name__}.ClassX",
            f"--y={__name__}.ClassY",
        ]
    )
    init = parser.instantiate(cfg)
    assert init.x.x1 == 6


class ClassN:
    def __init__(self, obj: BaseC):
        self.obj = obj  # pragma: no cover


def test_on_parse_and_instantiate_link_entire_instance(parser):
    parser.add_argument("--p", type=int)
    parser.add_class_arguments(ClassN, "n", instantiate=False)
    parser.add_class_arguments(BaseC, "c")
    parser.link_arguments("p", "c.p", apply_on="parse")
    parser.link_arguments("c", "n.obj", apply_on="instantiate")

    cfg = parser.parse_args(["--p=2"])
    assert cfg == Namespace(c=Namespace(p=2), p=2)
    init = parser.instantiate(cfg)
    assert isinstance(init.n, Namespace)
    assert isinstance(init.c, BaseC)
    assert init.c is init.n.obj


class ClassM:
    def __init__(self, objs: List[BaseC]):
        self.objs = objs


def test_on_instantiate_link_multi_source(parser):
    def as_list(*items):
        return [*items]

    parser.add_class_arguments(ClassM, "m")
    parser.add_class_arguments(BaseC, "c.one")
    parser.add_class_arguments(SubC, "c.two")
    parser.link_arguments(("c.one", "c.two"), "m.objs", apply_on="instantiate", compute_fn=as_list)

    cfg = parser.parse_args([])
    assert cfg.as_dict() == {"c": {"one": {"p": 0}, "two": {"p": 0}}}
    init = parser.instantiate(cfg)
    assert isinstance(init.c.one, BaseC)
    assert isinstance(init.c.two, SubC)
    assert init.m.objs == [init.c.one, init.c.two]


class ClassP:
    def __init__(self, p: int = 1):
        self.obj = BaseC(p=p)


class ClassQ:
    def __init__(self, obj: BaseC, q2: int = 2):
        self.obj = obj


def test_on_instantiate_link_object_in_attribute(parser):
    parser.add_class_arguments(ClassP, "p")
    parser.add_class_arguments(ClassQ, "q")
    parser.link_arguments("p.obj", "q.obj", apply_on="instantiate")

    cfg = parser.parse_args(["--p.p=2", "--q.q2=3"])
    assert cfg.p == Namespace(p=2)
    assert cfg.q == Namespace(q2=3)
    init = parser.instantiate(cfg)
    assert init.p.obj is init.q.obj
    assert init.q.obj.p == 2


def test_on_parse_link_entire_subclass(parser):
    parser.add_class_arguments(ClassN, "n")
    parser.add_class_arguments(ClassQ, "q")
    parser.link_arguments("n.obj", "q.obj", apply_on="parse")

    obj = {"class_path": f"{__name__}.BaseC", "init_args": {"p": 4}}
    cfg = parser.parse_args([f"--n.obj={json.dumps(obj)}", "--q.q2=7"])
    assert cfg.n.obj == cfg.q.obj
    assert cfg.q.q2 == 7


class ClassV:
    def __init__(self, v1: int = 1):
        self.v1 = v1


class ClassW:
    def __init__(self, w1: int = 2):
        self.w1 = w1


def test_on_parse_subclass_link_ignored_missing_param(parser, caplog):
    parser.logger = {"level": "DEBUG"}
    parser.logger.handlers = [caplog.handler]

    parser.add_subclass_arguments(ClassV, "v", default=lazy_instance(ClassV))
    parser.add_subclass_arguments(ClassW, "w", default=lazy_instance(ClassW))
    parser.link_arguments("v.init_args.v2", "w.init_args.w1", apply_on="parse")
    parser.link_arguments("v.init_args.v1", "w.init_args.w2", apply_on="parse")

    parser.parse_args([f"--v={__name__}.ClassV", f"--w={__name__}.ClassW"])
    assert "'v.init_args.v2 --> w.init_args.w1' ignored since source" in caplog.text
    assert "'v.init_args.v1 --> w.init_args.w2' ignored since target" in caplog.text


def test_on_instantiate_subclass_link_ignored_missing_param(parser, caplog):
    parser.logger = {"level": "DEBUG"}
    parser.logger.handlers = [caplog.handler]

    parser.add_subclass_arguments(ClassV, "v", default=lazy_instance(ClassV))
    parser.add_subclass_arguments(ClassW, "w", default=lazy_instance(ClassW))
    parser.link_arguments("v.init_args.v2", "w.init_args.w1", apply_on="instantiate")
    parser.link_arguments("v.init_args.v1", "w.init_args.w2", apply_on="instantiate")

    cfg = parser.parse_args([f"--v={__name__}.ClassV", f"--w={__name__}.ClassW"])
    parser.instantiate(cfg)
    assert "'v.init_args.v2 --> w.init_args.w1' ignored since attribute" in caplog.text
    assert "'v.init_args.v1 --> w.init_args.w2' ignored since target" in caplog.text


class SubRequired:
    def __init__(self):
        pass


class RequiredTarget:
    def __init__(
        self,
        a: int,
        b: SubRequired,
    ):
        self.a = a
        self.b = b


class RequiredSource:
    def __init__(self, a: int):
        self.a = a


def test_on_instantiate_add_argument_subclass_required_params(parser):
    parser.add_argument("--cls1", type=RequiredSource)
    parser.add_argument("--cls2", type=RequiredTarget)
    parser.link_arguments("cls1.a", "cls2.init_args.a", apply_on="instantiate")
    cfg = parser.parse_args(["--cls1=RequiredSource", "--cls1.a=1", "--cls2=RequiredTarget", "--cls2.b=SubRequired"])
    init = parser.instantiate(cfg)
    assert isinstance(init.cls1, RequiredSource)
    assert isinstance(init.cls2, RequiredTarget)
    assert isinstance(init.cls2.b, SubRequired)
    assert init.cls2.a == 1


class WithinDeepSource:
    def __init__(self, model_name: str):
        self.output_channels = dict(
            modelA=16,
            modelB=32,
        )[model_name]


class WithinDeepTarget:
    def __init__(self, input_channels: int):
        self.input_channels = input_channels


class WithinDeepModel:
    def __init__(
        self,
        encoder: WithinDeepSource,
        decoder: WithinDeepTarget,
    ):
        self.encoder = encoder
        self.decoder = decoder


within_deep_config = {
    "model": {
        "class_path": f"{__name__}.WithinDeepModel",
        "init_args": {
            "encoder": {
                "class_path": f"{__name__}.WithinDeepSource",
                "init_args": {
                    "model_name": "modelA",
                },
            },
            "decoder": {
                "class_path": f"{__name__}.WithinDeepTarget",
            },
        },
    },
}


def test_on_instantiate_within_deep_subclass(parser, caplog):
    parser.logger = {"level": "DEBUG"}
    parser.logger.handlers = [caplog.handler]

    parser.add_argument("--cfg", action="config")
    parser.add_argument("--model", type=WithinDeepModel)
    parser.link_arguments(
        "model.encoder.output_channels",
        "model.init_args.decoder.init_args.input_channels",
        apply_on="instantiate",
    )

    cfg = parser.parse_args([f"--cfg={json.dumps(within_deep_config)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.model, WithinDeepModel)
    assert isinstance(init.model.encoder, WithinDeepSource)
    assert isinstance(init.model.decoder, WithinDeepTarget)
    assert init.model.decoder.input_channels == 16
    assert "Applied link 'encoder.output_channels --> decoder.init_args.input_channels'" in caplog.text


class WithinDeeperSystem:
    def __init__(self, model: WithinDeepModel):
        self.model = model


within_deeper_config = {
    "system": {
        "class_path": f"{__name__}.WithinDeeperSystem",
        "init_args": within_deep_config,
    },
}


def test_on_instantiate_within_deeper_subclass(parser, caplog):
    parser.logger = {"level": "DEBUG"}
    parser.logger.handlers = [caplog.handler]

    parser.add_argument("--cfg", action="config")
    parser.add_subclass_arguments(WithinDeeperSystem, "system")
    parser.link_arguments(
        "system.model.encoder.output_channels",
        "system.init_args.model.init_args.decoder.init_args.input_channels",
        apply_on="instantiate",
    )

    cfg = parser.parse_args([f"--cfg={json.dumps(within_deeper_config)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.system, WithinDeeperSystem)
    assert isinstance(init.system.model, WithinDeepModel)
    assert isinstance(init.system.model.encoder, WithinDeepSource)
    assert isinstance(init.system.model.decoder, WithinDeepTarget)
    assert init.system.model.decoder.input_channels == 16
    assert "Applied link 'encoder.output_channels --> decoder.init_args.input_channels'" in caplog.text


class SourceA:
    def __init__(self, param_a: str):
        self.attr_a = param_a


class SourceB:
    def __init__(self, param_b: str):
        self.attr_b = param_b


class HierarchyGrandchild:
    def __init__(self, param_grandchild: str):
        self.attr_grandchild = param_grandchild


class HierarchyChild:
    def __init__(self, param_child: str, grandchild: HierarchyGrandchild):
        self.attr_child = param_child
        self.grandchild = grandchild


class HierarchyRoot:
    def __init__(self, child: HierarchyChild):
        self.child = child


def get_source_a_attr(source_a):
    assert isinstance(source_a, SourceA)
    return source_a.attr_a


def test_on_instantiate_targets_share_parent(parser):
    config = {
        "source_a": {
            "param_a": "value a",
        },
        "source_b": {
            "param_b": "value b",
        },
        "root": {
            "child": {
                "class_path": "HierarchyChild",
                "init_args": {
                    "grandchild": {
                        "class_path": "HierarchyGrandchild",
                    },
                },
            },
        },
    }
    parser.add_argument("--config", action="config")
    parser.add_class_arguments(SourceA, "source_a")
    parser.add_class_arguments(SourceB, "source_b")
    parser.add_class_arguments(HierarchyRoot, "root")
    parser.link_arguments(
        "source_a",
        "root.child.init_args.grandchild.init_args.param_grandchild",
        apply_on="instantiate",
        compute_fn=get_source_a_attr,
    )
    parser.link_arguments("source_b.attr_b", "root.child.init_args.param_child", apply_on="instantiate")
    cfg = parser.parse_args([f"--config={json.dumps(config)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.source_a, SourceA)
    assert isinstance(init.source_b, SourceB)
    assert isinstance(init.root, HierarchyRoot)
    assert isinstance(init.root.child, HierarchyChild)
    assert isinstance(init.root.child.grandchild, HierarchyGrandchild)
    assert init.source_a.attr_a == "value a"
    assert init.root.child.grandchild.attr_grandchild is init.source_a.attr_a
    assert init.source_b.attr_b == "value b"
    assert init.root.child.attr_child is init.source_b.attr_b


class Dataloader:
    def __init__(self, batch_size: int = 6):
        self.batch_size = batch_size
        self.num_classes = 7


def custom_instantiator(class_type, *args, applied_instantiation_links: dict, **kwargs):
    init = class_type(*args, **kwargs)
    init.applied_instantiation_links = applied_instantiation_links
    return init


def test_on_instantiate_targets_passed_to_instantiator(parser, clear_instantiators):
    parser.add_argument("--data", type=Dataloader)
    parser.add_argument("--model", type=Model)
    parser.link_arguments(
        "data.num_classes",
        "model.init_args.optimizer.init_args.num_classes",
        apply_on="instantiate",
    )
    add_instantiator(custom_instantiator, Dataloader, subclasses=True)
    add_instantiator(custom_instantiator, Model, subclasses=True)

    cfg = parser.parse_args(["--data=Dataloader", "--model=Model", "--model.label=ok"])
    init = parser.instantiate(cfg)

    assert isinstance(init.data, Dataloader)
    assert init.data.applied_instantiation_links == {}
    assert isinstance(init.model, Model)
    assert callable(init.model.optimizer)
    assert init.model.applied_instantiation_links == {"model.init_args.optimizer.init_args.num_classes": 7}


@dataclass
class DataDep:
    param: int = 1


@dataclass
class DepContainer:
    dep: DataDep
    ref: str = ""


def test_on_instantiate_target_entire_dataclass(parser, tmp_cwd):
    parser.add_class_arguments(DataDep, "data")
    parser.add_class_arguments(DepContainer, "container")
    parser.link_arguments("data", "container.dep", apply_on="instantiate")

    defaults = parser.get_defaults()
    assert defaults == Namespace(data=Namespace(param=1), container=Namespace(ref=""))
    cfg = parser.parse_args(["--data.param=2", "--container.ref=x"])
    assert cfg == Namespace(data=Namespace(param=2), container=Namespace(ref="x"))
    init = parser.instantiate(cfg)
    assert init.data is init.container.dep
    assert init.container.dep.param == 2

    help_str = get_parser_help(parser)
    assert "data --> container.dep [applied on instantiate]" in help_str
    assert "--container.dep" not in help_str


# link creation failures


def test_link_failure_invalid_apply_on(parser):
    parser.add_argument("--a")
    parser.add_argument("--b")
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("a", "b", apply_on="bad")
    ctx.match("apply_on must be 'parse' or 'instantiate'")


def test_on_parse_link_failure_previous_target_as_source(parser):
    parser.add_argument("--a")
    parser.add_argument("--b")
    parser.add_argument("--c")
    parser.link_arguments("a", "b")
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("b", "c")
    ctx.match('Source "b" not allowed')


def test_on_parse_link_failure_previous_source_as_target(parser):
    parser.add_argument("--a")
    parser.add_argument("--b")
    parser.add_argument("--c")
    parser.link_arguments("b", "c")
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("a", "b")
    ctx.match('Target "b" not allowed')


def test_on_parse_link_failure_already_linked():
    parser = _parser_classes_links_on_parse()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("a.v2", "b.v1")
    ctx.match('Target "b.v1" is already a target of another link')


def test_on_parse_link_failure_non_existing_source():
    parser = _parser_classes_links_on_parse()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("x", "b.v3")
    ctx.match('No action for key "x"')


def test_on_parse_link_failure_non_existing_target():
    parser = _parser_classes_links_on_parse()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("a.v1", "x")
    ctx.match('No action for key "x"')


def test_on_parse_link_failure_multi_source_missing_compute_fn():
    parser = _parser_classes_links_on_parse()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments(("a.v1", "a.v2"), "b.v3")
    ctx.match("Multiple source keys requires a compute function")


def test_on_parse_link_failure_invalid_subclass_target(parser):
    parser.add_subclass_arguments(ClassS1, "s")
    parser.add_subclass_arguments(ClassS2, "c")
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("s.init_args.v1", "c.init_args")
    ctx.match('Target key expected to start with "c.init_args."')


def test_on_parse_link_failure_invalid_source_attribute(parser):
    parser.add_class_arguments(ClassP, "p")
    parser.add_class_arguments(ClassQ, "q")
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("p.obj", "q.obj", apply_on="parse")
    ctx.match('key "p.obj"')


def test_on_instantiate_link_failure_cycle_self():
    parser = get_parser_classes_links_on_instantiate()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("y.y2", "y.y3", apply_on="instantiate")
    ctx.match("cycle")


def test_on_instantiate_link_failure_cycle_pair():
    parser = get_parser_classes_links_on_instantiate()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("x.x2", "y.y3", apply_on="instantiate")
    ctx.match("cycle")


def test_on_instantiate_link_failure_cycle_triple():
    parser = get_parser_classes_links_on_instantiate()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("x.x2", "z.z2", apply_on="instantiate")
    ctx.match("cycle")


def test_on_instantiate_link_failure_source_not_class():
    parser = get_parser_classes_links_on_instantiate()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("d", "c.c2", apply_on="instantiate")
    ctx.match("require source")


def test_on_instantiate_link_failure_missing_init_args():
    parser = get_parser_subclasses_link_on_instantiate()
    with pytest.raises(ValueError) as ctx:
        parser.link_arguments("x.y.z", "y.y3", apply_on="instantiate")
    ctx.match('Target key expected to start with "y.init_args."')


# help tests


def test_help_link_on_parse_single_source(parser):
    parser.add_class_arguments(ClassA, "a")
    parser.add_class_arguments(ClassB, "b")
    parser.link_arguments("a.v2", "b.v1")
    help_str = get_parser_help(parser)
    assert "a.v2 --> b.v1 [applied on parse]" in help_str


def test_help_link_on_parse_multi_source(parser):
    parser.add_class_arguments(ClassA, "a")
    parser.add_class_arguments(ClassB, "b")
    parser.link_arguments(("a.v1", "a.v2"), "b.v2", sum)
    help_str = get_parser_help(parser)
    assert "sum(a.v1, a.v2) --> b.v2 [applied on parse]" in help_str


def test_help_link_on_parse_lambda_compute_fn():
    parser = get_parser_classes_links_on_instantiate()
    parser.link_arguments("z.z2", "y.y3", lambda v: v)
    help_str = get_parser_help(parser)
    assert "<lambda>(z.z2) --> y.y3 [applied on parse]" in help_str


def test_help_link_on_instantiate_single_source():
    parser = get_parser_classes_links_on_instantiate()
    help_str = get_parser_help(parser)
    assert "y.y2 --> x.x1 [applied on instantiate]" in help_str


def test_help_link_on_instantiate_multi_source():
    parser = get_parser_subclasses_link_on_instantiate()
    help_str = get_parser_help(parser)
    assert "get_y2(y) --> x.init_args.x1 [applied on instantiate]" in help_str


# other tests


class DeepD:
    pass


class DeepA:
    def __init__(self, d: DeepD) -> None:
        self.d = d


class DeepBSuper:
    pass


class DeepBSub(DeepBSuper):
    def __init__(self, a: DeepA) -> None:
        self.a = a


class DeepC:
    def fn(self) -> DeepD:
        return DeepD()


def test_on_instantiate_linking_deep_targets(parser, tmp_path):
    config = {
        "b": {
            "class_path": f"{__name__}.DeepBSub",
            "init_args": {
                "a": {
                    "class_path": f"{__name__}.DeepA",
                },
            },
        },
        "c": {},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(json_or_yaml_dump(config))

    parser.add_argument("--config", action="config")
    parser.add_subclass_arguments(DeepBSuper, nested_key="b", required=True)
    parser.add_class_arguments(DeepC, nested_key="c")
    parser.link_arguments("c", "b.init_args.a.init_args.d", compute_fn=DeepC.fn, apply_on="instantiate")

    config = parser.parse_args([f"--config={config_path}"])
    config_init = parser.instantiate(config)
    assert isinstance(config_init["b"].a.d, DeepD)


class DeepBSub2(DeepBSuper):
    def __init__(self, a_map: Mapping[str, DeepA]) -> None:
        self.a_map = a_map


def test_on_instantiate_linking_deep_targets_mapping(parser, tmp_path):
    config = {
        "b": {
            "class_path": f"{__name__}.DeepBSub2",
            "init_args": {
                "a_map": {
                    "name": {
                        "class_path": f"{__name__}.DeepA",
                    },
                },
            },
        },
        "c": {},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(json_or_yaml_dump(config))

    parser.add_argument("--config", action="config")
    parser.add_subclass_arguments(DeepBSuper, nested_key="b", required=True)
    parser.add_class_arguments(DeepC, nested_key="c")
    parser.link_arguments(
        "c",
        "b.init_args.a_map.name.init_args.d",
        compute_fn=DeepC.fn,
        apply_on="instantiate",
    )

    config = parser.parse_args([f"--config={config_path}"])
    config_init = parser.instantiate(config)
    assert isinstance(config_init["b"].a_map["name"].d, DeepD)

    config_init = parser.instantiate(config)
    assert isinstance(config_init["b"].a_map["name"].d, DeepD)


def test_on_instantiate_linking_deep_targets_undefined_parent(parser, tmp_path):
    config = {
        "b": {
            "class_path": f"{__name__}.DeepBSuper",
        },
        "c": {},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(json_or_yaml_dump(config))

    parser.add_argument("--config", action="config")
    parser.add_subclass_arguments(DeepBSuper, nested_key="b", required=True)
    parser.add_class_arguments(DeepC, nested_key="c")
    # .init_args.a is undefined in DeepBSuper
    parser.link_arguments("c", "b.init_args.a.init_args.d", compute_fn=DeepC.fn, apply_on="instantiate")

    config = parser.parse_args([f"--config={config_path}"])
    config_init = parser.instantiate(config)
    assert isinstance(config_init["b"], DeepBSuper)


class DeepTarget:
    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b


class Node:
    def __init__(self, sub_class: DeepTarget) -> None:
        self.sub_class = sub_class


class Source:
    def __init__(self) -> None:
        self.a = 1


def test_on_instantiate_linking_deep_targets_multiple(parser):
    parser.add_subclass_arguments(Node, "Node")
    parser.add_class_arguments(Source, "Source")
    parser.link_arguments("Source.a", "Node.init_args.sub_class.init_args.a", apply_on="instantiate")
    parser.link_arguments("Source.a", "Node.init_args.sub_class.init_args.b", apply_on="instantiate")
    cfg = parser.parse_args(["--Node=Node", "--Node.init_args.sub_class=DeepTarget"])
    init = parser.instantiate(cfg)
    assert 1 == init.Node.sub_class.a
    assert 1 == init.Node.sub_class.b
