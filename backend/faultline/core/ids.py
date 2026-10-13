"""Prefixed, time-sortable identifiers (ULID layout: 48-bit ms timestamp + 80 random bits)."""
import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def ulid() -> str:
    return _encode(int(time.time() * 1000), 10) + _encode(secrets.randbits(80), 16)


def new_id(prefix: str) -> str:
    """Return an id such as job_01J9Q... for the given prefix."""
    return f"{prefix}_{ulid()}"
