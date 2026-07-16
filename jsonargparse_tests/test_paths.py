from __future__ import annotations

import json
import os
import pathlib
import stat
import zipfile
from io import StringIO
from typing import Any, Dict, List, Optional, Union
from unittest.mock import patch

import pytest

from jsonargparse import ArgumentError, Namespace, set_parsing_settings
from jsonargparse._optionals import fsspec_support, url_support
from jsonargparse._paths import _current_path_dir, _parse_url
from jsonargparse.typing import Path, Path_drw, Path_fc, Path_fr, path_type
from jsonargparse_tests.conftest import (
    get_parser_help,
    is_posix,
    json_or_yaml_dump,
    json_or_yaml_load,
    patch_parsing_settings,
    responses_activate,
    responses_available,
    skip_if_fsspec_unavailable,
    skip_if_requests_unavailable,
    skip_if_responses_unavailable,
    skip_if_running_as_root,
)

if responses_available:
    import responses
if fsspec_support:
    import fsspec


# stdlib path types tests


def test_pathlib_path(parser, file_r):
    parser.add_argument("--path", type=pathlib.Path)
    cfg = parser.parse_args([f"--path={file_r}"])
    assert isinstance(cfg.path, pathlib.Path)
    assert str(cfg.path) == file_r
    assert json_or_yaml_load(parser.dump(cfg)) == {"path": "file_r"}


def test_os_pathlike(parser, file_r):
    parser.add_argument("--path", type=os.PathLike)
    assert file_r == parser.parse_args([f"--path={file_r}"]).path


# base path tests


@pytest.fixture(scope="module")
def paths(tmp_path_factory):
    cwd = os.getcwd()
    tmp_path = tmp_path_factory.mktemp("paths_fixture")
    os.chdir(tmp_path)

    try:
        paths = Namespace()
        paths.tmp_path = tmp_path
        paths.file_rw = file_rw = pathlib.Path("file_rw")
        paths.file_r = file_r = pathlib.Path("file_r")
        paths.file_ = file_ = pathlib.Path("file_")
        paths.dir_rwx = dir_rwx = pathlib.Path("dir_rwx")
        paths.dir_rx = dir_rx = pathlib.Path("dir_rx")
        paths.dir_x = dir_x = pathlib.Path("dir_x")
        paths.dir_file_rx = dir_file_rx = dir_x / "file_rx"

        file_r.write_text("file contents")
        file_rw.touch()
        file_.touch()
        dir_rwx.mkdir()
        dir_rx.mkdir()
        dir_x.mkdir()
        dir_file_rx.touch()

        file_rw.chmod(stat.S_IREAD | stat.S_IWRITE)
        file_r.chmod(stat.S_IREAD)
        file_.chmod(0)
        dir_file_rx.chmod(stat.S_IREAD | stat.S_IEXEC)
        dir_rwx.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        dir_rx.chmod(stat.S_IREAD | stat.S_IEXEC)
        dir_x.chmod(stat.S_IEXEC)

        yield paths
    finally:
        dir_x.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        os.chdir(cwd)


def test_path_init(paths):
    path1 = Path(paths.file_rw, "frw")
    path2 = Path(path1)
    assert path1.cwd == path2.cwd
    assert path1.absolute == path2.absolute
    assert path1.relative == path2.relative
    assert path1.is_url == path2.is_url


def test_path_init_failures(paths):
    pytest.raises(TypeError, lambda: Path(True))
    pytest.raises(ValueError, lambda: Path(paths.file_rw, "-"))
    pytest.raises(ValueError, lambda: Path(paths.file_rw, "frr"))


def test_path_cwd(paths):
    path = Path("file_rx", mode="fr", cwd=(paths.tmp_path / paths.dir_x))
    assert path.cwd == Path("file_rx", mode="fr", cwd=path.cwd).cwd


def test_path_empty_mode(paths):
    path = Path("does_not_exist", "")
    assert path.absolute == str(paths.tmp_path / "does_not_exist")


