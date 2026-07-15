from __future__ import annotations

import json
import os
import pickle
import sys
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from random import randint, shuffle
from typing import Union
from unittest.mock import patch

import pytest

from jsonargparse import (
    SUPPRESS,
    ActionConfigFile,
    ActionJsonnet,
    ActionJsonSchema,
    ActionParser,
    ArgumentError,
    ArgumentParser,
    Namespace,
    set_parsing_settings,
)
from jsonargparse._formatters import get_env_var
from jsonargparse._namespace import NSKeyError
from jsonargparse._optionals import jsonnet_support, jsonschema_support, pyyaml_available, ruamel_support
from jsonargparse.typing import Path_fc, Path_fr, path_type
from jsonargparse_tests.conftest import (
    capture_logs,
    get_parse_args_stderr,
    get_parse_args_stdout,
    get_parser_help,
    is_cpython,
    json_or_yaml_dump,
    json_or_yaml_load,
    responses_activate,
    skip_if_docstring_parser_unavailable,
    skip_if_fsspec_unavailable,
    skip_if_no_pyyaml,
    skip_if_not_posix,
    skip_if_responses_unavailable,
    skip_if_running_as_root,
    source_unavailable,
)


def test_add_argument_positional_with_default(parser):
    with pytest.raises(ValueError, match="Positional arguments not allowed to have a default value"):
        parser.add_argument("pos", default="abc")


def test_add_argument_positional_with_default_nargs_star(parser):
    parser.add_argument("pos", nargs="*", default=["abc"])
    assert parser.parse_args([]) == Namespace(pos=["abc"])
    assert parser.parse_args(["x"]) == Namespace(pos=["x"])
    assert parser.parse_args(["x", "y"]) == Namespace(pos=["x", "y"])


def test_add_argument_positional_with_default_nargs_question(parser):
    parser.add_argument("pos", nargs="?", default="abc")
    assert parser.parse_args([]) == Namespace(pos="abc")
    assert parser.parse_args(["x"]) == Namespace(pos="x")


def test_parse_args_simple(parser):
    parser.add_argument("--op", type=int)
    assert parser.parse_args(["--op=1"]) == Namespace(op=1)
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--op=1.1"]))


def test_parse_args_nested(parser):
    parser.add_argument("--l1.l2.op", type=float)
    assert parser.parse_args(["--l1.l2.op=2.1"]).l1.l2.op == 2.1
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--l1.l2.op=x"]))


def test_parse_args_unrecognized_arguments(parser):
    err = get_parse_args_stderr(parser, ["--unrecognized"])
    assert "unrecognized arguments:" in err


def test_parse_args_from_sys_argv(parser):
    parser.add_argument("--op", type=str)
    with patch("sys.argv", ["", "--op", "hello"]):
        assert parser.parse_args() == Namespace(op="hello")


def test_parse_args_invalid_args(parser):
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args([{}])
    ctx.match("expected to be strings")


def test_parse_args_base_namespace(parser):
    parser.add_argument("--op1")
    parser.add_argument("--op2")
    cfg = parser.parse_args(["--op1=abc"], Namespace(op2="xyz"))
    assert cfg == Namespace(op1="abc", op2="xyz")


def test_parse_args_unexpected_kwarg(parser):
    with pytest.raises(ValueError):
        parser.parse_args([], unexpected=True)


def test_parse_args_nargs_plus(parser):
    parser.add_argument("--val", nargs="+", type=int)
    assert [9] == parser.parse_args(["--val", "9"]).val
    assert [3, 6, 2] == parser.parse_args(["--val", "3", "6", "2"]).val
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--val"]))


def test_parse_args_nargs_asterisk(parser):
    parser.add_argument("--val", nargs="*", type=float)
    assert [5.2, 1.9] == parser.parse_args(["--val", "5.2", "1.9"]).val
    assert [] == parser.parse_args(["--val"]).val


def test_parse_args_nargs_questionmark(parser):
    parser.add_argument("--val", nargs="?", type=str)
    assert "~" == parser.parse_args(["--val", "~"]).val
    assert None is parser.parse_args(["--val"]).val


def test_parse_args_nargs_number(parser):
    parser.add_argument("--one", nargs=1)
    parser.add_argument("--two", nargs=2)
    assert parser.parse_args(["--one", "-"]) == Namespace(one=["-"], two=None)
    assert parser.parse_args(["--two", "q", "p"]) == Namespace(one=None, two=["q", "p"])
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--two", "-"]))


def test_parse_args_positional_nargs_questionmark(parser):
    parser.add_argument("pos1")
    parser.add_argument("pos2", nargs="?")
    with pytest.raises(ArgumentError, match="the following arguments are required: pos1"):
        parser.parse_args([])
    assert parser.parse_args(["v1"]) == Namespace(pos1="v1", pos2=None)
    assert parser.parse_args(["v1", "v2"]) == Namespace(pos1="v1", pos2="v2")


def test_parse_args_positional_nargs_plus(parser):
    parser.add_argument("pos1")
    parser.add_argument("pos2", nargs="+")
    with pytest.raises(ArgumentError, match="the following arguments are required: pos2"):
        parser.parse_args(["v1"])
    assert parser.parse_args(["v1", "v2", "v3"]) == Namespace(pos1="v1", pos2=["v2", "v3"])


def test_parse_args_missing_required_lists_all(parser):
    parser.add_argument("req_pos")
    parser.add_argument("--req_opt", required=True)
    with pytest.raises(TypeError, match="the following arguments are required: req_pos, req_opt"):
        parser.validate(Namespace())


def test_public_required_action_state(parser):
    action = parser.add_argument("--req_opt", required=True)
    assert action.required is True
    assert parser._extra_required_keys == set()


def test_parse_args_positional_config(parser):
    parser.add_argument("pos1")
    parser.add_argument("pos2", nargs="+")
    parser.add_argument("--cfg", action="config")
    cfg = parser.parse_args(["--cfg", '{"pos2": ["v2", "v3"]}', "v1"])
    assert cfg == Namespace(cfg=[None], pos1="v1", pos2=["v2", "v3"])


def test_parse_args_choices(parser):
    parser.add_argument("--ch1", choices="ABC")
    parser.add_argument("--ch2", type=str, choices=["v1", "v2"])
    cfg = parser.parse_args(["--ch1", "C", "--ch2", "v1"])
    assert cfg.as_dict() == {"ch1": "C", "ch2": "v1"}
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--ch1", "D"]))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--ch2", "v0"]))


