"""M3.2: golden files, hostile inputs and name normalisation for the Python manifest parsers."""
import json
import os
from pathlib import Path

import pytest

from faultline.core.errors import ErrorCode
from faultline.parsers.common import PathEscape, SnapshotFS, canonical_name, to_jsonable
from faultline.parsers.python.locks import parse_poetry_lock, parse_uv_lock
from faultline.parsers.python.pyproject import parse_pyproject, poetry_specifier
from faultline.parsers.python.requirements import parse_requirements

GOLD = Path(__file__).resolve().parents[1] / "golden" / "python"


def check_golden(name: str, obj) -> None:
    path = GOLD / f"{name}.golden.json"
    text = json.dumps(to_jsonable(obj), indent=2, sort_keys=True, default=str) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.read_text(encoding="utf-8") == text, f"{name} differs from its golden file (UPDATE_GOLDEN=1 to regenerate, then review)"


@pytest.fixture
def gold_fs():
    return SnapshotFS(GOLD)


def test_tc_3_2_1_requirements_golden(gold_fs):
    check_golden("requirements", parse_requirements(gold_fs, "requirements.txt"))


def test_tc_3_2_1_pep621_golden(gold_fs):
    check_golden("pep621", parse_pyproject(gold_fs, "pep621.toml"))


def test_tc_3_2_1_poetry_golden(gold_fs):
    check_golden("poetry", parse_pyproject(gold_fs, "poetry.toml"))


def test_tc_3_2_1_uv_lock_golden(gold_fs):
    check_golden("uv_lock", parse_uv_lock(gold_fs, "uv.lock"))


def test_tc_3_2_1_poetry_lock_golden(gold_fs):
    check_golden("poetry_lock", parse_poetry_lock(gold_fs, "poetry.lock"))


@pytest.mark.parametrize("spec,expected", [
    ("^1.2.3", ">=1.2.3,<2"), ("^0.2.3", ">=0.2.3,<0.3"), ("^0.0.3", ">=0.0.3,<0.0.4"), ("^1.2", ">=1.2,<2"),
    ("^0", ">=0,<1"), ("~1.2.3", ">=1.2.3,<1.3"), ("~1.2", ">=1.2,<1.3"), ("~1", ">=1,<2"), ("1.2.3", "==1.2.3"),
    (">=1,<2", ">=1,<2"), ("*", ""), ("~=1.4", "~=1.4")])
def test_poetry_caret_and_tilde_follow_the_documented_rules(spec, expected):
    assert poetry_specifier(spec) == expected


def test_tc_3_2_3_name_normalisation(gold_fs):
    r = parse_requirements(gold_fs, "requirements.txt")
    fb = [d for d in r.dependencies if d.name == "foo-bar"]
    assert [d.display for d in fb] == ["Foo_Bar", "foo.bar", "FOO-BAR"]                   # one identity, three spellings kept
    assert {canonical_name(x) for x in ("Foo_Bar", "foo.bar", "FOO-BAR", "foo__bar", "Foo-.-Bar")} == {"foo-bar"}


def test_includes_are_followed_with_their_own_origin_and_constraints_kept_apart(gold_fs):
    r = parse_requirements(gold_fs, "requirements.txt")
    by = {d.name: d for d in r.dependencies}
    assert by["jinja2"].origin == "base.txt" and by["click"].origin == "nested/deep.txt"
    assert [c.name for c in r.constraints] == ["markupsafe"] and "markupsafe" not in by
    assert any(d.code == "UNPARSEABLE_LINE" and d.line == 17 for d in r.diagnostics) and r.status == "PARTIAL"


# ------------------------------------------------------------------------------------------------ hostile inputs

def snap(tmp_path, files: dict[str, bytes | str]) -> SnapshotFS:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
    return SnapshotFS(tmp_path)


@pytest.mark.parametrize("inc", ["../../outside.txt", "/etc/passwd", r"C:\x.txt", "a/../../../x.txt", r"..\x.txt"])
def test_tc_3_2_2_include_path_escape_is_refused(tmp_path, inc):
    (tmp_path.parent / "outside.txt").write_text("evil==1\n")
    fs = snap(tmp_path, {"sub/requirements.txt": f"flask==2.2.2\n-r {inc}\n"})
    r = parse_requirements(fs, "sub/requirements.txt")
    assert r.status == "FAILED" and any(d.code == "PATH_ESCAPE" for d in r.diagnostics)
    assert [d.name for d in r.dependencies] == ["flask"]                                  # nothing from outside was read


