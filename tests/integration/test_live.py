"""M4.4: the live pipeline on real (locally hosted) git repositories, through the sandboxed fetch and offline world builds."""
import json

import pytest

from faultline.analysis.live import run_live_analysis
from tests.liveenv import ingest_all
from tests.livefix import fixture_repo

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def d_scenario(daemon, image):
    """Scenario D, ingested and analysed once for the module."""
    import tempfile
    from pathlib import Path

    from faultline.sandbox.client import SandboxClient
    from faultline.storage.db import connect
    from faultline.storage.migrate import migrate
    from tests.conftest import TOKEN
    tmp = Path(tempfile.mkdtemp())
    conn = connect(tmp / "t.db")
    migrate(conn)
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=600)
    apid, ids = ingest_all(conn, sbx, image, daemon.store, {
        "rm_live_prod": ("faultline-demo/acme-models", fixture_repo("acme-models")),
        "rm_live_notify": ("faultline-demo/notify-svc", fixture_repo("notify-svc/D")),
        "rm_live_orders": ("faultline-demo/orders-svc", fixture_repo("orders-svc/D"))})
    res = run_live_analysis(conn, sbx, image, daemon.store, apid)
    return conn, res, ids


def test_tc_4_4_1_live_analysis_stores_per_world_outcomes_with_stable_fingerprints(d_scenario):
    conn, res, ids = d_scenario
    states = {c["state"] for c in res.cells}
    assert states == {"ANALYZED", "NO_DRIFT"} and res.funnel["consumers_discovered"] == 2 and res.funnel["consumers_analysed"] == 2
    analysed = next(c for c in res.cells if c["state"] == "ANALYZED")
    runs = conn.execute("SELECT r.* FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.cell_id=? ORDER BY j.side, r.run_index", (analysed["cell_id"],)).fetchall()
    assert len(runs) == 12 and all(r["provenance"] == "FRESH_EXECUTION" for r in runs)                  # 6 for O-import and 6 for O-tests
    by_oracle = {}
    for r in conn.execute("SELECT j.oracle, j.side FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.cell_id=?", (analysed["cell_id"],)):
        by_oracle.setdefault(r["oracle"], []).append(r["side"])
    assert {k: sorted(v) for k, v in by_oracle.items()} == {"o_import": ["ref"] * 3 + ["test"] * 3, "o_tests": ["ref"] * 3 + ["test"] * 3}
    ref_fp = {r["env_fingerprint"] for r in conn.execute("SELECT r.env_fingerprint FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.cell_id=? AND j.side='ref'", (analysed["cell_id"],))}
    assert len(ref_fp) == 1 and None not in ref_fp                                           # same reference fingerprint on every run
    f = conn.execute("SELECT * FROM finding WHERE id=?", (analysed["finding_id"],)).fetchone()
    assert f["verdict"] == "BREAK_WITNESSED" and "url_quote" in f["headline"] and "3 of 3" in f["headline"]
    scope = json.loads(f["scope_json"])
    assert {d["name"] for d in scope["delta"]} == {"itsdangerous", "werkzeug"} and scope["consumers"] == ["faultline-demo/notify-svc"]
    assert scope["oracle_plan"][0]["oracle"] == "o_import" and scope["oracle_plan"][0]["status"] == "RAN"
    tests = scope["oracle_plan"][1]
    assert tests["oracle"] == "o_tests" and tests["status"] == "RAN"                                     # acme-models ships its tests and a hash-pinned test lock
    assert sorted(tests["entries"]) == ["test_customer.py::test_default_points", "test_customer.py::test_round_trip", "test_web.py::test_show_customer"]
    w = {x["entry_point"]: x for x in conn.execute("SELECT * FROM witness WHERE cell_id=?", (analysed["cell_id"],))}
    assert sorted(w) == ["acme_models.web", "test_web.py::test_show_customer"]                           # the import fails, and so does the library's own web test
    assert w["test_web.py::test_show_customer"]["oracle"] == "o_tests" and w["test_web.py::test_show_customer"]["divergence"] == "TEST_FAIL"
    assert all(x["ref_pass"] == 3 and x["test_fail"] == 3 for x in w.values())


