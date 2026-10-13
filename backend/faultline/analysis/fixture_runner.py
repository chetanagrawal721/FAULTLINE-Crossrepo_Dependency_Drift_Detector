"""Runs a fixture scenario end to end: lock files -> worlds -> artifact -> witness verification -> finding.

FIXTURE mode only. Every step really executes (worlds are built offline, oracles run in the sandbox, six fresh runs per
checked cell); only the inputs are the committed fixture repositories instead of freshly ingested GitHub snapshots.
"""
import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..core.config import repo_root
from ..core.enums import Verdict, WorldKind
from ..core.ids import new_id
from ..core.scenario import Scenario, load_scenario
from ..oracles.artifacts import prepare_artifact
from ..oracles.o_import import ORACLE, ORACLE_VERSION, plan_modules, run_o_import
from ..sandbox import images
from ..sandbox.client import SandboxClient
from ..storage.store import Store
from ..verdicts import templates
from ..verdicts.engine import POLICY_VERSION, PRIORITY, fixture_verdict
from ..witnesses.verify import Verification, verify_cell
from ..worlds.builder import WorldBuilder
from .fixture import FixtureCell, ensure_fixture_cell


@dataclass(frozen=True)
class CellOutcome:
    consumer: str
    state: str                       # NO_DRIFT | ANALYZED | INCONCLUSIVE
    cell: FixtureCell
    finding_id: str | None = None
    verification: Verification | None = None


def scenario_path(scenario_id: str, root: Path | None = None) -> Path:
    p = (root or repo_root()) / "fixtures" / "scenarios" / f"{scenario_id}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"unknown scenario {scenario_id!r}")
    return p


def _delta(ref_entries, test_entries) -> list[dict]:
    r = {e["name"]: e["version"] for e in ref_entries}
    t = {e["name"]: e["version"] for e in test_entries}
    return [{"name": n, "reference": r.get(n), "consumer": t.get(n)} for n in sorted(set(r) | set(t)) if r.get(n) != t.get(n)]


def run_scenario(conn: sqlite3.Connection, sbx: SandboxClient, store: Store, scenario_id: str, *,
                 root: Path | None = None, progress: Callable[[float, str], None] | None = None) -> list[CellOutcome]:
    root = root or repo_root()
    sc: Scenario = load_scenario(scenario_path(scenario_id, root))
    say = progress or (lambda f, m: None)
    image = images.default_image()
    builder = WorldBuilder(sbx, image, conn)
    art_dir = root / sc.artifact.path
    ref_text = (art_dir / sc.artifact.runtime_lock).read_text(encoding="utf-8")
    say(0.05, "building the reference world offline")
    ref = builder.materialize(ref_text, WorldKind.REFERENCE)
    res = builder.build(ref, ref_text)
    if res.status == "FAILED":
        raise RuntimeError(f"reference world could not be built: {res.reason}")
    artifact = prepare_artifact(art_dir, store)
    outcomes: list[CellOutcome] = []
    n = len(sc.consumers)
    for i, c in enumerate(sc.consumers):
        base = 0.1 + 0.85 * i / n
        say(base, f"{c.repo}: building the consumer world")
        text = (root / c.path / c.lock).read_text(encoding="utf-8")
        world = builder.materialize(text, WorldKind.PROJECTED)
        res = builder.build(world, text)
        if res.status == "FAILED":
            raise RuntimeError(f"consumer world for {c.repo} could not be built: {res.reason}")
        cell = ensure_fixture_cell(conn, scenario_id=sc.id, consumer=c.repo, artifact_hash=artifact, ref_world=ref,
                                   test_world=world, env=builder.env)
        if world.world_hash == ref.world_hash:
            conn.execute("UPDATE cell SET state='NO_DRIFT' WHERE id=?", (cell.cell_id,))
            outcomes.append(CellOutcome(c.repo, "NO_DRIFT", cell))
            continue
        modules = plan_modules(sc.artifact.import_package, c.imports)
        say(base + 0.05 / n, f"{c.repo}: running O-import (3 reference + 3 consumer runs) on {', '.join(modules)}")

        def run(world_hash: str, modules=modules):
            return run_o_import(sbx, image, world_hash=world_hash, artifact_hash=artifact,
                                top_level=sc.artifact.import_package, modules=modules)
        v = verify_cell(conn, cell, oracle=ORACLE, version=ORACLE_VERSION, run_in_world=run, args={"modules": modules})
        finding_id = _write_finding(conn, sc, c.repo, cell, v, ref, world)
        state = "ANALYZED" if v.decisions else "INCONCLUSIVE"
        conn.execute("UPDATE cell SET state=? WHERE id=?", (state, cell.cell_id))
        outcomes.append(CellOutcome(c.repo, state, cell, finding_id, v))
    say(1.0, "done")
    return outcomes


def _write_finding(conn, sc: Scenario, consumer: str, cell: FixtureCell, v: Verification, ref, world) -> str:
    vr = fixture_verdict(v)
    artifact = sc.artifact.repo
    kw = {"artifact": artifact, "consumer": consumer, "exercised": vr.exercised, "reasons": vr.reasons}
    if vr.verdict == Verdict.BREAK_WITNESSED:
        d = next(x for x in v.decisions if x.entry == vr.witness_entries[0])
        kw.update(entry=d.entry, exc=d.signature.exc_type, message=d.signature.message_norm)
    head = templates.headline(vr.verdict, **kw)
    conn.execute("DELETE FROM finding_evidence WHERE finding_id IN (SELECT id FROM finding WHERE cell_id=?)", (cell.cell_id,))
    conn.execute("DELETE FROM finding WHERE cell_id=?", (cell.cell_id,))
    fid = new_id("fnd")
    scope = {"exercised": list(vr.exercised), "not_applicable": list(vr.not_applicable),
             "not_checked": list(templates.NOT_CHECKED_PHASE1), "reasons": list(vr.reasons), "policy": POLICY_VERSION}
    conn.execute("INSERT INTO finding(id, analysis_id, scope_kind, cell_id, verdict, headline, scope_json, priority, created_at) "
                 "VALUES (?,?, 'ARTIFACT_CELL', ?,?,?,?,?,?)",
                 (fid, cell.analysis_id, cell.cell_id, vr.verdict.value, head, json.dumps(scope, sort_keys=True),
                  PRIORITY[vr.verdict], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    for d in v.decisions:
        if d.witness_id:
            conn.execute("INSERT OR IGNORE INTO finding_evidence(finding_id, evidence_kind, evidence_id) VALUES (?, 'WITNESS', ?)",
                         (fid, d.witness_id))
    for r in v.ref_runs + v.test_runs:
        conn.execute("INSERT OR IGNORE INTO finding_evidence(finding_id, evidence_kind, evidence_id) VALUES (?, 'ORACLE_RUN', ?)",
                     (fid, r.run_id))
    return fid
