"""Python project discovery inside an immutable snapshot.

Reads the inventory (paths) and manifests (TOML/INI text) only. It never imports project code and never runs setup.py.
A repository can hold several projects; each has a distribution name, a source root and import packages, and these are
different things (distribution `acme-models` is imported as `acme_models`).
"""
import configparser
import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from ...ingestion.classify import classify
from ..common import ManifestError, SnapshotFS, canonical_name
from .pyproject import parse_pyproject

REQ_DIRS = {"requirements", "reqs", "requirement", "deps"}
NOT_PACKAGES = {"tests", "test", "testing", "docs", "doc", "examples", "example", "scripts", "build", "dist", "benchmarks",
                "bench", "tools", "venv", "env", "node_modules", "site-packages", "__pycache__"}
NOT_MODULES = {"setup.py", "conftest.py", "noxfile.py", "manage.py", "fabfile.py", "tasks.py"}
NATIVE_EXT = (".c", ".cc", ".cpp", ".cxx", ".pyx", ".rs", ".go", ".f90")


@dataclass
class PythonProject:
    rel_path: str                           # '.' or 'services/api'
    name: str                               # canonical distribution name (or directory name for requirement-only projects)
    display_name: str
    origin: str                             # pyproject | setup_cfg | setup_py | requirements_only
    version: str | None = None
    requires_python: str | None = None
    manifests: dict[str, list[str]] = field(default_factory=dict)   # kind -> snapshot-relative paths
    source_roots: list[str] = field(default_factory=list)
    import_packages: list[str] = field(default_factory=list)
    has_tests: bool = False
    pure_python: bool | None = None
    notes: list[str] = field(default_factory=list)
    build_backend: str | None = None


@dataclass
class Discovery:
    projects: list[PythonProject]
    unassigned: list[str]                   # manifest paths that belong to no project, with the reason in `notes`
    notes: list[str] = field(default_factory=list)


def _dir(p: str) -> str:
    d = posixpath.dirname(p)
    return d or "."


def _under(d: str, base: str) -> str | None:
    """Relative path of d under base, or None when d is not inside base."""
    if base == ".":
        return "" if d == "." else d
    if d == base:
        return ""
    return d[len(base) + 1:] if d.startswith(base + "/") else None


def _config_roots(meta_tool: dict, project_dir: str) -> list[str]:
    roots: list[str] = []
    st = meta_tool.get("setuptools", {})
    where = st.get("packages", {}).get("find", {}).get("where") if isinstance(st.get("packages"), dict) else None
    roots += list(where or [])
    pd = st.get("package-dir", {})
    if isinstance(pd, dict) and "" in pd:
        roots.append(pd[""])
    hatch = meta_tool.get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {}).get("packages", [])
    roots += [posixpath.dirname(h) or "." for h in hatch if isinstance(h, str)]
    for pk in meta_tool.get("poetry", {}).get("packages", []) or []:
        if isinstance(pk, dict):
            roots.append(pk.get("from", "."))
    out = []
    for r in roots:
        n = posixpath.normpath(posixpath.join(project_dir, r)) if project_dir != "." else posixpath.normpath(r)
        if not n.startswith("..") and n not in out:
            out.append(n)
    return out


def _packages_in(root: str, paths: set[str]) -> list[str]:
    names: set[str] = set()
    prefix = "" if root == "." else root + "/"
    for p in paths:
        if not p.startswith(prefix) or not p.endswith(".py"):
            continue
        rest = p[len(prefix):].split("/")
        if len(rest) == 1:
            if rest[0] not in NOT_MODULES:
                names.add(rest[0][:-3])
        elif rest[0] not in NOT_PACKAGES and not rest[0].startswith(".") and rest[0] != "__pycache__":
            names.add(rest[0])
    return sorted(names)


