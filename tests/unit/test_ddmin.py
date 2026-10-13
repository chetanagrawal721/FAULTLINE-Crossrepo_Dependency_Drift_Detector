"""M5.1: ddmin on mock oracles."""
import itertools

from faultline.attribution.ddmin import Budget, Outcome, ddmin

ITEMS = list("abcdefgh")


def oracle(fails):
    """fails(subset) -> True when the subset reproduces the failure."""
    calls = []

    def t(s):
        calls.append(frozenset(s))
        return Outcome.FAIL if fails(frozenset(s)) else Outcome.PASS
    t.calls = calls
    return t


def one_minimal(result_set, fails, items=ITEMS):
    return fails(frozenset(result_set)) and all(not fails(frozenset(result_set) - {x}) for x in result_set)


def test_tc_5_1_1_single_cause():
    fails = lambda s: "e" in s  # noqa: E731
    r = ddmin(ITEMS, oracle(fails))
    assert r.minimal == ("e",) and r.status == "COMPLETE" and not r.non_monotonic and one_minimal(r.minimal, fails)
    assert r.tests <= len(ITEMS) + 1                                                     # singleton pre-check, then the full-delta check


def test_tc_5_1_1_two_interacting_causes_are_found_together():
    fails = lambda s: {"b", "g"} <= s  # noqa: E731
    r = ddmin(ITEMS, oracle(fails))
    assert set(r.minimal) == {"b", "g"} and r.status == "COMPLETE" and one_minimal(r.minimal, fails) and not r.non_monotonic


def test_tc_5_1_1_three_way_interaction_and_many_items():
    items = [f"p{i:02d}" for i in range(24)]
    fails = lambda s: {"p03", "p11", "p20"} <= s  # noqa: E731
    r = ddmin(items, oracle(fails), Budget(max_tests=1000))
    assert set(r.minimal) == {"p03", "p11", "p20"} and one_minimal(r.minimal, fails)
    assert r.tests < 2 ** 8                                                              # far fewer than testing all subsets


def test_tc_5_1_1_no_cause_returns_empty():
    r = ddmin(ITEMS, oracle(lambda s: False))
    assert r.minimal is None and r.status == "NO_CAUSE"
    assert ddmin([], oracle(lambda s: True)).minimal is None


def test_tc_5_1_1_several_independent_causes_are_reported_as_alternatives():
    r = ddmin(ITEMS, oracle(lambda s: bool({"c", "f"} & s)))
    assert r.minimal == ("c",) and r.alternatives == [("f",)]


def test_tc_5_1_1_non_monotonic_oracle_is_flagged():
    # fails only for exactly {d}: adding anything makes it pass again
    fails = lambda s: s == frozenset({"d"})  # noqa: E731
    r = ddmin(ITEMS, oracle(fails))
    assert r.minimal == ("d",) and r.non_monotonic is True


def test_unresolved_subsets_never_count_as_failing():
    def t(s):
        return Outcome.UNRESOLVED if "x" in s and len(s) == 1 else (Outcome.FAIL if {"x", "y"} <= s else Outcome.PASS)
    r = ddmin(["x", "y", "z"], t)
    assert set(r.minimal) == {"x", "y"} and r.unresolved >= 1


def test_tc_5_1_5_budget_exhaustion_is_reported_with_the_best_subset_so_far():
    fails = lambda s: {"b", "g"} <= s  # noqa: E731
    r = ddmin(ITEMS, oracle(fails), Budget(max_tests=11))
    assert r.status == "BUDGET_LIMITED" and r.tests == 11
    if r.minimal is not None:
        assert fails(frozenset(r.minimal)) and len(r.minimal) <= len(ITEMS)             # a real failing subset, not claimed minimal
    zero = ddmin(ITEMS, oracle(fails), Budget(max_tests=2))
    assert zero.status == "BUDGET_LIMITED" and zero.minimal is None


def test_exhaustive_check_that_the_result_is_always_one_minimal():
    items = list("abcd")
    for target in [set(c) for n in (1, 2, 3) for c in itertools.combinations(items, n)]:
        fails = lambda s, t=target: t <= s  # noqa: E731
        r = ddmin(items, oracle(fails))
        assert set(r.minimal) == target
