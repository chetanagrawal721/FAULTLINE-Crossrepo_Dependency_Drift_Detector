"""Ablation of the Faultline design (configurations A to G), computed from the SAME real runs and the committed labels.

A version-only            flag any dependency difference inside the artifact's closure (no execution)
B API diff                NOT COMPUTED: static API analysis is not built (M6.2)
C API diff + usage        NOT COMPUTED: usage index is not built (M6.3)
D author-selected matrix  test only the worlds the producer's CI would test (heuristic; the artifact's own world), so consumer worlds are never run
E consumer-derived worlds run the oracle once in each consumer-derived world (no witness discipline)
F + witness discipline    a break needs 3 fresh reference passes and 3 fresh consumer failures with one signature
G + ddmin                 F, and the cause is attributed (two-sided)

The headline is the number of breaks that E (consumer-derived worlds) finds and D (author-selected matrix) misses.
"""
CONFIGS = [
    ("A", "version-only"), ("B", "API diff"), ("C", "API diff + usage"), ("D", "author-selected matrix"),
    ("E", "consumer-derived worlds"), ("F", "+ witness discipline"), ("G", "+ ddmin attribution"),
]
NOT_COMPUTED = {"B": "static API analysis is not built (M6.2)", "C": "the usage index is not built (M6.3)"}


def predict(config: str, view: dict) -> bool | None:
    """Does this configuration flag the scenario as a break? None = the configuration cannot be computed."""
    if config in NOT_COMPUTED:
        return None
    cells = view["cells"]
    if config == "A":
        return any(c["state"] != "NO_DRIFT" and c["delta"] for c in cells)
    if config == "D":
        return False                                  # the author's world (the reference) passes by construction: consumer worlds are not run
    first = view.get("_first_run_failed", {})
    if config == "E":
        return any(first.get(c["id"]) for c in cells)
    witnessed = any(c["verdict"] in ("BREAK_WITNESSED", "SILENT_DIVERGENCE_WITNESSED") for c in cells)
    if config == "F":
        return witnessed
    if config == "G":
        return witnessed and all(c.get("attribution") for c in cells if c["verdict"] == "BREAK_WITNESSED")
    raise ValueError(config)


def confusion(rows: list[dict], config: str) -> dict:
    """TP/FP/FN/TN against the committed labels only, over scenarios that have a label and were evaluated."""
    c = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}
    for r in rows:
        if r["label"] is None or not r["evaluated"]:
            continue
        pred = predict(config, r["view"])
        if pred is None:
            return {"computed": False, "reason": NOT_COMPUTED[config]}
        truth = r["label"] in ("break", "silent_divergence")
        c["TP" if pred and truth else "FP" if pred else "FN" if truth else "TN"] += 1
    return {"computed": True, **c, "samples": sum(c.values())}


def consumer_derived_only(rows: list[dict]) -> dict:
    """Breaks (label: break) that consumer-derived worlds (E) flag and the author-selected matrix (D) misses. Reported even when zero."""
    found = [r["id"] for r in rows if r["evaluated"] and r["label"] == "break" and predict("E", r["view"]) and not predict("D", r["view"])]
    return {"count": len(found), "scenarios": sorted(found),
            "denominator": sum(1 for r in rows if r["evaluated"] and r["label"] == "break"),
            "meaning": "labelled breaks found only by running the artifact in consumer-derived worlds"}
