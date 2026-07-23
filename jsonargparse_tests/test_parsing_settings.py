import re
from dataclasses import dataclass
from typing import List, Literal, Optional
from unittest.mock import patch

import pytest

from jsonargparse import SUPPRESS, ActionYesNo, ArgumentError, Namespace, Unset, set_parsing_settings
from jsonargparse._common import _UnsetType, get_parsing_setting
from jsonargparse_tests.conftest import capture_logs, get_parse_args_stdout, get_parser_help, json_or_yaml_load
from jsonargparse_tests.test_typehints import Optimizer


@pytest.fixture(autouse=True)
def auto_patch_parsing_settings():
    with patch.dict("jsonargparse._common.parsing_settings"):
        yield


def test_get_parsing_setting_failure():
    with pytest.raises(ValueError, match="Unknown parsing setting"):
        get_parsing_setting("unknown_setting")


# validate_defaults


def test_set_validate_defaults_failure():
    with pytest.raises(ValueError, match="validate_defaults must be a boolean"):
        set_parsing_settings(validate_defaults="invalid")


def test_validate_defaults_success(parser):
    set_parsing_settings(validate_defaults=True)

    parser.add_argument("--config", action="config")
    parser.add_argument("--num", type=int, default=1)
    parser.add_argument("--untyped", default=2)


def test_validate_defaults_failure(parser):
    set_parsing_settings(validate_defaults=True)

    with pytest.raises(ValueError, match="Default value is not valid:"):
        parser.add_argument("--num", type=int, default="x")


@dataclass
class DataWithDefault:
    param: str = "foo"


def test_validate_defaults_dataclass(parser):
    set_parsing_settings(validate_defaults=True)

    added_args = parser.add_class_arguments(DataWithDefault)
    assert added_args == ["param"]


# parse_optionals_as_positionals


def test_set_parse_optionals_as_positionals_failure():
    with pytest.raises(ValueError, match="parse_optionals_as_positionals must be a boolean"):
        set_parsing_settings(parse_optionals_as_positionals="invalid")


def test_parse_optionals_as_positionals_simple(parser, logger, subtests):
    set_parsing_settings(parse_optionals_as_positionals=True)

    parser.add_argument("p1", type=Optional[Literal["p1"]])
    parser.add_argument("--o1", type=Optional[int])
    parser.add_argument("--flag", default=False, nargs=0, action=ActionYesNo)
    parser.add_argument("--o2", type=Optional[Literal["o2"]])
    parser.add_argument("--o3")

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert " p1 [o1 [o2 [o3]]]" in help_str
        assert "extra positionals are parsed as optionals in the order shown above" in help_str

    with subtests.test("no extra positionals"):
        cfg = parser.parse_args(["--o2=o2", "--o1=1", "p1"])
        assert cfg == Namespace(p1="p1", o1=1, o2="o2", o3=None, flag=False)

    with subtests.test("one extra positional"):
        cfg = parser.parse_args(["--o2=o2", "p1", "2"])
        assert cfg == Namespace(p1="p1", o1=2, o2="o2", o3=None, flag=False)

    with subtests.test("two extra positionals"):
        cfg = parser.parse_args(["p1", "3", "o2"])
        assert cfg == Namespace(p1="p1", o1=3, o2="o2", o3=None, flag=False)

    with subtests.test("three extra positionals"):
        cfg = parser.parse_args(["p1", "3", "o2", "v3"])
        assert cfg == Namespace(p1="p1", o1=3, o2="o2", o3="v3", flag=False)

    with subtests.test("extra positional has precedence"):
        cfg = parser.parse_args(["p1", "3", "o2", "--o1=4"])
        assert cfg == Namespace(p1="p1", o1=3, o2="o2", o3=None, flag=False)

    with subtests.test("extra positionals invalid values"):
        with pytest.raises(ArgumentError) as ex:
            parser.parse_args(["p1", "o2", "5"])
        assert re.match('Parser key "o1".*Given value: o2', ex.value.message, re.DOTALL)

        with pytest.raises(ArgumentError) as ex:
            parser.parse_args(["p1", "6", "invalid"])
        assert re.match('Parser key "o2".*Given value: invalid', ex.value.message, re.DOTALL)

    parser.logger = logger
    with subtests.test("unrecognized arguments"):
        with capture_logs(logger) as logs:
            with pytest.raises(ArgumentError, match="unrecognized arguments: --unk=x"):
                parser.parse_args(["--unk=x"])
        assert "Positional argument p1 missing, aborting _positional_optionals" in logs.getvalue()

    with subtests.test("mixed unrecognized"):
        with capture_logs(logger) as logs:
            with pytest.raises(ArgumentError, match="unrecognized arguments: --unexpected arg xyz"):
                parser.parse_args(["p1", "3", "--unexpected", "arg", "xyz"])
        assert "unrecognized arguments: --unexpected arg xyz" in logs.getvalue()


