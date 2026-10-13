"""Read models for projects, repositories and snapshot inventories, built from persisted rows only."""
import json
import sqlite3

from ..core.views import FileView, ProjectView, RepositoryView, SnapshotSummary


def _snapshot(conn: sqlite3.Connection, repository_id: str, sha: str | None) -> SnapshotSummary | None:
    if not sha:
        return None
    s = conn.execute("SELECT * FROM snapshot WHERE repository_id=? AND sha=?", (repository_id, sha)).fetchone()
    if s is None:
        return None
    c = conn.execute("SELECT COUNT(*) AS n, SUM(CASE WHEN kind='file' THEN 1 ELSE 0 END) AS stored, "
                     "SUM(CASE WHEN role LIKE 'manifest:%' THEN 1 ELSE 0 END) AS m FROM snapshot_file WHERE snapshot_id=?",
                     (s["id"],)).fetchone()
    return SnapshotSummary(id=s["id"], sha=s["sha"], status=s["ingest_status"], truncated=bool(s["tree_truncated"]),
                           warnings=json.loads(s["ingest_warnings_json"] or "[]"), file_count=c["n"] or 0,
                           stored_files=c["stored"] or 0, manifests=c["m"] or 0)


def repository_view(conn: sqlite3.Connection, row: sqlite3.Row, job_id: str | None = None) -> RepositoryView:
    return RepositoryView(
        id=row["id"], project_id=row["analysis_project_id"], owner=row["owner"], name=row["name"],
        url=f"https://github.com/{row['owner']}/{row['name']}", requested_ref=row["requested_ref"],
        default_branch=row["default_branch"], pinned_sha=row["pinned_sha"], committed_at=row["committed_at"],
        is_fork=bool(row["is_fork"]), is_archived=bool(row["is_archived"]), status=row["status"],
        error=json.loads(row["error_json"]) if row["error_json"] else None,
        snapshot=_snapshot(conn, row["id"], row["pinned_sha"]), job_id=job_id)


def project_view(conn: sqlite3.Connection, row: sqlite3.Row) -> ProjectView:
    repos = conn.execute("SELECT * FROM repository WHERE analysis_project_id=? ORDER BY created_at, id", (row["id"],)).fetchall()
    return ProjectView(id=row["id"], name=row["name"], mode=row["mode"], created_at=row["created_at"],
                       repositories=[repository_view(conn, r) for r in repos])


def file_views(conn: sqlite3.Connection, repository_id: str, sha: str | None, role: str | None, limit: int,
               offset: int) -> list[FileView]:
    s = conn.execute("SELECT id FROM snapshot WHERE repository_id=? AND sha=?", (repository_id, sha)).fetchone() if sha else None
    if s is None:
        return []
    sql = "SELECT * FROM snapshot_file WHERE snapshot_id=?"
    args: list = [s["id"]]
    if role:
        sql += " AND (role=? OR role LIKE ?)"
        args += [role, role + ":%"]
    sql += " ORDER BY path LIMIT ? OFFSET ?"
    args += [limit, offset]
    return [FileView(path=r["path"], kind=r["kind"], size=r["size"], role=r["role"],
                     tags=[t for t in (r["tags"] or "").split(",") if t], reason=r["reason"],
                     sha256=r["content_hash"] if r["kind"] == "file" else None)
            for r in conn.execute(sql, args)]
