from __future__ import annotations

import calendar
import functools
import json
import logging
import operator
import os
import pickle
import sys
from calendar import Calendar
from types import ModuleType, UnionType
from typing import Any, Callable, Optional
from unittest.mock import patch

import pytest

from jsonargparse import ArgumentError, FromConfigMixin, set_parsing_settings
from jsonargparse._common import ImportDenied, check_import_path, get_settings_logger, null_logger
from jsonargparse._util import import_object
from jsonargparse_tests.conftest import capture_logs, get_parser_help, json_or_yaml_dump


@pytest.fixture(autouse=True)
def import_paths_settings(parsing_settings_patch):
    yield


# settings validation


def test_invalid_entry_not_a_string():
    with pytest.raises(ValueError, match="import path"):
        set_parsing_settings(import_path_denylist=[123])


@pytest.mark.parametrize("entry", ["my-pkg", "os.", "", "mypkg.*", "a b"])
def test_invalid_entry_not_an_import_path(entry):
    with pytest.raises(ValueError, match="import path"):
        set_parsing_settings(import_path_allowlist=[entry])


def test_star_only_accepted_in_denylist():
    with pytest.raises(ValueError, match="only accepted in import_path_denylist"):
        set_parsing_settings(import_path_allowlist=["*"])


def test_invalid_entry_leaves_settings_unchanged():
    with pytest.raises(ValueError):
        set_parsing_settings(import_path_denylist=["calendar", "not valid"])
    check_import_path("calendar.TextCalendar")


# policy resolution


def test_denied_by_default_entry():
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ImportDenied, match="'subprocess'"):
        check_import_path("subprocess.Popen")


def test_allowed_when_no_entry_matches():
    set_parsing_settings(import_path_denylist=[])
    check_import_path("calendar.TextCalendar")


def test_prefix_matches_only_on_component_boundary():
    set_parsing_settings(import_path_denylist=["cal"])
    check_import_path("calendar.TextCalendar")
    with pytest.raises(ImportDenied):
        check_import_path("cal.sub.Thing")


def test_more_specific_allow_wins_over_broader_deny():
    set_parsing_settings(import_path_allowlist=["functools.partial"])
    check_import_path("functools.partial")
    with pytest.raises(ImportDenied, match="'functools'"):
        check_import_path("functools.reduce")


def test_more_specific_deny_wins_over_broader_allow():
    set_parsing_settings(import_path_denylist=["calendar.TextCalendar"])
    check_import_path("calendar.Calendar")
    with pytest.raises(ImportDenied, match="'calendar.TextCalendar'"):
        check_import_path("calendar.TextCalendar")


def test_allow_wins_tie_removing_a_default_entry():
    set_parsing_settings(import_path_allowlist=["functools"])
    check_import_path("functools.reduce")


def test_entries_add_to_the_defaults():
    set_parsing_settings(import_path_denylist=["calendar"])
    with pytest.raises(ImportDenied):
        check_import_path("calendar.TextCalendar")
    with pytest.raises(ImportDenied):
        check_import_path("subprocess.Popen")


def test_entries_accumulate_across_calls():
    set_parsing_settings(import_path_denylist=["calendar"])
    set_parsing_settings(import_path_allowlist=["calendar.Calendar"])
    check_import_path("calendar.Calendar")
    with pytest.raises(ImportDenied):
        check_import_path("calendar.TextCalendar")


def test_star_denies_everything_not_allowed():
    set_parsing_settings(import_path_denylist=["*"], import_path_allowlist=["calendar"])
    check_import_path("calendar.TextCalendar")
    with pytest.raises(ImportDenied, match=r"'\*'"):
        check_import_path("json.JSONEncoder")


def test_jsonargparse_denied_by_default():
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ImportDenied, match="'jsonargparse'"):
        check_import_path("jsonargparse.set_parsing_settings")


@pytest.mark.parametrize("entry", ["jsonargparse", "jsonargparse._common.parsing_settings"])
def test_jsonargparse_not_accepted_in_allowlist(entry):
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ValueError, match="Import paths under 'jsonargparse' can't be allowed"):
        set_parsing_settings(import_path_allowlist=[entry])
    with pytest.raises(ImportDenied, match="'jsonargparse'"):
        check_import_path("jsonargparse.set_parsing_settings")


def test_allowlist_accepts_package_named_after_jsonargparse():
    set_parsing_settings(import_path_denylist=["*"], import_path_allowlist=["jsonargparse_tests"])
    check_import_path("jsonargparse_tests.test_import_paths.Data")


denied_builtins = [
    "eval",
    "exec",
    "compile",
    "__import__",
    "breakpoint",  # enters pdb
    "help",  # instance that runs pydoc
    "exit",  # instance that raises SystemExit
    "quit",
    "getattr",  # reflection, the builtins counterparts of the denied inspect and operator
    "setattr",
    "delattr",
    "vars",
    "globals",
]


