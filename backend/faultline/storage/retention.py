"""Retention: remove old data, never evidence that a finding still refers to.

What is evidence: for every cell that has a finding or a witness, its artifact source tree, the repository snapshots of the artifact and of
its consumers, the worlds of both sides, and each witness's exported bundle. Anything else in the store that is older than the limit
is removable. The wheelhouse and the local test remotes are never touched. dry_run=True reports what would go and deletes nothing.
"""
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from .store import Store

KINDS = ("snapshots", "artifacts", "worlds", "bundles")


@dataclass
class RetentionReport:
    deleted: dict[str, list[str]] = field(default_factory=lambda: {k: [] for k in KINDS})
    kept_referenced: dict[str, list[str]] = field(default_factory=lambda: {k: [] for k in KINDS})
    kept_recent: dict[str, list[str]] = field(default_factory=lambda: {k: [] for k in KINDS})
    dry_run: bool = False


def referenced(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Store keys that retained findings and witnesses depend on."""
    cells = [r["id"] for r in conn.execute("SELECT DISTINCT cell_id AS id FROM finding WHERE cell_id IS NOT NULL UNION SELECT DISTINCT cell_id FROM witness")]
    out: dict[str, set[str]] = {k: set() for k in KINDS}
    marks = ",".join("?" * len(cells)) or "NULL"
    projects: set[str] = set()
    for r in conn.execute(f"SELECT artifact_project_id, ref_world_hash, test_world_hash FROM cell WHERE id IN ({marks})", cells):
        projects.add(r["artifact_project_id"])
        out["worlds"] |= {r["ref_world_hash"], r["test_world_hash"]}
    for r in conn.execute(f"SELECT consumer_project_id FROM cell_consumer WHERE cell_id IN ({marks})", cells):
        projects.add(r["consumer_project_id"])
    for r in conn.execute("SELECT DISTINCT project_id FROM relationship_evidence WHERE relationship_id IN "
                          "(SELECT evidence_id FROM finding_evidence WHERE evidence_kind='RELATIONSHIP')"):
        projects.add(r["project_id"])
    pmarks = ",".join("?" * len(projects)) or "NULL"
    sql = (f"SELECT p.artifact_content_hash AS art, s.store_path AS snap FROM project p "
           f"LEFT JOIN snapshot s ON s.id=p.snapshot_id WHERE p.id IN ({pmarks})")
    for r in conn.execute(sql, list(projects)):
        if r["art"]:
            out["artifacts"].add(r["art"])
        if r["snap"]:
            out["snapshots"].add(r["snap"])
    for r in conn.execute(f"SELECT w.id FROM witness w WHERE w.cell_id IN ({marks})", cells):
        out["bundles"].add(f"{r['id']}.zip")
    return out


def cleanup(conn: sqlite3.Connection, store: Store, *, max_age_days: float, dry_run: bool = False, now: float | None = None) -> RetentionReport:
    """Delete unreferenced store entries older than max_age_days (0 means every unreferenced entry)."""
    keep = referenced(conn)
    report = RetentionReport(dry_run=dry_run)
    cutoff = (now if now is not None else time.time()) - max_age_days * 86400
    for kind in KINDS:
        base = store.root / kind
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            name = entry.name
            if name in keep[kind]:
                report.kept_referenced[kind].append(name)
            elif entry.stat().st_mtime > cutoff:
                report.kept_recent[kind].append(name)
            else:
                report.deleted[kind].append(name)
                if not dry_run:
                    _remove(entry)
    return report


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        if path.exists():                                              # read-only snapshot files: make them writable, then retry
            for p in path.rglob("*"):
                try:
                    p.chmod(0o700)
                except OSError:
                    pass
            shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def prune_logs(directory: Path, *, max_age_days: float, now: float | None = None) -> list[str]:
    """Remove log files older than the limit. Logs are not evidence; the findings and bundles carry what is needed to re-check them."""
    cutoff = (now if now is not None else time.time()) - max_age_days * 86400
    removed = []
    if directory.is_dir():
        for f in sorted(directory.glob("*.log")):
            if f.stat().st_mtime <= cutoff:
                f.unlink(missing_ok=True)
                removed.append(f.name)
    return removed
