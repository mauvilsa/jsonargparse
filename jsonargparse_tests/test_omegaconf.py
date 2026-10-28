from __future__ import annotations

import json
import math
import multiprocessing
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from jsonargparse import ArgumentParser, Namespace
from jsonargparse._common import parser_context, set_parsing_settings
from jsonargparse._loaders_dumpers import loaders, yaml_dump
from jsonargparse._optionals import omegaconf_absolute_to_relative_paths, omegaconf_support
from jsonargparse.typing import Path_fr
from jsonargparse_tests.conftest import get_parser_help, skip_if_omegaconf_unavailable

if omegaconf_support:
    from omegaconf import OmegaConf, errors


@pytest.fixture(autouse=True)
def patch_loaders():
    with patch.dict("jsonargparse._loaders_dumpers.loaders"):
        yield


@pytest.mark.skipif(
    not (omegaconf_support and "JSONARGPARSE_OMEGACONF_FULL_TEST" in os.environ),
    reason="only for omegaconf as the yaml loader",
)
def test_omegaconf_as_yaml_loader():
    assert loaders["yaml"] is loaders["omegaconf"]


@skip_if_omegaconf_unavailable
@pytest.mark.parametrize("mode", ["omegaconf", "omegaconf+"])
def test_omegaconf_interpolation(mode):
    parser = ArgumentParser(parser_mode=mode)
    parser.add_argument("--server.host", type=str)
    parser.add_argument("--server.port", type=int)
    parser.add_argument("--client.url", type=str)
    parser.add_argument("--config", action="config")

    config = {
        "server": {
            "host": "localhost",
            "port": 80,
        },
        "client": {
            "url": "http://${server.host}:${server.port}/",
        },
    }
    cfg = parser.parse_args([f"--config={yaml_dump(config)}"])
    assert cfg.client.url == "http://localhost:80/"
    assert "url: http://localhost:80/" in parser.dump(cfg)


@skip_if_omegaconf_unavailable
@pytest.mark.parametrize("mode", ["omegaconf", "omegaconf+", "omegaconf+absolute"])
@patch.dict("jsonargparse._common.parsing_settings")
def test_omegaconf_interpolation_in_subcommands(mode, parser, subparser):
    subparser.add_argument("--config", action="config")
    subparser.add_argument("--source", type=str)
    subparser.add_argument("--target", type=str)

    parser.parser_mode = mode.replace("absolute", "")
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("sub", subparser)

    config = {
        "source": "hello",
        "target": "${.source}" if mode == "omegaconf+" else "${source}",
    }

    if mode == "omegaconf+absolute":
        with pytest.raises(errors.InterpolationKeyError):
            parser.parse_args(["sub", f"--config={yaml_dump(config)}"])
        set_parsing_settings(omegaconf_absolute_to_relative_paths=True)

    cfg = parser.parse_args(["sub", f"--config={yaml_dump(config)}"])
    assert cfg.sub.target == "hello"


@dataclass
class Server:
    host: str = "localhost"
    port: int = 80


@dataclass
class Client:
    url: str = "http://example.com:8080"


@skip_if_omegaconf_unavailable
def test_omegaconf_global_interpolation(parser):
    parser.parser_mode = "omegaconf+"
    parser.add_class_arguments(Server, "server")
    parser.add_class_arguments(Client, "client")

    config = {"url": "http://${server.host}:${..server.port}/"}
    cfg = parser.parse_args([f"--client={yaml_dump(config)}"])
    assert cfg.client == Namespace(url="http://localhost:80/")

    cfg = parser.parse_args([f"--client={yaml_dump(config)}", "--server.port=9000"])
    assert cfg.client == Namespace(url="http://localhost:9000/")


@skip_if_omegaconf_unavailable
def test_omegaconf_global_default_config_files_interpolation(parser, tmp_cwd):
    config_path = tmp_cwd / "config.yaml"
    config_path.write_text(yaml_dump({"complex": {"a": 3, "b": 4}, "simple": "${complex.b}"}))

    parser.parser_mode = "omegaconf+"
    parser.add_argument("--config", action="config")
    parser.add_argument("--complex.a", type=int)
    parser.add_argument("--complex.b", type=int)
    parser.add_argument("--simple", type=int)

    cfg = parser.parse_args([f"--config={config_path}", "--complex.b=5"])
    assert cfg.simple == 5

    parser.default_config_files = [str(config_path)]
    cfg = parser.parse_args(["--complex.b=5"])
    assert cfg.simple == 5


