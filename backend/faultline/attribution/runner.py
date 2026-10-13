"""Two-sided attribution of a witnessed break to the smallest dependency difference.

Sufficiency: the reference world plus the cause reproduces the failure (exact signature).
Necessity:   the consumer world with the cause reverted no longer fails.
Both directions are tried; if one cannot be built or tested the result is PARTIAL and names the missing direction.
"""
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from ..core.enums import WorldKind
from ..core.hashing import object_hash
from ..core.models import FailureSignature, OracleRunResult
from ..oracles.o_import import run_o_import
from ..resolvers.pinned import PinnedRequirement
from ..witnesses.signature import signature_of
from ..worlds.builder import WorldBuilder, WorldBuildError
from ..worlds.forced import LABEL, ForcedWorld, force
from .ddmin import Budget, DdminResult, Outcome, ddmin


@dataclass
class Attribution:
    status: str                              # COMPLETE | PARTIAL | BUDGET_LIMITED | UNSTABLE | UNAVAILABLE
    sidedness: str                           # two_sided | one_sided | untestable
    minimal: tuple[str, ...] | None
    sufficiency: bool | None                 # True/False once tested, None when it could not be tested
    necessity: bool | None
    runs: int
    notes: list[str] = field(default_factory=list)
    alternatives: list[tuple[str, ...]] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)
    attribution_id: str | None = None

    @property
    def minimal_claim(self) -> str | None:
        """Wording rule: only a COMPLETE, two-sided attribution may be called minimal."""
        if self.status == "COMPLETE" and self.sidedness == "two_sided" and self.minimal:
            return "minimal (among the tested subsets, 1-minimal)"
        return None


def make_tester(sbx, image, store_hash: str, builder: WorldBuilder, *, entry: str, top_level: str, pythonpath: str, signature: FailureSignature,
                ref: list[PinnedRequirement], consumer: list[PinnedRequirement], log: list[dict], run: Callable[..., OracleRunResult] | None = None):
    """Returns test functions for the sufficiency (ref + S) and necessity (consumer - S) directions."""
    run = run or run_o_import

    def execute(fw: ForcedWorld) -> tuple[Outcome, str, str | None]:
        try:
            w = builder.materialize(fw.lock_text, WorldKind.FORCED)
            if builder.build(w, fw.lock_text).status == "FAILED":
                return Outcome.UNRESOLVED, "forced world could not be built offline", None
        except WorldBuildError as e:
            return Outcome.UNRESOLVED, f"forced world could not be built: {e.message}", None
        r = run(sbx, image, world_hash=w.world_hash, artifact_hash=store_hash, top_level=top_level, modules=[entry], pythonpath=(pythonpath,))
        e = next((x for x in r.entries if x.entry == entry), None)
        if e is None:
            return Outcome.UNRESOLVED, f"no result for the entry ({r.failure_class.value})", w.world_hash
        if e.passed:
            return Outcome.PASS, "entry passed", w.world_hash
        if e.not_applicable:
            return Outcome.UNRESOLVED, "a package this entry needs is absent in this forced world", w.world_hash
        sig = signature_of(e, entry)
        if sig == signature:
            return Outcome.FAIL, "witness signature reproduced exactly", w.world_hash
        return Outcome.UNRESOLVED, f"failed differently: {sig.exc_type}: {sig.message_norm[:120]}", w.world_hash

    def sufficiency(subset: frozenset[str]) -> Outcome:
        fw = force(ref, consumer, subset, "reference")
        out, note, wh = execute(fw)
        log.append({"direction": "search", "subset": sorted(subset), "world_hash": wh, "outcome": out.value, "note": note})
        return out

    def necessity(subset: frozenset[str]) -> tuple[Outcome, str, str | None]:
        return execute(force(consumer, ref, subset, "consumer"))

    return sufficiency, necessity


