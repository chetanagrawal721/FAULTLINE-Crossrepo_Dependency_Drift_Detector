"""M2.1 to M2.3 with real containers: fetching pinned commits from local git remotes, including hostile ones."""
import json
import os
import stat
from pathlib import Path

import pytest

from faultline.core.errors import ErrorCode
from faultline.core.ids import new_id
from faultline.ingestion import service
from faultline.ingestion.clone import (
    FetchError,
    fetch_snapshot,
    load_inventory,
    snapshot_key,
    verify_snapshot,
)
from faultline.ingestion.github import GitHubClient, Resolved
from faultline.ingestion.urls import RepoRef
from tests.gitremote import Remote

pytestmark = pytest.mark.docker


def make_fake_github(shas: dict[str, str]):
    """A GitHub client whose answers come from a dict {ref: sha}; it can be changed between calls (a moving tag)."""
    class Fake(GitHubClient):
        def resolve(self, repo: RepoRef) -> Resolved:
            ref = repo.ref or "main"
            return Resolved(sha=shas[ref], committed_at="2026-01-01T00:00:00Z", default_branch="main", is_fork=False,
                            is_archived=False, requested_ref=repo.ref, resolved_ref=ref)
    return Fake(token=None, transport=lambda u, h: (500, {}, b""))


@pytest.fixture
def remotes(daemon):
    def make(name: str) -> Remote:
        return Remote(daemon.store.remote_dir(name))
    return make


@pytest.fixture
def ing(conn, sbx, image, daemon):
    return type("Ing", (), {"conn": conn, "sbx": sbx, "image": image, "store": daemon.store})


def fetch(ing, remote_name, sha, **kw):
    return fetch_snapshot(ing.sbx, ing.image, ing.store, "o", remote_name, sha, remote=remote_name, **kw)


# ----------------------------------------------------------------------------- M2.3 snapshot basics

def test_snapshot_is_complete_hashed_read_only_and_cached(ing, remotes):
    r = remotes("rm_basic")
    sha = r.commit({"README.md": b"# hi\n", "src": {"a.py": b"x = 1\n", "b.py": b"y = 2\n"}, "requirements.txt": b"flask==2.2.2\n"})
    s = fetch(ing, "rm_basic", sha)
    assert not s.cached and s.key == snapshot_key("o", "rm_basic", sha)
    inv = s.inventory
    assert inv["commit"] == sha and {e["path"] for e in inv["entries"]} == {"README.md", "src/a.py", "src/b.py", "requirements.txt"}
    assert all(e["kind"] == "file" and len(e["sha256"]) == 64 for e in inv["entries"])
    from tests.gitremote import git as run_git
    tree = {ln.split("	")[1]: ln.split()[2] for ln in run_git(r.path, "ls-tree", "-r", sha).splitlines()}
    assert {e["path"]: e["blob"] for e in inv["entries"]} == tree                 # same files, same git blob ids
    assert verify_snapshot(s.path) == []
    # read-only and tamper-evident
    f = s.path / "src" / "a.py"
    assert not os.access(f, os.W_OK)
    unlock(f)
    f.write_bytes(b"x = 999\n")
    assert verify_snapshot(s.path) == ["modified file: src/a.py"]
    f.write_bytes(b"x = 1\n")                                                    # restore for the cache check
    f.chmod(stat.S_IREAD)
    again = fetch(ing, "rm_basic", sha)
    assert again.cached and again.key == s.key                                   # same repo + SHA: no second fetch


