"""The artifact's runtime closure inside a world: the packages the artifact can actually pull in.

Roots are the artifact's own runtime dependencies (plus the extras a consumer asked for). Edges come from the wheels' own
METADATA (Requires-Dist), read inside the sandbox, never guessed from names. A consumer package that is not reachable from
the artifact (an unrelated `requests`) is not part of the artifact's world, so it cannot create drift.
"""
from collections.abc import Callable

from packaging.markers import InvalidMarker
from packaging.requirements import InvalidRequirement, Requirement

from ..parsers.common import canonical_name
from ..resolvers.pinned import PinnedRequirement
from ..resolvers.python import TARGET

Edges = dict[str, list[str]]                      # canonical name -> raw Requires-Dist strings


def requires_of(raw: list[str], extras: frozenset[str]) -> list[tuple[str, frozenset[str]]]:
    """The (package, requested extras) pairs a package pulls in for CPython 3.12 on linux, given the extras requested of it."""
    out = []
    for text in raw:
        try:
            req = Requirement(text)
        except InvalidRequirement:
            continue
        ok = True
        if req.marker is not None:
            try:
                ok = req.marker.evaluate({**TARGET, "extra": ""}) or any(req.marker.evaluate({**TARGET, "extra": e}) for e in extras)
            except InvalidMarker:
                ok = True
        if ok:
            out.append((canonical_name(req.name), frozenset(req.extras)))
    return out


def reach(roots: list[tuple[str, frozenset[str]]], present: set[str], edges: Edges) -> set[str]:
    """Packages reachable from the roots that exist in the world. A root or dependency absent from the world is simply not reached."""
    seen: dict[str, frozenset[str]] = {}
    todo = list(roots)
    while todo:
        name, extras = todo.pop()
        if name not in present:
            continue
        have = seen.get(name)
        if have is not None and extras <= have:
            continue
        seen[name] = (have or frozenset()) | extras
        todo += requires_of(edges.get(name, []), seen[name])
    return set(seen)


def closure(pinned: list[PinnedRequirement], roots: list[tuple[str, frozenset[str]]], edges: Edges) -> set[str]:
    return reach(roots, {p.name for p in pinned}, edges)


def fetch_edges(fetch_wheels: Callable[[str], list[dict]], read_metadata: Callable[[list[str]], dict], pinned: list[PinnedRequirement]) -> Edges:
    """Requires-Dist for every pinned package, read from the wheels that the hash-pinned lock selects (offline, in the sandbox)."""
    from ..resolvers.pinned import render_lock
    from ..worlds.builder import wheels_for
    files = fetch_wheels(render_lock(pinned))
    by_name: dict[str, str] = {}
    for p in pinned:
        match = [f for f in files if wheels_for([p], [f])]
        if match:
            by_name[p.name] = match[0]["name"]
    meta = read_metadata(sorted(set(by_name.values())))
    return {name: meta.get(wheel, {}).get("requires", []) for name, wheel in by_name.items()}
