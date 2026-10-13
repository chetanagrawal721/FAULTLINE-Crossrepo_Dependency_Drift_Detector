-- 0004_resolution: cache of resolution outcomes, keyed by every input that can change the result (M3.4).
CREATE TABLE resolution_cache (
  cache_key TEXT PRIMARY KEY,             -- 'rc_' + sha256(manifest hashes, resolver, platform, flags, index, cutoff)
  ecosystem TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('OK','OK_PARTIAL','FAILED')),
  outcome_json TEXT NOT NULL,
  world_hash TEXT REFERENCES resolved_world(world_hash),
  created_at TEXT NOT NULL
);
