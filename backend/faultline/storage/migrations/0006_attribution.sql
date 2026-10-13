-- 0006_attribution: every subset the attribution search tried, with its outcome (M5.1). Forced worlds are experiments, not observations.
CREATE TABLE attribution_attempt (
  attribution_id TEXT NOT NULL REFERENCES attribution(id),
  seq INTEGER NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('sufficiency', 'necessity', 'search')),
  subset_json TEXT NOT NULL,              -- the package names applied (sufficiency/search) or reverted (necessity)
  world_hash TEXT,                        -- the forced world that was built for this attempt
  outcome TEXT NOT NULL CHECK (outcome IN ('FAIL', 'PASS', 'UNRESOLVED')),
  note TEXT,
  PRIMARY KEY (attribution_id, seq)
);
