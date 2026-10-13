"""Suspected relationships (L3'): model twins. A class with the same name and a similar set of fields in two repositories
is common and says nothing on its own, so it can only ever land in the suspected tray; it never produces a finding."""
import ast
from pathlib import Path

from ..ingestion.classify import classify
from .signals import Candidate, Evidence, PyProject

MIN_JACCARD = 0.8
MIN_FIELDS = 2
MAX_FILE_BYTES = 512 * 1024
MODEL_BASES = {"BaseModel", "BaseSettings", "SQLModel", "Struct"}


def class_fields(snapshot: Path, inventory_entries: list[dict]) -> dict[str, list[tuple[str, int, frozenset[str]]]]:
    """class name -> [(file, line, field names)] for annotated-field classes. Source is parsed, never imported."""
    out: dict[str, list[tuple[str, int, frozenset[str]]]] = {}
    for e in inventory_entries:
        path = e["path"]
        if e["kind"] != "file" or not path.endswith(".py"):
            continue
        c = classify(path)
        if c.role == "ignored" or "VENDORED" in c.tags or "TEST" in c.tags or e.get("size", 0) > MAX_FILE_BYTES:
            continue
        try:
            tree = ast.parse((snapshot / path).read_text(encoding="utf-8"))
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            fields = frozenset(s.target.id for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name))
            bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
            if len(fields) >= MIN_FIELDS and (bases & MODEL_BASES or any(isinstance(d, ast.Name) and d.id == "dataclass" for d in node.decorator_list)):
                out.setdefault(node.name, []).append((path, node.lineno, fields))
    return out


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def twin_candidates(a: PyProject, a_fields: dict, b: PyProject, b_fields: dict) -> list[Candidate]:
    """Suspected twins between two projects in different repositories (producer = a, consumer = b by convention)."""
    out: list[Candidate] = []
    for name in sorted(set(a_fields) & set(b_fields)):
        for fa in a_fields[name]:
            for fb in b_fields[name]:
                j = jaccard(fa[2], fb[2])
                if j >= MIN_JACCARD:
                    ev = [Evidence("model_twin", a.id, fa[0], fa[1], f"class {name}: {', '.join(sorted(fa[2]))}"),
                          Evidence("model_twin", b.id, fb[0], fb[1], f"class {name}: {', '.join(sorted(fb[2]))}")]
                    out.append(Candidate(a.id, b.id, "SUSPECTED_TWIN", "L3P", "LOW", False, "SUSPECTED", ev,
                                         f"class {name} appears in both with field overlap {j:.2f}; same name and similar fields is not evidence of a relationship"))
    return out