def test_path_pathlike(paths):
    path = Path(paths.file_rw)
    assert isinstance(path, os.PathLike)
    assert os.fspath(path) == str(paths.tmp_path / paths.file_rw)
    assert os.path.dirname(path) == str(paths.tmp_path)


def test_path_equality_operator(paths):
    path1 = Path(paths.file_rw)
    path2 = Path(paths.tmp_path / paths.file_rw)
    assert path1 == path2
    assert Path("123", "fc") != 123


@skip_if_running_as_root
def test_path_file_access_mode(paths):
    Path(paths.file_rw, "frw")
    Path(paths.file_r, "fr")
    Path(paths.file_, "f")
    Path(paths.dir_file_rx, "fr")
    if is_posix:
        pytest.raises(TypeError, lambda: Path(paths.file_rw, "fx"))
        pytest.raises(TypeError, lambda: Path(paths.file_, "fr"))
    pytest.raises(TypeError, lambda: Path(paths.file_r, "fw"))
    pytest.raises(TypeError, lambda: Path(paths.dir_file_rx, "fw"))
    pytest.raises(TypeError, lambda: Path(paths.dir_rx, "fr"))
    pytest.raises(TypeError, lambda: Path("file_ne", "fr"))


@skip_if_running_as_root
def test_path_dir_access_mode(paths):
    Path(paths.dir_rwx, "drwx")
    Path(paths.dir_rx, "drx")
    Path(paths.dir_x, "dx")
    if is_posix:
        pytest.raises(TypeError, lambda: Path(paths.dir_rx, "dw"))
        pytest.raises(TypeError, lambda: Path(paths.dir_x, "dr"))
    pytest.raises(TypeError, lambda: Path(paths.file_r, "dr"))


def test_path_read_text(paths):
    assert "file contents" == Path(paths.file_r, "fr").read_text()
    assert "file contents" == Path(f"file://{paths.tmp_path}/{paths.file_r}", "fr").read_text()
    assert "file contents" == Path(f"file://{paths.tmp_path}/{paths.file_r}", "ur").read_text()


@skip_if_running_as_root
def test_path_create_mode(paths):
    Path(paths.file_rw, "fcrw")
    Path(paths.tmp_path / "file_c", "fc")
    Path(paths.tmp_path / "not_existing_dir" / "file_c", "fcc")
    Path(paths.dir_rwx, "dcrwx")
    Path(paths.tmp_path / "dir_c", "dc")
    if is_posix:
        pytest.raises(TypeError, lambda: Path(paths.dir_rx / "file_c", "fc"))
        pytest.raises(TypeError, lambda: Path(paths.dir_rx / "dir_c", "dc"))
        pytest.raises(TypeError, lambda: Path(paths.dir_rx / "not_existing_dir" / "file_c", "fcc"))
    pytest.raises(TypeError, lambda: Path(paths.file_rw, "dc"))
    pytest.raises(TypeError, lambda: Path(paths.dir_rwx, "fc"))
    pytest.raises(TypeError, lambda: Path(paths.dir_rwx / "ne" / "file_c", "fc"))


@pytest.mark.parametrize(
    ("path_attr", "mode"),
    [
        ("file_rw", "fW"),
        ("file_rw", "fR"),
        ("dir_rwx", "dX"),
        ("file_rw", "F"),
        ("dir_rwx", "D"),
    ],
)
def test_path_complement_modes(paths, path_attr, mode):
    with pytest.raises(TypeError):
        Path(getattr(paths, path_attr), mode)


@pytest.mark.parametrize(
    "mode",
    [
        True,
        "≠",
        "fd",
        pytest.param("du", marks=pytest.mark.skipif(not url_support, reason="requests package is required")),
    ],
)
def test_path_invalid_modes(paths, mode):
    with pytest.raises(ValueError):
        Path(paths.file_rw, mode)


def test_path_class_hidden_methods(paths):
    path = Path(paths.file_rw, "frw")
    assert str(path) == str(paths.file_rw)
    assert path.__repr__().startswith("Path_frw(")


