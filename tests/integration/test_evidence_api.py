"""The workspace's Evidence view reads a witness's bundle manifest and integrity result from the API (no Docker: the witness is synthetic)."""
import pytest
from fastapi.testclient import TestClient

from faultline.api.main import create_app
from faultline.core.config import Settings
from faultline.core.enums import Mode
from tests.synthetic import make_witness


@pytest.fixture
def served(conn, tmp_path, settings):
    w = make_witness(conn, tmp_path)
    s = Settings(db_path=settings.db_path, store_path=w.store.root, mode=Mode.FIXTURE, admin_token=None, lease_seconds=30, heartbeat_seconds=10, poll_seconds=0.5)
    with TestClient(create_app(s)) as c:
        yield c, w


def test_the_manifest_endpoint_reports_what_the_bundle_contains_and_that_it_verifies(served):
    c, w = served
    r = c.get(f"/api/witnesses/{w.wid}/bundle/manifest")
    assert r.status_code == 200
    m = r.json()
    assert m["verified"] is True and m["errors"] == [] and m["witness_id"] == w.wid
    assert m["schema_version"] and m["bundle_id"].startswith("bdl_") and m["files"] and all(len(f["sha256"]) == 64 for f in m["files"])
    assert m["run_summary"]["reference_passes"] == 3 and m["run_summary"]["consumer_failures"] == 3 and m["run_summary"]["all_fresh"] is True
    assert m["claim"]["statement"] and m["claim"]["not_claimed"]                              # the bundle says what it does not claim


def test_an_unknown_witness_is_a_clear_not_found(served):
    c, _ = served
    r = c.get("/api/witnesses/wit_does_not_exist/bundle/manifest")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
