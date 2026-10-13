# ADR 0002: Generic `job` table (PROPOSED CHANGE PC-12)

Status: accepted (2026-10-13).

The master schema has `analysis.status` and `oracle_job` but no generic orchestration job. Plan v3.1 Phase 0.3
requires status, idempotency key, attempts, lease owner and expiry, heartbeat and cancellation. These are stored in
`job` (and `job_attempt`, one row per execution attempt) in migration 0002.

- Claim is atomic: `BEGIN IMMEDIATE`, select a QUEUED job or a RUNNING job whose lease expired, update it, insert the attempt.
- A trigger makes terminal states final and forbids QUEUED to DONE or FAILED, so the transition table is enforced in the database as well as in Python.
- `oracle_job` and `oracle_run` stay as the master defines them; they record oracle executions, not orchestration.
- Heartbeat tuning, backpressure and cache-stampede tests are deferred (amendment A-6).
