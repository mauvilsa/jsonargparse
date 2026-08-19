import dataclasses
import os
import re
import select
import shlex
import struct
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from enum import Enum
from importlib.util import find_spec
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Generic, Literal, Optional, TypedDict, TypeVar, Union
from unittest.mock import patch

import pytest

from jsonargparse import ArgumentError, ArgumentParser, set_parsing_settings
from jsonargparse._completions import get_shtab_script, norm_name
from jsonargparse._optionals import pydantic_support
from jsonargparse._parameter_resolvers import get_signature_parameters
from jsonargparse._typehints import Unpack, type_to_str
from jsonargparse.typing import Path_drw, Path_fr
from jsonargparse_tests.conftest import capture_logs, get_parse_args_stdout

if pydantic_support:
    import pydantic


@pytest.fixture(autouse=True, scope="module")
def skip_if_no_shtab():
    if not find_spec("shtab"):
        pytest.skip("shtab package is required")


@pytest.fixture(autouse=True, scope="module")
def skip_if_wsl_message():
    popen = subprocess.Popen(["bash", "-c", "echo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, _ = popen.communicate()
    if "Windows Subsystem for Linux has no installed distributions" in out.decode().replace("\x00", ""):
        pytest.skip(out.decode().replace("\x00", ""))  # pragma: no cover


@pytest.fixture(autouse=True, scope="module")
def term_env_var():
    with patch.dict("os.environ", {"TERM": "xterm-256color", "COLUMNS": "200"}):
        yield


@pytest.fixture
def parser() -> ArgumentParser:
    return ArgumentParser(exit_on_error=False, prog="tool")


def get_bash_array(shtab_script, name):
    """Elements of a bash array assignment, independent of how shtab quotes them."""
    match = re.search(rf"^{re.escape(name)}=\((.*)\)$", shtab_script, re.MULTILINE)
    assert match, f"{name} array not found in shtab script"
    return shlex.split(match.group(1))


def get_zsh_completion_actions(shtab_script):
    """Completion action of each zsh option spec, independent of the message shtab puts in it.

    A zsh option spec is ``"--opt[description]:message:action"``. Older shtab versions use the
    action's dest as message, newer ones its metavar when there is one.
    """
    actions = {}
    for match in re.finditer(r'^\s*"(--[^\[]+)\[.*\]:([^:]*):(.*)"$', shtab_script, re.MULTILINE):
        actions[match.group(1)] = match.group(3)
    return actions


def is_positional(dest, parser):
    if parser is not None:
        action = next(a for a in parser._actions if a.dest == dest)
        return action.option_strings == []
    return False


def assert_bash_typehint_completions(subtests, shtab_script, completions):
    parser = None
    if isinstance(shtab_script, ArgumentParser):
        parser = shtab_script
        shtab_script = get_shtab_script(shtab_script, "bash")
    with tempfile.TemporaryDirectory() as tmpdir:
        shtab_script_path = Path(tmpdir) / "comp.sh"
        shtab_script_path.write_text(shtab_script)

        for dest, typehint, word, choices, extra in completions:
            typehint = type_to_str(typehint)
            with subtests.test(f"{word} -> {extra}"):
                sh = f'source {shtab_script_path}; COMP_TYPE=63 _jsonargparse_tool_{norm_name(dest)}_typehint "{word}"'
                popen = subprocess.Popen(["bash", "-c", sh], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = popen.communicate()
                assert out.decode().splitlines() == choices
                if extra is None:
                    assert f"Expected type: {typehint}" in err.decode()
                elif re.match(r"^\d/\d$", extra):
                    assert f"Expected type: {typehint}; {extra} matched choices" in err.decode()
                else:
                    assert f"Expected type: {typehint}; Accepted by subclasses: {extra}" in err.decode()
                if is_positional(dest, parser):
                    assert f"Argument: {dest}; Expected type: {typehint}" in err.decode()
                redraw_requested = "\x1b[5n" in err.decode()
                assert redraw_requested == (choices == []), "device status report expected iff there are no completions"


def test_bash_any(parser, subtests):
    parser.add_argument("--any", type=Any)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("any", Any, "", [], None),
        ],
    )


def test_bash_object(parser, subtests):
    parser.add_argument("--obj", type=object)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("obj", object, "", [], None),
        ],
    )


