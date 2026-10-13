"""npm worlds from a committed package-lock.json. Inventory only: nothing is installed or executed, and no runtime claim
is made. Every package instance is a world entry keyed by its node_modules path; visibility is computed per importer."""
from dataclasses import dataclass, field

from ..core.enums import Ecosystem, Scope, SourceKind, WorldKind
from ..core.hashing import env_profile_id, world_hash
from ..core.models import EnvProfile, ResolvedWorld, Runtime, WorldEntry
from ..parsers.common import SnapshotFS
from ..parsers.npm.discover import NpmProject
from ..parsers.npm.package_lock import NpmLock, parse_package_lock
from .visibility import importer_visibility

INVENTORY_ENV = EnvProfile(image_ref="inventory-only")          # no execution environment: this world is never run
INVENTORY_RUNTIME = Runtime(name="node", version="unspecified")  # no runtime claim for npm


@dataclass
class VisibilityRow:
    importer: str                     # locator of the importing package ('' is the project root)
    name: str                         # the dependency name as the importer requires it
    locator: str | None               # the instance it resolves to; None when the lockfile cannot satisfy it
    version: str | None


@dataclass
class NpmOutcome:
    status: str                       # OK | FAILED
    world: ResolvedWorld | None = None
    lock: NpmLock | None = None
    visibility: list[VisibilityRow] = field(default_factory=list)
    failure: dict | None = None
    warnings: list[str] = field(default_factory=list)
    importers: list[str] = field(default_factory=list)


def _failed(reason: str, detail: str, lock: NpmLock | None = None) -> NpmOutcome:
    return NpmOutcome("FAILED", None, lock, failure={"code": "RESOLUTION_FAILED", "reason": reason, "detail": detail})


def resolve_npm_project(fs: SnapshotFS, project: NpmProject) -> NpmOutcome:
    if project.package_json.status in ("FAILED", "TOO_LARGE"):
        return _failed("package_json_unreadable", project.package_json.error or "")
    if not project.lockfile:
        return _failed("no_lockfile", "no package-lock.json: Faultline does not run npm install, so the dependency tree is unknown")
    lock = parse_package_lock(fs, project.lockfile)
    if lock.status != "OK":
        return _failed(f"lock_{lock.status.lower()}", lock.error or "", lock)
    root = lock.instances[""]
    declared = {*project.package_json.dependencies, *project.package_json.dev_dependencies, *project.package_json.optional_dependencies}
    in_lock = {n for n, _ in (*root.dependencies, *root.dev_dependencies, *root.peer_dependencies)}
    stale = sorted(declared - in_lock) if root.dependencies or declared else []
    if stale and not project.package_json.workspaces:
        return _failed("lock_out_of_sync", f"declared in package.json but absent from the lockfile root: {', '.join(stale)}", lock)

    entries: list[WorldEntry] = []
    for loc, inst in sorted(lock.instances.items()):
        if loc == "" or inst.link_target is not None:
            continue
        scope = {"dev": Scope.DEV, "optional": Scope.OPTIONAL, "peer": Scope.PEER}.get(inst.scope, Scope.RUNTIME)
        ref = (inst.resolved or "") + (f"#{inst.integrity}" if inst.integrity else "") or None
        entries.append(WorldEntry(locator=loc, name=inst.name, version=inst.version or "", scope=scope,
                                  source_kind=SourceKind(inst.source_kind), source_ref=ref))
    env_id = env_profile_id(INVENTORY_ENV)
    draft = {"ecosystem": Ecosystem.NPM.value, "runtime": INVENTORY_RUNTIME.model_dump(mode="json"), "env_profile_id": env_id,
             "entries": tuple(entries)}
    world = ResolvedWorld(world_hash=world_hash(draft), ecosystem=Ecosystem.NPM, kind=WorldKind.REFERENCE, runtime=INVENTORY_RUNTIME,
                          env_profile_id=env_id, entries=tuple(entries))
    rows: list[VisibilityRow] = []
    for loc in sorted(lock.instances):
        if lock.instances[loc].link_target is not None:
            continue
        for name, inst in importer_visibility(lock.instances, loc).items():
            rows.append(VisibilityRow(loc, name, inst.locator if inst else None, inst.version if inst else None))
    warnings = [f"{i.locator or '(root)'} has install scripts: they are never run" for i in lock.instances.values() if i.has_install_script]
    unresolved = [r for r in rows if r.locator is None and r.importer == ""]
    warnings += [f"the root requires {r.name}, which the lockfile does not provide" for r in unresolved]
    importers = [""] + sorted(i.locator for i in lock.instances.values() if i.is_workspace)
    return NpmOutcome("OK", world, lock, rows, None, warnings, importers)
