"""Native resolution for Python projects. No home-made solver: a committed lockfile is authoritative, otherwise the pinned
uv resolves inside the fetch zone at a recorded cutoff. Every outcome carries its provenance; a failure is never an
empty world.

Wheels only. A package that would need an sdist build is classified needs_build and nothing is built or executed.
"""
import re
from dataclasses import dataclass, field

from packaging.markers import InvalidMarker, Marker
from packaging.requirements import Requirement

from ..core.errors import ErrorCode
from ..core.hashing import content_hash
from ..parsers.common import Dependency, SnapshotFS, canonical_name
from ..parsers.python.discover import PythonProject
from ..parsers.python.locks import LockedPackage, parse_poetry_lock, parse_uv_lock
from ..parsers.python.pyproject import parse_pyproject
from ..parsers.python.requirements import parse_requirements
from ..parsers.python.setup_cfg import parse_setup_cfg
from ..parsers.python.setup_py import parse_setup_py
from ..sandbox.client import SandboxClient
from .pinned import PinnedRequirement, render_lock

PUBLIC_INDEX_HOSTS = ("pypi.org", "files.pythonhosted.org")
TARGET = {"python_version": "3.12", "python_full_version": "3.12.15", "sys_platform": "linux", "platform_system": "Linux",
          "os_name": "posix", "platform_machine": "x86_64", "implementation_name": "cpython",
          "platform_python_implementation": "CPython", "implementation_version": "3.12.15", "extra": ""}
PLATFORM = "x86_64-unknown-linux-gnu"
LOGIC_VERSION = "6"      # bump whenever which-files-count or lock-reading rules change: part of every cache key
RESOLVER_FLAGS = ("--no-build", "--generate-hashes", "--no-config", f"--python-platform={PLATFORM}")


@dataclass
class ResolveOutcome:
    status: str                                    # OK | OK_PARTIAL | FAILED
    source: str                                    # lockfile | resolver
    pinned: list[PinnedRequirement] = field(default_factory=list)
    private: list[str] = field(default_factory=list)          # package names served by a non-public index; never fetched
    failure: dict | None = None                    # {code, reason, detail}
    provenance: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def lock_text(self) -> str:
        return render_lock(self.pinned)


def _failed(source: str, reason: str, detail: str, prov: dict, code: ErrorCode = ErrorCode.RESOLUTION_FAILED, **extra) -> ResolveOutcome:
    return ResolveOutcome("FAILED", source, failure={"code": code.value, "reason": reason, "detail": detail, **extra}, provenance=prov)


def marker_applies(marker: str | None) -> bool:
    """Does a PEP 508 marker hold in the target environment (CPython 3.12, linux, x86_64)? Unreadable markers say yes."""
    if not marker:
        return True
    try:
        return Marker(marker).evaluate(TARGET)
    except InvalidMarker:
        return True


def is_public(url: str | None) -> bool:
    if not url:
        return True
    m = re.match(r"^https?://([^/:]+)", url)
    return bool(m) and m.group(1).lower() in PUBLIC_INDEX_HOSTS


NON_RUNTIME = re.compile(r"(test|dev|doc|lint|ci|typing|mypy|coverage|bench|build|release|tox|nox|style|format|example)", re.I)


def runtime_requirement_files(project: PythonProject) -> list[str]:
    """requirements-dev.txt, requirements-test.txt and friends are not part of the runtime world."""
    return [p for p in project.manifests.get("requirements", []) if not NON_RUNTIME.search(p.rsplit("/", 1)[-1])]


def _states_its_dependencies(res) -> bool:
    """A pyproject with a [project] or [tool.poetry] table is the authority for the project's runtime dependencies."""
    return bool(res.meta.get("name") or res.meta.get("poetry") or res.dependencies)


def _is_hash_pinned(res) -> bool:
    return bool(res.dependencies) and all(d.specifier.startswith("==") and d.kind == "registry" and d.hashes for d in res.dependencies)


