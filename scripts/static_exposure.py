"""Static exposure for one artifact against package version pairs (M6.2 to M6.4). Nothing is imported or run.

  python scripts/static_exposure.py --source fixtures/repos/acme-http --pair urllib3=old.whl,new.whl [--threshold 0.9]

For every pair the API surfaces of the two wheels are compared, the artifact's source is indexed, and the references that touch a
changed symbol are listed with the result of a binding simulation. The verdict comes from the same decision table the rest of the
product uses. A static verdict is explanatory: it never says that anything failed.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from faultline.diff.delta import compute_delta  # noqa: E402
from faultline.diff.surface import extract, read_wheel  # noqa: E402
from faultline.usage.exposure import compute_exposure  # noqa: E402
from faultline.usage.index import build_index  # noqa: E402
from faultline.verdicts.engine import Evidence, decide  # noqa: E402


def package_of(files: dict[str, bytes], name: str) -> str:
    """The import package inside a wheel: the distribution name if it is a directory there, else the only top-level package."""
    tops = sorted({p.split("/")[0] for p in files if "/" in p and not p.split("/")[0].endswith((".dist-info", ".data"))})
    guess = name.replace("-", "_").lower()
    return guess if guess in tops else (tops[0] if len(tops) == 1 else guess)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, type=Path, help="the artifact's source directory")
    ap.add_argument("--pair", action="append", required=True, metavar="PKG=OLD.whl,NEW.whl")
    ap.add_argument("--threshold", type=float, default=0.9)
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    a = ap.parse_args()
    files = {p.relative_to(a.source).as_posix(): p.read_bytes() for p in sorted(a.source.rglob("*")) if p.is_file() and p.suffix in (".py", ".ipynb")}
    deltas, divergent = {}, set()
    for spec in a.pair:
        name, _, rest = spec.partition("=")
        old_w, _, new_w = rest.partition(",")
        old_f, new_f = read_wheel(Path(old_w)), read_wheel(Path(new_w))
        pkg = package_of(new_f, name)
        deltas[pkg] = compute_delta(extract(old_f, pkg), extract(new_f, pkg))
        divergent.add(pkg)
    res = compute_exposure(build_index(files, divergent), deltas)
    out = decide(Evidence(relationship_level="L2", cell_state="ANALYZED", coverage_threshold=a.threshold, **res.evidence_fields()))
    if a.json:
        print(json.dumps({"verdict": out.outcome, "rule": out.rule, "sub_label": out.sub_label, "reasons": list(out.reasons), "coverage": res.coverage.text(),
                          "limits": list(res.static_limits), "exposures": [e.to_json() for e in res.exposures],
                          "deltas": {k: v.to_json() for k, v in deltas.items()}}, indent=2))
        return 0
    print(f"{out.outcome}{' (' + out.sub_label + ')' if out.sub_label else ''}  [rule {out.rule}]  coverage {res.coverage.text()}  (static: nothing was executed)")
    for pkg, d in deltas.items():
        print(f"  {pkg}: {len(d.entries)} public change(s), {sum(e.breaking for e in d.entries)} breaking{'; surface is incomplete' if d.incomplete else ''}")
    for e in res.exposures:
        flag = {False: "does not bind", True: "still binds", None: "not simulated"}[e.static_ok]
        print(f"  {e.ref.ref_id}  {e.ref.kind.lower()} of {e.change.symbol}  [{e.change.change}, {flag}]")
        for d in e.change.details[:3]:
            print(f"      {d}")
    for r in out.reasons:
        print(f"  note: {r}")
    for r in res.dynamic:
        print(f"  unresolved: {r.ref_id} {r.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