def test_parse_args_choices_config(parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--ch1", choices="ABC")
    parser.add_argument("--ch2", type=str, choices=["v1", "v2"])
    assert parser.parse_args(['--cfg={"ch1": "B"}']).ch1 == "B"
    assert parser.parse_args(['--cfg={"ch2": "v2"}']).ch2 == "v2"
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--cfg={"ch1": "D"}']))
    pytest.raises(ArgumentError, lambda: parser.parse_args(['--cfg={"ch2": "v0"}']))


def test_parse_args_non_hashable_choice(parser):
    choices = {"A": 1, "B": 2}
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--ch1", choices=choices.keys())
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(['--cfg={"ch1": [1,2]}'])
    ctx.match("not among choices")


def test_parse_args_choices_nargs_plus(parser):
    parser.add_argument("--ch", nargs="+", choices=["A", "B"])
    assert ["A", "B"] == parser.parse_args(["--ch", "A", "B"]).ch
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--ch", "B", "X"])
    ctx.match("invalid choice")


def test_parse_args_choices_type_int(parser):
    parser.add_argument("--ch", type=int, choices=[0, 1])
    assert 0 == parser.parse_args(["--ch=0"]).ch


def test_parse_args_choices_type_union(parser):
    parser.add_argument("--ch", type=Union[int, str], choices=[0, 1, "x", "y"])
    assert 0 == parser.parse_args(["--ch=0"]).ch
    assert "x" == parser.parse_args(["--ch=x"]).ch


def test_parse_object_simple(parser):
    parser.add_argument("--op", type=int)
    assert parser.parse_object({"op": 1}) == Namespace(op=1)
    pytest.raises(ArgumentError, lambda: parser.parse_object({"op": 1.1}))
    pytest.raises(ArgumentError, lambda: parser.parse_object({"undefined": True}))


def test_parse_object_config(parser, tmp_cwd):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--a", type=int)
    parser.add_argument("--b", type=int)
    path = Path("config.json")
    path.write_text('{"a": 1, "b": 2}')
    cfg = parser.parse_object({"b": 0, "cfg": str(path), "a": 3})
    popped_cfg = cfg.pop("cfg")
    assert popped_cfg[0].relative == "config.json"
    assert cfg == Namespace(a=3, b=2)


def test_parse_object_nested(parser):
    parser.add_argument("--l1.l2.op", type=float)
    assert parser.parse_object({"l1": {"l2": {"op": 2.1}}}).l1.l2.op == 2.1
    pytest.raises(ArgumentError, lambda: parser.parse_object({"l1": {"l2": {"op": "x"}}}))


def test_env_prefix_from_prog_with_dashes():
    parser = ArgumentParser(prog="cli-name")
    action = parser.add_argument("--arg")
    assert get_env_var(parser, action) == "CLI_NAME_ARG"


def test_parse_env_simple():
    parser = ArgumentParser(prog="app", exit_on_error=False)
    parser.add_argument("--op", type=int)
    with patch.dict(os.environ, {"APP_OP": "1"}):
        assert parser.parse_env() == Namespace(op=1)
    pytest.raises(ArgumentError, lambda: parser.parse_env({"APP_OP": "1.1"}))


def test_parse_env_nested():
    parser = ArgumentParser(prog="app", exit_on_error=False)
    parser.add_argument("--l1.l2.op", type=float)
    assert parser.parse_env({"APP_L1__L2__OP": "2.1"}).l1.l2.op == 2.1
    pytest.raises(ArgumentError, lambda: parser.parse_env({"APP_L1__L2__OP": "x"}))


def test_parse_env_config(parser):
    parser.env_prefix = "app"
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--l1.num", type=int)
    cfg = parser.parse_env({"APP_CFG": '{"l1": {"num": 1}}'})
    assert cfg.cfg == [None]
    assert cfg.l1 == Namespace(num=1)
    pytest.raises(ArgumentError, lambda: parser.parse_env({"APP_CFG": '{"undefined": True}'}))


def test_parse_env_positional():
    parser = ArgumentParser(prog="app", exit_on_error=False, default_env=True)
    parser.add_argument("pos", type=int)
    with patch.dict(os.environ, {"APP_POS": "1"}):
        assert parser.parse_env() == Namespace(pos=1)
    with pytest.raises(ArgumentError, match="Got value: 1.1"):
        parser.parse_env({"APP_POS": "1.1"})


def test_parse_env_positional_nargs_plus(parser):
    parser.env_prefix = "app"
    parser.add_argument("req", nargs="+")
    assert parser.parse_env({"APP_REQ": "abc"}).req == ["abc"]
    assert parser.parse_env({"APP_REQ": '["abc", "xyz"]'}).req == ["abc", "xyz"]
    assert parser.parse_env({"APP_REQ": '[""","""]'}).req == ['[""","""]']


@pytest.mark.parametrize(
    ("env", "key", "expected"),
    [
        ({"APP_FLAG_TRUE": "true"}, "flag_true", True),
        ({"APP_FLAG_TRUE": "false"}, "flag_true", False),
        ({"APP_FLAG_FALSE": "false"}, "flag_false", False),
        ({"APP_FLAG_FALSE": "true"}, "flag_false", True),
    ],
)
def test_parse_env_store_true_false(parser, env, key, expected):
    parser.env_prefix = "app"
    parser.add_argument("--flag_true", action="store_true")
    parser.add_argument("--flag_false", action="store_false")
    assert parser.parse_args([]) == Namespace(flag_true=False, flag_false=True)
    assert parser.get_defaults() == Namespace(flag_true=False, flag_false=True)
    assert getattr(parser.parse_env(env), key) is expected
    with pytest.raises(ArgumentError, match="Invalid boolean value for environment variable APP_FLAG_TRUE: not_bool"):
        parser.parse_env({"APP_FLAG_TRUE": "not_bool"})
    with pytest.raises(ArgumentError, match="Invalid boolean value for environment variable APP_FLAG_FALSE: not_bool"):
        parser.parse_env({"APP_FLAG_FALSE": "not_bool"})


def test_default_env_property():
    parser = ArgumentParser()
    assert False is parser.default_env
    parser.default_env = True
    assert True is parser.default_env
    parser = ArgumentParser(default_env=True)
    assert True is parser.default_env
    parser.default_env = False
    assert False is parser.default_env
    with pytest.raises(ValueError) as ctx:
        parser.default_env = "invalid"
    ctx.match("default_env expects a boolean")


@pytest.mark.parametrize(
    ("env_value", "constructor_default", "assigned_default", "expected_default"),
    [
        ("True", False, False, True),
        ("False", True, True, False),
    ],
)
def test_default_env_override(env_value, constructor_default, assigned_default, expected_default):
    with patch.dict(os.environ, {"JSONARGPARSE_DEFAULT_ENV": env_value}):
        parser = ArgumentParser(default_env=constructor_default)
        assert parser.default_env is expected_default
        parser.default_env = assigned_default
        assert parser.default_env is expected_default


def test_env_prefix_true():
    with patch("sys.argv", ["fake.py"]), patch.dict(sys.modules, {"__main__": {}}):
        parser = ArgumentParser(env_prefix=True, default_env=True, exit_on_error=False)
        assert parser.prog == "fake.py"
        parser.add_argument("--test_arg", type=str, required=True)

        with patch.dict(os.environ, {"TEST_ARG": "one"}):
            pytest.raises(ArgumentError, lambda: parser.parse_args([]))

        with patch.dict(os.environ, {"FAKE_TEST_ARG": "one"}):
            cfg = parser.parse_args([])
        assert "one" == cfg.test_arg


def test_env_prefix_false():
    parser = ArgumentParser(env_prefix=False, default_env=True)
    parser.add_argument("--test_arg", type=str, required=True)
    with patch.dict(os.environ, {"TEST_ARG": "one"}):
        cfg = parser.parse_args([])
    assert "one" == cfg.test_arg


def test_env_properties_set_invalid(parser):
    with pytest.raises(ValueError):
        parser.default_env = "invalid"
    with pytest.raises(ValueError):
        parser.env_prefix = lambda: "invalid"


def test_parse_string_simple(parser):
    parser.add_argument("--op", type=int)
    assert parser.parse_string('{"op": 1}').op == 1


@pytest.mark.parametrize(
    "config",
    [
        '{"op": 1.1}',
        '{"undefined": true}',
        '"""',
        "not a dict",
    ],
)
def test_parse_string_simple_errors(parser, config):
    with pytest.raises(ArgumentError):
        parser.parse_string(config)


def test_parse_string_nested(parser):
    parser.add_argument("--l1.l2.op", type=float)
    assert parser.parse_string('{"l1": {"l2": {"op": 2.1}}}').l1.l2.op == 2.1
    pytest.raises(ArgumentError, lambda: parser.parse_string('{"l1": {"l2": {"op": "x"}}}'))


def test_parse_path_simple(parser, tmp_cwd):
    parser.add_argument("--op", type=int)
    path = Path("config.json")
    path.write_text('{"op": 1}')
    assert parser.parse_path(path) == Namespace(op=1)


@pytest.mark.parametrize(
    "config",
    [
        '{"op": 1.1}',
        '{"undefined": true}',
    ],
)
def test_parse_path_simple_errors(parser, tmp_cwd, config):
    parser.add_argument("--op", type=int)
    path = Path("config.json")
    path.write_text(config)
    with pytest.raises(ArgumentError):
        parser.parse_path(path)


def test_parse_path_defaults(parser, tmp_cwd):
    parser.add_argument("--op1", type=int, default=1)
    parser.add_argument("--op2", type=float, default=2.3)
    path = Path("config.json")
    path.write_text('{"op1": 2}')
    assert parser.parse_path(path, defaults=True) == Namespace(op1=2, op2=2.3)
    assert parser.parse_path(path, defaults=False) == Namespace(op1=2)
    path.write_text('{"op2": 4.5}')
    assert parser.parse_path(path, defaults=False) == Namespace(op2=4.5)


@skip_if_not_posix
@skip_if_running_as_root
def test_parse_path_file_not_readable(parser, tmp_cwd):
    config_path = Path("config.json")
    config_path.touch()
    config_path.chmod(0)
    pytest.raises(TypeError, lambda: parser.parse_path(config_path))


def test_precedence_of_sources(tmp_cwd, subtests):
    input1_config_file = tmp_cwd / "input1.yaml"
    input2_config_file = tmp_cwd / "input2.yaml"
    default_config_file = tmp_cwd / "default.yaml"

    parser = ArgumentParser(prog="app", default_env=True, default_config_files=[default_config_file])
    parser.add_argument("--op1", default="from parser default")
    parser.add_argument("--op2")
    parser.add_argument("--cfg", action="config")

    input1_config_file.write_text(json_or_yaml_dump({"op1": "from input config file"}))
    input2_config_file.write_text(json_or_yaml_dump({"op2": "unused"}))

    # parse_env precedence
    with subtests.test("parse_env parser default"):
        assert "from parser default" == parser.parse_env({}).op1
    with subtests.test("parse_env default config file"):
        default_config_file.write_text(json_or_yaml_dump({"op1": "from default config file"}))
        assert "from default config file" == parser.parse_env({}).op1
    with subtests.test("parse_env environment config string"):
        env = {"APP_CFG": '{"op1": "from env config"}'}
        assert "from env config" == parser.parse_env(env).op1
    with subtests.test("parse_env environment variable"):
        env["APP_OP1"] = "from env var"
        assert "from env var" == parser.parse_env(env).op1
    default_config_file.unlink()

    # parse_path precedence
    with subtests.test("parse_path parser default"):
        assert "from parser default" == parser.parse_path(input2_config_file).op1
    with subtests.test("parse_path default config file"):
        default_config_file.write_text(json_or_yaml_dump({"op1": "from default config file"}))
        assert "from default config file" == parser.parse_path(input2_config_file).op1
    env = {"APP_CFG": str(input1_config_file)}
    with subtests.test("parse_path environment config file"), patch.dict(os.environ, env):
        assert "from input config file" == parser.parse_path(input2_config_file).op1
    env["APP_OP1"] = "from env var"
    with subtests.test("parse_path environment variable"), patch.dict(os.environ, env):
        assert "from env var" == parser.parse_path(input2_config_file).op1
    env["APP_CFG"] = str(input2_config_file)
    with subtests.test("parse_path input config file"), patch.dict(os.environ, env):
        assert "from input config file" == parser.parse_path(input1_config_file).op1
    default_config_file.unlink()

    # parse_args precedence
    with subtests.test("parse_args parser default"):
        assert "from parser default" == parser.parse_args([]).op1
    with subtests.test("parse_args default config file"):
        default_config_file.write_text(json_or_yaml_dump({"op1": "from default config file"}))
        assert "from default config file" == parser.parse_args([]).op1
    env = {"APP_CFG": str(input1_config_file)}
    with subtests.test("parse_args environment config file"), patch.dict(os.environ, env):
        assert "from input config file" == parser.parse_args([]).op1
    env["APP_OP1"] = "from env var"
    with subtests.test("parse_args environment variable"), patch.dict(os.environ, env):
        assert "from env var" == parser.parse_args([]).op1
    env["APP_CFG"] = str(input2_config_file)
    with subtests.test("parse_args input argument"), patch.dict(os.environ, env):
        assert "from arg" == parser.parse_args(["--op1", "from arg"]).op1
    with subtests.test("parse_args argument override config"), patch.dict(os.environ, env):
        assert "from arg" == parser.parse_args([f"--cfg={input1_config_file}", "--op1=from arg"]).op1
    with subtests.test("parse_args config override argument"), patch.dict(os.environ, env):
        assert "from input config file" == parser.parse_args(["--op1=from arg", f"--cfg={input1_config_file}"]).op1

    with subtests.test("parse_args config paths"), patch.dict(os.environ, env):
        cfg = parser.parse_args([f"--cfg={input1_config_file}"])
    config_paths = parser.get_config_files(cfg)
    assert str(default_config_file) == str(config_paths[0])
    assert str(input2_config_file) == str(config_paths[1])  # APP_CFG
    assert str(input1_config_file) == str(config_paths[2])  # --cfg


def test_non_positional_required(parser, subtests):
    group = parser.add_argument_group("Group 1")
    group.add_argument("--req1", required=True)
    parser.add_argument("--lev1.req2", required=True)

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "--req1 REQ1 --lev1.req2 REQ2" in help_str
        assert "--lev1.req2 REQ2  (required)" in help_str

    with subtests.test("parse_env"):
        parser.env_prefix = "APP"
        cfg = parser.parse_env({"APP_REQ1": "val5", "APP_LEV1__REQ2": "val6"})
        assert cfg == Namespace(lev1=Namespace(req2="val6"), req1="val5")
        pytest.raises(ArgumentError, lambda: parser.parse_env({}))

    with subtests.test("parse_string"):
        cfg = parser.parse_string('{"req1":"val3","lev1":{"req2":"val4"}}')
        assert cfg == Namespace(lev1=Namespace(req2="val4"), req1="val3")
        pytest.raises(ArgumentError, lambda: parser.parse_string('{"lev1":{"req2":"val4"}}'))

    with subtests.test("parse_args"):
        cfg = parser.parse_args(["--req1", "val1", "--lev1.req2", "val2"])
        assert cfg == Namespace(lev1=Namespace(req2="val2"), req1="val1")
        pytest.raises(ArgumentError, lambda: parser.parse_args(["--req1", "val1"]))

    with subtests.test("parse_args config"):
        parser.add_argument("--cfg", action="config")
        cfg = parser.parse_args(["--cfg", '{"req1":"val1","lev1":{"req2":"val2"}}'])
        assert cfg == Namespace(cfg=[None], lev1=Namespace(req2="val2"), req1="val1")


@pytest.fixture
def dump_parser(parser):
    parser.add_argument("--op1", default=123)
    parser.add_argument("--op2", default="abc")
    return parser


def test_dump_complete(dump_parser):
    cfg1 = dump_parser.get_defaults()
    cfg2 = dump_parser.parse_string(dump_parser.dump(cfg1))
    assert cfg1 == cfg2


def test_dump_incomplete(dump_parser):
    dump = dump_parser.dump(Namespace(op1=456))
    assert {"op1": 456} == json_or_yaml_load(dump)


@pytest.mark.skipif(not is_cpython, reason="requires __setattr__ insertion order")
def test_dump_formats(dump_parser):
    cfg = dump_parser.get_defaults()
    if pyyaml_available:
        assert dump_parser.dump(cfg) == "op1: 123\nop2: abc\n"
        assert dump_parser.dump(cfg, format="yaml") == dump_parser.dump(cfg)
    assert dump_parser.dump(cfg, format="json") == '{"op1":123,"op2":"abc"}'
    assert dump_parser.dump(cfg, format="json_indented") == '{\n  "op1": 123,\n  "op2": "abc"\n}\n'
    pytest.raises(ValueError, lambda: dump_parser.dump(cfg, format="invalid"))


def test_dump_skip_default_simple(dump_parser):
    dump = dump_parser.dump(dump_parser.get_defaults(), skip_default=True)
    expected = "{}\n" if pyyaml_available else "{}"
    assert dump == expected
    dump = dump_parser.dump(Namespace(op1=123, op2="xyz"), skip_default=True)
    expected = "op2: xyz\n" if pyyaml_available else '{"op2":"xyz"}'
    assert dump == expected


def test_dump_skip_default_nested(parser):
    parser.add_argument("--g1.op1", type=int, default=123)
    parser.add_argument("--g1.op2", type=str, default="abc")
    parser.add_argument("--g2.op1", type=int, default=987)
    parser.add_argument("--g2.op2", type=str, default="xyz")
    dump = parser.dump(parser.get_defaults(), skip_default=True)
    expected = "{}\n" if pyyaml_available else "{}"
    assert dump == expected
    dump = parser.dump(parser.parse_args(["--g1.op1=0"]), skip_default=True)
    expected = "g1:\n  op1: 0\n" if pyyaml_available else '{"g1":{"op1":0}}'
    assert dump == expected
    dump = parser.dump(parser.parse_args(["--g2.op2=pqr"]), skip_default=True)
    expected = "g2:\n  op2: pqr\n" if pyyaml_available else '{"g2":{"op2":"pqr"}}'
    assert dump == expected


def test_dump_skip_validation(parser):
    parser.add_argument("--key", type=int)
    cfg = Namespace(key="-")
    with pytest.raises(TypeError):
        parser.dump(cfg)
    dump = parser.dump(cfg, skip_validation=True)
    assert "-" in dump


def test_dump_unexpected_kwarg(parser):
    parser.add_argument("--key", type=int)
    cfg = Namespace(key="-")
    with pytest.raises(ValueError, match="Unexpected keyword parameter"):
        parser.dump(cfg, unexpected=True)


@skip_if_no_pyyaml
def test_dump_order(parser, subtests):
    args = {}
    for num in range(50):
        args[num] = "".join(chr(randint(97, 122)) for _ in range(8))

    for num in range(len(args)):
        parser.add_argument("--" + args[num], default=num)

    with subtests.test("get_defaults"):
        cfg = parser.get_defaults()
        dump = parser.dump(cfg)
        assert dump == "\n".join(v + ": " + str(n) for n, v in args.items()) + "\n"

    with subtests.test("parse_string"):
        rand = list(range(len(args)))
        shuffle(rand)
        yaml = "\n".join(args[n] + ": " + str(n) for n in rand) + "\n"
        cfg = parser.parse_string(yaml)
        dump = parser.dump(cfg)
        assert dump == "\n".join(v + ": " + str(n) for n, v in args.items()) + "\n"


def test_dump_comments_not_supported(parser):
    parser.parser_mode = "json"
    parser.add_argument("--op", type=int, default=1)
    cfg = parser.get_defaults()
    with pytest.raises(ValueError, match="Dumping with comments is not supported for format 'json'"):
        parser.dump(cfg, with_comments=True)


@skip_if_no_pyyaml
def test_dump_comments_missing_ruamel(parser):
    parser.add_argument("--op", type=int, default=1)
    cfg = parser.get_defaults()
    with patch.dict("jsonargparse._loaders_dumpers.dumpers") as dumpers:
        dumpers.pop("yaml_comments", None)
        with pytest.raises(ValueError, match="ruamel.yaml is required for dumping YAML with comments"):
            parser.dump(cfg, with_comments=True)


@pytest.fixture
def parser_schema_jsonnet(parser, example_parser):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--subparser", action=ActionParser(parser=example_parser))
    if jsonschema_support:
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
        }
        parser.add_argument(
            "--schema",
            default={"a": 1, "b": 2},
            action=ActionJsonSchema(schema=schema),
        )
    if jsonnet_support:
        parser.add_argument(
            "--jsonnet",
            default={"c": 3, "d": 4},
            action=ActionJsonnet(ext_vars=None),
        )
    expected = parser.parse_args(["--subparser.bool=false", "--subparser.nums.val1=3"])
    subparser_body = json_or_yaml_dump(expected.subparser.as_dict())
    schema_body = json.dumps(expected.schema) if jsonschema_support else ""
    jsonnet_body = json.dumps(expected.jsonnet) if jsonnet_support else ""
    return parser, expected, subparser_body, schema_body, jsonnet_body