def _declared(project: PythonProject, fs: SnapshotFS) -> tuple[list[Dependency], list[Dependency], dict, list[str]]:
    """Main-group dependencies that apply to the target, constraints, index declarations, parse problems."""
    deps: list[Dependency] = []
    cons: list[Dependency] = []
    meta: dict = {}
    problems: list[str] = []
    authoritative = False
    for kind in ("pyproject", "setup_cfg", "setup_py", "requirements", "constraints"):
        if authoritative and kind not in ("pyproject", "setup_cfg", "setup_py"):      # requirements files next to a described project are dev/test pins
            continue
        paths = project.manifests.get(kind, [])
        if kind == "requirements":
            # a fully hash-pinned file is a LOCK (output of a resolution), not a declaration: it never feeds a new resolution
            paths = [p for p in runtime_requirement_files(project) if not _is_hash_pinned(parse_requirements(fs, p))]
        for path in paths:
            r = parse_pyproject(fs, path) if kind == "pyproject" else parse_setup_cfg(fs, path) if kind == "setup_cfg" else parse_setup_py(fs, path) if kind == "setup_py" else parse_requirements(fs, path)
            if r.status in ("FAILED", "TOO_LARGE"):
                problems.append(f"{path}: {r.diagnostics[0].message}")
                continue
            if r.status == "PARTIAL":
                problems += [f"{path}: {d.message}" for d in r.diagnostics]
            meta.setdefault("used_files", []).append(path)
            authoritative = authoritative or (kind in ("pyproject", "setup_cfg", "setup_py") and r.status != "UNSUPPORTED" and _states_its_dependencies(r))
            deps += [d for d in r.dependencies if d.group == "main" and marker_applies(d.marker)]
            cons += [d for d in r.constraints if marker_applies(d.marker)]
            for k in ("index_urls", "extra_index_urls", "find_links"):
                if r.meta.get(k):
                    meta.setdefault(k, []).extend(r.meta[k])
    return deps, cons, meta, problems


def _requirement_line(d: Dependency) -> str:
    extras = f"[{','.join(d.extras)}]" if d.extras else ""
    if d.kind != "registry":
        return f"{d.display}{extras} @ {d.source_ref}"
    return f"{d.display}{extras}{d.specifier}" + (f" ; {d.marker}" if d.marker else "")


# ------------------------------------------------------------------------------------------------ lockfile path

def _from_lock(project: PythonProject, fs: SnapshotFS, prov: dict) -> ResolveOutcome | None:
    for kind, parse in (("uv_lock", parse_uv_lock), ("poetry_lock", parse_poetry_lock)):
        paths = project.manifests.get(kind, [])
        if not paths:
            continue
        path = paths[0]
        lock = parse(fs, path)
        prov = {**prov, "lockfile": {"kind": kind, "path": path, "sha256": content_hash(fs.read_bytes(path)) if lock.status != "TOO_LARGE" else None,
                                     **lock.meta}}
        if lock.status != "OK":
            return _failed("lockfile", f"lock_{lock.status.lower()}", lock.error or "", prov,
                           ErrorCode.MANIFEST_TOO_LARGE if lock.status == "TOO_LARGE" else ErrorCode.MANIFEST_PARSE_FAILED)
        by = {p.name: p for p in lock.packages}
        deps, _cons, dmeta, _problems = _declared(project, fs)
        prov = {**prov, "declared_from": dmeta.get("used_files", [])}
        if kind == "uv_lock":
            roots = [p for p in lock.packages if p.source_kind in ("virtual", "editable", "directory") and
                     (p.source_ref in (".", project.rel_path) or p.name == project.name)]
            start = [(n, m) for r in roots for n, m in r.dep_edges]
        else:
            start = [(d.name, d.marker) for d in deps]
        missing = sorted({n for n, m in start if n not in by and marker_applies(m)} | {d.name for d in deps if d.name not in by})
        if missing:
            return _failed("lockfile", "lock_missing_declared", f"declared but not in the lock: {', '.join(missing)}", prov)
        reach: dict[str, LockedPackage] = {}
        todo = [n for n, m in start if marker_applies(m)]
        while todo:
            n = todo.pop()
            if n in reach or n not in by:
                continue
            reach[n] = by[n]
            todo += [d for d, m in by[n].dep_edges if marker_applies(m)]
        pinned: list[PinnedRequirement] = []
        private: list[str] = []
        needs_build, non_registry = [], []
        for n, p in sorted(reach.items()):
            if p.source_kind in ("virtual", "editable", "directory") and p.name == project.name:
                continue
            if p.source_kind != "registry":
                non_registry.append(f"{n} ({p.source_kind})")
            elif not is_public(p.source_ref):
                private.append(n)
            elif not p.wheel_hashes:
                needs_build.append(n)
            else:
                pinned.append(PinnedRequirement(n, p.display, p.version, tuple(sorted(p.wheel_hashes))))
        if non_registry:
            return _failed("lockfile", "non_registry_source", f"packages not served by a registry: {', '.join(non_registry)}", prov)
        if needs_build:
            return _failed("lockfile", "needs_build", f"no wheel is published for: {', '.join(needs_build)}; building is not allowed",
                           prov, packages=needs_build)
        if not pinned and not private:
            return _failed("lockfile", "empty_world", "the lock contains no installable packages for the target", prov)
        status = "OK_PARTIAL" if private else "OK"
        warn = [f"{n} comes from a non-public index and is PRIVATE: it is not fetched" for n in private]
        return ResolveOutcome(status, "lockfile", pinned, private, None, prov, warn)
    return None


