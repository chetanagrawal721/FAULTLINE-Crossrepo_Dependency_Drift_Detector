import secrets
from collections.abc import Iterator

from fastapi import Header, Request

from ..core.config import Settings
from ..core.enums import Mode
from ..core.errors import InvalidTransitionError, UnauthorizedError
from ..storage.db import connect


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def fresh_conn(request: Request) -> Iterator:
    """A connection whose findings are current: any finding decided under an older verdict policy is recomputed from its stored evidence first.
    REPLAY serves the recorded database untouched."""
    conn = connect(request.app.state.settings.db_path, check_same_thread=False)
    try:
        if request.app.state.settings.mode.value != "REPLAY":
            from ..verdicts.recompute import recompute_all_stale
            recompute_all_stale(conn)
        yield conn
    finally:
        conn.close()


def get_conn(request: Request) -> Iterator:
    # FastAPI runs sync dependencies in a thread pool, so setup and teardown can land on different threads.
    # Each request still owns its connection exclusively, so sharing it across those two threads is safe.
    conn = connect(request.app.state.settings.db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def require_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Mutating endpoints need the admin token when one is configured, and are refused in REPLAY mode (recorded evidence only)."""
    if request.app.state.settings.mode == Mode.REPLAY:
        raise InvalidTransitionError("REPLAY mode shows recorded evidence only: nothing can be started or re-run")
    token = request.app.state.settings.admin_token
    if token is None:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, token):
        raise UnauthorizedError("missing or invalid admin token")
