from __future__ import annotations

import dataclasses
import json
import pathlib
from typing import Any, Dict, List, Optional

import pytest

from jsonargparse import ArgumentError, ArgumentParser, FromConfigMixin, Namespace, set_parsing_settings
from jsonargparse._formatters import describe_source
from jsonargparse._namespace import get_provenance
from jsonargparse._optionals import toml_load_available
from jsonargparse_tests.conftest import (
    skip_if_jsonschema_unavailable,
    skip_if_no_pyyaml,
    skip_if_omegaconf_unavailable,
)


@dataclasses.dataclass
class Encoder:
    layers: int = 2
    dropout: float = 0.0


@dataclasses.dataclass
class Model:
    lr: float = 0.1
    encoder: Encoder = dataclasses.field(default_factory=Encoder)


class Hook:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose  # pragma: no cover


class LogHook(Hook):
    def __init__(self, log_file: str = "run.log", **kwargs):  # pragma: no cover
        super().__init__(**kwargs)
        self.log_file = log_file


class TimerHook(Hook):
    def __init__(self, interval: int = 60, **kwargs):  # pragma: no cover
        super().__init__(**kwargs)
        self.interval = interval


log_hook = f"{__name__}.LogHook"
timer_hook = f"{__name__}.TimerHook"


@pytest.fixture(autouse=True)
def config_include_enabled(parsing_settings_patch):
    set_parsing_settings(config_include_enabled=True)


@pytest.fixture
def config_parser() -> ArgumentParser:
    parser = ArgumentParser(exit_on_error=False, parser_mode="json", env_prefix="APP")
    parser.add_argument("--config", action="config")
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    parser.add_argument("--c", type=int, default=0)
    return parser


def write(path: str, data) -> None:
    file = pathlib.Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(data if isinstance(data, str) else json.dumps(data))


def get_sources(cfg) -> dict:
    return {
        key: describe_source(source)
        for key, source in get_provenance(cfg).items()
        if key.rsplit(".", 1)[-1] != "config"
    }


# base behavior


def test_include_single_path(config_parser, tmp_cwd):
    write("base.json", {"a": 1, "b": 1})
    write("main.json", {"__include__": "base.json", "b": 2})
    cfg = config_parser.parse_args(["--config=main.json"])
    assert cfg.a == 1
    assert cfg.b == 2
    assert cfg.c == 0


def test_include_disabled_by_default(config_parser, tmp_cwd):
    set_parsing_settings(config_include_enabled=False)
    write("base.json", {"a": 1})
    write("main.json", {"__include__": "base.json", "b": 2})
    with pytest.raises(ArgumentError) as ctx:
        config_parser.parse_args(["--config=main.json"])
    ctx.match("Option '__include__' is not accepted")


def test_include_list_of_paths(config_parser, tmp_cwd):
    write("one.json", {"a": 1, "b": 1, "c": 1})
    write("two.json", {"b": 2, "c": 2})
    write("main.json", {"__include__": ["one.json", "two.json"], "c": 3})
    cfg = config_parser.parse_args(["--config=main.json"])
    assert (cfg.a, cfg.b, cfg.c) == (1, 2, 3)


def test_include_only(config_parser, tmp_cwd):
    write("base.json", {"a": 1, "b": 1})
    write("main.json", {"__include__": "base.json"})
    cfg = config_parser.parse_args(["--config=main.json"])
    assert (cfg.a, cfg.b) == (1, 1)


def test_include_chained(config_parser, tmp_cwd):
    write("one.json", {"a": 1, "b": 1, "c": 1})
    write("two.json", {"__include__": "one.json", "b": 2, "c": 2})
    write("main.json", {"__include__": "two.json", "c": 3})
    cfg = config_parser.parse_args(["--config=main.json"])
    assert (cfg.a, cfg.b, cfg.c) == (1, 2, 3)


