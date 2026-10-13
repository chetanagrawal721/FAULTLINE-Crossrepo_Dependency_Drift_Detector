"""Run every committed fixture scenario through the LIVE pipeline and compare with its expectations (milestone M5.5).

    python scripts/run_fixtures.py --assert            # exit 1 on any mismatch
    python scripts/run_fixtures.py --only A,D,H        # a subset

Each scenario's repositories become local git remotes, are fetched through the sandbox like any repository, analysed, related,
projected into cells, executed (3 + 3 fresh runs) and attributed. Nothing here is mocked. TP, FP and FN are computed ONLY against
the ground-truth labels committed in the scenario files; the sample size and scope are printed with them.
"""
import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from tests.liveenv import ingest_all  # noqa: E402
from tests.livefix import read_tree  # noqa: E402

from faultline.analysis.live import run_live_analysis  # noqa: E402
from faultline.analysis.read import analysis_view  # noqa: E402
from faultline.core.scenario import Scenario, load_scenario  # noqa: E402
from faultline.sandbox import images, runner  # noqa: E402
from faultline.sandbox.client import SandboxClient  # noqa: E402
from faultline.sandbox.sandboxd import Daemon, serve  # noqa: E402
from faultline.storage.db import connect  # noqa: E402
from faultline.storage.migrate import migrate  # noqa: E402
from faultline.storage.store import Store  # noqa: E402

TOKEN = "fixture-run-token-not-secret"
SCOPE = ("Measured only on the committed fixture scenarios, against their committed ground-truth labels. This is NOT an estimate of "
         "accuracy on real-world repositories.")


def start_daemon(store: Store) -> tuple[Daemon, SandboxClient]:
    runner.sweep_orphans()
    d = Daemon(TOKEN, store=store)
    srv = serve("127.0.0.1", 0, d)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    d.port = srv.server_address[1]
    return d, SandboxClient(port=d.port, token=TOKEN, timeout=900)


def run_scenario(sc: Scenario, sbx: SandboxClient, image: str, store: Store) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"fl-fixture-{sc.id}-"))
    conn = connect(tmp / "t.db")
    migrate(conn)
    repos = {f"rm_{sc.id.lower()}_{sc.artifact.repo.replace('-', '')}": (f"faultline-demo/{sc.artifact.repo}", read_tree(ROOT / sc.artifact.path))}
    for c in sc.consumers:
        repos[f"rm_{sc.id.lower()}_{c.repo.replace('-', '')}"] = (f"faultline-demo/{c.repo}", read_tree(ROOT / c.path))
    for b in sc.bystanders:
        repos[f"rm_{sc.id.lower()}_{b.repo.replace('-', '')}"] = (f"faultline-demo/{b.repo}", read_tree(ROOT / b.path))
    apid, _ids = ingest_all(conn, sbx, image, store, repos)
    res = run_live_analysis(conn, sbx, image, store, apid)
    view = analysis_view(conn, res.analysis_id).model_dump()
    # per cell: did the FIRST consumer-side run already fail with an artifact failure? (used only by the benchmark ablation)
    first = {}
    for c in view["cells"]:
        row = conn.execute("SELECT r.failure_class FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id WHERE j.cell_id=? AND j.side='test' "
                           "ORDER BY r.created_at, r.run_index LIMIT 1", (c["id"],)).fetchone()
        first[c["id"]] = bool(row and row[0] == "ARTIFACT_FAILURE")
    view["_first_run_failed"] = first
    return view