def test_orders_svc_matching_the_reference_queued_no_oracle_jobs(d_scenario):
    conn, res, ids = d_scenario
    nd = next(c for c in res.cells if c["state"] == "NO_DRIFT")
    assert conn.execute("SELECT COUNT(*) FROM oracle_job WHERE cell_id=?", (nd["cell_id"],)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM finding WHERE cell_id=?", (nd["cell_id"],)).fetchone()[0] == 0


def test_analysis_api_serves_persisted_records_only(d_scenario, tmp_path):
    from fastapi.testclient import TestClient

    from faultline.api.main import create_app
    from faultline.core.config import Settings
    from faultline.core.enums import Mode
    conn, res, ids = d_scenario
    db = conn.execute("PRAGMA database_list").fetchone()["file"]
    settings = Settings(db_path=__import__("pathlib").Path(db), store_path=tmp_path, mode=Mode.LIVE, admin_token=None, lease_seconds=30,
                        heartbeat_seconds=10, poll_seconds=0.5)
    with TestClient(create_app(settings)) as c:
        a = c.get(f"/api/analyses/{res.analysis_id}").json()
        pid = conn.execute("SELECT analysis_project_id FROM analysis WHERE id=?", (res.analysis_id,)).fetchone()[0]
        assert c.get(f"/api/projects/{pid}/analysis").json()["id"] == res.analysis_id
    assert a["funnel"]["consumers_discovered"] == 2 and a["funnel"]["cells_by_state"] == {"ANALYZED": 1, "NO_DRIFT": 1}
    rel = next(r for r in a["relationships"] if r["consumer"].endswith("notify-svc"))
    assert rel["level"] == "L2" and rel["actionable"] and {e["file_path"] for e in rel["evidence"]} == {"pyproject.toml", "requirements.txt"}
    assert all(len(e["commit"]) == 40 and e["line"] for e in rel["evidence"])                                  # pinned SHA and a line each
    cell = next(x for x in a["cells"] if x["state"] == "ANALYZED")
    assert cell["verdict"] == "BREAK_WITNESSED" and {d["name"] for d in cell["delta"]} == {"itsdangerous", "werkzeug"}
    assert cell["imported_modules"] == ["acme_models.web"] and cell["consumers"] == ["faultline-demo/notify-svc"]
    assert cell["ref_world_hash"].startswith("w_") and cell["test_world_hash"] != cell["ref_world_hash"]


def test_live_break_is_attributed_two_sided_and_served_with_forced_world_labels(d_scenario, tmp_path):
    from pathlib import Path

    from fastapi.testclient import TestClient

    from faultline.api.main import create_app
    from faultline.core.config import Settings
    from faultline.core.enums import Mode
    conn, res, ids = d_scenario
    db = conn.execute("PRAGMA database_list").fetchone()["file"]
    settings = Settings(db_path=Path(db), store_path=tmp_path, mode=Mode.LIVE, admin_token=None, lease_seconds=30, heartbeat_seconds=10, poll_seconds=0.5)
    with TestClient(create_app(settings)) as c:
        a = c.get(f"/api/analyses/{res.analysis_id}").json()
    att = next(x for x in a["cells"] if x["state"] == "ANALYZED")["attribution"]
    assert att["minimal"] == ["werkzeug"] and att["status"] == "COMPLETE" and att["sidedness"] == "two_sided" and att["minimal_claim"]
    assert att["attempts"] and all(t["label"] == "attribution experiment (forced world)" for t in att["attempts"])


def test_tc_5_1_4_the_ui_labels_every_forced_world_in_the_why_path(d_scenario, tmp_path):
    """Serve the real API over the real analysis database and read the why-path in Chromium."""
    import socket
    import threading
    import time
    from pathlib import Path

    import uvicorn

    from faultline.api.main import create_app
    from faultline.core.config import Settings
    from faultline.core.enums import Mode
    sync_api = pytest.importorskip("playwright.sync_api")
    conn, res, ids = d_scenario
    db = conn.execute("PRAGMA database_list").fetchone()["file"]
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    settings = Settings(db_path=Path(db), store_path=tmp_path, mode=Mode.LIVE, admin_token=None, lease_seconds=30, heartbeat_seconds=10, poll_seconds=0.5)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        time.sleep(0.2)
        if server.started:
            break
    try:
        with sync_api.sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"Chromium is not installed: {e}")
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/#/app/worlds")
            wp = page.get_by_test_id("why-path").first
            wp.wait_for(timeout=30000)
            wp.locator("summary").click()
            text = wp.inner_text()
            browser.close()
    finally:
        server.should_exit = True
        t.join(timeout=10)
    assert "werkzeug" in text and "COMPLETE" in text and "two-sided" in text and "minimal" in text.lower()
    assert text.count("attribution experiment (forced world)") >= 3                       # every attempt carries the label
    assert "None of them is an environment a repository actually uses" in text