@skip_if_responses_unavailable
@responses_activate
def test_parse_args_url_config(parser_schema_jsonnet):
    import responses

    set_parsing_settings(config_read_mode_urls_enabled=True)
    parser, expected, subparser_body, schema_body, jsonnet_body = parser_schema_jsonnet

    base_url = "http://jsonargparse.com/"
    main_config = {"subparser": f"{base_url}subparser.yaml"}
    if jsonschema_support:
        main_config["schema"] = f"{base_url}schema.yaml"
    if jsonnet_support:
        main_config["jsonnet"] = f"{base_url}jsonnet.yaml"
    main_body = json_or_yaml_dump(main_config)

    for name, body in [
        ("main.yaml", main_body),
        ("subparser.yaml", subparser_body),
        ("schema.yaml", schema_body),
        ("jsonnet.yaml", jsonnet_body),
    ]:
        responses.add(responses.GET, base_url + name, status=200, body=body)
        responses.add(responses.HEAD, base_url + name, status=200)

    cfg = parser.parse_args([f"--cfg={base_url}main.yaml"]).clone(with_meta=False)
    assert expected.subparser == cfg.subparser
    if jsonschema_support:
        assert expected.schema == cfg.schema
    if jsonnet_support:
        assert expected.jsonnet == cfg.jsonnet

    set_parsing_settings(config_read_mode_urls_enabled=False)


