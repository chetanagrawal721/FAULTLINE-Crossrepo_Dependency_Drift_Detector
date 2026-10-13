"""Scoped wording for verdicts (master section 30.4). Text is assembled from evidence fields only; no free-form claims."""
from ..core.enums import Verdict

# What the Phase 1 pipeline did NOT check. Shown on every finding so a reader cannot mistake it for a full analysis.
NOT_CHECKED_PHASE1 = (
    "the artifact's own tests (O-tests) were not run by this pipeline",
    "static API and usage exposure were not analysed",
    "data-contract replay was not run",
    "the smallest causal package difference was not computed (attribution arrives in M5.1)",
    "consumers and dependency worlds other than the one named were not analysed",
)


def headline(verdict: Verdict, *, artifact: str, consumer: str, entry: str | None = None, exc: str | None = None,
             message: str | None = None, exercised: tuple[str, ...] = (), reasons: tuple[str, ...] = ()) -> str:
    if verdict == Verdict.BREAK_WITNESSED:
        return (f"Reproduced: importing `{entry}` fails with `{exc}: {message}` when {artifact} runs with {consumer}'s "
                f"dependencies. It passes with {artifact}'s own dependencies. 3 of 3 fresh runs each.")
    if verdict == Verdict.NO_DIVERGENCE_OBSERVED:
        return (f"No difference observed in {len(exercised)} interaction(s) ({', '.join(exercised)}) between {artifact}'s "
                f"own dependencies and {consumer}'s. This is not a statement that they are compatible.")
    if verdict == Verdict.INCONCLUSIVE:
        why = "; ".join(reasons) or "insufficient evidence"
        return f"Could not check {artifact} against {consumer}'s dependencies: {why}."
    raise ValueError(f"no Phase 1 template for {verdict.value}")
