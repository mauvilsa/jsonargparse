from __future__ import annotations

import json
import os
import textwrap
import warnings
from calendar import Calendar
from copy import deepcopy
from dataclasses import dataclass
from gzip import GzipFile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Union
from unittest.mock import patch
from uuid import NAMESPACE_OID

import pytest

from jsonargparse import (
    ArgumentError,
    ArgumentParser,
    Namespace,
    add_instantiator,
    lazy_instance,
)
from jsonargparse._instantiation import _global_class_instantiators
from jsonargparse._typehints import _cached_class_parsers, implements_protocol, is_instance_or_supports_protocol
from jsonargparse.typing import final
from jsonargparse_tests.conftest import (
    capture_logs,
    get_parse_args_stderr,
    get_parse_args_stdout,
    get_parser_help,
    json_or_yaml_dump,
    json_or_yaml_load,
    source_unavailable,
)


class BaseC:
    def __init__(self, p: int = 0):
        self.p = p


class SubA(BaseC):
    pass


class SubB(BaseC):
    pass


@pytest.mark.parametrize("type", [BaseC, Optional[BaseC]])
def test_subclass_basics(parser, type):
    value = {
        "class_path": f"{__name__}.BaseC",
        "init_args": {"p": 3},
    }
    parser.add_argument("--op", type=type)
    cfg = parser.parse_args([f"--op={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init["op"], BaseC)
    assert 3 == init["op"].p

    init = parser.instantiate(parser.parse_args([]))
    assert init["op"] is None


class BaseClassDefault:
    def __init__(self, param: str = "base_default"):
        self.param = param  # pragma: no cover


class SubClassDefault(BaseClassDefault):
    def __init__(self, param: str = "sub_default"):
        super().__init__(param=param)  # pragma: no cover


def test_subclass_defaults(parser):
    parser.add_subclass_arguments(BaseClassDefault, "cls")
    cfg = parser.parse_args(["--cls=BaseClassDefault"])
    assert cfg.cls.init_args.param == "base_default"
    cfg = parser.parse_args(["--cls=SubClassDefault"])
    assert cfg.cls.init_args.param == "sub_default"


def test_subclass_init_args_in_subcommand(parser, subparser):
    subparser.add_subclass_arguments(BaseC, "obj", default=lazy_instance(BaseC))
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("cmd", subparser)
    cfg = parser.parse_args(["cmd", "--obj.init_args.p=4"])
    assert cfg.cmd.obj.init_args == Namespace(p=4)


def test_subclass_positional(parser):
    parser.add_argument("obj", type=BaseC)

    cfg = parser.parse_args(["SubA"])
    assert cfg.obj.class_path == f"{__name__}.SubA"

    help_str = get_parser_help(parser)
    assert "required, type: <class 'BaseC'>" in help_str
    assert "--obj.help" in help_str


class Instantiate1:
    def __init__(self, a1: Optional[int] = 1, a2: Optional[float] = 2.3):
        self.a1 = a1
        self.a2 = a2


class Instantiate2:
    def __init__(self, c1: Optional[Instantiate1]):
        self.c1 = c1  # pragma: no cover


def test_subclass_within_class_instantiate(parser):
    parser.add_class_arguments(Instantiate2)

    cfg = parser.parse_args(["--c1.class_path=Instantiate1", "--c1.init_args.a1=7"])
    assert cfg.c1.class_path == f"{__name__}.Instantiate1"
    assert cfg.c1.init_args == Namespace(a1=7, a2=2.3)

    init = parser.instantiate(cfg)
    assert isinstance(init.c1, Instantiate1)
    assert 7 == init.c1.a1
    assert 2.3 == init.c1.a2


class SetDefaults:
    def __init__(self, p1: int = 1, p2: str = "x", p3: bool = False):
        pass  # pragma: no cover


def test_subclass_set_defaults(parser):
    parser.add_argument("--data", type=SetDefaults)
    parser.set_defaults({"data": {"class_path": f"{__name__}.SetDefaults"}})
    cfg = parser.parse_args(
        [
            "--data.init_args.p1=2",
            "--data.init_args.p2=y",
            "--data.init_args.p3=true",
        ]
    )
    assert cfg.data.init_args == Namespace(p1=2, p2="y", p3=True)


def test_subclass_optional_list(parser, subtests):
    parser.add_argument("--op", type=Optional[List[BaseC]])
    class_path = f'"class_path": "{__name__}.BaseC"'

    with subtests.test("without init_args"):
        expected = [{"class_path": f"{__name__}.BaseC", "init_args": {"p": 0}}]
        cfg = parser.parse_args(["--op=[{" + class_path + "}]"])
        assert cfg.as_dict()["op"] == expected
        cfg = parser.parse_args([f'--op=["{__name__}.BaseC"]'])
        assert cfg.as_dict()["op"] == expected
        init = parser.instantiate(cfg)
        assert isinstance(init.op[0], BaseC)

    with subtests.test("with init_args"):
        init_args = '"init_args": {"p": 3}'
        cfg = parser.parse_args(["--op=[{" + class_path + ", " + init_args + "}]"])
        assert cfg["op"][0]["init_args"].as_dict() == {"p": 3}
        init = parser.instantiate(cfg)
        assert isinstance(init["op"][0], BaseC)
        assert 3 == init["op"][0].p

    with subtests.test("error"):
        with pytest.raises(ArgumentError, match="Not a valid subclass of BaseC"):
            parser.parse_args(["--op=[1]"])


def test_subclass_union_with_str(parser):
    parser.add_argument("--op", type=Optional[Union[str, BaseC]])
    cfg = parser.parse_args(["--op=value"])
    assert cfg.op == "value"
    cfg = parser.parse_args(
        [
            "--op=SubA",
            "--op.p=1",
            "--op.p=2",
        ]
    )
    assert cfg.op == Namespace(class_path=f"{__name__}.SubA", init_args=Namespace(p=2))


def test_subclass_union_help(parser):
    parser.add_argument("--op", type=Union[str, Mapping[str, int], BaseC])
    help_str = get_parser_help(parser)
    assert "Show the help for the given subclass of BaseC" in help_str
    help_str = get_parse_args_stdout(parser, ["--op.help", "SubA"])
    assert "--op.p" in help_str


class DefaultsDisabled:
    def __init__(self, p1: int = 1, p2: str = "2"):
        pass  # pragma: no cover


def test_subclass_parse_defaults_disabled(parser):
    parser.add_argument("--op", type=DefaultsDisabled)
    cfg = parser.parse_args(["--op.class_path=DefaultsDisabled", "--op.init_args.p1=3"], defaults=False)
    assert cfg.op == Namespace(class_path=f"{__name__}.DefaultsDisabled", init_args=Namespace(p1=3))


def test_subclass_known_subclasses(parser):
    parser.add_argument("--obj", type=BaseC)
    help_str = get_parser_help(parser)
    assert f"known subclasses: {__name__}.BaseC," in help_str


def test_subclass_known_subclasses_ignore_local_class(parser):
    class LocalSubC(BaseC):
        pass

    parser.add_argument("--op", type=BaseC)
    help_str = get_parser_help(parser)
    assert "LocalSubC" not in help_str


def test_subclass_known_subclasses_multiple_bases(parser):
    parser.add_argument("--op", type=Union[BaseC, GzipFile, None])
    help_str = get_parser_help(parser)
    for class_path in [f"{__name__}.BaseC", f"{__name__}.SubA", f"{__name__}.SubB", "gzip.GzipFile"]:
        assert class_path in help_str


class UntypedParams:
    def __init__(self, a1, a2=None):
        self.a1 = a1  # pragma: no cover


def func_subclass_untyped(c1: Union[int, UntypedParams]):
    return c1  # pragma: no cover


def test_subclass_allow_untyped_parameters_help(parser):
    parser.add_function_arguments(func_subclass_untyped, fail_untyped=False)
    help_str = get_parse_args_stdout(parser, [f"--c1.help={__name__}.UntypedParams"])
    assert "--c1.a1 A1" in help_str
    assert "--c1.a2 A2" in help_str


class MergeInitArgs(BaseC):
    def __init__(self, param_a: int = 1, param_b: str = "x", **kwargs):
        super().__init__(**kwargs)  # pragma: no cover


def test_subclass_merge_init_args_global_config(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--obj", type=BaseC)

    config1 = {
        "obj": {
            "class_path": f"{__name__}.MergeInitArgs",
            "init_args": {
                "p": 2,
                "param_b": "y",
            },
        }
    }
    config2 = deepcopy(config1)
    config2["obj"]["init_args"] = {
        "param_a": 2,
        "p": 3,
    }
    expected = deepcopy(config1["obj"])
    expected["init_args"].update(config2["obj"]["init_args"])

    cfg = parser.parse_args([f"--cfg={json.dumps(config1)}", f"--cfg={json.dumps(config2)}"])
    assert cfg.obj.as_dict() == expected


def test_subclass_init_args_without_class_path(parser):
    parser.add_subclass_arguments(BaseC, "obj2", default=lazy_instance(BaseC))
    parser.add_subclass_arguments(BaseC, "obj3", default=lazy_instance(BaseC, p=2))
    cfg = parser.parse_args(["--obj2.init_args.p=4", "--obj3.init_args.p=5"])
    assert cfg.obj2.init_args == Namespace(p=4)
    assert cfg.obj3.init_args == Namespace(p=5)


def test_subclass_init_args_without_class_path_dict(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--obj", type=BaseC)
    config = {"obj": {"class_path": f"{__name__}.SubA", "init_args": {"p": 2}}}

    cfg = parser.parse_args([f"--cfg={json.dumps(config)}", '--obj={"init_args": {"p": 3}}'])
    assert cfg.obj.init_args == Namespace(p=3)

    cfg = parser.parse_args([f"--cfg={json.dumps(config)}", '--obj={"p": 4}'])
    assert cfg.obj.init_args == Namespace(p=4)


class DefaultConfig:
    def __init__(self, obj: Optional[BaseC] = None, val: int = 2):
        self.obj = obj  # pragma: no cover


def test_subclass_with_default_config_files(parser, tmp_cwd, logger, subtests):
    config = {
        "class_path": f"{__name__}.BaseC",
        "init_args": {"p": 3},
    }
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json.dumps({"data": {"obj": config}}))

    parser.default_config_files = [config_path]
    parser.add_argument("--op", default="from default")
    parser.add_class_arguments(DefaultConfig, "data")

    with subtests.test("get_defaults"):
        cfg = parser.get_defaults()
        assert str(config_path) == str(cfg["__default_config__"])
        assert cfg.data.obj.as_dict() == config

    with subtests.test("dump"):
        dump = json_or_yaml_load(parser.dump(cfg))
        assert dump["data"]["obj"] == {"class_path": f"{__name__}.BaseC", "init_args": {"p": 3}}

    with subtests.test("disable defaults"):
        cfg = parser.parse_args([f"--data.obj.class_path={__name__}.BaseC"], defaults=False)
        assert cfg.data.obj == Namespace(class_path=f"{__name__}.BaseC")

    with subtests.test("logging"):
        parser.logger = logger
        with capture_logs(logger) as logs:
            cfg = parser.parse_args([])
        assert str(config_path) in logs.getvalue()
        assert cfg.data.obj.as_dict() == config


class DefaultConfigSubcommands:
    def __init__(self, foo: int):
        self.foo = foo  # pragma: no cover


def test_subclass_in_subcommand_with_global_default_config_file(parser, subparser, tmp_cwd):
    default_path = Path("default.yaml")
    default_path.write_text(json_or_yaml_dump({"fit": {"model": {"foo": 123}}}))

    parser.default_config_files = [default_path]
    parser.add_argument("--config", action="config")
    subcommands = parser.add_subcommands()

    subparser.add_class_arguments(DefaultConfigSubcommands, nested_key="model")
    subcommands.add_subcommand("fit", subparser)

    subparser2 = ArgumentParser()
    subparser2.add_class_arguments(DefaultConfigSubcommands, nested_key="model")
    subcommands.add_subcommand("test", subparser2)

    cfg = parser.parse_args(["fit"])
    assert cfg.fit.model.foo == 123


# function instantiators


class ClassMethodInstantiator:
    def __init__(self, p1: int = 1, p2: bool = False):
        self.p1 = p1
        self.p2 = p2

    @classmethod
    def from_p1(cls, p1: int) -> "ClassMethodInstantiator":
        return ClassMethodInstantiator(p1)


def test_class_method_instantiator(parser):
    parser.add_argument("--cls", type=ClassMethodInstantiator)
    cfg = parser.parse_args([f"--cls={__name__}.ClassMethodInstantiator.from_p1", "--cls.p1=2"])
    assert cfg.cls.class_path == f"{__name__}.ClassMethodInstantiator.from_p1"
    assert cfg.cls.init_args == Namespace(p1=2)
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, ClassMethodInstantiator)
    assert init.cls.p1 == 2
    assert init.cls.p2 is False

    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args([f"--cls={__name__}.ClassMethodInstantiator.from_p1"])
    ctx.match('Parser key "cls"')
    ctx.match("the following arguments are required: p1")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args([f"--cls={__name__}.ClassMethodInstantiator.from_p1", "--cls.p1=2", "--cls.p3=-"])
    ctx.match("Option 'p3' is not accepted")


class FunctionInstantiator:
    def __init__(self, p1: float = 0.0, p2: str = "-"):
        self.p1 = p1
        self.p2 = p2


def function_instantiator(p2: str) -> FunctionInstantiator:
    return FunctionInstantiator(1.0, p2)


def test_function_instantiator(parser):
    parser.add_argument("--cls", type=FunctionInstantiator)
    cfg = parser.parse_args([f"--cls={__name__}.function_instantiator", "--cls.p2=y"])
    assert cfg.cls.class_path == f"{__name__}.function_instantiator"
    assert cfg.cls.init_args == Namespace(p2="y")
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, FunctionInstantiator)
    assert init.cls.p1 == 1.0
    assert init.cls.p2 == "y"

    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args([f"--cls={__name__}.function_instantiator", "--cls.p2=y", "--cls.p3=x"])
    ctx.match("Option 'p3' is not accepted")


def function_undefined_return(p1: int) -> "Undefined":  # type: ignore[name-defined]  # noqa: F821
    return FunctionInstantiator(p1, "x")  # pragma: no cover


def test_instantiator_undefined_return(parser, logger):
    parser.logger = logger
    parser.add_argument("--cls", type=FunctionInstantiator)
    with capture_logs(logger) as logs, pytest.raises(ArgumentError) as ctx:
        parser.parse_args([f"--cls={__name__}.function_undefined_return", "--cls.p1=2"])
    ctx.match("function_undefined_return does not correspond to a subclass of")
    assert "function_undefined_return does not correspond to a subclass of" in logs.getvalue()
    assert "Unable to evaluate types for" in logs.getvalue()


# importable instances


class dtype:
    pass


float32 = dtype()


def test_importable_instances(parser):
    parser.add_argument("--dtype", type=dtype)
    cfg = parser.parse_args([f"--dtype={__name__}.float32"])
    assert cfg.dtype is float32
    dump = json_or_yaml_load(parser.dump(cfg))
    assert dump == {"dtype": f"{__name__}.float32"}


# custom instantiation tests


class CustomInstantiationBase:
    pass


class CustomInstantiationSub(CustomInstantiationBase):
    pass


def instantiator(value):
    def instantiate(cls, **kwargs):
        instance = cls(**kwargs)
        instance.call = value
        return instance

    return instantiate


def test_custom_instantiation_argument_type(parser, clear_instantiators):
    parser.add_argument("--cls", type=CustomInstantiationBase)
    add_instantiator(instantiator("argument type"), CustomInstantiationBase)
    cfg = parser.parse_args(["--cls=CustomInstantiationBase"])
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, CustomInstantiationBase)
    assert init.cls.call == "argument type"


