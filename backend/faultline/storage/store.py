"""Content-addressed file store. Paths are derived from hashes only, never from request strings."""
import re
from pathlib import Path

_HASH = re.compile(r"^[A-Za-z0-9_]{6,100}$")


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _dir(self, kind: str, key: str) -> Path:
        if not _HASH.match(key):
            raise ValueError(f"unsafe store key {key!r}")
        return self.root / kind / key

    def world_dir(self, world_hash: str) -> Path:
        return self._dir("worlds", world_hash)

    def artifact_dir(self, content_hash: str) -> Path:
        return self._dir("artifacts", content_hash)

    def snapshot_dir(self, key: str) -> Path:
        """key is derived from owner, repository and the pinned sha (see ingestion.clone.snapshot_key)."""
        return self._dir("snapshots", key)

    def remote_dir(self, name: str) -> Path:
        """Local git remotes used by tests (mounted read-only into the fetch container as /source)."""
        return self._dir("remotes", name)

    def wheelhouse(self) -> Path:
        return self.root / "wheels"

    def ensure(self, p: Path) -> Path:
        p.mkdir(parents=True, exist_ok=True)
        return p
