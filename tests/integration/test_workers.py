"""TC-0.4.1 to TC-0.4.4: the durable job contract, exercised with real worker processes."""
import os
import subprocess
import sys
import time

from faultline.core.enums import JobStatus
from faultline.storage import jobs
from faultline.storage.db import connect
from faultline.storage.migrate import migrate

ENV_KEYS = {"FAULTLINE_LEASE_SECONDS": "1.5", "FAULTLINE_HEARTBEAT_SECONDS": "0.3", "FAULTLINE_POLL_SECONDS": "0.05"}


def spawn_worker(db_path, once=False):
    env = {**os.environ, "FAULTLINE_DB": str(db_path), **ENV_KEYS,
           "PYTHONPATH": os.path.join(os.path.dirname(__file__), "..", "..", "backend")}
    args = [sys.executable, "-m", "faultline.workers.run"] + (["--once"] if once else [])
    return subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def wait_for(cond, timeout=20.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    raise AssertionError("condition not met in time")


def test_tc_0_4_1_atomic_claim_two_workers_fifty_jobs(settings, conn):
    ids = [jobs.create_job(conn, "noop", {"i": i})[0].job_id for i in range(50)]
    workers = [spawn_worker(settings.db_path, once=True) for _ in range(2)]
    for w in workers:
        w.wait(timeout=60)
        assert w.returncode == 0, w.stdout.read().decode()
    rows = conn.execute("SELECT job_id, status, attempts FROM job").fetchall()
    assert len(rows) == 50 and all(r["status"] == "DONE" for r in rows)
    assert all(r["attempts"] == 1 for r in rows)                      # each job executed exactly once
    per_job = conn.execute("SELECT job_id, COUNT(*) n FROM job_attempt GROUP BY job_id").fetchall()
    assert len(per_job) == 50 and all(r["n"] == 1 for r in per_job)   # no duplicate run records
    assert {r["job_id"] for r in rows} == set(ids)
    used = {r["worker"] for r in conn.execute("SELECT DISTINCT worker FROM job_attempt")}
    assert len(used) >= 1


def test_tc_0_4_2_stale_lease_is_reclaimed_after_worker_crash(settings, conn):
    job, _ = jobs.create_job(conn, "sleep", {"seconds": 0.5})
    w1 = spawn_worker(settings.db_path)
    wait_for(lambda: jobs.get_job(conn, job.job_id).status == JobStatus.RUNNING)
    w1.kill()                                                          # crash mid-job: no cleanup runs
    w1.wait()
    w2 = spawn_worker(settings.db_path)
    try:
        done = wait_for(lambda: (j := jobs.get_job(conn, job.job_id)).status == JobStatus.DONE and j)
    finally:
        w2.terminate()
        w2.wait(timeout=10)
    assert done.attempts == 2
    outcomes = [r["outcome"] for r in conn.execute("SELECT outcome FROM job_attempt WHERE job_id=? ORDER BY attempt",
                                                   (job.job_id,))]
    assert outcomes == ["LEASE_LOST", "DONE"]


def test_attempts_exhausted_after_repeated_crashes_fails_job(settings, conn):
    job, _ = jobs.create_job(conn, "noop", max_attempts=1)
    c = jobs.claim_next(conn, "ghost", 0.05)                           # claims and never finishes
    assert c.attempt == 1
    time.sleep(0.2)
    assert jobs.claim_next(conn, "w2", 5) is None                      # expired, attempts exhausted -> FAILED
    assert jobs.get_job(conn, job.job_id).status == JobStatus.FAILED


def test_retry_then_success(settings, conn):
    job, _ = jobs.create_job(conn, "flaky", {"succeed_on_attempt": 2})
    w = spawn_worker(settings.db_path, once=True)
    w.wait(timeout=30)
    j = jobs.get_job(conn, job.job_id)
    assert j.status == JobStatus.DONE and j.attempts == 2


def test_permanent_failure_is_not_retried(settings, conn):
    job, _ = jobs.create_job(conn, "fail")
    w = spawn_worker(settings.db_path, once=True)
    w.wait(timeout=30)
    j = jobs.get_job(conn, job.job_id)
    assert j.status == JobStatus.FAILED and j.attempts == 1 and j.error["code"] == "HANDLER_ERROR"


def test_unknown_kind_fails_permanently(settings, conn):
    job, _ = jobs.create_job(conn, "does_not_exist")
    spawn_worker(settings.db_path, once=True).wait(timeout=30)
    j = jobs.get_job(conn, job.job_id)
    assert j.status == JobStatus.FAILED and j.error["code"] == "UNKNOWN_JOB_KIND"


def test_tc_0_4_4_cancellation_of_running_job(settings, conn):
    job, _ = jobs.create_job(conn, "sleep", {"seconds": 30})
    w = spawn_worker(settings.db_path)
    try:
        wait_for(lambda: jobs.get_job(conn, job.job_id).status == JobStatus.RUNNING)
        jobs.request_cancel(conn, job.job_id)
        j = wait_for(lambda: (x := jobs.get_job(conn, job.job_id)).status == JobStatus.CANCELLED and x, timeout=10)
    finally:
        w.terminate()
        w.wait(timeout=10)
    assert j.status == JobStatus.CANCELLED


def test_cancel_queued_job_never_runs(settings, conn):
    job, _ = jobs.create_job(conn, "noop")
    assert jobs.request_cancel(conn, job.job_id).status == JobStatus.CANCELLED
    spawn_worker(settings.db_path, once=True).wait(timeout=30)
    assert jobs.get_job(conn, job.job_id).attempts == 0


def test_contention_four_workers_no_lost_or_duplicated_work(settings, conn):
    n = 60
    for i in range(n):
        jobs.create_job(conn, "noop", {"i": i})
    ws = [spawn_worker(settings.db_path, once=True) for _ in range(4)]
    for w in ws:
        w.wait(timeout=90)
    assert conn.execute("SELECT COUNT(*) FROM job WHERE status='DONE'").fetchone()[0] == n
    assert conn.execute("SELECT COUNT(*) FROM job_attempt").fetchone()[0] == n


def test_migrate_available_for_workers(settings):
    c = connect(settings.db_path)
    assert migrate(c) >= 2
