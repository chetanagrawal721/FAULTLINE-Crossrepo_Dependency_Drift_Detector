"""Why-path and inventory graph read models, built only from persisted rows. A link that was not analysed says so; it is never invented."""
import json
import sqlite3

from ..core.errors import NotFoundError
from ..core.views import GraphEdge, GraphNode, InventoryGraph, WhyPath, WhyStep
from .read import _attribution, _commit, _label, latest_analysis_id


def why_path(conn: sqlite3.Connection, finding_id: str) -> WhyPath:
    f = conn.execute("SELECT * FROM finding WHERE id=?", (finding_id,)).fetchone()
    if f is None:
        raise NotFoundError(f"finding {finding_id} not found")
    scope = json.loads(f["scope_json"] or "{}")
    steps: list[WhyStep] = []
    rels = [r["evidence_id"] for r in conn.execute("SELECT evidence_id FROM finding_evidence WHERE finding_id=? AND evidence_kind='RELATIONSHIP'", (finding_id,))]
    if rels:
        items = []
        for rid in rels:
            for e in conn.execute("SELECT * FROM relationship_evidence WHERE relationship_id=?", (rid,)):
                items.append(f"{e['signal']}: {_label(conn, e['project_id']).split(':')[0]}@{_commit(conn, e['project_id'])[:10]} "
                             f"{e['file_path']}:{e['line']} - {e['excerpt']}")
        steps.append(WhyStep(kind="relationship", status="analysed", title="Why these repositories are related",
                             detail="Evidence read at the pinned commits (file and line).", items=items))
    else:
        steps.append(WhyStep(kind="relationship", status="not_analysed", title="Why these repositories are related",
                             detail="This finding has no stored relationship evidence (a fixture-mode finding)."))
    delta = scope.get("delta")
    if delta is not None:
        steps.append(WhyStep(kind="delta", status="analysed", title="What differs between the two worlds",
                             detail="Candidate causes, not findings by themselves.",
                             items=[f"{d['name']}: {d['reference'] or 'absent'} -> {d['consumer'] or 'absent'}" for d in delta]))
    else:
        steps.append(WhyStep(kind="delta", status="not_analysed", title="What differs between the two worlds", detail="No delta was stored for this finding."))
    plan = scope.get("oracle_plan")
    if plan:
        steps.append(WhyStep(kind="oracle", status="analysed", title="What was run", detail="Oracles planned and run for this cell.",
                             items=[f"{p['oracle']}: {p['status']}" + (f" ({p['reason']})" if p.get("reason") else "") for p in plan]))
    else:
        steps.append(WhyStep(kind="oracle", status="not_analysed", title="What was run", detail="No oracle plan was stored."))
    steps.append(WhyStep(kind="verdict", status="analysed", title="Why this verdict", detail=f["headline"],
                         items=[f"verdict: {f['verdict']}", f"policy: {scope.get('policy', 'unknown')}",
                                "predicate (for a witness): 3 fresh reference passes and 3 fresh consumer failures with the same normalised signature",
                                *[f"not checked: {n}" for n in scope.get("not_checked", [])]]))
    att = _attribution(conn, f["cell_id"])
    if att is None:
        steps.append(WhyStep(kind="attribution", status="not_analysed", title="Which difference caused it",
                             detail="No attribution was computed for this finding (only witnessed breaks are attributed)."))
    else:
        claim = f" ({att.minimal_claim})" if att.minimal_claim else " (not claimed as minimal)"
        steps.append(WhyStep(kind="attribution", status="analysed", title="Which difference caused it",
                             detail=f"{att.status}, {att.sidedness.replace('_', '-')}: " + (", ".join(att.minimal) or "no single cause") + claim,
                             items=[f"[attribution experiment (forced world)] {t.direction}: {', '.join(t.subset) or '(none)'} -> {t.outcome}"
                                    for t in att.attempts]))
    return WhyPath(finding_id=finding_id, verdict=f["verdict"], steps=steps)


def inventory_graph(conn: sqlite3.Connection, project_id: str) -> InventoryGraph:
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    for r in conn.execute("SELECT * FROM repository WHERE analysis_project_id=? ORDER BY owner, name", (project_id,)):
        rid = f"repo:{r['id']}"
        nodes[rid] = GraphNode(id=rid, kind="repository", label=f"{r['owner']}/{r['name']}", status="ok" if r["status"] == "INGESTED" else "failed",
                               detail=f"pinned {(r['pinned_sha'] or '')[:10]}")
        projects = conn.execute(
            "SELECT p.*, (SELECT status FROM project_world WHERE project_id=p.id ORDER BY resolved_at DESC LIMIT 1) AS wstatus "
            "FROM project p JOIN snapshot s ON s.id=p.snapshot_id WHERE s.repository_id=? AND s.sha=? ORDER BY p.rel_path", (r["id"], r["pinned_sha"])).fetchall()
        for p in projects:
            pid = f"prj:{p['id']}"
            unsupported = p["ecosystem"] == "maven" or p["origin"] == "setup_py"
            status = "unsupported" if unsupported else ("failed" if p["wstatus"] == "FAILED" else "ok")
            note = ("Maven: declared-dependency inventory only, no resolution" if p["ecosystem"] == "maven" else
                    "setup.py is read statically and never executed; only literal dependencies are used" if p["origin"] == "setup_py" else
                    (f"world {p['wstatus']}" if p["wstatus"] else None))
            where = "" if p["rel_path"] == "." else f" ({p['rel_path']})"
            nodes[pid] = GraphNode(id=pid, kind="project", label=(p["display_name"] or p["published_name"] or p["rel_path"]) + where,
                                   ecosystem=p["ecosystem"], status=status, detail=note)
            edges.append(GraphEdge(source=rid, target=pid, kind="contains"))
            for m in conn.execute("SELECT * FROM manifest WHERE project_id=? ORDER BY path LIMIT 12", (p["id"],)):
                mid = f"mf:{m['id']}"
                mstatus = "ok" if m["parse_status"] in ("OK", "PARTIAL") else "unsupported" if m["parse_status"] == "UNSUPPORTED" else "failed"
                nodes[mid] = GraphNode(id=mid, kind="manifest", label=m["path"], ecosystem=p["ecosystem"], status=mstatus,
                                       detail=f"{m['kind']} ({m['parse_status']})")
                edges.append(GraphEdge(source=pid, target=mid, kind="declares"))
            top = conn.execute("SELECT pv.name, pv.version FROM project_world pw JOIN world_entry we ON we.world_hash=pw.world_hash "
                               "JOIN package_version pv ON pv.id=we.package_version_id WHERE pw.project_id=? AND pw.status!='FAILED' "
                               "ORDER BY pv.name LIMIT 8", (p["id"],)).fetchall()
            for t in top:
                kid = f"pkg:{p['id']}:{t['name']}"
                nodes[kid] = GraphNode(id=kid, kind="package", label=f"{t['name']} {t['version']}", ecosystem=p["ecosystem"])
                edges.append(GraphEdge(source=pid, target=kid, kind="declares"))
    aid = latest_analysis_id(conn, project_id)
    if aid:
        for rel in conn.execute("SELECT * FROM relationship WHERE analysis_id=?", (aid,)):
            edges.append(GraphEdge(source=f"prj:{rel['producer_project_id']}", target=f"prj:{rel['consumer_project_id']}",
                                   kind="consumes" if rel["actionable"] else "suspected", label=rel["kind"], level=rel["level"]))
    return InventoryGraph(project_id=project_id, nodes=list(nodes.values()), edges=edges)
