"""M12.1: a publicly reported break, reproduced from public registries by resolution date (REAL1). Needs network access."""
import json
import re
import socket
from pathlib import Path

import pytest

from faultline.analysis.timemachine import run_time_machine
from faultline.core.scenario import load_scenario
from faultline.ingestion import service
from faultline.ingestion.github import GitHubClient

pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]


def online() -> bool:
    try:
        socket.create_connection(("api.github.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def real1(daemon, image):
    if not online():
        pytest.skip("no network access to GitHub")
    import tempfile

    from faultline.analysis.repository import analyze_repository
    from faultline.sandbox.client import SandboxClient
    from faultline.storage.db import connect
    from faultline.storage.migrate import migrate
    from tests.conftest import TOKEN
    sc = load_scenario(ROOT / "fixtures" / "scenarios" / "REAL1.yaml")
    conn = connect(Path(tempfile.mkdtemp()) / "t.db")
    migrate(conn)
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=900)
    pid = service.create_project(conn, "REAL1")
    rid, resolved, _ = service.add_repository(conn, GitHubClient(), pid, sc.real_source.url, sc.real_source.ref)
    service.ingest(conn, sbx, image, daemon.store, rid)
    analyze_repository(conn, sbx, image, daemon.store, rid, build=False)
    try:
        res = run_time_machine(conn, sbx, image, daemon.store, rid, reference_cutoff=sc.time_machine.reference_cutoff,
                               consumer_cutoff=sc.time_machine.consumer_cutoff)
    except ValueError as e:
        if "needs_build" in str(e):                    # a documented limit of the wheels-only policy on Python 3.12, see REAL1.md
            pytest.xfail("REAL1 is not reproducible by the pipeline: MarkupSafe 2.1.x has no CPython 3.12 wheel before 2024 and Faultline never builds from source")
        raise
    return sc, conn, res, resolved


def test_tc_12_1_2_faultline_reproduces_the_public_break_and_attributes_it(real1):
    sc, conn, res, resolved = real1
    assert resolved.sha and len(resolved.sha) == 40 and resolved.requested_ref == "2.2.2"
    f = conn.execute("SELECT * FROM finding WHERE id=?", (res.finding_id,)).fetchone()
    assert f["verdict"] == "BREAK_WITNESSED"
    e = sc.expect.cells[0]
    assert e.signature.exc_type in f["headline"] and e.signature.message_contains in f["headline"]            # the signature written in REAL1.md
    scope = json.loads(f["scope_json"])
    assert [d["name"] for d in scope["delta"]] == ["werkzeug"]
    d = scope["delta"][0]
    assert re.match(r"^2\.", d["reference"]) and d["consumer"].startswith("3.")                                # a Werkzeug major release separates the worlds
    att = conn.execute("SELECT a.* FROM attribution a JOIN witness w ON w.id=a.witness_id WHERE w.cell_id=?", (res.cell_id,)).fetchone()
    assert json.loads(att["minimal_set_json"]) == ["werkzeug"] and att["sidedness"] == "two_sided" and att["status"] == "COMPLETE"
    runs = conn.execute("SELECT r.provenance FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.cell_id=? AND j.oracle='o_import'", (res.cell_id,)).fetchall()
    assert len(runs) >= 6 and all(r["provenance"] == "FRESH_EXECUTION" for r in runs)


def test_both_resolution_cutoffs_are_recorded_in_the_provenance(real1):
    sc, conn, res, resolved = real1
    cuts = {r["resolved_at"] for r in conn.execute("SELECT resolved_at FROM project_world")}
    assert {sc.time_machine.reference_cutoff, sc.time_machine.consumer_cutoff} <= cuts
    rel = conn.execute("SELECT * FROM relationship WHERE analysis_id=?", (res.analysis_id,)).fetchone()
    assert rel["level"] == "L5" and rel["kind"] == "DECLARED" and "user-declared" in rel["shared_symbols_json"]        # labelled as declared, never as discovered
    analysis = conn.execute("SELECT options_json FROM analysis WHERE id=?", (res.analysis_id,)).fetchone()[0]
    assert json.loads(analysis)["time_machine"] == {"reference": sc.time_machine.reference_cutoff, "consumer": sc.time_machine.consumer_cutoff}


def test_the_scenario_file_links_public_evidence_and_the_hand_verification_record_exists():
    sc = load_scenario(ROOT / "fixtures" / "scenarios" / "REAL1.yaml")
    assert any("pallets/werkzeug/issues/2789" in u for u in sc.public_evidence)                                  # TC-12.1.3
    md = (ROOT / "fixtures" / "verification" / "REAL1.md").read_text(encoding="utf-8")
    assert "werkzeug 2.3.7" in md and "werkzeug 3.0.1" in md and "cannot import name 'url_quote' from 'werkzeug.urls'" in md   # TC-12.1.1
