"""The O-bind step of a cell: find the call sites in the artifact that call into the divergent packages, and plan what O-bind can check.

Divergent packages are the distribution names that differ between the reference world and the consumer world; their import roots are
taken from the name (dashes become underscores) plus a small table of well-known distributions whose import name differs. A package
whose import name is neither is not covered, and the finding says that dynamic or unmatched call sites were not checked.
"""
import ast
import sqlite3
from pathlib import Path

from ..usage.callsites import CallSite, extract_callsites, persist_callsites

# distribution name (normalised, lower case) -> import root
IMPORT_ALIASES = {
    "pyyaml": "yaml", "pillow": "PIL", "python-dateutil": "dateutil", "beautifulsoup4": "bs4", "scikit-learn": "sklearn",
    "opencv-python": "cv2", "attrs": "attr", "pyjwt": "jwt", "protobuf": "google", "pycryptodome": "Crypto", "python-jose": "jose",
    "msgpack-python": "msgpack", "setuptools": "setuptools", "typing-extensions": "typing_extensions", "pyzmq": "zmq",
}
SKIP_DIRS = {"tests", "test", ".git", "node_modules", "build", "dist", ".venv", "venv", "__pycache__", "docs", "doc", "examples", "example", "benchmarks"}
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 3000


def import_roots(distribution_names: list[str]) -> set[str]:
    out: set[str] = set()
    for n in distribution_names:
        key = n.lower().replace("_", "-")
        out.add(IMPORT_ALIASES.get(key, key.replace("-", "_")))
    return out


def artifact_sources(art_dir: Path) -> dict[str, bytes]:
    """The artifact's own Python source (relative POSIX path -> bytes), without tests, vendored or build directories."""
    files: dict[str, bytes] = {}
    for p in sorted(Path(art_dir).rglob("*.py")):
        rel = p.relative_to(art_dir)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]) or p.name == "conftest.py" or p.name.startswith("test_") or p.is_symlink():
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
            files[rel.as_posix()] = p.read_bytes()
        except OSError:
            continue
        if len(files) >= MAX_FILES:
            break
    return files


def module_of(path: str, src_root: str) -> str | None:
    """Dotted module name of a source file relative to the artifact's source root, or None for a file outside it."""
    rel = path
    if src_root not in (".", ""):
        if not path.startswith(src_root.rstrip("/") + "/"):
            return None
        rel = path[len(src_root.rstrip("/")) + 1:]
    parts = rel[:-3].split("/") if rel.endswith(".py") else []
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or None


def reachable_modules(files: dict[str, bytes], src_root: str, entry_modules: set[str]) -> set[str]:
    """The artifact modules a consumer loads: the modules it imports, the packages above them, and everything those import from the artifact."""
    by_module = {m: p for p, m in ((p, module_of(p, src_root)) for p in files) if m}
    seen: set[str] = set()
    queue = [m for m in entry_modules if m in by_module]

    def add(name: str) -> None:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):                                   # a module's parent packages are loaded with it
            m = ".".join(parts[:i])
            if m in by_module and m not in seen:
                seen.add(m)
                queue.append(m)
    for m in list(queue):
        add(m)
    while queue:
        cur = queue.pop()
        path = by_module[cur]
        is_package = path.endswith("__init__.py")
        try:
            tree = ast.parse(files[path].decode("utf-8", "replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    add(a.name)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    pkg = cur.split(".") if is_package else cur.split(".")[:-1]
                    pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                    base = ".".join([*pkg, *([node.module] if node.module else [])])
                if base:
                    add(base)
                    for a in node.names:
                        add(f"{base}.{a.name}")
    return seen


def find_sites(conn: sqlite3.Connection, art_dir: Path, delta_names: list[str], *, src_root: str = ".",
               consumer_modules: set[str] | None = None) -> tuple[list[CallSite], list[CallSite]]:
    """(sites O-bind can check, dynamic or unresolved sites that stay unchecked). Records are persisted as usage_ref rows.

    With consumer_modules, only sites in modules the consumer loads (directly or through the artifact's own imports) are planned, the same
    principle as O-import's consumer import scan: a call in a module the consumer never loads says nothing about the consumer."""
    from ..oracles.o_bind import plan_sites
    files = artifact_sources(art_dir)
    roots = import_roots(delta_names)
    found = extract_callsites(files, roots)
    persist_callsites(conn, found, files)
    if consumer_modules is not None:
        reach = reachable_modules(files, src_root, consumer_modules)
        found = [s for s in found if module_of(s.file, src_root) in reach]
    unchecked = [s for s in found if s.status in ("DYNAMIC", "UNRESOLVED") and (s.package in roots or s.package is None)]
    return plan_sites(found), unchecked
