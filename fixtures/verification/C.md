# Scenario C: Signature changed: urllib3 2.x removed Retry(method_whitelist=...)

Verified: **yes** on 2026-10-12T19:34:19Z (win32, Python 3.12, wheels only).

Reference world pins: urllib3==1.26.18

Consumer world pins: urllib3==2.0.7

## Reference environment (3 runs)

- exit 0: `ok`
- exit 0: `ok`
- exit 0: `ok`

## Consumer environment (3 runs)

- exit 1: `TypeError: Retry.__init__() got an unexpected keyword argument 'method_whitelist'`
- exit 1: `TypeError: Retry.__init__() got an unexpected keyword argument 'method_whitelist'`
- exit 1: `TypeError: Retry.__init__() got an unexpected keyword argument 'method_whitelist'`

Full package lists are in results.json. Re-run: `python scripts/verify_fixture_facts.py`.