def check(sc: Scenario, a: dict) -> list[str]:
    """Differences between what Faultline produced and the scenario's expectations (empty list = match)."""
    bad: list[str] = []
    actionable = {(r["producer"].split("/")[1].split(":")[0], r["consumer"].split("/")[1].split(":")[0]): r for r in a["relationships"] if r["actionable"]}
    for e in sc.expect.relationships:
        r = actionable.get((e.producer, e.consumer))
        if r is None or r["level"] != e.level:
            bad.append(f"relationship {e.producer} -> {e.consumer} expected {e.level}, got {r['level'] if r else 'none'}")
    related = {c for _, c in actionable}
    for u in sc.expect.unrelated:
        if u in related:
            bad.append(f"{u} must have no actionable relationship but has one")
    tray = {(r["producer"].split("/")[1].split(":")[0], r["consumer"].split("/")[1].split(":")[0]) for r in a["relationships"] if r["status"] == "SUSPECTED"}
    want = {(s.producer, s.consumer) for s in sc.expect.suspected}
    if tray != want:
        bad.append(f"suspected tray expected {sorted(want)}, got {sorted(tray)}")
    for e in sc.expect.cells:
        cells = [c for c in a["cells"] if any(x.split("/")[1].split(":")[0] == e.consumer for x in c["consumers"])]
        if not cells:
            bad.append(f"{e.consumer}: no cell was built")
            continue
        c = cells[0]
        if e.state == "NO_DRIFT":
            if c["state"] != "NO_DRIFT":
                bad.append(f"{e.consumer}: expected NO_DRIFT, got {c['state']} (delta {[d['name'] for d in c['delta']]})")
            continue
        if sorted(d["name"] for d in c["delta"]) != sorted(e.delta):
            bad.append(f"{e.consumer}: delta expected {sorted(e.delta)}, got {sorted(d['name'] for d in c['delta'])}")
        if e.verdict and c["verdict"] != e.verdict.value:
            bad.append(f"{e.consumer}: verdict expected {e.verdict.value}, got {c['verdict']}")
        if e.signature and not (c["headline"] and e.signature.exc_type in c["headline"] and e.signature.message_contains in c["headline"]):
            bad.append(f"{e.consumer}: the headline does not contain the expected signature ({e.signature.exc_type}: {e.signature.message_contains})")
        if e.attribution:
            att = c.get("attribution")
            if not att or att["minimal"] != e.attribution.minimal_set or att["sidedness"] != e.attribution.sidedness:
                bad.append(f"{e.consumer}: attribution expected {e.attribution.minimal_set}/{e.attribution.sidedness}, got {att and (att['minimal'], att['sidedness'])}")
    if not sc.expect.cells and any(c["verdict"] for c in a["cells"]):
        bad.append("no finding was expected, but one was produced")
    return bad


def predicted_positive(a: dict) -> bool:
    return any(c["verdict"] in ("BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED") for c in a["cells"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assert", dest="do_assert", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=str(ROOT / "var" / "fixtures-report.json"))
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    scenarios = [load_scenario(p) for p in sorted((ROOT / "fixtures" / "scenarios").glob("*.yaml"))]
    scenarios = [s for s in scenarios if not only or s.id in only]
    store = Store(Path(tempfile.mkdtemp(prefix="fl-fixture-store-")))
    _d, sbx = start_daemon(store)
    image = images.default_image()
    rows, tp = [], dict(TP=0, FP=0, FN=0, TN=0)
    for sc in scenarios:
        if sc.kind == "real_world":
            rows.append({"id": sc.id, "title": sc.title, "evaluated": False, "reason": "real-world case: run by tests/integration/test_real1.py (needs network)", "label": sc.truth})
            print(f"{sc.id}: NOT RUN HERE - real-world case, see tests/integration/test_real1.py")
            continue
        if not sc.evaluated:
            rows.append({"id": sc.id, "title": sc.title, "evaluated": False, "reason": sc.not_evaluated_reason, "label": sc.truth})
            print(f"{sc.id}: NOT EVALUATED - {sc.not_evaluated_reason}")
            continue
        a = run_scenario(sc, sbx, image, store)
        diffs = check(sc, a)
        pos = predicted_positive(a)
        truth_pos = sc.truth in ("break", "silent_divergence")
        if sc.truth is not None:
            tp["TP" if pos and truth_pos else "FP" if pos else "FN" if truth_pos else "TN"] += 1
        verdicts = sorted({c["verdict"] or c["state"] for c in a["cells"]}) or ["(no cells)"]
        rows.append({"id": sc.id, "title": sc.title, "evaluated": True, "label": sc.truth, "predicted_positive": pos, "verdicts": verdicts,
                     "match": not diffs, "differences": diffs})
        print(f"{sc.id}: {'OK' if not diffs else 'MISMATCH'}  label={sc.truth} verdicts={verdicts}")
        for d in diffs:
            print("   -", d)
    evaluated = [r for r in rows if r["evaluated"]]
    report = {"scenarios_total": len(rows), "scenarios_evaluated": len(evaluated), "scenarios_not_evaluated": len(rows) - len(evaluated),
              "all_match": all(r["match"] for r in evaluated), "confusion": tp, "labelled_samples": sum(tp.values()), "scope": SCOPE, "rows": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nsamples: {report['scenarios_evaluated']} evaluated of {report['scenarios_total']} registered; labelled: {report['labelled_samples']}; "
          f"TP={tp['TP']} FP={tp['FP']} FN={tp['FN']} TN={tp['TN']}\n{SCOPE}")
    return 1 if args.do_assert and not report["all_match"] else 0


if __name__ == "__main__":
    sys.exit(main())
