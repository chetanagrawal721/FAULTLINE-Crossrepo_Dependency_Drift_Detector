"""M3.7: Maven projects are recorded as a declared-dependency inventory and never as a resolved world."""
from faultline.parsers.common import SnapshotFS
from faultline.parsers.maven.pom import discover_maven
from faultline.worlds.canonical import ensure_maven_project
from tests.integration.test_worlds_canonical import snapshot_row
from tests.snapshots import make_snapshot
from tests.unit.test_maven import API, CORE, ROOT


def test_maven_inventory_through_the_api(client, conn, tmp_path):
    sid = snapshot_row(conn)
    conn.execute("UPDATE repository SET pinned_sha=? WHERE id='repo_t'", ("a" * 40,))
    root, inv = make_snapshot(tmp_path, {"pom.xml": ROOT, "core/pom.xml": CORE, "api/pom.xml": API})
    for p in discover_maven(root, inv):
        ensure_maven_project(conn, sid, SnapshotFS(root), p)
    projects = {p["rel_path"]: p for p in client.get("/api/repositories/repo_t/projects").json()}
    assert set(projects) == {".", "core", "api"} and all(p["ecosystem"] == "maven" for p in projects.values())
    assert all(p["world"] is None for p in projects.values())                                    # no world, no resolution claim
    assert any("resolution is not performed" in n for n in projects["core"]["notes"])
    inv_by = {d["name"]: d for d in projects["core"]["inventory"]}
    assert inv_by["com.fasterxml.jackson.core:jackson-databind"]["version"] == "2.17.0"
    assert inv_by["com.fasterxml.jackson.core:jackson-databind"]["version_source"] == "managed"
    api_deps = {d["name"]: d for d in projects["api"]["inventory"]}
    assert api_deps["org.unknown:no-version"]["version"] is None and api_deps["org.unknown:no-version"]["note"]
    assert projects["core"]["name"] == "com.acme:acme-core" and projects["core"]["origin"] == "pom"
