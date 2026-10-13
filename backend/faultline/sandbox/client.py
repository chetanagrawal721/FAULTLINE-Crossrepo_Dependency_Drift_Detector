"""SandboxClient: how the rest of Faultline asks for execution. Nothing else may start containers."""
import contextlib
import contextvars
import json
import os
import socket

from ..core.errors import ErrorCode, FaultlineError
from .sandboxd import load_token


class SandboxUnavailable(FaultlineError):
    """sandboxd is not reachable or refused the job. Usually transient (it may still be starting), so it is retryable."""
    code = ErrorCode.SANDBOX_FAILED
    http_status = 503

    def __init__(self, message: str, *, code: ErrorCode | None = None, details: dict | None = None):
        super().__init__(message, code=code, details={"retryable": True, **(details or {})})


CURRENT_GROUP: contextvars.ContextVar[str | None] = contextvars.ContextVar("faultline_sandbox_group", default=None)


@contextlib.contextmanager
def job_group(group: str):
    """Everything submitted inside this block is labelled with the worker job, so cancelling the job can stop its containers."""
    token = CURRENT_GROUP.set(group)
    try:
        yield
    finally:
        CURRENT_GROUP.reset(token)


class SandboxClient:
    def __init__(self, host: str | None = None, port: int | None = None, token: str | None = None,
                 timeout: float = 1000.0):
        self.host = host or os.environ.get("FAULTLINE_SANDBOX_HOST", "127.0.0.1")
        self.port = port or int(os.environ.get("FAULTLINE_SANDBOX_PORT", "8787"))
        self.token = token or load_token()
        self.timeout = timeout

    def _call(self, payload: dict, timeout: float | None = None) -> dict:
        if not self.token:
            raise SandboxUnavailable("no sandboxd token: sandboxd has not been started")
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout or self.timeout) as s:
                s.sendall((json.dumps({"token": self.token, **payload}) + "\n").encode())
                s.settimeout(timeout or self.timeout)
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
        except OSError as exc:
            raise SandboxUnavailable(f"sandboxd is not reachable: {exc}") from exc
        reply = json.loads(buf or b"{}")
        if reply.get("error") == "unauthorized":
            raise SandboxUnavailable("sandboxd rejected the token")
        return reply

    def ping(self) -> bool:
        try:
            return bool(self._call({"cmd": "ping"}, timeout=2).get("ok"))
        except SandboxUnavailable:
            return False

    def status(self, timeout: float = 3.0) -> dict:
        return self._call({"cmd": "status"}, timeout=timeout)

    def submit(self, job: dict) -> dict:
        """Run one structured job. Raises SandboxUnavailable when execution is not possible (fail closed)."""
        group = CURRENT_GROUP.get()
        if group and "group" not in job:
            job = {**job, "group": group}
        reply = self._call({"cmd": "run", "job": job})
        if reply.get("error") and "failure_class" not in reply:      # protocol-level error, not a job result
            raise SandboxUnavailable(reply["error"])
        return reply

    def verify(self) -> dict:
        return self._call({"cmd": "verify"}, timeout=300)

    def volume_exists(self, world: str | None = None) -> bool:
        """Does the world's volume (or, with no argument, the shared wheelhouse volume) exist?"""
        return bool(self._call({"cmd": "volume_exists", **({"world": world} if world else {})}, timeout=30).get("exists"))

    def volume_rm(self, world: str) -> bool:
        return bool(self._call({"cmd": "volume_rm", "world": world}, timeout=60).get("removed"))

    def cancel(self, group: str) -> list[str]:
        """Kill the running containers of one worker job. Returns the container ids."""
        return self._call({"cmd": "cancel", "group": group}, timeout=60).get("killed", [])

    def groups(self) -> list[str]:
        return self._call({"cmd": "groups"}, timeout=30).get("groups", [])

    def sweep(self) -> list[str]:
        return self._call({"cmd": "sweep"}, timeout=120).get("removed", [])