def test_parse_optionals_as_positionals_subcommands(parser, subparser, subtests):
    set_parsing_settings(parse_optionals_as_positionals=True)

    subparser.add_argument("p1", type=Optional[Literal["p1"]])
    subparser.add_argument("--o1", type=Optional[int])
    subparser.add_argument("--o2", type=Optional[Literal["o2"]])
    parser.add_argument("--g1")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("subcmd", subparser)

    with subtests.test("help global"):
        help_str = get_parser_help(parser)
        assert " [g1]" not in help_str
        assert "extra positionals are parsed as optionals in the order shown above" not in help_str

    with subtests.test("help subcommand"):
        help_str = get_parse_args_stdout(parser, ["subcmd", "-h"])
        assert " p1 [o1 [o2]]" in help_str
        assert "extra positionals are parsed as optionals in the order shown above" in help_str

    with subtests.test("no extra positionals"):
        cfg = parser.parse_args(["subcmd", "--o2=o2", "--o1=1", "p1"])
        assert cfg.subcmd == Namespace(p1="p1", o1=1, o2="o2")

    with subtests.test("one extra positional"):
        cfg = parser.parse_args(["subcmd", "--o2=o2", "p1", "2"])
        assert cfg.subcmd == Namespace(p1="p1", o1=2, o2="o2")

    with subtests.test("two extra positionals"):
        cfg = parser.parse_args(["subcmd", "p1", "3", "o2"])
        assert cfg.subcmd == Namespace(p1="p1", o1=3, o2="o2")

    with subtests.test("extra positionals invalid values"):
        with pytest.raises(ArgumentError) as ex:
            parser.parse_args(["subcmd", "p1", "o2", "5"])
        assert re.match('Parser key "o1".*Given value: o2', ex.value.message, re.DOTALL)

    with subtests.test("mixed unrecognized"):
        with pytest.raises(ArgumentError, match="unrecognized arguments: --unexpected=arg"):
            parser.parse_args(["subcmd", "p1", "3", "--unexpected=arg"])


def test_optionals_as_positionals_usage_wrap(parser):
    set_parsing_settings(parse_optionals_as_positionals=True)

    parser.prog = "long_prog_name"
    parser.add_argument("relatively_long_positional")
    parser.add_argument("--first_long_optional")
    parser.add_argument("--second_long_optional")

    help_str = get_parser_help(parser, columns="80")
    assert "usage: long_prog_name " in help_str
    assert "                      relatively_long_positional" in help_str
    assert "                      [first_long_optional [second_long_optional]]" in help_str


@dataclass
class DataOptions:
    d1: int = 1


def test_optionals_as_positionals_unsupported_arguments(parser):
    set_parsing_settings(parse_optionals_as_positionals=True)

    parser.add_argument("p1", type=Optional[Literal["p1"]])
    parser.add_argument("--o1", type=Optimizer)
    parser.add_argument("--o2", type=Optional[int])
    parser.add_argument("--o3", type=DataOptions)
    parser.add_argument("--o4.n1", type=float)

    help_str = get_parser_help(parser)
    assert " p1 [o2 [o3.d1 [o4.n1]]]" in help_str

    help_str = get_parse_args_stdout(parser, ["--o1.help=Adam"])
    assert "extra positionals are parsed as optionals in the order shown above" not in help_str


# stubs_resolver_allow_py_files


def test_set_print_completion_argument_failure():
    with pytest.raises(ValueError, match="add_print_completion_argument must be a boolean"):
        set_parsing_settings(add_print_completion_argument="invalid")


def test_set_print_completion_argument_success():
    set_parsing_settings(add_print_completion_argument=True)
    assert get_parsing_setting("add_print_completion_argument")


