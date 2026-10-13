"""Job handlers. Later phases register ingest, resolve, relate, verify and so on here.

Phase 0 ships only inert handlers used to prove the job contract.
"""
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..core.errors import Cancelled  # noqa: F401  (re-exported: handlers and the worker import it from here)


class TransientError(Exception):
    """A failure worth retrying (network blip, rate limit)."""


@dataclass
class JobContext:
    job_id: str
    kind: str
    payload: dict
    attempt: int
    _check_cancel: Callable[[], bool]
    _progress: Callable[[float, str | None], None]

    def check_cancel(self) -> None:
        if self._check_cancel():
            raise Cancelled()

    def progress(self, fraction: float, message: str | None = None) -> None:
        self._progress(fraction, message)


def noop(ctx: JobContext) -> dict:
    return {"echo": ctx.payload}


def sleep(ctx: JobContext) -> dict:
    """Sleeps for payload['seconds'], checking for cancellation. Used by the lease and cancel tests."""
    total = float(ctx.payload.get("seconds", 1))
    end = time.monotonic() + total
    while time.monotonic() < end:
        ctx.check_cancel()
        ctx.progress(1 - max(0.0, end - time.monotonic()) / total if total else 1.0, "sleeping")
        time.sleep(0.05)
    return {"slept": total}


def flaky(ctx: JobContext) -> dict:
    """Fails with a transient error until payload['succeed_on_attempt']. Tests retry behaviour."""
    if ctx.attempt < int(ctx.payload.get("succeed_on_attempt", 2)):
        raise TransientError("simulated transient failure")
    return {"attempt": ctx.attempt}


def always_fail(ctx: JobContext) -> dict:
    raise RuntimeError("simulated permanent failure")


def fixture_scenario(ctx: JobContext) -> dict:
    """Run a fixture scenario end to end (worlds, sandboxed oracles, witness verification, findings)."""
    from ..analysis.fixture_runner import run_scenario
    from ..core.config import Settings
    from ..sandbox.client import SandboxClient
    from ..storage.db import connect
    from ..storage.store import Store

    settings = Settings.from_env()
    conn = connect(settings.db_path)
    try:
        def progress(fraction: float, message: str) -> None:
            ctx.check_cancel()
            ctx.progress(fraction, message)
        outcomes = run_scenario(conn, SandboxClient(), Store(settings.store_path), ctx.payload["scenario_id"], progress=progress)
        return {"scenario_id": ctx.payload["scenario_id"],
                "cells": [{"consumer": o.consumer, "state": o.state, "finding_id": o.finding_id} for o in outcomes]}
    finally:
        conn.close()


def ingest_repository(ctx: JobContext) -> dict:
    """Fetch the pinned commit of a repository into an immutable snapshot and record its inventory."""
    from ..core.config import Settings
    from ..core.errors import FaultlineError
    from ..ingestion import service
    from ..sandbox.client import SandboxClient
    from ..sandbox.images import default_image
    from ..storage.db import connect
    from ..storage.store import Store

    settings = Settings.from_env()
    conn = connect(settings.db_path)
    try:
        ctx.progress(0.1, "fetching pinned commit")
        try:
            sid = service.ingest(conn, SandboxClient(), default_image(), Store(settings.store_path), ctx.payload["repository_id"])
        except FaultlineError as e:
            if e.details.get("retryable"):
                raise TransientError(e.message) from e
            raise
        return {"snapshot_id": sid, "repository_id": ctx.payload["repository_id"], "sha": ctx.payload.get("sha")}
    finally:
        conn.close()


def analyze_repository(ctx: JobContext) -> dict:
    """Discover projects in an ingested snapshot, resolve their worlds, build them offline, record visibility."""
    from ..analysis.repository import analyze_repository as run
    from ..core.config import Settings
    from ..sandbox.client import SandboxClient
    from ..sandbox.images import default_image
    from ..storage.db import connect
    from ..storage.store import Store

    settings = Settings.from_env()
    conn = connect(settings.db_path)
    try:
        def progress(fraction: float, message: str) -> None:
            ctx.check_cancel()
            ctx.progress(fraction, message)
        return run(conn, SandboxClient(), default_image(), Store(settings.store_path), ctx.payload["repository_id"], progress=progress)
    finally:
        conn.close()