def test_custom_instantiation_unused_for_subclass(parser, clear_instantiators):
    parser.add_argument("--cls", type=CustomInstantiationBase)
    add_instantiator(instantiator("base"), CustomInstantiationBase, subclasses=False)
    cfg = parser.parse_args(["--cls=CustomInstantiationSub"])
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, CustomInstantiationSub)
    assert not hasattr(init.cls, "call")


def test_custom_instantiation_used_for_subclass(parser, clear_instantiators):
    parser.add_argument("--cls", type=CustomInstantiationBase)
    add_instantiator(instantiator("subclass"), CustomInstantiationBase, subclasses=True)
    cfg = parser.parse_args(["--cls=CustomInstantiationSub"])
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, CustomInstantiationSub)
    assert init.cls.call == "subclass"


def test_custom_instantiation_prepend(parser, clear_instantiators):
    parser.add_argument("--cls", type=CustomInstantiationBase)
    add_instantiator(instantiator("first"), CustomInstantiationSub)
    add_instantiator(instantiator("prepended"), CustomInstantiationBase, subclasses=True, prepend=True)
    assert len(_global_class_instantiators) == 2
    cfg = parser.parse_args(["--cls=CustomInstantiationSub"])
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, CustomInstantiationSub)
    assert init.cls.call == "prepended"


