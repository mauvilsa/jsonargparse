from __future__ import annotations

import copy
import dataclasses
import json
import os
import pickle
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from jsonargparse import ArgumentError, ArgumentParser, Namespace, set_loader, set_parsing_settings
from jsonargparse._formatters import describe_source
from jsonargparse._namespace import get_provenance
from jsonargparse._optionals import omegaconf_support, pyyaml_available, ruamel_support
from jsonargparse_tests.conftest import (
    get_parse_args_stderr,
    get_parse_args_stdout,
    get_parser_help,
    skip_if_no_pyyaml,
)

skip_if_no_ruamel = pytest.mark.skipif(
    not (ruamel_support and pyyaml_available),
    reason="ruamel.yaml and PyYAML packages are required",
)


@dataclasses.dataclass
class Encoder:
    layers: int = 2
    dropout: float = 0.0


@dataclasses.dataclass
class Model:
    lr: float = 0.1
    encoder: Encoder = dataclasses.field(default_factory=Encoder)


class Optimizer:
    def __init__(self, lr: float = 0.1):
        self.lr = lr  # pragma: no cover


class SGD(Optimizer):
    def __init__(self, lr: float = 0.2, momentum: float = 0.9):  # pragma: no cover
        super().__init__(lr)
        self.momentum = momentum


class Trainer:
    def __init__(self, opts: Optional[list[Optimizer]] = None):
        self.opts = opts  # pragma: no cover


sgd = f"{__name__}.SGD"
optimizer = f"{__name__}.Optimizer"


@pytest.fixture
def parser() -> ArgumentParser:
    """Parser in json mode, for which there are no line numbers, so that extras are not required."""
    parser = ArgumentParser(exit_on_error=False, parser_mode="json", env_prefix="APP")
    parser.add_argument("--config", action="config")
    return parser


@pytest.fixture
def yaml_parser() -> ArgumentParser:
    parser = ArgumentParser(exit_on_error=False, parser_mode="yaml", env_prefix="APP")
    parser.add_argument("--config", action="config")
    return parser


def get_sources(cfg: Namespace) -> dict[str, str]:
    """Returns the description of where each value came from, except for config arguments.

    There is no public way to get the provenance, other than the provenance flag of print config, which requires
    ruamel.yaml. The internals are used so that tracking the provenance is tested without extras.
    """
    return {
        key: describe_source(source)
        for key, source in get_provenance(cfg).items()
        if key.rsplit(".", 1)[-1] != "config"
    }


# sources


def test_default(parser):
    parser.add_argument("pos", nargs="?", default="p")
    parser.add_argument("--val", type=int, default=3)
    parser.add_argument("--name", type=str, default="x")
    assert get_sources(parser.parse_args([])) == {"pos": "default", "val": "default", "name": "default"}


def test_command_line(parser):
    parser.add_argument("pos", type=int)
    parser.add_argument("--val", type=int, default=3)
    parser.add_argument("--flag", action="store_true")
    assert get_sources(parser.parse_args(["1", "--val=7", "--flag"])) == {
        "pos": "command line argument pos",
        "val": "command line argument --val",
        "flag": "command line argument --flag",
    }


def test_command_line_positional_left_out(parser):
    parser.add_argument("pos", nargs="?", default="p")
    parser.add_argument("--val", type=int, default=3)
    assert get_sources(parser.parse_args(["--val=7"])) == {"pos": "default", "val": "command line argument --val"}


def test_optionals_as_positionals(parser, parsing_settings_patch):
    set_parsing_settings(parse_optionals_as_positionals=True)
    parser.add_argument("--val", type=int, default=3)
    assert get_sources(parser.parse_args(["7"])) == {"val": "command line argument --val"}


def test_environment_variable(parser, monkeypatch):
    parser.default_env = True
    parser.add_argument("--val", type=int, default=3)
    parser.add_argument("--model", type=Model)
    monkeypatch.setenv("APP_VAL", "11")
    monkeypatch.setenv("APP_MODEL__LR", "0.5")
    assert get_sources(parser.parse_args([])) == {
        "val": "environment variable APP_VAL",
        "model.lr": "environment variable APP_MODEL__LR",
        "model.encoder.layers": "default",
        "model.encoder.dropout": "default",
    }


def test_config_file(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=3)
    parser.add_argument("--other", type=int, default=3)
    Path("cfg.json").write_text('{"other": 4, "val": 5}')
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == {
        "val": "config file cfg.json",
        "other": "config file cfg.json",
    }


