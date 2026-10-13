"""M4.7 browser end to end (Playwright + Chromium) against a RUNNING stack and REAL public GitHub repositories.

    python tools/fl.py up                      (in another terminal)
    FAULTLINE_BASE_URL=http://127.0.0.1:8000 python -m pytest tests/e2e/test_ui_browser.py

It needs network access to github.com. Skipped when the stack or Playwright is not available.
The person's path through the workspace: New analysis -> two repository URLs -> pinned inputs -> run -> overview, relationships and world matrix.
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
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        yield pg
        browser.close()


def newest_live_project():
    return api("/api/projects?mode=LIVE")[0]["id"]


def test_tc_4_7_1_two_urls_end_to_end_in_a_real_browser(page):
    page.goto(BASE + "/#/app/new")
    page.reload()
    page.get_by_label("Producer repository URL").fill(PRODUCER[0])
    page.get_by_label("Producer ref").fill(PRODUCER[1])
    page.get_by_label("Consumer repository URL").fill(CONSUMER[0])
    page.get_by_role("button", name="Pin repositories").click()
    page.get_by_test_id("review-inputs").wait_for(timeout=90000)
    page.wait_for_function("document.querySelectorAll('[data-testid=repo-card]').length >= 2", timeout=60000)
    shas = page.get_by_test_id("pinned-sha").all_inner_texts()
    assert len(shas) == 2 and all(re.fullmatch(r"[0-9a-f]{10}", s) for s in shas)                      # a ref became one immutable commit before anything ran
    page.wait_for_function("[...document.querySelectorAll('[data-testid=repo-card]')].every(c => c.innerText.toLowerCase().includes('pinned and fetched'))", timeout=300000)

    page.get_by_role("checkbox").check()
    page.get_by_role("button", name="Run analysis").click()
    page.get_by_test_id("submitted").wait_for(timeout=60000)
    page.get_by_role("button", name="Open the analysis run").click()
    page.get_by_text("Result available").wait_for(timeout=900000)                                      # the run view follows the real job until it is DONE

    pid = newest_live_project()
    stored = api(f"/api/projects/{pid}/analysis")
    f = stored["funnel"]
    assert f["relationships_actionable"] == 1 and f["consumers_discovered"] == 1 and f["consumers_analysed"] == 1 and f["cells"] == 1

    page.goto(BASE + "/#/app")
    page.get_by_test_id("analysis").wait_for(timeout=60000)
    assert page.get_by_test_id("analysis").get_attribute("data-analysis-id") == stored["id"]
    assert page.get_by_test_id("funnel-relationships").locator("small").inner_text().startswith("1 ")
    assert page.get_by_test_id("funnel-worlds").locator("small").inner_text().startswith("1 ")

    page.goto(BASE + "/#/app/relationships")
    rel = page.get_by_test_id("relationship").first
    rel.wait_for(timeout=30000)
    shown = rel.inner_text()
    assert "pallets/flask" in shown and "maxcountryman/flask-login" in shown and "L2" in shown
    assert "pyproject.toml" in page.locator(".workspace-content").inner_text()                           # file-level evidence for the relationship

    page.goto(BASE + "/#/app/worlds")
    row = page.get_by_test_id("matrix-row").first
    row.wait_for(timeout=30000)
    assert re.search(r"NO DIVERGENCE OBSERVED|BREAK WITNESSED|INCONCLUSIVE", row.inner_text().upper())
    assert page.get_by_test_id("world-hash").first.get_attribute("title") == stored["cells"][0]["ref_world_hash"]   # what the page shows equals what the API stored
    assert "compatible" not in page.locator(".workspace-content").inner_text().lower().replace("not a statement that they are compatible", "")


def test_tc_4_7_2_the_ui_renders_exactly_the_value_the_api_returns(page):
    """Intercept the analysis response and replace the world hash with a value nobody has seen: the UI must show that value."""
    stored = api(f"/api/projects/{newest_live_project()}/analysis")
    unseen = "w_" + secrets.token_hex(20)
    mutated = json.loads(json.dumps(stored))
    mutated["cells"][0]["ref_world_hash"] = unseen

    page.route(re.compile(r".*/api/projects/[^/]+/analysis$"), lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(mutated)))
    page.goto(BASE + "/#/app/worlds")
    page.reload()
    page.get_by_test_id("world-hash").first.wait_for(timeout=30000)
    shown = page.get_by_test_id("world-hash").first.get_attribute("title")
    assert shown == unseen and unseen[:14] in page.get_by_test_id("world-hash").first.inner_text()
    page.unroute(re.compile(r".*/api/projects/[^/]+/analysis$"))
