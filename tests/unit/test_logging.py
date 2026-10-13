"""M5.4: structured logs with correlation ids and phase timings, and secrets never written (TC-5.4.1)."""
import io
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from faultline.core.logging import collect_timings, configure, correlated, phase
from faultline.storage import jobs

ROOT = Path(__file__).resolve().parents[2]
CANARY = "canary-admin-token-91b7e4c2"
GH = "ghp_" + "Q" * 36


def capture() -> io.StringIO:
    buf = io.StringIO()
    configure(stream=buf)
    return buf


def lines(buf: io.StringIO) -> list[dict]:
    return [json.loads(x) for x in buf.getvalue().splitlines() if x.strip()]


def test_every_line_is_json_with_a_correlation_id_and_a_phase_has_a_duration(monkeypatch):
    buf = capture()
    log = logging.getLogger("faultline.test")
    with correlated("job_abc123"):
        with phase("build worlds", log, cells=2):
            time.sleep(0.03)
        log.info("done")
    log.info("outside any correlation")
    rows = lines(buf)
    assert all({"ts", "level", "logger", "msg", "correlation_id"} <= set(r) for r in rows)
    first = rows[0]
    assert first["phase"] == "build worlds" and first["cells"] == 2 and first["duration_ms"] >= 30 and first["correlation_id"] == "job_abc123"
    assert rows[1]["correlation_id"] == "job_abc123" and rows[2]["correlation_id"] is None


def test_phase_timings_can_be_collected_and_a_failed_phase_is_marked():
    capture()
    with collect_timings() as t:
        with phase("one"):
            pass
        try:
            with phase("two"):
                raise ValueError("x")
        except ValueError:
            pass
    assert [e["phase"] for e in t] == ["one", "two"] and t[1]["failed"] is True and all(isinstance(e["duration_ms"], int) for e in t)


def test_secrets_are_redacted_by_value_by_shape_in_fields_and_in_tracebacks(monkeypatch):
    monkeypatch.setenv("FAULTLINE_ADMIN_TOKEN", CANARY)
    monkeypatch.setenv("SOME_API_KEY", "another-canary-value-77")
    buf = capture()
    log = logging.getLogger("faultline.test")
    log.info("starting with %s and %s", CANARY, GH)
    log.info("header was Authorization Bearer abcdefghijklmnop1234567890")
    log.info("fields", extra={"fl": {"detail": f"token={CANARY}", "nested": {"k": ["another-canary-value-77"]}}})
    try:
        raise RuntimeError(f"failed with {CANARY}")
    except RuntimeError:
        log.exception("boom")
    out = buf.getvalue()
    for secret in (CANARY, GH, "abcdefghijklmnop1234567890", "another-canary-value-77"):
        assert secret not in out, secret
    assert "[REDACTED]" in out and "Traceback" in out                       # the traceback is kept, only the secret is removed


def test_tc_5_4_1_a_worker_process_never_writes_a_canary_to_its_logs(conn, settings, tmp_path):
    """A real worker process with a canary token in its environment runs a job whose payload carries the canary; its whole log is searched."""
    job, _ = jobs.create_job(conn, "noop", {"note": f"the token is {CANARY}", "other": GH}, "canary-job")
    err = tmp_path / "worker.log"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), "FAULTLINE_DB": str(settings.db_path), "FAULTLINE_ADMIN_TOKEN": CANARY,
           "FAULTLINE_POLL_SECONDS": "0.1", "FAULTLINE_SANDBOX_PORT": "1"}
    with err.open("wb") as f:
        p = subprocess.run([sys.executable, "-m", "faultline.workers.run", "--once"], env=env, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=60)
    assert p.returncode == 0
    text = err.read_text(encoding="utf-8")
    assert CANARY not in text and GH not in text                              # the payload was echoed into the log line, and redacted
    rows = [json.loads(x) for x in text.splitlines() if x.startswith("{")]
    finished = [r for r in rows if "finished" in r["msg"]]
    assert finished and finished[0]["correlation_id"] == job.job_id and "[REDACTED]" in finished[0]["msg"]
    timing = [r for r in rows if r.get("phase") == "job"]
    assert timing and timing[0]["kind"] == "noop" and timing[0]["correlation_id"] == job.job_id and isinstance(timing[0]["duration_ms"], int)
    assert jobs.get_job(conn, job.job_id).status.value == "DONE"
