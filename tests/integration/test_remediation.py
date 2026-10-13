"""M8.0: demo-minimal remediation on the real, live scenario-D break."""
import json
import re
from pathlib import Path

import pytest

from faultline.remediation.minimal import diff_for, propose_constraint, remediate
from tests.integration.test_live import d_scenario  # noqa: F401

pytestmark = pytest.mark.docker


def break_finding(conn):
    return conn.execute("SELECT id FROM finding WHERE verdict='BREAK_WITNESSED' ORDER BY rowid DESC LIMIT 1").fetchone()[0]


def test_constraint_proposal_and_diff_are_structured():
    assert propose_constraint("werkzeug", "2.2.3", "3.0.6") == "werkzeug<3"
    assert propose_constraint("x", "1.2.0", "1.3.0") == "x==1.2.0"                 # no major jump: pin back to the reference version
    assert propose_constraint("x", None, "1.0") is None
    d = diff_for("requirements.txt", "flask==2.2.2\n", "werkzeug<3")
    assert d.splitlines()[:2] == ["--- a/requirements.txt", "+++ b/requirements.txt"] and "+werkzeug<3" in d and "-" not in d.split("@@")[-1]


def test_tc_8_0_1_the_fix_verifies_with_fresh_runs(d_scenario, daemon, image):  # noqa: F811
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    conn, res, ids = d_scenario
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=900)
    r = remediate(conn, sbx, image, daemon.store, break_finding(conn))
    assert r.label == "VERIFIED", (r.label, r.reason)
    assert r.constraint == "werkzeug<3" and r.witnesses_before == ["acme_models.web"] and r.witnesses_after == []     # original witness gone, none new
    assert r.fresh_runs == 6 and r.other_consumers_unchanged and r.new_world_hash
    assert "+werkzeug<3" in r.diff and r.diff.startswith("--- a/requirements.")           # a requirements file of the consumer; diff only
    row = conn.execute("SELECT * FROM remediation_plan WHERE id=?", (r.plan_id,)).fetchone()
    assert row["label"] == "VERIFIED" and json.loads(row["gates_json"])["G2_witness_gone"] is True
    assert "+werkzeug<3" in Path(row["diff_path"]).read_text(encoding="utf-8")
    runs = conn.execute("SELECT r.provenance FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.world_hash=?", (r.new_world_hash,)).fetchall()
    assert len(runs) >= 3 and all(x["provenance"] == "FRESH_EXECUTION" for x in runs)           # the 3 consumer-side runs in the fixed world (the 3 reference runs use the reference world)


def test_tc_8_0_2_a_bad_fix_is_not_verified(d_scenario, daemon, image):  # noqa: F811
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    conn, res, ids = d_scenario
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=900)
    fid = break_finding(conn)
    impossible = remediate(conn, sbx, image, daemon.store, fid, constraint="werkzeug>=99")
    assert impossible.label == "REJECTED" and "could not be resolved" in impossible.reason
    assert conn.execute("SELECT COUNT(*) FROM remediation_plan WHERE id=?", ("rp_" + "x",)).fetchone()[0] == 0
    useless = remediate(conn, sbx, image, daemon.store, fid, constraint="werkzeug<4")                # still resolves to werkzeug 3: the break persists
    assert useless.label == "SUGGESTED" and "persists" in useless.reason and useless.witnesses_after == ["acme_models.web"]
    assert conn.execute("SELECT label FROM remediation_plan WHERE id=?", (useless.plan_id,)).fetchone()[0] == "SUGGESTED"


def test_tc_8_0_3_remediation_never_pushes_or_writes_to_the_network():
    base = Path(__file__).resolve().parents[2] / "backend" / "faultline" / "remediation"
    src = "\n".join(p.read_text(encoding="utf-8") for p in base.glob("*.py"))
    assert not re.search(r"git\s+push|git\.push|\bpush\b.*origin|urllib|\brequests\b|\bhttpx\b|socket|http\.client|subprocess|os\.system|\.post\(|\.put\(", src), \
        "remediation must produce a diff only"
    assert "difflib.unified_diff" in src
