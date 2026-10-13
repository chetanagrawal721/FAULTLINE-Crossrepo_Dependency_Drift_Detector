# Faultline: Understanding Guide

**Purpose of this document:** to help you understand (1) the problem we are solving, (2) every important idea behind it, and (3) exactly how our current solution works and where it lives in the code. Read it top to bottom once; later use it as a reference.

Project: HACKTOPIA 2026, problem statement **PS07 – Cross-Repo Dependency Drift Detector**.
Tagline: **"Witnesses, not warnings."**

---

## Part 1. The problem

### 1.1 Vocabulary you need first

| Word | Plain meaning | Example |
|---|---|---|
| **Repository (repo)** | A folder of code stored on GitHub | `notify-svc` |
| **Package / library** | Code written by someone else that your code uses | `flask`, `pydantic` |
| **Dependency** | A package your project needs in order to run | notify-svc depends on `flask` |
| **Version** | The release number of a package | `flask 2.2.2` |
| **Transitive dependency** | A package your package needs (you never asked for it directly) | `flask` needs `werkzeug` |
| **Lock file** | A file that freezes exact versions so installs repeat | `uv.lock`, `package-lock.json` |
| **Shared artifact** | A library written inside the company and used by several repos | `acme-models` |
| **Producer / consumer** | Producer = repo that publishes the shared code. Consumer = repo that uses it | producer: acme-models, consumer: notify-svc |
| **World** | The exact list of package versions one repo really runs with | `{flask 2.2.2, werkzeug 3.0.2, ...}` |

### 1.2 What goes wrong

A shared library is written and tested in **its own world**. Each consumer repo has **a different world**, because each team upgrades packages at different times.

```
Producer's world:   flask 2.2.2 + werkzeug 2.2.3     -> library works
Consumer A's world: flask 2.2.2 + werkzeug 2.2.3     -> same, works
Consumer B's world: flask 2.2.2 + werkzeug 3.0.2     -> library CRASHES
```

Nothing in the shared library changed. Nobody made a mistake in a single repo. The problem only exists **between** repos. That is **dependency drift**.

Real example we reproduced: Flask 2.2.2 imports `url_quote` from `werkzeug.urls`. Werkzeug 3 removed it. So any repo that pins Flask 2.2.2 but lets Werkzeug float to 3.x crashes with
`ImportError: cannot import name 'url_quote' from 'werkzeug.urls'`.

### 1.3 Why it is hard

1. The break only shows up **inside one specific combination** of versions.
2. The people who own the consumer repo may not know the library changed or how they resolve.
3. Looking at one repo at a time (what most tools do) cannot see it.
4. Many "differences" are harmless. Reporting all of them creates noise, and people ignore noisy tools.

### 1.4 What exactly PS07 asks

Detect, **across repositories**, where dependency differences will affect a shared artifact, and report it in a way a developer can trust. That means: read several repos, understand their dependency worlds, relate them, and say where drift matters.

---

## Part 2. Why current tools fall short (the gap)

| Existing approach | Good at | Gap |
|---|---|---|
| Dependabot / Renovate | Suggesting upgrades inside one repo | Do not test whether shared code still works in another repo |
| `pip check`, `npm ls` | Finding conflicts in one install | One repo, no cross-repo view |
| Vulnerability scanners | Known security problems | Not about compatibility |
| Plain version comparison | Spotting that versions differ | Differences are not proof of breakage: huge noise |

**The gap:** nobody gives *evidence* that "shared code X fails in consumer Y's real dependency world." Everyone gives *warnings*. Faultline gives *witnesses*.

---

## Part 3. Our solution: the core idea

### 3.1 Witness vs warning
- **Warning:** "This might break." (opinion)
- **Witness:** "We ran it and it broke, three times, the same way, and here is how to repeat it." (evidence)

