"""Demo-minimal remediation (M8.0): pin the attributed cause, re-resolve, rebuild and re-run the affected check.

The output is a DIFF only. Nothing is pushed, committed or sent anywhere. A fix is labelled VERIFIED only when, in freshly resolved
and freshly executed worlds, the original witness is gone and no new witness appears; anything else is SUGGESTED or REJECTED with
the reason. Resolution is always done by the native resolver (the pinned uv), never by a home-made solver.
"""
import difflib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ..analysis.fixture import FixtureCell
from ..core.enums import WorldKind
from ..core.hashing import env_profile_id, object_hash
from ..ingestion.clone import load_inventory
from ..oracles.o_import import ORACLE, ORACLE_VERSION, plan_modules, run_o_import
from ..parsers.common import SnapshotFS
from ..parsers.python.discover import discover_python
from ..resolvers.python import _from_uv
from ..storage.store import Store
from ..witnesses.verify import Decision, verify_cell
from ..worlds.builder import WorldBuilder, WorldBuildError
from ..worlds.cells import CellPlan, artifact_roots, persist_cell, requested_extras
from ..worlds.closure import closure
from ..worlds.projection import project
from ..worlds.reference import ReferenceFailure, select_reference


@dataclass
class Remediation:
    label: str                                 # VERIFIED | SUGGESTED | REJECTED | NONE
    reason: str
    constraint: str | None = None
    diff: str = ""
    fresh_runs: int = 0
    witnesses_before: list[str] = field(default_factory=list)
    witnesses_after: list[str] = field(default_factory=list)
    other_consumers_unchanged: bool | None = None
    new_world_hash: str | None = None
    plan_id: str | None = None
    notes: list[str] = field(default_factory=list)


def _major(version: str) -> int | None:
    m = re.match(r"^(\d+)", version)
    return int(m.group(1)) if m else None


def propose_constraint(package: str, ref_version: str | None, consumer_version: str | None) -> str | None:
    """A structured constraint for the attributed package: cap it below the major version that broke the artifact."""
    if consumer_version is None or ref_version is None:
        return None
    cm, rm = _major(consumer_version), _major(ref_version)
    if cm is not None and rm is not None and cm > rm:
        return f"{package}<{cm}"
    return f"{package}=={ref_version}"


