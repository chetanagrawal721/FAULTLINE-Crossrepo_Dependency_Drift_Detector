"""World builder: turns a hash-pinned lock into a ResolvedWorld and an offline-built virtualenv volume.

Flow (all execution through SandboxClient):
  1. fetch zone (network): pip download --only-binary --no-deps --require-hashes  -> shared wheelhouse volume
  2. materialize: pair every lock entry with the wheel that was actually downloaded; its sha256 becomes part of
     the world identity
  3. exec zone (NO network): uv venv + uv pip install --offline --require-hashes into volume fl-world-<hash>
  4. reuse: a world already built (DB says BUILT and the volume exists) is not rebuilt, and no container runs.
"""
import sqlite3
from dataclasses import dataclass

from packaging.utils import InvalidWheelFilename, parse_wheel_filename

from ..core.enums import Ecosystem, Scope, VenvStatus, WorldKind
from ..core.errors import ErrorCode, FaultlineError
from ..core.hashing import content_hash, env_profile_id, world_hash
from ..core.models import EnvProfile, ResolvedWorld, Runtime, WorldEntry
from ..resolvers.pinned import PinnedRequirement, canonical_name, parse_pinned_lock
from ..sandbox.client import SandboxClient
from ..storage import worlds as world_store

DEFAULT_RUNTIME = Runtime(name="cpython", version="3.12.15")


class WorldBuildError(FaultlineError):
    code = ErrorCode.WORLD_BUILD_FAILED


@dataclass(frozen=True)
class BuildResult:
    status: str                  # BUILT | REUSED | FAILED
    world_hash: str
    reason: str | None = None


def env_profile_for(image_id: str) -> EnvProfile:
    return EnvProfile(image_ref=image_id, env={"PYTHONHASHSEED": "0", "SOURCE_DATE_EPOCH": "1700000000"})


def lock_digest(lock_text: str) -> str:
    return content_hash(lock_text.encode("utf-8"))


def world_from_lock(reqs: list[PinnedRequirement], wheels: dict[str, str], *, kind: WorldKind, runtime: Runtime,
                    env: EnvProfile, scopes: dict[str, Scope] | None = None) -> ResolvedWorld:
    """wheels: canonical package name -> sha256 of the wheel that was downloaded. scopes: name -> scope (default runtime)."""
    missing = [r.name for r in reqs if r.name not in wheels]
    if missing:
        raise WorldBuildError(f"no wheel was fetched for: {', '.join(missing)}", code=ErrorCode.NO_WHEEL)
    scopes = scopes or {}
    entries = tuple(WorldEntry(locator=r.name, name=r.name, version=r.version, artifact_sha256=wheels[r.name],
                               scope=scopes.get(r.name, Scope.RUNTIME)) for r in reqs)
    env_id = env_profile_id(env)
    draft = {"ecosystem": Ecosystem.PYPI.value, "runtime": runtime.model_dump(mode="json"),
             "env_profile_id": env_id, "entries": entries}
    return ResolvedWorld(world_hash=world_hash(draft), ecosystem=Ecosystem.PYPI, kind=kind, runtime=runtime,
                         env_profile_id=env_id, entries=entries)


def wheels_for(reqs: list[PinnedRequirement], files: list[dict]) -> dict[str, str]:
    """Pick, for each pinned requirement, the one wheel in the wheelhouse listing that matches name and version."""
    by_key: dict[tuple[str, str], list[dict]] = {}
    for f in files:
        try:
            name, version, _build, _tags = parse_wheel_filename(f["name"])
        except InvalidWheelFilename:
            continue
        by_key.setdefault((canonical_name(str(name)), str(version)), []).append(f)
    out: dict[str, str] = {}
    for r in reqs:
        cands = by_key.get((r.name, r.version), [])
        if len(cands) > 1:
            raise WorldBuildError(f"more than one wheel for {r.name}=={r.version} in the wheelhouse",
                                  details={"files": [c["name"] for c in cands]})
        if cands and (not r.hashes or cands[0]["sha256"] in r.hashes):
            out[r.name] = cands[0]["sha256"]
    return out