def test_only_dangerous_builtins_denied():
    set_parsing_settings(import_path_denylist=[])
    for name in ["print", "int", "sorted"]:
        check_import_path(f"builtins.{name}")
    for name in denied_builtins:
        with pytest.raises(ImportDenied):
            check_import_path(f"builtins.{name}")


@pytest.mark.parametrize(
    "path",
    [
        "cProfile.run",
        "profile.Profile.runctx",
        "doctest.testfile",
        "_frozen_importlib.__import__",
        "_frozen_importlib_external.SourceFileLoader",
        "pkg_resources.load_entry_point",
        "ensurepip.bootstrap",
        "unittest.mock.patch",
        "_sitebuiltins.Quitter",
        "resource.setrlimit",
        "faulthandler.dump_traceback_later",
    ],
)
def test_execution_and_disruption_paths_denied_by_default(path):
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ImportDenied):
        check_import_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "builtins.open",
        "io.FileIO",
        "logging.FileHandler",
        "logging.handlers.SocketHandler",
        "sqlite3.connect",
        "gzip.GzipFile",
        "tarfile.TarFile",
        "urllib.request.urlopen",
        "http.client.HTTPConnection",
        "ftplib.FTP",
        "smtplib.SMTP",
        "socketserver.TCPServer",
        "xmlrpc.client.ServerProxy",
        "asyncio.create_subprocess_shell",
        "codecs.open",
        "winreg.SetValueEx",
        "xml.sax.parse",
        "antigravity",
    ],
)
def test_file_and_network_paths_denied_by_default(path):
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ImportDenied):
        check_import_path(path)


# debug logging


def test_debug_log_disabled_by_default():
    assert get_settings_logger() is null_logger


@patch.dict(os.environ, {"JSONARGPARSE_DEBUG": "true"})
def test_debug_log_entries_set():
    with capture_logs(get_settings_logger()) as logs:
        set_parsing_settings(
            import_path_denylist=["mypackage.internal", "subprocess"],
            import_path_allowlist=["functools"],
        )
    assert "Import path 'mypackage.internal' added as denied" in logs.getvalue()
    assert "Import path 'subprocess' already denied" in logs.getvalue()
    assert "Import path 'functools' changed to allowed" in logs.getvalue()


# import_object


def test_denied_before_the_module_is_imported():
    set_parsing_settings(import_path_denylist=["unimportable_denied_module"])
    with pytest.raises(ImportDenied):
        import_object("unimportable_denied_module.Thing")
    assert "unimportable_denied_module" not in sys.modules


def test_denied_module_reexported_by_another_module():
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ImportDenied, match="'os'"):
        import_object(f"{__name__}.os")
    with pytest.raises(ImportDenied, match=f"'{os.system.__module__}'"):
        import_object(f"{__name__}.os.system")  # os.system is defined in posix, nt on Windows


def test_denied_object_reexported_under_another_name():
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ImportDenied, match="'_pickle'"):
        import_object(f"{__name__}.load_bytes")


def test_denied_callable_bound_by_a_partial():
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ImportDenied, match=f"'{os.system.__module__}'"):
        import_object(f"{__name__}.system_partial")  # partial bound to os.system, defined in posix, nt on Windows


def test_denied_callable_exposed_by_an_instance():
    set_parsing_settings(import_path_denylist=[])
    with pytest.raises(ImportDenied, match="'operator'"):
        import_object(f"{__name__}.attr_getter")  # instance of the denied operator.attrgetter


def test_denied_instance_by_its_defining_class():
    set_parsing_settings(import_path_allowlist=["builtins.help"])
    with pytest.raises(ImportDenied, match="'_sitebuiltins'"):
        import_object("builtins.help")  # instance of _sitebuiltins._Helper, which reaches pydoc


def test_object_without_canonical_path_is_not_rechecked():
    set_parsing_settings(import_path_denylist=[])
    assert import_object("calendar.day_name") is calendar.day_name


def test_object_without_module_is_not_rechecked():
    set_parsing_settings(import_path_denylist=[])
    assert import_object(f"{__name__}.no_module_function") is no_module_function


def test_import_object_unaffected_when_allowed():
    set_parsing_settings(import_path_denylist=[])
    assert import_object("calendar.TextCalendar") is calendar.TextCalendar


# objects imported by the tests above


load_bytes = pickle.loads  # defined in _pickle, reachable here under a different module

system_partial = functools.partial(os.system, "echo test")  # binds a denied callable, defined in posix

attr_getter = operator.attrgetter("__globals__")  # instance of the denied operator.attrgetter


def no_module_function():
    """Mimics extension functions that have __module__ set to None."""


no_module_function.__module__ = None  # type: ignore[assignment]


