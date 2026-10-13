# ADR 0006: scenarios J and E use their own small artifact (acme-contracts), not acme-models

Status: accepted, 2026-10-14.

## Context

The master (scenario table) puts the data-contract models for scenarios J and E in `acme-models`: `CustomerRequest.middle_name:
Optional[str]` with no default, and `Ref.value: Union[int, str]`. `acme-models` is the shared artifact of scenarios A, B, D, G, H and L.
Its `CustomerRequest` already exists with different fields (`customer_id`, `email`, `loyalty_points`), the O-tests of those scenarios
exercise it, and its reference world is pinned in `requirements.lock.txt`. Changing the model would change what six labelled scenarios
measure, after their labels and results were committed.

## Decision

Scenarios J and E get a separate artifact, `fixtures/repos/acme-contracts` (import package `acme_contracts`: `customer.py` with
`CustomerRequest` and a negative-control `LoyaltyNote`, `ids.py` with `Ref`, and `fixtures/ref_example.json` as the T1 sample), and two
consumers `fixtures/repos/billing-svc/J` and `.../E` that resolve pydantic 2.7.4. The reference world is pydantic 1.10.13. The behaviour
the master specifies is unchanged: both worlds import the models; the payload the pydantic 1 world sends (`exclude_none`) is rejected by
pydantic 2 (J); the text `"42"` is read as an integer in the reference world and kept as text in the consumer world (E).

## Consequences

- The other scenarios are byte-for-byte unchanged (`scripts/make_fixtures.py --only-contracts` writes only the new files).
- A reader looking for `acme-models/ids.py` will not find it; this ADR is the pointer.
- Scenarios J and E each need their own GitHub repository when the fixtures are published (`scripts/push_fixtures.py`).
