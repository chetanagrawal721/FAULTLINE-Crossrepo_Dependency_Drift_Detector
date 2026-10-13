"""O-tests: run the artifact's own test suite in a world, in the sandbox, with per-test outcomes."""
from ..core.enums import FailureClass, RunProvenance
from ..core.models import EntryOutcome, OracleRunResult
from ..sandbox.client import SandboxClient
from .classify import classify_entry, classify_run

ORACLE = "o_tests"
ORACLE_VERSION = "1.0.0"


def run_o_tests(sbx: SandboxClient, image: str, *, world_hash: str, artifact_hash: str, top_level: str,
                tests_dir: str = "/artifact/tests", pythonpath: tuple[str, ...] = ("/artifact/src",),
                timeout_s: int = 300) -> OracleRunResult:
    r = sbx.submit({
        "image": image, "zone": "exec", "script": "o_tests.py", "interpreter": "world",
        "args": {"tests_dir": tests_dir, "pythonpath": list(pythonpath)},
        "limits": {"timeout_s": timeout_s},
        "mounts": {"/opt/world": {"world": world_hash}, "/artifact": {"artifact": artifact_hash}},
    })
    data = r.get("data") or {}
    entries: list[EntryOutcome] = []
    classes: list[FailureClass] = []
    for e in data.get("entries", []):
        fc, na = classify_entry(e, top_level)
        if e.get("collection_error") and fc == FailureClass.ARTIFACT_FAILURE and e.get("exc_type") == "ModuleNotFoundError":
            fc = FailureClass.HARNESS_FAILURE            # a test file needs a package no world provides: not a break
        classes.append(fc)
        entries.append(EntryOutcome(
            entry=e["entry"], passed=bool(e.get("passed")) or bool(e.get("skipped")), exc_type=e.get("exc_type"),
            message=e.get("message"), frames=tuple(e.get("frames", [])), failure_class=fc, not_applicable=na,
            skipped=bool(e.get("skipped"))))
    if data.get("harness_error"):
        classes.append(FailureClass.HARNESS_FAILURE)
    return OracleRunResult(
        job_id=r["job_id"], run_id=r["run_id"], provenance=RunProvenance.FRESH_EXECUTION, exit_code=r.get("exit_code"),
        duration_ms=r.get("duration_ms", 0), failure_class=classify_run(r["failure_class"], classes),
        entries=tuple(entries), stdout_tail=r.get("stdout_tail", ""), stderr_tail=r.get("stderr_tail", ""),
        data=data or None, truncated=bool(r.get("truncated")))
