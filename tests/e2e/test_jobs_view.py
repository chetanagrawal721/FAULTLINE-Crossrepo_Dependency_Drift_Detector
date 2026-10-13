"""NFR-6: every job's status, duration and failure class are visible in the UI, read from real job records (real Chromium)."""
import time

import pytest
from tests.uiserve import serve_database

from faultline.storage import jobs
from faultline.storage.db import connect
from faultline.storage.migrate import migrate

sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("jobsui")
    conn = connect(tmp / "t.db")
    migrate(conn)

    def run(key, outcome):
        j, _ = jobs.create_job(conn, "demo_" + key, {}, key)
        jobs.claim_next(conn, "w1", 30)
        time.sleep(0.06)
        if outcome == "done":
            jobs.complete(conn, j.job_id, "w1", {})
        elif outcome == "failed":
            jobs.fail(conn, j.job_id, "w1", {"code": "HANDLER_ERROR", "message": "the handler raised"}, retryable=False)
        elif outcome == "cancelled":
            jobs.request_cancel(conn, j.job_id)
            jobs.mark_cancelled(conn, j.job_id, "w1")
        return j.job_id
    ids = {k: run(k, k) for k in ("done", "failed", "cancelled")}
    ids["running"] = run("running", "running")
    with serve_database(conn, tmp) as base:
        yield base, ids
    conn.close()


@pytest.fixture(scope="module")
def page(site):
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium is not installed: {e}")
        yield browser.new_context(viewport={"width": 1300, "height": 900}).new_page()
        browser.close()


def test_the_jobs_view_shows_status_duration_and_failure_class_for_every_job(page, site):
    base, ids = site
    page.goto(base + "/#/app/jobs")
    page.reload()
    page.get_by_test_id("jobs").wait_for(timeout=20000)
    row = lambda k: page.get_by_test_id(f"job-{ids[k]}")  # noqa: E731
    assert row("done").get_by_test_id("job-status").inner_text() == "DONE" and row("done").get_by_test_id("job-failure").inner_text() == "none"
    assert row("failed").get_by_test_id("job-status").inner_text() == "FAILED" and row("failed").get_by_test_id("job-failure").inner_text() == "HANDLER_ERROR"
    assert row("cancelled").get_by_test_id("job-status").inner_text() == "CANCELLED" and row("cancelled").get_by_test_id("job-failure").inner_text() == "CANCELLED"
    assert row("running").get_by_test_id("job-status").inner_text() == "RUNNING"
    for k in ids:                                                              # a duration is shown for every job, finished or running
        cells = row(k).locator("td").all_inner_texts()
        assert cells[2].endswith(("ms", "s")) and cells[2] != "n/a", (k, cells)
    assert "the handler raised" in row("failed").inner_text()
    nav = page.get_by_test_id("nav").inner_text()
    assert "Jobs" in nav
