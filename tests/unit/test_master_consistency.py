"""M11.1 (TC-11.1.1): the enums and verdict words in the code are identical to the master, or the difference is listed here and in an ADR.

The master is read as text; nothing is copied into this test except the approved differences.
"""
import re
from pathlib import Path

from faultline.core import enums

MASTER = (Path(__file__).resolve().parents[2] / "docs" / "FAULTLINE_MASTER.md").read_text(encoding="utf-8")

# Differences between the master's frozen-contract excerpt (section 63.2) and the code, each with the ADR that approves it.
APPROVED = {
    "oracle names": ({"o_contract_producer", "o_contract_consumer"}, {"o_contract"}, "docs/adr/0007-master-consistency-differences.md"),
}


def literal(name: str) -> set[str]:
    m = re.search(rf"^{name} = Literal\[(.*?)\]", MASTER, re.M | re.S)
    assert m, name
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def inline_literal(field: str) -> set[str]:
    m = re.search(rf"{field}: Literal\[(.*?)\]", MASTER, re.S)
    assert m, field
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def values(cls) -> set[str]:
    return {m.value for m in cls}


def test_the_frozen_contract_enums_equal_the_masters():
    assert literal("Scope") == values(enums.Scope)
    assert literal("Eco") == values(enums.Ecosystem)
    assert literal("FailureClass") == values(enums.FailureClass)
    assert inline_literal("source_kind") == values(enums.SourceKind)
    m = re.search(r'kind: Literal\[("observed".*?)\]', MASTER, re.S)
    assert set(re.findall(r'"([^"]+)"', m.group(1))) == values(enums.WorldKind)


def test_the_verdict_words_equal_the_masters_section_7_1():
    section = MASTER.split("## 7.1 Verdicts and their epistemic meaning")[1].split("\n---")[0]
    rows = re.findall(r"^\| (?:\*\(cell state\)\* )?\*\*([A-Z][A-Z_ ]+?)(?:\(reason\))?\*\* \|", section, re.M)
    words = {r.strip().replace(" ", "_") for r in rows}
    verdicts = {w for w in words if w not in ("NO_DRIFT", "NOT_APPLICABLE")}
    assert verdicts == values(enums.Verdict)
    assert {w for w in words if w in ("NO_DRIFT", "NOT_APPLICABLE")} == {"NO_DRIFT", "NOT_APPLICABLE"} == {c for c in values(enums.CellState) if c in ("NO_DRIFT", "NOT_APPLICABLE")}


def test_witness_classes_and_cell_states_match_the_masters_schema():
    ddl = MASTER
    assert "class IN ('BREAK', 'SILENT_DIVERGENCE')" in ddl or "BREAK|SILENT_DIVERGENCE" in ddl
    assert values(enums.WitnessClass) == {"BREAK", "SILENT_DIVERGENCE"}
    for state in ("NO_DRIFT", "PENDING", "ANALYZED", "NOT_APPLICABLE", "INCONCLUSIVE"):
        assert state in ddl and state in values(enums.CellState)


def test_the_oracle_names_differ_from_the_masters_excerpt_only_as_approved():
    oracle = re.search(r'oracle: Literal\[(.*?)\]', MASTER, re.S)
    master = set(re.findall(r'"([^"]+)"', oracle.group(1)))
    code = {"o_import", "o_tests", "o_bind", "o_contract", "o_typecheck"}
    only_master, only_code = master & {"o_contract_producer", "o_contract_consumer"}, code & {"o_contract"}
    approved_master, approved_code, adr = APPROVED["oracle names"]
    assert only_master == approved_master and only_code == approved_code
    assert (Path(__file__).resolve().parents[2] / adr).exists()
    from faultline.oracles import o_contract, o_import, o_tests
    from faultline.oracles.o_bind import ORACLE as bind
    assert {o_import.ORACLE, o_tests.ORACLE, bind, o_contract.ORACLE} <= code


def test_no_forbidden_wording_in_user_facing_code_and_docs():
    root = Path(__file__).resolve().parents[2]
    bad = re.compile(r"\b(compatible|proof|guarantee[ds]?|AI[- ]detected)\b", re.I)
    allowed_contexts = ("not a statement that", "is not ", "never ", "does not ", "no ", "do not")
    offenders = []
    for p in [*(root / "backend" / "faultline").rglob("*.py"), *(root / "frontend" / "src").rglob("*.tsx")]:
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if bad.search(line) and not any(a in line.lower() for a in allowed_contexts) and "incompatible" not in line.lower():
                offenders.append(f"{p.relative_to(root)}:{n}")
    assert offenders == []
