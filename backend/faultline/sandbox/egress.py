"""The egress path of the fetch zone (SR-4): an internal Docker network plus one proxy container that is the only way out.

Fetch containers join FETCH_NETWORK, which is created with --internal (no gateway, no route to the host or the internet).
The proxy container is attached to that network and to the default bridge, runs the allowlist in
oracles/harness/egress_proxy.py, and has no published ports. If the network or the proxy cannot be brought up, the fetch zone is
disabled with a reason: it never falls back to an unrestricted network.
"""
import subprocess
import threading
import time

from . import profiles
from .runner import docker_cmd

PROXY_NAME = profiles.EGRESS_HOST
_lock = threading.Lock()
_state: dict = {"ok": False, "at": 0.0, "reason": "not started", "image": None}


def _run(docker_host: str | None, *args: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(docker_cmd(docker_host, *args), capture_output=True, text=True, timeout=timeout)


def network_internal(docker_host: str | None = None) -> bool | None:
    r = _run(docker_host, "network", "inspect", profiles.FETCH_NETWORK, "--format", "{{.Internal}}")
    return None if r.returncode != 0 else r.stdout.strip() == "true"


def ensure(image: str, docker_host: str | None = None) -> tuple[bool, str]:
    """Create the internal network and start the proxy if needed. Returns (ok, reason). The real state is checked on every call."""
    with _lock:
        internal = network_internal(docker_host)
        if internal is None:
            r = _run(docker_host, "network", "create", "--internal", "--label", "faultline=1", profiles.FETCH_NETWORK)
            if r.returncode != 0:
                return _fail(f"cannot create the internal fetch network: {r.stderr.strip()[-200:]}")
            internal = True
        if internal is not True:
            return _fail(f"network {profiles.FETCH_NETWORK} exists but is not internal: refusing to use it")
        r = _run(docker_host, "inspect", PROXY_NAME, "--format", "{{.State.Running}}|{{.Config.Image}}")
        up = r.returncode == 0 and r.stdout.strip() == f"true|{image}"
        if not up:
            _run(docker_host, "rm", "-f", PROXY_NAME)
            r = _run(docker_host, "run", "-d", "--name", PROXY_NAME, "--label", "faultline=1", "--label", "faultline.zone=egress",
                     "--restart", "unless-stopped", "--network", "bridge", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                     "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--pids-limit", "256",
                     "--memory", "256m", "--memory-swap", "256m", "--cpus", "1", image, "python", "-u", "/faultline_harness/egress_proxy.py")
            if r.returncode != 0:
                return _fail(f"cannot start the egress proxy: {r.stderr.strip()[-200:]}")
            r = _run(docker_host, "network", "connect", "--alias", PROXY_NAME, profiles.FETCH_NETWORK, PROXY_NAME)
            if r.returncode != 0:
                _run(docker_host, "rm", "-f", PROXY_NAME)
                return _fail(f"cannot attach the egress proxy to the fetch network: {r.stderr.strip()[-200:]}")
            time.sleep(1.0)
        _state.update(ok=True, at=time.monotonic(), reason="egress proxy running", image=image)
        return True, "egress proxy running"


def _fail(reason: str) -> tuple[bool, str]:
    _state.update(ok=False, at=time.monotonic(), reason=reason)
    return False, reason


def stop(docker_host: str | None = None) -> None:
    _run(docker_host, "rm", "-f", PROXY_NAME)
    _state.update(ok=False, at=0.0, reason="stopped")
