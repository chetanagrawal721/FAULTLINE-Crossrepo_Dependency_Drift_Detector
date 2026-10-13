"""uv.lock and poetry.lock readers. A lockfile is authoritative: the locked set is the world, so a lock that cannot be
read fully is FAILED, never an empty or partial world."""
import tomllib
from dataclasses import dataclass, field

from ..common import ManifestError, SnapshotFS, canonical_name

SUPPORTED_UV_VERSIONS = {1}
SUPPORTED_POETRY_LOCK_MAJOR = {1, 2}


@dataclass(frozen=True)
class LockedPackage:
    name: str                       # canonical
    display: str
    version: str
    source_kind: str                # registry | git | url | path | editable | virtual
    source_ref: str | None
    wheel_hashes: tuple[str, ...] = ()      # sha256 of each wheel file (hex)
    wheel_files: tuple[str, ...] = ()
    has_sdist: bool = False
    dependencies: tuple[str, ...] = ()      # canonical names
    dep_edges: tuple[tuple[str, str | None], ...] = ()   # (canonical name, marker or None): what this package requires


@dataclass
class LockResult:
    kind: str
    path: str
    status: str = "OK"              # OK | FAILED | TOO_LARGE | UNSUPPORTED
    packages: list[LockedPackage] = field(default_factory=list)
    requires_python: str | None = None
    meta: dict = field(default_factory=dict)
    error: str | None = None


def _hex(h: str | None) -> str | None:
    return h.split(":", 1)[1].lower() if h and h.startswith("sha256:") else None


def _fail(kind: str, path: str, e: ManifestError | str, status: str = "FAILED") -> LockResult:
    if isinstance(e, ManifestError):
        status = "TOO_LARGE" if e.code.value == "MANIFEST_TOO_LARGE" else status
        return LockResult(kind, path, status, error=e.message)
    return LockResult(kind, path, status, error=e)


def _poetry_marker(v) -> str | None:
    """Marker text of a poetry.lock dependency entry (a version string has none)."""
    items = v if isinstance(v, list) else [v]
    marks = []
    for i in items:
        if isinstance(i, dict) and i.get("markers"):
            marks.append(f"({i['markers']})")
        elif not isinstance(i, dict) or not i.get("markers"):
            return None                       # at least one unconditional form: always required
    return " or ".join(marks) or None


def parse_uv_lock(fs: SnapshotFS, rel: str) -> LockResult:
    try:
        data = tomllib.loads(fs.read_text(rel))
    except ManifestError as e:
        return _fail("uv_lock", rel, e)
    except tomllib.TOMLDecodeError as e:
        return _fail("uv_lock", rel, f"{rel} is not valid TOML: {e}")
    version = data.get("version")
    if version not in SUPPORTED_UV_VERSIONS:
        return _fail("uv_lock", rel, f"uv.lock format version {version!r} is not supported (supported: {sorted(SUPPORTED_UV_VERSIONS)})", "UNSUPPORTED")
    res = LockResult("uv_lock", rel, requires_python=data.get("requires-python"), meta={"lock_version": version, "revision": data.get("revision")})
    pkgs = data.get("package")
    if not isinstance(pkgs, list) or not pkgs:
        return _fail("uv_lock", rel, "uv.lock contains no [[package]] entries")
    seen: set[tuple[str, str | None]] = set()
    for p in pkgs:
        try:
            name, ver = p["name"], p.get("version")
            src = p.get("source", {})
            kind = next((k for k in ("registry", "git", "url", "path", "editable", "virtual", "directory") if k in src), None)
            if kind is None:
                return _fail("uv_lock", rel, f"package {name!r} has an unrecognised source")
            if ver is None and kind not in ("virtual", "editable", "directory", "path"):
                return _fail("uv_lock", rel, f"package {name!r} has no version")
            wheels = p.get("wheels", [])
            hashes = tuple(h for h in (_hex(w.get("hash")) for w in wheels) if h)
            if len(hashes) != len(wheels):
                return _fail("uv_lock", rel, f"package {name!r} has a wheel without a sha256 hash")
            files = tuple(w["url"].rsplit("/", 1)[-1] for w in wheels if "url" in w)
            key = (canonical_name(name), ver)
            if key in seen:
                return _fail("uv_lock", rel, f"package {name!r} {ver} is listed twice")
            seen.add(key)
            res.packages.append(LockedPackage(canonical_name(name), name, ver or "", kind, src.get(kind) if isinstance(src.get(kind), str) else None,
                                              hashes, files, "sdist" in p,
                                              tuple(sorted({canonical_name(d["name"]) for d in p.get("dependencies", [])})),
                                              tuple(sorted({(canonical_name(d["name"]), d.get("marker")) for d in p.get("dependencies", [])},
                                                           key=lambda e: (e[0], e[1] or "")))))
        except (KeyError, TypeError, AttributeError) as e:
            return _fail("uv_lock", rel, f"malformed [[package]] entry: {e!r}")
    return res


def parse_poetry_lock(fs: SnapshotFS, rel: str) -> LockResult:
    try:
        data = tomllib.loads(fs.read_text(rel))
    except ManifestError as e:
        return _fail("poetry_lock", rel, e)
    except tomllib.TOMLDecodeError as e:
        return _fail("poetry_lock", rel, f"{rel} is not valid TOML: {e}")
    meta = data.get("metadata", {})
    lv = str(meta.get("lock-version", ""))
    try:
        major = int(lv.split(".")[0])
    except ValueError:
        return _fail("poetry_lock", rel, f"poetry.lock has no readable lock-version ({lv!r})", "UNSUPPORTED")
    if major not in SUPPORTED_POETRY_LOCK_MAJOR:
        return _fail("poetry_lock", rel, f"poetry.lock lock-version {lv} is not supported", "UNSUPPORTED")
    pkgs = data.get("package")
    if not isinstance(pkgs, list) or not pkgs:
        return _fail("poetry_lock", rel, "poetry.lock contains no [[package]] entries")
    res = LockResult("poetry_lock", rel, requires_python=meta.get("python-versions"),
                     meta={"lock_version": lv, "content_hash": meta.get("content-hash")})
    old_files = meta.get("files", {}) if major == 1 else {}
    for p in pkgs:
        try:
            name, ver = p["name"], p["version"]
            src = p.get("source", {"type": "legacy"})
            stype = src.get("type", "registry")
            kind = {"legacy": "registry", "directory": "path", "file": "path"}.get(stype, stype)
            files = p.get("files") if major >= 2 else old_files.get(name, [])
            wheels = [f for f in files or [] if f["file"].endswith(".whl")]
            hashes = tuple(h for h in (_hex(f.get("hash")) for f in wheels) if h)
            if len(hashes) != len(wheels):
                return _fail("poetry_lock", rel, f"package {name!r} has a wheel without a sha256 hash")
            res.packages.append(LockedPackage(canonical_name(name), name, ver, kind, src.get("url"), hashes,
                                              tuple(f["file"] for f in wheels), any(not f["file"].endswith(".whl") for f in files or []),
                                              tuple(sorted(canonical_name(d) for d in p.get("dependencies", {}))),
                                              tuple(sorted(((canonical_name(d), _poetry_marker(v)) for d, v in p.get("dependencies", {}).items()),
                                                           key=lambda e: (e[0], e[1] or "")))))
        except (KeyError, TypeError, AttributeError) as e:
            return _fail("poetry_lock", rel, f"malformed [[package]] entry: {e!r}")
    return res
