# FAULTLINE PLAYBOOK
## Phase-by-phase build, validation, logbook and checklist

**Project:** Faultline, Cross-Repo Dependency Drift Detector (HACKTOPIA 2026, PS07)
**Based on:** *FAULTLINE Phased MVP-First Scalable Implementation Plan v3.1 FINAL*, with the canonical `FAULTLINE_Master_Document` as the specification for algorithms, schemas, verdict rules and scenarios.
**Companion files:** `LOGBOOK.md` (append-only build log), `CHECKLIST.md` (generated status), `tools/track.py` (the tracker), `playbook/phases/*.yaml` (source of this playbook).

> This playbook is generated from the YAML files by `python tools/track.py render`. Edit the YAML, not this file.

---

# PART A - ASSESSMENT OF PLAN v3.1

*Reviewed as an engineer, a hackathon judge and a jury member. Scores are my judgement, not measurements.*

## A.1 Verdict

**Plan v3.1 is a strong engineering plan. It is not yet a hackathon-winning plan, and it is not perfect.** It is good enough to build from, and this playbook applies ten amendments that close the gaps. After the amendments I consider it a sound plan to win with, provided the team respects the priority cut lines in Part B.

| Dimension | v3.1 as written | With this playbook | Why |
|---|---|---|---|
| Engineering rigour | 9 / 10 | 9 / 10 | Gates A to E, a single canonical model, native resolvers only, fail-closed sandbox, versioned evidence, deterministic verdict. |
| Claim discipline | 9.5 / 10 | 9.5 / 10 | Every gate lists what it must not claim. Fixture, live and replay stay distinct. |
| Internal consistency | 7 / 10 | 8.5 / 10 | One real contradiction and several duplications (A.3). |
| Completeness against the master | 7.5 / 10 | 9 / 10 | Missing: sandbox build, real-world case, ablation, demo modes, submission. |
| Hackathon fit | 6 / 10 | 8.5 / 10 | No priority cut line, no demo spine, heavy Gate D. |
| Demo readiness | 4 / 10 | 8.5 / 10 | The plan explicitly excludes pitching and has no demo milestone. |

## A.2 What the plan gets right (keep all of it)

1. **Thin real product early.** Gate B (fixture proof) and Gate C (first live finding) before the full MVP is the right order for a risky project.
2. **Honest gates.** Each gate states what it must not claim. This is the quality judges reward most in a verification tool.
3. **The witness predicate is protected.** Three fresh reference passes, three fresh consumer failures, same normalized signature, and cached results never count as repeats.
4. **Failure taxonomy and reference-world failure policy.** Infrastructure, harness and baseline failures become INCONCLUSIVE, never a break and never clean.
5. **Traceability matrix.** Every canonical MUST maps to an automated test and a retained artifact.
6. **Scale path without premature scale.** Replaceable boundaries, SQLite WAL first, explicit migration trigger, no Kubernetes, Kafka or graph database.
7. **No LLM in the decision path**, enforced as an invariant.

## A.3 Defects found in v3.1

| # | Severity | Finding | Where | Resolution in this playbook |
|---|---|---|---|---|
| D-1 | **High** | Contradiction. Phase 5 says Gate D needs Phases 0 to 4 "and 9 to 10", but section 5 says Phases 9 and 10 are expansion and not Gate D prerequisites. | Phase 5 goal vs section 5 | Gate D requires only the npm and Maven **inventory** milestones (M3.6, M3.7). Runtime expansion (M9.1, M10.1) is NICE. |
| D-2 | **High** | No milestone builds the sandbox. Phase 1.3 already routes code through `sandboxd`, Gate C demands the minimum isolation controls, but the isolation tests are scheduled only at Gate E. | Phases 1, 4, 11 | New **M1.2** builds `sandboxd` and the hardened profile and tests escape attempts at Gate B. |
| D-3 | Medium | Gate D scope hides in sub-sections 3.6, 3.7 and in the matrix. Phase 4.6 holds Gate D dashboard requirements under the Gate C phase. | Phases 3, 4 | Split into separate milestones with explicit gates (M3.6, M3.7, M4.6, M4.7). |
| D-4 | Medium | Duplicated rows: the dashboard conformance row appears twice, PC-1 appears twice. Duplicates drift apart. | Matrix section 9 | Merged into M4.6 and M5.6. |
| D-5 | Low | Formatting: "3.5 World inspector" has no body of its own and 3.6/3.7 appear as paragraphs inside it. Phase numbers and section numbers collide (section "5." vs "Phase 5"). | Phase 3 | Each is its own milestone. |
| D-6 | Medium | Phase 5 is overloaded: attribution, bundles, durable workers, observability, false-positive controls, and dashboard completion in one phase. | Phase 5 | Split into M5.1 to M5.7, each with its own tests. |

## A.4 Gaps that matter for winning