def test_tc_3_2_2_join_never_leaves_the_root():
    for bad in ("..", "../a", "a/../../b", "/abs", "x\x00y", ""):
        with pytest.raises(PathEscape):
            SnapshotFS.join("b.txt", bad)
    with pytest.raises(PathEscape):
        SnapshotFS.join("b.txt", "../c.txt")
    assert SnapshotFS.join("a/b.txt", "../c.txt") == "c.txt"                              # up one level, still inside


def test_tc_3_2_2_oversized_file_is_too_large_not_a_crash(tmp_path):
    fs = snap(tmp_path, {"requirements.txt": b"a==1\n" * 4})
    fs.max_bytes = 10
    r = parse_requirements(fs, "requirements.txt")
    assert r.status == "TOO_LARGE" and r.diagnostics[0].code == ErrorCode.MANIFEST_TOO_LARGE.value
    big = SnapshotFS(tmp_path, max_bytes=50 * 1024 * 1024)
    (tmp_path / "huge.txt").write_bytes(b"x" * (50 * 1024 * 1024 + 1))
    big.max_bytes = 5 * 1024 * 1024
    assert parse_requirements(big, "huge.txt").status == "TOO_LARGE"                      # a 50 MB file hits the default limit


@pytest.mark.parametrize("parse,name,content", [
    (parse_uv_lock, "uv.lock", "this is = not [ toml"),
    (parse_uv_lock, "uv.lock", "version = 1\n"),
    (parse_uv_lock, "uv.lock", 'version = 1\n[[package]]\nname = "a"\nversion = "1"\n'),
    (parse_uv_lock, "uv.lock", 'version = 1\n[[package]]\nname = "a"\nversion = "1"\nsource = {registry = "x"}\nwheels = [{url = "u"}]\n'),
    (parse_poetry_lock, "poetry.lock", "[[package]\n"),
    (parse_poetry_lock, "poetry.lock", '[metadata]\nlock-version = "2.0"\n'),
])
def test_tc_3_2_2_malformed_lockfile_is_failed_not_empty(tmp_path, parse, name, content):
    r = parse(snap(tmp_path, {name: content}), name)
    assert r.status == "FAILED" and r.packages == [] and r.error


def test_unknown_lock_versions_are_unsupported(tmp_path):
    assert parse_uv_lock(snap(tmp_path, {"uv.lock": "version = 99\n"}), "uv.lock").status == "UNSUPPORTED"
    r = parse_poetry_lock(snap(tmp_path, {"poetry.lock": '[metadata]\nlock-version = "9.0"\n'}), "poetry.lock")
    assert r.status == "UNSUPPORTED"


def test_pyproject_malformed_and_without_project(tmp_path):
    assert parse_pyproject(snap(tmp_path, {"p.toml": "[project\n"}), "p.toml").status == "FAILED"
    r = parse_pyproject(snap(tmp_path, {"q.toml": "[tool.ruff]\nline-length = 100\n"}), "q.toml")
    assert r.status == "UNSUPPORTED" and r.dependencies == []


def test_dynamic_dependencies_are_flagged_not_guessed(tmp_path):
    r = parse_pyproject(snap(tmp_path, {"p.toml": '[project]\nname = "x"\ndynamic = ["dependencies"]\n'}), "p.toml")
    assert r.status == "PARTIAL" and any(d.code == "DYNAMIC_DEPENDENCIES" for d in r.diagnostics)


def test_include_cycles_and_depth_terminate(tmp_path):
    fs = snap(tmp_path, {"a.txt": "-r b.txt\nx==1\n", "b.txt": "-r a.txt\ny==1\n"})
    r = parse_requirements(fs, "a.txt")
    assert any(d.code == "INCLUDE_CYCLE" for d in r.diagnostics) and {d.name for d in r.dependencies} == {"x", "y"}


def test_odd_input_does_not_crash(tmp_path):
    lines = ["\x00", "-", "--", "-r", "-r ", "== 1", "a==", "[extras]", "a @ ", "${HOME}/x", "--hash=sha256:zz", "   ", "\\", "a\\"]
    r = parse_requirements(snap(tmp_path, {"r.txt": "\n".join(lines)}), "r.txt")
    assert r.status in ("PARTIAL", "FAILED", "OK")


