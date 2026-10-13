"""requirements.txt / constraints parser. Handles -r and -c includes inside the snapshot, markers, extras, URLs, VCS
requirements and hashes. Unknown syntax becomes a diagnostic; nothing is executed and nothing outside the snapshot is read."""
import re

from packaging.requirements import InvalidRequirement, Requirement

from ...core.errors import ErrorCode
from ..common import (
    Dependency,
    Diagnostic,
    ManifestError,
    ManifestResult,
    PathEscape,
    SnapshotFS,
    canonical_name,
    failed,
)

MAX_DEPTH = 8
VCS_SCHEMES = ("git+", "hg+", "svn+", "bzr+")
HASH = re.compile(r"--hash[= ]sha256:([0-9a-fA-F]{64})")
FLAG_ONLY = {"--pre", "--prefer-binary", "--require-hashes", "--no-index", "--no-deps", "--no-cache-dir", "--use-pep517",
             "--no-use-pep517", "--no-build-isolation"}
VALUE_OPTS = {"--only-binary", "--no-binary", "--trusted-host", "--use-feature", "--python-version", "--platform",
              "--implementation", "--abi"}
EGG = re.compile(r"[#&]egg=([A-Za-z0-9][A-Za-z0-9._-]*)")
COMMENT = re.compile(r"(^|\s)#.*$")


