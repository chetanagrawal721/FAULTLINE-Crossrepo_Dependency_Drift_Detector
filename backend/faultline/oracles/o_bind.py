"""O-bind: check that the call shapes found in the artifact still bind to the signatures of the world's packages, in the sandbox.

This is a bind check, not an execution: placeholders of the right shape are bound with inspect.signature(...).bind(...). Sites with
star arguments, dynamic targets or no available signature are not claimed either way.
"""
from ..core.enums import FailureClass, RunProvenance
from ..core.models import EntryOutcome, OracleRunResult
from ..sandbox.client import SandboxClient
from ..usage.callsites import CallSite
from .classify import classify_entry, classify_run

ORACLE = "o_bind"
ORACLE_VERSION = "1.0.0"
MAX_SITES = 200


def site_payload(s: CallSite) -> dict:
    return {"id": s.site_id, "callee": s.callee, "n_positional": s.n_positional, "keyword_names": list(s.keyword_names),
            "has_star_args": s.has_star_args, "has_star_kwargs": s.has_star_kwargs}


def plan_sites(sites: list[CallSite]) -> list[CallSite]:
    """The call sites O-bind can check: resolved callee, a runtime path (not TYPE_ONLY), at most MAX_SITES."""
    usable = [s for s in sites if s.status == "RESOLVED" and s.callee and "TYPE_ONLY" not in s.flags]
    return usable[:MAX_SITES]


def run_o_bind(sbx: SandboxClient, image: str, *, world_hash: str, artifact_hash: str, sites: list[dict], top_level: str = "",
               pythonpath: tuple[str, ...] = ("/artifact/src",), timeout_s: int = 180) -> OracleRunResult:
    r = sbx.submit({
        "image": image, "zone": "exec", "script": "bind_sites.py", "interpreter": "world",
        "args": {"sites": sites, "pythonpath": list(pythonpath)},
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
            frames=tuple(e.get("frames", [])), warnings=(), failure_class=fc, not_applicable=na, skipped=bool(e.get("skipped"))))
    return OracleRunResult(
        job_id=r["job_id"], run_id=r["run_id"], provenance=RunProvenance.FRESH_EXECUTION, exit_code=r.get("exit_code"),
        duration_ms=r.get("duration_ms", 0), failure_class=classify_run(r["failure_class"], classes),
        entries=tuple(entries), stdout_tail=r.get("stdout_tail", ""), stderr_tail=r.get("stderr_tail", ""),
        data=data or None, truncated=bool(r.get("truncated")))
