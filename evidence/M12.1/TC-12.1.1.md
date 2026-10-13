# REAL2: hand verification (done before the pipeline was run on this case)

Claim: **requests-toolbelt 0.10.1 fails to import when its dependencies are resolved after urllib3 2.0 reached requests, and imports
fine when they are resolved before.** This is a publicly reported break, not a fixture. Every package involved is a pure-Python
wheel, so the case is reproducible by a wheels-only resolver on CPython 3.12 (REAL1 was not, see REAL1.md).

## Dates (read from the GitHub API on 2026-10-13)

| Item | Date |
|---|---|
| requests-toolbelt tag `0.10.1` (commit `9e5ef799346379a6d77f0bc6626bd54d5cdc03a7`) | 2022-10-25 |
| urllib3 2.0.0 released (`urllib3/urllib3` tag `2.0.0`) | 2023-04-26T17:20:25Z |
| requests 2.30.0 released (first requests that allows urllib3 2) | 2023-05-04T14:39:22Z |
| requests-toolbelt 1.0.0 (the fix) | 2023-05-01 |

## Plain virtual environments, no Faultline code

Two throw-away venvs (CPython 3.12), wheels only, the same command at two resolution dates, with the 0.10.1 source tree on `PYTHONPATH`:

```
uv venv before --python 3.12
uv pip install --python before/Scripts/python.exe "requests>=2.0.1,<3.0.0" --only-binary :all: --exclude-newer 2023-04-15T00:00:00Z
uv venv after  --python 3.12
uv pip install --python after/Scripts/python.exe  "requests>=2.0.1,<3.0.0" --only-binary :all: --exclude-newer 2023-05-20T00:00:00Z
```

| Environment | Resolved at | Installed | `import requests_toolbelt` |
|---|---|---|---|
| `before` | 2023-04-15 | certifi 2022.12.7, charset-normalizer 3.1.0, idna 3.4, requests 2.28.2, **urllib3 1.26.15** | `IMPORT OK 0.10.1` |
| `after` | 2023-05-20 | certifi 2023.5.7, charset-normalizer 3.1.0, idna 3.4, requests 2.30.0, **urllib3 2.0.2** | failure below |

Observed error in the `after` environment (verbatim, path shortened):

```
  File ".../requests_toolbelt/_compat.py", line 50, in <module>
    from urllib3.contrib import appengine as gaecontrib
ImportError: cannot import name 'appengine' from 'urllib3.contrib' (.../site-packages/urllib3/contrib/__init__.py)
```

Three packages differ (certifi, requests, urllib3). The removed module is `urllib3.contrib.appengine`, which only urllib3 owns.

## Public evidence

- https://github.com/requests/toolbelt/issues/354 ("Urllib3 Removed AppEngine Support in v2.0.0", opened 2023-04-27).
- https://github.com/requests/toolbelt/issues/361 (opened 2023-05-02, the same import failure).

## Expected Faultline outcome (written before running the pipeline)

- Artifact: `requests/toolbelt` pinned at tag `0.10.1`; entry point `requests_toolbelt` (O-import).
- Reference world resolved as of 2023-04-15, consumer world as of 2023-05-20 (both cutoffs stored in provenance).
- Verdict BREAK WITNESSED with signature `ImportError: cannot import name 'appengine' from 'urllib3.contrib'`.
- Attribution names `urllib3` (two-sided), though three packages differ.
- Relationship level L5 (a user-declared time-machine comparison), shown as declared and never as discovered.

## What this does and does not show

It shows that a break caused only by WHEN a project is resolved is reproduced from public registries and attributed to one package.
It does not show that any particular third-party repository was affected.
