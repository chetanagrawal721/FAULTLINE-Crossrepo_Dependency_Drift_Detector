"""O-contract: replay a data contract between a producer world and a consumer world (master section 26, pydantic).

The bytes are produced once, in the producer world (the artifact's reference world). Exactly those bytes are then parsed in the
consumer world and in the producer world, and the two parses are compared:

  reference parse ok, consumer parse error            REJECTED_IN_TEST     a break
  reference parse ok, consumer parse ok, values differ VALUE_DIVERGENCE     a silent divergence
  same values, different key order or formatting       FORMAT_DIVERGENCE    informational
  same values, the library warned                      WARNING_ONLY         informational
  the reference world rejects the input                invalid              discarded and counted, never reported

Inputs come in tiers. T1 are samples found in the artifact (the JSON file is the wire bytes), T2 is the smallest valid instance, T3 is
generated (seeded) and used only when T1 and T2 found nothing; such a witness is labelled "generated". A candidate is shrunk before it
is verified. Verification is the ordinary 3 + 3 rule over fresh runs of the same stored bytes, one entry per input.

Serialisation options (`exclude_none`) are not read from call sites yet; both the default and the `exclude_none` variants are replayed and
every witness says the options were assumed. Custom validators and serialisers are artifact code and run in the sandbox.
"""
import ast
import base64
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..core.enums import FailureClass, RunProvenance
from ..core.hashing import content_hash
from ..core.models import EntryOutcome, OracleRunResult
from ..sandbox.client import SandboxClient
from .classify import classify_entry, classify_run

ORACLE = "o_contract"
ORACLE_VERSION = "1.0.0"
VARIANTS = [{"label": "default", "options": {}}, {"label": "exclude_none", "options": {"exclude_none": True}}]
TIER_ORDER = {"T1": 0, "T2": 1, "T3": 2}
MAX_TYPES = 6
MAX_CANDIDATES = 3
MAX_SAME_SAMPLES = 4
MAX_T1_FILES = 12
MAX_SAMPLE_BYTES = 64 * 1024
SAMPLE_DIRS = ("fixtures", "examples", "tests/data", "tests/fixtures", "data", "samples")
FAIL_KINDS = ("REJECTED_IN_TEST", "VALUE_DIVERGENCE")


@dataclass(frozen=True)
class ContractType:
    module: str
    name: str


@dataclass
class Item:
    """One input whose bytes the producer world emitted and its own reference parse accepted."""
    type: ContractType
    id: str
    tier: str
    kind: str                                  # fields | wire
    variant: str
    options: dict
    bytes_b64: str
    ref: str
    ref_redump: str
    fields: dict | None = None
    wire: object = None
    source: str | None = None                  # T1: the file the sample came from
    consumer_kind: str | None = None           # filled by the exploration run
    consumer_message: str | None = None
    consumer_got: str | None = None

    @property
    def entry(self) -> str:
        return f"contract:{self.type.name}:{self.id}"

    @property
    def bytes_hash(self) -> str:
        return content_hash(base64.b64decode(self.bytes_b64))

    @property
    def assumed_options(self) -> bool:
        return self.kind == "fields"

    def payload(self) -> dict:
        return {"id": self.id, "bytes": self.bytes_b64, "ref": self.ref, "ref_redump": self.ref_redump}


@dataclass
class Exploration:
    types: list[ContractType]
    n_total: int = 0
    n_invalid: int = 0
    classes: Counter = field(default_factory=Counter)
    items: list[Item] = field(default_factory=list)
    candidates: list[Item] = field(default_factory=list)       # shrunk, in verification order
    notes: list[str] = field(default_factory=list)

    @property
    def n_valid(self) -> int:
        return self.n_total - self.n_invalid

    def verification_items(self) -> list[Item]:
        """The shrunk candidates plus a few inputs that behaved the same, so the finding can say what was exercised."""
        same = [i for i in self.items if i.consumer_kind in ("SAME", "FORMAT_DIVERGENCE", "WARNING_ONLY")]
        same.sort(key=lambda i: (TIER_ORDER.get(i.tier, 9), i.id))
        picked: list[Item] = []
        seen: set[tuple] = set()
        for i in same:
            k = (i.type.name, i.tier, i.variant)
            if k not in seen and len(picked) < MAX_SAME_SAMPLES:
                seen.add(k)
                picked.append(i)
        return [*self.candidates, *picked]


