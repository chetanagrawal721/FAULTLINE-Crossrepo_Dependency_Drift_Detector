"""M3.4: deduplication of equivalent worlds and cache invalidation on every input."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from faultline.core.hashing import object_hash
from faultline.ingestion import service
from faultline.parsers.common import SnapshotFS
from faultline.parsers.python.discover import discover_python
from faultline.resolvers.pinned import PinnedRequirement
from faultline.resolvers.python import ResolveOutcome
from faultline.worlds.canonical import ResolutionContext, cache_key, ensure_project_world
from tests.snapshots import make_snapshot

CTX = ResolutionContext(cutoff="2024-10-30T00:00:00Z")


def snapshot_row(conn, sha="a" * 40) -> str:
    pid = service.create_project(conn, "p")
    conn.execute("INSERT INTO repository(id, analysis_project_id, owner, name, status) VALUES ('repo_t', ?, 'o', 'r', 'INGESTED')", (pid,))
    conn.execute("INSERT INTO snapshot(id, repository_id, sha, committed_at, store_path, ingest_status) "
                 "VALUES ('snp_t', 'repo_t', ?, '2024-10-30T00:00:00Z', 'k', 'OK')", (sha,))
    return "snp_t"


class FakeResolver:
    def __init__(self):
        self.calls = 0

    def __call__(self, sbx, image, fs, project, *, cutoff):
        self.calls += 1
        return ResolveOutcome("OK", "resolver", [PinnedRequirement("flask", "Flask", "2.2.2", ("a" * 64,))], [], None,
                              {"cutoff": cutoff, "lockfile": None})


class FakeBuilder:
    def __init__(self, conn):
        self.conn, self.calls = conn, 0

    def materialize(self, lock_text):
        self.calls += 1
        h = "w_" + object_hash(lock_text)[:32]
        self.conn.execute("INSERT OR IGNORE INTO env_profile(id, image_ref, arch, locale, tz, env_json, seed) VALUES ('ep_x','i','a','l','t','{}',0)")
        self.conn.execute("INSERT OR IGNORE INTO resolved_world(world_hash, ecosystem, runtime_json, env_profile_id, kind) VALUES (?,?,?,?,?)",
                          (h, "pypi", "{}", "ep_x", "reference"))
        return SimpleNamespace(world_hash=h)


def one_project(tmp_path, files):
    root, inv = make_snapshot(tmp_path, files)
    return SnapshotFS(root), discover_python(root, inv).projects[0]


def test_tc_3_4_2_cache_invalidates_on_any_input(conn, tmp_path):
    sid = snapshot_row(conn)
    fs, prj = one_project(tmp_path, {"requirements.txt": "flask==2.2.2\n"})
    res, bld = FakeResolver(), FakeBuilder(conn)

    def run(ctx, fs_=fs, prj_=prj):
        return ensure_project_world(conn, None, "img", sid, fs_, prj_, ctx, resolver=res, builder=bld)

    first = run(CTX)
    assert not first.cache_hit and res.calls == 1
    again = run(CTX)
    assert again.cache_hit and res.calls == 1 and again.world_hash == first.world_hash          # identical inputs: reused, nothing re-run

    variants = [replace(CTX, cutoff="2025-01-01T00:00:00Z"), replace(CTX, platform="aarch64-unknown-linux-gnu"),
                replace(CTX, resolver_version="uv 9.9.9"), replace(CTX, index="https://mirror.example/simple"),
                replace(CTX, python="3.13"), replace(CTX, flags=(*CTX.flags, "--prerelease=allow"))]
    for i, v in enumerate(variants, start=2):
        out = run(v)
        assert not out.cache_hit and res.calls == i, v                                          # each change resolves again
    assert len({cache_key(fs, prj, c) for c in [CTX, *variants]}) == 1 + len(variants)

    (tmp_path / "requirements.txt").write_text("flask==2.2.3\n")                              # a manifest change
    fs2, prj2 = one_project(tmp_path, {"requirements.txt": "flask==2.2.3\n"})
    assert not run(CTX, fs2, prj2).cache_hit and res.calls == len(variants) + 2


def test_failed_resolutions_are_cached_unless_transient(conn, tmp_path):
    sid = snapshot_row(conn)
    fs, prj = one_project(tmp_path, {"requirements.txt": "flask==2.2.2\n"})
    calls = []

    def failing(code):
        def r(sbx, image, fs, project, *, cutoff):
            calls.append(code)
            return ResolveOutcome("FAILED", "resolver", failure={"code": code, "reason": "x", "detail": ""}, provenance={})
        return r

    for code, expect_hit in (("RESOLUTION_FAILED", True), ("FETCH_FAILED", False)):
        calls.clear()
        fs_ = fs if code == "RESOLUTION_FAILED" else one_project(tmp_path / "t", {"requirements.txt": "other==1\n"})[0]
        prj_ = prj if code == "RESOLUTION_FAILED" else one_project(tmp_path / "t2", {"requirements.txt": "other==1\n"})[1]
        ensure_project_world(conn, None, "img", sid, fs_, prj_, CTX, resolver=failing(code))
        second = ensure_project_world(conn, None, "img", sid, fs_, prj_, CTX, resolver=failing(code))
        assert second.cache_hit is expect_hit
        assert second.world_hash is None and second.status == "FAILED"                          # a failed resolution has no world


def test_project_world_and_manifest_rows_are_recorded(conn, tmp_path):
    sid = snapshot_row(conn)
    fs, prj = one_project(tmp_path, {"requirements.txt": "flask==2.2.2\n", "pyproject.toml": '[project]\nname="d"\nversion="0"\n'})
    out = ensure_project_world(conn, None, "img", sid, fs, prj, CTX, resolver=FakeResolver(), builder=FakeBuilder(conn))
    pw = conn.execute("SELECT * FROM project_world WHERE project_id=?", (out.project_id,)).fetchone()
    assert pw["world_hash"] == out.world_hash and pw["status"] == "OK" and pw["resolved_at"] == CTX.cutoff
    kinds = {r["kind"]: r["parse_status"] for r in conn.execute("SELECT kind, parse_status FROM manifest WHERE project_id=?", (out.project_id,))}
    assert kinds == {"requirements": "OK", "pyproject": "OK"}


# ----------------------------------------------------------------------------- TC-3.4.1 with the real pipeline

@pytest.mark.docker
def test_tc_3_4_1_equivalent_worlds_dedupe(conn, tmp_path, sbx, image):
    sid = snapshot_row(conn)
    root, inv = make_snapshot(tmp_path, {
        "svc_a/pyproject.toml": '[project]\nname = "svc-a"\nversion = "0"\ndependencies = ["itsdangerous==2.2.0"]\n',
        "svc_b/requirements.txt": "itsdangerous==2.2.0\n"})
    fs = SnapshotFS(root)
    projects = discover_python(root, inv).projects
    assert [p.rel_path for p in projects] == ["svc_a", "svc_b"]
    results = [ensure_project_world(conn, sbx, image, sid, fs, p, CTX) for p in projects]
    assert all(r.status == "OK" for r in results), [r.outcome.failure for r in results]
    assert results[0].world_hash == results[1].world_hash and results[0].project_id != results[1].project_id
    assert conn.execute("SELECT COUNT(*) FROM resolved_world WHERE world_hash=?", (results[0].world_hash,)).fetchone()[0] == 1
    links = conn.execute("SELECT project_id FROM project_world WHERE world_hash=?", (results[0].world_hash,)).fetchall()
    assert {r["project_id"] for r in links} == {r.project_id for r in results}
    assert conn.execute("SELECT COUNT(*) FROM resolved_world").fetchone()[0] == 1            # one world row for two projects