| ID | Gap in v3.1 | Why it matters | Amendment (milestone) |
|---|---|---|---|
| A-1 | No step verifies the third-party facts the fixtures rely on. | The master marks every pydantic, Werkzeug and urllib3 behaviour as unverified. A wrong example collapses the demo. | **M1.0** verify by hand first. |
| A-2 | Sandbox not scheduled (D-2). | Nothing executes honestly without it. | **M1.2** |
| A-3 | Contract replay is post-MVP (Phase 7). | It is the most dramatic, hardest-to-copy demo and the master's data-crossing hero. | **M7.1** flagged as the first expansion (priority P1). |
| A-4 | "Fix" (remediation) is Phase 8, after Gates D and E. | The pitch story is Detect, Reproduce, Attribute, **Fix**. | **M8.0** adds a minimal verified pin-and-re-run. |
| A-5 | No ablation. | Faultline's novelty claim is "consumer-derived worlds find breaks that author-chosen matrices miss". Without measuring that, a judge can dismiss it as matrix testing. | **M11.2** |
| A-6 | Over-engineering for a hackathon: cache-stampede tests, queue backpressure, retention policy, concurrency envelope. | Time spent here is time not spent on the demo. | **M11.4** trimmed; **M5.3, M5.4** reduced scope. |
| A-7 | The real-world case was dropped. | It is the answer to "is the demo staged?". | **M12.1** |
| A-8 | LIVE, FIXTURE and REPLAY demo modes and fallbacks were dropped. | A demo that depends on live GitHub and PyPI will eventually fail on stage. | **M12.2** |
| A-9 | No demo script, rehearsal or judge Q&A. | The demo is how the work is judged. | **M12.3** |
| A-10 | No submission pack. | Slides and README must match what the product actually does. | **M12.4** |

## A.5 Biggest remaining risk (honest)

**Scope.** Gate D alone asks for: Python resolution, npm and Maven inventory, relationships, cells, three oracles, witnesses, two-sided ddmin, portable bundles with replay, an eight-view dashboard in all states, durable workers and a full conformance report. For a small student team this is a lot. The plan itself does not say what to cut. **Part B gives the cut lines.** The rule is: finish every P0 first, freeze, then spend any remaining time on P1.

---

# PART B - HOW TO USE THIS PLAYBOOK

## B.1 The loop (every milestone)

```text
1. python tools/track.py next                    # shows the next milestone and its test cases
2. python tools/track.py start Mx.y              # logs the start
3. Build the tasks listed for the milestone.
4. Run every validation test case. Save the output under evidence/Mx.y/.
5. python tools/track.py tc TC-x.y.z pass --evidence evidence/Mx.y/<file>   (or fail --note "...")
6. python tools/track.py done Mx.y               # refuses unless every test case passed
7. git commit (message starts with the milestone id)
8. At the end of a gate: python tools/track.py gate C
```

Every one of those commands appends to `LOGBOOK.md` and refreshes `CHECKLIST.md`.

## B.2 Rules

1. **A milestone is done only when every one of its test cases has a recorded PASS with evidence.** `done` refuses otherwise. A PASS without evidence is refused.
2. **A waiver is allowed only with a written reason** (`done --waive "reason"`). It is permanently visible in the log and the checklist, and a gate with waivers needs `--accept-waivers`.
3. **A failing test case is recorded as `fail`**, not skipped. Fix and re-record; both entries stay in the log.
4. **The master document is canonical** for algorithms, schemas and verdict rules. If this playbook and the master differ, stop and resolve it with an ADR in `docs/adr/`.
5. **Never weaken a check to make a test pass.** Change the code, or change the expected value only with a written reason in the log.
6. **Claim discipline.** No slide, README or UI text may say proof, guarantee, "compatible", "AI detected", or imply live analysis when the mode is FIXTURE or REPLAY.
7. **Execution only through the sandbox.** If the boundary cannot be verified, the execution capability is disabled, not bypassed.
8. **The LLM is never in the decision path.** The product must work with the LLM off.
9. **Expansion cannot substitute for a MUST.** Do not start a P1 item while a P0 is open, unless the P0 is blocked.
10. **Freeze.** When all P0 items are done, stop adding features. Only bug fixes, rehearsals and the submission pack remain.

## B.3 Priority cut lines

{{PRIORITY_TABLE}}

Reading the table:
- **P0** is the demo spine. If only P0 is finished you can show: a real producer and consumer, the consumer-derived world matrix, a re-runnable witness, attribution, a verified fix, the evidence bundle, the real-world case, and a rehearsed, honest demo.
- **P1** makes the project hard to copy (contract replay, static API and exposure) and hardens it (deployment security gate).
- **P2** is the first to cut when time is short: Maven inventory depth, type checking, full what-if search, concurrency envelope.
- Note that **Gate D also requires** M3.6 and M3.7 (npm and Maven inventory), M4.6 (targeted O-bind), M5.3 (durable worker) and M5.4 (logging and retention), which are P1 or P2 above. If you cut any of them you cannot declare Gate D, and the submission must say "Python MVP, Gate C reached" instead of "PS07-compliant MVP". Say exactly which gate you reached.

## B.4 Where evidence lives

```text
evidence/
  M1.4/                 one folder per milestone
    TC-1.4.1.txt        raw command output or screenshot for each test case
playbook/state.json     machine state (do not edit by hand)
LOGBOOK.md              append-only history
CHECKLIST.md            generated status
```

## B.5 What "test case kind" means

- **auto**: a command or test that exits non-zero on failure. Put the command in the evidence file with its output.
- **manual**: a human performs the steps and writes what they saw. Two people should do critical manual cases (for example the clean-machine replay).

---
