"""Static public API surface of a package (M6.2). The package is parsed, never imported or run.

A surface lists the public functions, classes (constructor signature), methods and constants of a package, with parameter kinds and
whether each parameter is required. Re-exports are recorded as aliases and resolved when two surfaces are compared. What cannot be
seen statically is recorded, not hidden: compiled modules (`opaque_modules`), modules that build their exports at runtime
(`dynamic_exports`), and files that do not parse (`unparsed_files`).
"""
import ast
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core.hashing import content_hash, object_hash

EXTRACTOR_VERSION = "surface/1"
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES = 6000
OPAQUE_SUFFIXES = (".so", ".pyd", ".dll", ".dylib")


@dataclass(frozen=True)
class Param:
    name: str
    kind: str                       # positional_only | positional_or_keyword | var_positional | keyword_only | var_keyword
    required: bool

    def text(self) -> str:
        prefix = {"var_positional": "*", "var_keyword": "**"}.get(self.kind, "")
        return f"{prefix}{self.name}{'' if self.required or prefix else '=...'}"


@dataclass(frozen=True)
class Symbol:
    qualname: str
    kind: str                       # function | class | method | constant | alias
    params: tuple[Param, ...] | None = None     # None: no signature (constants, aliases, classes without __init__)
    bases: tuple[str, ...] = ()
    target: str | None = None       # for an alias: the dotted name it re-exports

    def describe(self) -> str:
        if self.kind == "alias":
            return f"alias of {self.target}"
        sig = "" if self.params is None else "(" + ", ".join(p.text() for p in self.params) + ")"
        base = f" bases {', '.join(self.bases)}" if self.bases else ""
        return f"{self.kind}{sig}{base}"


@dataclass
class Surface:
    package: str
    symbols: dict[str, Symbol] = field(default_factory=dict)
    opaque_modules: list[str] = field(default_factory=list)
    dynamic_exports: list[str] = field(default_factory=list)
    unparsed_files: list[str] = field(default_factory=list)
    package_hash: str = ""
    extractor_version: str = EXTRACTOR_VERSION

    def public_names(self) -> list[str]:
        """Names a user can reach without naming a private module or member. Symbols of private modules stay in `symbols` so that
        a public re-export of them still resolves."""
        return sorted(q for q in self.symbols if all(_public(part) for part in q.split(".")[1:]))

    @property
    def complete(self) -> bool:
        return not (self.opaque_modules or self.dynamic_exports or self.unparsed_files)

    def to_json(self) -> dict:
        return {"package": self.package, "package_hash": self.package_hash, "extractor_version": self.extractor_version,
                "opaque_modules": self.opaque_modules, "dynamic_exports": self.dynamic_exports, "unparsed_files": self.unparsed_files,
                "symbols": [{"qualname": s.qualname, "kind": s.kind, "target": s.target, "bases": list(s.bases),
                             "params": None if s.params is None else [[p.name, p.kind, p.required] for p in s.params]}
                            for s in sorted(self.symbols.values(), key=lambda x: x.qualname)]}

    @classmethod
    def from_json(cls, d: dict) -> "Surface":
        syms = {s["qualname"]: Symbol(s["qualname"], s["kind"], None if s["params"] is None else tuple(Param(*p) for p in s["params"]),
                                      tuple(s["bases"]), s["target"]) for s in d["symbols"]}
        return cls(d["package"], syms, d["opaque_modules"], d["dynamic_exports"], d["unparsed_files"], d["package_hash"], d["extractor_version"])


# ------------------------------------------------------------------------------------------------ reading sources

def read_tree(root: Path) -> dict[str, bytes]:
    """{path relative to root: bytes} for the Python and compiled files under root. Reads bytes only."""
    out: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and (p.suffix == ".py" or p.name.endswith(OPAQUE_SUFFIXES)):
            if len(out) >= MAX_FILES:
                break
            out[p.relative_to(root).as_posix()] = p.read_bytes() if p.stat().st_size <= MAX_FILE_BYTES else b""
    return out