def test_include_relative_to_including_config(config_parser, tmp_cwd):
    write("sub/base.json", {"a": 1, "b": 1})
    write("sub/mid.json", {"__include__": "base.json", "b": 2})
    write("main.json", {"__include__": "sub/mid.json", "c": 3})
    cfg = config_parser.parse_args(["--config=main.json"])
    assert (cfg.a, cfg.b, cfg.c) == (1, 2, 3)


def test_include_parse_path(config_parser, tmp_cwd):
    write("base.json", {"a": 1})
    write("main.json", {"__include__": "base.json", "b": 2})
    cfg = config_parser.parse_path("main.json")
    assert (cfg.a, cfg.b) == (1, 2)


def test_include_parse_string(config_parser, tmp_cwd):
    write("base.json", {"a": 1})
    cfg = config_parser.parse_string(json.dumps({"__include__": "base.json", "b": 2}))
    assert (cfg.a, cfg.b) == (1, 2)


def test_include_config_string_in_command_line(config_parser, tmp_cwd):
    write("base.json", {"a": 1})
    cfg = config_parser.parse_args(["--config=" + json.dumps({"__include__": "base.json", "b": 2})])
    assert (cfg.a, cfg.b) == (1, 2)


def test_include_parse_object(config_parser, tmp_cwd):
    write("base.json", {"a": 1})
    obj = {"__include__": "base.json", "b": 2}
    cfg = config_parser.parse_object(obj)
    assert (cfg.a, cfg.b) == (1, 2)
    assert obj == {"__include__": "base.json", "b": 2}


def test_include_in_group_value_in_command_line(parser, tmp_cwd):
    parser.add_class_arguments(Model, "model")
    write("model.json", {"lr": 0.5, "encoder": {"layers": 3}})
    cfg = parser.parse_args(["--model=" + json.dumps({"__include__": "model.json", "encoder": {"dropout": 0.2}})])
    assert cfg.model.lr == 0.5
    assert cfg.model.encoder == Namespace(layers=3, dropout=0.2)


def test_include_in_subclass_value_in_command_line(parser, tmp_cwd):
    parser.add_argument("--hook", type=Hook)
    write("hook.json", {"class_path": log_hook, "init_args": {"verbose": True}})
    cfg = parser.parse_args(["--hook=" + json.dumps({"__include__": "hook.json", "init_args": {"log_file": "a.log"}})])
    assert cfg.hook.class_path == log_hook
    assert cfg.hook.init_args == Namespace(verbose=True, log_file="a.log")


def test_include_default_config_file(config_parser, tmp_cwd):
    write("base.json", {"a": 1, "b": 1})
    write("defaults.json", {"__include__": "base.json", "b": 2})
    config_parser.default_config_files = ["defaults.json"]
    cfg = config_parser.parse_args([])
    assert (cfg.a, cfg.b) == (1, 2)


def test_include_environment_variable_config(config_parser, tmp_cwd, monkeypatch):
    config_parser.default_env = True
    write("base.json", {"a": 1, "b": 1})
    write("main.json", {"__include__": "base.json", "b": 2})
    monkeypatch.setenv("APP_CONFIG", "main.json")
    cfg = config_parser.parse_args([])
    assert (cfg.a, cfg.b) == (1, 2)


def test_command_line_overrides_include(config_parser, tmp_cwd):
    write("base.json", {"a": 1, "b": 1})
    write("main.json", {"__include__": "base.json", "b": 2})
    cfg = config_parser.parse_args(["--config=main.json", "--a=9"])
    assert (cfg.a, cfg.b) == (9, 2)


# nested includes


