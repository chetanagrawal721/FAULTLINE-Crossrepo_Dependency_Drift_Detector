"""World inspector read models. Three different things are kept apart: the range a manifest DECLARES, the version the
resolver or lockfile RESOLVED, and the version an importer can actually SEE. A failed resolution is a failure with a reason,
never an empty or clean world."""
import json
import sqlite3

from ..core.views import DeclaredView, InventoryDep, ManifestView, PackageView, ProjectDetail, WorldDetail


def _declared(conn: sqlite3.Connection, project_id: str, used: list[str] | None) -> dict[str, list[DeclaredView]]:
    """Declared ranges, only from the manifests the resolution actually used (dev and docs pins are not shown as declared)."""
    out: dict[str, list[DeclaredView]] = {}
    for m in conn.execute("SELECT parsed_json, kind FROM manifest WHERE project_id=? AND kind IN ('pyproject','requirements')", (project_id,)):
        if not m["parsed_json"]:
            continue
        for d in json.loads(m["parsed_json"]).get("dependencies", []):
            if used is not None and d["origin"] not in used or d["group"] != "main":
                continue
            out.setdefault(d["name"], []).append(DeclaredView(spec=d["specifier"], group=d["group"], marker=d["marker"],
                                                              origin=d["origin"], kind=d["kind"]))
    return out


def project_details(conn: sqlite3.Connection, snapshot_id: str) -> list[ProjectDetail]:
    out = []
    for p in conn.execute("SELECT * FROM project WHERE snapshot_id=? ORDER BY rel_path", (snapshot_id,)):
        pid = p["id"]
        manifests = [ManifestView(path=m["path"], kind=m["kind"], parse_status=m["parse_status"], parse_error=m["parse_error"])
                     for m in conn.execute("SELECT * FROM manifest WHERE project_id=? ORDER BY path", (pid,))]
        pw = conn.execute("SELECT * FROM project_world WHERE project_id=? ORDER BY resolved_at DESC LIMIT 1", (pid,)).fetchone()
        out.append(ProjectDetail(project_id=pid, rel_path=p["rel_path"], ecosystem=p["ecosystem"], name=p["display_name"] or p["published_name"],
                                 origin=p["origin"], notes=json.loads(p["notes_json"] or "[]"), manifests=manifests, world=_world(conn, pid, pw, p["ecosystem"]) if pw else None,
                                 inventory=_maven_inventory(conn, pid) if p["ecosystem"] == "maven" else []))
    return out


def _world(conn: sqlite3.Connection, project_id: str, pw: sqlite3.Row, ecosystem: str = "pypi") -> WorldDetail:
    args = json.loads(pw["resolver_args_json"] or "{}")
    cache = conn.execute("SELECT outcome_json FROM resolution_cache WHERE cache_key=?", (args.get("cache_key"),)).fetchone()
    outcome = json.loads(cache["outcome_json"]) if cache else {}
    prov = outcome.get("provenance", {})
    failure = json.loads(pw["failure_json"]) if pw["failure_json"] else None
    packages: list[PackageView] = []
    if pw["world_hash"] and pw["status"] != "FAILED" and ecosystem == "npm":
        packages = _npm_packages(conn, project_id, pw["world_hash"])
    elif pw["world_hash"] and pw["status"] != "FAILED":
        declared = _declared(conn, project_id, prov.get("declared_from"))
        visible = {r["locator"]: (r["visible_version"], r["source"]) for r in
                   conn.execute("SELECT * FROM world_visible WHERE world_hash=? AND importer=''", (pw["world_hash"],))}
        rows = conn.execute("SELECT we.locator, we.scope, we.source_kind, pv.name, pv.version, pv.artifact_sha256 FROM world_entry we "
                            "JOIN package_version pv ON pv.id = we.package_version_id WHERE we.world_hash=? ORDER BY pv.name",
                            (pw["world_hash"],)).fetchall()
        for r in rows:
            v = visible.get(r["locator"])
            packages.append(PackageView(name=r["name"], declared=declared.get(r["name"], []), resolved=r["version"],
                                        visible=v[0] if v else None, visible_source=v[1] if v else None, scope=r["scope"],
                                        source_kind=r["source_kind"], artifact_sha256=r["artifact_sha256"]))
    repro = {"cutoff": pw["resolved_at"], "platform": args.get("platform"), "python": args.get("python"), "index": args.get("index"),
             "resolver_version": args.get("resolver_version"), "flags": args.get("flags"), "cache_key": args.get("cache_key"),
             "lockfile": prov.get("lockfile"), "inputs": prov.get("inputs")}
    return WorldDetail(status=pw["status"], source=pw["source"], world_hash=pw["world_hash"], resolver=pw["resolver"],
                       cutoff=pw["resolved_at"], failure=failure, warnings=outcome.get("warnings", []),
                       private=outcome.get("private", []), reproducibility=repro, packages=packages)


def _npm_packages(conn: sqlite3.Connection, project_id: str, world_hash: str) -> list[PackageView]:
    """One row per package INSTANCE (node_modules path). Visibility is per importer, never a flat name-to-version map."""
    root_declared: dict[str, DeclaredView] = {}
    for m in conn.execute("SELECT parsed_json FROM manifest WHERE project_id=? AND kind='package_json'", (project_id,)):
        pj = json.loads(m["parsed_json"] or "{}")
        for group, key in (("main", "dependencies"), ("dev", "dev_dependencies"), ("optional", "optional_dependencies")):
            for n, spec in (pj.get(key) or {}).items():
                root_declared[n] = DeclaredView(spec=spec, group=group, marker=None, origin=pj.get("path", ""), kind="registry")
    seen_by: dict[str, list[str]] = {}
    for r in conn.execute("SELECT locator, importer FROM world_visible WHERE world_hash=? ORDER BY importer", (world_hash,)):
        seen_by.setdefault(r["locator"], []).append(r["importer"])
    out = []
    for r in conn.execute("SELECT we.locator, we.scope, we.source_kind, pv.name, pv.version FROM world_entry we JOIN package_version pv "
                          "ON pv.id = we.package_version_id WHERE we.world_hash=? ORDER BY we.locator", (world_hash,)):
        top = r["locator"] == f"node_modules/{r['name']}"
        d = root_declared.get(r["name"]) if top else None
        out.append(PackageView(name=r["name"], declared=[d] if d else [], resolved=r["version"], visible=None,
                               visible_source="per importer (simulated node_modules lookup)", scope=r["scope"],
                               source_kind=r["source_kind"], artifact_sha256=None, locator=r["locator"],
                               visible_to=["(root)" if i == "" else i for i in seen_by.get(r["locator"], [])]))
    return out


def _maven_inventory(conn: sqlite3.Connection, project_id: str) -> list[InventoryDep]:
    out = []
    for m in conn.execute("SELECT parsed_json FROM manifest WHERE project_id=? AND kind='pom'", (project_id,)):
        for d in json.loads(m["parsed_json"] or "{}").get("dependencies", []):
            out.append(InventoryDep(name=f"{d['group_id']}:{d['artifact_id']}", version=d["version"], scope=d["scope"],
                                    version_source=d["version_source"], note=d["note"]))
    return out