# ------------------------------------------------------------------------------------------------ discovery

def discover_types(sources: dict[str, bytes], modules_of: dict[str, str | None], wanted_modules: set[str]) -> list[ContractType]:
    """Pydantic model classes defined in the given artifact modules: `class X(BaseModel)` or `class X(pydantic.BaseModel)`.
    `modules_of` maps a source path to its dotted module name. Source is parsed, never imported."""
    out: list[ContractType] = []
    for path in sorted(sources):
        mod = modules_of.get(path)
        if not mod or mod not in wanted_modules:
            continue
        try:
            tree = ast.parse(sources[path].decode("utf-8", "replace"))
        except (SyntaxError, ValueError):
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                for b in node.bases:
                    name = b.attr if isinstance(b, ast.Attribute) else b.id if isinstance(b, ast.Name) else ""
                    if name == "BaseModel":
                        out.append(ContractType(mod, node.name))
    return out[:MAX_TYPES]


def t1_inputs(art_dir: Path) -> list[dict]:
    """JSON samples shipped with the artifact. A sample is only a candidate: the reference world decides whether it is valid."""
    found: list[dict] = []
    files: list[Path] = []
    for d in SAMPLE_DIRS:
        base = Path(art_dir) / d
        if base.is_dir():
            files += sorted(p for p in base.rglob("*.json") if p.is_file() and not p.is_symlink())
    for p in files[:MAX_T1_FILES]:
        try:
            if p.stat().st_size > MAX_SAMPLE_BYTES:
                continue
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rel = p.relative_to(art_dir).as_posix()
        for n, obj in enumerate(doc if isinstance(doc, list) else [doc][:1]):
            if isinstance(obj, dict) and n < 3:
                found.append({"id": f"T1-{content_hash(json.dumps(obj, sort_keys=True).encode())[:8]}", "tier": "T1", "kind": "wire", "wire": obj, "source": rel})
    return found


# ------------------------------------------------------------------------------------------------ sandbox calls

def _submit(sbx: SandboxClient, image: str, *, script: str, world_hash: str, artifact_hash: str, args: dict, timeout_s: int = 180) -> dict:
    return sbx.submit({"image": image, "zone": "exec", "script": script, "interpreter": "world", "args": args, "limits": {"timeout_s": timeout_s},
                       "mounts": {"/opt/world": {"world": world_hash}, "/artifact": {"artifact": artifact_hash}}})


def produce(sbx, image, *, world_hash: str, artifact_hash: str, ctype: ContractType, pythonpath: tuple[str, ...], inputs: list[dict], t2: bool = True,
            t3: dict | None = None, variants: list[dict] | None = None) -> dict:
    r = _submit(sbx, image, script="contract_producer.py", world_hash=world_hash, artifact_hash=artifact_hash,
                args={"module": ctype.module, "type": ctype.name, "pythonpath": list(pythonpath), "inputs": inputs, "t2": t2, "t3": t3,
                      "variants": variants or VARIANTS})
    return {"run": r, "data": r.get("data") or {}}


def consume_raw(sbx, image, *, world_hash: str, artifact_hash: str, ctype: ContractType, pythonpath: tuple[str, ...], items: list[Item], compare: bool) -> dict:
    return _submit(sbx, image, script="contract_consumer.py", world_hash=world_hash, artifact_hash=artifact_hash,
                   args={"module": ctype.module, "type": ctype.name, "pythonpath": list(pythonpath), "items": [i.payload() for i in items], "compare": compare})


def _to_items(ctype: ContractType, data: dict, inputs: list[dict]) -> tuple[list[Item], int, int]:
    by_id = {i["id"]: i for i in inputs}
    items: list[Item] = []
    for it in data.get("items", []):
        if it.get("status") != "ok":
            continue
        base = it["id"].split(":")[0]
        src = by_id.get(base, {})
        items.append(Item(ctype, f"{it['tier']}-{content_hash(base64.b64decode(it['bytes']))[:8]}-{it['variant']}", it["tier"], it["kind"], it["variant"],
                          it["options"], it["bytes"], it["ref"], it["ref_redump"], fields=it.get("fields"), wire=src.get("wire"), source=src.get("source")))
    return items, len(data.get("items", [])), int(data.get("n_invalid", 0))


