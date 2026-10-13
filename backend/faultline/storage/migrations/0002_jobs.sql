-- 0002_jobs: durable job contract (plan v3.1, Phase 0.3).
-- PROPOSED CHANGE PC-12 (docs/adr/0002-generic-job-table.md): the master schema has analysis.status and
-- oracle_job but no generic orchestration job. The plan requires leases, heartbeats, cancellation and
-- idempotency, so stages run as rows of this table.

CREATE TABLE job (
  job_id TEXT PRIMARY KEY,                               -- 'job_...'
  kind TEXT NOT NULL,
  analysis_id TEXT REFERENCES analysis(id),
  idempotency_key TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED','CANCELLED')),
  priority INTEGER NOT NULL DEFAULT 100,
  payload_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT,
  error_json TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  progress REAL NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 1),
  message TEXT,
  lease_owner TEXT,
  lease_expires_at REAL,                                 -- unix seconds
  heartbeat_at REAL,
  cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0,1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_job_claim ON job(status, priority, created_at);

CREATE TABLE job_attempt (
  attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES job(job_id),
  attempt INTEGER NOT NULL,
  worker TEXT NOT NULL,
  started_at REAL NOT NULL,
  finished_at REAL,
  outcome TEXT,                                          -- DONE | FAILED | RETRY | CANCELLED | LEASE_LOST
  UNIQUE (job_id, attempt)
);

-- Terminal states are final, and a queued job cannot jump straight to DONE or FAILED.
CREATE TRIGGER trg_job_final_states
BEFORE UPDATE OF status ON job
WHEN (OLD.status IN ('DONE','FAILED','CANCELLED') AND NEW.status <> OLD.status)
  OR (OLD.status = 'QUEUED' AND NEW.status IN ('DONE','FAILED'))
BEGIN
  SELECT RAISE(ABORT, 'invalid_transition');
END;
