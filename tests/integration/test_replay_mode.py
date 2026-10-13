"""M12.2: REPLAY mode shows recorded evidence only, needs no Docker, refuses to run anything, and the badge cannot lie."""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scripts.export_replay import export

from faultline.api.main import create_app
from faultline.core.config import Settings
from faultline.core.enums import Mode
from faultline.relationships.engine import create_analysis, discover
from faultline.storage.store import Store
from faultline.worlds.cells import persist_cell, plan_cells
from tests.livefix import (
    fixture_repo,
    lock_text,
    new_analysis_project,
    seed_projects,
    seed_repository,
    seed_world,
)
from tests.uiserve import serve_database


@pytest.fixture
def recorded(conn, tmp_path):
    """A LIVE-mode analysis with cells, recorded, then exported as a REPLAY pack."""
    store = Store(tmp_path / "store")
    apid = new_analysis_project(conn)
    conn.execute("INSERT OR IGNORE INTO env_profile(id, image_ref, arch, locale, tz, env_json, seed) VALUES ('ep_x','i','a','l','t','{}',0)")
    conn.execute("INSERT OR IGNORE INTO resolved_world(world_hash, ecosystem, runtime_json, env_profile_id, kind) VALUES ('w_projected','pypi','{}','ep_x','projected')")
    for name, sub in (("acme-models", "acme-models"), ("notify-svc", "notify-svc/D"), ("orders-svc", "orders-svc/A")):
        _r, sid = seed_repository(conn, store, apid, "faultline-demo", name, fixture_repo(sub))
        seed_world(conn, seed_projects(conn, store, sid)[0], lock_text(sub))
    aid = create_analysis(conn, apid)
    rels = discover(conn, store, aid, apid)
    for plan in plan_cells(conn, rels).cells:
        persist_cell(conn, aid, plan, "w_projected", {})
    conn.execute("UPDATE analysis SET status='DONE' WHERE id=?", (aid,))
    from faultline.storage import jobs  # a finished job with an attempt: the pack must still export
    jobs.create_job(conn, "analyze_project", {"project_id": apid})
    assert jobs.claim_next(conn, "w1", 30) is not None
    db = conn.execute("PRAGMA database_list").fetchone()["file"]
    pack = export(Path(db), store.root, tmp_path / "pack")
    return apid, aid, tmp_path / "pack", pack


def replay_settings(pack: Path) -> Settings:
    return Settings(db_path=pack / "faultline.db", store_path=pack / "store", mode=Mode.REPLAY, admin_token=None, lease_seconds=30,
                    heartbeat_seconds=10, poll_seconds=0.5)


def test_the_pack_marks_every_analysis_as_a_recording_and_keeps_where_it_came_from(recorded):
    apid, aid, pack, info = recorded
    c = sqlite3.connect(pack / "faultline.db")
    mode, opts = c.execute("SELECT mode, options_json FROM analysis WHERE id=?", (aid,)).fetchone()
    assert mode == "REPLAY" and json.loads(opts)["recorded_from_mode"] == "LIVE"
    assert c.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0 and info["skipped"] == []


def test_replay_serves_records_and_refuses_every_action(recorded, monkeypatch):
    apid, aid, pack, _ = recorded
    monkeypatch.setenv("DOCKER_HOST", "tcp://127.0.0.1:1")                     # Docker is unreachable: reading recorded evidence must still work
    with TestClient(create_app(replay_settings(pack))) as c:
        a = c.get(f"/api/projects/{apid}/analysis")
        assert a.status_code == 200 and a.json()["mode"] == "REPLAY" and len(a.json()["cells"]) == 2
        assert c.get("/api/health").json()["mode"] == "REPLAY"
        for method, path, body in (("post", f"/api/projects/{apid}/analyze", None), ("post", "/api/jobs", {"kind": "noop"}),
                                   ("post", "/api/projects", {"name": "x"}), ("post", "/api/scenarios/D/run", None)):
            r = getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)
            assert r.status_code == 409 and "REPLAY mode shows recorded evidence only" in r.json()["error"]["message"], path
        assert c.get("/api/jobs").json() == []                                  # nothing was queued


def test_tc_12_2_3_the_mode_shown_is_the_mode_stored_with_the_evidence_not_the_requested_one(recorded, tmp_path):
    apid, aid, pack, _ = recorded
    with TestClient(create_app(replay_settings(pack))) as c:
        plain = c.get(f"/api/projects/{apid}/analysis").json()
        forced = c.get(f"/api/projects/{apid}/analysis?mode=LIVE", headers={"X-Faultline-Mode": "LIVE", "Mode": "LIVE"}).json()
        assert plain["mode"] == forced["mode"] == "REPLAY"
        assert [x["mode"] for x in c.get("/api/findings?mode=LIVE").json()] == []             # a filter selects records; it never relabels them
    sync_api = pytest.importorskip("playwright.sync_api")
    conn = sqlite3.connect(pack / "faultline.db")
    conn.row_factory = sqlite3.Row
    with serve_database(conn, tmp_path, Mode.REPLAY) as base, sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium is not installed: {e}")
        page = browser.new_page()
        page.goto(base + "/?mode=LIVE#/app")                                 # the URL asks for LIVE
        page.get_by_test_id("analysis").wait_for(timeout=30000)
        badges = [b.inner_text() for b in page.get_by_test_id("mode-badge").all()]
        assert "LIVE" not in badges and all(b == "RECORDED" for b in badges) and badges           # the record says REPLAY: the badge says RECORDED
        browser.close()
