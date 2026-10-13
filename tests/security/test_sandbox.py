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
    assert EXEC.network == "none"
    assert FETCH.network == "faultline-fetch" and FETCH.network not in ("bridge", "host")      # SR-4: only the internal network, never the default bridge
    fetch_args = " ".join(FETCH.docker_args(__import__("faultline.sandbox.profiles", fromlist=["x"]).DEFAULT_LIMITS, "n", "j"))
    assert "--network faultline-fetch" in fetch_args and "HTTPS_PROXY=http://faultline-egress:3128" in fetch_args


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


# ----------------------------------------------------------------------------- SR-4 fetch-zone egress (real containers)

@pytest.fixture(scope="module")
def egress_probe(daemon, image):
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=120)
    r = sbx.submit({"image": image, "zone": "fetch", "probe": "egress", "limits": {"timeout_s": 60},
                    "args": {"targets": ["169.254.169.254:80", "127.0.0.1:443", "10.0.0.1:443", "example.com:443", "github.com:22", "github.com:443"],
                             "direct": [["1.1.1.1", 443], ["169.254.169.254", 80]]}})
    assert r["failure_class"] == "NONE", r
    return r["data"]["data"]


def test_sr4_fetch_zone_has_no_direct_route_out(egress_probe):
    assert egress_probe["direct"] == {"1.1.1.1:443": False, "169.254.169.254:80": False}


def test_sr4_proxy_refuses_metadata_private_unlisted_and_other_ports(egress_probe):
    c = egress_probe["connect"]
    assert all(c[t] == "403" for t in ("169.254.169.254:80", "127.0.0.1:443", "10.0.0.1:443", "example.com:443", "github.com:22")), c


def test_sr4_proxy_allows_a_listed_host_when_the_network_is_up(egress_probe):
    status = egress_probe["connect"]["github.com:443"]
    if status.startswith("error") or status in ("502", "503"):
        pytest.skip(f"no outbound network from this machine ({status})")
    assert status == "200"


def test_sr4_fetch_network_is_internal_and_the_boundary_report_includes_the_egress_checks(daemon):
    from faultline.sandbox import egress
    assert egress.network_internal() is True
    b = daemon.verify_boundary()
    names = {c["check"]: c["ok"] for c in b["checks"]}
    for need in ("egress proxy running", "fetch network is internal", "direct egress from the fetch zone is blocked",
                 "proxy refuses cloud metadata, loopback and private targets", "proxy refuses hosts that are not allowlisted and other ports"):
        assert names.get(need) is True, (need, b["checks"])
    assert b["verified"] is True


def test_sr4_fetch_fails_closed_when_the_proxy_cannot_start(daemon, image, monkeypatch):
    from faultline.sandbox import egress
    monkeypatch.setattr(egress, "ensure", lambda *a, **k: (False, "simulated: proxy cannot start"))
    r = daemon.run({"image": image, "zone": "fetch", "probe": "echo", "args": {}, "limits": {"timeout_s": 30}})
    assert r["failure_class"] == "SANDBOX_FAILURE" and "fetch zone disabled" in r["error"] and r["data"] is None


def test_sr4_the_orphan_sweeper_never_removes_the_egress_proxy(daemon, image):
    from faultline.sandbox import egress, runner
    ok, why = egress.ensure(image)
    assert ok, why
    removed = runner.sweep_orphans()
    assert "faultline-egress" not in removed
    ok, why = egress.ensure(image)                                       # still there, no restart needed
    assert ok, why


