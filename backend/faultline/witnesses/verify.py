"""The witness predicate (master Algorithm 8).

An entry (a module import, a test, ...) becomes a WITNESS only if, across independent FRESH executions:
  * the reference world passes it 3 out of 3 times, and
  * the consumer world fails it 3 out of 3 times, as an ARTIFACT_FAILURE, with one identical normalized signature.
Everything else is classified, never silently dropped: reference also fails (discarded), flaky or mixed results,
infrastructure problems, tests that did not run, and cached results that did not really execute.
"""
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from ..analysis.fixture import FixtureCell
from ..core.enums import FailureClass, RunProvenance, WitnessClass
from ..core.hashing import object_hash
from ..core.ids import new_id
from ..core.models import EntryOutcome, FailureSignature, OracleRunResult, Witness
from .runs import RunRecord, execute_run
from .signature import signature_of

K = 3
INFRA_CLASSES = {FailureClass.HARNESS_FAILURE, FailureClass.SANDBOX_FAILURE, FailureClass.TIMEOUT,
                 FailureClass.RESOURCE_LIMIT, FailureClass.BUILD_FAILURE, FailureClass.RESOLUTION_FAILURE,
                 FailureClass.UNSUPPORTED, FailureClass.NEEDS_EXTERNAL}


class Decision(StrEnum):
    WITNESS = "WITNESS"
    NO_DIVERGENCE = "NO_DIVERGENCE"            # reference passed 3/3 and the consumer passed 3/3: exercised and matched
    DISCARDED = "DISCARDED"                    # the reference itself fails: a break cannot be attributed to the consumer world
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EXERCISED = "NOT_EXERCISED"            # skipped, so nothing was learned
    REUSED_ONLY = "REUSED_ONLY"                # results came from the cache; they cannot count as fresh repeats


@dataclass(frozen=True)
class EntryDecision:
    entry: str
    decision: Decision
    reason: str
    signature: FailureSignature | None = None
    ref_run_ids: tuple[str, ...] = ()
    test_run_ids: tuple[str, ...] = ()
    witness_id: str | None = None


@dataclass
class Verification:
    ref_runs: list[RunRecord]
    test_runs: list[RunRecord]
    decisions: list[EntryDecision] = field(default_factory=list)
    problem: str | None = None      # a run-level infrastructure failure that produced no entries (e.g. harness crash)

    def decision_for(self, entry: str) -> EntryDecision:
        return next(d for d in self.decisions if d.entry == entry)

    @property
    def witnesses(self) -> list[EntryDecision]:
        return [d for d in self.decisions if d.decision == Decision.WITNESS]


def _entry(record: RunRecord, name: str) -> EntryOutcome | None:
    return next((e for e in record.result.entries if e.entry == name), None)


def decide_entry(name: str, ref: list[RunRecord], test: list[RunRecord]) -> EntryDecision:
    ref_ids, test_ids = tuple(r.run_id for r in ref), tuple(r.run_id for r in test)

    def d(decision: Decision, reason: str, sig: FailureSignature | None = None) -> EntryDecision:
        return EntryDecision(name, decision, reason, sig, ref_ids, test_ids)

    runs = ref + test
    if not all(r.fresh for r in runs):
        return d(Decision.REUSED_ONLY, "some results came from the cache; only fresh executions can count")
    if len(ref) != K or len(test) != K:
        return d(Decision.INCONCLUSIVE, f"need {K} runs per side, got {len(ref)} and {len(test)}")
    for r in runs:                                           # infrastructure taints everything it touched
        if r.result.failure_class in INFRA_CLASSES and not any(e.entry == name for e in r.result.entries):
            return d(Decision.INCONCLUSIVE, r.result.failure_class.value.lower())
    ref_e, test_e = [_entry(r, name) for r in ref], [_entry(r, name) for r in test]
    if any(e is None for e in ref_e + test_e):
        return d(Decision.INCONCLUSIVE, "entry missing from some runs")
    for e in ref_e + test_e:
        if e.failure_class in INFRA_CLASSES:
            return d(Decision.INCONCLUSIVE, e.failure_class.value.lower())
    if any(e.not_applicable for e in test_e):
        return d(Decision.NOT_APPLICABLE, "a package this entry needs is not part of the consumer world")
    if any(e.not_applicable for e in ref_e):
        return d(Decision.INCONCLUSIVE, "reference_not_applicable")
    if any(e.skipped for e in ref_e + test_e):
        return d(Decision.NOT_EXERCISED, "the entry was skipped, so nothing was observed")

    ref_pass = [e.passed for e in ref_e]
    if not all(ref_pass):
        if not any(ref_pass):
            return d(Decision.DISCARDED, "the reference world also fails: not attributable to the consumer world")
        return d(Decision.INCONCLUSIVE, "flaky: the reference world did not behave the same on every run")

    test_pass = [e.passed for e in test_e]
    if all(test_pass):
        return d(Decision.NO_DIVERGENCE, "passed 3/3 in both worlds")
    if any(test_pass):
        return d(Decision.INCONCLUSIVE, "flaky: the consumer world did not behave the same on every run")
    if any(e.failure_class != FailureClass.ARTIFACT_FAILURE for e in test_e):
        return d(Decision.INCONCLUSIVE, "consumer failures are not all artifact failures")
    sigs = [signature_of(e, name) for e in test_e]
    if len({s.model_dump_json() for s in sigs}) != 1:
        return d(Decision.INCONCLUSIVE, "flaky: the consumer failed differently on different runs")
    return d(Decision.WITNESS, "reference passed 3/3, consumer failed 3/3 with an identical signature", sigs[0])


