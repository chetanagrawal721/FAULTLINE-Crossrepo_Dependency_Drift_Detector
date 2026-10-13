"""Canonical worlds for projects: resolution cache keys, project and manifest records, and deduplication.

Two projects that resolve to the same package set share ONE resolved_world row (its hash is the identity) and each gets
its own project_world link. The resolution cache key covers every input that can change an outcome, so changing any one of
them (a manifest, the cutoff, the platform, the resolver version, the index policy or the flags) resolves again.
"""
import json
import sqlite3
import time
import tomllib
from dataclasses import dataclass
from typing import Any

from ..core.config import repo_root
from ..core.enums import Ecosystem
from ..core.errors import ErrorCode
from ..core.hashing import content_hash, object_hash
from ..parsers.common import SnapshotFS, to_jsonable
from ..parsers.python.discover import PythonProject
from ..parsers.python.locks import parse_poetry_lock, parse_uv_lock
from ..parsers.python.pyproject import parse_pyproject
from ..parsers.python.requirements import parse_requirements
from ..parsers.python.setup_cfg import parse_setup_cfg
from ..parsers.python.setup_py import parse_setup_py
from ..resolvers.pinned import PinnedRequirement
from ..resolvers.python import LOGIC_VERSION, PLATFORM, RESOLVER_FLAGS, ResolveOutcome, resolve_project


def _uv_version() -> str:
    try:
        return "uv " + tomllib.loads((repo_root() / "versions.toml").read_text(encoding="utf-8"))["tools"]["uv"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "uv unknown"


@dataclass(frozen=True)
class ResolutionContext:
    """Everything outside the manifests that can change a resolution."""
    cutoff: str                                   # RFC 3339; normally the snapshot's commit time
    platform: str = PLATFORM
    python: str = "3.12"
    resolver_version: str = ""
    index: str = "https://pypi.org/simple"
    flags: tuple[str, ...] = RESOLVER_FLAGS

    def __post_init__(self) -> None:
        if not self.resolver_version:
            object.__setattr__(self, "resolver_version", _uv_version())


@dataclass
class ProjectWorld:
    project_id: str
    status: str                                   # OK | OK_PARTIAL | FAILED
    source: str
    world_hash: str | None
    outcome: ResolveOutcome
    cache_hit: bool


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def manifest_digests(fs: SnapshotFS, project: PythonProject) -> dict[str, str]:
    return {p: content_hash(fs.read_bytes(p)) for paths in project.manifests.values() for p in paths}


def cache_key(fs: SnapshotFS, project: PythonProject, ctx: ResolutionContext) -> str:
    return "rc_" + object_hash({"eco": "pypi", "project": project.rel_path, "name": project.name,
                                "manifests": manifest_digests(fs, project), "cutoff": ctx.cutoff, "platform": ctx.platform,
                                "python": ctx.python, "resolver": ctx.resolver_version, "index": ctx.index,
                                "flags": list(ctx.flags), "logic": LOGIC_VERSION})


# ------------------------------------------------------------------------------------------------ outcome <-> json

def outcome_to_json(o: ResolveOutcome) -> str:
    return json.dumps({"status": o.status, "source": o.source, "private": o.private, "failure": o.failure, "provenance": o.provenance,
                       "warnings": o.warnings, "pinned": [[p.name, p.display_name, p.version, list(p.hashes)] for p in o.pinned]},
                      sort_keys=True)


def outcome_from_json(text: str) -> ResolveOutcome:
    d = json.loads(text)
    return ResolveOutcome(d["status"], d["source"], [PinnedRequirement(n, dn, v, tuple(h)) for n, dn, v, h in d["pinned"]],
                          d["private"], d["failure"], d["provenance"], d["warnings"])


# ------------------------------------------------------------------------------------------------ project records

def project_id_for(snapshot_id: str, rel_path: str) -> str:
    return "prj_" + object_hash([snapshot_id, rel_path, "pypi"])[:24]


PARSERS = {"setup_py": parse_setup_py, "setup_cfg": parse_setup_cfg, "requirements": parse_requirements, "constraints": parse_requirements, "pyproject": parse_pyproject,
           "uv_lock": parse_uv_lock, "poetry_lock": parse_poetry_lock}


def record_project(conn: sqlite3.Connection, snapshot_id: str, fs: SnapshotFS, project: PythonProject) -> str:
    """Insert (or find) the project row and one manifest row per manifest, with parse status. Idempotent."""
    pid = project_id_for(snapshot_id, project.rel_path)
    runtime = {"name": "cpython", "version": "3.12", "source": "faultline default"}
    conn.execute("INSERT OR IGNORE INTO project(id, snapshot_id, rel_path, ecosystem, published_name, runtime_json, is_pure_python, has_tests) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (pid, snapshot_id, project.rel_path, Ecosystem.PYPI.value, project.name if project.origin != "requirements_only" else None,
                  json.dumps(runtime), None if project.pure_python is None else int(project.pure_python), int(project.has_tests)))
    conn.execute("UPDATE project SET origin=?, display_name=?, notes_json=?, layout_json=? WHERE id=?",
                 (project.origin, project.display_name, json.dumps(project.notes),
                  json.dumps({"source_roots": project.source_roots, "import_packages": project.import_packages,
                              "version": project.version, "requires_python": project.requires_python}, sort_keys=True), pid))
    for kind, paths in sorted(project.manifests.items()):
        for path in paths:
            if conn.execute("SELECT 1 FROM manifest WHERE project_id=? AND path=?", (pid, path)).fetchone():
                continue
            parse = PARSERS.get(kind)
            parsed: Any = None
            status, err = "UNSUPPORTED", None
            if parse:
                parsed = parse(fs, path)
                status = parsed.status
                err = (parsed.error if hasattr(parsed, "error") else
                       "; ".join(d.message for d in parsed.diagnostics[:3])) or None
            conn.execute("INSERT INTO manifest(id, project_id, path, kind, content_hash, parsed_json, parse_status, parse_error) "
                         "VALUES (?,?,?,?,?,?,?,?)",
                         ("mf_" + object_hash([pid, path])[:24], pid, path, kind, content_hash(fs.read_bytes(path)),
                          json.dumps(to_jsonable(parsed), sort_keys=True, default=str) if parsed is not None else None, status, err))
    return pid


