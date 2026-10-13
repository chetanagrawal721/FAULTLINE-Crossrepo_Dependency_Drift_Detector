"""Conformance report (milestone M5.7): prove every canonical MUST with a command, a result and a retained artifact.

    python scripts/conformance_report.py                      # run every row's tests (needs Docker for some rows)
    python scripts/conformance_report.py --matrix other.yaml  # use another matrix (used by the self-test)
    python scripts/conformance_report.py --no-run             # check only that tests and artifacts EXIST (fast, not a PASS)

A row is PASS only when its tests pass and every artifact path exists. A row marked `implemented: false` is NOT_IMPLEMENTED. Exit
code 0 only when every row is PASS. The header never says more than the evidence supports.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


_RAN: dict[str, tuple[bool, str]] = {}


def run_row(row: dict, run: bool) -> dict:
    out = {"id": row["id"], "requirement": row["requirement"], "phase": row.get("phase"), "note": row.get("note")}
    if row.get("implemented") is False:
        return {**out, "status": "NOT_IMPLEMENTED", "reason": row.get("reason", "not built"), "command": None, "artifacts": row.get("artifact", [])}
    tests = row.get("tests", [])
    artifacts = row.get("artifact", [])
    out.update(command=" ".join(["python -m pytest -q", *tests]), artifacts=artifacts)
    if not tests or not artifacts:
        return {**out, "status": "MISSING_TEST" if not tests else "MISSING_ARTIFACT", "reason": "a row needs at least one test and one artifact"}
    for t in tests:
        if not (ROOT / t.split("::")[0]).exists():
            return {**out, "status": "MISSING_TEST", "reason": f"test path does not exist: {t}"}
    missing = [a for a in artifacts if not (ROOT / a).exists()]
    if missing:
        return {**out, "status": "MISSING_ARTIFACT", "reason": f"artifact does not exist: {', '.join(missing)}"}
    if not run:
        return {**out, "status": "NOT_RUN", "reason": "--no-run: existence checked only"}
    t0 = time.monotonic()
    tails, ok = [], True
    for spec in tests:                          # each test target runs once per report; rows sharing it reuse the real result
        if spec not in _RAN:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", spec], cwd=str(ROOT), capture_output=True, text=True)
            tail = (r.stdout.strip().splitlines() or [""])[-1]
            _RAN[spec] = (r.returncode == 0 and " passed" in tail and " failed" not in tail and "error" not in tail.lower(), tail)
        passed, tail = _RAN[spec]
        ok = ok and passed
        tails.append(f"{spec}: {tail}")
    return {**out, "status": "PASS" if ok else "FAIL", "reason": "; ".join(tails) if not ok else f"{len(tests)} test target(s) passed",
            "details": tails, "seconds": round(time.monotonic() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default=str(ROOT / "docs" / "conformance" / "ps07-matrix.yaml"))
    ap.add_argument("--out", default=str(ROOT / "var" / "conformance-report.json"))
    ap.add_argument("--no-run", action="store_true")
    args = ap.parse_args()
    rows = yaml.safe_load(Path(args.matrix).read_text(encoding="utf-8"))["rows"]
    results = []
    for row in rows:
        res = run_row(row, not args.no_run)
        results.append(res)
        print(f"{res['status']:<16} {res['id']:<12} {res.get('reason') or ''}"[:200])
    bad = [r for r in results if r["status"] != "PASS"]
    passing = len(results) - len(bad)
    header = ("MVP conformant: every canonical MUST row passed. NOT release-hardened: that needs Gate E (security release gate, "
              "evaluation, clean-machine replay)." if not bad else
              f"NOT conformant: {len(bad)} of {len(results)} MUST rows are not PASS ({', '.join(r['id'] for r in bad)}). Gate D is blocked. "
              "Not release-hardened (Gate E).")
    report = {"header": header, "rows_total": len(results), "rows_pass": passing, "rows_not_pass": [{"id": r["id"], "status": r["status"], "reason": r.get("reason")} for r in bad],
              "generated_by": "scripts/conformance_report.py", "rows": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print("\n" + header)
    for r in bad:
        print(f"  - {r['id']}: {r['status']}: {r.get('reason')}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
