from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from jsonargparse import (
    SUPPRESS,
    ActionSubCommands,
    ArgumentError,
    ArgumentParser,
    Namespace,
    add_instantiator,
)
from jsonargparse_tests.conftest import (
    get_parse_args_stderr,
    get_parse_args_stdout,
    get_parser_help,
    json_or_yaml_dump,
    json_or_yaml_load,
)
from jsonargparse_tests.test_subclasses import CustomInstantiationBase, instantiator


@pytest.fixture
def subcommands_parser(parser, subparser, example_parser):
    subparser.add_argument("ap1")
    subparser.add_argument("--ao1", default="ao1_def")
    parser.env_prefix = "APP"
    parser.add_argument("--o1", default="o1_def")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("a", subparser)
    subcommands.add_subcommand("b", example_parser, aliases=["B"])
    return parser


def test_add_subparsers_not_implemented(parser):
    with pytest.raises(NotImplementedError) as ctx:
        parser.add_subparsers()
    ctx.match("add_subcommands method")


def test_action_subcommands_public_api(parser):
    subcommands = parser.add_subcommands()
    assert isinstance(subcommands, ActionSubCommands)
    assert subcommands.required is True
    assert parser._extra_required_keys == set()


def test_add_parser_not_implemented(parser):
    subcommands = parser.add_subcommands()
    with pytest.raises(NotImplementedError) as ctx:
        subcommands.add_parser("")
    ctx.match("add_subcommand method")


def test_subcommands_get_defaults(subcommands_parser):
    cfg = subcommands_parser.get_defaults().as_dict()
    assert cfg == {"o1": "o1_def", "subcommand": None}


def test_subcommands_undefined_subcommand(subcommands_parser):
    pytest.raises(ArgumentError, lambda: subcommands_parser.parse_args(["c"]))


def test_subcommands_not_given_when_few_subcommands(subcommands_parser):
    err = get_parse_args_stderr(subcommands_parser, [])
    assert 'error: expected "subcommand" to be one of {a,b,B}, but it was not provided.' in err


def test_subcommands_not_given_when_many_subcommands(parser, subparser):
    subcommands = parser.add_subcommands()
    for subcommand in range(ord("a"), ord("l") + 1):
        subcommands.add_subcommand(chr(subcommand), subparser)
    err = get_parse_args_stderr(parser, [])
    assert 'error: expected "subcommand" to be one of {a,b,c,d,e, ...}, but it was not provided.' in err


def test_subcommands_missing_required_subargument(subcommands_parser):
    with pytest.raises(ArgumentError, match=r"the following arguments are required: a\.ap1"):
        subcommands_parser.parse_args(["a"])


def test_subcommands_undefined_subargument(subcommands_parser):
    pytest.raises(ArgumentError, lambda: subcommands_parser.parse_args(["b", "--unk"]))


def test_subcommands_parse_args_basics(subcommands_parser):
    cfg = subcommands_parser.parse_args(["--o1", "o1_arg", "a", "ap1_arg"])
    assert cfg["o1"] == "o1_arg"
    assert cfg["subcommand"] == "a"
    assert cfg["a"].as_dict() == {"ap1": "ap1_arg", "ao1": "ao1_def"}
    assert "b" not in cfg

    cfg = subcommands_parser.parse_args(["a", "ap1_arg", "--ao1", "ao1_arg"])
    assert cfg["a"].as_dict() == {"ap1": "ap1_arg", "ao1": "ao1_arg"}

    cfg = subcommands_parser.parse_args(["b"])
    assert cfg["subcommand"] == "b"
    assert "a" not in cfg


def test_main_subcommands_help(subcommands_parser):
    help_str = get_parser_help(subcommands_parser)
    assert help_str.count("{a,b,B}") == 1
    assert "Available subcommands:" in help_str
    assert "b (B)" in help_str


def test_subcommands_parse_args_alias(subcommands_parser):
    cfg = subcommands_parser.parse_args(["B"])
    assert cfg["subcommand"] == "B"
    pytest.raises(ArgumentError, lambda: subcommands_parser.parse_args(["A"]))


def test_subcommands_parse_args_config(subcommands_parser):
    subcommands_parser.add_argument("--cfg", action="config")
    cfg = subcommands_parser.parse_args(['--cfg={"o1": "o1_arg"}', "a", "ap1_arg"]).as_dict()
    assert cfg == {
        "a": {"ao1": "ao1_def", "ap1": "ap1_arg"},
        "cfg": [None],
        "o1": "o1_arg",
        "subcommand": "a",
    }


