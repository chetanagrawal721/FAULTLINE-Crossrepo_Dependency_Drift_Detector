"""Exposure and coverage (M6.3, master section 21): which references touch a symbol that changed, and how much of the usage was resolved.

Exposure is static evidence. It says "this code refers to something that changed", not "this code fails". Only an oracle run can
witness a failure, so nothing here can produce a witnessed verdict.
"""
from dataclasses import dataclass, field

from ..diff.delta import KIND_CHANGED, REMOVED, SIGNATURE_BREAKING, ApiDelta, DeltaEntry
from ..diff.surface import Param
from .index import RESOLVED_STATUSES, Coverage, Reference, UsageIndex


@dataclass(frozen=True)
class Exposure:
    ref: Reference
    change: DeltaEntry
    package: str
    static_ok: bool | None          # binding simulation against the new signature; None when it does not apply or cannot be told
    confidence: str                 # RESOLVED | LOW_CONFIDENCE

    @property
    def exposure_id(self) -> str:
        return f"{self.ref.ref_id}->{self.change.symbol}"

    def to_json(self) -> dict:
        return {"id": self.exposure_id, "ref": self.ref.to_json(), "symbol": self.change.symbol, "change": self.change.change,
                "breaking": self.change.breaking, "static_ok": self.static_ok, "confidence": self.confidence}


@dataclass
class ExposureResult:
    exposures: list[Exposure]
    coverage: Coverage
    deltas: dict[str, ApiDelta]
    dynamic: list[Reference] = field(default_factory=list)       # references to divergent packages that are not resolved
    divergent: frozenset[str] = frozenset()

    @property
    def breaking_exposures(self) -> list[Exposure]:
        """Exposures to a breaking change that the binding simulation did not clear."""
        return [e for e in self.exposures if e.change.breaking and e.static_ok is not True]

    @property
    def static_limits(self) -> tuple[str, ...]:
        out = []
        for pkg, d in sorted(self.deltas.items()):
            if d.opaque_modules:
                out.append(f"{pkg}: compiled modules cannot be read statically ({', '.join(d.opaque_modules[:3])})")
            if d.dynamic_exports:
                out.append(f"{pkg}: modules build their exports at runtime ({', '.join(d.dynamic_exports[:3])})")
            if d.unparsed_files:
                out.append(f"{pkg}: {len(d.unparsed_files)} file(s) did not parse")
        missing = sorted(self.divergent - set(self.deltas))
        out += [f"{pkg}: no API delta was computed" for pkg in missing]
        return tuple(out)

    def evidence_fields(self) -> dict:
        """Keyword arguments for `verdicts.engine.Evidence`. Nothing is guessed: no delta means `api_delta_breaking` stays None."""
        computed = bool(self.deltas) and not (self.divergent - set(self.deltas))
        be = self.breaking_exposures
        return {"exposures": tuple(e.exposure_id for e in be) if computed else None,
                "api_delta_breaking": any(d.breaking for d in self.deltas.values()) if computed else None,
                "dynamic_refs": bool(self.dynamic),
                "coverage": self.coverage.ratio,
                "static_confirmed": any(e.static_ok is False for e in be),
                "static_limits": self.static_limits}


# ------------------------------------------------------------------------------------------------ binding simulation

def simulate_bind(shape: dict, params: tuple[Param, ...]) -> bool | None:
    """Would a call with this shape bind to the signature? Same rules as inspect.Signature.bind. None when star arguments make it unknown."""
    if shape.get("star") or shape.get("dstar"):
        return None
    n_pos, kws = shape["n_pos"], list(shape["kw"])
    positional = [p for p in params if p.kind in ("positional_only", "positional_or_keyword")]
    var_pos = any(p.kind == "var_positional" for p in params)
    var_kw = any(p.kind == "var_keyword" for p in params)
    if n_pos > len(positional) and not var_pos:
        return False
    filled = {p.name for p in positional[:n_pos]}
    for k in kws:
        match = next((p for p in params if p.name == k and p.kind in ("positional_or_keyword", "keyword_only")), None)
        if match is None:
            if not var_kw:
                return False
        elif k in filled:
            return False
        else:
            filled.add(k)
    return all(p.name in filled for p in params if p.required and p.kind in ("positional_only", "positional_or_keyword", "keyword_only"))


def _hits(target: str, entry: DeltaEntry) -> bool:
    if target == entry.symbol:
        return True
    return target.startswith(entry.symbol + ".") and entry.change in (REMOVED, KIND_CHANGED)       # everything under a removed symbol is gone with it


def compute_exposure(index: UsageIndex, deltas: dict[str, ApiDelta]) -> ExposureResult:
    """`deltas`: {divergent package: ApiDelta between its reference-world and consumer-world versions}."""
    out: list[Exposure] = []
    for r in index.refs_to_divergent():
        if r.status not in RESOLVED_STATUSES or r.package not in deltas or not r.target:
            continue
        for e in deltas[r.package].entries:
            if not _hits(r.target, e) or (r.kind == "IMPORT" and e.change == SIGNATURE_BREAKING):
                continue                                                   # importing a callable whose signature changed is not yet a use of the signature
            ok: bool | None = None
            if e.change == REMOVED:
                ok = False
            elif r.kind == "CALL" and r.shape and e.new_params is not None and r.target == e.symbol:
                ok = simulate_bind(r.shape, e.new_params)
            out.append(Exposure(r, e, r.package, ok, r.status))
    cov = index.coverage()
    return ExposureResult(out, cov, dict(deltas), list(cov.unresolved), index.divergent)
