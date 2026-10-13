"""M3.6: npm inventory worlds. Nested instances, per-importer visibility, workspaces, unsupported lockfiles."""
import json

import pytest

from faultline.core.enums import Ecosystem
from faultline.parsers.common import SnapshotFS
from faultline.parsers.npm.discover import discover_npm
from faultline.parsers.npm.package_json import parse_package_json
from faultline.parsers.npm.package_lock import name_from_locator, parse_package_lock
from faultline.resolvers.npm import resolve_npm_project
from faultline.resolvers.visibility import candidate_dirs, resolve_from
from tests.snapshots import make_snapshot

REG = "https://registry.npmjs.org"


def pkg(version, **kw):
    return {"version": version, "resolved": f"{REG}/x/-/x-{version}.tgz", "integrity": "sha512-" + "A" * 86 + "==", **kw}


NESTED_LOCK = {
    "name": "app", "lockfileVersion": 3, "requires": True,
    "packages": {
        "": {"name": "app", "version": "1.0.0", "dependencies": {"a": "^1.0.0", "b": "^1.0.0"}},
        "node_modules/a": pkg("1.0.0", dependencies={"shared": "^1.0.0"}),
        "node_modules/a/node_modules/shared": pkg("1.0.0"),            # a needs the OLD shared: nested instance
        "node_modules/b": pkg("1.0.0", dependencies={"shared": "^2.0.0"}),
        "node_modules/shared": pkg("2.0.0"),                             # b and the root see the hoisted NEW one
        "node_modules/@scope/pkg": pkg("3.1.4", dev=True),
    },
}
NESTED_PKG = {"name": "app", "version": "1.0.0", "dependencies": {"a": "^1.0.0", "b": "^1.0.0"}, "scripts": {"postinstall": "node -e \"require('fs').writeFileSync('CANARY','x')\""}}

WS_PKG = {"name": "mono", "private": True, "workspaces": ["packages/*"]}
WS_LOCK = {
    "name": "mono", "lockfileVersion": 3,
    "packages": {
        "": {"name": "mono", "workspaces": ["packages/*"]},
        "node_modules/@acme/lib": {"resolved": "packages/lib", "link": True},
        "node_modules/@acme/app": {"resolved": "packages/app", "link": True},
        "node_modules/lodash": pkg("4.17.21"),
        "packages/app": {"name": "@acme/app", "version": "1.0.0", "dependencies": {"@acme/lib": "^1.0.0", "lodash": "^4.0.0"}},
        "packages/lib": {"name": "@acme/lib", "version": "1.2.0", "dependencies": {"lodash": "^3.0.0"}},
        "packages/lib/node_modules/lodash": pkg("3.10.1"),
    },
}


def snap(tmp_path, files):
    return make_snapshot(tmp_path, {k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in files.items()})


def test_tc_3_6_1_nested_versions_are_preserved_and_visibility_is_per_importer(tmp_path):
    root, inv = snap(tmp_path, {"package.json": NESTED_PKG, "package-lock.json": NESTED_LOCK})
    [prj] = discover_npm(root, inv)
    out = resolve_npm_project(SnapshotFS(root), prj)
    assert out.status == "OK" and out.world.ecosystem == Ecosystem.NPM
    locs = {e.locator: e.version for e in out.world.entries}
    assert locs["node_modules/shared"] == "2.0.0" and locs["node_modules/a/node_modules/shared"] == "1.0.0"   # two instances kept
    inst = parse_package_lock(SnapshotFS(root), "package-lock.json").instances
    assert resolve_from(inst, "node_modules/a", "shared").version == "1.0.0"             # a sees its nested copy
    assert resolve_from(inst, "node_modules/b", "shared").version == "2.0.0"             # b sees the hoisted copy
    assert resolve_from(inst, "", "shared").version == "2.0.0"                           # the root sees the hoisted copy
    assert resolve_from(inst, "", "missing-pkg") is None
    vis = {(r.importer, r.name): r.version for r in out.visibility}
    assert vis[("node_modules/a", "shared")] == "1.0.0" and vis[("node_modules/b", "shared")] == "2.0.0"
    assert out.world.world_hash.startswith("w_")


