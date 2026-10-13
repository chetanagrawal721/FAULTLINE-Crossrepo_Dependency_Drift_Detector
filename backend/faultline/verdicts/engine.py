"""Verdicts for the fixture pipeline (Phase 1 SUBSET of the master decision table).

Only what Phase 1 can know: a witnessed break, no divergence observed (scoped), or inconclusive. The full ordered
table (EXPOSED, POTENTIAL, NOT EXPOSED, HYGIENE, ...) arrives with milestone M4.5. This function is deterministic and
reads only persisted evidence: no LLM input, no randomness, no clock.
"""
from dataclasses import dataclass

from ..core.enums import Verdict
from ..witnesses.verify import Decision, EntryDecision, Verification

POLICY_VERSION = "verdict-policy/0-fixture"
PRIORITY = {Verdict.BREAK_WITNESSED: 1, Verdict.SILENT_DIVERGENCE_WITNESSED: 2, Verdict.INCONCLUSIVE: 6,
            Verdict.NO_DIVERGENCE_OBSERVED: 7}


@dataclass(frozen=True)
class VerdictResult:
    verdict: Verdict
    exercised: tuple[str, ...]
    not_applicable: tuple[str, ...]
    reasons: tuple[str, ...]
    witness_entries: tuple[str, ...]


def fixture_verdict(v: Verification) -> VerdictResult:
    decisions: list[EntryDecision] = v.decisions
    witness = tuple(d.entry for d in decisions if d.decision == Decision.WITNESS)
    exercised = tuple(d.entry for d in decisions if d.decision in (Decision.WITNESS, Decision.NO_DIVERGENCE))
    na = tuple(d.entry for d in decisions if d.decision == Decision.NOT_APPLICABLE)
    bad = [d for d in decisions if d.decision in (Decision.INCONCLUSIVE, Decision.REUSED_ONLY, Decision.NOT_EXERCISED)]
    reasons = tuple(f"{d.entry}: {d.reason}" for d in bad) + ((f"run problem: {v.problem}",) if v.problem else ())
    if witness:
        return VerdictResult(Verdict.BREAK_WITNESSED, exercised, na, reasons, witness)
    discarded = [d for d in decisions if d.decision == Decision.DISCARDED]
    if v.problem or bad or discarded or not exercised:
        extra = tuple(f"{d.entry}: {d.reason}" for d in discarded)
        return VerdictResult(Verdict.INCONCLUSIVE, exercised, na, reasons + extra or ("no interaction could be exercised",), ())
    return VerdictResult(Verdict.NO_DIVERGENCE_OBSERVED, exercised, na, (), ())


# ---------------------------------------------------------------------------------------------------------------
# The full ordered decision table (master section 30.2). Pure function of persisted evidence: no LLM, no clock, no randomness.
# ---------------------------------------------------------------------------------------------------------------

LIVE_POLICY_VERSION = "verdict-policy/1"
OUTCOMES = ("HYGIENE", "NO_DRIFT", "NOT_APPLICABLE", *(v.value for v in Verdict))
LIVE_PRIORITY = {Verdict.BREAK_WITNESSED: 1, Verdict.SILENT_DIVERGENCE_WITNESSED: 2, Verdict.EXPOSED: 3, Verdict.POTENTIAL: 4,
                 Verdict.INCONCLUSIVE: 6, Verdict.NO_DIVERGENCE_OBSERVED: 7, Verdict.NOT_EXPOSED: 8, Verdict.HYGIENE: 9}
ACTIONABLE_LEVELS = ("L2", "L3", "L4", "L5")


