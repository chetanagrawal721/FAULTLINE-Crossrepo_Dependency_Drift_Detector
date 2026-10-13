"""M7.1: contract replay in real sandboxes. Scenario J (pydantic 1 sends, pydantic 2 rejects) and scenario E (a union read differently)."""
import base64
import json
import tempfile
from pathlib import Path

import pytest

from faultline.analysis.live import run_live_analysis
from faultline.oracles import o_contract
from tests.liveenv import ingest_all
from tests.livefix import fixture_repo

pytestmark = pytest.mark.docker


def _run(daemon, image, consumer_dir: str):
    from faultline.sandbox.client import SandboxClient
    from faultline.storage.db import connect
    from faultline.storage.migrate import migrate
    from tests.conftest import TOKEN
    conn = connect(Path(tempfile.mkdtemp()) / "t.db")
    migrate(conn)
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=900)
    apid, ids = ingest_all(conn, sbx, image, daemon.store, {
        "rm_ct_art": ("faultline-demo/acme-contracts", fixture_repo("acme-contracts")),
        "rm_ct_billing": ("faultline-demo/billing-svc", fixture_repo(consumer_dir))})
    return conn, sbx, run_live_analysis(conn, sbx, image, daemon.store, apid)


@pytest.fixture(scope="module")
def scenario_j(daemon, image):
    return _run(daemon, image, "billing-svc/J")


@pytest.fixture(scope="module")
def scenario_e(daemon, image):
    return _run(daemon, image, "billing-svc/E")


def test_tc_7_1_1_a_payload_the_consumer_rejects_is_witnessed_on_a_minimal_input(scenario_j):
    conn, _sbx, res = scenario_j
    assert [c["state"] for c in res.cells] == ["ANALYZED"]
    f = conn.execute("SELECT * FROM finding WHERE id=?", (res.cells[0]["finding_id"],)).fetchone()
    assert f["verdict"] == "BREAK_WITNESSED", f["scope_json"]
    w = conn.execute("SELECT * FROM witness WHERE oracle='o_contract'").fetchall()
    assert len(w) == 1 and w[0]["class"] == "BREAK" and w[0]["divergence"] == "CONTRACT_REJECTED"
    assert w[0]["input_tier"] == "T2" and w[0]["entry_point"].startswith("contract:CustomerRequest:T2-") and w[0]["ref_pass"] == 3 and w[0]["test_fail"] == 3
    sig = json.loads(w[0]["signature_json"])
    assert sig["exc_type"] == "ValidationError" and "middle_name: Field required" in sig["message_norm"]
    assert "middle_name: Field required" in f["headline"] and "Input tier T2" in f["headline"] and "options were assumed" in f["headline"]
    body = json.loads(w[0]["body_json"])
    stored = base64.b64decode(body["input"]["bytes_b64"])                                      # the exact bytes the producer world emitted are stored
    assert json.loads(stored) == {"customer_id": 0, "email": ""} and body["input"]["sha256"] == w[0]["input_hash"] and body["input"]["variant"] == "exclude_none"
    runs = conn.execute("SELECT j.side, r.provenance, r.failure_class FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.oracle='o_contract'").fetchall()
    assert sorted((r["side"], r["provenance"]) for r in runs) == [("ref", "FRESH_EXECUTION")] * 3 + [("test", "FRESH_EXECUTION")] * 3
    a = conn.execute("SELECT a.* FROM attribution a JOIN witness w ON w.id=a.witness_id WHERE w.oracle='o_contract'").fetchone()
    assert "pydantic" in json.loads(a["minimal_set_json"]) and a["status"] in ("COMPLETE", "PARTIAL")


