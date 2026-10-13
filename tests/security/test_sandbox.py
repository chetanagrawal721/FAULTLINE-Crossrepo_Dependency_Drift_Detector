"""M1.2 sandbox escape tests (TC-1.2.1 to TC-1.2.5). These run real containers through real sandboxd."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from faultline.sandbox import runner, status
from faultline.sandbox.client import SandboxClient, SandboxUnavailable
from faultline.sandbox.sandboxd import Daemon
from tests.conftest import TOKEN, labelled_containers

pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]


def data(result):
    return (result["data"] or {}).get("data")


# ----------------------------------------------------------------------------- TC-1.2.1 network

def test_tc_1_2_1_no_network_to_internet_or_metadata_endpoint(probe):
    for host, port in (("1.1.1.1", 443), ("169.254.169.254", 80), ("8.8.8.8", 53), ("127.0.0.1", 8000)):
        r = probe("network", {"host": host, "port": port, "timeout": 2})
        d = data(r)
        assert d["connected"] is False, (host, d)
        assert d["dns"] is False
        assert r["failure_class"] == "NONE"          # a refused connection is data, not a sandbox failure


# ----------------------------------------------------------------------------- TC-1.2.2 filesystem and identity

def test_tc_1_2_2_identity_is_unprivileged_and_isolated(probe):
    d = data(probe("identity"))
    assert d["uid"] == 65534 and d["euid"] == 65534 and d["gid"] == 65534
    assert d["cap_eff"] == "0000000000000000"
    assert d["no_new_privs"] == "1"
    assert d["seccomp"] == "2"                      # a seccomp filter is active
    assert d["root_read_only"] is True
    assert d["docker_sock_exists"] is False
    assert not any("CANARY" in n or "TOKEN" in n or "SECRET" in n for n in d["env_names"])
    assert set(d["env_names"]) <= {"LANG", "LC_ALL", "TZ", "PYTHONHASHSEED", "SOURCE_DATE_EPOCH",
                                   "PYTHONDONTWRITEBYTECODE", "HOME", "PATH", "HOSTNAME", "PYTHON_VERSION",
                                   "PYTHON_SHA256", "GPG_KEY", "PYTHONUNBUFFERED", "PIP_NO_CACHE_DIR",
                                   "PIP_DISABLE_PIP_VERSION_CHECK", "UV_NO_CACHE"}
    for target in ("/tmp", "/work"):
        assert d["mounts"][target]["noexec"] is True


@pytest.mark.parametrize("path", ["/faultline_probe", "/etc/faultline_probe", "/usr/faultline_probe",
                                  "/faultline_harness/probe.py", "/opt/faultline_probe"])
def test_tc_1_2_2_cannot_write_outside_tmpfs(probe, path):
    assert data(probe("write", {"path": path}))["written"] is False


@pytest.mark.parametrize("path", ["/tmp/ok", "/work/ok"])
def test_tmpfs_scratch_is_writable(probe, path):
    assert data(probe("write", {"path": path}))["written"] is True


def test_tc_1_2_2_docker_socket_and_host_files_unreadable(probe):
    for path in ("/var/run/docker.sock", "/run/docker.sock", "/host", "/proc/1/root/etc/shadow"):
        assert data(probe("read", {"path": path}))["readable"] is False


# ----------------------------------------------------------------------------- TC-1.2.3 resource bombs

@pytest.mark.slow
def test_tc_1_2_3_fork_bomb_is_stopped_by_pids_limit(probe, sbx):
    t0 = time.monotonic()
    r = probe("fork_bomb", {"max": 5000}, pids=64, timeout_s=60)
    d = data(r)
    assert d["reached_limit"] is False and d["forked"] < 100 and d["stopped_by"]
    assert time.monotonic() - t0 < 40
    assert sbx.ping()                              # the host and sandboxd stay responsive


@pytest.mark.slow
def test_tc_1_2_3_memory_bomb_is_oom_killed(probe):
    r = probe("memory", {"mb": 4096}, memory_mb=256, timeout_s=60)
    assert r["failure_class"] == "RESOURCE_LIMIT" and r["oom"] is True and r["exit_code"] == 137


@pytest.mark.slow
def test_tc_1_2_3_disk_fill_stops_at_tmpfs_size(probe):
    d = data(probe("disk", {"path": "/tmp/fill", "mb": 2048}, tmpfs_mb=64))
    assert d["completed"] is False and d["written_mb"] <= 70 and d["error"] == "OSError"


@pytest.mark.slow
def test_tc_1_2_3_output_flood_is_capped(probe):
    r = probe("print_flood", {"mb": 100}, output_bytes=8192, timeout_s=60)
    assert r["truncated"] is True
    assert len(r["stdout_tail"]) <= 2000


@pytest.mark.slow
def test_tc_1_2_3_runaway_job_is_killed_by_wall_clock(probe):
    t0 = time.monotonic()
    r = probe("busy", {"seconds": 120}, timeout_s=4)
    assert r["failure_class"] == "TIMEOUT" and r["timed_out"] is True
    assert time.monotonic() - t0 < 30
    assert [n for n in labelled_containers() if r["run_id"][-6:].lower() in n] == []     # container was removed


# ----------------------------------------------------------------------------- TC-1.2.4 no orphans

@pytest.mark.slow
def test_tc_1_2_4_no_orphans_after_sandboxd_crash(image):
    """Kill sandboxd while a job is running: the container survives it (an orphan). A restarted sandboxd removes it."""
    port = 18787
    env = {**os.environ, "FAULTLINE_SANDBOX_TOKEN": TOKEN, "FAULTLINE_SANDBOX_PORT": str(port),
           "PYTHONPATH": str(ROOT / "backend")}
    runner.sweep_orphans()

    def start():
        p = subprocess.Popen([sys.executable, "-m", "faultline.sandbox.sandboxd", "--port", str(port), "--no-verify"],
                             env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        c = SandboxClient(port=port, token=TOKEN, timeout=120)
        for _ in range(60):
            if c.ping():
                return p, c
            time.sleep(0.3)
        raise AssertionError("sandboxd did not start")

    p1, c1 = start()
    import threading
    t = threading.Thread(target=lambda: _swallow(lambda: c1.submit({"image": image, "probe": "sleep",
                                                                    "args": {"seconds": 60}, "limits": {"timeout_s": 120}})),
                         daemon=True)
    t.start()
    for _ in range(60):
        if labelled_containers():
            break
        time.sleep(0.5)
    assert labelled_containers(), "job container never appeared"
    subprocess.run(["taskkill", "/PID", str(p1.pid), "/T", "/F"], capture_output=True) if os.name == "nt" else p1.kill()
    p1.wait(timeout=30)
    assert labelled_containers(), "expected an orphaned container after the crash"
    p2, c2 = start()                                  # startup sweep
    try:
        for _ in range(20):
            if not labelled_containers():
                break
            time.sleep(0.5)
        assert labelled_containers() == []
    finally:
        subprocess.run(["taskkill", "/PID", str(p2.pid), "/T", "/F"], capture_output=True) if os.name == "nt" else p2.kill()
        runner.sweep_orphans()


def _swallow(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------------- TC-1.2.5 fail closed

def test_tc_1_2_5_docker_unreachable_disables_execution(image):
    d = Daemon(TOKEN, docker_host="tcp://127.0.0.1:1")
    r = d.run({"image": image, "probe": "echo", "args": {"x": 1}})
    assert r["failure_class"] == "SANDBOX_FAILURE" and "execution disabled" in r["error"]
    assert r.get("data") is None
    st = d.status()
    assert st["docker"] is False


def test_tc_1_2_5_sandboxd_down_reports_unavailable_and_raises():
    status._cache.update(at=0.0, value=None)
    dead = SandboxClient(port=1, token="x", timeout=1)          # nothing listens on port 1
    s = status.current_sandbox_status(dead, use_cache=False)
    assert s.state.value == "unavailable" and s.verified is False and "execution is disabled" in s.reason
    with pytest.raises(SandboxUnavailable):
        dead.submit({"image": "sha256:" + "0" * 64, "probe": "echo"})


# ----------------------------------------------------------------------------- policy: what is refused

def test_unlisted_or_mutable_images_are_rejected(sbx):
    for bad in ("python:3.12-slim", "sha256:" + "0" * 64, "faultline/exec-python:0.1.0"):
        r = sbx.submit({"image": bad, "probe": "echo"})
        assert r["failure_class"] == "SANDBOX_FAILURE" and "rejected" in r["error"], bad


def test_unknown_limits_scripts_and_mounts_are_rejected(sbx, image):
    assert "rejected" in sbx.submit({"image": image, "probe": "echo", "limits": {"privileged": 1}})["error"]
    assert "rejected" in sbx.submit({"image": image, "probe": "echo", "script": "../../bin/sh"})["error"]
    r = sbx.submit({"image": image, "probe": "echo", "mounts": {"/etc": {"world": "w_x"}}})
    assert "rejected" in r["error"]
    r = sbx.submit({"image": image, "probe": "echo", "mounts": {"/opt/world": {"world": "../../x"}}})
    assert "rejected" in r["error"]


def test_limits_are_clamped_to_hard_ceilings():
    from faultline.sandbox.profiles import MAX_LIMITS, clamp_limits
    c = clamp_limits({"memory_mb": 10**9, "timeout_s": 10**9, "cpus": 64})
    assert c["memory_mb"] == MAX_LIMITS["memory_mb"] and c["timeout_s"] == MAX_LIMITS["timeout_s"] and c["cpus"] == 2.0


def test_wrong_token_is_rejected(daemon):
    bad = SandboxClient(port=daemon.port, token="wrong", timeout=5)
    with pytest.raises(SandboxUnavailable):
        bad.status()


def test_unknown_probe_is_refused_by_the_harness(probe):
    r = probe("rm_rf")
    assert r["data"]["error"].startswith("unknown probe") and r["exit_code"] == 2


def test_container_profile_flags_contain_the_required_hardening():
    from faultline.sandbox.profiles import EXEC, FETCH
    args = EXEC.docker_args(__import__("faultline.sandbox.profiles", fromlist=["x"]).DEFAULT_LIMITS, "n", "j")
    joined = " ".join(args)
    for needle in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges:true", "--user 65534:65534",
                   "--pids-limit", "--memory-swap"):
        assert needle in joined, needle
    assert "--privileged" not in joined and "docker.sock" not in joined
    assert FETCH.network == "bridge" and EXEC.network == "none"


# ----------------------------------------------------------------------------- real-deployment verification

def test_boundary_verification_passes_on_this_deployment(daemon):
    res = daemon.verify_boundary()
    assert res["verified"] is True, res
    names = {c["check"] for c in res["checks"]}
    assert {"non-root user", "no capabilities", "no-new-privileges", "seccomp filter active",
            "root filesystem read-only", "docker socket absent", "no network", "cannot write to /etc"} <= names


def test_status_reports_verified_only_after_real_checks(daemon, sbx):
    daemon.verify_boundary()
    s = status.current_sandbox_status(sbx, use_cache=False)
    assert s.verified is True and s.state.value == "verified"