def test_config_string(parser):
    parser.add_argument("--val", type=int, default=3)
    assert get_sources(parser.parse_args(['--config={"val": 5}'])) == {"val": "config string"}


def test_default_config_file(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=3)
    Path("defaults.json").write_text('{"val": 9}')
    parser.default_config_files = ["defaults.json"]
    assert get_sources(parser.parse_args([])) == {"val": "default config file defaults.json"}


def test_config_file_inside_config_file(parser, tmp_cwd):
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    Path("inner.json").write_text('{"b": 2}')
    Path("outer.json").write_text('{"a": 1, "config": "inner.json"}')
    assert get_sources(parser.parse_args(["--config=outer.json"])) == {
        "a": "config file outer.json",
        "b": "config file inner.json",
    }


def test_custom_loader_config_file_without_line_numbers(tmp_cwd):
    with patch.dict("jsonargparse._loaders_dumpers.loaders"):
        set_loader("provenance_custom", json.loads)
        parser = ArgumentParser(exit_on_error=False, parser_mode="provenance_custom")
        parser.add_argument("--config", action="config")
        parser.add_argument("--val", type=int, default=0)
        Path("cfg.custom").write_text('{"val": 2}')
        assert get_sources(parser.parse_args(["--config=cfg.custom"])) == {"val": "config file cfg.custom"}


def test_subconfig_file_path_relative_to_working_directory(parser, tmp_cwd):
    parser.add_argument("--model", type=Model, sub_configs=True)
    Path("cfgs").mkdir()
    Path("cfgs", "model.json").write_text('{"lr": 0.001}')
    Path("cfgs", "main.json").write_text('{"model": "model.json"}')
    sources = get_sources(parser.parse_args(["--config=" + str(Path("cfgs", "main.json"))]))
    assert sources["model.lr"] == f"config file {Path('cfgs', 'model.json')}"


def test_config_file_path_outside_working_directory(parser, tmp_path, monkeypatch):
    defaults = tmp_path / "defaults.json"
    defaults.write_text('{"val": 9}')
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    parser.add_argument("--val", type=int, default=3)
    parser.default_config_files = [str(defaults)]
    assert get_sources(parser.parse_args([])) == {"val": f"default config file {defaults}"}


# precedence between sources


def test_precedence(parser, tmp_cwd, monkeypatch):
    parser.default_env = True
    for key in "abcde":
        parser.add_argument(f"--{key}", type=int, default=0)
    Path("defaults.json").write_text('{"b": 1, "c": 1, "d": 1, "e": 1}')
    Path("cfg.json").write_text('{"d": 3, "e": 3}')
    parser.default_config_files = ["defaults.json"]
    monkeypatch.setenv("APP_C", "2")
    assert get_sources(parser.parse_args(["--config=cfg.json", "--e=4"])) == {
        "a": "default",
        "b": "default config file defaults.json",
        "c": "environment variable APP_C",
        "d": "config file cfg.json",
        "e": "command line argument --e",
    }


def test_value_equal_to_default(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=10)
    Path("cfg.json").write_text('{"val": 10}')
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == {"val": "config file cfg.json"}


def test_later_config_file_overrides(parser, tmp_cwd):
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    Path("one.json").write_text('{"a": 1, "b": 1}')
    Path("two.json").write_text('{"b": 2}')
    assert get_sources(parser.parse_args(["--config=one.json", "--config=two.json"])) == {
        "a": "config file one.json",
        "b": "config file two.json",
    }


def test_parse_args_namespace_keeps_provenance(parser, tmp_cwd):
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    Path("cfg.json").write_text('{"a": 1}')
    cfg = parser.parse_args(["--config=cfg.json"])
    cfg = parser.parse_args(["--b=2"], namespace=cfg)
    assert get_sources(cfg) == {"a": "config file cfg.json", "b": "command line argument --b"}


# nested values


def test_nested_dataclass(parser, tmp_cwd):
    parser.add_argument("--model", type=Model)
    Path("cfg.json").write_text('{"model": {"lr": 0.001, "encoder": {"layers": 12}}}')
    assert get_sources(parser.parse_args(["--config=cfg.json", "--model.encoder.dropout=0.3"])) == {
        "model.lr": "config file cfg.json",
        "model.encoder.layers": "config file cfg.json",
        "model.encoder.dropout": "command line argument --model.encoder.dropout",
    }