@pytest.mark.parametrize("any_type", [Any, object])
def test_bash_union_literal_and_any(parser, any_type, subtests):
    typehint = Union[Literal["one", "two"], any_type]
    parser.add_argument("--union", type=typehint)
    # the choices are not all that is accepted, so a prefix is required to complete them
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("union", typehint, "", [], None),
            ("union", typehint, "t", ["two"], "1/2"),
        ],
    )


def test_bash_bool(parser, subtests):
    parser.add_argument("--bool", type=bool)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("bool", bool, "", ["true", "false"], "2/2"),
        ],
    )


def test_bash_optional_bool(parser, subtests):
    parser.add_argument("--bool", type=Optional[bool])
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("bool", Optional[bool], "", ["true", "false", "null"], "3/3"),
            ("bool", Optional[bool], "tr", ["true"], "1/3"),
            ("bool", Optional[bool], "x", [], "0/3"),
        ],
    )


def test_bash_optional_int(parser, subtests):
    parser.add_argument("--num", type=Optional[int])
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("num", Optional[int], "", [], "0/1"),
            ("num", Optional[int], "n", ["null"], "1/1"),
        ],
    )


def test_bash_argument_group(parser, subtests):
    group = parser.add_argument_group("Group1")
    group.add_argument("--bool", type=bool)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("bool", bool, "", ["true", "false"], "2/2"),
        ],
    )


class AXEnum(Enum):
    ABC = "abc"
    XY = "xy"
    XZ = "xz"


def test_bash_enum(parser, subtests):
    parser.add_argument("--enum", type=AXEnum)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("enum", AXEnum, "", ["ABC", "XY", "XZ"], "3/3"),
            ("enum", AXEnum, "A", ["ABC"], "1/3"),
            ("enum", AXEnum, "X", ["XY", "XZ"], "2/3"),
        ],
    )


def test_bash_optional_enum(parser, subtests):
    parser.add_argument("--enum", type=Optional[AXEnum])
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("enum", Optional[AXEnum], "", ["ABC", "XY", "XZ", "null"], "4/4"),
        ],
    )


def test_bash_literal(parser, subtests):
    typehint = Optional[Literal["one", "two"]]
    parser.add_argument("--literal", type=typehint)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("literal", typehint, "", ["one", "two", "null"], "3/3"),
            ("literal", typehint, "t", ["two"], "1/3"),
        ],
    )


def test_bash_literal_special_characters(parser, subtests):
    typehint = Literal["one two", "three", "it's"]
    parser.add_argument("--literal", type=typehint)
    shtab_script = get_shtab_script(parser, "bash")
    syntax_check = subprocess.run(["bash", "-n"], input=shtab_script.encode(), capture_output=True)
    assert syntax_check.returncode == 0, syntax_check.stderr.decode()
    assert_bash_typehint_completions(
        subtests,
        shtab_script,
        [
            ("literal", typehint, "", ["one two", "three", "it's"], "3/3"),
            ("literal", typehint, "o", ["one two"], "1/3"),
            ("literal", typehint, "i", ["it's"], "1/3"),
        ],
    )


def test_bash_literal_none(parser, subtests):
    typehint = Literal[None]
    parser.add_argument("--literal", type=typehint)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("literal", typehint, "", ["null"], "1/1"),
            ("literal", typehint, "n", ["null"], "1/1"),
        ],
    )


def test_bash_union(parser, subtests):
    typehint = Optional[Union[bool, AXEnum]]
    parser.add_argument("--union", type=typehint)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("union", typehint, "", ["true", "false", "ABC", "XY", "XZ", "null"], "6/6"),
            ("union", typehint, "z", [], "0/6"),
        ],
    )


def test_bash_union_literal_and_int(parser, subtests):
    typehint = Union[Literal[False], int]
    parser.add_argument("--union", type=typehint)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("union", typehint, "", [], "0/1"),
            ("union", typehint, "f", ["false"], "1/1"),
        ],
    )


def test_bash_union_float_and_enum(parser, subtests):
    typehint = Union[float, AXEnum]
    parser.add_argument("--union", type=typehint)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("union", typehint, "", [], "0/3"),
            ("union", typehint, "X", ["XY", "XZ"], "2/3"),
        ],
    )


