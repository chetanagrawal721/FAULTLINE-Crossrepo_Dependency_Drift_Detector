"""Orphan cleanup: containers started for a worker job that is no longer running (the worker was killed) are stopped.

Containers are labelled with their worker job (group). A group whose job is not RUNNING has no owner, so its containers are killed.
Runs when a worker starts and every few minutes while idle. The egress proxy has no group and is never touched.
"""
import logging
import sqlite3

from ..sandbox.client import SandboxClient
from ..storage import jobs

log = logging.getLogger("faultline.worker.cleanup")


def sweep_ownerless(conn: sqlite3.Connection, sbx: SandboxClient) -> list[str]:
    stopped = []
    for group in sbx.groups():
        try:
            job = jobs.get_job(conn, group)
        except Exception:  # noqa: BLE001 - an unknown job id also means no live owner
            job = None
        if job is None or job.status.value != "RUNNING":
            killed = sbx.cancel(group)
            if killed:
                log.info("stopped %d orphaned container(s) of job %s", len(killed), group)
                stopped.append(group)
    return stopped