def test_optional_dataclass(parser, tmp_cwd):
    parser.add_argument("--encoder", type=Optional[Encoder], default=None)
    Path("cfg.json").write_text('{"encoder": {"layers": 12}}')
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == {
        "encoder.layers": "config file cfg.json",
        "encoder.dropout": "default",
    }


def test_class_group_subconfig_file(parser, tmp_cwd):
    parser.add_argument("--model", type=Model, sub_configs=True)
    Path("model.json").write_text('{"lr": 0.001, "encoder": {"layers": 12}}')
    Path("cfg.json").write_text('{"model": "model.json"}')
    expected = {
        "model.lr": "config file model.json",
        "model.encoder.layers": "config file model.json",
        "model.encoder.dropout": "default",
    }
    assert get_sources(parser.parse_args(["--model=model.json"])) == expected
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == expected


def test_subclass_from_config_file(parser, tmp_cwd):
    parser.add_argument("--opt", type=Optimizer)
    Path("cfg.json").write_text(json.dumps({"opt": {"class_path": sgd, "init_args": {"momentum": 0.5}}}))
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == {
        "opt.class_path": "config file cfg.json",
        "opt.init_args.lr": "default",
        "opt.init_args.momentum": "config file cfg.json",
    }


def test_subclass_init_arg_from_command_line(parser, tmp_cwd):
    parser.add_argument("--opt", type=Optimizer)
    Path("cfg.json").write_text(json.dumps({"opt": {"class_path": sgd, "init_args": {"momentum": 0.5}}}))
    assert get_sources(parser.parse_args(["--config=cfg.json", "--opt.init_args.lr=0.9"])) == {
        "opt.class_path": "config file cfg.json",
        "opt.init_args.lr": "command line argument --opt.init_args.lr",
        "opt.init_args.momentum": "config file cfg.json",
    }


def test_subclass_init_args_in_later_config_file(parser, tmp_cwd):
    parser.add_argument("--opt", type=Optimizer)
    Path("one.json").write_text(json.dumps({"opt": {"class_path": sgd}}))
    Path("two.json").write_text('{"opt": {"init_args": {"momentum": 0.5}}}')
    assert get_sources(parser.parse_args(["--config=one.json", "--config=two.json"])) == {
        "opt.class_path": "config file one.json",
        "opt.init_args.lr": "default",
        "opt.init_args.momentum": "config file two.json",
    }


def test_subclass_from_command_line(parser):
    parser.add_argument("--opt", type=Optimizer)
    assert get_sources(parser.parse_args([f"--opt={sgd}", "--opt.init_args.momentum=0.5"])) == {
        "opt.class_path": "command line argument --opt",
        "opt.init_args.lr": "default",
        "opt.init_args.momentum": "command line argument --opt.init_args.momentum",
    }


def test_subclass_subconfig_file(parser, tmp_cwd):
    parser.add_argument("--opt", type=Optimizer, sub_configs=True)
    Path("sub.json").write_text(json.dumps({"class_path": sgd, "init_args": {"momentum": 0.5}}))
    Path("cfg.json").write_text('{"opt": "sub.json"}')
    expected = {
        "opt.class_path": "config file sub.json",
        "opt.init_args.lr": "default",
        "opt.init_args.momentum": "config file sub.json",
    }
    assert get_sources(parser.parse_args(["--opt=sub.json"])) == expected
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == expected


def test_subcommand(parser, subparser, tmp_cwd):
    subparser.add_argument("--config", action="config")
    subparser.add_argument("--val", type=int, default=1)
    subparser.add_argument("--other", type=int, default=1)
    parser.add_subcommands().add_subcommand("fit", subparser)
    Path("fit.json").write_text('{"val": 2}')
    Path("cfg.json").write_text('{"fit": {"val": 2}}')
    command_line = {"subcommand": "command line argument subcommand", "fit.other": "command line argument --other"}
    sources = get_sources(parser.parse_args(["fit", "--config=fit.json", "--other=3"]))
    assert sources == {**command_line, "fit.val": "config file fit.json"}
    sources = get_sources(parser.parse_args(["--config=cfg.json", "fit", "--other=3"]))
    assert sources == {**command_line, "fit.val": "config file cfg.json"}


def test_subcommand_environment_variable(parser, subparser, monkeypatch):
    parser.default_env = True
    subparser.add_argument("--val", type=int, default=1)
    parser.add_subcommands().add_subcommand("fit", subparser)
    monkeypatch.setenv("APP_SUBCOMMAND", "fit")
    monkeypatch.setenv("APP_FIT__VAL", "2")
    assert get_sources(parser.parse_args([])) == {
        "subcommand": "environment variable APP_SUBCOMMAND",
        "fit.val": "environment variable APP_FIT__VAL",
    }


