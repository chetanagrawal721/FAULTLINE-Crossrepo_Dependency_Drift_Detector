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

| Priority | Milestones (build order) |
|---|---|
| P0 - needed for a convincing demo | M0.1, M0.2, M0.3, M0.4, M0.5, M0.6, M1.0, M1.1, M1.2, M1.3, M1.4, M1.6, M1.7, M1.8, M2.1, M2.2, M2.3, M2.4, M3.1, M3.2, M3.3, M3.4, M4.1, M4.2, M4.3, M4.4, M4.5, M4.7, M4.G, M5.1, M5.2, M5.5, M5.6, M5.7, M8.0, M11.2, M12.1, M12.2, M12.3, M12.4 |
| P1 - strongly improves it | M1.5, M3.5, M3.6, M4.6, M5.3, M6.2, M6.3, M6.4, M7.1, M11.1, M11.3, M11.5 |
| P2 - can be cut | M3.7, M5.4, M6.1, M7.2, M7.3, M8.1, M8.2, M8.3, M9.1, M10.1, M11.4 |

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


---

# PART C - PHASE-BY-PHASE IMPLEMENTATION

Every milestone lists tasks, files, and the **test cases that must pass before it is marked done**. `[AMENDMENT]` marks a change I made to plan v3.1; everything else follows the plan.


## Phase 0: Bootstrap, contracts and runnable shell  (gate A)

### M0.1 Repository layout and pinned toolchain

**Gate:** A | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** One command boots everything; every tool version is pinned.

**Tasks**

- Create backend/faultline, frontend, docker, fixtures, tests, scripts, migrations, docs/adr, benchmarks.
- Pin Python 3.12 (exact patch), Node, uv, npm, Docker image digests, CI tool versions in one versions file.
- Provide make up / make test / make fixtures / make e2e. Each returns a non-zero exit code on failure.

**Expected files:** `Makefile`, `pyproject.toml`, `uv.lock`, `versions.toml`, `docker/compose.yml`, `.github/workflows/ci.yml`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-0.1.1 | Clean checkout boots | auto | git clone to an empty directory; run make up. | API, worker, sandbox stub and UI all start. GET /api/health returns 200. |
| TC-0.1.2 | Pins are real | auto | Run scripts/check_pins.py (fails on any floating tag such as :latest or unpinned dependency). | Exit 0. Every image reference contains @sha256. Python, uv and Node versions equal versions.toml. |
| TC-0.1.3 | Make targets fail loudly | auto | Introduce a deliberate failing test; run make test. | Non-zero exit code. Remove the failure and the exit code is 0. |

**Record progress:** `python tools/track.py start M0.1`, then `python tools/track.py tc TC-0.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M0.1`.

### M0.2 Canonical models, schema and migrations

**Gate:** A | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** One canonical shape per concept: ResolvedWorld, Cell, OracleJob, OracleRunResult, Witness, Finding.

**Tasks**

- Implement the master-defined core models in core/models.py. No alternate shapes.
- Create explicit SQL migrations for the master schema (project, repository, snapshot, manifest, world, cell, oracle run, witness, finding).
- Make enums explicit and reject invalid status transitions.
- Version the API schema and the persisted evidence schema.

**Expected files:** `backend/faultline/core/models.py`, `backend/faultline/core/enums.py`, `backend/faultline/storage/migrations/*.sql`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-0.2.1 | Migration is clean and idempotent | auto | Apply migrations to an empty DB; apply again. | First run creates all tables. Second run is a no-op with no error. |
| TC-0.2.2 | Failed migration leaves no half schema | auto | Inject a failing statement in a test migration; run it. | Whole migration rolled back. Schema equals the pre-migration state. |
| TC-0.2.3 | Invalid transition and unknown enum rejected | auto | Try job status DONE -> QUEUED; try to store an unknown verdict string. | Both rejected with a typed error. Nothing persisted. |
| TC-0.2.4 | Foreign-key chain exists | auto | Insert a full chain project -> repository -> snapshot -> manifest -> world -> cell -> oracle run -> witness -> finding. | All inserts succeed. Deleting a snapshot referenced by a finding is refused. |

**Record progress:** `python tools/track.py start M0.2`, then `python tools/track.py tc TC-0.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M0.2`.

### M0.3 Canonical hashing

**Gate:** A | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** A single function computes every identity hash.

**Tasks**

- Implement canonical JSON serialization and hashing in core/hashing.py only.
- World identity excludes absolute paths and incidental timestamps; includes runtime, platform and visibility dimensions.
- Add a lint rule that fails if any other module computes a hash of a model.

**Expected files:** `backend/faultline/core/hashing.py`, `tests/unit/test_hashing.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-0.3.1 | Order independence | auto | Hash the same world with its entries and keys shuffled 100 times. | Exactly one distinct hash. |
| TC-0.3.2 | Semantic sensitivity | auto | Change one of: package version, runtime minor, platform, artifact hash. | Hash changes in every case. Changing only a timestamp or a local path does not change it. |
| TC-0.3.3 | NaN and float handling | auto | Serialize a payload containing NaN, -0.0 and a very large float. | NaN is rejected with an explicit error. -0.0 and large floats serialize deterministically. |

**Record progress:** `python tools/track.py start M0.3`, then `python tools/track.py tc TC-0.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M0.3`.

### M0.4 Durable job contract

**Gate:** A | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Analysis runs asynchronously in a separate worker with a safe job lifecycle.

**Tasks**

- Persist job status, idempotency key, attempts, timestamps, lease owner and expiry, cancellation flag.
- Atomic claim; stale leases reclaimable; transient and permanent failures distinguished.
- API returns a job id immediately and exposes progress without holding the request open.
- Hackathon scope: lease plus retry plus cancellation. Heartbeat tuning and backpressure are deferred to Phase 11.

**Expected files:** `backend/faultline/storage/jobs.py`, `backend/faultline/workers/run.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-0.4.1 | Atomic claim under contention | auto | Start two workers; enqueue 50 jobs; run to completion. | Each job executed exactly once. No duplicate run records. |
| TC-0.4.2 | Stale lease reclaimed | auto | Kill a worker mid-job; wait past lease expiry. | Another worker reclaims and completes the job. The attempt count is 2. |
| TC-0.4.3 | Idempotent submission | auto | POST the same analysis twice with the same idempotency key. | One job. Both calls return the same job id. |
| TC-0.4.4 | Cancellation | auto | Cancel a running job. | Status becomes CANCELLED. The worker stops at the next checkpoint. |

**Record progress:** `python tools/track.py start M0.4`, then `python tools/track.py tc TC-0.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M0.4`.

### M0.5 Health, capabilities and the capability banner

**Gate:** A | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** The product states what it can and cannot do before any analysis exists.

**Tasks**

- Implement GET /api/health and GET /api/capabilities (mode, ecosystems, oracles, sandbox state, disabled reasons).
- Render the mode badge and capability banner in the frontend.
- Sandbox stub reports 'not verified' and must never be shown as isolation.

**Expected files:** `backend/faultline/api/routers/system.py`, `frontend/src/components/CapabilityBanner.tsx`, `frontend/src/components/ModeBadge.tsx`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-0.5.1 | Capability truthfulness | auto | Call /api/capabilities with the sandbox stub. | Execution oracles listed as unavailable with reason 'sandbox not verified'. |
| TC-0.5.2 | Banner renders from API | manual | Open the UI before any analysis exists. | Mode badge and per-ecosystem and per-oracle states visible. No finding is displayed. |

**Record progress:** `python tools/track.py start M0.5`, then `python tools/track.py tc TC-0.5.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M0.5`.

### M0.6 CI gate

**Gate:** A | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Every push proves the skeleton still works.

**Tasks**

- CI runs: migration check, API schema check, lint and unit tests, frontend typecheck and build, service boot.
- Generate TypeScript types from OpenAPI and fail CI on drift.

**Expected files:** `.github/workflows/ci.yml`, `scripts/check_openapi_types.sh`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-0.6.1 | CI is green on main | auto | Push to main. | All CI jobs pass. |
| TC-0.6.2 | Schema drift is caught | auto | Change an API field without regenerating types; push. | CI fails on the type-drift check. |

**Record progress:** `python tools/track.py start M0.6`, then `python tools/track.py tc TC-0.6.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M0.6`.


## Phase 1: Fixture-backed end-to-end differential proof  (gate B)

### M1.0 Verify every fixture claim by hand [AMENDMENT]

**Gate:** B | **Tier:** AMEND | **Hackathon priority:** P0

> **Amendment.** A-1. The plan says 'select a verified scenario' but has no step that does the verifying. All third-party behaviours in the master (pydantic v1/v2, Werkzeug 3 / Flask 2.2, urllib3 2, PyJWT) were marked VERIFY and are not yet verified.

**Goal.** Every behaviour a fixture depends on has been reproduced in a plain virtualenv, outside Faultline, with the log kept.

**Tasks**

- For each scenario you intend to use (minimum B or D, C or H, and J), reproduce the claimed behaviour with pinned packages in a plain venv.
- Record exact versions, command, and output in fixtures/verification/<scenario>.md.
- If a claim is false, replace the example. Never change the expected verdict to fit.

**Expected files:** `fixtures/verification/*.md`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.0.1 | Break reproduces outside Faultline | manual | In a fresh venv, install the pinned consumer-world packages and run the failing import or test. | The failure matches the expected normalized signature in the scenario YAML. |
| TC-1.0.2 | Reference world passes outside Faultline | manual | In a second fresh venv with the reference pins, run the identical command. | Passes 3 times out of 3. |
| TC-1.0.3 | Verification record is committed | auto | scripts/check_fixture_verification.py | Every scenario referenced by a test has verified: true, a date, and package versions. |

