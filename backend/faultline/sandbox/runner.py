"""Runs one job in one container through the Docker CLI. Only sandboxd imports this module.

Security properties enforced here:
  * the image must be on the allowlist and is run by immutable id;
  * the spec travels over stdin, the result comes back as a framed block on stdout, so nothing host-writable is mounted;
  * mounts are read-only and come from a fixed table keyed by hash, never from the request;
  * the container always has a wall-clock limit, is labelled, and is removed in a finally block.
"""
import json
import re
import subprocess
import threading
import time
from pathlib import Path

from ..core.enums import FailureClass
from ..core.ids import new_id
from ..oracles.harness.common import BEGIN, END
from . import images, profiles

LABEL = "faultline=1"


def docker_cmd(docker_host: str | None, *args: str) -> list[str]:
    cmd = ["docker"]
    if docker_host:
        cmd += ["-H", docker_host]
    return cmd + list(args)


_ok_cache: dict = {}


def docker_ok(docker_host: str | None = None, timeout: float = 8.0, max_age: float = 0.0) -> bool:
    """Is the Docker engine reachable? max_age > 0 allows a recent positive answer to be reused (a negative never is)."""
    hit = _ok_cache.get(docker_host)
    if max_age and hit and hit[0] and time.monotonic() - hit[1] < max_age:
        return True
    ok = _docker_ok(docker_host, timeout)
    _ok_cache[docker_host] = (ok, time.monotonic())
    return ok


