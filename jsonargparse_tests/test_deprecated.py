from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import sys
from calendar import Calendar
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from enum import Enum
from importlib import import_module
from inspect import getmodule as inspect_getmodule
from io import StringIO
from types import ModuleType
from typing import Optional
from unittest.mock import patch
from warnings import catch_warnings

import pytest

from jsonargparse import (
    CLI,
    ActionJsonnet,
    ActionJsonSchema,
    ArgumentError,
    ArgumentParser,
    Namespace,
    auto_cli,
    compose_dataclasses,
    get_config_read_mode,
    set_config_read_mode,
    set_docstring_parse_options,
    set_url_support,
)
from jsonargparse._deprecated import (
    ActionEnum,
    ActionJsonnetExtVars,
    ActionOperators,
    ActionPath,
    ActionPathList,
    LoggerProperty,
    ParserError,
    deprecation_warning,
    dict_to_namespace,
    namespace_to_dict,
    shown_deprecation_warnings,
    strip_meta,
    usage_and_exit_error_handler,
)
from jsonargparse._formatters import DefaultHelpFormatter
from jsonargparse._optionals import (
    docstring_parser_support,
    get_docstring_parse_options,
    import_ruamel,
    jsonnet_support,
    pyyaml_available,
    ruamel_support,
    url_support,
)
from jsonargparse._util import argument_error
from jsonargparse.typing import Path
from jsonargparse_tests.conftest import (
    get_parser_help,
    is_posix,
    responses_activate,
    skip_if_docstring_parser_unavailable,
    skip_if_fsspec_unavailable,
    skip_if_jsonschema_unavailable,
    skip_if_requests_unavailable,
    skip_if_responses_unavailable,
)
from jsonargparse_tests.test_dataclasses import DataClassA
from jsonargparse_tests.test_jsonnet import example_2_jsonnet
from jsonargparse_tests.test_paths import paths  # noqa: F401
from jsonargparse_tests.test_signatures import WithMethods
from jsonargparse_tests.test_subclasses import CustomInstantiationBase, instantiator
from jsonargparse_tests.test_subcommands import subcommands_parser  # noqa: F401


@pytest.fixture(autouse=True, scope="module")
def no_pyyaml_skip():
    if not pyyaml_available:
        pytest.skip("pyyaml package is required")


@pytest.fixture(autouse=True)
def clear_shown_deprecation_warnings():
    yield
    shown_deprecation_warnings.clear()


@contextmanager
def suppress_stderr():
    with open(os.devnull, "w") as fnull:
        with redirect_stderr(fnull):
            yield


source = pathlib.Path(__file__).read_text().splitlines()


def assert_deprecation_warn(warns, message, code):
    assert message in str(warns[-1].message)
    if code is None:
        return  # pragma: no cover
    assert pathlib.Path(warns[-1].filename).name == pathlib.Path(__file__).name
    assert code in source[warns[-1].lineno - 1]


def test_deprecation_warning():
    with catch_warnings(record=True) as w:
        message = "Deprecation warning"
        deprecation_warning(None, message)
        assert 2 == len(w)
        assert "only one JsonargparseDeprecationWarning per type is shown" in str(w[0].message)
        assert message == str(w[1].message).strip()


class MyEnum(Enum):
    A = 1
    B = 2
    C = 3


def func(a1: MyEnum = MyEnum["A"]):
    return a1  # pragma: no cover


def test_ActionEnum():
    parser = ArgumentParser(exit_on_error=False)
    with catch_warnings(record=True) as w:
        action = ActionEnum(enum=MyEnum)
    assert_deprecation_warn(
        w,
        message="ActionEnum was deprecated",
        code="ActionEnum(enum=MyEnum)",
    )
    parser.add_argument("--enum", action=action, default=MyEnum.C, help="Description")

    for val in ["A", "B", "C"]:
        assert MyEnum[val] == parser.parse_args(["--enum=" + val]).enum
    for val in ["X", "b", 2]:
        pytest.raises(ArgumentError, lambda: parser.parse_args(["--enum=" + str(val)]))

    cfg = parser.parse_args(["--enum=C"]).clone(with_meta=False)
    assert "enum: C\n" == parser.dump(cfg)

    help_str = get_parser_help(parser)
    assert "Description (type: MyEnum, default: C)" in help_str

    parser = ArgumentParser()
    parser.add_function_arguments(func)
    assert MyEnum["A"] == parser.get_defaults().a1
    assert MyEnum["B"] == parser.parse_args(["--a1=B"]).a1

    pytest.raises(ValueError, ActionEnum)
    pytest.raises(ValueError, lambda: ActionEnum(enum=object))
    pytest.raises(ValueError, lambda: parser.add_argument("--bad1", type=MyEnum, action=True))
    pytest.raises(ValueError, lambda: parser.add_argument("--bad2", type=float, action=action))