def test_tc_7_1_3_inputs_the_reference_world_rejects_are_discarded_and_counted(scenario_j, daemon, image):
    conn, sbx, _res = scenario_j
    scope = json.loads(conn.execute("SELECT scope_json FROM finding").fetchone()[0])["contract"]
    assert scope["inputs_invalid"] >= 1 and scope["inputs_valid"] == scope["inputs_total"] - scope["inputs_invalid"]       # the shipped sample is not a CustomerRequest
    assert not any("ref_example" in str(w["entry_point"]) for w in conn.execute("SELECT entry_point FROM witness"))
    cell = conn.execute("SELECT c.ref_world_hash, p.artifact_content_hash FROM cell c JOIN project p ON p.id=c.artifact_project_id").fetchone()
    t = o_contract.ContractType("acme_contracts.customer", "CustomerRequest")
    bad = [{"id": "bad-1", "tier": "T1", "kind": "wire", "wire": {"customer_id": "not a number", "email": 5}},
           {"id": "bad-2", "tier": "T1", "kind": "wire", "wire": {"unrelated": True}},
           {"id": "ok-1", "tier": "T1", "kind": "wire", "wire": {"customer_id": 1, "email": "a@b.c", "middle_name": None}},
           {"id": "gen-bad", "tier": "T3", "kind": "fields", "fields": {"customer_id": "x"}}]
    got = o_contract.produce(sbx, image, world_hash=cell["ref_world_hash"], artifact_hash=cell["artifact_content_hash"], ctype=t, pythonpath=("/artifact/src",),
                             inputs=bad, t2=False)["data"]
    by = {i["id"].split(":")[0]: i["status"] for i in got["items"]}
    assert by["bad-1"] == "ref_error" and by["bad-2"] == "ref_error" and by["gen-bad"] == "producer_error" and by["ok-1"] == "ok"
    assert got["n_invalid"] == 4 == len([i for i in got["items"] if i["status"] != "ok"])         # discarded and counted (the generated one under both option variants); none can reach the consumer world


def test_tc_7_1_4_a_field_with_a_default_is_the_same_in_both_worlds(scenario_j, daemon, image):
    conn, sbx, _res = scenario_j
    cell = conn.execute("SELECT c.ref_world_hash, c.test_world_hash, p.artifact_content_hash, p.rel_path FROM cell c JOIN project p ON p.id=c.artifact_project_id").fetchone()
    art_dir = daemon.store.artifact_dir(cell["artifact_content_hash"])
    ex = o_contract.explore(sbx, image, producer_world=cell["ref_world_hash"], consumer_world=cell["test_world_hash"], artifact_hash=cell["artifact_content_hash"],
                            art_dir=art_dir, types=[o_contract.ContractType("acme_contracts.customer", "LoyaltyNote")], pythonpath=("/artifact/src",))
    assert ex.n_valid >= 2 and dict(ex.classes) == {"SAME": ex.n_valid}                              # every accepted input reads the same
    assert ex.candidates == []
    scope = json.loads(conn.execute("SELECT scope_json FROM finding").fetchone()[0])["contract"]
    assert any(e.startswith("contract:LoyaltyNote:") for e in scope["inputs"])                       # it was exercised in the real run
    assert not any(w["entry_point"].startswith("contract:LoyaltyNote") for w in conn.execute("SELECT entry_point FROM witness"))


def test_tc_7_1_2_a_silent_divergence_shows_both_values(scenario_e):
    conn, _sbx, res = scenario_e
    f = conn.execute("SELECT * FROM finding WHERE id=?", (res.cells[0]["finding_id"],)).fetchone()
    assert f["verdict"] == "SILENT_DIVERGENCE_WITNESSED"
    w = conn.execute("SELECT * FROM witness WHERE oracle='o_contract'").fetchone()
    assert w["class"] == "SILENT_DIVERGENCE" and w["divergence"] == "VALUE_DIVERGENCE" and w["input_tier"] == "T1" and w["ref_pass"] == 3 and w["test_fail"] == 3
    sig = json.loads(w["signature_json"])
    assert sig["exc_type"] == "ValueDivergence" and 'value: reference=42, consumer="42"' in sig["message_norm"]       # both values
    assert 'value: reference=42, consumer="42"' in f["headline"] and "Accepted in both worlds" in f["headline"] and "Input tier T1" in f["headline"]
    body = json.loads(w["body_json"])
    assert json.loads(base64.b64decode(body["input"]["bytes_b64"])) == {"value": "42"} and body["input"]["source"] == "fixtures/ref_example.json"
    assert body["input"]["options_assumed"] is False                                                # a shipped sample is the wire bytes: no options were assumed