@dataclass(frozen=True)
class Evidence:
    """Everything the decision table may look at. Fields the pipeline did not compute stay None: they never default to a pass."""
    relationship_level: str
    cell_state: str                                   # NO_DRIFT | PENDING | ANALYZED | NOT_APPLICABLE | INCONCLUSIVE
    decisions: tuple[EntryDecision, ...] = ()
    run_problem: str | None = None
    silent_entries: tuple[str, ...] = ()              # SILENT_DIVERGENCE witnesses (contract replay; not built in the MVP)
    exposures: tuple[str, ...] | None = None          # static exposures; None = static analysis was not run
    exposures_all_exercised: bool | None = None
    exposures_all_matched: bool | None = None
    static_confirmed: bool = False                    # typecheck or binding simulation failed
    api_delta_breaking: bool | None = None            # None = ApiDelta was not computed
    dynamic_refs: bool | None = None
    coverage: float | None = None
    coverage_threshold: float = 0.8


@dataclass(frozen=True)
class Outcome:
    outcome: str                                      # one of OUTCOMES
    rule: int                                         # the decision-table row that fired
    reasons: tuple[str, ...] = ()
    sub_label: str | None = None
    exercised: tuple[str, ...] = ()
    not_applicable: tuple[str, ...] = ()
    witness_entries: tuple[str, ...] = ()
    coverage: float | None = None

    @property
    def verdict(self) -> Verdict | None:
        return Verdict(self.outcome) if self.outcome in {v.value for v in Verdict} else None


def decide(ev: Evidence) -> Outcome:
    d = ev.decisions
    witnesses = tuple(x.entry for x in d if x.decision == Decision.WITNESS)
    exercised = tuple(x.entry for x in d if x.decision in (Decision.WITNESS, Decision.NO_DIVERGENCE))
    na = tuple(x.entry for x in d if x.decision == Decision.NOT_APPLICABLE)
    problems = tuple(f"{x.entry}: {x.reason}" for x in d if x.decision in (Decision.INCONCLUSIVE, Decision.REUSED_ONLY, Decision.NOT_EXERCISED,
                                                                          Decision.DISCARDED))
    if ev.run_problem:
        problems += (f"run problem: {ev.run_problem}",)
    common = {"exercised": exercised, "not_applicable": na}
    if ev.relationship_level not in ACTIONABLE_LEVELS:                                               # 0
        return Outcome("HYGIENE", 0, ("the relationship is below L2: inventory only, no finding",), **common)
    if ev.cell_state == "NO_DRIFT":                                                                  # 1
        return Outcome("NO_DRIFT", 1, ("the consumer's projection equals the reference world",), **common)
    if d and len(na) == len(d) and not witnesses:                                                    # 2
        return Outcome("NOT_APPLICABLE", 2, ("the consumer uses no module whose dependencies are present in its world",), **common)
    if witnesses:                                                                                    # 3
        return Outcome("BREAK_WITNESSED", 3, problems, witness_entries=witnesses, **common)
    if ev.silent_entries:                                                                            # 4
        return Outcome("SILENT_DIVERGENCE_WITNESSED", 4, problems, witness_entries=ev.silent_entries, **common)
    if ev.exposures:                                                                                 # 5 and 6
        if ev.exposures_all_exercised and ev.exposures_all_matched:
            return Outcome("NO_DIVERGENCE_OBSERVED", 5, (), **common)
        return Outcome("EXPOSED", 6, problems or ("exposed interactions were not all exercised",),
                       sub_label="static-confirmed" if ev.static_confirmed else None, **common)
    if ev.api_delta_breaking and ev.dynamic_refs:                                                    # 7
        return Outcome("POTENTIAL", 7, ("breaking API changes exist and dynamic references could not be resolved",), **common)
    if ev.api_delta_breaking is not None and ev.exposures is not None and not ev.exposures \
            and ev.coverage is not None and ev.coverage >= ev.coverage_threshold:                    # 8
        return Outcome("NOT_EXPOSED", 8, (), coverage=ev.coverage, **common)
    if ev.exposures is None and exercised and not problems and not ev.run_problem:                   # MVP: rules 5-8 are not reachable
        return Outcome("NO_DIVERGENCE_OBSERVED", 5, (), sub_label="oracle-only", **common)
    return Outcome("INCONCLUSIVE", 9, problems or ("no interaction could be exercised",), **common)  # 9
