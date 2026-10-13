"""API contract: health, capabilities truthfulness, job submission, errors, auth."""
from fastapi.testclient import TestClient

from faultline.api.main import create_app
from faultline.core.config import Settings
from faultline.core.enums import Mode


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["db"] == "ok" and body["schema_version"] >= 2
    assert body["mode"] == "FIXTURE" and body["auth"] == "disabled"


def test_tc_0_5_1_capabilities_are_truthful(client):
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    cap = r.json()
    # no sandboxd is running in this test, so execution must be reported as unavailable, never as verified
    assert cap["sandbox"]["state"] == "unavailable" and cap["sandbox"]["verified"] is False
    assert "sandbox not verified" in cap["sandbox"]["reason"]
    for name, status in cap["oracles"].items():
        assert status["state"] == "unavailable", name
        assert status["reason"] == "sandbox not verified", name
    allowed = {("pypi", "inventory"), ("npm", "inventory"), ("npm", "resolve"), ("npm", "world"), ("maven", "inventory")}
    for eco in cap["ecosystems"]:
        for dim in ("inventory", "resolve", "world", "runtime_witness"):
            if eco[dim]["state"] == "enabled":
                assert (eco["ecosystem"], dim) in allowed, (eco["ecosystem"], dim)   # only what reads files and runs nothing
            assert eco[dim]["reason"]
        assert eco["runtime_witness"]["state"] != "enabled"
    assert {e["ecosystem"] for e in cap["ecosystems"]} == {"pypi", "npm", "maven"}
    assert cap["features"]["llm_assistance"]["state"] == "unavailable"


def test_no_findings_exist_before_any_analysis(client):
    """No claim without evidence: a fresh system reports an empty list, never an example finding."""
    assert client.get("/api/findings").json() == []


def test_tc_0_4_3_idempotent_submission(client):
    body = {"kind": "noop", "payload": {"a": 1}, "idempotency_key": "same-key"}
    a = client.post("/api/jobs", json=body)
    b = client.post("/api/jobs", json=body)
    assert a.status_code == 202 and b.status_code == 202
    assert a.json()["job_id"] == b.json()["job_id"]
    assert len(client.get("/api/jobs").json()) == 1


def test_submission_returns_immediately_with_queued_status(client):
    r = client.post("/api/jobs", json={"kind": "sleep", "payload": {"seconds": 30}})
    assert r.status_code == 202
    j = r.json()
    assert j["status"] == "QUEUED" and j["attempts"] == 0
    assert client.get(f"/api/jobs/{j['job_id']}").json()["status"] == "QUEUED"


def test_cancel_via_api(client):
    j = client.post("/api/jobs", json={"kind": "noop"}).json()
    r = client.post(f"/api/jobs/{j['job_id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"


def test_error_envelope(client):
    r = client.post("/api/jobs", json={"kind": "no_such_kind"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNKNOWN_JOB_KIND"
    r = client.get("/api/jobs/job_missing")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = client.post("/api/jobs", json={"nope": 1})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_admin_token_required_for_mutations_when_configured(tmp_path):
    s = Settings(db_path=tmp_path / "t.db", store_path=tmp_path / "s", mode=Mode.FIXTURE, admin_token="secret",
                 lease_seconds=1, heartbeat_seconds=0.2, poll_seconds=0.05)
    with TestClient(create_app(s)) as c:
        assert c.get("/api/health").json()["auth"] == "token"
        assert c.post("/api/jobs", json={"kind": "noop"}).status_code == 401
        assert c.post("/api/jobs", json={"kind": "noop"}, headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = c.post("/api/jobs", json={"kind": "noop"}, headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 202


def test_openapi_documents_core_contracts(client):
    spec = client.get("/openapi.json").json()
    assert "/api/capabilities" in spec["paths"] and "/api/jobs" in spec["paths"]
    assert "Capabilities" in spec["components"]["schemas"]


def test_connections_survive_threadpool_hops(client):
    """FastAPI may open and close a request's connection on different worker threads; many requests must all succeed."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(lambda _: client.get("/api/findings").status_code, range(60)))
    assert set(codes) == {200}
