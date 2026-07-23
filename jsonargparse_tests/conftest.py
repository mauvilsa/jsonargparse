import logging
import os
import platform
import re
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from functools import wraps
from importlib.util import find_spec
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jsonargparse import ArgumentParser, set_parsing_settings
from jsonargparse._loaders_dumpers import json_compact_dump, json_load, yaml_dump, yaml_load
from jsonargparse._optionals import (
    docstring_parser_support,
    fsspec_support,
    jsonnet_support,
    jsonschema_support,
    omegaconf_support,
    pyyaml_available,
    toml_load_available,
    url_support,
)

if docstring_parser_support:
    from docstring_parser import DocstringStyle

    set_parsing_settings(docstring_parse_style=DocstringStyle.GOOGLE)


columns = "200"

is_cpython = platform.python_implementation() == "CPython"
is_posix = os.name == "posix"

json_or_yaml_dump = yaml_dump if pyyaml_available else json_compact_dump
json_or_yaml_load = yaml_load if pyyaml_available else json_load

skip_if_no_pyyaml = pytest.mark.skipif(
    not pyyaml_available,
    reason="PyYAML package is required",
)

skip_if_not_cpython = pytest.mark.skipif(
    not is_cpython,
    reason="only supported in CPython",
)

skip_if_not_posix = pytest.mark.skipif(
    not is_posix,
    reason="only supported in posix systems",
)


skip_if_jsonschema_unavailable = pytest.mark.skipif(
    not jsonschema_support,
    reason="jsonschema package is required",
)

skip_if_fsspec_unavailable = pytest.mark.skipif(
    not fsspec_support,
    reason="fsspec package is required",
)

skip_if_docstring_parser_unavailable = pytest.mark.skipif(
    not docstring_parser_support,
    reason="docstring-parser package is required",
)

skip_if_requests_unavailable = pytest.mark.skipif(
    not url_support,
    reason="requests package is required",
)

responses_available = bool(find_spec("responses"))

skip_if_responses_unavailable = pytest.mark.skipif(
    not responses_available,
    reason="responses package is required",
)

skip_if_omegaconf_unavailable = pytest.mark.skipif(
    not omegaconf_support,
    reason="omegaconf package is required",
)


skip_if_running_as_root = pytest.mark.skipif(
    is_posix and os.geteuid() == 0,
    reason="User is root, permission tests will not work",
)

if responses_available:
    import responses

    responses_activate = responses.activate
else:

    def nothing_decorator(func):
        return func

    responses_activate = nothing_decorator


def parser_modes(test_function):
    if "JSONARGPARSE_OMEGACONF_FULL_TEST" in os.environ:
        parser_modes = ["yaml"]
    else:
        parser_modes = ["json"]
        if toml_load_available:
            parser_modes += ["toml"]
        if pyyaml_available:
            parser_modes += ["yaml"]
        if jsonnet_support:
            parser_modes += ["jsonnet"]
        if omegaconf_support:
            parser_modes += ["omegaconf"]
    return pytest.mark.parametrize("parser", parser_modes, indirect=True)(test_function)


@pytest.fixture
def parser(request) -> ArgumentParser:
    kwargs = {}
    if getattr(request, "param", None):
        kwargs["parser_mode"] = request.param
    return ArgumentParser(exit_on_error=False, **kwargs)


@pytest.fixture
def subparser() -> ArgumentParser:
    return ArgumentParser(exit_on_error=False)


@pytest.fixture
def subsubparser() -> ArgumentParser:
    return ArgumentParser(exit_on_error=False)


@pytest.fixture
def clear_instantiators():
    from jsonargparse._instantiation import _class_instantiators

    _class_instantiators.clear()
    yield
    _class_instantiators.clear()


@pytest.fixture
def example_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="app", exit_on_error=False)
    group_1 = parser.add_argument_group("Group 1", name="group1")
    group_1.add_argument("--bool", type=bool, default=True)
    group_2 = parser.add_argument_group("Group 2")
    group_2.add_argument("--nums.val1", type=int, default=1)
    group_2.add_argument("--nums.val2", type=float, default=2.0)
    return parser


@pytest.fixture
def parsing_settings_patch():
    with patch.dict("jsonargparse._common.parsing_settings"):
        yield


@pytest.fixture
def subclass_behavior(monkeypatch) -> Iterator[None]:
    from jsonargparse._typehints import _cached_class_parsers

    monkeypatch.setattr("jsonargparse._common.subclasses_enabled_types", set())
    monkeypatch.setattr("jsonargparse._common.subclasses_disabled_types", set())
    _cached_class_parsers.clear()
    with patch.dict("jsonargparse._common.subclasses_disabled_selectors"):
        yield
    _cached_class_parsers.clear()


@pytest.fixture
def tmp_cwd(tmpdir) -> Iterator[Path]:
    with tmpdir.as_cwd():
        yield Path(tmpdir)


@pytest.fixture
def file_r(tmp_cwd) -> Iterator[str]:
    filename = "file_r"
    Path(filename).touch()
    yield filename


@pytest.fixture
def mock_stdin():
    @contextmanager
    def _mock_stdin(data: str):
        mock = MagicMock()
        mock.read.side_effect = [data, ""]
        with patch("sys.stdin", mock):
            yield

    return _mock_stdin


@pytest.fixture
def logger() -> logging.Logger:
    logger = logging.getLogger(__name__)
    logger.level = logging.DEBUG
    logger.parent = None
    logger.handlers = [logging.StreamHandler()]
    return logger


def patch_parsing_settings(fn):
    @wraps(fn)
    def _patch_parsing_settings(*args, **kwargs):
        with patch.dict("jsonargparse._common.parsing_settings"):
            return fn(*args, **kwargs)

    return _patch_parsing_settings


@contextmanager
def capture_logs(logger: logging.Logger) -> Iterator[StringIO]:
    with ExitStack() as stack:
        captured = StringIO()
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                stack.enter_context(patch.object(handler, "stream", captured))
        yield captured


@contextmanager
def source_unavailable(obj=None):
    if obj and obj.__module__ in sys.modules:
        del sys.modules[obj.__module__]
    with patch("inspect.getsource", side_effect=OSError("mock source code not available")):
        yield


@pytest.fixture(autouse=True, scope="session")
def no_color():
    with patch.dict(os.environ, {"NO_COLOR": "true"}):
        yield


def get_parser_help(parser: ArgumentParser, strip=False, columns=columns) -> str:
    out = StringIO()
    with patch.dict(os.environ, {"COLUMNS": columns}):
        parser.print_help(out)
    if strip:
        return re.sub("  *", " ", out.getvalue())
    return out.getvalue()


def get_parse_args_stdout(parser: ArgumentParser, args: list[str]) -> str:
    out = StringIO()
    with patch.dict(os.environ, {"COLUMNS": columns}), redirect_stdout(out), pytest.raises(SystemExit):
        parser.parse_args(args)
    return out.getvalue()


def get_parse_args_stderr(parser: ArgumentParser, args: list[str]) -> str:
    err = StringIO()
    with patch.object(parser, "exit_on_error", return_value=True):
        with patch.dict(os.environ, {"COLUMNS": columns}), redirect_stderr(err), pytest.raises(SystemExit):
            parser.parse_args(args)
    return err.getvalue()


class BaseClass:
    def __init__(self):
        pass  # pragma: no cover


def wrap_fn(fn):
    @wraps(fn)
    def wrapped_fn(*args, **kwargs):
        return fn(*args, **kwargs)  # pragma: no cover

    return wrapped_fn
