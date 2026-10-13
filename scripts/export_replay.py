"""Export a REPLAY pack: recorded evidence only, no execution (milestone M12.2).

    python scripts/export_replay.py --db var/faultline.db --store var/store --out var/replay

The pack contains a copy of the database in which every analysis is marked REPLAY (the mode it was recorded in is kept in its
options), no queued or running jobs, and a pre-built, pre-verified evidence bundle per witness. Serve it with:

    FAULTLINE_MODE=REPLAY FAULTLINE_DB=var/replay/faultline.db FAULTLINE_STORE=var/replay/store \\
        python -m uvicorn faultline.api.main:app_factory --factory --port 8001

REPLAY mode refuses every action that would start work, serves only these records, and needs neither Docker nor the network.
"""
import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.storage.db import connect  # noqa: E402
from faultline.storage.store import Store  # noqa: E402
from faultline.witnesses.bundle import verify_bundle, write_bundle  # noqa: E402


def export(db: Path, store: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    dest_db = out / "faultline.db"
    if dest_db.exists():
        dest_db.unlink()
    src = sqlite3.connect(db)
    dst = sqlite3.connect(dest_db)
    src.backup(dst)
    src.close()
    dst.close()
    conn = connect(dest_db)
    for a in conn.execute("SELECT id, mode, options_json FROM analysis").fetchall():
        opts = json.loads(a["options_json"] or "{}")
        opts["recorded_from_mode"] = a["mode"]
        conn.execute("UPDATE analysis SET mode='REPLAY', options_json=? WHERE id=?", (json.dumps(opts, sort_keys=True), a["id"]))
    conn.execute("DELETE FROM job_attempt")                    # attempts point at jobs, so they go first
    conn.execute("DELETE FROM job")
    bundles = out / "store" / "bundles"
    bundles.mkdir(parents=True, exist_ok=True)
    n = 0
    skipped = []
    for w in conn.execute("SELECT id FROM witness").fetchall():
        target = bundles / f"{w['id']}.zip"
        try:
            write_bundle(conn, w["id"], target, Store(store), mode="REPLAY")
        except Exception as e:  # noqa: BLE001
            skipped.append({"witness": w["id"], "reason": str(e)[:200]})
            continue
        if not verify_bundle(target).ok:
            target.unlink()
            skipped.append({"witness": w["id"], "reason": "bundle failed verification"})
            continue
        n += 1
    conn.close()
    for sub in ("remediation",):
        if (store / sub).is_dir():
            shutil.copytree(store / sub, out / "store" / sub, dirs_exist_ok=True)
    return {"database": str(dest_db), "bundles": n, "skipped": skipped}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "var" / "faultline.db"))
    ap.add_argument("--store", default=str(ROOT / "var" / "store"))
    ap.add_argument("--out", default=str(ROOT / "var" / "replay"))
    a = ap.parse_args()
    res = export(Path(a.db), Path(a.store), Path(a.out))
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
