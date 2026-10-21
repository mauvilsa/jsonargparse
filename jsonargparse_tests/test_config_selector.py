from __future__ import annotations

import json
import os
import pathlib

import pytest

from jsonargparse import ArgumentError, ArgumentParser
from jsonargparse._formatters import describe_source
from jsonargparse._namespace import get_provenance
from jsonargparse._optionals import toml_load_available
from jsonargparse_tests.conftest import capture_logs, get_parser_help, skip_if_no_pyyaml


@pytest.fixture
def config_parser() -> ArgumentParser:
    parser = ArgumentParser(exit_on_error=False, parser_mode="json")
    parser.add_argument("--config", action="config")
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    return parser


def write(path: str, data) -> None:
    pathlib.Path(path).write_text(data if isinstance(data, str) else json.dumps(data))


def get_sources(cfg) -> dict:
    return {
        key: describe_source(source)
        for key, source in get_provenance(cfg).items()
        if key.rsplit(".", 1)[-1] != "config"
    }


def get_error(parser: ArgumentParser, args: list[str]) -> str:
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(args)
    return str(ctx.value)


# config argument and parse_path


def test_selector_config_argument(config_parser, tmp_cwd):
    write("package.json", {"name": "pkg", "myapp": {"a": 1}})
    cfg = config_parser.parse_args(["--config=package.json#myapp"])
    assert (cfg.a, cfg.b) == (1, 0)
    assert cfg.config == ["package.json#myapp"]
    assert config_parser.get_config_files(cfg) == ["package.json#myapp"]


def test_selector_config_path_relative_to_cwd(config_parser, tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "work").mkdir()
    (tmp_path / "configs" / "main.json").write_text('{"config": "package.json#myapp"}')
    (tmp_path / "configs" / "package.json").write_text('{"myapp": {"a": 1}}')
    monkeypatch.chdir(tmp_path / "work")
    cfg = config_parser.parse_args(["--config=../configs/main.json"])
    assert cfg.a == 1
    assert cfg.config == [os.path.join("..", "configs", "package.json") + "#myapp", "../configs/main.json"]


def test_selector_nested_key(config_parser, tmp_cwd):
    write("Cargo.json", {"package": {"metadata": {"myapp": {"b": 2}}, "version": "1"}})
    cfg = config_parser.parse_args(["--config=Cargo.json#package.metadata.myapp"])
    assert cfg.b == 2


def test_selector_parse_path(config_parser, tmp_cwd):
    write("package.json", {"myapp": {"a": 3}})
    assert config_parser.parse_path("package.json#myapp").a == 3


def test_selector_missing_key_error(config_parser, tmp_cwd):
    write("package.json", {"name": "pkg"})
    error = get_error(config_parser, ["--config=package.json#myapp"])
    assert 'Key "myapp" not found in the config' in error
    assert error.endswith("Source: config file package.json#myapp")


def test_selector_not_a_mapping_error(config_parser, tmp_cwd):
    write("package.json", {"myapp": [1, 2]})
    error = get_error(config_parser, ["--config=package.json#myapp"])
    assert 'Expected a mapping at key "myapp". Got value: [1, 2]' in error


def test_selector_file_name_with_hash(config_parser, tmp_cwd):
    write("a#b.json", {"a": 1})
    write("c#d.json", {"myapp": {"a": 2}})
    assert config_parser.parse_args(["--config=a#b.json"]).a == 1
    assert config_parser.parse_args(["--config=c#d.json#myapp"]).a == 2


def test_selector_file_not_found(config_parser, tmp_cwd):
    error = get_error(config_parser, ["--config=missing.json#myapp"])
    assert "Not a valid path nor a config string" in error
    assert "missing.json#myapp" in error


def test_selector_section_of_other_file(config_parser, tmp_cwd):
    write("shared.json", {"base": {"a": 1, "b": 2}})
    write("main.json", {"app": {"config": "shared.json#base", "b": 3}})
    cfg = config_parser.parse_args(["--config=main.json#app"])
    assert (cfg.a, cfg.b) == (1, 3)
    assert cfg.config == ["shared.json#base", "main.json#app"]


def test_selector_same_file_other_section_error(config_parser, tmp_cwd):
    write("shared.json", {"base": {"a": 1}, "app": {"config": "shared.json#base"}})
    error = get_error(config_parser, ["--config=shared.json#app"])
    assert "Loading another section of the same config file is not supported" in error
    assert "shared.json#app -> shared.json#base" in error