def record_visible(conn: sqlite3.Connection, world_hash: str, info: dict) -> None:
    """Store which version of each package the built world really exposes to an importer (Python: one flat site-packages)."""
    from ..parsers.common import canonical_name
    in_world = {r["locator"] for r in conn.execute("SELECT locator FROM world_entry WHERE world_hash=?", (world_hash,))}
    for name, version in info["info"]["packages"]:
        loc = canonical_name(name)
        if loc in in_world:
            conn.execute("INSERT OR REPLACE INTO world_visible(world_hash, locator, importer, visible_version, source) VALUES (?,?,?,?,?)",
                         (world_hash, loc, "", version, "built_world"))


# ------------------------------------------------------------------------------------------------ world per project

def ensure_project_world(conn: sqlite3.Connection, sbx: Any, image: str, snapshot_id: str, fs: SnapshotFS, project: PythonProject,
                         ctx: ResolutionContext, *, resolver=resolve_project, builder: Any = None, build: bool = False) -> ProjectWorld:
    """Resolve (or reuse a cached resolution), materialize the world, and link it to the project."""
    from .builder import WorldBuilder, WorldBuildError

    pid = record_project(conn, snapshot_id, fs, project)
    key = cache_key(fs, project, ctx)
    row = conn.execute("SELECT * FROM resolution_cache WHERE cache_key=?", (key,)).fetchone()
    hit = row is not None
    if hit:
        outcome, world_hash = outcome_from_json(row["outcome_json"]), row["world_hash"]
    else:
        outcome = resolver(sbx, image, fs, project, cutoff=ctx.cutoff)
        world_hash = None
        if outcome.status in ("OK", "OK_PARTIAL"):
            builder = builder or WorldBuilder(sbx, image, conn)
            try:
                world = builder.materialize(outcome.lock_text)
                world_hash = world.world_hash
                if build and outcome.status == "OK":                 # a world with PRIVATE packages is incomplete: never built
                    built = builder.build(world, outcome.lock_text)
                    if built.status == "FAILED":
                        raise WorldBuildError("the world could not be built offline", details={"reason": "build_failed", "tail": built.reason})
                    record_visible(conn, world_hash, builder.info(world))
            except WorldBuildError as e:
                outcome = ResolveOutcome("FAILED", outcome.source, [], outcome.private,
                                         {"code": e.code.value, "reason": e.details.get("reason", "world_build_failed"), "detail": e.message},
                                         outcome.provenance, outcome.warnings)
        transient = outcome.failure and outcome.failure.get("code") in (ErrorCode.FETCH_FAILED.value, ErrorCode.SANDBOX_FAILED.value)
        if not transient:
            conn.execute("INSERT OR REPLACE INTO resolution_cache(cache_key, ecosystem, status, outcome_json, world_hash, created_at) "
                         "VALUES (?,?,?,?,?,?)", (key, "pypi", outcome.status, outcome_to_json(outcome), world_hash, _now()))
    args = {"cache_key": key, "flags": list(ctx.flags), "platform": ctx.platform, "index": ctx.index, "python": ctx.python,
            "resolver_version": ctx.resolver_version}
    conn.execute("INSERT OR REPLACE INTO project_world(id, project_id, world_hash, source, resolver, resolver_args_json, resolved_at, status, failure_json) "
                 "VALUES (?,?,?,?,?,?,?,?,?)",
                 ("pw_" + object_hash([pid, ctx.cutoff])[:24], pid, world_hash, outcome.source,
                  ctx.resolver_version if outcome.source == "resolver" else (outcome.provenance.get("lockfile") or {}).get("kind"),
                  json.dumps(args, sort_keys=True), ctx.cutoff, outcome.status,
                  json.dumps(outcome.failure, sort_keys=True) if outcome.failure else None))
    return ProjectWorld(pid, outcome.status, outcome.source, world_hash, outcome, hit)


