"""M11.2: ablation arithmetic on synthetic views (the real runs are produced by scripts/run_benchmark.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.ablations import confusion, consumer_derived_only, predict  # noqa: E402
from benchmarks.ci_worlds import producer_ci_worlds  # noqa: E402


def view(verdict=None, delta=("x",), state="ANALYZED", first_failed=False, attribution=True):
    cell = {"id": "c1", "state": state, "verdict": verdict, "delta": [{"name": n} for n in delta], "attribution": {"minimal": ["x"]} if attribution else None}
    return {"cells": [cell], "_first_run_failed": {"c1": first_failed}}


ROWS = [
    {"id": "BRK", "label": "break", "evaluated": True, "view": view("BREAK_WITNESSED", first_failed=True)},
    {"id": "HARMLESS", "label": "no_break", "evaluated": True, "view": view("NO_DIVERGENCE_OBSERVED")},
    {"id": "SAME", "label": "no_break", "evaluated": True, "view": view(None, delta=(), state="NO_DRIFT")},
    {"id": "NOT-EVAL", "label": None, "evaluated": False, "view": None},
]


def test_each_configuration_is_scored_only_against_labels():
    a = confusion(ROWS, "A")
    assert (a["TP"], a["FP"], a["FN"], a["TN"], a["samples"]) == (1, 1, 0, 1, 3)       # version-only flags the harmless drift: a false positive
    d = confusion(ROWS, "D")
    assert (d["TP"], d["FN"]) == (0, 1)                                                  # the author-selected matrix misses the break
    f = confusion(ROWS, "F")
    assert (f["TP"], f["FP"], f["FN"], f["TN"]) == (1, 0, 0, 2)
    assert confusion(ROWS, "G")["TP"] == 1


def test_uncomputable_configurations_say_so_instead_of_inventing_numbers():
    for k in ("B", "C"):
        c = confusion(ROWS, k)
        assert c["computed"] is False and "not built" in c["reason"]


def test_consumer_derived_only_is_reported_even_when_zero():
    got = consumer_derived_only(ROWS)
    assert got == {"count": 1, "scenarios": ["BRK"], "denominator": 1, "meaning": got["meaning"]}
    none = consumer_derived_only([{"id": "X", "label": "break", "evaluated": True, "view": view("BREAK_WITNESSED", first_failed=False)}])
    assert none["count"] == 0 and none["denominator"] == 1                               # a zero is printed, not hidden


def test_witness_discipline_removes_a_flaky_single_run_false_positive():
    flaky = {"id": "FLAKY", "label": "no_break", "evaluated": True, "view": view("INCONCLUSIVE", first_failed=True)}
    assert predict("E", flaky["view"]) is True and predict("F", flaky["view"]) is False


def test_producer_ci_worlds_are_heuristic_and_say_so(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("matrix:\n  python-version: [3.10, 3.12]\nsteps:\n  - run: pip install pydantic==1.10.13\n")
    w = producer_ci_worlds(tmp_path)
    assert w["heuristic"] is True and w["python_versions"] == ["3.10", "3.12"] and w["pinned_installs"] == ["pydantic==1.10.13"] and "limitation" in w
    assert producer_ci_worlds(tmp_path / "nowhere")["workflows"] == []