def discover_python(snapshot: Path, inventory: dict) -> Discovery:
    fs = SnapshotFS(snapshot)
    files = [e["path"] for e in inventory["entries"] if e["kind"] in ("file", "lfs_pointer")]
    usable = [p for p in files if classify(p).role != "ignored" and "VENDORED" not in classify(p).tags]
    pathset = set(usable)
    notes: list[str] = []
    projects: dict[str, PythonProject] = {}
    tools: dict[str, dict] = {}

    # 1. projects declared by a manifest that names them
    for p in sorted(usable):
        base = posixpath.basename(p)
        d = _dir(p)
        if base == "pyproject.toml":
            res = parse_pyproject(fs, p)
            if res.status in ("FAILED", "TOO_LARGE"):
                projects[d] = PythonProject(d, canonical_name(posixpath.basename(d) if d != "." else "project"),
                                            posixpath.basename(d) if d != "." else "project", "pyproject",
                                            notes=[f"pyproject.toml could not be read: {res.diagnostics[0].message}"])
            elif res.meta.get("name") or res.meta.get("poetry") or res.status != "UNSUPPORTED":
                nm = res.meta.get("name") or (posixpath.basename(d) if d != "." else "project")
                prj = PythonProject(d, canonical_name(nm), nm, "pyproject", res.meta.get("version"), res.meta.get("requires_python"),
                                    build_backend=res.meta.get("build_backend"))
                prj.notes.append("version is dynamic" if "version" in (res.meta.get("dynamic") or []) else "")
                prj.notes = [n for n in prj.notes if n]
                tools[d] = _tool_table(fs, p)
                projects[d] = prj
        elif base == "setup.cfg" and d not in projects:
            cp = configparser.ConfigParser(interpolation=None)
            try:
                cp.read_string(fs.read_text(p))
            except (configparser.Error, ManifestError):
                continue
            nm = cp.get("metadata", "name", fallback=None)
            if nm:
                projects[d] = PythonProject(d, canonical_name(nm), nm, "setup_cfg", cp.get("metadata", "version", fallback=None),
                                            cp.get("options", "python_requires", fallback=None))
        elif base == "setup.py" and d not in projects:
            from .setup_py import parse_setup_py
            sp = parse_setup_py(fs, p)
            nm = sp.meta.get("name") or (posixpath.basename(d) if d != "." else "project")
            projects[d] = PythonProject(d, canonical_name(nm), nm, "setup_py", sp.meta.get("version") if isinstance(sp.meta.get("version"), str) else None,
                                        sp.meta.get("requires_python") if isinstance(sp.meta.get("requires_python"), str) else None,
                                        notes=["setup.py is read statically (parsed to an AST, never executed): only literal arguments are used"])

    # 2. manifests, assigned to the nearest enclosing project or to a requirement-only project
    unassigned: list[str] = []
    kinds = {"requirements": "requirements", "constraints": "constraints", "uv_lock": "uv_lock", "poetry_lock": "poetry_lock",
             "pyproject": "pyproject", "setup_cfg": "setup_cfg", "setup_py": "setup_py"}
    for p in sorted(usable):
        c = classify(p)
        if c.role != "manifest" or c.manifest_kind not in kinds:
            continue
        d = _dir(p)
        owner = None
        for pd in sorted(projects, key=len, reverse=True):
            sub = _under(d, pd)
            if sub is not None and (sub == "" or sub.split("/")[0] in REQ_DIRS):
                owner = pd
                break
        if owner is None:
            # A project at the repository root does not own every directory; one deeper does own what is under it.
            enclosed = any(pd != "." and _under(d, pd) not in (None, "") for pd in projects)
            if enclosed or posixpath.basename(d) in NOT_PACKAGES:
                unassigned.append(p)
                notes.append(f"{p} sits inside another project but not at its root or in a requirements/ directory, or is in a docs/tests-style directory; not attributed to any project")
                continue
            if c.manifest_kind in ("setup_cfg", "setup_py", "pyproject"):
                continue
            nm = posixpath.basename(d) if d != "." else "project"
            projects[d] = PythonProject(d, canonical_name(nm), nm, "requirements_only",
                                        notes=["no pyproject.toml: the distribution name is taken from the directory name"])
            owner = d
        projects[owner].manifests.setdefault(kinds[c.manifest_kind], []).append(p)

    # 3. layout: source roots, import packages, tests, native code
    def owner_of(q: str) -> str | None:
        return next((pd for pd in sorted(projects, key=len, reverse=True) if _under(_dir(q), pd) is not None), None)

    mine: dict[str, set[str]] = {d: set() for d in projects}
    for q in pathset:
        o = owner_of(q)
        if o is not None:
            mine[o].add(q)
    for d, prj in sorted(projects.items()):
        own = mine[d]
        roots = [r for r in _config_roots(tools.get(d, {}), d) if any(q.startswith(r + "/") or r == "." for q in own)]
        if not roots:
            src = "src" if d == "." else f"{d}/src"
            roots = [src] if any(q.startswith(src + "/") and q.endswith(".py") for q in own) else [d]
        prj.source_roots = roots
        prj.import_packages = sorted({n for r in roots for n in _packages_in(r, own)})
        prj.has_tests = any("TEST" in classify(q).tags for q in own)
        prj.pure_python = None if not own else not any(q.endswith(NATIVE_EXT) for q in own)
        if prj.build_backend and any(k in prj.build_backend for k in ("maturin", "scikit_build", "mesonpy", "cython")):
            prj.pure_python = False
        prj.notes = list(dict.fromkeys(prj.notes))
    return Discovery(sorted(projects.values(), key=lambda x: x.rel_path), sorted(unassigned), notes)


def _tool_table(fs: SnapshotFS, rel: str) -> dict:
    import tomllib
    try:
        return tomllib.loads(fs.read_text(rel)).get("tool", {})
    except (tomllib.TOMLDecodeError, ManifestError):
        return {}
