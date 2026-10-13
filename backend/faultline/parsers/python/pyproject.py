"""pyproject.toml parser: PEP 621, PEP 735 dependency groups, and Poetry. Reads TOML only; never runs a build backend."""
import dataclasses
import re
import tomllib

from packaging.requirements import InvalidRequirement, Requirement

from ..common import Dependency, ManifestError, ManifestResult, SnapshotFS, canonical_name, failed

VCS = ("git+", "hg+", "svn+", "bzr+")


def _req(res: ManifestResult, text: str, group: str, origin: str) -> Dependency | None:
    try:
        r = Requirement(text)
    except InvalidRequirement as e:
        res.add("UNPARSEABLE_REQUIREMENT", f"cannot parse {text[:80]!r}: {e}", None, origin)
        return None
    kind, ref = "registry", None
    if r.url:
        kind = "vcs" if r.url.startswith(VCS) else ("path" if r.url.startswith("file:") else "url")
        ref = r.url
    return Dependency(canonical_name(r.name), r.name, str(r.specifier), tuple(sorted(r.extras)),
                      str(r.marker) if r.marker else None, kind, ref, group, origin)


# ------------------------------------------------------------------------------------------------ Poetry versions

def _nums(v: str) -> list[int]:
    parts = re.match(r"^\s*(\d+(?:\.\d+)*)", v)
    return [int(x) for x in parts.group(1).split(".")] if parts else []


def _join(p: list[int]) -> str:
    return ".".join(str(x) for x in p)


def poetry_specifier(spec: str) -> str:
    """Translate a Poetry constraint to a PEP 440 specifier. Caret and tilde follow Poetry's documented rules."""
    spec = spec.strip()
    if spec in ("", "*"):
        return ""
    out = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = re.match(r"^(\^|~(?!=)|~=|==|!=|>=|<=|>|<|=)?\s*(\d[\w.*+!-]*)$", part)
        if not m:
            raise ValueError(f"unsupported Poetry constraint {part!r}")
        op, ver = m.group(1) or "", m.group(2)
        n = _nums(ver)
        if op == "^":
            if not n:
                raise ValueError(f"bad caret version {ver!r}")
            i = next((k for k, x in enumerate(n) if x), len(n) - 1)
            upper = n[: i] + [n[i] + 1]
            out += [f">={ver}", f"<{_join(upper)}"]
        elif op == "~":
            upper = [n[0] + 1] if len(n) == 1 else [n[0], n[1] + 1]
            out += [f">={ver}", f"<{_join(upper)}"]
        elif op in ("", "="):
            out.append(f"=={ver}")
        else:
            out.append(f"{op}{ver}")
    return ",".join(out)


def _poetry_dep(res: ManifestResult, name: str, val, group: str, origin: str) -> list[Dependency]:
    if name.lower() == "python":
        return []
    items = val if isinstance(val, list) else [val]
    out = []
    for item in items:
        try:
            if isinstance(item, str):
                out.append(Dependency(canonical_name(name), name, poetry_specifier(item), (), None, "registry", None, group, origin))
                continue
            kind, ref, spec = "registry", None, ""
            if "git" in item:
                kind, ref = "vcs", "git+" + item["git"] + (f"@{item.get('rev') or item.get('tag') or item.get('branch')}" if any(k in item for k in ("rev", "tag", "branch")) else "")
            elif "url" in item:
                kind, ref = "url", item["url"]
            elif "path" in item:
                kind, ref = "path", item["path"]
            else:
                spec = poetry_specifier(item.get("version", "*"))
            markers = []
            if item.get("markers"):
                markers.append(f"({item['markers']})")
            if item.get("python"):
                for c in poetry_specifier(item["python"]).split(","):
                    m = re.match(r"^(>=|<=|==|!=|>|<)(.+)$", c)
                    if m:
                        var = "python_full_version" if m.group(2).count(".") >= 2 else "python_version"
                        markers.append(f"{var} {m.group(1)} '{m.group(2)}'")
            out.append(Dependency(canonical_name(name), name, spec, tuple(sorted(item.get("extras", []))),
                                  " and ".join(markers) or None, kind, ref,
                                  f"optional:{name}" if item.get("optional") and group == "main" else group, origin))
        except (ValueError, TypeError) as e:
            res.add("UNSUPPORTED_POETRY_CONSTRAINT", f"{name}: {e}", None, origin)
    return out


def _poetry(res: ManifestResult, data: dict, origin: str) -> None:
    poetry = data.get("tool", {}).get("poetry")
    if not isinstance(poetry, dict):
        return
    res.meta["poetry"] = True
    res.meta.setdefault("name", poetry.get("name"))
    res.meta.setdefault("version", poetry.get("version"))
    deps = poetry.get("dependencies", {})
    if "python" in deps and isinstance(deps["python"], str):
        try:
            res.meta["requires_python"] = poetry_specifier(deps["python"])
        except ValueError as e:
            res.add("UNSUPPORTED_POETRY_CONSTRAINT", f"python: {e}", None, origin)
    for n, v in deps.items():
        res.dependencies += _poetry_dep(res, n, v, "main", origin)
    for n, v in poetry.get("dev-dependencies", {}).items():
        res.dependencies += _poetry_dep(res, n, v, "group:dev", origin)
    for g, body in poetry.get("group", {}).items():
        for n, v in body.get("dependencies", {}).items():
            res.dependencies += _poetry_dep(res, n, v, f"group:{g}", origin)
    for s in poetry.get("source", []):
        if isinstance(s, dict) and s.get("url"):
            res.meta.setdefault("index_urls", []).append({"name": s.get("name"), "url": s["url"], "priority": s.get("priority", "primary")})
    if "packages" in poetry:
        res.meta["packages"] = poetry["packages"]