### 3.2 The 3 + 3 rule (the heart of the system)
An observation becomes a **witness** only if all are true:
1. In the **reference world** (the library's own versions) the check **passes 3 out of 3** times.
2. In the **consumer world** the same check **fails 3 out of 3** times.
3. The three consumer failures have the **same normalised error signature** (same exception type, same message after removing paths).
4. All six runs are **fresh executions** (a result remembered from cache never counts).
5. The failure is classified as a real **artifact failure**, not a problem in our own tools (sandbox crash, timeout, network, harness bug).

If any condition fails the result is *not* a witness; we report **INCONCLUSIVE** or **NO DIVERGENCE OBSERVED** with the reason.

### 3.3 What we deliberately never say
We never say "compatible", "safe", "proof of no bug" or "detected by AI". We can only **demonstrate failures**, not prove absence of failures.

---

## Part 4. How the system works (pipeline)

```
 URLs --> PIN --> FETCH --> READ --> RESOLVE --> RELATE
                                                   |
 REPORT <-- VERDICT <-- WITNESS <-- RUN <-- BUILD WORLDS <-- CELLS
```

| Step | What happens | Where in code |
|---|---|---|
| **Pin** | Turn a branch/tag into one exact 40-character commit SHA | `backend/faultline/ingestion/` (`urls.py`, `github.py`) |
| **Fetch** | Download that commit inside the sandbox; refuse symlinks, `..` paths, hooks; store as a read-only hashed snapshot | `ingestion/clone.py`, `oracles/harness/fetch_repo.py` |
| **Read** | Parse manifests as text, never run them (Python, npm, Maven) | `backend/faultline/parsers/` |
| **Resolve** | Prefer the lock file; otherwise ask the pinned `uv` tool with a date cutoff; wheels only; record provenance | `backend/faultline/resolvers/` |
| **Relate** | Link two repos only with evidence (file path + line); weak matches go to a suspected tray | `backend/faultline/relationships/` |
| **Cells** | One cell per unique world difference; list the exact package deltas | `backend/faultline/worlds/` (`reference.py`, `projection.py`, `cells.py`) |
| **Build worlds** | Install the exact wheels, with hashes, into a volume with **no network** | `worlds/builder.py` |
| **Run** | Oracles (import check, test run) execute in the sandbox, 3 times per side | `oracles/` |
| **Witness / Verdict** | Apply the 3+3 rule, then an ordered decision table | `witnesses/`, `verdicts/` |
| **Report** | API + web UI + downloadable evidence bundle | `api/`, `frontend/`, `witnesses/bundle.py` |

### 4.1 Pin and fetch
Branch names move. A SHA does not. So every claim points to a SHA and can be re-checked next month. Fetch happens in a **fetch zone** container (internet allowed), while code **execution** happens in an **exec zone** container (no internet).

### 4.2 Reading projects safely
We treat repositories as hostile. We parse `requirements.txt`, `pyproject.toml`, `uv.lock`, `poetry.lock`, `package.json`, `package-lock.json` and `pom.xml` **as data**. XML uses a hardened parser (no DTDs, no external entities). `setup.py` is **never executed**.

### 4.3 Resolving worlds
- Lock file present → it is authoritative.
- Otherwise `uv pip compile` at a recorded time cutoff, wheels only (`--no-build`).
- If a package would need building from source → we say `needs_build`; we do not build it.
- If a private index is involved and there is no lock → we refuse to guess.
- npm: every package **instance** is kept by its `node_modules` path; visibility is computed per importer.
- Maven: inventory only (coordinates + declared dependencies); versions we cannot know stay "unresolved".

### 4.4 Relationships
A cross-repo link needs evidence, for example *"repo B's `requirements.txt` line 12 declares `acme-models` and repo A's `pyproject.toml` line 2 names `acme-models`."* A class with the same name in two repos is only a **suspected twin** and never creates a finding.

### 4.5 Worlds, projection and cells
- **Reference world** = the library's own resolved world.
- **Projection** = the consumer's world compared with the reference.
- **Cell** = one unique projection. Two consumers with identical worlds share a cell.
- If the projection equals the reference: **NO_DRIFT**, nothing to run.
- If a consumer's world cannot be built, it stays counted as *discovered but not analysed*, with a reason. We report counts, never a "compatibility score".

### 4.6 Oracles (the experiments)
- **O-import:** import the library's top-level package and the modules the consumer really uses.
- **O-tests:** run the library's own tests (with test-only packages overlaid).
- If the top-level import already fails, later checks are marked *blocked by import* so one cause is not reported many times.
- A missing optional package (for example Flask not installed) makes that module **NOT_APPLICABLE**, not a failure.

### 4.7 Verdict table (ordered, deterministic)

| # | Condition | Verdict |
|---|---|---|
| 0 | Relationship weaker than L2 | HYGIENE |
| 1 | Consumer world equals reference | NO_DRIFT |
| 2 | Consumer uses no affected module | NOT_APPLICABLE |
| 3 | A 3+3 break witness exists | **BREAK WITNESSED** |
| 4 | A silent-divergence witness exists | SILENT DIVERGENCE WITNESSED |
| 5 | Exposures all exercised and matched | NO DIVERGENCE OBSERVED |
| 6 | Exposed but not fully exercised | EXPOSED |
| 7 | Breaking API change + unresolved dynamic use | POTENTIAL |
| 8 | API compared, enough coverage, no exposure | NOT EXPOSED |
| 9 | Anything else | INCONCLUSIVE (with reasons) |

No AI is used anywhere in this decision. The same evidence always produces the same verdict.

### 4.7.1 Why there are so many "honest" outcomes
Because most real situations are *not* clear breaks. Saying INCONCLUSIVE with a reason is more useful than a confident guess.

---

## Part 5. Security design (why the sandbox matters)

Running other people's code is dangerous. Rules we enforce:
- Only one component (`sandboxd`) can talk to Docker; everything else asks it.
- Containers run as a non-root user, all Linux capabilities dropped, read-only filesystem, memory/CPU/time limits, **no network in the exec zone**.
- Only approved images (checked by digest) can run.
- Secrets are scrubbed from outputs and bundles.
- If the sandbox cannot be verified, execution is **disabled** instead of bypassed.

Known limit: Docker Desktop shares the host kernel; it is not as strong as gVisor.

---

## Part 6. Evidence bundle

Every witness can be exported as a zip containing: the witness, the six runs, the two worlds (with lock files and hashes), the artifact source, the environment profile, and a manifest with a hash for every file. A separate verifier re-checks the hashes and the 3+3 facts, so a third party can confirm the result without trusting us.

---

## Part 7. What is finished and what is not

Finished (28 of 63 milestones in our tracker):
- Foundation, sandbox, oracles, witness engine, evidence bundle, fixture proof.
- Real GitHub ingestion, Python/npm/Maven reading, world resolution and inspector.
- Relationship discovery, projection, cells and funnel counts.

In progress / next:
- Live end-to-end oracle run on real ingested repos and final verdict tests.
- Call-site checking, full dashboard, root-cause attribution (smallest causing package set), replay of bundles, real-world historical case, demo mode, benchmark, submission pack.

Tracking files: `LOGBOOK.md` (what happened, when) and `CHECKLIST.md` (what is done/not). Plan: `docs/FAULTLINE_PLAYBOOK.md`.

---

## Part 8. Honest limitations

- Python verification is the deepest; npm and Maven are inventory only.
- Docker Desktop isolation, not gVisor.
- A witness proves a failure; it never proves safety.
- Resolution depends on lock files or on the resolver's date cutoff.
- Our benchmark numbers (when published) will come from scripts with denominators, never invented.

---

## Part 9. Quick self-test (can you answer these?)

1. What is the difference between a warning and a witness?
2. Why must the reference world pass 3 out of 3 times?
3. Why do we pin a SHA instead of a branch name?
4. Why is a same-named class in two repos not enough to link them?
5. Why is a failed world counted as "discovered, not analysed"?
6. Why do we refuse to say "compatible"?

If you can answer these, you understand Faultline.