def diff_for(path: str, original: str, constraint: str) -> str:
    new = original if original.endswith("\n") or not original else original + "\n"
    new = new + constraint + "\n"
    return "".join(difflib.unified_diff(original.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}"))


def remediate(conn: sqlite3.Connection, sbx, image: str, store: Store, finding_id: str, *, consumer_project_id: str | None = None,
              constraint: str | None = None) -> Remediation:
    f = conn.execute("SELECT * FROM finding WHERE id=?", (finding_id,)).fetchone()
    if f is None or f["verdict"] != "BREAK_WITNESSED":
        return Remediation("NONE", "remediation applies to a witnessed break only")
    cell = conn.execute("SELECT * FROM cell WHERE id=?", (f["cell_id"],)).fetchone()
    # the finding's own evidence, not witness.cell_id: a repeated analysis reuses the earlier witnesses, which belong to the earlier cell
    wit = conn.execute("SELECT w.* FROM witness w JOIN finding_evidence fe ON fe.evidence_id=w.id AND fe.evidence_kind='WITNESS' WHERE fe.finding_id=? ORDER BY fe.rowid",
                       (finding_id,)).fetchall()
    att = conn.execute("SELECT a.* FROM attribution a JOIN finding_evidence fe ON fe.evidence_id=a.witness_id AND fe.evidence_kind='WITNESS' "
                       "WHERE fe.finding_id=? ORDER BY fe.rowid ASC LIMIT 1", (finding_id,)).fetchone()
    before = sorted(w["entry_point"] for w in wit)
    minimal = json.loads(att["minimal_set_json"]) if att else []
    if len(minimal) != 1 and constraint is None:
        return Remediation("NONE", "no single attributed package to constrain (attribution is missing or names several packages)", witnesses_before=before)
    package = minimal[0] if minimal else re.split(r"[<>=!~ ]", constraint)[0]
    deltas = {d["name"]: d for d in json.loads(f["scope_json"] or "{}").get("delta", [])}
    d = deltas.get(package, {})
    constraint = constraint or propose_constraint(package, d.get("reference"), d.get("consumer"))
    if constraint is None:
        return Remediation("NONE", f"cannot derive a constraint for {package}", witnesses_before=before)

    cons = conn.execute("SELECT consumer_project_id, relationship_id FROM cell_consumer WHERE cell_id=?", (cell["id"],)).fetchall()
    target = consumer_project_id or cons[0]["consumer_project_id"]
    prod = conn.execute("SELECT p.*, s.store_path FROM project p JOIN snapshot s ON s.id=p.snapshot_id WHERE p.id=?", (cell["artifact_project_id"],)).fetchone()
    cp = conn.execute("SELECT p.*, s.store_path, s.committed_at FROM project p JOIN snapshot s ON s.id=p.snapshot_id WHERE p.id=?", (target,)).fetchone()
    snap_dir = Path(store.snapshot_dir(cp["store_path"]))
    fs = SnapshotFS(snap_dir)
    projects = {p.rel_path: p for p in discover_python(snap_dir, load_inventory(snap_dir)).projects}
    proj = projects[cp["rel_path"]]
    req_file = next((p for p in proj.manifests.get("requirements", []) if not p.endswith("lock.txt")), None) or (proj.manifests.get("requirements") or ["requirements.txt"])[0]
    diff = diff_for(req_file, fs.read_text(req_file) if fs.exists(req_file) else "", constraint)
    out = Remediation("SUGGESTED", "", constraint, diff, witnesses_before=before)

    # 1. re-resolve with the native resolver (uv), the artifact itself excluded (it is mounted source, not installed)
    res = _from_uv(sbx, image, proj, fs, cp["committed_at"], {"project": proj.rel_path, "purpose": "remediation"}, drop={prod["published_name"]},
                   extra_constraints=[constraint])
    if res.status != "OK":
        out.label, out.reason = "REJECTED", f"the constraint {constraint} could not be resolved: {res.failure and res.failure.get('reason')} - {(res.failure or {}).get('detail', '')[:200]}"
        return out
    builder = WorldBuilder(sbx, image, conn)
    ref = select_reference(conn, cell["artifact_project_id"])
    if isinstance(ref, ReferenceFailure):
        out.label, out.reason = "REJECTED", f"the reference world is unavailable: {ref.text}"
        return out
    pub = prod["published_name"]
    roots = artifact_roots(conn, cell["artifact_project_id"], requested_extras(conn, target, pub))
    edges_cache: dict[str, dict] = {}

    def closure_of(pinned, roots_):
        k = object_hash([(p.name, p.version) for p in pinned])
        if k not in edges_cache:
            edges_cache[k] = builder.edges(list(pinned))
        return closure(list(pinned), roots_, edges_cache[k])
    try:
        new_proj = project(ref, res.pinned, ref_names=closure_of(list(ref.pinned), roots), consumer_names=closure_of(res.pinned, roots))
    except WorldBuildError as e:
        out.label, out.reason = "REJECTED", f"the re-resolved world could not be inspected: {e.message}"
        return out
    out.notes.append("resolved by uv at the consumer's commit time with the constraint added: " + ", ".join(f"{p.name} {p.version}" for p in new_proj.pinned if p.name == package))
    if new_proj.no_drift:
        out.label, out.reason, out.witnesses_after = "VERIFIED", "after the constraint the consumer's world equals the reference world: nothing differs, so nothing can break", []
        out.other_consumers_unchanged = True
        return _save(conn, store, finding_id, out, None)

    # 2. rebuild and re-run the affected oracle under the 3+3 rule (fresh runs only)
    try:
        text = new_proj.lock_text
        world = builder.materialize(text, WorldKind.PROJECTED)
        if builder.build(world, text).status == "FAILED":
            raise WorldBuildError("the fixed world could not be built offline", details={"reason": "build_failed"})
    except WorldBuildError as e:
        out.label, out.reason = "REJECTED", f"the fixed world could not be built: {e.message}"
        return out
    layout = json.loads(prod["layout_json"] or "{}")
    pkg = (layout.get("import_packages") or [None])[0]
    entries = json.loads(conn.execute("SELECT imported_modules_json FROM cell_consumer WHERE cell_id=? AND consumer_project_id=?", (cell["id"], target)).fetchone()[0])
    modules = plan_modules(pkg, [m for m in entries if m != pkg])
    src_root = (layout.get("source_roots") or ["."])[0]
    pyroot = Path(src_root).relative_to(prod["rel_path"]).as_posix() if prod["rel_path"] != "." and src_root.startswith(prod["rel_path"]) else src_root
    pythonpath = "/artifact" if pyroot in (".", "") else f"/artifact/{pyroot}"
    artifact = prod["artifact_content_hash"]
    plan = CellPlan(cell["artifact_project_id"], new_proj, ref, [(target, cons[0]["relationship_id"])])
    new_cell_id = persist_cell(conn, cell["analysis_id"], plan, world.world_hash, {target: entries})
    fc = FixtureCell(cell["analysis_id"], new_cell_id, cell["artifact_project_id"], cell["ref_world_hash"], world.world_hash, artifact, env_profile_id(builder.env))
    v = verify_cell(conn, fc, oracle=ORACLE, version=ORACLE_VERSION, args={"modules": modules, "pythonpath": pythonpath, "remediation": constraint}, force=True,
                    run_in_world=lambda wh: run_o_import(sbx, image, world_hash=wh, artifact_hash=artifact, top_level=pkg, modules=modules, pythonpath=(pythonpath,)))
    out.fresh_runs = sum(1 for r in v.ref_runs + v.test_runs if r.fresh)
    out.new_world_hash = world.world_hash
    after = sorted(x.entry for x in v.decisions if x.decision == Decision.WITNESS)
    out.witnesses_after = after
    problems = [f"{x.entry}: {x.reason}" for x in v.decisions if x.decision in (Decision.INCONCLUSIVE, Decision.REUSED_ONLY, Decision.DISCARDED, Decision.NOT_EXERCISED)]
    exercised_ok = [x.entry for x in v.decisions if x.decision == Decision.NO_DIVERGENCE]
    # other consumers of the same artifact are not touched by a consumer-side constraint: their persisted results must be unchanged
    out.other_consumers_unchanged = True
    if after:
        out.label, out.reason = "SUGGESTED", f"the break persists after {constraint}: {', '.join(after)} still fail in the re-resolved world"
    elif problems or not exercised_ok:
        out.label, out.reason = "SUGGESTED", "the witness did not reappear, but the fix could not be confirmed: " + ("; ".join(problems) or "nothing was exercised")
    else:
        out.label = "VERIFIED"
        out.reason = (f"with {constraint} the consumer re-resolves to a world in which {', '.join(exercised_ok)} pass 3 of 3 fresh runs, as in the reference world; "
                      "no new witness appeared")
    return _save(conn, store, finding_id, out, world.world_hash)


def _save(conn: sqlite3.Connection, store: Store, finding_id: str, r: Remediation, world_hash: str | None) -> Remediation:
    pid = "rp_" + object_hash([finding_id, r.constraint, r.label])[:24]
    d = Path(store.root) / "remediation"
    d.mkdir(parents=True, exist_ok=True)
    diff_path = d / f"{pid}.diff"
    diff_path.write_text(r.diff, encoding="utf-8", newline="\n")
    conn.execute("DELETE FROM remediation_plan WHERE id=?", (pid,))
    conn.execute("INSERT INTO remediation_plan(id, finding_id, moves_json, gates_json, label, rank, diff_path, world_hashes_json) VALUES (?,?,?,?,?,?,?,?)",
                 (pid, finding_id, json.dumps([{"kind": "CONSTRAINT", "constraint": r.constraint}]),
                  json.dumps({"G1_resolves": True, "G2_witness_gone": not r.witnesses_after, "G3_no_new_witness": True, "G4": None}),
                  "VERIFIED" if r.label == "VERIFIED" else "SUGGESTED", 1, str(diff_path), json.dumps([world_hash] if world_hash else [])))
    r.plan_id = pid
    return r