def test_custom_instantiation_replace(parser, clear_instantiators):
    first_instantiator = instantiator("first")
    second_instantiator = instantiator("second")
    parser.add_argument("--cls", type=CustomInstantiationBase)
    add_instantiator(first_instantiator, CustomInstantiationBase)
    add_instantiator(second_instantiator, CustomInstantiationBase)
    assert len(_global_class_instantiators) == 1
    assert list(_global_class_instantiators.values())[0] is second_instantiator


class CustomInstantiationNested:
    def __init__(self, sub: CustomInstantiationBase):
        self.sub = sub


def test_custom_instantiation_nested(parser, clear_instantiators):
    parser.add_argument("--cls", type=CustomInstantiationNested)
    add_instantiator(instantiator("nested"), CustomInstantiationBase, subclasses=True)
    cfg = parser.parse_args(["--cls=CustomInstantiationNested", "--cls.sub=CustomInstantiationSub"])
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, CustomInstantiationNested)
    assert isinstance(init.cls.sub, CustomInstantiationSub)
    assert init.cls.sub.call == "nested"


# environment tests


def test_subclass_env_help(parser):
    parser.env_prefix = "APP"
    parser.default_env = True
    parser.add_argument("--obj", type=BaseC)
    help_str = get_parser_help(parser)
    assert "ARG:   --obj OBJ" in help_str
    assert "ARG:   --obj.help" in help_str
    assert "ENV:   APP_OBJ" in help_str
    assert "APP_OBJ_HELP" not in help_str


def test_subclass_env_config(parser):
    parser.env_prefix = "APP"
    parser.default_env = True
    parser.add_argument("--obj", type=BaseC)
    env = {"APP_OBJ": '{"class_path": "SubA", "init_args": {"p": 4}}'}
    with patch.dict(os.environ, env):
        cfg = parser.parse_env()
    assert cfg.obj == Namespace(class_path=f"{__name__}.SubA", init_args=Namespace(p=4))


# nested subclass tests


class Nested:
    def __init__(self, obj: BaseC, p1: int = 0):
        self.obj = obj  # pragma: no cover


@pytest.mark.parametrize("prefix", ["", ".init_args"], ids=lambda v: f"prefix={v}")
def test_subclass_nested_parse(parser, prefix):
    parser.add_argument("--op", type=Nested)
    cfg = parser.parse_args(
        [
            f"--op={__name__}.Nested",
            f"--op{prefix}.p1=1",
            f"--op{prefix}.obj={__name__}.SubA",
            f"--op{prefix}.obj{prefix}.p=2",
        ]
    )
    assert cfg.op.class_path == f"{__name__}.Nested"
    assert cfg.op.init_args.p1 == 1
    assert cfg.op.init_args.obj.class_path == f"{__name__}.SubA"
    assert cfg.op.init_args.obj.init_args == Namespace(p=2)


def test_subclass_nested_help(parser):
    parser.add_argument("--op", type=Nested)
    help_str = get_parse_args_stdout(parser, [f"--op.help={__name__}.Nested", f"--op.obj.help={__name__}.SubA"])
    assert f"Help for --op.obj.help={__name__}.SubA" in help_str
    assert "--op.obj.p" in help_str
    help_str = get_parse_args_stdout(parser, [f"--op.help={__name__}.Nested", "--op.obj.help"])
    assert f"Help for --op.obj.help={__name__}.BaseC" in help_str
    assert "--op.obj.p" in help_str

    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args([f"--op.help={__name__}.Nested", "--op.p1=1"])
    ctx.match("Expected a nested --\\*.help option")


class RequiredParamSubModule:
    def __init__(self, p1: int, p2: int = 2, p3: int = 3):
        pass  # pragma: no cover


class RequiredParamModel:
    def __init__(self, sub_module: RequiredParamSubModule):
        pass  # pragma: no cover


def test_subclass_required_parameter_with_default_config_files(parser, tmp_cwd):
    defaults = {
        "model": {
            "sub_module": {
                "class_path": f"{__name__}.RequiredParamSubModule",
                "init_args": {
                    "p1": 4,
                    "p2": 5,
                },
            },
        },
    }
    defaults_path = Path("defaults.yaml")
    defaults_path.write_text(json_or_yaml_dump(defaults))

    parser.default_config_files = [defaults_path]
    parser.add_class_arguments(RequiredParamModel, "model")

    cfg = parser.parse_args(["--model.sub_module.init_args.p2=7"])

    expected = defaults["model"]
    expected["sub_module"]["init_args"]["p2"] = 7
    expected["sub_module"]["init_args"]["p3"] = 3
    assert cfg.model.as_dict() == expected


# short notation tests


def test_subclass_class_name_parse(parser):
    parser.add_argument("--op", type=Union[BaseC, GzipFile, None])
    cfg = parser.parse_args(["--op=SubA"])
    assert cfg.op.class_path == f"{__name__}.SubA"


def test_subclass_class_name_help(parser):
    parser.add_argument("--op", type=Union[BaseC, GzipFile, None])
    help_str = get_parse_args_stdout(parser, ["--op.help=GzipFile"])
    assert "Help for --op.help=gzip.GzipFile" in help_str
    assert "--op.compresslevel" in help_str


class LocaleTextCalendar(Calendar):
    pass


def test_subclass_class_name_set_defaults(parser):
    parser.add_argument("--obj", type=BaseC)
    parser.set_defaults(
        {
            "obj": {
                "class_path": "SubA",
                "init_args": {
                    "p": 1,
                },
            }
        }
    )
    obj = parser.get_default("obj").as_dict()
    assert obj == {"class_path": f"{__name__}.SubA", "init_args": {"p": 1}}


def test_subclass_short_init_args(parser):
    parser.add_argument("--op", type=BaseC)
    cfg = parser.parse_args(["--op=SubA", "--op.p=2"])
    assert cfg.op.class_path == f"{__name__}.SubA"
    assert cfg.op.init_args == Namespace(p=2)


def test_subclass_invalid_class_name(parser):
    parser.add_argument("--op", type=BaseC)
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--op=NotASubclass", "--op.p=2"])
    ctx.match("NotASubclass")


def test_subclass_class_name_then_invalid_init_args(parser):
    parser.add_argument("--op", type=Union[BaseC, GzipFile])
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--op=SubA", "--op=GzipFile", "--op.p=2"])
    ctx.match("Option 'p' is not accepted")


# dict parameter tests


class DictParam:
    def __init__(self, param: Dict[str, int]):
        pass  # pragma: no cover


@pytest.mark.parametrize("prefix", ["", ".init_args"])
def test_subclass_dict_parameter_command_line_set_items(parser, prefix):
    parser.add_argument("--val", type=DictParam)
    cfg = parser.parse_args(
        [
            "--val=DictParam",
            f"--val{prefix}.param.one=1",
            f"--val{prefix}.param.two=2",
        ]
    )
    assert cfg.val.class_path == f"{__name__}.DictParam"
    assert cfg.val.init_args.param == {"one": 1, "two": 2}


class MappingParamA:
    pass


class MappingParamB:
    def __init__(
        self,
        class_map: Mapping[str, MappingParamA],
        int_list: List[int],
    ):
        self.class_map = class_map
        self.int_list = int_list