def test_ActionOperators():
    parser = ArgumentParser(prog="app", exit_on_error=False)
    with catch_warnings(record=True) as w:
        parser.add_argument("--le0", action=ActionOperators(expr=("<", 0)))
    assert_deprecation_warn(
        w,
        message="ActionOperators was deprecated",
        code='ActionOperators(expr=("<", 0))',
    )
    parser.add_argument(
        "--gt1.a.le4",
        action=ActionOperators(expr=[(">", 1.0), ("<=", 4.0)], join="and", type=float),
    )
    parser.add_argument(
        "--lt5.o.ge10.o.eq7",
        action=ActionOperators(expr=[("<", 5), (">=", 10), ("==", 7)], join="or", type=int),
    )
    parser.add_argument("--ge0", nargs=3, action=ActionOperators(expr=(">=", 0)))

    assert 1.5 == parser.parse_args(["--gt1.a.le4", "1.5"]).gt1.a.le4
    assert 4.0 == parser.parse_args(["--gt1.a.le4", "4.0"]).gt1.a.le4
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--gt1.a.le4", "1.0"]))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--gt1.a.le4", "5.5"]))

    assert 1.5 == parser.parse_string("gt1:\n  a:\n    le4: 1.5").gt1.a.le4
    assert 4.0 == parser.parse_string("gt1:\n  a:\n    le4: 4.0").gt1.a.le4
    pytest.raises(ArgumentError, lambda: parser.parse_string("gt1:\n  a:\n    le4: 1.0"))
    pytest.raises(ArgumentError, lambda: parser.parse_string("gt1:\n  a:\n    le4: 5.5"))

    assert 1.5 == parser.parse_env({"APP_GT1__A__LE4": "1.5"}).gt1.a.le4
    assert 4.0 == parser.parse_env({"APP_GT1__A__LE4": "4.0"}).gt1.a.le4
    pytest.raises(ArgumentError, lambda: parser.parse_env({"APP_GT1__A__LE4": "1.0"}))
    pytest.raises(ArgumentError, lambda: parser.parse_env({"APP_GT1__A__LE4": "5.5"}))

    assert 2 == parser.parse_args(["--lt5.o.ge10.o.eq7", "2"]).lt5.o.ge10.o.eq7
    assert 7 == parser.parse_args(["--lt5.o.ge10.o.eq7", "7"]).lt5.o.ge10.o.eq7
    assert 10 == parser.parse_args(["--lt5.o.ge10.o.eq7", "10"]).lt5.o.ge10.o.eq7
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--lt5.o.ge10.o.eq7", "5"]))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--lt5.o.ge10.o.eq7", "8"]))

    assert [0, 1, 2] == parser.parse_args(["--ge0", "0", "1", "2"]).ge0

    pytest.raises(ValueError, lambda: parser.add_argument("--op1", action=ActionOperators))
    action = ActionOperators(expr=("<", 0))
    pytest.raises(ValueError, lambda: parser.add_argument("--op2", type=float, action=action))
    pytest.raises(ValueError, lambda: parser.add_argument("--op3", nargs=0, action=action))
    pytest.raises(ValueError, ActionOperators)
    pytest.raises(ValueError, lambda: ActionOperators(expr="<"))
    pytest.raises(ValueError, lambda: ActionOperators(expr=[("<", 5), (">=", 10)], join="xor"))


@skip_if_requests_unavailable
def test_url_support_true():
    with catch_warnings(record=True) as w:
        assert "fr" == get_config_read_mode()
    assert_deprecation_warn(
        w,
        message="get_config_read_mode was deprecated",
        code="get_config_read_mode()",
    )
    with catch_warnings(record=True) as w:
        set_url_support(True)
    assert_deprecation_warn(
        w,
        message="set_url_support was deprecated",
        code="set_url_support(True)",
    )
    assert "fur" == get_config_read_mode()
    set_url_support(False)
    assert "fr" == get_config_read_mode()


@pytest.mark.skipif(url_support, reason="requests package should not be installed")
def test_url_support_false():
    with catch_warnings(record=True) as w:
        assert "fr" == get_config_read_mode()
    assert_deprecation_warn(
        w,
        message="get_config_read_mode was deprecated",
        code="get_config_read_mode()",
    )
    with catch_warnings(record=True) as w:
        with pytest.raises(ImportError):
            set_url_support(True)
        assert "set_url_support was deprecated" in str(w[-1].message)
    assert "fr" == get_config_read_mode()
    set_url_support(False)
    assert "fr" == get_config_read_mode()


@skip_if_fsspec_unavailable
def test_set_config_read_mode():
    with catch_warnings(record=True) as w:
        assert "fr" == get_config_read_mode()
    assert_deprecation_warn(
        w,
        message="get_config_read_mode was deprecated",
        code="get_config_read_mode()",
    )
    with catch_warnings(record=True) as w:
        set_config_read_mode(fsspec_enabled=True)
    assert_deprecation_warn(
        w,
        message="set_config_read_mode was deprecated",
        code="set_config_read_mode(fsspec_enabled=True)",
    )
    assert "fsr" == get_config_read_mode()
    set_config_read_mode(fsspec_enabled=False)
    assert "fr" == get_config_read_mode()


def test_instantiate_subclasses():
    parser = ArgumentParser(exit_on_error=False)
    parser.add_argument("--cal", type=Calendar)
    cfg = parser.parse_object({"cal": {"class_path": "calendar.Calendar"}})
    with catch_warnings(record=True) as w:
        cfg_init = parser.instantiate_subclasses(cfg)
    assert_deprecation_warn(
        w,
        message="instantiate_subclasses was deprecated",
        code="parser.instantiate_subclasses(cfg)",
    )
    assert isinstance(cfg_init["cal"], Calendar)


def test_instantiate_classes():
    parser = ArgumentParser(exit_on_error=False)
    parser.add_argument("--cal", type=Calendar)
    cfg = parser.parse_object({"cal": {"class_path": "calendar.Calendar"}})
    with catch_warnings(record=True) as w:
        cfg_init = parser.instantiate_classes(cfg)
    assert_deprecation_warn(
        w,
        message="``instantiate_classes`` was deprecated",
        code="cfg_init = parser.instantiate_classes(cfg)",
    )
    assert isinstance(cfg_init["cal"], Calendar)


def test_add_instantiator_method_deprecated(parser):
    parser.add_argument("--cls", type=CustomInstantiationBase)
    with catch_warnings(record=True) as w:
        parser.add_instantiator(instantiator("custom"), CustomInstantiationBase)
    assert_deprecation_warn(
        w,
        message="``ArgumentParser.add_instantiator`` was deprecated",
        code='parser.add_instantiator(instantiator("custom"), CustomInstantiationBase)',
    )
    cfg = parser.parse_args(["--cls=CustomInstantiationBase"])
    init = parser.instantiate(cfg)
    assert isinstance(init.cls, CustomInstantiationBase)
    assert init.cls.call == "custom"


def function(a1: float):
    return a1  # pragma: no cover


def test_single_function_cli():
    with catch_warnings(record=True) as w:
        parser = CLI(function, return_parser=True, set_defaults={"a1": 3.4})
    assert_deprecation_warn(
        w,
        message="return_parser parameter was deprecated",
        code="CLI(function, return_parser=True,",
    )
    assert isinstance(parser, ArgumentParser)


def cmd1(a1: int):
    return a1  # pragma: no cover


def cmd2(a2: str = "X"):
    return a2  # pragma: no cover


def test_multiple_functions_cli():
    with catch_warnings(record=True) as w:
        parser = CLI([cmd1, cmd2], return_parser=True, set_defaults={"cmd2.a2": "Z"})
    assert_deprecation_warn(
        w,
        message="return_parser parameter was deprecated",
        code="CLI([cmd1, cmd2], return_parser=True,",
    )
    assert isinstance(parser, ArgumentParser)