def test_subcommands_parse_args_error_config_before_subcommand(parser, subparser):
    subparser.add_argument("--sp1")
    subcommands = parser.add_subcommands(required=False)
    subcommands.add_subcommand("a", subparser)
    parser.add_argument("--cfg", action="config")
    parser.prog = "app"
    parser.exit_on_error = True
    err = get_parse_args_stderr(parser, ['--cfg={"sp1": "x"}', "a"])
    assert "Option 'sp1' is not accepted before subcommand 'a'" in err
    assert "For details of accepted options run: app --help" in err
    err = get_parse_args_stderr(parser, ['--cfg={"sp1": "x"}'])
    assert "Option 'sp1' is not accepted before subcommand {a,...}" in err
    assert "For details of accepted options run: app --help" in err
    assert "usage: app [--cfg CFG] {a} ..." in err


def test_subcommands_parse_args_error_config_after_subcommand(parser, subparser):
    parser.prog = "app"
    parser.exit_on_error = True
    subparser.add_argument("--sp1")
    subcommands = parser.add_subcommands(required=False)
    subcommands.add_subcommand("a", subparser)
    parser.add_argument("--cfg", action="config")
    err = get_parse_args_stderr(parser, ['--cfg={"a": {"sp2": "x"}}'])
    assert "Subcommand 'a' does not accept option 'sp2'" in err
    assert "For details of accepted options run: app a --help" in err
    assert "usage: app [options] a [--sp1 SP1]" in err


def test_subcommands_parse_string_implicit_subcommand(subcommands_parser):
    cfg = subcommands_parser.parse_string('{"a": {"ap1": "ap1_cfg"}}').as_dict()
    assert cfg["subcommand"] == "a"
    assert cfg["a"] == {"ap1": "ap1_cfg", "ao1": "ao1_def"}
    with pytest.raises(ArgumentError) as ctx:
        subcommands_parser.parse_string('{"a": {"ap1": "ap1_cfg", "unk": "unk_cfg"}}')
    ctx.match("Subcommand 'a' does not accept option 'unk'")


def test_subcommands_parse_string_explicit_subcommand(subcommands_parser):
    cfg = subcommands_parser.parse_string('{"subcommand": "b", "a": {"ap1": "ap1_cfg"}, "b": {"nums": {"val1": 2}}}')
    assert cfg.subcommand == "b"
    assert cfg.b.as_dict() == {"bool": True, "nums": {"val1": 2, "val2": 2.0}}
    assert "a" not in cfg


def test_subcommands_parse_args_config_explicit_subcommand_arg(subcommands_parser):
    subcommands_parser.add_argument("--cfg", action="config")
    cfg = subcommands_parser.parse_args(['--cfg={"a": {"ap1": "ap1_cfg"}, "b": {"nums": {"val1": 2}}}', "a"])
    assert cfg.as_dict() == {
        "o1": "o1_def",
        "subcommand": "a",
        "cfg": [None],
        "a": {"ap1": "ap1_cfg", "ao1": "ao1_def"},
    }


def test_subcommands_parse_string_missing_explicit_subcommand(subcommands_parser):
    with pytest.raises(ValueError) as ctx:
        subcommands_parser.parse_string('{"a": {"ap1": "ap1_cfg"}, "b": {"nums": {"val1": 2}}}')
    ctx.match("Multiple subcommand settings .* without providing an explicit 'subcommand' key")


env = {
    "APP_O1": "o1_env",
    "APP_A__AP1": "ap1_env",
    "APP_A__AO1": "ao1_env",
    "APP_B__NUMS__VAL2": "5.6",
}


@patch.dict(os.environ, env)
def test_subcommands_parse_args_environment(subcommands_parser):
    cfg = subcommands_parser.parse_args(["a"], env=True).as_dict()
    assert cfg["o1"] == "o1_env"
    assert cfg["subcommand"] == "a"
    assert cfg["a"] == {"ap1": "ap1_env", "ao1": "ao1_env"}

    subcommands_parser.default_env = True
    cfg = subcommands_parser.parse_args(["b"]).as_dict()
    assert cfg["subcommand"] == "b"
    assert cfg["b"] == {"bool": True, "nums": {"val1": 1, "val2": 5.6}}


@patch.dict(os.environ, {"APP_SUBCOMMAND": "a", **env})
def test_subcommands_parse_env(subcommands_parser):
    cfg = subcommands_parser.parse_env().as_dict()
    assert cfg["o1"] == "o1_env"
    assert cfg["subcommand"] == "a"
    assert cfg["a"] == {"ap1": "ap1_env", "ao1": "ao1_env"}


