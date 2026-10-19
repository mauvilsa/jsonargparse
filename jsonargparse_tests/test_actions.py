from __future__ import annotations

from pathlib import Path

import pytest

from jsonargparse import (
    SUPPRESS,
    ActionFail,
    ActionParser,
    ActionYesNo,
    ArgumentError,
    ArgumentParser,
    Namespace,
)
from jsonargparse_tests.conftest import get_parser_help, json_or_yaml_dump

# ActionConfigFile tests


def test_action_config_file(parser, tmp_cwd):
    rel_yaml_file = Path("subdir", "config.yaml")
    abs_yaml_file = (tmp_cwd / rel_yaml_file).resolve()
    abs_yaml_file.parent.mkdir()
    abs_yaml_file.write_text(json_or_yaml_dump({"val": "yaml"}))

    parser.add_argument("--cfg", action="config")
    parser.add_argument("--val")

    cfg = parser.parse_args([f"--cfg={abs_yaml_file}", f"--cfg={rel_yaml_file}", "--cfg", '{"val": "arg"}'])
    assert 3 == len(cfg.cfg)
    assert "arg" == cfg.val
    assert str(abs_yaml_file) == cfg.cfg[0]
    assert str(rel_yaml_file) == cfg.cfg[1]
    assert None is cfg.cfg[2]


def test_action_config_file_set_defaults_error(parser):
    parser.add_argument("--cfg", action="config")
    with pytest.raises(ValueError) as ctx:
        parser.set_defaults(cfg="config.yaml")
    ctx.match("does not accept a default, use default_config_files")


def test_action_config_file_add_argument_default_error(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("--cfg", default="config.yaml", action="config")
    ctx.match("does not accept a default, use default_config_files")


def test_action_config_file_nested_error(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("--nested.cfg", action="config")
    ctx.match("ActionConfigFile must be a top level option")


@pytest.mark.parametrize(
    "args",
    [
        ["--cfg", '"""'],
        ["--cfg=not-exist"],
        ["--cfg", '{"k":"v"}'],
    ],
)
def test_action_config_file_argument_errors(parser, args):
    parser.add_argument("--cfg", action="config")
    with pytest.raises(ArgumentError):
        parser.parse_args(args)


# ActionFail tests


def test_action_fail_optional(parser):
    parser.add_argument(
        "--unavailable",
        action=ActionFail(message="needs package xyz"),
        help="Option not available due to missing package xyz",
    )
    help_str = get_parser_help(parser)
    assert "--unavailable" in help_str
    assert "Option not available due to missing package xyz" in help_str
    defaults = parser.get_defaults()
    assert "unavailable" not in defaults
    with pytest.raises(ArgumentError, match="needs package xyz"):
        parser.parse_args(["--unavailable=x"])
    with pytest.raises(ArgumentError, match="needs package xyz"):
        parser.parse_args(["--unavailable.child=x"])


def test_action_fail_positional(parser):
    parser.add_argument(
        "unexpected",
        action=ActionFail(message="unexpected positional: %(value)s"),
        help=SUPPRESS,
    )
    parser.add_argument("--something", default="else")
    help_str = get_parser_help(parser)
    assert "unexpected" not in help_str
    assert parser.parse_args([]) == Namespace(something="else")
    with pytest.raises(ArgumentError, match="unexpected positional: given_value"):
        parser.parse_args(["given_value"])


# ActionYesNo tests


def test_yes_no_action_defaults(parser):
    parser.add_argument("--default_false", default=False, action=ActionYesNo)
    parser.add_argument("--default_true", default=True, action=ActionYesNo)
    defaults = parser.get_defaults()
    assert False is defaults.default_false
    assert True is defaults.default_true


@pytest.mark.parametrize(
    ("args", "key", "expected"),
    [
        (["--default_false"], "default_false", True),
        (["--no_default_false"], "default_false", False),
        (["--default_true"], "default_true", True),
        (["--no_default_true"], "default_true", False),
    ],
)
def test_yes_no_action_without_argument(parser, args, key, expected):
    parser.add_argument("--default_false", default=False, nargs=0, action=ActionYesNo)
    parser.add_argument("--default_true", default=True, nargs="?", action=ActionYesNo)
    assert getattr(parser.parse_args(args), key) is expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--default_false=true"], True),
        (["--default_false=false"], False),
        (["--default_false=yes"], True),
        (["--default_false=no"], False),
    ],
)
def test_yes_no_action_with_argument(parser, args, expected):
    parser.add_argument("--default_false", default=False, nargs="?", action=ActionYesNo)
    assert parser.parse_args(args).default_false is expected


