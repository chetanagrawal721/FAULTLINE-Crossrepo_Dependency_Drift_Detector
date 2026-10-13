"""package.json reader. Scripts are recorded by name only and are never run."""
import json
from dataclasses import dataclass, field

from ..common import ManifestError, SnapshotFS, failed

INSTALL_HOOKS = ("preinstall", "install", "postinstall", "prepare", "prepublish", "prepack")


@dataclass
class PackageJson:
    path: str
    status: str = "OK"                     # OK | PARTIAL | FAILED | TOO_LARGE
    name: str | None = None
    version: str | None = None
    private: bool = False
    dependencies: dict[str, str] = field(default_factory=dict)
    dev_dependencies: dict[str, str] = field(default_factory=dict)
    optional_dependencies: dict[str, str] = field(default_factory=dict)
    peer_dependencies: dict[str, str] = field(default_factory=dict)
    workspaces: list[str] = field(default_factory=list)
    engines: dict[str, str] = field(default_factory=dict)
    script_names: list[str] = field(default_factory=list)
    install_hooks: list[str] = field(default_factory=list)      # lifecycle scripts that would run on install; NEVER executed
    diagnostics: list[str] = field(default_factory=list)
    error: str | None = None


def _deps(data: dict, key: str, out: PackageJson) -> dict[str, str]:
    v = data.get(key, {})
    if not isinstance(v, dict) or any(not isinstance(k, str) or not isinstance(x, str) for k, x in v.items()):
        out.diagnostics.append(f"{key} is not a name-to-range object; ignored")
        out.status = "PARTIAL"
        return {}
    return dict(v)


def parse_package_json(fs: SnapshotFS, rel: str) -> PackageJson:
    out = PackageJson(rel)
    try:
        data = json.loads(fs.read_text(rel))
    except ManifestError as e:
        r = failed("package_json", rel, e)
        out.status, out.error = r.status, r.diagnostics[0].message
        return out
    except ValueError as e:
        out.status, out.error = "FAILED", f"{rel} is not valid JSON: {e}"
        return out
    if not isinstance(data, dict):
        out.status, out.error = "FAILED", f"{rel} is not a JSON object"
        return out
    out.name = data.get("name") if isinstance(data.get("name"), str) else None
    out.version = data.get("version") if isinstance(data.get("version"), str) else None
    out.private = bool(data.get("private"))
    out.dependencies = _deps(data, "dependencies", out)
    out.dev_dependencies = _deps(data, "devDependencies", out)
    out.optional_dependencies = _deps(data, "optionalDependencies", out)
    out.peer_dependencies = _deps(data, "peerDependencies", out)
    ws = data.get("workspaces", [])
    if isinstance(ws, dict):
        ws = ws.get("packages", [])
    out.workspaces = [w for w in ws if isinstance(w, str)] if isinstance(ws, list) else []
    if isinstance(data.get("engines"), dict):
        out.engines = {k: v for k, v in data["engines"].items() if isinstance(v, str)}
    scripts = data.get("scripts", {}) if isinstance(data.get("scripts"), dict) else {}
    out.script_names = sorted(scripts)
    out.install_hooks = [h for h in INSTALL_HOOKS if h in scripts]
    return out
