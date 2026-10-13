-- 0003_ingestion: what Phase 2 needs to record about a repository and its snapshot inventory.
-- The requested ref and the pinned SHA are kept separately; every later step uses the SHA.
ALTER TABLE repository ADD COLUMN pinned_sha TEXT CHECK (pinned_sha IS NULL OR length(pinned_sha) = 40);
ALTER TABLE repository ADD COLUMN committed_at TEXT;
ALTER TABLE repository ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','INGESTING','INGESTED','FAILED'));
ALTER TABLE repository ADD COLUMN error_json TEXT;
ALTER TABLE repository ADD COLUMN created_at TEXT;
ALTER TABLE snapshot_file ADD COLUMN kind TEXT NOT NULL DEFAULT 'file';
ALTER TABLE snapshot_file ADD COLUMN size INTEGER;
ALTER TABLE snapshot_file ADD COLUMN blob_sha TEXT;
ALTER TABLE snapshot_file ADD COLUMN reason TEXT;
ALTER TABLE snapshot_file ADD COLUMN role TEXT;
CREATE INDEX ix_snapshot_file_role ON snapshot_file(snapshot_id, role);
