"""M11.5: the release manifest is deterministic, covers what a rebuild needs, and notices any change."""
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release_manifest.py"
spec = importlib.util.spec_from_file_location("release_manifest", SCRIPT)
rm = importlib.util.module_from_spec(spec)
sys.modules["release_manifest"] = rm
spec.loader.exec_module(rm)


def make_tree(root: Path) -> None:
    files = {"versions.toml": '[python]\nversion = "3.12.15"\n', "pyproject.toml": "[project]\nname='x'\n", "uv.lock": "lock\n",
             "docker/images.lock.json": '{"exec-python": {"id": "sha256:abc"}}', "docker/exec-python/Dockerfile": "FROM x\n",
             "backend/faultline/a.py": "x = 1\n", "frontend/src/a.tsx": "export {}\n", "frontend/package-lock.json": "{}\n", "frontend/openapi.json": "{}\n",
             "tests/t.py": "pass\n", "scripts/s.py": "pass\n", "fixtures/repos/r/f.txt": "f\n", "benchmarks/cases/c.yaml": "id: c\n",
             "docs/conformance/ps07-matrix.yaml": "rows: []\n", "docs/schemas/evidence-bundle-v1.json": "{}\n"}
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())


def test_the_manifest_is_deterministic_and_carries_what_a_rebuild_needs(tmp_path):
    make_tree(tmp_path)
    a, b = rm.build_manifest(tmp_path), rm.build_manifest(tmp_path)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["toolchain"]["python"]["version"] == "3.12.15" and a["images"]["lock"]["exec-python"]["id"] == "sha256:abc"
    assert a["sources"]["backend"]["files"] == 1 and a["data"]["fixtures"]["files"] == 1 and a["locks"]["uv.lock"]
    assert a["contracts"]["openapi"] and a["contracts"]["evidence_bundle_schema"] and "python tools/fl.py ci" in a["release_blocking_suite"]
    text = json.dumps(a)
    assert str(tmp_path) not in text                                                                  # no host paths, no timestamps: the same commit gives the same bytes


def test_line_endings_do_not_change_the_manifest(tmp_path):
    make_tree(tmp_path)
    before = rm.build_manifest(tmp_path)
    p = tmp_path / "backend" / "faultline" / "a.py"
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    assert rm.build_manifest(tmp_path) == before


def test_any_change_is_listed_by_the_check(tmp_path):
    make_tree(tmp_path)
    recorded = rm.build_manifest(tmp_path)
    assert rm.differences(recorded, rm.build_manifest(tmp_path)) == []
    (tmp_path / "backend" / "faultline" / "a.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("other\n", encoding="utf-8")
    (tmp_path / "docker" / "images.lock.json").write_text('{"exec-python": {"id": "sha256:def"}}', encoding="utf-8")
    diffs = rm.differences(recorded, rm.build_manifest(tmp_path))
    joined = "\n".join(diffs)
    assert "sources.backend.sha256" in joined and "locks.uv.lock" in joined and "images.lock.exec-python.id" in joined