def test_subcommands_help_default_env_true(subcommands_parser):
    subcommands_parser.default_env = True
    help_str = get_parser_help(subcommands_parser)
    assert "ENV:   APP_SUBCOMMAND" in help_str


def test_subcommand_env_overrides_default_config(parser, subparser, tmp_cwd):
    Path("config.json").write_text(json.dumps({"create": {"stats": True}}))
    parser.env_prefix = "APP"
    parser.default_env = True
    parser.default_config_files = ["config.json"]

    subparser.add_argument("--stats", action="store_true")
    subcommands = parser.add_subcommands(required=False)
    subcommands.add_subcommand("create", subparser)

    cfg = parser.parse_args(["create"])
    assert cfg.create.stats is True

    with patch.dict(os.environ, {"APP_CREATE__STATS": "false"}):
        cfg = parser.parse_args(["create"])
    assert cfg.create.stats is False


def test_subcommand_required_false(parser, subparser):
    subcommands = parser.add_subcommands(required=False)
    subcommands.add_subcommand("foo", subparser)
    cfg = parser.parse_args([])
    assert cfg == Namespace(subcommand=None)


def test_subcommand_without_options(parser, subparser):
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("foo", subparser)
    cfg = parser.parse_args(["foo"])
    assert cfg.subcommand == "foo"


def test_subcommand_print_config_default_env(subparser):
    subparser.add_argument("--config", action="config")
    subparser.add_argument("--o", type=int, default=1)

    parser = ArgumentParser(exit_on_error=False, default_env=True)
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("a", subparser)

    out = get_parse_args_stdout(parser, ["a", "--print_config"])
    assert json_or_yaml_load(out) == {"o": 1}


def test_subcommand_default_config_repeated_keys(parser, subparser, tmp_cwd):
    defaults = tmp_cwd / "defaults.json"
    defaults.write_text('{"test":{"test":"value"}}')
    parser.default_config_files = [defaults]
    subparser.add_argument("--test")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("test", subparser)

    cfg = parser.parse_args([]).clone(with_meta=False)
    assert cfg == Namespace(subcommand="test", test=Namespace(test="value"))
    cfg = parser.parse_args(["test", "--test=x"]).clone(with_meta=False)
    assert cfg == Namespace(subcommand="test", test=Namespace(test="x"))


def test_subsubcommand_default_config_repeated_keys(parser, subparser, tmp_cwd):
    defaults = tmp_cwd / "defaults.json"
    defaults.write_text('{"test":{"test":{"test":"value"}}}')
    parser.default_config_files = [defaults]
    subsubparser = ArgumentParser()
    subsubparser.add_argument("--test")
    subcommands1 = parser.add_subcommands()
    subcommands1.add_subcommand("test", subparser)
    subcommands2 = subparser.add_subcommands()
    subcommands2.add_subcommand("test", subsubparser)

    cfg = parser.parse_args([]).clone(with_meta=False)
    assert cfg.as_dict() == {"subcommand": "test", "test": {"subcommand": "test", "test": {"test": "value"}}}
    cfg = parser.parse_args(["test", "test", "--test=x"]).clone(with_meta=False)
    assert cfg.as_dict() == {"subcommand": "test", "test": {"subcommand": "test", "test": {"test": "x"}}}


def test_subcommand_required_arg_in_default_config(parser, subparser, tmp_cwd):
    config = {"output": "test", "prepare": {"media": "test"}}
    Path("config.yaml").write_text(json_or_yaml_dump(config))
    parser.default_config_files = ["config.yaml"]
    parser.add_argument("--output", required=True)
    subcommands = parser.add_subcommands()
    subparser = ArgumentParser()
    subparser.add_argument("--media", required=True)
    subcommands.add_subcommand("prepare", subparser)
    cfg = parser.parse_args([])
    assert str(cfg.__default_config__) == "config.yaml"
    assert cfg.clone(with_meta=False) == Namespace(output="test", prepare=Namespace(media="test"), subcommand="prepare")


class SubModel:
    def __init__(self, p1: int, p2: str = "-"):
        pass


class Model:
    def __init__(self, submodel: SubModel):
        self.submodel = submodel


