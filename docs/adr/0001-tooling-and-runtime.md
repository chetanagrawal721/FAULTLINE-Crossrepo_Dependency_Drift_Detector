# ADR 0001: Tooling and runtime choices for Phase 0

Status: accepted (2026-10-13). Context: plan v3.1 Phase 0.1 and the machine the team develops on.

| Decision | Reason |
|---|---|
| Python 3.12.15 for the control plane, managed by `uv` | The plan pins 3.12. This machine had only 3.13 and 3.14, so `uv python install 3.12` supplies it. |
| `tools/fl.py` is the task runner; the Makefile only forwards to it | `make` is not installed on the Windows development machines. One implementation keeps Linux (the demo VM) and Windows identical. |
| TypeScript 5.9.3, not 7.x | `openapi-typescript` 7.13.0 declares a peer dependency on TypeScript ^5. Revisit when it supports 7. |
| `httpx2` 2.13.0 as the API test client | Starlette's TestClient warns that `httpx` is deprecated in favour of `httpx2`. |
| `docker/compose.yml` is deferred to M1.2 | There are no images yet. A compose file with unpinned images would violate the pin check. `up` runs the API and worker as local processes. |
| System fonts only in the UI | The demo must work with the network unplugged. |
