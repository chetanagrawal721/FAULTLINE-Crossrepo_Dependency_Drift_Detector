"""Maven POM inventory. Coordinates, direct dependencies, same-POM properties and in-repository parents, read with a
hardened XML parser (DTDs, entities and external references are refused). Maven is never run and nothing is resolved:
a version that cannot be established from the repository itself stays unresolved, it is never guessed."""
import posixpath
import re
from dataclasses import dataclass, field

import defusedxml.ElementTree as SafeET
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError

from ..common import ManifestError, PathEscape, SnapshotFS

MAX_ELEMENTS = 200_000
MAX_DEPTH = 64
MAX_INTERPOLATION_DEPTH = 10
PROP = re.compile(r"\$\{([^}]+)\}")


@dataclass
class PomDependency:
    group_id: str
    artifact_id: str
    version: str | None               # None: unresolved (see `note`)
    scope: str = "compile"
    type: str = "jar"
    classifier: str | None = None
    optional: bool = False
    version_source: str = "declared"  # declared | property | managed | unresolved
    note: str | None = None


@dataclass
class PomModel:
    path: str
    status: str = "OK"                # OK | PARTIAL | FAILED | TOO_LARGE
    group_id: str | None = None
    artifact_id: str | None = None
    version: str | None = None
    packaging: str = "jar"
    parent: dict | None = None        # {group_id, artifact_id, version, relative_path, found_in_repository, path}
    modules: list[str] = field(default_factory=list)          # module directories relative to the snapshot root
    properties: dict[str, str] = field(default_factory=dict)  # own properties only
    dependencies: list[PomDependency] = field(default_factory=list)
    managed: dict[str, str] = field(default_factory=dict)     # "g:a" -> version from this POM's dependencyManagement
    diagnostics: list[dict] = field(default_factory=list)
    error: str | None = None

    def diag(self, code: str, message: str) -> None:
        self.diagnostics.append({"code": code, "message": message})
        if self.status == "OK":
            self.status = "PARTIAL"


def _tag(el) -> str:
    return el.tag.split("}")[-1] if isinstance(el.tag, str) else ""


def _child(el, name: str):
    return next((c for c in el if _tag(c) == name), None)


def _text(el, name: str) -> str | None:
    c = _child(el, name)
    return c.text.strip() if c is not None and c.text and c.text.strip() else None