@skip_if_omegaconf_unavailable
def test_omegaconf_global_resolver_config(parser):
    OmegaConf.register_resolver("increment", lambda x: x + 1)

    parser.parser_mode = "omegaconf+"
    parser.add_argument("--config", action="config")
    parser.add_argument("--value", type=int, default=0)
    parser.add_argument("--incremented", type=int, default=0)

    assert parser.parse_args([]) == Namespace(config=None, value=0, incremented=0)

    config = {"value": 1, "incremented": "${increment:${value}}"}
    cfg = parser.parse_args([f"--config={yaml_dump(config)}", "--value=5"])
    assert cfg == Namespace(value=5, incremented=6)  # currently config is lost

    OmegaConf.clear_resolver("increment")


@skip_if_omegaconf_unavailable
def test_omegaconf_global_resolver_argument(parser):
    def const(expr: str):
        allowed = {"pi": math.pi}
        return eval(expr, {"__builtins__": None}, allowed)

    OmegaConf.register_resolver("const", const)

    parser.parser_mode = "omegaconf+"
    parser.add_argument("--value", type=float)
    cfg = parser.parse_args(["--value=${const:3*pi/4}"])
    assert cfg.value == 3 * math.pi / 4

    OmegaConf.clear_resolver("const")


@skip_if_omegaconf_unavailable
@patch.dict(os.environ, {"X": "true"})
def test_omegaconf_global_resolver_default(parser):
    parser.parser_mode = "omegaconf+"
    action = parser.add_argument("--env", type=bool, default="${oc.env:X}")
    assert action.default == "${oc.env:X}"

    help_str = get_parser_help(parser)
    assert "default: ${oc.env:X}" in help_str

    cfg = parser.parse_args([])
    assert cfg.env is True


@dataclass
class Nested:
    path: Path_fr


@skip_if_omegaconf_unavailable
@patch.dict(os.environ, {"X": "Y"})
def test_omegaconf_global_path_preserve_relative(parser, tmp_cwd):
    import yaml

    parser.parser_mode = "omegaconf+"
    parser.add_class_arguments(Nested, "nested")
    parser.add_argument("--env")

    subdir = Path("sub")
    subdir.mkdir()
    (subdir / "file").touch()
    nested = subdir / "nested.json"
    nested.write_text(json.dumps({"path": "file"}))

    cfg = parser.parse_args([f"--nested={nested}", "--env=${oc.env:X}"])
    assert cfg.env == "Y"
    assert cfg.nested.path.relative == "file"
    assert cfg.nested.path.cwd == str(tmp_cwd / subdir)

    with parser_context(path_dump_preserve_relative=True):
        dump = yaml.safe_load(parser.dump(cfg))["nested"]["path"]
    assert dump == {"relative": "file", "cwd": str(tmp_cwd / subdir)}


@skip_if_omegaconf_unavailable
def test_omegaconf_inf_nan(parser):
    parser.parser_mode = "omegaconf+"
    parser.add_argument("--a", type=float, default=0.0)
    parser.add_argument("--b", type=float, default=1.0)
    parser.add_argument("--c", type=float, default=float("nan"))
    parser.add_argument("--d", type=float, default=float("inf"))
    parser.add_argument("--e", type=float, default=float("-inf"))

    cfg = parser.parse_args(["--a=2.5", "--b=${a}"])
    assert cfg.a == 2.5
    assert cfg.b == 2.5
    assert math.isnan(cfg.c)
    assert cfg.d == float("inf")
    assert cfg.e == float("-inf")


@skip_if_omegaconf_unavailable
def test_omegaconf_absolute_to_relative_paths():
    data = {
        "a": "x",
        "b": "prefix ${a} suffix",
        "c": {"d": "${b}", "e": "${c.d}"},
        "f": [10, "${c.e}", "${..b}"],
        "g": "${env:USER}",
        "h": "${f[0]}",
    }
    expected = {
        "a": "x",
        "b": "prefix ${.a} suffix",
        "c": {"d": "${..b}", "e": "${.d}"},
        "f": [10, "${..c.e}", "${..b}"],
        "g": "${env:USER}",
        "h": "${.f[0]}",
    }
    assert omegaconf_absolute_to_relative_paths(data) == expected


def parse_in_spawned_process(queue, parser, args):  # pragma: no cover
    try:
        cfg = parser.parse_args(args)
        queue.put(cfg)
    except Exception as ex:
        queue.put(ex)


@skip_if_omegaconf_unavailable
@pytest.mark.skipif(sys.version_info[:3] == (3, 14, 3), reason="not pickleable in Python 3.14.3")
def test_omegaconf_in_spawned_process(parser):
    parser.parser_mode = "omegaconf"
    parser.add_argument("--dict", type=dict)
    assert parser.parse_args(['--dict={"x":1}']).dict == {"x": 1}

    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    process = ctx.Process(target=parse_in_spawned_process, args=(queue, parser, ['--dict={"x":2}']))
    process.start()
    process.join()

    cfg = queue.get()
    assert cfg.dict == {"x": 2}
