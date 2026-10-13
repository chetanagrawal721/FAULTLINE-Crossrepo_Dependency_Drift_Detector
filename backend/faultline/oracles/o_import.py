"""O-import: import the artifact (and the modules a consumer actually uses) in a world, in the sandbox."""
from ..core.enums import FailureClass, RunProvenance
from ..core.models import EntryOutcome, OracleRunResult
from ..sandbox.client import SandboxClient
from .classify import classify_entry, classify_run

ORACLE = "o_import"
ORACLE_VERSION = "1.0.0"


def plan_modules(top_level: str, consumer_imports: list[str]) -> list[str]:
    """The artifact's top-level package, then the artifact modules the consumer imports (PC-4), without duplicates."""
    seen: dict[str, None] = {top_level: None}
    for m in consumer_imports:
        seen.setdefault(m, None)
    return list(seen)


def run_o_import(sbx: SandboxClient, image: str, *, world_hash: str, artifact_hash: str, top_level: str,
                 modules: list[str], pythonpath: tuple[str, ...] = ("/artifact/src",),
                 timeout_s: int = 120) -> OracleRunResult:
    r = sbx.submit({
        "image": image, "zone": "exec", "script": "o_import.py", "interpreter": "world",
        "args": {"modules": modules, "pythonpath": list(pythonpath)},
        "limits": {"timeout_s": timeout_s},
        "mounts": {"/opt/world": {"world": world_hash}, "/artifact": {"artifact": artifact_hash}},
    })
    data = r.get("data") or {}
    entries: list[EntryOutcome] = []
    classes: list[FailureClass] = []
    for e in data.get("entries", []):
        fc, na = classify_entry(e, top_level)
        classes.append(fc)
        entries.append(EntryOutcome(
            entry=e["entry"], passed=bool(e.get("passed")), exc_type=e.get("exc_type"), message=e.get("message"),
            frames=tuple(e.get("frames", [])), warnings=tuple(e.get("warnings", [])),
            failure_class=fc, not_applicable=na))
    return OracleRunResult(
        job_id=r["job_id"], run_id=r["run_id"], provenance=RunProvenance.FRESH_EXECUTION, exit_code=r.get("exit_code"),
        duration_ms=r.get("duration_ms", 0), failure_class=classify_run(r["failure_class"], classes),
        entries=tuple(entries), stdout_tail=r.get("stdout_tail", ""), stderr_tail=r.get("stderr_tail", ""),
        data=data or None, truncated=bool(r.get("truncated")))
