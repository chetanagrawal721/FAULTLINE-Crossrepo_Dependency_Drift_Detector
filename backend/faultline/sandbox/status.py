"""What the API reports about the sandbox: the real answer from sandboxd, or an honest 'unavailable'."""
import time

from ..core.enums import SandboxState
from ..core.models import SandboxStatus
from .client import SandboxClient, SandboxUnavailable

_cache: dict = {"at": 0.0, "value": None}
CACHE_SECONDS = 5.0


def current_sandbox_status(client: SandboxClient | None = None, use_cache: bool = True) -> SandboxStatus:
    now = time.monotonic()
    if use_cache and _cache["value"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["value"]
    try:
        st = (client or SandboxClient()).status()
        b = st.get("boundary", {})
        if not st.get("docker"):
            value = SandboxStatus(state=SandboxState.UNAVAILABLE, verified=False,
                                  reason="sandbox not verified: Docker is not reachable, execution is disabled")
        elif b.get("verified"):
            value = SandboxStatus(state=SandboxState.VERIFIED, verified=True,
                                  reason=f"boundary checks passed ({len(b.get('checks', []))} checks) on the running deployment")
        else:
            value = SandboxStatus(state=SandboxState.UNAVAILABLE, verified=False,
                                  reason=f"sandbox not verified: {b.get('reason', 'boundary not checked')}; execution is disabled")
    except SandboxUnavailable:
        value = SandboxStatus(state=SandboxState.UNAVAILABLE, verified=False,
                              reason="sandbox not verified: sandboxd is not running, execution is disabled")
    _cache.update(at=now, value=value)
    return value
