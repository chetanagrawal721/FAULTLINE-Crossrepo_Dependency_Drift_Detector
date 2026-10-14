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
from ..oracles import o_contract, planner
from ..oracles.artifacts import prepare_artifact
from ..oracles.o_bind import ORACLE as BIND_ORACLE
from ..oracles.o_bind import ORACLE_VERSION as BIND_VERSION
from ..oracles.o_bind import run_o_bind, site_payload
from ..oracles.o_import import ORACLE, ORACLE_VERSION, plan_modules, run_o_import
from ..oracles.o_tests import ORACLE as TESTS_ORACLE
from ..oracles.o_tests import ORACLE_VERSION as TESTS_VERSION
from ..oracles.o_tests import run_o_tests
from ..relationships.engine import create_analysis, discover
from ..resolvers.pinned import parse_pinned_lock, render_lock
from ..sandbox.client import SandboxClient
from ..storage.store import Store
from ..usage.consumer_imports import artifact_modules, scan_imports
from ..verdicts import templates
from ..verdicts.engine import LIVE_POLICY_VERSION, LIVE_PRIORITY, Evidence, decide, split_silent
from ..verdicts.stats import funnel
from ..witnesses.verify import INFRA_CLASSES, Verification, verify_cell
from ..worlds.builder import WorldBuilder, WorldBuildError
from ..worlds.cells import CellPlan, persist_cell, plan_cells
from ..worlds.overlay import overlay_lock
from .bind import artifact_sources, find_sites, module_of
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


def _bind_runner(payload: dict):
    """Attribution re-runs one call site at a time in each forced world; this adapts O-bind to the runner interface attribute() expects."""
    def runner(sbx, image, *, world_hash, artifact_hash, top_level, modules, pythonpath):
        return run_o_bind(sbx, image, world_hash=world_hash, artifact_hash=artifact_hash, sites=[payload], top_level=top_level, pythonpath=pythonpath)
    return runner


def _contract_runner(item: "o_contract.Item"):
    """Attribution re-runs one contract input in each forced world; this adapts O-contract to the runner interface attribute() expects."""
    def runner(sbx, image, *, world_hash, artifact_hash, top_level, modules, pythonpath):
        return o_contract.run_o_contract(sbx, image, world_hash=world_hash, artifact_hash=artifact_hash, items=[item], compare=True, top_level=top_level,
                                         pythonpath=pythonpath)
    return runner


