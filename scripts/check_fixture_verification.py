"""TC-1.0.3: every scenario used by a test must have a hand-verification record.

A scenario file (fixtures/scenarios/<ID>.yaml) must name `verified_by: <ID>` that exists in
fixtures/verification/results.json with verified=true, a date, and the exact package versions.
Exit 1 on any violation.
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def check(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    res_file = root / "fixtures" / "verification" / "results.json"
    if not res_file.exists():
        return ["fixtures/verification/results.json is missing; run scripts/verify_fixture_facts.py"]
    meta = json.loads(res_file.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in meta["results"]}
    if not meta.get("verified_at"):
        errors.append("results.json has no verified_at date")
    for rid, r in by_id.items():
        if not r.get("verified"):
            errors.append(f"verification {rid}: verified is not true")
        if not r.get("ref_freeze") or not r.get("test_freeze"):
            errors.append(f"verification {rid}: exact package versions are missing")
        for side in ("ref_runs", "test_runs"):
            if len(r.get(side, [])) != 3:
                errors.append(f"verification {rid}: {side} must have 3 runs")
    for f in sorted((root / "fixtures" / "scenarios").glob("*.yaml")):
        sc = yaml.safe_load(f.read_text(encoding="utf-8"))
        if sc.get("kind") == "real_world":
            continue                                    # real-world cases have their own record (M12.1)
        vid = sc.get("verified_by")
        if vid is None:
            errors.append(f"{f.name}: no verified_by")
        elif vid not in by_id:
            errors.append(f"{f.name}: verified_by {vid!r} has no record")
        elif not by_id[vid]["verified"]:
            errors.append(f"{f.name}: its verification record is not verified")
    return errors


if __name__ == "__main__":
    errs = check()
    for e in errs:
        print("ERROR:", e)
    print("FAILED" if errs else "ok: all fixture verification records are complete")
    sys.exit(1 if errs else 0)
