"""M3.6: npm worlds are recorded and shown through the API per package instance and per importer."""
import json

from faultline.parsers.common import SnapshotFS
from faultline.parsers.npm.discover import discover_npm
from faultline.worlds.canonical import ensure_npm_world
from tests.integration.test_worlds_canonical import snapshot_row
from tests.snapshots import make_snapshot
from tests.unit.test_npm import NESTED_LOCK, NESTED_PKG, WS_LOCK, WS_PKG


def record(conn, tmp_path, files):
    sid = snapshot_row(conn)
    conn.execute("UPDATE repository SET pinned_sha=? WHERE id='repo_t'", ("a" * 40,))
    root, inv = make_snapshot(tmp_path, {k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in files.items()})
    return [ensure_npm_world(conn, sid, SnapshotFS(root), p) for p in discover_npm(root, inv)]


def test_npm_world_is_persisted_and_inspectable_per_instance(client, conn, tmp_path):
    [pw] = record(conn, tmp_path, {"package.json": NESTED_PKG, "package-lock.json": NESTED_LOCK})
    assert pw.status == "OK" and pw.world_hash
    projects = client.get("/api/repositories/repo_t/projects").json()
    w = projects[0]["world"]
    assert projects[0]["ecosystem"] == "npm" and w["status"] == "OK" and w["source"] == "lockfile"
    by_loc = {p["locator"]: p for p in w["packages"]}
    assert set(by_loc) >= {"node_modules/shared", "node_modules/a/node_modules/shared"}          # two instances of one package
    assert by_loc["node_modules/a/node_modules/shared"]["resolved"] == "1.0.0" and by_loc["node_modules/a/node_modules/shared"]["visible_to"] == ["node_modules/a"]
    assert by_loc["node_modules/shared"]["visible_to"] == ["node_modules/b"]        # only importers that depend on it; the root does not
    assert by_loc["node_modules/a"]["declared"][0]["spec"] == "^1.0.0"
    assert any("install scripts" in x or "never run" in x for x in projects[0]["notes"])
    assert w["reproducibility"]["lockfile"]["version"] == 3


def test_workspace_world_and_failures_through_the_api(client, conn, tmp_path):
    files = {"package.json": WS_PKG, "package-lock.json": WS_LOCK, "packages/app/package.json": {"name": "@acme/app"}, "packages/lib/package.json": {"name": "@acme/lib"},
             "svc/package.json": {"name": "svc", "dependencies": {"x": "1"}}}
    res = record(conn, tmp_path, files)
    assert [r.status for r in res] == ["OK", "FAILED"]
    projects = {p["rel_path"]: p for p in client.get("/api/repositories/repo_t/projects").json()}
    assert projects["svc"]["world"]["failure"]["reason"] == "no_lockfile" and projects["svc"]["world"]["packages"] == []
    lib = next(p for p in projects["."]["world"]["packages"] if p["locator"] == "packages/lib")
    assert "packages/app" in lib["visible_to"]                                                    # the app sees the sibling workspace


def test_unsupported_lockfile_world_is_failed_not_clean(client, conn, tmp_path):
    [pw] = record(conn, tmp_path, {"package.json": NESTED_PKG, "package-lock.json": {**NESTED_LOCK, "lockfileVersion": 1}})
    assert pw.status == "FAILED" and pw.world_hash is None
    w = client.get("/api/repositories/repo_t/projects").json()[0]["world"]
    assert w["status"] == "FAILED" and w["packages"] == [] and w["failure"]["reason"] == "lock_unsupported"