def _contract_scope(ex: "o_contract.Exploration", items: list["o_contract.Item"]) -> dict:
    import base64
    return {"types": [f"{t.module}.{t.name}" for t in ex.types], "inputs_total": ex.n_total, "inputs_valid": ex.n_valid, "inputs_invalid": ex.n_invalid,
            "classes": dict(sorted(ex.classes.items())), "notes": list(ex.notes),
            "inputs": {i.entry: {"type": f"{i.type.module}.{i.type.name}", "tier": i.tier, "variant": i.variant, "options_assumed": i.assumed_options,
                                 "source": i.source, "sha256": i.bytes_hash, "generated": i.tier == "T3",
                                 "preview": base64.b64decode(i.bytes_b64).decode("utf-8", "replace")[:160]} for i in items}}


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
    delta_names = [d.name for d in plan.projection.delta]
    sites, unchecked = find_sites(conn, art_dir, delta_names, src_root=pyroot, consumer_modules=set(modules))
    site_by_entry = {"bind:" + s.site_id: s for s in sites}
    ctypes: list = []
    creason = "pydantic does not differ between the reference world and the consumer world"
    if any(d.lower() == "pydantic" for d in delta_names):
        srcs = artifact_sources(art_dir)
        ctypes = o_contract.discover_types(srcs, {p: module_of(p, pyroot) for p in srcs}, set(modules))
        creason = "no pydantic model is defined in the modules the consumer imports"
    test_text = _test_lock(art_dir) if has_tests else None
    steps = planner.after_import(planner.plan(pkg, modules, has_tests=has_tests, test_lock=test_text is not None, bind_sites=len(sites), contract_types=len(ctypes),
                                              contract_reason=creason), pkg, v)
    if any(s.oracle == "o_bind" and s.status == "PLANNED" for s in steps):
        say(base + 0.095 / n, f"running O-bind (3 + 3 fresh runs) on {len(sites)} call site(s)")
        payload = [site_payload(s) for s in sites]

        def run_bind(world_hash: str):
            return retrying(lambda: run_o_bind(sbx, image, world_hash=world_hash, artifact_hash=artifact, sites=payload, top_level=pkg, pythonpath=(pythonpath,)),
                            checkpoint=lambda: say(base + 0.095 / n, "checking whether the job was cancelled"))()
        with phase("verify O-bind (3 + 3 fresh runs)", cell=cell_id, sites=len(sites)):
            vb = verify_cell(conn, cell, oracle=BIND_ORACLE, version=BIND_VERSION, run_in_world=run_bind, args={"sites": [p["id"] for p in payload]}, force=True)
        v = Verification(v.ref_runs + vb.ref_runs, v.test_runs + vb.test_runs, v.decisions + vb.decisions, v.problem or vb.problem)
        steps = planner.mark_ran(steps, "o_bind", tuple("bind:" + p["id"] for p in payload))
    test_entries: set[str] = set()
    tests_note: list[str] = []
    if any(s.oracle == "o_tests" and s.status == "PLANNED" for s in steps):
        say(base + 0.093 / n, "building the test overlay worlds and running the library's own tests (3 + 3 fresh runs)")
        try:
            ovs: dict[str, tuple[str, object]] = {}
            for key, text in ((cell.ref_world_hash, render_lock(list(plan.reference.pinned))), (cell.test_world_hash, plan.projection.lock_text)):
                ov = overlay_lock(text, test_text)
                w = builder.materialize(ov.lock_text, WorldKind.OVERLAY, scopes=ov.scopes())
                if builder.build(w, ov.lock_text).status == "FAILED":
                    raise WorldBuildError("a test overlay world could not be built offline", details={"reason": "overlay_build_failed"})
                ovs[key] = (w.world_hash, ov)
        except WorldBuildError as e:
            steps = [planner.Step("o_tests", "NOT_PLANNED", f"the test overlay could not be built: {e.message}") if s.oracle == "o_tests" else s for s in steps]
        else:
            def run_tests(world_hash: str):
                return retrying(lambda: run_o_tests(sbx, image, world_hash=ovs[world_hash][0], artifact_hash=artifact, top_level=pkg, pythonpath=(pythonpath,)),
                                checkpoint=lambda: say(base + 0.093 / n, "checking whether the job was cancelled"))()
            with phase("verify O-tests (3 + 3 fresh runs)", cell=cell_id):
                vt = verify_cell(conn, cell, oracle=TESTS_ORACLE, version=TESTS_VERSION, run_in_world=run_tests, args={"overlay_worlds": [ovs[k][0] for k in sorted(ovs)]}, force=True)
            v = Verification(v.ref_runs + vt.ref_runs, v.test_runs + vt.test_runs, v.decisions + vt.decisions, v.problem or vt.problem)
            test_entries = {d.entry for d in vt.decisions}
            steps = planner.mark_ran(steps, "o_tests", tuple(sorted(test_entries)))
            tests_note = [f"the test overlay kept the runtime version of {name} ({keep}) over the {want} its test lock asked for" for _k, (_h, o) in ovs.items() for name, keep, want in o.conflicts]
            if tests_note:
                steps = [planner.Step(x.oracle, x.status, "; ".join(tests_note) + " (the overlay is marked forced)", x.entries) if x.oracle == "o_tests" else x for x in steps]
    contract_scope: dict | None = None
    item_by_entry: dict = {}
    if any(s.oracle == "o_contract" and s.status == "PLANNED" for s in steps):
        say(base + 0.097 / n, f"replaying the data contracts of {len(ctypes)} model(s): bytes from the reference world, parsed in the consumer world")
        with phase("explore data contracts", cell=cell_id, models=len(ctypes)):
            ex = o_contract.explore(sbx, image, producer_world=cell.ref_world_hash, consumer_world=test_hash, artifact_hash=artifact, art_dir=art_dir,
                                    types=ctypes, pythonpath=(pythonpath,))
        citems = ex.verification_items()
        item_by_entry = {i.entry: i for i in citems}
        contract_scope = _contract_scope(ex, citems)
        if citems:
            def run_contract(world_hash: str):
                return retrying(lambda: o_contract.run_o_contract(sbx, image, world_hash=world_hash, artifact_hash=artifact, items=citems,
                                                                  compare=world_hash != cell.ref_world_hash, top_level=pkg, pythonpath=(pythonpath,)),
                                checkpoint=lambda: say(base + 0.097 / n, "checking whether the job was cancelled"))()
            with phase("verify O-contract (3 + 3 fresh runs)", cell=cell_id, inputs=len(citems)):
                vc = verify_cell(conn, cell, oracle=o_contract.ORACLE, version=o_contract.ORACLE_VERSION, run_in_world=run_contract,
                                 args={"items": [i.entry for i in citems]}, force=True, entry_meta={i.entry: o_contract.witness_input(i) for i in citems})
            v = Verification(v.ref_runs + vc.ref_runs, v.test_runs + vc.test_runs, v.decisions + vc.decisions, v.problem or vc.problem)
            steps = planner.mark_ran(steps, "o_contract", tuple(i.entry for i in citems))
        else:
            steps = [planner.Step("o_contract", "NOT_PLANNED", "; ".join(ex.notes) or "no input was accepted by the reference world, so there was nothing to replay")
                     if s.oracle == "o_contract" else s for s in steps]
    for dec in v.witnesses:
        if dec.entry in test_entries:
            continue                                   # a failing test is a witness, but its cause is searched through the import and call-site witnesses
        if dec.witness_id and dec.signature is not None:
            say(base + 0.1 / n, f"attributing the break in {dec.entry} (two-sided search)")
            site = site_by_entry.get(dec.entry)
            runner = _bind_runner(site_payload(site)) if site is not None else None
            if dec.entry in item_by_entry:
                runner = _contract_runner(item_by_entry[dec.entry])
            with phase("attribute (two-sided ddmin)", cell=cell_id, entry=dec.entry):
                a = attribute(sbx, image, builder, artifact_hash=artifact, entry=dec.entry, top_level=pkg, pythonpath=pythonpath, signature=dec.signature,
                              ref=list(plan.reference.pinned), consumer=list(plan.projection.pinned), delta=delta_names, run=runner)
            persist(conn, dec.witness_id, a)
    fid = write_live_finding(conn, aid, cell, v, layout, plan, steps, rels, sites=site_by_entry, unchecked_sites=len(unchecked), contract=contract_scope)
    state = "ANALYZED" if v.decisions else "INCONCLUSIVE"
    conn.execute("UPDATE cell SET state=? WHERE id=?", (state, cell_id))
    return fid, state


