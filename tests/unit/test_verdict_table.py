"""M4.5: the ordered decision table (one case per row), determinism, no LLM input, scoped wording."""
import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from faultline.core.enums import Verdict
from faultline.verdicts import templates
from faultline.verdicts.engine import Evidence, decide
from faultline.witnesses.verify import Decision, EntryDecision


def d(entry, decision, reason="r"):
    return EntryDecision(entry, decision, reason)


WIT, OK, NA = Decision.WITNESS, Decision.NO_DIVERGENCE, Decision.NOT_APPLICABLE
BASE = {"relationship_level": "L2", "cell_state": "PENDING"}

CASES = [
    ("row0 below L2", {"relationship_level": "L1", "cell_state": "PENDING"}, "HYGIENE", 0),
    ("row0 L0", {"relationship_level": "L0", "cell_state": "PENDING"}, "HYGIENE", 0),
    ("row1 no drift", {**BASE, "cell_state": "NO_DRIFT"}, "NO_DRIFT", 1),
    ("row2 nothing applicable", {**BASE, "decisions": (d("a", NA), d("b", NA))}, "NOT_APPLICABLE", 2),
    ("row3 break", {**BASE, "decisions": (d("a", WIT), d("b", OK))}, "BREAK_WITNESSED", 3),
    ("row3 beats row4", {**BASE, "decisions": (d("a", WIT),), "silent_entries": ("c",)}, "BREAK_WITNESSED", 3),
    ("row4 silent", {**BASE, "decisions": (d("a", OK),), "silent_entries": ("c",)}, "SILENT_DIVERGENCE_WITNESSED", 4),
    ("row5 exposures matched", {**BASE, "decisions": (d("a", OK),), "exposures": ("x",), "exposures_all_exercised": True, "exposures_all_matched": True},
     "NO_DIVERGENCE_OBSERVED", 5),
    ("row6 exposed", {**BASE, "decisions": (d("a", OK),), "exposures": ("x",), "exposures_all_exercised": False}, "EXPOSED", 6),
    ("row6 static confirmed", {**BASE, "exposures": ("x",), "exposures_all_exercised": False, "static_confirmed": True}, "EXPOSED", 6),
    ("row7 potential", {**BASE, "api_delta_breaking": True, "dynamic_refs": True, "exposures": ()}, "POTENTIAL", 7),
    ("row8 not exposed", {**BASE, "api_delta_breaking": False, "exposures": (), "coverage": 0.9}, "NOT_EXPOSED", 8),
    ("row8 low coverage is not enough", {**BASE, "api_delta_breaking": False, "exposures": (), "coverage": 0.3}, "INCONCLUSIVE", 9),
    ("mvp oracle only", {**BASE, "decisions": (d("a", OK), d("b", OK))}, "NO_DIVERGENCE_OBSERVED", 5),
    ("unknown: nothing exercised", {**BASE}, "INCONCLUSIVE", 9),
    ("unknown: inconclusive entry", {**BASE, "decisions": (d("a", OK), d("b", Decision.INCONCLUSIVE, "flaky"))}, "INCONCLUSIVE", 9),
    ("unknown: discarded baseline", {**BASE, "decisions": (d("a", Decision.DISCARDED),)}, "INCONCLUSIVE", 9),
    ("unknown: reused only", {**BASE, "decisions": (d("a", Decision.REUSED_ONLY),)}, "INCONCLUSIVE", 9),
    ("unknown: run problem", {**BASE, "decisions": (d("a", OK),), "run_problem": "sandbox_failure"}, "INCONCLUSIVE", 9),
    ("unknown: weird state", {**BASE, "cell_state": "SOMETHING_ELSE"}, "INCONCLUSIVE", 9),
]


@pytest.mark.parametrize("name,kw,outcome,rule", CASES, ids=[c[0] for c in CASES])
def test_tc_4_5_1_every_row_and_unknown_combination(name, kw, outcome, rule):
    o = decide(Evidence(**kw))
    assert (o.outcome, o.rule) == (outcome, rule), name
    if outcome == "INCONCLUSIVE":
        assert o.reasons                                              # never an unexplained INCONCLUSIVE
    if outcome == "BREAK_WITNESSED":
        assert o.witness_entries and o.verdict == Verdict.BREAK_WITNESSED


def test_sub_labels_and_coverage_are_carried():
    assert decide(Evidence(**CASES[9][1])).sub_label == "static-confirmed"
    assert decide(Evidence(**CASES[11][1])).coverage == 0.9
    assert decide(Evidence(**CASES[13][1])).sub_label == "oracle-only"


def test_tc_4_5_2_same_evidence_gives_the_same_verdict_across_processes():
    ev = Evidence(**CASES[4][1])
    here = decide(ev)
    code = ("import json,sys; sys.path.insert(0,'backend');"
            "from faultline.verdicts.engine import Evidence, decide;"
            "from faultline.witnesses.verify import Decision, EntryDecision;"
            "ev=Evidence(relationship_level='L2',cell_state='PENDING',decisions=(EntryDecision('a',Decision.WITNESS,'r'),EntryDecision('b',Decision.NO_DIVERGENCE,'r')));"
            "o=decide(ev);print(json.dumps([o.outcome,o.rule,list(o.reasons),list(o.witness_entries)]))")
    root = Path(__file__).resolve().parents[2]
    outs = {subprocess.run([sys.executable, "-I", "-c", code], cwd=root, capture_output=True, text=True).stdout.strip() for _ in range(10)}
    assert outs == {json.dumps([here.outcome, here.rule, list(here.reasons), list(here.witness_entries)])}
    assert len({decide(ev) for _ in range(10)}) == 1


FORBIDDEN = ("anthropic", "openai", "langchain", "llama", "ollama", "google.generativeai", "mistral", "cohere", "transformers", "litellm")


def test_tc_4_5_3_the_verdict_modules_import_no_llm_client():
    base = Path(__file__).resolve().parents[2] / "backend" / "faultline" / "verdicts"
    for f in base.glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for m in mods:
                assert not any(m.lower().startswith(x) for x in FORBIDDEN), (f.name, m)


def test_tc_4_5_4_no_divergence_wording_is_scoped_and_never_says_compatible():
    text = templates.live_headline("NO_DIVERGENCE_OBSERVED", artifact="acme-models", consumers=["billing-svc"],
                                   exercised=("acme_models", "acme_models.customer"))
    assert "acme_models.customer" in text and "Not checked:" in text and "static API" in text
    low = text.lower()
    assert "not a statement that they are compatible" in low
    for outcome in ("BREAK_WITNESSED", "NO_DIVERGENCE_OBSERVED", "NOT_APPLICABLE", "NO_DRIFT", "HYGIENE", "EXPOSED", "INCONCLUSIVE"):
        t = templates.live_headline(outcome, artifact="a", consumers=["c"], entry="m", exc="E", message="x", exercised=("m",), reasons=("r",)).lower()
        assert "proof" not in t and "guarantee" not in t and "ai detected" not in t
        assert "compatible" not in t or "not a statement" in t
