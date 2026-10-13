"""Failure classification: only failures of the artifact or its world may ever become evidence (TC-1.4.2)."""
import pytest

from faultline.core.enums import FailureClass as F
from faultline.oracles.classify import classify_entry, classify_run
from faultline.oracles.o_import import plan_modules

TOP = "acme_models"


def fail(exc, frames=None, **kw):
    return {"passed": False, "exc_type": exc, "frames": frames or [{"module": "flask.helpers"}], **kw}


def test_pass_is_none():
    assert classify_entry({"passed": True}, TOP) == (F.NONE, False)


def test_import_error_inside_the_world_is_an_artifact_failure():
    assert classify_entry(fail("ImportError"), TOP) == (F.ARTIFACT_FAILURE, False)


def test_error_in_harness_code_is_a_harness_failure_never_a_break():
    assert classify_entry(fail("TypeError", frames=[{"module": "importlib"}, {"module": "faultline_harness"}]), TOP) == (F.HARNESS_FAILURE, False)
    assert classify_entry(fail("ChildCrash"), TOP)[0] == F.HARNESS_FAILURE
    assert classify_entry(fail("TimeoutExpired"), TOP)[0] == F.HARNESS_FAILURE


@pytest.mark.parametrize("exc", ["gaierror", "ConnectionRefusedError", "URLError", "MaxRetryError"])
def test_network_errors_need_external_resources(exc):
    assert classify_entry(fail(exc), TOP)[0] == F.NEEDS_EXTERNAL


def test_missing_third_party_package_is_not_applicable_not_a_failure():
    assert classify_entry(fail("ModuleNotFoundError", missing="flask"), TOP) == (F.NONE, True)
    assert classify_entry(fail("ModuleNotFoundError", missing="flask.helpers"), TOP) == (F.NONE, True)


def test_missing_artifact_internal_module_is_a_real_failure():
    assert classify_entry(fail("ModuleNotFoundError", missing="acme_models.nonexistent"), TOP) == (F.ARTIFACT_FAILURE, False)


def test_run_class_precedence():
    assert classify_run("NONE", [F.NONE, F.ARTIFACT_FAILURE]) == F.ARTIFACT_FAILURE
    assert classify_run("NONE", [F.ARTIFACT_FAILURE, F.HARNESS_FAILURE]) == F.HARNESS_FAILURE
    assert classify_run("NONE", [F.NEEDS_EXTERNAL, F.ARTIFACT_FAILURE]) == F.NEEDS_EXTERNAL
    assert classify_run("NONE", [F.NONE]) == F.NONE
    for sandbox_level in ("TIMEOUT", "RESOURCE_LIMIT", "SANDBOX_FAILURE", "HARNESS_FAILURE"):
        assert classify_run(sandbox_level, [F.ARTIFACT_FAILURE]).value == sandbox_level   # infrastructure always wins


def test_plan_modules_dedupes_and_keeps_top_level_first():
    assert plan_modules("a", ["a.x", "a", "a.y", "a.x"]) == ["a", "a.x", "a.y"]