def _groups(res: ManifestResult, groups: dict, origin: str) -> None:
    """PEP 735 [dependency-groups], with include-group expanded and cycles reported."""
    def expand(name: str, chain: tuple[str, ...]) -> list[Dependency]:
        if name in chain:
            res.add("INCLUDE_CYCLE", f"dependency group cycle: {' -> '.join((*chain, name))}", None, origin)
            return []
        out: list[Dependency] = []
        for item in groups.get(name, []):
            if isinstance(item, str):
                d = _req(res, item, f"group:{name}", origin)
                if d:
                    out.append(d)
            elif isinstance(item, dict) and "include-group" in item:
                inc = item["include-group"]
                if inc not in groups:
                    res.add("INCLUDE_MISSING", f"dependency group {inc!r} is not defined", None, origin)
                    continue
                out += [Dependency(**{**d.__dict__, "group": f"group:{name}"}) for d in expand(inc, (*chain, name))]
            else:
                res.add("UNSUPPORTED_GROUP_ITEM", f"unsupported dependency-group item in {name!r}", None, origin)
        return out

    for g in groups:
        res.dependencies += expand(g, ())


def _line_finder(text: str):
    """Locate the source line of a dependency (a quoted requirement in an array, or a Poetry `name = ...` key) so every
    relationship and finding can point at a file and a line. Matches are consumed in order for repeated names."""
    lines = text.splitlines()
    used: dict[str, int] = {}

    def find(display: str) -> int | None:
        lit = re.compile(r"""["']\s*""" + re.escape(display) + r"""(?![A-Za-z0-9_-])(?![.][A-Za-z0-9])""", re.I)
        key = re.compile(r"""^\s*["']?""" + re.escape(display) + r"""["']?\s*=""", re.I)
        skip = used.get(display.lower(), 0)
        hits = [i + 1 for i, ln in enumerate(lines) if lit.search(ln) or key.match(ln)]
        used[display.lower()] = skip + 1
        return hits[skip] if skip < len(hits) else (hits[-1] if hits else None)
    return find


def _name_line(text: str) -> int | None:
    section = None
    for i, ln in enumerate(text.splitlines(), 1):
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", ln)
        if m:
            section = m.group(1).strip()
        elif section in ("project", "tool.poetry") and re.match(r"^\s*name\s*=", ln):
            return i
    return None


def parse_pyproject(fs: SnapshotFS, rel: str) -> ManifestResult:
    try:
        text = fs.read_text(rel)
        data = tomllib.loads(text)
    except ManifestError as e:
        return failed("pyproject", rel, e)
    except tomllib.TOMLDecodeError as e:
        return failed("pyproject", rel, ManifestError(f"{rel} is not valid TOML: {e}", path=rel))
    res = ManifestResult("pyproject", rel)
    proj = data.get("project")
    if isinstance(proj, dict):
        res.meta.update(name=proj.get("name"), version=proj.get("version"), requires_python=proj.get("requires-python"),
                        dynamic=proj.get("dynamic", []))
        if "dependencies" in proj.get("dynamic", []):
            res.add("DYNAMIC_DEPENDENCIES", "dependencies are declared dynamic; they cannot be read without running the build backend")
        for t in proj.get("dependencies", []):
            d = _req(res, t, "main", rel)
            if d:
                res.dependencies.append(d)
        for extra, items in proj.get("optional-dependencies", {}).items():
            for t in items:
                d = _req(res, t, f"optional:{extra}", rel)
                if d:
                    res.dependencies.append(d)
    if isinstance(data.get("dependency-groups"), dict):
        _groups(res, data["dependency-groups"], rel)
    _poetry(res, data, rel)
    br = data.get("build-system", {})
    res.meta["build_requires"] = list(br.get("requires", []))
    res.meta["build_backend"] = br.get("build-backend")
    uv = data.get("tool", {}).get("uv", {})
    idx = [*uv.get("index", []), *([{"url": u} for u in [uv["index-url"]]] if uv.get("index-url") else []),
           *([{"url": u} for u in uv.get("extra-index-url", [])])]
    for i in idx:
        if isinstance(i, dict) and i.get("url"):
            res.meta.setdefault("index_urls", []).append({"name": i.get("name"), "url": i["url"], "priority": "default" if i.get("default") else "primary"})
    if not isinstance(proj, dict) and "poetry" not in res.meta:
        res.status = "UNSUPPORTED"
        res.add("NO_PROJECT_TABLE", "pyproject.toml has neither [project] nor [tool.poetry]; no dependencies are declared here")
        res.status = "UNSUPPORTED"
    res.meta["tool"] = sorted(data.get("tool", {}).keys())
    find = _line_finder(text)
    res.dependencies = [d if d.line else dataclasses.replace(d, line=find(d.display)) for d in res.dependencies]
    res.meta["name_line"] = _name_line(text)
    return res
