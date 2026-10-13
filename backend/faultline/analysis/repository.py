"""Analyse an ingested repository snapshot: discover projects, resolve and build their worlds, record the results.

Python is analysed here; npm and Maven inventories are added by their own modules (M3.6, M3.7). Nothing from the
repository is executed: manifests are parsed as data, and wheels are installed only inside the sandbox.
"""
import sqlite3
from collections.abc import Callable

from ..core.errors import ErrorCode, FaultlineError, NotFoundError
from ..ingestion.clone import load_inventory, verify_snapshot
from ..parsers.common import SnapshotFS
from ..parsers.maven.pom import discover_maven
from ..parsers.npm.discover import discover_npm
from ..parsers.python.discover import discover_python
from ..sandbox.client import SandboxClient
from ..storage.store import Store
from ..worlds.canonical import ResolutionContext, ensure_maven_project, ensure_npm_world, ensure_project_world


def analyze_repository(conn: sqlite3.Connection, sbx: SandboxClient, image: str, store: Store, repository_id: str, *,
                       build: bool = True, progress: Callable[[float, str], None] | None = None) -> dict:
    repo = conn.execute("SELECT * FROM repository WHERE id=?", (repository_id,)).fetchone()
    if repo is None:
        raise NotFoundError(f"repository {repository_id} not found")
    snap = conn.execute("SELECT * FROM snapshot WHERE repository_id=? AND sha=?", (repository_id, repo["pinned_sha"])).fetchone()
    if snap is None:
        raise FaultlineError("the repository has not been ingested yet", code=ErrorCode.NOT_FOUND)
    path = store.snapshot_dir(snap["store_path"])
    problems = verify_snapshot(path)
    if problems:                                           # never analyse a snapshot that no longer matches its hashes
        raise FaultlineError(f"snapshot failed verification: {problems[:3]}", code=ErrorCode.FETCH_FAILED)
    fs = SnapshotFS(path)
    found = discover_python(path, load_inventory(path))
    ctx = ResolutionContext(cutoff=snap["committed_at"])
    out = []
    for i, prj in enumerate(found.projects):
        if progress:
            progress(i / max(1, len(found.projects)), f"resolving {prj.rel_path}")
        pw = ensure_project_world(conn, sbx, image, snap["id"], fs, prj, ctx, build=build)
        out.append({"project": prj.rel_path, "status": pw.status, "world_hash": pw.world_hash, "cache_hit": pw.cache_hit,
                    "failure": pw.outcome.failure})
    for prj in discover_npm(path, load_inventory(path)):
        nw = ensure_npm_world(conn, snap["id"], fs, prj)
        out.append({"project": prj.rel_path, "ecosystem": "npm", "status": nw.status, "world_hash": nw.world_hash, "cache_hit": False,
                    "failure": nw.outcome.failure})
    for mp in discover_maven(path, load_inventory(path)):
        ensure_maven_project(conn, snap["id"], fs, mp)
        out.append({"project": mp.rel_path, "ecosystem": "maven", "status": "INVENTORY", "world_hash": None, "cache_hit": False,
                    "failure": None})
    return {"snapshot_id": snap["id"], "projects": out, "unassigned": found.unassigned, "notes": found.notes}