def test_subcommand_default_config_add_subdefaults(parser, subparser, tmp_cwd):
    config = {
        "fit": {
            "model": {
                "class_path": f"{__name__}.Model",
                "init_args": {
                    "submodel": {
                        "class_path": f"{__name__}.SubModel",
                        "init_args": {"p1": 1},
                    }
                },
            }
        }
    }
    Path("config.json").write_text(json.dumps(config))
    parser.default_config_files = ["config.json"]
    subcommands = parser.add_subcommands()
    subparser = ArgumentParser()
    subparser.add_argument("--model", type=Model, required=True)
    subcommands.add_subcommand("fit", subparser)
    cfg = parser.parse_args([])
    assert cfg.fit.model.class_path == f"{__name__}.Model"
    assert list(cfg.fit.model.init_args.__dict__) == ["submodel"]
    assert cfg.fit.model.init_args.submodel.class_path == f"{__name__}.SubModel"
    assert cfg.fit.model.init_args.submodel.init_args == Namespace(p1=1, p2="-")
    init = parser.instantiate(cfg)
    assert isinstance(init.fit.model, Model)
    assert isinstance(init.fit.model.submodel, SubModel)


def test_subcommand_name_collision_with_option_string(parser, subparser):
    parser.add_argument("--typed", type=int, default=1)
    parser.add_argument("--info", dest="log_level", action="store_true", default=SUPPRESS)
    subcommands = parser.add_subcommands()
    subparser.add_argument("--info", dest="log_level", action="store_true", default=SUPPRESS)
    subcommands.add_subcommand("info", subparser)

    cfg = parser.parse_args(["info"])
    assert cfg.subcommand == "info"
    assert cfg.info == Namespace()
    assert "log_level" not in cfg


def test_subsubcommands_parse_args(subtests):
    parser_s1_a = ArgumentParser(exit_on_error=False)
    parser_s1_a.add_argument("--os1a", default="os1a_def")

    parser_s2_b = ArgumentParser(exit_on_error=False)
    parser_s2_b.add_argument("--os2b", default="os2b_def")

    parser = ArgumentParser(prog="app", exit_on_error=False)
    subcommands1 = parser.add_subcommands()
    subcommands1.add_subcommand("a", parser_s1_a)

    subcommands2 = parser_s1_a.add_subcommands()
    subcommands2.add_subcommand("b", parser_s2_b)

    with subtests.test("errors"):
        pytest.raises(ArgumentError, lambda: parser.parse_args([]))
        pytest.raises(ArgumentError, lambda: parser.parse_args(["a"]))

    with subtests.test("subsubcommand"):
        cfg = parser.parse_args(["a", "b"]).as_dict()
        assert cfg == {
            "subcommand": "a",
            "a": {"subcommand": "b", "os1a": "os1a_def", "b": {"os2b": "os2b_def"}},
        }

    with subtests.test("sub-optional"):
        cfg = parser.parse_args(["a", "--os1a=os1a_arg", "b"]).as_dict()
        assert cfg == {
            "subcommand": "a",
            "a": {"subcommand": "b", "os1a": "os1a_arg", "b": {"os2b": "os2b_def"}},
        }

    with subtests.test("subsub-optional"):
        cfg = parser.parse_args(["a", "b", "--os2b=os2b_arg"]).as_dict()
        assert cfg == {
            "subcommand": "a",
            "a": {"subcommand": "b", "os1a": "os1a_def", "b": {"os2b": "os2b_arg"}},
        }


def test_subsubcommands_wrong_add_order(parser):
    parser_s1_a = ArgumentParser()
    parser_s2_b = ArgumentParser()

    subcommands2 = parser_s1_a.add_subcommands()
    subcommands2.add_subcommand("b", parser_s2_b)

    subcommands1 = parser.add_subcommands()
    with pytest.raises(ValueError) as ctx:
        subcommands1.add_subcommand("a", parser_s1_a)
    ctx.match("Multiple levels of subcommands must be added in level order")


def test_subcommands_custom_instantiator(parser, subparser, subtests, clear_instantiators):
    subparser.add_argument("--cls", type=CustomInstantiationBase)
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("cmd", subparser)

    with subtests.test("main parser"):
        add_instantiator(instantiator("main parser"), CustomInstantiationBase)
        cfg = parser.parse_args(["cmd", "--cls", "CustomInstantiationBase"])
        init = parser.instantiate(cfg)
        assert isinstance(init.cmd.cls, CustomInstantiationBase)
        assert init.cmd.cls.call == "main parser"

    with subtests.test("subparser"):
        add_instantiator(instantiator("subparser"), CustomInstantiationBase)
        cfg = parser.parse_args(["cmd", "--cls", "CustomInstantiationBase"])
        init = parser.instantiate(cfg)
        assert isinstance(init.cmd.cls, CustomInstantiationBase)
        assert init.cmd.cls.call == "subparser"


