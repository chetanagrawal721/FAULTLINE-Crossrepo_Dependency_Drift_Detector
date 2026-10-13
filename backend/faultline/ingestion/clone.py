"""Fetching a pinned commit into an immutable snapshot directory (via the sandboxed fetch zone)."""
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import ErrorCode, FaultlineError
from ..core.hashing import content_hash, object_hash
from ..sandbox.client import SandboxClient
from ..storage.store import Store

INVENTORY = ".faultline-inventory.json"
COMPLETE = ".faultline-complete"


class FetchError(FaultlineError):
    def __init__(self, message: str, code: ErrorCode, retryable: bool = False):
        super().__init__(message, code=code, details={"retryable": retryable})
        self.retryable = retryable


@dataclass(frozen=True)
class SnapshotResult:
    key: str
    path: Path
    inventory: dict
    cached: bool


def snapshot_key(owner: str, name: str, sha: str) -> str:
    return f"{sha}_{object_hash([owner.lower(), name.lower()])[:12]}"


def _read_only(root: Path) -> None:
    for p in root.rglob("*"):
        if p.is_file():
            try:
                p.chmod(stat.S_IREAD)
            except OSError:                    # on a Linux host the files belong to the container user; the harness already made them 0444
                if os.access(p, os.W_OK):
                    raise


def _writable(root: Path) -> None:
    for p in root.rglob("*"):
        try:
            p.chmod(stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass


def load_inventory(path: Path) -> dict:
    return json.loads((path / INVENTORY).read_text(encoding="utf-8"))


def verify_snapshot(path: Path) -> list[str]:
    """Re-hash every stored file against the inventory. Returns problems (empty means the snapshot is intact)."""
    problems: list[str] = []
    if not (path / COMPLETE).exists():
        return ["snapshot is not marked complete"]
    inv = load_inventory(path)
    if (path / COMPLETE).read_text(encoding="utf-8").strip() != content_hash((path / INVENTORY).read_bytes()):
        problems.append("inventory file was modified")
    stored = 0
    for e in inv["entries"]:
        if "sha256" not in e:
            continue
        f = path.joinpath(*e["path"].split("/"))
        stored += 1
        if not f.is_file():
            problems.append(f"missing file: {e['path']}")
        elif content_hash(f.read_bytes()) != e["sha256"]:
            problems.append(f"modified file: {e['path']}")
    on_disk = {p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()} - {INVENTORY, COMPLETE}
    extra = on_disk - {e["path"] for e in inv["entries"] if "sha256" in e}
    problems += [f"unexpected file: {p}" for p in sorted(extra)]
    return problems


def fetch_snapshot(sbx: SandboxClient, image: str, store: Store, owner: str, name: str, sha: str, *,
                   remote: str | None = None, limits: dict | None = None) -> SnapshotResult:
    key = snapshot_key(owner, name, sha)
    dest = store.snapshot_dir(key)
    if (dest / COMPLETE).exists() and not verify_snapshot(dest):
        return SnapshotResult(key, dest, load_inventory(dest), cached=True)
    if dest.exists():                                    # an interrupted earlier attempt: start clean
        _writable(dest)
        import shutil
        shutil.rmtree(dest, ignore_errors=True)
    mounts: dict = {"/snapshot": {"snapshot": key}}
    if remote:
        mounts["/source"] = {"remote": remote}
    r = sbx.submit({"image": image, "zone": "fetch", "script": "fetch_repo.py", "mounts": mounts,
                    "args": {"url": "/source" if remote else f"https://github.com/{owner}/{name}.git", "sha": sha,
                             **({"limits": limits} if limits else {})},
                    "limits": {"timeout_s": 420, "tmpfs_mb": 1024, "memory_mb": 1536}})
    data = r.get("data") or {}
    if r["failure_class"] != "NONE" or data.get("status") != "OK":
        import shutil
        shutil.rmtree(dest, ignore_errors=True)
        code = ErrorCode(data["code"]) if data.get("code") in ErrorCode._value2member_map_ else (
            ErrorCode.TIMEOUT if r["failure_class"] == "TIMEOUT" else ErrorCode.FETCH_FAILED)
        msg = data.get("message") or r.get("error") or r["failure_class"]
        if not data.get("message") and r.get("stderr_tail"):                   # the harness died before it could report: say what it printed
            msg = f"{msg} (exit {r.get('exit_code')}): {r['stderr_tail'].strip()[-400:]}"
        raise FetchError(f"could not fetch {owner}/{name}@{sha[:10]}: {msg}", code,
                         retryable=code in (ErrorCode.FETCH_FAILED, ErrorCode.TIMEOUT))
    (dest / COMPLETE).write_text(content_hash((dest / INVENTORY).read_bytes()), encoding="utf-8")
    problems = verify_snapshot(dest)
    if problems:
        raise FetchError(f"snapshot failed verification right after fetch: {problems[:3]}", ErrorCode.FETCH_FAILED)
    _read_only(dest)
    return SnapshotResult(key, dest, load_inventory(dest), cached=False)


def make_read_only_walk_ok(path: Path) -> bool:
    return all(not os.access(p, os.W_OK) for p in path.rglob("*") if p.is_file())
