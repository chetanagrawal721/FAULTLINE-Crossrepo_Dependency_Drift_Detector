# ADR 0007: differences between the master's frozen-contract excerpt and the code

Status: accepted, 2026-10-14.

## Context

M11.1 requires that enums and verdict names in the code are identical to the master, or that an ADR documents the approved difference.
`tests/unit/test_master_consistency.py` reads the master as text and compares: Scope, Ecosystem, FailureClass, SourceKind, WorldKind,
the eight verdict words, the two cell states of section 7.1, and the witness classes. All of them are identical.

## The one difference

The excerpt in section 63.2 lists two oracle names for contract replay, `o_contract_producer` and `o_contract_consumer`, one per sandbox
job. The code uses one oracle name, `o_contract`. Contract replay is verified as one oracle: its 3 + 3 runs each parse the stored bytes
in a world, and the producer step that makes the bytes is an exploration run before verification. Two names would make one witness
refer to two oracle ids in the database and in the bundle.

## Decision

The oracle name stored in `oracle_job`, `witness` and the bundle is `o_contract`. The two sandbox scripts keep the master's roles
(`contract_producer.py`, `contract_consumer.py`). No verdict word, failure class or witness class differs.

## Consequences

- A reader comparing the master's `OracleJob.oracle` literal with the code will find `o_contract` in place of the pair; this ADR is the pointer.
- The consistency test fails if any other enum or verdict word drifts from the master, or if this difference changes.
