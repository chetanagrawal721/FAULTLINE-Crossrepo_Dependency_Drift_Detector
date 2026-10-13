"""Consumer-import scan (PC-4): which modules of the artifact does the consumer actually import?

Only those modules are exercised, so a consumer that never touches an optional part of the artifact is not blamed for it.
Source is parsed, never imported or run. Dynamic imports are recorded as dynamic, never treated as absent.
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path

from ..ingestion.classify import classify

MAX_BYTES = 512 * 1024


@dataclass
class ImportScan:
    modules: list[str] = field(default_factory=list)       # artifact modules the consumer imports, sorted
    sites: list[dict] = field(default_factory=list)        # {module, file, line}
    dynamic: list[dict] = field(default_factory=list)      # {file, line, form}: imports that cannot be resolved statically


def artifact_modules(snapshot: Path, entries: list[dict], source_root: str, package: str) -> set[str]:
    """Dotted names of every module inside the artifact's import package (from the producer snapshot's file list)."""
    prefix = "" if source_root in (".", "") else source_root.rstrip("/") + "/"
    out: set[str] = set()
    for e in entries:
        p = e["path"]
        if e["kind"] != "file" or not p.endswith(".py") or not p.startswith(prefix + package):
            continue
        parts = p[len(prefix):-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts and parts[0] == package:
            out.add(".".join(parts))
    return out


def scan_imports(snapshot: Path, entries: list[dict], package: str, known: set[str], *, under: str = "") -> ImportScan:
    scan = ImportScan()
    found: dict[str, None] = {}
    prefix = "" if under in ("", ".") else under.rstrip("/") + "/"
    for e in sorted(entries, key=lambda x: x["path"]):
        path = e["path"]
        if e["kind"] != "file" or not path.endswith(".py") or not path.startswith(prefix) or e.get("size", 0) > MAX_BYTES:
            continue
        c = classify(path)
        if c.role == "ignored" or "VENDORED" in c.tags:
            continue
        try:
            tree = ast.parse((snapshot / path).read_text(encoding="utf-8"))
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names if a.name != "*"]
            elif isinstance(node, ast.Call) and _is_dynamic_import(node) and not _literal_target(node):
                scan.dynamic.append({"file": path, "line": node.lineno, "form": "importlib.import_module / __import__ with a non-literal argument"})
            elif isinstance(node, ast.Call) and _is_dynamic_import(node) and (lit := _literal_target(node)):
                names = [lit]
            for n in names:
                if n == package or n.startswith(package + "."):
                    if n in known:                                  # a submodule that exists; an attribute is not a module
                        found.setdefault(n)
                        scan.sites.append({"module": n, "file": path, "line": getattr(node, "lineno", 0)})
                    elif n == package:
                        found.setdefault(package)
    scan.modules = sorted(found)
    return scan


def _is_dynamic_import(node: ast.Call) -> bool:
    f = node.func
    return (isinstance(f, ast.Attribute) and f.attr == "import_module") or (isinstance(f, ast.Name) and f.id in ("__import__", "import_module"))


def _literal_target(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None