def _from_pinned_requirements(project: PythonProject, fs: SnapshotFS, prov: dict) -> ResolveOutcome | None:
    """A fully hash-pinned requirements file is a lockfile in practice (pip-compile --generate-hashes output)."""
    cands = []
    for path in runtime_requirement_files(project):
        r = parse_requirements(fs, path)
        if r.status == "OK" and _is_hash_pinned(r):
            cands.append((path, r))
    if not cands:
        return None
    if len(cands) > 1:
        return _failed("lockfile", "ambiguous_lock", f"more than one hash-pinned requirements file: {', '.join(c[0] for c in cands)}", prov)
    path, r = cands[0]
    prov = {**prov, "lockfile": {"kind": "requirements_lock", "path": path, "sha256": content_hash(fs.read_bytes(path))}}
    pinned = [PinnedRequirement(d.name, d.display, d.specifier[2:], tuple(sorted(set(d.hashes)))) for d in r.dependencies
              if marker_applies(d.marker)]
    if not pinned:
        return _failed("lockfile", "empty_world", "the pinned requirements apply to no package on the target", prov)
    return ResolveOutcome("OK", "lockfile", sorted(pinned, key=lambda x: x.name), [], None, prov)


# ------------------------------------------------------------------------------------------------ uv path

def classify_uv_failure(stderr: str) -> tuple[str, ErrorCode]:
    low = stderr.lower()
    if "building" in low and "disabled" in low or "no-build" in low or "source distribution" in low:
        return "needs_build", ErrorCode.RESOLUTION_FAILED
    if "no solution found" in low or "no matching" in low or "not found in the package registry" in low or "cannot be satisfied" in low:
        return "unsatisfiable", ErrorCode.RESOLUTION_FAILED
    if "error sending request" in low or "dns error" in low or "connection" in low or "timed out" in low:
        return "network", ErrorCode.FETCH_FAILED
    return "resolver_error", ErrorCode.RESOLUTION_FAILED


def parse_compiled(text: str) -> list[PinnedRequirement]:
    from .pinned import parse_pinned_lock
    return parse_pinned_lock(text)


