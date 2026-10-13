"""npm project discovery from the snapshot inventory. Reads package.json files as data; runs nothing."""
import posixpath
import re
from dataclasses import dataclass, field

from ...ingestion.classify import classify
from ..common import SnapshotFS
from .package_json import PackageJson, parse_package_json


@dataclass
class NpmProject:
    rel_path: str                                   # '.' or 'apps/web'
    name: str | None
    package_json: PackageJson
    lockfile: str | None                            # snapshot path of package-lock.json / npm-shrinkwrap.json
    workspace_dirs: list[str] = field(default_factory=list)       # member directories relative to the snapshot root
    notes: list[str] = field(default_factory=list)

    @property
    def manifests(self) -> dict[str, list[str]]:
        out = {"package_json": [self.package_json.path]}
        if self.lockfile:
            out["package_lock"] = [self.lockfile]
        return out


def _glob_re(pattern: str) -> re.Pattern:
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile("^" + out + "$")


def workspace_members(root_dir: str, patterns: list[str], package_dirs: set[str]) -> list[str]:
    inc = [_glob_re(posixpath.normpath(posixpath.join(root_dir, p))) for p in patterns if not p.startswith("!")]
    exc = [_glob_re(posixpath.normpath(posixpath.join(root_dir, p[1:]))) for p in patterns if p.startswith("!")]
    return sorted(d for d in package_dirs if d != root_dir and any(r.match(d) for r in inc) and not any(r.match(d) for r in exc))


def discover_npm(snapshot, inventory: dict) -> list[NpmProject]:
    fs = SnapshotFS(snapshot)
    files = [e["path"] for e in inventory["entries"] if e["kind"] in ("file", "lfs_pointer")]
    usable = {p for p in files if classify(p).role != "ignored" and "VENDORED" not in classify(p).tags}
    pj_paths = sorted(p for p in usable if posixpath.basename(p) == "package.json")
    dirs = {(posixpath.dirname(p) or "."): p for p in pj_paths}
    parsed = {d: parse_package_json(fs, p) for d, p in dirs.items()}
    owned: set[str] = set()
    projects: list[NpmProject] = []
    for d in sorted(dirs, key=lambda x: (x.count("/"), x)):
        if d in owned:
            continue
        pj = parsed[d]
        members = workspace_members(d, pj.workspaces, set(dirs)) if pj.workspaces else []
        owned.update(members)
        lock = next((posixpath.join(d, n) if d != "." else n for n in ("package-lock.json", "npm-shrinkwrap.json")
                     if (posixpath.join(d, n) if d != "." else n) in usable), None)
        notes = []
        if pj.install_hooks:
            notes.append(f"declares lifecycle scripts ({', '.join(pj.install_hooks)}); they are never run")
        if pj.workspaces and not members:
            notes.append("declares workspaces but no member package.json matched")
        projects.append(NpmProject(d, pj.name, pj, lock, members, notes))
    return projects