def test_list_of_subclasses(parser, tmp_cwd):
    parser.add_argument("--opts", type=list[Optimizer])
    config = {"opts": [{"class_path": sgd, "init_args": {"momentum": 0.5}}, {"class_path": optimizer}]}
    Path("cfg.json").write_text(json.dumps(config))
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == {
        "opts[0].class_path": "config file cfg.json",
        "opts[0].init_args.lr": "default",
        "opts[0].init_args.momentum": "config file cfg.json",
        "opts[1].class_path": "config file cfg.json",
        "opts[1].init_args.lr": "default",
    }


def test_list_of_subclasses_appended_from_command_line(parser, tmp_cwd):
    parser.add_argument("--opts", type=list[Optimizer])
    Path("cfg.json").write_text(json.dumps({"opts": [{"class_path": sgd, "init_args": {"momentum": 0.5}}]}))
    args = ["--config=cfg.json", f"--opts+={optimizer}", "--opts.init_args.lr=0.7"]
    assert get_sources(parser.parse_args(args)) == {
        "opts[0].class_path": "config file cfg.json",
        "opts[0].init_args.lr": "default",
        "opts[0].init_args.momentum": "config file cfg.json",
        "opts[1].class_path": "command line argument --opts+",
        "opts[1].init_args.lr": "command line argument --opts.init_args.lr",
    }


def test_list_of_subclasses_item_from_subconfig_file(parser, tmp_cwd):
    parser.add_argument("--opts", type=list[Optimizer], sub_configs=True)
    Path("item.json").write_text(json.dumps({"class_path": sgd, "init_args": {"momentum": 0.5}}))
    Path("cfg.json").write_text('{"opts": ["item.json"]}')
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == {
        "opts[0].class_path": "config file item.json",
        "opts[0].init_args.lr": "default",
        "opts[0].init_args.momentum": "config file item.json",
    }


def test_list_of_subclasses_from_subconfig_file(parser, tmp_cwd):
    parser.add_argument("--opts", type=list[Optimizer], sub_configs=True)
    Path("opts.json").write_text(json.dumps([{"class_path": sgd, "init_args": {"momentum": 0.5}}]))
    assert get_sources(parser.parse_args(["--opts=opts.json"])) == {
        "opts[0].class_path": "config file opts.json",
        "opts[0].init_args.lr": "default",
        "opts[0].init_args.momentum": "config file opts.json",
    }


def test_list_of_subclasses_in_init_args(parser, tmp_cwd):
    parser.add_argument("--trainer", type=Trainer)
    config = {"trainer": {"class_path": f"{__name__}.Trainer", "init_args": {"opts": [{"class_path": sgd}]}}}
    Path("cfg.json").write_text(json.dumps(config))
    assert get_sources(parser.parse_args(["--config=cfg.json"])) == {
        "trainer.class_path": "config file cfg.json",
        "trainer.init_args.opts[0].class_path": "config file cfg.json",
        "trainer.init_args.opts[0].init_args.lr": "default",
        "trainer.init_args.opts[0].init_args.momentum": "default",
    }


def test_dict_of_subclasses(parser, tmp_cwd):
    parser.add_argument("--opts", type=dict[str, Optimizer])
    Path("cfg.json").write_text(json.dumps({"opts": {"a": {"class_path": sgd, "init_args": {"momentum": 0.5}}}}))
    assert get_sources(parser.parse_args(["--config=cfg.json", f"--opts.b={optimizer}"])) == {
        "opts.a.class_path": "config file cfg.json",
        "opts.a.init_args.lr": "default",
        "opts.a.init_args.momentum": "config file cfg.json",
        "opts.b.class_path": "command line argument --opts.b",
        "opts.b.init_args.lr": "default",
    }


def test_list_and_dict_values(parser, tmp_cwd):
    parser.add_argument("--items", type=list[int], default=[])
    parser.add_argument("--mapping", type=dict[str, int], default={})
    Path("cfg.json").write_text('{"items": [1], "mapping": {"a": 1}}')
    assert get_sources(parser.parse_args(["--config=cfg.json", "--items+=2"])) == {
        "items": "command line argument --items+",
        "mapping": "config file cfg.json",
    }


