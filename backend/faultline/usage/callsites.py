"""Minimal call-site extractor (PC-1, master section 20.2): real call sites into divergent packages, read from source, never executed.

For every Python file the extractor builds an alias map from its imports, then records every Call whose callee resolves, through
imports, aliases, module-level attribute chains and getattr with a literal name, into a package in D (the divergent packages). Each
record keeps the call shape (positional count, keyword names, star flags, literal argument values when all of them are literals),
the file hash, the line and the column.

Status classes: RESOLVED (callee known), DYNAMIC (getattr or import with a non-literal name, so the target is unknown) and
UNRESOLVED (exec and eval). A dynamic or unresolved site is recorded; it is never treated as absent.

Limits, on purpose: method calls on instances (`x = pkg.Cls(); x.method()`), calls through decorators and metaclasses, and
re-exports through the artifact's own modules are not followed; they produce no record. O-bind therefore checks only the sites listed
here and says so.
"""
import ast
from dataclasses import asdict, dataclass

from ..core.hashing import content_hash

ANALYZER_VERSION = "callsites/1"
DYNAMIC_IMPORTERS = {"importlib.import_module", "__import__"}
UNRESOLVED_CALLS = {"exec", "eval"}


@dataclass(frozen=True)
class CallSite:
    file: str
    file_sha256: str
    line: int
    col: int
    callee: str | None                  # fully qualified dotted name, e.g. urllib3.util.retry.Retry (None for DYNAMIC and UNRESOLVED)
    package: str | None                 # first component of callee (the import root)
    status: str                         # RESOLVED | DYNAMIC | UNRESOLVED
    n_positional: int
    keyword_names: tuple[str, ...]
    has_star_args: bool
    has_star_kwargs: bool
    literals: dict | None               # {"args": [...], "kwargs": {...}} only when every argument is a literal and there are no stars
    flags: tuple[str, ...] = ()         # TYPE_ONLY, OPTIONAL_PATH, DYNAMIC_GETATTR, DYNAMIC_IMPORT
    reason: str | None = None

    @property
    def site_id(self) -> str:
        return f"{self.file}:{self.line}:{self.col}"

    def to_json(self) -> dict:
        d = asdict(self)
        d["keyword_names"] = list(self.keyword_names)
        d["flags"] = list(self.flags)
        return d


