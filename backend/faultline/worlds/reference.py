"""The reference world: what the shared artifact experiences with its OWN dependencies.

Taken from the artifact project's recorded resolution (its lockfile if it has one, else the resolver at the artifact's commit
time). If that baseline is missing, unsupported, unreproducible or incomplete, the answer is INCONCLUSIVE with the reason:
never a clean result and never something blamed on a consumer.
"""
import json
import sqlite3
from dataclasses import dataclass, field

from ..resolvers.pinned import PinnedRequirement

# resolution failure reason -> the plain-language category shown to the user
REASON_TEXT = {
    "no_manifest": "the artifact has no dependency manifest or lockfile, so its own world is unknown",
    "no_declared_dependencies": "the artifact declares no resolvable dependencies",
    "needs_build": "a dependency has no wheel for the target platform and building is not allowed",
    "private_index_without_lock": "the artifact uses a private index without a lockfile; Faultline will not guess",
    "non_registry_source": "a dependency comes from git, a URL or a path, which the resolver does not support",
    "setup_py_not_executed": "the artifact declares dependencies only in setup.py, which is never executed",
    "lock_unsupported": "the artifact's lockfile format is not supported",
    "lock_failed": "the artifact's lockfile could not be read",
    "lock_missing_declared": "the artifact's lockfile is out of date with its manifest",
    "unsatisfiable": "the artifact's own requirements cannot be satisfied",
    "network": "the baseline could not be resolved because the network failed",
}


@dataclass(frozen=True)
class ReferenceWorld:
    project_id: str
    world_hash: str
    pinned: tuple[PinnedRequirement, ...]
    source: str                      # lockfile | resolver
    provenance: dict = field(default_factory=dict)

    @property
    def versions(self) -> dict[str, str]:
        return {p.name: p.version for p in self.pinned}


@dataclass(frozen=True)
class ReferenceFailure:
    reason: str
    text: str
    provenance: dict = field(default_factory=dict)


def select_reference(conn: sqlite3.Connection, artifact_project_id: str) -> ReferenceWorld | ReferenceFailure:
    pw = conn.execute("SELECT * FROM project_world WHERE project_id=? ORDER BY resolved_at DESC LIMIT 1", (artifact_project_id,)).fetchone()
    if pw is None:
        return ReferenceFailure("not_resolved", "the artifact's world has not been resolved yet")
    args = json.loads(pw["resolver_args_json"] or "{}")
    cache = conn.execute("SELECT outcome_json FROM resolution_cache WHERE cache_key=?", (args.get("cache_key"),)).fetchone()
    outcome = json.loads(cache["outcome_json"]) if cache else {}
    prov = {"source": pw["source"], "resolver": pw["resolver"], "cutoff": pw["resolved_at"], **(outcome.get("provenance") or {})}
    if pw["status"] == "FAILED" or not pw["world_hash"]:
        failure = json.loads(pw["failure_json"]) if pw["failure_json"] else {}
        reason = failure.get("reason", "unknown")
        return ReferenceFailure(reason, REASON_TEXT.get(reason, failure.get("detail") or "the baseline failed"), {**prov, "failure": failure})
    if pw["status"] == "OK_PARTIAL":
        return ReferenceFailure("private_packages", "the artifact's baseline includes private packages that are never fetched",
                                {**prov, "private": outcome.get("private", [])})
    pinned = tuple(PinnedRequirement(n, dn, v, tuple(h)) for n, dn, v, h in outcome.get("pinned", []))
    if not pinned:
        return ReferenceFailure("empty_world", "the artifact's baseline contains no packages", prov)
    return ReferenceWorld(artifact_project_id, pw["world_hash"], pinned, pw["source"], prov)