# ------------------------------------------------------------------------------------------------ npm (inventory worlds)

def ensure_npm_world(conn: sqlite3.Connection, snapshot_id: str, fs: SnapshotFS, project) -> ProjectWorld:
    """Record an npm project and its lockfile world. No process runs: the lockfile is read as data."""
    from ..resolvers.npm import INVENTORY_ENV, resolve_npm_project
    from ..storage import worlds as world_store

    pid = "prj_" + object_hash([snapshot_id, project.rel_path, "npm"])[:24]
    conn.execute("INSERT OR IGNORE INTO project(id, snapshot_id, rel_path, ecosystem, published_name, runtime_json, is_pure_python, has_tests) "
                 "VALUES (?,?,?,?,?,?,?,?)", (pid, snapshot_id, project.rel_path, "npm", project.name, None, None, 0))
    conn.execute("UPDATE project SET origin='package_json', display_name=?, notes_json=?, layout_json=? WHERE id=?",
                 (project.name, json.dumps(project.notes), json.dumps({"workspaces": project.workspace_dirs}, sort_keys=True), pid))
    out = resolve_npm_project(fs, project)
    for kind, paths in project.manifests.items():
        for path in paths:
            if conn.execute("SELECT 1 FROM manifest WHERE project_id=? AND path=?", (pid, path)).fetchone():
                continue
            if kind == "package_json":
                parsed, status, err = to_jsonable(project.package_json), project.package_json.status, project.package_json.error
            else:
                lk = out.lock
                parsed = {"lockfile_version": lk.lockfile_version, "instances": len(lk.instances)} if lk else None
                status, err = (lk.status, lk.error) if lk else ("FAILED", None)
            conn.execute("INSERT INTO manifest(id, project_id, path, kind, content_hash, parsed_json, parse_status, parse_error) VALUES (?,?,?,?,?,?,?,?)",
                         ("mf_" + object_hash([pid, path])[:24], pid, path, kind, content_hash(fs.read_bytes(path)),
                          json.dumps(parsed, sort_keys=True, default=str), status, err))
    world_hash = None
    if out.world is not None:
        world_store.save_world(conn, out.world, INVENTORY_ENV)
        world_hash = out.world.world_hash
        locs = {e.locator for e in out.world.entries}
        for r in out.visibility:
            if r.locator in locs and r.importer in locs | {""}:
                conn.execute("INSERT OR REPLACE INTO world_visible(world_hash, locator, importer, visible_version, source) VALUES (?,?,?,?,?)",
                             (world_hash, r.locator, r.importer, r.version or "", "simulated"))
    cutoff = "lockfile"                                       # an npm lockfile world has no resolution time: it is the committed lock
    lock_kind = f"package-lock v{out.lock.lockfile_version}" if out.lock and out.lock.lockfile_version else None
    prov = {"lockfile": {"kind": "package_lock", "path": project.lockfile, "version": out.lock.lockfile_version if out.lock else None,
                         "sha256": content_hash(fs.read_bytes(project.lockfile)) if project.lockfile else None},
            "declared_from": [project.package_json.path]}
    outcome = ResolveOutcome(out.status if out.status == "OK" else "FAILED", "lockfile", [], [], out.failure, prov, out.warnings)
    key = "rc_" + object_hash({"eco": "npm", "project": project.rel_path, "manifests": {p: content_hash(fs.read_bytes(p)) for ps in project.manifests.values() for p in ps}})
    conn.execute("INSERT OR REPLACE INTO resolution_cache(cache_key, ecosystem, status, outcome_json, world_hash, created_at) VALUES (?,?,?,?,?,?)",
                 (key, "npm", outcome.status, outcome_to_json(outcome), world_hash, _now()))
    conn.execute("INSERT OR REPLACE INTO project_world(id, project_id, world_hash, source, resolver, resolver_args_json, resolved_at, status, failure_json) "
                 "VALUES (?,?,?,?,?,?,?,?,?)",
                 ("pw_" + object_hash([pid, cutoff])[:24], pid, world_hash, "lockfile", lock_kind,
                  json.dumps({"cache_key": key, "importers": out.importers, "runtime": "none (inventory only)"}, sort_keys=True), cutoff,
                  outcome.status, json.dumps(out.failure, sort_keys=True) if out.failure else None))
    return ProjectWorld(pid, outcome.status, "lockfile", world_hash, outcome, False)