@pytest.mark.skipif(not omegaconf_support, reason="omegaconf package is required")
def test_omegaconf_interpolation(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False, parser_mode="omegaconf+")
    parser.add_argument("--config", action="config")
    parser.add_argument("--a", type=str, default="x")
    parser.add_argument("--b", type=str, default="y")
    Path("cfg.yaml").write_text("a: z\nb: ${a}\n")
    assert get_sources(parser.parse_args(["--config=cfg.yaml"])) == {
        "a": "config file cfg.yaml:1",
        "b": "config file cfg.yaml:2",
    }


# provenance is not visible otherwise


def test_provenance_not_part_of_equality(parser):
    parser.add_argument("--val", type=int, default=1)
    from_command_line = parser.parse_args(["--val=1"])
    from_default = parser.parse_args([])
    assert get_sources(from_command_line) != get_sources(from_default)
    assert from_command_line == from_default


def test_deepcopy_parsed_namespace(parser, tmp_cwd):
    parser.add_argument("--opts", type=list[Optimizer])
    Path("cfg.json").write_text(json.dumps({"opts": [{"class_path": sgd, "init_args": {"momentum": 0.5}}]}))
    cfg = parser.parse_args(["--config=cfg.json"])
    copied = copy.deepcopy(cfg)
    assert copied == cfg
    assert get_sources(copied) == get_sources(cfg)


def test_pickle_parsed_namespace(parser, tmp_cwd):
    parser.add_argument("--opt", type=Optimizer)
    Path("cfg.json").write_text(json.dumps({"opt": {"class_path": sgd}}))
    cfg = parser.parse_args(["--config=cfg.json"])
    unpickled = pickle.loads(pickle.dumps(cfg))
    assert unpickled == cfg
    assert get_sources(unpickled) == get_sources(cfg)


# error messages


def get_error(parser: ArgumentParser, args: list[str]) -> str:
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(args)
    return str(ctx.value)


def test_error_config_file(parser, tmp_cwd):
    parser.add_argument("--a", type=int, default=0)
    parser.add_argument("--val", type=int, default=0)
    Path("cfg.json").write_text('{"a": 1, "val": "abc"}')
    assert get_error(parser, ["--config=cfg.json"]).endswith("Got value: abc\n  Source: config file cfg.json")


def test_error_later_config_file(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=0)
    Path("one.json").write_text('{"val": 1}')
    Path("two.json").write_text('{"val": "abc"}')
    assert get_error(parser, ["--config=one.json", "--config=two.json"]).endswith("\n  Source: config file two.json")


def test_error_config_string(parser):
    parser.add_argument("--val", type=int, default=0)
    assert get_error(parser, ['--config={"val": "abc"}']).endswith("\n  Source: config string")


def test_error_config_file_syntax(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=0)
    Path("cfg.json").write_text('{"val": [1, 2}')
    error = get_error(parser, ["--config=cfg.json"])
    assert error.startswith("Problems parsing config:")
    assert error.endswith("\n  Source: config file cfg.json")


def test_error_default_config_file(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=0)
    Path("defaults.json").write_text('{"val": "abc"}')
    parser.default_config_files = ["defaults.json"]
    assert get_error(parser, []).endswith("\n  Source: default config file defaults.json")


def test_error_environment_variable(parser, monkeypatch):
    parser.default_env = True
    parser.add_argument("--val", type=int, default=0)
    monkeypatch.setenv("APP_VAL", "abc")
    assert get_error(parser, []).endswith("\n  Source: environment variable APP_VAL")


def test_error_unknown_key_in_config_file(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=0)
    Path("cfg.json").write_text('{"val": 1, "unknown": 2}')
    expected = "Option 'unknown' is not accepted\n  Source: config file cfg.json"
    assert get_error(parser, ["--config=cfg.json"]) == expected


def test_error_nested_value_in_config_file(parser, tmp_cwd):
    parser.add_argument("--opt", type=Optimizer)
    Path("cfg.json").write_text(json.dumps({"opt": {"class_path": sgd, "init_args": {"momentum": "abc"}}}))
    error = get_error(parser, ["--config=cfg.json"])
    assert 'Parser key "momentum"' in error
    assert error.count("Source:") == 1
    assert error.endswith("\n  Source: config file cfg.json")


def test_error_class_group_subconfig_file(parser, tmp_cwd):
    parser.add_argument("--model", type=Model, sub_configs=True)
    Path("model.json").write_text('{"lr": "abc"}')
    assert get_error(parser, ["--model=model.json"]).endswith("\n  Source: config file model.json")


