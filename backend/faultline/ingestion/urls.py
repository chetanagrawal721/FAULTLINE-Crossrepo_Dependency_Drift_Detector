"""Validation of repository inputs. Only https://github.com/<owner>/<repo>[/tree/<ref>|/commit/<sha>] is accepted.

Everything else is rejected before any network call: other hosts and schemes, credentials, ports, local paths,
queries, fragments, non-ASCII look-alikes and malformed refs. This also closes SSRF: Faultline never fetches a
user-supplied URL, it builds the clone URL itself from the validated owner and repository.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..core.errors import ErrorCode, FaultlineError

OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
REF = re.compile(r"^[A-Za-z0-9._/+@-]{1,200}$")
HEX = re.compile(r"^[0-9a-fA-F]{7,40}$")


class InvalidRepository(FaultlineError):
    code = ErrorCode.INVALID_REPOSITORY
    http_status = 400


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str
    ref: str | None = None          # branch, tag or (abbreviated) sha as requested; None = default branch

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"


def validate_ref(ref: str) -> str:
    bad = (".." in ref or ref.startswith(("-", "/", ".")) or ref.endswith(("/", ".", ".lock")) or "//" in ref
           or "@{" in ref or ref == "@" or not REF.match(ref) or any(p.startswith(".") or p.endswith(".lock") for p in ref.split("/")))
    if bad:
        raise InvalidRepository(f"invalid git ref {ref[:60]!r}")
    return ref


def validate_github_url(url: str, ref: str | None = None) -> RepoRef:
    if not isinstance(url, str) or not url.strip() or len(url) > 300:
        raise InvalidRepository("a repository URL is required")
    url = url.strip()
    if not url.isascii() or any(ord(c) < 32 for c in url):
        raise InvalidRepository("the URL contains characters that are not allowed")
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise InvalidRepository("only https://github.com URLs are accepted")
    if parts.netloc != "github.com":                      # also rejects userinfo (a@github.com), ports and subdomains
        raise InvalidRepository("only github.com repositories are accepted")
    if parts.query or parts.fragment:
        raise InvalidRepository("the URL must not contain a query string or fragment")
    segs = [s for s in parts.path.split("/") if s != ""]
    if "//" in parts.path.rstrip("/") or len(segs) < 2:
        raise InvalidRepository("expected https://github.com/<owner>/<repo>")
    owner, name = segs[0], segs[1].removesuffix(".git")
    if not OWNER.match(owner) or not REPO.match(name) or name in (".", ".."):
        raise InvalidRepository("invalid owner or repository name")
    url_ref: str | None = None
    rest = segs[2:]
    if rest:
        if rest[0] in ("tree", "commit") and len(rest) >= 2:
            url_ref = "/".join(rest[1:])
        elif rest[:2] == ["releases", "tag"] and len(rest) >= 3:
            url_ref = "/".join(rest[2:])
        else:
            raise InvalidRepository("unsupported URL path; use https://github.com/<owner>/<repo>[/tree/<ref>]")
    chosen = ref if ref else url_ref
    if ref and url_ref and ref != url_ref:
        raise InvalidRepository("the ref in the URL and the ref field disagree")
    if chosen is not None:
        validate_ref(chosen)
    return RepoRef(owner, name, chosen)


def looks_like_sha(ref: str) -> bool:
    return bool(HEX.match(ref))