def test_bash_positional(parser, subtests):
    typehint = Literal["Alice", "Bob"]
    parser.add_argument("name", type=typehint)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("name", typehint, "", ["Alice", "Bob"], "2/2"),
            ("name", typehint, "Al", ["Alice"], "1/2"),
        ],
    )


def test_shtab_bash_optionals_as_positionals(parser, subtests, parsing_settings_patch):
    set_parsing_settings(parse_optionals_as_positionals=True)
    parser.prog = "tool"

    parser.add_argument("job", type=str)
    parser.add_argument("--amount", type=int, default=0)
    parser.add_argument("--flag", type=bool, default=False)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("job", str, "", [], None),
            ("job", str, "easy", [], None),
            ("amount", int, "easy ", [], None),
            ("amount", int, "easy 10", [], None),
            ("flag", bool, "easy 10 x", [], "0/2"),
        ],
    )


def test_bash_script_binds_redraw_current_line(parser):
    parser.add_argument("--num", type=int)
    shtab_script = get_shtab_script(parser, "bash")
    assert "bind '\"\\e[0n\": redraw-current-line'" in shtab_script


def get_bash_major_version():
    out = subprocess.run(["bash", "-c", 'echo "${BASH_VERSINFO[0]}"'], capture_output=True)
    try:
        return int(out.stdout.strip())
    except ValueError:  # pragma: no cover
        return 0


def read_from_pty_until(fd, pattern, timeout=10.0):
    out = b""
    end = time.monotonic() + timeout
    while pattern not in out and time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], 0.5)
        if ready:
            try:
                data = os.read(fd, 65536)
            except OSError:  # pragma: no cover
                break
            if not data:
                break  # pragma: no cover
            out += data
    return out


@pytest.mark.skipif(sys.platform == "win32", reason="pty is not available on Windows")
@pytest.mark.filterwarnings("ignore:.*multi-threaded, use of forkpty.*:DeprecationWarning")
def test_bash_interactive_no_completions_redraws_prompt(parser, tmp_path):
    if get_bash_major_version() < 4:
        pytest.skip("test requires bash>=4")  # pragma: no cover
    import fcntl
    import pty
    import termios

    parser.add_argument("--num", type=int)
    shtab_script_path = tmp_path / "comp.sh"
    shtab_script_path.write_text(get_shtab_script(parser, "bash"))
    rcfile = tmp_path / "rcfile"
    rcfile.write_text(f"PS1='PROMPT$ '\nsource {shtab_script_path}\n")

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover
        try:
            os.environ["TERM"] = "xterm-256color"
            os.execvp("bash", ["bash", "--noprofile", "--rcfile", str(rcfile), "-i"])
        finally:
            os._exit(1)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 200, 0, 0))
        read_from_pty_until(fd, b"PROMPT$ ")
        os.write(fd, b"tool --num \t\t")
        out = read_from_pty_until(fd, b"\x1b[5n")
        assert b"Expected type: int" in out
        assert b"\x1b[5n" in out, "completion should request a device status report from the terminal"
        os.write(fd, b"\x1b[0n")  # a real terminal replies this to the \x1b[5n device status report
        out = read_from_pty_until(fd, b"PROMPT$ tool --num ")
        assert b"PROMPT$ tool --num " in out, "prompt should be redrawn after the guidance message"
    finally:
        with suppress(OSError):
            os.write(fd, b"\x03exit\n")
        with suppress(OSError):
            os.close(fd)
        with suppress(OSError):
            os.waitpid(pid, 0)


def test_bash_config(parser):
    parser.add_argument("--cfg", action="config")
    shtab_script = get_shtab_script(parser, "bash")
    assert "_cfg_COMPGEN=_shtab_compgen_files" in shtab_script


def test_bash_dir(parser):
    parser.add_argument("--path", type=Path_drw)
    shtab_script = get_shtab_script(parser, "bash")
    assert "_path_COMPGEN=_shtab_compgen_dirs" in shtab_script


