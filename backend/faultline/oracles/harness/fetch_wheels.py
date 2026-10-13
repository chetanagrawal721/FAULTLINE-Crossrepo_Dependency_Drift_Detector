"""FETCH zone only (network allowed): download exactly the wheels a hash-pinned lock names into /wheelhouse.

Security: wheels only (--only-binary), no dependency resolution (--no-deps), and every file must match a hash in the
lock (--require-hashes). Nothing from the downloaded files is executed.
"""
import hashlib
import os
import subprocess
import sys

from common import emit, read_spec


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    args = read_spec().get("args", {})
    os.makedirs("/work/in", exist_ok=True)
    with open("/work/in/lock.txt", "w", encoding="utf-8") as f:
        f.write(args["lock_text"])
    cmd = [sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--no-deps", "--require-hashes",
           "--disable-pip-version-check", "--no-cache-dir", "-r", "/work/in/lock.txt", "-d", "/wheelhouse"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    files = []
    for name in sorted(os.listdir("/wheelhouse")):
        if name.endswith(".whl"):
            p = os.path.join("/wheelhouse", name)
            files.append({"name": name, "sha256": sha256_file(p), "size": os.path.getsize(p)})
    emit({"returncode": r.returncode, "stderr_tail": r.stderr[-1500:], "stdout_tail": r.stdout[-500:], "files": files})


if __name__ == "__main__":
    main()
