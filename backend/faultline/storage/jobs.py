"""Durable job queue on SQLite: atomic claim, lease and heartbeat, retries, cancellation, idempotency."""
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from ..core.enums import JOB_TRANSITIONS, JobStatus
from ..core.errors import InvalidEnumError, InvalidTransitionError, NotFoundError
from ..core.ids import new_id
from ..core.models import Job


def _iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), UTC).isoformat(timespec="milliseconds")


def _row_to_job(r: sqlite3.Row) -> Job:
    return Job(
        job_id=r["job_id"], kind=r["kind"], status=JobStatus(r["status"]),
        idempotency_key=r["idempotency_key"], attempts=r["attempts"], max_attempts=r["max_attempts"],
        progress=r["progress"], message=r["message"], cancel_requested=bool(r["cancel_requested"]),
        result=json.loads(r["result_json"]) if r["result_json"] else None,
        error=json.loads(r["error_json"]) if r["error_json"] else None,
        created_at=datetime.fromisoformat(r["created_at"]), updated_at=datetime.fromisoformat(r["updated_at"]),
    )


def check_transition(old: JobStatus, new: JobStatus) -> None:
    if new not in JOB_TRANSITIONS[old]:
        raise InvalidTransitionError(f"job status cannot change from {old.value} to {new.value}",
                                     details={"from": old.value, "to": new.value})


