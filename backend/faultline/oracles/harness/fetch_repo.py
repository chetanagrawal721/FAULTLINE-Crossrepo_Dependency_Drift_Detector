"""FETCH zone: fetch exactly one commit of a repository and write a validated snapshot. Nothing is checked out.

Hostile-repository defences:
  * git runs with no system or global config, no hooks, no symlink materialisation, no submodule recursion, no LFS
    smudging, no prompts, and only the https protocol (file only for a locally mounted test remote);
  * blobs are read with `git cat-file --batch` and written by THIS script, so every path is validated first:
    no absolute paths, no '..', no '.git' component, no backslashes, no ':', no Windows reserved names, bounded length,
    no case collisions;
  * symlinks and submodules are recorded as metadata only and are never followed or fetched;
  * Git LFS pointers are recorded as pointers; LFS content is never downloaded;
  * file count, per-file size, total size and path length are bounded.
The inventory is written to <snapshot>/.faultline-inventory.json; a repository cannot supply a file of that name.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

from common import emit, proxy_env, read_spec

SNAP = "/snapshot"
INVENTORY = ".faultline-inventory.json"
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
LFS_MAGIC = b"version https://git-lfs.github.com/spec/"
SHA = re.compile(r"^[0-9a-f]{40}$")


def git_env(local: bool) -> dict:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/tmp/home", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1",
            "GIT_ALLOW_PROTOCOL": "file" if local else "https", "LC_ALL": "C.UTF-8", "GIT_OPTIONAL_LOCKS": "0", **proxy_env()}


CFG = ["-c", "core.symlinks=false", "-c", "core.hooksPath=/dev/null", "-c", "protocol.ext.allow=never",
       "-c", "submodule.recurse=false", "-c", "core.fsmonitor=false", "-c", "core.autocrlf=false",
       "-c", "filter.lfs.smudge=", "-c", "filter.lfs.process=", "-c", "filter.lfs.required=false"]


EXTRA_CFG: list[str] = []          # set for a locally mounted test remote (owned by another uid)


def git(args: list[str], env: dict, cwd: str | None = None, timeout: int = 240, input_: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *CFG, *EXTRA_CFG, *args], env=env, cwd=cwd, capture_output=True, timeout=timeout, input=input_)


def bad_path(path: str, max_len: int) -> str | None:
    if not path or path == INVENTORY:
        return "reserved_name"
    if len(path) > max_len:
        return "path_too_long"
    if path.startswith("/") or "\\" in path or "\x00" in path or ":" in path:
        return "unsafe_characters"
    for part in path.split("/"):
        low = part.lower()
        if part in ("", ".", "..") or low == ".git":
            return "unsafe_component"
        if low.split(".")[0] in RESERVED:
            return "reserved_name"
        if part != part.strip() or part.endswith("."):
            return "unsafe_component"
    return None


def main() -> None:
    args = read_spec().get("args", {})
    url, sha = args["url"], args["sha"]
    lim = {"max_files": 50000, "max_file_bytes": 2 * 1024 * 1024, "max_total_bytes": 200 * 1024 * 1024,
           "max_path_len": 240, **args.get("limits", {})}
    local = url.startswith("/source")
    if not SHA.match(sha):
        emit({"status": "FAILED", "code": "INVALID_REPOSITORY", "message": "sha must be 40 hex characters"})
        return
    env = git_env(local)
    os.makedirs("/tmp/home", exist_ok=True)
    if local:                                   # git honours safe.directory only from global config, not from -c
        with open("/tmp/home/gitconfig", "w") as f:
            f.write("[safe]\n\tdirectory = /source\n")
        env["GIT_CONFIG_GLOBAL"] = "/tmp/home/gitconfig"
    repo = "/work/repo"
    git(["init", "-q", repo], env)
    fetch_url = "/source" if local else url
    r = git(["fetch", "--depth", "1", "--no-tags", "-q", fetch_url, sha], env, cwd=repo)
    if r.returncode:
        err = r.stderr.decode("utf-8", "replace")[-600:]
        code = "REPOSITORY_NOT_FOUND" if ("not found" in err.lower() or "repository" in err.lower() and "access" in err.lower()) else "FETCH_FAILED"
        emit({"status": "FAILED", "code": code, "message": err})
        return
    head = git(["rev-parse", "FETCH_HEAD^{commit}"], env, cwd=repo).stdout.decode().strip()
    if head != sha:
        emit({"status": "FAILED", "code": "FETCH_FAILED", "message": f"fetched {head}, expected {sha}"})
        return
    committed = git(["log", "-1", "--format=%cI", "FETCH_HEAD"], env, cwd=repo).stdout.decode().strip()
    tree = git(["ls-tree", "-r", "-l", "-z", "FETCH_HEAD"], env, cwd=repo).stdout
    entries, warnings, truncated = [], [], False
    raw = [e for e in tree.split(b"\0") if e]
    if len(raw) > lim["max_files"]:
        truncated = True
        warnings.append(f"repository has {len(raw)} entries; only the first {lim['max_files']} are considered")
        raw = raw[: lim["max_files"]]
    seen_lower: dict[str, str] = {}
    to_read: list[tuple[str, str, int]] = []
    total = 0
    for e in raw:
        meta, _, path_b = e.partition(b"\t")
        mode, typ, oid, size_s = meta.decode().split(None, 3)
        path = path_b.decode("utf-8", "surrogateescape")
        size = int(size_s) if size_s.strip().isdigit() else 0
        item = {"path": path, "mode": mode, "blob": oid, "size": size, "kind": "file"}
        why = bad_path(path, lim["max_path_len"])
        if mode == "160000":
            item["kind"] = "submodule"
        elif mode == "120000":
            item["kind"] = "symlink"
        elif why:
            item.update(kind="unsupported_path", reason=why)
        elif path.lower() in seen_lower and seen_lower[path.lower()] != path:
            item.update(kind="unsupported_path", reason="case_collision")
        elif size > lim["max_file_bytes"]:
            item.update(kind="too_large")
        elif total + size > lim["max_total_bytes"]:
            item.update(kind="too_large", reason="total_size_limit")
            truncated = True
        else:
            seen_lower[path.lower()] = path
            total += size
            to_read.append((path, oid, size))
        entries.append(item)
    by_path = {e["path"]: e for e in entries}
    if to_read:
        order = [oid for _, oid, _ in to_read]
        p = subprocess.run(["git", *CFG, "cat-file", "--batch"], env=env, cwd=repo, input=("\n".join(order) + "\n").encode(),
                           capture_output=True, timeout=240)
        out, pos = p.stdout, 0
        for (path, _oid, _size) in to_read:
            nl = out.index(b"\n", pos)
            header = out[pos:nl].split()
            n = int(header[2])
            data = out[nl + 1: nl + 1 + n]
            pos = nl + 1 + n + 1
            item = by_path[path]
            dest = os.path.join(SNAP, *path.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
            item["size"] = len(data)
            if data.startswith(LFS_MAGIC) and len(data) < 1024:
                item["kind"] = "lfs_pointer"
    with open(os.path.join(SNAP, INVENTORY), "w", encoding="utf-8") as f:
        json.dump({"commit": head, "committed_at": committed, "entries": entries, "truncated": truncated,
                   "warnings": warnings}, f, sort_keys=True)
    for root, _dirs, files in os.walk(SNAP):              # directories stay deletable by the host user, files become read-only
        for path, mode in [(root, 0o777), *[(os.path.join(root, fn), 0o444) for fn in files]]:
            try:
                os.chmod(path, mode)
            except OSError:                               # the mount root belongs to the host and is prepared by sandboxd
                pass
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    emit({"status": "OK", "commit": head, "committed_at": committed, "counts": counts, "total_bytes": total,
          "truncated": truncated, "warnings": warnings})


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired:
        emit({"status": "FAILED", "code": "TIMEOUT", "message": "git did not finish in time"})
    sys.exit(0)
