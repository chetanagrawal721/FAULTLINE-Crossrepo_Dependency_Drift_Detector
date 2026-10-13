# Demo script (3 to 5 minutes): Detect, Reproduce, Attribute, Fix

Rule for the whole demo: say the mode on the screen out loud. Every cached or recorded result is labelled; the re-run is live.

## 0. Before you start (not shown)
- `python tools/fl.py up` is running; the mode badge in the top bar reads the mode you are about to claim (LIVE or FIXTURE).
- Warm caches done: `python scripts/warm_caches.py`. A REPLAY pack exists: `python scripts/export_replay.py` (backup).
- Browser open at `http://127.0.0.1:8000/#/app`. The mode banner under the top bar and the mode badge show what you are about to claim; **Capabilities** lists what this deployment can and cannot do.

## 1. The problem in one sentence (20 s)
"A shared library works in its own repository and breaks in a consumer's, because the two resolve different dependency versions. Existing
tools show that versions differ. Faultline shows that something fails, reproduces it, and says which package caused it."

## 2. Detect (60 s)
1. Open **New analysis** and paste the shared artifact URL and a consumer URL, then **Pin repositories**. Point at the **pinned commit** next to each:
   "every claim from here on is about these exact commits, not a branch".
2. Tick the confirmation and press **Run analysis**; the **Analysis run** page follows the real job. While it runs, say: "it related the repositories using evidence, built the consumer's dependency world offline in a
   sandbox, and will run the artifact in both worlds three times each."
3. **Overview** funnel: read the numbers. "N consumers discovered, M analysed; the rest are listed with the reason, not hidden."
4. Relationships: open one. "File and line in both manifests at the pinned commit. A look-alike class goes to the suspected tray and never becomes a finding."

## 3. Reproduce (60 s)
1. **World matrix**: select the row; the **exact delta** (for example `werkzeug: 2.2.3 → 3.0.6`), the runtime and platform, the modules exercised.
2. Open the finding, then **Open witness**: **BREAK WITNESSED**. Show the six-run board, all "Fresh execution: Yes", and the normalised signature.
   Say: "reference passed 3 of 3, consumer failed 3 of 3 with the identical signature. That is what we call a witness."
3. Open **raw output** of one failing run. This is the real exception.
4. (Fixture mode) Press **Re-run** and say "this one is live, not cached".

## 4. Attribute (45 s)
Open the **why-path**: relationship evidence, delta, oracle plan, verdict predicate, attribution. Point at the label **attribution experiment (forced world)**:
"adding only this package to the reference world reproduces the failure; reverting only it in the consumer's world removes it. Those worlds are
experiments we built, not environments anyone uses."

## 5. Fix (45 s)
Run the remediation for the finding: a **diff only** (`werkzeug<3`), the world re-resolved by the native resolver, re-run 3 + 3, label **VERIFIED**
(or SUGGESTED/REJECTED with the reason). "Nothing is pushed. You get a diff."

## 6. Evidence bundle and the real-world case (45 s)
1. Download the bundle, run `python -m faultline.witnesses.bundle witness.zip` (verifies hashes), mention `python -m faultline.witnesses.replay`.
2. Real historical case REAL1: Flask 2.2.2 resolved before and after Werkzeug 3.0.0, linked to the public issue
   `pallets/werkzeug#2789`. "Same pipeline, public registries, resolution date recorded."

## 7. Close (15 s)
"Witnesses, not warnings. Where we are not sure, we say INCONCLUSIVE and what we did not check. We never say compatible."

## Fallbacks
| Failure | Do this |
|---|---|
| GitHub or network down | FIXTURE mode from the local mirror (`var/mirror`) and warm wheelhouse; say "network is off, this is the warmed fixture mode" |
| Docker down | Start the REPLAY pack; badge reads RECORDED; Re-run is disabled; say so |
| A live run is slow | Show the previous run's record, labelled, then the why-path |
