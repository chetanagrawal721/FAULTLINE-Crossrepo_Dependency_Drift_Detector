"""Seeds an analysis project with ingested repository snapshots (as if fetched and analysed), without Docker.

Each repository is a dict of files. The snapshot directory, its inventory and completion marker are written exactly as the
ingestion step writes them, so everything downstream (verification, discovery, relationship scans) reads real files.
"""
import json
import shutil
from pathlib import Path

from faultline.core.hashing import content_hash, object_hash
from faultline.ingestion.clone import COMPLETE, INVENTORY, SnapshotResult, snapshot_key
from faultline.ingestion.service import create_project, persist_snapshot
from faultline.parsers.common import SnapshotFS
from faultline.parsers.python.discover import discover_python
from faultline.storage.store import Store
from faultline.worlds.canonical import record_project

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "repos"


def read_tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
            and "__pycache__" not in p.parts}


def seed_repository(conn, store: Store, analysis_project_id: str, owner: str, name: str, files: dict[str, bytes | str],
                    *, sha: str | None = None, ref: str | None = None) -> tuple[str, str]:
    """Create repository + snapshot rows and the snapshot directory. Returns (repository_id, snapshot_id)."""
    sha = sha or object_hash([owner, name, sorted((k, content_hash(v if isinstance(v, bytes) else v.encode())) for k, v in files.items())])[:40]
    rid = "repo_" + object_hash([analysis_project_id, owner, name])[:24]
    conn.execute("INSERT OR IGNORE INTO repository(id, analysis_project_id, owner, name, requested_ref, default_branch, pinned_sha, "
                 "committed_at, status, created_at) VALUES (?,?,?,?,?, 'main', ?, '2024-10-30T00:00:00Z', 'INGESTED', '2024-10-30T00:00:00Z')",
                 (rid, analysis_project_id, owner, name, ref, sha))
    key = snapshot_key(owner, name, sha)
    dest = store.snapshot_dir(key)
    shutil.rmtree(dest, ignore_errors=True)
    entries = []
    for rel, content in sorted(files.items()):
        data = content if isinstance(content, bytes) else content.encode()
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        entries.append({"path": rel, "kind": "file", "mode": "100644", "blob": "0" * 40, "size": len(data), "sha256": content_hash(data)})
    inv = {"commit": sha, "entries": entries, "truncated": False, "warnings": []}
    (dest / INVENTORY).write_text(json.dumps(inv, sort_keys=True), encoding="utf-8")
    (dest / COMPLETE).write_text(content_hash((dest / INVENTORY).read_bytes()), encoding="utf-8")
    sid = persist_snapshot(conn, rid, SnapshotResult(key, dest, inv, False), sha, "2024-10-30T00:00:00Z")
    return rid, sid


def seed_projects(conn, store: Store, sid: str) -> list[str]:
    """Discover Python projects in a seeded snapshot and record them (no resolution)."""
    snap = conn.execute("SELECT store_path FROM snapshot WHERE id=?", (sid,)).fetchone()
    root = store.snapshot_dir(snap["store_path"])
    inv = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    return [record_project(conn, sid, SnapshotFS(root), p) for p in discover_python(root, inv).projects]


def fixture_repo(subdir: str) -> dict[str, bytes]:
    return read_tree(FIXTURES / subdir)


def new_analysis_project(conn, name: str = "live") -> str:
    return create_project(conn, name)


def seed_world(conn, project_id: str, lock_text: str | None, *, failure: str | None = None, status: str = "OK") -> str | None:
    """Record a resolution outcome for a project exactly as ensure_project_world stores it (no network, no build)."""
    from faultline.resolvers.pinned import parse_pinned_lock
    from faultline.resolvers.python import ResolveOutcome
    from faultline.worlds.canonical import outcome_to_json
    cutoff = "2024-10-30T00:00:00Z"
    key = "rc_" + object_hash([project_id, lock_text, failure])[:24]
    if failure:
        out = ResolveOutcome("FAILED", "resolver", failure={"code": "RESOLUTION_FAILED", "reason": failure, "detail": failure}, provenance={})
        conn.execute("INSERT OR REPLACE INTO resolution_cache(cache_key, ecosystem, status, outcome_json, world_hash, created_at) VALUES (?,?,?,?,NULL,?)",
                     (key, "pypi", "FAILED", outcome_to_json(out), cutoff))
        wh = None
    else:
        out = ResolveOutcome(status, "lockfile", parse_pinned_lock(lock_text), [], None, {"cutoff": cutoff})
        wh = "w_" + object_hash(lock_text)[:40]
        conn.execute("INSERT OR IGNORE INTO env_profile(id, image_ref, arch, locale, tz, env_json, seed) VALUES ('ep_x','i','a','l','t','{}',0)")
        conn.execute("INSERT OR IGNORE INTO resolved_world(world_hash, ecosystem, runtime_json, env_profile_id, kind) VALUES (?,?,?,?,?)",
                     (wh, "pypi", "{}", "ep_x", "reference"))
        conn.execute("INSERT OR REPLACE INTO resolution_cache(cache_key, ecosystem, status, outcome_json, world_hash, created_at) VALUES (?,?,?,?,?,?)",
                     (key, "pypi", status, outcome_to_json(out), wh, cutoff))
    conn.execute("INSERT OR REPLACE INTO project_world(id, project_id, world_hash, source, resolver, resolver_args_json, resolved_at, status, failure_json) "
                 "VALUES (?,?,?,?,?,?,?,?,?)", ("pw_" + project_id, project_id, wh, "lockfile", "requirements_lock", json.dumps({"cache_key": key}), cutoff,
                                                "FAILED" if failure else status, json.dumps(out.failure) if failure else None))
    return wh


def lock_text(subdir: str) -> str:
    return (FIXTURES / subdir / "requirements.lock.txt").read_text(encoding="utf-8")
