"""M7.1: the parts of contract replay that need no container: discovery, shrinking neighbours, the silent/break split, wording, and the
harnesses run in-process against the pydantic of this environment."""
import base64
import json
import subprocess
import sys
from pathlib import Path

from faultline.core.models import FailureSignature
from faultline.oracles.o_contract import ContractType, _neighbours, discover_types, t1_inputs
from faultline.verdicts import templates
from faultline.verdicts.engine import Evidence, decide, split_silent
from faultline.witnesses.verify import Decision, EntryDecision

HARNESS = Path(__file__).resolve().parents[2] / "backend" / "faultline" / "oracles" / "harness"


def test_models_are_found_by_reading_source_not_importing_it():
    src = {"p/m.py": (b"from pydantic import BaseModel\nimport pydantic\nclass A(BaseModel): x: int\nclass B(pydantic.BaseModel): y: int\n"
                      b"class _C(BaseModel): z: int\nclass D: pass\n")}
    assert discover_types(src, {"p/m.py": "p.m"}, {"p.m"}) == [ContractType("p.m", "A"), ContractType("p.m", "B")]
    assert discover_types(src, {"p/m.py": "p.m"}, {"p.other"}) == []                                  # only modules the consumer imports


def test_t1_samples_come_from_json_files_in_known_directories(tmp_path):
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "a.json").write_text('{"value": "42"}', encoding="utf-8")
    (tmp_path / "fixtures" / "bad.json").write_text("not json", encoding="utf-8")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "c.json").write_text('{"x": 1}', encoding="utf-8")
    got = t1_inputs(tmp_path)
    assert [(g["tier"], g["wire"], g["source"]) for g in got] == [("T1", {"value": "42"}, "fixtures/a.json")]


def test_shrinking_tries_dropping_and_simplifying_each_field():
    n = _neighbours({"a": 5, "b": "x", "c": 0})
    assert {"b": "x", "c": 0} in n and {"a": 5, "c": 0} in n and {"a": 0, "b": "x", "c": 0} in n and {"a": 5, "b": "", "c": 0} in n
    assert _neighbours({"a": 0}) == [{}]                                                              # nothing simpler than zero except dropping it


def _wit(entry, exc):
    return EntryDecision(entry, Decision.WITNESS, "r", FailureSignature(exc_type=exc, message_norm="m", entry_point=entry))


def test_a_value_divergence_is_a_silent_witness_and_everything_else_is_a_break():
    plain, silent = split_silent((_wit("contract:A:1", "ValueDivergence"), _wit("contract:A:2", "ValidationError")))
    assert silent == ("contract:A:1",) and [d.entry for d in plain] == ["contract:A:2"]
    only = decide(Evidence(relationship_level="L2", cell_state="PENDING", decisions=split_silent((_wit("c", "ValueDivergence"),))[0], silent_entries=("c",)))
    assert only.outcome == "SILENT_DIVERGENCE_WITNESSED" and only.rule == 4 and only.witness_entries == ("c",) and "c" in only.exercised
    both = decide(Evidence(relationship_level="L2", cell_state="PENDING", decisions=(_wit("b", "ValidationError"),), silent_entries=("c",)))
    assert both.outcome == "BREAK_WITNESSED" and both.rule == 3                                      # a break outranks a silent divergence


def test_contract_wording_names_the_tier_the_options_and_both_values():
    c = {"type": "acme.Ref", "tier": "T1", "options_assumed": False, "preview": '{"value": "42"}', "generated": False}
    s = templates.live_headline("SILENT_DIVERGENCE_WITNESSED", artifact="acme", consumers=["billing"], message='value: reference=42, consumer="42"', contract=c)
    assert "Accepted in both worlds, but the result differs" in s and 'reference=42, consumer="42"' in s and "Input tier T1" in s
    b = templates.live_headline("BREAK_WITNESSED", artifact="acme", consumers=["billing"], exc="ValidationError", message="1 validation error(s): x: Field required",
                                contract={**c, "tier": "T3", "generated": True, "options_assumed": True})
    assert "generated" in b.lower() and "options were assumed" in b and "Field required" in b
    for t in (s, b):
        assert not any(w in t.lower() for w in ("compatible", "proof", "guarantee"))


def _run(script, args):
    r = subprocess.run([sys.executable, str(HARNESS / script)], input=json.dumps({"args": args}), capture_output=True, text=True, cwd=str(HARNESS))
    out = r.stdout.split("@@FAULTLINE_RESULT_BEGIN@@")[1].split("@@FAULTLINE_RESULT_END@@")[0]
    return json.loads(out)


def test_the_harnesses_classify_same_rejected_and_diverging_inputs(tmp_path):
    (tmp_path / "mm.py").write_text(
        "from typing import Optional, Union\nfrom pydantic import BaseModel\n"
        "class Need(BaseModel):\n    a: int\n    b: Optional[str] = None\n"
        "class U(BaseModel):\n    v: Union[int, str]\n", encoding="utf-8")
    base = {"module": "mm", "pythonpath": [str(tmp_path)]}
    prod = _run("contract_producer.py", {**base, "type": "Need", "inputs": [{"id": "bad", "tier": "T1", "kind": "wire", "wire": {"a": "x"}}], "t2": True})
    ok = [i for i in prod["items"] if i["status"] == "ok"]
    assert prod["n_invalid"] == 1 and {i["tier"] for i in ok} == {"T2"} and ok[0]["fields"] == {"a": 0}   # an input the reference rejects is counted and dropped
    items = [{"id": i["id"], "bytes": i["bytes"], "ref": i["ref"], "ref_redump": i["ref_redump"]} for i in ok]
    same = _run("contract_consumer.py", {**base, "type": "Need", "items": items, "compare": True})
    assert {e["kind"] for e in same["entries"]} == {"SAME"} and all(e["passed"] for e in same["entries"])
    bad_bytes = base64.b64encode(b'{"b": "x"}').decode()
    rej = _run("contract_consumer.py", {**base, "type": "Need", "items": [{"id": "r", "bytes": bad_bytes, "ref": "{}", "ref_redump": "{}"}], "compare": True})
    e = rej["entries"][0]
    assert e["kind"] == "REJECTED_IN_TEST" and not e["passed"] and "a: " in e["message"] and e["entry"] == "contract:Need:r"
    div_bytes = base64.b64encode(b'{"v": "42"}').decode()
    div = _run("contract_consumer.py", {**base, "type": "U", "compare": True, "items": [{"id": "d", "bytes": div_bytes, "ref": '{"v":42}', "ref_redump": '{"v":42}'}]})
    d = div["entries"][0]
    assert d["kind"] == "VALUE_DIVERGENCE" and d["exc_type"] == "ValueDivergence" and 'v: reference=42, consumer="42"' in d["message"]
