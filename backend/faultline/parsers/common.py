"""Shared pieces for manifest parsers: bounded reads inside a snapshot, diagnostics, and result types.

Parsers never execute anything. Every failure is a diagnostic or a typed status; a parser never returns an empty
success for input it could not read.
"""
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core.errors import ErrorCode, FaultlineError

MAX_MANIFEST_BYTES = 5 * 1024 * 1024


class ManifestError(FaultlineError):
    """A manifest could not be read. `code` is MANIFEST_PARSE_FAILED or MANIFEST_TOO_LARGE."""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.MANIFEST_PARSE_FAILED, path: str | None = None):
        super().__init__(message, code=code, details={"path": path} if path else {})
        self.path = path


class PathEscape(ManifestError):
    pass


def canonical_name(name: str) -> str:
    """PEP 503 normalisation: runs of '-', '_' and '.' collapse to one '-', lower case."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Diagnostic:
    code: str                       # UNPARSEABLE_LINE, UNSUPPORTED_OPTION, PATH_ESCAPE, INCLUDE_CYCLE, ...
    message: str
    path: str
    line: int | None = None


@dataclass(frozen=True)
class Dependency:
    name: str                       # canonical
    display: str
    specifier: str = ""             # PEP 440 specifier text, "" when unconstrained
    extras: tuple[str, ...] = ()
    marker: str | None = None
    kind: str = "registry"          # registry | vcs | url | path
    source_ref: str | None = None   # URL or path for non-registry dependencies
    group: str = "main"             # main | dev | optional:<extra> | group:<name>
    origin: str = ""                # manifest path
    line: int | None = None
    hashes: tuple[str, ...] = ()


@dataclass
class ManifestResult:
    kind: str
    path: str
    status: str = "OK"              # OK | PARTIAL | FAILED | TOO_LARGE | UNSUPPORTED
    dependencies: list[Dependency] = field(default_factory=list)
    constraints: list[Dependency] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def add(self, code: str, message: str, line: int | None = None, path: str | None = None) -> None:
        self.diagnostics.append(Diagnostic(code, message, path or self.path, line))
        if self.status == "OK":
            self.status = "PARTIAL"


class SnapshotFS:
    """Read-only view of a snapshot directory. Paths are snapshot-relative POSIX paths and cannot leave the root."""

    def __init__(self, root: Path, max_bytes: int = MAX_MANIFEST_BYTES):
        self.root = Path(root)
        self.max_bytes = max_bytes

    @staticmethod
    def join(base_file: str, include: str) -> str:
        """Resolve `include` relative to the directory of `base_file`; refuse anything outside the snapshot root."""
        if not include or "\x00" in include or "\\" in include or include.startswith("/") or re.match(r"^[A-Za-z]:", include):
            raise PathEscape(f"include path {include!r} is not a relative path inside the repository", path=base_file)
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(base_file), include))
        if joined == ".." or joined.startswith("../") or joined == ".":
            raise PathEscape(f"include path {include!r} leaves the repository", path=base_file)
        return joined

    def exists(self, rel: str) -> bool:
        return self._path(rel).is_file()

    def _path(self, rel: str) -> Path:
        parts = rel.split("/")
        if rel.startswith("/") or ".." in parts or "\\" in rel:
            raise PathEscape(f"path {rel!r} is outside the repository", path=rel)
        return self.root.joinpath(*parts)

    def read_bytes(self, rel: str) -> bytes:
        p = self._path(rel)
        if not p.is_file():
            raise ManifestError(f"{rel} is not a file in this snapshot", path=rel)
        size = p.stat().st_size
        if size > self.max_bytes:
            raise ManifestError(f"{rel} is {size} bytes; the limit is {self.max_bytes}", ErrorCode.MANIFEST_TOO_LARGE, rel)
        return p.read_bytes()

    def read_text(self, rel: str) -> str:
        try:
            return self.read_bytes(rel).decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise ManifestError(f"{rel} is not valid UTF-8", path=rel) from e

    def listdir_files(self, rel_dir: str) -> list[str]:
        """Names of regular files directly inside a directory (used only for layout discovery)."""
        d = self.root if rel_dir in ("", ".") else self._path(rel_dir)
        return sorted(p.name for p in d.iterdir() if p.is_file()) if d.is_dir() else []


def failed(kind: str, path: str, e: ManifestError) -> ManifestResult:
    r = ManifestResult(kind, path, "TOO_LARGE" if e.code == ErrorCode.MANIFEST_TOO_LARGE else "FAILED")
    r.diagnostics.append(Diagnostic(e.code.value, e.message, path))
    return r


def to_jsonable(obj):
    """Plain dict/list form of a parse result, for goldens, persistence and the API."""
    import dataclasses
    return dataclasses.asdict(obj)