def test_subsubcommand_default_env_true(parser, subparser, subsubparser):
    parser.default_env = True
    parser.env_prefix = "APP"
    subsubparser.add_argument("--v", type=int, default=1)
    subcommands1 = parser.add_subcommands()
    subcommands1.add_subcommand("s1", subparser)
    subcommands2 = subparser.add_subcommands()
    subcommands2.add_subcommand("s2", subsubparser)
    cfg = parser.parse_args(["s1", "s2"])
    assert cfg == Namespace(subcommand="s1", s1=Namespace(subcommand="s2", s2=Namespace(v=1)))

    with patch.dict(os.environ, {"APP_SUBCOMMAND": "s1", "APP_S1__SUBCOMMAND": "s2"}):
        cfg = parser.parse_args([])
    assert cfg == Namespace(subcommand="s1", s1=Namespace(subcommand="s2", s2=Namespace(v=1)))


@pytest.mark.parametrize("default_env", [True, False])
def test_subsubcommand_default_config_files(parser, subparser, subsubparser, default_env, tmp_cwd):
    config = {"val0": 123, "cmd1": {"val1": 456, "cmd2": {"val2": 789}}}
    Path("config.json").write_text(json.dumps(config))
    parser.default_env = default_env
    parser.default_config_files = ["config.json"]
    parser.add_argument("--val0")
    subparser.add_argument("--val1")
    subsubparser.add_argument("--val2")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("cmd1", subparser)
    subsubcommands = subparser.add_subcommands()
    subsubcommands.add_subcommand("cmd2", subsubparser)

    cfg = parser.parse_args([])
    assert cfg.clone(with_meta=False) == Namespace(
        val0=123, subcommand="cmd1", cmd1=Namespace(val1=456, subcommand="cmd2", cmd2=Namespace(val2=789))
    )


def test_subsubcommand_env_overrides_default_config(parser, subparser, subsubparser, tmp_cwd):
    config = {"cmd1": {"cmd2": {"flag": True}}}
    Path("config.json").write_text(json.dumps(config))
    parser.env_prefix = "APP"
    parser.default_env = True
    parser.default_config_files = ["config.json"]
    subsubparser.add_argument("--flag", action="store_true")

    subcommands = parser.add_subcommands(required=False)
    subcommands.add_subcommand("cmd1", subparser)
    subsubcommands = subparser.add_subcommands(required=False)
    subsubcommands.add_subcommand("cmd2", subsubparser)

    cfg = parser.parse_args(["cmd1", "cmd2"])
    assert cfg.cmd1.cmd2.flag is True

    with patch.dict(
        os.environ,
        {"APP_SUBCOMMAND": "cmd1", "APP_CMD1__SUBCOMMAND": "cmd2", "APP_CMD1__CMD2__FLAG": "false"},
    ):
        cfg = parser.parse_args([])
    assert cfg.cmd1.cmd2.flag is False


def test_subcommands_in_default_config_files(parser, subtests, tmp_cwd):
    parser.default_config_files = ["defaults.json"]
    subs = parser.add_subcommands(required=True, dest="sub")
    sub1 = ArgumentParser()
    sub1.add_argument("--sub1val")
    subs.add_subcommand("sub1", sub1)
    sub2 = ArgumentParser()
    sub2.add_argument("--sub2val")
    subs.add_subcommand("sub2", sub2)

    defaults: dict = {
        "sub1": {"sub1val": 2},
        "sub2": {"sub2val": 3},
    }
    Path("defaults.json").write_text(json.dumps(defaults))

    with subtests.test("choose subcommand defaults"):
        cfg = parser.parse_args(["sub1"])
        assert cfg.sub == "sub1"
        assert cfg.sub1 == Namespace(sub1val=2)
        assert "sub2" not in cfg
        cfg = parser.parse_args(["sub2"])
        assert cfg.sub == "sub2"
        assert cfg.sub2 == Namespace(sub2val=3)
        assert "sub1" not in cfg

    with subtests.test("no subcommand in defaults"):
        defaults["sub"] = "sub2"
        Path("defaults.json").write_text(json.dumps(defaults))
        err = get_parse_args_stderr(parser, [])
        assert (
            "Problem in default config file 'defaults.json': A specific "
            "subcommand can't be provided in defaults, got 'sub2'"
        ) in err