@contextmanager
def mock_getmodule_locals(parent_fn, locals_list=[]):
    module_name = "_" + parent_fn.__name__

    mock_module = ModuleType(module_name)
    for obj in locals_list + [CLI, auto_cli]:
        setattr(mock_module, obj.__name__, obj)
    sys.modules[module_name] = mock_module

    for obj in locals_list:
        obj.__module__ = module_name

    def patched_getmodule(obj, *args):
        if obj in locals_list or (parent_fn.__name__ in str(obj)):
            return mock_module
        return inspect_getmodule(obj, *args)

    with patch("inspect.getmodule", side_effect=patched_getmodule):
        yield
        del sys.modules[module_name]


@pytest.mark.parametrize("cli_fn", [CLI, auto_cli])
def test_automatic_components_empty_context(cli_fn):
    def empty_context():
        cli_fn()

    with mock_getmodule_locals(empty_context):
        with pytest.raises(ValueError, match="Either components parameter must be given or"):
            with catch_warnings(record=True) as w:
                empty_context()
        assert "explicit is better than implicit" in str(w[-1].message)


@pytest.mark.parametrize("cli_fn", [CLI, auto_cli])
def test_automatic_components_context_function(cli_fn):
    def function(a1: float):
        return a1

    def non_empty_context_function():
        return cli_fn(args=["6.7"])

    with mock_getmodule_locals(non_empty_context_function, [function]):
        with catch_warnings(record=True) as w:
            assert 6.7 == non_empty_context_function()
        assert "explicit is better than implicit" in str(w[-1].message)


@pytest.mark.parametrize("cli_fn", [CLI, auto_cli])
def test_automatic_components_context_class(cli_fn):
    class ClassX:
        def __init__(self, i1: str):
            self.i1 = i1

        def method(self, m1: int):
            return self.i1, m1

    def non_empty_context_class():
        return cli_fn(args=["a", "method", "2"])

    with mock_getmodule_locals(non_empty_context_class, [ClassX]):
        with catch_warnings(record=True) as w:
            assert ("a", 2) == non_empty_context_class()
        assert "explicit is better than implicit" in str(w[-1].message)


class InheritsLoggerProperty(LoggerProperty):
    pass


def test_logger_property():
    with catch_warnings(record=True) as w:
        InheritsLoggerProperty()
    assert_deprecation_warn(
        w,
        message="LoggerProperty was deprecated",
        code="InheritsLoggerProperty()",
    )


def test_logger_property_none():
    with catch_warnings(record=True) as w:
        ArgumentParser(logger=None)
    assert_deprecation_warn(
        w,
        message=" Setting the logger property to None was deprecated",
        code="ArgumentParser(logger=None)",
    )


def test_env_prefix_none():
    with catch_warnings(record=True) as w:
        ArgumentParser(env_prefix=None)
    assert_deprecation_warn(
        w,
        message="env_prefix",
        code="ArgumentParser(env_prefix=None)",
    )


def test_error_handler_parameter():
    with catch_warnings(record=True) as w:
        parser = ArgumentParser(error_handler=usage_and_exit_error_handler)
    code = "ArgumentParser(error_handler=usage_"
    if not is_posix:  # pragma: no cover
        code = None  # for some reason the stack trace differs in windows
    assert_deprecation_warn(
        w,
        message="error_handler was deprecated in v4.20.0",
        code=code,
    )
    with catch_warnings(record=True) as w:
        assert parser.error_handler == usage_and_exit_error_handler
    assert_deprecation_warn(
        w,
        message="error_handler property is deprecated",
        code="parser.error_handler",
    )
    with suppress_stderr(), pytest.raises(SystemExit), catch_warnings(record=True):
        parser.parse_args(["--invalid"])


def test_error_handler_property():
    def custom_error_handler(self, message):
        print("custom_error_handler")
        self.exit(2)

    parser = ArgumentParser()
    with catch_warnings(record=True) as w:
        parser.error_handler = custom_error_handler
    assert_deprecation_warn(
        w,
        message="error_handler was deprecated in v4.20.0",
        code="parser.error_handler = custom_error_handler",
    )
    with catch_warnings(record=True) as w:
        assert parser.error_handler == custom_error_handler
    assert_deprecation_warn(
        w,
        message="error_handler property is deprecated",
        code="parser.error_handler",
    )

    out = StringIO()
    with redirect_stdout(out), pytest.raises(SystemExit):
        parser.parse_args(["--invalid"])
    assert out.getvalue() == "custom_error_handler\n"

    with pytest.raises(ValueError):
        parser.error_handler = "invalid"


def test_ParserError():
    assert isinstance(argument_error(""), ParserError)


def test_parse_as_dict(tmp_cwd):
    with open("config.json", "w") as f:
        f.write("{}")
    with catch_warnings(record=True) as w:
        parser = ArgumentParser(parse_as_dict=True)
    assert_deprecation_warn(
        w,
        message="``parse_as_dict`` parameter was deprecated",
        code="ArgumentParser(parse_as_dict=True)",
    )
    assert {} == parser.parse_args([])
    assert {} == parser.parse_env([])
    assert {} == parser.parse_string("{}")
    assert {} == parser.parse_object({})
    assert {} == parser.parse_path("config.json")
    with catch_warnings(record=True) as w:
        result = parser.instantiate_classes({})
    assert {} == result
    assert_deprecation_warn(
        w,
        message="``instantiate_classes`` was deprecated",
        code="result = parser.instantiate_classes({})",
    )
    assert "{}\n" == parser.dump({})
    parser.save({}, "config.yaml")
    with open("config.yaml") as f:
        assert "{}\n" == f.read()


def test_default_meta_property(parser):
    with catch_warnings(record=True) as w:
        assert True is parser.default_meta
    assert_deprecation_warn(
        w,
        message="``default_meta`` property was deprecated",
        code="True is parser.default_meta",
    )
    with catch_warnings(record=True) as w:
        parser.default_meta = False
    assert_deprecation_warn(
        w,
        message="``default_meta`` property was deprecated",
        code="parser.default_meta = False",
    )
    assert False is parser.default_meta
    parser = ArgumentParser(default_meta=False)
    assert False is parser.default_meta
    parser.default_meta = True
    assert True is parser.default_meta
    with pytest.raises(ValueError) as ctx:
        parser.default_meta = "invalid"
    ctx.match("default_meta expects a boolean")