def test_path_tilde_home(paths):
    home_env = "USERPROFILE" if os.name == "nt" else "HOME"
    with patch.dict(os.environ, {home_env: str(paths.tmp_path)}):
        home = Path("~", "dr")
        path = Path(os.path.join("~", paths.file_rw), "frw")
        assert str(home) == "~"
        assert str(path) == os.path.join("~", paths.file_rw)
        assert home.absolute == str(paths.tmp_path)
        assert path.absolute == os.path.join(paths.tmp_path, paths.file_rw)


def test_std_input_path_read_text():
    input_text_to_test = "a text here\n"

    with patch("sys.stdin", StringIO(input_text_to_test)):
        path = Path("-", mode="fr")
        assert path == "-"
        assert input_text_to_test == path.read_text()


def test_std_input_path_open():
    input_text_to_test = "a text here\n"

    with patch("sys.stdin", StringIO(input_text_to_test)):
        path = Path("-", mode="fr")
        assert path == "-"
        with path.open("r") as std_input:
            assert input_text_to_test == "".join([line for line in std_input])


def test_std_output_path():
    path = Path("-", mode="fw")
    assert path == "-"
    output = StringIO("")
    with patch("sys.stdout", output):
        with path.open("w") as std_output:
            std_output.write("test\n")
    assert output.getvalue() == "test\n"


# url tests


@pytest.mark.parametrize(
    ["url", "scheme", "path"],
    [
        ("https://eg.com:8080/eg", "https://", "eg.com:8080/eg"),
        ("dask::s3://bucket/key", "dask::s3://", "bucket/key"),
        ("filecache::s3://bucket/key", "filecache::s3://", "bucket/key"),
        (
            "zip://*.csv::simplecache::gcs://bucket/file.zip",
            "zip://*.csv::simplecache::gcs://",
            "bucket/file.zip",
        ),
        (
            "simplecache::zip://*.csv::gcs://bucket/file.zip",
            "simplecache::zip://*.csv::gcs://",
            "bucket/file.zip",
        ),
        (
            "zip://existing.txt::file://file1.zip",
            "zip://existing.txt::file://",
            "file1.zip",
        ),
        ("file.txt", None, None),
        ("../../file.txt", None, None),
        ("/tmp/file.txt", None, None),
    ],
)
def test_parse_url(url, scheme, path):
    url_data = _parse_url(url)
    if scheme is None:
        assert url_data is None
    else:
        assert url_data.scheme == scheme
        assert url_data.url_path == path


@skip_if_responses_unavailable
@responses_activate
def test_path_url_200():
    existing = "http://example.com/existing-url"
    existing_body = "url contents"
    responses.add(responses.GET, existing, status=200, body=existing_body)
    responses.add(responses.HEAD, existing, status=200)
    path = Path(existing, mode="ur")
    assert existing_body == path.read_text()


@skip_if_responses_unavailable
@responses_activate
def test_path_url_404():
    nonexisting = "http://example.com/non-existing-url"
    responses.add(responses.HEAD, nonexisting, status=404)
    with pytest.raises(TypeError) as ctx:
        Path(nonexisting, mode="ur")
    ctx.match("404")


# fsspec tests


def create_zip(zip_path, file_path):
    ziph = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)
    ziph.write(file_path)
    ziph.close()


@skip_if_fsspec_unavailable
def test_path_fsspec_zipfile(tmp_cwd):
    existing = pathlib.Path("existing.txt")
    existing_body = "existing content"
    existing.write_text(existing_body)
    nonexisting = "non-existing.txt"
    zip1_path = "file1.zip"
    zip2_path = pathlib.Path("file2.zip")
    create_zip(zip1_path, existing)
    create_zip(zip2_path, existing)
    zip2_path.chmod(0)

    path = Path(f"zip://{existing}::file://{zip1_path}", mode="sr")
    assert existing_body == path.read_text()

    with pytest.raises(TypeError) as ctx:
        Path(f"zip://{nonexisting}::file://{zip1_path}", mode="sr")
    ctx.match("does not exist")

    if is_posix:
        with pytest.raises(TypeError) as ctx:
            Path(f"zip://{existing}::file://{zip2_path}", mode="sr")
        ctx.match("exists but no permission to access")


