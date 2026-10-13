"""setup.py reader that NEVER executes it: the file is parsed to an AST and only literal arguments of the `setup(...)` call are read.

`install_requires`, `extras_require`, `python_requires`, `name` and `version` are accepted when they are literals, or names bound
once at module level to a literal. Anything computed (function calls, file reads, conditionals) is reported as non-literal and
the dependencies it would have produced stay UNKNOWN: they are never guessed.
"""
import ast

from packaging.requirements import InvalidRequirement, Requirement

from ..common import Dependency, Diagnostic, ManifestError, ManifestResult, SnapshotFS, canonical_name, failed

KEYS = ("install_requires", "extras_require", "python_requires", "name", "version")


def _module_literals(tree: ast.Module) -> dict[str, ast.expr]:
    """Module-level `NAME = <expr>` assignments (only names assigned exactly once)."""
    seen: dict[str, list[ast.expr]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            seen.setdefault(node.targets[0].id, []).append(node.value)
    return {k: v[0] for k, v in seen.items() if len(v) == 1}


def _value(node: ast.expr, names: dict[str, ast.expr], depth: int = 0):
    """The literal value of an expression, or raise ValueError when it is not a literal."""
    if depth > 4:
        raise ValueError("too deeply nested")
    if isinstance(node, ast.Name) and node.id in names:
        return _value(names[node.id], names, depth + 1)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_value(e, names, depth + 1) for e in node.elts]
    if isinstance(node, ast.Dict):
        return {_value(k, names, depth + 1): _value(v, names, depth + 1) for k, v in zip(node.keys, node.values, strict=True) if k is not None}
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _value(node.left, names, depth + 1), _value(node.right, names, depth + 1)
        if isinstance(left, list) and isinstance(right, list):
            return left + right
    return ast.literal_eval(node)


def _setup_call(tree: ast.Module) -> ast.Call | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Name) and f.id == "setup") or (isinstance(f, ast.Attribute) and f.attr == "setup"):
                return node
    return None


def parse_setup_py(fs: SnapshotFS, rel: str) -> ManifestResult:
    try:
        text = fs.read_text(rel)
        tree = ast.parse(text)
    except ManifestError as e:
        return failed("setup_py", rel, e)
    except (SyntaxError, ValueError) as e:
        return failed("setup_py", rel, ManifestError(f"{rel} is not valid Python: {e}", path=rel))
    res = ManifestResult("setup_py", rel)
    call = _setup_call(tree)
    if call is None:
        res.status = "UNSUPPORTED"
        res.add("NO_SETUP_CALL", "no setup(...) call was found; nothing is executed to find out")
        return res
    names = _module_literals(tree)
    got: dict[str, object] = {}
    for kw in call.keywords:
        if kw.arg in KEYS:
            try:
                got[kw.arg] = _value(kw.value, names)
            except (ValueError, TypeError, SyntaxError):
                msg = f"{kw.arg} is computed, not a literal; it is not evaluated (setup.py is never executed)"
                if kw.arg in ("install_requires", "extras_require"):       # dependencies are unknown: the parse is partial
                    res.add("NON_LITERAL_ARGUMENT", msg, kw.value.lineno)
                else:                                                      # name, version or python_requires do not change which packages resolve
                    res.diagnostics.append(Diagnostic("NON_LITERAL_ARGUMENT", msg, res.path, kw.value.lineno))
        elif kw.arg is None:
            res.add("NON_LITERAL_ARGUMENT", "setup(**kwargs) hides its arguments; they are not evaluated", kw.value.lineno)
    res.meta.update(name=got.get("name"), version=got.get("version"), requires_python=got.get("python_requires"), setup_py=True)
    line = {kw.arg: kw.value.lineno for kw in call.keywords if kw.arg}
    res.meta["name_line"] = line.get("name")
    for group, items in [("main", got.get("install_requires") or [])] + [(f"optional:{k}", v) for k, v in (got.get("extras_require") or {}).items()]:
        if not isinstance(items, list):
            continue
        for text_req in items:
            try:
                r = Requirement(str(text_req))
            except InvalidRequirement as e:
                res.add("UNPARSEABLE_REQUIREMENT", f"cannot parse {str(text_req)[:80]!r}: {e}")
                continue
            res.dependencies.append(Dependency(canonical_name(r.name), r.name, str(r.specifier), tuple(sorted(r.extras)),
                                               str(r.marker) if r.marker else None, "registry", None, group, rel,
                                               line.get("install_requires") if group == "main" else line.get("extras_require")))
    return res
