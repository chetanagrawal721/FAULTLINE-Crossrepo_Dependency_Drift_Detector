# Scenario E: Silent divergence: Union[int, str] parses '42' as int in v1 and keeps str in v2

Verified: **yes** on 2026-10-12T19:34:19Z (win32, Python 3.12, wheels only).

Reference world pins: pydantic==1.10.13

Consumer world pins: pydantic==2.7.4

## Reference environment (3 runs)

- exit 0: `int 42`
- exit 0: `int 42`
- exit 0: `int 42`

## Consumer environment (3 runs)

- exit 0: `str '42'`
- exit 0: `str '42'`
- exit 0: `str '42'`

Full package lists are in results.json. Re-run: `python scripts/verify_fixture_facts.py`.