def test_selector_whole_file_to_own_section_error(config_parser, tmp_cwd):
    write("shared.json", {"config": "shared.json#base", "base": {"a": 1}})
    error = get_error(config_parser, ["--config=shared.json"])
    assert "Loading another section of the same config file is not supported" in error
    assert "shared.json -> shared.json#base" in error


def test_selector_same_section_loop_error(config_parser, tmp_cwd):
    write("one.json", {"app": {"config": "two.json"}})
    write("two.json", {"config": "one.json#app"})
    error = get_error(config_parser, ["--config=one.json#app"])
    assert "Config file loop detected: one.json#app -> two.json -> one.json#app" in error


def test_selector_empty_key(config_parser, tmp_cwd):
    write("package.json", {"a": 1})
    error = get_error(config_parser, ["--config=package.json#"])
    assert "Not a valid path nor a config string" in error


# default_config_files


def test_selector_default_config_files_precedence(config_parser, tmp_cwd):
    write("user.json", {"a": 1, "b": 1})
    write("package.json", {"myapp": {"a": 2, "b": 2}})
    write("app.json", {"b": 3})
    config_parser.default_config_files = ["user.json", "package.json#myapp", "app.json"]
    cfg = config_parser.parse_args([])
    assert (cfg.a, cfg.b) == (2, 3)
    assert cfg.__default_config__ == ["user.json", "package.json#myapp", "app.json"]
    assert get_sources(cfg) == {
        "a": "default config file package.json#myapp",
        "b": "default config file app.json",
    }


def test_selector_default_config_file_only(config_parser, tmp_cwd):
    write("package.json", {"myapp": {"a": 2}})
    config_parser.default_config_files = ["package.json#myapp"]
    cfg = config_parser.parse_args([])
    assert cfg.a == 2
    assert cfg.__default_config__ == "package.json#myapp"
    help_str = get_parser_help(config_parser)
    assert "overridden by the contents of: package.json#myapp" in help_str


def test_selector_default_config_file_missing_key_skipped(config_parser, tmp_cwd, logger):
    write("package.json", {"name": "pkg"})
    config_parser.logger = logger
    config_parser.default_config_files = ["package.json#myapp"]
    with capture_logs(logger) as logs:
        cfg = config_parser.parse_args([])
    assert cfg.a == 0
    assert "__default_config__" not in cfg
    assert 'Skipped default config file package.json#myapp: Key "myapp" not found' in logs.getvalue()


def test_selector_default_config_files_pattern(config_parser, tmp_cwd):
    write("one.json", {"myapp": {"a": 1}})
    write("two.json", {"myapp": {"b": 2}})
    config_parser.default_config_files = ["*.json#myapp"]
    cfg = config_parser.parse_args([])
    assert (cfg.a, cfg.b) == (1, 2)
    assert cfg.__default_config__ == ["one.json#myapp", "two.json#myapp"]


def test_selector_default_config_file_error(config_parser, tmp_cwd):
    write("package.json", {"myapp": {"a": "abc"}})
    config_parser.default_config_files = ["package.json#myapp"]
    error = get_error(config_parser, [])
    assert "Expected type: int. Got value: abc" in error
    assert error.endswith("Source: default config file package.json#myapp")


def test_selector_default_config_file_problem(config_parser, tmp_cwd):
    write("package.json", {"myapp": {"unknown": 1}})
    config_parser.default_config_files = ["package.json#myapp"]
    with pytest.raises(ArgumentError) as ctx:
        config_parser.get_defaults()
    assert str(ctx.value).startswith("Problem in default config file 'package.json#myapp'")


# formats


@pytest.mark.skipif(not toml_load_available, reason="tomllib or tomli package is required")
def test_selector_pyproject_toml(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="extension_or_json")
    parser.add_argument("--config", action="config")
    parser.add_argument("--line_length", type=int, default=80)
    write("pyproject.toml", '[project]\nname = "pkg"\n\n[tool.myapp]\nline_length = 100\n')
    parser.default_config_files = ["pyproject.toml#tool.myapp"]
    assert parser.parse_args([]).line_length == 100


@skip_if_no_pyyaml
def test_selector_yaml_line_numbers(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="yaml")
    parser.add_argument("--config", action="config")
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    write("services.yaml", "web:\n  a: 1\napi:\n  a: 2\n  b: 3\n")
    cfg = parser.parse_args(["--config=services.yaml#api"])
    assert get_sources(cfg) == {
        "a": "config file services.yaml#api:4",
        "b": "config file services.yaml#api:5",
    }