def unlock(f):
    """Make a snapshot file replaceable: chmod where the host owns it (Windows, macOS), else remove it (Linux: the container user owns it, the directory is open)."""
    try:
        f.chmod(stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        f.unlink()


def test_extra_or_missing_files_are_detected_by_verification(ing, remotes):
    r = remotes("rm_tamper")
    sha = r.commit({"a.txt": b"a\n", "b.txt": b"b\n"})
    s = fetch(ing, "rm_tamper", sha)
    unlock(s.path / "b.txt")
    (s.path / "b.txt").unlink(missing_ok=True)
    (s.path / "injected.py").write_text("print('x')\n")
    assert sorted(verify_snapshot(s.path)) == ["missing file: b.txt", "unexpected file: injected.py"]


# ----------------------------------------------------------------------------- M2.1 moving refs

def test_tc_2_1_2_moving_tag_creates_a_new_snapshot_and_keeps_the_old_one(ing, remotes, conn):
    r = remotes("rm_moving")
    sha1 = r.commit({"v.txt": b"one\n"}, tag="rel")
    shas = {"rel": sha1}
    gh = make_fake_github(shas)
    pid = service.create_project(conn, "p")
    rid, resolved, changed = service.add_repository(conn, gh, pid, "https://github.com/o/rm_moving", "rel")
    assert changed and resolved.sha == sha1
    s1 = service.ingest(conn, ing.sbx, ing.image, ing.store, rid, remote="rm_moving")

    sha2 = r.commit({"v.txt": b"two\n"})
    r.move_tag("rel", sha2)
    shas["rel"] = sha2                                                          # the tag moved upstream
    rid2, resolved2, changed2 = service.add_repository(conn, gh, pid, "https://github.com/o/rm_moving", "rel")
    assert rid2 == rid and changed2 and resolved2.sha == sha2
    s2 = service.ingest(conn, ing.sbx, ing.image, ing.store, rid, remote="rm_moving")

    assert s1 != s2
    rows = conn.execute("SELECT sha FROM snapshot WHERE repository_id=? ORDER BY committed_at, sha", (rid,)).fetchall()
    assert {x["sha"] for x in rows} == {sha1, sha2}
    old = ing.store.snapshot_dir(snapshot_key("o", "rm_moving", sha1))
    assert (old / "v.txt").read_text() == "one\n" and verify_snapshot(old) == []   # history was not overwritten
    assert (ing.store.snapshot_dir(snapshot_key("o", "rm_moving", sha2)) / "v.txt").read_text() == "two\n"
    assert conn.execute("SELECT requested_ref, pinned_sha FROM repository WHERE id=?", (rid,)).fetchone()["pinned_sha"] == sha2


def test_tc_2_1_3_retry_after_a_failure_keeps_the_same_sha(ing, remotes, conn):
    r = remotes("rm_retry")
    sha = r.commit({"a": b"1"})
    gh = make_fake_github({"main": sha})
    pid = service.create_project(conn, "p")
    rid, _, _ = service.add_repository(conn, gh, pid, "https://github.com/o/rm_retry")
    # first attempt fails because the remote is not mounted under that name; the SHA must not change
    with pytest.raises((FetchError, ValueError)):
        service.ingest(conn, ing.sbx, ing.image, ing.store, rid, remote="rm_doesnotexist")
    row = conn.execute("SELECT status, pinned_sha, error_json FROM repository WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "FAILED" and row["pinned_sha"] == sha
    service.ingest(conn, ing.sbx, ing.image, ing.store, rid, remote="rm_retry")
    row = conn.execute("SELECT status, pinned_sha FROM repository WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "INGESTED" and row["pinned_sha"] == sha


def test_asking_for_a_sha_the_remote_does_not_have_fails_cleanly(ing, remotes):
    remotes("rm_empty").commit({"a": b"1"})
    with pytest.raises(FetchError) as ei:
        fetch(ing, "rm_empty", "e" * 40)
    assert ei.value.code in (ErrorCode.FETCH_FAILED, ErrorCode.REPOSITORY_NOT_FOUND)
    assert not ing.store.snapshot_dir(snapshot_key("o", "rm_empty", "e" * 40)).exists()      # no partial snapshot is left


# ----------------------------------------------------------------------------- M2.2 hostile repository

def test_tc_2_2_1_hostile_repository(ing, remotes, daemon):
    r = remotes("rm_hostile")
    lfs = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 123456789\n"
    outside = "escape-marker.txt"
    sha = r.commit({
        "ok.py": b"print('fine')\n",
        "link-to-etc": ("symlink", "/etc/passwd"),
        "link-up": ("symlink", "../../../outside"),
        "mod": ("gitlink", "1" * 40),
        "weights.bin": lfs,
        ".gitmodules": b'[submodule "x"]\n\tpath = mod\n\turl = file:///etc\n',
        ".gitconfig": b"[core]\n\tfsmonitor = /bin/evil\n\thooksPath = /tmp/evil\n",
        ".githooks": {"post-checkout": b"#!/bin/sh\ntouch /snapshot/hook-ran\n"},
        "..": {outside: b"x"},                                   # a '..' directory entry
        ".git": {"config": b"[core]\n\tfsmonitor = evil\n"},       # a '.git' directory entry
        "dir": {"..": {outside: b"y"}, "x:stream.txt": b"ads", "aux.txt": b"reserved", "ok.txt": b"fine\n", "trail.": b"dot"},
        "Case.py": b"1", "case.py": b"2",                         # case collision
        "back\\slash.txt": b"bs",
    })
    s = fetch(ing, "rm_hostile", sha)
    by = {e["path"]: e for e in s.inventory["entries"]}

    assert by["ok.py"]["kind"] == "file" and by["dir/ok.txt"]["kind"] == "file" and by[".githooks/post-checkout"]["kind"] == "file"
    assert by["link-to-etc"]["kind"] == "symlink" and by["link-up"]["kind"] == "symlink"      # metadata only
    assert by["mod"]["kind"] == "submodule"
    assert by["weights.bin"]["kind"] == "lfs_pointer"
    for bad in ("../" + outside, ".git/config", "dir/../" + outside, "dir/x:stream.txt", "dir/aux.txt", "dir/trail.", "back\\slash.txt"):
        assert by[bad]["kind"] == "unsupported_path", bad
    assert {by["Case.py"]["kind"], by["case.py"]["kind"]} == {"file", "unsupported_path"}
    assert any(e.get("reason") == "case_collision" for e in by.values())

    # nothing unsafe reached the disk
    on_disk = {p.relative_to(s.path).as_posix() for p in s.path.rglob("*") if p.is_file()}
    assert "link-to-etc" not in on_disk and "link-up" not in on_disk and "mod" not in on_disk
    assert not any(".." in p.split("/") or p.startswith(".git/") for p in on_disk)
    assert (s.path / ".githooks" / "post-checkout").read_text().startswith("#!/bin/sh")        # present as inert data
    store = Path(daemon.store.root)
    assert not list(store.rglob(outside)) and not list(store.rglob("hook-ran"))
    assert verify_snapshot(s.path) == []


def test_tc_2_2_2_limits_produce_a_partial_snapshot_and_a_warning(ing, remotes):
    r = remotes("rm_limits")
    files = {f"f{i:03}.txt": b"x" * 10 for i in range(30)}
    files["big.bin"] = b"y" * 5000
    files["deep"] = {"a" * 100: {"b" * 100: {"c" * 100: b"long path"}}}
    sha = r.commit(files)
    s = fetch(ing, "rm_limits", sha, limits={"max_files": 20, "max_file_bytes": 1000, "max_path_len": 200})
    inv = s.inventory
    assert inv["truncated"] is True and any("only the first 20" in w for w in inv["warnings"])
    kinds = {e["path"]: e["kind"] for e in inv["entries"]}
    assert len(kinds) == 20
    if "big.bin" in kinds:
        assert kinds["big.bin"] == "too_large"
    long_path = "/".join(["deep", "a" * 100, "b" * 100, "c" * 100])
    assert kinds.get(long_path, "unsupported_path") == "unsupported_path"
    assert verify_snapshot(s.path) == []


def test_snapshot_persisted_with_classification(ing, remotes, conn):
    r = remotes("rm_persist")
    sha = r.commit({"pyproject.toml": b"[project]\nname='x'\n", "requirements.txt": b"a==1\n", "uv.lock": b"version = 1\n",
                    "package.json": b"{}", "pom.xml": b"<project/>", "node_modules": {"left-pad": {"package.json": b"{}"}},
                    "vendor": {"lib": {"requirements.txt": b"b==2\n"}}, "tests": {"test_a.py": b"def test(): pass\n"},
                    "svc": {"requirements-dev.txt": b"c==3\n", "api_pb2.py": b"# generated\n"}})
    gh = make_fake_github({"main": sha})
    pid = service.create_project(conn, "p")
    rid, _, _ = service.add_repository(conn, gh, pid, "https://github.com/o/rm_persist")
    sid = service.ingest(conn, ing.sbx, ing.image, ing.store, rid, remote="rm_persist")
    rows = {x["path"]: x for x in conn.execute("SELECT * FROM snapshot_file WHERE snapshot_id=?", (sid,))}
    assert rows["pyproject.toml"]["role"] == "manifest:pyproject" and rows["uv.lock"]["role"] == "manifest:uv_lock"
    assert rows["package.json"]["role"] == "manifest:package_json" and rows["pom.xml"]["role"] == "manifest:pom"
    assert rows["svc/requirements-dev.txt"]["role"] == "manifest:requirements"
    assert rows["node_modules/left-pad/package.json"]["role"] == "ignored"          # not a project
    assert rows["vendor/lib/requirements.txt"]["role"] == "other" and "VENDORED" in rows["vendor/lib/requirements.txt"]["tags"]
    assert "TEST" in rows["tests/test_a.py"]["tags"] and "GENERATED" in rows["svc/api_pb2.py"]["tags"]
    snap = conn.execute("SELECT * FROM snapshot WHERE id=?", (sid,)).fetchone()
    assert snap["sha"] == sha and snap["ingest_status"] == "OK"
    assert service.persist_snapshot(conn, rid, load_snap(ing, "rm_persist", sha), sha, "2026-01-01T00:00:00Z") == sid      # idempotent
    assert json.loads(snap["ingest_warnings_json"]) == []
    assert new_id("x")


def load_snap(ing, name, sha):
    from faultline.ingestion.clone import SnapshotResult
    key = snapshot_key("o", name, sha)
    p = ing.store.snapshot_dir(key)
    return SnapshotResult(key, p, load_inventory(p), True)
