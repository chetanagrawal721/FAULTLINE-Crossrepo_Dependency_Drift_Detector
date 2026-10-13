"""M3.3: native resolution with provenance. Real uv inside the fetch zone (network) and real world builds."""
import io
import tarfile
import textwrap

import pytest

from faultline.core.errors import ErrorCode
from faultline.parsers.common import SnapshotFS
from faultline.parsers.python.discover import discover_python
from faultline.resolvers.python import resolve_project
from faultline.worlds.builder import WorldBuilder, WorldBuildError
from tests.snapshots import make_snapshot

CUTOFF = "2024-10-30T00:00:00Z"
H1, H2 = "a" * 64, "b" * 64


def project_of(tmp_path, files):
    root, inv = make_snapshot(tmp_path, files)
    d = discover_python(root, inv)
    assert len(d.projects) == 1, [p.rel_path for p in d.projects]
    return SnapshotFS(root), d.projects[0]


class NoSandbox:
    """Any attempt to run something fails the test: used where nothing may be fetched or executed."""
    def submit(self, spec):
        raise AssertionError(f"sandbox must not be used here: {spec.get('script')}")


# ----------------------------------------------------------------------------- TC-3.3.1 (real uv, real fetch)

@pytest.mark.docker
def test_tc_3_3_1_reproducible_world(tmp_path, sbx, image):
    fs, prj = project_of(tmp_path / "s", {"pyproject.toml": '[project]\nname = "demo"\nversion = "0"\ndependencies = ["flask==2.2.2"]\n'})
    a = resolve_project(sbx, image, fs, prj, cutoff=CUTOFF)
    b = resolve_project(sbx, image, fs, prj, cutoff=CUTOFF)
    assert a.status == "OK" and a.source == "resolver" and a.failure is None, a.failure
    assert a.lock_text == b.lock_text and {p.name for p in a.pinned} >= {"flask", "werkzeug", "jinja2"}
    assert all(p.hashes for p in a.pinned)
    prov = a.provenance
    assert prov["resolver"]["name"] == "uv" and prov["resolver"]["version"].startswith("uv ") and prov["cutoff"] == CUTOFF
    assert "--no-build" in prov["resolver"]["flags"] and "--exclude-newer" in prov["resolver"]["flags"]
    assert prov["target"]["python"] == "3.12" and prov["inputs"] == ["flask==2.2.2"]

    wb = WorldBuilder(sbx, image)
    w1 = wb.materialize(a.lock_text)
    w2 = wb.materialize(b.lock_text)
    assert w1.world_hash == w2.world_hash and all(e.artifact_sha256 for e in w1.entries)

    later = resolve_project(sbx, image, fs, prj, cutoff="2026-01-01T00:00:00Z")           # a different cutoff is a different input
    assert later.provenance["cutoff"] != a.provenance["cutoff"]


# ----------------------------------------------------------------------------- TC-3.3.2 needs-build is not executed

def sdist_with_canary() -> bytes:
    setup = textwrap.dedent('''
        import pathlib
        for p in ("/work/canary", "/tmp/canary"):
            try:
                pathlib.Path(p).write_text("the build ran")
            except OSError:
                pass
        from setuptools import setup
        setup(name="canarypkg", version="1.0")
    ''')
    pkg_info = "Metadata-Version: 2.1\nName: canarypkg\nVersion: 1.0\n"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in (("canarypkg-1.0/setup.py", setup), ("canarypkg-1.0/PKG-INFO", pkg_info)):
            raw = data.encode()
            ti = tarfile.TarInfo(name)
            ti.size = len(raw)
            t.addfile(ti, io.BytesIO(raw))
    return buf.getvalue()


@pytest.mark.docker
def test_tc_3_3_2_needs_build_is_classified_and_nothing_is_built(tmp_path, sbx, image, daemon):
    index = daemon.store.remote_dir("rm_sdistindex")
    index.mkdir(parents=True, exist_ok=True)
    (index / "canarypkg-1.0.tar.gz").write_bytes(sdist_with_canary())
    fs, prj = project_of(tmp_path / "s", {"requirements.txt": "canarypkg==1.0\n"})
    out = resolve_project(sbx, image, fs, prj, cutoff=CUTOFF, no_index=True, find_links=["/source"],
                          mounts={"/source": {"remote": "rm_sdistindex"}}, probe_paths=["/work/canary", "/tmp/canary"])
    assert out.status == "FAILED" and out.failure["code"] == ErrorCode.RESOLUTION_FAILED.value
    assert out.failure["reason"] == "needs_build", out.failure
    assert out.failure["packages"] == ["canarypkg"]
    assert out.provenance["probes"] == {"/work/canary": False, "/tmp/canary": False}      # the build never ran
    assert out.pinned == []                                                                # a failure is never an empty world