def test_save_multifile(parser_schema_jsonnet, subtests, tmp_cwd):
    parser, expected, subparser_body, schema_body, jsonnet_body = parser_schema_jsonnet

    in_dir = tmp_cwd / "input"
    out_dir = tmp_cwd / "output"
    in_dir.mkdir()
    out_dir.mkdir()
    main_file_in = in_dir / "main.yaml"
    subparser_file_in = in_dir / "subparser.yaml"
    schema_file_in = in_dir / "schema.json"
    jsonnet_file_in = in_dir / "jsonnet.json"
    main_file_out = out_dir / "main.yaml"
    subparser_file_out = out_dir / "subparser.yaml"
    schema_file_out = out_dir / "schema.json"
    jsonnet_file_out = out_dir / "jsonnet.json"

    main_config = {"subparser": "subparser.yaml"}
    if jsonschema_support:
        main_config["schema"] = "schema.json"
    if jsonnet_support:
        main_config["jsonnet"] = "jsonnet.json"
    main_file_in.write_text(json_or_yaml_dump(main_config))
    subparser_file_in.write_text(subparser_body)
    if jsonschema_support:
        schema_file_in.write_text(schema_body)
    if jsonnet_support:
        jsonnet_file_in.write_text(jsonnet_body)

    def rm_out_files():
        for file in [main_file_out, subparser_file_out, schema_file_out, jsonnet_file_out]:
            if file.is_file():
                file.unlink()

    with subtests.test("parse_path with metadata"):
        cfg1 = parser.parse_path(main_file_in).clone(with_meta=True)
        assert expected == cfg1.clone(with_meta=False)
        assert str(cfg1.subparser["__path__"]) == "subparser.yaml"
        if jsonschema_support:
            assert str(cfg1.schema["__path__"]) == "schema.json"
        if jsonnet_support:
            assert str(cfg1.jsonnet["__path__"]) == "jsonnet.json"

    with subtests.test("save with metadata (multi-file)"):
        parser.save(cfg1, main_file_out)
        assert subparser_file_out.is_file()
        if jsonschema_support:
            assert schema_file_out.is_file()
        if jsonnet_support:
            assert jsonnet_file_out.read_text() == '{"c": 3, "d": 4}'
        cfg2 = parser.parse_path(main_file_out).clone(with_meta=False)
        assert expected == cfg2

    with subtests.test("save without metadata (single-file)"):
        rm_out_files()
        parser.save(cfg1, main_file_out, multifile=False)
        cfg3 = parser.parse_path(main_file_out).clone(with_meta=False)
        assert expected == cfg3

    if jsonschema_support:
        with subtests.test("save jsonschema output"):
            rm_out_files()
            schema_yaml_out = out_dir / "schema.yaml"
            cfg1.schema["__path__"] = Path_fc(schema_yaml_out)
            parser.save(cfg1, main_file_out, multifile=True)
            assert json_or_yaml_load(schema_yaml_out.read_text()) == {"a": 1, "b": 2}