@pytest.mark.parametrize("path_type", [Path_fr, PathLike, Path, Union[PathLike, str]])
def test_bash_file(parser, path_type):
    parser.add_argument("--path", type=path_type)
    shtab_script = get_shtab_script(parser, "bash")
    assert "_path_COMPGEN=_shtab_compgen_files" in shtab_script


@pytest.mark.parametrize("path_type", [Path_fr, PathLike, Path, Union[Union[PathLike, str], dict]])
def test_bash_optional_file(parser, path_type):
    parser.add_argument("--path", type=Optional[path_type])
    shtab_script = get_shtab_script(parser, "bash")
    assert "_path_COMPGEN=_shtab_compgen_files" in shtab_script


@pytest.mark.skipif(pydantic_support < 2, reason="pydantic>=2 is required")
def test_bash_pydantic_file_path(parser):
    parser.add_argument("--path", type=pydantic.FilePath)
    shtab_script = get_shtab_script(parser, "bash")
    assert "_path_COMPGEN=_shtab_compgen_files" in shtab_script


@pytest.mark.skipif(pydantic_support < 2, reason="pydantic>=2 is required")
def test_bash_pydantic_directory_path(parser):
    parser.add_argument("--path", type=pydantic.DirectoryPath)
    shtab_script = get_shtab_script(parser, "bash")
    assert "_path_COMPGEN=_shtab_compgen_dirs" in shtab_script


@pytest.mark.skipif(pydantic_support < 2, reason="pydantic>=2 is required")
def test_bash_optional_pydantic_directory_path(parser):
    parser.add_argument("--path", type=Optional[pydantic.DirectoryPath])
    shtab_script = get_shtab_script(parser, "bash")
    assert "_path_COMPGEN=_shtab_compgen_dirs" in shtab_script


@pytest.mark.skipif(pydantic_support < 2, reason="pydantic>=2 is required")
def test_bash_pydantic_new_path(parser):
    parser.add_argument("--path", type=pydantic.NewPath)
    shtab_script = get_shtab_script(parser, "bash")
    assert "_path_COMPGEN=_shtab_compgen_files" in shtab_script


@pytest.mark.skipif(pydantic_support < 2, reason="pydantic>=2 is required")
def test_bash_pydantic_model_path_fields(parser):
    class Model(pydantic.BaseModel):
        file: pydantic.FilePath
        dir: pydantic.DirectoryPath

    parser.add_argument("--model", type=Model)
    shtab_script = get_shtab_script(parser, "bash")
    assert "_model_file_COMPGEN=_shtab_compgen_files" in shtab_script
    assert "_model_dir_COMPGEN=_shtab_compgen_dirs" in shtab_script


class Base:
    def __init__(self, p1: int):
        pass  # pragma: no cover


def test_bash_class_config(parser):
    parser.add_class_arguments(Base, "class")
    shtab_script = get_shtab_script(parser, "bash")
    assert "_class_COMPGEN=_shtab_compgen_files" in shtab_script


class SubA(Base):
    def __init__(self, p1: int, p2: AXEnum):
        pass  # pragma: no cover


class SubB(Base):
    def __init__(self, p1: int, p3: float):
        pass  # pragma: no cover


def test_bash_subclasses_fail_get_perams(parser, logger):
    def get_params_patch(cls, method, logger):
        if cls == SubB:
            raise Exception("test get params failure")
        return get_signature_parameters(cls, method, logger)

    parser.logger = logger
    parser.add_argument("--cls", type=Base)
    with capture_logs(logger) as logs, patch("jsonargparse._completions.get_signature_parameters", get_params_patch):
        shtab_script = get_shtab_script(parser, "bash")
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert options == ["-h", "--help", "--cls.help", "--cls", "--cls.p1", "--cls.p2"]
    assert f"{__name__}.SubB" in get_bash_array(shtab_script, "_shtab_tool___cls_help_choices")
    assert "--cls.p3" not in shtab_script
    assert "test_shtab.SubB': test get params failure" in logs.getvalue()


def test_bash_subclasses_help(parser):
    parser.add_argument("--cls", type=Base)
    shtab_script = get_shtab_script(parser, "bash")
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert options == ["-h", "--help", "--cls.help", "--cls", "--cls.p1", "--cls.p2", "--cls.p3"]
    classes = [f"{__name__}.Base", f"{__name__}.SubA", f"{__name__}.SubB"]
    assert get_bash_array(shtab_script, "_shtab_tool___cls_help_choices") == classes


