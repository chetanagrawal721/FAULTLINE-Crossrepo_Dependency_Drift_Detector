# Scenario B: API removed: pydantic.BaseSettings moved out of pydantic in v2

Verified: **yes** on 2026-10-12T19:34:19Z (win32, Python 3.12, wheels only).

Reference world pins: pydantic==1.10.13

Consumer world pins: pydantic==2.7.4

## Reference environment (3 runs)

- exit 0: `ok`
- exit 0: `ok`
- exit 0: `ok`

## Consumer environment (3 runs)

- exit 1: `For further information visit https://errors.pydantic.dev/2.7/u/import-error`
- exit 1: `For further information visit https://errors.pydantic.dev/2.7/u/import-error`
- exit 1: `For further information visit https://errors.pydantic.dev/2.7/u/import-error`

Full package lists are in results.json. Re-run: `python scripts/verify_fixture_facts.py`.
