"""Live re-run of a witness: execute the same oracle again, 3 fresh runs per world, and report whether it still reproduces.

A re-run never reuses a cached result (force=True), and it records its runs like any other. It does not create a second witness for
the same key; it appends a re-verification to the existing one.
"""
import json
import sqlite3
import time
from dataclasses import dataclass, field

from ..analysis.fixture import FixtureCell
from ..core.hashing import env_profile_id
from ..oracles.o_import import ORACLE_VERSION, run_o_import
from ..sandbox.client import SandboxClient
from ..worlds.builder import env_profile_for
from .verify import Decision, verify_cell


@dataclass
class RerunResult:
    reproduced: bool
    reference_passes: int
    consumer_failures: int
    same_signature: bool
    fresh_runs: int
    seconds: float
    run_ids: list[str] = field(default_factory=list)
    reason: str = ""


def rerun_witness(conn: sqlite3.Connection, sbx: SandboxClient, image: str, witness_id: str) -> RerunResult:
    t0 = time.monotonic()
    w = conn.execute("SELECT * FROM witness WHERE id=?", (witness_id,)).fetchone()
    if w is None:
        raise KeyError(witness_id)
    cell = conn.execute("SELECT * FROM cell WHERE id=?", (w["cell_id"],)).fetchone()
    artifact = conn.execute("SELECT artifact_content_hash FROM project WHERE id=?", (cell["artifact_project_id"],)).fetchone()[0]
    job = conn.execute("SELECT spec_json FROM oracle_job WHERE cell_id=? AND oracle=? ORDER BY rowid DESC LIMIT 1", (cell["id"], w["oracle"])).fetchone()
    args = json.loads(job["spec_json"]) if job else {"modules": [w["entry_point"]]}
    modules = args.get("modules") or [w["entry_point"]]
    pythonpath = args.get("pythonpath") or "/artifact/src"
    top = modules[0]
    fc = FixtureCell(cell["analysis_id"], cell["id"], cell["artifact_project_id"], cell["ref_world_hash"], cell["test_world_hash"], artifact,
                     env_profile_id(env_profile_for(image)))
    v = verify_cell(conn, fc, oracle=w["oracle"], version=ORACLE_VERSION, args=args, force=True,
                    run_in_world=lambda wh: run_o_import(sbx, image, world_hash=wh, artifact_hash=artifact, top_level=top, modules=modules, pythonpath=(pythonpath,)))
    d = next((x for x in v.decisions if x.entry == w["entry_point"]), None)
    runs = v.ref_runs + v.test_runs
    ref_pass = sum(1 for r in v.ref_runs if any(e.entry == w["entry_point"] and e.passed for e in r.result.entries))
    fails = sum(1 for r in v.test_runs if any(e.entry == w["entry_point"] and not e.passed and not e.not_applicable for e in r.result.entries))
    reproduced = d is not None and d.decision == Decision.WITNESS
    return RerunResult(reproduced, ref_pass, fails, reproduced, sum(1 for r in runs if r.fresh), round(time.monotonic() - t0, 1), [r.run_id for r in runs],
                       d.reason if d else "the entry did not run")