def test_parse_with_meta_parameter(parser):
    with catch_warnings(record=True) as w:
        parser.parse_args([], with_meta=False)
    assert_deprecation_warn(
        w,
        message="``with_meta`` parameter was deprecated in v4.44.0 and will be removed in v5.0.0",
        code="parser.parse_args([], with_meta=False)",
    )


def test_deprecated_skip_check_method(parser):
    parser.add_argument("--key", type=int)
    cfg = Namespace(key=1)
    with catch_warnings(record=True) as w:
        parser.check_config(cfg)
    assert_deprecation_warn(
        w,
        message="ArgumentParser.check_config was deprecated",
        code="parser.check_config(cfg)",
    )


def test_deprecated_dump_skip_check_parameter(parser):
    parser.add_argument("--key", type=int)
    cfg = Namespace(key="-")
    with catch_warnings(record=True) as w:
        dump = parser.dump(cfg, skip_check=True)
    assert "-" in dump
    assert_deprecation_warn(
        w,
        message="skip_check parameter was deprecated",
        code="parser.dump(cfg, skip_check=True)",
    )


def test_ActionPath(tmp_cwd):
    os.mkdir(os.path.join(tmp_cwd, "example"))
    rel_yaml_file = os.path.join("..", "example", "example.yaml")
    abs_yaml_file = os.path.realpath(os.path.join(tmp_cwd, "example", rel_yaml_file))
    with open(abs_yaml_file, "w") as output_file:
        output_file.write("file: " + rel_yaml_file + "\ndir: " + str(tmp_cwd) + "\n")

    parser = ArgumentParser(exit_on_error=False)
    parser.add_argument("--cfg", action="config")
    with catch_warnings(record=True) as w:
        parser.add_argument("--file", action=ActionPath(mode="fr"))
    assert_deprecation_warn(
        w,
        message="ActionPath was deprecated",
        code='ActionPath(mode="fr")',
    )
    parser.add_argument("--dir", action=ActionPath(mode="drw"))
    parser.add_argument("--files", nargs="+", action=ActionPath(mode="fr"))

    cfg = parser.parse_args(["--cfg", abs_yaml_file])
    assert str(tmp_cwd) == os.path.realpath(cfg.dir.absolute)
    assert abs_yaml_file == os.path.realpath(cfg.cfg[0].relative)
    assert abs_yaml_file == os.path.realpath(cfg.cfg[0].absolute)
    assert rel_yaml_file == cfg.file.relative
    assert abs_yaml_file == os.path.realpath(cfg.file.absolute)
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--cfg", abs_yaml_file + "~"]))

    cfg = parser.parse_args(["--cfg", "file: " + abs_yaml_file + "\ndir: " + str(tmp_cwd) + "\n"])
    assert str(tmp_cwd) == os.path.realpath(cfg.dir.absolute)
    assert cfg.cfg[0] is None
    assert abs_yaml_file == os.path.realpath(cfg.file.absolute)
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--cfg", '{"k":"v"}']))

    cfg = parser.parse_args(["--file", abs_yaml_file, "--dir", str(tmp_cwd)])
    assert str(tmp_cwd) == os.path.realpath(cfg.dir.absolute)
    assert abs_yaml_file == os.path.realpath(cfg.file.absolute)
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--dir", abs_yaml_file]))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--file", str(tmp_cwd)]))

    cfg = parser.parse_args(["--files", abs_yaml_file, abs_yaml_file])
    assert isinstance(cfg.files, list)
    assert 2 == len(cfg.files)
    assert abs_yaml_file == os.path.realpath(cfg.files[-1].absolute)

    pytest.raises(TypeError, lambda: parser.add_argument("--op1", action=ActionPath))
    pytest.raises(
        ValueError,
        lambda: parser.add_argument("--op3", action=ActionPath(mode="+")),
    )
    pytest.raises(
        ValueError,
        lambda: parser.add_argument("--op4", type=str, action=ActionPath(mode="fr")),
    )


def test_ActionPath_skip_check(tmp_cwd):
    parser = ArgumentParser(exit_on_error=False)
    with catch_warnings(record=True) as w:
        parser.add_argument("--file", action=ActionPath(mode="fr", skip_check=True))
    assert_deprecation_warn(
        w,
        message="skip_check parameter of Path was deprecated",
        code='ActionPath(mode="fr", skip_check=True)',
    )
    cfg = parser.parse_args(["--file=not-exist"])
    assert isinstance(cfg.file, Path)
    assert str(cfg.file) == "not-exist"
    assert parser.dump(cfg) == "file: not-exist\n"
    assert repr(cfg.file).startswith("Path_fr_skip_check")


def test_ActionPath_dump(tmp_cwd):
    parser = ArgumentParser()
    with catch_warnings(record=True):
        parser.add_argument("--path", action=ActionPath(mode="fc"))
    cfg = parser.parse_string("path: path")
    assert parser.dump(cfg) == "path: path\n"

    parser = ArgumentParser()
    parser.add_argument("--paths", nargs="+", action=ActionPath(mode="fc"))
    cfg = parser.parse_args(["--paths", "path1", "path2"])
    assert parser.dump(cfg) == "paths:\n- path1\n- path2\n"


def test_ActionPath_nargs_questionmark(tmp_cwd):
    parser = ArgumentParser()
    parser.add_argument("val", type=int)
    with catch_warnings(record=True):
        parser.add_argument("path", nargs="?", action=ActionPath(mode="fc"))
    assert None is parser.parse_args(["1"]).path
    assert None is not parser.parse_args(["2", "file"]).path


def test_Path_attr_set(tmp_cwd):
    path = Path("file", "fc")
    with catch_warnings(record=True) as w:
        path.rel_path = "file"
        path.abs_path = os.path.join(tmp_cwd, "file")
        path.skip_check = False
        path.cwd = str(tmp_cwd)
        assert "Path objects are not meant to be mutable" in str(w[-1].message)
    with catch_warnings(record=True) as w:
        assert path.rel_path == "file"
        assert path.abs_path == os.path.join(tmp_cwd, "file")
        assert path.skip_check is False
        assert "Path objects are not meant to be mutable" in str(w[-1].message)


