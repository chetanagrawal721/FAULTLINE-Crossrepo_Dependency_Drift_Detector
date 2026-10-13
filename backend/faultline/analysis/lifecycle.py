"""What happens to an analysis when its worker is cancelled, dies or errors: the partial evidence is kept and the analysis says so.

An analysis row is never deleted and never left looking "in progress" forever. It becomes FAILED with `outcome` in its stats:
CANCELLED (the user stopped the job), INTERRUPTED (the worker lost its lease and the job was retried) or ERROR. A retry is a NEW
analysis with its own cells and runs, so evidence from the earlier attempt is never counted twice and is never served as the result.
"""
import json
import sqlite3
from datetime import UTC, datetime

ACTIVE = ("QUEUED", "INGESTING", "RESOLVING", "RELATING", "BUILDING_CELLS", "ANALYZING", "VERIFYING", "ATTRIBUTING")


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def retained(conn: sqlite3.Connection, analysis_id: str) -> dict:
    one = lambda sql: conn.execute(sql, (analysis_id,)).fetchone()[0]  # noqa: E731
    return {"cells": one("SELECT COUNT(*) FROM cell WHERE analysis_id=?"),
            "oracle_runs": one("SELECT COUNT(*) FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id JOIN cell c ON c.id=j.cell_id WHERE c.analysis_id=?"),
            "findings": one("SELECT COUNT(*) FROM finding f JOIN cell c ON c.id=f.cell_id WHERE c.analysis_id=?")}


def mark_partial(conn: sqlite3.Connection, analysis_id: str, outcome: str, reason: str) -> bool:
    """Close an analysis that did not finish. Returns False when it was already finished (nothing is changed)."""
    row = conn.execute("SELECT status FROM analysis WHERE id=?", (analysis_id,)).fetchone()
    if row is None or row["status"] not in ACTIVE:
        return False
    stats = {"outcome": outcome, "partial": True, "reason": reason, "retained": retained(conn, analysis_id)}
    conn.execute("UPDATE analysis SET status='FAILED', finished_at=?, stats_json=? WHERE id=? AND status NOT IN ('DONE','FAILED')",
                 (_now(), json.dumps(stats, sort_keys=True), analysis_id))
    conn.execute("UPDATE oracle_job SET status='FAILED', finished_at=? WHERE status IN ('QUEUED','RUNNING') AND cell_id IN (SELECT id FROM cell WHERE analysis_id=?)",
                 (_now(), analysis_id))                      # runs already recorded stay; a run that never finished is not left 'RUNNING'
    return True


def reconcile_abandoned(conn: sqlite3.Connection, job_id: str) -> list[str]:
    """Called when a job (re)starts: any analysis an earlier attempt of THIS job left unfinished is closed as INTERRUPTED."""
    closed = []
    for r in conn.execute(f"SELECT id, options_json FROM analysis WHERE status IN ({','.join('?' * len(ACTIVE))})", ACTIVE).fetchall():
        try:
            opts = json.loads(r["options_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if opts.get("job_id") == job_id and mark_partial(conn, r["id"], "INTERRUPTED", "the worker running this job lost its lease; the job was retried as a new analysis"):
            closed.append(r["id"])
    return closed