class ListItem:
    def __init__(self, a: int, b: str):  # pragma: no cover
        self.a = a
        self.b = b


def test_save_multifile_list(parser, tmp_cwd):
    in_dir = tmp_cwd / "input"
    out_dir = tmp_cwd / "output"
    in_dir.mkdir()
    out_dir.mkdir()
    main_file_in = in_dir / "main.yaml"
    main_file_out = out_dir / "main.yaml"
    item_1_file_in = in_dir / "item1.yaml"
    item_1_file_out = out_dir / "item1.yaml"
    item_2_file_in = in_dir / "item2.yaml"
    item_2_file_out = out_dir / "item2.yaml"

    main_content = {"items": ["item1.yaml", "item2.yaml"]}
    main_file_in.write_text(json_or_yaml_dump(main_content))
    item_1_file_in.write_text(json_or_yaml_dump({"a": 1, "b": "x"}))
    item_2_file_in.write_text(json_or_yaml_dump({"a": 2, "b": "y"}))

    parser.add_argument("--config", action="config")
    parser.add_argument(
        "--items",
        nargs="+",
        type=ListItem,
        required=True,
        sub_configs=True,
    )

    cfg = parser.parse_args([f"--config={main_file_in}"])
    parser.save(cfg, main_file_out)
    assert json_or_yaml_load(main_file_out.read_text()) == main_content
    item_1_expected = {"class_path": f"{__name__}.ListItem", "init_args": {"a": 1, "b": "x"}}
    assert json_or_yaml_load(item_1_file_out.read_text()) == item_1_expected
    item_2_expected = {"class_path": f"{__name__}.ListItem", "init_args": {"a": 2, "b": "y"}}
    assert json_or_yaml_load(item_2_file_out.read_text()) == item_2_expected


