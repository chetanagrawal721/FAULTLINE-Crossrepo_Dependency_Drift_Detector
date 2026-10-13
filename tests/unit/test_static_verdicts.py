"""M6.4: EXPOSED, POTENTIAL and NOT EXPOSED follow the master thresholds and stay distinct from witnesses."""
from pathlib import Path

from faultline.core.enums import Verdict
from faultline.diff.delta import compute_delta
from faultline.diff.surface import extract
from faultline.usage.exposure import compute_exposure
from faultline.usage.index import build_index
from faultline.verdicts import templates
from faultline.verdicts.engine import STATIC_VERDICTS, WITNESSED_VERDICTS, Evidence, decide, evidence_kind

BASE = {"relationship_level": "L2", "cell_state": "ANALYZED"}


def test_tc_6_4_1_coverage_gate_085_is_not_enough_and_095_is_():
    low = decide(Evidence(**BASE, api_delta_breaking=False, exposures=(), coverage=0.85))
    assert low.outcome == "INCONCLUSIVE" and any("insufficient_coverage" in r for r in low.reasons) and low.coverage == 0.85
    low_breaking = decide(Evidence(**BASE, api_delta_breaking=True, exposures=(), coverage=0.85))
    assert low_breaking.outcome == "POTENTIAL" and low_breaking.coverage == 0.85                       # breaking changes exist and references are unresolved
    high = decide(Evidence(**BASE, api_delta_breaking=False, exposures=(), coverage=0.95))
    assert high.outcome == "NOT_EXPOSED" and high.rule == 8 and high.coverage == 0.95
    assert decide(Evidence(**BASE, api_delta_breaking=False, exposures=(), coverage=0.9)).outcome == "NOT_EXPOSED"      # the default threshold is 0.9, inclusive
    assert decide(Evidence(**BASE, api_delta_breaking=False, exposures=(), coverage=0.85, coverage_threshold=0.8)).outcome == "NOT_EXPOSED"   # configurable


def test_not_exposed_needs_a_computed_delta_complete_enough_to_trust():
    assert decide(Evidence(**BASE, api_delta_breaking=None, exposures=None, coverage=1.0)).outcome == "INCONCLUSIVE"        # no delta: nothing is claimed
    limited = decide(Evidence(**BASE, api_delta_breaking=False, exposures=(), coverage=1.0, static_limits=("pkg: compiled modules cannot be read",)))
    assert limited.outcome == "INCONCLUSIVE" and any("compiled modules" in r for r in limited.reasons)
    assert decide(Evidence(**BASE, api_delta_breaking=True, exposures=(), coverage=0.95, dynamic_refs=True)).outcome == "POTENTIAL"


def test_tc_6_4_2_static_evidence_alone_can_never_produce_a_witnessed_verdict():
    o = decide(Evidence(**BASE, exposures=("a.py:3:4->pkg.f",), exposures_all_exercised=False, static_confirmed=True, api_delta_breaking=True, coverage=1.0))
    assert o.outcome == "EXPOSED" and o.sub_label == "static-confirmed" and o.rule == 6 and not o.witness_entries
    assert o.verdict not in (Verdict.BREAK_WITNESSED, Verdict.SILENT_DIVERGENCE_WITNESSED)
    # every combination of static inputs, with no execution decisions: the verdict is never one of the witnessed ones
    for exposures in (None, (), ("x",)):
        for brk in (None, False, True):
            for dyn in (None, False, True):
                for cov in (None, 0.2, 0.95):
                    for confirmed in (False, True):
                        out = decide(Evidence(**BASE, exposures=exposures, api_delta_breaking=brk, dynamic_refs=dyn, coverage=cov, static_confirmed=confirmed))
                        assert out.outcome not in WITNESSED_VERDICTS and not out.witness_entries


def test_static_and_witnessed_verdicts_are_two_distinct_kinds():
    assert STATIC_VERDICTS.isdisjoint(WITNESSED_VERDICTS)
    assert {evidence_kind(v) for v in STATIC_VERDICTS} == {"STATIC"} and {evidence_kind(v) for v in WITNESSED_VERDICTS} == {"WITNESSED"}
    assert evidence_kind("NO_DIVERGENCE_OBSERVED") == "OTHER" and evidence_kind("INCONCLUSIVE") == "OTHER"


def test_static_wording_shows_coverage_and_never_claims_a_failure():
    n = templates.static_headline("NOT_EXPOSED", artifact="acme", resolved=47, total=49, examples=("plugins.py:12 getattr(pydantic, name)",))
    assert "Coverage 47/49 (95.9%)" in n and "plugins.py:12" in n
    p = templates.static_headline("POTENTIAL", artifact="acme", package="urllib3", v0="1.26.18", v1="2.2.3", n_breaking=4, n_dynamic=2, resolved=8, total=10)
    assert "urllib3 1.26.18" in p and "4 breaking change(s)" in p and "Coverage 8/10 (80.0%)" in p
    e = templates.static_headline("EXPOSED", artifact="acme", symbol="urllib3.util.retry.Retry", change_kind="SIGNATURE_BREAKING", v0="1.26.18", v1="2.2.3",
                                  reason="no oracle exercised this call")
    assert "Not executed because no oracle exercised this call" in e
    for text in (n, p, e):
        assert not any(w in text.lower() for w in ("reproduced", "witness", "compatible", "proof", "guarantee"))


def test_the_static_path_end_to_end_on_the_scenario_c_artifact():
    """acme-http's own sources against the urllib3 Retry change: the call that no longer binds is found without running anything."""
    root = Path(__file__).resolve().parents[2] / "fixtures" / "repos" / "acme-http"
    files = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*.py")}
    old = {"urllib3/__init__.py": b"from .retry import Retry\n",
           "urllib3/retry.py": b"class Retry:\n    def __init__(self, total=10, method_whitelist=None, allowed_methods=None, backoff_factor=0): pass\n"}
    new = {"urllib3/__init__.py": b"from .retry import Retry\n",
           "urllib3/retry.py": b"class Retry:\n    def __init__(self, total=10, allowed_methods=None, backoff_factor=0): pass\n"}
    delta = compute_delta(extract(old, "urllib3"), extract(new, "urllib3"))
    files = {k: v.replace(b"urllib3.util.retry", b"urllib3.retry") for k, v in files.items()}
    res = compute_exposure(build_index(files, {"urllib3"}), {"urllib3": delta})
    ev = res.evidence_fields()
    o = decide(Evidence(**BASE, **ev))
    assert o.outcome == "EXPOSED" and o.sub_label == "static-confirmed"
    bad = [e for e in res.breaking_exposures if e.static_ok is False]
    assert [(e.ref.file, e.ref.line) for e in bad] == [("src/acme_http/retry.py", 7)]               # the call with method_whitelist, and not the one that still binds
