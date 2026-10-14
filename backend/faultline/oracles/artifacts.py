"""The artifact under test: a pinned source tree mounted read-only. It is never built or installed (pure Python only)."""
import os
import shutil
import time
from pathlib import Path

from ..core.hashing import object_hash, sha256_hex
from ..storage.store import Store

IGNORED = {"__pycache__", ".git", ".pytest_cache", ".venv", "node_modules"}


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and not IGNORED.intersection(p.relative_to(root).parts))


def content_hash(root: Path) -> str:
    """Hash of the source tree: sorted relative paths with the hash of each file's bytes."""
    # sorted by the path text itself: sorting Path objects is case-insensitive on Windows and case-sensitive on Linux, which gave one tree two hashes
    listing = sorted([p.relative_to(root).as_posix(), sha256_hex(p.read_bytes())] for p in _files(root))
    return "a_" + object_hash(listing)[:40]


def _publish(tmp: Path, dest: Path) -> None:
    """Move the finished copy into place. On Windows the rename can be refused for a moment while a virus scanner or indexer holds the new
    folder, and two workers can race to create the same artifact; both are harmless, so retry briefly and accept a copy that someone else finished."""
    for attempt in range(8):
        try:
            tmp.rename(dest)
            return
        except OSError:
            if dest.exists():
                shutil.rmtree(tmp, ignore_errors=True)               # another process finished the same content-addressed copy first
                return
            if attempt == 7:
                raise
            time.sleep(0.25 * (attempt + 1))


def prepare_artifact(source_dir: Path, store: Store) -> str:
    """Copy the tree into the content-addressed store (once) and return its content hash."""
    h = content_hash(source_dir)
    dest = store.artifact_dir(h)
    if not dest.exists():
        tmp = dest.with_name(f"{dest.name}.{os.getpid()}.tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        for p in _files(source_dir):
            t = tmp / p.relative_to(source_dir)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, t)
        _publish(tmp, dest)
    return h
