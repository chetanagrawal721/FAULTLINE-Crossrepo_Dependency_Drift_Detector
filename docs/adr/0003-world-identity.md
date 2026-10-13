# ADR 0003: What goes into a world hash

Status: accepted (2026-10-13). Implemented only in `core/hashing.py`.

Included: ecosystem; runtime name and version; environment profile id (image, OS, arch, locale, timezone, allow-listed
environment, seed); for every entry the locator, name, version, scope, source kind, source reference and artifact hash.

Excluded: absolute paths, timestamps, resolver provenance, venv location, and the `parents` reason edges.

Plan v3.1 section 3.4 says identity includes "relevant dependency edges". This implementation reads "relevant" as the
edges that change what an importer can see. For npm those are encoded by the locator (`node_modules/a/node_modules/x`),
so nested instances stay distinct. The `parents` edges explain why a package is present and do not change execution,
so two resolutions that install the same packages share one world. Revisit if a case shows otherwise.