def attribute(sbx, image, builder: WorldBuilder, *, artifact_hash: str, entry: str, top_level: str, pythonpath: str, signature: FailureSignature,
              ref: list[PinnedRequirement], consumer: list[PinnedRequirement], delta: list[str], budget: Budget | None = None,
              run: Callable[..., OracleRunResult] | None = None) -> Attribution:
    log: list[dict] = []
    suff, nec = make_tester(sbx, image, artifact_hash, builder, entry=entry, top_level=top_level, pythonpath=pythonpath, signature=signature,
                            ref=ref, consumer=consumer, log=log, run=run)
    res: DdminResult = ddmin(delta, suff, budget)
    notes = [f"search: {res.tests} forced worlds tried over {len(delta)} differing packages; no coupled package groups were assumed",
             "forced worlds are attribution experiments, not observed environments"]
    if res.unresolved:
        notes.append(f"{res.unresolved} subsets could not be tested (build failure or a different failure); minimality holds only among testable subsets")
    if res.non_monotonic:
        notes.append("non-monotonic: a larger set containing the cause did not fail, so the result is not stable")
    if res.status == "NO_CAUSE" or res.minimal is None:
        status = "BUDGET_LIMITED" if res.status == "BUDGET_LIMITED" else "UNSTABLE"
        if res.status == "NO_CAUSE":
            notes.append("no subset of the delta reproduced the failure in the reference world")
        return Attribution(status, "untestable", None, None, None, res.tests, notes, res.alternatives, log)

    minimal = res.minimal
    # sufficiency was established by the search itself (ref + minimal failed with the exact signature); re-confirm and test necessity
    sufficient = True
    suff_world = next((x["world_hash"] for x in log if x["subset"] == sorted(minimal) and x["outcome"] == "FAIL"), None)
    log.append({"direction": "sufficiency", "subset": list(minimal), "world_hash": suff_world, "outcome": "FAIL",
                "note": "reference world plus the cause reproduces the failure with the exact witness signature"})
    n_out, n_note, n_world = nec(frozenset(minimal))
    runs = res.tests + 1
    log.append({"direction": "necessity", "subset": list(minimal), "world_hash": n_world, "outcome": n_out.value, "note": f"consumer with the cause reverted: {n_note}"})
    necessary = True if n_out == Outcome.PASS else False if n_out == Outcome.FAIL else None
    if necessary is None:
        notes.append("necessity could not be tested: " + n_note)
    elif necessary is False:
        notes.append("the failure persists with the cause reverted: other differences also reproduce it")
    sided = "two_sided" if necessary else "one_sided"
    if res.status == "BUDGET_LIMITED":
        status = "BUDGET_LIMITED"
        notes.append("the search budget ran out: this is the smallest failing subset found so far, not a proven minimum")
    elif res.non_monotonic:
        status = "UNSTABLE"
    elif necessary:
        status = "COMPLETE"
    else:
        status = "PARTIAL"
        notes.append("missing direction: " + ("necessity (revert the cause in the consumer world)" if necessary is None else "necessity did not hold"))
    return Attribution(status, sided, minimal, sufficient, necessary, runs, notes, res.alternatives, log)


def persist(conn: sqlite3.Connection, witness_id: str, a: Attribution) -> str:
    aid = "att_" + object_hash([witness_id, list(a.minimal or [])])[:24]
    conn.execute("DELETE FROM attribution_attempt WHERE attribution_id IN (SELECT id FROM attribution WHERE witness_id=?)", (witness_id,))
    conn.execute("DELETE FROM attribution WHERE witness_id=?", (witness_id,))
    conn.execute("INSERT INTO attribution(id, witness_id, status, minimal_set_json, sidedness, forced_worlds_used, runs, notes_json) VALUES (?,?,?,?,?,?,?,?)",
                 (aid, witness_id, a.status, json.dumps(list(a.minimal or [])), a.sidedness, 1, a.runs,
                  json.dumps({"notes": a.notes, "alternatives": [list(x) for x in a.alternatives], "label": LABEL,
                              "sufficiency": a.sufficiency, "necessity": a.necessity})))
    for i, att in enumerate(a.attempts, 1):
        conn.execute("INSERT INTO attribution_attempt(attribution_id, seq, direction, subset_json, world_hash, outcome, note) VALUES (?,?,?,?,?,?,?)",
                     (aid, i, att["direction"], json.dumps(att["subset"]), att["world_hash"], att["outcome"], att["note"]))
    a.attribution_id = aid
    return aid
