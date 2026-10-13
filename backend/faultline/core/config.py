"""Runtime configuration read from environment variables (FAULTLINE_*)."""
import os
from dataclasses import dataclass
from pathlib import Path

from .enums import Mode

POLICY_VERSION = "verdict-policy/0"   # bumped whenever the verdict decision table changes
API_VERSION = "1"
EVIDENCE_SCHEMA_VERSION = "1"
CAPABILITY_VERSION = "0.1.0"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    db_path: Path
    store_path: Path
    mode: Mode
    admin_token: str | None
    lease_seconds: float
    heartbeat_seconds: float
    poll_seconds: float

    @staticmethod
    def from_env() -> "Settings":
        root = repo_root()
        mode = os.environ.get("FAULTLINE_MODE", Mode.FIXTURE.value).upper()
        return Settings(
            db_path=Path(os.environ.get("FAULTLINE_DB", root / "var" / "faultline.db")),
            store_path=Path(os.environ.get("FAULTLINE_STORE", root / "var" / "store")),
            mode=Mode(mode),
            admin_token=os.environ.get("FAULTLINE_ADMIN_TOKEN") or None,
            lease_seconds=float(os.environ.get("FAULTLINE_LEASE_SECONDS", "30")),
            heartbeat_seconds=float(os.environ.get("FAULTLINE_HEARTBEAT_SECONDS", "10")),
            poll_seconds=float(os.environ.get("FAULTLINE_POLL_SECONDS", "0.5")),
        )
