"""FETCH zone only (network allowed): make sure the wheels a hash-pinned lock names are in /wheelhouse.

Security: wheels only (--only-binary), no dependency resolution (--no-deps), and every file must match a hash in the
lock (--require-hashes). Nothing from the downloaded files is executed.

A wheel that is already in the wheelhouse with a hash the lock lists is the very same file the download would give, so it is used as it is and
the package index is not contacted for it. Only the missing wheels are downloaded. A warm run therefore needs no network at all, and a slow or
unreachable index cannot stall a world that is already complete.
"""
import hashlib
import os
import re
import subprocess
import sys

from common import emit, read_spec


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def parse_lock(text: str) -> list[dict]:
    """[{name, version, hashes, block}] from a pip lock with `name==version \\` lines followed by `--hash=sha256:...` lines."""
    out: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.strip().rstrip("\\").strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;]+)", line)
        if m:
            cur = {"name": m.group(1), "version": m.group(2), "hashes": re.findall(r"--hash=sha256:([0-9a-f]{64})", line), "block": [raw.rstrip()]}
            out.append(cur)                                       # hashes may be on this line (one-line locks) or on the lines that follow
        elif cur is not None:
            cur["block"].append(raw.rstrip())
            h = re.search(r"--hash=sha256:([0-9a-f]{64})", line)
            if h:
                cur["hashes"].append(h.group(1))
    return out


def in_wheelhouse(req: dict, wheelhouse: str) -> bool:
    """True when a wheel for this exact name and version is present and its hash is one of the lock's."""
    if not req["hashes"] or not os.path.isdir(wheelhouse):
        return False
    key = re.sub(r"[-_.]+", "_", req["name"]).lower() + "-" + req["version"].replace("-", "_") + "-"
    for fname in os.listdir(wheelhouse):
        if fname.endswith(".whl") and fname.lower().startswith(key) and sha256_file(os.path.join(wheelhouse, fname)) in req["hashes"]:
            return True
    return False


def main() -> None:
    args = read_spec().get("args", {})
    os.makedirs("/work/in", exist_ok=True)
    reqs = parse_lock(args["lock_text"])
    missing = [r for r in reqs if not in_wheelhouse(r, "/wheelhouse")]
    result = {"returncode": 0, "stderr_tail": "", "stdout_tail": "", "already_present": len(reqs) - len(missing), "downloaded": len(missing)}
    if missing or not reqs:
        text = "\n".join("\n".join(r["block"]) for r in missing) + "\n" if reqs else args["lock_text"]
        with open("/work/in/lock.txt", "w", encoding="utf-8") as f:
            f.write(text)
        cmd = [sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--no-deps", "--require-hashes",
               "--disable-pip-version-check", "--no-cache-dir", "--retries", "3", "--timeout", "20", "-r", "/work/in/lock.txt", "-d", "/wheelhouse"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        result.update(returncode=r.returncode, stderr_tail=r.stderr[-1500:], stdout_tail=r.stdout[-500:])
    files = []
    for name in sorted(os.listdir("/wheelhouse")):
        if name.endswith(".whl"):
            p = os.path.join("/wheelhouse", name)
            files.append({"name": name, "sha256": sha256_file(p), "size": os.path.getsize(p)})
    emit({**result, "files": files})


if __name__ == "__main__":
    main()
