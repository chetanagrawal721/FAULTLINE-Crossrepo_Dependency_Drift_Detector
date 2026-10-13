# ADR 0005: the static API surface is read with the standard-library `ast`, not griffe

Status: accepted, 2026-10-14.

## Context

The master (FR-15, M6.2) names griffe for the static API surface and ApiDelta. The requirement behind the name is a behaviour:
the surface of a package is read without importing it, extraction is cached by package hash and extractor version, and limits
(C extensions, dynamic exports) are flagged instead of hidden.

griffe is a third-party dependency with its own release cadence and a major-version API change in progress. Adding it means a new
pin in `pyproject.toml`, `uv.lock` and `versions.toml`, a new thing the pin check and the CI image must carry, and behaviour we
cannot read in a single sitting.

## Decision

`diff/surface.py` extracts the public surface with `ast`: public functions, classes (constructor signature from `__init__`),
public methods, module constants, `__all__`, and re-exports. It never imports or executes the package (a test plants a canary).
`diff/delta.py` compares two surfaces. The behaviour listed for M6.2 is unchanged.

## Consequences

- No new dependency. The extractor is a few hundred lines we own and test.
- griffe handles more constructs (for example inherited members and stub files). Where this extractor cannot see something it says
  so: `opaque_modules`, `dynamic_exports` and `unparsed_files` are part of every surface and of every delta, and the delta is
  marked incomplete.
- If a later release needs griffe's coverage, it can replace `extract` behind the same `Surface` type.
