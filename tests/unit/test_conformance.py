"""M5.7: the conformance report fails loudly when a row fails, and never claims more than the evidence supports."""
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "conformance_report.py"


def run(matrix: Path, tmp: Path, *extra: str):
    out = tmp / "report.json"
    r = subprocess.run([sys.executable, str(SCRIPT), "--matrix", str(matrix), "--out", str(out), *extra], capture_output=True, text=True, cwd=ROOT)
    return r, json.loads(out.read_text(encoding="utf-8"))


def write_matrix(tmp: Path, rows: list[dict]) -> Path:
    p = tmp / "m.yaml"
    p.write_text(yaml.safe_dump({"version": 1, "rows": rows}), encoding="utf-8")
    return p


def test_tc_5_7_2_a_failing_row_makes_the_report_fail_and_names_the_row(tmp_path):
    good = tmp_path / "test_good.py"
    good.write_text("def test_ok():\n    assert True\n")
    bad = tmp_path / "test_bad.py"
    bad.write_text("def test_broken():\n    assert 1 == 2\n")
    art = tmp_path / "artifact.txt"
    art.write_text("evidence")
    rel = lambda p: str(p.resolve().relative_to(ROOT)) if str(p.resolve()).startswith(str(ROOT)) else str(p)  # noqa: E731
    rows = [{"id": "ROW-GOOD", "requirement": "r", "tests": [str(good)], "artifact": [str(art)]},
            {"id": "ROW-BAD", "requirement": "r", "tests": [str(bad)], "artifact": [str(art)]}]
    # absolute paths are accepted: they simply resolve outside the repository root
    r, rep = run(write_matrix(tmp_path, rows), tmp_path)
    assert r.returncode == 1 and "ROW-BAD" in r.stdout and "FAIL" in r.stdout
    status = {x["id"]: x["status"] for x in rep["rows"]}
    assert status == {"ROW-GOOD": "PASS", "ROW-BAD": "FAIL"}
    assert rep["header"].startswith("NOT conformant") and "ROW-BAD" in rep["header"] and "Gate D is blocked" in rep["header"]
    assert rel(good)


def test_all_rows_passing_says_mvp_conformant_but_not_release_hardened(tmp_path):
    ok = tmp_path / "test_ok.py"
    ok.write_text("def test_ok():\n    assert True\n")
    art = tmp_path / "a.txt"
    art.write_text("x")
    r, rep = run(write_matrix(tmp_path, [{"id": "ROW-1", "requirement": "r", "tests": [str(ok)], "artifact": [str(art)]}]), tmp_path)
    assert r.returncode == 0 and rep["header"].startswith("MVP conformant") and "NOT release-hardened" in rep["header"]


def test_missing_tests_missing_artifacts_and_unbuilt_requirements_are_never_pass(tmp_path):
    ok = tmp_path / "test_ok.py"
    ok.write_text("def test_ok():\n    assert True\n")
    rows = [{"id": "NO-TEST", "requirement": "r", "tests": [str(tmp_path / "test_nothing.py")], "artifact": [str(ok)]},
            {"id": "NO-ART", "requirement": "r", "tests": [str(ok)], "artifact": [str(tmp_path / "gone.txt")]},
            {"id": "UNBUILT", "requirement": "r", "implemented": False, "reason": "not built"},
            {"id": "EMPTY", "requirement": "r"}]
    r, rep = run(write_matrix(tmp_path, rows), tmp_path)
    assert r.returncode == 1
    assert {x["id"]: x["status"] for x in rep["rows"]} == {"NO-TEST": "MISSING_TEST", "NO-ART": "MISSING_ARTIFACT", "UNBUILT": "NOT_IMPLEMENTED", "EMPTY": "MISSING_TEST"}


def test_the_real_matrix_is_well_formed_and_names_existing_tests():
    rows = yaml.safe_load((ROOT / "docs" / "conformance" / "ps07-matrix.yaml").read_text(encoding="utf-8"))["rows"]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        if r.get("implemented") is False:
            assert r.get("reason")                                              # every unbuilt MUST states why
            continue
        assert r["tests"] and r["artifact"]
        for t in r["tests"]:
            assert (ROOT / t.split("::")[0]).exists(), (r["id"], t)
    must = {"FR-1", "FR-9c", "FR-12", "FR-13", "FR-19", "ER-2", "PC-4", "PC-5", "PC-10", "REF-POLICY"}
    assert must <= set(ids)                                                      # PC-1 (O-bind), PC-4, PC-5, PC-10 and the reference policy are all traced