def test_error_config_file_path_relative_to_working_directory(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=0)
    Path("cfgs").mkdir()
    Path("cfgs", "cfg.json").write_text('{"val": "abc"}')
    error = get_error(parser, ["--config=" + str(Path("cfgs", "cfg.json"))])
    assert error.endswith(f"\n  Source: config file {Path('cfgs', 'cfg.json')}")


def test_error_subconfig_file_path_relative_to_working_directory(parser, tmp_cwd):
    parser.add_argument("--model", type=Model, sub_configs=True)
    Path("cfgs").mkdir()
    Path("cfgs", "model.json").write_text('{"lr": "abc"}')
    Path("cfgs", "main.json").write_text('{"model": "model.json"}')
    error = get_error(parser, ["--config=" + str(Path("cfgs", "main.json"))])
    assert error.endswith(f"\n  Source: config file {Path('cfgs', 'model.json')}")


def test_error_command_line(parser):
    parser.add_argument("--val", type=int, default=0)
    assert get_error(parser, ["--val=abc"]).endswith("Got value: abc\n  Source: command line argument --val")


def test_error_command_line_nested_option(parser):
    parser.add_argument("--opt", type=Optimizer)
    error = get_error(parser, [f"--opt={sgd}", "--opt.init_args.momentum=abc"])
    assert error.count("Source:") == 1
    assert error.endswith("Source: command line argument --opt.init_args.momentum")


def test_error_from_argparse_without_source(parser):
    parser.add_argument("--val", type=int, default=0)
    parser.add_argument("--other", type=int, default=0)
    error = get_error(parser, ["--val=1", "--other"])
    assert "expected one argument" in error
    assert "Source:" not in error


def test_error_parse_object_without_source(parser):
    parser.add_argument("--val", type=int, default=0)
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_object({"val": "abc"})
    assert "Source:" not in str(ctx.value)


def test_error_source_printed_to_stderr(parser, tmp_cwd):
    parser.add_argument("--val", type=int, default=0)
    Path("cfg.json").write_text('{"val": "abc"}')
    err = get_parse_args_stderr(parser, ["--config=cfg.json"])
    assert "Got value: abc\n  Source: config file cfg.json\n" in err


# line numbers


