"""Forced counterfactual worlds for attribution. They are EXPERIMENTS: a package set that no repository actually resolved.

Built from two real worlds by applying (or reverting) a chosen subset of their differences, with the exact hashes of the
real worlds' wheels, installed with --no-deps like every other world. Never presented as observed.
"""
from dataclasses import dataclass

from ..resolvers.pinned import PinnedRequirement, render_lock

LABEL = "attribution experiment (forced world)"


@dataclass(frozen=True)
class ForcedWorld:
    lock_text: str
    applied: tuple[str, ...]              # package names whose value was taken from the other world
    base: str                             # 'reference' or 'consumer'
    label: str = LABEL


def force(base: list[PinnedRequirement], other: list[PinnedRequirement], subset: set[str] | frozenset[str], base_name: str) -> ForcedWorld:
    """`base` with each package in `subset` replaced by its value in `other` (added if only `other` has it, removed if only `base` has it)."""
    want = {p.name: p for p in other}
    out = {p.name: p for p in base}
    for name in subset:
        if name in want:
            out[name] = want[name]
        else:
            out.pop(name, None)
    return ForcedWorld(render_lock(sorted(out.values(), key=lambda p: p.name)), tuple(sorted(subset)), base_name)
