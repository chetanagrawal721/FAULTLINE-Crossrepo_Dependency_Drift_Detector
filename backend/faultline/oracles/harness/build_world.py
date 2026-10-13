"""EXEC zone, NO network: build the virtualenv for one world from the local wheelhouse.

Everything is offline (--offline --no-index) and hash-checked (--require-hashes); only wheels are installed, so no
build backend or setup script can run. The world directory is /opt/world (a named volume mounted read-write for this
job only; every later use mounts it read-only).
"""
import json
import os
import subprocess
import sys

from common import emit, read_spec

PY = "/usr/local/bin/python3.12"


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def main() -> None:
    args = read_spec().get("args", {})
    os.makedirs("/work/in", exist_ok=True)
    with open("/work/in/lock.txt", "w", encoding="utf-8") as f:
        f.write(args["lock_text"])
    steps = []
    rc, out = run(["uv", "venv", "/opt/world", "--python", PY, "--clear", "-q"])
    steps.append({"step": "venv", "returncode": rc, "tail": out})
    if rc == 0:
        rc, out = run(["uv", "pip", "install", "--python", "/opt/world/bin/python", "--offline", "--no-index",
                       "--no-deps", "--require-hashes", "--find-links", "/wheelhouse", "-r", "/work/in/lock.txt", "-q"])
        steps.append({"step": "install", "returncode": rc, "tail": out})
    if rc == 0:
        with open("/opt/world/.faultline-world", "w", encoding="utf-8") as f:
            json.dump({"world_hash": args.get("world_hash"), "lock_sha256": args.get("lock_sha256")}, f)
    emit({"returncode": rc, "steps": steps})
    sys.exit(0)


if __name__ == "__main__":
    main()