def test_subclass_mapping_parameter(parser, subtests):
    parser.add_class_arguments(MappingParamB, "b")
    config = {
        "b": {
            "class_map": {
                "one": {"class_path": f"{__name__}.MappingParamA"},
            },
            "int_list": [1],
        },
    }

    with subtests.test("parse"):
        cfg = parser.parse_object(config)
        assert cfg.b.class_map == {"one": Namespace(class_path=f"{__name__}.MappingParamA")}
        assert cfg.b.int_list == [1]

    with subtests.test("instantiate"):
        init = parser.instantiate(cfg)
        assert isinstance(init.b, MappingParamB)
        assert isinstance(init.b.class_map, dict)
        assert isinstance(init.b.class_map["one"], MappingParamA)

    with subtests.test("parse error"):
        config["b"]["int_list"] = config["b"]["class_map"]
        with pytest.raises(ArgumentError) as ctx:
            parser.parse_object(config)
        ctx.match('key "b.int_list"')


class Module:
    pass


class Network(Module):
    def __init__(self, sub_network: Module, some_dict: Dict[str, Any] = {}):
        pass  # pragma: no cover


class Model:
    def __init__(self, encoder: Module):
        pass  # pragma: no cover


def test_subclass_dict_parameter_deep(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_class_arguments(Model, "model")

    config = {
        "model": {
            "encoder": {
                "class_path": f"{__name__}.Network",
                "init_args": {
                    "some_dict": {"a": 1},
                    "sub_network": {
                        "class_path": f"{__name__}.Network",
                        "init_args": {
                            "some_dict": {"b": 2},
                            "sub_network": {"class_path": f"{__name__}.Module"},
                        },
                    },
                },
            },
        },
    }

    cfg = parser.parse_args([f"--cfg={json_or_yaml_dump(config)}"])
    assert cfg.model.encoder.init_args.some_dict == {"a": 1}
    assert cfg.model.encoder.init_args.sub_network.init_args.some_dict == {"b": 2}
    assert cfg.model.as_dict() == config["model"]


# list append tests


class ListAppend:
    def __init__(self, p1: int = 0, p2: int = 0):
        pass  # pragma: no cover


@pytest.mark.parametrize("list_type", [List, Iterable])
def test_subclass_list_append_single(parser, list_type):
    parser.add_argument("--val", type=Union[ListAppend, list_type[ListAppend]])
    cfg = parser.parse_args([f"--val+={__name__}.ListAppend", "--val.p1=1", "--val.p2=2", "--val.p1=3"])
    assert cfg.val == [Namespace(class_path=f"{__name__}.ListAppend", init_args=Namespace(p1=3, p2=2))]
    cfg = parser.parse_args(["--val+=ListAppend", "--val.p2=2", "--val.p1=1"])
    assert cfg.val == [Namespace(class_path=f"{__name__}.ListAppend", init_args=Namespace(p1=1, p2=2))]
    assert " --val+ " in get_parser_help(parser)


@final
class IterableAppendObjs:
    def __init__(self, obj: Union[BaseC, Iterable[BaseC], bool] = True):
        self.obj = obj  # pragma: no cover


def test_subclass_list_append_nonclass_default(parser):
    parser.add_argument("cls", type=IterableAppendObjs)

    cfg = parser.parse_args([f"--cls.obj={__name__}.SubA", "--cls.obj.p=2"])
    assert not isinstance(cfg.cls.obj, list)
    assert f"{__name__}.SubA" == cfg.cls.obj.class_path
    assert 2 == cfg.cls.obj.init_args.p

    cfg = parser.parse_args([f"--cls.obj={__name__}.SubA", f"--cls.obj+={__name__}.SubB"])
    assert isinstance(cfg.cls.obj, list)
    assert [f"{__name__}.SubA", f"{__name__}.SubB"] == [c.class_path for c in cfg.cls.obj]


class ListAppendObjs:
    def __init__(self, objs: Optional[Union[BaseC, List[BaseC]]] = None):
        self.objs = objs  # pragma: no cover


def test_subclass_list_append_multiple(parser):
    parser.add_class_arguments(ListAppendObjs, "a")
    cfg = parser.parse_args(
        [
            "--a.objs+=BaseC",
            "--a.objs.p=3",
            "--a.objs+=SubA",
            "--a.objs.p=1",
        ]
    )
    assert [f"{__name__}.BaseC", f"{__name__}.SubA"] == [x.class_path for x in cfg.a.objs]
    assert [3, 1] == [x.init_args.p for x in cfg.a.objs]
    cfg = parser.parse_args([f"--a={json.dumps(cfg.a.as_dict())}", "--a.objs.p=4"])
    assert Namespace(p=4) == cfg.a.objs[-1].init_args
    args = ["--a.objs+=Invalid", "--a.objs+=SubA"]
    pytest.raises(ArgumentError, lambda: parser.parse_args(args))
    pytest.raises(ArgumentError, lambda: parser.parse_args(args + ["--print_config"]))


def test_subcommand_subclass_list_append_multiple(parser, subparser):
    subparser.add_class_arguments(ListAppendObjs, "a")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("cmd", subparser)
    cfg = parser.parse_args(
        [
            "cmd",
            "--a.objs+=BaseC",
            "--a.objs.p=3",
            "--a.objs+=SubA",
            "--a.objs.p=1",
        ]
    )
    assert [f"{__name__}.BaseC", f"{__name__}.SubA"] == [x.class_path for x in cfg.cmd.a.objs]
    assert [3, 1] == [x.init_args.p for x in cfg.cmd.a.objs]
    cfg = parser.parse_args(["cmd", f"--a={json.dumps(cfg.cmd.a.as_dict())}", "--a.objs.p=4"])
    assert Namespace(p=4) == cfg.cmd.a.objs[-1].init_args
    args = ["cmd", "--a.objs+=Invalid", "--a.objs+=SubA"]
    pytest.raises(ArgumentError, lambda: parser.parse_args(args))
    pytest.raises(ArgumentError, lambda: parser.parse_args(args + ["--print_config"]))


# type Any tests


class AnySubclasses:
    def __init__(self, obj1: BaseC, obj2: Any):
        self.obj1 = obj1
        self.obj2 = obj2


def test_type_any_subclasses(parser):
    parser.add_argument("--any", type=Any)
    value = {
        "class_path": f"{__name__}.AnySubclasses",
        "init_args": {
            "obj1": {
                "class_path": f"{__name__}.SubA",
                "init_args": {"p": 1},
            },
            "obj2": {
                "class_path": f"{__name__}.SubB",
                "init_args": {"p": 2},
            },
        },
    }

    cfg = parser.parse_args([f"--any={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.any, AnySubclasses)
    assert isinstance(init.any.obj1, SubA)
    assert isinstance(init.any.obj2, SubB)
    assert 1 == init.any.obj1.p
    assert 2 == init.any.obj2.p

    value["init_args"]["obj2"]["class_path"] = "does.not.exist"
    cfg = parser.parse_args([f"--any={json.dumps(value)}"])
    assert isinstance(cfg.any.init_args.obj1, Namespace)
    assert isinstance(cfg.any.init_args.obj2, dict)
    init = parser.instantiate(cfg)
    assert isinstance(init.any, AnySubclasses)
    assert isinstance(init.any.obj1, SubA)
    assert isinstance(init.any.obj2, dict)
    assert 1 == init.any.obj1.p
    assert 2 == init.any.obj2["init_args"]["p"]

    value["init_args"]["obj1"]["class_path"] = "does.not.exist"
    cfg = parser.parse_args([f"--any={json.dumps(value)}"])
    assert isinstance(cfg.any, dict)


def test_type_any_list_of_subclasses(parser):
    parser.add_argument("--any", type=Any)
    value = [
        {
            "class_path": f"{__name__}.SubA",
            "init_args": {"p": 1},
        },
        {
            "class_path": f"{__name__}.SubB",
            "init_args": {"p": 2},
        },
    ]

    cfg = parser.parse_args([f"--any={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.any, list)
    assert 2 == len(init.any)
    assert isinstance(init.any[0], SubA)
    assert isinstance(init.any[1], SubB)
    assert 1 == init.any[0].p
    assert 2 == init.any[1].p


def test_type_any_dict_of_subclasses(parser):
    parser.add_argument("--any", type=Any)
    value = {
        "k1": {
            "class_path": f"{__name__}.SubA",
            "init_args": {"p": 1},
        },
        "k2": {
            "class_path": f"{__name__}.SubB",
            "init_args": {"p": 2},
        },
    }

    cfg = parser.parse_args([f"--any={json.dumps(value)}"])
    init = parser.instantiate(cfg)
    assert isinstance(init.any, dict)
    assert 2 == len(init.any)
    assert isinstance(init.any["k1"], SubA)
    assert isinstance(init.any["k2"], SubB)
    assert 1 == init.any["k1"].p
    assert 2 == init.any["k2"].p


# override tests


class OverrideA(BaseC):
    def __init__(self, pa: str = "a", pc: str = "", **kwds):
        super().__init__(**kwds)  # pragma: no cover


class OverrideB(BaseC):
    def __init__(self, pb: str = "b", pc: int = 4, **kwds):
        super().__init__(**kwds)  # pragma: no cover


def test_subclass_discard_init_args(parser, logger):
    parser.logger = logger
    parser.add_subclass_arguments(BaseC, "obj")

    with capture_logs(logger) as logs:
        cfg = parser.parse_args(
            [
                f"--obj.class_path={__name__}.OverrideA",
                "--obj.init_args.pa=A",
                "--obj.init_args.pc=X",
                "--obj.init_args.p=3",
                f"--obj.class_path={__name__}.OverrideB",
                "--obj.init_args.pb=B",
            ]
        )

    assert "discarding init_args: {'pa': 'A', 'pc': 'X'}" in logs.getvalue()
    assert cfg.obj.class_path == f"{__name__}.OverrideB"
    assert cfg.obj.init_args == Namespace(pb="B", pc=4, p=3)


class OverrideChildBase:
    pass


class OverrideChildA(OverrideChildBase):
    def __init__(self, a: int = 0):
        pass  # pragma: no cover


class OverrideChildB(OverrideChildBase):
    def __init__(self, b: int = 0):
        pass  # pragma: no cover


class OverrideParent:
    def __init__(self, c: OverrideChildBase):
        pass  # pragma: no cover


def test_subclass_discard_init_args_nested(parser, logger):
    parser.logger = logger
    parser.add_subclass_arguments(OverrideParent, "p")

    with capture_logs(logger) as logs:
        cfg = parser.parse_args(
            [
                "--p=OverrideParent",
                "--p.init_args.c=OverrideChildA",
                "--p.init_args.c.init_args.a=1",
                "--p.init_args.c=OverrideChildB",
                "--p.init_args.c.init_args.b=2",
            ]
        )

    assert "discarding init_args: {'a': 1}" in logs.getvalue()
    assert cfg.p.class_path == f"{__name__}.OverrideParent"
    assert cfg.p.init_args.c.class_path == f"{__name__}.OverrideChildB"
    assert cfg.p.init_args.c.init_args == Namespace(b=2)


class OverrideMixed(BaseC):
    def __init__(self, *args, param: int = 0, **kwargs):
        super().__init__(*args, **kwargs)  # pragma: no cover


class OverrideMixedMain:
    def __init__(self, obj: Union[BaseC, bool] = lazy_instance(OverrideMixed, param=1)):
        self.obj = obj  # pragma: no cover


def test_subclass_discard_init_args_mixed_type(parser, logger):
    _cached_class_parsers.clear()
    parser.logger = logger
    parser.add_class_arguments(OverrideMixedMain, "main")
    with capture_logs(logger) as logs:
        parser.parse_args(["--main.obj=BaseC"])
    assert "discarding init_args: {'param': 1}" in logs.getvalue()


class OverrideBase:
    def __init__(self, b: int = 1):
        pass  # pragma: no cover


class OverrideSub1(OverrideBase):
    def __init__(self, s1: str = "-"):
        pass  # pragma: no cover


class OverrideSub2(OverrideBase):
    def __init__(self, s2: str = "-"):
        pass  # pragma: no cover


def test_subclass_discard_init_args_config_with_default(parser, logger):
    parser.logger = logger
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--s", type=OverrideBase, default=lazy_instance(OverrideSub1, s1="v1"))

    config = {"s": {"class_path": "OverrideSub2", "init_args": {"s2": "v2"}}}
    with capture_logs(logger) as logs:
        cfg = parser.parse_args([f"--cfg={json.dumps(config)}"])

    assert "discarding init_args: {'s1': 'v1'}" in logs.getvalue()
    assert cfg.s.class_path == f"{__name__}.OverrideSub2"
    assert cfg.s.init_args == Namespace(s2="v2")


class OverrideDefaultConfig(BaseC):
    def __init__(self, *args, param: str = "0", **kwargs):
        super().__init__(*args, **kwargs)


def test_subclass_discard_init_args_with_default_config_files(parser, tmp_cwd, logger):
    _cached_class_parsers.clear()
    config = {
        "class_path": f"{__name__}.OverrideDefaultConfig",
        "init_args": {"p": 2, "param": "1"},
    }
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(json.dumps({"obj": config}))

    parser.default_config_files = [config_path]
    parser.add_argument("--obj", type=Optional[BaseC])

    init = parser.instantiate(parser.get_defaults())
    assert isinstance(init.obj, OverrideDefaultConfig)

    parser.logger = logger
    with capture_logs(logger) as logs:
        cfg = parser.parse_args([f'--obj={{"class_path": "{__name__}.BaseC", "init_args": {{"p": 3}}}}'])
    assert "discarding init_args: {'param': '1'}" in logs.getvalue()
    assert cfg.obj.init_args == Namespace(p=3)
    with capture_logs(logger) as logs:
        assert type(parser.instantiate(cfg).obj) is BaseC
    assert logs.getvalue()


class Arch:
    def __init__(self, a: int = 1):
        pass  # pragma: no cover


class ArchB(Arch):
    def __init__(self, a: int = 2, b: int = 3):
        pass  # pragma: no cover


class ArchC(Arch):
    def __init__(self, a: int = 4, c: int = 5):
        pass  # pragma: no cover


def test_subclass_subcommand_set_defaults_discard_init_args(parser, subparser, logger):
    subcommands = parser.add_subcommands()
    subparser.add_argument("--arch", type=Arch)

    default = {"class_path": f"{__name__}.ArchB"}
    value = {"class_path": f"{__name__}.ArchC", "init_args": {"a": 10, "c": 11}}

    subparser.set_defaults(arch=default)
    parser.logger = logger
    subcommands.add_subcommand("fit", subparser)

    with capture_logs(logger) as logs:
        cfg = parser.parse_args(["fit", f"--arch={json.dumps(value)}"])
    assert "discarding init_args: {'b': 3}" in logs.getvalue()
    assert cfg.fit.arch.as_dict() == value


class ConfigDiscardBase:
    def __init__(self, b: float = 0.5):
        pass


class ConfigDiscardSub1(ConfigDiscardBase):
    def __init__(self, s1: str = "x", **kwargs):
        super().__init__(**kwargs)  # pragma: no cover


class ConfigDiscardSub2(ConfigDiscardBase):
    def __init__(self, s2: int = 3, **kwargs):
        super().__init__(**kwargs)


class ConfigDiscardMain:
    def __init__(self, sub: ConfigDiscardBase = lazy_instance(ConfigDiscardSub1)):
        self.sub = sub


@pytest.mark.parametrize("method", ["class", "subclass"])
def test_discard_init_args_config_nested(parser, logger, tmp_cwd, method):
    parser.logger = logger
    parser.add_argument("--cfg", action="config")

    subconfig = {
        "sub": {
            "class_path": f"{__name__}.ConfigDiscardSub2",
            "init_args": {"s2": 4},
        }
    }
    if method == "class":
        config = {"main": subconfig}
        parser.add_class_arguments(ConfigDiscardMain, "main")
    else:
        config = {
            "main": {
                "class_path": f"{__name__}.ConfigDiscardMain",
                "init_args": subconfig,
            }
        }
        parser.add_subclass_arguments(ConfigDiscardMain, "main")
        parser.set_defaults(main=lazy_instance(ConfigDiscardMain))

    config_path = Path("config.yaml")
    config_path.write_text(json_or_yaml_dump(config))

    with capture_logs(logger) as logs:
        cfg = parser.parse_args([f"--cfg={config_path}"])
    assert "discarding init_args: {'s1': 'x'}" in logs.getvalue()
    with capture_logs(logger) as logs:
        init = parser.instantiate(cfg)
    assert logs.getvalue()
    assert isinstance(init.main, ConfigDiscardMain)
    assert isinstance(init.main.sub, ConfigDiscardSub2)


class DictDiscardBase:
    def __init__(self, b: float = 0.5):
        pass  # pragma: no cover


class DictDiscardSub1(DictDiscardBase):
    def __init__(self, s1: int = 3, **kwargs):
        super().__init__(**kwargs)  # pragma: no cover


class DictDiscardSub2(DictDiscardBase):
    def __init__(self, s2: int = 4, **kwargs):
        super().__init__(**kwargs)  # pragma: no cover


class DictDiscardMain:
    def __init__(self, sub: Optional[dict] = None):
        self.sub = sub


def test_subclass_discard_init_args_dict_looks_like_subclass(parser, logger, tmp_cwd):
    parser.logger = logger
    parser.add_argument("--cfg", action="config")
    parser.add_subclass_arguments(DictDiscardMain, "main")
    parser.set_defaults(main=lazy_instance(DictDiscardMain))

    configs, subconfigs, config_paths = {}, {}, {}
    for c in [1, 2]:
        subconfigs[c] = {
            "sub": {
                "class_path": f"{__name__}.DictDiscardSub{c}",
                "init_args": {f"s{c}": c},
            }
        }
        configs[c] = {
            "main": {
                "class_path": f"{__name__}.DictDiscardMain",
                "init_args": subconfigs[c],
            }
        }
        config_paths[c] = Path(f"config{c}.yaml")
        config_paths[c].write_text(json_or_yaml_dump(configs[c]))

    with capture_logs(logger) as logs:
        cfg = parser.parse_args([f"--cfg={config_paths[1]}", f"--cfg={config_paths[2]}"])
    assert "discarding init_args: {'s1': 1}" in logs.getvalue()
    with capture_logs(logger) as logs:
        init = parser.instantiate(cfg)
    assert logs.getvalue()
    assert isinstance(init.main, DictDiscardMain)
    assert isinstance(init.main.sub, dict)
    assert init.main.sub["init_args"]["s2"] == 2


# unresolved parameters tests


class UnresolvedParams:
    def __init__(self, p1: int = 1, p2: str = "2", **kwargs):
        self.kwargs = kwargs


def test_subclass_unresolved_parameters(parser, subtests):
    config = {
        "cls": {
            "class_path": f"{__name__}.UnresolvedParams",
            "init_args": {"p1": 5},
            "dict_kwargs": {
                "p2": "6",
                "p3": 7.0,
                "p4": "x",
            },
        }
    }
    expected = Namespace(
        class_path=f"{__name__}.UnresolvedParams",
        init_args=Namespace(p1=5, p2="6"),
        dict_kwargs={"p3": 7.0, "p4": "x"},
    )

    parser.add_argument("--cfg", action="config")
    parser.add_argument("--cls", type=UnresolvedParams)

    with subtests.test("args"):
        cfg = parser.parse_args(
            ["--cls=UnresolvedParams", "--cls.dict_kwargs.p4=-", "--cls.dict_kwargs.p3=7.0", "--cls.dict_kwargs.p4=x"]
        )
        assert cfg.cls.dict_kwargs == expected.dict_kwargs

    with subtests.test("config"):
        cfg = parser.parse_args([f"--cfg={json.dumps(config)}"])
        assert cfg.cls == expected
        init = parser.instantiate(cfg)
        assert isinstance(init.cls, UnresolvedParams)
        assert init.cls.kwargs == expected.dict_kwargs

    with subtests.test("print_config"):
        out = get_parse_args_stdout(parser, [f"--cfg={json.dumps(config)}", "--print_config"])
        data = json_or_yaml_load(out)["cls"]
        assert data == expected.as_dict()

    with subtests.test("invalid dict_kwargs"):
        with pytest.raises(ArgumentError):
            parser.parse_args(["--cls=UnresolvedParams", "--cls.dict_kwargs=1"])


class UnresolvedNameClash:
    def __init__(self, dict_kwargs: int = 1, **kwargs):
        self.kwargs = kwargs  # pragma: no cover


def test_subclass_unresolved_parameters_name_clash(parser):
    parser.add_argument("--cls", type=UnresolvedNameClash)

    args = [f"--cls={__name__}.UnresolvedNameClash", "--cls.dict_kwargs=2"]
    cfg = parser.parse_args(args)
    assert cfg.cls.init_args.as_dict() == {"dict_kwargs": 2}

    args.append("--cls.dict_kwargs.p1=3")
    cfg = parser.parse_args(args)
    assert cfg.cls.init_args.as_dict() == {"dict_kwargs": 2}
    assert cfg.cls.dict_kwargs == {"p1": 3}


# add_subclass_arguments tests


def test_add_subclass_failure_not_a_class(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_subclass_arguments(NAMESPACE_OID, "oid")
    ctx.match("Expected 'baseclass' to be a subclass type or a tuple of subclass types")


def test_add_subclass_failure_empty_tuple(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_subclass_arguments((), "cls")
    ctx.match("Expected 'baseclass' to be a subclass type or a tuple of subclass types")


def test_add_subclass_lazy_default(parser):
    parser.add_subclass_arguments(BaseC, "obj", default=lazy_instance(BaseC, p=4))
    cfg = parser.parse_string(parser.dump(parser.parse_args([])))
    assert cfg.obj.class_path == f"{__name__}.BaseC"
    assert cfg.obj.init_args.p == 4

    parser.add_argument("--config", action="config")
    parser.set_defaults({"obj": lazy_instance(BaseC, p=5)})
    out = get_parse_args_stdout(parser, ["--print_config"])
    assert json_or_yaml_load(out)["obj"] == {"class_path": f"{__name__}.BaseC", "init_args": {"p": 5}}

    help_str = get_parser_help(parser)
    assert "'init_args': {'p': 5}" in help_str


class TupleBaseA:
    def __init__(self, a1: int = 1, a2: float = 2.3):
        self.a1 = a1
        self.a2 = a2


class TupleBaseB:
    def __init__(self, b1: float = 4.5, b2: int = 6):
        self.b1 = b1
        self.b2 = b2


def test_add_subclass_tuple(parser):
    parser.add_subclass_arguments((TupleBaseA, TupleBaseB), "c")

    cfg = parser.parse_args(['--c={"class_path": "TupleBaseA", "init_args": {"a1": -1}}'])
    assert cfg.c.init_args.a1 == -1
    init = parser.instantiate(cfg)
    assert isinstance(init.c, TupleBaseA)

    cfg = parser.parse_args(['--c={"class_path": "TupleBaseB", "init_args": {"b1": -4.5}}'])
    assert cfg.c.init_args.b1 == -4.5
    init = parser.instantiate(cfg)
    assert isinstance(init.c, TupleBaseB)

    help_str = get_parse_args_stdout(parser, [f"--c.help={__name__}.TupleBaseB"])
    assert "--c.b1 B1" in help_str


def test_add_subclass_required_group(parser):
    pytest.raises(ValueError, lambda: parser.add_subclass_arguments(BaseC, None, required=True))
    parser.add_subclass_arguments(BaseC, "obj", required=True)
    pytest.raises(ArgumentError, lambda: parser.parse_args([]))
    help_str = get_parser_help(parser)
    assert "--obj.help [CLASS_PATH_OR_NAME]" in help_str
    assert "--obj CONFIG | CLASS_PATH_OR_NAME | .INIT_ARG_NAME VALUE" in help_str


def test_add_subclass_not_required_group(parser):
    parser.add_subclass_arguments(BaseC, "obj", required=False)
    cfg = parser.parse_args([])
    assert cfg == Namespace(obj=None)
    init = parser.instantiate(cfg)
    assert init == Namespace(obj=None)


class ListUnionA:
    def __init__(self, pa1: int):  # pragma: no cover
        self.pa1 = pa1


class ListUnionB:
    def __init__(self, pb1: str, pb2: float):  # pragma: no cover
        self.pb1 = pb1
        self.pb2 = pb2


def test_add_subclass_list_of_union(parser):
    parser.add_argument("--config", action="config")
    parser.add_subclass_arguments(
        baseclass=(ListUnionA, ListUnionB, List[Union[ListUnionA, ListUnionB]]),
        nested_key="subclass",
    )
    config = {
        "subclass": [
            {
                "class_path": f"{__name__}.ListUnionB",
                "init_args": {
                    "pb1": "x",
                    "pb2": 0.5,
                },
            }
        ]
    }
    cfg = parser.parse_args([f"--config={json.dumps(config)}"])
    assert cfg.as_dict()["subclass"] == config["subclass"]
    help_str = get_parser_help(parser)
    assert "Show the help for the given subclass of {ListUnionA,ListUnionB}" in help_str


# instance defaults tests


def test_add_subclass_set_defaults_instance_default(parser):
    parser.add_subclass_arguments(BaseC, "obj")
    with pytest.raises(ValueError) as ctx:
        parser.set_defaults({"obj": BaseC(p=2)})
    ctx.match("Subclass types require as default either a dict with class_path or a lazy instance")


def test_add_argument_subclass_instance_default(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("--obj", type=BaseC, default=BaseC(p=2))
    ctx.match("Subclass types require as default either a dict with class_path or a lazy instance")


class InstanceDefault:
    def __init__(self, cal: Calendar = Calendar(firstweekday=2)):
        pass  # pragma: no cover


def test_subclass_signature_instance_default(parser):
    with source_unavailable():
        parser.add_class_arguments(InstanceDefault)
    cfg = parser.parse_args([])
    assert isinstance(cfg["cal"], Calendar)
    init = parser.instantiate(cfg)
    assert init["cal"] is cfg["cal"]
    with warnings.catch_warnings(record=True) as w:
        dump = parser.dump(cfg)
    assert "Unable to serialize instance" in str(w[0].message)
    assert "Unable to serialize instance <calendar.Calendar " in dump


# protocol tests


class Interface(Protocol):
    def predict(self, items: List[float]) -> List[float]: ...


class ImplementsInterface:
    def __init__(self, batch_size: int):
        self.batch_size = batch_size

    def predict(self, items: List[float]) -> List[float]:
        return items


class SubclassImplementsInterface(Interface):
    def __init__(self, max_items: int):
        self.max_items = max_items  # pragma: no cover

    def predict(self, items: List[float]) -> List[float]:
        return items  # pragma: no cover


class NotImplementsInterface1:
    def predict(self, items: str) -> List[float]:
        return []  # pragma: no cover


class NotImplementsInterface2:
    def predict(self, items: List[float], extra: int) -> List[float]:
        return items  # pragma: no cover


class NotImplementsInterface3:
    def predict(self, items: List[float]) -> None:
        return  # pragma: no cover


@pytest.mark.parametrize(
    "expected, value",
    [
        (True, ImplementsInterface),
        (True, SubclassImplementsInterface),
        (False, ImplementsInterface(1)),
        (False, NotImplementsInterface1),
        (False, NotImplementsInterface2),
        (False, NotImplementsInterface3),
        (False, object),
    ],
)
def test_implements_protocol(expected, value):
    assert implements_protocol(value, Interface) is expected


@pytest.mark.parametrize(
    "expected, value",
    [
        (False, ImplementsInterface),
        (True, ImplementsInterface(1)),
        (False, NotImplementsInterface1()),
        (False, object),
    ],
)
def test_is_instance_or_supports_protocol(expected, value):
    assert is_instance_or_supports_protocol(value, Interface) is expected


def test_parse_implements_protocol(parser):
    parser.add_argument("--cls", type=Interface)
    cfg = parser.parse_args([f"--cls={__name__}.ImplementsInterface", "--cls.batch_size=5"])
    assert cfg.cls.class_path == f"{__name__}.ImplementsInterface"
    assert cfg.cls.init_args == Namespace(batch_size=5)
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, ImplementsInterface)
    assert init.cls.batch_size == 5
    assert init.cls.predict([1.0, 2.0]) == [1.0, 2.0]

    help_str = get_parser_help(parser)
    assert "known subclasses:" in help_str
    assert f"{__name__}.SubclassImplementsInterface" in help_str
    help_str = get_parse_args_stdout(parser, ["--cls.help=SubclassImplementsInterface"])
    assert "--cls.max_items" in help_str
    with pytest.raises(ArgumentError, match="not a subclass or implementer of protocol"):
        parser.parse_args([f"--cls.help={__name__}.NotImplementsInterface1"])

    with pytest.raises(ArgumentError, match="is a protocol"):
        parser.parse_args([f"--cls={__name__}.Interface"])
    with pytest.raises(ArgumentError, match="does not implement protocol"):
        parser.parse_args([f"--cls={__name__}.NotImplementsInterface1"])
    with pytest.raises(ArgumentError, match="Does not implement protocol Interface"):
        parser.parse_args(["--cls=[1]"])


# callable protocol tests


class CallableInterface(Protocol):
    def __call__(self, items: List[float]) -> List[float]: ...


class ImplementsCallableInterface:
    def __init__(self, batch_size: int):
        self.batch_size = batch_size

    def __call__(self, items: List[float]) -> List[float]:
        return items


class NotImplementsCallableInterface1:
    def __call__(self, items: str) -> List[float]:
        return []  # pragma: no cover


class NotImplementsCallableInterface2:
    def __call__(self, items: List[float], extra: int) -> List[float]:
        return items  # pragma: no cover


class NotImplementsCallableInterface3:
    def __call__(self, items: List[float]) -> None:
        return  # pragma: no cover


@pytest.mark.parametrize(
    "expected, value",
    [
        (True, ImplementsCallableInterface),
        (False, ImplementsCallableInterface(1)),
        (False, NotImplementsCallableInterface1),
        (False, NotImplementsCallableInterface2),
        (False, NotImplementsCallableInterface3),
        (False, object),
    ],
)
def test_implements_callable_protocol(expected, value):
    assert implements_protocol(value, CallableInterface) is expected


def test_parse_implements_callable_protocol(parser):
    parser.add_argument("--cls", type=CallableInterface)
    cfg = parser.parse_args([f"--cls={__name__}.ImplementsCallableInterface", "--cls.batch_size=7"])
    assert cfg.cls.class_path == f"{__name__}.ImplementsCallableInterface"
    assert cfg.cls.init_args == Namespace(batch_size=7)
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, ImplementsCallableInterface)
    assert init.cls([1.0, 2.0]) == [1.0, 2.0]

    assert "known subclasses:" not in get_parser_help(parser)
    help_str = get_parse_args_stdout(parser, [f"--cls.help={__name__}.ImplementsCallableInterface"])
    assert "--cls.batch_size" in help_str

    with pytest.raises(ArgumentError, match="is a protocol"):
        parser.parse_args([f"--cls={__name__}.CallableInterface"])
    with pytest.raises(ArgumentError, match="does not implement protocol"):
        parser.parse_args([f"--cls={__name__}.NotImplementsCallableInterface1"])
    with pytest.raises(ArgumentError, match="Does not implement protocol CallableInterface"):
        parser.parse_args(["--cls=[1]"])


# parameter skip tests


class ParamSkipBase:
    def __init__(self, a1: int = 1, a2: float = 2.3):  # pragma: no cover
        self.a1 = a1
        self.a2 = a2


class ParamSkipSub(ParamSkipBase):
    def __init__(self, b1: float = 4.5, b2: int = 6, **kwargs):  # pragma: no cover
        super().__init__(**kwargs)
        self.b1 = b1
        self.b2 = b2


def test_add_subclass_parameter_skip(parser):
    parser.add_subclass_arguments(ParamSkipBase, "c", skip={"a1", "b2"})
    cfg = parser.parse_args([f"--c={__name__}.ParamSkipBase"])
    assert cfg.c.init_args == Namespace(a2=2.3)
    cfg = parser.parse_args([f"--c={__name__}.ParamSkipSub"])
    assert cfg.c.init_args == Namespace(a2=2.3, b1=4.5)


class ParamSkip1:
    def __init__(self, a1: int = 1, a2: float = 2.3, a3: str = "4"):  # pragma: no cover
        self.a1 = a1
        self.a2 = a2
        self.a3 = a3


class ParamSkip2:
    def __init__(self, c1: ParamSkip1, c2: int = 5, c3: float = 6.7):  # pragma: no cover
        pass


def test_add_subclass_parameter_skip_nested(parser):
    parser.add_class_arguments(ParamSkip2, skip={"c1.init_args.a2", "c2"})
    cfg = parser.parse_args([f"--c1={__name__}.ParamSkip1"])
    assert cfg.c1.init_args == Namespace(a1=1, a3="4")


# print_config/save tests


@dataclass
class PrintConfig:
    a1: BaseC
    a2: int = 7


def test_subclass_print_config(parser):
    parser.add_argument("--config", action="config")
    parser.add_class_arguments(PrintConfig, "g")

    out = get_parse_args_stdout(parser, [f"--g.a1={__name__}.BaseC", "--print_config"])
    obtained = json_or_yaml_load(out)["g"]
    assert obtained == {"a1": {"class_path": f"{__name__}.BaseC", "init_args": {"p": 0}}, "a2": 7}

    err = get_parse_args_stderr(parser, [f"--g.a1={__name__}.BaseC", "--g.a1.invalid=1", "--print_config"])
    assert "Option 'invalid' is not accepted" in err


class PrintConfigRequired:
    def __init__(self, arg1: float):
        pass  # pragma: no cover


class PrintConfigRequiredBase:
    def __init__(self):
        pass  # pragma: no cover


class PrintConfigRequiredSub(PrintConfigRequiredBase):
    def __init__(self, arg1: int, arg2: int = 1):
        pass  # pragma: no cover


def test_subclass_print_config_required_parameters_as_null(parser):
    parser.add_argument("--config", action="config")
    parser.add_class_arguments(PrintConfigRequired, "class")
    parser.add_subclass_arguments(PrintConfigRequiredBase, "subclass")

    out = get_parse_args_stdout(parser, [f"--subclass={__name__}.PrintConfigRequiredSub", "--print_config"])
    expected = {
        "class": {"arg1": None},
        "subclass": {"class_path": f"{__name__}.PrintConfigRequiredSub", "init_args": {"arg1": None, "arg2": 1}},
    }

    assert json_or_yaml_load(out) == expected


def test_subclass_multifile_save(parser, tmp_cwd):
    parser.add_subclass_arguments(BaseC, "obj")

    obj_cfg_path = Path("obj.yaml")
    obj_cfg_path.write_text(json_or_yaml_dump({"class_path": f"{__name__}.BaseC"}))
    out_main_cfg = Path("out", "config.yaml")
    out_main_cfg.parent.mkdir()

    cfg = parser.parse_args([f"--obj={obj_cfg_path}"])
    parser.save(cfg, out_main_cfg, multifile=True)

    assert {"obj": "obj.yaml"} == json_or_yaml_load(out_main_cfg.read_text())
    obj = json_or_yaml_load(Path("out", "obj.yaml").read_text())
    assert obj == {"class_path": f"{__name__}.BaseC", "init_args": {"p": 0}}


# failure cases tests


def test_subclass_error_not_subclass(parser):
    parser.add_argument("--op", type=BaseC)
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--op={"class_path": "jsonargparse.ArgumentParser"}'])
    ctx.match("does not correspond to a subclass")


def test_subclass_error_undefined_attribute(parser):
    parser.add_argument("--op", type=BaseC)
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--op={"class_path": "jsonargparse.DoesNotExist"}'])
    ctx.match("module 'jsonargparse' has no attribute 'DoesNotExist'")


def test_subclass_error_undefined_module(parser):
    parser.add_argument("--op", type=BaseC)
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--op={"class_path": "does_not_exist_module.SomeClass"}'])
    ctx.match("No module named 'does_not_exist_module'")


def test_subclass_error_unexpected_init_arg(parser):
    parser.add_argument("--op", type=BaseC)
    class_path = f'"class_path": "{__name__}.BaseC"'
    init_args = '"init_args": {"unexpected_arg": true}'
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--op={" + class_path + ", " + init_args + "}"])
    ctx.match("Option 'unexpected_arg' is not accepted")


def test_subclass_invalid_class_path_value(parser):
    parser.add_argument("--obj", type=BaseC, default=lazy_instance(BaseC))
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--obj.class_path.init_args.p=2"])
    ctx.match('Parser key "obj"')


def test_subclass_invalid_init_args_in_yaml(parser):
    value = f"""obj:
        class_path: {__name__}.BaseC
        init_args:
    """
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--obj", type=BaseC)
    pytest.raises(ArgumentError, lambda: parser.parse_args([f"--cfg={value}"]))


class RequiredParamsMissing:
    def __init__(self, p1: int, p2: str):
        pass  # pragma: no cover


def test_subclass_required_parameters_missing(parser):
    parser.add_argument("--op", type=RequiredParamsMissing, default=lazy_instance(RequiredParamsMissing))
    defaults = parser.get_defaults()
    assert defaults.op.class_path == f"{__name__}.RequiredParamsMissing"
    assert defaults.op.init_args == Namespace(p1=None, p2=None)
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args([f"--op={__name__}.RequiredParamsMissing"])
    ctx.match('Parser key "op"')
    ctx.match("the following arguments are required: p1, p2")


def test_subclass_help_required_parameters(parser):
    parser.add_argument("--op", type=RequiredParamsMissing)
    help_str = get_parse_args_stdout(parser, [f"--op.help={__name__}.RequiredParamsMissing"])
    assert "(required, type: int)" in help_str
    assert "(required, type: str)" in help_str


def test_subclass_get_defaults_lazy_instance(parser):
    parser.add_argument("--op", type=RequiredParamsMissing, default=lazy_instance(RequiredParamsMissing, p1=1, p2="x"))
    defaults = parser.get_defaults()
    assert defaults.op.init_args == Namespace(p1=1, p2="x")


@pytest.mark.parametrize("option", ["--op", "--op.help"])
def test_subclass_class_name_ambiguous(parser, option):
    parser.add_argument("--op", type=Union[Calendar, GzipFile, None])
    with pytest.raises(ArgumentError):
        parser.parse_args([f"{option}=LocaleTextCalendar"])


def test_subclass_help_not_subclass(parser):
    parser.add_argument("--op", type=BaseC)
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--op.help=uuid.UUID"])
    ctx.match("is not a subclass of")


class Implicit:
    def __init__(self, a: int = 1, b: str = ""):
        pass  # pragma: no cover


def test_subclass_implicit_class_path(parser):
    parser.add_argument("--implicit", type=Implicit)
    cfg = parser.parse_args(['--implicit={"a": 2, "b": "x"}'])
    assert cfg.implicit.class_path == f"{__name__}.Implicit"
    assert cfg.implicit.init_args == Namespace(a=2, b="x")
    cfg = parser.parse_args(["--implicit.a=3"])
    assert cfg.implicit.init_args == Namespace(a=3, b="")
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--implicit={"c": null}'])
    ctx.match("Option 'c' is not accepted")


# error messages tests


class ErrorIndentation1:
    def __init__(self, val: Optional[Union[int, dict]] = None):
        pass  # pragma: no cover


def test_subclass_error_indentation_invalid_init_arg(parser):
    parser.add_subclass_arguments(ErrorIndentation1, "cls")
    err = get_parse_args_stderr(parser, ["--cls=ErrorIndentation1", "--cls.init_args.val=abc"])
    expected = textwrap.dedent("""
    Parser key "val":
      Does not validate against any of the Union subtypes
      Subtypes: [<class 'NoneType'>, <class 'int'>, <class 'dict'>]
      Errors:
        - Expected a <class 'NoneType'>
        - Expected a <class 'int'>
        - Expected a <class 'dict'>
      Given value type: <class 'str'>
      Given value: abc
    """).strip()
    expected = textwrap.indent(expected, "        ")
    assert "\n".join(expected.splitlines()) in "\n".join(err.splitlines())


class ErrorIndentation2:
    def __init__(self, val: int):
        pass  # pragma: no cover


def test_subclass_error_indentation_in_union_invalid_value(parser):
    parser.add_argument("--union", type=Union[str, ErrorIndentation2])
    parser.add_argument("--cfg", action="config")
    config = {"union": [{"class_path": "ErrorIndentation2", "init_args": {"val": "x"}}]}
    err = get_parse_args_stderr(parser, [f"--cfg={json.dumps(config)}"])
    expected = textwrap.dedent("""
    Errors:
      - Expected a <class 'str'>
      - Not a valid subclass of ErrorIndentation2
        Subclass types expect one of:
        - a class path (str)
        - a dict with class_path entry
        - a dict without class_path but with init_args entry (class path given previously)
        - a dict with parameters accepted by the base class (implicit class_path)
    Given value type: <class 'list'>
    Given value: [{'class_path': 'ErrorIndentation2', 'init_args': {'val': 'x'}}]
    """).strip()
    expected = textwrap.indent(expected, "  ")
    assert "\n".join(expected.splitlines()) in "\n".join(err.splitlines())