def test_bash_subclasses(parser, subtests):
    parser.add_argument("--cls", type=Base)
    shtab_script = get_shtab_script(parser, "bash")
    classes = f"{__name__}.Base {__name__}.SubA {__name__}.SubB".split()
    assert_bash_typehint_completions(
        subtests,
        shtab_script,
        [
            ("cls", Base, "", classes, "3/3"),
            ("cls", Base, f"{__name__}.S", classes[1:], "2/3"),
            ("cls.p1", int, "1", [], "Base, SubA, SubB"),
            ("cls.p3", float, "", [], "SubB"),
        ],
    )


class Other:
    def __init__(self, o1: bool):
        pass  # pragma: no cover


def test_bash_union_subclasses(parser, subtests):
    parser.add_argument("--cls", type=Union[Base, Other])
    shtab_script = get_shtab_script(parser, "bash")
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert options == ["-h", "--help", "--cls.help", "--cls", "--cls.p1", "--cls.p2", "--cls.p3", "--cls.o1"]
    classes = [f"{__name__}.Base", f"{__name__}.SubA", f"{__name__}.SubB", f"{__name__}.Other"]
    assert get_bash_array(shtab_script, "_shtab_tool___cls_help_choices") == classes
    assert_bash_typehint_completions(
        subtests,
        shtab_script,
        [
            ("cls.p1", int, "", [], "Base, SubA, SubB"),
        ],
    )


class SupBase:
    def __init__(self, s1: Base):
        pass  # pragma: no cover


class SupA(SupBase):
    def __init__(self, s1: Optional[Base]):
        pass  # pragma: no cover


def test_bash_nested_subclasses(parser, subtests):
    parser.add_argument("--cls", type=SupBase)
    shtab_script = get_shtab_script(parser, "bash")
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert options == ["-h", "--help", "--cls.help", "--cls", "--cls.s1", "--cls.s1.p1", "--cls.s1.p2", "--cls.s1.p3"]
    assert_bash_typehint_completions(
        subtests,
        shtab_script,
        [
            ("cls.s1.p2", AXEnum, "X", ["XY", "XZ"], "SubA; 2/3 matched choices"),
        ],
    )


@dataclasses.dataclass
class Area:
    latitude: float
    longitude: float
    radius: float = 500.0


@pytest.mark.parametrize("area_type", [Area, Optional[Area]])
def test_bash_dataclass_fields(parser, area_type):
    parser.add_argument("--area", type=area_type)
    shtab_script = get_shtab_script(parser, "bash")
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert {"--area", "--area.latitude", "--area.longitude", "--area.radius"}.issubset(options)


def test_bash_optional_dataclass_field_types(parser, subtests):
    parser.add_argument("--area", type=Optional[Area])
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("area.latitude", float, "", [], None),
            ("area.radius", float, "5", [], None),
        ],
    )


class AreaDict(TypedDict):
    latitude: float
    longitude: float


def test_bash_typed_dict_help_choices(parser):
    parser.add_argument("--area", type=Union[AreaDict, Base])
    shtab_script = get_shtab_script(parser, "bash")
    choices = get_bash_array(shtab_script, "_shtab_tool___area_help_choices")
    assert choices == ["AreaDict", f"{__name__}.Base", f"{__name__}.SubA", f"{__name__}.SubB"]


PointVar = TypeVar("PointVar")

if sys.version_info >= (3, 11):  # a generic TypedDict requires python 3.11 or later

    class PointDict(TypedDict, Generic[PointVar]):
        x: PointVar
        y: PointVar


@pytest.mark.skipif(sys.version_info < (3, 11), reason="generic TypedDict introduced in python 3.11")
def test_bash_subscripted_typed_dict_help_choices(parser):
    parser.add_argument("--point", type=Union[PointDict[int], Base])
    shtab_script = get_shtab_script(parser, "bash")
    choices = get_bash_array(shtab_script, "_shtab_tool___point_help_choices")
    assert choices == ["PointDict", f"{__name__}.Base", f"{__name__}.SubA", f"{__name__}.SubB"]
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert {"--point", "--point.x", "--point.y"}.issubset(options)


