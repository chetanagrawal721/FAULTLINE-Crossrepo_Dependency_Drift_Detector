"""M1.3: worlds are built once, offline, from hash-verified wheels (TC-1.3.1 to TC-1.3.3). Uses real Docker."""
import re
import subprocess
from pathlib import Path

import pytest

from faultline.core.enums import VenvStatus, WorldKind
from faultline.core.errors import ErrorCode
from faultline.resolvers.pinned import canonical_name, diff_locks, parse_pinned_lock
from faultline.sandbox.client import SandboxClient
from faultline.storage import worlds as world_store
from faultline.worlds.builder import WorldBuilder, WorldBuildError

pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]
REPOS = ROOT / "fixtures" / "repos"
H_LOCK = (REPOS / "billing-svc" / "H" / "requirements.lock.txt").read_text(encoding="utf-8")        # small world
REF_LOCK = (REPOS / "acme-models" / "requirements.lock.txt").read_text(encoding="utf-8")
NOTIFY_LOCK = (REPOS / "notify-svc" / "D" / "requirements.lock.txt").read_text(encoding="utf-8")


class CountingClient(SandboxClient):
    """Counts container executions so tests can prove that reuse starts none."""

    def __init__(self, inner: SandboxClient):
        self.__dict__.update(inner.__dict__)
        self.runs = 0

    def submit(self, job):
        self.runs += 1
        return super().submit(job)


@pytest.fixture
def builder(sbx, image, conn):
    return WorldBuilder(CountingClient(sbx), image, conn)


def expected_packages(lock_text):
    return sorted((r.name, r.version) for r in parse_pinned_lock(lock_text))


def installed(info):
    return sorted((canonical_name(n), v) for n, v in info["info"]["packages"])


def test_tc_1_3_1_offline_build_from_verified_artifacts(builder, conn, sbx):
    world = builder.materialize(H_LOCK, WorldKind.PROJECTED)
    assert world.world_hash.startswith("w_") and all(e.artifact_sha256 for e in world.entries)
    sbx.volume_rm(world.world_hash)
    conn.execute("UPDATE resolved_world SET venv_status='NOT_BUILT' WHERE world_hash=?", (world.world_hash,))
    # the wheelhouse is full; the build now runs in the exec zone, which has no network at all
    result = builder.build(world, H_LOCK)
    assert result.status == "BUILT", result.reason
    info = builder.info(world)
    assert installed(info) == expected_packages(H_LOCK)                      # exactly the descriptor, nothing else
    assert info["info"]["python"] == "3.12.15"
    assert info["marker"]["world_hash"] == world.world_hash
    assert world_store.venv_status(conn, world.world_hash) == VenvStatus.BUILT


def test_exec_zone_build_job_has_no_network(builder, sbx, image):
    r = sbx.submit({"image": image, "probe": "network", "args": {"host": "pypi.org", "port": 443}})
    assert r["data"]["data"]["connected"] is False and r["data"]["data"]["dns"] is False


def with_wrong_hash(lock: str, name: str) -> str:
    """Replace every hash of one package in a lock text with a wrong one."""
    out, in_block = [], False
    for line in lock.splitlines():
        if line.startswith(name + "=="):
            in_block = True
        elif not line.startswith(" "):
            in_block = False
        out.append(re.sub(r"sha256:[0-9a-f]{64}", "sha256:" + "0" * 64, line) if in_block else line)
    return "\n".join(out) + "\n"


def test_tc_1_3_2_wrong_hash_in_lock_blocks_the_world(builder, conn):
    bad = with_wrong_hash(H_LOCK, "annotated-types")
    assert bad != H_LOCK
    before = conn.execute("SELECT COUNT(*) FROM resolved_world").fetchone()[0]
    with pytest.raises(WorldBuildError) as ei:
        builder.materialize(bad, WorldKind.PROJECTED)
    assert ei.value.details.get("reason") == "hash_mismatch" or "hash" in ei.value.message.lower()
    assert conn.execute("SELECT COUNT(*) FROM resolved_world").fetchone()[0] == before    # no world was recorded


