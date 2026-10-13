"""TC-2.1.1 and the GitHub client's error mapping (TC-2.1.3, TC-2.4.2 foundations). No network."""
import json

import pytest

from faultline.core.errors import ErrorCode
from faultline.ingestion.github import GitHubClient, GitHubError
from faultline.ingestion.urls import InvalidRepository, RepoRef, validate_github_url

VALID = [
    ("https://github.com/octocat/Hello-World", RepoRef("octocat", "Hello-World")),
    ("https://github.com/octocat/Hello-World/", RepoRef("octocat", "Hello-World")),
    ("https://github.com/octocat/Hello-World.git", RepoRef("octocat", "Hello-World")),
    ("https://github.com/pallets/flask/tree/2.2.x", RepoRef("pallets", "flask", "2.2.x")),
    ("https://github.com/pallets/flask/tree/release/2.2", RepoRef("pallets", "flask", "release/2.2")),
    ("https://github.com/pallets/flask/commit/ab12cd3", RepoRef("pallets", "flask", "ab12cd3")),
    ("https://github.com/pallets/flask/releases/tag/2.2.2", RepoRef("pallets", "flask", "2.2.2")),
    ("  https://github.com/a/b  ", RepoRef("a", "b")),
]
INVALID = [
    "", "   ", "github.com/a/b", "http://github.com/a/b", "ftp://github.com/a/b", "file:///etc/passwd", "/etc/passwd",
    "C:\\repo", "git@github.com:a/b.git", "ssh://git@github.com/a/b", "https://user:pw@github.com/a/b",
    "https://a@github.com/a/b", "https://github.com:8443/a/b", "https://www.github.com/a/b",
    "https://gist.github.com/a/b", "https://evilgithub.com/a/b", "https://github.com.evil.com/a/b",
    "https://github.com/a", "https://github.com/", "https://github.com/a/b/issues/1", "https://github.com/a/b/pull/3",
    "https://github.com/a/b?x=1", "https://github.com/a/b#frag", "https://github.com/-bad/b", "https://github.com/a/..",
    "https://github.com/a/.", "https://github.com/a/b/tree/../../etc", "https://github.com/a/b/tree/-x",
    "https://github.com/\u0430/b", "https://github.com/a/b\x00", "https://github.com/a/b c",
    "https://github.com/a//b", "x" * 400, None, 5,
]


@pytest.mark.parametrize("url,expected", VALID)
def test_tc_2_1_1_valid_urls(url, expected):
    assert validate_github_url(url) == expected


@pytest.mark.parametrize("url", INVALID)
def test_tc_2_1_1_invalid_inputs_are_rejected(url):
    with pytest.raises(InvalidRepository) as ei:
        validate_github_url(url)
    assert ei.value.code == ErrorCode.INVALID_REPOSITORY


@pytest.mark.parametrize("ref", ["..", "a..b", "-rf", "/abs", "a/", "a//b", "x.lock", "a b", "a~1", "a^", "a:b", "a?b",
                                 "a*", "a[", "a\\b", "@{u}", ".hidden", "a/.b", "ok/x.lock", "a" * 201])
def test_invalid_refs(ref):
    with pytest.raises(InvalidRepository):
        validate_github_url("https://github.com/a/b", ref)


def test_explicit_ref_and_url_ref_must_agree_and_clone_url_is_built_by_us():
    r = validate_github_url("https://github.com/a/b/tree/v1", "v1")
    assert r.ref == "v1" and r.clone_url == "https://github.com/a/b.git" and r.slug == "a/b"
    with pytest.raises(InvalidRepository):
        validate_github_url("https://github.com/a/b/tree/v1", "v2")


# ---------------------------------------------------------------------- GitHub client with a fake transport

def fake(responses):
    calls = []

    def transport(url, headers):
        calls.append((url, headers))
        for key, (status, hdrs, body) in responses.items():
            if url.endswith(key):
                return status, hdrs, json.dumps(body).encode() if not isinstance(body, bytes) else body
        raise AssertionError(f"unexpected request {url}")
    transport.calls = calls
    return transport


META = {"default_branch": "main", "fork": False, "archived": False, "private": False}
COMMIT = {"sha": "a" * 40, "commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}}


def test_resolve_default_branch_and_explicit_ref():
    t = fake({"/repos/a/b": (200, {}, META), "/commits/main": (200, {}, COMMIT), "/commits/v1": (200, {}, {**COMMIT, "sha": "b" * 40})})
    c = GitHubClient(token=None, transport=t)
    d = c.resolve(RepoRef("a", "b"))
    assert d.sha == "a" * 40 and d.resolved_ref == "main" and d.requested_ref is None
    assert c.resolve(RepoRef("a", "b", "v1")).sha == "b" * 40


def test_token_is_sent_only_in_the_authorization_header():
    t = fake({"/repos/a/b": (200, {}, META), "/commits/main": (200, {}, COMMIT)})
    GitHubClient(token="tok123", transport=t).resolve(RepoRef("a", "b"))
    assert all(h.get("Authorization") == "Bearer tok123" for _, h in t.calls) and all("tok123" not in u for u, _ in t.calls)


def test_rate_limit_is_retryable_and_says_when():
    reset = "9999999999"
    t = fake({"/repos/a/b": (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": reset}, {"message": "API rate limit exceeded"})})
    with pytest.raises(GitHubError) as ei:
        GitHubClient(transport=t).resolve(RepoRef("a", "b"))
    e = ei.value
    assert e.code == ErrorCode.GITHUB_RATE_LIMITED and e.retryable and e.http_status == 429 and e.details["retry_after_seconds"] > 0


def test_deleted_is_not_found_private_is_not_accessible_both_not_retryable():
    t = fake({"/repos/a/b": (404, {}, {"message": "Not Found"})})
    with pytest.raises(GitHubError) as ei:
        GitHubClient(transport=t).resolve(RepoRef("a", "b"))
    assert ei.value.code == ErrorCode.REPOSITORY_NOT_FOUND and not ei.value.retryable
    t = fake({"/repos/a/b": (200, {}, {**META, "private": True})})
    with pytest.raises(GitHubError) as ei:
        GitHubClient(transport=t).resolve(RepoRef("a", "b"))
    assert ei.value.code == ErrorCode.REPOSITORY_NOT_ACCESSIBLE and ei.value.http_status == 403 and not ei.value.retryable


def test_missing_ref_in_an_existing_repository_is_ref_not_found():
    t = fake({"/repos/a/b": (200, {}, META), "/commits/nope": (404, {}, {"message": "Not Found"})})
    with pytest.raises(GitHubError) as ei:
        GitHubClient(transport=t).resolve(RepoRef("a", "b", "nope"))
    assert ei.value.code == ErrorCode.REF_NOT_FOUND


def test_server_errors_are_retryable_and_sha_must_match():
    t = fake({"/repos/a/b": (503, {}, {})})
    with pytest.raises(GitHubError) as ei:
        GitHubClient(transport=t).resolve(RepoRef("a", "b"))
    assert ei.value.retryable
    t = fake({"/repos/a/b": (200, {}, META), "/commits/abcdef1": (200, {}, {**COMMIT, "sha": "9" * 40})})
    with pytest.raises(GitHubError):
        GitHubClient(transport=t).resolve(RepoRef("a", "b", "abcdef1"))
