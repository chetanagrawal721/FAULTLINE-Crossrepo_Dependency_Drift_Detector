"""Read models for a live analysis, built only from persisted rows: nothing here is computed on the fly or mocked."""
import json
import sqlite3

from ..core.errors import NotFoundError
from ..core.views import (
    AnalysisView,
    AttemptView,
    AttributionView,
    CellView,
    DeltaLine,
    EvidenceLine,
    FailedConsumer,
    OraclePlanStep,
    RelationshipView,
)
from ..verdicts.stats import funnel


def _label(conn: sqlite3.Connection, project_id: str) -> str:
    r = conn.execute("SELECT p.rel_path, r.owner, r.name FROM project p JOIN snapshot s ON s.id=p.snapshot_id JOIN repository r ON r.id=s.repository_id "
                     "WHERE p.id=?", (project_id,)).fetchone()
    if r is None:
        return project_id
    return f"{r['owner']}/{r['name']}" + ("" if r["rel_path"] == "." else f":{r['rel_path']}")


def _commit(conn: sqlite3.Connection, project_id: str) -> str:
    r = conn.execute("SELECT s.sha FROM project p JOIN snapshot s ON s.id=p.snapshot_id WHERE p.id=?", (project_id,)).fetchone()
    return r["sha"] if r else ""


def latest_analysis_id(conn: sqlite3.Connection, project_id: str) -> str | None:
    r = conn.execute("SELECT id FROM analysis WHERE analysis_project_id=? AND mode IN ('LIVE','REPLAY') ORDER BY started_at DESC, rowid DESC LIMIT 1", (project_id,)).fetchone()
    return r["id"] if r else None


def analysis_view(conn: sqlite3.Connection, analysis_id: str) -> AnalysisView:
    a = conn.execute("SELECT * FROM analysis WHERE id=?", (analysis_id,)).fetchone()
    if a is None:
        raise NotFoundError(f"analysis {analysis_id} not found")
    rels = []
    for r in conn.execute("SELECT * FROM relationship WHERE analysis_id=? ORDER BY actionable DESC, level, id", (analysis_id,)):
        ev = [EvidenceLine(signal=e["signal"], repository=_label(conn, e["project_id"]).split(":")[0], commit=_commit(conn, e["project_id"]),
                           file_path=e["file_path"] or "", line=e["line"], excerpt=e["excerpt"])
              for e in conn.execute("SELECT * FROM relationship_evidence WHERE relationship_id=? ORDER BY id", (r["id"],))]
        rels.append(RelationshipView(id=r["id"], producer=_label(conn, r["producer_project_id"]), consumer=_label(conn, r["consumer_project_id"]),
                                     level=r["level"], kind=r["kind"], confidence=r["confidence"], actionable=bool(r["actionable"]), status=r["status"],
                                     notes=json.loads(r["shared_symbols_json"] or "[]"), evidence=ev))
    cells = []
    for c in conn.execute("SELECT * FROM cell WHERE analysis_id=? ORDER BY id", (analysis_id,)):
        cons = conn.execute("SELECT consumer_project_id, imported_modules_json FROM cell_consumer WHERE cell_id=?", (c["id"],)).fetchall()
        mods = sorted({m for x in cons for m in json.loads(x["imported_modules_json"] or "[]")})
        delta = [DeltaLine(name=d["name"], reference=d["v_ref"], consumer=d["v_test"], kind=d["kind"])
                 for d in conn.execute("SELECT * FROM delta_entry WHERE cell_id=? ORDER BY name", (c["id"],))]
        f = conn.execute("SELECT id, verdict, headline, scope_json FROM finding WHERE cell_id=?", (c["id"],)).fetchone()
        plan = [OraclePlanStep(oracle=p["oracle"], status=p["status"], reason=p.get("reason", ""), entries=list(p.get("entries", [])))
                for p in (json.loads(f["scope_json"] or "{}").get("oracle_plan", []) if f else [])]
        att = _attribution(conn, c["id"])
        cells.append(CellView(id=c["id"], state=c["state"], ref_world_hash=c["ref_world_hash"], test_world_hash=c["test_world_hash"],
                              consumers=[_label(conn, x["consumer_project_id"]) for x in cons], imported_modules=mods, delta=delta,
                              finding_id=f["id"] if f else None, verdict=f["verdict"] if f else None, headline=f["headline"] if f else None,
                              attribution=att, oracle_plan=plan))
    stats = json.loads(a["stats_json"] or "{}")
    failed = [FailedConsumer(consumer=_label(conn, x["consumer"]), producer=_label(conn, x["producer"]), side=x["side"], reason=x["reason"], text=x["text"])
              for x in stats.get("failed_consumers", [])]
    return AnalysisView(id=a["id"], project_id=a["analysis_project_id"], status=a["status"], outcome=stats.get("outcome"), partial_note=stats.get("reason"), mode=a["mode"], started_at=a["started_at"],
                        finished_at=a["finished_at"], funnel=funnel(conn, analysis_id), failed=failed, relationships=rels, cells=cells)


def _attribution(conn: sqlite3.Connection, cell_id: str) -> AttributionView | None:
    # Found through the cell's own finding, not through witness.cell_id: when the same repositories are analysed again, the witness is the earlier
    # one (same artifact, same worlds, same entry), so its cell is the earlier cell. The finding of THIS analysis still lists it as its evidence.
    a = conn.execute("SELECT a.* FROM attribution a JOIN finding_evidence fe ON fe.evidence_id = a.witness_id AND fe.evidence_kind = 'WITNESS' "
                     "JOIN finding f ON f.id = fe.finding_id WHERE f.cell_id=? ORDER BY fe.rowid ASC LIMIT 1", (cell_id,)).fetchone()
    if a is None:
        return None
    meta = json.loads(a["notes_json"] or "{}")
    label = meta.get("label", "attribution experiment (forced world)")
    minimal = json.loads(a["minimal_set_json"] or "[]")
    claim = "minimal (among the tested subsets, 1-minimal)" if a["status"] == "COMPLETE" and a["sidedness"] == "two_sided" and minimal else None
    attempts = [AttemptView(direction=t["direction"], subset=json.loads(t["subset_json"]), outcome=t["outcome"], note=t["note"], label=label)
                for t in conn.execute("SELECT * FROM attribution_attempt WHERE attribution_id=? ORDER BY seq", (a["id"],))]
    return AttributionView(status=a["status"], sidedness=a["sidedness"], minimal=minimal, minimal_claim=claim, notes=meta.get("notes", []), attempts=attempts)
