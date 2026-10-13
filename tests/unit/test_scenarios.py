"""TC-1.1.1 and TC-1.1.2: scenario files are executable specifications and must be internally consistent."""
import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vs", ROOT / "scripts" / "validate_scenarios.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

SCENARIOS = sorted((ROOT / "fixtures" / "scenarios").glob("*.yaml"))


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_committed_scenarios_validate(path):
    assert vs.validate(path) == []


def test_negative_controls_are_declared_with_reasons():
    for sid in ("A", "H"):
        sc = yaml.safe_load((ROOT / "fixtures" / "scenarios" / f"{sid}.yaml").read_text(encoding="utf-8"))
        cell = sc["expect"]["cells"][0]
        assert cell["witness"] is False and cell["control"]["reason"]


def test_break_scenario_names_signature_and_attribution():
    sc = yaml.safe_load((ROOT / "fixtures" / "scenarios" / "D.yaml").read_text(encoding="utf-8"))
    broken = [c for c in sc["expect"]["cells"] if c["witness"]][0]
    assert broken["verdict"] == "BREAK_WITNESSED" and "url_quote" in broken["signature"]["message_contains"]
    assert broken["attribution"]["minimal_set"] == ["werkzeug"]


def test_validator_rejects_wrong_expected_delta(tmp_path):
    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    p = tmp_path / "fixtures" / "scenarios" / "D.yaml"
    sc = yaml.safe_load(p.read_text(encoding="utf-8"))
    sc["expect"]["cells"][0]["delta"] = ["werkzeug"]            # forgets itsdangerous
    p.write_text(yaml.safe_dump(sc), encoding="utf-8")
    errs = vs.validate(p, root=tmp_path)
    assert any("expected delta" in e for e in errs)


def test_validator_rejects_missing_control_and_bad_file(tmp_path):
    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    p = tmp_path / "fixtures" / "scenarios" / "H.yaml"
    sc = yaml.safe_load(p.read_text(encoding="utf-8"))
    del sc["expect"]["cells"][0]["control"]
    p.write_text(yaml.safe_dump(sc), encoding="utf-8")
    assert any("control" in e for e in vs.validate(p, root=tmp_path))
    p.write_text("id: H\nunknown_key: 1\n", encoding="utf-8")
    assert vs.validate(p, root=tmp_path)


def test_unpinned_reference_lock_is_rejected(tmp_path):
    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    lock = tmp_path / "fixtures" / "repos" / "acme-models" / "requirements.lock.txt"
    lock.write_text("flask>=2\n", encoding="utf-8")
    assert vs.validate(tmp_path / "fixtures" / "scenarios" / "D.yaml", root=tmp_path)