# ----------------------------------------------------------------------------- M5.3 TC-5.3.3 stale verdicts after a rule change (keep this test last: it edits and restores the module's findings)

def test_tc_5_3_3_a_policy_change_recomputes_findings_from_stored_evidence_without_running_anything(d_scenario, monkeypatch):
    from types import SimpleNamespace

    from faultline.api.deps import fresh_conn
    from faultline.verdicts import recompute
    from faultline.witnesses import verify
    conn, res, ids = d_scenario
    db = conn.execute("PRAGMA database_list").fetchone()["file"]

    def finding():
        return conn.execute("SELECT id, verdict, scope_json FROM finding WHERE verdict IN ('BREAK_WITNESSED','INCONCLUSIVE') ORDER BY rowid DESC LIMIT 1").fetchone()
    runs_before = conn.execute("SELECT COUNT(*) FROM oracle_run").fetchone()[0]
    first = finding()
    assert first["verdict"] == "BREAK_WITNESSED" and json.loads(first["scope_json"])["policy"] == "verdict-policy/1"
    assert recompute.recompute_all_stale(conn) == 0                          # nothing is stale while the policy is unchanged

    # the rules change: a new policy version, and a witness now needs 4 fresh repeats per side (only 3 were ever run)
    monkeypatch.setattr(recompute, "LIVE_POLICY_VERSION", "verdict-policy/2")
    monkeypatch.setattr(verify, "K", 4)
    replay_req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(db_path=db, mode=SimpleNamespace(value="REPLAY")))))
    live_req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(db_path=db, mode=SimpleNamespace(value="LIVE")))))

    g = fresh_conn(replay_req)                                               # REPLAY serves the recorded database untouched
    c = next(g)
    assert c.execute("SELECT verdict FROM finding WHERE id=?", (first["id"],)).fetchone()[0] == "BREAK_WITNESSED"
    g.close()

    g = fresh_conn(live_req)                                                 # serving a request recomputes first: no stale verdict is returned
    c = next(g)
    now = c.execute("SELECT verdict, headline, scope_json FROM finding WHERE id=?", (first["id"],)).fetchone()
    g.close()
    assert now["verdict"] == "INCONCLUSIVE" and json.loads(now["scope_json"])["policy"] == "verdict-policy/2"
    assert json.loads(now["scope_json"])["recomputed_from_stored_evidence"] is True
    assert conn.execute("SELECT COUNT(*) FROM oracle_run").fetchone()[0] == runs_before          # recomputed from evidence: no run was executed or added

    # and back: the earlier rules decide the same stored runs the same way again
    monkeypatch.undo()
    assert recompute.recompute_all_stale(conn) >= 1
    back = conn.execute("SELECT verdict, headline, scope_json FROM finding WHERE id=?", (first["id"],)).fetchone()
    assert back["verdict"] == "BREAK_WITNESSED" and json.loads(back["scope_json"])["policy"] == "verdict-policy/1"
    assert back["headline"] == conn.execute("SELECT headline FROM finding WHERE id=?", (first["id"],)).fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM oracle_run").fetchone()[0] == runs_before
