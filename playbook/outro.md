

---

# PART E - APPENDICES

## E.1 Tracker command reference

| Command | Effect | Logged |
|---|---|---|
| `python tools/track.py status [--gate G]` | Progress by gate and milestone | no |
| `python tools/track.py next` | Current or next milestone and its test cases | no |
| `python tools/track.py start M1.4` | Marks in progress | yes |
| `python tools/track.py tc TC-1.4.1 pass --evidence <path> --note "..."` | Records a test case result. PASS requires evidence | yes |
| `python tools/track.py done M1.4` | Completes a milestone only if all its test cases passed | yes |
| `python tools/track.py done M1.4 --waive "reason"` | Completes with a recorded waiver | yes |
| `python tools/track.py block M1.4 --reason "..."` | Marks blocked | yes |
| `python tools/track.py gate C [--check]` | Checks, then declares a gate. Requires prerequisite gates | yes |
| `python tools/track.py note "text"` | Free-form logbook entry (decisions, surprises) | yes |
| `python tools/track.py render` | Regenerates `CHECKLIST.md` and this playbook | no |
| `--by "Name"` (before the subcommand) | Overrides the author recorded in the log | n/a |

## E.2 Logbook entry format

```text
### 2026-10-14 11:32 UTC | TC PASS | TC-1.4.1 | by Chetan
- Reference passes, consumer fails
- evidence: evidence/M1.4/TC-1.4.1.txt
- ran make e2e SCENARIO=D, 3/3 both sides
```

Event types: `START`, `TC PASS`, `TC FAIL`, `DONE`, `DONE (waived)`, `BLOCKED`, `GATE DECLARED`, `NOTE`.
Write a `NOTE` whenever you make a decision the code does not explain: a changed fixture, a replaced example, a measured number, a surprise.

## E.3 Verdict vocabulary (use exactly these words)

| Verdict | Meaning | Never say |
|---|---|---|
| BREAK WITNESSED | Reference passes 3/3 and consumer fails 3/3 with the same normalized signature | "incompatible", "proven" |
| SILENT DIVERGENCE WITNESSED | Both succeed; normalized results differ reproducibly | "bug found by AI" |
| NO DIVERGENCE OBSERVED | Every exposed interaction that was exercised matched | "compatible", "safe" |
| EXPOSED | A changed API is statically used; execution not completed | "will break" |
| POTENTIAL | A breaking API change exists; usage not confidently resolved | "risk 87%" |
| NOT EXPOSED | No resolved reference touches a change and coverage is sufficient (coverage always shown) | "unaffected" |
| INCONCLUSIVE | Not enough evidence, with a reason | "clean" |
| HYGIENE | Drift with no confirmed cross-repository relationship | "harmless" |

## E.4 Facts you must still verify before relying on them

These came from the design discussion and have not been run. They are tested in **M1.0** and **M12.1**. Do not put them on a slide until the verification record exists.

- pydantic v1 to v2: `Optional[X]` without a default becomes required; `from pydantic import BaseSettings` raises; union resolution differences.
- Werkzeug 3.0 removing `url_quote`, and which Flask releases import it.
- urllib3 2.x removing `Retry(method_whitelist=...)`.
- PyJWT 2 requiring `algorithms=` in `decode`.
- `uv` flags (`--exclude-newer`, `--no-build`, `--python-platform`), offline install with `--require-hashes`.
- `griffe.find_breaking_changes` kinds, pyright rule names.

## E.5 Common failure patterns and what to do

| Symptom | Likely cause | Action |
|---|---|---|
| A witness appears but the reference also fails sometimes | Flaky test or hidden network use | Classify as INCONCLUSIVE(flaky); find the nondeterminism; do not raise k to hide it |
| Consumer fails with `ModuleNotFoundError` for pytest | Test overlay missing | HARNESS_FAILURE; fix the overlay |
| Forced world fails with an unrelated import error during ddmin | Coupled package missing | Group coupled packages; the signature check prevents false attribution |
| `database is locked` | SQLite contention | Retry with backoff; confirm one writer per process; see the PostgreSQL trigger ADR |
| Demo works on your laptop but not on the demo machine | Unpinned image or cold cache | Run `scripts/warm_caches.py` and the network-off drill on the demo machine |
| Slide claims a number | No benchmark behind it | Remove, or run `scripts/run_benchmark.py` and cite the denominator |

## E.6 Definition of done for the whole project

The project is submission-ready when: Gate C is declared, every P0 milestone is done, Gate S is declared, the demo has been rehearsed three times (normal, network off, Docker off), and every claim in the slides maps to a test case ID or a measured result in the benchmark report. Gates D and E are declared if their milestones were completed; if not, the submission must say exactly which gate was reached.

**FAULTLINE - WITNESSES, NOT WARNINGS.**
