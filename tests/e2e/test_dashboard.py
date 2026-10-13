"""M5.6: every workspace view against persisted records, in real Chromium, including every state.

One real, multi-ecosystem analysis (live pipeline, real Docker) is built once; the browser then reads it through the real API.
State coverage (TC-5.6.7) additionally intercepts API responses to produce empty, failed, unsupported, inconclusive and
not-applicable data, because those states cannot all be produced by one run.
"""
import json
import re
import tempfile
from pathlib import Path

import pytest
from tests.liveenv import ingest_all
from tests.livefix import fixture_repo
from tests.uiserve import serve_database
from tests.unit.test_maven import API, CORE, ROOT
from tests.unit.test_npm import NESTED_LOCK, NESTED_PKG

from faultline.analysis.live import run_live_analysis
from faultline.sandbox.client import SandboxClient
from faultline.storage.db import connect
from faultline.storage.migrate import migrate

pytestmark = pytest.mark.docker
sync_api = pytest.importorskip("playwright.sync_api")


def corrupt_hashes(text: str) -> str:
    return re.sub(r"sha256:([0-9a-f])", lambda m: "sha256:" + ("0" if m.group(1) != "0" else "1"), text)


@pytest.fixture(scope="module")
def full_run(daemon, image):
    from tests.conftest import TOKEN
    tmp = Path(tempfile.mkdtemp())
    conn = connect(tmp / "t.db")
    migrate(conn)
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=900)
    git = "acme-models @ git+https://github.com/faultline-demo/acme-models@scenario-X\n"
    bad = fixture_repo("billing-svc/H")
    bad["requirements.lock.txt"] = corrupt_hashes(bad["requirements.lock.txt"].decode()).encode()
    repos = {
        "rm_dash_acme": ("faultline-demo/acme-models", fixture_repo("acme-models")),
        "rm_dash_notify": ("faultline-demo/notify-svc", fixture_repo("notify-svc/D")),
        "rm_dash_orders": ("faultline-demo/orders-svc", fixture_repo("orders-svc/D")),
        "rm_dash_billing": ("faultline-demo/billing-svc", fixture_repo("billing-svc/H")),
        "rm_dash_private": ("faultline-demo/private-svc", {"requirements.txt": ("--extra-index-url https://pypi.internal.example/simple\n" + git).encode()}),
        "rm_dash_badhash": ("faultline-demo/badhash-svc", {**{k: v for k, v in bad.items() if k.startswith("requirements")}, "requirements.txt": git.encode()}),
        "rm_dash_legacy": ("faultline-demo/legacy-web", fixture_repo("legacy-web/L")),
        "rm_dash_polyglot": ("faultline-demo/polyglot", {
            "web/package.json": json.dumps(NESTED_PKG).encode(), "web/package-lock.json": json.dumps(NESTED_LOCK).encode(),
            "java/pom.xml": ROOT.encode(), "java/core/pom.xml": CORE.encode(), "java/api/pom.xml": API.encode(),
            "legacy/setup.py": b"from setuptools import setup\nsetup()\n"}),
    }
    apid, ids = ingest_all(conn, sbx, image, daemon.store, repos)
    res = run_live_analysis(conn, sbx, image, daemon.store, apid)
    return conn, res, apid, tmp


@pytest.fixture(scope="module")
def site(full_run):
    conn, res, apid, tmp = full_run
    with serve_database(conn, tmp) as base:
        yield base


@pytest.fixture(scope="module")
def chromium():
    """Launched first, so a machine without Chromium skips before the expensive real analysis is built."""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium is not installed: {e}")
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def page(chromium, site):
    yield chromium.new_context(viewport={"width": 1400, "height": 1000}).new_page()


def api_json(site, path):
    import urllib.request
    with urllib.request.urlopen(site + path, timeout=30) as r:
        return json.loads(r.read())


def current(site, full_run):
    conn, res, apid, tmp = full_run
    return api_json(site, f"/api/projects/{apid}/analysis")


