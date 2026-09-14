from __future__ import annotations

import calendar
import logging
import os
from functools import partialmethod
from importlib import import_module
from unittest.mock import patch

import pytest

from jsonargparse import (
    ArgumentParser,
    Namespace,
    capture_parser,
)
from jsonargparse._common import LoggerProperty, debug_mode_active, null_logger
from jsonargparse._util import (
    CaptureParserException,
    get_import_path,
    import_object,
    merge_config,
    object_path_serializer,
    register_unresolvable_import_paths,
    unique,
)
from jsonargparse_tests.conftest import capture_logs


def test_merge_config(parser):
    for key in [1, 2, 3]:
        parser.add_argument(f"--op{key}", type=int)
    cfg_from = Namespace(op1=1, op2=None)
    cfg_to = Namespace(op1=None, op2=2, op3=3)
    cfg = merge_config(parser, cfg_from, cfg_to)
    assert cfg == Namespace(op1=1, op2=None, op3=3)


# logger property tests


class WithLogger(LoggerProperty):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


log_message = "testing log message"


def test_logger_true():
    test = WithLogger(logger=True)
    assert test.logger.handlers[0].level == logging.WARNING
    assert test.logger.name == "WithLogger"
    with capture_logs(test.logger) as logs:
        test.logger.error(log_message)
    assert "ERROR" in logs.getvalue()
    assert log_message in logs.getvalue()


def test_logger_false():
    test = WithLogger(logger=False)
    assert test.logger is null_logger
    with capture_logs(test.logger) as logs:
        test.logger.error(log_message)
    assert "" == logs.getvalue()


def test_no_init_logger():
    class WithLoggerNoInit(LoggerProperty):
        pass

    test = WithLoggerNoInit()
    assert test.logger is null_logger


def test_logger_str():
    logger = logging.getLogger("test_logger_str")
    test = WithLogger(logger="test_logger_str")
    assert test.logger is logger


def test_logger_object():
    logger = logging.getLogger("test_logger_object")
    test = WithLogger(logger=logger)
    assert test.logger is logger
    assert test.logger.name == "test_logger_object"


def test_logger_name():
    test = WithLogger(logger={"name": "test_logger_name"})
    assert test.logger.name == "test_logger_name"


def test_logger_failure_cases():
    pytest.raises(ValueError, lambda: WithLogger(logger={"level": "invalid"}))
    pytest.raises(ValueError, lambda: WithLogger(logger=WithLogger))
    pytest.raises(ValueError, lambda: WithLogger(logger={"invalid": "value"}))


levels = {0: "DEBUG", 1: "INFO", 2: "WARNING", 3: "ERROR", 4: "CRITICAL"}


@pytest.mark.parametrize(["num", "level"], levels.items())
def test_logger_levels(num, level):
    test = WithLogger(logger={"level": level})
    with capture_logs(test.logger) as logs:
        getattr(test.logger, level.lower())(log_message)
    assert level in logs.getvalue()
    assert log_message in logs.getvalue()
    if level != "DEBUG":
        with capture_logs(test.logger) as logs:
            getattr(test.logger, levels[num - 1].lower())(log_message)
        assert "" == logs.getvalue()


@patch.dict(os.environ, {"JSONARGPARSE_DEBUG": "true"})
def test_logger_jsonargparse_debug():
    parser = ArgumentParser(logger=False)
    with capture_logs(parser.logger) as logs:
        parser.logger.debug(log_message)
    assert "DEBUG" in logs.getvalue()
    assert log_message in logs.getvalue()


@patch.dict(os.environ, {"JSONARGPARSE_DEBUG": "invalid"})
def test_jsonargparse_debug_invalid_value():
    with pytest.raises(ValueError) as ctx:
        debug_mode_active()
    ctx.match("Invalid boolean value for environment variable JSONARGPARSE_DEBUG: invalid")


# import paths tests