def _dotted(node: ast.AST) -> str | None:
    """Name or attribute chain as a dotted string, or None if it is anything else."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class _Imports(ast.NodeVisitor):
    """Alias map for one file, with the tags of the block each import sits in (TYPE_CHECKING, try/except ImportError)."""

    def __init__(self) -> None:
        self.alias: dict[str, str] = {}
        self.tags: dict[str, set[str]] = {}
        self._ctx: list[str] = []

    def _bind(self, name: str, target: str) -> None:
        self.alias[name] = target
        if self._ctx:
            self.tags.setdefault(name, set()).update(self._ctx)

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if a.asname:
                self._bind(a.asname, a.name)
            else:
                self._bind(a.name.split(".")[0], a.name.split(".")[0])      # `import a.b` binds `a`; the chain a.b.c resolves by attribute

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level or not node.module:                                    # relative imports point inside the artifact
            return
        for a in node.names:
            if a.name != "*":
                self._bind(a.asname or a.name, f"{node.module}.{a.name}")

    def visit_If(self, node: ast.If) -> None:
        test = _dotted(node.test) or ""
        if test.endswith("TYPE_CHECKING"):
            self._ctx.append("TYPE_ONLY")
            for n in node.body:
                self.visit(n)
            self._ctx.pop()
            for n in node.orelse:
                self.visit(n)
        else:
            self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        guards = any(isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "ModuleNotFoundError") or
                     isinstance(h.type, ast.Tuple) and any(isinstance(e, ast.Name) and e.id in ("ImportError", "ModuleNotFoundError") for e in h.type.elts)
                     for h in node.handlers)
        if guards:
            self._ctx.append("OPTIONAL_PATH")
        for n in node.body:
            self.visit(n)
        if guards:
            self._ctx.pop()
        for part in (node.handlers, node.orelse, node.finalbody):
            for n in part:
                self.visit(n)


def _is_literal(node: ast.AST) -> bool:
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False


def _shape(call: ast.Call) -> tuple[int, tuple[str, ...], bool, bool, dict | None]:
    star = any(isinstance(a, ast.Starred) for a in call.args)
    dstar = any(k.arg is None for k in call.keywords)
    n_pos = sum(1 for a in call.args if not isinstance(a, ast.Starred))
    kws = tuple(k.arg for k in call.keywords if k.arg)
    literals = None
    if not star and not dstar and all(_is_literal(a) for a in call.args) and all(_is_literal(k.value) for k in call.keywords):
        literals = {"args": [ast.literal_eval(a) for a in call.args], "kwargs": {k.arg: ast.literal_eval(k.value) for k in call.keywords}}
    return n_pos, kws, star, dstar, literals


def extract_file(path: str, source: bytes | str, divergent: set[str]) -> list[CallSite]:
    """Call sites in one file. A file that does not parse yields no records (the caller records it as PARSE_ERROR)."""
    raw = source if isinstance(source, bytes) else source.encode("utf-8")
    sha = content_hash(raw)
    try:
        tree = ast.parse(raw.decode("utf-8", "replace"))
    except SyntaxError:
        return []
    imports = _Imports()
    imports.visit(tree)

    def resolve(node: ast.AST) -> tuple[str | None, set[str]]:
        """(dotted target, tags) for a callee expression, following aliases, attribute chains and getattr with a literal name."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) == 2 \
                and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            base, tags = resolve(node.args[0])
            return (f"{base}.{node.args[1].value}" if base else None), tags
        d = _dotted(node)
        if d is None:
            return None, set()
        head, _, rest = d.partition(".")
        if head not in imports.alias:
            return None, set()
        target = imports.alias[head] + ("." + rest if rest else "")
        return target, imports.tags.get(head, set())

    sites: list[CallSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        n_pos, kws, star, dstar, literals = _shape(node)
        common = dict(file=path, file_sha256=sha, line=node.lineno, col=node.col_offset, n_positional=n_pos, keyword_names=kws,
                      has_star_args=star, has_star_kwargs=dstar, literals=literals)
        target, tags = resolve(node.func)
        func_name = _dotted(node.func)
        if isinstance(node.func, ast.Name) and node.func.id in UNRESOLVED_CALLS:
            sites.append(CallSite(callee=None, package=None, status="UNRESOLVED", flags=(), reason=f"{node.func.id}() runs code that cannot be read statically", **common))
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) == 2 and not (isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
            base, btags = resolve(node.args[0])
            if base and base.split(".")[0] in divergent:
                sites.append(CallSite(callee=None, package=base.split(".")[0], status="DYNAMIC", flags=tuple(sorted({"DYNAMIC_GETATTR", *btags})),
                                      reason=f"getattr on {base} with a name that is not a literal", **common))
            continue
        if target in DYNAMIC_IMPORTERS or (func_name in DYNAMIC_IMPORTERS) or (isinstance(node.func, ast.Name) and node.func.id == "__import__"):
            if node.args and not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                sites.append(CallSite(callee=None, package=None, status="DYNAMIC", flags=("DYNAMIC_IMPORT",), reason="import by a name that is not a literal", **common))
            continue
        if target and target.split(".")[0] in divergent:
            sites.append(CallSite(callee=target, package=target.split(".")[0], status="RESOLVED", flags=tuple(sorted(tags)), **common))
    sites.sort(key=lambda s: (s.file, s.line, s.col))
    return sites


def extract_callsites(files: dict[str, bytes | str], divergent: set[str]) -> list[CallSite]:
    """All call sites of a source tree: {relative path: source}. Only .py files are read."""
    out: list[CallSite] = []
    for path in sorted(files):
        if path.endswith(".py"):
            out += extract_file(path, files[path], divergent)
    return out


def persist_callsites(conn, sites: list[CallSite], files: dict[str, bytes | str]) -> int:
    """Store the records (usage_file per content hash, usage_ref per call site). Returns the number of call-site rows written."""
    import json

    from ..core.hashing import object_hash
    for path, src in files.items():
        if path.endswith(".py"):
            raw = src if isinstance(src, bytes) else src.encode("utf-8")
            conn.execute("INSERT OR IGNORE INTO usage_file(content_hash, analyzer_version, status) VALUES (?,?, 'OK')", (content_hash(raw), ANALYZER_VERSION))
    n = 0
    for s in sites:
        shape = {"n_pos": s.n_positional, "kw": list(s.keyword_names), "star": s.has_star_args, "dstar": s.has_star_kwargs, "literals": s.literals}
        conn.execute("INSERT OR REPLACE INTO usage_ref(id, content_hash, line, col, target, root_package, status, ref_kind, call_shape_json, tags) "
                     "VALUES (?,?,?,?,?,?,?, 'CALL', ?, ?)",
                     ("ur_" + object_hash([s.file_sha256, s.line, s.col, s.callee, s.status])[:24], s.file_sha256, s.line, s.col, s.callee, s.package,
                      s.status, json.dumps(shape, sort_keys=True), ",".join(s.flags)))
        n += 1
    return n