def open_overview(page, site):
    page.goto(site + "/#/app")
    page.get_by_test_id("analysis").wait_for(timeout=30000)


def count_of(page, key):
    return int(page.get_by_test_id(f"funnel-{key}").locator("small").inner_text().split()[0])


def test_tc_5_6_1_funnel_counts_equal_the_api(page, site, full_run):
    a = current(site, full_run)
    f = a["funnel"]
    open_overview(page, site)
    by_state = f["cells_by_state"]
    verdicts = [c["verdict"] for c in a["cells"] if c["verdict"]]
    repos = sum(len(p["repositories"]) for p in api_json(site, "/api/projects"))
    assert count_of(page, "submitted") == repos and count_of(page, "relationships") == f["relationships_discovered"]
    assert count_of(page, "worlds") == f["cells"] == len(a["cells"])
    assert count_of(page, "oracles") == by_state.get("ANALYZED", 0) + by_state.get("INCONCLUSIVE", 0)
    assert count_of(page, "witness") == sum(1 for v in verdicts if v in ("BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED")) and count_of(page, "verdict") == len(verdicts)
    # partial coverage: 3 of 5 consumers analysed, both gaps explained on the world matrix
    assert f["consumers_discovered"] == 5 and f["consumers_analysed"] == 3 and f["suspected"] == 1
    page.goto(site + "/#/app/worlds")
    page.get_by_test_id("coverage").wait_for(timeout=30000)
    cov = page.get_by_test_id("coverage").inner_text()
    assert "3" in cov and "5" in cov and "of" in cov and "count, not a score" in cov                      # the denominator is shown, and it is not a score
    bar = page.locator(".coverage-bar").inner_text()
    assert "1 unsupported" in bar and "1 failed" in bar and len(a["failed"]) == 2


def test_tc_5_6_2_world_matrix_has_supported_failed_unsupported_and_no_drift_cells(page, site, full_run):
    a = current(site, full_run)
    page.goto(site + "/#/app/worlds")
    page.get_by_test_id("matrix").wait_for(timeout=30000)
    rows = page.get_by_test_id("matrix-row").all()
    assert sorted(r.get_attribute("data-cell-state") for r in rows) == ["ANALYZED", "ANALYZED", "NO_DRIFT"]
    failed = {r.get_attribute("data-cell-state"): r.inner_text() for r in page.get_by_test_id("matrix-failed-row").all()}
    assert set(failed) == {"UNSUPPORTED", "FAILED"}
    assert "private_index_without_lock" in failed["UNSUPPORTED"] and "hash_mismatch" in failed["FAILED"]
    brk = next(c for c in a["cells"] if c["verdict"] == "BREAK_WITNESSED")
    assert {d["name"] for d in brk["delta"]} == {"itsdangerous", "werkzeug"}
    text = page.get_by_test_id("matrix").inner_text()
    assert "BREAK WITNESSED" in text and "NO DIVERGENCE OBSERVED" in text
    page.get_by_test_id("matrix-row").filter(has_text="BREAK WITNESSED").first.click()                     # select the break to see its worlds and delta
    page.get_by_test_id("runtime").first.wait_for(timeout=15000)
    runtime = page.get_by_test_id("runtime").first.inner_text()
    assert "cpython 3.12.15" in runtime and "linux/amd64" in runtime
    body = page.locator(".workspace-content").inner_text()
    assert "flat site-packages" in body                                                                       # importer visibility for Python
    delta = page.get_by_text("Exact delta against the reference").locator("xpath=ancestor::section[1]").inner_text()
    assert "werkzeug" in delta and "2.2.3" in delta and "3.0.6" in delta
    assert page.get_by_test_id("world-hash").first.get_attribute("title") == a["cells"][0]["ref_world_hash"]


def break_finding(site):
    return next(f for f in api_json(site, "/api/findings?mode=LIVE") if f["verdict"] == "BREAK_WITNESSED")