class OptionsDict(TypedDict, total=False):
    verbose: bool
    mode: AXEnum


@pytest.mark.parametrize("options_type", [OptionsDict, Optional[OptionsDict]])
def test_bash_typed_dict_keys(parser, options_type):
    parser.add_argument("--opts", type=options_type)
    shtab_script = get_shtab_script(parser, "bash")
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert {"--opts", "--opts.verbose", "--opts.mode"}.issubset(options)


def test_bash_typed_dict_key_types(parser, subtests):
    parser.add_argument("--opts", type=OptionsDict)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("opts.verbose", bool, "", ["true", "false"], "2/2"),
            ("opts.mode", AXEnum, "X", ["XY", "XZ"], "2/3"),
        ],
    )


def test_bash_typed_dict_in_union_key_types(parser, subtests):
    parser.add_argument("--opts", type=Union[OptionsDict, Base])
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("opts.verbose", bool, "", ["true", "false"], "2/2"),
            ("opts.p1", int, "", [], "Base, SubA, SubB"),
        ],
    )


if Unpack:

    class UnpackOptionsClass:
        def __init__(self, **kwargs: Unpack[OptionsDict]):
            pass  # pragma: no cover


@pytest.mark.skipif(not Unpack, reason="Unpack introduced in python 3.11 or backported in typing_extensions")
def test_bash_unpack_typed_dict_key_types(parser, subtests):
    parser.add_argument("--cls", type=UnpackOptionsClass)
    shtab_script = get_shtab_script(parser, "bash")
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert {"--cls", "--cls.verbose", "--cls.mode"}.issubset(options)
    assert_bash_typehint_completions(
        subtests,
        shtab_script,
        [
            ("cls.verbose", bool, "", ["true", "false"], "UnpackOptionsClass"),
            ("cls.mode", AXEnum, "X", ["XY", "XZ"], "UnpackOptionsClass"),
        ],
    )


def test_bash_callable_return_class(parser, subtests):
    parser.add_argument("--cls", type=Callable[[int], Base])
    shtab_script = get_shtab_script(parser, "bash")
    options = get_bash_array(shtab_script, "_shtab_tool_option_strings")
    assert options == ["-h", "--help", "--cls.help", "--cls", "--cls.p2", "--cls.p3"]
    assert "--cls.p1" not in shtab_script
    classes = f"{__name__}.Base {__name__}.SubA {__name__}.SubB".split()
    assert_bash_typehint_completions(
        subtests,
        shtab_script,
        [
            ("cls", Callable[[int], Base], "", classes, "3/3"),
            ("cls.p2", AXEnum, "z", [], "SubA"),
        ],
    )


def test_bash_callable_return_int(parser, subtests):
    typehint = Callable[[int], int]
    parser.add_argument("--num", type=typehint)
    assert_bash_typehint_completions(
        subtests,
        parser,
        [
            ("num", typehint, "", [], None),
            ("num", typehint, "1", [], None),
        ],
    )


def test_bash_subcommands(parser, subparser, subtests):
    subparser.add_argument("--enum", type=AXEnum)
    subparser2 = ArgumentParser()
    subparser2.add_argument("--cls", type=Base)
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("s1", subparser)
    subcommands.add_subcommand("s2", subparser2)

    help_str = get_parse_args_stdout(parser, ["--help"])
    assert "--print_completion" not in help_str
    help_str = get_parse_args_stdout(parser, ["s1", "--help"])
    assert "--print_completion" not in help_str

    shtab_script = get_shtab_script(parser, "bash")
    assert get_bash_array(shtab_script, "_shtab_tool_subparsers") == ["s1", "s2"]

    assert get_bash_array(shtab_script, "_shtab_tool_s1_option_strings") == ["-h", "--help", "--enum"]
    options = get_bash_array(shtab_script, "_shtab_tool_s2_option_strings")
    assert options == ["-h", "--help", "--cls.help", "--cls", "--cls.p1", "--cls.p2", "--cls.p3"]
    classes = [f"{__name__}.Base", f"{__name__}.SubA", f"{__name__}.SubB"]
    assert get_bash_array(shtab_script, "_shtab_tool_s2___cls_help_choices") == classes

    assert_bash_typehint_completions(
        subtests,
        shtab_script,
        [
            ("s1.enum", AXEnum, "A", ["ABC"], "1/3"),
            ("s2.cls.p1", int, "1", [], "Base, SubA, SubB"),
        ],
    )


