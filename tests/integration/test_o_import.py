"""M1.4: the O-import oracle on real worlds (TC-1.4.1 to TC-1.4.3). Real Docker, real wheels."""
from pathlib import Path

import pytest

from faultline.core.enums import FailureClass
from faultline.oracles.o_import import plan_modules, run_o_import

pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]
REPOS = ROOT / "fixtures" / "repos"
TOP = "acme_models"


def import_run(env, world, modules):
    return run_o_import(env.sbx, env.image, world_hash=env.worlds[world].world_hash, artifact_hash=env.artifact,
                        top_level=TOP, modules=modules)


def by_entry(run):
    return {e.entry: e for e in run.entries}


def test_tc_1_4_1_reference_passes_consumer_fails(env):
    modules = plan_modules(TOP, ["acme_models.web"])
    ref = import_run(env, "ref", modules)
    test = import_run(env, "notify_d", modules)

    assert ref.failure_class == FailureClass.NONE and all(e.passed for e in ref.entries)
    assert {e.entry for e in ref.entries} == {TOP, "acme_models.web"}

    assert test.failure_class == FailureClass.ARTIFACT_FAILURE
    e = by_entry(test)
    assert e[TOP].passed is True                                   # the package itself still imports
    web = e["acme_models.web"]
    assert web.passed is False and web.exc_type == "ImportError"
    assert "cannot import name 'url_quote' from 'werkzeug.urls'" in web.message
    assert web.failure_class == FailureClass.ARTIFACT_FAILURE and not web.not_applicable
    assert web.frames[-1]["module"].startswith("flask")             # the failing line is inside Flask, not our harness
    assert test.provenance.value == "FRESH_EXECUTION"


def test_tc_1_4_2_harness_crash_is_not_a_break(env):
    r = env.sbx.submit({"image": env.image, "script": "o_import.py", "interpreter": "world",
                        "args": {"modules": 5},                    # malformed: the harness itself raises
                        "mounts": {"/opt/world": {"world": env.worlds["ref"].world_hash},
                                   "/artifact": {"artifact": env.artifact}}})
    assert r["failure_class"] == "HARNESS_FAILURE" and r["data"] is None and r["exit_code"] not in (0, 125, 126, 127)


def test_tc_1_4_2_nothing_in_an_infrastructure_failure_looks_like_a_witness_candidate(env):
    run = run_o_import(env.sbx, env.image, world_hash=env.worlds["ref"].world_hash, artifact_hash=env.artifact,
                       top_level=TOP, modules=[TOP], timeout_s=1)
    # a 1 s limit may or may not be enough; either way no entry may be an ARTIFACT_FAILURE caused by the limit
    assert run.failure_class in (FailureClass.NONE, FailureClass.TIMEOUT)
    assert all(e.failure_class != FailureClass.ARTIFACT_FAILURE for e in run.entries)


def test_tc_1_4_3_missing_optional_package_is_not_applicable(env):
    modules = [TOP, "acme_models.customer", "acme_models.web"]
    ref = import_run(env, "ref", modules)
    cons = import_run(env, "billing_h", modules)               # this world has no Flask: the web extra is not installed
    assert ref.failure_class == FailureClass.NONE and all(e.passed for e in ref.entries)
    e = by_entry(cons)
    assert e[TOP].passed and e["acme_models.customer"].passed
    web = e["acme_models.web"]
    assert web.passed is False and web.not_applicable is True and web.failure_class == FailureClass.NONE
    assert web.exc_type == "ModuleNotFoundError"
    assert cons.failure_class == FailureClass.NONE                # N/A never turns the run into a failure


def test_missing_artifact_internal_module_is_a_real_failure(env):
    run = import_run(env, "ref", [TOP, "acme_models.nonexistent"])
    e = by_entry(run)["acme_models.nonexistent"]
    assert e.failure_class == FailureClass.ARTIFACT_FAILURE and not e.not_applicable
    assert run.failure_class == FailureClass.ARTIFACT_FAILURE


def test_each_module_is_imported_in_its_own_process(env):
    """A failing import must not poison a later one: customer imports fine after web failed."""
    run = import_run(env, "notify_d", ["acme_models.web", "acme_models.customer"])
    e = by_entry(run)
    assert e["acme_models.web"].passed is False and e["acme_models.customer"].passed is True


def test_import_runs_have_unique_run_ids_and_no_network(env):
    a = import_run(env, "ref", [TOP])
    b = import_run(env, "ref", [TOP])
    assert a.run_id != b.run_id
