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
