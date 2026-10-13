"""GitHub REST client (stdlib only). Used by the control plane to turn a ref into an immutable commit SHA.

The token, if any, stays in this process: it is never passed to a container. The transport is injectable so tests
can simulate rate limits, deleted repositories and moving tags without network access.
"""
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from ..core.errors import ErrorCode, FaultlineError
from .urls import RepoRef, looks_like_sha

API = "https://api.github.com"


class GitHubError(FaultlineError):
    def __init__(self, message: str, code: ErrorCode, http_status: int, *, retryable: bool = False, details: dict | None = None):
        super().__init__(message, code=code, details={"retryable": retryable, **(details or {})})
        self.http_status = http_status
        self.retryable = retryable


@dataclass(frozen=True)
class Resolved:
    sha: str
    committed_at: str
    default_branch: str
    is_fork: bool
    is_archived: bool
    requested_ref: str | None
    resolved_ref: str            # the ref that was actually resolved (default branch when none was requested)


Transport = Callable[[str, dict], tuple[int, dict, bytes]]


def urllib_transport(url: str, headers: dict) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GitHubError(f"could not reach GitHub: {e}", ErrorCode.FETCH_FAILED, 502, retryable=True) from e


class GitHubClient:
    def __init__(self, token: str | None = None, transport: Transport | None = None):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        self.transport = transport or urllib_transport

    def _get(self, path: str) -> dict:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "faultline-hacktopia"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        status, hdrs, body = self.transport(API + path, headers)
        h = {k.lower(): v for k, v in hdrs.items()}
        if status == 200:
            return json.loads(body or b"{}")
        if status in (403, 429) and (h.get("x-ratelimit-remaining") == "0" or status == 429 or "rate limit" in body.decode("utf-8", "replace").lower()):
            reset = h.get("x-ratelimit-reset")
            wait = max(0, int(reset) - int(time.time())) if reset and reset.isdigit() else None
            raise GitHubError("GitHub rate limit reached; retry later (a GITHUB_TOKEN raises the limit)",
                              ErrorCode.GITHUB_RATE_LIMITED, 429, retryable=True, details={"retry_after_seconds": wait})
        if status in (401, 403):
            raise GitHubError("repository is not accessible (private, or access is restricted); only public repositories "
                              "are supported", ErrorCode.REPOSITORY_NOT_ACCESSIBLE, 403)
        if status == 404:
            raise GitHubError("repository or ref not found, or not accessible", ErrorCode.REPOSITORY_NOT_FOUND, 404)
        if status == 422:
            raise GitHubError("GitHub could not resolve that ref", ErrorCode.REF_NOT_FOUND, 404)
        raise GitHubError(f"GitHub answered HTTP {status}", ErrorCode.FETCH_FAILED, 502, retryable=status >= 500)

    def resolve(self, repo: RepoRef) -> Resolved:
        meta = self._get(f"/repos/{repo.owner}/{repo.name}")
        if meta.get("private"):
            raise GitHubError("private repositories are not supported", ErrorCode.REPOSITORY_NOT_ACCESSIBLE, 403)
        ref = repo.ref or meta["default_branch"]
        try:
            commit = self._get(f"/repos/{repo.owner}/{repo.name}/commits/{ref}")
        except GitHubError as e:
            if e.code == ErrorCode.REPOSITORY_NOT_FOUND:      # the repository exists, so the ref is what is missing
                raise GitHubError(f"ref {ref!r} was not found in {repo.slug}", ErrorCode.REF_NOT_FOUND, 404) from e
            raise
        sha = commit["sha"]
        if repo.ref and looks_like_sha(repo.ref) and not sha.startswith(repo.ref.lower()):
            raise GitHubError("the SHA does not resolve to itself", ErrorCode.REF_NOT_FOUND, 404)
        return Resolved(sha=sha, committed_at=commit["commit"]["committer"]["date"], default_branch=meta["default_branch"],
                        is_fork=bool(meta.get("fork")), is_archived=bool(meta.get("archived")), requested_ref=repo.ref,
                        resolved_ref=ref)