def test_tc_1_3_2_corrupted_wheel_in_wheelhouse_blocks_build(builder, conn, sbx, image):
    world = builder.materialize(H_LOCK, WorldKind.PROJECTED)
    sbx.volume_rm(world.world_hash)
    conn.execute("UPDATE resolved_world SET venv_status='NOT_BUILT' WHERE world_hash=?", (world.world_hash,))
    target = "annotated_types-0.7.0-py3-none-any.whl"
    def root(sh):
        return subprocess.run(["docker", "run", "--rm", "--user", "0", "-v", "fl-wheelhouse:/w", image, "sh", "-c", sh],
                              capture_output=True, text=True)

    assert root(f"ls /w/{target}").returncode == 0
    try:
        assert root(f"echo corrupt >> /w/{target}").returncode == 0
        result = builder.build(world, H_LOCK)
        assert result.status == "FAILED"
        assert world_store.venv_status(conn, world.world_hash) == VenvStatus.FAILED     # not usable
        assert not builder.sandbox.volume_exists(world.world_hash)                      # nothing half-built is kept
    finally:
        root(f"rm -f /w/{target}")
        builder.materialize(H_LOCK, WorldKind.PROJECTED)                                 # restore a clean wheelhouse
    assert builder.build(world, H_LOCK).status == "BUILT"


def test_tc_1_3_3_reuse_is_not_an_execution(builder, conn):
    world = builder.materialize(H_LOCK, WorldKind.PROJECTED)
    first = builder.build(world, H_LOCK)
    assert first.status in ("BUILT", "REUSED")
    runs_before = builder.sandbox.runs
    again = builder.build(world, H_LOCK)
    assert again.status == "REUSED" and again.world_hash == world.world_hash
    assert builder.sandbox.runs == runs_before                                   # no container started
    assert conn.execute("SELECT COUNT(*) FROM oracle_run").fetchone()[0] == 0   # and no oracle run recorded
    assert conn.execute("SELECT COUNT(*) FROM oracle_job").fetchone()[0] == 0


def test_same_lock_gives_same_world_hash_and_different_lock_differs(builder):
    a = builder.materialize(H_LOCK, WorldKind.PROJECTED)
    b = builder.materialize(H_LOCK, WorldKind.PROJECTED)
    assert a.world_hash == b.world_hash
    ref = builder.materialize(REF_LOCK, WorldKind.REFERENCE)
    assert ref.world_hash != a.world_hash


def test_reference_and_consumer_worlds_differ_exactly_as_the_scenario_says(builder):
    ref = builder.materialize(REF_LOCK, WorldKind.REFERENCE)
    test = builder.materialize(NOTIFY_LOCK, WorldKind.PROJECTED)
    delta = diff_locks(parse_pinned_lock(REF_LOCK), parse_pinned_lock(NOTIFY_LOCK))
    assert sorted(delta) == ["itsdangerous", "werkzeug"]
    ref_v = {e.name: e.version for e in ref.entries}
    test_v = {e.name: e.version for e in test.entries}
    assert ref_v["werkzeug"] == "2.2.3" and test_v["werkzeug"] == "3.0.6"
    assert ref.world_hash != test.world_hash


def test_missing_wheel_is_reported_not_built(builder):
    lock = "flask==99.0.0 --hash=sha256:" + "a" * 64 + "\n"
    with pytest.raises(WorldBuildError) as ei:
        builder.materialize(lock, WorldKind.PROJECTED)
    assert ei.value.code in (ErrorCode.NO_WHEEL, ErrorCode.WORLD_BUILD_FAILED)


def test_world_persistence_is_idempotent(builder, conn):
    w = builder.materialize(H_LOCK, WorldKind.PROJECTED)
    assert world_store.save_world(conn, w, builder.env) is False             # already saved by materialize
    assert world_store.world_packages(conn, w.world_hash) == [(e.name, e.version) for e in w.entries]
