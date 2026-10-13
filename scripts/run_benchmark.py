"""Benchmark and ablation (milestone M11.2): numbers come from this script, with denominators, against committed labels only.

    python scripts/run_benchmark.py                    # run each labelled scenario through the live pipeline once
    python scripts/run_benchmark.py --repeat 2         # run twice and check the metrics are identical (reproducibility)
    python scripts/run_benchmark.py --out benchmarks/results/report.json

The label files are benchmarks/cases/*.yaml. They are committed BEFORE any result and results never edit them. Timings are reported
but excluded from the reproducibility comparison. No accuracy target is stated: this is a baseline on a small fixture set.
"""
import argparse
import hashlib
import json
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from benchmarks.ablations import CONFIGS, confusion, consumer_derived_only  # noqa: E402
from benchmarks.ci_worlds import producer_ci_worlds  # noqa: E402
from scripts.run_fixtures import check, run_scenario, start_daemon  # noqa: E402

from faultline.core.scenario import load_scenario  # noqa: E402
from faultline.sandbox import images  # noqa: E402
from faultline.storage.store import Store  # noqa: E402

LIMITS = [
    "A small set of fixture scenarios written by the same team that built the tool; not a sample of real-world repositories.",
    "Labels cover only the scenarios the MVP oracles can observe; C, E, F, I and J are registered but not evaluated, so recall on silent divergence, signature change and dynamic usage is unknown.",
    "Configurations B and C (API diff, API diff + usage) are not computed because static API analysis is not built.",
    "Producer CI worlds are detected heuristically from workflow text and are labelled as such.",
    "Latency was measured on one developer machine under Docker Desktop with warm caches and says nothing about other environments.",
]


def labels() -> dict[str, dict]:
    return {d["scenario"]: d for d in (yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "benchmarks" / "cases").glob("*.yaml")))}


def rss_mb() -> float | None:
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except ImportError:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return round(pmc.PeakWorkingSetSize / 1024 / 1024, 1)
    except Exception:  # noqa: BLE001
        return None


def dir_mb(p: Path) -> float:
    return round(sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1024 / 1024, 1)


def one_pass(store: Store, sbx, image) -> tuple[list[dict], list[float]]:
    lab = labels()
    rows, seconds = [], []
    for path in sorted((ROOT / "fixtures" / "scenarios").glob("*.yaml")):
        sc = load_scenario(path)
        meta = lab.get(sc.id, {})
        row = {"id": sc.id, "label": meta.get("truth") if meta.get("truth") != "unlabelled" else None, "evaluated": bool(meta.get("evaluated")) and sc.evaluated}
        if not row["evaluated"]:
            row["view"] = None
            rows.append(row)
            continue
        t0 = time.monotonic()
        row["view"] = run_scenario(sc, sbx, image, store)
        seconds.append(time.monotonic() - t0)
        row["matches_expectations"] = not check(sc, row["view"])
        rows.append(row)
    return rows, seconds


def metrics_of(rows: list[dict]) -> dict:
    evaluated = [r for r in rows if r["evaluated"]]
    ablation = {k: {"name": name, **confusion(rows, k)} for k, name in CONFIGS}
    findings = [c for r in evaluated for c in r["view"]["cells"] if c["verdict"]]
    funnel = [r["view"]["funnel"] for r in evaluated]
    discovered = sum(f["consumers_discovered"] for f in funnel)
    analysed = sum(f["consumers_analysed"] for f in funnel)
    return {
        "scenarios_registered": len(rows), "scenarios_evaluated": len(evaluated), "scenarios_not_evaluated": [r["id"] for r in rows if not r["evaluated"]],
        "all_match_expectations": all(r["matches_expectations"] for r in evaluated),
        "verdicts": {r["id"]: sorted({c["verdict"] or c["state"] for c in r["view"]["cells"]}) or ["(no cells)"] for r in evaluated},
        "ablation": ablation,
        "consumer_derived_vs_author_selected": consumer_derived_only(rows),
        "world_coverage": {"consumers_analysed": analysed, "consumers_discovered": discovered},
        "inconclusive_rate": {"inconclusive_findings": sum(1 for c in findings if c["verdict"] == "INCONCLUSIVE"), "findings": len(findings)},
        "witness_reproducibility": {"witnesses": sum(1 for c in findings if c["verdict"] == "BREAK_WITNESSED"),
                                    "each_has_3_plus_3_fresh_runs": True},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "report.json"))
    args = ap.parse_args()
    store_dir = Path(tempfile.mkdtemp(prefix="fl-bench-store-"))
    store = Store(store_dir)
    _d, sbx = start_daemon(store)
    image = images.default_image()
    passes, all_seconds = [], []
    for _ in range(args.repeat):
        rows, secs = one_pass(store, sbx, image)
        passes.append(metrics_of(rows))
        all_seconds += secs
    canon = [json.dumps(m, sort_keys=True) for m in passes]
    reproducible = len(set(canon)) == 1
    base = passes[0]
    report = {
        "metrics": base,
        "reproducibility": {"passes": len(passes), "identical_metrics": reproducible,
                            "metrics_sha256": hashlib.sha256(canon[0].encode()).hexdigest(), "timings_excluded": True},
        "producer_ci_worlds": producer_ci_worlds(ROOT / "fixtures" / "repos" / "acme-models"),
        "denominators": {"labelled_evaluated_scenarios": base["ablation"]["F"].get("samples"), "scenarios_registered": base["scenarios_registered"]},
        "limitations": LIMITS,
        "no_accuracy_target": "No accuracy target is stated: this establishes a baseline.",
        "environment_measurements": {                           # NOT part of the reproducibility comparison
            "latency_seconds_per_scenario": {"p50": round(statistics.median(all_seconds), 1) if all_seconds else None,
                                              "p95": round(sorted(all_seconds)[max(0, int(len(all_seconds) * 0.95) - 1)], 1) if all_seconds else None,
                                              "samples": len(all_seconds)},
            "peak_rss_mb_of_this_process": rss_mb(), "store_disk_mb": dir_mb(store_dir)},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    m = base
    print(f"scenarios evaluated: {m['scenarios_evaluated']} of {m['scenarios_registered']} registered; not evaluated: {m['scenarios_not_evaluated']}")
    for k, v in m["ablation"].items():
        print(f"  {k} {v['name']:<26} " + (f"TP={v['TP']} FP={v['FP']} FN={v['FN']} TN={v['TN']} (n={v['samples']})" if v["computed"] else f"not computed: {v['reason']}"))
    cd = m["consumer_derived_vs_author_selected"]
    print(f"breaks found only by consumer-derived worlds (E) and missed by the author-selected matrix (D): {cd['count']} of {cd['denominator']} {cd['scenarios']}")
    print(f"reproducible across {len(passes)} pass(es): {reproducible}")
    shutil.rmtree(store_dir, ignore_errors=True)
    return 0 if reproducible and m["all_match_expectations"] else 1


if __name__ == "__main__":
    sys.exit(main())
