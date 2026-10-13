"""Relationship discovery over the projects of an analysis project. Findings need an actionable L2 relationship backed by
evidence on both sides; weak signals go to the suspected tray and never produce a finding."""
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from ..core.hashing import object_hash
from ..ingestion.clone import load_inventory
from ..storage.store import Store
from .signals import Candidate, PyProject, candidates, load_projects
from .suspected import class_fields, twin_candidates


@dataclass(frozen=True)
class RelationshipRow:
    id: str
    producer_project_id: str
    consumer_project_id: str
    kind: str
    level: str
    confidence: str
    actionable: bool
    status: str
    note: str


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def create_analysis(conn: sqlite3.Connection, analysis_project_id: str, mode: str = "LIVE", options: dict | None = None) -> str:
    aid = "an_" + object_hash([analysis_project_id, _now(), options or {}, time.monotonic_ns()])[:24]
    conn.execute("INSERT INTO analysis(id, analysis_project_id, status, mode, options_json, started_at) VALUES (?,?, 'RELATING', ?,?,?)",
                 (aid, analysis_project_id, mode, json.dumps(options or {}, sort_keys=True), _now()))
    return aid


def persist(conn: sqlite3.Connection, analysis_id: str, cands: list[Candidate]) -> list[RelationshipRow]:
    rows = []
    for c in cands:
        rid = "rel_" + object_hash([analysis_id, c.kind, c.producer_id, c.consumer_id])[:24]
        conn.execute("INSERT OR REPLACE INTO relationship(id, analysis_id, producer_project_id, consumer_project_id, kind, level, confidence, "
                     "actionable, status, shared_symbols_json, roles_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (rid, analysis_id, c.producer_id, c.consumer_id, c.kind, c.level, c.confidence, int(c.actionable), c.status,
                      json.dumps([c.note] if c.note else []), None))
        conn.execute("DELETE FROM relationship_evidence WHERE relationship_id=?", (rid,))
        for i, e in enumerate(c.evidence):
            conn.execute("INSERT INTO relationship_evidence(id, relationship_id, signal, project_id, file_path, line, excerpt) VALUES (?,?,?,?,?,?,?)",
                         (f"re_{object_hash([rid, i])[:20]}", rid, e.signal, e.project_id, e.file_path, e.line, e.excerpt))
        rows.append(RelationshipRow(rid, c.producer_id, c.consumer_id, c.kind, c.level, c.confidence, c.actionable, c.status, c.note))
    return rows


def discover(conn: sqlite3.Connection, store: Store, analysis_id: str, analysis_project_id: str) -> list[RelationshipRow]:
    projects = load_projects(conn, analysis_project_id)
    found = candidates(projects, projects)
    related = {(c.producer_id, c.consumer_id) for c in found if c.actionable}
    # suspected twins: only between projects of different repositories that are not already actionably related
    fields: dict[str, dict] = {}

    def fields_of(p: PyProject) -> dict:
        if p.id not in fields:
            snap = conn.execute("SELECT store_path FROM snapshot WHERE id=?", (p.snapshot_id,)).fetchone()
            root = store.snapshot_dir(snap["store_path"])
            inv = load_inventory(Path(root))
            prefix = "" if p.rel_path == "." else p.rel_path + "/"
            fields[p.id] = class_fields(Path(root), [e for e in inv["entries"] if e["path"].startswith(prefix)])
        return fields[p.id]

    for i, a in enumerate(projects):
        for b in projects[i + 1:]:
            if a.repo_id == b.repo_id or (a.id, b.id) in related or (b.id, a.id) in related:
                continue
            found += twin_candidates(a, fields_of(a), b, fields_of(b))
    return persist(conn, analysis_id, found)


def evidence_for(conn: sqlite3.Connection, relationship_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT signal, project_id, file_path, line, excerpt FROM relationship_evidence WHERE relationship_id=? ORDER BY id",
                                          (relationship_id,))]
