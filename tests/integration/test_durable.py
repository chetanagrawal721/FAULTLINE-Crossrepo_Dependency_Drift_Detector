"""M5.3: durable worker behaviour with real worker processes, a real sandbox daemon and real Docker.

TC-5.3.1 a worker is killed mid-analysis and another worker finishes the job without duplicating anything
TC-5.3.2 a cancellation stops the running container, keeps the partial evidence and labels it
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from faultline.sandbox.client import SandboxClient
from faultline.storage import jobs
from faultline.storage.db import connect
from faultline.storage.migrate import migrate
from tests.conftest import TOKEN, labelled_containers
from tests.liveenv import ingest_all
from tests.livefix import fixture_repo

pytestmark = [pytest.mark.docker, pytest.mark.slow]
ROOT = Path(__file__).resolve().parents[2]
LEASE = 4.0


@pytest.fixture(scope="module")
def world(daemon, image, tmp_path_factory):
    """Scenario D ingested into a database FILE that separate worker processes can open."""
    db = tmp_path_factory.mktemp("durable") / "faultline.db"
    conn = connect(db)
    migrate(conn)
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=600)
    apid, _ids = ingest_all(conn, sbx, image, daemon.store, {
        "rm_dur_prod": ("faultline-demo/acme-models", fixture_repo("acme-models")),
        "rm_dur_notify": ("faultline-demo/notify-svc", fixture_repo("notify-svc/D")),
        "rm_dur_orders": ("faultline-demo/orders-svc", fixture_repo("orders-svc/D"))})
    yield {"db": db, "conn": conn, "apid": apid, "daemon": daemon}
    conn.close()


def start_worker(world, extra_env: dict | None = None) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), "FAULTLINE_DB": str(world["db"]), "FAULTLINE_STORE": str(world["daemon"].store.root),
           "FAULTLINE_SANDBOX_PORT": str(world["daemon"].port), "FAULTLINE_SANDBOX_TOKEN": TOKEN, "FAULTLINE_LEASE_SECONDS": str(LEASE),
           "FAULTLINE_HEARTBEAT_SECONDS": "1", "FAULTLINE_POLL_SECONDS": "0.3", "FAULTLINE_MODE": "LIVE", "PYTHONIOENCODING": "utf-8", **(extra_env or {})}
    return subprocess.Popen([sys.executable, "-m", "faultline.workers.run", "--once"], env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def new_job(world, key: str) -> str:
    job, _ = jobs.create_job(world["conn"], "live_analysis", {"analysis_project_id": world["apid"]}, key)
    return job.job_id


def analyses_of(world, job_id: str) -> list[dict]:
    c = connect(world["db"])
    try:
        return [dict(r) for r in c.execute("SELECT id, status, stats_json, options_json FROM analysis WHERE analysis_project_id=? ORDER BY started_at, rowid", (world["apid"],))
                if json.loads(r["options_json"] or "{}").get("job_id") == job_id]
    finally:
        c.close()


def wait_for(predicate, what: str, limit: float = 300.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        v = predicate()
        if v:
            return v
        time.sleep(0.4)
    pytest.fail(f"timed out waiting for {what}")


def running_oracle_job(world, job_id: str) -> bool:
    c = connect(world["db"])
    try:
        return bool(c.execute("SELECT 1 FROM oracle_job oj JOIN analysis a ON a.id=oj.analysis_id WHERE a.options_json LIKE ? AND oj.status='RUNNING'",
                              (f'%"{job_id}"%',)).fetchone())
    finally:
        c.close()


def test_tc_5_3_1_a_killed_worker_is_replaced_and_nothing_is_duplicated(world):
    job_id = new_job(world, "durable:crash")
    a = start_worker(world)
    wait_for(lambda: running_oracle_job(world, job_id), "the first worker to be mid-verification")
    a.kill()                                                                  # the crash
    a.wait(timeout=30)
    time.sleep(LEASE + 1.5)                                                   # the lease expires
    b = start_worker(world)
    assert b.wait(timeout=900) == 0

    conn = connect(world["db"])
    job = jobs.get_job(conn, job_id)
    assert job.status.value == "DONE" and job.attempts == 2, (job.status, job.attempts)
    rows = analyses_of(world, job_id)
    assert [r["status"] for r in rows] == ["FAILED", "DONE"], rows
    interrupted, done = rows
    stats = json.loads(interrupted["stats_json"])
    assert stats["outcome"] == "INTERRUPTED" and stats["partial"] is True and "lease" in stats["reason"]

    def n(sql, *a):
        return conn.execute(sql, a).fetchone()[0]
    assert n("SELECT COUNT(*) FROM witness WHERE analysis_id=?", done["id"]) == 1                     # exactly one witness in the result that is served
    assert n("SELECT COUNT(*) FROM witness WHERE analysis_id=?", interrupted["id"]) == 0              # the killed attempt never reached a witness
    assert n("SELECT COUNT(*) FROM finding f JOIN cell c ON c.id=f.cell_id WHERE c.analysis_id=? AND f.verdict='BREAK_WITNESSED'", done["id"]) == 1
    assert n("SELECT COUNT(*) FROM finding f JOIN cell c ON c.id=f.cell_id WHERE c.analysis_id=?", interrupted["id"]) == 0
    runs = conn.execute("SELECT r.id, c.analysis_id, r.provenance FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id JOIN cell c ON c.id=j.cell_id "
                        "WHERE c.analysis_id IN (?,?)", (interrupted["id"], done["id"])).fetchall()
    assert len({r["id"] for r in runs}) == len(runs)                                                  # no run record is counted twice
    assert sum(1 for r in runs if r["analysis_id"] == done["id"]) == 6 and all(r["provenance"] == "FRESH_EXECUTION" for r in runs if r["analysis_id"] == done["id"])
    assert n("SELECT COUNT(*) FROM oracle_job WHERE status='RUNNING' AND analysis_id=?", interrupted["id"]) == 0      # nothing is left 'running'
    from faultline.analysis.read import analysis_view, latest_analysis_id
    view = analysis_view(conn, latest_analysis_id(conn, world["apid"]))
    assert view.status == "DONE" and view.id == done["id"] and sum(1 for c in view.cells if c.verdict == "BREAK_WITNESSED") == 1
    conn.close()


def test_tc_5_3_2_cancelling_stops_the_container_keeps_partial_evidence_and_labels_it(world):
    job_id = new_job(world, "durable:cancel")
    a = start_worker(world)
    wait_for(lambda: running_oracle_job(world, job_id), "the worker to be mid-verification")
    t0 = time.monotonic()
    jobs.request_cancel(world["conn"], job_id)
    assert a.wait(timeout=120) == 0
    assert time.monotonic() - t0 < 100                                        # it did not run the whole analysis out first

    conn = connect(world["db"])
    assert jobs.get_job(conn, job_id).status.value == "CANCELLED"
    rows = analyses_of(world, job_id)
    assert len(rows) == 1 and rows[0]["status"] == "FAILED"
    stats = json.loads(rows[0]["stats_json"])
    assert stats["outcome"] == "CANCELLED" and stats["partial"] is True and set(stats["retained"]) == {"cells", "oracle_runs", "findings"}
    assert stats["retained"]["cells"] >= 1                                    # the partial evidence is retained, not deleted
    assert conn.execute("SELECT COUNT(*) FROM finding f JOIN cell c ON c.id=f.cell_id WHERE c.analysis_id=?", (rows[0]["id"],)).fetchone()[0] == 0   # no claim for unfinished work
    assert conn.execute("SELECT COUNT(*) FROM oracle_job WHERE status='RUNNING' AND analysis_id=?", (rows[0]["id"],)).fetchone()[0] == 0
    sbx = SandboxClient(port=world["daemon"].port, token=TOKEN, timeout=60)
    assert job_id not in sbx.groups()                                          # the container of this job is gone
    assert [n for n in labelled_containers() if job_id.lower().replace("_", "-") in n] == []
    from faultline.analysis.read import analysis_view
    view = analysis_view(conn, rows[0]["id"])
    assert view.status == "FAILED" and view.outcome == "CANCELLED" and view.partial_note
    conn.close()


def test_orphaned_containers_of_a_dead_worker_are_stopped_by_the_cleanup(world):
    import threading

    from faultline.workers.cleanup import sweep_ownerless
    daemon = world["daemon"]
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=120)
    from faultline.sandbox import images
    from faultline.sandbox.client import job_group
    image = images.default_image()
    ghost = "job_ghost_never_existed"                                         # a group whose job is not RUNNING in the database
    t = threading.Thread(target=lambda: _quiet(lambda: _long(sbx, image, ghost, job_group)))
    t.start()
    wait_for(lambda: ghost in sbx.groups(), "the ghost container", 40)
    assert sweep_ownerless(world["conn"], sbx) == [ghost]
    t.join(timeout=30)
    assert ghost not in sbx.groups()


def _long(sbx, image, group, job_group):
    with job_group(group):
        sbx.submit({"image": image, "zone": "exec", "probe": "sleep", "args": {"seconds": 60}, "limits": {"timeout_s": 120}})


def _quiet(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass
