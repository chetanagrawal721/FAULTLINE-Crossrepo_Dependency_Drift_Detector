"""M2.4 API: projects, repositories, pinned SHAs and distinct failure states. GitHub is a fake transport; no network."""
import json

import pytest

from faultline.ingestion.github import GitHubClient

SHA = "c" * 40
META = {"default_branch": "main", "fork": False, "archived": False, "private": False}
COMMIT = {"sha": SHA, "commit": {"committer": {"date": "2026-02-03T04:05:06Z"}}}


def gh(responses):
    def transport(url, headers):
        for key, (status, hdrs, body) in responses.items():
            if url.endswith(key):
                return status, hdrs, json.dumps(body).encode()
        raise AssertionError(f"unexpected {url}")
    return GitHubClient(token=None, transport=transport)


@pytest.fixture
def api(client):
    client.app.state.github = gh({"/repos/o/r": (200, {}, META), "/commits/main": (200, {}, COMMIT)})
    pid = client.post("/api/projects", json={"name": "demo"}).json()["id"]
    return client, pid


def test_create_and_list_projects(client):
    r = client.post("/api/projects", json={"name": "  demo  "})
    assert r.status_code == 201 and r.json()["name"] == "demo" and r.json()["repositories"] == []
    assert [p["id"] for p in client.get("/api/projects").json()] == [r.json()["id"]]
    assert client.post("/api/projects", json={"name": "   "}).status_code == 400
    assert client.get("/api/projects/ap_missing").status_code == 404


def test_submitting_a_repository_pins_the_sha_and_queues_one_job(api):
    c, pid = api
    r = c.post(f"/api/projects/{pid}/repositories", json={"url": "https://github.com/o/r"})
    assert r.status_code == 202
    b = r.json()
    assert b["pinned_sha"] == SHA and b["status"] == "PENDING" and b["snapshot"] is None and b["job_id"]
    assert b["url"] == "https://github.com/o/r" and b["committed_at"] == "2026-02-03T04:05:06Z"
    job = c.get(f"/api/jobs/{b['job_id']}").json()
    assert job["kind"] == "ingest_repository" and job["status"] == "QUEUED"
    again = c.post(f"/api/projects/{pid}/repositories", json={"url": "https://github.com/o/r/"}).json()
    assert again["id"] == b["id"] and again["job_id"] == b["job_id"]                    # same repo, same SHA: same job
    assert c.get(f"/api/repositories/{b['id']}").json()["pinned_sha"] == SHA
    assert c.get(f"/api/projects/{pid}").json()["repositories"][0]["id"] == b["id"]
    assert c.get(f"/api/repositories/{b['id']}/files").json() == []                      # nothing ingested yet


@pytest.mark.parametrize("url", ["file:///etc/passwd", "git@github.com:o/r.git", "https://evil.example/o/r", "http://github.com/o/r",
                                 "https://user:pw@github.com/o/r"])
def test_invalid_urls_are_rejected_before_any_network_call(api, url):
    c, pid = api
    c.app.state.github = gh({})                         # any request would raise AssertionError
    r = c.post(f"/api/projects/{pid}/repositories", json={"url": url})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REPOSITORY"


def test_tc_2_4_2_failure_states_are_distinct(api):
    c, pid = api
    url = {"url": "https://github.com/o/r"}
    seen = {}
    cases = {
        "deleted": {"/repos/o/r": (404, {}, {"message": "Not Found"})},
        "private": {"/repos/o/r": (200, {}, {**META, "private": True})},
        "forbidden": {"/repos/o/r": (403, {}, {"message": "Repository access blocked"})},
        "rate": {"/repos/o/r": (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"}, {"message": "API rate limit exceeded"})},
        "badref": {"/repos/o/r": (200, {}, META), "/commits/nope": (404, {}, {"message": "Not Found"})},
        "upstream": {"/repos/o/r": (503, {}, {})},
    }
    for name, resp in cases.items():
        c.app.state.github = gh(resp)
        body = {**url, "ref": "nope"} if name == "badref" else url
        r = c.post(f"/api/projects/{pid}/repositories", json=body)
        seen[name] = (r.status_code, r.json()["error"]["code"], r.json()["error"]["details"].get("retryable"))
    assert seen["deleted"] == (404, "REPOSITORY_NOT_FOUND", False)
    assert seen["private"] == (403, "REPOSITORY_NOT_ACCESSIBLE", False)
    assert seen["forbidden"] == (403, "REPOSITORY_NOT_ACCESSIBLE", False)
    assert seen["rate"] == (429, "GITHUB_RATE_LIMITED", True)
    assert seen["badref"] == (404, "REF_NOT_FOUND", False)
    assert seen["upstream"] == (502, "FETCH_FAILED", True)
    assert len({v[1] for v in seen.values()}) == 5                                       # five distinct states
    assert c.get(f"/api/projects/{pid}").json()["repositories"] == []                    # failures leave no half-created repo


def test_retry_only_for_failed_ingestions_and_keeps_the_sha(api):
    c, pid = api
    b = c.post(f"/api/projects/{pid}/repositories", json={"url": "https://github.com/o/r"}).json()
    assert c.post(f"/api/repositories/{b['id']}/retry").status_code == 409                # still PENDING
    from faultline.storage.db import connect
    conn = connect(c.app.state.settings.db_path)
    conn.execute("UPDATE repository SET status='FAILED', error_json=? WHERE id=?",
                 (json.dumps({"code": "FETCH_FAILED", "message": "x", "retryable": True}), b["id"]))
    conn.close()
    got = c.get(f"/api/repositories/{b['id']}").json()
    assert got["status"] == "FAILED" and got["error"]["retryable"] is True
    r = c.post(f"/api/repositories/{b['id']}/retry")
    assert r.status_code == 202 and r.json()["pinned_sha"] == SHA and r.json()["status"] == "PENDING"
    assert r.json()["job_id"] != b["job_id"]                                              # a new job, the same commit


def test_moving_ref_repoints_and_requeues(api):
    c, pid = api
    first = c.post(f"/api/projects/{pid}/repositories", json={"url": "https://github.com/o/r"}).json()
    c.app.state.github = gh({"/repos/o/r": (200, {}, META), "/commits/main": (200, {}, {**COMMIT, "sha": "d" * 40})})
    second = c.post(f"/api/projects/{pid}/repositories", json={"url": "https://github.com/o/r"}).json()
    assert second["id"] == first["id"] and second["pinned_sha"] == "d" * 40 and second["job_id"] != first["job_id"]
