"""Builds a snapshot directory and its inventory from a dict of files, for parser and discovery tests."""
from pathlib import Path


def make_snapshot(root: Path, files: dict[str, bytes | str]) -> tuple[Path, dict]:
    entries = []
    for rel, content in sorted(files.items()):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        data = content if isinstance(content, bytes) else content.encode()
        p.write_bytes(data)
        entries.append({"path": rel, "kind": "file", "mode": "100644", "blob": "0" * 40, "size": len(data)})
    return root, {"commit": "0" * 40, "entries": entries, "truncated": False, "warnings": []}
