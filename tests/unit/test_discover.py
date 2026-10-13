"""M3.1: Python project discovery from a snapshot, without running anything."""
from faultline.parsers.python.discover import discover_python
from tests.snapshots import make_snapshot

MONOREPO = {
    "pyproject.toml": '[tool.ruff]\nline-length = 100\n',                                  # workspace config only: not a project
    "libs/core/pyproject.toml": '[project]\nname = "Acme.Core"\nversion = "1.0"\nrequires-python = ">=3.10"\ndependencies = ["pydantic>=2"]\n',
    "libs/core/src/acme_core/__init__.py": "",
    "libs/core/src/acme_core/models.py": "x = 1\n",
    "libs/core/tests/test_models.py": "def test(): pass\n",
    "services/api/pyproject.toml": '[tool.poetry]\nname = "acme-api"\nversion = "0.2.0"\n[tool.poetry.dependencies]\npython = "^3.11"\nflask = "^3"\n'
                                   '[[tool.poetry.packages]]\ninclude = "api_app"\n',
    "services/api/api_app/__init__.py": "",
    "services/api/api_app/views.py": "",
    "services/api/poetry.lock": '[metadata]\nlock-version = "2.0"\n',
    "services/api/requirements/dev.txt": "pytest\n",
    "services/api/docs/requirements.txt": "sphinx\n",
    "tools/batch/requirements.txt": "requests==2.31.0\n",
    "tools/batch/job.py": "print('x')\n",
    "tools/batch/helper.py": "",
    "vendor/lib/pyproject.toml": '[project]\nname = "vendored"\n',
    "node_modules/x/setup.py": "",
    "setup.py": "from setuptools import setup\nsetup()\n",
}


def test_tc_3_1_1_multi_project_repository(tmp_path):
    root, inv = make_snapshot(tmp_path, MONOREPO)
    d = discover_python(root, inv)
    by = {p.rel_path: p for p in d.projects}
    assert set(by) == {".", "libs/core", "services/api", "tools/batch"}, set(by)        # vendored and node_modules ignored

    core = by["libs/core"]
    assert (core.name, core.display_name, core.origin, core.version, core.requires_python) == ("acme-core", "Acme.Core", "pyproject", "1.0", ">=3.10")
    assert core.source_roots == ["libs/core/src"] and core.import_packages == ["acme_core"] and core.has_tests and core.pure_python
    assert core.manifests == {"pyproject": ["libs/core/pyproject.toml"]}

    api = by["services/api"]
    assert (api.name, api.source_roots, api.import_packages) == ("acme-api", ["services/api"], ["api_app"])
    assert api.manifests["poetry_lock"] == ["services/api/poetry.lock"] and api.manifests["requirements"] == ["services/api/requirements/dev.txt"]
    assert "services/api/docs/requirements.txt" in d.unassigned                          # nested outside root/requirements/: not guessed

    batch = by["tools/batch"]
    assert batch.origin == "requirements_only" and batch.name == "batch" and batch.import_packages == ["helper", "job"]
    assert batch.manifests == {"requirements": ["tools/batch/requirements.txt"]}

    root_prj = by["."]                                                                    # the bare setup.py repository root
    assert root_prj.origin == "setup_py" and any("never executed" in n for n in root_prj.notes)
    assert root_prj.import_packages == []                                                # sub-projects are not attributed to the root


def test_tc_3_1_2_setup_py_is_never_executed(tmp_path):
    canary = tmp_path / "CANARY_WAS_CREATED"
    evil = (f"import pathlib\npathlib.Path({str(canary)!r}).write_text('executed')\n"
            "from setuptools import setup\nsetup(name='evil')\n")
    root, inv = make_snapshot(tmp_path / "snap", {"setup.py": evil, "pyproject.toml": "[build-system]\nrequires=['setuptools']\n",
                                                  "evil/__init__.py": evil, "conftest.py": evil})
    d = discover_python(root, inv)
    assert not canary.exists()
    assert [p.origin for p in d.projects] == ["setup_py"]                                  # pyproject without [project]: legacy setup.py project
    assert d.projects[0].import_packages == ["evil"]


def test_native_code_is_not_pure_python(tmp_path):
    root, inv = make_snapshot(tmp_path, {"pyproject.toml": '[project]\nname="fast"\n', "fast/__init__.py": "", "fast/_core.c": "int x;"})
    assert discover_python(root, inv).projects[0].pure_python is False


def test_unreadable_pyproject_is_reported_not_dropped(tmp_path):
    root, inv = make_snapshot(tmp_path, {"pyproject.toml": "[project\n", "a.py": ""})
    p = discover_python(root, inv).projects[0]
    assert p.origin == "pyproject" and any("could not be read" in n for n in p.notes)