def test_yes_no_action_double_negative(parser):
    parser.add_argument("--default_true", default=True, nargs=1, action=ActionYesNo)
    assert True is parser.parse_args(["--no_default_true=no"]).default_true


def test_yes_no_action_invalid_value(parser):
    parser.add_argument("--default_true", default=True, nargs=1, action=ActionYesNo)
    with pytest.raises(ArgumentError):
        parser.parse_args(["--default_true=invalid"])


def test_yes_no_action_unspecified_default_and_nargs(parser):
    parser.add_argument("--arg", action=ActionYesNo)
    assert False is parser.get_defaults().arg
    help_str = get_parser_help(parser)
    assert "--arg, --no_arg  (type: bool, default: False)" in help_str


def test_yes_no_action_nested(parser):
    parser.add_argument("--g.arg", action=ActionYesNo)
    assert False is parser.get_defaults().g.arg
    assert True is parser.parse_args(["--g.arg"]).g.arg
    assert False is parser.parse_args(["--no_g.arg"]).g.arg


def test_yes_no_action_prefixes(parser):
    parser.add_argument("--with-arg", action=ActionYesNo(yes_prefix="with-", no_prefix="without-"))
    assert True is parser.parse_args(["--with-arg"]).with_arg
    assert False is parser.parse_args(["--without-arg"]).with_arg


