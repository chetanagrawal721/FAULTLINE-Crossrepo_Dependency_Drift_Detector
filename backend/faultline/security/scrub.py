"""Secret scrubbing. Evidence and logs must never carry credentials.

scrub_text removes (a) the values of any environment variable whose name looks secret, and (b) well-known token
shapes. It is applied to every free-text field that goes into an evidence bundle.
"""
import os
import re
from collections.abc import Mapping

SECRET_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL|CANARY)", re.I)
TOKEN_SHAPES = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),                       # GitHub tokens
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I),
    re.compile(r"AKIA[0-9A-Z]{16}"),                                  # AWS access key id
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
]
MIN_SECRET_LENGTH = 6


def secret_values(env: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if env is None else env
    return sorted({v for k, v in env.items() if SECRET_NAME.search(k) and len(v) >= MIN_SECRET_LENGTH}, key=len, reverse=True)


def scrub_text(text: str | None, env: Mapping[str, str] | None = None) -> str:
    if not text:
        return text or ""
    out = text
    for v in secret_values(env):
        out = out.replace(v, "[REDACTED]")
    for rx in TOKEN_SHAPES:
        out = rx.sub("[REDACTED]", out)
    return out


def scrub_obj(obj, env: Mapping[str, str] | None = None):
    """Scrub every string inside a JSON-like structure."""
    if isinstance(obj, str):
        return scrub_text(obj, env)
    if isinstance(obj, dict):
        return {k: scrub_obj(v, env) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub_obj(v, env) for v in obj]
    return obj
