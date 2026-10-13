"""M4.6: O-bind in real sandboxes, on scenario C (urllib3 2.x removed Retry(method_whitelist=...))."""
import json

import pytest

from faultline.analysis.live import run_live_analysis
from tests.liveenv import ingest_all
from tests.livefix import fixture_repo

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def scenario_c(daemon, image):
    import tempfile
    from pathlib import Path

    from faultline.sandbox.client import SandboxClient
    from faultline.storage.db import connect
    from faultline.storage.migrate import migrate
    from tests.conftest import TOKEN
    conn = connect(Path(tempfile.mkdtemp()) / "t.db")
    migrate(conn)
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=900)
    apid, ids = ingest_all(conn, sbx, image, daemon.store, {
        "rm_bind_http": ("faultline-demo/acme-http", fixture_repo("acme-http")),
        "rm_bind_orders": ("faultline-demo/orders-svc", fixture_repo("orders-svc/C"))})
    res = run_live_analysis(conn, sbx, image, daemon.store, apid)
    return conn, res


def test_tc_4_6_2_a_call_that_no_longer_binds_is_witnessed_under_the_three_plus_three_rule(scenario_c):
    conn, res = scenario_c
    assert [c["state"] for c in res.cells] == ["ANALYZED"]
    f = conn.execute("SELECT * FROM finding WHERE id=?", (res.cells[0]["finding_id"],)).fetchone()
    assert f["verdict"] == "BREAK_WITNESSED"
    assert "urllib3.util.retry.Retry(total=..., method_whitelist=...)" in f["headline"] and "src/acme_http/retry.py:7:11" in f["headline"]
    assert "got an unexpected keyword argument 'method_whitelist'" in f["headline"] and "was not executed" in f["headline"]
    w = conn.execute("SELECT * FROM witness WHERE oracle='o_bind'").fetchall()
    assert len(w) == 1 and w[0]["entry_point"] == "bind:src/acme_http/retry.py:7:11" and w[0]["ref_pass"] == 3 and w[0]["test_fail"] == 3
    assert json.loads(w[0]["signature_json"])["exc_type"] == "TypeError"
    runs = conn.execute("SELECT j.side, r.provenance, r.failure_class FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.oracle='o_bind'").fetchall()
    assert sorted((r["side"], r["provenance"]) for r in runs) == [("ref", "FRESH_EXECUTION")] * 3 + [("test", "FRESH_EXECUTION")] * 3
    assert {r["failure_class"] for r in runs if r["side"] == "test"} == {"ARTIFACT_FAILURE"} and {r["failure_class"] for r in runs if r["side"] == "ref"} == {"NONE"}


def test_a_call_that_still_binds_is_exercised_and_not_reported_and_import_alone_passes(scenario_c):
    conn, res = scenario_c
    scope = json.loads(conn.execute("SELECT scope_json FROM finding").fetchone()[0])
    plan = {p["oracle"]: p for p in scope["oracle_plan"]}
    assert plan["o_import"]["status"] == "RAN" and plan["o_bind"]["status"] == "RAN"
    assert sorted(plan["o_bind"]["entries"]) == ["bind:src/acme_http/retry.py:12:11", "bind:src/acme_http/retry.py:7:11"]
    assert "bind:src/acme_http/retry.py:12:11" in scope["exercised"]                                                       # make_quick_retry binds in both worlds
    assert "bind:src/acme_http/retry.py:7:11" in scope["exercised"]                                                        # the witnessed site counts as exercised too
    assert "bind:src/acme_http/retry.py:12:11" not in json.dumps([w["entry_point"] for w in conn.execute("SELECT entry_point FROM witness")])
    imp = conn.execute("SELECT r.failure_class FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.oracle='o_import' AND j.side='test'").fetchall()
    assert len(imp) == 3 and {r[0] for r in imp} == {"NONE"}                  # an import-only check cannot see this break
    assert any("O-bind checks that each call shape still binds" in n for n in scope["not_checked"])                       # the limit of the check is on the finding


def test_the_break_is_attributed_to_urllib3_two_sided_with_the_bind_oracle(scenario_c):
    conn, res = scenario_c
    a = conn.execute("SELECT a.* FROM attribution a JOIN witness w ON w.id=a.witness_id WHERE w.oracle='o_bind'").fetchone()
    assert json.loads(a["minimal_set_json"]) == ["urllib3"] and a["sidedness"] == "two_sided" and a["status"] == "COMPLETE"


