"""Persistence for resolved worlds (tables resolved_world, world_entry, package_version, env_profile)."""
import json
import sqlite3

from ..core.enums import Ecosystem, VenvStatus
from ..core.hashing import object_hash
from ..core.models import EnvProfile, ResolvedWorld


def package_version_id(ecosystem: Ecosystem | str, name: str, version: str) -> str:
    eco = getattr(ecosystem, "value", ecosystem)
    return object_hash({"eco": eco, "name": name, "version": version})


def save_env_profile(conn: sqlite3.Connection, env_id: str, env: EnvProfile) -> None:
    conn.execute("INSERT OR IGNORE INTO env_profile(id, image_ref, arch, locale, tz, env_json, seed) VALUES (?,?,?,?,?,?,?)",
                 (env_id, env.image_ref, env.arch, env.locale, env.tz,
                  json.dumps(env.env, sort_keys=True), env.seed))


def save_world(conn: sqlite3.Connection, world: ResolvedWorld, env: EnvProfile) -> bool:
    """Insert a world and its entries. Idempotent. Returns True if the world was new."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        save_env_profile(conn, world.env_profile_id, env)
        cur = conn.execute(
            "INSERT OR IGNORE INTO resolved_world(world_hash, ecosystem, runtime_json, env_profile_id, kind) VALUES (?,?,?,?,?)",
            (world.world_hash, world.ecosystem.value, world.runtime.model_dump_json(), world.env_profile_id,
             world.kind.value))
        new = cur.rowcount == 1
        if new:
            for e in world.entries:
                pv = package_version_id(world.ecosystem, e.name, e.version)
                conn.execute("INSERT OR IGNORE INTO package_version(id, ecosystem, name, version, artifact_sha256) "
                             "VALUES (?,?,?,?,?)", (pv, world.ecosystem.value, e.name, e.version, e.artifact_sha256))
                conn.execute("INSERT INTO world_entry(world_hash, locator, package_version_id, scope, source_kind, parents_json) "
                             "VALUES (?,?,?,?,?,?)",
                             (world.world_hash, e.locator, pv, e.scope.value, e.source_kind.value,
                              json.dumps(list(e.parents))))
        conn.execute("COMMIT")
        return new
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def set_venv_status(conn: sqlite3.Connection, world_hash: str, status: VenvStatus, venv_path: str | None = None) -> None:
    conn.execute("UPDATE resolved_world SET venv_status=?, venv_path=? WHERE world_hash=?",
                 (status.value, venv_path, world_hash))


def venv_status(conn: sqlite3.Connection, world_hash: str) -> VenvStatus | None:
    r = conn.execute("SELECT venv_status FROM resolved_world WHERE world_hash=?", (world_hash,)).fetchone()
    return VenvStatus(r["venv_status"]) if r else None


def world_packages(conn: sqlite3.Connection, world_hash: str) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT pv.name, pv.version FROM world_entry we JOIN package_version pv "
                        "ON pv.id = we.package_version_id WHERE we.world_hash=? ORDER BY pv.name", (world_hash,)).fetchall()
    return [(r["name"], r["version"]) for r in rows]