def test_set_stubs_resolver_allow_py_files_failure():
    with pytest.raises(ValueError, match="stubs_resolver_allow_py_files must be a boolean"):
        set_parsing_settings(stubs_resolver_allow_py_files="invalid")


# omegaconf_absolute_to_relative_paths


def test_set_omegaconf_absolute_to_relative_paths_failure():
    with pytest.raises(ValueError, match="omegaconf_absolute_to_relative_paths must be a boolean"):
        set_parsing_settings(omegaconf_absolute_to_relative_paths="invalid")


# enable/disable-subclasses


def test_default_subclass_disable_functions(subclass_behavior):
    from jsonargparse._common import subclasses_disabled_selectors

    set_parsing_settings(
        subclasses_enabled=["is_pure_dataclass", "is_pydantic_model", "is_attrs_class", "is_final_class"]
    )
    assert not subclasses_disabled_selectors


def test_unknown_subclass_disable_function():
    with pytest.raises(ValueError, match="no function 'unknown_selector'"):
        set_parsing_settings(subclasses_enabled=["unknown_selector"])


def test_invalid_item_type_subclass_enable():
    with pytest.raises(ValueError, match="Expected 'subclasses_enabled' list items to be types or strings"):
        set_parsing_settings(subclasses_enabled=[123])


def test_invalid_item_type_subclass_disable():
    with pytest.raises(ValueError, match="Expected 'subclasses_disabled' list items to be types or functions"):
        set_parsing_settings(subclasses_disabled=[123])


# unset_sentinel


def test_set_unset_sentinel_failure():
    with pytest.raises(ValueError, match="unset_sentinel must be a boolean"):
        set_parsing_settings(unset_sentinel="invalid")


def test_unset_sentinel_default_is_none(parser):
    assert get_parsing_setting("unset_sentinel") is None


def test_unset_sentinel_get_defaults(parser):
    set_parsing_settings(unset_sentinel=True)

    parser.add_argument("--num", type=int)
    defaults = parser.get_defaults()
    assert defaults.num is Unset


def test_unset_sentinel_optional_int(parser):
    set_parsing_settings(unset_sentinel=True)

    parser.add_argument("--num", type=Optional[int])

    cfg = parser.parse_args([])
    assert cfg.num is Unset

    cfg = parser.parse_args(["--num=null"])
    assert cfg.num is None

    cfg = parser.parse_args(["--num=5"])
    assert cfg.num == 5


def test_unset_sentinel_explicit_none_default_stays_none(parser):
    set_parsing_settings(unset_sentinel=True)

    parser.add_argument("--num", type=Optional[int], default=None)

    cfg = parser.parse_args([])
    assert cfg.num is None

    defaults = parser.get_defaults()
    assert defaults.num is None


def test_unset_sentinel_dump_skip_unset(parser):
    set_parsing_settings(unset_sentinel=True)

    parser.add_argument("--num", type=Optional[int])
    parser.add_argument("--name", type=str, default="hello")

    cfg = parser.parse_args([])
    assert cfg.num is Unset
    assert cfg.name == "hello"

    dump_skip = parser.dump(cfg, skip_unset=True)
    assert json_or_yaml_load(dump_skip) == {"name": "hello"}

    dump_no_skip = parser.dump(cfg, skip_unset=False)
    assert json_or_yaml_load(dump_no_skip) == {"num": "==UNSET==", "name": "hello"}


@dataclass
class UnsetListItem:
    name: str
    value: Optional[int]


def test_unset_sentinel_list_of_dataclasses(parser):
    set_parsing_settings(unset_sentinel=True)

    parser.add_argument("--records", type=List[UnsetListItem])

    with pytest.raises(ArgumentError, match="the following arguments are required: value"):
        parser.parse_args(['--records=[{"name":"a"},{"name":"b","value":2}]'])

    cfg = parser.parse_args(['--records=[{"name":"a","value":null},{"name":"b","value":2}]'])
    assert cfg.records[0] == Namespace(name="a", value=None)
    assert cfg.records[1] == Namespace(name="b", value=2)

    defaults = parser.get_defaults()
    assert defaults == Namespace(records=Unset)

    dump_skip = parser.dump(defaults, skip_unset=True)
    assert json_or_yaml_load(dump_skip) == {}

    dump_no_skip = parser.dump(defaults, skip_unset=False)
    assert json_or_yaml_load(dump_no_skip) == {"records": "==UNSET=="}


