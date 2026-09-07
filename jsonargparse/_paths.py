import os
import re
import stat
import sys
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from io import StringIO
from typing import IO, Any

from ._optionals import (
    fsspec_support,
    import_fsspec,
    import_requests,
    url_support,
)

_current_path_dir: ContextVar[str | None] = ContextVar("_current_path_dir", default=None)


class _CachedStdin(StringIO):
    """Used to allow reading sys.stdin multiple times."""


def _get_cached_stdin() -> _CachedStdin:
    if not isinstance(sys.stdin, _CachedStdin):
        sys.stdin = _CachedStdin(sys.stdin.read())
    return sys.stdin


def _read_cached_stdin() -> str:
    stdin = _get_cached_stdin()
    value = stdin.read()
    stdin.seek(0)
    return value


@dataclass
class _UrlData:
    scheme: str
    url_path: str


def _parse_url(url: str) -> _UrlData | None:
    index = url.rfind("://")
    if index <= 0:
        return None
    return _UrlData(
        scheme=url[: index + 3],
        url_path=url[index + 3 :],
    )


def _is_absolute_path(path: str) -> bool:
    if path.find("://") > 0:
        return True
    return os.path.isabs(path)


def _resolve_relative_path(path: str) -> str:
    parts = path.split("/")
    resolved: list[str] = []
    for part in parts:
        if part == "..":
            resolved.pop()
        elif part != ".":
            resolved.append(part)
    return "/".join(resolved)


def _known_to_fsspec(path: str) -> bool:
    import_fsspec("_known_to_fsspec")
    from fsspec.registry import known_implementations

    for protocol in known_implementations:
        if path.startswith(protocol + "://") or path.startswith(protocol + "::"):
            return True
    return False


class PathError(TypeError):
    """Exception raised for errors in the Path class."""


