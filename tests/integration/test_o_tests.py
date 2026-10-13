"""M1.5: O-tests with the test-only overlay (TC-1.5.1 to TC-1.5.3). Real Docker, real wheels, real pytest runs."""
import pytest

from faultline.core.enums import FailureClass, Scope
from faultline.oracles.o_tests import run_o_tests
from faultline.resolvers.pinned import canonical_name
from faultline.storage import worlds as world_store
from faultline.worlds.overlay import overlay_lock

pytestmark = pytest.mark.docker
TOP = "acme_models"


def exec_tests(env, world):
    return run_o_tests(env.sbx, env.image, world_hash=env.worlds[world].world_hash, artifact_hash=env.artifact,
                       top_level=TOP)


def by_id(run):
    return {e.entry: e for e in run.entries}


def test_tc_1_5_1_per_test_differential(env):
    ref = exec_tests(env, "ref+tests")
    test = exec_tests(env, "notify_d+tests")

    r, t = by_id(ref), by_id(test)
    assert set(r) == set(t) == {"test_customer.py::test_round_trip", "test_customer.py::test_default_points",
                                "test_web.py::test_show_customer"}
    assert ref.failure_class == FailureClass.NONE and all(e.passed and not e.skipped for e in ref.entries)

    # same artifact revision, same tests; only the world differs
    assert t["test_customer.py::test_round_trip"].passed and t["test_customer.py::test_default_points"].passed
    web = t["test_web.py::test_show_customer"]
    assert web.passed is False and web.failure_class == FailureClass.ARTIFACT_FAILURE
    assert web.exc_type == "ImportError" and "url_quote" in web.message
    assert web.frames and web.frames[-1]["module"].startswith("flask")
    assert test.failure_class == FailureClass.ARTIFACT_FAILURE


def test_tc_1_5_1_tests_for_an_absent_extra_are_skipped_not_failed(env):
    run = exec_tests(env, "billing_h+tests")           # no Flask in this world
    e = by_id(run)
    assert e["test_web.py::test_show_customer"].skipped is True and e["test_web.py::test_show_customer"].passed
    assert e["test_customer.py::test_round_trip"].passed and not e["test_customer.py::test_round_trip"].skipped
    assert run.failure_class == FailureClass.NONE


def test_tc_1_5_2_overlay_does_not_change_runtime_versions(env):
    for name in ("ref", "notify_d", "billing_h"):
        runtime, ov = env.worlds[name], env.worlds[name + "+tests"]
        assert runtime.world_hash != ov.world_hash                          # overlay is a different world
        before = {(e.name, e.version) for e in runtime.entries}
        after_runtime = {(e.name, e.version) for e in ov.entries if e.scope == Scope.RUNTIME}
        assert after_runtime == before                                      # runtime packages untouched
        assert {e.name for e in ov.entries if e.scope == Scope.TEST} == set(env.overlays[name].test_packages) != set()
        assert env.overlays[name].forced is False
    # what is really installed in the built overlay world equals runtime + test packages, nothing else
    info = env.builder.info(env.worlds["notify_d+tests"])
    installed = {(canonical_name(n), v) for n, v in info["info"]["packages"]}
    assert installed == {(e.name, e.version) for e in env.worlds["notify_d+tests"].entries}
    # persisted with scopes, so the world inspector can tell runtime from test-only
    scopes = {r["scope"] for r in env.conn.execute(
        "SELECT scope FROM world_entry WHERE world_hash=?", (env.worlds["notify_d+tests"].world_hash,))}
    assert scopes == {"runtime", "test"}
    assert world_store.venv_status(env.conn, env.worlds["notify_d+tests"].world_hash).value == "BUILT"


def test_tc_1_5_2_conflicting_overlay_keeps_runtime_and_is_flagged_forced():
    h = "a" * 64
    runtime = f"packaging==20.0 --hash=sha256:{h}\nflask==2.2.2 --hash=sha256:{h}\n"
    tests = f"packaging==24.0 --hash=sha256:{h}\npytest==8.3.3 --hash=sha256:{h}\n"
    ov = overlay_lock(runtime, tests)
    assert ov.forced is True and ov.conflicts == (("packaging", "20.0", "24.0"),)
    assert "packaging==20.0" in ov.lock_text and "packaging==24.0" not in ov.lock_text      # runtime wins
    assert ov.test_packages == ("pytest",)


def test_tc_1_5_3_missing_pytest_is_a_harness_failure_not_a_break(env):
    run = exec_tests(env, "notify_d")                  # the runtime world WITHOUT the test overlay
    assert run.failure_class == FailureClass.HARNESS_FAILURE
    assert run.entries == () and "pytest is not installed" in run.data["harness_error"]
    assert all(e.failure_class != FailureClass.ARTIFACT_FAILURE for e in run.entries)


def test_o_tests_runs_are_fresh_and_independent(env):
    a, b = exec_tests(env, "ref+tests"), exec_tests(env, "ref+tests")
    assert a.run_id != b.run_id and a.provenance.value == "FRESH_EXECUTION"
    assert [e.passed for e in a.entries] == [e.passed for e in b.entries]


def test_a_test_that_writes_files_runs_in_a_scratch_copy(env):
    """The artifact mount is read-only; tests execute from a writable tmpfs copy."""
    run = exec_tests(env, "ref+tests")
    assert run.failure_class == FailureClass.NONE and run.data["returncode"] == 0