def test_save_overwrite(example_parser, tmp_cwd):
    cfg = example_parser.parse_args(["--nums.val1=7"])
    example_parser.save(cfg, "config.yaml")
    with pytest.raises(ValueError) as ctx:
        example_parser.save(cfg, "config.yaml")
    ctx.match("Refusing to overwrite")
    example_parser.save(cfg, "config.yaml", overwrite=True)


def test_save_subconfig_overwrite(parser, example_parser, tmp_cwd):
    Path("subparser.yaml").write_text(example_parser.dump(example_parser.get_defaults()))
    parser.add_argument("--subparser", action=ActionParser(parser=example_parser))
    cfg = parser.get_defaults()
    cfg.subparser.__path__ = Path_fr("subparser.yaml")
    with pytest.raises(ValueError) as ctx:
        parser.save(cfg, "main.yaml")
    ctx.match("Refusing to overwrite")
    parser.save(cfg, "main.yaml", overwrite=True)


def test_save_invalid_format(example_parser, tmp_cwd):
    cfg = example_parser.parse_args(["--nums.val2=-1.2"])
    with pytest.raises(ValueError) as ctx:
        example_parser.save(cfg, "invalid_format.yaml", format="invalid")
    ctx.match("Unknown output format")


def test_save_path_content(parser, tmp_cwd):
    parser.add_argument("--the.path", type=Path_fr)

    Path("pathdir").mkdir()
    Path("outdir").mkdir()
    in_file = Path("pathdir", "file.txt")
    out_yaml = Path("outdir", "saved.yaml")
    out_file = Path("outdir", "file.txt")
    in_file.write_text("file content")

    cfg = parser.parse_args([f"--the.path={in_file}"])
    parser.save_path_content.add("the.path")
    parser.save(cfg, out_yaml)

    expected = "the:\n  path: file.txt\n" if pyyaml_available else '{"the":{"path":"file.txt"}}'
    assert out_yaml.read_text() == expected
    assert out_file.read_text() == "file content"


@skip_if_fsspec_unavailable
def test_save_fsspec(example_parser):
    cfg = example_parser.parse_args(["--nums.val1=5"])
    example_parser.save(cfg, "memory://config.yaml", multifile=False)
    path = path_type("sr")("memory://config.yaml")
    assert cfg == example_parser.parse_string(path.read_text())

    with pytest.raises(NotImplementedError) as ctx:
        example_parser.save(cfg, "memory://config.yaml", multifile=True)
    ctx.match("multifile=True not supported")


@pytest.fixture
def print_parser(parser, subparser):
    parser.description = "cli tool"
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--v0", help=SUPPRESS, default="0")
    parser.add_argument("--v1", help="Option v1.", default=1)
    parser.add_argument("--g1.v2", help="Option v2.", default="2")
    subparser.add_argument("--v3")
    parser.add_argument("--g2", action=ActionParser(parser=subparser))
    return parser


def test_print_config_normal(print_parser):
    out = get_parse_args_stdout(print_parser, ["--print_config"])
    assert json_or_yaml_load(out) == {"g1": {"v2": "2"}, "g2": {"v3": None}, "v1": 1}


def test_print_config_skip_unset(print_parser):
    out = get_parse_args_stdout(print_parser, ["--print_config=skip_unset"])
    assert json_or_yaml_load(out) == {"g1": {"v2": "2"}, "g2": {}, "v1": 1}


@pytest.mark.skipif(not ruamel_support, reason="ruamel.yaml package is required")
@skip_if_docstring_parser_unavailable
def test_print_config_comments(print_parser):
    help_str = get_parser_help(print_parser)
    assert "comments," in help_str
    out = get_parse_args_stdout(print_parser, ["--print_config=comments"])
    assert "# cli tool" in out
    assert "# Option v1. (default: 1)" in out
    assert "# Option v2. (default: 2)" in out


