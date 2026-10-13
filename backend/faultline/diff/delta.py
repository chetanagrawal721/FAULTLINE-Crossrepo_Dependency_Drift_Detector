"""ApiDelta (M6.2): which public symbols changed between two versions of a package, from two static surfaces.

The delta is explanatory. It says what changed and whether an existing call could stop binding; it never says that anything fails.
Only an oracle run can witness a failure. Where either surface could not be read completely, the delta says so (`incomplete`).
"""
from dataclasses import dataclass, field

from .surface import Param, Surface, Symbol, resolve

REMOVED, ADDED, KIND_CHANGED, SIGNATURE_BREAKING, SIGNATURE_CHANGED = "REMOVED", "ADDED", "KIND_CHANGED", "SIGNATURE_BREAKING", "SIGNATURE_CHANGED"
CALLABLE_KINDS = ("function", "class", "method")


@dataclass(frozen=True)
class DeltaEntry:
    symbol: str                     # public dotted name, e.g. acme.util.parse
    change: str                     # REMOVED | ADDED | KIND_CHANGED | SIGNATURE_BREAKING | SIGNATURE_CHANGED
    kind: str                       # kind of the symbol in the version where it exists (the old one for REMOVED)
    old: str | None                 # description in the old version
    new: str | None                 # description in the new version
    breaking: bool
    details: tuple[str, ...] = ()
    new_params: tuple[Param, ...] | None = None    # the new signature, for binding simulation

    def to_json(self) -> dict:
        return {"symbol": self.symbol, "change": self.change, "kind": self.kind, "old": self.old, "new": self.new,
                "breaking": self.breaking, "details": list(self.details)}


@dataclass
class ApiDelta:
    package: str
    old_hash: str
    new_hash: str
    entries: list[DeltaEntry] = field(default_factory=list)
    opaque_modules: list[str] = field(default_factory=list)
    dynamic_exports: list[str] = field(default_factory=list)
    unparsed_files: list[str] = field(default_factory=list)
    explanatory_only: bool = True                  # a static delta never witnesses anything

    @property
    def breaking(self) -> bool:
        return any(e.breaking for e in self.entries)

    @property
    def incomplete(self) -> bool:
        return bool(self.opaque_modules or self.dynamic_exports or self.unparsed_files)

    def changed(self, symbol: str) -> DeltaEntry | None:
        return next((e for e in self.entries if e.symbol == symbol), None)

    def to_json(self) -> dict:
        return {"package": self.package, "old_hash": self.old_hash, "new_hash": self.new_hash, "breaking": self.breaking,
                "incomplete": self.incomplete, "explanatory_only": True, "opaque_modules": self.opaque_modules,
                "dynamic_exports": self.dynamic_exports, "unparsed_files": self.unparsed_files, "entries": [e.to_json() for e in self.entries]}


def _positional(ps: tuple[Param, ...]) -> list[str]:
    return [p.name for p in ps if p.kind in ("positional_only", "positional_or_keyword")]


def signature_changes(old: tuple[Param, ...], new: tuple[Param, ...]) -> tuple[bool, list[str]]:
    """(breaking, details). Breaking means a call shape that bound to the old signature may no longer bind to the new one."""
    details: list[str] = []
    breaking = False
    new_by = {p.name: p for p in new}
    old_pos, new_pos = _positional(old), _positional(new)
    new_var_kw = any(p.kind == "var_keyword" for p in new)
    new_var_pos = any(p.kind == "var_positional" for p in new)
    for p in old:
        if p.kind in ("var_positional", "var_keyword"):
            if not any(q.kind == p.kind for q in new):
                breaking = True
                details.append(f"{p.text()} was removed")
            continue
        q = new_by.get(p.name)
        if q is None:
            absorbed = new_var_kw if p.kind == "keyword_only" else (new_var_pos and new_var_kw)
            breaking = breaking or not absorbed
            details.append(f"parameter `{p.name}` was removed" + (" (a **kwargs now takes it, and ignores it)" if absorbed else ""))
            continue
        if p.kind == "positional_or_keyword" and q.kind == "keyword_only":
            breaking = True
            details.append(f"parameter `{p.name}` became keyword-only")
        elif p.kind == "positional_or_keyword" and q.kind == "positional_only":
            breaking = True
            details.append(f"parameter `{p.name}` became positional-only")
        elif p.kind == "keyword_only" and q.kind == "positional_only":
            breaking = True
            details.append(f"parameter `{p.name}` became positional-only")
        if not p.required and q.required:
            breaking = True
            details.append(f"parameter `{p.name}` became required")
        if p.name in old_pos and q.name in new_pos and old_pos.index(p.name) != new_pos.index(q.name) and p.kind != "keyword_only":
            breaking = True
            details.append(f"parameter `{p.name}` moved from position {old_pos.index(p.name)} to {new_pos.index(q.name)}")
    old_names = {p.name for p in old}
    for q in new:
        if q.name not in old_names and q.kind not in ("var_positional", "var_keyword"):
            if q.required:
                breaking = True
                details.append(f"a required parameter `{q.name}` was added")
            else:
                details.append(f"an optional parameter `{q.name}` was added")
        elif q.name not in old_names:
            details.append(f"{q.text()} was added")
    details.sort(key=lambda d: 0 if "removed" in d or "required" in d or "became" in d else 1)       # the cause first, the knock-on position shifts after
    return breaking, details


def _compare(name: str, o: Symbol, n: Symbol) -> DeltaEntry | None:
    if o.kind != n.kind:
        both_callable = o.kind in CALLABLE_KINDS and n.kind in CALLABLE_KINDS
        return DeltaEntry(name, KIND_CHANGED, o.kind, o.describe(), n.describe(), not both_callable, (f"{o.kind} became {n.kind}",))
    details: list[str] = []
    breaking = False
    if o.params is not None and n.params is not None:
        breaking, details = signature_changes(o.params, n.params)
    elif o.params is not None and n.params is None:
        details = ["the class no longer defines __init__ (it may inherit one); its signature cannot be read statically"]
    if o.bases != n.bases:
        details.append(f"bases changed from ({', '.join(o.bases)}) to ({', '.join(n.bases)})")
    if not details:
        return None
    return DeltaEntry(name, SIGNATURE_BREAKING if breaking else SIGNATURE_CHANGED, o.kind, o.describe(), n.describe(), breaking, tuple(details), n.params)


def compute_delta(old: Surface, new: Surface) -> ApiDelta:
    d = ApiDelta(package=new.package, old_hash=old.package_hash, new_hash=new.package_hash,
                 opaque_modules=sorted(set(old.opaque_modules) | set(new.opaque_modules)),
                 dynamic_exports=sorted(set(old.dynamic_exports) | set(new.dynamic_exports)),
                 unparsed_files=sorted(set(old.unparsed_files) | set(new.unparsed_files)))
    for name in sorted(set(old.public_names()) | set(new.public_names())):
        o, n = resolve(old, name), resolve(new, name)
        if o is not None and n is None:
            d.entries.append(DeltaEntry(name, REMOVED, o.kind, o.describe(), None, True, ("no longer present in the public surface",)))
        elif o is None and n is not None:
            d.entries.append(DeltaEntry(name, ADDED, n.kind, None, n.describe(), False))
        elif o is not None and n is not None:
            e = _compare(name, o, n)
            if e:
                d.entries.append(e)
    return d
