"""Ingestion service: repositories, pinned SHAs, snapshots and their file inventory in the database."""
import json
import sqlite3
import time

from ..core.errors import ErrorCode, FaultlineError, NotFoundError
from ..core.hashing import object_hash
from ..core.ids import new_id
from ..sandbox.client import SandboxClient
from ..storage.store import Store
from .classify import classify
from .clone import SnapshotResult, fetch_snapshot
from .github import GitHubClient, Resolved
from .urls import RepoRef, validate_github_url


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def create_project(conn: sqlite3.Connection, name: str, mode: str = "LIVE") -> str:
    pid = new_id("ap")
    conn.execute("INSERT INTO analysis_project(id, name, mode, created_at) VALUES (?,?,?,?)", (pid, name, mode, _now()))
    return pid


def get_project(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM analysis_project WHERE id=?", (project_id,)).fetchone()
    if r is None:
        raise NotFoundError(f"project {project_id} not found")
    return r


def add_repository(conn: sqlite3.Connection, github: GitHubClient, project_id: str, url: str,
                   ref: str | None = None) -> tuple[str, Resolved, bool]:
    """Validate, resolve the ref to a commit SHA once, and record both. Returns (repository_id, resolved, new_snapshot_needed).

    Re-submitting the same repository re-resolves the ref. If the SHA changed (a branch advanced or a tag moved) the
    repository is repointed and a NEW snapshot will be created; earlier snapshots and their evidence are untouched.
    """
    get_project(conn, project_id)
    rr: RepoRef = validate_github_url(url, ref)
    resolved = github.resolve(rr)
    row = conn.execute("SELECT id, pinned_sha FROM repository WHERE analysis_project_id=? AND owner=? AND name=?",
                       (project_id, rr.owner, rr.name)).fetchone()
    if row is None:
        rid = new_id("repo")
        conn.execute("INSERT INTO repository(id, analysis_project_id, owner, name, requested_ref, is_fork, is_archived, "
                     "default_branch, pinned_sha, committed_at, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?, 'PENDING', ?)",
                     (rid, project_id, rr.owner, rr.name, rr.ref, int(resolved.is_fork), int(resolved.is_archived),
                      resolved.default_branch, resolved.sha, resolved.committed_at, _now()))
        return rid, resolved, True
    changed = row["pinned_sha"] != resolved.sha
    conn.execute("UPDATE repository SET requested_ref=?, is_fork=?, is_archived=?, default_branch=?, pinned_sha=?, "
                 "committed_at=?, status=CASE WHEN ? THEN 'PENDING' ELSE status END, error_json=NULL WHERE id=?",
                 (rr.ref, int(resolved.is_fork), int(resolved.is_archived), resolved.default_branch, resolved.sha,
                  resolved.committed_at, int(changed), row["id"]))
    return row["id"], resolved, changed


def get_repository(conn: sqlite3.Connection, repository_id: str) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM repository WHERE id=?", (repository_id,)).fetchone()
    if r is None:
        raise NotFoundError(f"repository {repository_id} not found")
    return r


def persist_snapshot(conn: sqlite3.Connection, repository_id: str, snap: SnapshotResult, sha: str, committed_at: str) -> str:
    """Store the snapshot row and its file inventory. Idempotent per (repository, sha)."""
    existing = conn.execute("SELECT id FROM snapshot WHERE repository_id=? AND sha=?", (repository_id, sha)).fetchone()
    if existing:
        return existing["id"]
    inv = snap.inventory
    sid = "snp_" + object_hash([repository_id, sha])[:24]
    status = "PARTIAL" if inv.get("truncated") or any(e["kind"] in ("too_large", "unsupported_path") for e in inv["entries"]) else "OK"
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("INSERT INTO snapshot(id, repository_id, sha, committed_at, tree_truncated, store_path, ingest_status, "
                     "ingest_warnings_json) VALUES (?,?,?,?,?,?,?,?)",
                     (sid, repository_id, sha, committed_at, int(bool(inv.get("truncated"))), snap.key, status,
                      json.dumps(inv.get("warnings", []))))
        for e in inv["entries"]:
            c = classify(e["path"], e["kind"])
            conn.execute("INSERT INTO snapshot_file(snapshot_id, path, content_hash, tags, kind, size, blob_sha, reason, role) "
                         "VALUES (?,?,?,?,?,?,?,?,?)",
                         (sid, e["path"], e.get("sha256") or e["blob"], ",".join(c.tags), e["kind"], e.get("size"),
                          e["blob"], e.get("reason"), c.manifest_kind and f"manifest:{c.manifest_kind}" or c.role))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return sid


def ingest(conn: sqlite3.Connection, sbx: SandboxClient, image: str, store: Store, repository_id: str, *,
           remote: str | None = None) -> str:
    """Fetch the pinned SHA and record the snapshot. Records failure on the repository and re-raises."""
    repo = get_repository(conn, repository_id)
    sha = repo["pinned_sha"]
    if not sha:
        raise FaultlineError("repository has no pinned SHA", code=ErrorCode.REF_NOT_FOUND)
    conn.execute("UPDATE repository SET status='INGESTING', error_json=NULL WHERE id=?", (repository_id,))
    try:
        snap = fetch_snapshot(sbx, image, store, repo["owner"], repo["name"], sha, remote=remote)
        sid = persist_snapshot(conn, repository_id, snap, sha, repo["committed_at"] or _now())
    except FaultlineError as e:
        conn.execute("UPDATE repository SET status='FAILED', error_json=? WHERE id=?",
                     (json.dumps({"code": e.code.value, "message": e.message, "retryable": bool(e.details.get("retryable"))}),
                      repository_id))
        raise
    conn.execute("UPDATE repository SET status='INGESTED', error_json=NULL WHERE id=?", (repository_id,))
    return sid
