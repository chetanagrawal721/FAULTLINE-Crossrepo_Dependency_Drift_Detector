"""Failure classification (master section 28.4). Runs BEFORE anything can become evidence.

An import or test failure is only an ARTIFACT_FAILURE when the failing code is the artifact or the packages in the
world. Failures of the harness, the sandbox, the network or the environment are never compatibility failures.
"""
from ..core.enums import FailureClass

NETWORK_EXCEPTIONS = {"gaierror", "ConnectionError", "ConnectionRefusedError", "ConnectionResetError", "URLError",
                      "TimeoutError", "socket.timeout", "SSLError", "MaxRetryError", "NewConnectionError"}
HARNESS_MODULE = "faultline_harness"


def innermost_module(frames: list[dict]) -> str | None:
    return frames[-1].get("module") if frames else None


def classify_entry(entry: dict, artifact_top_level: str) -> tuple[FailureClass, bool]:
    """Returns (failure_class, not_applicable) for one entry (a module import, a test, ...)."""
    if entry.get("passed") or entry.get("skipped"):
        return FailureClass.NONE, False
    exc = entry.get("exc_type") or ""
    frames = entry.get("frames") or []
    if exc in ("ChildCrash", "TimeoutExpired") or innermost_module(frames) == HARNESS_MODULE:
        return FailureClass.HARNESS_FAILURE, False
    if exc in NETWORK_EXCEPTIONS or (exc == "KeyError" and _env_lookup(frames)):
        return FailureClass.NEEDS_EXTERNAL, False
    missing = entry.get("missing")
    if exc == "ModuleNotFoundError" and missing:
        root = str(missing).split(".")[0]
        if root != artifact_top_level:
            # a third-party package this world does not contain: an optional extra that is not installed here
            return FailureClass.NONE, True
    return FailureClass.ARTIFACT_FAILURE, False


def _env_lookup(frames: list[dict]) -> bool:
    return any(f.get("func") == "__getitem__" and "os" in (f.get("module") or "") for f in frames)


PRECEDENCE = [FailureClass.HARNESS_FAILURE, FailureClass.NEEDS_EXTERNAL, FailureClass.ARTIFACT_FAILURE]


def classify_run(sandbox_class: str, entry_classes: list[FailureClass]) -> FailureClass:
    """Run-level class. Sandbox-level problems (timeout, resource limit, sandbox failure, harness crash) win."""
    sc = FailureClass(sandbox_class)
    if sc != FailureClass.NONE:
        return sc
    for c in PRECEDENCE:
        if c in entry_classes:
            return c
    return FailureClass.NONE