def test_import_object_invalid():
    with pytest.raises(ValueError) as ctx:
        import_object(True)
    ctx.match("Expected a dot import path string")
    with pytest.raises(ValueError) as ctx:
        import_object("jsonargparse-tests.os")
    ctx.match("Unexpected import path format")


def test_get_import_path():
    assert get_import_path(ArgumentParser) == "jsonargparse.ArgumentParser"
    assert get_import_path(ArgumentParser.parse_args) == "jsonargparse.ArgumentParser.parse_args"
    from email.mime.base import MIMEBase

    assert get_import_path(MIMEBase) == "email.mime.base.MIMEBase"
    from dataclasses import MISSING

    assert get_import_path(MISSING) == "dataclasses.MISSING"


class _StaticMethods:
    @staticmethod
    def static_method():
        pass  # pragma: no cover


static_method = _StaticMethods.static_method


def test_get_import_path_static_method_shorthand():
    assert get_import_path(static_method) == f"{__name__}.static_method"


class ParentClassmethod:
    __module__ = "jsonargparse_tests"

    @classmethod
    def class_method(cls):
        pass  # pragma: no cover


class ChildClassmethod(ParentClassmethod):
    pass


def test_get_import_path_classpath_inheritance():
    assert get_import_path(ParentClassmethod.class_method) == "jsonargparse_tests.ParentClassmethod.class_method"
    assert get_import_path(ChildClassmethod.class_method) == f"{__name__}.ChildClassmethod.class_method"


class WithPartialMethod:
    def method(self, p1: int, p2: str = "x"):
        pass  # pragma: no cover

    partial_method = partialmethod(method, p2="y")
    other_module_partial_method = partialmethod(calendar.Calendar.getfirstweekday)


def test_get_import_path_partialmethod():
    path = f"{__name__}.WithPartialMethod.partial_method"
    assert get_import_path(WithPartialMethod.partial_method) == path
    assert object_path_serializer(WithPartialMethod.partial_method) == path


def test_get_import_path_partialmethod_not_found():
    with pytest.raises(ValueError, match="Not possible to determine the import path"):
        get_import_path(WithPartialMethod.other_module_partial_method)


def unresolvable_import():
    pass  # pragma: no cover


@patch.dict("jsonargparse._util.unresolvable_import_paths")
def test_register_unresolvable_import_paths():
    unresolvable_import.__module__ = None
    pytest.raises(ValueError, lambda: get_import_path(unresolvable_import))
    register_unresolvable_import_paths(import_module(__name__))
    assert get_import_path(unresolvable_import) == f"{__name__}.unresolvable_import"


class Class:
    @staticmethod
    def method1():
        pass  # pragma: no cover

    def method2(self):
        pass  # pragma: no cover


def test_object_path_serializer_class_method():
    assert object_path_serializer(Class.method1) == f"{__name__}.Class.method1"
    assert object_path_serializer(Class.method2) == f"{__name__}.Class.method2"


def test_object_path_serializer_reimport_differs():
    class FakeClass:
        pass

    FakeClass.__module__ = Class.__module__
    FakeClass.__qualname__ = Class.__qualname__
    pytest.raises(ValueError, lambda: object_path_serializer(FakeClass))


# other tests


def test_unique():
    data = [1.0, 2, {}, "x", ([], {}), 2, [], {}, [], ([], {}), 2]
    assert unique(data) == [1.0, 2, {}, "x", ([], {}), []]


def test_capture_parser():
    def parse_args(args=[]):
        parser = ArgumentParser()
        parser.add_argument("--int", type=int, default=1)
        return parser.parse_args(args)

    parser = capture_parser(parse_args, ["--int=2"])
    assert isinstance(parser, ArgumentParser)
    assert parser.get_defaults() == Namespace(int=1)

    with pytest.raises(CaptureParserException) as ctx:
        capture_parser(lambda: None)
    ctx.match("No parse_args call to capture the parser")