class Path:
    """Base class for Path types. Stores a (possibly relative) path and the corresponding absolute path.

    From the object the absolute path can be obtained without having to remember
    the working directory (or parent remote path) from when the object was
    created.

    When a Path instance is created, it is checked that: the path exists,
    whether it is a file or directory and whether it has the required access
    permissions (f=file, d=directory, r=readable, w=writable, x=executable,
    c=creatable, u=url, s=fsspec or in uppercase meaning not, i.e., F=not-file,
    D=not-directory, R=not-readable, W=not-writable and X=not-executable).

    The creatable flag "c" can be given one or two times. If given once, the
    parent directory must exist and be writable. If given twice, the parent
    directory does not have to exist, but should be allowed to create.

    An instance of Path class can also refer to the standard input or output.
    To do that, path must be set with the value "-"; it is a common practice.
    Then, getting the content or opening it will automatically be done on
    standard input or output.
    """

    _url_data: _UrlData | None
    _file_scheme = re.compile("^file:///?")

    def __init__(
        self,
        path: "str | os.PathLike | Path",
        mode: str = "fr",
        cwd: str | os.PathLike | None = None,
    ):
        """Initializer for Path instance.

        Args:
            path: The path to check and store.
            mode: The required type and access permissions among ``[fdrwxcuFDRWX]``.
            cwd: Working directory for relative paths. If ``None`` then ``os.getcwd()`` is used.

        Raises:
            ValueError: If the provided mode is invalid.
            PathError: If the path does not exist or does not agree with the mode.
        """
        self._check_mode(mode)
        self._std_io = False

        is_url = False
        is_fsspec = False
        if isinstance(path, Path):
            self._std_io = path._std_io
            is_url = path.is_url
            is_fsspec = path.is_fsspec
            url_data = path._url_data
            cwd = path.cwd
            abs_path = path.absolute
            path = path.relative
        elif isinstance(path, (str, os.PathLike)):
            if path == "-":
                self._std_io = True
            path = os.fspath(path)
            cwd = os.fspath(cwd) if cwd else None
            abs_path = os.path.expanduser(path)
            if self._file_scheme.match(abs_path):
                abs_path = self._file_scheme.sub("" if os.name == "nt" else "/", abs_path)
            is_absolute = _is_absolute_path(abs_path)
            url_data = _parse_url(abs_path)
            cwd_url_data = _parse_url(cwd or _current_path_dir.get() or os.getcwd())
            if ("u" in mode or "s" in mode) and (url_data or (cwd_url_data and not is_absolute)):
                if cwd_url_data and not is_absolute:
                    abs_path = _resolve_relative_path(cwd_url_data.url_path + "/" + path)
                    abs_path = cwd_url_data.scheme + abs_path
                    url_data = _parse_url(abs_path)
                if cwd is None:
                    cwd = _current_path_dir.get() or os.getcwd()
                if "u" in mode and url_support:
                    is_url = True
                elif "s" in mode and fsspec_support and _known_to_fsspec(abs_path):
                    is_fsspec = True
            else:
                if cwd is None:
                    cwd = os.getcwd()
                abs_path = abs_path if is_absolute else os.path.join(cwd, abs_path)
                url_data = None
        else:
            raise PathError("Expected path to be a string, os.PathLike or a Path object.")

        if is_url:
            if "r" in mode:
                requests = import_requests("Path with URL support")
                try:
                    requests.head(abs_path).raise_for_status()
                except requests.HTTPError as ex:
                    raise PathError(f"{abs_path} HEAD not accessible :: {ex}") from ex
        elif is_fsspec:
            fsspec_mode = "".join(c for c in mode if c in {"r", "w"})
            if fsspec_mode:
                fsspec = import_fsspec("Path")
                try:
                    handle = fsspec.open(abs_path, fsspec_mode)
                    handle.open()
                    handle.close()
                except (FileNotFoundError, KeyError) as ex:
                    raise PathError(f"Path does not exist: {abs_path!r}") from ex
                except PermissionError as ex:
                    raise PathError(f"Path exists but no permission to access: {abs_path!r}") from ex
        elif not self._std_io:
            ptype = "Directory" if "d" in mode else "File"
            if "c" in mode:
                pdir = os.path.realpath(os.path.join(abs_path, ".."))
                if not os.path.isdir(pdir) and mode.count("c") == 2:
                    ppdir = None
                    while not os.path.isdir(pdir) and pdir != ppdir:
                        ppdir = pdir
                        pdir = os.path.realpath(os.path.join(pdir, ".."))
                if not os.path.isdir(pdir):
                    raise PathError(f"{ptype} is not creatable since parent directory does not exist: {abs_path!r}")
                if not os.access(pdir, os.W_OK):
                    raise PathError(f"{ptype} is not creatable since parent directory not writable: {abs_path!r}")
                if "d" in mode and os.access(abs_path, os.F_OK) and not os.path.isdir(abs_path):
                    raise PathError(f"{ptype} is not creatable since path already exists: {abs_path!r}")
                if "f" in mode and os.access(abs_path, os.F_OK) and not os.path.isfile(abs_path):
                    raise PathError(f"{ptype} is not creatable since path already exists: {abs_path!r}")
            elif "d" in mode or "f" in mode:
                if not os.access(abs_path, os.F_OK):
                    raise PathError(f"{ptype} does not exist: {abs_path!r}")
                if "d" in mode and not os.path.isdir(abs_path):
                    raise PathError(f"Path is not a directory: {abs_path!r}")
                if "f" in mode and not (os.path.isfile(abs_path) or stat.S_ISFIFO(os.stat(abs_path).st_mode)):
                    raise PathError(f"Path is not a file: {abs_path!r}")

            if "r" in mode and not os.access(abs_path, os.R_OK):
                raise PathError(f"{ptype} is not readable: {abs_path!r}")
            if "w" in mode and not os.access(abs_path, os.W_OK):
                raise PathError(f"{ptype} is not writable: {abs_path!r}")
            if "x" in mode and not os.access(abs_path, os.X_OK):
                raise PathError(f"{ptype} is not executable: {abs_path!r}")
            if "D" in mode and os.path.isdir(abs_path):
                raise PathError(f"Path is a directory: {abs_path!r}")
            if "F" in mode and (os.path.isfile(abs_path) or stat.S_ISFIFO(os.stat(abs_path).st_mode)):
                raise PathError(f"Path is a file: {abs_path!r}")
            if "R" in mode and os.access(abs_path, os.R_OK):
                raise PathError(f"{ptype} is readable: {abs_path!r}")
            if "W" in mode and os.access(abs_path, os.W_OK):
                raise PathError(f"{ptype} is writable: {abs_path!r}")
            if "X" in mode and os.access(abs_path, os.X_OK):
                raise PathError(f"{ptype} is executable: {abs_path!r}")

        self._relative = path
        self._absolute = abs_path
        self._cwd = cwd
        self._mode = mode
        self._is_url = is_url
        self._is_fsspec = is_fsspec
        self._url_data = url_data

    @property
    def relative(self) -> str:
        """Returns the relative representation of the path (how the path was given on instance creation)."""
        return self._relative

    @property
    def absolute(self) -> str:
        """Returns the absolute representation of the path."""
        return self._absolute

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def cwd(self) -> str:
        return self._cwd

    @property
    def is_url(self) -> bool:
        return self._is_url

    @property
    def is_fsspec(self) -> bool:
        return self._is_fsspec

    def __str__(self):
        return self._relative

    def __repr__(self):
        name = "Path_" + self._mode
        cwd = ""
        if self._relative != self._absolute:
            cwd = ", cwd=" + self._cwd
        return f"{name}({self._relative}{cwd})"

    def __fspath__(self) -> str:
        return self._absolute

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Path):
            return self._absolute == other._absolute
        elif isinstance(other, str):
            return str(self) == other
        return False

    def read_text(self) -> str:
        """Returns the text contents of the file or the remote path."""
        if self._std_io:
            return _read_cached_stdin()
        elif self._is_url:
            requests = import_requests("Path.read_text")
            response = requests.get(self._absolute)
            response.raise_for_status()
            return response.text
        elif self._is_fsspec:
            fsspec = import_fsspec("Path.read_text")
            with fsspec.open(self._absolute, "r") as handle:
                with handle as input_file:
                    return input_file.read()
        else:
            with open(self._absolute) as input_file:
                return input_file.read()

    @contextmanager
    def open(self, mode: str = "r") -> Iterator[IO]:
        """Return an opened file object for the path."""
        if self._std_io:
            if "r" in mode:
                yield _get_cached_stdin()
            elif "w" in mode:
                yield sys.stdout
        elif self._is_url:
            yield StringIO(self.read_text())
        elif self._is_fsspec:
            fsspec = import_fsspec("Path.open")
            with fsspec.open(self._absolute, mode) as handle:
                yield handle
        else:
            with open(self._absolute, mode) as handle:
                yield handle

    @contextmanager
    def relative_path_context(self) -> Iterator[str]:
        """Context manager to use this path's parent (directory or URL) for relative paths defined within."""
        with change_to_path_dir(self) as path_dir:
            assert isinstance(path_dir, str)
            yield path_dir

    @staticmethod
    def _check_mode(mode: str):
        if not isinstance(mode, str):
            raise ValueError("Expected mode to be a string.")
        if len(set(mode) - set("fdrwxcusFDRWX")) > 0:
            raise ValueError("Expected mode to only include [fdrwxcusFDRWX] flags.")
        for flag, count in Counter(mode).items():
            if count > (2 if flag == "c" else 1):
                raise ValueError(f'Too many occurrences ({count}) for flag "{flag}".')
        if "f" in mode and "d" in mode:
            raise ValueError('Both modes "f" and "d" not possible.')
        if "u" in mode and "d" in mode:
            raise ValueError('Both modes "d" and "u" not possible.')
        if "s" in mode and "d" in mode:
            raise ValueError('Both modes "d" and "s" not possible.')


@contextmanager
def change_to_path_dir(path: Path | str | None) -> Iterator[str | None]:
    """A context manager for running code in the directory of a path."""
    path_dir = _current_path_dir.get()
    chdir: bool | str = False
    if path is not None:
        if isinstance(path, str):
            path = Path(path, mode="d")
        if path._url_data and (path.is_url or path.is_fsspec):
            scheme = path._url_data.scheme
            path_dir = path._url_data.url_path
        else:
            scheme = ""
            path_dir = path.absolute
            chdir = True
        if "d" not in path.mode:
            path_dir = os.path.dirname(path_dir)
        path_dir = scheme + path_dir

    token = _current_path_dir.set(path_dir)
    if chdir and path_dir:
        chdir = os.getcwd()
        path_dir = os.path.abspath(path_dir)
        os.chdir(path_dir)

    try:
        yield path_dir
    finally:
        _current_path_dir.reset(token)
        if chdir:
            os.chdir(chdir)
