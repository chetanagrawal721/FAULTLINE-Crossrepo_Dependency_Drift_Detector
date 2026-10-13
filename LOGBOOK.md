# FAULTLINE LOGBOOK

Append-only record of build progress. Entries are written by `tools/track.py` when a milestone starts,
a test case is recorded, a milestone completes (or is blocked or waived), or a gate is declared.
Do not edit past entries. Add context with `python tools/track.py note "..."`.

Format: `### <UTC time> | <EVENT> | <id> | by <name>` followed by details.

---

### 2026-10-12 18:11 UTC | NOTE | - | by Claude
- Playbook created from Implementation Plan v3.1. Review verdict: strong engineering plan, not yet hackathon-winning. Ten amendments (A-1..A-10) added and six defects (D-1..D-6) resolved; see Part A of docs/FAULTLINE_PLAYBOOK.md.

### 2026-10-12 18:11 UTC | NOTE | - | by Claude
- Decision: Gate D requires npm/Maven INVENTORY milestones (M3.6, M3.7) only. Runtime expansion (M9.1, M10.1) is NICE. Resolves contradiction D-1 in plan v3.1.

### 2026-10-12 18:11 UTC | NOTE | - | by Claude
- Decision: all third-party behaviours from the master (pydantic v1/v2, Werkzeug 3 / Flask 2.2, urllib3 2, PyJWT 2, uv flags) are UNVERIFIED until M1.0 and M12.1 record hand verification.

### 2026-10-12 18:36 UTC | START | M0.1 | by Claude
- Repository layout and pinned toolchain

### 2026-10-12 18:53 UTC | START | M0.2 | by Claude
- Canonical models, schema and migrations

### 2026-10-12 18:53 UTC | START | M0.3 | by Claude
- Canonical hashing

### 2026-10-12 18:53 UTC | START | M0.4 | by Claude
- Durable job contract

### 2026-10-12 18:53 UTC | START | M0.5 | by Claude
- Health, capabilities and the capability banner

### 2026-10-12 18:53 UTC | START | M0.6 | by Claude
- CI gate

### 2026-10-12 18:53 UTC | TC PASS | TC-0.1.1 | by Claude
- Clean checkout boots
- evidence: evidence/M0.1/TC-0.1.1.txt
- throwaway clone outside the project repo; uv sync --frozen, npm ci, fl.py up --check exit 0

### 2026-10-12 18:53 UTC | TC PASS | TC-0.1.2 | by Claude
- Pins are real
- evidence: evidence/M0.1/TC-0.1.2.txt
- 0 image refs exist yet; sha256 rule proven by negative tests, exercised for real from M1.2

### 2026-10-12 18:53 UTC | TC PASS | TC-0.1.3 | by Claude
- Make targets fail loudly
- evidence: evidence/M0.1/TC-0.1.3.txt
- tools/fl.py exit codes verified. The Makefile only forwards to it; make is not installed here, so run 'make test' once on the Linux VM

### 2026-10-12 18:53 UTC | TC PASS | TC-0.2.1 | by Claude
- Migration is clean and idempotent
- evidence: evidence/M0.2/TC-0.2.1.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.2.2 | by Claude
- Failed migration leaves no half schema
- evidence: evidence/M0.2/TC-0.2.2.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.2.3 | by Claude
- Invalid transition and unknown enum rejected
- evidence: evidence/M0.2/TC-0.2.3.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.2.4 | by Claude
- Foreign-key chain exists
- evidence: evidence/M0.2/TC-0.2.4.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.3.1 | by Claude
- Order independence
- evidence: evidence/M0.3/TC-0.3.1.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.3.2 | by Claude
- Semantic sensitivity
- evidence: evidence/M0.3/TC-0.3.2.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.3.3 | by Claude
- NaN and float handling
- evidence: evidence/M0.3/TC-0.3.3.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.4.1 | by Claude
- Atomic claim under contention
- evidence: evidence/M0.4/TC-0.4.1.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.4.2 | by Claude
- Stale lease reclaimed
- evidence: evidence/M0.4/TC-0.4.2.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.4.3 | by Claude
- Idempotent submission
- evidence: evidence/M0.4/TC-0.4.3.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.4.4 | by Claude
- Cancellation
- evidence: evidence/M0.4/TC-0.4.4.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.5.1 | by Claude
- Capability truthfulness
- evidence: evidence/M0.5/TC-0.5.1.txt

