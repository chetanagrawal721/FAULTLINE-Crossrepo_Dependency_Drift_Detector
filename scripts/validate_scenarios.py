"""TC-1.1.1: scenario files validate, point at real pinned lock files, and their expected deltas match reality.

    python scripts/validate_scenarios.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.core.scenario import Scenario, load_scenario  # noqa: E402
from faultline.resolvers.pinned import diff_locks, parse_pinned_lock  # noqa: E402


def validate(path: Path, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        sc: Scenario = load_scenario(path)
    except Exception as exc:  # noqa: BLE001
        return [f"{path.name}: {exc}"]
    if path.stem != sc.id:
        errors.append(f"{path.name}: id {sc.id!r} does not match the file name")
    if sc.kind == "real_world":                       # no local lock files: the world is resolved from public registries at the recorded cutoffs
        if not (sc.real_source and sc.time_machine and sc.public_evidence):
            errors.append(f"{path.name}: a real_world scenario needs real_source, time_machine and at least one public_evidence link")
        elif not (sc.time_machine.reference_cutoff < sc.time_machine.consumer_cutoff):
            errors.append(f"{path.name}: the reference cutoff must be earlier than the consumer cutoff")
        return errors
    art_dir = root / sc.artifact.path
    try:
        ref = parse_pinned_lock((art_dir / sc.artifact.runtime_lock).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return errors + [f"{path.name}: reference lock: {exc}"]
    if any(not r.hashes for r in ref):
        errors.append(f"{path.name}: reference lock has packages without sha256 hashes")
    consumers = {c.repo: c for c in sc.consumers}
    for cell in sc.expect.cells:
        c = consumers[cell.consumer]
        try:
            lock = parse_pinned_lock((root / c.path / c.lock).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: {cell.consumer} lock: {exc}")
            continue
        actual = sorted(diff_locks(ref, lock))
        if cell.control and cell.control.kind == "unrelated_drift":
            # the locks differ only in packages the artifact cannot reach: its closure is unchanged, so there is no drift
            outside = [n for n in actual if n not in {r.name for r in ref}]
            if outside != actual or cell.state != "NO_DRIFT":
                errors.append(f"{path.name}: {cell.consumer} claims unrelated drift but the locks differ inside the artifact closure: {actual}")
            continue
        if actual != sorted(cell.delta):
            errors.append(f"{path.name}: {cell.consumer} expected delta {sorted(cell.delta)} but the locks differ in {actual}")
        if (cell.state == "NO_DRIFT") != (not actual):
            errors.append(f"{path.name}: {cell.consumer} state {cell.state} contradicts the lock difference")
        if cell.attribution:
            missing = [p for p in cell.attribution.minimal_set if p not in actual]
            if missing:
                errors.append(f"{path.name}: attribution names packages that do not differ: {missing}")
    if not sc.breaks and not any(c.control for c in sc.expect.cells) and not sc.expect.suspected and sc.evaluated:
        errors.append(f"{path.name}: a scenario without a witness must declare a control with a reason")
    return errors


def main() -> int:
    files = sorted((ROOT / "fixtures" / "scenarios").glob("*.yaml"))
    errors = [e for f in files for e in validate(f)]
    for e in errors:
        print("ERROR:", e)
    print(f"{len(files)} scenario files checked:", "FAILED" if errors else "ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
