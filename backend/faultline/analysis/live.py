"""The live pipeline: ingested repositories -> relationships -> reference/projected worlds -> cells -> oracle runs ->
witnesses -> findings. Same machinery as the fixture pipeline, but every input comes from pinned snapshots of real repositories.
"""
import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..attribution.runner import attribute, persist
from ..core.enums import FailureClass, WorldKind
from ..core.errors import Cancelled, LeaseLost
from ..core.ids import new_id
from ..core.logging import phase
from ..core.models import OracleRunResult
from ..ingestion.clone import load_inventory
from ..oracles import planner
from ..oracles.artifacts import prepare_artifact
from ..oracles.o_import import ORACLE, ORACLE_VERSION, plan_modules, run_o_import
from ..relationships.engine import create_analysis, discover
from ..resolvers.pinned import render_lock
from ..sandbox.client import SandboxClient
from ..storage.store import Store
from ..usage.consumer_imports import artifact_modules, scan_imports
from ..verdicts import templates
from ..verdicts.engine import LIVE_POLICY_VERSION, LIVE_PRIORITY, Evidence, decide
from ..verdicts.stats import funnel
from ..witnesses.verify import INFRA_CLASSES, Verification, verify_cell
from ..worlds.builder import WorldBuilder, WorldBuildError
from ..worlds.cells import CellPlan, persist_cell, plan_cells
from .fixture import FixtureCell
from .lifecycle import mark_partial, reconcile_abandoned

RETRIES = 2


@dataclass(frozen=True)
class LiveResult:
    analysis_id: str
    cells: list[dict]
    funnel: dict


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _project_layout(conn: sqlite3.Connection, project_id: str) -> dict:
    p = conn.execute("SELECT p.rel_path, p.layout_json, p.published_name, s.store_path FROM project p JOIN snapshot s ON s.id=p.snapshot_id WHERE p.id=?",
                     (project_id,)).fetchone()
    layout = json.loads(p["layout_json"] or "{}")
    return {"rel_path": p["rel_path"], "store_path": p["store_path"], "name": p["published_name"], **layout}


def retrying(run: Callable[[], OracleRunResult], checkpoint: Callable[[], None] | None = None) -> Callable[[], OracleRunResult]:
    """Infrastructure failures are retried; they are never evidence about the artifact. `checkpoint` raises Cancelled when the job was cancelled, so a killed container is not retried."""
    def go() -> OracleRunResult:
        last = run()
        for _ in range(RETRIES):
            if last.failure_class not in INFRA_CLASSES or last.entries:
                break
            if checkpoint:
                checkpoint()
            last = run()
        return last
    return go


def _primary_package(layout: dict) -> str | None:
    pkgs = layout.get("import_packages") or []
    want = (layout.get("name") or "").replace("-", "_")
    return want if want in pkgs else (pkgs[0] if pkgs else None)


def run_live_analysis(conn: sqlite3.Connection, sbx: SandboxClient, image: str, store: Store, analysis_project_id: str, *,
                      progress: Callable[[float, str], None] | None = None, job_id: str | None = None) -> LiveResult:
    """Wraps the work so that a cancelled, interrupted or failed run is closed and labelled with its partial evidence kept."""
    say = progress or (lambda f, m: None)
    if job_id:
        reconcile_abandoned(conn, job_id)
    aid = create_analysis(conn, analysis_project_id, options={"job_id": job_id} if job_id else None)
    try:
        return _run_live(conn, sbx, image, store, analysis_project_id, aid, say)
    except LeaseLost:
        mark_partial(conn, aid, "INTERRUPTED", "the worker lost its lease while running; the job was taken over as a new analysis")
        raise
    except Cancelled:
        mark_partial(conn, aid, "CANCELLED", "cancelled by the user; partial evidence is kept and no finding is claimed for unfinished cells")
        raise
    except Exception as exc:
        mark_partial(conn, aid, "ERROR", f"{type(exc).__name__}: {str(exc)[:200]}")
        raise