# ------------------------------------------------------------------------------------------------ maven (declared-dependency inventory)

def ensure_maven_project(conn: sqlite3.Connection, snapshot_id: str, fs: SnapshotFS, project) -> str:
    """Record a Maven project and its declared dependencies. No resolution, no world, and Maven is never run."""
    pom = project.pom
    pid = "prj_" + object_hash([snapshot_id, project.rel_path, "maven"])[:24]
    name = f"{pom.group_id}:{pom.artifact_id}" if pom.artifact_id else None
    conn.execute("INSERT OR IGNORE INTO project(id, snapshot_id, rel_path, ecosystem, published_name, runtime_json, is_pure_python, has_tests) "
                 "VALUES (?,?,?,?,?,?,?,?)", (pid, snapshot_id, project.rel_path, "maven", name, None, None, 0))
    notes = [*project.notes, "Maven resolution is not performed: this is an inventory of declared dependencies, not a resolved world"]
    conn.execute("UPDATE project SET origin='pom', display_name=?, notes_json=?, layout_json=? WHERE id=?",
                 (name, json.dumps(list(dict.fromkeys(notes))),
                  json.dumps({"module_of": project.module_of, "modules": pom.modules, "packaging": pom.packaging, "version": pom.version}, sort_keys=True), pid))
    path = pom.path
    if not conn.execute("SELECT 1 FROM manifest WHERE project_id=? AND path=?", (pid, path)).fetchone():
        conn.execute("INSERT INTO manifest(id, project_id, path, kind, content_hash, parsed_json, parse_status, parse_error) VALUES (?,?,?,?,?,?,?,?)",
                     ("mf_" + object_hash([pid, path])[:24], pid, path, "pom", content_hash(fs.read_bytes(path)),
                      json.dumps(to_jsonable(pom), sort_keys=True, default=str), pom.status,
                      pom.error or "; ".join(d["message"] for d in pom.diagnostics[:3]) or None))
    return pid