### 2026-10-12 18:53 UTC | TC PASS | TC-0.5.2 | by Claude
- Banner renders from API
- evidence: evidence/M0.5/TC-0.5.2.txt
- viewed in the in-app browser; screenshot saved

### 2026-10-12 18:53 UTC | DONE | M0.1 | by Claude
- Repository layout and pinned toolchain
- test cases passed: 3/3

### 2026-10-12 18:53 UTC | DONE | M0.2 | by Claude
- Canonical models, schema and migrations
- test cases passed: 4/4

### 2026-10-12 18:53 UTC | DONE | M0.3 | by Claude
- Canonical hashing
- test cases passed: 3/3

### 2026-10-12 18:53 UTC | DONE | M0.4 | by Claude
- Durable job contract
- test cases passed: 4/4

### 2026-10-12 18:53 UTC | DONE | M0.5 | by Claude
- Health, capabilities and the capability banner
- test cases passed: 2/2

### 2026-10-12 18:53 UTC | NOTE | - | by Claude
- M0.6 NOT done: TC-0.6.1 (CI green on main) and TC-0.6.2 (CI catches type drift) need the first push to GitHub. Local equivalent passed: 'python tools/fl.py ci' exit 0 (evidence/M0.6/local-ci-run.txt) and the drift check fails when the API changes without regenerated types (evidence/M0.6/local-type-drift-check.txt). Gate A cannot be declared until CI runs on GitHub.

### 2026-10-12 18:53 UTC | NOTE | - | by Claude
- Decision: TypeScript 5.9.3 instead of 7.x because openapi-typescript 7.13.0 requires TypeScript ^5. make is not installed on this Windows machine, so tools/fl.py is the real task runner and the Makefile forwards to it. docker/compose.yml deferred to M1.2 (no pinned images exist yet). See docs/adr/0001-0003.

### 2026-10-12 18:53 UTC | NOTE | - | by Claude
- Process: no git commits are made locally by the assistant. All Phase 0 work is uncommitted in the working tree; commit it under your own timeline. .gitattributes forces LF line endings so Windows and the Linux VM agree.

