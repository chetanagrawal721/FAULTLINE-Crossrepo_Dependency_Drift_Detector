"""Time-machine analysis: one pinned repository, its dependency world resolved at two dates, and the same checks as any cell.

This reproduces a publicly reported break that happened because a dependency released a new major version AFTER the project:
the artifact is run in the world resolved before the release (the reference) and in the world resolved after it. The comparison
is a user-DECLARED relationship (level L5), labelled as such; both resolution cutoffs are recorded in the provenance.
"""
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..ingestion.clone import load_inventory
from ..parsers.common import SnapshotFS
from ..parsers.python.discover import discover_python
from ..relationships.engine import create_analysis
from ..resolvers.pinned import render_lock
from ..sandbox.client import SandboxClient
from ..storage.store import Store
from ..verdicts.stats import funnel
from ..worlds.builder import WorldBuilder
from ..worlds.canonical import ResolutionContext, ensure_project_world
from ..worlds.cells import CellPlan, artifact_roots, persist_cell
from ..worlds.closure import closure
from ..worlds.projection import project
from ..worlds.reference import ReferenceWorld
from .live import _now, _primary_package, _project_layout, execute_cell


@dataclass
class TimeMachineResult:
    analysis_id: str
    cell_id: str
    finding_id: str | None
    state: str
    reference_cutoff: str
    consumer_cutoff: str
    funnel: dict


def run_time_machine(conn: sqlite3.Connection, sbx: SandboxClient, image: str, store: Store, repository_id: str, *, reference_cutoff: str,
                     consumer_cutoff: str, project_rel: str = ".", say=None) -> TimeMachineResult:
    say = say or (lambda f, m: None)
    repo = conn.execute("SELECT * FROM repository WHERE id=?", (repository_id,)).fetchone()
    snap = conn.execute("SELECT * FROM snapshot WHERE repository_id=? AND sha=?", (repository_id, repo["pinned_sha"])).fetchone()
    root = Path(store.snapshot_dir(snap["store_path"]))
    fs = SnapshotFS(root)
    inv = load_inventory(root)
    prj = next(p for p in discover_python(root, inv).projects if p.rel_path == project_rel)
    say(0.05, f"resolving the project as of {reference_cutoff} (reference) and {consumer_cutoff} (consumer)")
    ref_pw = ensure_project_world(conn, sbx, image, snap["id"], fs, prj, ResolutionContext(cutoff=reference_cutoff))
    con_pw = ensure_project_world(conn, sbx, image, snap["id"], fs, prj, ResolutionContext(cutoff=consumer_cutoff))
    if ref_pw.status != "OK" or con_pw.status != "OK":
        raise ValueError(f"could not resolve both worlds: reference {ref_pw.status} {ref_pw.outcome.failure}, consumer {con_pw.status} {con_pw.outcome.failure}")
    pid = ref_pw.project_id
    builder = WorldBuilder(sbx, image, conn)
    ref_pinned, con_pinned = list(ref_pw.outcome.pinned), list(con_pw.outcome.pinned)
    ref_text = render_lock(ref_pinned)
    ref_world = builder.materialize(ref_text)
    builder.build(ref_world, ref_text)
    layout = _project_layout(conn, pid)
    pkg = _primary_package(layout)
    roots = artifact_roots(conn, pid, frozenset())
    ref = ReferenceWorld(pid, ref_world.world_hash, tuple(ref_pinned), "resolver", {"cutoff": reference_cutoff})
    proj = project(ref, con_pinned, ref_names=closure(ref_pinned, roots, builder.edges(ref_pinned)), consumer_names=closure(con_pinned, roots, builder.edges(con_pinned)))
    aid = create_analysis(conn, repo["analysis_project_id"], "LIVE", {"time_machine": {"reference": reference_cutoff, "consumer": consumer_cutoff}})
    rel_id = "rel_tm_" + aid[-16:]
    conn.execute("INSERT INTO relationship(id, analysis_id, producer_project_id, consumer_project_id, kind, level, confidence, actionable, status, shared_symbols_json) "
                 "VALUES (?,?,?,?, 'DECLARED', 'L5', 'HIGH', 1, 'ACTIVE', ?)",
                 (rel_id, aid, pid, pid, json.dumps([f"user-declared time-machine comparison: world resolved at {reference_cutoff} versus {consumer_cutoff}"])))
    conn.execute("INSERT INTO relationship_evidence(id, relationship_id, signal, project_id, file_path, line, excerpt) VALUES (?,?,?,?,?,?,?)",
                 ("re_tm_" + aid[-16:], rel_id, "declared", pid, "(user-supplied)", None, f"reference cutoff {reference_cutoff}; consumer cutoff {consumer_cutoff}"))
    if proj.no_drift:
        plan = CellPlan(pid, proj, ref, [(pid, rel_id)])
        cid = persist_cell(conn, aid, plan, None, {pid: [pkg]})
        conn.execute("UPDATE analysis SET status='DONE', finished_at=? WHERE id=?", (_now(), aid))
        return TimeMachineResult(aid, cid, None, "NO_DRIFT", reference_cutoff, consumer_cutoff, funnel(conn, aid))
    text = proj.lock_text
    w = builder.materialize(text)
    builder.build(w, text)
    plan = CellPlan(pid, proj, ref, [(pid, rel_id)])
    src_root = (layout.get("source_roots") or ["."])[0]
    cid = persist_cell(conn, aid, plan, w.world_hash, {pid: [pkg]})
    rels = [type("R", (), {"consumer_project_id": pid, "producer_project_id": pid, "level": "L5"})()]
    fid, state = execute_cell(conn, sbx, image, store, builder, aid, cid, plan, layout, pkg, {pid: [pkg]}, w.world_hash, rels, say, 0.1, 1,
                              prod_root=root, prod_inv=inv, src_root=src_root)
    conn.execute("UPDATE analysis SET status='DONE', finished_at=? WHERE id=?", (_now(), aid))
    return TimeMachineResult(aid, cid, fid, state, reference_cutoff, consumer_cutoff, funnel(conn, aid))
