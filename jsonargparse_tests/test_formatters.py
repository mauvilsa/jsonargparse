from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from jsonargparse import ActionParser, ActionYesNo, ArgumentParser
from jsonargparse_tests.conftest import get_parse_args_stdout, get_parser_help, json_or_yaml_dump


@pytest.fixture
def parser() -> ArgumentParser:
    return ArgumentParser(prog="app", default_env=True)


def test_help_basics(parser):
    help_str = get_parser_help(parser)
    assert "ARG:   -h, --help" in help_str
    assert "APP_HELP" not in help_str


def test_help_action_version(parser):
    parser.add_argument("--version", action="version", version="1.0.0")
    help_str = get_parser_help(parser)
    assert "ARG:   --version" in help_str
    assert "APP_VERSION" not in help_str
    assert "show program's version number and exit" in help_str


def test_help_action_config_file(parser):
    parser.add_argument("-c", "--config", help="Config in yaml/json.", action="config")
    help_str = get_parser_help(parser)
    assert "ARG:   --print_config" in help_str
    assert "ARG:   -c CONFIG, --config CONFIG" in help_str or "ARG:   -c, --config CONFIG" in help_str
    assert "ENV:   APP_CONFIG" in help_str
    assert "Config in yaml/json." in help_str
    assert "APP_PRINT_CONFIG" not in help_str


def test_help_positional(parser):
    parser.add_argument("pos")
    help_str = get_parser_help(parser)
    assert "ARG:   pos" in help_str
    assert "ENV:   APP_POS" in help_str


def test_help_required_and_default(parser):
    parser.add_argument("--v1", help="Option v1.", default="v1", required=True)
    help_str = get_parser_help(parser)
    assert "ARG:   --v1 V1" in help_str
    assert "ENV:   APP_V1" in help_str
    assert "Option v1. (required, default: v1)" in help_str


def test_help_required_preserved_in_parse_args(parser):
    parser.add_argument("--v1", type=int, help="Option v1.", required=True)
    help_str = get_parse_args_stdout(parser, ["--help"])
    assert "Option v1. (required, type: int)" in help_str


def test_help_type_and_null_default(parser):
    parser.add_argument("--v2", type=int, help="Option v2.")
    help_str = get_parser_help(parser)
    assert "ARG:   --v2 V2" in help_str
    assert "ENV:   APP_V2" in help_str
    assert "Option v2. (type: int, default: null)" in help_str


def test_help_no_type_and_default(parser):
    parser.add_argument("--g1.v3", help="Option v3.", default="v3")
    help_str = get_parser_help(parser)
    assert "ARG:   --g1.v3 V3" in help_str
    assert "ENV:   APP_G1__V3" in help_str
    assert "Option v3. (default: v3)" in help_str


def test_help_choices_and_null_default(parser):
    parser.add_argument("--v4", choices=["A", "B"], help="Option v4.")
    help_str = get_parser_help(parser)
    assert "ARG:   --v4 {A,B}" in help_str
    assert "ENV:   APP_V4" in help_str
    assert "Option v4. (default: null)" in help_str


def test_help_action_parser(parser):
    parser2 = ArgumentParser()
    parser2.add_argument("--v4")
    parser.add_argument("--g2", action=ActionParser(parser=parser2))
    help_str = get_parser_help(parser)
    assert "ARG:   --g2.v4 V4" in help_str
    assert "ENV:   APP_G2__V4" in help_str


def test_help_action_yes_no(parser):
    parser.add_argument("--v5", action=ActionYesNo, default=True, help="Option v5.")
    help_str = get_parser_help(parser)
    assert "ARG:   --v5, --no_v5" in help_str
    assert "ENV:   APP_V5" in help_str
    assert "Option v5. (type: bool, default: True)" in help_str


@pytest.fixture
def default_config_files(tmp_cwd) -> tuple[ArgumentParser, str, Path]:
    not_exist = "does_not_exist.yaml"
    exists = Path("config.yaml")
    exists.write_text(json_or_yaml_dump({"v1": "from yaml v1", "n1.v2": "from yaml v2"}))

    parser = ArgumentParser(default_config_files=[not_exist, exists])
    parser.add_argument("--v1", default="from default v1")
    parser.add_argument("--n1.v2", default="from default v2")
    return parser, not_exist, exists


def test_help_default_config_files_overridden(default_config_files):
    parser, not_exist, exists = default_config_files
    help_str = get_parser_help(parser)
    assert "default config file locations" in help_str
    assert "from yaml v1" in help_str
    assert "from yaml v2" in help_str
    assert f"['{not_exist}', '{exists}']" in help_str
    assert f"overridden by the contents of: {exists}" in help_str


def test_help_default_config_files_not_overridden(default_config_files):
    parser, not_exist, _ = default_config_files
    parser.default_config_files = [not_exist]
    help_str = get_parser_help(parser)
    assert "from default v1" in help_str
    assert "from default v2" in help_str
    assert str([not_exist]) in help_str
    assert "no existing default config file found" in help_str


def test_help_default_config_files_none(default_config_files):
    parser, _, _ = default_config_files
    parser.default_config_files = None
    help_str = get_parser_help(parser)
    assert "default config file locations" not in help_str


def test_help_default_config_files_with_required(tmp_path, parser):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(json_or_yaml_dump({"v1": "from config"}))

    parser.default_config_files = [config_path]
    parser.add_argument("req", help="req description")
    parser.add_argument("--v1", default="from default")

    help_str = get_parser_help(parser)
    assert "req description" in help_str
    assert "from config" in help_str


def test_help_subcommands_with_default_env(parser):
    subcommands = parser.add_subcommands()
    subparser1 = ArgumentParser()
    subparser2 = ArgumentParser()
    subcommands.add_subcommand("greet", subparser1, help="Greet someone")
    subcommands.add_subcommand("farewell", subparser2, help="Say goodbye")
    help_str = get_parser_help(parser)
    # Individual subcommands should NOT have ARG: prefix or ENV: lines
    assert "ARG:   greet" not in help_str
    assert "ARG:   farewell" not in help_str
    assert "ENV:   APP_GREET" not in help_str
    assert "ENV:   APP_FAREWELL" not in help_str
    # But the subcommand names and help should still be present
    assert "greet" in help_str
    assert "Greet someone" in help_str
    assert "farewell" in help_str
    assert "Say goodbye" in help_str


def test_format_usage(parser):
    parser.add_argument("--v1")
    with patch.dict(os.environ, {"COLUMNS": "200"}):
        assert parser.format_usage() == "usage: app [--v1 V1]\n"
