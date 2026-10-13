from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from ...capabilities import build_capabilities
from ...core.config import Settings
from ...core.models import Capabilities, Health
from ...sandbox.status import current_sandbox_status
from ...storage.migrate import schema_version
from ..deps import get_conn, get_settings

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=Health)
def health(settings: Settings = Depends(get_settings), conn=Depends(get_conn)) -> Health:
    try:
        conn.execute("SELECT 1").fetchone()
        db, version = "ok", schema_version(conn)
    except Exception:  # noqa: BLE001
        db, version = "error", 0
    return Health(status="ok" if db == "ok" else "degraded", db=db, schema_version=version,
                  mode=settings.mode, auth="token" if settings.admin_token else "disabled",
                  time=datetime.now(UTC))


@router.get("/capabilities", response_model=Capabilities)
def capabilities(settings: Settings = Depends(get_settings)) -> Capabilities:
    return build_capabilities(settings.mode, current_sandbox_status())