def _logical_lines(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    buf, start = "", 0
    for n, raw in enumerate(text.splitlines(), 1):
        if not buf:
            start = n
        if raw.rstrip().endswith("\\"):
            buf += raw.rstrip()[:-1] + " "
            continue
        line = COMMENT.sub("", buf + raw).strip()
        buf = ""
        if line:
            out.append((start, line))
    if buf.strip():
        out.append((start, COMMENT.sub("", buf).strip()))
    return out


def _split_option(line: str) -> tuple[str, str]:
    """('-r', 'other.txt') for '-r other.txt', '--requirement=other.txt' and '-rother.txt'."""
    if line.startswith("--"):
        key, _, val = line.partition("=") if "=" in line.split()[0] else (line.split()[0], " ", " ".join(line.split()[1:]))
        return key, val.strip()
    key = line[:2]
    return key, line[2:].strip()


def _dep_from_requirement(req: Requirement, group: str, origin: str, line: int, hashes: tuple[str, ...]) -> Dependency:
    kind, ref = "registry", None
    if req.url:
        kind = "vcs" if req.url.startswith(VCS_SCHEMES) else ("path" if req.url.startswith("file:") else "url")
        ref = req.url
    return Dependency(name=canonical_name(req.name), display=req.name, specifier=str(req.specifier),
                      extras=tuple(sorted(req.extras)), marker=str(req.marker) if req.marker else None, kind=kind,
                      source_ref=ref, group=group, origin=origin, line=line, hashes=hashes)


def _bare_target(text: str, group: str, origin: str, line: int, res: ManifestResult, editable: bool) -> Dependency | None:
    """A requirement written as a URL, VCS URL or local path, with no `name @` prefix."""
    if "://" in text or text.startswith(VCS_SCHEMES):
        m = EGG.search(text)
        if not m:
            res.add("BARE_URL_NO_NAME", f"URL requirement without #egg=name; the package name is unknown: {text[:80]}", line, origin)
            return None
        kind = "vcs" if text.startswith(VCS_SCHEMES) else "url"
        return Dependency(canonical_name(m.group(1)), m.group(1), "", (), None, kind, text.split("#")[0], group, origin, line)
    try:
        SnapshotFS.join(origin, text)
    except PathEscape:
        res.add("PATH_ESCAPE", f"local path {text!r} leaves the repository", line, origin)
        res.status = "FAILED"
        return None
    base = re.sub(r"(\.tar\.gz|\.zip|\.whl|\.tar\.bz2|\.tgz)$", "", text.rstrip("/").rsplit("/", 1)[-1])
    name = base.split("-")[0] if text.endswith((".whl", ".tar.gz", ".zip", ".tgz")) else base
    return Dependency(canonical_name(name or "unknown"), name or "unknown", "", (), None, "path", text, group, origin, line)


def _parse_file(fs: SnapshotFS, rel: str, res: ManifestResult, group: str, as_constraints: bool, chain: tuple[str, ...]) -> None:
    if rel in chain:
        res.add("INCLUDE_CYCLE", f"{rel} includes itself through {' -> '.join(chain)}", None, rel)
        return
    if len(chain) >= MAX_DEPTH:
        res.add("INCLUDE_TOO_DEEP", f"include depth exceeds {MAX_DEPTH}", None, rel)
        return
    try:
        text = fs.read_text(rel)
    except ManifestError as e:
        res.diagnostics.append(Diagnostic(e.code.value, e.message, rel))
        res.status = "TOO_LARGE" if e.code == ErrorCode.MANIFEST_TOO_LARGE else "FAILED"
        return
    sink = res.constraints if as_constraints else res.dependencies
    for n, line in _logical_lines(text):
        if "${" in line:
            res.add("UNSUPPORTED_ENV_VAR", "environment-variable substitution is not supported; line skipped", n, rel)
            continue
        if line.startswith("-"):
            key, val = _split_option(line)
            if key in ("-r", "--requirement", "-c", "--constraint"):
                try:
                    target = SnapshotFS.join(rel, val)
                except PathEscape as e:
                    res.diagnostics.append(Diagnostic("PATH_ESCAPE", e.message, rel, n))
                    res.status = "FAILED"
                    continue
                if not fs.exists(target):
                    res.add("INCLUDE_MISSING", f"{target} is not in the snapshot", n, rel)
                    continue
                _parse_file(fs, target, res, group, as_constraints or key in ("-c", "--constraint"), (*chain, rel))
            elif key in ("-e", "--editable"):
                dep = _bare_target(val, group, rel, n, res, True)
                if dep:
                    sink.append(dep)
                    res.meta.setdefault("editable", []).append(val)
            elif key in ("-i", "--index-url", "--extra-index-url"):
                res.meta.setdefault("index_urls" if key != "--extra-index-url" else "extra_index_urls", []).append(val)
            elif key in ("-f", "--find-links"):
                res.meta.setdefault("find_links", []).append(val)
            elif key in FLAG_ONLY or key in VALUE_OPTS:
                res.meta.setdefault("options", []).append(f"{key} {val}".strip())
            else:
                res.add("UNSUPPORTED_OPTION", f"option {key!r} is not supported", n, rel)
            continue
        hashes = tuple(sorted({h.lower() for h in HASH.findall(line)}))
        req_text = re.sub(r"\s--[a-z-]+(?:[= ]\S+)?", "", line) if "--" in line else line
        req_text = req_text.strip()
        if req_text.startswith(("./", "../", "/")) or "://" in req_text.split(";")[0].split(" @ ")[0] or req_text.startswith(VCS_SCHEMES):
            dep = _bare_target(req_text, group, rel, n, res, False)
            if dep:
                sink.append(dep)
            continue
        try:
            sink.append(_dep_from_requirement(Requirement(req_text), group, rel, n, hashes))
        except InvalidRequirement as e:
            res.add("UNPARSEABLE_LINE", f"cannot parse {req_text[:80]!r}: {e}", n, rel)


def parse_requirements(fs: SnapshotFS, rel: str, group: str = "main") -> ManifestResult:
    kind = "constraints" if canonical_name(rel.rsplit("/", 1)[-1]).startswith("constraints") else "requirements"
    res = ManifestResult(kind, rel)
    try:
        fs.read_bytes(rel)
    except ManifestError as e:
        return failed(kind, rel, e)
    _parse_file(fs, rel, res, group, kind == "constraints", ())
    return res
