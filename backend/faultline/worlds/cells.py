"""Cells: one per unique effective projection, with consumer links and exact deltas.

A consumer whose world cannot be projected stays in the discovered count as failed, with its reason. A cell is never a
compatibility score: coverage is the count of discovered versus analysed consumers.
"""
import json
import sqlite3
from dataclasses import dataclass, field

from ..core.hashing import object_hash
from ..resolvers.pinned import PinnedRequirement
from .projection import Projection, project
from .reference import ReferenceFailure, ReferenceWorld, select_reference


@dataclass
class CellPlan:
    producer_project_id: str
    projection: Projection
    reference: ReferenceWorld
    consumers: list[tuple[str, str]] = field(default_factory=list)       # (consumer_project_id, relationship_id)


@dataclass
class Planned:
    cells: list[CellPlan] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)                    # {consumer, producer, reason, text}


def consumer_pinned(conn: sqlite3.Connection, project_id: str) -> list[PinnedRequirement] | dict:
    """The consumer's resolved runtime world, or a failure dict {reason, text} when it has none."""
    pw = conn.execute("SELECT * FROM project_world WHERE project_id=? ORDER BY resolved_at DESC LIMIT 1", (project_id,)).fetchone()
    if pw is None:
        return {"reason": "not_resolved", "text": "the consumer's world has not been resolved"}
    if pw["status"] == "FAILED" or not pw["world_hash"]:
        f = json.loads(pw["failure_json"]) if pw["failure_json"] else {}
        return {"reason": f.get("reason", "unknown"), "text": f.get("detail") or "resolution failed"}
    args = json.loads(pw["resolver_args_json"] or "{}")
    row = conn.execute("SELECT outcome_json FROM resolution_cache WHERE cache_key=?", (args.get("cache_key"),)).fetchone()
    pinned = json.loads(row["outcome_json"]).get("pinned", []) if row else []
    if not pinned:
        return {"reason": "empty_world", "text": "the consumer's world has no packages"}
    if pw["status"] == "OK_PARTIAL":
        return {"reason": "private_packages", "text": "the consumer's world includes private packages that are never fetched"}
    return [PinnedRequirement(n, dn, v, tuple(h)) for n, dn, v, h in pinned]


def plan_cells(conn: sqlite3.Connection, relationships) -> Planned:
    out = Planned()
    refs: dict[str, ReferenceWorld | ReferenceFailure] = {}
    groups: dict[tuple[str, str], CellPlan] = {}
    for rel in relationships:
        if not rel.actionable:
            continue
        ref = refs.setdefault(rel.producer_project_id, select_reference(conn, rel.producer_project_id))
        if isinstance(ref, ReferenceFailure):
            out.failed.append({"consumer": rel.consumer_project_id, "producer": rel.producer_project_id, "reason": ref.reason,
                               "text": "reference world unavailable: " + ref.text, "side": "reference"})
            continue
        cw = consumer_pinned(conn, rel.consumer_project_id)
        if isinstance(cw, dict):
            out.failed.append({"consumer": rel.consumer_project_id, "producer": rel.producer_project_id, "reason": cw["reason"],
                               "text": cw["text"], "side": "consumer"})
            continue
        proj = project(ref, cw)
        key = (rel.producer_project_id, proj.key)
        plan = groups.setdefault(key, CellPlan(rel.producer_project_id, proj, ref))
        plan.consumers.append((rel.consumer_project_id, rel.id))
    out.cells = list(groups.values())
    return out


def persist_cell(conn: sqlite3.Connection, analysis_id: str, plan: CellPlan, test_world_hash: str | None,
                 imported: dict[str, list[str]] | None = None) -> str:
    """Insert the cell, its delta and its consumer links. NO_DRIFT cells reuse the reference world and queue no oracle."""
    no_drift = plan.projection.no_drift
    test_hash = plan.reference.world_hash if no_drift else test_world_hash
    cid = "cell_" + object_hash([analysis_id, plan.producer_project_id, plan.projection.key])[:24]
    conn.execute("INSERT OR REPLACE INTO cell(id, analysis_id, artifact_project_id, ref_world_hash, test_world_hash, state, forced_overlay) "
                 "VALUES (?,?,?,?,?,?,0)", (cid, analysis_id, plan.producer_project_id, plan.reference.world_hash, test_hash,
                                            "NO_DRIFT" if no_drift else "PENDING"))
    conn.execute("DELETE FROM delta_entry WHERE cell_id=?", (cid,))
    for d in plan.projection.delta:
        kind = "ADDED" if d.reference is None else "REMOVED" if d.consumer is None else "CHANGED"
        conn.execute("INSERT INTO delta_entry(cell_id, name, v_ref, v_test, kind) VALUES (?,?,?,?,?)", (cid, d.name, d.reference, d.consumer, kind))
    for consumer_id, rel_id in plan.consumers:
        conn.execute("INSERT OR REPLACE INTO cell_consumer(cell_id, consumer_project_id, relationship_id, imported_modules_json) VALUES (?,?,?,?)",
                     (cid, consumer_id, rel_id, json.dumps((imported or {}).get(consumer_id, []))))
    return cid
