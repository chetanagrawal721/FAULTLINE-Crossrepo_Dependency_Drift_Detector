"""Minimal parser for fully pinned lock files (`name==version --hash=sha256:...`).

Phase 1 only: it reads the lock files committed in the fixture repositories so that worlds come from recorded
inputs, not from guesses. It is not a general requirements parser (that is milestone M3.2). Anything it does not
understand raises, so a malformed lock can never be treated as an empty world.
"""
import re
from dataclasses import dataclass

from ..core.errors import ErrorCode, FaultlineError

_LINE = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[A-Za-z0-9.!+_-]+)(?P<rest>.*)$")
_HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


@dataclass(frozen=True)
class PinnedRequirement:
    name: str            # canonical (PEP 503): lower case, runs of - _ . collapsed to "-"
    display_name: str
    version: str
    hashes: tuple[str, ...]


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pinned_lock(text: str) -> list[PinnedRequirement]:
    """Parse a hash-pinned lock. Continuation lines (trailing backslash) are joined."""
    logical: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            buf += line[:-1].strip() + " "
            continue
        logical.append((buf + line).strip())
        buf = ""
    if buf:
        raise FaultlineError("lock file ends with a dangling line continuation", code=ErrorCode.MANIFEST_PARSE_FAILED)
    out: list[PinnedRequirement] = []
    seen: set[str] = set()
    for line in logical:
        if line.startswith(("-", "git+", "http", ".", "/")) or " @ " in line:
            raise FaultlineError(f"unsupported lock entry: {line[:80]!r}", code=ErrorCode.MANIFEST_PARSE_FAILED)
        m = _LINE.match(line)
        if not m:
            raise FaultlineError(f"cannot parse lock entry: {line[:80]!r}", code=ErrorCode.MANIFEST_PARSE_FAILED)
        hashes = tuple(sorted(set(_HASH.findall(m["rest"]))))
        leftover = _HASH.sub("", m["rest"]).replace(";", "").strip()
        if leftover:
            raise FaultlineError(f"unsupported content after pin: {leftover[:60]!r}", code=ErrorCode.MANIFEST_PARSE_FAILED)
        cn = canonical_name(m["name"])
        if cn in seen:
            raise FaultlineError(f"duplicate package in lock: {cn}", code=ErrorCode.MANIFEST_PARSE_FAILED)
        seen.add(cn)
        out.append(PinnedRequirement(cn, m["name"], m["version"], hashes))
    if not out:
        raise FaultlineError("lock file contains no packages", code=ErrorCode.MANIFEST_PARSE_FAILED)
    return sorted(out, key=lambda r: r.name)


def diff_locks(ref: list[PinnedRequirement], test: list[PinnedRequirement]) -> dict[str, tuple[str | None, str | None]]:
    """Packages whose version differs (or that exist on one side only): name -> (ref_version, test_version)."""
    r = {x.name: x.version for x in ref}
    t = {x.name: x.version for x in test}
    return {n: (r.get(n), t.get(n)) for n in sorted(set(r) | set(t)) if r.get(n) != t.get(n)}


def render_lock(reqs: list[PinnedRequirement]) -> str:
    """Write requirements back out in the same hash-pinned format (one logical line per package)."""
    lines = []
    for r in sorted(reqs, key=lambda x: x.name):
        lines.append(" ".join([f"{r.display_name}=={r.version}", *(f"--hash=sha256:{h}" for h in r.hashes)]))
    return "\n".join(lines) + "\n"
