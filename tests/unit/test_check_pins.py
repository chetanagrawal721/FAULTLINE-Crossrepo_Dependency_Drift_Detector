"""TC-0.1.2: the pin check must fail on anything unpinned, not just pass on the current tree."""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_pins.py"


def load():
    spec = importlib.util.spec_from_file_location("check_pins_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fresh(mod, root):
    mod.ROOT = root
    mod.errors = []
    mod.checked = {"python_deps": 0, "npm_deps": 0, "images": 0, "actions": 0}
    return mod


def test_unpinned_image_is_reported(tmp_path):
    (tmp_path / "docker" / "x").mkdir(parents=True)
    (tmp_path / "docker" / "x" / "Dockerfile").write_text("FROM python:3.12-slim\nRUN true\n")
    m = fresh(load(), tmp_path)
    m.check_images({"images": {}})
    assert any("no @sha256" in e for e in m.errors)


def test_pinned_image_passes_and_build_stage_alias_is_ignored(tmp_path):
    digest = "a" * 64
    (tmp_path / "docker" / "x").mkdir(parents=True)
    (tmp_path / "docker" / "x" / "Dockerfile").write_text(
        f"FROM python:3.12-slim@sha256:{digest} AS build\nFROM build\n")
    m = fresh(load(), tmp_path)
    m.check_images({"images": {}})
    assert m.errors == [] and m.checked["images"] == 1


def test_floating_npm_and_python_versions_are_reported(tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(json.dumps(
        {"dependencies": {"react": "^19.0.0", "left-pad": "latest", "ok": "1.2.3"}}))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=["fastapi>=0.1", "pydantic==2.0.0"]\n')
    m = fresh(load(), tmp_path)
    m.check_npm_deps()
    m.check_python_deps()
    text = "\n".join(m.errors)
    assert "react" in text and "left-pad" in text and "ok" not in text.replace("package.json", "")
    assert "fastapi>=0.1" in text and "pydantic==2.0.0" not in text
    assert "requires-python" in text and "uv.lock is missing" in text


def test_unpinned_github_action_is_reported(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("steps:\n  - uses: actions/checkout@main\n  - uses: actions/setup-node@v4\n")
    m = fresh(load(), tmp_path)
    m.check_actions()
    assert len(m.errors) == 1 and "checkout" in m.errors[0]