def test_needs_build_from_a_lockfile_names_the_package(tmp_path):
    lock = textwrap.dedent(f'''
        version = 1
        requires-python = ">=3.12"
        [[package]]
        name = "demo"
        version = "0"
        source = {{ virtual = "." }}
        dependencies = [{{ name = "sdistonly" }}, {{ name = "okpkg" }}]
        [[package]]
        name = "sdistonly"
        version = "1.0"
        source = {{ registry = "https://pypi.org/simple" }}
        sdist = {{ url = "https://files.pythonhosted.org/x.tar.gz", hash = "sha256:{H1}" }}
        [[package]]
        name = "okpkg"
        version = "2.0"
        source = {{ registry = "https://pypi.org/simple" }}
        wheels = [{{ url = "https://files.pythonhosted.org/okpkg-2.0-py3-none-any.whl", hash = "sha256:{H2}" }}]
    ''')
    fs, prj = project_of(tmp_path, {"pyproject.toml": '[project]\nname = "demo"\nversion = "0"\ndependencies = ["sdistonly", "okpkg"]\n', "uv.lock": lock})
    out = resolve_project(NoSandbox(), "img", fs, prj, cutoff=CUTOFF)
    assert out.status == "FAILED" and out.failure["reason"] == "needs_build" and out.failure["packages"] == ["sdistonly"]


# ----------------------------------------------------------------------------- TC-3.3.3 private index

LOCK_PRIVATE = textwrap.dedent(f'''
    version = 1
    requires-python = ">=3.12"
    [[package]]
    name = "demo"
    version = "0"
    source = {{ virtual = "." }}
    dependencies = [{{ name = "flask" }}, {{ name = "acme-secret" }}]
    [[package]]
    name = "flask"
    version = "2.2.2"
    source = {{ registry = "https://pypi.org/simple" }}
    wheels = [{{ url = "https://files.pythonhosted.org/flask-2.2.2-py3-none-any.whl", hash = "sha256:{H1}" }}]
    [[package]]
    name = "acme-secret"
    version = "9.9"
    source = {{ registry = "https://pypi.internal.example/simple" }}
    wheels = [{{ url = "https://pypi.internal.example/files/acme_secret-9.9-py3-none-any.whl", hash = "sha256:{H2}" }}]
''')


def test_tc_3_3_3_private_packages_are_marked_and_never_fetched_publicly(tmp_path):
    fs, prj = project_of(tmp_path, {"pyproject.toml": '[project]\nname = "demo"\nversion = "0"\ndependencies = ["flask", "acme-secret"]\n',
                                    "uv.lock": LOCK_PRIVATE})
    out = resolve_project(NoSandbox(), "img", fs, prj, cutoff=CUTOFF)
    assert out.status == "OK_PARTIAL" and out.private == ["acme-secret"]
    assert [p.name for p in out.pinned] == ["flask"] and "acme-secret" not in out.lock_text      # never offered to the public fetch
    assert any("PRIVATE" in w for w in out.warnings)
    assert out.provenance["lockfile"]["kind"] == "uv_lock" and len(out.provenance["lockfile"]["sha256"]) == 64


def test_tc_3_3_3_declared_private_index_without_a_lock_is_not_guessed(tmp_path):
    for i, files in enumerate(({"requirements.txt": "--extra-index-url https://pypi.internal.example/simple\nacme-secret==1\n"},
                  {"pyproject.toml": '[project]\nname="d"\nversion="0"\ndependencies=["acme-secret"]\n[[tool.uv.index]]\nname="int"\nurl="https://pypi.internal.example/simple"\n'})):
        fs, prj = project_of(tmp_path / f"case{i}", files)
        out = resolve_project(NoSandbox(), "img", fs, prj, cutoff=CUTOFF)                  # NoSandbox: nothing was queried at all
        assert out.status == "FAILED" and out.failure["reason"] == "private_index_without_lock" and out.pinned == []


def test_hash_pinned_requirements_file_counts_as_a_lock_and_dev_files_are_excluded(tmp_path):
    fs, prj = project_of(tmp_path, {"requirements.lock.txt": f"Flask==2.2.2 --hash=sha256:{H1}\nwerkzeug==2.2.2 --hash=sha256:{H2}\n",
                                    "requirements-dev.txt": "pytest==8.0.0\n", "requirements.in": "flask\n"})
    out = resolve_project(NoSandbox(), "img", fs, prj, cutoff=CUTOFF)
    assert out.status == "OK" and out.source == "lockfile" and [p.name for p in out.pinned] == ["flask", "werkzeug"]
    assert out.provenance["lockfile"]["kind"] == "requirements_lock"


