# Faultline

**Witnesses, not warnings.** Cross-repo dependency drift verification for HACKTOPIA 2026 (PS07).

Faultline finds the dependency worlds your consumer repositories actually resolve, checks a shared artifact in each
one, and backs every failure it reports with a reproducible witness narrowed to the package change responsible.

A **witness** is a failure that reproduces: the artifact passes 3 of 3 fresh runs in its own dependency world and fails 3 of 3
fresh runs, with the same normalised signature, in a consumer's world. Faultline never says "compatible"; when it cannot
show a failure it says what it exercised and what it did not check.

## What works today

- Paste public GitHub URLs: refs are pinned to commit SHAs and fetched inside a sandbox into immutable, hashed snapshots.
- Python (requirements, pyproject, uv.lock, poetry.lock), npm (package-lock v2/v3, per-importer visibility) and Maven (POM inventory)
  are read as data; Python worlds come from lockfiles or the pinned `uv`, installed offline in the sandbox.
- Relationships need evidence on both sides (file and line); look-alikes go to a suspected tray and never become findings.
- Cells deduplicate by projection onto the artifact's runtime closure; the oracle runs 3 + 3 fresh times; an ordered, deterministic
  verdict table decides; breaks are attributed two-sided (ddmin) and exported as an evidence bundle that can be replayed.
- The workspace (a React interface, `frontend/`) shows the funnel, world matrix, six-run witness board, why-path, findings, suspected tray, inventory graph, evidence bundle, jobs and capabilities from persisted records, and starts analyses. Routes are `#/` (product site) and `#/app/<view>` (workspace).

See `docs/FAULTLINE_UNDERSTANDING_GUIDE.md` for the problem and the design in plain language.

## Quick start

```bash
python -m pip install uv==0.13.0
uv sync --frozen                    # Python 3.12 environment from uv.lock
npm ci --prefix frontend            # UI dependencies
python scripts/build_images.py      # build the sandbox image (needs Docker)
python tools/fl.py up               # API + worker + sandbox + UI at http://127.0.0.1:8000
```

`make <target>` forwards to `python tools/fl.py <target>`; use whichever your machine has.

| Command | Purpose |
|---|---|
| `python tools/fl.py ci` | Everything CI runs: lint, pins, tests, API/type drift, UI build, boot check |
| `python tools/fl.py test` | Unit and integration tests |
| `python scripts/run_fixtures.py --assert` | Every fixture scenario through the live pipeline against its expected verdict |
| `python scripts/conformance_report.py` | Traceability of every canonical MUST to a passing test and a retained artifact |
| `python -m faultline.witnesses.replay bundle.zip` | Replay a witness from its evidence bundle |
| `python tools/fl.py gen-types` | Regenerate `frontend/openapi.json` and the TypeScript types |

## How the project is built

- Specification: `docs/FAULTLINE_MASTER.md`. Build plan: `docs/FAULTLINE_PLAYBOOK.md`.
- Progress: `CHECKLIST.md` (generated) and `LOGBOOK.md` (append-only), both driven by `python tools/track.py`.
- Decisions: `docs/adr/`.

## Honest limits

- The sandbox is Docker Desktop (shared kernel), not gVisor. The fetch zone can reach only GitHub and PyPI over HTTPS, through an allowlisting proxy.
- Python is verified end to end. npm and Maven are inventory only.
- O-bind checks that call shapes found in the artifact still bind to the current signatures (scenario C). It does not execute the calls, and call
  sites with star arguments, dynamic targets or instance methods are not checked.
- Scenarios E and J (data contracts) are reproduced by contract replay (`tests/integration/test_o_contract.py`) but are not in the benchmark denominator; F and I need static analysis in the live pipeline, which is a script and library only (`scripts/static_exposure.py`).
- Numbers come from scripts, against committed labels, on a small fixture set: they are not an estimate of real-world accuracy.
