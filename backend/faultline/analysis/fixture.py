"""Creates the database rows a fixture analysis needs (project, snapshot, cell, ...) so oracle runs, witnesses and
findings can be stored with proper foreign keys. FIXTURE mode only; live ingestion (Phase 2) replaces this.
"""
import json
import sqlite3
from dataclasses import dataclass

from ..core.hashing import object_hash
from ..core.models import EnvProfile, ResolvedWorld
from ..storage import worlds as world_store

NOW = "2026-10-13T00:00:00Z"        # fixed: fixture rows must not depend on when they were created


@dataclass(frozen=True)
class FixtureCell:
    analysis_id: str
    cell_id: str
    artifact_project_id: str
    ref_world_hash: str
    test_world_hash: str
    artifact_hash: str
    env_profile_id: str


def _id(prefix: str, *parts) -> str:
    return f"{prefix}_{object_hash(list(parts))[:24]}"


def ensure_fixture_cell(conn: sqlite3.Connection, *, scenario_id: str, consumer: str, artifact_hash: str,
                        ref_world: ResolvedWorld, test_world: ResolvedWorld, env: EnvProfile) -> FixtureCell:
    world_store.save_world(conn, ref_world, env)
    world_store.save_world(conn, test_world, env)
    ap = _id("ap", "fixture", scenario_id)
    repo = _id("repo", ap, "acme-models")
    snap = _id("snp", repo, artifact_hash)
    prj = _id("prj", snap)
    analysis = _id("an", ap, consumer)
    cell = _id("cell", analysis, ref_world.world_hash, test_world.world_hash)
    sha = artifact_hash.removeprefix("a_").ljust(40, "0")[:40]
    conn.execute("INSERT OR IGNORE INTO analysis_project(id, name, mode, created_at) VALUES (?,?, 'FIXTURE', ?)",
                 (ap, f"fixture {scenario_id}", NOW))
    conn.execute("INSERT OR IGNORE INTO repository(id, analysis_project_id, owner, name) VALUES (?,?,?,?)",
                 (repo, ap, "faultline-demo", "acme-models"))
    conn.execute("INSERT OR IGNORE INTO snapshot(id, repository_id, sha, committed_at, store_path, ingest_status) "
                 "VALUES (?,?,?,?,?, 'OK')", (snap, repo, sha, NOW, "fixtures/repos/acme-models"))
    conn.execute("INSERT OR IGNORE INTO project(id, snapshot_id, rel_path, ecosystem, published_name, artifact_content_hash, "
                 "is_pure_python, has_tests) VALUES (?,?, '.', 'pypi', 'acme-models', ?, 1, 1)", (prj, snap, artifact_hash))
    conn.execute("INSERT OR IGNORE INTO analysis(id, analysis_project_id, status, mode, options_json) "
                 "VALUES (?,?, 'QUEUED', 'FIXTURE', ?)", (analysis, ap, json.dumps({"consumer": consumer, "scenario": scenario_id})))
    conn.execute("INSERT OR IGNORE INTO cell(id, analysis_id, artifact_project_id, ref_world_hash, test_world_hash, state) "
                 "VALUES (?,?,?,?,?, 'PENDING')", (cell, analysis, prj, ref_world.world_hash, test_world.world_hash))
    return FixtureCell(analysis, cell, prj, ref_world.world_hash, test_world.world_hash, artifact_hash,
                       ref_world.env_profile_id)
