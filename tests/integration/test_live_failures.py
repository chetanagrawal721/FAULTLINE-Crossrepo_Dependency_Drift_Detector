"""M4.4: oracle planning short-circuit and infrastructure failures that must never become evidence."""
import subprocess
import threading
import time

import pytest

from faultline.analysis.live import retrying
from faultline.core.enums import FailureClass, RunProvenance
from faultline.core.models import EntryOutcome, OracleRunResult
from faultline.oracles import planner
from faultline.witnesses.verify import Decision, Verification, decide_entry
from tests.conftest import labelled_containers
from tests.unit.test_witness_decision import NAME, bad, ok, runs


def test_tc_4_4_2_a_failing_top_level_import_blocks_downstream_oracles():
    steps = planner.plan(NAME, [NAME, "acme_models.web"], has_tests=True, test_lock=True, bind_sites=2, contract_types=1)
    assert [s.oracle for s in steps] == ["o_import", "o_tests", "o_bind", "o_contract"] and [s.status for s in steps] == ["PLANNED"] * 4
    assert planner.plan(NAME, [NAME], has_tests=True, test_lock=True)[2].status == "NOT_PLANNED"                        # no call site into a differing package: O-bind is not planned
    witness = decide_entry(NAME, runs("ref", [ok()] * 3), runs("test", [bad()] * 3))
    assert witness.decision == Decision.WITNESS
    after = planner.after_import(steps, NAME, Verification([], [], [witness]))
    assert after[0].status == "RAN"
    assert after[1].status == "BLOCKED" and after[1].reason.startswith("blocked_by_import") and NAME in after[1].reason
    assert after[2].status == "BLOCKED" and after[2].reason.startswith("blocked_by_import")                           # O-bind is blocked the same way: one cause is not reported twice
    # a passing top-level import blocks nothing, and a missing test lock is reported, not silently skipped
    fine = decide_entry(NAME, runs("ref", [ok()] * 3), runs("test", [ok()] * 3))
    assert planner.after_import(steps, NAME, Verification([], [], [fine]))[1].status == "PLANNED"
    assert planner.plan("p", ["p"], has_tests=True, test_lock=False)[1].reason.startswith("no hash-pinned test-only lock")
    assert planner.plan("p", ["p"], has_tests=False, test_lock=False)[1].reason == "the artifact has no tests directory"


def result(fc, entries=()):
    return OracleRunResult(job_id="j", run_id="r", provenance=RunProvenance.FRESH_EXECUTION, exit_code=1, duration_ms=1, failure_class=fc,
                           entries=tuple(entries), stdout_tail="", stderr_tail="")


def test_infrastructure_failures_are_retried_and_a_recovery_is_used():
    calls = []

    def flaky():
        calls.append(1)
        return result(FailureClass.SANDBOX_FAILURE) if len(calls) < 3 else result(FailureClass.NONE, [EntryOutcome(entry="m", passed=True, failure_class=FailureClass.NONE)])
    assert retrying(flaky)().failure_class == FailureClass.NONE and len(calls) == 3


def test_persistent_infrastructure_failure_is_inconclusive_never_a_witness():
    calls = []

    def dead():
        calls.append(1)
        return result(FailureClass.SANDBOX_FAILURE)
    r = retrying(dead)()
    assert r.failure_class == FailureClass.SANDBOX_FAILURE and len(calls) == 3
    from tests.unit.test_witness_decision import rec
    test_runs = [rec(i, "test", None, run_class=FailureClass.SANDBOX_FAILURE) if False else _infra_rec(i) for i in (1, 2, 3)]
    d = decide_entry("m", runs("ref", [ok()] * 3), test_runs)
    assert d.decision == Decision.INCONCLUSIVE and d.decision != Decision.WITNESS


def _infra_rec(i):
    from faultline.witnesses.runs import RunRecord
    return RunRecord(f"run{i}", f"job{i}", i, "test", "w", RunProvenance.FRESH_EXECUTION, result(FailureClass.SANDBOX_FAILURE))


@pytest.mark.docker
def test_tc_4_4_3_killing_the_container_during_a_run_is_a_sandbox_failure(probe):
    def killer():
        for _ in range(60):
            time.sleep(0.5)
            names = labelled_containers()
            if names:
                subprocess.run(["docker", "kill", names[0]], capture_output=True, timeout=30)
                return
    t = threading.Thread(target=killer, daemon=True)
    t.start()
    r = probe("sleep", {"seconds": 25}, timeout_s=60)
    t.join(timeout=30)
    assert r["failure_class"] == FailureClass.SANDBOX_FAILURE.value, r
    assert r["data"] is None and r["exit_code"] in (137, 143)