def live_analysis(ctx: JobContext) -> dict:
    """Relationships, cells, oracle runs, witnesses and findings for every ingested repository of an analysis project."""
    from ..analysis.live import run_live_analysis
    from ..core.config import Settings
    from ..sandbox.client import SandboxClient
    from ..sandbox.images import default_image
    from ..storage.db import connect
    from ..storage.store import Store

    settings = Settings.from_env()
    conn = connect(settings.db_path)
    try:
        def progress(fraction: float, message: str) -> None:
            ctx.check_cancel()
            ctx.progress(fraction, message)
        from ..analysis.repository import analyze_repository as discover
        sbx, image, store = SandboxClient(), default_image(), Store(settings.store_path)
        pending = [r["id"] for r in conn.execute(           # ingested repositories whose projects and worlds were not built yet
            "SELECT r.id FROM repository r WHERE r.analysis_project_id=? AND r.status='INGESTED' AND NOT EXISTS "
            "(SELECT 1 FROM project p JOIN snapshot s ON s.id=p.snapshot_id WHERE s.repository_id=r.id AND s.sha=r.pinned_sha)",
            (ctx.payload["analysis_project_id"],))]
        for n, rid in enumerate(pending):
            ctx.check_cancel()
            ctx.progress(0.05 + 0.25 * n / max(len(pending), 1), f"discovering projects and building worlds ({n + 1} of {len(pending)})")
            discover(conn, sbx, image, store, rid)
        res = run_live_analysis(conn, sbx, image, store, ctx.payload["analysis_project_id"], progress=progress, job_id=ctx.job_id)
        return {"analysis_id": res.analysis_id, "cells": res.cells, "funnel": res.funnel}
    finally:
        conn.close()


def rerun_witness(ctx: JobContext) -> dict:
    """Run a witness's oracle again, 3 fresh runs per world, and report whether it still reproduces."""
    from dataclasses import asdict

    from ..core.config import Settings
    from ..sandbox.client import SandboxClient
    from ..sandbox.images import default_image
    from ..storage.db import connect
    from ..witnesses.rerun import rerun_witness as run

    conn = connect(Settings.from_env().db_path)
    try:
        ctx.progress(0.1, "re-running 3 + 3 fresh executions")
        return asdict(run(conn, SandboxClient(), default_image(), ctx.payload["witness_id"]))
    finally:
        conn.close()


def remediate_finding(ctx: JobContext) -> dict:
    """Propose a constraint for the attributed cause, re-resolve, rebuild and re-run. Produces a diff only: nothing is pushed."""
    from dataclasses import asdict

    from ..core.config import Settings
    from ..remediation.minimal import remediate
    from ..sandbox.client import SandboxClient
    from ..sandbox.images import default_image
    from ..storage.db import connect
    from ..storage.store import Store

    settings = Settings.from_env()
    conn = connect(settings.db_path)
    try:
        ctx.progress(0.1, "re-resolving with the proposed constraint")
        return asdict(remediate(conn, SandboxClient(), default_image(), Store(settings.store_path), ctx.payload["finding_id"],
                                constraint=ctx.payload.get("constraint")))
    finally:
        conn.close()


HANDLERS: dict[str, Callable[[JobContext], dict]] = {
    "noop": noop,
    "sleep": sleep,
    "flaky": flaky,
    "fail": always_fail,
    "fixture_scenario": fixture_scenario,
    "ingest_repository": ingest_repository,
    "analyze_repository": analyze_repository,
    "live_analysis": live_analysis,
    "rerun_witness": rerun_witness,
    "remediate_finding": remediate_finding,
}