def read_pom(fs: SnapshotFS, rel: str) -> tuple[PomModel, object | None]:
    """Parse one POM into a model with the raw values. Hostile XML is rejected; nothing is read or fetched for it."""
    m = PomModel(rel)
    try:
        text = fs.read_text(rel)
    except ManifestError as e:
        m.status = "TOO_LARGE" if e.code.value == "MANIFEST_TOO_LARGE" else "FAILED"
        m.error = e.message
        return m, None
    try:
        root = SafeET.fromstring(text, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as e:
        m.status, m.error = "FAILED", f"{rel} uses an XML construct that is refused ({type(e).__name__}): DTDs, entities and external references are not allowed"
        return m, None
    except (ParseError, ValueError) as e:
        m.status, m.error = "FAILED", f"{rel} is not well-formed XML: {e}"
        return m, None
    stack, deepest = [(root, 1)], 0
    while stack:                                       # iterative: a hostile document cannot exhaust the Python stack
        el, depth = stack.pop()
        deepest = max(deepest, depth)
        if deepest > MAX_DEPTH:
            m.status, m.error = "FAILED", f"{rel} is nested deeper than {MAX_DEPTH} elements"
            return m, None
        stack.extend((c, depth + 1) for c in el)
    if sum(1 for _ in root.iter()) > MAX_ELEMENTS:
        m.status, m.error = "FAILED", f"{rel} has more than {MAX_ELEMENTS} elements"
        return m, None
    if _tag(root) != "project":
        m.status, m.error = "FAILED", f"{rel} is not a Maven POM (root element {_tag(root)!r})"
        return m, None
    m.group_id, m.artifact_id, m.version = _text(root, "groupId"), _text(root, "artifactId"), _text(root, "version")
    m.packaging = _text(root, "packaging") or "jar"
    par = _child(root, "parent")
    if par is not None:
        m.parent = {"group_id": _text(par, "groupId"), "artifact_id": _text(par, "artifactId"), "version": _text(par, "version"),
                    "relative_path": _text(par, "relativePath") if _child(par, "relativePath") is not None else "../pom.xml",
                    "found_in_repository": False, "path": None}
        m.group_id = m.group_id or m.parent["group_id"]
        m.version = m.version or m.parent["version"]
    props = _child(root, "properties")
    if props is not None:
        m.properties = {_tag(p): (p.text or "").strip() for p in props if _tag(p)}
    mods = _child(root, "modules")
    if mods is not None:
        base = posixpath.dirname(rel)
        for mod in mods:
            if _tag(mod) == "module" and mod.text and mod.text.strip():
                try:
                    m.modules.append(posixpath.normpath(posixpath.join(base, mod.text.strip())) if base else posixpath.normpath(mod.text.strip()))
                except ValueError:
                    m.diag("BAD_MODULE", f"unusable module path {mod.text!r}")
    return m, root


def _deps(container, model: PomModel, managed: bool) -> list[tuple[PomDependency, str | None]]:
    out = []
    for d in container if container is not None else []:
        if _tag(d) != "dependency":
            continue
        g, a = _text(d, "groupId"), _text(d, "artifactId")
        if not g or not a:
            model.diag("BAD_DEPENDENCY", "a dependency without groupId or artifactId was skipped")
            continue
        out.append((PomDependency(g, a, None, _text(d, "scope") or "compile", _text(d, "type") or "jar", _text(d, "classifier"),
                                  (_text(d, "optional") or "").lower() == "true"), _text(d, "version")))
    return out


def interpolate(value: str | None, props: dict[str, str], model: PomModel, what: str, depth: int = 0) -> tuple[str | None, bool]:
    """Resolve ${...} from the properties in scope. Returns (value, fully_resolved). Unknown properties stay raw and are reported."""
    if value is None or "${" not in value:
        return value, True
    if depth >= MAX_INTERPOLATION_DEPTH:
        model.diag("INTERPOLATION_TOO_DEEP", f"{what}: property nesting is deeper than {MAX_INTERPOLATION_DEPTH} (a cycle?)")
        return value, False
    ok = True

    def sub(mt: re.Match) -> str:
        nonlocal ok
        key = mt.group(1)
        if key.startswith(("env.", "settings.", "sys.")) or key in ("basedir", "project.basedir", "project.build.directory"):
            model.diag("UNSUPPORTED_INTERPOLATION", f"{what}: ${{{key}}} depends on the environment and is not evaluated")
            ok = False
            return mt.group(0)
        if key not in props:
            model.diag("UNRESOLVED_PROPERTY", f"{what}: ${{{key}}} is not defined in this repository's POMs")
            ok = False
            return mt.group(0)
        return props[key]

    out = PROP.sub(sub, value)
    if out != value and "${" in out:
        out2, ok2 = interpolate(out, props, model, what, depth + 1)
        return out2, ok and ok2
    return out, ok


def load_pom_tree(fs: SnapshotFS, rel: str, _chain: tuple[str, ...] = (), _cache: dict | None = None) -> tuple[PomModel, dict[str, str], dict[str, str]]:
    """Parse a POM and resolve what the repository itself can answer: in-repo parent chain, properties, managed versions.

    Returns (model, effective_properties, effective_managed_versions). The model's dependencies carry resolved versions or an
    explicit note saying why a version is unknown.
    """
    cache = _cache if _cache is not None else {}
    model, root = read_pom(fs, rel)
    if root is None:
        return model, {}, {}
    props: dict[str, str] = {}
    managed: dict[str, str] = {}
    if model.parent:
        p = model.parent
        ppath = None
        rp = p["relative_path"]
        if rp:                                    # an empty relativePath means: do not look in the repository
            try:
                ppath = SnapshotFS.join(rel, rp if rp.endswith(".xml") else posixpath.join(rp, "pom.xml"))
            except PathEscape:
                model.diag("PATH_ESCAPE", f"parent relativePath {rp!r} leaves the repository and was not followed")
        if ppath and ppath not in _chain and fs.exists(ppath):
            parent, pprops, pmanaged = cache.get(ppath) or load_pom_tree(fs, ppath, (*_chain, rel), cache)
            cache[ppath] = (parent, pprops, pmanaged)
            if parent.artifact_id == p["artifact_id"] and parent.status != "FAILED":
                p.update(found_in_repository=True, path=ppath)
                props.update(pprops)
                managed.update(pmanaged)
                model.group_id = model.group_id or parent.group_id
                model.version = model.version or parent.version
            else:
                model.diag("PARENT_MISMATCH", f"{ppath} is not the declared parent {p['group_id']}:{p['artifact_id']}")
        else:
            model.diag("EXTERNAL_PARENT", f"parent {p['group_id']}:{p['artifact_id']}:{p['version']} is not in this repository; its properties and managed versions are unsupported and left unresolved")
    props.update(model.properties)
    builtin = {"project.groupId": model.group_id, "project.artifactId": model.artifact_id, "project.version": model.version,
               "pom.version": model.version, "version": model.version,
               "project.parent.version": (model.parent or {}).get("version"), "project.parent.groupId": (model.parent or {}).get("group_id")}
    props.update({k: v for k, v in builtin.items() if v})

    dm = _child(root, "dependencyManagement")
    for dep, ver in _deps(_child(dm, "dependencies") if dm is not None else None, model, True):
        if dep.scope == "import" and dep.type == "pom":
            model.diag("EXTERNAL_BOM", f"BOM import {dep.group_id}:{dep.artifact_id} is unsupported; versions it manages are left unresolved")
            continue
        v, ok = interpolate(ver, props, model, f"managed {dep.group_id}:{dep.artifact_id}")
        if v and ok:
            managed[f"{dep.group_id}:{dep.artifact_id}"] = v
    model.managed = {k: v for k, v in managed.items()}

    for dep, ver in _deps(_child(root, "dependencies"), model, False):
        what = f"{dep.group_id}:{dep.artifact_id}"
        key = what
        if ver:
            v, ok = interpolate(ver, props, model, what)
            dep.version, dep.version_source = (v, "property" if "${" in ver else "declared") if ok else (None, "unresolved")
            if not ok:
                dep.note = f"version {ver} could not be resolved from this repository"
        elif key in managed:
            dep.version, dep.version_source = managed[key], "managed"
        else:
            dep.version_source = "unresolved"
            dep.note = ("no version here and no managed version in this repository"
                        + (" (an external parent may manage it)" if model.parent and not model.parent["found_in_repository"] else ""))
        model.dependencies.append(dep)
    return model, props, managed


@dataclass
class MavenProject:
    rel_path: str
    pom: PomModel
    module_of: str | None = None      # rel_path of the aggregator that lists this module
    notes: list[str] = field(default_factory=list)

    @property
    def manifests(self) -> dict[str, list[str]]:
        return {"pom": [self.pom.path]}


def discover_maven(snapshot, inventory: dict) -> list[MavenProject]:
    from ...ingestion.classify import classify
    fs = SnapshotFS(snapshot)
    paths = sorted(e["path"] for e in inventory["entries"] if e["kind"] == "file" and posixpath.basename(e["path"]) == "pom.xml"
                   and classify(e["path"]).role != "ignored" and "VENDORED" not in classify(e["path"]).tags)
    cache: dict = {}
    projects = {}
    for p in paths:
        model, _props, _managed = load_pom_tree(fs, p, (), cache)
        d = posixpath.dirname(p) or "."
        projects[d] = MavenProject(d, model, None, [x["message"] for x in model.diagnostics])
    for d, prj in projects.items():
        for mod in prj.pom.modules:
            child = mod if mod else "."
            if child in projects and child != d:
                projects[child].module_of = d
    return sorted(projects.values(), key=lambda x: x.rel_path)