def test_path_call(paths):  # noqa: F811
    path = Path(paths.file_rw, "frw")
    with catch_warnings(record=True) as w:
        assert path(False) == str(paths.file_rw)
    assert_deprecation_warn(
        w,
        message="Calling Path objects is deprecated",
        code="assert path(False) == ",
    )
    assert path(True) == str(paths.tmp_path / paths.file_rw)
    assert path() == str(paths.tmp_path / paths.file_rw)


def test_file_path_get_content(paths):  # noqa: F811
    path = Path(paths.file_r, "fr")
    with catch_warnings(record=True) as w:
        content = path.get_content()
    assert_deprecation_warn(
        w,
        message="``Path.get_content`` was deprecated",
        code="content = path.get_content()",
    )
    assert "file contents" == content


def test_std_input_path_get_content():
    input_text_to_test = "a text here\n"
    with patch("sys.stdin", StringIO(input_text_to_test)), catch_warnings(record=True) as w:
        path = Path("-", mode="fr")
        assert input_text_to_test == path.get_content()
    assert_deprecation_warn(
        w,
        message="``Path.get_content`` was deprecated",
        code="input_text_to_test == path.get_content()",
    )


@skip_if_responses_unavailable
@responses_activate
def test_path_url_200():
    import responses

    existing = "http://example.com/existing-url"
    existing_body = "url contents"
    responses.add(responses.GET, existing, status=200, body=existing_body)
    responses.add(responses.HEAD, existing, status=200)
    path = Path(existing, mode="ur")
    with catch_warnings(record=True) as w:
        assert existing_body == path.get_content()
    assert_deprecation_warn(
        w,
        message="``Path.get_content`` was deprecated",
        code="existing_body == path.get_content()",
    )


@skip_if_fsspec_unavailable
def test_path_fsspec_memory():
    import fsspec

    file_content = "content in memory"
    memfile = "memfile.txt"
    path = Path(f"memory://{memfile}", mode="sw")
    with fsspec.open(path, "w") as f:
        f.write(file_content)
    with catch_warnings(record=True) as w:
        assert file_content == path.get_content()
    assert_deprecation_warn(
        w,
        message="``Path.get_content`` was deprecated",
        code="file_content == path.get_content()",
    )


def test_ActionPathList(tmp_cwd):
    tmpdir = os.path.join(tmp_cwd, "subdir")
    os.mkdir(tmpdir)
    pathlib.Path(os.path.join(tmpdir, "file1")).touch()
    pathlib.Path(os.path.join(tmpdir, "file2")).touch()
    pathlib.Path(os.path.join(tmpdir, "file3")).touch()
    pathlib.Path(os.path.join(tmpdir, "file4")).touch()
    pathlib.Path(os.path.join(tmpdir, "file5")).touch()
    list_file = os.path.join(tmpdir, "files.lst")
    list_file2 = os.path.join(tmpdir, "files2.lst")
    list_file3 = os.path.join(tmpdir, "files3.lst")
    list_file4 = os.path.join(tmpdir, "files4.lst")
    with open(list_file, "w") as output_file:
        output_file.write("file1\nfile2\nfile3\nfile4\n")
    with open(list_file2, "w") as output_file:
        output_file.write("file5\n")
    pathlib.Path(list_file3).touch()
    with open(list_file4, "w") as output_file:
        output_file.write("file1\nfile2\nfile6\n")

    parser = ArgumentParser(prog="app", exit_on_error=False)
    with catch_warnings(record=True) as w:
        parser.add_argument("--list", nargs="+", action=ActionPathList(mode="fr", rel="list"))
    assert_deprecation_warn(
        w,
        message="ActionPathList was deprecated",
        code="ActionPathList(mode=",
    )
    parser.add_argument("--list_cwd", action=ActionPathList(mode="fr", rel="cwd"))

    cfg = parser.parse_args(["--list", list_file])
    assert 4 == len(cfg.list)
    assert ["file1", "file2", "file3", "file4"] == [str(x) for x in cfg.list]

    cfg = parser.parse_args(["--list", list_file, list_file2])
    assert 5 == len(cfg.list)
    assert ["file1", "file2", "file3", "file4", "file5"] == [str(x) for x in cfg.list]

    assert 0 == len(parser.parse_args(["--list", list_file3]).list)

    cwd = os.getcwd()
    os.chdir(tmpdir)
    cfg = parser.parse_args(["--list_cwd", list_file])
    assert 4 == len(cfg.list_cwd)
    assert ["file1", "file2", "file3", "file4"] == [str(x) for x in cfg.list_cwd]
    os.chdir(cwd)

    pytest.raises(ArgumentError, lambda: parser.parse_args(["--list"]))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--list", list_file4]))
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--list", "no-such-file"]))

    pytest.raises(ValueError, lambda: parser.add_argument("--op1", action=ActionPathList))
    pytest.raises(
        ValueError,
        lambda: parser.add_argument("--op2", action=ActionPathList(mode="fr"), nargs="*"),
    )
    pytest.raises(
        ValueError,
        lambda: parser.add_argument("--op3", action=ActionPathList(mode="fr", rel=".")),
    )


@skip_if_docstring_parser_unavailable
def test_import_import_docstring_parse():
    from jsonargparse._optionals import import_docstring_parser

    with catch_warnings(record=True) as w:
        from jsonargparse.optionals import import_docstring_parse

    assert_deprecation_warn(
        w,
        message="Only use the public API",
        code="from jsonargparse.optionals import import_docstring_parse",
    )
    assert import_docstring_parse is import_docstring_parser


@skip_if_docstring_parser_unavailable
def test_docstring_parse_options():
    from docstring_parser import DocstringStyle

    options = get_docstring_parse_options()
    options["style"] = None

    with catch_warnings(record=True) as w:
        for style in [DocstringStyle.NUMPYDOC, DocstringStyle.GOOGLE]:
            set_docstring_parse_options(style=style)
            assert options["style"] == style
    assert_deprecation_warn(
        w,
        message="set_docstring_parse_options was deprecated",
        code="set_docstring_parse_options(style=style)",
    )


def test_import_from_deprecated():
    import jsonargparse.deprecated as deprecated

    with catch_warnings(record=True) as w:
        func = deprecated.set_url_support

    assert_deprecation_warn(
        w,
        message="Only use the public API",
        code="func = deprecated.set_url_support",
    )
    assert func is set_url_support


