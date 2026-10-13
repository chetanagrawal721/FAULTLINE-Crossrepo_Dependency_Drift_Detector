"""Test-only overlay (PC-5): add the artifact's test packages to a runtime world WITHOUT changing runtime versions.

The overlay world contains every runtime package exactly as the consumer resolved it, plus the test-only packages
(pytest and friends) from the artifact's reference test lock. If a test package needs a different version of a
package the runtime world already has, the runtime version wins and the overlay is marked forced, so the result is
never presented as the consumer's real environment.
"""
from dataclasses import dataclass

from ..core.enums import Scope
from ..resolvers.pinned import PinnedRequirement, parse_pinned_lock, render_lock


@dataclass(frozen=True)
class Overlay:
    lock_text: str                               # runtime packages + added test packages
    test_packages: tuple[str, ...]               # canonical names added by the overlay
    conflicts: tuple[tuple[str, str, str], ...]  # (name, runtime version kept, test version wanted)

    @property
    def forced(self) -> bool:
        return bool(self.conflicts)

    def scopes(self) -> dict[str, Scope]:
        return {n: Scope.TEST for n in self.test_packages}


def overlay_lock(runtime_text: str, test_text: str) -> Overlay:
    runtime = parse_pinned_lock(runtime_text)
    tests = parse_pinned_lock(test_text)
    have = {r.name: r for r in runtime}
    added: list[PinnedRequirement] = []
    conflicts: list[tuple[str, str, str]] = []
    for t in tests:
        r = have.get(t.name)
        if r is None:
            added.append(t)
        elif r.version != t.version:
            conflicts.append((t.name, r.version, t.version))      # runtime wins
    return Overlay(lock_text=render_lock(runtime + added), test_packages=tuple(sorted(a.name for a in added)),
                   conflicts=tuple(sorted(conflicts)))
