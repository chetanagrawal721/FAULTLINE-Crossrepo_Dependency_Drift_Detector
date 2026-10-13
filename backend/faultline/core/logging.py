"""Structured logs: one JSON object per line, a correlation id on every line, a duration for every phase, and secrets removed.

    configure()                              # once per process (API, worker, sandboxd)
    with correlated(job_id): ...             # every log line inside carries correlation_id
    with phase("build worlds", cells=3): ... # logs the phase and how long it took

Redaction is applied to every record by the handler, whatever logger produced it, so a message or traceback that contains a token
(by value, because the variable name looks secret, or by shape, such as a GitHub token) never reaches the output.
"""
import contextlib
import contextvars
import json
import logging
import sys
import time
import traceback

from ..security.scrub import scrub_obj, scrub_text

CORRELATION: contextvars.ContextVar[str | None] = contextvars.ContextVar("faultline_correlation_id", default=None)
TIMINGS: contextvars.ContextVar[list | None] = contextvars.ContextVar("faultline_phase_timings", default=None)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = scrub_text("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        if getattr(record, "fl", None):
            record.fl = scrub_obj(record.fl)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z"
        out = {"ts": stamp, "level": record.levelname, "logger": record.name, "msg": record.getMessage(), "correlation_id": CORRELATION.get()}
        out.update(getattr(record, "fl", None) or {})
        if record.exc_text:
            out["exception"] = record.exc_text
        return json.dumps(out, sort_keys=True, default=str)


def configure(level: int = logging.INFO, stream=None) -> None:
    """Replace the root handlers with one JSON, redacting handler. Safe to call more than once."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level)


@contextlib.contextmanager
def correlated(correlation_id: str):
    token = CORRELATION.set(correlation_id)
    try:
        yield
    finally:
        CORRELATION.reset(token)


@contextlib.contextmanager
def phase(name: str, logger: logging.Logger | None = None, **fields):
    """Time a phase of work. The duration is logged and kept for the current correlation (see collect_timings)."""
    log = logger or logging.getLogger("faultline.phase")
    t0 = time.monotonic()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        ms = int((time.monotonic() - t0) * 1000)
        entry = {"phase": name, "duration_ms": ms, **fields, **({"failed": True} if failed else {})}
        bucket = TIMINGS.get()
        if bucket is not None:
            bucket.append(entry)
        log.info("phase %s took %d ms", name, ms, extra={"fl": entry})


@contextlib.contextmanager
def collect_timings():
    """Collect the phases that run inside the block as a list of {phase, duration_ms}."""
    bucket: list = []
    token = TIMINGS.set(bucket)
    try:
        yield bucket
    finally:
        TIMINGS.reset(token)
