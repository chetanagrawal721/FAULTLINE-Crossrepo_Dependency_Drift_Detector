"""EXEC zone, NO network, run with the PRODUCER world's interpreter (/opt/world/bin/python -P).

Contract replay, producer side. For one pydantic model class it builds inputs, serializes them with the producer's library, parses the
same bytes once with that library (the reference parse) and reports bytes and canonical results. Inputs are
  T1  wire samples found in the artifact (JSON files): the sample IS the wire bytes
  T2  the smallest valid instance (required fields only; None for Optionals, zero values elsewhere)
  T3  seeded generated instances (only when the caller asks for them)
An input the reference world itself rejects is reported as invalid and never becomes evidence.
The model class is the artifact's own code and runs in the sandbox, like any other artifact code.
"""
import base64
import enum
import importlib
import json
import random
import sys
import typing

sys.path.append("/faultline_harness")           # appended last: packages in the world always win over harness files

from common import emit, read_spec  # noqa: E402


def version_major() -> int:
    import pydantic
    return int(str(pydantic.VERSION).split(".")[0])


def fields_of(T, major):
    """[(name, annotation, required)] for the model's own fields."""
    if major >= 2:
        return [(n, f.annotation, f.is_required()) for n, f in T.model_fields.items()]
    return [(n, f.outer_type_ if not f.allow_none else typing.Optional[f.outer_type_], bool(f.required)) for n, f in T.__fields__.items()]  # noqa: UP045 (a runtime value, not an annotation)


def minimal(ann, major, depth=0):
    origin, args = typing.get_origin(ann), typing.get_args(ann)
    if ann is type(None):
        return None
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        return None if len(non_none) < len(args) else minimal(non_none[0], major, depth)
    if origin is typing.Literal:
        return args[0]
    if origin in (list, set, frozenset, tuple) or ann in (list, set, frozenset, tuple):
        return []
    if origin is dict or ann is dict:
        return {}
    if isinstance(ann, type):
        if issubclass(ann, bool):
            return False
        if issubclass(ann, enum.Enum):
            return list(ann)[0].value
        if issubclass(ann, int):
            return 0
        if issubclass(ann, float):
            return 0.0
        if issubclass(ann, str):
            return ""
        name = ann.__name__
        if name == "UUID":
            return "00000000-0000-0000-0000-000000000000"
        if name == "datetime":
            return "1970-01-01T00:00:00+00:00"
        if name == "date":
            return "1970-01-01"
        if name == "Decimal":
            return "0"
        if hasattr(ann, "model_fields") or hasattr(ann, "__fields__"):
            return {n: minimal(a, major, depth + 1) for n, a, req in fields_of(ann, major) if req} if depth < 4 else {}
    return None


def t2_fields(T, major):
    return {n: minimal(a, major) for n, a, req in fields_of(T, major) if req}


def generated(T, major, rng):
    out = {}
    for n, a, req in fields_of(T, major):
        if not req and rng.random() < 0.4:
            continue
        base = minimal(a, major)
        if isinstance(base, bool):
            out[n] = rng.choice([True, False])
        elif isinstance(base, int):
            out[n] = rng.randint(-5, 1000)
        elif isinstance(base, str) and base == "":
            out[n] = rng.choice(["a", "42", "x y", "é", "0"])
        elif isinstance(base, float):
            out[n] = rng.choice([0.5, 1.25, 3.0])
        else:
            out[n] = base
    return out


def parse(T, data: bytes, major):
    return T.model_validate_json(data) if major >= 2 else T.parse_raw(data)


def dump_json(obj, major, options):
    return obj.model_dump_json(**options) if major >= 2 else obj.json(**options)


def canonical(obj, major):
    raw = obj.model_dump_json() if major >= 2 else obj.json()
    loaded = json.loads(raw)
    return (json.dumps(loaded, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            json.dumps(loaded, ensure_ascii=False, separators=(",", ":")))       # the second keeps key order: only whitespace is normalised away


def message_of(exc) -> str:
    errs = None
    try:
        errs = exc.errors()
    except Exception:
        pass
    if isinstance(errs, list):
        parts = ["{}: {}".format(".".join(str(x) for x in e.get("loc", ())) or "(root)", e.get("msg", "")) for e in errs]
        return f"{len(parts)} validation error(s): " + "; ".join(parts)
    return str(exc)[:300]


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def main() -> None:
    args = read_spec().get("args", {})
    sys.path[:0] = list(args.get("pythonpath", []))
    mod = importlib.import_module(args["module"])
    T = getattr(mod, args["type"])
    major = version_major()
    items = []
    inputs = list(args.get("inputs", []))                                      # [{id, tier, kind: fields|wire, fields|wire}]
    if args.get("t2"):
        inputs.append({"id": "T2-min", "tier": "T2", "kind": "fields", "fields": t2_fields(T, major)})
    t3 = args.get("t3")
    if t3:
        rng = random.Random(int(t3.get("seed", 17)))
        for i in range(min(int(t3.get("n", 0)), 200)):
            inputs.append({"id": f"T3-{i:03d}", "tier": "T3", "kind": "fields", "fields": generated(T, major, rng)})
    variants = args.get("variants") or [{"label": "default", "options": {}}]
    n_invalid = 0
    for inp in inputs:
        vs = [{"label": "wire", "options": {}}] if inp["kind"] == "wire" else variants
        for v in vs:
            iid = inp["id"] + ("" if inp["kind"] == "wire" else ":" + v["label"])
            item = {"id": iid, "tier": inp["tier"], "kind": inp["kind"], "variant": v["label"], "options": v["options"]}
            try:
                if inp["kind"] == "wire":
                    data = json.dumps(inp["wire"]).encode() if not isinstance(inp["wire"], str) else inp["wire"].encode()
                    item["fields"] = None
                else:
                    obj = T(**inp["fields"])
                    data = dump_json(obj, major, v["options"]).encode()
                    item["fields"] = json.loads(json.dumps(inp["fields"], default=str))
            except Exception as exc:
                item.update(status="producer_error", exc_type=type(exc).__name__, message=message_of(exc))
                n_invalid += 1
                items.append(item)
                continue
            try:
                ref = parse(T, data, major)
                canon, raw = canonical(ref, major)
            except Exception as exc:
                item.update(status="ref_error", exc_type=type(exc).__name__, message=message_of(exc))
                n_invalid += 1
                items.append(item)
                continue
            item.update(status="ok", bytes=b64(data), ref=canon, ref_redump=raw)
            items.append(item)
    emit({"python": sys.version.split()[0], "pydantic_major": major, "items": items, "n_invalid": n_invalid})


if __name__ == "__main__":
    main()