def test_scoped_names_scopes_and_source_identity(tmp_path):
    root, inv = snap(tmp_path, {"package.json": NESTED_PKG, "package-lock.json": NESTED_LOCK})
    lock = parse_package_lock(SnapshotFS(root), "package-lock.json")
    sp = lock.instances["node_modules/@scope/pkg"]
    assert name_from_locator("node_modules/a/node_modules/@scope/pkg") == "@scope/pkg"
    assert sp.name == "@scope/pkg" and sp.scope == "dev" and sp.source_kind == "registry" and sp.integrity.startswith("sha512-")


def test_install_scripts_are_reported_and_never_run(tmp_path):
    root, inv = snap(tmp_path, {"package.json": NESTED_PKG, "package-lock.json": NESTED_LOCK})
    [prj] = discover_npm(root, inv)
    assert prj.package_json.install_hooks == ["postinstall"] and any("never run" in n for n in prj.notes)
    resolve_npm_project(SnapshotFS(root), prj)
    assert not (root / "CANARY").exists()


def test_tc_3_6_2_workspace_importers_and_sibling_links(tmp_path):
    files = {"package.json": WS_PKG, "package-lock.json": WS_LOCK,
             "packages/app/package.json": {"name": "@acme/app", "version": "1.0.0", "dependencies": {"@acme/lib": "^1.0.0", "lodash": "^4.0.0"}},
             "packages/lib/package.json": {"name": "@acme/lib", "version": "1.2.0", "dependencies": {"lodash": "^3.0.0"}}}
    root, inv = snap(tmp_path, files)
    projects = discover_npm(root, inv)
    assert [p.rel_path for p in projects] == ["."] and projects[0].workspace_dirs == ["packages/app", "packages/lib"]
    out = resolve_npm_project(SnapshotFS(root), projects[0])
    assert out.status == "OK" and out.importers == ["", "packages/app", "packages/lib"]
    vis = {(r.importer, r.name): (r.locator, r.version) for r in out.visibility}
    assert vis[("packages/app", "lodash")] == ("node_modules/lodash", "4.17.21")            # app: the hoisted lodash 4
    assert vis[("packages/lib", "lodash")] == ("packages/lib/node_modules/lodash", "3.10.1")  # lib: its own nested lodash 3
    assert vis[("packages/app", "@acme/lib")] == ("packages/lib", "1.2.0")                  # link recognised: the sibling workspace
    names = {e.locator for e in out.world.entries}
    assert "packages/lib" in names and "node_modules/@acme/lib" not in names                # links are not separate packages


def test_candidate_dirs_skip_node_modules_components():
    assert candidate_dirs("node_modules/a/node_modules/b") == ["node_modules/a/node_modules/b", "node_modules/a", ""]
    assert candidate_dirs("packages/lib") == ["packages/lib", "packages", ""]
    assert candidate_dirs("") == [""]


@pytest.mark.parametrize("version", [1, 4, 99, "3", None])
def test_tc_3_6_3_unsupported_lockfile_version_is_not_a_partial_result(tmp_path, version):
    lock = {**NESTED_LOCK, "lockfileVersion": version} if version is not None else {k: v for k, v in NESTED_LOCK.items() if k != "lockfileVersion"}
    root, inv = snap(tmp_path, {"package.json": NESTED_PKG, "package-lock.json": lock})
    parsed = parse_package_lock(SnapshotFS(root), "package-lock.json")
    assert parsed.status == "UNSUPPORTED" and parsed.instances == {} and "not supported" in parsed.error
    [prj] = discover_npm(root, inv)
    out = resolve_npm_project(SnapshotFS(root), prj)
    assert out.status == "FAILED" and out.world is None and out.failure["reason"] == "lock_unsupported"


