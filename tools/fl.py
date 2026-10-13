#!/usr/bin/env python3
"""Cross-platform task runner. The Makefile only forwards here, so Windows and Linux behave the same.

  python tools/fl.py up [--check] [--port 8000]   start API + worker (+ built UI); --check boots, probes, stops
  python tools/fl.py down                          stop processes started with `up --detach`
  python tools/fl.py test                          unit + integration tests
  python tools/fl.py lint                          ruff
  python tools/fl.py fixtures                      run fixture scenarios (arrives with M1.1)
  python tools/fl.py e2e [SCENARIO]                end-to-end scenario run (arrives with M1.8)
  python tools/fl.py check-pins                    verify tool and dependency pins
  python tools/fl.py gen-types                     regenerate OpenAPI JSON and TypeScript types
  python tools/fl.py check-types                   fail if the committed types are stale (the CI drift check)
  python tools/fl.py ci                            everything CI runs, in order

Every command exits non-zero on failure.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
VAR = ROOT / "var"


def venv_python() -> str:
    for cand in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if cand.exists():
            return str(cand)
    return sys.executable


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(cwd), env={**os.environ, **(env or {})})


def kill_tree(pid: int) -> None:
    """Stop a process and its children. On Windows the venv python.exe is a launcher that spawns the real
    interpreter, so terminating the launcher alone would leave the server running."""
    if os.name == "nt":
        subprocess.call(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def npm(*args: str) -> list[str]:
    return [shutil.which("npm") or "npm", *args]


# ----------------------------------------------------------------------------- commands

def cmd_test(_: list[str]) -> int:
    # tests/security needs Docker and the built image; its fixtures skip (and say so) when either is missing
    return run([venv_python(), "-m", "pytest", "-q", "tests/unit", "tests/integration", "tests/security"])


def cmd_lint(_: list[str]) -> int:
    return run([venv_python(), "-m", "ruff", "check", "backend", "tests", "tools", "scripts"])


def cmd_fixtures(_: list[str]) -> int:
    script = ROOT / "scripts" / "run_fixtures.py"
    if not script.exists():
        print("fixtures are not available yet: scripts/run_fixtures.py arrives with milestone M1.1", file=sys.stderr)
        return 2
    return run([venv_python(), str(script), "--assert"])


def cmd_e2e(args: list[str]) -> int:
    if not list((ROOT / "tests" / "e2e").glob("test_*.py")):
        print("no end-to-end tests yet: the first arrives with milestone M1.8", file=sys.stderr)
        return 2
    env = {"FAULTLINE_SCENARIO": args[0]} if args else {}
    return run([venv_python(), "-m", "pytest", "-q", "tests/e2e"], env=env)


def cmd_check_pins(_: list[str]) -> int:
    return run([venv_python(), "scripts/check_pins.py"])


def cmd_images(_: list[str] | None = None) -> int:
    probe = subprocess.run(["docker", "info"], capture_output=True)
    if probe.returncode:
        print("Docker is not running: skipping the image build; sandbox tests will be skipped", file=sys.stderr)
        return 0
    return run([venv_python(), "scripts/build_images.py"])


def cmd_gen_types(_: list[str]) -> int:
    rc = run([venv_python(), "scripts/export_openapi.py"])
    return rc or run(npm("run", "gen:types"), cwd=FRONTEND)


def build_ui() -> int:
    if not (FRONTEND / "node_modules").exists():
        rc = run(npm("ci", "--no-audit", "--no-fund"), cwd=FRONTEND)
        if rc:
            return rc
    return run(npm("run", "build"), cwd=FRONTEND)


def wait_http(url: str, timeout: float = 30.0) -> bytes:
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.read()
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last = exc
            time.sleep(0.3)
    raise RuntimeError(f"{url} did not answer in {timeout}s: {last}")


def cmd_up(args: list[str]) -> int:
    check = "--check" in args
    detach = "--detach" in args
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8000
    if not (FRONTEND / "dist" / "index.html").exists():
        rc = build_ui()
        if rc:
            return rc
    db_dir = Path(tempfile.mkdtemp(prefix="faultline-up-")) if check else VAR
    env = {**os.environ, "FAULTLINE_DB": str(db_dir / "faultline.db"), "PYTHONPATH": str(ROOT / "backend")}
    VAR.mkdir(exist_ok=True)
    py = venv_python()
    out = {}
    if detach:
        out = {"stdout": open(VAR / "api.log", "ab"), "stderr": subprocess.STDOUT}   # keep the caller's terminal free
    api = subprocess.Popen([py, "-m", "uvicorn", "faultline.api.main:app_factory", "--factory",
                            "--host", "127.0.0.1", "--port", str(port)], cwd=str(ROOT), env=env, **out)
    if detach:
        out = {"stdout": open(VAR / "worker.log", "ab"), "stderr": subprocess.STDOUT}
    worker = subprocess.Popen([py, "-m", "faultline.workers.run"], cwd=str(ROOT), env=env, **out)
    procs = [api, worker]
    sandboxd = None
    if (ROOT / "docker" / "images.lock.json").exists():
        out = {"stdout": open(VAR / "sandboxd.log", "ab"), "stderr": subprocess.STDOUT} if detach else {}
        sandboxd = subprocess.Popen([py, "-m", "faultline.sandbox.sandboxd"], cwd=str(ROOT), env=env, **out)
        procs.append(sandboxd)

    def stop(*_):
        for p in procs:
            if p.poll() is None:
                kill_tree(p.pid)
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()

    try:
        base = f"http://127.0.0.1:{port}"
        health = json.loads(wait_http(f"{base}/api/health"))
        caps = json.loads(wait_http(f"{base}/api/capabilities"))
        ui = wait_http(f"{base}/")
        print(f"API ok (schema v{health['schema_version']}, mode {health['mode']}), "
              f"sandbox {caps['sandbox']['state']}, UI {len(ui)} bytes at {base}/")
        if worker.poll() is not None:
            print("worker exited early", file=sys.stderr)
            return 1
        if check:
            return 0
        if detach:
            (VAR / "pids.json").write_text(json.dumps({"api": api.pid, "worker": worker.pid,
                                                      **({"sandboxd": sandboxd.pid} if sandboxd else {})}))
            print("started in the background; stop with: python tools/fl.py down")
            return 0
        print("running. Ctrl-C to stop.")
        signal.signal(signal.SIGINT, stop)
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        return 1
    finally:
        if not detach or check:
            stop()
            if check:
                shutil.rmtree(db_dir, ignore_errors=True)


def cmd_down(_: list[str]) -> int:
    f = VAR / "pids.json"
    if not f.exists():
        print("nothing to stop")
        return 0
    for name, pid in json.loads(f.read_text()).items():
        kill_tree(pid)
        print(f"stopped {name} ({pid})")
    f.unlink()
    return 0


def cmd_ci(_: list[str]) -> int:
    steps = [
        ("lint", cmd_lint),
        ("pins", cmd_check_pins),
        ("images", lambda a: cmd_images()),
        ("tests", cmd_test),
        ("openapi/types current", lambda a: types_current()),
        ("frontend build", lambda a: build_ui()),
        ("boot", lambda a: cmd_up(["--check", "--port", "8123"])),
    ]
    for name, fn in steps:
        print(f"\n=== {name} ===", flush=True)
        rc = fn([])
        if rc:
            print(f"\nCI step failed: {name}", file=sys.stderr)
            return rc
    print("\nCI: all steps passed")
    return 0


def types_current() -> int:
    """The committed OpenAPI JSON and generated TypeScript types must match the API as it is now."""
    rc = run([venv_python(), "scripts/export_openapi.py", "--check"])
    if rc:
        return rc
    tmp = Path(tempfile.mkdtemp(prefix="fl-types-")) / "schema.d.ts"
    rc = run(npm("exec", "--", "openapi-typescript", "./openapi.json", "-o", str(tmp)), cwd=FRONTEND)
    if rc:
        return rc
    committed = (FRONTEND / "src" / "api" / "schema.d.ts").read_text(encoding="utf-8")
    if tmp.read_text(encoding="utf-8") != committed:
        print("frontend/src/api/schema.d.ts is stale: run `python tools/fl.py gen-types`", file=sys.stderr)
        return 1
    print("TypeScript types are current")
    return 0


COMMANDS = {"up": cmd_up, "down": cmd_down, "test": cmd_test, "lint": cmd_lint, "fixtures": cmd_fixtures,
            "e2e": cmd_e2e, "check-pins": cmd_check_pins, "gen-types": cmd_gen_types,
            "check-types": lambda a: types_current(), "images": cmd_images, "ci": cmd_ci}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
