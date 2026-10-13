# Scenario D: Transitive world drift: Flask 2.2.2 imports werkzeug.urls.url_quote, removed in Werkzeug 3

Verified: **yes** on 2026-10-12T19:34:19Z (win32, Python 3.12, wheels only).

Reference world pins: flask==2.2.2, werkzeug==2.2.3

Consumer world pins: flask==2.2.2, werkzeug==3.0.6

## Reference environment (3 runs)

- exit 0: `ok 2.2.2`
- exit 0: `ok 2.2.2`
- exit 0: `ok 2.2.2`

## Consumer environment (3 runs)

- exit 1: `ImportError: cannot import name 'url_quote' from 'werkzeug.urls' (C:\Users\Chetan\AppData\Local\Temp\fl-verify-gy8glla1\D-test\Lib\site-packages\werkzeug\urls.py). Did you mean: 'unquote'?`
- exit 1: `ImportError: cannot import name 'url_quote' from 'werkzeug.urls' (C:\Users\Chetan\AppData\Local\Temp\fl-verify-gy8glla1\D-test\Lib\site-packages\werkzeug\urls.py). Did you mean: 'unquote'?`
- exit 1: `ImportError: cannot import name 'url_quote' from 'werkzeug.urls' (C:\Users\Chetan\AppData\Local\Temp\fl-verify-gy8glla1\D-test\Lib\site-packages\werkzeug\urls.py). Did you mean: 'unquote'?`

Full package lists are in results.json. Re-run: `python scripts/verify_fixture_facts.py`.