### 2026-10-12 18:53 UTC | NOTE | - | by Claude
- Gotcha fixed: on Windows the venv python.exe is a launcher, so terminating it left uvicorn running. tools/fl.py now kills the process tree (taskkill /T) and detached runs log to var/*.log.

### 2026-10-12 19:32 UTC | NOTE | - | by Claude
- M0.6 deferred by decision: local CI passes; TC-0.6.1/TC-0.6.2 will be recorded after the first GitHub CI run. Proceeding to Phase 1 without declaring Gate A.

### 2026-10-12 19:32 UTC | START | M1.0 | by Claude
- Verify every fixture claim by hand

### 2026-10-12 19:34 UTC | TC PASS | TC-1.0.1 | by Claude
- Break reproduces outside Faultline
- evidence: evidence/M1.0/TC-1.0.1.txt

### 2026-10-12 19:34 UTC | TC PASS | TC-1.0.2 | by Claude
- Reference world passes outside Faultline
- evidence: evidence/M1.0/TC-1.0.2.txt

### 2026-10-12 19:34 UTC | TC PASS | TC-1.0.3 | by Claude
- Verification record is committed
- evidence: evidence/M1.0/TC-1.0.3.txt
- checker plus negative tests

### 2026-10-12 19:34 UTC | DONE | M1.0 | by Claude
- Verify every fixture claim by hand
- test cases passed: 3/3

### 2026-10-12 19:36 UTC | START | M1.1 | by Claude
- Fixture repositories, scenario YAML and negative control

### 2026-10-12 19:38 UTC | TC PASS | TC-1.1.1 | by Claude
- Scenario files validate
- evidence: evidence/M1.1/TC-1.1.1.txt
- validator also cross-checks expected deltas against the real lock files

### 2026-10-12 19:38 UTC | TC PASS | TC-1.1.2 | by Claude
- Negative control exists and is labelled
- evidence: evidence/M1.1/TC-1.1.2.txt

### 2026-10-12 19:38 UTC | DONE | M1.1 | by Claude
- Fixture repositories, scenario YAML and negative control
- test cases passed: 2/2

### 2026-10-12 19:38 UTC | NOTE | - | by Claude
- Fixtures live in fixtures/repos (acme-models + consumers per scenario A, D, H), generated by scripts/make_fixtures.py with uv pip compile --generate-hashes --exclude-newer 2024-10-30 (so Werkzeug resolves to 3.0.6). The real GitHub repos and scenario tags are NOT created yet: scripts/push_fixtures.py is dry-run by default and builds them locally; pushing needs your GitHub org and a decision. Scenarios B, C, E, G, J, L are verified (B, C, E, J) or unwritten and will be added when a phase needs them.

### 2026-10-12 19:42 UTC | START | M1.2 | by Claude
- Sandbox v0: sandboxd, execution image and hardened profile

### 2026-10-12 19:55 UTC | TC PASS | TC-1.2.1 | by Claude
- Network is unreachable
- evidence: evidence/M1.2/TC-1.2.1.txt

### 2026-10-12 19:55 UTC | TC PASS | TC-1.2.2 | by Claude
- Filesystem and identity
- evidence: evidence/M1.2/TC-1.2.2.txt

### 2026-10-12 19:55 UTC | TC PASS | TC-1.2.3 | by Claude
- Resource bombs are contained
- evidence: evidence/M1.2/TC-1.2.3.txt
- fork bomb, 4GB allocation, disk fill, output flood and runaway loop all contained; host and sandboxd stayed responsive

### 2026-10-12 19:55 UTC | TC PASS | TC-1.2.4 | by Claude
- No orphans
- evidence: evidence/M1.2/TC-1.2.4.txt
- real sandboxd subprocess force-killed mid-job; restarted sandboxd swept the orphan

### 2026-10-12 19:55 UTC | TC PASS | TC-1.2.5 | by Claude
- Fail closed
- evidence: evidence/M1.2/TC-1.2.5.txt
- Docker Desktop was not stopped (restart takes minutes); Docker and sandboxd were made unreachable via closed ports, which exercises the same fail-closed paths

### 2026-10-12 19:56 UTC | DONE | M1.2 | by Claude
- Sandbox v0: sandboxd, execution image and hardened profile
- test cases passed: 5/5

### 2026-10-12 19:56 UTC | NOTE | - | by Claude
- M1.2 sandbox: gate C minimum controls now exist and are tested on the real daemon (Docker 29.8.0, Docker Desktop on Windows): non-root, no caps, no-new-privileges, seccomp, read-only root, no network, no docker socket, resource limits, orphan sweep. LIMITS TO STATE HONESTLY: (1) this is hardened Docker on a shared-kernel Docker Desktop VM, not gVisor; the disposable-VM claim applies only to the real demo VM, so tests/security must be re-run there (TC-11.3.1); (2) the fetch profile uses the default bridge network with NO egress allowlist yet; (3) the exec image id changes on every rebuild (pip install is not reproducible) so docker/images.lock.json must be regenerated with scripts/build_images.py on each machine; (4) warm container job takes about 1.4 s on this machine.

### 2026-10-12 19:56 UTC | START | M1.3 | by Claude
- World descriptors and the offline world builder

### 2026-10-12 20:03 UTC | TC PASS | TC-1.3.1 | by Claude
- Offline build from verified artifacts
- evidence: evidence/M1.3/TC-1.3.1.txt
- build runs in the exec zone (no network); installed set equals the lock exactly

### 2026-10-12 20:03 UTC | TC PASS | TC-1.3.2 | by Claude
- Hash mismatch blocks use
- evidence: evidence/M1.3/TC-1.3.2.txt
- wrong hash in lock is refused by pip --require-hashes; a corrupted wheel is refused at build (here caught as a broken zip, the hash check being the backstop for an intact-but-altered wheel)

### 2026-10-12 20:03 UTC | TC PASS | TC-1.3.3 | by Claude
- Reuse is not an execution
- evidence: evidence/M1.3/TC-1.3.3.txt

### 2026-10-12 20:03 UTC | DONE | M1.3 | by Claude
- World descriptors and the offline world builder
- test cases passed: 3/3

### 2026-10-12 20:03 UTC | NOTE | - | by Claude
- M1.3 design decisions: worlds and the wheelhouse live in NAMED DOCKER VOLUMES (fl-world-<hash>, fl-wheelhouse), not host bind mounts, because Windows bind mounts cannot hold the symlinks a venv needs; volumes inherit uid 65534 ownership from the image mount points. A world is writable only for the build_world job; every other use mounts it read-only. World identity includes the sha256 of the actual wheel fetched, so the descriptor is completed after the fetch step. Fetch zone currently has unrestricted bridge egress (allowlist not built).

### 2026-10-12 20:04 UTC | START | M1.4 | by Claude
- O-import and failure classification

### 2026-10-12 20:10 UTC | TC PASS | TC-1.4.1 | by Claude
- Reference passes, consumer fails
- evidence: evidence/M1.4/TC-1.4.1.txt
- first real differential observation by Faultline's own pipeline: reference passes, notify-svc world fails with ImportError url_quote raised inside flask.app

### 2026-10-12 20:10 UTC | TC PASS | TC-1.4.2 | by Claude
- Harness error is not a break
- evidence: evidence/M1.4/TC-1.4.2.txt
- harness crash (no result frame) classified HARNESS_FAILURE; classification rules unit-tested; infrastructure classes always outrank entry classes

### 2026-10-12 20:10 UTC | TC PASS | TC-1.4.3 | by Claude
- Missing optional module is not a break
- evidence: evidence/M1.4/TC-1.4.3.txt
- a missing third-party package is NOT_APPLICABLE; a missing artifact-internal module is still ARTIFACT_FAILURE

### 2026-10-12 20:10 UTC | DONE | M1.4 | by Claude
- O-import and failure classification
- test cases passed: 3/3

### 2026-10-12 20:11 UTC | START | M1.5 | by Claude
- O-tests with the test-only overlay

### 2026-10-12 20:20 UTC | TC PASS | TC-1.5.1 | by Claude
- Per-test differential
- evidence: evidence/M1.5/TC-1.5.1.txt
- real pytest runs in the sandbox: notify-svc world fails test_show_customer with ImportError url_quote raised in flask.app; billing-svc world (no Flask) skips it

### 2026-10-12 20:20 UTC | TC PASS | TC-1.5.2 | by Claude
- Overlay does not change runtime versions
- evidence: evidence/M1.5/TC-1.5.2.txt

### 2026-10-12 20:20 UTC | TC PASS | TC-1.5.3 | by Claude
- Collection error from test-only package
- evidence: evidence/M1.5/TC-1.5.3.txt

### 2026-10-12 20:20 UTC | DONE | M1.5 | by Claude
- O-tests with the test-only overlay
- test cases passed: 3/3

### 2026-10-12 20:20 UTC | NOTE | - | by Claude
- M1.5 design notes: (1) the fixture test for the web extra uses importlib.util.find_spec, NOT pytest.importorskip, because importorskip turns a present-but-broken Flask into a SKIP and would hide the very break Faultline must catch. (2) The test overlay is a distinct world (kind overlay) whose test packages carry scope=test; runtime versions always win and a conflict marks the overlay forced. (3) Per-test JUnit parsing happens inside the container; classification happens in the control plane.

### 2026-10-12 20:21 UTC | START | M1.6 | by Claude
- Witness verifier: 3 reference passes and 3 consumer failures

### 2026-10-12 20:37 UTC | TC PASS | TC-1.6.1 | by Claude
- Witness predicate
- evidence: evidence/M1.6/TC-1.6.1.txt
- first real Faultline witness: 3 fresh reference passes, 3 fresh consumer failures, identical normalized signature (ImportError url_quote, origin flask.app)

### 2026-10-12 20:37 UTC | TC PASS | TC-1.6.2 | by Claude
- Flaky and both-fail are rejected
- evidence: evidence/M1.6/TC-1.6.2.txt

### 2026-10-12 20:37 UTC | TC PASS | TC-1.6.3 | by Claude
- Cache cannot fake repeats
- evidence: evidence/M1.6/TC-1.6.3.txt

### 2026-10-12 20:37 UTC | TC PASS | TC-1.6.4 | by Claude
- Negative control stays clean
- evidence: evidence/M1.6/TC-1.6.4.txt
- Scenario A is covered as a NO_DRIFT cell (identical lock), Scenario H by real runs

### 2026-10-12 20:37 UTC | DONE | M1.6 | by Claude
- Witness verifier: 3 reference passes and 3 consumer failures
- test cases passed: 4/4

### 2026-10-12 20:37 UTC | NOTE | - | by Claude
- M1.6 design notes: the oracle cache key is semantic (oracle, version, world hash, artifact hash, args, run index) and is shared ACROSS cells, so two cells with the same interaction reuse results; this is correct but means tests that want fresh runs must use distinct interactions or force=True. Witness identity (witness_key) is cell-independent: a repeat verification appends to the existing witness instead of creating a second. A run-level infrastructure failure with no entries is surfaced as Verification.problem (not silently an empty result).

### 2026-10-12 20:38 UTC | START | M1.7 | by Claude
- Evidence bundle v1 and export

### 2026-10-12 20:41 UTC | TC PASS | TC-1.7.1 | by Claude
- Bundle validates against schema
- evidence: evidence/M1.7/TC-1.7.1.txt
- real bundle (28 files, 22 KB) verified by the standalone verifier; sample kept at evidence/M1.7/witness-D.bundle.zip

### 2026-10-12 20:41 UTC | TC PASS | TC-1.7.2 | by Claude
- Tamper is detected
- evidence: evidence/M1.7/TC-1.7.2.txt

### 2026-10-12 20:41 UTC | TC PASS | TC-1.7.3 | by Claude
- No secrets
- evidence: evidence/M1.7/TC-1.7.3.txt

### 2026-10-12 20:41 UTC | DONE | M1.7 | by Claude
- Evidence bundle v1 and export
- test cases passed: 3/3

### 2026-10-12 20:41 UTC | NOTE | - | by Claude
- M1.7: bundle = deterministic zip (fixed timestamps) with manifest.json listing every file's sha256; verifier is independent of the database and also checks consistency (3+3 fresh runs, witness key, bundle id) so a bundle with recomputed hashes still cannot lie about provenance. NOT YET BUILT: automated replay (M5.2). REPRODUCE.md says so plainly. Note: bundles contain the artifact source tree, so do not export bundles for private repositories without thinking about that.

### 2026-10-12 20:42 UTC | START | M1.8 | by Claude
- Thin UI for the fixture finding

### 2026-10-12 20:57 UTC | TC PASS | TC-1.8.1 | by Claude
- End to end from scenario id
- evidence: evidence/M1.8/TC-1.8.1.txt
- automated API+worker end-to-end test for scenarios A, D, H plus a manual browser run of D

### 2026-10-12 20:57 UTC | TC PASS | TC-1.8.2 | by Claude
- No false live claim
- evidence: evidence/M1.8/TC-1.8.2.txt

### 2026-10-12 20:57 UTC | DONE | M1.8 | by Claude
- Thin UI for the fixture finding
- test cases passed: 2/2

### 2026-10-12 20:57 UTC | NOTE | - | by Claude
- M1.8 bugs found and fixed during the browser check: (1) FastAPI sync dependencies can open and close a request's SQLite connection on different threads -> intermittent 500s; get_conn now uses check_same_thread=False and a 60-request threadpool regression test exists. (2) Capability banner still said 'unavailable' for things built in M1.4-M1.7; it now reports PARTIAL (FIXTURE scenarios only) when the sandbox is verified, and tests prevent any ENABLED claim. Verdict engine is the Phase 1 SUBSET (policy verdict-policy/0-fixture); the full ordered table is M4.5.

### 2026-10-12 21:04 UTC | NOTE | - | by Claude
- Phase 1 complete locally: M1.0 to M1.8 all done (9/9 milestones, 30 test cases with evidence). Gate B NOT declared only because its prerequisite Gate A is waiting on the first GitHub CI run (M0.6). Local CI (python tools/fl.py ci) passes: 167 tests + 5 e2e (A, D, H) + lint + pins + type drift + UI build + boot with a verified sandbox. docker/images.lock.json is gitignored because the image id is machine specific; run python scripts/build_images.py on every machine before the sandbox tests.

### 2026-10-12 21:17 UTC | NOTE | - | by Claude
- Starting Phase 2 and Phase 3 in one pass as requested (no questions). Plan: ingestion fetches inside the fetch-zone container by reading git objects (no checkout), writing only validated paths to a host snapshot directory; GitHub API client is stdlib-only and injectable for tests.

### 2026-10-12 21:17 UTC | START | M2.1 | by Claude
- URL and ref validation, SHA pinning

### 2026-10-12 21:17 UTC | START | M2.2 | by Claude
- Restricted fetch

### 2026-10-12 21:26 UTC | START | M2.3 | by Claude
- Immutable snapshot and inventory

### 2026-10-12 21:26 UTC | TC PASS | TC-2.1.1 | by Claude
- Validation table
- evidence: evidence/M2.1/TC-2.1.1.txt

### 2026-10-12 21:26 UTC | TC PASS | TC-2.1.2 | by Claude
- Moving tag creates a new snapshot
- evidence: evidence/M2.1/TC-2.1.2.txt

### 2026-10-12 21:26 UTC | TC PASS | TC-2.1.3 | by Claude
- Retry keeps the SHA
- evidence: evidence/M2.1/TC-2.1.3.txt

### 2026-10-12 21:26 UTC | TC PASS | TC-2.2.1 | by Claude
- Hostile repository
- evidence: evidence/M2.2/TC-2.2.1.txt
- symlinks recorded as metadata only (stricter than 'plain file'); local-remote uses git global safe.directory

### 2026-10-12 21:26 UTC | TC PASS | TC-2.2.2 | by Claude
- Limits
- evidence: evidence/M2.2/TC-2.2.2.txt
- partial snapshot with truncated flag + warning (status PARTIAL)

### 2026-10-12 21:26 UTC | TC PASS | TC-2.3.1 | by Claude
- Inventory is complete and hashed
- evidence: evidence/M2.3/TC-2.3.1.txt

### 2026-10-12 21:26 UTC | TC PASS | TC-2.3.2 | by Claude
- Snapshot is read-only
- evidence: evidence/M2.3/TC-2.3.2.txt
- filesystem read-only + hash verification; API exposes no snapshot mutation endpoint

### 2026-10-12 21:26 UTC | DONE | M2.1 | by Claude
- URL and ref validation, SHA pinning
- test cases passed: 3/3

### 2026-10-12 21:26 UTC | DONE | M2.2 | by Claude
- Restricted fetch
- test cases passed: 2/2

### 2026-10-12 21:26 UTC | DONE | M2.3 | by Claude
- Immutable snapshot and inventory
- test cases passed: 2/2

### 2026-10-12 21:27 UTC | START | M2.4 | by Claude
- Ingestion API and UI

### 2026-10-12 21:51 UTC | TC PASS | TC-2.4.1 | by Claude
- Real public repository
- evidence: evidence/M2.4/TC-2.4.1.txt
- octocat/Hello-World real fetch; ci 255 passed; e2e A,D,H 5 passed

### 2026-10-12 21:51 UTC | TC PASS | TC-2.4.2 | by Claude
- Failure states
- evidence: evidence/M2.4/TC-2.4.2-live.txt
- live not-found/bad-ref/invalid + UI + fake-transport private/rate-limit

### 2026-10-12 21:51 UTC | DONE | M2.4 | by Claude
- Ingestion API and UI
- test cases passed: 2/2

### 2026-10-12 21:57 UTC | START | M3.1 | by Claude
- Python project discovery

### 2026-10-12 21:57 UTC | START | M3.2 | by Claude
- Python parsers with diagnostics

### 2026-10-12 21:57 UTC | TC PASS | TC-3.1.1 | by Claude
- Multi-project repository
- evidence: evidence/M3.1/TC-3.1.1.txt

### 2026-10-12 21:57 UTC | TC PASS | TC-3.1.2 | by Claude
- No code execution
- evidence: evidence/M3.1/TC-3.1.2.txt

### 2026-10-12 21:57 UTC | TC PASS | TC-3.2.1 | by Claude
- Golden files
- evidence: evidence/M3.2/TC-3.2.1.txt

### 2026-10-12 21:57 UTC | TC PASS | TC-3.2.2 | by Claude
- Hostile inputs
- evidence: evidence/M3.2/TC-3.2.2.txt

### 2026-10-12 21:57 UTC | TC PASS | TC-3.2.3 | by Claude
- Name normalisation
- evidence: evidence/M3.2/TC-3.2.3.txt

### 2026-10-12 21:57 UTC | DONE | M3.1 | by Claude
- Python project discovery
- test cases passed: 2/2

### 2026-10-12 21:57 UTC | DONE | M3.2 | by Claude
- Python parsers with diagnostics
- test cases passed: 3/3

### 2026-10-12 22:02 UTC | START | M3.3 | by Claude
- Native resolution with provenance

### 2026-10-12 22:02 UTC | TC PASS | TC-3.3.1 | by Claude
- Reproducible world
- evidence: evidence/M3.3/TC-3.3.1.txt
- uv compile twice, same cutoff: identical lock text and world hash

### 2026-10-12 22:02 UTC | TC PASS | TC-3.3.2 | by Claude
- Needs-build is not executed
- evidence: evidence/M3.3/TC-3.3.2.txt
- real uv --no-build; canary probes absent

### 2026-10-12 22:02 UTC | TC PASS | TC-3.3.3 | by Claude
- Custom index
- evidence: evidence/M3.3/TC-3.3.3.txt

### 2026-10-12 22:02 UTC | TC PASS | TC-3.3.4 | by Claude
- Artifact hash mismatch blocks use
- evidence: evidence/M3.3/TC-3.3.4.txt

### 2026-10-12 22:02 UTC | DONE | M3.3 | by Claude
- Native resolution with provenance
- test cases passed: 4/4

### 2026-10-12 22:02 UTC | NOTE | - | by Claude
- M3.3: lockfile (uv.lock/poetry.lock/hash-pinned requirements) is authoritative and a broken lock fails rather than falling back to uv; extra-index/find-links without a lock is refused (dependency-confusion risk); dev/test requirements files are not runtime world; only the runtime closure (markers evaluated for CPython 3.12 linux x86_64) is pinned

### 2026-10-12 22:04 UTC | START | M3.4 | by Claude
- Canonical world and deduplication

### 2026-10-12 22:04 UTC | TC PASS | TC-3.4.1 | by Claude
- Equivalent worlds dedupe
- evidence: evidence/M3.4/TC-3.4.1.txt
- real uv + real fetch: pyproject and requirements projects share one world row

### 2026-10-12 22:04 UTC | TC PASS | TC-3.4.2 | by Claude
- Cache invalidates on any input
- evidence: evidence/M3.4/TC-3.4.2.txt

### 2026-10-12 22:04 UTC | DONE | M3.4 | by Claude
- Canonical world and deduplication
- test cases passed: 2/2

### 2026-10-12 22:15 UTC | START | M3.5 | by Claude
- World inspector

### 2026-10-12 22:15 UTC | TC PASS | TC-3.5.1 | by Claude
- Three views of a version
- evidence: evidence/M3.5/TC-3.5.1.txt
- real pallets/flask 3.0.3 in the UI; found+fixed dev-pins-as-runtime bug

### 2026-10-12 22:15 UTC | TC PASS | TC-3.5.2 | by Claude
- Failed resolution is not an empty world
- evidence: evidence/M3.5/TC-3.5.2.txt

### 2026-10-12 22:15 UTC | DONE | M3.5 | by Claude
- World inspector
- test cases passed: 2/2

### 2026-10-12 22:22 UTC | START | M3.7 | by Claude
- Maven POM inventory (MUST for Gate D)

### 2026-10-12 22:22 UTC | START | M3.6 | by Claude
- npm manifests and lockfile worlds (inventory, MUST for Gate D)

### 2026-10-12 22:22 UTC | TC PASS | TC-3.7.1 | by Claude
- Properties and in-repo parent
- evidence: evidence/M3.7/TC-3.7.1.txt

### 2026-10-12 22:22 UTC | TC PASS | TC-3.7.2 | by Claude
- External parent and BOM
- evidence: evidence/M3.7/TC-3.7.2.txt

### 2026-10-12 22:22 UTC | TC PASS | TC-3.7.3 | by Claude
- Hostile XML
- evidence: evidence/M3.7/TC-3.7.3.txt

### 2026-10-12 22:22 UTC | TC PASS | TC-3.7.4 | by Claude
- No Maven process
- evidence: evidence/M3.7/TC-3.7.4.txt

### 2026-10-12 22:22 UTC | DONE | M3.7 | by Claude
- Maven POM inventory (MUST for Gate D)
- test cases passed: 4/4

### 2026-10-12 22:22 UTC | TC PASS | TC-3.6.1 | by Claude
- Nested versions preserved
- evidence: evidence/M3.6/TC-3.6.1.txt

### 2026-10-12 22:22 UTC | TC PASS | TC-3.6.2 | by Claude
- Workspace importer
- evidence: evidence/M3.6/TC-3.6.2.txt

### 2026-10-12 22:22 UTC | TC PASS | TC-3.6.3 | by Claude
- Unsupported lockfile version
- evidence: evidence/M3.6/TC-3.6.3.txt

### 2026-10-12 22:28 UTC | TC PASS | TC-3.6.4 | by Claude
- Capability honesty
- evidence: evidence/M3.6/TC-3.6.4.txt
- live capability banner + real mocha lockfile worlds; found+fixed 2 real-world defects

### 2026-10-12 22:28 UTC | DONE | M3.6 | by Claude
- npm manifests and lockfile worlds (inventory, MUST for Gate D)
- test cases passed: 4/4

### 2026-10-12 22:28 UTC | NOTE | - | by Claude
- Phase 3 live checks on real repos found real defects, all fixed with regression tests: Flask requirements/*.txt dev pins treated as runtime deps; mocha lockfile root devDependencies and unversioned workspace members; sandbox-unavailable at startup was not retryable. psf/requests@2.32.3 (deps only in setup.py) is reported FAILED(setup_py_not_executed) by design; spring-petclinic Maven versions stay unresolved (external parent).

### 2026-10-12 22:40 UTC | START | M4.1 | by Claude
- Relationship evidence

### 2026-10-12 22:40 UTC | TC PASS | TC-4.1.1 | by Claude
- Positive relationship
- evidence: evidence/M4.1/TC-4.1.1.txt

### 2026-10-12 22:40 UTC | TC PASS | TC-4.1.2 | by Claude
- Name-only match is not actionable
- evidence: evidence/M4.1/TC-4.1.2.txt

### 2026-10-12 22:40 UTC | TC PASS | TC-4.1.3 | by Claude
- Evidence is traceable
- evidence: evidence/M4.1/TC-4.1.3.txt

### 2026-10-12 22:40 UTC | DONE | M4.1 | by Claude
- Relationship evidence
- test cases passed: 3/3