def test_call_sites_were_extracted_and_stored_with_their_shapes(scenario_c):
    conn, res = scenario_c
    rows = conn.execute("SELECT line, col, target, root_package, status, call_shape_json FROM usage_ref ORDER BY line").fetchall()
    assert [(r["line"], r["col"], r["target"], r["status"]) for r in rows] == [(7, 11, "urllib3.util.retry.Retry", "RESOLVED"), (12, 11, "urllib3.util.retry.Retry", "RESOLVED")]
    assert json.loads(rows[0]["call_shape_json"])["kw"] == ["total", "method_whitelist"] and json.loads(rows[1]["call_shape_json"])["kw"] == ["total", "backoff_factor"]


def test_the_call_is_bound_never_executed(daemon, image):
    """A callee whose body raises if it is ever called: binding must not run it. The harness binds placeholders to the signature only."""
    import tempfile
    from pathlib import Path

    from faultline.oracles.artifacts import prepare_artifact
    from faultline.oracles.o_bind import run_o_bind
    from faultline.sandbox.client import SandboxClient
    from faultline.worlds.builder import WorldBuilder
    from tests.conftest import TOKEN
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=600)
    b = WorldBuilder(sbx, image)
    lock = (Path(__file__).resolve().parents[2] / "fixtures" / "repos" / "acme-http" / "requirements.lock.txt").read_text(encoding="utf-8")
    world = b.materialize(lock)
    assert b.build(world, lock).status in ("BUILT", "REUSED")
    art_dir = Path(tempfile.mkdtemp())
    (art_dir / "marker_pkg").mkdir()
    (art_dir / "marker_pkg" / "__init__.py").write_text("def danger(a, b=1):\n    raise RuntimeError('the call was made')\n", encoding="utf-8")
    art = prepare_artifact(art_dir, daemon.store)
    sites = [{"id": "x.py:1:0", "callee": "marker_pkg.danger", "n_positional": 1, "keyword_names": ["b"], "has_star_args": False, "has_star_kwargs": False},
             {"id": "x.py:2:0", "callee": "marker_pkg.danger", "n_positional": 0, "keyword_names": ["zzz"], "has_star_args": False, "has_star_kwargs": False},
             {"id": "x.py:3:0", "callee": "marker_pkg.missing", "n_positional": 0, "keyword_names": [], "has_star_args": False, "has_star_kwargs": False},
             {"id": "x.py:4:0", "callee": "marker_pkg.danger", "n_positional": 0, "keyword_names": [], "has_star_args": True, "has_star_kwargs": False},
             {"id": "x.py:5:0", "callee": "package_not_in_this_world.thing", "n_positional": 0, "keyword_names": [], "has_star_args": False, "has_star_kwargs": False}]
    r = run_o_bind(sbx, image, world_hash=world.world_hash, artifact_hash=art, sites=sites, top_level="marker_pkg", pythonpath=("/artifact",))
    by = {e.entry: e for e in r.entries}
    assert by["bind:x.py:1:0"].passed                                         # it binds, and the body (which raises if it ever runs) did not run
    assert not by["bind:x.py:2:0"].passed and by["bind:x.py:2:0"].exc_type == "TypeError" and by["bind:x.py:2:0"].message   # a wrong shape does not bind
    assert not by["bind:x.py:3:0"].passed and by["bind:x.py:3:0"].exc_type == "AttributeError"            # the symbol is gone
    assert by["bind:x.py:4:0"].skipped and not by["bind:x.py:4:0"].passed                                     # star arguments: not claimed either way
    assert by["bind:x.py:5:0"].not_applicable and by["bind:x.py:5:0"].failure_class.value == "NONE"           # a package this world does not contain is not a break
    assert not any("the call was made" in (e.message or "") for e in r.entries)
    assert r.failure_class.value == "ARTIFACT_FAILURE"


def test_the_analysis_view_serves_each_cells_oracle_plan_for_the_world_matrix(scenario_c):
    from faultline.analysis.read import analysis_view
    conn, res = scenario_c
    cell = analysis_view(conn, res.analysis_id).cells[0]
    plan = {p.oracle: p for p in cell.oracle_plan}
    assert plan["o_import"].status == "RAN" and plan["o_bind"].status == "RAN" and len(plan["o_bind"].entries) == 2
    assert plan["o_tests"].status == "NOT_PLANNED" and plan["o_tests"].reason                  # an oracle that did not run says why
