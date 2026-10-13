# Scenario H: Harmless drift: pydantic .dict() still works in v2 (deprecated, warns)

Verified: **yes** on 2026-10-12T19:34:19Z (win32, Python 3.12, wheels only).

Reference world pins: pydantic==1.10.13

Consumer world pins: pydantic==2.7.4

## Reference environment (3 runs)

- exit 0: `{'a': 1}`
- exit 0: `{'a': 1}`
- exit 0: `{'a': 1}`

## Consumer environment (3 runs)

- exit 0: `{'a': 1}`
- exit 0: `{'a': 1}`
- exit 0: `{'a': 1}`

Full package lists are in results.json. Re-run: `python scripts/verify_fixture_facts.py`.
