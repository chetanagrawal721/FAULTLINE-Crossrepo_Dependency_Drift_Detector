"""Relationship signals between Python projects in different repositories. Every signal carries the evidence rows that
justify it: a snapshot file path and a line. A same-name package or a version difference is never enough on its own."""
import json
import re
import sqlite3
from dataclasses import dataclass, field

GITHUB_URL = re.compile(r"github\.com[/:]([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?(?:[@#/]|$)", re.I)


@dataclass(frozen=True)
class Evidence:
    signal: str                    # published_name | git_dep | name_collision | model_twin
    project_id: str
    file_path: str
    line: int
    excerpt: str


@dataclass
class Candidate:
    producer_id: str
    consumer_id: str
    kind: str                      # SHARED_ARTIFACT | SUSPECTED_TWIN
    level: str                     # L2 | L3P
    confidence: str                # HIGH | LOW
    actionable: bool
    status: str                    # ACTIVE | SUSPECTED
    evidence: list[Evidence] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True)
class PyProject:
    id: str
    repo_id: str
    repo_slug: str                 # owner/name, lower case
    rel_path: str
    published: str | None          # canonical distribution name, None for requirement-only projects
    snapshot_id: str
    manifests: tuple[tuple[str, str, str | None], ...]    # (path, kind, parsed_json)


def load_projects(conn: sqlite3.Connection, analysis_project_id: str) -> list[PyProject]:
    out = []
    rows = conn.execute(
        "SELECT p.id, p.rel_path, p.published_name, p.origin, s.id AS snap, r.id AS repo, r.owner, r.name FROM project p "
        "JOIN snapshot s ON s.id = p.snapshot_id JOIN repository r ON r.id = s.repository_id AND r.pinned_sha = s.sha "
        "WHERE r.analysis_project_id=? AND p.ecosystem='pypi' ORDER BY r.owner, r.name, p.rel_path", (analysis_project_id,)).fetchall()
    for r in rows:
        mf = tuple((m["path"], m["kind"], m["parsed_json"]) for m in
                   conn.execute("SELECT path, kind, parsed_json FROM manifest WHERE project_id=? ORDER BY path", (r["id"],)))
        published = r["published_name"] if r["origin"] in ("pyproject", "setup_cfg") else None
        out.append(PyProject(r["id"], r["repo"], f"{r['owner']}/{r['name']}".lower(), r["rel_path"], published, r["snap"], mf))
    return out


def declared(project: PyProject) -> list[dict]:
    """Runtime-relevant dependencies the project declares (main group and optional extras), with manifest path and line."""
    out = []
    for path, kind, parsed in project.manifests:
        if kind not in ("pyproject", "requirements") or not parsed:
            continue
        for d in json.loads(parsed).get("dependencies", []):
            if d["group"] == "main" or d["group"].startswith("optional:"):
                out.append({**d, "origin": d.get("origin") or path})
    return out


def producer_name_evidence(producer: PyProject) -> Evidence | None:
    for path, kind, parsed in producer.manifests:
        if kind == "pyproject" and parsed:
            meta = json.loads(parsed).get("meta", {})
            if meta.get("name") and meta.get("name_line"):
                return Evidence("published_name", producer.id, path, int(meta["name_line"]), f"name = {meta['name']!r}")
    return None


def repo_of_url(url: str | None) -> str | None:
    m = GITHUB_URL.search(url or "")
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def find_line(conn_text: str | None, needle: str) -> int:
    """Last resort: first line that mentions the needle (so evidence still points somewhere real)."""
    for i, ln in enumerate((conn_text or "").splitlines(), 1):
        if needle.lower() in ln.lower():
            return i
    return 1


def candidates(producers: list[PyProject], consumers: list[PyProject]) -> list[Candidate]:
    """L2 candidates: a consumer declares a dependency that is the producer's published name or its git URL."""
    out: list[Candidate] = []
    for prod in producers:
        if not prod.published:
            continue
        name_ev = producer_name_evidence(prod)
        for cons in consumers:
            if cons.repo_id == prod.repo_id:
                continue                                           # cross-repository relationships only
            for d in declared(cons):
                if d["name"] != prod.published:
                    pointed = repo_of_url(d["source_ref"]) if d["kind"] == "vcs" else None
                    if pointed and pointed == prod.repo_slug:      # a git dependency on the producer's repository, other name
                        ev = Evidence("git_dep", cons.id, d["origin"], d["line"] or 1, f"{d['display']} @ {d['source_ref']}")
                        out.append(Candidate(prod.id, cons.id, "SHARED_ARTIFACT", "L2", "HIGH", True, "ACTIVE", [ev, *( [name_ev] if name_ev else [])]))
                    continue
                pointed = repo_of_url(d["source_ref"]) if d["kind"] == "vcs" else None
                line = d["line"] or 1
                excerpt = f"{d['display']}{d['specifier']}" + (f" @ {d['source_ref']}" if d["source_ref"] else "")
                if d["kind"] == "vcs" and pointed != prod.repo_slug:
                    # same name, but the source is a different repository: a collision, never an actionable relationship
                    ev = Evidence("name_collision", cons.id, d["origin"], line, excerpt)
                    out.append(Candidate(prod.id, cons.id, "SHARED_ARTIFACT", "L2", "LOW", False, "SUSPECTED", [ev, *([name_ev] if name_ev else [])],
                                         f"{cons.repo_slug} depends on a package named {prod.published} from {pointed or d['source_ref']}, not from {prod.repo_slug}"))
                    continue
                signal = "git_dep" if pointed == prod.repo_slug else "published_name"
                cev = Evidence(signal, cons.id, d["origin"], line, excerpt)
                out.append(Candidate(prod.id, cons.id, "SHARED_ARTIFACT", "L2", "HIGH", True, "ACTIVE", [cev, *([name_ev] if name_ev else [])]))
                break                                              # one relationship per (producer, consumer) pair
    return out
