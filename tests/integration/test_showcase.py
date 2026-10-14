"""The showcase: one artifact and two consumers submitted together show every kind of finding in a single analysis."""
import json
import tempfile
from pathlib import Path

import pytest

from faultline.analysis.live import run_live_analysis
from tests.liveenv import ingest_all
from tests.livefix import fixture_repo

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def showcase(daemon, image):
    from faultline.sandbox.client import SandboxClient
    from faultline.storage.db import connect
    from faultline.storage.migrate import migrate
    from tests.conftest import TOKEN
    conn = connect(Path(tempfile.mkdtemp()) / "t.db")
    migrate(conn)
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=900)
    apid, ids = ingest_all(conn, sbx, image, daemon.store, {
        "rm_sc_art": ("faultline-demo/acme-showcase", fixture_repo("acme-showcase")),
        "rm_sc_ful": ("faultline-demo/fulfilment-svc", fixture_repo("fulfilment-svc")),
        "rm_sc_rep": ("faultline-demo/reporting-svc", fixture_repo("reporting-svc"))})
    return conn, run_live_analysis(conn, sbx, image, daemon.store, apid)


def test_one_submission_shows_every_kind_of_finding(showcase):
    conn, res = showcase
    assert sorted(c["state"] for c in res.cells) == ["ANALYZED", "NO_DRIFT"]                                          # the control has nothing to run
    f = conn.execute("SELECT * FROM finding").fetchall()
    assert [x["verdict"] for x in f] == ["BREAK_WITNESSED"]
    w = {r["entry_point"]: r for r in conn.execute("SELECT * FROM witness")}
    kinds = {(r["oracle"], r["class"]) for r in w.values()}
    assert kinds == {("o_import", "BREAK"), ("o_bind", "BREAK"), ("o_contract", "BREAK"), ("o_contract", "SILENT_DIVERGENCE")}
    assert "acme_showcase.web" in w                                                                                    # the import break
    assert any(e.startswith("bind:src/acme_showcase/retry.py:7") for e in w)                                           # the call that no longer binds
    assert not any("retry.py:12" in e or "LoyaltyNote" in e for e in w)                                                # the harmless call and the control model are not reported
    assert any(e.startswith("contract:CustomerRequest:") for e in w) and any(e.startswith("contract:Ref:") for e in w)
    assert all(r["ref_pass"] == 3 and r["test_fail"] == 3 for r in w.values())
    cause = {r["entry_point"]: set(json.loads(a["minimal_set_json"])) for r in w.values() for a in conn.execute("SELECT * FROM attribution WHERE witness_id=?", (r["id"],))}
    assert "werkzeug" in cause["acme_showcase.web"] and any("urllib3" in v for k, v in cause.items() if k.startswith("bind:")) and any("pydantic" in v for k, v in cause.items() if k.startswith("contract:"))