def _run_live(conn, sbx, image, store, analysis_project_id, aid, say) -> LiveResult:
    say(0.05, "discovering relationships")
    with phase("discover relationships", analysis=aid):
        rels = discover(conn, store, aid, analysis_project_id)
    builder = WorldBuilder(sbx, image, conn)
    edge_cache: dict[str, dict] = {}

    def closure_of(pinned, roots):
        from ..core.hashing import object_hash
        from ..worlds.closure import closure
        key = object_hash([(p.name, p.version, list(p.hashes)) for p in pinned])
        if key not in edge_cache:
            edge_cache[key] = builder.edges(list(pinned))
        return closure(list(pinned), roots, edge_cache[key])

    planned = plan_cells(conn, rels, closure_of)
    failed = list(planned.failed)
    conn.execute("UPDATE analysis SET status='BUILDING_CELLS' WHERE id=?", (aid,))
    out_cells: list[dict] = []
    ref_built: dict[str, str] = {}
    n = max(1, len(planned.cells))
    for i, plan in enumerate(planned.cells):
        base = 0.1 + 0.85 * i / n
        layout = _project_layout(conn, plan.producer_project_id)
        pkg = _primary_package(layout)
        if pkg is None:
            failed += [{"consumer": c, "producer": plan.producer_project_id, "reason": "no_import_package",
                        "text": "the artifact exposes no importable Python package", "side": "reference"} for c, _ in plan.consumers]
            continue
        try:
            say(base, f"building the reference world for {layout['name'] or layout['rel_path']}")
            ref_key = plan.reference.world_hash
            if ref_key not in ref_built:
                text = render_lock(list(plan.reference.pinned))
                ref_world = builder.materialize(text, WorldKind.REFERENCE)
                if builder.build(ref_world, text).status == "FAILED":
                    raise WorldBuildError("the reference world could not be built offline", details={"reason": "reference_build_failed"})
                ref_built[ref_key] = ref_world.world_hash
            plan = CellPlan(plan.producer_project_id, plan.projection, _with_hash(plan.reference, ref_built[ref_key]), plan.consumers)
            test_hash = None
            if not plan.projection.no_drift:
                say(base + 0.02 / n, "building the projected consumer world")
                text = plan.projection.lock_text
                w = builder.materialize(text, WorldKind.PROJECTED)
                if builder.build(w, text).status == "FAILED":
                    raise WorldBuildError("the projected world could not be built offline", details={"reason": "world_build_failed"})
                test_hash = w.world_hash
        except WorldBuildError as e:
            failed += [{"consumer": c, "producer": plan.producer_project_id, "reason": e.details.get("reason", "world_build_failed"),
                        "text": e.message, "side": "reference" if "reference" in str(e.details.get("reason")) else "consumer"} for c, _ in plan.consumers]
            continue

        # PC-4: which artifact modules do the consumers actually import?
        prod_root = store.snapshot_dir(layout["store_path"])
        prod_inv = load_inventory(Path(prod_root))
        src_root = (layout.get("source_roots") or ["."])[0]
        known = artifact_modules(prod_root, prod_inv["entries"], src_root, pkg)
        imported: dict[str, list[str]] = {}
        for cid_, _rid in plan.consumers:
            cl = _project_layout(conn, cid_)
            cdir = store.snapshot_dir(cl["store_path"])
            scan = scan_imports(Path(cdir), load_inventory(Path(cdir))["entries"], pkg, known, under=cl["rel_path"])
            imported[cid_] = scan.modules
        cell_id = persist_cell(conn, aid, plan, test_hash, imported)
        if plan.projection.no_drift:
            out_cells.append({"cell_id": cell_id, "state": "NO_DRIFT", "finding_id": None, "consumers": [c for c, _ in plan.consumers]})
            continue

        fid, state = execute_cell(conn, sbx, image, store, builder, aid, cell_id, plan, layout, pkg, imported, test_hash, rels, say, base, n,
                                  prod_root=prod_root, prod_inv=prod_inv, src_root=src_root)
        out_cells.append({"cell_id": cell_id, "state": state, "finding_id": fid, "consumers": [c for c, _ in plan.consumers]})
    conn.execute("UPDATE analysis SET status='DONE', finished_at=?, stats_json=? WHERE id=?",
                 (_now(), json.dumps({"failed_consumers": failed}, sort_keys=True), aid))
    return LiveResult(aid, out_cells, funnel(conn, aid))


def execute_cell(conn, sbx, image, store, builder, aid, cell_id, plan, layout, pkg, imported, test_hash, rels, say, base, n, *, prod_root, prod_inv, src_root):
    """Run the oracle 3 + 3 times on one cell, attribute any witness, and write the finding. Returns (finding_id, cell_state)."""
    art_dir = Path(prod_root) / layout["rel_path"] if layout["rel_path"] != "." else Path(prod_root)
    artifact = prepare_artifact(art_dir, store)
    conn.execute("UPDATE project SET artifact_content_hash=? WHERE id=?", (artifact, plan.producer_project_id))
    pyroot = Path(src_root).relative_to(layout["rel_path"]).as_posix() if layout["rel_path"] != "." and src_root.startswith(layout["rel_path"]) else src_root
    pythonpath = "/artifact" if pyroot in (".", "") else f"/artifact/{pyroot}"
    modules = plan_modules(pkg, sorted({m for ms in imported.values() for m in ms if m != pkg}))
    env_id = builder.env_profile_id if hasattr(builder, "env_profile_id") else _env_id(builder)
    cell = FixtureCell(aid, cell_id, plan.producer_project_id, plan.reference.world_hash, test_hash, artifact, env_id)
    say(base + 0.05 / n, f"running O-import (3 + 3 fresh runs) on {', '.join(modules)}")

    def run(world_hash: str, modules=modules, artifact=artifact, pkg=pkg, pythonpath=pythonpath):
        return retrying(lambda: run_o_import(sbx, image, world_hash=world_hash, artifact_hash=artifact, top_level=pkg,
                                             modules=modules, pythonpath=(pythonpath,)),
                        checkpoint=lambda: say(base + 0.05 / n, "checking whether the job was cancelled"))()

    with phase("verify (3 + 3 fresh runs)", cell=cell_id):
        v = verify_cell(conn, cell, oracle=ORACLE, version=ORACLE_VERSION, run_in_world=run, args={"modules": modules, "pythonpath": pythonpath}, force=True)
    say(base + 0.09 / n, "recording the verified result")                      # raises Cancelled here, before any finding is written for a killed run
    has_tests = any(e["path"].startswith(("tests/", "test/")) for e in prod_inv["entries"])
    for dec in v.witnesses:
        if dec.witness_id and dec.signature is not None:
            say(base + 0.1 / n, f"attributing the break in {dec.entry} (two-sided search)")
            with phase("attribute (two-sided ddmin)", cell=cell_id, entry=dec.entry):
                a = attribute(sbx, image, builder, artifact_hash=artifact, entry=dec.entry, top_level=pkg, pythonpath=pythonpath, signature=dec.signature,
                              ref=list(plan.reference.pinned), consumer=list(plan.projection.pinned), delta=[d.name for d in plan.projection.delta])
            persist(conn, dec.witness_id, a)
    steps = planner.after_import(planner.plan(pkg, modules, has_tests=has_tests, test_lock=False), pkg, v)
    fid = write_live_finding(conn, aid, cell, v, layout, plan, steps, rels)
    state = "ANALYZED" if v.decisions else "INCONCLUSIVE"
    conn.execute("UPDATE cell SET state=? WHERE id=?", (state, cell_id))
    return fid, state