@skip_if_fsspec_unavailable
def test_path_fsspec_memory():
    file_content = "content in memory"
    memfile = "memfile.txt"
    path = Path(f"memory://{memfile}", mode="sw")
    with fsspec.open(path, "w") as f:
        f.write(file_content)
    assert file_content == path.read_text()


def test_path_fsspec_invalid_mode():
    with pytest.raises(ValueError) as ctx:
        Path("memory://file.txt", mode="ds")
    ctx.match('Both modes "d" and "s" not possible')


@skip_if_fsspec_unavailable
def test_path_fsspec_invalid_scheme():
    with pytest.raises(TypeError) as ctx:
        Path("unsupported://file.txt", mode="sr")
    ctx.match("not readable")


# path open tests


def test_path_open_local(tmp_cwd):
    pathlib.Path("file.txt").write_text("content")
    path = Path("file.txt", mode="fr")
    with path.open() as f:
        assert "content" == f.read()


@skip_if_responses_unavailable
@responses_activate
def test_path_open_url():
    url = "http://example.com/file.txt"
    responses.add(responses.GET, url, status=200, body="content")
    responses.add(responses.HEAD, url, status=200)
    path = Path(url, mode="ur")
    with path.open() as f:
        assert "content" == f.read()


@skip_if_fsspec_unavailable
def test_path_open_fsspec():
    path = Path("memory://nested/file.txt", mode="sc")
    with fsspec.open(path, "w") as f:
        f.write("content")
    path = Path("memory://nested/file.txt", mode="sr")
    with path.open() as f:
        assert "content" == f.read()


# path relative path context tests


@skip_if_requests_unavailable
def test_path_relative_path_context_url():
    path1 = Path("http://example.com/nested/path/file1.txt", mode="u")
    with path1.relative_path_context() as dir:
        assert "http://example.com/nested/path" == dir
        path2 = Path("../file2.txt", mode="u")
        assert path2.absolute == "http://example.com/nested/file2.txt"


@skip_if_fsspec_unavailable
def test_relative_path_context_fsspec(tmp_cwd, subtests):
    local_path = tmp_cwd / "file0.txt"
    local_path.write_text("zero")

    mem_path = Path("memory://one/two/file1.txt", mode="sc")
    with fsspec.open(mem_path, "w") as f:
        f.write("one")

    with Path("memory://one/two/three/file1.txt", mode="sc").relative_path_context() as dir1:
        with subtests.test("get current path dir"):
            assert "memory://one/two/three" == dir1
            assert "memory://one/two/three" == _current_path_dir.get()

        with subtests.test("absolute local path"):
            path0 = Path(local_path, mode="fr")
            assert "zero" == path0.read_text()

        with subtests.test("relative fsspec path"):
            path1 = Path("../file1.txt", mode="fsr")
            assert "one" == path1.read_text()
            assert str(path1) == "../file1.txt"
            assert path1.absolute == "memory://one/two/file1.txt"
            assert path1._url_data is not None

        with subtests.test("nested fsspec dir"):
            with path1.relative_path_context() as dir2:
                assert "memory://one/two" == dir2
                path2 = Path("four/five/six/../file2.txt", mode="fsc")
                assert path2.absolute == "memory://one/two/four/five/file2.txt"

        with subtests.test("non-fsspec path"):
            path3 = Path("file3.txt", mode="fc")
            assert path3.absolute == str(tmp_cwd / "file3.txt")

    with subtests.test("current path dir unset"):
        assert _current_path_dir.get() is None


# path types tests


def test_path_fr(file_r):
    path = Path_fr(file_r)
    assert path == file_r
    assert path.absolute == os.path.realpath(file_r)
    pytest.raises(TypeError, lambda: Path_fr("does_not_exist"))


def test_path_fc_with_kwargs(tmpdir):
    path = Path_fc("some-file.txt", cwd=tmpdir)
    assert path.absolute == os.path.join(tmpdir, "some-file.txt")


def test_path_fr_already_registered():
    assert Path_fr is path_type("fr")


