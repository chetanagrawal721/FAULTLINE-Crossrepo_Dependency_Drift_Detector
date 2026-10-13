# ADR 0004: scenario C uses its own small artifact (acme-http), not acme-models

Status: accepted, 2026-10-13.

## Context

The master (section on scenarios) describes scenario C as a module `http.py` inside `acme-models` that calls
`Retry(method_whitelist=...)`, with the reference world on urllib3 1.26.x and `orders-svc` on urllib3 2.x.

`acme-models` is the single shared artifact of scenarios A, B, D, G, H and L. Every one of them resolves the same reference world from
`fixtures/repos/acme-models/requirements.lock.txt`. Adding `urllib3` to that reference world (which scenario C needs, so that the
reference and consumer worlds differ in urllib3) changes the set of packages in the reference world of all those scenarios. Their
expected deltas would then include urllib3, and the attribution and ablation numbers that were committed with their labels would
no longer describe the same experiment.

## Decision

Scenario C gets a separate artifact, `fixtures/repos/acme-http` (import package `acme_http`, one module `retry.py` with the calls
described in the master), and its own consumer `fixtures/repos/orders-svc/C`. The behaviour the master specifies is unchanged: the
import succeeds in both worlds, the call `Retry(total=3, method_whitelist=["GET"])` does not bind on urllib3 2.x, and only O-bind sees it.

## Consequences

- The other scenarios are byte-for-byte unchanged (`scripts/make_fixtures.py` regenerates them identically; `--only-c` writes only C).
- A fixture reader looking for `acme-models/http.py` will not find it. This ADR is the pointer.
- Scenario C needs its own GitHub repository when the fixtures are published (`scripts/push_fixtures.py`).