def _guard(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Cursor:
    try:
        return conn.execute(sql, params)
    except sqlite3.IntegrityError as exc:
        if "invalid_transition" in str(exc):
            raise InvalidTransitionError("job status change rejected by the database") from exc
        if "CHECK constraint failed" in str(exc):
            raise InvalidEnumError(f"value rejected by schema: {exc}") from exc
        raise


def _with_timing(conn: sqlite3.Connection, job: Job) -> Job:
    """Add what the UI shows for every job: how long it ran, how long it waited, and how it failed."""
    attempts = conn.execute("SELECT attempt, started_at, finished_at, outcome FROM job_attempt WHERE job_id=? ORDER BY attempt", (job.job_id,)).fetchall()
    now = time.time()
    duration = int(sum(((a["finished_at"] or now) - a["started_at"]) * 1000 for a in attempts)) if attempts else None
    wait = int(max(0.0, attempts[0]["started_at"] - job.created_at.timestamp()) * 1000) if attempts else None
    failure = (job.error or {}).get("code") if job.status.value in ("FAILED", "DEAD") else ("CANCELLED" if job.status.value == "CANCELLED" else None)
    earlier = [a["outcome"] for a in attempts[:-1] if a["outcome"] and a["outcome"] != "DONE"]
    return job.model_copy(update={"duration_ms": duration, "queue_wait_ms": wait, "failure_class": failure, "retried_after": earlier[-1] if earlier else None})


def get_job(conn: sqlite3.Connection, job_id: str) -> Job:
    r = conn.execute("SELECT * FROM job WHERE job_id=?", (job_id,)).fetchone()
    if r is None:
        raise NotFoundError(f"job {job_id} not found")
    return _with_timing(conn, _row_to_job(r))


def list_jobs(conn: sqlite3.Connection, limit: int = 50) -> list[Job]:
    rows = conn.execute("SELECT * FROM job ORDER BY created_at DESC, job_id DESC LIMIT ?", (limit,)).fetchall()
    return [_with_timing(conn, _row_to_job(r)) for r in rows]


def create_job(conn: sqlite3.Connection, kind: str, payload: dict | None = None,
               idempotency_key: str | None = None, max_attempts: int = 3, priority: int = 100) -> tuple[Job, bool]:
    """Insert a job. With an idempotency key, a repeat returns the existing job. Returns (job, created)."""
    now = _iso()
    job_id = new_id("job")
    try:
        conn.execute(
            "INSERT INTO job(job_id, kind, idempotency_key, payload_json, max_attempts, priority, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (job_id, kind, idempotency_key, json.dumps(payload or {}, sort_keys=True), max_attempts, priority, now, now))
        return get_job(conn, job_id), True
    except sqlite3.IntegrityError:
        if idempotency_key is None:
            raise
        r = conn.execute("SELECT job_id FROM job WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        return get_job(conn, r["job_id"]), False


@dataclass
class Claimed:
    job: Job
    payload: dict
    attempt: int


def claim_next(conn: sqlite3.Connection, worker: str, lease_seconds: float) -> Claimed | None:
    """Atomically claim one runnable job. Runnable = QUEUED, or RUNNING with an expired lease (crashed worker)."""
    while True:
        now = time.time()
        conn.execute("BEGIN IMMEDIATE")
        try:
            r = conn.execute(
                "SELECT * FROM job WHERE status='QUEUED' OR (status='RUNNING' AND lease_expires_at < ?) "
                "ORDER BY priority, created_at, job_id LIMIT 1", (now,)).fetchone()
            if r is None:
                conn.execute("COMMIT")
                return None
            if r["status"] == "RUNNING":
                # lease expired: close the abandoned attempt
                conn.execute("UPDATE job_attempt SET finished_at=?, outcome='LEASE_LOST' "
                             "WHERE job_id=? AND attempt=? AND finished_at IS NULL", (now, r["job_id"], r["attempts"]))
                if r["attempts"] >= r["max_attempts"]:
                    _guard(conn, "UPDATE job SET status='FAILED', lease_owner=NULL, updated_at=?, error_json=? WHERE job_id=?",
                           (_iso(), json.dumps({"code": "LEASE_EXPIRED", "message": "attempts exhausted after lease expiry"}),
                            r["job_id"]))
                    conn.execute("COMMIT")
                    continue
            if r["cancel_requested"]:
                _guard(conn, "UPDATE job SET status='CANCELLED', lease_owner=NULL, updated_at=? WHERE job_id=?",
                       (_iso(), r["job_id"]))
                conn.execute("COMMIT")
                continue
            attempt = r["attempts"] + 1
            _guard(conn, "UPDATE job SET status='RUNNING', attempts=?, lease_owner=?, lease_expires_at=?, heartbeat_at=?, "
                         "updated_at=? WHERE job_id=?", (attempt, worker, now + lease_seconds, now, _iso(), r["job_id"]))
            conn.execute("INSERT INTO job_attempt(job_id, attempt, worker, started_at) VALUES (?,?,?,?)",
                         (r["job_id"], attempt, worker, now))
            conn.execute("COMMIT")
            return Claimed(get_job(conn, r["job_id"]), json.loads(r["payload_json"]), attempt)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise


def heartbeat(conn: sqlite3.Connection, job_id: str, worker: str, lease_seconds: float,
              progress: float | None = None, message: str | None = None) -> tuple[bool, bool]:
    """Extend the lease. Returns (still_owner, cancel_requested)."""
    now = time.time()
    cur = conn.execute(
        "UPDATE job SET lease_expires_at=?, heartbeat_at=?, updated_at=?, "
        "progress=COALESCE(?, progress), message=COALESCE(?, message) "
        "WHERE job_id=? AND lease_owner=? AND status='RUNNING'",
        (now + lease_seconds, now, _iso(), progress, message, job_id, worker))
    if cur.rowcount == 0:
        return False, False
    r = conn.execute("SELECT cancel_requested FROM job WHERE job_id=?", (job_id,)).fetchone()
    return True, bool(r["cancel_requested"])


def _finish(conn, job_id, worker, status: str, outcome: str, result=None, error=None) -> bool:
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = _guard(conn, "UPDATE job SET status=?, result_json=?, error_json=?, lease_owner=NULL, "
                           "lease_expires_at=NULL, progress=CASE WHEN ?='DONE' THEN 1 ELSE progress END, "
                           "message=CASE WHEN ?='DONE' THEN 'done' ELSE message END, updated_at=? "
                           "WHERE job_id=? AND lease_owner=? AND status='RUNNING'",
                     (status, json.dumps(result) if result is not None else None,
                      json.dumps(error) if error is not None else None, status, status, _iso(), job_id, worker))
        if cur.rowcount == 1:
            conn.execute("UPDATE job_attempt SET finished_at=?, outcome=? WHERE job_id=? AND finished_at IS NULL",
                         (now, outcome, job_id))
        conn.execute("COMMIT")
        return cur.rowcount == 1
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def complete(conn, job_id: str, worker: str, result: dict | None = None) -> bool:
    return _finish(conn, job_id, worker, "DONE", "DONE", result=result or {})


def mark_cancelled(conn, job_id: str, worker: str) -> bool:
    return _finish(conn, job_id, worker, "CANCELLED", "CANCELLED")


def fail(conn, job_id: str, worker: str, error: dict, retryable: bool) -> str:
    """Record a failure. Retryable failures return to QUEUED while attempts remain. Returns the new status."""
    r = conn.execute("SELECT attempts, max_attempts FROM job WHERE job_id=? AND lease_owner=? AND status='RUNNING'",
                     (job_id, worker)).fetchone()
    if r is None:
        return "LOST"
    if retryable and r["attempts"] < r["max_attempts"]:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("UPDATE job SET status='QUEUED', lease_owner=NULL, lease_expires_at=NULL, error_json=?, updated_at=? "
                         "WHERE job_id=? AND lease_owner=? AND status='RUNNING'",
                         (json.dumps(error), _iso(), job_id, worker))
            conn.execute("UPDATE job_attempt SET finished_at=?, outcome='RETRY' WHERE job_id=? AND finished_at IS NULL",
                         (time.time(), job_id))
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return "QUEUED"
    _finish(conn, job_id, worker, "FAILED", "FAILED", error=error)
    return "FAILED"


def request_cancel(conn: sqlite3.Connection, job_id: str) -> Job:
    conn.execute("BEGIN IMMEDIATE")
    try:
        r = conn.execute("SELECT status FROM job WHERE job_id=?", (job_id,)).fetchone()
        if r is None:
            conn.execute("ROLLBACK")
            raise NotFoundError(f"job {job_id} not found")
        if r["status"] == "QUEUED":
            _guard(conn, "UPDATE job SET status='CANCELLED', cancel_requested=1, updated_at=? WHERE job_id=?",
                   (_iso(), job_id))
        elif r["status"] == "RUNNING":
            conn.execute("UPDATE job SET cancel_requested=1, updated_at=? WHERE job_id=?", (_iso(), job_id))
        conn.execute("COMMIT")
    except NotFoundError:
        raise
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return get_job(conn, job_id)


def set_status(conn: sqlite3.Connection, job_id: str, new: JobStatus | str) -> Job:
    """Administrative status change that enforces the transition table (used by tests and tooling)."""
    try:
        new = JobStatus(new)
    except ValueError as exc:
        raise InvalidEnumError(f"unknown job status {new!r}") from exc
    cur = get_job(conn, job_id)
    check_transition(cur.status, new)
    _guard(conn, "UPDATE job SET status=?, updated_at=? WHERE job_id=?", (new.value, _iso(), job_id))
    return get_job(conn, job_id)
