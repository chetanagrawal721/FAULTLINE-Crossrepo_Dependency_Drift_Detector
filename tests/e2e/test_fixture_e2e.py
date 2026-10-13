"""M1.8 end to end: from a scenario id to a stored, displayed finding. Real Docker, real worker code, real API.

    FAULTLINE_SCENARIO=D python tools/fl.py e2e D        (A, D and H exist; default: D)

The worker's own run_one() executes the queued job, so this exercises the real job path (API -> job table -> worker ->
handler -> sandbox -> database -> API read models -> evidence bundle), not a shortcut.
"""
import os
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from faultline.api.main import create_app
from faultline.core.config import Settings
from faultline.core.enums import Mode
from faultline.core.scenario import load_scenario
from faultline.storage.db import connect
from faultline.storage.migrate import migrate
from faultline.witnesses.bundle import verify_bundle
from faultline.workers.run import run_one

pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = [s.strip() for s in os.environ.get("FAULTLINE_SCENARIO", "D").split(",") if s.strip()]


@pytest.fixture
def stack(daemon, image, tmp_path, monkeypatch):
    monkeypatch.setenv("FAULTLINE_DB", str(tmp_path / "e2e.db"))
    monkeypatch.setenv("FAULTLINE_STORE", str(daemon.store.root))
    monkeypatch.setenv("FAULTLINE_SANDBOX_PORT", str(daemon.port))
    monkeypatch.setenv("FAULTLINE_SANDBOX_TOKEN", "test-token-not-secret")
    from faultline.sandbox import status
    status._cache.update(at=0.0, value=None)
    settings = Settings(db_path=tmp_path / "e2e.db", store_path=daemon.store.root, mode=Mode.FIXTURE, admin_token=None,
                        lease_seconds=60, heartbeat_seconds=5, poll_seconds=0.1)
    c = connect(settings.db_path)
    migrate(c)
    with TestClient(create_app(settings)) as api:
        yield api, settings, c
    c.close()


def run_job_to_completion(api, settings, conn, scenario_id):
    r = api.post(f"/api/scenarios/{scenario_id}/run")
    assert r.status_code == 202
    job = r.json()
    assert job["status"] == "QUEUED"
    assert run_one(conn, "e2e-worker", settings) is True                # the real worker code path
    end = time.time() + 5
    while time.time() < end:
        j = api.get(f"/api/jobs/{job['job_id']}").json()
        if j["status"] in ("DONE", "FAILED", "CANCELLED"):
            break
        time.sleep(0.1)
    assert j["status"] == "DONE", j
    return j


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_tc_1_8_1_end_to_end_from_scenario_id_to_displayed_finding(stack, scenario_id):
    api, settings, conn = stack
    sc = load_scenario(ROOT / "fixtures" / "scenarios" / f"{scenario_id}.yaml")
    assert api.get("/api/findings").json() == []                         # nothing before the run: no claim without evidence

    job = run_job_to_completion(api, settings, conn, scenario_id)
    states = {c["consumer"]: c["state"] for c in job["result"]["cells"]}

    findings = api.get("/api/findings").json()
    expected = [c for c in sc.expect.cells if c.state != "NO_DRIFT"]
    assert len(findings) == len(expected)
    for cell in sc.expect.cells:
        assert states[cell.consumer] == ("NO_DRIFT" if cell.state == "NO_DRIFT" else "ANALYZED"), (cell.consumer, states)
    for cell in expected:
        f = next(x for x in findings if x["consumer"] == cell.consumer)
        assert f["verdict"] == cell.verdict.value                        # the expectation written before any code existed
        assert f["mode"] == "FIXTURE"                                    # never presented as live analysis
        d = api.get(f"/api/findings/{f['finding_id']}").json()
        assert d["fresh_runs"] == 6 and d["reused_runs"] == 0
        assert len(d["runs"]) == 6 and {r["side"] for r in d["runs"]} == {"ref", "test"}
        assert d["reference"]["world_hash"] != d["consumer_world"]["world_hash"]
        assert {x["name"] for x in d["delta"]} == set(cell.delta)        # exactly the dependency difference in the locks
        assert d["scope"]["not_checked"], "a finding must say what was not checked"
        if cell.witness:
            w = d["witnesses"][0]
            assert w["entry_point"] == cell.entry_point and w["oracle"] == cell.oracle
            assert (w["ref_pass"], w["test_fail"]) == (3, 3) and len(set(w["ref_run_ids"] + w["test_run_ids"])) == 6
            assert w["signature"]["exc_type"] == cell.signature.exc_type
            assert cell.signature.message_contains in w["signature"]["message_norm"]
            assert d["headline"].startswith("Reproduced:")
            b = api.get(f"/api/witnesses/{w['witness_id']}/bundle")
            assert b.status_code == 200 and b.headers["content-type"] == "application/zip"
            path = Path(settings.db_path).with_name("served.zip")
            path.write_bytes(b.content)
            assert verify_bundle(path).ok and "manifest.json" in zipfile.ZipFile(BytesIO(b.content)).namelist()
        else:
            assert d["witnesses"] == [] and d["bundle_url"] is None      # negative control: no witness, no bundle
            assert "compatible" not in d["headline"].lower().replace("not a statement that they are compatible", "")


def test_unknown_scenario_is_a_clear_error(stack):
    api, *_ = stack
    r = api.post("/api/scenarios/ZZZ/run")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_scenarios_endpoint_lists_expectations(stack):
    api, *_ = stack
    s = {x["id"]: x for x in api.get("/api/scenarios").json()}
    assert {"A", "D", "H"} <= set(s)
    d = next(c for c in s["D"]["consumers"] if c["repo"] == "notify-svc")
    assert d["expected_verdict"] == "BREAK_WITNESSED" and d["expects_witness"] is True
