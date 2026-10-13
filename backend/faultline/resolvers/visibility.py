"""Which package instance can an importer see? Simulates Node's node_modules lookup over lockfile locators.

The lookup is per importer: it starts in the importer's own directory and walks upwards, skipping `node_modules` path
components, taking the first `<dir>/node_modules/<name>` that exists. There is no flat name-to-version map.
"""
import posixpath

from ..parsers.npm.package_lock import NpmInstance


def candidate_dirs(importer: str) -> list[str]:
    """Directories searched, innermost first. '' is the repository (project) root."""
    out, cur = [], importer
    while True:
        if posixpath.basename(cur) != "node_modules":
            out.append(cur)
        if cur == "":
            return out
        cur = posixpath.dirname(cur)


def resolve_from(instances: dict[str, NpmInstance], importer: str, name: str) -> NpmInstance | None:
    """The instance `require(name)` finds from `importer`, following workspace links; None when it does not resolve."""
    for d in candidate_dirs(importer):
        loc = posixpath.join(d, "node_modules", name) if d else f"node_modules/{name}"
        inst = instances.get(loc)
        if inst is None:
            continue
        if inst.link_target is not None:
            return instances.get(inst.link_target)
        return inst
    return None


def importer_visibility(instances: dict[str, NpmInstance], importer: str) -> dict[str, NpmInstance | None]:
    """For every dependency the importer declares: the instance it resolves to (None means the lock cannot satisfy it)."""
    imp = instances.get(importer)
    if imp is None:
        return {}
    names = [n for n, _ in (*imp.dependencies, *imp.dev_dependencies, *imp.peer_dependencies)]
    return {n: resolve_from(instances, importer, n) for n in sorted(set(names))}