def _test_lock(art_dir: Path) -> str | None:
    """The artifact's hash-pinned test-only lock, or None. A lock that is not fully pinned is not used: the overlay must be exact."""
    f = Path(art_dir) / "requirements.test.lock.txt"
    if not f.is_file():
        return None
    text = f.read_text(encoding="utf-8")
    try:
        reqs = parse_pinned_lock(text)
    except Exception:  # noqa: BLE001
        return None
    return text if reqs and all(r.hashes for r in reqs) else None


def _with_hash(ref, world_hash: str):
    from dataclasses import replace
    return replace(ref, world_hash=world_hash)


def _env_id(builder: WorldBuilder) -> str:
    from ..core.hashing import env_profile_id
    return env_profile_id(builder.env)


def write_live_finding(conn: sqlite3.Connection, analysis_id: str, cell: FixtureCell, v: Verification, layout: dict, plan: CellPlan,
                       steps: list[planner.Step], rels, sites: dict | None = None, unchecked_sites: int = 0, contract: dict | None = None) -> str:
    consumers = [conn.execute("SELECT p.rel_path, r.owner, r.name FROM project p JOIN snapshot s ON s.id=p.snapshot_id JOIN repository r ON r.id=s.repository_id "
                              "WHERE p.id=?", (c,)).fetchone() for c, _ in plan.consumers]
    names = [f"{c['owner']}/{c['name']}" for c in consumers]
    rel_levels = {r.consumer_project_id: r.level for r in rels if r.producer_project_id == plan.producer_project_id}
    level = "L2" if all(rel_levels.get(c) in ("L2", "L3", "L4", "L5") for c, _ in plan.consumers) else "L1"
    plain, silent = split_silent(v.decisions)
    out = decide(Evidence(relationship_level=level, cell_state="PENDING", decisions=plain, run_problem=v.problem, silent_entries=silent))
    artifact = layout["name"] or layout["rel_path"]
    sites = sites or {}
    ran_bind = any(s.oracle == "o_bind" and s.status == "RAN" for s in steps)
    ran_contract = any(s.oracle == "o_contract" and s.status == "RAN" for s in steps)
    live_not_checked = tuple(x for x in templates.NOT_CHECKED_LIVE if not (ran_contract and x == "data-contract replay was not run"))
    not_checked = (*live_not_checked, *(templates.NOT_CHECKED_BIND if ran_bind else ()), *(templates.NOT_CHECKED_CONTRACT if ran_contract else ()),
                   *((f"{unchecked_sites} dynamic or unresolved call site(s) were recorded and not checked",) if unchecked_sites else ()))
    shown = tuple(f"call `{sites[e].callee}` at {sites[e].site_id}" if e in sites else e for e in out.exercised)
    kw = {"artifact": artifact, "consumers": names, "exercised": shown, "reasons": out.reasons, "not_checked": not_checked}
    cinputs = (contract or {}).get("inputs", {})
    if out.outcome in ("BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED"):
        dec = next(x for x in v.decisions if x.entry == out.witness_entries[0])
        kw.update(entry=dec.entry, exc=dec.signature.exc_type, message=dec.signature.message_norm)
        if dec.entry in cinputs:
            kw["contract"] = cinputs[dec.entry]
        if dec.entry in sites:
            s = sites[dec.entry]
            kw["site"] = {"id": s.site_id, "callee": s.callee, "n_positional": s.n_positional, "keyword_names": list(s.keyword_names)}
    headline = templates.live_headline(out.outcome, **kw)
    conn.execute("DELETE FROM finding_evidence WHERE finding_id IN (SELECT id FROM finding WHERE cell_id=?)", (cell.cell_id,))
    conn.execute("DELETE FROM finding WHERE cell_id=?", (cell.cell_id,))
    fid = new_id("fnd")
    verdict = out.verdict
    scope = {"exercised": list(out.exercised), "not_applicable": list(out.not_applicable), "not_checked": list(not_checked), "bind_sites": {e: {"id": s.site_id, "callee": s.callee, "n_positional": s.n_positional, "keyword_names": list(s.keyword_names)} for e, s in sites.items()},
             "reasons": list(out.reasons), "policy": LIVE_POLICY_VERSION, "oracle_plan": planner.as_json(steps), "consumers": names, "contract": contract,
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
