# REAL1: hand verification (done before any detection code ran)

Claim: **Flask 2.2.2 fails to import when its dependencies are resolved after Werkzeug 3.0.0, and imports fine when they are
resolved before it.** This is a publicly reported break, not a fixture.

## Dates (read from the GitHub releases API on 2026-10-13)

| Release | Published |
|---|---|
| Flask 2.2.2 (`pallets/flask` tag `2.2.2`) | 2022-08-08T23:28:14Z |
| Werkzeug 3.0.0 (`pallets/werkzeug` tag `3.0.0`) | 2023-09-30T14:01:08Z |

## Plain virtual environments, no Faultline code

Two throw-away venvs on the author's machine (CPython 3.12.15). Same command, two resolution dates:

```
uv venv before --python 3.12
uv pip install --python before/Scripts/python.exe "flask==2.2.2" --exclude-newer 2023-09-01T00:00:00Z
uv venv after  --python 3.12
uv pip install --python after/Scripts/python.exe  "flask==2.2.2" --exclude-newer 2023-11-01T00:00:00Z
```

| Environment | Resolved at | Result of `import flask` |
|---|---|---|
| `before` | 2023-09-01 | click 8.1.7, flask 2.2.2, itsdangerous 2.1.2, jinja2 3.1.2, markupsafe 2.1.3, **werkzeug 2.3.7**: `IMPORT OK flask 2.2.2` |
| `after` | 2023-11-01 | click 8.1.7, flask 2.2.2, itsdangerous 2.1.2, jinja2 3.1.2, markupsafe 2.1.3, **werkzeug 3.0.1**: failure below |

Observed error in the `after` environment (verbatim, path shortened):

```
    from werkzeug.urls import url_quote
ImportError: cannot import name 'url_quote' from 'werkzeug.urls' (.../site-packages/werkzeug/urls.py). Did you mean: 'unquote'?
```

Only Werkzeug differs between the two environments (2.3.7 versus 3.0.1). The removed symbol is `werkzeug.urls.url_quote`.

## Public evidence

- Report of this exact failure: https://github.com/pallets/werkzeug/issues/2789 ("werkzeug 3.0.0 Import issue with url_quote", opened 2023-10-02).
- The release that removed it: https://github.com/pallets/werkzeug/releases/tag/3.0.0

## IMPORTANT: why Faultline's own pipeline cannot reproduce THIS case (found when it was run)

The hand verification above let `uv` build MarkupSafe 2.1.3 from source, because that release has no CPython 3.12 wheel (3.12 wheels
start with MarkupSafe 2.1.4, 2024-01). Faultline resolves wheels only and never builds from source, so resolving Flask 2.2.2 as of
2023-09-01 for Python 3.12 fails with `needs_build` (MarkupSafe), which Faultline reports as RESOLUTION_FAILED, not as a break. Any
Flask or Jinja2 world dated before 2024 hits the same wall. TC-12.1.2 therefore does NOT pass for this case and is not claimed.
A different public case must be chosen whose before-world has CPython 3.12 wheels (dates after about October 2023), for example a
numpy 2.0 (2024-06-16) or httpx 0.28 (2024-11-28) removal that breaks an import. The facts above remain true historical facts.

## Expected Faultline outcome (written before running the pipeline; NOT reproduced, see above)

- Artifact: `pallets/flask` pinned at tag `2.2.2`; entry point `flask` (O-import).
- Reference world resolved as of 2023-09-01, consumer world resolved as of 2023-11-01 (both cutoffs stored in provenance).
- Verdict BREAK WITNESSED with signature `ImportError: cannot import name 'url_quote' from 'werkzeug.urls'`.
- Attribution: `werkzeug`, two-sided.
- Relationship level L5 (a user-declared time-machine comparison), shown as declared and never as discovered.

## What this does and does not show

It shows that a break caused only by WHEN a project is resolved is reproduced from public registries and attributed to one package.
It does not show that any particular third-party repository was affected.