@pytest.mark.parametrize(
    ["module", "attr"],
    [
        ("actions", "ActionYesNo"),
        ("cli", "CLI"),
        ("core", "ArgumentParser"),
        ("formatters", "DefaultHelpFormatter"),
        ("jsonnet", "ActionJsonnet"),
        ("jsonschema", "ActionJsonSchema"),
        ("link_arguments", "ArgumentLinking"),
        ("loaders_dumpers", "set_loader"),
        ("namespace", "Namespace"),
        ("typehints", "lazy_instance"),
        ("util", "Path"),
        ("parameter_resolvers", "ParamData"),
    ],
)
def test_import_from_module(module, attr):
    module = import_module(f"jsonargparse.{module}")
    with catch_warnings(record=True) as w:
        getattr(module, attr)
    assert_deprecation_warn(
        w,
        message="Only use the public API",
        code="getattr(module, attr)",
    )


@pytest.mark.skipif(not jsonnet_support, reason="jsonnet package is required")
def test_action_jsonnet_ext_vars(parser):
    with catch_warnings(record=True) as w:
        parser.add_argument("--ext_vars", action=ActionJsonnetExtVars())
    assert_deprecation_warn(
        w,
        message="ActionJsonnetExtVars was deprecated",
        code="action=ActionJsonnetExtVars()",
    )
    parser.add_argument("--jsonnet", action=ActionJsonnet(ext_vars="ext_vars"))

    cfg = parser.parse_args(["--ext_vars", '{"param": 123}', "--jsonnet", example_2_jsonnet])
    assert 123 == cfg.jsonnet["param"]
    assert 9 == len(cfg.jsonnet["records"])
    assert "#8" == cfg.jsonnet["records"][-2]["ref"]
    assert 15.5 == cfg.jsonnet["records"][-2]["val"]


def test_add_dataclass_arguments(parser, subtests):
    with catch_warnings(record=True) as w:
        parser.add_dataclass_arguments(DataClassA, "a", default=DataClassA(), title="CustomA title")
    assert_deprecation_warn(
        w,
        message="add_dataclass_arguments was deprecated",
        code='parser.add_dataclass_arguments(DataClassA, "a", default=DataClassA(), title="CustomA title")',
    )

    with subtests.test("get_defaults"):
        cfg = parser.get_defaults()
        assert dataclasses.asdict(DataClassA()) == cfg["a"].as_dict()
        dump = __import__("yaml").safe_load(parser.dump(cfg))
        assert dataclasses.asdict(DataClassA()) == dump["a"]

    with subtests.test("instantiate_classes"):
        init = parser.instantiate(cfg)
        assert isinstance(init["a"], DataClassA)

    with subtests.test("docstrings in help"):
        help_str = get_parser_help(parser)
        if docstring_parser_support:
            assert "CustomA title:" in help_str


def test_dict_to_namespace():
    ns1 = Namespace(a=1, b=Namespace(c=2), d=[Namespace(e=3)])
    dic = {"a": 1, "b": {"c": 2}, "d": [{"e": 3}]}
    with catch_warnings(record=True) as w:
        ns2 = dict_to_namespace(dic)
    assert ns1 == ns2
    assert_deprecation_warn(
        w,
        message="dict_to_namespace was deprecated",
        code="ns2 = dict_to_namespace(dic)",
    )


def test_namespace_to_dict():
    ns = Namespace()
    ns["w"] = 1
    ns["x.y"] = 2
    ns["x.z"] = 3
    with catch_warnings(record=True) as w:
        dic1 = namespace_to_dict(ns)
    dic2 = ns.as_dict()
    assert dic1 == dic2
    assert dic1 is not dic2
    assert_deprecation_warn(
        w,
        message="namespace_to_dict was deprecated",
        code="dic1 = namespace_to_dict(ns)",
    )


def test_strip_meta():
    ns = Namespace(x=1, __path__="path")
    with catch_warnings(record=True) as w:
        result = strip_meta(ns)
    assert result == Namespace(x=1)
    assert_deprecation_warn(
        w,
        message="strip_meta was deprecated",
        code="result = strip_meta(ns)",
    )
    result = strip_meta(ns.as_dict())
    assert result == {"x": 1}


def test_namespace_get_sorted_keys():
    ns = Namespace(a=Namespace(b=1))
    with catch_warnings(record=True) as w:
        keys = ns.get_sorted_keys()
    assert keys == ["a.b", "a"]
    assert_deprecation_warn(
        w,
        message="get_sorted_keys method was deprecated",
        code="keys = ns.get_sorted_keys()",
    )


def test_namespace_get_value_and_parent():
    ns = Namespace(a=Namespace(b=1))
    with catch_warnings(record=True) as w:
        value, parent, key = ns.get_value_and_parent("a.b")
    assert value == 1
    assert parent == ns.a
    assert key == "b"
    assert_deprecation_warn(
        w,
        message="get_value_and_parent method was deprecated",
        code='value, parent, key = ns.get_value_and_parent("a.b")',
    )


@pytest.mark.skipif(not ruamel_support, reason="ruamel.yaml package is required")
def test_DefaultHelpFormatter_yaml_comments(parser):
    parser.add_argument("--arg", type=int, help="Description")
    formatter = DefaultHelpFormatter(prog="test")
    from jsonargparse._common import parent_parser

    parent_parser.set(parser)
    ruyaml = import_ruamel("test_DefaultHelpFormatter_yaml_comments")
    yaml = ruyaml.YAML()
    cfg = yaml.load("arg: 1")

    with catch_warnings(record=True) as w:
        formatter.add_yaml_comments("arg: 1")
    assert "add_yaml_comments method is deprecated and will be removed in v5.0.0" in str(w[-1].message)
    assert "formatter.add_yaml_comments(" in source[w[-1].lineno - 1]

    with catch_warnings(record=True) as w:
        formatter.set_yaml_start_comment("start", cfg)
    assert "set_yaml_start_comment method is deprecated and will be removed in v5.0.0" in str(w[-1].message)
    assert "formatter.set_yaml_start_comment(" in source[w[-1].lineno - 1]

    with catch_warnings(record=True) as w:
        formatter.set_yaml_group_comment("group", cfg, "arg", 0)
    assert "set_yaml_group_comment method is deprecated and will be removed in v5.0.0" in str(w[-1].message)
    assert "formatter.set_yaml_group_comment(" in source[w[-1].lineno - 1]

    with catch_warnings(record=True) as w:
        formatter.set_yaml_argument_comment("arg", cfg, "arg", 0)
    assert "set_yaml_argument_comment method is deprecated and will be removed in v5.0.0" in str(w[-1].message)
    assert "formatter.set_yaml_argument_comment(" in source[w[-1].lineno - 1]


