"""M12.1: a publicly reported break, reproduced from public registries by resolution date. REAL2 is reproduced; REAL1 is a documented
wheels-only limit (xfail). Needs network access."""
import json
import socket
from pathlib import Path

import pytest

from faultline.analysis.timemachine import run_time_machine
from faultline.core.scenario import load_scenario
from faultline.ingestion import service
from faultline.ingestion.github import GitHubClient, GitHubError

pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]


def online() -> bool:
    try:
        socket.create_connection(("api.github.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module", params=["REAL2", "REAL1"])
def real1(request, daemon, image):
    if not online():
        pytest.skip("no network access to GitHub")
    import tempfile

    from faultline.analysis.repository import analyze_repository
    from faultline.sandbox.client import SandboxClient
    from faultline.storage.db import connect
    from faultline.storage.migrate import migrate
    from tests.conftest import TOKEN
    sc = load_scenario(ROOT / "fixtures" / "scenarios" / f"{request.param}.yaml")
    conn = connect(Path(tempfile.mkdtemp()) / "t.db")
    migrate(conn)
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=900)
    pid = service.create_project(conn, request.param)
    try:
        rid, resolved, _ = service.add_repository(conn, GitHubClient(), pid, sc.real_source.url, sc.real_source.ref)
    except GitHubError as e:
        if "rate limit" in str(e):
            pytest.skip("GitHub API rate limit reached (set GITHUB_TOKEN)")
        raise
    service.ingest(conn, sbx, image, daemon.store, rid)
    analyze_repository(conn, sbx, image, daemon.store, rid, build=False)
    try:
        res = run_time_machine(conn, sbx, image, daemon.store, rid, reference_cutoff=sc.time_machine.reference_cutoff,
                               consumer_cutoff=sc.time_machine.consumer_cutoff)
    except ValueError as e:
        if "needs_build" in str(e):                    # a documented limit of the wheels-only policy on Python 3.12, see REAL1.md
            pytest.xfail(f"{request.param} is not reproducible by the pipeline: a dependency has no CPython 3.12 wheel at that date and Faultline never builds from source")
        raise
    return sc, conn, res, resolved


def test_tc_12_1_2_faultline_reproduces_the_public_break_and_attributes_it(real1):
    sc, conn, res, resolved = real1
    assert resolved.sha and len(resolved.sha) == 40 and resolved.requested_ref == sc.real_source.ref
    assert res.finding_id, f"no finding was produced: {res}"
    f = conn.execute("SELECT * FROM finding WHERE id=?", (res.finding_id,)).fetchone()
    assert f["verdict"] == "BREAK_WITNESSED", f["headline"]
    e = sc.expect.cells[0]
    assert e.signature.exc_type in f["headline"] and e.signature.message_contains in f["headline"]            # the signature written in REAL1.md
    scope = json.loads(f["scope_json"])
    assert sorted(d["name"] for d in scope["delta"]) == sorted(e.delta)
    d = next(x for x in scope["delta"] if x["name"] == e.attribution.minimal_set[0])
    assert d["reference"] != d["consumer"] and d["reference"] and d["consumer"]                                # the attributed package differs between the worlds
    att = conn.execute("SELECT a.* FROM attribution a JOIN witness w ON w.id=a.witness_id WHERE w.cell_id=?", (res.cell_id,)).fetchone()
    assert json.loads(att["minimal_set_json"]) == e.attribution.minimal_set and att["sidedness"] == "two_sided" and att["status"] == "COMPLETE"
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


def test_real2_scenario_links_public_evidence_and_the_hand_verification_record_exists():
    sc = load_scenario(ROOT / "fixtures" / "scenarios" / "REAL2.yaml")
    assert any("requests/toolbelt/issues/354" in u for u in sc.public_evidence)
    md = (ROOT / "fixtures" / "verification" / "REAL2.md").read_text(encoding="utf-8")
    assert "urllib3 1.26.15" in md.replace("**", "") and "urllib3 2.0.2" in md.replace("**", "")
    assert "cannot import name 'appengine' from 'urllib3.contrib'" in md