@pytest.mark.skipif(ruamel_support, reason="ruamel.yaml package should not be installed")
def test_print_config_comments_unavailable(print_parser):
    help_str = get_parser_help(print_parser)
    assert "comments," not in help_str
    with pytest.raises(ArgumentError, match='Invalid option "comments"'):
        get_parse_args_stdout(print_parser, ["--print_config=comments"])


def test_print_config_invalid_flag(print_parser):
    with pytest.raises(ArgumentError) as ctx:
        print_parser.parse_args(["--print_config=invalid"])
    ctx.match('Invalid option "invalid"')


def test_print_config_empty_default_config_file(print_parser, tmp_cwd):
    default_config_file = tmp_cwd / "defaults.yaml"
    default_config_file.touch()
    print_parser.default_config_files = [default_config_file]
    out = get_parse_args_stdout(print_parser, ["--print_config"])
    assert json_or_yaml_load(out) == {"g1": {"v2": "2"}, "g2": {"v3": None}, "v1": 1}


def test_print_config_reuse_name():
    parser = ArgumentParser(exit_on_error=False, print_config="--print_%s")
    parser.add_argument("--conf", action="config")
    parser.add_argument("--x", default=1)
    out = get_parse_args_stdout(parser, ["--print_conf"])
    assert json_or_yaml_load(out) == {"x": 1}


class Subclass:
    pass


def test_default_config_files(parser, subtests, tmp_cwd):
    default_config_file = tmp_cwd / "defaults.yaml"
    default_config_file.write_text(json_or_yaml_dump({"op1": "from default config file"}))

    parser.default_config_files = [default_config_file]
    parser.add_argument("--op1", default="from parser default")
    parser.add_argument("--op2", default="from parser default")

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "default values below are the ones overridden" in help_str
        assert "from default config file" in help_str
        assert "from parser default" in help_str

    with subtests.test("get_defaults"):
        cfg = parser.get_defaults()
        assert "from default config file" == cfg.op1
        assert "from parser default" == cfg.op2

    with subtests.test("get_default"):
        assert parser.get_default("op1") == "from default config file"
        parser.add_subclass_arguments(Subclass, "cls")
        assert parser.get_default("cls") is None

    with subtests.test("set invalid"):
        with pytest.raises(ValueError) as ctx:
            parser.default_config_files = False
        assert "default_config_files expects None or List[str | os.PathLike]." == str(ctx.value)


def test_default_config_file_help_message_no_existing(parser, tmp_cwd):
    parser.default_config_files = ["defaults.yaml"]
    help_str = get_parser_help(parser)
    assert "no existing default config file" in help_str


def test_default_config_file_invalid_value(parser, tmp_cwd):
    default_config_file = Path("defaults.yaml")
    default_config_file.write_text(json_or_yaml_dump({"op2": "v2"}))

    parser.default_config_files = [default_config_file]
    parser.add_argument("--op1", default="from default")

    with pytest.raises(ArgumentError) as ctx:
        parser.get_default("op1")
    ctx.match("Problem in default config file")

    help_str = get_parser_help(parser)
    assert "tried getting defaults considering default_config_files but failed" in help_str.replace("\n", " ")


@skip_if_not_posix
@skip_if_running_as_root
def test_default_config_file_unreadable(parser, tmp_cwd):
    default_config_file = Path("defaults.yaml")
    default_config_file.write_text(json_or_yaml_dump({"op1": "from config"}))

    parser.default_config_files = [default_config_file]
    parser.add_argument("--op1", default="from default")

    assert parser.get_default("op1") == "from config"
    default_config_file.chmod(0)
    assert parser.get_default("op1") == "from default"


def test_default_config_files_pattern(parser, subtests, tmp_cwd):
    default_configs_pattern = tmp_cwd / "defaults_*.yaml"
    parser.default_config_files = [default_configs_pattern]
    parser.add_argument("--op1", default="from default")
    parser.add_argument("--op2", default="from default")

    with subtests.test("one config"):
        config_1 = tmp_cwd / "defaults_1.yaml"
        config_1.write_text(json_or_yaml_dump({"op1": "from config 1", "op2": "from config 1"}))

        cfg = parser.get_defaults()
        assert cfg.op1 == "from config 1"
        assert cfg.op2 == "from config 1"
        assert str(cfg.__default_config__) == str(config_1)

    with subtests.test("two configs"):
        config_2 = tmp_cwd / "defaults_2.yaml"
        config_2.write_text(json_or_yaml_dump({"op1": "from config 2"}))

        cfg = parser.get_defaults()
        assert cfg.op1 == "from config 2"
        assert cfg.op2 == "from config 1"
        assert list(map(str, cfg.__default_config__)) == list(map(str, [config_1, config_2]))

    with subtests.test("three configs"):
        config_0 = tmp_cwd / "defaults_0.yaml"
        config_0.write_text(json_or_yaml_dump({"op2": "from config 0"}))

        cfg = parser.get_defaults()
        assert cfg.op1 == "from config 2"
        assert cfg.op2 == "from config 1"
        assert list(map(str, cfg.__default_config__)) == list(map(str, [config_0, config_1, config_2]))

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "defaults_*.yaml" in help_str
        assert "defaults_0.yaml" in help_str
        assert "defaults_1.yaml" in help_str
        assert "defaults_2.yaml" in help_str


def test_named_argument_groups(parser):
    parser.add_argument_group("Group 1", name="group1")
    parser.add_argument_group("Group 2", name="group2")
    assert {"group1", "group2"} == set(parser.groups)
    with pytest.raises(ValueError) as ctx:
        parser.add_argument_group("Bad", name="group1")
    ctx.match("Group with name group1 already exists")


def test_set_get_defaults_single(parser):
    parser.add_argument("--v1")
    parser.set_defaults(v1=1)
    assert parser.get_default("v1") == 1


def test_set_get_defaults_multiple(parser, subparser, subtests):
    parser.add_argument("--v1", default="1")
    parser.add_argument("--g1.v2", default="2")
    subparser.add_argument("--g2.v3", default="3")
    parser.add_argument("--n", action=ActionParser(parser=subparser))

    with subtests.test("set_defaults"):
        parser.set_defaults({"g1.v2": "b", "n.g2.v3": "c"}, v1="a")

    with subtests.test("get_defaults"):
        cfg = parser.get_defaults()
        assert cfg.as_dict() == {"v1": "a", "g1": {"v2": "b"}, "n": {"g2": {"v3": "c"}}}

    with subtests.test("get_default"):
        assert parser.get_default("v1") == cfg.v1
        assert parser.get_default("g1.v2") == cfg.g1.v2
        assert parser.get_default("n.g2.v3") == cfg.n.g2.v3

    with subtests.test("set_defaults undefined key"):
        pytest.raises(KeyError, lambda: parser.set_defaults(v4="d"))

    with subtests.test("get_default undefined key"):
        pytest.raises(KeyError, lambda: parser.get_default("v4"))