**Record progress:** `python tools/track.py start M1.0`, then `python tools/track.py tc TC-1.0.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.0`.

### M1.1 Fixture repositories, scenario YAML and negative control

**Gate:** B | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Expected outcomes are written before any detection code exists.

**Tasks**

- Create the demo repositories (shared artifact, at least two consumers, one unrelated project) with tags per scenario.
- Write fixtures/scenarios/<ID>.yaml with expected relationships, cells, verdicts, oracle and signature.
- Include at least one no-drift control (Scenario A) and one harmless-drift control (Scenario H).
- Do not manufacture a failure by breaking the consumer fixture unless that is the exact scenario.

**Expected files:** `fixtures/scenarios/*.yaml`, `fixtures/repos/**`, `scripts/push_fixtures.sh`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.1.1 | Scenario files validate | auto | scripts/validate_scenarios.py | Every YAML matches the scenario schema and references pinned SHAs and lockfiles. |
| TC-1.1.2 | Negative control exists and is labelled | auto | Inspect scenarios A and H. | Both declare an expected non-break verdict and a reason. |

**Record progress:** `python tools/track.py start M1.1`, then `python tools/track.py tc TC-1.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.1`.

### M1.2 Sandbox v0: sandboxd, execution image and hardened profile [AMENDMENT]

**Gate:** B | **Tier:** AMEND | **Hackathon priority:** P0

> **Amendment.** A-2. The plan routes Phase 1 code through sandboxd but never schedules building it or testing its isolation until Gate E. Without this milestone Phase 1.3 cannot be done honestly, and Gate C requires these controls.

**Goal.** No repository or package code runs outside SandboxClient to sandboxd to an allowlisted image.

**Tasks**

- Build sandboxd as the only holder of the Docker socket; accept structured jobs over a Unix socket.
- Build the Python execution image pinned by digest; harness scripts baked in; no secrets.
- Enforce: no network, non-root, read-only root, tmpfs only for /tmp and /work, cap-drop ALL, no-new-privileges, CPU/memory/PID/disk/time/output limits, container cleanup in a finally block.
- Write adversarial tests (they are the deliverable, not an afterthought).

**Expected files:** `backend/faultline/sandbox/sandboxd.py`, `backend/faultline/sandbox/client.py`, `backend/faultline/sandbox/profiles.py`, `docker/exec-python/Dockerfile`, `tests/security/test_sandbox.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.2.1 | Network is unreachable | auto | Run a job that opens a socket to 1.1.1.1:443 and to the cloud metadata address. | Both fail. The job is classified as ARTIFACT_FAILURE or NEEDS_EXTERNAL, not as a sandbox error. |
| TC-1.2.2 | Filesystem and identity | auto | Run jobs that write to /, read /var/run/docker.sock, print id, and read host environment. | Write fails; socket absent; uid is not 0; no host secrets in the environment. |
| TC-1.2.3 | Resource bombs are contained | auto | Run a fork bomb, a 4 GB allocation, a disk-fill loop, and an infinite print loop. | Each is killed or capped. The host stays responsive. Output is truncated at the cap. The class is RESOURCE_LIMIT or TIMEOUT. |
| TC-1.2.4 | No orphans | auto | Kill the worker and sandboxd mid-job; restart; list containers. | No faultline containers remain after the cleanup sweep. |
| TC-1.2.5 | Fail closed | auto | Stop the Docker daemon; submit an execution job. | Capability reports execution unavailable with a reason. No job runs outside a container. |

**Record progress:** `python tools/track.py start M1.2`, then `python tools/track.py tc TC-1.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.2`.

### M1.3 World descriptors and the offline world builder

**Gate:** B | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Reference and consumer worlds are built once, offline, from verified artifacts.

**Tasks**

- Define explicit reference and consumer world descriptors from committed fixture lockfiles.
- Fetch wheels with hash verification into a wheelhouse (fetch zone). Install offline into /opt/world per world hash (PC-10).
- Reusing a world must not create an oracle run.

**Expected files:** `backend/faultline/worlds/builder.py`, `backend/faultline/resolvers/python.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.3.1 | Offline build from verified artifacts | auto | Build a world with the network disabled after the wheelhouse is filled. | Build succeeds. The installed package set equals the descriptor exactly. |
| TC-1.3.2 | Hash mismatch blocks use | auto | Corrupt one wheel in the wheelhouse; build. | Build fails with a hash-mismatch error. The world is not marked BUILT. |
| TC-1.3.3 | Reuse is not an execution | auto | Request the same world twice, then count oracle run records. | World status BUILT then REUSED. Oracle run count unchanged. |

**Record progress:** `python tools/track.py start M1.3`, then `python tools/track.py tc TC-1.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.3`.

### M1.4 O-import and failure classification

**Gate:** B | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** The cheapest oracle works and failures are classified before they become evidence.

**Tasks**

- Implement the O-import harness: import the artifact top-level package and each consumer-imported module.
- Classify each run: ARTIFACT_FAILURE, HARNESS_FAILURE, RESOLUTION_FAILURE, BUILD_FAILURE, SANDBOX_FAILURE, RESOURCE_LIMIT, TIMEOUT, NEEDS_EXTERNAL, UNSUPPORTED.

**Expected files:** `backend/faultline/oracles/o_import.py`, `backend/faultline/oracles/harness/import_modules.py`, `backend/faultline/oracles/classify.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.4.1 | Reference passes, consumer fails | auto | Run O-import for the chosen break scenario in both worlds. | Reference PASS. Consumer FAIL with the expected exception type and module. |
| TC-1.4.2 | Harness error is not a break | auto | Run a harness with an injected bug. | Classified HARNESS_FAILURE. No witness candidate is created. |
| TC-1.4.3 | Missing optional module is not a break | auto | Artifact module imports an extra the consumer lacks and does not use. | NOT_APPLICABLE, not ARTIFACT_FAILURE. |

**Record progress:** `python tools/track.py start M1.4`, then `python tools/track.py tc TC-1.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.4`.

### M1.5 O-tests with the test-only overlay

**Gate:** B | **Tier:** MUST | **Hackathon priority:** P1

**Goal.** The artifact's own tests run in each world using the authors' real inputs.

**Tasks**

- Run pytest inside the sandbox with per-test JUnit output parsed into per-test outcomes.
- Overlay test-only packages (PC-5) without replacing runtime dependencies; record the overlay in world identity.
- Disable plugin autoload; add needed plugins explicitly.

**Expected files:** `backend/faultline/oracles/o_tests.py`, `backend/faultline/oracles/harness/run_pytest.py`, `backend/faultline/worlds/overlay.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.5.1 | Per-test differential | auto | Run the artifact tests in both worlds for scenario C or H. | Per-test records exist. Differences are listed per test id. |
| TC-1.5.2 | Overlay does not change runtime versions | auto | Compare runtime package versions before and after overlay. | Identical. The overlay set is recorded and the world is flagged if it was forced. |
| TC-1.5.3 | Collection error from test-only package | auto | Remove pytest from the overlay. | HARNESS_FAILURE, not a break. |

**Record progress:** `python tools/track.py start M1.5`, then `python tools/track.py tc TC-1.5.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.5`.

### M1.6 Witness verifier: 3 reference passes and 3 consumer failures

**Gate:** B | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** A witness exists only if six genuinely fresh runs agree.

**Tasks**

- Run three independent reference executions and three consumer executions.
- Require reference 3/3 pass, consumer 3/3 fail, identical normalized failure signature.
- Record run provenance FRESH_EXECUTION or REUSED_RESULT. Only fresh runs count.
- Keep raw output separate from the normalized signature.

