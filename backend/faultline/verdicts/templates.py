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


NOT_CHECKED_BIND = (
    "O-bind checks that each call shape still binds to the current signature; it does not execute the call",
    "call sites with star arguments, dynamic or unresolved targets, and method calls on instances are not checked",
)

NOT_CHECKED_LIVE = (
    "static API and usage exposure were not analysed",
    "the artifact's own tests (O-tests) were not run unless listed as exercised",
    "data-contract replay was not run",
    "consumers and dependency worlds other than the ones named were not analysed",
)


def live_headline(outcome: str, *, artifact: str, consumers: list[str], entry: str | None = None, exc: str | None = None,
                  message: str | None = None, exercised: tuple[str, ...] = (), reasons: tuple[str, ...] = (),
                  not_checked: tuple[str, ...] = NOT_CHECKED_LIVE, site: dict | None = None) -> str:
    who = ", ".join(consumers) or "the consumer"
    if outcome == "BREAK_WITNESSED" and site:
        shape = ", ".join([*(["..."] * site["n_positional"]), *(f"{k}=..." for k in site["keyword_names"])])
        return (f"Reproduced: the call `{site['callee']}({shape})` at {site['id']} no longer binds to its signature and fails with `{exc}: {message}` when "
                f"{artifact} runs with the dependencies of {who}. It binds with {artifact}'s own dependencies. 3 of 3 fresh runs on each side. "
                "The call was checked by binding its shape to the signature; it was not executed.")
    if outcome == "BREAK_WITNESSED":
        return (f"Reproduced: importing `{entry}` fails with `{exc}: {message}` when {artifact} runs with the dependencies of {who}. "
                f"It passes with {artifact}'s own dependencies. 3 of 3 fresh runs on each side.")
    if outcome == "NO_DIVERGENCE_OBSERVED":
        return (f"No difference observed in {len(exercised)} exercised interaction(s) ({', '.join(exercised)}) between {artifact}'s own "
                f"dependencies and those of {who}. Not checked: {'; '.join(not_checked)}. This is not a statement that they are compatible.")
    if outcome == "NOT_APPLICABLE":
        return f"{who} does not use any part of {artifact} whose dependencies are present in its world, so there was nothing to check."
    if outcome == "NO_DRIFT":
        return f"{who} resolves exactly the dependency world {artifact} was checked with. Nothing differs."
    if outcome == "HYGIENE":
        return f"{who} and {artifact} are not related by evidence strong enough for a finding; recorded for inventory only."
    if outcome in ("EXPOSED", "POTENTIAL", "NOT_EXPOSED", "SILENT_DIVERGENCE_WITNESSED"):
        return f"{outcome.replace('_', ' ').title()}: see the scoped evidence for {artifact} with {who}."
    why = "; ".join(reasons) or "insufficient evidence"
    return f"Could not check {artifact} against the dependencies of {who}: {why}."
