"""Explicit SQL migrations. Each file is applied inside one transaction; a failure rolls everything back."""
import hashlib
import re
import sqlite3
import time
from pathlib import Path

from ..core.errors import ErrorCode, FaultlineError

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


def _discover(directory: Path) -> list[tuple[int, str, str, str]]:
    found = []
    for f in sorted(directory.glob("*.sql")):
        m = _NAME.match(f.name)
        if not m:
            raise FaultlineError(f"bad migration file name: {f.name}", code=ErrorCode.MIGRATION_FAILED)
        text = f.read_text(encoding="utf-8")
        found.append((int(m.group(1)), m.group(2), text, hashlib.sha256(text.encode()).hexdigest()))
    versions = [v for v, *_ in found]
    if versions != sorted(set(versions)):
        raise FaultlineError("duplicate or unordered migration versions", code=ErrorCode.MIGRATION_FAILED)
    return found


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
    if row is None:
        return 0
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]


def migrate(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> int:
    """Apply pending migrations. Safe to run repeatedly. Returns the schema version afterwards."""
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
    applied = ({r["version"]: r["checksum"] for r in conn.execute("SELECT version, checksum FROM schema_migrations")}
               if has_table else {})
    for version, name, text, checksum in _discover(directory):
        if version in applied:
            if applied[version] != checksum:
                raise FaultlineError(f"migration {version:04d}_{name} was modified after it was applied",
                                     code=ErrorCode.MIGRATION_FAILED)
            continue
        try:
            conn.execute("BEGIN IMMEDIATE")
            # created inside the transaction so a failed first migration leaves no trace
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                         "version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, "
                         "applied_at REAL NOT NULL)")
            # executescript would COMMIT first, so run statements one by one inside our transaction.
            for stmt in _split_statements(text):
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (?,?,?,?)",
                         (version, name, checksum, time.time()))
            conn.execute("COMMIT")
        except Exception as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise FaultlineError(f"migration {version:04d}_{name} failed: {exc}",
                                 code=ErrorCode.MIGRATION_FAILED,
                                 details={"version": version, "name": name}) from exc
    return schema_version(conn)


def _split_statements(sql: str) -> list[str]:
    """Split a script into complete statements using SQLite itself (handles triggers and strings)."""
    statements, buf = [], ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                statements.append(buf.strip())
            buf = ""
    if buf.strip() and not all(ln.strip().startswith("--") or not ln.strip() for ln in buf.splitlines()):
        raise FaultlineError("incomplete statement at end of migration", code=ErrorCode.MIGRATION_FAILED)
    return statements
