"""The ONLY place identity hashes are computed.

Rules (enforced by tests/unit/test_hash_policy.py):
  * canonical JSON: UTF-8, sorted keys, no whitespace, no NaN or Infinity, integers stay integers;
  * world identity covers semantic dimensions only: ecosystem, runtime, environment profile, and for every
    entry the locator, name, version, scope, source kind and reference, and artifact hash;
  * world identity never includes absolute paths, timestamps, provenance, venv location or the
    `parents` reason edges. Nested npm instances stay distinct because the locator is part of identity.
"""
import hashlib
import json
import math
from typing import Any

from .errors import CanonicalizationError
from .models import EnvProfile, ResolvedWorld, WorldEntry


def _check(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise CanonicalizationError(f"non-finite number at {path}", details={"path": path})
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise CanonicalizationError(f"non-string key at {path}", details={"path": path})
            _check(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check(v, f"{path}[{i}]")
    elif isinstance(obj, (str, int, bool)) or obj is None:
        return
    else:
        raise CanonicalizationError(f"unsupported type {type(obj).__name__} at {path}", details={"path": path})


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON bytes. Raises CanonicalizationError for NaN, Infinity and unsupported types."""
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(data: bytes) -> str:
    """Hash of raw bytes (files, blobs)."""
    return sha256_hex(data)


def object_hash(obj: Any) -> str:
    """Hash of any canonicalizable JSON-like object."""
    return sha256_hex(canonical_json(obj))


def env_profile_id(profile: EnvProfile) -> str:
    return "ep_" + object_hash(profile.model_dump(mode="json"))[:32]


def _entry_identity(e: WorldEntry) -> dict:
    return {
        "locator": e.locator,
        "name": e.name,
        "version": e.version,
        "scope": e.scope.value,
        "source_kind": e.source_kind.value,
        "source_ref": e.source_ref,
        "artifact_sha256": e.artifact_sha256,
    }


def world_hash(world: ResolvedWorld | dict) -> str:
    """Identity of a world. Accepts a ResolvedWorld or an equivalent dict (extra non-semantic keys ignored)."""
    if isinstance(world, dict):
        w = world
        entries = [WorldEntry.model_validate(e) if isinstance(e, dict) else e for e in w["entries"]]
        runtime = w["runtime"] if isinstance(w["runtime"], dict) else w["runtime"].model_dump(mode="json")
        ecosystem = getattr(w["ecosystem"], "value", w["ecosystem"])
        env_id = w["env_profile_id"]
    else:
        entries = list(world.entries)
        runtime = world.runtime.model_dump(mode="json")
        ecosystem = world.ecosystem.value
        env_id = world.env_profile_id
    identity = {
        "ecosystem": ecosystem,
        "runtime": {"name": runtime["name"], "version": runtime["version"]},
        "env_profile_id": env_id,
        "entries": sorted((_entry_identity(e) for e in entries),
                          key=lambda d: (d["locator"], d["name"], d["version"])),
    }
    return "w_" + object_hash(identity)[:40]