@skip_if_no_pyyaml
def test_config_file_line_numbers(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--val", type=int, default=0)
    yaml_parser.add_argument("--model", type=Model)
    Path("cfg.yaml").write_text("val: 1\nmodel:\n  lr: 0.001\n  encoder:\n    layers: 12\n")
    assert get_sources(yaml_parser.parse_args(["--config=cfg.yaml"])) == {
        "val": "config file cfg.yaml:1",
        "model.lr": "config file cfg.yaml:3",
        "model.encoder.layers": "config file cfg.yaml:5",
        "model.encoder.dropout": "default",
    }


@skip_if_no_pyyaml
def test_list_of_subclasses_line_numbers(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--opts", type=list[Optimizer])
    content = f"opts:\n  - class_path: {sgd}\n    init_args:\n      momentum: 0.5\n  - class_path: {optimizer}\n"
    Path("cfg.yaml").write_text(content)
    assert get_sources(yaml_parser.parse_args(["--config=cfg.yaml"])) == {
        "opts[0].class_path": "config file cfg.yaml:2",
        "opts[0].init_args.lr": "default",
        "opts[0].init_args.momentum": "config file cfg.yaml:4",
        "opts[1].class_path": "config file cfg.yaml:5",
        "opts[1].init_args.lr": "default",
    }


@skip_if_no_pyyaml
def test_json_config_file_line_numbers(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--model", type=Model)
    Path("cfg.json").write_text(json.dumps({"model": {"lr": 0.001, "encoder": {"layers": 12}}}, indent=2))
    assert get_sources(yaml_parser.parse_args(["--config=cfg.json"])) == {
        "model.lr": "config file cfg.json:3",
        "model.encoder.layers": "config file cfg.json:5",
        "model.encoder.dropout": "default",
    }


@skip_if_no_pyyaml
def test_default_config_file_line_numbers(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--a", type=int, default=0)
    yaml_parser.add_argument("--val", type=int, default=0)
    Path("defaults.yaml").write_text("a: 1\nval: 9\n")
    yaml_parser.default_config_files = ["defaults.yaml"]
    assert get_sources(yaml_parser.parse_args([])) == {
        "a": "default config file defaults.yaml:1",
        "val": "default config file defaults.yaml:2",
    }


@skip_if_no_pyyaml
def test_subclass_line_numbers(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--opt", type=Optimizer)
    Path("cfg.yaml").write_text(f"opt:\n  class_path: {sgd}\n  init_args:\n    momentum: 0.5\n")
    assert get_sources(yaml_parser.parse_args(["--config=cfg.yaml"])) == {
        "opt.class_path": "config file cfg.yaml:2",
        "opt.init_args.lr": "default",
        "opt.init_args.momentum": "config file cfg.yaml:4",
    }


@skip_if_no_pyyaml
def test_subclass_implicit_init_args_line_numbers(yaml_parser, tmp_cwd):
    """Keys that are not literally in the file, like the class_path, get the line of their closest ancestor."""
    yaml_parser.add_argument("--opt", type=Optimizer)
    Path("cfg.yaml").write_text("opt:\n  lr: 0.5\n")
    assert get_sources(yaml_parser.parse_args(["--config=cfg.yaml"])) == {
        "opt.class_path": "config file cfg.yaml:1",
        "opt.init_args.lr": "config file cfg.yaml:2",
    }


@skip_if_no_pyyaml
def test_subclass_subconfig_file_line_numbers(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--opt", type=Optimizer, sub_configs=True)
    Path("sub.yaml").write_text(f"class_path: {sgd}\ninit_args:\n  momentum: 0.5\n")
    Path("implicit.yaml").write_text("lr: 0.5\n")
    assert get_sources(yaml_parser.parse_args(["--opt=sub.yaml"])) == {
        "opt.class_path": "config file sub.yaml:1",
        "opt.init_args.lr": "default",
        "opt.init_args.momentum": "config file sub.yaml:3",
    }
    assert get_sources(yaml_parser.parse_args(["--opt=implicit.yaml"])) == {
        "opt.class_path": "config file implicit.yaml",
        "opt.init_args.lr": "config file implicit.yaml:1",
    }


@skip_if_no_pyyaml
def test_subcommand_line_numbers(yaml_parser, subparser, tmp_cwd):
    subparser.add_argument("--val", type=int, default=1)
    yaml_parser.add_subcommands().add_subcommand("fit", subparser)
    Path("cfg.yaml").write_text("fit:\n  val: 2\n")
    assert get_sources(yaml_parser.parse_args(["--config=cfg.yaml", "fit"])) == {
        "subcommand": "command line argument subcommand",
        "fit.val": "config file cfg.yaml:2",
    }


@skip_if_no_pyyaml
@pytest.mark.skipif(
    "JSONARGPARSE_OMEGACONF_FULL_TEST" in os.environ,
    reason="the omegaconf yaml loader does not accept duplicate keys",
)
def test_duplicate_key_line_number(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--val", type=int, default=0)
    Path("cfg.yaml").write_text("val: 1\nval: 2\n")
    assert get_sources(yaml_parser.parse_args(["--config=cfg.yaml"])) == {"val": "config file cfg.yaml:2"}


@skip_if_no_pyyaml
def test_error_line_number(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--a", type=int, default=0)
    yaml_parser.add_argument("--val", type=int, default=0)
    Path("cfg.yaml").write_text("a: 1\nval: abc\n")
    expected = "Got value: abc\n  Source: config file cfg.yaml:2\n    2 | val: abc"
    assert get_error(yaml_parser, ["--config=cfg.yaml"]).endswith(expected)


@skip_if_no_pyyaml
def test_error_line_of_single_line_json_is_shortened(yaml_parser, tmp_cwd):
    config = {f"a{num}": num for num in range(20)} | {"val": "abc"} | {f"b{num}": num for num in range(20)}
    for key in config:
        yaml_parser.add_argument(f"--{key}", type=int, default=0)
    Path("cfg.json").write_text(json.dumps(config))
    snippet = get_error(yaml_parser, ["--config=cfg.json"]).splitlines()[-1]
    assert snippet.startswith("    1 | ...")
    assert snippet.endswith("...")
    assert '"val": "abc"' in snippet
    assert len(snippet) < 100


@skip_if_no_pyyaml
def test_error_syntax_without_line_number(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--val", type=int, default=0)
    Path("cfg.yaml").write_text("val: [1, 2\n")
    assert get_error(yaml_parser, ["--config=cfg.yaml"]).endswith("\n  Source: config file cfg.yaml")


@skip_if_no_pyyaml
def test_dump_without_provenance(yaml_parser):
    yaml_parser.add_argument("--val", type=int, default=1)
    cfg = yaml_parser.parse_args(["--val=2"])
    assert yaml_parser.dump(cfg) == "val: 2\n"


# print config provenance flag


def test_help_lists_provenance_flag(parser):
    assert "provenance" in get_parser_help(parser)


@skip_if_no_ruamel
def test_print_config_provenance(yaml_parser, tmp_cwd, monkeypatch):
    yaml_parser.default_env = True
    yaml_parser.add_argument("--val", type=int, default=0)
    yaml_parser.add_argument("--model", type=Model)
    yaml_parser.add_argument("--encoder", type=Optional[Encoder], default=None)
    yaml_parser.add_argument("--opt", type=Optimizer)
    Path("cfg.yaml").write_text(
        f"model:\n  lr: 0.001\n  encoder:\n    layers: 12\nencoder:\n  layers: 3\nopt:\n  class_path: {sgd}\n"
    )
    monkeypatch.setenv("APP_VAL", "7")
    out = get_parse_args_stdout(
        yaml_parser, ["--config=cfg.yaml", "--model.encoder.dropout=0.3", "--print_config=provenance"]
    )
    assert out == (
        "val: 7 # environment variable APP_VAL\n"
        "model:\n"
        "  lr: 0.001 # config file cfg.yaml:2\n"
        "  encoder:\n"
        "    layers: 12 # config file cfg.yaml:4\n"
        "    dropout: 0.3 # command line argument --model.encoder.dropout\n"
        "encoder:\n"
        "  layers: 3 # config file cfg.yaml:6\n"
        "  dropout: 0.0 # default\n"
        "opt:\n"
        f"  class_path: {sgd} # config file cfg.yaml:8\n"
        "  init_args:\n"
        "    lr: 0.2 # default\n"
        "    momentum: 0.9 # default\n"
    )


@skip_if_no_ruamel
def test_print_config_provenance_list_of_subclasses(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--opts", type=list[Optimizer])
    Path("cfg.yaml").write_text(f"opts:\n  - class_path: {sgd}\n    init_args:\n      momentum: 0.5\n")
    out = get_parse_args_stdout(yaml_parser, ["--config=cfg.yaml", "--print_config=provenance"])
    assert out == (
        "opts:\n"
        f"- class_path: {sgd} # config file cfg.yaml:2\n"
        "  init_args:\n"
        "    lr: 0.2 # default\n"
        "    momentum: 0.5 # config file cfg.yaml:4\n"
    )


@skip_if_no_ruamel
def test_print_config_provenance_list_and_dict(yaml_parser, tmp_cwd):
    yaml_parser.add_argument("--items", type=list[int], default=[])
    yaml_parser.add_argument("--mapping", type=dict[str, int], default={})
    Path("cfg.yaml").write_text("items: [1]\nmapping:\n  a: 1\n")
    out = get_parse_args_stdout(yaml_parser, ["--config=cfg.yaml", "--items+=2", "--print_config=provenance"])
    assert out == "items: # command line argument --items+\n- 1\n- 2\nmapping: # config file cfg.yaml:2\n  a: 1\n"


@skip_if_no_ruamel
def test_print_config_provenance_with_comments(yaml_parser):
    yaml_parser.add_argument("--val", type=int, default=1, help="Value.")
    out = get_parse_args_stdout(yaml_parser, ["--val=2", "--print_config=comments,provenance"])
    assert "# Value. (type: int, default: 1)\nval: 2 # command line argument --val\n" in out


@skip_if_no_ruamel
def test_print_config_provenance_with_skip_default(yaml_parser):
    yaml_parser.add_argument("--a", type=int, default=1)
    yaml_parser.add_argument("--b", type=int, default=1)
    out = get_parse_args_stdout(yaml_parser, ["--b=2", "--print_config=provenance,skip_default"])
    assert out == "b: 2 # command line argument --b\n"


@skip_if_no_ruamel
def test_print_config_provenance_multiline_string(yaml_parser):
    yaml_parser.add_argument("--text", type=str, default="multi\nline")
    yaml_parser.add_argument("--val", type=int, default=1)
    out = get_parse_args_stdout(yaml_parser, ["--val=2", "--print_config=provenance"])
    assert out == "# default\ntext: |-\n  multi\n  line\nval: 2 # command line argument --val\n"
