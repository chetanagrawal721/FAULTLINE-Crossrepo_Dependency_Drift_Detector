"""setup.cfg reader (declarative setuptools metadata only). It is INI text: nothing is executed. Anything dynamic (attr:, file:)
is reported, never evaluated."""
import configparser

from packaging.requirements import InvalidRequirement, Requirement

from ..common import Dependency, ManifestError, ManifestResult, SnapshotFS, canonical_name, failed


def _lines(value: str | None) -> list[str]:
    return [ln.strip() for ln in (value or "").replace(";", ";").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def parse_setup_cfg(fs: SnapshotFS, rel: str) -> ManifestResult:
    try:
        text = fs.read_text(rel)
    except ManifestError as e:
        return failed("setup_cfg", rel, e)
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(text)
    except configparser.Error as e:
        return failed("setup_cfg", rel, ManifestError(f"{rel} is not valid INI: {e}", path=rel))
    res = ManifestResult("setup_cfg", rel)
    res.meta.update(name=cp.get("metadata", "name", fallback=None), version=cp.get("metadata", "version", fallback=None),
                    requires_python=cp.get("options", "python_requires", fallback=None))
    if str(res.meta["version"] or "").startswith(("attr:", "file:")):
        res.meta["version"] = None
        res.meta["dynamic_version"] = True                 # informational: the version does not affect which dependencies are declared
    sections = [("main", "options", "install_requires")]
    seen = False
    for group, section, key in sections:
        raw = cp.get(section, key, fallback=None)
        if raw is not None:
            seen = True
        for ln in _lines(raw):
            _add(res, ln, group, rel)
    if cp.has_section("options.extras_require"):
        seen = True
        for extra, raw in cp.items("options.extras_require"):
            for ln in _lines(raw):
                _add(res, ln, f"optional:{extra.split(':')[0].strip()}", rel)
    if not seen and not cp.has_section("metadata"):
        res.status = "UNSUPPORTED"
        res.add("NO_METADATA", "setup.cfg has neither [metadata] nor [options]")
    res.meta["name_line"] = next((i for i, t in enumerate(text.splitlines(), 1) if t.strip().startswith("name")), None)
    return res


def _add(res: ManifestResult, line: str, group: str, rel: str) -> None:
    try:
        r = Requirement(line)
    except InvalidRequirement as e:
        res.add("UNPARSEABLE_REQUIREMENT", f"cannot parse {line[:80]!r}: {e}", None, rel)
        return
    res.dependencies.append(Dependency(canonical_name(r.name), r.name, str(r.specifier), tuple(sorted(r.extras)),
                                       str(r.marker) if r.marker else None, "registry", None, group, rel))
