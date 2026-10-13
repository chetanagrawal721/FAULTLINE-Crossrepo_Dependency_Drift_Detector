"""Oracle planning per cell. Import comes first; if the artifact's top-level import already fails in the consumer world,
downstream oracles are blocked (blocked_by_import) so one cause is not reported many times."""
from dataclasses import asdict, dataclass

from ..witnesses.verify import Decision, Verification


@dataclass(frozen=True)
class Step:
    oracle: str
    status: str                  # PLANNED | RAN | BLOCKED | NOT_PLANNED
    reason: str = ""
    entries: tuple[str, ...] = ()


def plan(top_level: str, modules: list[str], *, has_tests: bool, test_lock: bool, bind_sites: int = 0, contract_types: int = 0,
         contract_reason: str = "") -> list[Step]:
    steps = [Step("o_import", "PLANNED", "", tuple(modules))]
    if not has_tests:
        steps.append(Step("o_tests", "NOT_PLANNED", "the artifact has no tests directory"))
    elif not test_lock:
        steps.append(Step("o_tests", "NOT_PLANNED", "no hash-pinned test-only lock to overlay (PC-5)"))
    else:
        steps.append(Step("o_tests", "PLANNED", "", ()))
    if bind_sites:
        steps.append(Step("o_bind", "PLANNED", f"{bind_sites} call site(s) into the differing packages", ()))
    else:
        steps.append(Step("o_bind", "NOT_PLANNED", "no call site in the artifact calls into a package that differs between the worlds"))
    if contract_types:
        steps.append(Step("o_contract", "PLANNED", f"{contract_types} pydantic model(s) in the modules the consumer imports", ()))
    else:
        steps.append(Step("o_contract", "NOT_PLANNED", contract_reason or "no pydantic model in the modules the consumer imports"))
    return steps


def after_import(steps: list[Step], top_level: str, v: Verification) -> list[Step]:
    """Mark o_import as run and block downstream oracles when the top-level import failed in the consumer world."""
    top = next((d for d in v.decisions if d.entry == top_level), None)
    failed_top = top is not None and top.decision == Decision.WITNESS
    out = []
    for s in steps:
        if s.oracle == "o_import":
            out.append(Step(s.oracle, "RAN", "", s.entries))
        elif s.status == "PLANNED" and failed_top:
            out.append(Step(s.oracle, "BLOCKED", f"blocked_by_import: importing {top_level} already fails in the consumer world", s.entries))
        else:
            out.append(s)
    return out


def mark_ran(steps: list[Step], oracle: str, entries: tuple[str, ...]) -> list[Step]:
    return [Step(s.oracle, "RAN", "", entries) if s.oracle == oracle else s for s in steps]


def as_json(steps: list[Step]) -> list[dict]:
    return [asdict(s) for s in steps]
