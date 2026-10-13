"""Read side for findings: assembles API views from persisted rows (nothing is invented, nothing comes from the UI)."""
import json
import sqlite3

from ..core.errors import NotFoundError
from ..core.models import FailureSignature
from ..core.views import (
    DeltaItem,
    EntryView,
    FindingDetail,
    FindingSummary,
    RunView,
    Scope,
    WitnessView,
    WorldView,
)
from ..witnesses.signature import origin_frame

SUMMARY_SQL = (
    "SELECT f.id, f.analysis_id, f.cell_id, f.verdict, f.headline, f.created_at, a.mode, r.name AS artifact, "
    "a.id AS aid, c.test_world_hash, c.ref_world_hash FROM finding f JOIN analysis a ON a.id = f.analysis_id "
    "JOIN cell c ON c.id = f.cell_id JOIN project p ON p.id = c.artifact_project_id "
    "JOIN snapshot s ON s.id = p.snapshot_id JOIN repository r ON r.id = s.repository_id")


def _consumer_name(conn: sqlite3.Connection, analysis_id: str) -> str:
    # fixture analysis ids end with the consumer name hash; the human name is stored on the analysis_project name only
    # for the project, so the consumer is read from the finding's oracle plan instead (kept in cell_consumer later)
    row = conn.execute("SELECT options_json FROM analysis WHERE id=?", (analysis_id,)).fetchone()
    named = json.loads(row["options_json"] or "{}").get("consumer") if row else None
    if named:
        return named
    # live analyses: the consumers linked to the cells of this analysis
    names = sorted({f"{x['owner']}/{x['name']}" for x in conn.execute(
        "SELECT r.owner, r.name FROM cell_consumer cc JOIN cell c ON c.id = cc.cell_id JOIN project p ON p.id = cc.consumer_project_id "
        "JOIN snapshot s ON s.id = p.snapshot_id JOIN repository r ON r.id = s.repository_id WHERE c.analysis_id=?", (analysis_id,))})
    return ", ".join(names) or "consumer"


def _summary(conn: sqlite3.Connection, r: sqlite3.Row) -> FindingSummary:
    wits = [x["evidence_id"] for x in conn.execute(
        "SELECT evidence_id FROM finding_evidence WHERE finding_id=? AND evidence_kind='WITNESS' ORDER BY evidence_id", (r["id"],))]
    return FindingSummary(finding_id=r["id"], analysis_id=r["analysis_id"], cell_id=r["cell_id"], mode=r["mode"],
                          verdict=r["verdict"], headline=r["headline"], artifact=r["artifact"],
                          consumer=_consumer_name(conn, r["analysis_id"]), created_at=r["created_at"], witness_ids=wits)


def list_findings(conn: sqlite3.Connection) -> list[FindingSummary]:
    rows = conn.execute(SUMMARY_SQL + " ORDER BY f.priority, f.created_at DESC, f.id").fetchall()
    return [_summary(conn, r) for r in rows]


def _world(conn: sqlite3.Connection, world_hash: str) -> WorldView:
    w = conn.execute("SELECT * FROM resolved_world WHERE world_hash=?", (world_hash,)).fetchone()
    n = conn.execute("SELECT COUNT(*) FROM world_entry WHERE world_hash=?", (world_hash,)).fetchone()[0]
    rt = json.loads(w["runtime_json"])
    return WorldView(world_hash=world_hash, kind=w["kind"], runtime=f"{rt['name']} {rt['version']}",
                     env_profile_id=w["env_profile_id"], package_count=n)


def _packages(conn: sqlite3.Connection, world_hash: str) -> list[dict]:
    return [{"name": r["name"], "version": r["version"]} for r in conn.execute(
        "SELECT pv.name, pv.version FROM world_entry we JOIN package_version pv ON pv.id = we.package_version_id "
        "WHERE we.world_hash=? ORDER BY pv.name", (world_hash,))]


def _entry_view(e: dict) -> EntryView:
    f = origin_frame(e.get("frames") or [])
    return EntryView(entry=e["entry"], passed=bool(e.get("passed")), skipped=bool(e.get("skipped")),
                     not_applicable=bool(e.get("not_applicable")), failure_class=e.get("failure_class", "NONE"),
                     exc_type=e.get("exc_type"), message=e.get("message"), origin_module=(f or {}).get("module"))


def get_finding(conn: sqlite3.Connection, finding_id: str, bundle_url: str | None = None) -> FindingDetail:
    r = conn.execute(SUMMARY_SQL + " WHERE f.id=?", (finding_id,)).fetchone()
    if r is None:
        raise NotFoundError(f"finding {finding_id} not found")
    base = _summary(conn, r)
    ref_pk, test_pk = _packages(conn, r["ref_world_hash"]), _packages(conn, r["test_world_hash"])
    rv = {p["name"]: p["version"] for p in ref_pk}
    tv = {p["name"]: p["version"] for p in test_pk}
    delta = [DeltaItem(name=n, reference=rv.get(n), consumer=tv.get(n)) for n in sorted(set(rv) | set(tv)) if rv.get(n) != tv.get(n)]
    run_ids = [x["evidence_id"] for x in conn.execute(
        "SELECT evidence_id FROM finding_evidence WHERE finding_id=? AND evidence_kind='ORACLE_RUN'", (finding_id,))]
    runs: list[RunView] = []
    for rid in run_ids:
        row = conn.execute("SELECT r.*, j.side FROM oracle_run r JOIN oracle_job j ON j.id = r.oracle_job_id WHERE r.id=?",
                           (rid,)).fetchone()
        res = json.loads(row["result_json"])
        runs.append(RunView(run_id=rid, side=row["side"], run_index=row["run_index"], provenance=row["provenance"],
                            failure_class=row["failure_class"], duration_ms=row["duration_ms"] or 0,
                            entries=[_entry_view(e) for e in res.get("entries", [])],
                            stdout_tail=res.get("stdout_tail", ""), stderr_tail=res.get("stderr_tail", "")))
    runs.sort(key=lambda x: (0 if x.side == "ref" else 1, x.run_index))
    witnesses = []
    for wid in base.witness_ids:
        w = conn.execute("SELECT * FROM witness WHERE id=?", (wid,)).fetchone()
        body = json.loads(w["body_json"])
        witnesses.append(WitnessView(
            witness_id=wid, witness_class=w["class"], oracle=w["oracle"], oracle_version=w["oracle_version"],
            entry_point=w["entry_point"], divergence=w["divergence"], ref_pass=w["ref_pass"], test_fail=w["test_fail"],
            signature=FailureSignature.model_validate_json(w["signature_json"]), ref_run_ids=body["ref_run_ids"],
            test_run_ids=body["test_run_ids"], reverifications=len(body.get("reverifications", []))))
    f = conn.execute("SELECT scope_json FROM finding WHERE id=?", (finding_id,)).fetchone()
    scope = json.loads(f["scope_json"])
    return FindingDetail(
        **base.model_dump(), reference=_world(conn, r["ref_world_hash"]), consumer_world=_world(conn, r["test_world_hash"]),
        delta=delta, runs=runs, witnesses=witnesses,
        scope=Scope(exercised=scope["exercised"], not_applicable=scope["not_applicable"], not_checked=scope["not_checked"],
                    reasons=scope["reasons"], policy=scope["policy"]),
        fresh_runs=sum(1 for x in runs if x.provenance == "FRESH_EXECUTION"),
        reused_runs=sum(1 for x in runs if x.provenance == "REUSED_RESULT"),
        bundle_url=(bundle_url if witnesses else None))