def test_paths_config_relative_absolute(parser, tmp_cwd):
    parser.add_argument("--cfg", action="config")
    parser.add_argument("--file", type=Path_fr)
    parser.add_argument("--dir", type=Path_drw)

    (tmp_cwd / "example").mkdir()
    rel_yaml_file = pathlib.Path("..", "example", "example.yaml")
    abs_yaml_file = (tmp_cwd / "example" / rel_yaml_file).resolve()
    abs_yaml_file.write_text(json_or_yaml_dump({"file": str(rel_yaml_file), "dir": str(tmp_cwd)}))

    cfg = parser.parse_args([f"--cfg={abs_yaml_file}"])
    assert os.path.realpath(tmp_cwd) == os.path.realpath(cfg.dir)
    assert str(rel_yaml_file) == str(cfg.file)
    assert str(abs_yaml_file) == os.path.realpath(cfg.file)

    cfg = parser.parse_args([f"--file={abs_yaml_file}", f"--dir={tmp_cwd}"])
    assert str(abs_yaml_file) == os.path.realpath(cfg.file)
    assert str(tmp_cwd) == os.path.realpath(cfg.dir)

    pytest.raises(ArgumentError, lambda: parser.parse_args([f"--dir={abs_yaml_file}"]))
    pytest.raises(ArgumentError, lambda: parser.parse_args([f"--file={tmp_cwd}"]))


def test_path_fc_nargs_plus(parser, tmp_cwd):
    parser.add_argument("--files", nargs="+", type=Path_fc)
    (tmp_cwd / "subdir").mkdir()
    cfg = parser.parse_args(["--files", "file1", "subdir/file2"])
    assert isinstance(cfg.files, list)
    assert 2 == len(cfg.files)
    assert str(tmp_cwd / "subdir" / "file2") == os.path.realpath(cfg.files[1])


def test_list_path_fc(parser, tmp_cwd):
    parser.add_argument("--paths", type=List[Path_fc])
    cfg = parser.parse_args(['--paths=["file1", "file2"]'])
    assert ["file1", "file2"] == cfg.paths
    assert isinstance(cfg.paths[0], Path_fc)
    assert isinstance(cfg.paths[1], Path_fc)


def test_optional_path_fr(parser, file_r):
    parser.add_argument("--path", type=Optional[Path_fr])
    assert None is parser.parse_args(["--path=null"]).path
    cfg = parser.parse_args([f"--path={file_r}"])
    assert file_r == cfg.path
    assert isinstance(cfg.path, Path_fr)
    pytest.raises(ArgumentError, lambda: parser.parse_args(["--path=not_exist"]))


def test_register_path_dcc_default_path(parser, tmp_cwd):
    path_dcc = path_type("dcc")
    parser.add_argument("--path", type=path_dcc, default=path_dcc("test"))
    cfg = parser.parse_args([])
    assert {"path": "test"} == json_or_yaml_load(parser.dump(cfg))
    help_str = get_parser_help(parser)
    assert "(type: Path_dcc, default: test)" in help_str


def test_path_dump(parser, tmp_cwd):
    parser.add_argument("--path", type=Path_fc)
    cfg = parser.parse_string(json_or_yaml_dump({"path": "path"}))
    assert json_or_yaml_load(parser.dump(cfg)) == {"path": "path"}


def test_paths_dump(parser, tmp_cwd):
    parser.add_argument("--paths", nargs="+", type=Path_fc)
    cfg = parser.parse_args(["--paths", "path1", "path2"])
    assert json_or_yaml_load(parser.dump(cfg)) == {"paths": ["path1", "path2"]}


def test_path_fr_default_stdin(parser):
    parser.add_argument("--path", type=Path_fr, default="-")

    defaults = parser.get_defaults()
    assert defaults.path == Path_fr("-")

    defaults = parser.parse_args([])
    assert defaults.path == Path_fr("-")


# sub_configs tests