class WorldBuilder:
    def __init__(self, sandbox: SandboxClient, image_id: str, conn: sqlite3.Connection | None = None,
                 runtime: Runtime = DEFAULT_RUNTIME):
        self.sandbox, self.image, self.conn, self.runtime = sandbox, image_id, conn, runtime
        self.env = env_profile_for(image_id)

    # -- step 1
    def fetch_wheels(self, lock_text: str) -> list[dict]:
        spec = {"image": self.image, "zone": "fetch", "script": "fetch_wheels.py",
                "args": {"lock_text": lock_text}, "limits": {"timeout_s": 300}, "mounts": {"/wheelhouse": {"rw": True}}}
        r = self.sandbox.submit(spec)
        data = r.get("data") or {}
        if r["failure_class"] != "NONE" and not data.get("stderr_tail"):      # an infrastructure failure with no pip output: try once more
            r = self.sandbox.submit(spec)
            data = r.get("data") or {}
        if r["failure_class"] != "NONE" or data.get("returncode") != 0:
            tail = data.get("stderr_tail", r.get("error", ""))
            code = ErrorCode.NO_WHEEL if "No matching distribution" in tail or "only-binary" in tail else ErrorCode.WORLD_BUILD_FAILED
            if "DO NOT MATCH THE HASHES" in tail.upper():
                raise WorldBuildError("a downloaded wheel does not match the hash in the lock", code=ErrorCode.WORLD_BUILD_FAILED,
                                      details={"reason": "hash_mismatch", "tail": tail[-600:]})
            raise WorldBuildError("could not fetch wheels", code=code, details={"tail": tail[-600:], "failure_class": r["failure_class"], "returncode": data.get("returncode")})
        return data["files"]

    # -- step 2
    def materialize(self, lock_text: str, kind: WorldKind = WorldKind.REFERENCE,
                    scopes: dict[str, Scope] | None = None) -> ResolvedWorld:
        reqs = parse_pinned_lock(lock_text)
        files = self.fetch_wheels(lock_text)
        world = world_from_lock(reqs, wheels_for(reqs, files), kind=kind, runtime=self.runtime, env=self.env,
                                scopes=scopes)
        if self.conn is not None:
            world_store.save_world(self.conn, world, self.env)
        return world

    # -- steps 3 and 4
    def build(self, world: ResolvedWorld, lock_text: str) -> BuildResult:
        vol_exists = self.sandbox.volume_exists(world.world_hash)
        if self.conn is not None and vol_exists and world_store.venv_status(self.conn, world.world_hash) == VenvStatus.BUILT:
            return BuildResult("REUSED", world.world_hash)
        if vol_exists:
            self.sandbox.volume_rm(world.world_hash)          # half-built or unrecorded: start clean
        r = self.sandbox.submit({"image": self.image, "zone": "exec", "script": "build_world.py",
                                 "args": {"lock_text": lock_text, "world_hash": world.world_hash,
                                          "lock_sha256": lock_digest(lock_text)},
                                 "limits": {"timeout_s": 300, "memory_mb": 1024},
                                 "mounts": {"/opt/world": {"world": world.world_hash, "rw": True},
                                            "/wheelhouse": {}}})
        data = r.get("data") or {}
        ok = r["failure_class"] == "NONE" and data.get("returncode") == 0
        if not ok:
            self.sandbox.volume_rm(world.world_hash)
            tail = " | ".join(s.get("tail", "") for s in data.get("steps", []) if s.get("returncode"))[-600:] or r.get("error", "")
            if self.conn is not None:
                world_store.set_venv_status(self.conn, world.world_hash, VenvStatus.FAILED)
            return BuildResult("FAILED", world.world_hash, tail or r["failure_class"])
        if self.conn is not None:
            world_store.set_venv_status(self.conn, world.world_hash, VenvStatus.BUILT, f"volume:fl-world-{world.world_hash}")
        return BuildResult("BUILT", world.world_hash)

    def read_metadata(self, wheel_files: list[str]) -> dict:
        """Requires-Dist and Provides-Extra of wheels in the wheelhouse, read offline in the sandbox (no wheel code runs)."""
        r = self.sandbox.submit({"image": self.image, "zone": "exec", "script": "wheel_metadata.py", "args": {"files": wheel_files},
                                 "mounts": {"/wheelhouse": {}}})
        data = r.get("data") or {}
        if r["failure_class"] != "NONE" or "metadata" not in data:
            raise WorldBuildError("could not read wheel metadata", details={"tail": r.get("error", "")})
        return data["metadata"]

    def edges(self, pinned: list[PinnedRequirement]) -> dict[str, list[str]]:
        """Dependency edges of a pinned world, from the wheels' own metadata."""
        from .closure import fetch_edges
        return fetch_edges(lambda text: self.fetch_wheels(text), self.read_metadata, pinned)

    def info(self, world: ResolvedWorld) -> dict:
        """What the built world really contains, read in a fresh read-only container."""
        r = self.sandbox.submit({"image": self.image, "zone": "exec", "script": "world_info.py",
                                 "mounts": {"/opt/world": {"world": world.world_hash}}})
        data = r.get("data") or {}
        if r["failure_class"] != "NONE" or data.get("returncode") != 0 or not data.get("info"):
            raise WorldBuildError("could not inspect the built world", details={"tail": data.get("stderr_tail", "")})
        return data