def test_tc_5_6_3_witness_detail_shows_six_fresh_runs_signature_and_raw_output(page, site):
    f = break_finding(site)
    page.goto(f"{site}/#/app/witness/{f['finding_id']}")
    page.get_by_test_id("run-board").wait_for(timeout=30000)
    cards = page.get_by_test_id("run-card").all()
    assert len(cards) == 6 and all("Fresh execution" in c.inner_text() and "Yes" in c.inner_text() for c in cards)
    assert "artifact failure" in page.get_by_test_id("run-board").inner_text().lower()                        # failure taxonomy shown
    assert sum(1 for c in cards if c.get_attribute("data-side") == "ref") == 3
    sig = page.get_by_test_id("signature").inner_text()
    detail = api_json(site, f"/api/findings/{f['finding_id']}")
    w = detail["witnesses"][0]["signature"]
    assert w["exc_type"] in sig and w["message_norm"] in sig and "url_quote" in sig
    assert "url_quote" in page.locator("pre.code-block").first.inner_text()
    assert "Satisfied" in page.get_by_test_id("witness-rule").inner_text() and "3 / 3 fresh passes" in page.get_by_test_id("witness-rule").inner_text() or "3 / 3" in page.get_by_test_id("witness-rule").inner_text()
    page.goto(f"{site}/#/app/finding/{f['finding_id']}")
    page.get_by_test_id("repeatability").wait_for(timeout=30000)
    assert "6/6" in page.get_by_test_id("repeatability").inner_text()
    rows = page.get_by_test_id("run-rows").locator("tbody tr").all()
    assert len(rows) == 6 and all("fresh execution" in r.inner_text() for r in rows)


def test_tc_5_6_4_why_path_chain_and_unanalysed_links(page, site):
    f = break_finding(site)
    page.goto(f"{site}/#/app/finding/{f['finding_id']}")
    page.get_by_test_id("why-path-panel").wait_for(timeout=30000)
    step = lambda k: page.get_by_test_id(f"why-step-{k}")  # noqa: E731
    rel = step("relationship").text_content() or ""
    assert "requirements.txt:" in rel and "pyproject.toml:" in rel and "@" in rel                              # file, line and pinned commit
    assert "werkzeug: 2.2.3 -> 3.0.6" in (step("delta").text_content() or "")
    assert "o_import: RAN" in (step("oracle").text_content() or "")
    verdict = step("verdict").text_content() or ""
    assert "verdict-policy/1" in verdict and "3 fresh reference passes" in verdict
    att = step("attribution")
    assert att.get_attribute("data-status") == "analysed" and "werkzeug" in (att.text_content() or "") and "attribution experiment (forced world)" in (att.text_content() or "")
    # a finding that was never attributed says so instead of inventing a cause
    h = next(x for x in api_json(site, "/api/findings?mode=LIVE") if x["verdict"] == "NO_DIVERGENCE_OBSERVED")
    page.goto(f"{site}/#/app/finding/{h['finding_id']}")
    page.get_by_test_id("why-path-panel").wait_for(timeout=30000)
    na = step("attribution")
    assert na.get_attribute("data-status") == "not_analysed" and "No attribution was computed" in (na.text_content() or "")


def test_tc_5_6_5_findings_filter_and_the_suspected_tray(page, site):
    page.goto(site + "/#/app/findings")
    page.get_by_test_id("findings-list").wait_for(timeout=30000)
    kinds = {r.get_attribute("data-verdict") for r in page.get_by_test_id("finding-row").all()}
    assert {"BREAK_WITNESSED", "NO_DIVERGENCE_OBSERVED"} <= kinds
    page.get_by_label("Filter by verdict").select_option("BREAK_WITNESSED")
    page.wait_for_function("[...document.querySelectorAll('[data-testid=finding-row]')].every(r => r.dataset.verdict === 'BREAK_WITNESSED')")
    assert page.get_by_test_id("finding-row").count() >= 1
    tray = page.get_by_test_id("suspected-item")
    assert tray.count() == 1 and "legacy-web" in tray.first.inner_text() and "L3P" in tray.first.inner_text()
    assert "not a finding" in tray.first.inner_text()
    assert not any("legacy-web" in r.inner_text() for r in page.get_by_test_id("finding-row").all())            # displayed in the tray never makes it a finding
    assert all(f["verdict"] != "SUSPECTED" for f in api_json(site, "/api/findings"))