def test_sub_configs_dict(parser, tmp_cwd):
    data = {"a": 1, "b": 2, "c": [3, 4]}
    pathlib.Path("data.yaml").write_text(json.dumps(data))

    parser.add_argument("--data", type=Dict[str, Any], sub_configs=True)
    cfg = parser.parse_args(["--data=data.yaml"])
    assert "data.yaml" == str(cfg["data"].pop("__path__"))
    assert data == cfg["data"]
    with pytest.raises(ArgumentError) as ctx:
        parser.parse_args(["--data=does-not-exist.yaml"])
    ctx.match("Expected a path but does-not-exist.yaml either not accessible or invalid")


def test_sub_configs_subclass(parser, tmp_cwd):
    obj = {"class_path": f"{__name__}.Base"}
    pathlib.Path("obj.yaml").write_text(json.dumps(obj))

    parser.add_argument("--cls", type=Base, sub_configs=True)
    cfg = parser.parse_args(["--cls=obj.yaml"])
    init = parser.instantiate(cfg)
    assert isinstance(init["cls"], Base)


def test_sub_configs_list_path_fr(parser, tmp_cwd, mock_stdin, subtests):
    tmpdir = tmp_cwd / "subdir"
    tmpdir.mkdir()
    (tmpdir / "file1").touch()
    (tmpdir / "file2").touch()
    (tmpdir / "file3").touch()
    (tmpdir / "file4").touch()
    (tmpdir / "file5").touch()
    list_file1 = tmpdir / "files1.lst"
    list_file2 = tmpdir / "files2.lst"
    list_file3 = tmpdir / "files3.lst"
    list_file4 = tmpdir / "files4.lst"
    list_file1.write_text("file1\nfile2\nfile3\nfile4\n")
    list_file2.write_text("file5\n")
    list_file3.touch()
    list_file4.write_text("file1\nfile2\nfile6\n")

    parser.add_argument(
        "--list",
        type=List[Path_fr],
        sub_configs=True,
    )
    parser.add_argument(
        "--lists",
        nargs="+",
        type=List[Path_fr],
        sub_configs=True,
    )

    with subtests.test("paths list from file"):
        cfg = parser.parse_args([f"--list={list_file1}"])
        assert all(isinstance(x, Path_fr) for x in cfg.list)
        assert ["file1", "file2", "file3", "file4"] == [str(x) for x in cfg.list]

    with subtests.test("paths list from stdin"):
        with mock_stdin("file1\nfile2\n"):
            with Path_drw("subdir").relative_path_context():
                cfg = parser.parse_args(["--list", "-"])
        assert all(isinstance(x, Path_fr) for x in cfg.list)
        assert ["file1", "file2"] == [str(x) for x in cfg.list]

    with subtests.test("paths list from stdin path not exist"):
        with mock_stdin("file1\nfile2\n"):
            with pytest.raises(ArgumentError) as ctx:
                parser.parse_args(["--list", "-"])
            ctx.match("File does not exist")

    with subtests.test("paths list nargs='+' single"):
        cfg = parser.parse_args(["--lists", str(list_file1)])
        assert 1 == len(cfg.lists)
        assert ["file1", "file2", "file3", "file4"] == [str(x) for x in cfg.lists[0]]
        assert all(isinstance(x, Path_fr) for x in cfg.lists[0])

    with subtests.test("paths list nargs='+' multiple"):
        cfg = parser.parse_args(["--lists", str(list_file1), str(list_file2)])
        assert 2 == len(cfg.lists)
        assert ["file1", "file2", "file3", "file4"] == [str(x) for x in cfg.lists[0]]
        assert ["file5"] == [str(x) for x in cfg.lists[1]]

    with subtests.test("paths list nargs='+' empty"):
        cfg = parser.parse_args(["--lists", str(list_file3)])
        assert [[]] == cfg.lists

    with subtests.test("paths list nargs='+' path not exist"):
        pytest.raises(ArgumentError, lambda: parser.parse_args(["--lists", str(list_file4)]))

    with subtests.test("paths list nargs='+' list not exist"):  # TODO: check error message
        with pytest.raises(ArgumentError) as ctx:
            parser.parse_args(["--lists", "no-such-file"])
        ctx.match("Expected a path but no-such-file either not accessible or invalid")


