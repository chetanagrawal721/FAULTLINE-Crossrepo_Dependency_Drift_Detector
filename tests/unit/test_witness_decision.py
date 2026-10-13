"""The witness predicate on synthetic runs (no Docker): every way an entry can fail to become a witness."""
from faultline.core.enums import FailureClass as F
from faultline.core.enums import RunProvenance as P
from faultline.core.models import EntryOutcome, OracleRunResult
from faultline.witnesses.runs import RunRecord
from faultline.witnesses.signature import normalize_message, signature_of
from faultline.witnesses.verify import Decision, decide_entry

NAME = "acme_models.web"
FRAMES = ({"module": "faultline_harness"}, {"module": "importlib"}, {"module": "flask.app", "line": 30, "func": "<module>"})


def ok(skipped=False):
    return EntryOutcome(entry=NAME, passed=True, skipped=skipped)


def bad(msg="cannot import name 'url_quote' from 'werkzeug.urls' (/opt/world/lib/python3.12/site-packages/werkzeug/urls.py)",
        exc="ImportError", fc=F.ARTIFACT_FAILURE, na=False):
    return EntryOutcome(entry=NAME, passed=False, exc_type=exc, message=msg, frames=FRAMES, failure_class=fc,
                        not_applicable=na)


def rec(i, side, entry, prov=P.FRESH_EXECUTION, run_class=F.NONE, entries=None):
    es = (entry,) if entry is not None else ()
    result = OracleRunResult(job_id="oj", run_id=f"run_{side}{i}", provenance=prov, exit_code=0, duration_ms=1,
                             failure_class=run_class, entries=es if entries is None else entries)
    return RunRecord(f"run_{side}{i}", "oj", i, side, "w_x", prov, result)


def runs(side, entries, **kw):
    return [rec(i, side, e, **kw) for i, e in enumerate(entries, 1)]


def decide(ref, test):
    return decide_entry(NAME, ref, test)


def test_witness_when_reference_passes_3_of_3_and_consumer_fails_3_of_3_identically():
    d = decide(runs("ref", [ok()] * 3), runs("test", [bad()] * 3))
    assert d.decision == Decision.WITNESS
    assert d.signature.exc_type == "ImportError" and d.signature.origin_package == "flask"
    assert "url_quote" in d.signature.message_norm and "/opt/world" not in d.signature.message_norm
    assert len(d.ref_run_ids) == 3 and len(d.test_run_ids) == 3


def test_reference_failing_three_times_discards_never_witnesses():
    d = decide(runs("ref", [bad()] * 3), runs("test", [bad()] * 3))
    assert d.decision == Decision.DISCARDED


def test_flaky_reference_is_inconclusive():
    assert decide(runs("ref", [ok(), bad(), ok()]), runs("test", [bad()] * 3)).decision == Decision.INCONCLUSIVE


def test_flaky_consumer_is_inconclusive():
    assert decide(runs("ref", [ok()] * 3), runs("test", [bad(), ok(), bad()])).decision == Decision.INCONCLUSIVE


def test_different_signatures_across_runs_are_not_a_witness():
    d = decide(runs("ref", [ok()] * 3), runs("test", [bad(), bad(), bad(msg="cannot import name 'other'")]))
    assert d.decision == Decision.INCONCLUSIVE and "differently" in d.reason


def test_two_failures_out_of_three_is_not_enough():
    assert decide(runs("ref", [ok()] * 3), runs("test", [bad(), bad(), ok()])).decision == Decision.INCONCLUSIVE


def test_both_pass_means_no_divergence_observed_for_this_entry():
    assert decide(runs("ref", [ok()] * 3), runs("test", [ok()] * 3)).decision == Decision.NO_DIVERGENCE


def test_cached_results_never_count_as_fresh_repeats():
    ref = runs("ref", [ok()] * 3, prov=P.REUSED_RESULT)
    test = runs("test", [bad()] * 3, prov=P.REUSED_RESULT)
    assert decide(ref, test).decision == Decision.REUSED_ONLY
    mixed = runs("ref", [ok()] * 3) + []
    assert decide(mixed, runs("test", [bad(), bad()]) + [rec(3, "test", bad(), prov=P.REUSED_RESULT)]).decision == Decision.REUSED_ONLY


def test_fewer_than_three_runs_is_inconclusive():
    assert decide(runs("ref", [ok()] * 2), runs("test", [bad()] * 2)).decision == Decision.INCONCLUSIVE


def test_infrastructure_and_harness_classes_are_never_witnesses():
    for fc in (F.HARNESS_FAILURE, F.NEEDS_EXTERNAL):
        d = decide(runs("ref", [ok()] * 3), runs("test", [bad(fc=fc)] * 3))
        assert d.decision == Decision.INCONCLUSIVE, fc
    d = decide(runs("ref", [ok()] * 3), runs("test", [None] * 3, run_class=F.TIMEOUT))
    assert d.decision == Decision.INCONCLUSIVE and d.reason == "timeout"


def test_not_applicable_and_skipped_entries_are_not_witnesses():
    d = decide(runs("ref", [ok()] * 3), runs("test", [bad(exc="ModuleNotFoundError", fc=F.NONE, na=True)] * 3))
    assert d.decision == Decision.NOT_APPLICABLE
    assert decide(runs("ref", [ok()] * 3), runs("test", [ok(skipped=True)] * 3)).decision == Decision.NOT_EXERCISED


def test_entry_missing_from_a_run_is_inconclusive():
    assert decide(runs("ref", [ok()] * 3), runs("test", [bad(), bad()]) + [rec(3, "test", None)]).decision == Decision.INCONCLUSIVE


def test_signature_normalization_removes_run_to_run_noise():
    a = normalize_message("boom at 0x7f3a1c (/opt/world/lib/python3.12/site-packages/x/y.py) in /tmp/abc123/file.py 0.0123s")
    b = normalize_message("boom at 0x55555 (/opt/world/lib/python3.12/site-packages/x/y.py) in /tmp/zzz999/file.py 0.9876s")
    assert a == b
    assert signature_of(bad(), NAME).origin_module == "flask.app"                      # harness and importlib frames skipped


def test_baseline_that_fails_its_own_import_yields_inconclusive_never_a_consumer_break():
    """TC-4.2.3: a reference world that fails the same entry is not evidence against the consumer."""
    from faultline.core.enums import Verdict
    from faultline.verdicts.engine import fixture_verdict
    from faultline.witnesses.verify import Verification
    d = decide(runs("ref", [bad()] * 3), runs("test", [bad()] * 3))
    v = Verification(ref_runs=[], test_runs=[], decisions=[d])
    assert fixture_verdict(v).verdict == Verdict.INCONCLUSIVE and fixture_verdict(v).witness_entries == ()
