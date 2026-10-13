"""Remove old data from the store without touching evidence that a finding refers to.

    python scripts/retention.py --max-age-days 30 --dry-run     # show what would be removed
    python scripts/retention.py --max-age-days 30               # remove it
    python scripts/retention.py --max-age-days 14 --logs var/logs

Snapshots, artifacts, worlds and bundles that a retained finding or witness depends on are always kept (see storage/retention.py).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.core.config import Settings  # noqa: E402
from faultline.storage.db import connect  # noqa: E402
from faultline.storage.retention import cleanup, prune_logs  # noqa: E402
from faultline.storage.store import Store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-days", type=float, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--logs", help="a directory of *.log files to prune with the same age limit")
    a = ap.parse_args()
    settings = Settings.from_env()
    conn = connect(settings.db_path)
    report = cleanup(conn, Store(settings.store_path), max_age_days=a.max_age_days, dry_run=a.dry_run)
    out = {"dry_run": a.dry_run, "deleted": report.deleted, "kept_because_referenced": {k: len(v) for k, v in report.kept_referenced.items()},
           "kept_because_recent": {k: len(v) for k, v in report.kept_recent.items()}}
    if a.logs:
        out["logs_removed"] = [] if a.dry_run else prune_logs(Path(a.logs), max_age_days=a.max_age_days)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