def test_add_print_completion_argument_opt_in(parser, parsing_settings_patch):
    set_parsing_settings(add_print_completion_argument=True)
    help_str = get_parse_args_stdout(parser, ["--help"])
    assert "--print_completion" in help_str
    script = get_parse_args_stdout(parser, ["--print_completion=shtab-bash"])
    assert "_jsonargparse_" in script


def test_add_print_completion_argument_only_top_level(parser, subparser, parsing_settings_patch):
    set_parsing_settings(add_print_completion_argument=True)
    subcommands = parser.add_subcommands()
    subcommands.add_subcommand("s1", subparser)
    assert "--print_completion" in get_parse_args_stdout(parser, ["--help"])
    assert "--print_completion" not in get_parse_args_stdout(parser, ["s1", "--help"])


def test_add_print_completion_argument_env_var_enables(parser, parsing_settings_patch):
    set_parsing_settings(add_print_completion_argument=False)
    with patch.dict("os.environ", {"JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT": "TRUE"}):
        help_str = get_parse_args_stdout(parser, ["--help"])
    assert "--print_completion" in help_str
    assert "--print_shtab" not in parser._option_string_actions


def test_add_print_completion_argument_env_var_takes_precedence(parser, parsing_settings_patch):
    set_parsing_settings(add_print_completion_argument=True)
    with patch.dict("os.environ", {"JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT": "FALSE"}):
        help_str = get_parse_args_stdout(parser, ["--help"])
    assert "--print_completion" not in help_str


def test_hidden_print_shtab_argument_shows_guidance(parser):
    help_str = get_parse_args_stdout(parser, ["--help"])
    assert "--print_shtab" not in help_str
    with pytest.raises(ArgumentError, match=r"Use set_parsing_settings\(add_print_completion_argument=True\)"):
        parser.parse_args(["--print_shtab=bash"])
    with pytest.raises(ArgumentError, match="JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT=true"):
        parser.parse_args(["--print_shtab=bash"])


def test_get_completion_script_invalid_completion_type(parser):
    with pytest.raises(ValueError, match="Unsupported completion_type"):
        parser.get_completion_script("unknown")


def test_get_completion_script_requires_shtab(parser):
    with patch("jsonargparse._completions.find_spec", return_value=None):
        with pytest.raises(ValueError, match="shtab package is required"):
            parser.get_completion_script("shtab-bash")


def test_get_completion_script_unsupported_shtab_shell(parser):
    with pytest.raises(ValueError, match="Unsupported completion_type: shtab-unsupported"):
        parser.get_completion_script("shtab-unsupported")


def test_get_completion_script_invalidates_parser(parser):
    parser.get_completion_script("shtab-bash")
    with pytest.raises(ValueError, match="invalidated by get_completion_script"):
        parser.parse_args([])


def test_add_print_completion_argument_invalidates_parser(parser, parsing_settings_patch):
    set_parsing_settings(add_print_completion_argument=True)
    _ = get_parse_args_stdout(parser, ["--print_completion=shtab-bash"])
    with pytest.raises(ValueError, match="invalidated by get_completion_script"):
        parser.parse_args([])


def test_zsh_script(parser):
    parser.add_argument("--enum", type=Optional[AXEnum])
    parser.add_argument("--path", type=PathLike)
    parser.add_argument("--cls", type=Base)
    shtab_script = get_shtab_script(parser, "zsh")
    actions = get_zsh_completion_actions(shtab_script)
    classes = f"{__name__}.Base {__name__}.SubA {__name__}.SubB"
    assert actions["--enum"] == "(ABC XY XZ null)"
    assert actions["--path"] == "_files"
    assert actions["--cls.help"] == f"({classes})"
    assert actions["--cls"] == f"({classes})"
    assert actions["--cls.p1"] == ""
    assert actions["--cls.p2"] == "(ABC XY XZ)"
    assert actions["--cls.p3"] == ""
