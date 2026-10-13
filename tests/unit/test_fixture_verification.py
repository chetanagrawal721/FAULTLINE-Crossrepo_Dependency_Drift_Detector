"""The verification record checker must fail when a record is missing or incomplete (TC-1.0.3)."""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_fixture_verification.py"
spec = importlib.util.spec_from_file_location("cfv", SCRIPT)
cfv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfv)


def record(rid="D", verified=True, freeze=("flask==2.2.2",), runs=3):
    return {"id": rid, "verified": verified, "ref_freeze": list(freeze), "test_freeze": list(freeze),
            "ref_runs": [{}] * runs, "test_runs": [{}] * runs}


def setup(tmp, results, scenario=None):
    (tmp / "fixtures" / "verification").mkdir(parents=True)
    (tmp / "fixtures" / "scenarios").mkdir(parents=True)
    (tmp / "fixtures" / "verification" / "results.json").write_text(
        json.dumps({"verified_at": "2026-10-13T00:00:00Z", "results": results}))
    if scenario:
        (tmp / "fixtures" / "scenarios" / "S.yaml").write_text(scenario)


def test_complete_records_pass(tmp_path):
    setup(tmp_path, [record()], "id: S\nverified_by: D\n")
    assert cfv.check(tmp_path) == []


def test_missing_results_file_fails(tmp_path):
    assert cfv.check(tmp_path)


def test_unverified_record_fails(tmp_path):
    setup(tmp_path, [record(verified=False)])
    assert any("not true" in e for e in cfv.check(tmp_path))


def test_missing_versions_or_runs_fail(tmp_path):
    setup(tmp_path, [record(freeze=()), record(rid="X", runs=2)])
    errs = " ".join(cfv.check(tmp_path))
    assert "package versions are missing" in errs and "must have 3 runs" in errs


def test_scenario_without_or_with_unknown_verification_fails(tmp_path):
    setup(tmp_path, [record()], "id: S\n")
    assert any("no verified_by" in e for e in cfv.check(tmp_path))
    (tmp_path / "fixtures" / "scenarios" / "S.yaml").write_text("id: S\nverified_by: Z\n")
    assert any("no record" in e for e in cfv.check(tmp_path))
