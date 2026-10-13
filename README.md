# Faultline

**Witnesses, not warnings.** Cross-repo dependency drift verification for HACKTOPIA 2026 (PS07).

Faultline finds the dependency worlds your consumer repositories actually resolve, checks a shared artifact in each
one, and backs every failure it reports with a reproducible witness narrowed to the package change responsible.

> Status: Phase 0 (runnable skeleton). The API, worker, schema, job contract and capability banner exist.
> Nothing is analysed yet, and the sandbox is a stub, so Faultline makes no compatibility claims.

## Quick start

```bash
python -m pip install uv==0.13.0
uv sync --frozen                    # Python 3.12 environment from uv.lock
npm ci --prefix frontend            # UI dependencies
python tools/fl.py up               # API + worker + UI at http://127.0.0.1:8000
```

`make <target>` forwards to `python tools/fl.py <target>`; use whichever your machine has.

| Command | Purpose |
|---|---|
| `python tools/fl.py ci` | Everything CI runs: lint, pins, tests, API/type drift, UI build, boot check |
| `python tools/fl.py test` | Unit and integration tests |
| `python tools/fl.py up --check` | Boot, probe health and the UI, then stop |
| `python tools/fl.py gen-types` | Regenerate `frontend/openapi.json` and the TypeScript types |

## How the project is built

- Specification: `docs/FAULTLINE_MASTER.md`. Build plan: `docs/FAULTLINE_PLAYBOOK.md`.
- Progress: `CHECKLIST.md` (generated) and `LOGBOOK.md` (append-only), both driven by `python tools/track.py`.
- Decisions: `docs/adr/`.
- Working rules for contributors and AI assistants: `CLAUDE.md`.