def test_tc_5_6_6_inventory_graph_covers_ecosystems_edges_levels_and_unsupported_nodes(page, site):
    page.goto(site + "/#/app/inventory")
    page.get_by_test_id("inventory-graph").wait_for(timeout=30000)
    g = page.get_by_test_id("inventory-graph")
    for kind in ("repository", "project", "manifest", "package"):
        assert page.get_by_test_id(f"node-{kind}").count() >= 1, kind
    text = g.text_content() or ""
    assert page.get_by_test_id("edge-consumes").count() >= 3 and "L2 consumes" in text
    assert page.get_by_test_id("edge-suspected").count() == 1 and "L3P suspected" in text
    unsupported = [n.text_content() or "" for n in page.locator("[data-testid=node-project][data-status=unsupported]").all()]
    assert unsupported and any("Maven: declared-dependency inventory only" in t or "unsupported" in t for t in unsupported)
    assert "setup.py is read statically and never executed" in (page.get_by_test_id("inventory-legend").text_content() or "")
    ecos = {n.get_attribute("data-status") for n in page.locator("[data-testid=node-project]").all()}
    assert "unsupported" in ecos and "ok" in ecos
    assert "package-lock.json" in text and "pom.xml" in text                                                     # npm and Maven manifests are present


def stub(page, pattern, body=None, status=200):
    page.route(re.compile(pattern), lambda route: route.fulfill(status=status, content_type="application/json", body=json.dumps(body)))


