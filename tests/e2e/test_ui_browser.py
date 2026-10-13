"""M4.7 browser end to end (Playwright + Chromium) against a RUNNING stack and REAL public GitHub repositories.

    python tools/fl.py up                      (in another terminal)
    FAULTLINE_BASE_URL=http://127.0.0.1:8000 python -m pytest tests/e2e/test_ui_browser.py

It needs network access to github.com. Skipped when the stack or Playwright is not available.
"""
import json
import os
import re
import secrets
import urllib.request

import pytest

BASE = os.environ.get("FAULTLINE_BASE_URL", "http://127.0.0.1:8000")
PRODUCER = ("https://github.com/pallets/flask", "3.0.3")
CONSUMER = ("https://github.com/maxcountryman/flask-login", "")


def api(path, method="GET", body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


@pytest.fixture(scope="module")
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        api("/api/health")
    except OSError:
        pytest.skip(f"no Faultline stack at {BASE}")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium is not installed: {e}")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        yield pg
        browser.close()


@pytest.fixture(scope="module")
def fresh_project():
    """A new project, so the UI (which shows the newest project) starts empty."""
    return api("/api/projects", "POST", {"name": f"browser e2e {secrets.token_hex(3)}"})["id"]


def add_repo(page, url, ref):
    page.get_by_label("GitHub repository URL").fill(url)
    page.get_by_label("Ref").fill(ref)
    page.get_by_role("button", name="Add repository").click()


def test_tc_4_7_1_two_urls_end_to_end_in_a_real_browser(page, fresh_project):
    page.goto(BASE + "/")
    page.get_by_test_id("repositories-panel").wait_for()
    add_repo(page, *PRODUCER)
    page.get_by_test_id("pinned-sha").first.wait_for(timeout=60000)
    page.get_by_text("INGESTED").first.wait_for(timeout=240000)
    add_repo(page, *CONSUMER)
    page.wait_for_function("document.querySelectorAll('[data-testid=repo-card]').length >= 2", timeout=60000)
    page.wait_for_function("[...document.querySelectorAll('[data-testid=repo-card]')].every(c => c.innerText.includes('INGESTED'))", timeout=300000)
    shas = page.get_by_test_id("pinned-sha").all_inner_texts()
    assert len(shas) == 2 and all(re.fullmatch(r"[0-9a-f]{10}", s) for s in shas)

    for card in page.get_by_test_id("repo-card").all():                     # worlds must be resolved before the cross-repo run
        href = card.get_by_test_id("inspect-link").get_attribute("href")
        rid = href.split("/")[-1]
        api(f"/api/repositories/{rid}/analyze", "POST")
    page.wait_for_timeout(1000)
    for _ in range(90):
        jobs = api("/api/jobs")
        if not [j for j in jobs if j["kind"] == "analyze_repository" and j["status"] in ("QUEUED", "RUNNING")]:
            break
        page.wait_for_timeout(5000)

    page.reload()
    page.get_by_role("button", name="Run analysis").click()
    page.get_by_test_id("analysis").wait_for(timeout=600000)
    funnel = {k: page.get_by_test_id(f"funnel-{k}").inner_text() for k in ("relationships found", "actionable", "consumers discovered", "consumers analysed", "cells")}
    assert funnel["actionable"] == "1" and funnel["consumers discovered"] == "1" and funnel["consumers analysed"] == "1" and funnel["cells"] == "1"
    rel = page.get_by_test_id("relationship").first.inner_text()
    assert "pallets/flask" in rel and "maxcountryman/flask-login" in rel and "L2" in rel and "pyproject.toml" in rel
    row = page.get_by_test_id("matrix-row").first.inner_text()
    assert "flask:" not in row or "→" in row                                                    # the exact delta is displayed
    assert re.search(r"NO DIVERGENCE OBSERVED|BREAK WITNESSED|INCONCLUSIVE", row.upper().replace("_", " "))
    # what the page shows equals what the API stored
    pid = fresh_project
    stored = api(f"/api/projects/{pid}/analysis")
    assert page.get_by_test_id("analysis").get_attribute("data-analysis-id") == stored["id"]
    assert page.get_by_test_id("world-hash").first.get_attribute("title") == stored["cells"][0]["test_world_hash"]
    assert "compatible" not in page.get_by_test_id("dashboard").inner_text().lower().replace("not a statement that they are compatible", "")


def test_tc_4_7_2_the_ui_renders_exactly_the_value_the_api_returns(page, fresh_project):
    """Intercept the analysis response and replace the world hash with a value nobody has seen: the UI must show that value."""
    stored = api(f"/api/projects/{fresh_project}/analysis")
    unseen = "w_" + secrets.token_hex(20)
    mutated = json.loads(json.dumps(stored))
    mutated["cells"][0]["test_world_hash"] = unseen

    page.route(re.compile(r".*/api/projects/[^/]+/analysis$"), lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(mutated)))
    page.goto(BASE + "/")
    page.get_by_test_id("world-hash").first.wait_for(timeout=30000)
    shown = page.get_by_test_id("world-hash").first.get_attribute("title")
    assert shown == unseen and unseen[:14] in page.get_by_test_id("world-hash").first.inner_text()
    page.unroute(re.compile(r".*/api/projects/[^/]+/analysis$"))
