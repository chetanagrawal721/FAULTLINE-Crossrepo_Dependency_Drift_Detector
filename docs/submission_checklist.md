# Submission checklist

Tick an item only when you have checked it yourself. Each claim must trace to a test id or a measured number.

## Product
- [ ] `python tools/fl.py ci` is green on a clean checkout (and the GitHub Actions run is green).
- [ ] `python scripts/run_fixtures.py --assert` passes (7 evaluated scenarios).
- [ ] `python scripts/conformance_report.py` was run; its header is quoted exactly (MVP conformant, or NOT conformant with the rows listed).
- [ ] Replay of one bundle was done on a DIFFERENT computer (TC-5.2.2) and the outcome recorded in `LOGBOOK.md`.
- [ ] Network-off FIXTURE run (TC-12.2.1) and Docker-off REPLAY run (TC-12.2.2) were rehearsed.
- [ ] Three timed rehearsals by three different members, each 3 to 5 minutes (TC-12.3.1); Q&A drill done (TC-12.3.2).

## Claims audit (TC-12.4.1)
| Claim on a slide or in the README | Evidence (test id or number) |
|---|---|
| A witness is 3 fresh reference passes and 3 fresh consumer failures with one signature | `tests/unit/test_witness_decision.py`, M1.6 |
| The verdict is deterministic and uses no LLM | `tests/unit/test_verdict_table.py` (TC-4.5.2, TC-4.5.3) |
| Relationships need evidence; look-alikes never become findings | `tests/integration/test_relationships.py` (TC-4.1.2) |
| The cause is attributed two-sided | `tests/integration/test_attribution.py` (TC-5.1.2) |
| Reproduced a real public break (Flask 2.2.2, Werkzeug 3.0.0) | `fixtures/verification/REAL1.md`, `tests/integration/test_real1.py` |
| Fixture accuracy numbers | `benchmarks/results/report.json` (denominators and limits are printed in it) |

Forbidden wording in all materials: "proof", "guarantee", "compatible" (except in "not a statement that they are compatible"), "AI detected".

## Honest limits to state on the limits slide
- Docker Desktop isolation (shared kernel); the fetch zone is limited to GitHub and PyPI by a proxy allowlist.
- Python verified end to end; npm and Maven are inventory only.
- O-bind is bind-level only (calls are not executed; star, dynamic and instance-method call sites are not checked).
- Scenarios E and J have contract-replay tests but are outside the benchmark denominator; F and I (static analysis) are registered but not evaluated.
- Small fixture set: no claim about real-world accuracy.

## Materials
- [ ] Slides within the template limit; every number comes from a script.
- [ ] README quickstart followed by a teammate on a clean machine (TC-12.4.2).
- [ ] Backup recording, clearly labelled as a recording.