def test_tc_5_6_7_every_state_renders_a_distinct_truthful_message(page, site, full_run):
    real = current(site, full_run)
    seen: dict[str, str] = {}

    def visit(url):
        page.goto(url)
        page.reload()                                         # a hash-only navigation would keep the old React state

    def capture(view, kind):
        loc = page.get_by_test_id(f"state-{view}-{kind}").first
        loc.wait_for(timeout=15000)
        assert loc.get_attribute("data-state") == kind
        seen[f"{view}/{kind}"] = loc.inner_text()

    analysis_url = r".*/api/projects/[^/]+/analysis$"
    # ---- funnel: empty (no analysis), failed (API error)
    page.unroute_all()
    stub(page, analysis_url, {"error": {"code": "NOT_FOUND", "message": "this project has not been analysed yet", "details": {}}}, 404)
    visit(site + "/#/app")
    capture("funnel", "empty")
    page.unroute_all()
    stub(page, analysis_url, {"error": {"code": "INTERNAL", "message": "boom", "details": {}}}, 500)
    visit(site + "/#/app")
    capture("funnel", "failed")
    # ---- funnel/matrix: zero consumers discovered, unsupported and failed consumers, inconclusive and not-applicable cells
    page.unroute_all()
    zero = json.loads(json.dumps(real))
    zero["funnel"]["consumers_discovered"] = 0
    zero["funnel"]["cells"] = 0
    zero["cells"], zero["failed"] = [], []
    stub(page, analysis_url, zero)
    visit(site + "/#/app")
    capture("funnel", "empty")
    visit(site + "/#/app/worlds")
    capture("matrix", "empty")
    page.unroute_all()
    mixed = json.loads(json.dumps(real))
    base_cell = mixed["cells"][0]
    inc = {**base_cell, "id": "c_inc", "verdict": "INCONCLUSIVE", "headline": "Could not check", "state": "ANALYZED", "attribution": None}
    nap = {**base_cell, "id": "c_na", "verdict": None, "state": "NOT_APPLICABLE", "finding_id": None, "headline": None, "attribution": None, "delta": []}
    mixed["cells"] = [inc, nap]
    mixed["failed"] = [{"consumer": "x/unsup", "producer": "p/a", "side": "consumer", "reason": "needs_build", "text": "no wheel"},
                       {"consumer": "x/fail", "producer": "p/a", "side": "consumer", "reason": "hash_mismatch", "text": "bad hash"}]
    stub(page, analysis_url, mixed)
    visit(site + "/#/app/worlds")
    capture("matrix", "inconclusive")
    capture("matrix", "not-applicable")
    capture("matrix", "unsupported")
    capture("matrix", "failed")
    # ---- findings
    page.unroute_all()
    stub(page, r".*/api/findings(\?.*)?$", [])
    visit(site + "/#/app/findings")
    capture("findings", "empty")
    page.unroute_all()
    stub(page, r".*/api/findings(\?.*)?$", {"error": {"code": "X", "message": "db down", "details": {}}}, 500)
    visit(site + "/#/app/findings")
    capture("findings", "failed")
    page.unroute_all()
    rows = api_json(site, "/api/findings?mode=LIVE")
    inc_row = {**rows[0], "verdict": "INCONCLUSIVE", "headline": "Could not check x"}
    stub(page, r".*/api/findings(\?.*)?$", [inc_row])
    visit(site + "/#/app/findings")
    capture("finding", "inconclusive")
    # ---- suspected tray
    page.unroute_all()
    stub(page, analysis_url, {**real, "relationships": [r for r in real["relationships"] if r["status"] != "SUSPECTED"]})
    visit(site + "/#/app/findings")
    capture("tray", "empty")
    # ---- why-path
    page.unroute_all()
    fid = break_finding(site)["finding_id"]
    stub(page, r".*/api/findings/[^/]+/why-path$", {"error": {"code": "NOT_FOUND", "message": "nope", "details": {}}}, 404)
    visit(f"{site}/#/app/finding/{fid}")
    capture("why-path", "failed")
    # ---- inventory
    page.unroute_all()
    stub(page, r".*/api/projects/[^/]+/inventory$", {"project_id": "p", "nodes": [], "edges": []})
    visit(site + "/#/app/inventory")
    capture("inventory", "empty")
    page.unroute_all()
    stub(page, r".*/api/projects/[^/]+/inventory$", {"error": {"code": "X", "message": "broken", "details": {}}}, 500)
    visit(site + "/#/app/inventory")
    capture("inventory", "failed")
    page.unroute_all()
    # distinct, truthful: no two different states share a message, and none claims a pass
    by_kind: dict[str, set[str]] = {}
    for key, text in seen.items():
        by_kind.setdefault(key.split("/")[1], set()).add(text.split("\n")[0])
        assert "compatible" not in text.lower() and "all clear" not in text.lower()
    titles = {kind: next(iter(v)) for kind, v in by_kind.items()}
    assert len(set(titles.values())) == len(titles) == 5, titles                                         # five states, five different titles
    assert {"empty", "failed", "unsupported", "inconclusive", "not-applicable"} == set(titles)


def test_the_workspace_shows_no_prototype_or_illustrative_data_and_every_view_loads(page, site, full_run):
    """The redesign draws every view from the API. No view may fall back to sample content, and none may fail to load."""
    f = break_finding(site)
    routes = ["", "/new", "/run", "/findings", f"/finding/{f['finding_id']}", "/worlds", f"/witness/{f['finding_id']}", "/relationships", "/inventory", "/evidence", "/jobs",
              "/repository", "/coverage", "/settings"]
    for r in routes:
        page.goto(f"{site}/#/app{r}")
        page.reload()
        page.locator(".workspace-content h1").wait_for(timeout=30000)
        page.wait_for_timeout(1200)
        text = page.locator(".workspace-content").inner_text().lower()
        assert "illustrative" not in text and "prototype" not in text and "example.com" not in text, r
        assert page.locator("[role=alert]").count() == 0, (r, page.locator("[role=alert]").all_inner_texts())