def _docker_ok(docker_host: str | None, timeout: float) -> bool:
    try:
        r = subprocess.run(docker_cmd(docker_host, "info", "--format", "{{.ServerVersion}}"), capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode == 0 and bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def volume_exists(name: str, docker_host: str | None = None) -> bool:
    r = subprocess.run(docker_cmd(docker_host, "volume", "inspect", name), capture_output=True, text=True, timeout=30)
    return r.returncode == 0


def volume_rm(name: str, docker_host: str | None = None) -> bool:
    r = subprocess.run(docker_cmd(docker_host, "volume", "rm", "-f", name), capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def sweep_orphans(docker_host: str | None = None) -> list[str]:
    """Remove every faultline-labelled job container (crash recovery), but not the long-lived egress proxy. Returns the removed names."""
    r = subprocess.run(docker_cmd(docker_host, "ps", "-a", "--filter", f"label={LABEL}", "--format", "{{.Names}}"),
                       capture_output=True, text=True, timeout=30)
    names = [n for n in r.stdout.split() if n and n != profiles.EGRESS_HOST]
    if names:
        subprocess.run(docker_cmd(docker_host, "rm", "-f", *names), capture_output=True, timeout=60)
    return names


def kill_group(group: str, docker_host: str | None = None) -> list[str]:
    """Kill every running container started for one worker job (cancellation). The job's own run_job then reports the kill; nothing is retried."""
    r = subprocess.run(docker_cmd(docker_host, "ps", "-q", "--filter", f"label=faultline.group={group}"), capture_output=True, text=True, timeout=30)
    ids = [i for i in r.stdout.split() if i]
    if ids:
        subprocess.run(docker_cmd(docker_host, "kill", *ids), capture_output=True, timeout=60)
    return ids


def running_groups(docker_host: str | None = None) -> list[str]:
    """The worker-job groups that currently have a container (used to find containers whose worker died)."""
    r = subprocess.run(docker_cmd(docker_host, "ps", "--filter", f"label={LABEL}", "--format", '{{.Label "faultline.group"}}'),
                       capture_output=True, text=True, timeout=30)
    return sorted({g for g in r.stdout.split() if g})


def _read_capped(stream, cap: int, sink: list, flag: dict) -> None:
    total = 0
    while True:
        chunk = stream.read(8192)
        if not chunk:
            return
        total += len(chunk)
        if sum(len(c) for c in sink) < cap:
            sink.append(chunk[: cap - sum(len(c) for c in sink)])
        else:
            flag["truncated"] = True


def extract_frame(text: str) -> dict | None:
    if BEGIN not in text or END not in text:
        return None
    body = text.split(BEGIN, 1)[1].split(END, 1)[0].strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


HARNESS_SCRIPTS = {"probe.py", "bind_sites.py", "fetch_wheels.py", "build_world.py", "world_info.py", "o_import.py", "fetch_repo.py",
                   "resolve_uv.py", "wheel_metadata.py", "contract_producer.py", "contract_consumer.py"}


def mount_arg(m: dict) -> str:
    """m = {"type": "bind"|"volume", "source": str|Path, "target": str, "readonly": bool}"""
    if m["type"] not in ("bind", "volume"):
        raise ValueError(f"mount type {m['type']!r} is not allowed")
    arg = f"type={m['type']},source={m['source']},target={m['target']}"
    return arg + (",readonly" if m.get("readonly", True) else "")


def run_job(job: dict, *, mounts: list[dict] | None = None, docker_host: str | None = None,
            lock_path: Path | None = None) -> dict:
    """Execute a structured job. Returns a plain dict shaped like OracleRunResult."""
    t0 = time.monotonic()
    job_id = job.get("job_id") or new_id("oj")
    run_id = new_id("run")
    result = {"job_id": job_id, "run_id": run_id, "provenance": "FRESH_EXECUTION", "exit_code": None,
              "failure_class": FailureClass.NONE.value, "data": None, "stdout_tail": "", "stderr_tail": "",
              "truncated": False, "duration_ms": 0, "timed_out": False, "oom": False}
    try:
        image = images.require_allowed(job["image"], lock_path)
        profile = profiles.PROFILES[job.get("zone", "exec")]
        limits = profiles.clamp_limits(job.get("limits"))
        interpreter = job.get("interpreter", "system")
        if interpreter not in ("system", "world"):
            raise ValueError(f"unknown interpreter {interpreter!r}")
        group = job.get("group")
        if group is not None and not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(group)):
            raise ValueError("group must be 1 to 80 letters, digits, dots, dashes or underscores")
        script = job.get("script", "probe.py")
        if script not in HARNESS_SCRIPTS and not (script.startswith("o_") and script.endswith(".py") and "/" not in script):
            raise ValueError(f"unknown harness script {script!r}")
    except (KeyError, ValueError) as exc:
        result.update(failure_class=FailureClass.SANDBOX_FAILURE.value, error=f"rejected: {exc}")
        return result
    if not docker_ok(docker_host, max_age=10.0):
        result.update(failure_class=FailureClass.SANDBOX_FAILURE.value, error="docker is not available: execution disabled")
        return result

    name = f"fl-{job_id}-{run_id[-6:]}".lower().replace("_", "-")
    args = profile.docker_args(limits, name, job_id, group)
    for m in mounts or []:
        args += ["--mount", mount_arg(m)]
    if interpreter == "world":
        if not any(m["target"] == "/opt/world" for m in mounts or []):
            raise_ = "interpreter 'world' needs /opt/world mounted"
            result.update(failure_class=FailureClass.SANDBOX_FAILURE.value, error=f"rejected: {raise_}")
            return result
        exe = ["/opt/world/bin/python", "-P"]          # -P: do not put the harness directory first on sys.path
    else:
        exe = ["python"]
    cmd = docker_cmd(docker_host, "run", *args, image, *exe, f"/faultline_harness/{script}")
    spec = json.dumps({"probe": job.get("probe"), "args": job.get("args", {})})
    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    flags = {"truncated": False}
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cap = int(limits["output_bytes"])
        threads = [threading.Thread(target=_read_capped, args=(proc.stdout, cap, out_chunks, flags), daemon=True),
                   threading.Thread(target=_read_capped, args=(proc.stderr, cap, err_chunks, flags), daemon=True)]
        for t in threads:
            t.start()
        try:
            proc.stdin.write(spec.encode())
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=limits["timeout_s"])
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
            subprocess.run(docker_cmd(docker_host, "kill", name), capture_output=True, timeout=30)
            proc.wait(timeout=30)
        for t in threads:
            t.join(timeout=5)
        result["exit_code"] = proc.returncode
        info = subprocess.run(docker_cmd(docker_host, "inspect", name, "--format", "{{.State.ExitCode}} {{.State.OOMKilled}}"),
                              capture_output=True, text=True, timeout=30)
        if info.returncode == 0:
            code, oom = info.stdout.split()
            result["exit_code"] = int(code)
            result["oom"] = oom == "true"
    except Exception as exc:  # noqa: BLE001
        result.update(failure_class=FailureClass.SANDBOX_FAILURE.value, error=f"{type(exc).__name__}: {exc}")
    finally:
        subprocess.run(docker_cmd(docker_host, "rm", "-f", name), capture_output=True, timeout=60)
        if proc is not None and proc.poll() is None:
            proc.kill()
    stdout = b"".join(out_chunks).decode("utf-8", "replace")
    result["stdout_tail"] = stdout[-2000:]
    result["stderr_tail"] = b"".join(err_chunks).decode("utf-8", "replace")[-2000:]
    result["truncated"] = flags["truncated"]
    result["data"] = extract_frame(stdout)
    if result["failure_class"] == FailureClass.NONE.value:
        if result["timed_out"]:
            result["failure_class"] = FailureClass.TIMEOUT.value
        elif result["oom"]:
            result["failure_class"] = FailureClass.RESOURCE_LIMIT.value
        elif result["data"] is None:
            # docker itself reports 125-127 when it could not create, start or find the command; any other
            # exit without a result frame means the harness crashed or misbehaved. 137 and 143 are SIGKILL and SIGTERM
            # that were not our own timeout or an out-of-memory kill: something outside the job stopped the container
            result["failure_class"] = (FailureClass.SANDBOX_FAILURE.value if result["exit_code"] in (125, 126, 127, 137, 143)
                                       else FailureClass.HARNESS_FAILURE.value)
    result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return result
