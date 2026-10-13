# Scenario J: Data contract: Optional field without a default is required in pydantic v2

Verified: **yes** on 2026-10-12T19:34:19Z (win32, Python 3.12, wheels only).

Reference world pins: pydantic==1.10.13

Consumer world pins: pydantic==2.7.4

## Reference environment (3 runs)

- exit 0: `accepted`
- exit 0: `accepted`
- exit 0: `accepted`

## Consumer environment (3 runs)

- exit 1: `    For further information visit https://errors.pydantic.dev/2.7/v/missing`
- exit 1: `    For further information visit https://errors.pydantic.dev/2.7/v/missing`
- exit 1: `    For further information visit https://errors.pydantic.dev/2.7/v/missing`

Full package lists are in results.json. Re-run: `python scripts/verify_fixture_facts.py`.