def test_setup_cfg_declarative_metadata_is_read_and_dynamic_parts_are_not_evaluated(tmp_path):
    """Flask 2.2.x declares its dependencies in setup.cfg; reading it is plain INI parsing."""
    from faultline.parsers.python.setup_cfg import parse_setup_cfg
    cfg = ("[metadata]\nname = Flask\nversion = attr: flask.__version__\n\n[options]\npython_requires = >= 3.7\ninstall_requires =\n"
           "    Werkzeug >= 2.2.2\n    Jinja2 >= 3.0\n    importlib-metadata >= 3.6.0; python_version < '3.10'\n\n"
           "[options.extras_require]\nasync = asgiref >= 3.2\ndotenv = python-dotenv\n")
    fs = snap(tmp_path, {"setup.cfg": cfg})
    r = parse_setup_cfg(fs, "setup.cfg")
    assert r.meta["name"] == "Flask" and r.meta["version"] is None and r.meta["requires_python"] == ">= 3.7"
    assert [(d.name, d.group) for d in r.dependencies] == [("werkzeug", "main"), ("jinja2", "main"), ("importlib-metadata", "main"),
                                                           ("asgiref", "optional:async"), ("python-dotenv", "optional:dotenv")]
    assert r.dependencies[2].marker == 'python_version < "3.10"'
    assert r.meta["dynamic_version"] is True and r.status == "OK"                         # attr: is reported, never evaluated, and does not block resolution
    assert parse_setup_cfg(snap(tmp_path / "x", {"setup.cfg": "[broken"}), "setup.cfg").status == "FAILED"


def test_setup_py_is_parsed_to_an_ast_and_never_executed(tmp_path):
    """Flask 2.2.x and requests declare dependencies in setup.py. Literals are read; anything computed is reported, not run."""
    from faultline.parsers.python.setup_py import parse_setup_py
    canary = tmp_path / "CANARY"
    src = (f"import pathlib\npathlib.Path({str(canary)!r}).write_text('executed')\nfrom setuptools import setup\n"
           "requires = ['charset_normalizer>=2,<4', 'idna>=2.5,<4']\nextra = {'socks': ['PySocks>=1.5.6,!=1.5.7']}\n"
           "setup(name='requests', version='2.32.3', python_requires='>=3.8', install_requires=requires + ['urllib3>=1.21.1'], extras_require=extra)\n")
    r = parse_setup_py(snap(tmp_path / "s", {"setup.py": src}), "setup.py")
    assert not canary.exists()                                                           # nothing was executed
    assert r.meta["name"] == "requests" and r.meta["requires_python"] == ">=3.8" and r.status == "OK"
    assert [(d.name, d.group) for d in r.dependencies] == [("charset-normalizer", "main"), ("idna", "main"), ("urllib3", "main"), ("pysocks", "optional:socks")]
    computed = parse_setup_py(snap(tmp_path / "c", {"setup.py": "from setuptools import setup\nimport os\nsetup(name='x', install_requires=open('r.txt').read().split())\n"}), "setup.py")
    assert computed.dependencies == [] and any(d.code == "NON_LITERAL_ARGUMENT" for d in computed.diagnostics) and computed.status == "PARTIAL"
    assert parse_setup_py(snap(tmp_path / "n", {"setup.py": "print('hi')\n"}), "setup.py").status == "UNSUPPORTED"
    assert parse_setup_py(snap(tmp_path / "b", {"setup.py": "def ("}), "setup.py").status == "FAILED"


def test_a_computed_version_does_not_make_a_setup_py_partial_but_computed_dependencies_do(tmp_path):
    from faultline.parsers.python.setup_py import parse_setup_py
    src = "from setuptools import setup\nsetup(name='x', version=open('v.txt').read(), install_requires=['requests>=2'])\n"
    ok = parse_setup_py(snap(tmp_path / "a", {"setup.py": src}), "setup.py")
    assert ok.status == "OK" and [d.name for d in ok.dependencies] == ["requests"]
    assert any(d.code == "NON_LITERAL_ARGUMENT" and "version" in d.message for d in ok.diagnostics)         # still reported, not hidden
    bad = parse_setup_py(snap(tmp_path / "b", {"setup.py": "from setuptools import setup\nsetup(name='x', install_requires=f())\n"}), "setup.py")
    assert bad.status == "PARTIAL"


def test_artifact_roots_include_dependencies_declared_in_setup_py():
    import json
    import sqlite3

    from faultline.worlds.cells import artifact_roots
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE manifest(project_id TEXT, kind TEXT, parsed_json TEXT)")
    c.execute("INSERT INTO manifest VALUES ('p', 'setup_py', ?)", (json.dumps({"dependencies": [{"name": "requests", "group": "main", "extras": []}]}),))
    assert artifact_roots(c, "p", frozenset()) == [("requests", frozenset())]
