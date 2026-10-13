# Scenario C: expected Faultline outcome, with a second plain-environment check (urllib3 1.26.20 and 2.2.3), written before O-bind ran

Claim: **`urllib3.util.retry.Retry(total=3, method_whitelist=["GET"])` works on urllib3 1.26.x and raises `TypeError` on urllib3 2.x, while
`import urllib3.util.retry` succeeds on both.** An import-only check cannot see this change; a call-shape check can.

## Plain virtual environments, no Faultline code (CPython 3.12, 2026-10-13)

```
uv venv v1 --python 3.12 ; uv pip install --python v1/... "urllib3==1.26.20"
uv venv v2 --python 3.12 ; uv pip install --python v2/... "urllib3==2.2.3"
```

| urllib3 | `method_whitelist` in `inspect.signature(Retry)` | `Retry(total=3, method_whitelist=["GET"])` | `Retry(total=3, allowed_methods=["GET"])` |
|---|---|---|---|
| 1.26.20 (2024-08-29) | yes | OK, with `DeprecationWarning: Using 'method_whitelist' with Retry is deprecated and will be removed in v2.0` | OK |
| 2.2.3 | no | `TypeError: Retry.__init__() got an unexpected keyword argument 'method_whitelist'` | OK |

The release that removed it: urllib3 2.0.0 (2023-04-26). The warning in 1.26.x announces the removal.

## What Faultline is expected to report (written before the pipeline ran)

- Artifact `acme-http` (a fixture, `fixtures/repos/acme-http`), reference world urllib3 1.26.20, consumer `orders-svc` (scenario C) with urllib3 2.2.3.
- O-import passes in both worlds (the removed keyword is used inside a function, not at import time).
- O-bind: the call site `Retry(total=3, method_whitelist=["GET"])` binds in the reference world and fails to bind in the consumer world, 3 of 3 fresh runs each:
  verdict BREAK WITNESSED with signature `TypeError: ... got an unexpected keyword argument 'method_whitelist'`.
- The call site `Retry(total=2, backoff_factor=0.1)` binds in both worlds (a call that still binds is not reported).
- Attribution: `urllib3`.

## Limits

Binding is checked with `inspect.signature(...).bind(...)` on placeholder values of the extracted shape. Faultline does not execute the call.