def test_include_nested_key(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--model", type=Model)
    write("model.json", {"lr": 0.5, "encoder": {"layers": 4, "dropout": 0.1}})
    write("main.json", {"model": {"__include__": "model.json", "encoder": {"dropout": 0.2}}})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.model.lr == 0.5
    assert cfg.model.encoder.layers == 4
    assert cfg.model.encoder.dropout == 0.2


def test_include_nested_subclass_spec(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hook", type=Hook)
    write("hook.json", {"class_path": log_hook, "init_args": {"log_file": "base.log", "verbose": True}})
    write("main.json", {"hook": {"__include__": "hook.json", "init_args": {"log_file": "main.log"}}})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.hook.class_path == log_hook
    assert cfg.hook.init_args.log_file == "main.log"
    assert cfg.hook.init_args.verbose is True


def test_include_in_list_item(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hooks", type=List[Hook])
    write("hook.json", {"class_path": log_hook, "init_args": {"log_file": "base.log", "verbose": True}})
    write("main.json", {"hooks": [{"__include__": "hook.json", "init_args": {"log_file": "main.log"}}, timer_hook]})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.hooks[0].init_args.as_dict() == {"log_file": "main.log", "verbose": True}
    assert cfg.hooks[1].class_path == timer_hook


def test_include_in_list_item_class_path_change_same_as_two_configs(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hooks", type=List[Hook])
    spec = {"class_path": log_hook, "init_args": {"log_file": "base.log", "verbose": True}}
    write("hook.json", spec)
    write("one.json", {"hooks": [spec]})
    write("two.json", {"hooks": [{"class_path": timer_hook}]})
    write("main.json", {"hooks": [{"__include__": "hook.json", "class_path": timer_hook}]})
    expected = parser.parse_args(["--config=one.json", "--config=two.json"]).hooks
    included = parser.parse_args(["--config=main.json"]).hooks
    assert included[0].init_args.as_dict() == expected[0].init_args.as_dict() == {"interval": 60, "verbose": True}


def test_include_nested_only_include(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hook", type=Hook)
    write("hook.json", {"class_path": log_hook, "init_args": {"log_file": "base.log"}})
    write("main.json", {"hook": {"__include__": "hook.json"}})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.hook.init_args.log_file == "base.log"


def test_include_only_include_in_dict_value(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--data", type=dict)
    write("base.json", {"x": 1})
    write("main.json", {"data": {"__include__": "base.json"}})
    assert parser.parse_args(["--config=main.json"]).data == {"x": 1}


def test_include_schema_key_ignored_in_included_dict_value(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--data", type=Dict[str, int])
    write("base.json", {"$schema": "./data.schema.json", "x": 1})
    write("main.json", {"data": {"__include__": "base.json"}})
    assert parser.parse_args(["--config=main.json"]).data == {"x": 1}


def test_include_spec_for_dataclass_same_as_two_configs(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--model", type=Model)
    spec = {"class_path": f"{__name__}.Model", "init_args": {"lr": 0.5}}
    write("model.json", spec)
    write("one.json", {"model": spec})
    write("two.json", {"model": {"encoder": {"layers": 7}}})
    write("main.json", {"model": {"__include__": "model.json", "encoder": {"layers": 7}}})
    expected = parser.parse_args(["--config=one.json", "--config=two.json"]).model
    assert parser.parse_args(["--config=main.json"]).model == expected


def test_include_within_untyped_value_not_supported(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--data", type=Any)
    write("base.json", {"x": 1})
    write("main.json", {"data": {"sub": {"__include__": "base.json"}}})
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--config=main.json"])
    ctx.match('Key "data.sub": "__include__" is not supported for this argument')


def test_include_within_untyped_sub_config_from_command_line_not_supported(parser, tmp_cwd):
    parser.add_argument("--data", type=Any, sub_configs=True)
    write("base.json", {"x": 1})
    write("data.json", {"sub": {"__include__": "base.json"}})
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--data=data.json"])
    ctx.match('Key "data.sub": "__include__" is not supported for this argument')


def test_include_inside_sub_config_file(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--model", type=Model, sub_configs=True)
    write("base.json", {"lr": 0.5, "encoder": {"layers": 4}})
    write("model.json", {"__include__": "base.json", "encoder": {"dropout": 0.3}})
    write("main.json", {"model": "model.json"})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.model.lr == 0.5
    assert cfg.model.encoder.layers == 4
    assert cfg.model.encoder.dropout == 0.3


def test_include_inside_sub_config_file_list_item(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hooks", type=List[Hook], sub_configs=True)
    write("base.json", {"class_path": log_hook, "init_args": {"verbose": True}})
    write("hook.json", {"__include__": "base.json", "init_args": {"log_file": "hook.log"}})
    write("main.json", {"hooks": ["hook.json"]})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.hooks[0].init_args.log_file == "hook.log"
    assert cfg.hooks[0].init_args.verbose is True


def test_include_in_dict_value_replaces_as_a_whole(parser, tmp_cwd):
    """A dict value is replaced, not merged, the same as when two configs give it."""
    parser.add_argument("--config", action="config")
    parser.add_argument("--data", type=dict)
    write("base.json", {"x": 1, "y": 1})
    write("one.json", {"data": {"x": 1, "y": 1}})
    write("two.json", {"data": {"y": 2}})
    write("main.json", {"data": {"__include__": "base.json", "y": 2}})
    expected = parser.parse_args(["--config=one.json", "--config=two.json"]).data
    assert parser.parse_args(["--config=main.json"]).data == expected == {"y": 2}


# class_path changes must behave as in any other config source


def include_and_equivalents() -> dict:
    """The same class_path change expressed as an include and as the routes that already existed."""
    spec = {"class_path": log_hook, "init_args": {"log_file": "base.log", "verbose": True}}
    write("base.json", {"hook": spec})
    write("sub_hook.json", spec)
    write("override.json", {"hook": {"class_path": timer_hook}})
    write("include.json", {"__include__": "base.json", "hook": {"class_path": timer_hook}})
    write("include_nested.json", {"hook": {"__include__": "sub_hook.json", "class_path": timer_hook}})
    return {
        "two config files": ["--config=base.json", "--config=override.json"],
        "config and command line": ["--config=base.json", f"--hook={timer_hook}"],
        "sub-config and command line": ["--hook=sub_hook.json", f"--hook={timer_hook}"],
        "include": ["--config=include.json"],
        "nested include": ["--config=include_nested.json"],
    }


def test_include_class_path_change_same_as_other_sources(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hook", type=Hook, sub_configs=True)
    for route, args in include_and_equivalents().items():
        hook = parser.parse_args(args).hook
        assert (hook.class_path, hook.init_args.as_dict()) == (timer_hook, {"interval": 60, "verbose": True}), route


def test_include_same_class_path_keeps_init_args(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hook", type=Hook, sub_configs=True)
    write("base.json", {"hook": {"class_path": log_hook, "init_args": {"log_file": "base.log", "verbose": True}}})
    write("main.json", {"__include__": "base.json", "hook": {"init_args": {"log_file": "main.log"}}})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.hook.init_args.log_file == "main.log"
    assert cfg.hook.init_args.verbose is True


def test_include_class_path_change_as_string_keeps_shared_init_args(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hook", type=Hook, sub_configs=True)
    write("base.json", {"hook": {"class_path": log_hook, "init_args": {"log_file": "base.log", "verbose": True}}})
    write("main.json", {"__include__": "base.json", "hook": timer_hook})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.hook.class_path == timer_hook
    assert cfg.hook.init_args.verbose is True


# list append


def test_include_append_to_included_list(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--nums", type=List[int])
    write("base.json", {"nums": [1, 2]})
    write("main.json", {"__include__": "base.json", "nums+": [3]})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.nums == [1, 2, 3]


def test_include_append_single_item_to_included_list(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--nums", type=List[int])
    write("base.json", {"nums": [1, 2]})
    write("main.json", {"__include__": "base.json", "nums+": 3})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.nums == [1, 2, 3]


def test_include_append_without_included_list(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--nums", type=List[int], default=[0])
    write("base.json", {})
    write("main.json", {"__include__": "base.json", "nums+": [3]})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.nums == [0, 3]


def test_include_append_in_two_included_configs(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--nums", type=List[int], default=[0])
    write("one.json", {"nums+": [1]})
    write("two.json", {"nums+": [2]})
    write("main.json", {"__include__": ["one.json", "two.json"], "nums+": [3]})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.nums == [0, 1, 2, 3]


def test_include_replaces_pending_append(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--nums", type=List[int], default=[0])
    write("base.json", {"nums+": [1]})
    write("main.json", {"__include__": "base.json", "nums": [9]})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.nums == [9]


# errors


def test_include_not_first_key(config_parser, tmp_cwd):
    write("base.json", {"a": 1})
    write("main.json", {"b": 2, "__include__": "base.json"})
    with pytest.raises(ArgumentError) as ctx:
        config_parser.parse_args(["--config=main.json"])
    ctx.match('"__include__" must be the first key')


def test_include_after_schema_key(config_parser, tmp_cwd):
    write("base.json", {"a": 1, "b": 1})
    write("main.json", {"$schema": "app.schema.json", "__include__": "base.json", "b": 2})
    cfg = config_parser.parse_args(["--config=main.json"])
    assert (cfg.a, cfg.b) == (1, 2)


def test_include_not_first_key_nested(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--model", type=Model)
    write("model.json", {"lr": 0.5})
    write("main.json", {"model": {"lr": 0.2, "__include__": "model.json"}})
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--config=main.json"])
    ctx.match('"__include__" must be the first key')


def test_include_invalid_value_type(config_parser, tmp_cwd):
    write("main.json", {"__include__": 3})
    with pytest.raises(ArgumentError) as ctx:
        config_parser.parse_args(["--config=main.json"])
    ctx.match('"__include__" expects a config path or a list of config paths')


def test_include_path_not_found(config_parser, tmp_cwd):
    write("main.json", {"__include__": "missing.json"})
    with pytest.raises(ArgumentError) as ctx:
        config_parser.parse_args(["--config=main.json"])
    ctx.match('"__include__" value "missing.json"')


def test_include_content_not_valid(config_parser, tmp_cwd):
    write("base.json", "{not valid")
    write("main.json", {"__include__": "base.json"})
    with pytest.raises(ArgumentError) as ctx:
        config_parser.parse_args(["--config=main.json"])
    ctx.match('Problems parsing config included from "base.json"')


def test_include_content_not_a_mapping(config_parser, tmp_cwd):
    write("base.json", [1, 2])
    write("main.json", {"__include__": "base.json"})
    with pytest.raises(ArgumentError) as ctx:
        config_parser.parse_args(["--config=main.json"])
    ctx.match('Expected config included from "base.json" to be a mapping')


def test_include_loop_detected(config_parser, tmp_cwd):
    write("one.json", {"__include__": "two.json"})
    write("two.json", {"__include__": "one.json"})
    with pytest.raises(ArgumentError) as ctx:
        config_parser.parse_args(["--config=one.json"])
    ctx.match(r"Config file loop detected: .*one\.json -> two\.json -> one\.json")


def test_include_self_loop_detected(config_parser, tmp_cwd):
    write("main.json", {"__include__": "main.json"})
    with pytest.raises(ArgumentError) as ctx:
        config_parser.parse_args(["--config=main.json"])
    ctx.match("Config file loop detected")


@skip_if_jsonschema_unavailable
def test_include_not_supported_for_jsonschema_action(parser, tmp_cwd):
    from jsonargparse import ActionJsonSchema

    parser.add_argument("--data", action=ActionJsonSchema(schema={"type": "object"}))
    write("base.json", {"a": 1})
    write("data.json", {"__include__": "base.json"})
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--data=data.json"])
    ctx.match('"__include__" is not supported for this argument')


def test_include_error_names_included_config(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hook", type=Hook)
    write("base.json", {"class_path": log_hook, "init_args": {"verbose": "not a bool"}})
    write("main.json", {"hook": {"__include__": "base.json", "init_args": {"log_file": "main.log"}}})
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--config=main.json"])
    ctx.match("Source: config file base.json")


# provenance


def test_include_provenance(config_parser, tmp_cwd):
    write("base.json", {"a": 1, "b": 1})
    write("main.json", {"__include__": "base.json", "b": 2})
    cfg = config_parser.parse_args(["--config=main.json"])
    assert get_sources(cfg) == {
        "a": "config file base.json",
        "b": "config file main.json",
        "c": "default",
    }


def test_include_provenance_nested(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="json")
    parser.add_argument("--config", action="config")
    parser.add_argument("--model", type=Model)
    write("model.json", {"lr": 0.5, "encoder": {"layers": 4, "dropout": 0.1}})
    write("main.json", {"model": {"__include__": "model.json", "encoder": {"dropout": 0.2}}})
    cfg = parser.parse_args(["--config=main.json"])
    assert get_sources(cfg) == {
        "model.lr": "config file model.json",
        "model.encoder.layers": "config file model.json",
        "model.encoder.dropout": "config file main.json",
    }


def test_include_provenance_root_and_nested(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="json")
    parser.add_argument("--config", action="config")
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--model", type=Model)
    write("base.json", {"a": 1})
    write("model.json", {"lr": 0.5, "encoder": {"layers": 4}})
    write("main.json", {"__include__": "base.json", "model": {"__include__": "model.json"}})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.model.lr == 0.5
    assert get_sources(cfg) == {
        "a": "config file base.json",
        "model.lr": "config file model.json",
        "model.encoder.layers": "config file model.json",
        "model.encoder.dropout": "default",
    }


def test_include_provenance_chained(config_parser, tmp_cwd):
    write("one.json", {"a": 1, "b": 1, "c": 1})
    write("two.json", {"__include__": "one.json", "b": 2, "c": 2})
    write("main.json", {"__include__": "two.json", "c": 3})
    cfg = config_parser.parse_args(["--config=main.json"])
    assert get_sources(cfg) == {
        "a": "config file one.json",
        "b": "config file two.json",
        "c": "config file main.json",
    }


def test_include_provenance_inside_sub_config_file(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="json")
    parser.add_argument("--config", action="config")
    parser.add_argument("--hook", type=Hook, sub_configs=True)
    write("base.json", {"class_path": log_hook, "init_args": {"verbose": True}})
    write("hook.json", {"__include__": "base.json", "init_args": {"log_file": "hook.log"}})
    write("main.json", {"hook": "hook.json"})
    cfg = parser.parse_args(["--config=main.json"])
    assert get_sources(cfg) == {
        "hook.class_path": "config file base.json",
        "hook.init_args.verbose": "config file base.json",
        "hook.init_args.log_file": "config file hook.json",
    }


def test_include_provenance_inside_sub_config_file_of_dataclass(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="json")
    parser.add_argument("--config", action="config")
    parser.add_argument("--model", type=Model, sub_configs=True)
    write("base.json", {"lr": 0.5, "encoder": {"layers": 4}})
    write("model.json", {"__include__": "base.json", "encoder": {"dropout": 0.3}})
    write("main.json", {"model": "model.json"})
    cfg = parser.parse_args(["--config=main.json"])
    assert get_sources(cfg) == {
        "model.lr": "config file base.json",
        "model.encoder.layers": "config file base.json",
        "model.encoder.dropout": "config file model.json",
    }


@skip_if_no_pyyaml
def test_include_provenance_line_numbers(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="yaml")
    parser.add_argument("--config", action="config")
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    write("base.yaml", "a: 1\nb: 1\n")
    write("main.yaml", "__include__: base.yaml\nb: 2\n")
    cfg = parser.parse_args(["--config=main.yaml"])
    assert get_sources(cfg) == {"a": "config file base.yaml:1", "b": "config file main.yaml:2"}


@pytest.mark.skipif(not toml_load_available, reason="toml package is required")
def test_include_toml_mode(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="toml")
    parser.add_argument("--config", action="config")
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    write("base.toml", "a = 1\nb = 1\n")
    write("main.toml", '__include__ = "base.toml"\nb = 2\n')
    cfg = parser.parse_args(["--config=main.toml"])
    assert (cfg.a, cfg.b) == (1, 2)


@skip_if_omegaconf_unavailable
def test_include_omegaconf_plus_interpolation(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="omegaconf+")
    parser.add_argument("--config", action="config")
    parser.add_argument("--a", type=str, default="")
    parser.add_argument("--b", type=str, default="")
    write("base.yaml", "a: from base\nb: ${a}\n")
    write("main.yaml", "__include__: base.yaml\na: from main\n")
    cfg = parser.parse_args(["--config=main.yaml"])
    assert (cfg.a, cfg.b) == ("from main", "from main")


# other parse entry points


def test_include_from_config_mixin(tmp_cwd):
    from jsonargparse import FromConfigMixin

    class Component(FromConfigMixin):
        def __init__(self, x: int = 0, y: int = 0):
            self.x = x
            self.y = y

    write("base.json", {"x": 1, "y": 1})
    write("main.json", {"__include__": "base.json", "y": 2})
    component = Component.from_config("main.json")
    assert (component.x, component.y) == (1, 2)


def test_include_from_config_mixin_chained(tmp_cwd):
    from jsonargparse import FromConfigMixin

    class Component(FromConfigMixin):
        def __init__(self, x: int = 0, y: int = 0, z: int = 0):
            self.x, self.y, self.z = x, y, z

    write("one.json", {"x": 1, "y": 1, "z": 1})
    write("two.json", {"__include__": "one.json", "y": 2, "z": 2})
    write("main.json", {"__include__": "two.json", "z": 3})
    component = Component.from_config("main.json")
    assert (component.x, component.y, component.z) == (1, 2, 3)


class Component(FromConfigMixin):
    def __init__(self, x: int, y: int = 0):
        self.x = x
        self.y = y


class LogComponent(Component):
    def __init__(self, log_file: str = "run.log", **kwargs):
        super().__init__(**kwargs)
        self.log_file = log_file


class TimerComponent(Component):
    def __init__(self, interval: int = 60, **kwargs):
        super().__init__(**kwargs)
        self.interval = interval


def test_include_from_config_mixin_class_path_change(tmp_cwd):
    write("base.json", {"class_path": "LogComponent", "init_args": {"log_file": "a.log", "y": 1}})
    main = {"__include__": "base.json", "class_path": "TimerComponent", "init_args": {"x": 2, "interval": 5}}
    write("main.json", main)
    component = Component.from_config("main.json")
    assert isinstance(component, TimerComponent)
    assert (component.x, component.y, component.interval) == (2, 1, 5)


def test_include_from_config_mixin_class_path_in_included(tmp_cwd):
    write("base.json", {"class_path": "LogComponent", "init_args": {"x": 1}})
    component = Component.from_config({"__include__": "base.json", "init_args": {"log_file": "b.log"}})
    assert isinstance(component, LogComponent)
    assert (component.x, component.log_file) == (1, "b.log")


def test_include_subcommand_config(parser, subparser, tmp_cwd):
    subparser.add_argument("--config", action="config")
    subparser.add_argument("--a", type=int, default=0)
    subparser.add_argument("--b", type=int, default=0)
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("fit", subparser)
    write("base.json", {"a": 1, "b": 1})
    write("main.json", {"__include__": "base.json", "b": 2})
    cfg = parser.parse_args(["fit", "--config=main.json"])
    assert (cfg.fit.a, cfg.fit.b) == (1, 2)


def test_include_optional_subclass_sub_config(parser, tmp_cwd):
    parser.add_argument("--config", action="config")
    parser.add_argument("--hook", type=Optional[Hook], sub_configs=True)
    write("base.json", {"class_path": log_hook, "init_args": {"verbose": True}})
    write("hook.json", {"__include__": "base.json", "init_args": {"log_file": "hook.log"}})
    write("main.json", {"hook": "hook.json"})
    cfg = parser.parse_args(["--config=main.json"])
    assert cfg.hook.init_args.verbose is True
    assert cfg.hook.init_args.log_file == "hook.log"