def _with_hash(ref, world_hash: str):
    from dataclasses import replace
    return replace(ref, world_hash=world_hash)


def _env_id(builder: WorldBuilder) -> str:
    from ..core.hashing import env_profile_id
    return env_profile_id(builder.env)


def write_live_finding(conn: sqlite3.Connection, analysis_id: str, cell: FixtureCell, v: Verification, layout: dict, plan: CellPlan,
                       steps: list[planner.Step], rels) -> str:
    consumers = [conn.execute("SELECT p.rel_path, r.owner, r.name FROM project p JOIN snapshot s ON s.id=p.snapshot_id JOIN repository r ON r.id=s.repository_id "
                              "WHERE p.id=?", (c,)).fetchone() for c, _ in plan.consumers]
    names = [f"{c['owner']}/{c['name']}" for c in consumers]
    rel_levels = {r.consumer_project_id: r.level for r in rels if r.producer_project_id == plan.producer_project_id}
    level = "L2" if all(rel_levels.get(c) in ("L2", "L3", "L4", "L5") for c, _ in plan.consumers) else "L1"
    out = decide(Evidence(relationship_level=level, cell_state="PENDING", decisions=tuple(v.decisions), run_problem=v.problem))
    artifact = layout["name"] or layout["rel_path"]
    kw = {"artifact": artifact, "consumers": names, "exercised": out.exercised, "reasons": out.reasons}
    if out.outcome == "BREAK_WITNESSED":
        dec = next(x for x in v.decisions if x.entry == out.witness_entries[0])
        kw.update(entry=dec.entry, exc=dec.signature.exc_type, message=dec.signature.message_norm)
    headline = templates.live_headline(out.outcome, **kw)
    conn.execute("DELETE FROM finding_evidence WHERE finding_id IN (SELECT id FROM finding WHERE cell_id=?)", (cell.cell_id,))
    conn.execute("DELETE FROM finding WHERE cell_id=?", (cell.cell_id,))
    fid = new_id("fnd")
    verdict = out.verdict
    scope = {"exercised": list(out.exercised), "not_applicable": list(out.not_applicable), "not_checked": list(templates.NOT_CHECKED_LIVE),
             "reasons": list(out.reasons), "policy": LIVE_POLICY_VERSION, "oracle_plan": planner.as_json(steps), "consumers": names,
             "delta": [{"name": d.name, "reference": d.reference, "consumer": d.consumer} for d in plan.projection.delta]}
    conn.execute("INSERT INTO finding(id, analysis_id, scope_kind, cell_id, verdict, sub_label, headline, scope_json, priority, created_at) "
                 "VALUES (?,?, 'ARTIFACT_CELL', ?,?,?,?,?,?,?)",
                 (fid, analysis_id, cell.cell_id, verdict.value, out.sub_label, headline, json.dumps(scope, sort_keys=True), LIVE_PRIORITY[verdict], _now()))
    for d in v.decisions:
        if d.witness_id:
            conn.execute("INSERT OR IGNORE INTO finding_evidence(finding_id, evidence_kind, evidence_id) VALUES (?, 'WITNESS', ?)", (fid, d.witness_id))
    for r in v.ref_runs + v.test_runs:
        conn.execute("INSERT OR IGNORE INTO finding_evidence(finding_id, evidence_kind, evidence_id) VALUES (?, 'ORACLE_RUN', ?)", (fid, r.run_id))
    for _c, rid in plan.consumers:
        conn.execute("INSERT OR IGNORE INTO finding_evidence(finding_id, evidence_kind, evidence_id) VALUES (?, 'RELATIONSHIP', ?)", (fid, rid))
    return fid


__all__ = ["run_live_analysis", "LiveResult", "FailureClass", "OracleRunResult"]
