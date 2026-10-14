"""Recompute findings from their stored evidence when the verdict policy version changed (M5.3).

A finding records the policy version it was decided under. When the running policy differs, the verdict is derived again from the
stored oracle runs and witnesses with the current rules. Nothing is executed again and no run is added, so a rule change can never
leave a stale verdict being served, and can never create evidence.
"""
import json
import sqlite3

from ..core.models import OracleRunResult
from ..witnesses.runs import RunRecord
from ..witnesses.verify import Decision, EntryDecision, decide_entry
from . import templates
from .engine import LIVE_POLICY_VERSION, LIVE_PRIORITY, Evidence, decide, split_silent

LEVELS_OK = ("L2", "L3", "L4", "L5")


ORACLES = ("o_import", "o_tests", "o_bind", "o_contract")


def _records(conn: sqlite3.Connection, cell_id: str, oracle: str = "o_import") -> tuple[list[RunRecord], list[RunRecord]]:
    rows = conn.execute("SELECT j.id AS job_id, j.side, j.world_hash, r.id AS run_id, r.run_index, r.provenance, r.result_json FROM oracle_run r "
                        "JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.cell_id=? AND j.oracle=? AND r.provenance='FRESH_EXECUTION' "
                        "ORDER BY r.created_at, r.run_index", (cell_id, oracle)).fetchall()
    by_side: dict[str, list[RunRecord]] = {"ref": [], "test": []}
    for r in rows:
        by_side.setdefault(r["side"], []).append(RunRecord(r["run_id"], r["job_id"], r["run_index"], r["side"], r["world_hash"], r["provenance"],
                                                         OracleRunResult.model_validate_json(r["result_json"])))
    return by_side["ref"][-3:], by_side["test"][-3:]


def stale_findings(conn: sqlite3.Connection, analysis_id: str) -> list[sqlite3.Row]:
    return [f for f in conn.execute("SELECT * FROM finding WHERE analysis_id=? AND cell_id IS NOT NULL", (analysis_id,))
            if json.loads(f["scope_json"] or "{}").get("policy") not in (None, LIVE_POLICY_VERSION)]


def recompute_finding(conn: sqlite3.Connection, finding: sqlite3.Row) -> str:
    """Re-decide one finding from its stored runs. Returns the new verdict."""
    scope = json.loads(finding["scope_json"] or "{}")
    witnesses = {w["entry_point"]: w["id"] for w in conn.execute(
        "SELECT w.id, w.entry_point FROM witness w JOIN finding_evidence fe ON fe.evidence_id=w.id AND fe.evidence_kind='WITNESS' WHERE fe.finding_id=?", (finding["id"],))}
    decisions = []
    problem = None
    for oracle in ORACLES:                                                    # every oracle that ran for this cell, in the order the pipeline used
        ref, test = _records(conn, finding["cell_id"], oracle)
        names: list[str] = []
        for r in ref + test:
            for e in r.result.entries:
                if e.entry not in names:
                    names.append(e.entry)
        for name in names:
            d = decide_entry(name, ref, test)
            if d.decision == Decision.WITNESS:
                d = EntryDecision(d.entry, d.decision, d.reason, d.signature, d.ref_run_ids, d.test_run_ids, witnesses.get(name))
            decisions.append(d)
        problem = problem or next((r.result.failure_class.value.lower() for r in ref + test if r.result.failure_class.value != "NONE" and not r.result.entries), None)
    levels = [x["level"] for x in conn.execute(
        "SELECT rl.level FROM finding_evidence fe JOIN relationship rl ON rl.id=fe.evidence_id WHERE fe.finding_id=? AND fe.evidence_kind='RELATIONSHIP'", (finding["id"],))]
    level = "L2" if levels and all(x in LEVELS_OK for x in levels) else "L1"
    plain, silent = split_silent(decisions)
    out = decide(Evidence(relationship_level=level, cell_state="PENDING", decisions=plain, run_problem=problem, silent_entries=silent))
    artifact = conn.execute("SELECT COALESCE(published_name, display_name, rel_path) FROM project p JOIN cell c ON c.artifact_project_id=p.id WHERE c.id=?",
                            (finding["cell_id"],)).fetchone()[0]
    sites = scope.get("bind_sites", {})
    shown = tuple(f"call `{sites[e]['callee']}` at {sites[e]['id']}" if e in sites else e for e in out.exercised)
    kw = {"artifact": artifact, "consumers": scope.get("consumers", []), "exercised": shown, "reasons": out.reasons}
    if scope.get("not_checked"):
        kw["not_checked"] = tuple(scope["not_checked"])
    cinputs = (scope.get("contract") or {}).get("inputs", {})
    if out.outcome in ("BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED"):
        dec = next(x for x in decisions if x.entry == out.witness_entries[0])
        kw.update(entry=dec.entry, exc=dec.signature.exc_type, message=dec.signature.message_norm)
        if dec.entry in cinputs:
            kw["contract"] = cinputs[dec.entry]
        if dec.entry in sites:
            kw["site"] = sites[dec.entry]
    headline = templates.live_headline(out.outcome, **kw)
    scope.update(exercised=list(out.exercised), not_applicable=list(out.not_applicable), reasons=list(out.reasons), policy=LIVE_POLICY_VERSION,
                 recomputed_from_stored_evidence=True)
    verdict = out.verdict
    conn.execute("UPDATE finding SET verdict=?, sub_label=?, headline=?, scope_json=?, priority=? WHERE id=?",
                 (verdict.value, out.sub_label, headline, json.dumps(scope, sort_keys=True), LIVE_PRIORITY[verdict], finding["id"]))
    return verdict.value


def recompute_stale(conn: sqlite3.Connection, analysis_id: str) -> dict[str, str]:
    """Recompute every finding of an analysis that was decided under another policy version. {finding_id: new verdict}."""
    return {f["id"]: recompute_finding(conn, f) for f in stale_findings(conn, analysis_id)}


def recompute_all_stale(conn: sqlite3.Connection) -> int:
    """Recompute every finding decided under another policy version (one cheap query when nothing is stale). Returns how many changed."""
    rows = conn.execute("SELECT * FROM finding WHERE cell_id IS NOT NULL AND json_extract(scope_json, '$.policy') IS NOT NULL "
                        "AND json_extract(scope_json, '$.policy') != ?", (LIVE_POLICY_VERSION,)).fetchall()
    for f in rows:
        recompute_finding(conn, f)
    return len(rows)
