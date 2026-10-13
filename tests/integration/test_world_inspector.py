"""M3.5: the inspector API shows declared range, resolved version and visible version separately; failures are not empty worlds."""
import pytest

from faultline.analysis.repository import analyze_repository
from faultline.ingestion import service
from tests.gitremote import Remote
from tests.integration.test_ingestion import make_fake_github

pytestmark = pytest.mark.docker


@pytest.fixture
def analysed(client, conn, sbx, image, daemon):
    r = Remote(daemon.store.remote_dir("rm_inspect"))
    sha = r.commit({
        "good": {"pyproject.toml": b'[project]\nname = "good-svc"\nversion = "1.0"\ndependencies = ["flask>=2.2,<2.3"]\n',
                 "good": {"__init__.py": b""}},
        "bad": {"requirements.txt": b"--extra-index-url https://pypi.internal.example/simple\nacme-private==1.0\n"},
        "empty": {"pyproject.toml": b'[tool.ruff]\nline-length = 100\n', "setup.py": b"from setuptools import setup\nsetup()\n"},
    })
    pid = service.create_project(conn, "p")
    rid, _, _ = service.add_repository(conn, make_fake_github({"main": sha}), pid, "https://github.com/o/rm_inspect")
    service.ingest(conn, sbx, image, daemon.store, rid, remote="rm_inspect")
    result = analyze_repository(conn, sbx, image, daemon.store, rid)
    return client, rid, result


def test_tc_3_5_1_three_views_of_a_version(analysed):
    client, rid, result = analysed
    projects = {p["rel_path"]: p for p in client.get(f"/api/repositories/{rid}/projects").json()}
    good = projects["good"]["world"]
    assert good["status"] == "OK" and good["source"] == "resolver" and good["world_hash"]
    flask = next(p for p in good["packages"] if p["name"] == "flask")
    assert flask["declared"][0]["spec"] == "<2.3,>=2.2" and flask["declared"][0]["origin"] == "good/pyproject.toml"
    assert flask["resolved"].startswith("2.2.") and flask["resolved"] not in ("2.2", "2.3")      # the version the resolver chose
    assert flask["visible"] == flask["resolved"] and flask["visible_source"] == "built_world"      # read from the installed world
    transitive = next(p for p in good["packages"] if p["name"] == "werkzeug")
    assert transitive["declared"] == [] and transitive["resolved"]                                  # nobody declared it: shown as transitive
    r = good["reproducibility"]
    assert r["cutoff"] and r["platform"] == "x86_64-unknown-linux-gnu" and r["resolver_version"].startswith("uv ") and "--no-build" in r["flags"]
    assert projects["good"]["name"] == "good-svc" and projects["good"]["origin"] == "pyproject"


def test_tc_3_5_2_failed_resolution_is_a_failure_not_an_empty_world(analysed):
    client, rid, _ = analysed
    projects = {p["rel_path"]: p for p in client.get(f"/api/repositories/{rid}/projects").json()}
    bad = projects["bad"]["world"]
    assert bad["status"] == "FAILED" and bad["packages"] == [] and bad["world_hash"] is None
    assert bad["failure"]["reason"] == "private_index_without_lock" and bad["failure"]["code"] == "RESOLUTION_FAILED"
    assert projects["bad"]["origin"] == "requirements_only"
    empty = projects["empty"]["world"]
    assert empty["status"] == "FAILED" and empty["failure"]["reason"] == "setup_py_not_executed"               # a setup.py project is not read, so not clean
    assert any("never executed" in n for n in projects["empty"]["notes"])


def test_analyze_endpoint_queues_a_job_only_for_an_ingested_repository(client, conn):
    pid = service.create_project(conn, "p")
    sha = "e" * 40
    rid, _, _ = service.add_repository(conn, make_fake_github({"main": sha}), pid, "https://github.com/o/pending")
    assert client.post(f"/api/repositories/{rid}/analyze").status_code == 409
    conn.execute("UPDATE repository SET status='INGESTED' WHERE id=?", (rid,))
    j = client.post(f"/api/repositories/{rid}/analyze")
    assert j.status_code == 202 and j.json()["kind"] == "analyze_repository"