def _online() -> bool:
    import socket
    try:
        socket.create_connection(("github.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


def test_sr4_a_real_github_clone_goes_through_the_proxy(daemon, image):
    """A fresh store, so nothing is cached: git inside the fetch zone must reach github.com only via the egress proxy."""
    if not _online():
        pytest.skip("no outbound network from this machine")
    from faultline.ingestion.clone import fetch_snapshot
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=300)
    snap = fetch_snapshot(sbx, image, daemon.store, "chetanagrawal721", "faultline-fixture-acme-models", "2e072e64e4ed0cba0127fd9e457274823febe8a6")
    assert not snap.cached and any(e["path"] == "pyproject.toml" for e in snap.inventory["entries"])


def test_sr4_uv_resolution_goes_through_the_proxy(daemon, image):
    if not _online():
        pytest.skip("no outbound network from this machine")
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=300)
    r = sbx.submit({"image": image, "zone": "fetch", "script": "resolve_uv.py", "limits": {"timeout_s": 240},
                    "args": {"requirements": ["idna==3.4"], "exclude_newer": "2024-10-30T00:00:00Z"}})
    data = r.get("data") or {}
    assert r["failure_class"] == "NONE" and data.get("returncode") == 0, (r.get("failure_class"), (data.get("stderr") or r.get("stderr_tail") or "")[-300:])


# ----------------------------------------------------------------------------- TC-11.3.2 fail closed on a bad control

def test_tc_11_3_2_a_network_on_the_execution_profile_fails_the_inspector_and_disables_execution(daemon, sbx, monkeypatch):
    from faultline.sandbox import profiles
    try:
        monkeypatch.setitem(profiles.PROFILES, "exec", profiles.Profile("exec", "bridge"))          # the misconfiguration: the execution zone gets a network
        res = daemon.verify_boundary()
        assert res["verified"] is False and "no network" in res["reason"], res
        failed = [c["check"] for c in res["checks"] if not c["ok"]]
        assert "no network" in failed
        s = status.current_sandbox_status(sbx, use_cache=False)
        assert s.verified is False and s.state.value != "verified" and s.reason       # execution is reported unavailable, with a reason
    finally:
        monkeypatch.undo()
        assert daemon.verify_boundary()["verified"] is True                              # and it recovers once the profile is correct


def test_tc_11_3_2_a_broken_egress_control_fails_the_inspector(daemon, monkeypatch):
    from faultline.sandbox import egress
    monkeypatch.setattr(egress, "ensure", lambda *a, **k: (False, "simulated: proxy cannot start"))
    res = daemon.verify_boundary()
    assert res["verified"] is False and "egress proxy running" in res["reason"]
    monkeypatch.undo()
    assert daemon.verify_boundary()["verified"] is True


# ----------------------------------------------------------------------------- M5.3 cancellation reaches the running container

def test_cancelling_a_job_group_kills_its_running_container_and_removes_it(daemon, image):
    import threading
    import time

    from faultline.sandbox.client import SandboxClient, job_group
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=120)
    group = "job_cancel_test_1"
    box: dict = {}

    def long_job():
        with job_group(group):
            box["r"] = sbx.submit({"image": image, "zone": "exec", "probe": "sleep", "args": {"seconds": 60}, "limits": {"timeout_s": 120}})
    t = threading.Thread(target=long_job)
    t0 = time.monotonic()
    t.start()
    for _ in range(40):                                                          # wait until the container exists
        if group in sbx.groups():
            break
        time.sleep(0.5)
    assert group in sbx.groups()
    assert sbx.cancel(group), "a running container should have been killed"
    t.join(timeout=30)
    assert not t.is_alive() and time.monotonic() - t0 < 50                      # it did not run for its full 60 seconds
    assert box["r"]["failure_class"] in ("SANDBOX_FAILURE", "TIMEOUT", "HARNESS_FAILURE") or box["r"]["exit_code"] != 0
    assert sbx.groups() == [] or group not in sbx.groups()
    assert [n for n in labelled_containers() if group in n] == []                # removed, not just stopped


def test_a_group_name_cannot_inject_anything(sbx, image):
    r = sbx.submit({"image": image, "zone": "exec", "probe": "echo", "args": {}, "group": "x --privileged", "limits": {"timeout_s": 20}})
    assert r["failure_class"] == "SANDBOX_FAILURE" and "group must be" in r["error"]
