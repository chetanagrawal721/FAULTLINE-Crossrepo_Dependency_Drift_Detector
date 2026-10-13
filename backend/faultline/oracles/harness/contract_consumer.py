"""EXEC zone, NO network, run with the CONSUMER world's interpreter (/opt/world/bin/python -P).

Contract replay, consumer side: parse the exact bytes the producer world emitted, with this world's library, and compare with what the
reference parse produced. The same script also runs in the reference world (compare=false) to repeat the reference parse.

Per item:  SAME | REJECTED_IN_TEST | VALUE_DIVERGENCE | FORMAT_DIVERGENCE | WARNING_ONLY
FORMAT_DIVERGENCE (same values, different re-dumped text) and WARNING_ONLY (same values, the library warned) pass: they are
annotations, never witnesses. REJECTED_IN_TEST and VALUE_DIVERGENCE fail, with a failure signature built from the library's own message.
"""
import base64
import importlib
import json
import sys
import warnings

sys.path.append("/faultline_harness")           # appended last: packages in the world always win over harness files

from common import emit, read_spec  # noqa: E402


def version_major() -> int:
    import pydantic
    return int(str(pydantic.VERSION).split(".")[0])


def message_of(exc) -> str:
    try:
        errs = exc.errors()
    except Exception:
        errs = None
    if isinstance(errs, list):
        parts = ["{}: {}".format(".".join(str(x) for x in e.get("loc", ())) or "(root)", e.get("msg", "")) for e in errs]
        return f"{len(parts)} validation error(s): " + "; ".join(parts)
    return str(exc)[:300]


def diff_fields(ref: dict, got: dict) -> list[str]:
    out = []
    for k in sorted(set(ref) | set(got)):
        if ref.get(k, "<absent>") != got.get(k, "<absent>"):
            out.append("{}: reference={}, consumer={}".format(k, json.dumps(ref.get(k, "<absent>")), json.dumps(got.get(k, "<absent>"))))
    return out[:5]


def main() -> None:
    args = read_spec().get("args", {})
    sys.path[:0] = list(args.get("pythonpath", []))
    mod = importlib.import_module(args["module"])
    T = getattr(mod, args["type"])
    major = version_major()
    compare = bool(args.get("compare", True))
    entries = []
    for it in args["items"]:
        entry = {"entry": "contract:{}:{}".format(args["type"], it["id"]), "input_id": it["id"]}
        data = base64.b64decode(it["bytes"])
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                obj = T.model_validate_json(data) if major >= 2 else T.parse_raw(data)
                raw = obj.model_dump_json() if major >= 2 else obj.json()
        except Exception as exc:
            entry.update(passed=False, kind="REJECTED_IN_TEST", exc_type=type(exc).__name__, message=message_of(exc),
                         frames=[{"module": type(exc).__module__ or "pydantic"}])
            entries.append(entry)
            continue
        loaded = json.loads(raw)
        canon = json.dumps(loaded, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        ordered = json.dumps(loaded, ensure_ascii=False, separators=(",", ":"))      # key order kept; whitespace normalised away
        entry["got"] = canon
        if compare and canon != it["ref"]:
            d = diff_fields(json.loads(it["ref"]), json.loads(canon))
            entry.update(passed=False, kind="VALUE_DIVERGENCE", exc_type="ValueDivergence", message="; ".join(d) or "values differ",
                         frames=[{"module": "pydantic"}])
        elif compare and it.get("ref_redump") is not None and ordered != it["ref_redump"]:
            entry.update(passed=True, kind="FORMAT_DIVERGENCE")
        elif caught:
            entry.update(passed=True, kind="WARNING_ONLY", warnings=sorted({str(w.message)[:120] for w in caught})[:3])
        else:
            entry.update(passed=True, kind="SAME")
        entries.append(entry)
    emit({"python": sys.version.split()[0], "pydantic_major": major, "entries": entries})


if __name__ == "__main__":
    main()
