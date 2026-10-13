"""Failure signatures: the normalized identity of a failure, used to decide that three failures are 'the same'.

Raw output is kept elsewhere; only this normalized form is compared. Normalization removes things that vary between
runs but do not change what failed (memory addresses, scratch paths, whitespace).
"""
import re

from ..core.models import EntryOutcome, FailureSignature

_SITE = re.compile(r"/opt/world/lib/python[\d.]+/site-packages/")
_SKIP_MODULE_PREFIXES = ("faultline_harness", "importlib", "<frozen", "_pytest", "pluggy", "pytest")


def normalize_message(message: str | None) -> str:
    m = message or ""
    m = re.sub(r"0x[0-9a-fA-F]+", "0x...", m)
    m = _SITE.sub("<site>/", m)
    m = re.sub(r"/(?:tmp|work)/[^\s'\")]*", "<scratch>", m)
    m = re.sub(r"\b\d+\.\d{3,}s\b", "<seconds>", m)           # timings
    return re.sub(r"\s+", " ", m).strip()


def origin_frame(frames: tuple[dict, ...] | list[dict]) -> dict | None:
    """The innermost frame that belongs to the artifact, its tests or a package in the world."""
    for f in reversed(list(frames)):
        mod = f.get("module") or ""
        if mod and not mod.startswith(_SKIP_MODULE_PREFIXES):
            return f
    return None


def signature_of(entry: EntryOutcome, entry_point: str | None = None) -> FailureSignature:
    f = origin_frame(entry.frames)
    module = (f or {}).get("module")
    return FailureSignature(
        exc_type=entry.exc_type or "Unknown",
        message_norm=normalize_message(entry.message),
        origin_module=module,
        origin_package=module.split(".")[0] if module else None,
        entry_point=entry_point or entry.entry,
    )