def _classify(items: list[Item], entries: list[dict]) -> None:
    by = {e["input_id"]: e for e in entries}
    for i in items:
        e = by.get(i.id)
        if e is None:
            continue
        i.consumer_kind, i.consumer_message, i.consumer_got = e["kind"], e.get("message"), e.get("got")


# ------------------------------------------------------------------------------------------------ shrinking

def _simpler(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0
    if isinstance(value, float):
        return 0.0
    if isinstance(value, str):
        return ""
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return value


def _neighbours(doc: dict) -> list[dict]:
    out: list[dict] = []
    for k in doc:
        out.append({a: b for a, b in doc.items() if a != k})                  # without this field
    for k, v in doc.items():
        s = _simpler(v)
        if s != v:
            out.append({**doc, k: s})                                           # this field at its simplest value
    return out


def shrink(sbx, image, *, producer_world: str, consumer_world: str, artifact_hash: str, cand: Item, pythonpath: tuple[str, ...], rounds: int = 3) -> Item:
    """Greedy, batched: each round tries every one-step simplification of the input in one producer run and one consumer run, and keeps the
    smallest one that fails in the same way. The reference world must still accept it (an invalid input is never a candidate)."""
    best = cand
    for r in range(rounds):
        doc = best.wire if best.kind == "wire" else best.fields
        if not isinstance(doc, dict) or not doc:
            break
        key = "wire" if best.kind == "wire" else "fields"
        trials = [{"id": f"S{r}-{n}", "tier": best.tier, "kind": best.kind, key: d} for n, d in enumerate(_neighbours(doc))]
        if not trials:
            break
        got = produce(sbx, image, world_hash=producer_world, artifact_hash=artifact_hash, ctype=best.type, pythonpath=pythonpath, inputs=trials, t2=False,
                      variants=[{"label": best.variant, "options": best.options}])
        items, _n, _bad = _to_items(best.type, got["data"], trials)
        if not items:
            break
        cons = consume_raw(sbx, image, world_hash=consumer_world, artifact_hash=artifact_hash, ctype=best.type, pythonpath=pythonpath, items=items, compare=True)
        _classify(items, (cons.get("data") or {}).get("entries", []))
        same_way = [i for i in items if i.consumer_kind == best.consumer_kind and i.consumer_message == best.consumer_message]
        if not same_way:
            break
        smallest = min(same_way, key=lambda i: len(json.dumps(i.wire if i.kind == "wire" else i.fields, sort_keys=True)))
        if len(json.dumps(smallest.wire if smallest.kind == "wire" else smallest.fields, sort_keys=True)) >= len(json.dumps(doc, sort_keys=True)):
            break
        smallest.source = best.source
        best = smallest
    return best


# ------------------------------------------------------------------------------------------------ exploration

def explore(sbx, image, *, producer_world: str, consumer_world: str, artifact_hash: str, art_dir: Path, types: list[ContractType],
            pythonpath: tuple[str, ...], seed: int = 17, n_generated: int = 40) -> Exploration:
    """Produce bytes in the producer world, parse them in the consumer world, classify, pick and shrink the failing inputs."""
    ex = Exploration(types)
    samples = t1_inputs(art_dir)
    for ctype in types:
        got = produce(sbx, image, world_hash=producer_world, artifact_hash=artifact_hash, ctype=ctype, pythonpath=pythonpath, inputs=samples, t2=True)
        if got["run"].get("failure_class", "NONE") != "NONE" and not got["data"]:
            ex.notes.append(f"{ctype.name}: the producer run did not finish ({got['run'].get('failure_class')})")
            continue
        items, total, bad = _to_items(ctype, got["data"], samples)
        if not any(i.tier in ("T1", "T2") for i in items):                                  # nothing valid from T1 and T2: generate (T3)
            g = produce(sbx, image, world_hash=producer_world, artifact_hash=artifact_hash, ctype=ctype, pythonpath=pythonpath, inputs=[], t2=False,
                        t3={"seed": seed, "n": n_generated})
            more, t, b = _to_items(ctype, g["data"], [])
            items, total, bad = items + more, total + t, bad + b
        ex.n_total += total
        ex.n_invalid += bad
        if not items:
            continue
        cons = consume_raw(sbx, image, world_hash=consumer_world, artifact_hash=artifact_hash, ctype=ctype, pythonpath=pythonpath, items=items, compare=True)
        _classify(items, (cons.get("data") or {}).get("entries", []))
        for i in items:
            ex.classes[i.consumer_kind or "NOT_RUN"] += 1
        ex.items += items
        failing = [i for i in items if i.consumer_kind in FAIL_KINDS]
        if any(i.tier in ("T1", "T2") for i in failing):                                     # T3 is used only if no T1 or T2 input failed
            failing = [i for i in failing if i.tier in ("T1", "T2")]
        failing.sort(key=lambda i: (TIER_ORDER.get(i.tier, 9), i.id))
        distinct: dict[tuple, Item] = {}
        for i in failing:
            distinct.setdefault((i.consumer_kind, i.consumer_message), i)
        for cand in list(distinct.values())[:MAX_CANDIDATES]:
            ex.candidates.append(shrink(sbx, image, producer_world=producer_world, consumer_world=consumer_world, artifact_hash=artifact_hash,
                                        cand=cand, pythonpath=pythonpath))
    return ex


# ------------------------------------------------------------------------------------------------ the oracle run (one of the 3 + 3)

def run_o_contract(sbx: SandboxClient, image: str, *, world_hash: str, artifact_hash: str, items: list[Item], compare: bool, top_level: str = "",
                   pythonpath: tuple[str, ...] = ("/artifact/src",), timeout_s: int = 180) -> OracleRunResult:
    """Parse the stored bytes of every item in this world. On the reference side (compare=False) the parse only has to succeed; on the consumer
    side it must also give the values the reference parse gave."""
    entries: list[EntryOutcome] = []
    classes: list[FailureClass] = []
    first: dict | None = None
    sandbox_class, duration, tails = "NONE", 0, ["", ""]
    by_type: dict[ContractType, list[Item]] = {}
    for i in items:
        by_type.setdefault(i.type, []).append(i)
    for ctype, group in by_type.items():
        r = consume_raw(sbx, image, world_hash=world_hash, artifact_hash=artifact_hash, ctype=ctype, pythonpath=pythonpath, items=group, compare=compare)
        first = first or r
        duration += r.get("duration_ms", 0)
        if r["failure_class"] != "NONE" and sandbox_class == "NONE":
            sandbox_class = r["failure_class"]
        tails = [r.get("stdout_tail", ""), r.get("stderr_tail", "")]
        for e in (r.get("data") or {}).get("entries", []):
            fc, na = classify_entry(e, top_level)
            classes.append(fc)
            entries.append(EntryOutcome(entry=e["entry"], passed=bool(e.get("passed")), exc_type=e.get("exc_type"), message=e.get("message"),
                                        frames=tuple(e.get("frames", [])), warnings=tuple(e.get("warnings", [])), failure_class=fc, not_applicable=na,
                                        output_canonical=e.get("got")))
    assert first is not None
    return OracleRunResult(job_id=first["job_id"], run_id=first["run_id"], provenance=RunProvenance.FRESH_EXECUTION, exit_code=first.get("exit_code"),
                           duration_ms=duration, failure_class=classify_run(sandbox_class, classes), entries=tuple(entries),
                           stdout_tail=tails[0], stderr_tail=tails[1], data={"items": len(items), "compare": compare}, truncated=bool(first.get("truncated")))


def witness_input(item: Item) -> dict:
    """What a bundle stores about the input: the exact bytes, their hash, the tier and the options (assumed unless the input is a wire sample)."""
    return {"type": f"{item.type.module}.{item.type.name}", "tier": item.tier, "variant": item.variant, "options": item.options,
            "options_assumed": item.assumed_options, "source": item.source, "bytes_b64": item.bytes_b64, "sha256": item.bytes_hash,
            "reference_parse": item.ref, "generated": item.tier == "T3"}