@pytest.mark.parametrize("content,reason", [("{not json", "lock_failed"), ("[]", "lock_failed"),
                                            (json.dumps({"lockfileVersion": 3, "packages": {}}), "lock_failed"),
                                            (json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/x": {}}}), "lock_failed")])
def test_malformed_locks_fail(tmp_path, content, reason):
    root, inv = snap(tmp_path, {"package.json": NESTED_PKG, "package-lock.json": content})
    [prj] = discover_npm(root, inv)
    out = resolve_npm_project(SnapshotFS(root), prj)
    assert out.status == "FAILED" and out.world is None and out.failure["reason"] == reason


def test_no_lockfile_and_stale_lockfile_are_failures_not_guesses(tmp_path):
    root, inv = snap(tmp_path / "a", {"package.json": NESTED_PKG})
    [prj] = discover_npm(root, inv)
    out = resolve_npm_project(SnapshotFS(root), prj)
    assert out.status == "FAILED" and out.failure["reason"] == "no_lockfile"
    root, inv = snap(tmp_path / "b", {"package.json": {**NESTED_PKG, "dependencies": {"a": "^1", "b": "^1", "c": "^1"}}, "package-lock.json": NESTED_LOCK})
    [prj] = discover_npm(root, inv)
    out = resolve_npm_project(SnapshotFS(root), prj)
    assert out.failure["reason"] == "lock_out_of_sync" and "c" in out.failure["detail"]


def test_package_json_variants(tmp_path):
    root, _ = snap(tmp_path, {"p.json": {"name": "x", "workspaces": {"packages": ["a/*"]}, "dependencies": ["not", "an", "object"], "engines": {"node": ">=20"}},
                              "bad.json": "{oops"})
    fs = SnapshotFS(root)
    p = parse_package_json(fs, "p.json")
    assert p.workspaces == ["a/*"] and p.status == "PARTIAL" and p.dependencies == {} and p.engines == {"node": ">=20"}
    assert parse_package_json(fs, "bad.json").status == "FAILED"


def test_nested_projects_and_ignored_directories(tmp_path):
    files = {"package.json": {"name": "root"}, "package-lock.json": {"lockfileVersion": 3, "packages": {"": {}}},
             "examples/demo/package.json": {"name": "demo"}, "node_modules/dep/package.json": {"name": "dep"},
             "vendor/x/package.json": {"name": "vendored"}}
    root, inv = snap(tmp_path, files)
    assert [p.rel_path for p in discover_npm(root, inv)] == [".", "examples/demo"]


def test_root_dev_dependencies_and_unversioned_workspace_members_are_accepted(tmp_path):
    """Found on mocha: devDependencies live in the lockfile root entry, and workspace members need not have a version."""
    lock = {"lockfileVersion": 3, "packages": {
        "": {"name": "m", "dependencies": {"a": "^1"}, "devDependencies": {"tool": "^2"}, "workspaces": ["w/*"]},
        "node_modules/a": pkg("1.0.0"), "node_modules/tool": pkg("2.0.0", dev=True),
        "w/x": {"name": "x"},                                           # a workspace member without a version
        "node_modules/x": {"resolved": "w/x", "link": True}}}
    files = {"package.json": {"name": "m", "dependencies": {"a": "^1"}, "devDependencies": {"tool": "^2"}, "workspaces": ["w/*"]},
             "package-lock.json": lock, "w/x/package.json": {"name": "x"}}
    root, inv = snap(tmp_path, files)
    [prj] = discover_npm(root, inv)
    out = resolve_npm_project(SnapshotFS(root), prj)
    assert out.status == "OK", out.failure
    vis = {(r.importer, r.name): r.version for r in out.visibility}
    assert vis[("", "tool")] == "2.0.0" and vis[("", "a")] == "1.0.0"          # the root can see its dev dependency
    assert {e.locator: e.version for e in out.world.entries}["w/x"] == ""      # unversioned stays unversioned, never invented