def test_set_get_default_suppress_optional(parser):
    parser.add_argument("--p1", type=int, default=SUPPRESS)
    with pytest.raises(NSKeyError, match="does not specify a default"):
        parser.get_default("p1")
    assert parser.get_defaults() == Namespace()
    help_str = get_parser_help(parser)
    assert "--p1 P1     (type: int)" in help_str


def test_set_get_default_suppress_required(parser):
    parser.add_argument("--p2", type=int, default=SUPPRESS, required=True)
    with pytest.raises(NSKeyError, match="does not specify a default"):
        parser.get_default("p2")
    assert parser.get_defaults() == Namespace()
    help_str = get_parser_help(parser)
    assert "--p2 P2     (required, type: int)" in help_str


def test_set_get_default_suppress_default_config_file(parser, tmp_cwd):
    default_config_file = tmp_cwd / "defaults.yaml"
    default_config_file.write_text(json_or_yaml_dump({"p3": 1.2}))

    parser.default_config_files = [default_config_file]
    parser.add_argument("--p3", type=float, default=SUPPRESS)
    parser.add_argument("--p4", type=int, default=SUPPRESS)

    assert parser.get_default("p3") == 1.2
    with pytest.raises(NSKeyError, match="does not specify a default"):
        parser.get_default("p4")


def test_add_config_action_class(parser):
    parser.add_argument("--cfg", action=ActionConfigFile)
    parser.add_argument("--op", type=int)
    assert parser.parse_args(['--cfg={"op": 2}']).op == 2


@pytest.mark.parametrize("action", [ActionConfigFile, "config"])
def test_add_multiple_config_arguments_error(parser, action):
    parser.add_argument("--cfg1", action=action)
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("--cfg2", action=action)
    ctx.match("only allowed to have a single")


def test_validate_skip_unset(parser):
    parser.add_argument("--op1", type=int)
    parser.add_argument("--op2", type=float)
    cfg = parser.parse_args(["--op2=2.2"])
    parser.validate(cfg, skip_unset=True)
    with pytest.raises(TypeError) as ctx:
        parser.validate(cfg, skip_unset=False)
    ctx.match("Expected a <class 'int'>")


def test_validate_branch(example_parser):
    cfg = example_parser.get_defaults()
    example_parser.validate(cfg.nums, branch="nums")
    cfg.nums.val1 = "invalid"
    with pytest.raises(TypeError) as ctx:
        example_parser.validate(cfg.nums, branch="nums")
    ctx.match("Expected a <class 'int'>")


def test_strip_unknown(parser, example_parser):
    for key, default in example_parser.get_defaults().items():
        parser.add_argument("--" + key, default=default)
    parser.add_argument("--val", default="val_def")
    parser.add_argument("--lev1.opt4", default="opt3_def")
    parser.add_argument("--nums.val3", type=float, default=1.5)
    cfg = parser.parse_args([])
    cfg.__path__ = "some path"
    stripped = example_parser.strip_unknown(cfg)
    assert set(cfg.keys()) - set(stripped.keys()) == {"val", "nums.val3", "lev1.opt4"}
    assert stripped.pop("__path__") == "some path"


def test_exit_on_error():
    parser = ArgumentParser(exit_on_error=True)
    parser.add_argument("--val", type=int)
    err = StringIO()
    with redirect_stderr(err):
        assert 8 == parser.parse_args(["--val", "8"]).val
        pytest.raises(SystemExit, lambda: parser.parse_args(["--val", "eight"]))
    assert 'Parser key "val":' in err.getvalue()


def test_version_print():
    parser = ArgumentParser(prog="app", version="1.2.3")
    out = get_parse_args_stdout(parser, ["--version"])
    assert out == "app 1.2.3\n"


@patch.dict(os.environ, {"JSONARGPARSE_DEBUG": "true"})
def test_debug_environment_variable(logger):
    parser = ArgumentParser(logger=logger)
    parser.add_argument("--int", type=int)
    with pytest.raises(ArgumentError), capture_logs(logger) as logs:
        parser.parse_args(["--int=invalid"])
    assert "Debug enabled, thus raising exception instead of exit" in logs.getvalue()


def test_parse_known_args_not_implemented(parser):
    pytest.raises(NotImplementedError, lambda: parser.parse_known_args([]))


@pytest.mark.skipif(sys.version_info[:3] == (3, 14, 3), reason="not pickleable in Python 3.14.3")
def test_pickle_parser(example_parser):
    parser = pickle.loads(pickle.dumps(example_parser))
    assert example_parser.get_defaults() == parser.get_defaults()


def replace_underscores(args):
    return [arg.replace("_", "-") for arg in args]


class UnderscoresToDashesParser(ArgumentParser):
    def add_argument(self, *args, **kwargs):
        args = replace_underscores(args)
        return super().add_argument(*args, **kwargs)


def test_get_argument_group_class_failure(logger):
    with source_unavailable(), capture_logs(logger) as logs:
        UnderscoresToDashesParser(logger=logger)
    assert "Failed to create ArgumentGroup subclass based on" in logs.getvalue()


@pytest.mark.skipif(sys.version_info[:3] == (3, 14, 3), reason="not pickleable in Python 3.14.3")
def test_get_argument_group_class_underscores_to_dashes():
    parser = UnderscoresToDashesParser()
    parser.add_argument("--int_value", type=int, default=1)
    group = parser.add_argument_group("group")
    group.add_argument("--group_float_value", type=float, default=2.0)
    help_str = get_parser_help(parser)
    assert "--int-value" in help_str
    assert "--group-float-value" in help_str
    cfg = parser.parse_args(["--int-value=2", "--group-float-value=3.0"])
    assert cfg == Namespace(int_value=2, group_float_value=3.0)
    clone_parser = pickle.loads(pickle.dumps(parser))
    assert clone_parser.get_defaults() == parser.get_defaults()