# parsing


class Data:
    def __init__(self, cal: Optional[Calendar] = None):
        self.cal = cal  # pragma: no cover


def test_subclass_class_path_denied(parser):
    set_parsing_settings(import_path_denylist=["calendar"])
    parser.add_argument("--cal", type=Calendar)
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args(["--cal=calendar.TextCalendar"])


def test_subclass_class_path_allowed_by_exception(parser):
    set_parsing_settings(import_path_denylist=["calendar"], import_path_allowlist=["calendar.TextCalendar"])
    parser.add_argument("--cal", type=Calendar)
    cfg = parser.parse_args(["--cal=calendar.TextCalendar"])
    assert cfg.cal.class_path == "calendar.TextCalendar"


def test_subclass_class_path_denied_by_default(parser):
    set_parsing_settings(import_path_denylist=[])
    parser.add_argument("--handler", type=logging.Handler)
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args(["--handler=logging.FileHandler"])


def test_star_callable_bound_to_denied_callable_denied(parser):
    set_parsing_settings(import_path_denylist=["*"], import_path_allowlist=["jsonargparse_tests"])
    parser.add_argument("--fn", type=Callable)
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args([f"--fn={__name__}.system_partial"])


def test_parsing_settings_class_path_denied(parser):
    set_parsing_settings(import_path_denylist=[])
    parser.add_argument("--fn", type=Callable)
    spec = json.dumps(
        {"class_path": "jsonargparse.set_parsing_settings", "init_args": {"import_path_allowlist": ["os"]}}
    )
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args([f"--fn={spec}"])


def test_any_type_class_path_denied(parser):
    set_parsing_settings(import_path_denylist=[], validate_subclass_spec_in_any=True)
    parser.add_argument("--any", type=Any)
    spec = json.dumps({"class_path": "subprocess.Popen", "init_args": {"args": ["ls"]}})
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args([f"--any={spec}"])


def test_callable_type_denied(parser):
    set_parsing_settings(import_path_denylist=[])
    parser.add_argument("--fn", type=Callable)
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args(["--fn=os.getcwd"])


def test_type_type_denied(parser):
    set_parsing_settings(import_path_denylist=[])
    parser.add_argument("--cls", type=type)
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args(["--cls=subprocess.Popen"])


def test_module_type_denied(parser):
    set_parsing_settings(import_path_denylist=[])
    parser.add_argument("--mod", type=ModuleType)
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args(["--mod=subprocess"])


def test_module_type_non_string_value(parser):
    set_parsing_settings(import_path_denylist=[])
    parser.add_argument("--mod", type=ModuleType)
    with pytest.raises(ArgumentError, match="import path corresponding to a module"):
        parser.parse_args(["--mod=1"])


def test_module_type_allowed(parser):
    set_parsing_settings(import_path_denylist=[])
    parser.add_argument("--mod", type=ModuleType)
    cfg = parser.parse_args(["--mod=calendar"])
    assert parser.instantiate(cfg).mod is calendar


def test_type_expression_denied(parser):
    set_parsing_settings(import_path_denylist=[])
    parser.add_argument("--expr", type=UnionType)
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args(["--expr=subprocess.Popen | int"])


def test_subclasses_disabled_class_path_denied(parser, subclass_behavior):
    set_parsing_settings(import_path_denylist=["calendar"], subclasses_disabled=[Calendar])
    parser.add_argument("--cal", type=Calendar)
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args(["--cal=calendar.TextCalendar"])


def test_help_class_path_denied(parser):
    set_parsing_settings(import_path_denylist=["calendar"])
    parser.add_subclass_arguments(Calendar, "cal")
    with pytest.raises(ArgumentError, match="not allowed"):
        parser.parse_args(["--cal.help=calendar.TextCalendar"])


def test_from_config_class_path_denied(tmp_cwd):
    class Base(FromConfigMixin):
        def __init__(self, p: int = 1):
            self.p = p  # pragma: no cover

    set_parsing_settings(import_path_denylist=["calendar"])
    config = json_or_yaml_dump({"class_path": "calendar.TextCalendar"})
    (tmp_cwd / "config.yaml").write_text(config)
    with pytest.raises(ImportDenied):
        Base.from_config("config.yaml")


# not applied to code given import paths


def test_dump_of_denied_default_is_not_checked(parser):
    parser.add_argument("--cls", type=type, default=calendar.TextCalendar)
    set_parsing_settings(import_path_denylist=["calendar"])
    assert "calendar.TextCalendar" in parser.dump(parser.get_defaults())


def test_annotation_of_denied_type_not_checked(parser):
    set_parsing_settings(import_path_denylist=["calendar"])
    parser.add_class_arguments(Data, "data")
    help_str = get_parser_help(parser)
    assert "--data.cal" in help_str
