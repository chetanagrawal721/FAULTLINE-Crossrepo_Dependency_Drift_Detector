"""SQLite access (single host, WAL). Never put the database file on a network filesystem."""
import sqlite3
from pathlib import Path


def connect(path: str | Path, *, timeout: float = 30.0, check_same_thread: bool = True) -> sqlite3.Connection:
    p = Path(path)
    if str(path) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=timeout, isolation_level=None,   # autocommit; we BEGIN explicitly
                           check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