def witness_key(cell: FixtureCell, oracle: str, version: str, entry: str, env_profile_id: str, input_hash: str | None = None) -> str:
    return "wk_" + object_hash({"artifact": cell.artifact_hash, "entry": entry, "input": input_hash,
                                "world_ref": cell.ref_world_hash, "world_test": cell.test_world_hash,
                                "env": env_profile_id, "oracle": f"{oracle}@{version}"})[:40]


DIVERGENCE = {"o_import": "IMPORT_ERROR", "o_tests": "TEST_FAIL", "o_bind": "BIND_FAIL", "o_contract": "CONTRACT_REJECTED"}
SILENT_EXC = "ValueDivergence"


def _save_witness(conn: sqlite3.Connection, cell: FixtureCell, oracle: str, version: str, dec: EntryDecision, meta: dict | None = None) -> str:
    meta = meta or {}
    key = witness_key(cell, oracle, version, dec.entry, cell.env_profile_id, meta.get("sha256"))
    silent = oracle == "o_contract" and dec.signature is not None and dec.signature.exc_type == SILENT_EXC
    existing = conn.execute("SELECT id, body_json FROM witness WHERE witness_key=?", (key,)).fetchone()
    if existing:                                             # already witnessed: record the re-verification
        body = json.loads(existing["body_json"])
        body.setdefault("reverifications", []).append({"ref_run_ids": list(dec.ref_run_ids),
                                                       "test_run_ids": list(dec.test_run_ids)})
        conn.execute("UPDATE witness SET body_json=? WHERE id=?", (json.dumps(body, sort_keys=True), existing["id"]))
        return existing["id"]
    wid = new_id("wit")
    w = Witness(witness_id=wid, witness_class=WitnessClass.SILENT_DIVERGENCE if silent else WitnessClass.BREAK, cell_id=cell.cell_id, oracle=oracle,
                oracle_version=version, entry_point=dec.entry, witness_key=key, signature=dec.signature,
                ref_run_ids=dec.ref_run_ids, test_run_ids=dec.test_run_ids, input_tier=meta.get("tier"))
    body = w.model_dump(mode="json")
    if meta:
        body["input"] = meta                                     # the exact bytes (base64), their hash, the tier and the options
    conn.execute("INSERT INTO witness(id, analysis_id, cell_id, class, divergence, oracle, oracle_version, entry_point, input_tier, input_hash, "
                 "witness_key, signature_json, ref_pass, test_fail, body_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (wid, cell.analysis_id, cell.cell_id, "SILENT_DIVERGENCE" if silent else "BREAK", "VALUE_DIVERGENCE" if silent else DIVERGENCE.get(oracle, "UNKNOWN"),
                  oracle, version, dec.entry, meta.get("tier"), meta.get("sha256"), key, dec.signature.model_dump_json(), len(dec.ref_run_ids),
                  len(dec.test_run_ids), json.dumps(body, sort_keys=True)))
    return wid


def verify_cell(conn: sqlite3.Connection, cell: FixtureCell, *, oracle: str, version: str,
                run_in_world: Callable[[str], OracleRunResult], args: dict, force: bool = False, entry_meta: dict[str, dict] | None = None) -> Verification:
    """Run the oracle K times in each world, decide every entry, and record witnesses."""
    ref = [execute_run(conn, cell, oracle=oracle, version=version, side="ref", world_hash=cell.ref_world_hash,
                       run_index=i, args=args, runner=lambda: run_in_world(cell.ref_world_hash), force=force)
           for i in range(1, K + 1)]
    test = [execute_run(conn, cell, oracle=oracle, version=version, side="test", world_hash=cell.test_world_hash,
                        run_index=i, args=args, runner=lambda: run_in_world(cell.test_world_hash), force=force)
            for i in range(1, K + 1)]
    names: list[str] = []
    for r in ref + test:
        for e in r.result.entries:
            if e.entry not in names:
                names.append(e.entry)
    v = Verification(ref, test)
    for r in ref + test:
        if r.result.failure_class in INFRA_CLASSES and not r.result.entries:
            v.problem = r.result.failure_class.value.lower()
            break
    for name in names:
        dec = decide_entry(name, ref, test)
        if dec.decision == Decision.WITNESS:
            dec = EntryDecision(dec.entry, dec.decision, dec.reason, dec.signature, dec.ref_run_ids, dec.test_run_ids,
                                _save_witness(conn, cell, oracle, version, dec, (entry_meta or {}).get(name)))
        elif dec.decision == Decision.REUSED_ONLY:
            key = witness_key(cell, oracle, version, name, cell.env_profile_id, ((entry_meta or {}).get(name) or {}).get("sha256"))
            row = conn.execute("SELECT id FROM witness WHERE witness_key=?", (key,)).fetchone()
            if row:                                           # shown, not re-counted
                dec = EntryDecision(dec.entry, dec.decision, dec.reason + "; the earlier witness stands", None,
                                    dec.ref_run_ids, dec.test_run_ids, row["id"])
        v.decisions.append(dec)
    return v


__all__ = ["Decision", "EntryDecision", "Verification", "decide_entry", "verify_cell", "witness_key", "K",
           "RunProvenance"]