def read_wheel(path: Path) -> dict[str, bytes]:
    """The same mapping from a wheel, without extracting it to disk."""
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            n = info.filename
            if info.is_dir() or ".." in n.split("/") or n.startswith("/"):
                continue
            if n.endswith(".py") or n.endswith(OPAQUE_SUFFIXES):
                if len(out) >= MAX_FILES:
                    break
                out[n] = z.read(n) if info.file_size <= MAX_FILE_BYTES else b""
    return out


# ------------------------------------------------------------------------------------------------ extraction

def _module_name(path: str, package: str) -> str | None:
    parts = path.split("/")
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
        if parts[-1] == "__init__":
            parts = parts[:-1]
    else:
        parts[-1] = parts[-1].split(".")[0]                          # compiled module: name before the first dot
    if not parts or parts[0] != package:
        return None
    return ".".join(parts)


def _public(name: str) -> bool:
    return not name.startswith("_")


def _params(args: ast.arguments, drop_first: bool) -> tuple[Param, ...]:
    out: list[Param] = []
    pos = [*args.posonlyargs, *args.args]
    defaults = [None] * (len(pos) - len(args.defaults)) + list(args.defaults)
    for i, a in enumerate(pos):
        kind = "positional_only" if i < len(args.posonlyargs) else "positional_or_keyword"
        out.append(Param(a.arg, kind, defaults[i] is None))
    if drop_first and out:
        out = out[1:]
    if args.vararg:
        out.append(Param(args.vararg.arg, "var_positional", False))
    for a, dflt in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        out.append(Param(a.arg, "keyword_only", dflt is None))
    if args.kwarg:
        out.append(Param(args.kwarg.arg, "var_keyword", False))
    return tuple(out)


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = set()
    for d in node.decorator_list:
        n = d.func if isinstance(d, ast.Call) else d
        names.add(n.attr if isinstance(n, ast.Attribute) else n.id if isinstance(n, ast.Name) else "")
    return names


def _dotted(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join(reversed([*parts, node.id])) if isinstance(node, ast.Name) else None


def _statements(body: list[ast.stmt]):
    """Module-level statements, descending into `if` and `try` blocks (a definition under a guard is still a definition)."""
    for st in body:
        if isinstance(st, ast.If):
            yield from _statements(st.body)
            yield from _statements(st.orelse)
        elif isinstance(st, ast.Try):
            yield from _statements(st.body)
            for h in st.handlers:
                yield from _statements(h.body)
            yield from _statements(st.orelse)
        else:
            yield st


def _literal_names(node: ast.AST) -> list[str] | None:
    if isinstance(node, (ast.List, ast.Tuple)) and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
        return [e.value for e in node.elts]
    return None


def _resolve_from(module: str, is_init: bool, node: ast.ImportFrom) -> str | None:
    if not node.level:
        return node.module
    parts = module.split(".")
    base = parts if is_init else parts[:-1]
    drop = node.level - 1
    if drop > len(base) - 1:
        return None
    base = base[: len(base) - drop]
    return ".".join([*base, *([node.module] if node.module else [])])


def _extract_module(surface: Surface, module: str, is_init: bool, tree: ast.Module) -> None:
    all_names: list[str] | None = None
    dynamic = False
    wildcard: list[str] = []
    stmts = list(_statements(tree.body))
    for st in stmts:                                              # __all__ first: it decides what is public
        if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in st.targets):
            lit = _literal_names(st.value)
            if lit is None:
                dynamic = True
            else:
                all_names = lit
        elif isinstance(st, ast.AugAssign) and isinstance(st.target, ast.Name) and st.target.id == "__all__":
            lit = _literal_names(st.value)
            if lit is None:
                dynamic = True
            else:
                all_names = (all_names or []) + lit
        elif isinstance(st, ast.FunctionDef | ast.AsyncFunctionDef) and st.name == "__getattr__":
            dynamic = True

    def listed(name: str) -> bool:
        return name in all_names if all_names is not None else _public(name)

    def add(sym: Symbol) -> None:
        surface.symbols.setdefault(sym.qualname, sym)

    for st in stmts:
        if isinstance(st, ast.FunctionDef | ast.AsyncFunctionDef) and listed(st.name) and st.name != "__getattr__":
            add(Symbol(f"{module}.{st.name}", "function", _params(st.args, False)))
        elif isinstance(st, ast.ClassDef) and listed(st.name):
            init = next((m for m in st.body if isinstance(m, ast.FunctionDef) and m.name == "__init__"), None)
            bases = tuple(b for b in (_dotted(x) for x in st.bases) if b and b != "object")
            add(Symbol(f"{module}.{st.name}", "class", _params(init.args, True) if init else None, bases))
            for m in st.body:
                if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef) and _public(m.name):
                    drop = "staticmethod" not in _decorators(m)
                    add(Symbol(f"{module}.{st.name}.{m.name}", "method", _params(m.args, drop)))
                elif isinstance(m, ast.Assign):
                    for t in m.targets:
                        if isinstance(t, ast.Name) and _public(t.id):
                            add(Symbol(f"{module}.{st.name}.{t.id}", "constant"))
        elif isinstance(st, ast.Assign):
            for t in st.targets:
                if isinstance(t, ast.Name) and t.id != "__all__" and listed(t.id):
                    add(Symbol(f"{module}.{t.id}", "constant"))
        elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and listed(st.target.id):
            add(Symbol(f"{module}.{st.target.id}", "constant"))
        elif isinstance(st, ast.ImportFrom):
            src = _resolve_from(module, is_init, st)
            if src is None:
                continue
            for a in st.names:
                if a.name == "*":
                    wildcard.append(src)
                elif listed(a.asname or a.name) and (is_init or all_names is not None):
                    add(Symbol(f"{module}.{a.asname or a.name}", "alias", target=f"{src}.{a.name}"))
    if wildcard:
        surface.symbols.setdefault(f"{module}.*", Symbol(f"{module}.*", "alias", target=",".join(wildcard)))
    if dynamic:
        surface.dynamic_exports.append(module)


