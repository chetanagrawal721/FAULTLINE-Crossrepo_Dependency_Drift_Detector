import secrets
from collections.abc import Iterator

from fastapi import Header, Request

from ..core.config import Settings
from ..core.errors import UnauthorizedError
from ..storage.db import connect


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_conn(request: Request) -> Iterator:
    # FastAPI runs sync dependencies in a thread pool, so setup and teardown can land on different threads.
    # Each request still owns its connection exclusively, so sharing it across those two threads is safe.
    conn = connect(request.app.state.settings.db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def require_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Mutating endpoints need the admin token when one is configured."""
    token = request.app.state.settings.admin_token
    if token is None:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied, token):
        raise UnauthorizedError("missing or invalid admin token")
