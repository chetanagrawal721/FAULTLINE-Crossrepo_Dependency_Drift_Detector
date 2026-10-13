"""Projection: the world the artifact actually experiences inside a consumer.

The projection is the consumer's resolved runtime world, compared with the artifact's reference world. Two consumers that
resolve identically share one projection, hence one cell.
"""
from dataclasses import dataclass

from ..core.hashing import object_hash
from ..resolvers.pinned import PinnedRequirement
from .reference import ReferenceWorld

RUNTIME = {"name": "cpython", "version": "3.12.15"}


@dataclass(frozen=True)
class DeltaItem:
    name: str
    reference: str | None
    consumer: str | None            # None means absent from the consumer's world


@dataclass(frozen=True)
class Projection:
    pinned: tuple[PinnedRequirement, ...]      # the consumer's version (and hashes) for each closure package it has
    absent: tuple[str, ...]
    delta: tuple[DeltaItem, ...]
    key: str                                   # identity of the projection, used to deduplicate cells

    @property
    def no_drift(self) -> bool:
        return not self.delta

    @property
    def lock_text(self) -> str:
        from ..resolvers.pinned import render_lock
        return render_lock(list(self.pinned))


def project(ref: ReferenceWorld, consumer: list[PinnedRequirement]) -> Projection:
    """The consumer's resolved runtime world, compared with the reference over the UNION of package names.

    Packages only the consumer has (for example what a newer pydantic pulls in) belong to the delta: the artifact runs next to
    them. Reference packages the consumer lacks are ABSENT. Deltas are candidate causes, never findings by themselves.
    """
    have = {c.name: c for c in consumer}
    want = ref.versions
    absent = sorted(n for n in want if n not in have)
    delta = [DeltaItem(n, want.get(n), have[n].version if n in have else None)
             for n in sorted(set(want) | set(have)) if want.get(n) != (have[n].version if n in have else None)]
    pinned = tuple(sorted(consumer, key=lambda x: x.name))
    key = object_hash({"runtime": RUNTIME, "versions": [(p.name, p.version) for p in pinned], "reference": ref.world_hash})
    return Projection(pinned, tuple(absent), tuple(delta), key)