**Expected files:** `backend/faultline/witnesses/verify.py`, `backend/faultline/witnesses/signature.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.6.1 | Witness predicate | auto | Run the verifier on the chosen break scenario. | Six run records with unique run ids and FRESH_EXECUTION. Signatures identical. Witness created. |
| TC-1.6.2 | Flaky and both-fail are rejected | auto | Use a flaky test (random failure) and a scenario where the reference also fails. | No witness. Outcomes are INCONCLUSIVE(flaky) and discarded(reference fails). |
| TC-1.6.3 | Cache cannot fake repeats | auto | Run the verifier twice with the cache warm. | Cached results are shown as REUSED_RESULT and are not counted as fresh. A forced re-run creates six new run ids. |
| TC-1.6.4 | Negative control stays clean | auto | Run scenarios A and H. | No witness in either. |

**Record progress:** `python tools/track.py start M1.6`, then `python tools/track.py tc TC-1.6.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.6`.

### M1.7 Evidence bundle v1 and export

**Gate:** B | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** A machine-readable, versioned, hash-checked bundle for the witness.

**Tasks**

- Define the bundle schema with an explicit version and a manifest of every file with its SHA-256.
- Include world descriptors, runtime and platform, image digest, oracle plan, six run records, signature.
- Exclude secrets and unbounded logs.

**Expected files:** `backend/faultline/witnesses/bundle.py`, `docs/schemas/evidence-bundle-v1.json`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.7.1 | Bundle validates against schema | auto | Export the bundle; validate against the schema. | Valid. Version field present. |
| TC-1.7.2 | Tamper is detected | auto | Modify one byte in a bundle file; run the verifier. | Rejected with the name of the modified file. |
| TC-1.7.3 | No secrets | auto | Set a canary secret in the control-plane environment; export; grep the bundle. | Canary not present. |

**Record progress:** `python tools/track.py start M1.7`, then `python tools/track.py tc TC-1.7.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.7`.

### M1.8 Thin UI for the fixture finding

**Gate:** B | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** A judge can inspect one complete finding, labelled FIXTURE.

**Tasks**

- Show mode, both world hashes, oracle results, six runs, normalized failure, raw traceback link, bundle download.
- Persistent FIXTURE badge.

**Expected files:** `frontend/src/pages/WitnessDetail.tsx`, `frontend/src/components/WitnessCard.tsx`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-1.8.1 | End to end from scenario id | auto | make e2e SCENARIO=<id> (starts from the scenario id, ends at the displayed finding). | Expected verdict displayed. Badge reads FIXTURE. |
| TC-1.8.2 | No false live claim | manual | Read every label on the page. | Nothing says live or real-time analysis. |

**Record progress:** `python tools/track.py start M1.8`, then `python tools/track.py tc TC-1.8.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M1.8`.


## Phase 2: Pinned public repository ingestion  (gate C)

### M2.1 URL and ref validation, SHA pinning

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Only well-formed GitHub inputs are accepted and every analysis uses an immutable SHA.

**Tasks**

- Accept only https://github.com/<owner>/<repo> forms with an optional ref. Reject local paths, credentials in URLs, other schemes, malformed refs.
- Resolve a branch, tag or default ref to a commit SHA once. Store requested ref and pinned SHA separately.
- All later steps fetch the SHA, never the moving ref.

**Expected files:** `backend/faultline/ingestion/urls.py`, `backend/faultline/ingestion/github.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-2.1.1 | Validation table | auto | Feed 30 valid and invalid inputs (file://, ssh, userinfo, ports, .., unicode tricks, other hosts). | Exactly the valid GitHub URLs are accepted; every other input returns INVALID_REPOSITORY. |
| TC-2.1.2 | Moving tag creates a new snapshot | auto | Pin a tag; move the tag in a local test remote; resubmit. | A second snapshot with a new SHA. The first snapshot and its evidence are untouched. |
| TC-2.1.3 | Retry keeps the SHA | auto | Simulate a rate limit mid-ingest; retry. | The retry fetches the same pinned SHA. |

**Record progress:** `python tools/track.py start M2.1`, then `python tools/track.py tc TC-2.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M2.1`.

### M2.2 Restricted fetch

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Fetching a hostile repository cannot run code or escape its directory.

**Tasks**

- Fetch inside the fetch zone: controlled HOME, no system/global Git config, hooks disabled, symlinks disabled, LFS smudge disabled, submodules not recursed.
- Bound size, time, file count and path length.
- No build step runs during ingestion.

**Expected files:** `backend/faultline/ingestion/clone.py`, `docker/fetch/Dockerfile`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-2.2.1 | Hostile repository | auto | Fetch a local repo containing a symlink to /etc, a ../ path, an LFS pointer, a submodule, a post-checkout hook and a .gitconfig include. | No hook runs; symlink stored as a plain file; submodule not fetched; no file outside the snapshot directory is written. |
| TC-2.2.2 | Limits | auto | Fetch a repo over the size, file-count and path-length limits. | INGEST_LIMIT with a partial snapshot and a warning; no crash. |

**Record progress:** `python tools/track.py start M2.2`, then `python tools/track.py tc TC-2.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M2.2`.

### M2.3 Immutable snapshot and inventory

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** A content-hashed, read-only record of exactly what was analysed.

**Tasks**

- Persist snapshot metadata and a file inventory with content hashes.
- Represent LFS pointers, submodules, unavailable files and unsupported paths explicitly.
- Cache by repository and SHA. A new SHA is a new snapshot.

**Expected files:** `backend/faultline/ingestion/classify.py`, `backend/faultline/storage/snapshots.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-2.3.1 | Inventory is complete and hashed | auto | Ingest a fixture repo; compare the inventory to git ls-tree. | Same file set; every file has a SHA-256; special entries carry an explicit type. |
| TC-2.3.2 | Snapshot is read-only | auto | Attempt to modify a stored snapshot file through the API and the filesystem as the worker user. | Refused. Hash verification of the snapshot still passes. |

**Record progress:** `python tools/track.py start M2.3`, then `python tools/track.py tc TC-2.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M2.3`.

### M2.4 Ingestion API and UI

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** A user can submit a real public repository and see exactly what was pinned.

**Tasks**

- Add repository submission and snapshot status to the UI; progress is persisted.
- Show the pinned SHA and file inventory before resolving dependencies.

**Expected files:** `frontend/src/pages/Projects.tsx`, `backend/faultline/api/routers/projects.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-2.4.1 | Real public repository | manual | Submit a small real public GitHub repository. | Pinned SHA and inventory appear. The fixture pipeline still passes make e2e. |
| TC-2.4.2 | Failure states | manual | Submit a deleted repo, a private repo, and trigger a rate limit. | Distinct, readable states: not found, not accessible, retryable. |

**Record progress:** `python tools/track.py start M2.4`, then `python tools/track.py tc TC-2.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M2.4`.


## Phase 3: Manifest parsing and native resolution  (gate C)

### M3.1 Python project discovery

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Distinguish repository, project, distribution name, import package and source root.

**Tasks**

- Discover one or more Python projects per repository (pyproject.toml, uv.lock, poetry.lock, requirements files).
- Never import project code or run setup.py to learn metadata.

**Expected files:** `backend/faultline/parsers/python/discover.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-3.1.1 | Multi-project repository | auto | Discover projects in a monorepo fixture with three Python projects. | Three projects with correct names, source roots and import packages. |
| TC-3.1.2 | No code execution | auto | Place a setup.py that writes a canary file; ingest and discover. | Canary file never created. |

**Record progress:** `python tools/track.py start M3.1`, then `python tools/track.py tc TC-3.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M3.1`.

### M3.2 Python parsers with diagnostics

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Every dependency form is parsed or explicitly reported as unsupported.

**Tasks**

- Parse direct dependencies, extras, markers, Python constraints, VCS/URL/local deps and -r/-c includes inside the snapshot root.
- Normalise names per PEP 503, keep display name.
- Unknown syntax, path escape, malformed lockfile, unsupported build dependency are explicit statuses.

**Expected files:** `backend/faultline/parsers/python/requirements.py`, `backend/faultline/parsers/python/pyproject.py`, `backend/faultline/parsers/python/uv_lock.py`, `backend/faultline/parsers/python/poetry_lock.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-3.2.1 | Golden files | auto | Parse the golden set (markers, extras, VCS URL, Poetry caret and tilde, nested -r). | Output equals the committed golden JSON. |
| TC-3.2.2 | Hostile inputs | auto | Parse an -r include of ../../outside, a 50 MB requirements file, a malformed lockfile. | Path escape refused; size limit hit with TOO_LARGE; malformed -> MANIFEST_PARSE_FAILED. No crash. |
| TC-3.2.3 | Name normalisation | auto | Parse Foo_Bar, foo.bar and FOO-BAR. | All three share one canonical name; display names preserved. |

**Record progress:** `python tools/track.py start M3.2`, then `python tools/track.py tc TC-3.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M3.2`.

### M3.3 Native resolution with provenance

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Worlds come from lockfiles or the pinned uv, never a home-made solver.

**Tasks**

- Prefer a committed lockfile; otherwise resolve with pinned uv at a recorded cutoff time and index policy.
- Record interpreter, OS, architecture, marker environment, resolver version, flags and artifact hashes.
- Use wheels only. A package needing an sdist build is classified needs-build and not executed.
- Note: --no-build is not a complete isolation guarantee. Resolution runs inside the fetch zone regardless.

**Expected files:** `backend/faultline/resolvers/python.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-3.3.1 | Reproducible world | auto | Resolve the same project twice with the same cutoff. | Identical world hash. |
| TC-3.3.2 | Needs-build is not executed | auto | Resolve a project depending on an sdist-only package whose build writes a canary. | RESOLUTION_FAILED(needs_build); canary absent. |
| TC-3.3.3 | Custom index | auto | Resolve a project declaring a private index. | Private packages marked PRIVATE; never fetched from the public index. |
| TC-3.3.4 | Artifact hash mismatch blocks use | auto | Alter a downloaded wheel. | World build refused. |

**Record progress:** `python tools/track.py start M3.3`, then `python tools/track.py tc TC-3.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M3.3`.

### M3.4 Canonical world and deduplication

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Identical worlds share one identity; importer-specific differences are preserved.

**Tasks**

- World identity includes package identity, version, source, artifact hash, relevant edges, runtime, platform, resolver context and visibility data.
- Cache key includes manifest or lockfile hash, resolver version, platform, flags, index identity and cutoff.

**Expected files:** `backend/faultline/worlds/canonical.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-3.4.1 | Equivalent worlds dedupe | auto | Resolve two projects that produce the same package set. | One world row, two project_world links. |
| TC-3.4.2 | Cache invalidates on any input | auto | Change the cutoff, then the platform, then the resolver version. | A new world is resolved each time. |

**Record progress:** `python tools/track.py start M3.4`, then `python tools/track.py tc TC-3.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M3.4`.

### M3.5 World inspector

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P1

**Goal.** Declared ranges, resolved versions and importer-visible versions are shown separately.

**Tasks**

- Expose normalised dependencies, resolution warnings and reproducibility metadata through the API and UI.

**Expected files:** `backend/faultline/api/routers/worlds.py`, `frontend/src/pages/WorldInspector.tsx`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-3.5.1 | Three views of a version | manual | Open a package whose range, resolved version and visible version differ. | All three are displayed and labelled distinctly. |
| TC-3.5.2 | Failed resolution is not an empty world | manual | Open a project whose resolution failed. | Failure reason shown. No empty or clean world is rendered. |

**Record progress:** `python tools/track.py start M3.5`, then `python tools/track.py tc TC-3.5.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M3.5`.

### M3.6 npm manifests and lockfile worlds (inventory, MUST for Gate D)

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P1

**Goal.** npm projects appear with nested instances and importer-specific visibility. No npm runtime claim.

**Tasks**

- Parse supported package.json and package-lock.json versions; keep nested package instances, integrity and source identity.
- Compute per-importer visibility by simulating node_modules resolution. Do not flatten into a Python-like map.
- Emit dependency and relationship inventory signals. Never run lifecycle scripts.
- Unknown lockfile version is unsupported/inconclusive.

**Expected files:** `backend/faultline/parsers/npm/package_lock.py`, `backend/faultline/resolvers/npm.py`, `backend/faultline/resolvers/visibility.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-3.6.1 | Nested versions preserved | auto | Parse a lockfile where two packages need different versions of the same dependency. | Two instances kept; visible(importer) returns the correct one for each importer. |
| TC-3.6.2 | Workspace importer | auto | Parse an npm workspace fixture. | Each workspace has its own visibility; links to sibling workspaces recognised. |
| TC-3.6.3 | Unsupported lockfile version | auto | Parse an unknown lockfileVersion. | Unsupported with a reason; no partial clean result. |
| TC-3.6.4 | Capability honesty | manual | Check the capability banner for npm. | Inventory and world enabled; runtime witness shown unavailable. |

**Record progress:** `python tools/track.py start M3.6`, then `python tools/track.py tc TC-3.6.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M3.6`.

### M3.7 Maven POM inventory (MUST for Gate D)

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P2

**Goal.** Maven projects appear with coordinates and direct dependencies. No Maven resolution claim.

**Tasks**

- Parse coordinates, direct dependencies, same-POM properties and supported in-repository parents with a hardened XML parser.
- External parents, BOM imports and unsupported interpolation are explicit unsupported/inconclusive.
- Never run Maven.

**Expected files:** `backend/faultline/parsers/maven/pom.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-3.7.1 | Properties and in-repo parent | auto | Parse a multi-module fixture using ${properties} and an in-repo parent. | Coordinates and versions resolved correctly; module boundaries preserved. |
| TC-3.7.2 | External parent and BOM | auto | Parse a POM importing an external BOM. | Marked unsupported with the reason; versions left unresolved, not guessed. |
| TC-3.7.3 | Hostile XML | auto | Parse an XML bomb and an external-entity POM. | Rejected. No file read, no network call. |
| TC-3.7.4 | No Maven process | auto | Run inventory under a process monitor. | No mvn process started. |

**Record progress:** `python tools/track.py start M3.7`, then `python tools/track.py tc TC-3.7.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M3.7`.


## Phase 4: First live vertical slice  (gate C)

### M4.1 Relationship evidence

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Two repositories are linked only on traceable evidence.

**Tasks**

- Implement relationship levels L2/L3 (and suspected L3') with the evidence chain: published name to dependency, path or git dependency, workspace, identical schema.
- A same-name package or a version difference is candidate evidence only.
- Uncertain relationships go to the suspected tray with supporting and missing evidence. Declared relationships are labelled user-supplied.

**Expected files:** `backend/faultline/relationships/signals.py`, `backend/faultline/relationships/engine.py`, `backend/faultline/relationships/suspected.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-4.1.1 | Positive relationship | auto | Run discovery on the fixture where the consumer depends on the producer's published name. | One L2 relationship with evidence lines in both manifests. |
| TC-4.1.2 | Name-only match is not actionable | auto | Run discovery on the unrelated-project control and the look-alike model control. | No actionable relationship. Look-alike appears only in the suspected tray. |
| TC-4.1.3 | Evidence is traceable | auto | For each relationship fetch its evidence. | Every evidence row points to a snapshot file path and line. |

**Record progress:** `python tools/track.py start M4.1`, then `python tools/track.py tc TC-4.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M4.1`.

### M4.2 Reference world, projection, test overlay and consumer-import scan

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Compute the world the shared artifact actually experiences inside each consumer.

**Tasks**

- Select the reference world: artifact lockfile if present, otherwise manifest resolved as of the artifact commit time.
- Compute the artifact runtime closure; project each consumer's importer-visible versions onto it plus runtime and artifact dimensions.
- Overlay test-only dependencies (PC-5). Build offline (PC-10).
- Consumer-import scan (PC-4): record the artifact top-level package and the modules the consumer actually imports; an absent optional import is NOT_APPLICABLE.
- Reference-world failure policy: baseline unsupported, unreproducible or failing -> INCONCLUSIVE, never clean, never consumer-caused.

**Expected files:** `backend/faultline/worlds/reference.py`, `backend/faultline/worlds/projection.py`, `backend/faultline/worlds/overlay.py`, `backend/faultline/usage/consumer_imports.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-4.2.1 | Exact projection | auto | Project the break-scenario consumer onto the artifact closure. | The projected package set and runtime equal the scenario YAML exactly. |
| TC-4.2.2 | Consumer-import scan | auto | Scan a consumer that imports only two artifact modules. | Exactly those modules plus the top-level package are listed. A module needing an absent extra is NOT_APPLICABLE. |
| TC-4.2.3 | Reference failure policy | auto | Inject: missing lockfile, unavailable wheel, unsupported resolver semantics, baseline that fails its own tests. | Each yields INCONCLUSIVE with provenance and reason. None yields a consumer-caused BREAK. |

**Record progress:** `python tools/track.py start M4.2`, then `python tools/track.py tc TC-4.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M4.2`.

### M4.3 Cells, deltas and world coverage

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** One cell per unique effective projection, with exact discovered and analysed counts.

**Tasks**

- Build one cell per projection; keep consumer-to-cell links.
- Compute package and runtime deltas against the reference. Deltas are candidate causes, not findings.
- A cell that cannot be built stays in the discovered count as unsupported or failed, with a reason.
- Coverage is discovered vs analysed counts, never a compatibility score.

**Expected files:** `backend/faultline/worlds/cells.py`, `backend/faultline/verdicts/stats.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-4.3.1 | Dedup and links | auto | Two consumers with identical projections. | One cell, two consumer links. |
| TC-4.3.2 | NO_DRIFT cell | auto | A consumer matching the reference exactly. | Cell state NO_DRIFT; no oracle jobs queued. |
| TC-4.3.3 | Failed cell counted | auto | Make one consumer's world unresolvable. | Discovered = 3, analysed = 2, the third listed as failed with its reason. |

**Record progress:** `python tools/track.py start M4.3`, then `python tools/track.py tc TC-4.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M4.3`.

### M4.4 Live oracle execution

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** O-import and O-tests run on real pinned inputs with the same artifact revision in both worlds.

**Tasks**

- Plan oracles per cell (import first; stop downstream oracles if the top-level import already fails).
- Persist per-run output, traceback, classification and environment fingerprint.
- Infrastructure, harness, timeout, resource and resolution failures never become witnesses.

**Expected files:** `backend/faultline/oracles/planner.py`, `backend/faultline/workers/stages.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-4.4.1 | Live import oracle | auto | Run the live analysis on two real public repositories (or the fixture repos pushed to GitHub). | Per-world outcomes stored; fingerprints identical for the reference side across runs. |
| TC-4.4.2 | Short-circuit | auto | Break the top-level import in the consumer world. | Downstream oracles marked blocked_by_import with a reason; no duplicate failures reported. |
| TC-4.4.3 | Infrastructure failure is not evidence | auto | Kill the container during a consumer run. | Class SANDBOX_FAILURE; retried; never a witness. |

**Record progress:** `python tools/track.py start M4.4`, then `python tools/track.py tc TC-4.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M4.4`.

### M4.5 Witness and ordered verdict engine

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** A deterministic, ordered decision table over persisted evidence.

**Tasks**

- Enforce 3 fresh reference passes and 3 fresh consumer failures with the same normalized signature.
- Implement the master's ordered verdict table (HYGIENE, NO_DRIFT, NOT_APPLICABLE, BREAK WITNESSED, SILENT DIVERGENCE WITNESSED, NO DIVERGENCE OBSERVED, EXPOSED, POTENTIAL, NOT EXPOSED, INCONCLUSIVE).
- Unknown combinations become INCONCLUSIVE. Reason text is templated and scoped. Policy is versioned.
- NO DIVERGENCE OBSERVED states exactly what was and was not exercised.

**Expected files:** `backend/faultline/verdicts/engine.py`, `backend/faultline/verdicts/templates.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-4.5.1 | Decision table coverage | auto | Run table-driven tests with one case per row plus unknown combinations. | Every row returns its verdict; unknown -> INCONCLUSIVE; no branch untested (coverage report). |
| TC-4.5.2 | Determinism | auto | Recompute the verdict from persisted evidence 10 times, in a different process. | Identical verdict and reason text. |
| TC-4.5.3 | No LLM input | auto | Static check: verdict module imports. | No import of any LLM client; test fails if one appears. |
| TC-4.5.4 | Scoped wording | auto | Render NO DIVERGENCE OBSERVED. | Text lists exercised interactions and a 'not checked' list; never says compatible. |

**Record progress:** `python tools/track.py start M4.5`, then `python tools/track.py tc TC-4.5.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M4.5`.

### M4.6 Targeted call-site extractor and O-bind (PC-1, MUST for Gate D)

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P1

**Goal.** Real call sites into the divergent package are extracted and checked against the new signature.

**Tasks**

- AST pass over the artifact: imports, from-imports, aliases, module-level attribute chains; every Call resolving into a divergent package D with positional count, keyword names, star flags and literal arguments when all literal; file hash, line and column.
- O-bind: resolve the symbol in the world, bind the call shape against its signature. Execute only literal-only, side-effect-contained candidates.
- Dynamic, star-argument and unsupported forms stay DYNAMIC/UNRESOLVED.

**Expected files:** `backend/faultline/usage/callsites.py`, `backend/faultline/oracles/o_bind.py`, `backend/faultline/oracles/harness/bind_sites.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-4.6.1 | Extraction fixture | auto | Run on a fixture containing import, from-import, alias, attribute chain, positional, keyword, star and literal calls. | Records match the golden file including line and column. |
| TC-4.6.2 | Bind failure witnessed | auto | Run O-bind for the signature-change scenario (C). | Reference binds; consumer world fails to bind; witness created under the 3+3 rule. |
| TC-4.6.3 | Dynamic stays dynamic | auto | Include getattr(lib, name) and importlib.import_module(var). | Recorded as DYNAMIC; never treated as absent. |

**Record progress:** `python tools/track.py start M4.6`, then `python tools/track.py tc TC-4.6.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M4.6`.

### M4.7 MVP UI against persisted API records

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Submit two public repositories and see relationship, matrix, witness, verdict and export.

**Tasks**

- Show pinned SHAs, relationship evidence, world matrix, exact delta, witness, verdict and export.
- Mode badge and capability states; support refresh, failed jobs, retryable jobs, empty and unsupported states.
- No frontend mock data may satisfy a MUST.

**Expected files:** `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/Matrix.tsx`, `frontend/src/pages/Findings.tsx`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-4.7.1 | Two-URL end to end | auto | Browser E2E: submit two repository URLs and wait for completion. | Funnel, matrix, witness and verdict are displayed from API records. |
| TC-4.7.2 | Mock-free proof | auto | Run the E2E with the API returning an unseen value (random world hash). | UI displays that exact value, proving it renders persisted data. |

**Record progress:** `python tools/track.py start M4.7`, then `python tools/track.py tc TC-4.7.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M4.7`.

### M4.G Gate C acceptance: first live finding

**Gate:** C | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** One real public producer/consumer pair yields a repeatable, correctly scoped LIVE finding.

**Tasks**

- Run the clean-checkout end-to-end from two public repository URLs.
- Confirm a negative control stays clean and every claim points to pinned SHAs.

**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-4.G.1 | Clean checkout live run | auto | Fresh clone, make up, submit the two URLs of the break scenario. | BREAK WITNESSED with six fresh runs, badge LIVE, evidence points to pinned SHAs. |
| TC-4.G.2 | Negative control clean | auto | Submit the no-drift or harmless-drift pair. | No witness. |
| TC-4.G.3 | Unfinished MUSTs are visible as unavailable | manual | Read the capability banner. | Attribution, bundle replay and unfinished dashboard views are shown unavailable, not hidden. |

**Record progress:** `python tools/track.py start M4.G`, then `python tools/track.py tc TC-4.G.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M4.G`.


## Phase 5: Complete the MUST core (attribution, evidence, dashboard, conformance)  (gate D)

### M5.1 Two-sided ddmin attribution

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Narrow a witnessed failure to the smallest dependency difference, in both directions.

**Tasks**

- Group coupled packages only when resolver metadata justifies it (for example a package and its compiled core).
- Singleton pre-check, then ddmin over the world delta. Forced worlds are built with --no-deps and the witness signature must match exactly.
- Two-sided confirmation: applying the cause to the reference reproduces the failure, and reverting it in the consumer world makes the failure disappear.
- If either direction cannot be built or tested, report PARTIAL or INCONCLUSIVE and name the missing direction. Never label it fully attributed.
- Label observed worlds separately from forced counterfactual worlds. Report search budget and minimality scope.

**Expected files:** `backend/faultline/attribution/ddmin.py`, `backend/faultline/worlds/forced.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-5.1.1 | ddmin on a mock oracle | auto | Unit tests: single cause, two interacting causes, no cause, non-monotonic oracle. | Returns a 1-minimal set for the monotonic cases; flags non-monotonicity; returns empty for no cause. |
| TC-5.1.2 | Real scenario attribution | auto | Run attribution on the transitive-drift scenario (D) with several irrelevant differing packages. | Minimal set equals the expected package in the scenario YAML; sidedness two_sided; each attempted subset and outcome stored. |
| TC-5.1.3 | One-sided is labelled | auto | Make the necessity world unbuildable (remove a wheel). | Result PARTIAL with the missing direction named; UI does not say 'minimal'. |
| TC-5.1.4 | Forced worlds are never presented as observed | manual | Open the why-path for the attribution. | Forced worlds carry the label 'attribution experiment (forced world)'. |
| TC-5.1.5 | Budget honesty | auto | Set a tiny time budget. | Status budget-limited with the best subset so far; not 'complete'. |

**Record progress:** `python tools/track.py start M5.1`, then `python tools/track.py tc TC-5.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M5.1`.

### M5.2 Portable evidence bundle, verifier and replay

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Another machine can verify and replay a witness from the bundle.

**Tasks**

- Bundle contains pinned SHAs, manifests and lockfiles, world descriptors, runtime and platform, resolver versions, image digests, oracle plan, six run records, signature, attribution attempts, verdict predicate and policy version, reproduction instructions.
- Verifier rejects missing, modified, duplicate, conflicting or path-traversal entries.
- Replay outcome is exactly one of EXACT_REPRODUCTION, ENVIRONMENT_LIMITED, NON_REPRODUCIBLE with reasons. Missing artifacts are never fetched from moving refs.

**Expected files:** `backend/faultline/witnesses/bundle.py`, `backend/faultline/witnesses/replay.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-5.2.1 | Verifier rejects bad bundles | auto | Feed bundles with: a missing file, a changed byte, a duplicated entry, a ../ path, an unknown schema version. | Each rejected with a specific error. None processed. |
| TC-5.2.2 | Replay on a clean machine | manual | On a different computer, run the bundle replay command. | Outcome EXACT_REPRODUCTION or ENVIRONMENT_LIMITED with reasons; recorded in the log. |
| TC-5.2.3 | No moving refs | auto | Delete an artifact from the replay machine cache. | Replay reports the missing artifact; nothing is fetched by branch or tag. |

**Record progress:** `python tools/track.py start M5.2`, then `python tools/track.py tc TC-5.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M5.2`.

### M5.3 Durable worker behaviour

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P1

**Goal.** Crashes, retries and cancellations do not corrupt evidence.

**Tasks**

- Atomic claim, lease and heartbeat, bounded retries, cancellation, duplicate idempotency, orphan sandbox cleanup.
- Partial evidence is preserved with a status. Retries create new run records.
- Cache keys include parser, resolver, oracle and verdict versions.

**Expected files:** `backend/faultline/workers/run.py`, `backend/faultline/workers/cleanup.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-5.3.1 | Worker crash mid-analysis | auto | Kill the worker during VERIFY. | Another worker resumes; no duplicated witnesses; no run is counted twice. |
| TC-5.3.2 | Cancellation cleans up | auto | Cancel during execution. | The container is removed; partial evidence is retained and labelled. |
| TC-5.3.3 | Stale cache after rule change | auto | Bump the verdict policy version. | Findings are recomputed from evidence; no stale verdict served. |

**Record progress:** `python tools/track.py start M5.3`, then `python tools/track.py tc TC-5.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M5.3`.

### M5.4 Observability and retention (minimal)

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P2

**Goal.** Know where time goes; never delete referenced evidence.

**Tasks**

- Structured logs with correlation ids and phase timings; redact tokens and secrets.
- Retention limits for repositories, artifacts, logs and bundles; cleanup must not delete evidence referenced by a retained finding.
- Hackathon scope: log plus timing per phase. Dashboards for queue wait and cache rate are deferred.

**Expected files:** `backend/faultline/core/logging.py`, `backend/faultline/storage/retention.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-5.4.1 | Secrets redacted | auto | Run an analysis with a canary token in the environment and grep all logs. | Canary absent. |
| TC-5.4.2 | Retention safety | auto | Run cleanup with aggressive limits. | Anything referenced by a finding survives. |

**Record progress:** `python tools/track.py start M5.4`, then `python tools/track.py tc TC-5.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M5.4`.

### M5.5 Scenario set and false-positive controls

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Measured only against committed labels.

**Tasks**

- Add the master scenarios and negative controls (A through J, plus the look-alike control).
- Compute TP, FP and FN only against committed labels; report sample count and scope.
- Do not claim general ecosystem accuracy from a small set.

**Expected files:** `fixtures/scenarios/*.yaml`, `scripts/run_fixtures.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-5.5.1 | All scenarios match expected verdicts | auto | python scripts/run_fixtures.py --assert | Every scenario's verdict equals its YAML expectation. Output lists the sample count. |
| TC-5.5.2 | Controls produce no witness | auto | Inspect results for A, G, H and the look-alike control. | Zero BREAK or SILENT witnesses. |

**Record progress:** `python tools/track.py start M5.5`, then `python tools/track.py tc TC-5.5.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M5.5`.

### M5.6 Complete MUST dashboard (eight views, all states)

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** Funnel, world matrix, witness detail, why-path, findings list, suspected tray, inventory graph, mode and capability indicators.

**Tasks**

- Implement each view against persisted API records only.
- For each view, handle normal, empty, failed, unsupported, inconclusive and not-applicable states.
- Retain screenshots and the test report per release.

**Expected files:** `frontend/src/pages/*.tsx`, `tests/e2e/dashboard.spec.ts`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-5.6.1 | Funnel counts | auto | E2E asserts every stage count against the API, including zero and partial coverage. | Displayed counts equal API values. |
| TC-5.6.2 | World matrix | auto | E2E on a run with supported, failed, unsupported and NO_DRIFT cells. | Importer visibility, runtime, platform, cell status and coverage denominator are all correct. |
| TC-5.6.3 | Witness detail | auto | E2E opens a witness. | Six fresh run records, normalized signature, raw and normalized output, failure taxonomy shown. |
| TC-5.6.4 | Why-path | auto | E2E opens the why-path of a witnessed finding. | Chain: relationship evidence with source location, world delta, oracle, verdict predicate, partial attribution if any. Missing links are 'not analysed', never invented. |
| TC-5.6.5 | Findings and suspected tray | auto | E2E filters findings; opens the suspected tray. | Scoped verdicts and evidence status shown. A suspected candidate never becomes a finding by display alone. |
| TC-5.6.6 | Inventory graph | auto | E2E on a multi-ecosystem run. | Repositories, nested manifests, packages, producer/consumer edges, evidence levels and unsupported nodes are present. |
| TC-5.6.7 | State coverage | auto | Parameterised E2E over empty, failed, unsupported, inconclusive and not-applicable states for each view. | Each state renders a distinct, truthful message. |

**Record progress:** `python tools/track.py start M5.6`, then `python tools/track.py tc TC-5.6.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M5.6`.

### M5.7 Conformance report and Gate D decision

**Gate:** D | **Tier:** MUST | **Hackathon priority:** P0

**Goal.** A machine-readable report proves every master MUST passes.

**Tasks**

- Build the traceability matrix (requirement, phase, test command, result, retained artifact).
- Include PC-1, PC-4, PC-5 and PC-10 cases and the reference-failure policy.
- Any missing test, missing artifact or non-PASS row blocks Gate D.

**Expected files:** `docs/conformance/ps07-matrix.yaml`, `scripts/conformance_report.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-5.7.1 | Report is complete | auto | python scripts/conformance_report.py | Every MUST row has a command, a result PASS and an existing artifact path. |
| TC-5.7.2 | Report fails when a row fails | auto | Break one test deliberately and rerun the report. | Report exits non-zero and names the row. |
| TC-5.7.3 | Gate D is not Gate E | manual | Read the report header. | States 'MVP conformant' and 'not release-hardened' until Gate E passes. |

**Record progress:** `python tools/track.py start M5.7`, then `python tools/track.py tc TC-5.7.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M5.7`.


## Phase 6: Static API analysis and exposure  (gate X)

### M6.1 Relationship sufficiency matrix

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P2

**Goal.** Each signal maps to the strongest conclusion it allows.

**Tasks**

- same name or version drift = candidate; dependency declaration or import = possible; traceable artifact identity plus consumer reference = stronger; verified provenance plus observed consumption = confirmable.
- Keep the suspected tray separate. Name-only matches, forks and vendored code never create confirmed edges.

**Expected files:** `backend/faultline/relationships/sufficiency.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-6.1.1 | Signal-to-conclusion table | auto | Table-driven test over every signal combination. | Output level equals the table; no combination skips a level. |
| TC-6.1.2 | Forks and vendored code | auto | Run on a fork and on a repo vendoring the artifact. | No confirmed edge; suspected with the missing evidence listed. |

**Record progress:** `python tools/track.py start M6.1`, then `python tools/track.py tc TC-6.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M6.1`.

### M6.2 Static API surface and ApiDelta (griffe)

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P1

**Goal.** Explain which public symbols changed between two package versions.

**Tasks**

- Extract API statically without importing target modules; cache by package hash and extractor version.
- Preserve incomplete extraction when dynamic exports or C extensions limit visibility.
- Static delta is explanatory only.

**Expected files:** `backend/faultline/diff/surface.py`, `backend/faultline/diff/delta.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-6.2.1 | Known removal is reported | auto | Compute the delta for the package pair in a verified fixture scenario. | The expected removed or changed symbol appears with kind and old/new description. |
| TC-6.2.2 | No import of target code | auto | Run extraction on a package whose __init__ writes a canary. | Canary absent. |
| TC-6.2.3 | Limits are flagged | auto | Run on a package with a C extension and a module __getattr__. | Flags opaque_modules and dynamic_exports set. |

**Record progress:** `python tools/track.py start M6.2`, then `python tools/track.py tc TC-6.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M6.2`.

### M6.3 Full usage index and exposure

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P1

**Goal.** Know which changed symbols are actually referenced, with honest coverage.

**Tasks**

- Resolve imports, aliases, attribute chains, wildcard imports (via __all__), local type propagation, string-path references; tag GENERATED, NOTEBOOK, TYPE_ONLY, OPTIONAL_PATH.
- Mark dynamic and reflective forms DYNAMIC or UNRESOLVED.
- Exposure = reference to a changed symbol. Coverage = resolved references / all references to divergent packages.

**Expected files:** `backend/faultline/usage/index.py`, `backend/faultline/usage/exposure.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-6.3.1 | Resolution fixtures | auto | Run on re-export, wildcard, alias, shadowing and notebook fixtures. | Statuses match the golden file. |
| TC-6.3.2 | Coverage is computed | auto | Run on a file with 9 resolved and 1 dynamic reference. | Coverage 0.9; dynamic reference listed. |
| TC-6.3.3 | Cache invalidation | auto | Edit one source file. | Only that file is re-analysed (content-hash keyed). |

**Record progress:** `python tools/track.py start M6.3`, then `python tools/track.py tc TC-6.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M6.3`.

### M6.4 EXPOSED, POTENTIAL and NOT EXPOSED verdicts

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P1

**Goal.** Static findings follow the master thresholds and stay distinct from witnesses.

**Tasks**

- NOT EXPOSED is forbidden when coverage is below threshold. Show coverage on every NOT EXPOSED and POTENTIAL.
- Static findings and witnessed findings are visually and semantically distinct.

**Expected files:** `backend/faultline/verdicts/engine.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-6.4.1 | Coverage gate | auto | Feed coverage 0.85 and 0.95 with no exposures. | 0.85 -> not NOT_EXPOSED (POTENTIAL or INCONCLUSIVE); 0.95 -> NOT_EXPOSED with coverage shown. |
| TC-6.4.2 | Static cannot witness | auto | Feed exposures with no execution witness. | Verdict is EXPOSED, never BREAK_WITNESSED. |

**Record progress:** `python tools/track.py start M6.4`, then `python tools/track.py tc TC-6.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M6.4`.


## Phase 7: Contract replay, type checking, reconciliation  (gate X)

### M7.1 Contract replay (pydantic JSON, producer bytes to consumer) [AMENDMENT]

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P1

> **Amendment.** A-3. The plan puts contract replay after the MVP, but the master's hero demo for the data-crossing channel depends on it. Recommended as the first expansion item once Gate C is stable.

**Goal.** Catch silent data divergence between producer and consumer worlds.

**Tasks**

- Produce bytes once in the producer world and feed those exact bytes to the consumer world.
- Inputs in tiers: real fixtures (T1), minimal valid (T2), schema-generated (T3). An input counts only if the reference world accepts it.
- Classify SAME, REJECTED_IN_TEST, VALUE_DIVERGENCE, FORMAT_DIVERGENCE, WARNING_ONLY, BOTH_FAIL. Shrink inputs. Headline witnesses come from T1 or T2.

**Expected files:** `backend/faultline/oracles/o_contract.py`, `backend/faultline/oracles/harness/contract_producer.py`, `backend/faultline/oracles/harness/contract_consumer.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-7.1.1 | Known rejection | auto | Run on the data-contract scenario (J). | REJECTED_IN_TEST on a T2 input; witness under the 3+3 rule; bytes stored. |
| TC-7.1.2 | Known silent divergence | auto | Run on the union scenario (E) if it was verified in M1.0. | VALUE_DIVERGENCE with both values shown. |
| TC-7.1.3 | Anti-garbage | auto | Generate inputs that the reference world rejects. | They are discarded and counted as invalid, never reported. |
| TC-7.1.4 | Negative control | auto | Run on a model whose field has a default. | All SAME. |

**Record progress:** `python tools/track.py start M7.1`, then `python tools/track.py tc TC-7.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M7.1`.

### M7.2 Differential type checking (pyright)

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P2

**Goal.** A static signal for typed packages, never a runtime claim.

**Tasks**

- Pin pyright and the exact flags and interpreter; run both worlds with identical source and configuration.
- Report only new diagnostics. Configuration or import-resolution failure makes the oracle inconclusive.

**Expected files:** `backend/faultline/oracles/o_typecheck.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-7.2.1 | Identical worlds, zero new diagnostics | auto | Run with ref == test. | No new diagnostics. |
| TC-7.2.2 | Correct interpreter used | auto | Print the interpreter pyright resolved in each run. | Each equals the world's /opt/world interpreter, not the host. |

**Record progress:** `python tools/track.py start M7.2`, then `python tools/track.py tc TC-7.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M7.2`.

### M7.3 Expanded O-bind and cross-oracle reconciliation

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P2

**Goal.** More call shapes covered; conflicting signals shown, not hidden.

**Tasks**

- Store each oracle independently; the ordered verdict engine decides precedence.
- Typecheck or contract results never erase a valid repeatable runtime witness.

**Expected files:** `backend/faultline/oracles/reconcile.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-7.3.1 | No erasure | auto | Combine a runtime witness with a passing typecheck. | Verdict remains BREAK_WITNESSED; the typecheck shown as a non-conflicting signal. |

**Record progress:** `python tools/track.py start M7.3`, then `python tools/track.py tc TC-7.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M7.3`.


## Phase 8: What-if and verified remediation  (gate X)

### M8.0 Demo-minimal remediation: pin and re-run [AMENDMENT]

**Gate:** S | **Tier:** AMEND | **Hackathon priority:** P0

> **Amendment.** A-4. The story is Detect, Reproduce, Attribute, Fix, but the plan delivers 'fix' only in Phase 8 after Gates D and E. This milestone adds the smallest honest version earlier.

**Goal.** For the attributed cause, apply one constraint change, re-resolve, and re-run the matrix.

**Tasks**

- Generate a structured constraint change (for example a version cap on the attributed package) for one consumer.
- Resolve with the native resolver, rebuild the world, and re-run the affected oracles under the 3+3 rule.
- Label VERIFIED only if the witness disappears and no new witness appears for that artifact's other consumer worlds; otherwise SUGGESTED.

**Expected files:** `backend/faultline/remediation/minimal.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-8.0.1 | Fix verifies | auto | Apply the expected constraint for the transitive-drift scenario and re-run. | Original witness gone; no new witness; label VERIFIED with fresh run records. |
| TC-8.0.2 | Bad fix is not verified | auto | Apply a constraint that makes resolution fail or breaks another consumer. | Label SUGGESTED or REJECTED with the reason. |
| TC-8.0.3 | No auto-push | auto | Search the code for git push or network writes in remediation. | None; output is a diff only. |

**Record progress:** `python tools/track.py start M8.0`, then `python tools/track.py tc TC-8.0.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M8.0`.

### M8.1 Bounded candidate generation

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P2

**Goal.** Candidate worlds without a Cartesian explosion.

**Tasks**

- Candidates from the minimal cause, observed consumer versions and bounded satisfying versions; at most six per package.
- Record explored and pruned candidates and the budget. The native resolver validates each candidate.

**Expected files:** `backend/faultline/whatif/moves.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-8.1.1 | Bounded | auto | Run on a finding with 3 cause packages. | No more than 6 versions per package; explored and pruned lists stored. |

**Record progress:** `python tools/track.py start M8.1`, then `python tools/track.py tc TC-8.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M8.1`.

### M8.2 What-if evaluation and ranking

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P2

**Goal.** Rank candidate worlds deterministically.

**Tasks**

- Resolve candidates, run the minimal oracle first, then the full relevant matrix for promising ones.
- Rank by number of changes, constraints and verification completeness.
- Budget exhaustion returns SEARCH_INCOMPLETE, never 'no fix exists'.

**Expected files:** `backend/faultline/whatif/search.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-8.2.1 | Deterministic ranking | auto | Run the search twice. | Same ranked list. |
| TC-8.2.2 | Budget message | auto | Set a tiny budget. | SEARCH_INCOMPLETE. |

**Record progress:** `python tools/track.py start M8.2`, then `python tools/track.py tc TC-8.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M8.2`.

### M8.3 Full remediation gates G1 to G4

**Gate:** X | **Tier:** SHOULD | **Hackathon priority:** P2

**Goal.** VERIFIED only after resolution, witness disappearance, affected oracles and matrix regression all pass.

**Tasks**

- G1 resolve; G2 witness disappears; G3 affected reference and consumer oracles pass; G4 no new confirmed break in the affected matrix.
- Validate a structured manifest or constraint diff. No shell commands, no auto-push.

**Expected files:** `backend/faultline/remediation/gates.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-8.3.1 | All gates pass | auto | Verify a known-good plan. | VERIFIED with four gate records and fresh runs. |
| TC-8.3.2 | One consumer fixed, another broken | auto | Verify a plan that helps one consumer but breaks another. | G4 fails; not VERIFIED. |
| TC-8.3.3 | Stale cache is not verification | auto | Verify a plan with a warm cache. | Fresh runs required; reused results not counted. |

**Record progress:** `python tools/track.py start M8.3`, then `python tools/track.py tc TC-8.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M8.3`.


## Phase 9: npm runtime expansion  (gate X)

### M9.1 npm runtime verification (NICE)

**Gate:** X | **Tier:** NICE | **Hackathon priority:** P2

**Goal.** Enable Node execution only after its own sandbox profile passes adversarial tests.

**Tasks**

- Pin Node and npm; script suppression; separate sandbox image; O-import first.
- Expose runtime capability independently from inventory and relationship support.

**Expected files:** `docker/exec-node/Dockerfile`, `backend/faultline/oracles/o_import_node.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-9.1.1 | Lifecycle scripts never run | auto | Include a package whose postinstall writes a canary. | Canary absent. |
| TC-9.1.2 | Nested copies preserved | auto | Run on the nested-version fixture. | World hash keeps nested visibility; negative control passes. |

**Record progress:** `python tools/track.py start M9.1`, then `python tools/track.py tc TC-9.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M9.1`.


## Phase 10: Maven runtime expansion  (gate X)

### M10.1 Maven resolution and runtime (NICE)

**Gate:** X | **Tier:** NICE | **Hackathon priority:** P2

**Goal.** Only via Maven's model-builder and resolver libraries, never lifecycle goals.

**Tasks**

- Enable only after an isolated image, pinned JDK and fixtures validate the exact operation.
- SNAPSHOT artifacts are non-reproducible unless an immutable timestamp is captured.

**Expected files:** `tools/maven-resolve/`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-10.1.1 | No plugin or lifecycle execution | auto | Resolve a POM declaring a build extension that writes a canary. | Canary absent. |
| TC-10.1.2 | Capability matches tests | manual | Read the Maven row of the capability banner. | States exactly what is tested: inventory, resolution, runtime. |

**Record progress:** `python tools/track.py start M10.1`, then `python tools/track.py tc TC-10.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M10.1`.


## Phase 11: Conformance, evaluation, security release gate  (gate E)

### M11.1 Final traceability and consistency pass

**Gate:** E | **Tier:** MUST | **Hackathon priority:** P1

**Goal.** The master, the plan, the code and the tests agree.

**Tasks**

- Re-run the conformance report; consistency pass against the master (no unapproved schema or verdict divergence).

**Expected files:** `docs/conformance/ps07-matrix.yaml`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-11.1.1 | No divergence from the master | manual | Diff enums and verdict names in code against the master. | Identical, or an ADR documents the approved difference. |

**Record progress:** `python tools/track.py start M11.1`, then `python tools/track.py tc TC-11.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M11.1`.

### M11.2 Evaluation protocol, benchmark and ablation [AMENDMENT]

**Gate:** E | **Tier:** MUST | **Hackathon priority:** P0

> **Amendment.** A-5. The plan has an evaluation section but not the ablation (version-only, API-diff, author matrix, consumer-derived worlds, witnesses, ddmin). The consumer-derived-worlds claim is the project's novelty, so it must be measured directly.

**Goal.** Numbers in the pitch come from scripts, with denominators.

**Tasks**

- Compute TP, FP and FN only against committed labels, including negative controls and sample size.
- Ablation A to G: version-only; API diff; API diff + usage; author-selected matrix; consumer-derived matrix; + witness discipline; + ddmin. Headline: breaks found by consumer-derived worlds that the author-selected matrix misses.
- Measure reproducibility, world coverage, inconclusive rate, latency p50 and p95, memory and disk. Detect producer CI worlds heuristically for the comparison and label them heuristic.
- Do not state accuracy targets before a baseline exists.

**Expected files:** `benchmarks/cases/*.yaml`, `benchmarks/ablations.py`, `benchmarks/ci_worlds.py`, `scripts/run_benchmark.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-11.2.1 | Reproducible report | auto | Run scripts/run_benchmark.py twice. | Identical metrics (timings excluded); report lists denominators and limitations. |
| TC-11.2.2 | Labels precede results | auto | Check git history for the label files and the results file. | Label commit is earlier than the first results commit. |
| TC-11.2.3 | Ablation D vs E is reported | auto | Read the report. | Reports the count of breaks found only by consumer-derived worlds, even if zero. |

**Record progress:** `python tools/track.py start M11.2`, then `python tools/track.py tc TC-11.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M11.2`.

### M11.3 Deployment security release gate

**Gate:** E | **Tier:** MUST | **Hackathon priority:** P1

**Goal.** Test the real deployment, not mocks.

**Tasks**

- On the actual disposable VM and Docker daemon: socket exposure, privileges, pinned images, network and egress policy, CPU/memory/PID/disk/time limits, non-root, read-only mounts, dropped capabilities, seccomp, absence of secrets, orphan cleanup after crash and cancellation.
- Test archive traversal, symlinks and hard links, decompression bombs, egress to cloud metadata and internal addresses, output flood, secret leakage.
- If a control is absent or unverifiable, disable arbitrary-code execution and report it unavailable.

**Expected files:** `tests/security/test_deployment.py`, `docs/security/deployment-report.md`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-11.3.1 | Boundary inspection | auto | Run the deployment inspector on the demo VM. | Every control reported PASS with the observed value (not just the configured value). |
| TC-11.3.2 | Fail closed on a bad control | auto | Add a host mount or enable network on an execution profile. | Inspector fails; execution capability is disabled with a reason. |
| TC-11.3.3 | Attack suite | auto | Run traversal, symlink, hard link, zip bomb, metadata egress, output flood and secret canary tests. | All contained; no canary visible; host healthy. |

**Record progress:** `python tools/track.py start M11.3`, then `python tools/track.py tc TC-11.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M11.3`.

### M11.4 Concurrency and scale envelope (trimmed) [AMENDMENT]

**Gate:** E | **Tier:** SHOULD | **Hackathon priority:** P2

> **Amendment.** A-6. Cache stampede tests, queue backpressure and a documented PostgreSQL migration trigger are good engineering, but are lower priority than the demo for a hackathon. Keep duplicate-submission, crash and lock-contention tests; defer the rest to the post-hackathon backlog.

**Goal.** Know the tested envelope and state it.

**Tasks**

- Test duplicate submissions, worker crashes, lease expiry and SQLite contention.
- Document the measured envelope and the PostgreSQL migration trigger.

**Expected files:** `tests/integration/test_concurrency.py`, `docs/adr/postgres-trigger.md`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-11.4.1 | Contention | auto | Run 4 workers and 20 concurrent submissions. | No lost or duplicated evidence; any lock errors handled by retry. |

**Record progress:** `python tools/track.py start M11.4`, then `python tools/track.py tc TC-11.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M11.4`.

### M11.5 Release manifest and clean-machine replay

**Gate:** E | **Tier:** MUST | **Hackathon priority:** P1

**Goal.** A release candidate rebuilds from nothing.

**Tasks**

- Pin the toolchain and image digests; generate the release manifest in CI.
- REPLAY mode shows recorded evidence without Docker or network; re-run is disabled and labelled when prerequisites are missing.
- Bundle import validates schema version, hashes, paths and size limits.

**Expected files:** `scripts/release_manifest.py`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-11.5.1 | Clean-environment deploy and tests | manual | On a new VM, deploy the release candidate and run the release-blocking suite. | All green; deployment fingerprint and cleanup report retained. |
| TC-11.5.2 | Replay without Docker or network | manual | Stop Docker, disconnect the network, open REPLAY mode. | Evidence displays; Re-run disabled with a visible reason; badge RECORDED. |

**Record progress:** `python tools/track.py start M11.5`, then `python tools/track.py tc TC-11.5.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M11.5`.


## Phase 12: Real-world case, demo and submission  (gate S)

### M12.1 Real-world historical case (not a fixture) [AMENDMENT]

**Gate:** S | **Tier:** AMEND | **Hackathon priority:** P0

> **Amendment.** A-7. v3.1 dropped the real-world case. It is the answer to 'is the demo staged?' and must be built and verified.

**Goal.** Reproduce a publicly reported dependency break from public registries by resolution date.

**Tasks**

- Candidate: an older Flask release resolved before and after a Werkzeug major release (time-bounded resolution). Verify every fact by hand first (release dates, removed symbol, error text, versions).
- Run it through the same pipeline, with the time-machine cutoff recorded in provenance.
- If the case does not reproduce as expected, pick another public case and record why.

**Expected files:** `fixtures/scenarios/REAL1.yaml`, `fixtures/verification/REAL1.md`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-12.1.1 | Facts verified by hand | manual | Reproduce the failure in plain venvs for the two dates. | Failure and pass observed; versions and error recorded in REAL1.md. |
| TC-12.1.2 | Faultline reproduces it | auto | Run the pipeline with the two resolution cutoffs. | BREAK WITNESSED, signature matches REAL1.md, attribution names the package you verified. |
| TC-12.1.3 | Public evidence linked | manual | Collect at least one public issue or changelog link describing the break. | Link stored in the scenario file; claim in slides matches it. |

**Record progress:** `python tools/track.py start M12.1`, then `python tools/track.py tc TC-12.1.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M12.1`.

### M12.2 Demo modes, warm caches and fallbacks [AMENDMENT]

**Gate:** S | **Tier:** AMEND | **Hackathon priority:** P0

> **Amendment.** A-8. The master's three demo modes and fallbacks are missing from v3.1.

**Goal.** The demo survives GitHub, registry and Docker failures, and is always honest about what is live.

**Tasks**

- FIXTURE mode: real public fixture repositories at pinned SHAs, warm caches, Re-run executes live.
- REPLAY mode: recorded evidence only; Re-run disabled.
- Local git mirror for pinned SHAs, warmed wheelhouse, images pulled by digest on the demo machine and a backup machine.
- Mode badge cannot be hidden by configuration.

**Expected files:** `scripts/warm_caches.py`, `scripts/export_replay.py`, `docs/demo_drill.md`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-12.2.1 | Network unplugged | manual | Disconnect the network and run FIXTURE mode end to end. | Works from mirror and caches; badge says so. |
| TC-12.2.2 | Docker stopped | manual | Stop Docker and open REPLAY. | Recorded evidence displays; badge RECORDED; Re-run disabled. |
| TC-12.2.3 | Badge cannot lie | auto | Serve a cached result with mode LIVE forced in the request. | UI shows the mode stored with the evidence, not the requested one. |

**Record progress:** `python tools/track.py start M12.2`, then `python tools/track.py tc TC-12.2.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M12.2`.

### M12.3 Demo script, rehearsal and judge Q&A [AMENDMENT]

**Gate:** S | **Tier:** AMEND | **Hackathon priority:** P0

> **Amendment.** A-9. The plan explicitly excludes any pitching or demo script. A hackathon playbook needs a rehearsed demo and Q&A milestone, because the demo is how the work is judged.

**Goal.** A rehearsed 3 to 5 minute run: Detect, Reproduce, Attribute, Fix.

**Tasks**

- Script the sequence: repositories at pinned SHAs, consumer-derived worlds, funnel, open witness, live Re-run, attribution, fix and re-verify, evidence bundle, real-world case.
- Rehearse three times: normal, network off, Docker off.
- Prepare answers to the judge-attack matrix in the master and have every member rehearse them.

**Expected files:** `docs/demo_script.md`, `docs/judge_qa.md`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-12.3.1 | Timed rehearsal | manual | Three timed runs, each by a different member. | Each finishes between 3 and 5 minutes with no unlabelled cached result. |
| TC-12.3.2 | Q&A drill | manual | A teammate asks all questions in judge_qa.md in random order. | Every answer is honest and matches what the product does. |

**Record progress:** `python tools/track.py start M12.3`, then `python tools/track.py tc TC-12.3.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M12.3`.

### M12.4 Submission pack [AMENDMENT]

**Gate:** S | **Tier:** AMEND | **Hackathon priority:** P0

> **Amendment.** A-10. No submission milestone exists in the plan. Slides and README claims must be audited against the product.

**Goal.** Slides, README, repository and short recording are consistent with the product.

**Tasks**

- Slides within the template's slide limit; every claim traceable to a test or a measured result.
- README with quickstart (make up, make demo-fixture).
- Backup recording of the demo clearly labelled as a recording.

**Expected files:** `README.md`, `docs/submission_checklist.md`


**Validation test cases** (all must pass before `done`)

| ID | Test | Kind | Steps | Expected result |
|---|---|---|---|---|
| TC-12.4.1 | Claims audit | manual | Read every slide claim and link it to a test id or measured number. | No claim without evidence; no 'proof', 'guarantee' or 'compatible' wording. |
| TC-12.4.2 | Fresh-clone quickstart | manual | A teammate follows the README from a clean machine. | Demo runs in FIXTURE mode with no undocumented steps. |

**Record progress:** `python tools/track.py start M12.4`, then `python tools/track.py tc TC-12.4.1 pass --evidence <file-or-url>` for each test case, then `python tools/track.py done M12.4`.


---

# PART D - GATE EXIT CRITERIA

**Gate A.** The product boots, states its mode and capabilities, core contracts are stable, and no compatibility claim is displayed.  
*Must not claim:* Any compatibility finding. Any security claim based on the stub.

**Gate B.** A judge can inspect one complete fixture-backed differential witness, labelled FIXTURE, with a clean negative control.  
*Must not claim:* Live repository analysis. Any oracle that did not run.

**Gate C-input.** A real public repository can be submitted and inspected at a pinned SHA, and the fixture pipeline still works unchanged.  
*Must not claim:* Any dependency or compatibility result yet.

**Gate C-worlds.** At least one real Python repository resolves reproducibly and its world can be rebuilt from recorded inputs. npm and Maven inventory are labelled as inventory only.  
*Must not claim:* npm or Maven runtime compatibility.

**Gate C.** One real public producer/consumer pair yields a repeatable, correctly scoped LIVE finding with traceable evidence, and a negative control stays clean.  
*Must not claim:* Full MVP conformance. Gate D is a separate decision.

**Gate D.** Every canonical MUST passes with an automated test and a retained evidence artifact.  
*Must not claim:* SHOULD or NICE completion, universal compatibility, npm or Maven runtime support, or release hardening.

**Gate X-analysis.** Each expansion capability is enabled only after its own fixtures and tests pass, and none can overrule a runtime witness.  
*Must not claim:* That expansion work substitutes for any missing MUST.

**Gate E.** The deployment boundary, security, regression, reliability and clean-machine replay checks are green on the actual demo deployment.  
*Must not claim:* Any security guarantee beyond the tested disposable-VM and Docker configuration.



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