def test_broken_or_stale_locks_fail_instead_of_falling_back(tmp_path):
    fs, prj = project_of(tmp_path / "a", {"pyproject.toml": '[project]\nname="d"\nversion="0"\ndependencies=["flask"]\n', "uv.lock": "version = 99\n"})
    out = resolve_project(NoSandbox(), "img", fs, prj, cutoff=CUTOFF)
    assert out.status == "FAILED" and out.failure["reason"] == "lock_unsupported"
    stale = LOCK_PRIVATE.replace('dependencies = [{ name = "flask" }, { name = "acme-secret" }]', 'dependencies = [{ name = "flask" }]')
    fs, prj = project_of(tmp_path / "b", {"pyproject.toml": '[project]\nname="demo"\nversion="0"\ndependencies=["flask","requests"]\n', "uv.lock": stale})
    out = resolve_project(NoSandbox(), "img", fs, prj, cutoff=CUTOFF)                        # declared `requests` is absent from the lock
    assert out.status == "FAILED" and out.failure["reason"] == "lock_missing_declared" and "requests" in out.failure["detail"]


def test_markers_exclude_packages_that_do_not_apply_on_linux(tmp_path):
    lock = LOCK_PRIVATE.replace('{ name = "acme-secret" }', '{ name = "pywin32", marker = "sys_platform == \'win32\'" }') + textwrap.dedent(f'''
        [[package]]
        name = "pywin32"
        version = "306"
        source = {{ registry = "https://pypi.org/simple" }}
        wheels = [{{ url = "https://files.pythonhosted.org/pywin32-306-cp312-cp312-win_amd64.whl", hash = "sha256:{H2}" }}]
    ''')
    fs, prj = project_of(tmp_path, {"pyproject.toml": '[project]\nname = "demo"\nversion = "0"\ndependencies = ["flask"]\n', "uv.lock": lock})
    out = resolve_project(NoSandbox(), "img", fs, prj, cutoff=CUTOFF)
    assert out.status == "OK" and [p.name for p in out.pinned] == ["flask"]


# ----------------------------------------------------------------------------- TC-3.3.4 hash mismatch blocks use

@pytest.mark.docker
def test_tc_3_3_4_a_wheel_that_does_not_match_its_hash_blocks_the_world(tmp_path, sbx, image):
    wrong = "0" * 64
    lock = textwrap.dedent(f'''
        version = 1
        requires-python = ">=3.12"
        [[package]]
        name = "demo"
        version = "0"
        source = {{ virtual = "." }}
        dependencies = [{{ name = "itsdangerous" }}]
        [[package]]
        name = "itsdangerous"
        version = "2.2.0"
        source = {{ registry = "https://pypi.org/simple" }}
        wheels = [{{ url = "https://files.pythonhosted.org/itsdangerous-2.2.0-py3-none-any.whl", hash = "sha256:{wrong}" }}]
    ''')
    fs, prj = project_of(tmp_path, {"pyproject.toml": '[project]\nname = "demo"\nversion = "0"\ndependencies = ["itsdangerous"]\n', "uv.lock": lock})
    out = resolve_project(NoSandbox(), "img", fs, prj, cutoff=CUTOFF)
    assert out.status == "OK"                                                                # the lock is readable; the artifact decides
    with pytest.raises(WorldBuildError) as ei:
        WorldBuilder(sbx, image).materialize(out.lock_text)
    assert ei.value.details["reason"] == "hash_mismatch"


def test_requirements_next_to_a_described_project_are_not_its_runtime_world(tmp_path):
    """Flask-style layout: [project] dependencies are the runtime world; requirements/*.txt are dev, docs and typing pins."""
    from faultline.resolvers.python import _declared
    files = {"pyproject.toml": '[project]\nname = "app"\nversion = "1"\ndependencies = ["werkzeug>=3"]\n',
             "requirements/tests.txt": "pytest==8.0.0\n", "requirements/build.txt": "build==1.2.1\n",
             "requirements/typing.txt": "mypy==1.9.0\n", "requirements-dev.txt": "ruff\n"}
    fs, prj = project_of(tmp_path, files)
    deps, _cons, _meta, _problems = _declared(prj, fs)
    assert [d.name for d in deps] == ["werkzeug"]