def test_yes_no_action_invalid_yes_prefix(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("--arg", action=ActionYesNo(yes_prefix="yes_"))
    ctx.match('Expected option string to start with "--yes_"')


def test_yes_no_action_invalid_no_prefix(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("--arg", nargs="?", action=ActionYesNo(no_prefix=None))
    ctx.match("no_prefix=None only supports nargs=1")


def test_yes_no_action_invalid_positional(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("pos", action=ActionYesNo)
    ctx.match("not intended for positional")


@pytest.mark.parametrize(
    ("env", "key", "expected"),
    [
        ({"APP_G__DEFAULT_FALSE": "true"}, "g.default_false", True),
        ({"APP_G__DEFAULT_FALSE": "yes"}, "g.default_false", True),
        ({"APP_DEFAULT_TRUE": "false"}, "default_true", False),
        ({"APP_DEFAULT_TRUE": "no"}, "default_true", False),
    ],
)
def test_yes_no_action_parse_env(parser, env, key, expected):
    parser.default_env = True
    parser.env_prefix = "APP"
    parser.add_argument("--g.default_false", default=False, action=ActionYesNo)
    parser.add_argument("--default_true", default=True, nargs="?", action=ActionYesNo)
    parsed = parser.parse_env(env)
    assert parsed.get(key) is expected


def test_yes_no_action_move_to_subparser(parser, subparser):
    subparser.add_argument("--g.key", default=False, action=ActionYesNo)
    parser.add_argument("--subparser", action=ActionParser(parser=subparser))
    assert parser.parse_args([]) == Namespace(subparser=Namespace(g=Namespace(key=False)))


# ActionParser tests


@pytest.fixture
def composed_parsers(tmp_path_factory):
    parser_lv3 = ArgumentParser(prog="lv3", default_env=False)
    parser_lv3.add_argument("--opt3", default="opt3_def")

    parser_lv2 = ArgumentParser(prog="lv2", default_env=False)
    parser_lv2.add_argument("--opt2", default="opt2_def")
    parser_lv2.add_argument("--inner3", action=ActionParser(parser=parser_lv3))

    parser = ArgumentParser(prog="lv1", default_env=True, exit_on_error=False)
    parser.add_argument("--opt1", default="opt1_def")
    parser.add_argument("--inner2", action=ActionParser(parser=parser_lv2))

    tmp_path = tmp_path_factory.mktemp("composed_parsers")

    yaml_main = tmp_path / "main.yaml"
    yaml_inner2 = tmp_path / "inner2.yaml"
    yaml_inner3 = tmp_path / "inner3.yaml"

    yaml_main.write_text(json_or_yaml_dump({"opt1": "opt1_yaml", "inner2": "inner2.yaml"}))
    yaml_inner2.write_text(json_or_yaml_dump({"opt2": "opt2_yaml", "inner3": "inner3.yaml"}))
    yaml_inner3.write_text(json_or_yaml_dump({"opt3": "opt3_yaml"}))

    return parser, yaml_main, yaml_inner2, yaml_inner3


def test_action_parser_defaults(composed_parsers):
    parser = composed_parsers[0]
    defaults = parser.get_defaults()
    assert "opt1_def" == defaults.opt1
    assert "opt2_def" == defaults.inner2.opt2
    assert "opt3_def" == defaults.inner2.inner3.opt3


def test_action_parser_unexpected_group_value(composed_parsers):
    parser = composed_parsers[0]
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--inner2=x"]))


def test_action_parser_parse_path(composed_parsers):
    parser, yaml_main = composed_parsers[:2]
    expected = {"opt1": "opt1_yaml", "inner2": {"opt2": "opt2_yaml", "inner3": {"opt3": "opt3_yaml"}}}
    cfg = parser.parse_path(yaml_main)
    assert "inner2.yaml" == str(cfg.inner2.__path__)
    assert "inner3.yaml" == str(cfg.inner2.inner3.__path__)
    assert expected == cfg.clone(with_meta=False).as_dict()

    yaml_main2 = yaml_main.parent / "main2.yaml"
    yaml_main2.write_text(parser.dump(cfg))
    cfg2 = parser.parse_path(yaml_main2).clone(with_meta=False)
    assert expected == cfg2.as_dict()


def test_action_parser_config_loop(composed_parsers):
    parser, yaml_main, yaml_inner2 = composed_parsers[:3]
    yaml_main.write_text(json_or_yaml_dump({"inner2": "main.yaml"}))
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_path(yaml_main)
    ctx.match(r"Config file loop detected: .+main\.yaml -> main\.yaml")

    yaml_main.write_text(json_or_yaml_dump({"inner2": "inner2.yaml"}))
    yaml_inner2.write_text(json_or_yaml_dump({"inner3": "main.yaml"}))
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_path(yaml_main)
    ctx.match(r"Config file loop detected: .+main\.yaml -> inner2\.yaml -> main\.yaml")

    yaml_main.write_text(json_or_yaml_dump({"inner2": "main.yaml"}))
    parser.default_config_files = [str(yaml_main)]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args([])
    ctx.match(r"Config file loop detected: .+main\.yaml -> main\.yaml")


def test_action_parser_parse_env_inner(composed_parsers):
    parser, _, yaml_inner2, yaml_inner3 = composed_parsers
    assert "opt2_env" == parser.parse_env({"LV1_INNER2__OPT2": "opt2_env"}).inner2.opt2
    assert "opt3_env" == parser.parse_env({"LV1_INNER2__INNER3__OPT3": "opt3_env"}).inner2.inner3.opt3
    expected = {"opt1": "opt1_def", "inner2": {"opt2": "opt2_def", "inner3": {"opt3": "opt3_yaml"}}}
    cfg = parser.parse_env({"LV1_INNER2__INNER3": str(yaml_inner3)}).clone(with_meta=False)
    assert expected == cfg.as_dict()
    assert "opt2_yaml" == parser.parse_env({"LV1_INNER2": str(yaml_inner2)}).inner2.opt2


def test_action_parser_parse_args_subconfig_path(composed_parsers):
    parser, _, yaml_inner2, yaml_inner3 = composed_parsers

    expected = {"opt1": "opt1_arg", "inner2": {"opt2": "opt2_yaml", "inner3": {"opt3": "opt3_yaml"}}}
    cfg = parser.parse_args(["--opt1", "opt1_arg", f"--inner2={yaml_inner2}"]).clone(with_meta=False)
    assert expected == cfg.as_dict()

    expected = {"opt1": "opt1_def", "inner2": {"opt2": "opt2_arg", "inner3": {"opt3": "opt3_yaml"}}}
    cfg = parser.parse_args(["--inner2.opt2", "opt2_arg", f"--inner2.inner3={yaml_inner3}"]).clone(with_meta=False)
    assert expected == cfg.as_dict()

    expected = {"opt1": "opt1_def", "inner2": {"opt2": "opt2_def", "inner3": {"opt3": "opt3_arg"}}}
    cfg = parser.parse_args([f"--inner2.inner3={yaml_inner3}", "--inner2.inner3.opt3", "opt3_arg"]).clone(
        with_meta=False
    )
    assert expected == cfg.as_dict()


def test_action_parser_parse_args_subconfig_string(composed_parsers):
    parser = composed_parsers[0]

    expected = {"opt2": "opt2_str", "inner3": {"opt3": "opt3_str"}}
    cfg = parser.parse_args([f"--inner2={json_or_yaml_dump(expected)}"]).clone(with_meta=False)
    assert expected == cfg.inner2.as_dict()

    expected = {"opt3": "opt3_str"}
    cfg = parser.parse_args([f"--inner2.inner3={json_or_yaml_dump(expected)}"]).clone(with_meta=False)
    assert expected == cfg.inner2.inner3.as_dict()


def test_action_parser_parse_args_global_config(composed_parsers):
    parser, yaml_main = composed_parsers[:2]
    parser.add_argument("--cfg", action="config")

    expected = {"opt1": "opt1_yaml", "inner2": {"opt2": "opt2_yaml", "inner3": {"opt3": "opt3_yaml"}}}
    cfg = parser.parse_args([f"--cfg={yaml_main}"]).clone(with_meta=False)
    delattr(cfg, "cfg")
    assert expected == cfg.as_dict()

    cfg = parser.parse_args([f"--cfg={yaml_main}", "--inner2.opt2", "opt2_arg", "--inner2.inner3.opt3", "opt3_arg"])
    assert "opt2_arg" == cfg.inner2.opt2
    assert "opt3_arg" == cfg.inner2.inner3.opt3


def test_action_parser_required_argument(parser, subparser):
    subparser.add_argument("--op1", required=True)
    parser.add_argument("--op2", action=ActionParser(parser=subparser))
    assert "1" == parser.parse_args(["--op2.op1=1"]).op2.op1
    with pytest.raises(ArgumentError, match=r"the following arguments are required: op2\.op1"):
        parser.parse_args([])


def test_action_parser_init_failures(parser, subparser):
    pytest.raises(TypeError, ActionParser)
    pytest.raises(ValueError, lambda: ActionParser(parser=object))
    pytest.raises(Exception, lambda: parser.add_argument("--missing-subparser", action=ActionParser))
    pytest.raises(
        ValueError, lambda: parser.add_argument("--unexpected-type", type=str, action=ActionParser(subparser))
    )


def test_action_parser_failure_add_parser_to_self(parser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("--subparser", action=ActionParser(parser=parser))
    ctx.match("cannot be added as a subparser of itself")


def test_action_parser_failure_only_single_optional(parser, subparser):
    with pytest.raises(ValueError) as ctx:
        parser.add_argument("-b", "--bad", action=ActionParser(subparser))
    ctx.match("only accepts a single optional")


def test_action_parser_conflict_subparser_key(parser, subparser):
    subparser.add_argument("--op")
    parser.add_argument("--inner.op")
    pytest.raises(ValueError, lambda: parser.add_argument("--inner", action=ActionParser(subparser)))


def test_action_parser_nested_dash_names(parser, subparser, subsubparser):
    subsubparser.add_argument("--op1-like")
    subparser.add_argument("--op2-like", action=ActionParser(parser=subsubparser))
    assert "a" == subparser.parse_args(["--op2-like.op1-like=a"]).op2_like.op1_like
    parser.add_argument("--op3", action=ActionParser(parser=subparser))
    assert "b" == parser.parse_args(["--op3.op2-like.op1-like=b"]).op3.op2_like.op1_like


def get_parser_subgroup():
    parser_lv2 = ArgumentParser(description="parser_lv2 description")
    parser_lv2.add_argument("--a1", help="lv2_a1 help")
    group_lv2 = parser_lv2.add_argument_group(description="group_lv2 description")
    group_lv2.add_argument("--a2", help="lv2_a2 help")
    return parser_lv2


def test_action_parser_help_subparser_group(parser):
    parser_lv2 = get_parser_subgroup()
    parser.add_argument("--lv2", action=ActionParser(parser_lv2))
    help_str = get_parser_help(parser)
    assert "parser_lv2 description" in help_str
    assert "group_lv2 description" in help_str
    assert "--lv2.a1 A1" in help_str


def test_action_parser_help_title_and_description(parser):
    parser_lv2 = get_parser_subgroup()
    parser.add_argument(
        "--lv2",
        title="ActionParser title",
        description="ActionParser description",
        action=ActionParser(parser_lv2),
    )
    help_str = get_parser_help(parser)
    assert "ActionParser title" in help_str
    assert "ActionParser description" in help_str
