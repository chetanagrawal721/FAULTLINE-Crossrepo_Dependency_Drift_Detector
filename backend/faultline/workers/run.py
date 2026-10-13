"""Worker process: claims jobs, keeps the lease alive, runs the handler, records the outcome.

    python -m faultline.workers.run [--once] [--db PATH]
"""
import argparse
import logging
import os
import signal
import threading
import time
import traceback

from ..core.config import Settings
from ..core.errors import LeaseLost
from ..core.logging import CORRELATION, phase
from ..core.logging import configure as configure_logging
from ..sandbox.client import SandboxClient, job_group
from ..storage import jobs
from ..storage.db import connect
from ..storage.migrate import migrate
from .handlers import HANDLERS, Cancelled, JobContext, TransientError

log = logging.getLogger("faultline.worker")


def worker_id() -> str:
    return f"{os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'host')}:{os.getpid()}"


SWEEP_SECONDS = 120.0


def _sweep(conn) -> None:
    try:
        from .cleanup import sweep_ownerless
        sweep_ownerless(conn, SandboxClient(timeout=30))
    except Exception as exc:  # noqa: BLE001 - cleanup is best effort and must never stop the worker
        log.warning("orphan cleanup skipped: %s", exc)


def _stop_containers(job_id: str) -> None:
    try:
        killed = SandboxClient(timeout=30).cancel(job_id)
        log.info("cancel requested for %s: stopped %d container(s)", job_id, len(killed))
    except Exception as exc:  # noqa: BLE001 - the job still stops at its next checkpoint
        log.warning("could not stop the containers of %s: %s", job_id, exc)


def run_one(conn, worker: str, settings: Settings) -> bool:
    """Claim and run one job. Returns False when the queue is empty."""
    claimed = jobs.claim_next(conn, worker, settings.lease_seconds)
    if claimed is None:
        return False
    job = claimed.job
    handler = HANDLERS.get(job.kind)
    if handler is None:
        jobs.fail(conn, job.job_id, worker, {"code": "UNKNOWN_JOB_KIND", "message": f"no handler for {job.kind}"}, retryable=False)
        return True

    stop = threading.Event()
    state = {"cancel": False, "lost": False, "progress": None, "message": None}

    def beat():
        hb_conn = connect(settings.db_path)     # SQLite connections are bound to their creating thread
        while not stop.wait(settings.heartbeat_seconds):
            owner, cancel = jobs.heartbeat(hb_conn, job.job_id, worker, settings.lease_seconds,
                                           state["progress"], state["message"])
            if not owner:
                state["lost"] = True
                break
            if cancel and not state["cancel"]:
                _stop_containers(job.job_id)        # cancellation does not wait for a running container to finish
            state["cancel"] = state["cancel"] or cancel
        hb_conn.close()

    t = threading.Thread(target=beat, daemon=True)
    t.start()

    def check_cancel() -> bool:
        if state["lost"]:
            raise LeaseLost()                       # lease lost: another worker owns the job now
        owner, cancel = jobs.heartbeat(conn, job.job_id, worker, settings.lease_seconds)
        if not owner:
            state["lost"] = True
            raise LeaseLost()
        return state["cancel"] or cancel

    def progress(fraction: float, message: str | None) -> None:
        state["progress"], state["message"] = fraction, message

    ctx = JobContext(job.job_id, job.kind, claimed.payload, claimed.attempt, check_cancel, progress)
    correlation = CORRELATION.set(job.job_id)                    # every log line from here on carries the job id
    try:
        with job_group(job.job_id), phase("job", log, kind=job.kind, attempt=claimed.attempt):
            result = handler(ctx)
        log.info("job %s (%s) finished: %s", job.job_id, job.kind, str(result)[:300])
        jobs.complete(conn, job.job_id, worker, result)
    except Cancelled:
        if state["lost"]:
            log.warning("lease lost for %s", job.job_id)
        else:
            jobs.mark_cancelled(conn, job.job_id, worker)
    except TransientError as exc:
        jobs.fail(conn, job.job_id, worker, {"code": "TRANSIENT", "message": str(exc)}, retryable=True)
    except Exception as exc:  # noqa: BLE001 - any handler error is recorded, never crashes the worker
        log.error("job %s (%s) failed: %s", job.job_id, job.kind, exc)
        jobs.fail(conn, job.job_id, worker, {"code": "HANDLER_ERROR", "message": str(exc),
                                             "trace": traceback.format_exc(limit=5)}, retryable=False)
    finally:
        CORRELATION.reset(correlation)
        stop.set()
        t.join(timeout=2)
    return True


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="drain the queue, then exit")
    ap.add_argument("--db", help="database path (default: FAULTLINE_DB)")
    args = ap.parse_args(argv)
    settings = Settings.from_env()
    if args.db:
        os.environ["FAULTLINE_DB"] = args.db
        settings = Settings.from_env()
    configure_logging()
    conn = connect(settings.db_path)
    migrate(conn)
    wid = worker_id()
    stopping = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stopping.update(flag=True))
    log.info("worker %s started (db=%s)", wid, settings.db_path)
    last_sweep = 0.0
    while not stopping["flag"]:
        if time.monotonic() - last_sweep > SWEEP_SECONDS:
            last_sweep = time.monotonic()
            _sweep(conn)
        if not run_one(conn, wid, settings):
            if args.once:
                break
            time.sleep(settings.poll_seconds)
    log.info("worker %s stopped", wid)


if __name__ == "__main__":
    main()