@pytest.mark.skipif(not ruamel_support, reason="ruamel.yaml package is required")
def test_deprecated_dump_yaml_comments_parameter(parser):
    parser.add_argument("--arg", type=int, default=1, help="Description")
    cfg = parser.get_defaults()
    with catch_warnings(record=True) as w:
        parser.dump(cfg, yaml_comments=True)
    assert_deprecation_warn(
        w,
        message="yaml_comments parameter was deprecated in v4.44.0 and will be removed in v5.0.0",
        code="parser.dump(cfg, yaml_comments=True)",
    )


@dataclasses.dataclass
class ComposeA:
    a: int = 1

    def __post_init__(self):
        self.a += 1


@dataclasses.dataclass
class ComposeB:
    b: str = "1"


def test_compose_dataclasses():
    with catch_warnings(record=True) as w:
        ComposeAB = compose_dataclasses(ComposeA, ComposeB)
    assert_deprecation_warn(
        w,
        message="compose_dataclasses is deprecated",
        code="ComposeAB = compose_dataclasses(ComposeA, ComposeB)",
    )
    assert 2 == len(dataclasses.fields(ComposeAB))
    assert {"a": 3, "b": "2"} == dataclasses.asdict(ComposeAB(a=2, b="2"))  # pylint: disable=unexpected-keyword-arg


def test_add_argument_enable_path_deprecated(parser, tmp_cwd):
    import json

    data = {"a": 1}
    pathlib.Path("data.yaml").write_text(json.dumps(data))

    with catch_warnings(record=True) as w:
        parser.add_argument("--data", type=dict, enable_path=True)
    assert_deprecation_warn(
        w,
        message="``enable_path`` parameter of ``add_argument`` was deprecated",
        code='parser.add_argument("--data", type=dict, enable_path=True)',
    )
    cfg = parser.parse_args(["--data=data.yaml"])
    path_value = cfg["data"].pop("__path__")
    assert "data.yaml" == str(path_value)
    assert data == cfg["data"]


@skip_if_jsonschema_unavailable
def test_action_json_schema_enable_path_deprecated(parser):

    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}

    with catch_warnings(record=True) as w:
        action = ActionJsonSchema(schema=schema, enable_path=False)
    assert_deprecation_warn(
        w,
        message="``enable_path`` parameter of ``ActionJsonSchema`` was deprecated",
        code="ActionJsonSchema(schema=schema, enable_path=False)",
    )
    parser.add_argument("--obj", action=action)
    cfg = parser.parse_args(['--obj={"x": 1}'])
    assert cfg.obj == {"x": 1}


# skip_none deprecation tests


def test_deprecated_dump_skip_none_parameter(parser):
    parser.add_argument("--val", type=int)
    cfg = parser.parse_args(["--val=1"])
    with catch_warnings(record=True) as w:
        dump = parser.dump(cfg, skip_none=True)
    assert "val: 1" in dump
    assert_deprecation_warn(
        w,
        message="skip_none parameter was deprecated",
        code="parser.dump(cfg, skip_none=True)",
    )


def test_deprecated_save_skip_none_parameter(parser, tmp_cwd):
    parser.add_argument("--val", type=int)
    cfg = parser.parse_args(["--val=1"])
    with catch_warnings(record=True) as w:
        parser.save(cfg, "out.yaml", skip_none=True)
    assert_deprecation_warn(
        w,
        message="skip_none parameter was deprecated",
        code='parser.save(cfg, "out.yaml", skip_none=True)',
    )
    with open("out.yaml") as f:
        assert "val: 1" in f.read()


def test_deprecated_validate_skip_none_parameter(parser):
    parser.add_argument("--val", type=int)
    cfg = parser.parse_args(["--val=1"])
    with catch_warnings(record=True) as w:
        parser.validate(cfg, skip_none=True)
    assert_deprecation_warn(
        w,
        message="skip_none parameter was deprecated",
        code="parser.validate(cfg, skip_none=True)",
    )


def test_save_unexpected_kwarg(parser, tmp_cwd):
    parser.add_argument("--val", type=int)
    cfg = parser.parse_args(["--val=1"])
    with pytest.raises(ValueError, match="Unexpected keyword parameters"):
        parser.save(cfg, "out.yaml", unknown_kwarg=True)


def test_dump_unexpected_kwarg(parser):
    parser.add_argument("--val", type=int)
    cfg = parser.parse_args(["--val=1"])
    with pytest.raises(ValueError, match="Unexpected keyword parameters"):
        parser.dump(cfg, unknown_kwarg=True)


def test_deprecated_print_config_skip_null(parser):
    from jsonargparse_tests.conftest import get_parse_args_stdout

    parser.add_argument("--cfg", action="config")
    parser.add_argument("--op", type=int)
    with catch_warnings(record=True) as w:
        get_parse_args_stdout(parser, ["--print_config=skip_null"])
    assert_deprecation_warn(
        w,
        message="skip_null flag for --print_config was deprecated",
        code=None,
    )


def test_subcommands_parse_string_first_implicit_subcommand(subcommands_parser):  # noqa: F811
    with catch_warnings(record=True) as w:
        cfg = subcommands_parser.parse_string('{"a": {"ap1": "ap1_cfg"}, "b": {"nums": {"val1": 2}}}')
    assert_deprecation_warn(
        w,
        message="Multiple subcommand settings provided",
        code="cfg = subcommands_parser.parse_string(",
    )
    assert "Subcommand 'a' will be" in str(w[1].message)
    assert cfg.subcommand == "a"
    assert "b" not in cfg


def test_subcommands_implicit_in_default_config_files(parser, tmp_cwd):
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
    pathlib.Path("defaults.json").write_text(json.dumps(defaults))

    with catch_warnings(record=True) as w:
        cfg = parser.parse_args([])
    assert_deprecation_warn(
        w,
        message="Multiple subcommand settings provided",
        code="cfg = parser.parse_args([])",
    )
    assert "Subcommand 'sub1' will be" in str(w[1].message)
    assert cfg.sub == "sub1"
    assert cfg.sub1 == Namespace(sub1val=2)
    assert "sub2" not in cfg


def test_deprecated_merge_config(parser):
    for key in [1, 2, 3]:
        parser.add_argument(f"--op{key}", type=int)
    cfg_from = Namespace(op1=1, op2=None)
    cfg_to = Namespace(op1=None, op2=2, op3=3)
    with catch_warnings(record=True) as w:
        cfg = parser.merge_config(cfg_from, cfg_to)
    assert cfg == Namespace(op1=1, op2=None, op3=3)
    assert_deprecation_warn(
        w,
        message="``ArgumentParser.merge_config`` was deprecated",
        code="cfg = parser.merge_config(cfg_from, cfg_to)",
    )


def test_add_class_arguments_class_type_rename(parser):
    with catch_warnings(record=True) as w:
        parser.add_class_arguments(theclass=ComposeA)
    assert_deprecation_warn(
        w,
        message="Parameter 'theclass' was renamed to 'class_type'",
        code="parser.add_class_arguments(theclass=ComposeA)",
    )


def test_add_method_arguments_class_type_rename(parser):
    with catch_warnings(record=True) as w:
        parser.add_method_arguments(theclass=WithMethods, themethod="normal_method")
    assert_deprecation_warn(
        w,
        message="Parameter 'theclass' was renamed to 'class_type'",
        code='parser.add_method_arguments(theclass=WithMethods, themethod="normal_method")',
    )


def test_add_method_arguments_method_name_rename(parser):
    with catch_warnings(record=True) as w:
        parser.add_method_arguments(WithMethods, themethod="normal_method")
    assert_deprecation_warn(
        w,
        message="Parameter 'themethod' was renamed to 'method_name'",
        code='parser.add_method_arguments(WithMethods, themethod="normal_method")',
    )


def test_parse_object_obj_rename(parser):
    parser.add_argument("--p1", type=float)
    with catch_warnings(record=True) as w:
        assert parser.parse_object(cfg_obj={"p1": 1.2}) == Namespace(p1=1.2)
    assert_deprecation_warn(
        w,
        message="Parameter 'cfg_obj' was renamed to 'obj'",
        code='parser.parse_object(cfg_obj={"p1": 1.2})',
    )


def test_parse_object_namespace_rename(parser):
    parser.add_argument("--p1", type=float)
    parser.add_argument("--p2", type=int)
    with catch_warnings(record=True) as w:
        assert parser.parse_object({"p1": 2.1}, cfg_base=Namespace(p2=3)) == Namespace(p1=2.1, p2=3)
    assert_deprecation_warn(
        w,
        message="Parameter 'cfg_base' was renamed to 'namespace'",
        code='parser.parse_object({"p1": 2.1}, cfg_base=Namespace(p2=3))',
    )


def test_parse_path_path_rename(parser, tmp_cwd):
    parser.add_argument("--p1", type=float)
    pathlib.Path("cfg.json").write_text('{"p1": 2.1}')
    with catch_warnings(record=True) as w:
        assert parser.parse_path(cfg_path="cfg.json") == Namespace(p1=2.1)
    assert_deprecation_warn(
        w,
        message="Parameter 'cfg_path' was renamed to 'path'",
        code='parser.parse_path(cfg_path="cfg.json")',
    )


def test_parse_string_content_rename(parser):
    parser.add_argument("--p1", type=float)
    with catch_warnings(record=True) as w:
        assert parser.parse_string(cfg_str='{"p1": 2.1}') == Namespace(p1=2.1)
    assert_deprecation_warn(
        w,
        message="Parameter 'cfg_str' was renamed to 'content'",
        code="parser.parse_string(cfg_str='{\"p1\": 2.1}')",
    )


def test_parse_string_path_rename(parser):
    parser.add_argument("--p1", type=float)
    with catch_warnings(record=True) as w:
        assert parser.parse_string(content='{"p1": 2.1}', cfg_path="cfg.yaml") == Namespace(p1=2.1)
    assert_deprecation_warn(
        w,
        message="Parameter 'cfg_path' was renamed to 'path'",
        code='parser.parse_string(content=\'{"p1": 2.1}\', cfg_path="cfg.yaml")',
    )


def test_optional_parameter_without_default_deprecation(parser, monkeypatch):
    def without_default(value: Optional[int]):
        pass  # pragma: no cover

    monkeypatch.delenv("JSONARGPARSE_DEPRECATION_WARNINGS", raising=False)
    with catch_warnings(record=True) as warnings:
        parser.add_function_arguments(without_default)
    assert warnings == []

    monkeypatch.setenv("JSONARGPARSE_DEPRECATION_WARNINGS", "all")

    def without_default_warning(other: Optional[int]):
        pass  # pragma: no cover

    with catch_warnings(record=True) as warnings:
        parser.add_function_arguments(without_default_warning)
    assert len(warnings) == 1
    assert "Optional type parameters without a default" in str(warnings[0].message)
    assert "In v5 they will be required" in str(warnings[0].message)

    assert parser.get_defaults() == Namespace(value=None, other=None)


def test_fail_untyped_false_required_parameter_deprecation(parser, monkeypatch):
    def with_untyped_required(a1, a2=None):
        pass  # pragma: no cover

    monkeypatch.delenv("JSONARGPARSE_DEPRECATION_WARNINGS", raising=False)
    with catch_warnings(record=True) as warnings:
        parser.add_function_arguments(with_untyped_required, fail_untyped=False)
    assert warnings == []

    monkeypatch.setenv("JSONARGPARSE_DEPRECATION_WARNINGS", "all")

    def with_untyped_required_warning(b1, b2=None):
        pass  # pragma: no cover

    with catch_warnings(record=True) as warnings:
        parser.add_function_arguments(with_untyped_required_warning, fail_untyped=False)
    assert len(warnings) == 1
    assert "fail_untyped=False" in str(warnings[0].message)
    assert "In v5 the type will be set to Any but the parameter will remain required" in str(warnings[0].message)

    assert parser.get_defaults() == Namespace(a1=None, a2=None, b1=None, b2=None)