def test_unset_sentinel_validate_skip_unset(parser):
    set_parsing_settings(unset_sentinel=True)

    parser.add_argument("--num", type=int)

    cfg = parser.parse_args([])
    assert cfg.num is Unset

    parser.validate(cfg, skip_unset=True)

    with pytest.raises(TypeError, match="Expected a <class 'int'>"):
        parser.validate(cfg, skip_unset=False)


def test_unset_sentinel_required_arg(parser):
    set_parsing_settings(unset_sentinel=True)

    parser.add_argument("--num", type=int, required=True)

    with pytest.raises(ArgumentError, match="the following arguments are required: num"):
        parser.parse_args([])


def test_unset_repr():
    assert repr(Unset) == "Unset"


def test_unset_bool():
    assert bool(Unset) is False
    assert bool(not Unset) is True


def test_unset_is_singleton():
    assert _UnsetType() is Unset


# add_function_arguments with unset_sentinel


def test_unset_sentinel_function_arguments_no_default_is_required(parser):
    """Optional param with no default in function signature should be Unset when unset_sentinel=True."""
    set_parsing_settings(unset_sentinel=True)

    def my_func(num: Optional[int], name: str = "hello"):
        pass  # pragma: no cover

    parser.add_function_arguments(my_func)

    with pytest.raises(ArgumentError, match="the following arguments are required: num"):
        parser.parse_args([])

    cfg = parser.parse_args(["--num=null"])
    assert cfg.num is None  # explicitly set to null → None
    assert cfg.name == "hello"  # has default → kept

    cfg = parser.parse_args(["--num=5"])
    assert cfg.num == 5


def test_unset_sentinel_function_arguments_explicit_none_default_stays_none(parser):
    """Optional param with explicit default=None in function signature stays None."""
    set_parsing_settings(unset_sentinel=True)

    def my_func(num: Optional[int] = None, flag: Optional[int] = 0):
        pass  # pragma: no cover

    parser.add_function_arguments(my_func)

    cfg = parser.parse_args([])
    assert cfg.num is None  # explicit default=None → None (not Unset)
    assert cfg.flag == 0  # explicit default=0 → 0


# Interaction between Unset and default SUPPRESS


def test_unset_and_suppress_default_per_argument(parser):
    """argument with default=SUPPRESS is absent from namespace even when unset_sentinel=True."""
    set_parsing_settings(unset_sentinel=True)

    # --opt has normal None default -> becomes Unset
    parser.add_argument("--opt", type=Optional[int])
    # --suppressed has default=SUPPRESS -> completely absent from namespace
    parser.add_argument("--suppressed", type=int, default=SUPPRESS)

    cfg = parser.parse_args([])
    assert cfg.opt is Unset  # Unset sentinel for unprovided optional
    assert not hasattr(cfg, "suppressed")  # SUPPRESS: key absent entirely

    cfg = parser.parse_args(["--suppressed=42"])
    assert cfg.suppressed == 42  # provided value is present normally
    assert cfg.opt is Unset


def test_unset_and_argument_default_suppress(parser):
    """argument_default=SUPPRESS on the parser excludes all unprovided args; Unset is never assigned."""
    set_parsing_settings(unset_sentinel=True)

    # Use argument_default=SUPPRESS so all arguments start with SUPPRESS default
    parser.argument_default = SUPPRESS
    parser.add_argument("--num", type=int)
    parser.add_argument("--name", type=str)

    cfg = parser.parse_args([])
    assert not hasattr(cfg, "num")  # completely absent, NOT Unset
    assert not hasattr(cfg, "name")  # completely absent, NOT Unset

    cfg = parser.parse_args(["--num=7"])
    assert cfg.num == 7
    assert not hasattr(cfg, "name")  # still absent


def test_unset_parse_and_print_config(parser):
    set_parsing_settings(unset_sentinel=True)

    parser.add_argument("--num", type=int)
    parser.add_argument("--name", type=str, default="a")
    parser.add_argument("--cfg", action="config")

    cfg = parser.parse_args(["--cfg={}"])
    assert cfg == Namespace(num=Unset, name="a", cfg=[None])

    out = get_parse_args_stdout(parser, ["--print_config"])
    assert json_or_yaml_load(out) == {"num": "==UNSET==", "name": "a"}
