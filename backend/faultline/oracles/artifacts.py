"""The artifact under test: a pinned source tree mounted read-only. It is never built or installed (pure Python only)."""
import shutil
from pathlib import Path

from ..core.hashing import object_hash, sha256_hex
from ..storage.store import Store

IGNORED = {"__pycache__", ".git", ".pytest_cache", ".venv", "node_modules"}


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and not IGNORED.intersection(p.relative_to(root).parts))


def content_hash(root: Path) -> str:
    """Hash of the source tree: sorted relative paths with the hash of each file's bytes."""
    listing = [[p.relative_to(root).as_posix(), sha256_hex(p.read_bytes())] for p in _files(root)]
    return "a_" + object_hash(listing)[:40]


def prepare_artifact(source_dir: Path, store: Store) -> str:
    """Copy the tree into the content-addressed store (once) and return its content hash."""
    h = content_hash(source_dir)
    dest = store.artifact_dir(h)
    if not dest.exists():
        tmp = dest.with_name(dest.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        for p in _files(source_dir):
            t = tmp / p.relative_to(source_dir)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, t)
        tmp.rename(dest)
    return h