def _from_uv(sbx: SandboxClient, image: str, project: PythonProject, fs: SnapshotFS, cutoff: str, prov: dict, *,
             index_url: str = "https://pypi.org/simple", no_index: bool = False, find_links: list[str] | None = None,
             mounts: dict | None = None, probe_paths: list[str] | None = None, extra_constraints: list[str] | None = None,
             drop: set[str] | None = None) -> ResolveOutcome:
    """`drop` removes packages that must not be installed (the artifact under test, which is mounted as source) and
    `extra_constraints` adds requirement-style constraints (remediation): both are explicit and recorded in the provenance."""
    deps, cons, meta, problems = _declared(project, fs)
    deps = [d for d in deps if d.name not in (drop or set())]
    if problems:
        return _failed("resolver", "manifest_problem", "; ".join(problems)[:600], prov, ErrorCode.MANIFEST_PARSE_FAILED)
    declared = [*meta.get("index_urls", []), *meta.get("extra_index_urls", [])]
    custom = [(i["url"] if isinstance(i, dict) else i) for i in declared]
    custom = [u for u in custom if not is_public(u)]
    if custom or meta.get("find_links"):
        return _failed("resolver", "private_index_without_lock",
                       "the project declares a non-public index or find-links; without a lockfile Faultline will not guess "
                       "which packages come from where, and will not query the public index for them", prov, indexes=sorted(custom))
    if not deps and project.origin == "setup_py":
        return _failed("resolver", "setup_py_not_executed", "no literal dependencies could be read from setup.py (it is parsed, never executed); "
                       "provide a lockfile, a pyproject.toml or a setup.cfg", prov)
    if not deps:
        return _failed("resolver", "no_declared_dependencies", "no resolvable dependencies were declared for the main group", prov)
    prov = {**prov, "extra_constraints": list(extra_constraints or []), "dropped": sorted(drop or []), "inputs": sorted(_requirement_line(d) for d in deps), "declared_from": meta.get("used_files", [])}
    spec = {"image": image, "zone": "fetch", "script": "resolve_uv.py", "mounts": mounts or {},
            "args": {"requirements": [_requirement_line(d) for d in deps], "constraints": [*(_requirement_line(c) for c in cons), *(extra_constraints or [])],
                     "python_version": "3.12", "exclude_newer": cutoff, "index_url": index_url, "no_index": no_index,
                     "find_links": find_links or [], "probe_paths": probe_paths or []},
            "limits": {"timeout_s": 300, "memory_mb": 1024}}
    r = sbx.submit(spec)
    data = r.get("data") or {}
    prov = {**prov, "resolver": {"name": "uv", "version": data.get("uv_version"), "flags": data.get("flags")}, "probes": data.get("probes", {})}
    if r["failure_class"] != "NONE":
        return _failed("resolver", "sandbox_failure", r.get("error") or r["failure_class"], prov, ErrorCode.SANDBOX_FAILED)
    if data.get("returncode") != 0:
        reason, code = classify_uv_failure(data.get("stderr_tail", ""))
        found = re.findall(r"Because ([A-Za-z0-9][A-Za-z0-9._-]*)==|for `([A-Za-z0-9][A-Za-z0-9._-]*)`", data.get("stderr_tail", ""))
        names = sorted({canonical_name(a or b) for a, b in found})[:5]
        return _failed("resolver", reason, data.get("stderr_tail", "")[-500:], prov, code, packages=names)
    try:
        pinned = parse_compiled(data["output"])
    except Exception as e:  # noqa: BLE001 - any parse problem is a failure, never an empty world
        return _failed("resolver", "unreadable_output", str(e), prov, ErrorCode.RESOLUTION_FAILED)
    return ResolveOutcome("OK", "resolver", pinned, [], None, prov)


def resolve_project(sbx: SandboxClient, image: str, fs: SnapshotFS, project: PythonProject, *, cutoff: str, **uv_kw) -> ResolveOutcome:
    """Lockfile first; otherwise pinned uv at `cutoff` (an RFC 3339 timestamp, normally the snapshot's commit time)."""
    prov = {"project": project.rel_path, "target": {"python": "3.12", "platform": PLATFORM, "markers": TARGET}, "cutoff": cutoff,
            "flags": list(RESOLVER_FLAGS), "index": "https://pypi.org/simple"}
    out = _from_lock(project, fs, prov)
    if out is not None:
        return out
    out = _from_pinned_requirements(project, fs, prov)
    if out is not None:
        return out
    if not any(project.manifests.get(k) for k in ("pyproject", "setup_cfg", "setup_py", "requirements")):
        return _failed("resolver", "no_manifest", "no dependency manifest was found for this project", prov)
    return _from_uv(sbx, image, project, fs, cutoff, prov, **uv_kw)


def canonical_requirement_name(text: str) -> str:
    return canonical_name(Requirement(text).name)
