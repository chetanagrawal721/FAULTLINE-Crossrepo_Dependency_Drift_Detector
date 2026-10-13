"""package-lock.json (lockfileVersion 2 and 3). Every package INSTANCE is kept at its node_modules path: two versions of the
same package are two instances. Lockfile v1 and unknown versions are unsupported, never a partial result."""
import json
import re
from dataclasses import dataclass, field

from ..common import ManifestError, SnapshotFS

SUPPORTED_LOCKFILE_VERSIONS = (2, 3)
PUBLIC_REGISTRY_HOSTS = ("registry.npmjs.org", "registry.yarnpkg.com")


@dataclass(frozen=True)
class NpmInstance:
    locator: str                      # "" for the root, "node_modules/a/node_modules/b", or a workspace directory
    name: str
    version: str | None
    resolved: str | None
    integrity: str | None
    source_kind: str                  # registry | git | path | url | private
    scope: str                        # runtime | dev | optional | peer
    link_target: str | None = None    # set when this entry is a link to a workspace directory
    is_workspace: bool = False
    dependencies: tuple[tuple[str, str], ...] = ()          # (name, range) the package itself requires (incl. optional)
    peer_dependencies: tuple[tuple[str, str], ...] = ()
    dev_dependencies: tuple[tuple[str, str], ...] = ()      # only the root and workspace members carry devDependencies in a lockfile
    has_install_script: bool = False


@dataclass
class NpmLock:
    path: str
    status: str = "OK"                # OK | FAILED | TOO_LARGE | UNSUPPORTED
    lockfile_version: int | None = None
    instances: dict[str, NpmInstance] = field(default_factory=dict)
    error: str | None = None


def name_from_locator(locator: str) -> str:
    """The package name of an instance: what follows the LAST node_modules/ (scoped names keep their scope)."""
    return locator.rsplit("node_modules/", 1)[-1]


def classify_source(resolved: str | None, link: bool) -> str:
    if link:
        return "path"
    if not resolved:
        return "registry"
    if resolved.startswith(("git+", "git://", "github:", "git@")) or re.match(r"^https?://[^/]+/[^/]+/[^/]+\.git(#|$)", resolved):
        return "git"
    if resolved.startswith(("file:", "./", "../")):
        return "path"
    m = re.match(r"^https?://([^/:]+)", resolved)
    if m:
        return "registry" if m.group(1).lower() in PUBLIC_REGISTRY_HOSTS else "private"
    return "url"


def parse_package_lock(fs: SnapshotFS, rel: str) -> NpmLock:
    out = NpmLock(rel)
    try:
        data = json.loads(fs.read_text(rel))
    except ManifestError as e:
        out.status = "TOO_LARGE" if e.code.value == "MANIFEST_TOO_LARGE" else "FAILED"
        out.error = e.message
        return out
    except ValueError as e:
        out.status, out.error = "FAILED", f"{rel} is not valid JSON: {e}"
        return out
    if not isinstance(data, dict):
        out.status, out.error = "FAILED", f"{rel} is not a JSON object"
        return out
    ver = data.get("lockfileVersion")
    out.lockfile_version = ver if isinstance(ver, int) else None
    if ver not in SUPPORTED_LOCKFILE_VERSIONS:
        out.status = "UNSUPPORTED"
        out.error = f"lockfileVersion {ver!r} is not supported (supported: {list(SUPPORTED_LOCKFILE_VERSIONS)}); no partial result is produced"
        return out
    pkgs = data.get("packages")
    if not isinstance(pkgs, dict) or "" not in pkgs:
        out.status, out.error = "FAILED", "lockfile has no packages map with a root entry"
        return out
    for key, e in pkgs.items():
        if not isinstance(key, str) or not isinstance(e, dict):
            out.status, out.error = "FAILED", f"malformed package entry {key!r}"
            out.instances = {}
            return out
        link = bool(e.get("link"))
        in_nm = "node_modules/" in key or key.startswith("node_modules")
        is_ws = key != "" and not in_nm and not link
        name = e.get("name") if isinstance(e.get("name"), str) else (name_from_locator(key) if in_nm else key.rsplit("/", 1)[-1])
        if key == "":
            name = e.get("name") or "(root)"
        if not link and key != "" and not is_ws and not isinstance(e.get("version"), str):     # workspace members may be unversioned
            out.status, out.error = "FAILED", f"package {key!r} has no version"
            out.instances = {}
            return out
        scope = "dev" if e.get("dev") else "optional" if e.get("optional") else "peer" if e.get("peer") else "runtime"
        deps = {**(e.get("dependencies") or {}), **(e.get("optionalDependencies") or {})}
        peers = e.get("peerDependencies") or {}
        out.instances[key] = NpmInstance(
            locator=key, name=name, version=e.get("version"), resolved=e.get("resolved"), integrity=e.get("integrity"),
            source_kind=classify_source(e.get("resolved"), link) if key != "" else "path", scope=scope,
            link_target=e.get("resolved") if link else None, is_workspace=is_ws,
            dependencies=tuple(sorted((str(k), str(v)) for k, v in deps.items())),
            peer_dependencies=tuple(sorted((str(k), str(v)) for k, v in peers.items())),
            dev_dependencies=tuple(sorted((str(k), str(v)) for k, v in (e.get("devDependencies") or {}).items())),
            has_install_script=bool(e.get("hasInstallScript")))
    return out