@pytest.mark.parametrize("validate_defaults", [False, True])
@patch_parsing_settings
def test_sub_configs_list_path_fr_default_stdin(parser, tmp_cwd, validate_defaults, mock_stdin, subtests):
    set_parsing_settings(validate_defaults=validate_defaults)
    (tmp_cwd / "file1").touch()
    (tmp_cwd / "file2").touch()

    parser.add_argument(
        "--list",
        type=List[Path_fr],
        sub_configs=True,
        default="-",
    )

    with subtests.test("defaults"):
        defaults = parser.get_defaults()
        assert defaults.list == "-"

    with subtests.test("without args"):
        with mock_stdin("file1\nfile2\n"):
            cfg = parser.parse_args([])
        assert all(isinstance(x, Path_fr) for x in cfg.list)
        assert ["file1", "file2"] == [str(x) for x in cfg.list]

    with subtests.test("stdin arg"):
        with mock_stdin("file1\nfile2\n"):
            cfg = parser.parse_args(["--list=-"])
        assert all(isinstance(x, Path_fr) for x in cfg.list)
        assert ["file1", "file2"] == [str(x) for x in cfg.list]

    with subtests.test("help"):
        help_str = get_parser_help(parser)
        assert "'[\"PATH1\",...]' | LIST_OF_PATHS_FILE | -" in help_str


class ClassListPath:
    def __init__(self, files: list[Path_fr]):
        self.files = files  # pragma: no cover


def test_add_class_list_path(parser, tmp_cwd):
    (tmp_cwd / "file1").touch()
    (tmp_cwd / "file2").touch()
    list_file1 = tmp_cwd / "files.lst"
    list_file1.write_text("file1\nfile2\n")

    parser.add_class_arguments(ClassListPath, "cls", sub_configs=True)

    cfg = parser.parse_args([f"--cls.files={list_file1}"])
    assert all(isinstance(x, Path_fr) for x in cfg.cls.files)
    assert ["file1", "file2"] == [str(x) for x in cfg.cls.files]

    help_str = get_parser_help(parser)
    assert "'[\"PATH1\",...]' | LIST_OF_PATHS_FILE | -" in help_str


class DataOptionalPath:
    def __init__(self, path: Optional[os.PathLike] = None):
        pass  # pragma: no cover


def test_sub_configs_optional_pathlike_subclass_parameter(parser, tmp_cwd):
    data_path = pathlib.Path("data.json")
    data_path.write_text('{"a": 1}')

    parser.add_argument("--data", type=DataOptionalPath, sub_configs=True)

    cfg = parser.parse_args([f"--data={__name__}.DataOptionalPath", f"--data.path={data_path}"])
    assert cfg.data.class_path == f"{__name__}.DataOptionalPath"
    assert cfg.data.init_args == Namespace(path=str(data_path))


class Base:
    pass


class DataUnionPath:
    def __init__(self, path: Union[Base, os.PathLike, str] = ""):
        pass  # pragma: no cover


def test_sub_configs_union_subclass_and_pathlike(parser, tmp_cwd):
    data_path = pathlib.Path("data.csv")
    data_path.write_text("x\ny\n")
    config = {
        "data": {
            "path": "data.csv",
        }
    }
    config_path = pathlib.Path("config.json")
    config_path.write_text(json.dumps(config))

    parser.add_class_arguments(DataUnionPath, "data", sub_configs=True)
    parser.add_argument("--cfg", action="config")

    cfg = parser.parse_args([f"--cfg={config_path}"])
    assert cfg.data.path == str(data_path)


def test_union_path_or_dict(parser, tmp_cwd):
    arg_path = pathlib.Path("arg.json")
    arg_path.touch()

    parser.add_argument("--arg", type=Union[Path_fr, dict])

    cfg = parser.parse_args([f"--arg={arg_path}"])
    assert isinstance(cfg.arg, Path_fr)
    assert str(arg_path) == str(cfg.arg)

    cfg = parser.parse_args(['--arg={"key": "value"}'])
    assert cfg.arg == {"key": "value"}


def test_import_old_path_location():
    from jsonargparse import Path as path_old

    assert path_old is Path