def _expand_wildcards(surface: Surface) -> None:
    """`from .x import *` re-exports every public symbol that sits directly under x."""
    for q in [q for q in surface.symbols if q.endswith(".*")]:
        owner = q[:-2]
        for src in surface.symbols.pop(q).target.split(","):
            for name, s in list(surface.symbols.items()):
                tail = name[len(src) + 1:]
                if s.kind != "alias" and name.startswith(src + ".") and "." not in tail and _public(tail):
                    surface.symbols.setdefault(f"{owner}.{tail}", Symbol(f"{owner}.{tail}", "alias", target=name))


def extract(files: dict[str, bytes], package: str) -> Surface:
    """Surface of `package` from {path: bytes}. Paths are relative to the directory that contains the package directory."""
    surface = Surface(package=package, package_hash=object_hash(sorted((p, content_hash(b)) for p, b in files.items() if p.split("/")[0] == package)))
    for path in sorted(files):
        mod = _module_name(path, package)
        if mod is None:
            continue
        if path.endswith(OPAQUE_SUFFIXES):
            surface.opaque_modules.append(mod)
            continue
        try:
            tree = ast.parse(files[path].decode("utf-8", "replace"))
        except (SyntaxError, ValueError, RecursionError):
            surface.unparsed_files.append(path)
            continue
        _extract_module(surface, mod, path.endswith("__init__.py"), tree)
    _expand_wildcards(surface)
    surface.opaque_modules.sort()
    surface.dynamic_exports.sort()
    return surface


def resolve(surface: Surface, qualname: str) -> Symbol | None:
    """The defining symbol behind a public name, following re-exports (at most 8 hops; a cycle resolves to nothing)."""
    s = surface.symbols.get(qualname)
    for _ in range(8):
        if s is None or s.kind != "alias":
            return s
        s = surface.symbols.get(s.target or "")
    return None


def cached_surface(files: dict[str, bytes], package: str, cache_dir: Path) -> tuple[Surface, bool]:
    """(surface, from_cache). Keyed by the package content hash and the extractor version."""
    key = object_hash([package, sorted((p, content_hash(b)) for p, b in files.items() if p.split("/")[0] == package), EXTRACTOR_VERSION])
    f = cache_dir / f"surface-{key[:32]}.json"
    if f.exists():
        try:
            return Surface.from_json(json.loads(f.read_text(encoding="utf-8"))), True
        except (ValueError, KeyError, TypeError):
            pass
    s = extract(files, package)
    cache_dir.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(s.to_json(), sort_keys=True), encoding="utf-8")
    return s, False
