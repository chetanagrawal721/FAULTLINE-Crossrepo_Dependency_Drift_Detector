-- 0001_init: canonical schema from the master document, section 37.3.
-- Added in this repository: CHECK constraints generated from core/enums.py, and oracle_run.provenance,
-- created_at and env_fingerprint (plan v3.1: only FRESH_EXECUTION runs count toward a witness).

-- ============ PROJECTS & SOURCES ============
CREATE TABLE analysis_project (           -- a user's workspace: a named set of repos
  id TEXT PRIMARY KEY,                    -- 'ap_…'
  name TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('LIVE','FIXTURE','REPLAY')),
  config_json TEXT NOT NULL DEFAULT '{}', -- declared (L5) relationships, thresholds
  created_at TEXT NOT NULL
);

CREATE TABLE repository (
  id TEXT PRIMARY KEY,                    -- 'repo_…'
  analysis_project_id TEXT NOT NULL REFERENCES analysis_project(id),
  host TEXT NOT NULL DEFAULT 'github.com',
  owner TEXT NOT NULL, name TEXT NOT NULL,
  requested_ref TEXT,                     -- branch/tag/sha as requested
  is_fork INTEGER, is_archived INTEGER, default_branch TEXT,
  UNIQUE (analysis_project_id, owner, name)
);

CREATE TABLE snapshot (                   -- repository @ pinned SHA ("Commit")
  id TEXT PRIMARY KEY,                    -- 'snp_…'
  repository_id TEXT NOT NULL REFERENCES repository(id),
  sha TEXT NOT NULL CHECK (length(sha) = 40),
  committed_at TEXT NOT NULL,             -- used as default resolution timestamp for reference worlds
  tree_truncated INTEGER NOT NULL DEFAULT 0,
  store_path TEXT NOT NULL,               -- store/snapshots/<sha>
  ingest_status TEXT NOT NULL CHECK (ingest_status IN ('OK', 'PARTIAL', 'FAILED')),            -- OK | PARTIAL | FAILED
  ingest_warnings_json TEXT NOT NULL DEFAULT '[]',
  UNIQUE (repository_id, sha)
);

CREATE TABLE project (                    -- buildable unit inside a snapshot
  id TEXT PRIMARY KEY,                    -- 'prj_…'
  snapshot_id TEXT NOT NULL REFERENCES snapshot(id),
  rel_path TEXT NOT NULL,                 -- '.' or 'services/billing'
  ecosystem TEXT NOT NULL CHECK (ecosystem IN ('pypi','npm','maven')),
  published_name TEXT,                    -- normalized; NULL if not a publishable package
  runtime_json TEXT,                      -- {"name":"cpython","version":"3.12","source":".python-version"}
  artifact_content_hash TEXT,             -- sha256 over source tree (for artifacts)
  is_pure_python INTEGER,                 -- path-injection eligible
  has_tests INTEGER NOT NULL DEFAULT 0,
  UNIQUE (snapshot_id, rel_path, ecosystem)
);
CREATE INDEX ix_project_published ON project(ecosystem, published_name);

CREATE TABLE manifest (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES project(id),
  path TEXT NOT NULL,                     -- relative to snapshot root
  kind TEXT NOT NULL,                     -- requirements|pyproject|uv_lock|poetry_lock|package_json|package_lock|pnpm_lock|yarn_lock|pom
  content_hash TEXT NOT NULL,
  parsed_json TEXT,                       -- normalized declared deps: [{name, spec, scope, source, line}]
  parse_status TEXT NOT NULL,             -- OK | FAILED | TOO_LARGE
  parse_error TEXT
);
CREATE INDEX ix_manifest_project ON manifest(project_id);

-- ============ WORLDS & PACKAGES ============
CREATE TABLE package_version (            -- global, immutable
  id TEXT PRIMARY KEY,                    -- sha256(eco|name|version)
  ecosystem TEXT NOT NULL CHECK (ecosystem IN ('pypi', 'npm', 'maven')), name TEXT NOT NULL, version TEXT NOT NULL,
  artifact_sha256 TEXT,                   -- wheel/tarball/jar hash (platform-specific wheel chosen)
  artifact_filename TEXT,
  has_wheel INTEGER,                      -- python: compatible wheel for linux/amd64 + runtime
  published_at TEXT,
  UNIQUE (ecosystem, name, version)
);

CREATE TABLE resolved_world (             -- global, content-addressed
  world_hash TEXT PRIMARY KEY,            -- 'w_' || sha256(canonical content)
  ecosystem TEXT NOT NULL,
  runtime_json TEXT NOT NULL,
  env_profile_id TEXT NOT NULL REFERENCES env_profile(id),
  kind TEXT NOT NULL CHECK (kind IN ('observed','reference','projected','forced','overlay')),
  venv_status TEXT NOT NULL CHECK (venv_status IN ('NOT_BUILT', 'BUILT', 'FAILED')) DEFAULT 'NOT_BUILT',   -- NOT_BUILT | BUILT | FAILED
  venv_path TEXT
);

CREATE TABLE world_entry (
  world_hash TEXT NOT NULL REFERENCES resolved_world(world_hash),
  locator TEXT NOT NULL,
  package_version_id TEXT NOT NULL REFERENCES package_version(id),
  scope TEXT NOT NULL,                    -- runtime|dev|test|optional|provided|peer
  source_kind TEXT NOT NULL,              -- registry|git|path|url|private
  parents_json TEXT NOT NULL DEFAULT '[]',
  PRIMARY KEY (world_hash, locator)
);
CREATE INDEX ix_world_entry_pkg ON world_entry(package_version_id);

CREATE TABLE project_world (              -- which world a project resolved to, with provenance
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES project(id),
  world_hash TEXT REFERENCES resolved_world(world_hash),
  source TEXT NOT NULL,                   -- lockfile|resolver
  resolver TEXT, resolver_args_json TEXT,
  resolved_at TEXT NOT NULL,              -- timestamp used for --exclude-newer
  status TEXT NOT NULL CHECK (status IN ('OK', 'OK_PARTIAL', 'FAILED')),                   -- OK | OK_PARTIAL | FAILED
  failure_json TEXT,
  UNIQUE (project_id, resolved_at)
);

CREATE TABLE env_profile (
  id TEXT PRIMARY KEY,                    -- 'ep_' || sha256
  image_ref TEXT NOT NULL,                -- with @sha256 digest
  arch TEXT NOT NULL, locale TEXT NOT NULL, tz TEXT NOT NULL,
  env_json TEXT NOT NULL, seed INTEGER NOT NULL
);

-- ============ ANALYSIS, RELATIONSHIPS, CELLS ============
CREATE TABLE analysis (
  id TEXT PRIMARY KEY,                    -- 'an_…'
  analysis_project_id TEXT NOT NULL REFERENCES analysis_project(id),
  status TEXT NOT NULL CHECK (status IN ('QUEUED', 'INGESTING', 'RESOLVING', 'RELATING', 'BUILDING_CELLS', 'ANALYZING', 'VERIFYING', 'ATTRIBUTING', 'DONE', 'FAILED')),                   -- QUEUED|INGESTING|RESOLVING|RELATING|BUILDING_CELLS|ANALYZING|VERIFYING|ATTRIBUTING|DONE|FAILED
  mode TEXT NOT NULL CHECK (mode IN ('LIVE', 'FIXTURE', 'REPLAY')),
  options_json TEXT NOT NULL,             -- enabled oracles, thresholds, time-machine date
  started_at TEXT, finished_at TEXT,
  stats_json TEXT                         -- funnel counts
);

CREATE TABLE relationship (
  id TEXT PRIMARY KEY,                    -- 'rel_…'
  analysis_id TEXT NOT NULL REFERENCES analysis(id),
  producer_project_id TEXT NOT NULL REFERENCES project(id),
  consumer_project_id TEXT NOT NULL REFERENCES project(id),
  kind TEXT NOT NULL,                     -- SHARED_ARTIFACT|SHARED_SCHEMA|SCHEMA_DRIFT|GENERATED_CODE|PRODUCER_CONSUMER|SUSPECTED_TWIN|TOPOLOGY|DOCKER_COINSTALL|DECLARED
  level TEXT NOT NULL CHECK (level IN ('L2', 'L3', 'L3P', 'L4', 'L5')),                    -- L2|L3|L3P|L4|L5
  confidence TEXT NOT NULL,               -- HIGH|MEDIUM|LOW
  actionable INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUSPECTED', 'CONFIRMED', 'REJECTED')) DEFAULT 'ACTIVE',  -- ACTIVE|SUSPECTED|CONFIRMED|REJECTED
  shared_symbols_json TEXT NOT NULL DEFAULT '[]',
  roles_json TEXT                         -- L4: {producer_sites:[...], consumer_sites:[...], options:{...}}
);
CREATE INDEX ix_rel_analysis ON relationship(analysis_id, actionable);

CREATE TABLE relationship_evidence (
  id TEXT PRIMARY KEY,
  relationship_id TEXT NOT NULL REFERENCES relationship(id),
  signal TEXT NOT NULL,                   -- published_name|path_dep|git_dep|workspace|schema_hash|pb2_header|serializer_site|parser_site|compose_url|...
  project_id TEXT NOT NULL REFERENCES project(id),
  file_path TEXT, line INTEGER, excerpt TEXT
);

CREATE TABLE cell (
  id TEXT PRIMARY KEY,                    -- 'cell_…'
  analysis_id TEXT NOT NULL REFERENCES analysis(id),
  artifact_project_id TEXT NOT NULL REFERENCES project(id),
  ref_world_hash TEXT NOT NULL REFERENCES resolved_world(world_hash),
  test_world_hash TEXT NOT NULL REFERENCES resolved_world(world_hash),
  state TEXT NOT NULL CHECK (state IN ('NO_DRIFT', 'PENDING', 'ANALYZED', 'NOT_APPLICABLE', 'INCONCLUSIVE')),                    -- NO_DRIFT|PENDING|ANALYZED|NOT_APPLICABLE|INCONCLUSIVE
  forced_overlay INTEGER NOT NULL DEFAULT 0,
  UNIQUE (analysis_id, artifact_project_id, test_world_hash)
);

CREATE TABLE cell_consumer (
  cell_id TEXT NOT NULL REFERENCES cell(id),
  consumer_project_id TEXT NOT NULL REFERENCES project(id),
  relationship_id TEXT NOT NULL REFERENCES relationship(id),
  imported_modules_json TEXT NOT NULL DEFAULT '[]',   -- PC-4
  pinned_artifact_ref TEXT,                            -- e.g. git tag the consumer pins
  PRIMARY KEY (cell_id, consumer_project_id)
);

CREATE TABLE delta_entry (
  cell_id TEXT NOT NULL REFERENCES cell(id),
  name TEXT NOT NULL,                     -- package name or '<runtime>' / '<artifact>'
  v_ref TEXT, v_test TEXT,                -- NULL = absent
  kind TEXT NOT NULL,                     -- CHANGED|ADDED|REMOVED
  PRIMARY KEY (cell_id, name)
);

-- ============ API & USAGE ============
CREATE TABLE api_surface (
  package_version_id TEXT PRIMARY KEY REFERENCES package_version(id),
  extractor TEXT NOT NULL,                -- griffe@x.y | tsd | japicmp
  blob_path TEXT NOT NULL,                -- store/api/...json
  flags_json TEXT NOT NULL DEFAULT '{}'   -- opaque_modules, dynamic_exports
);

CREATE TABLE api_delta (
  id TEXT PRIMARY KEY,                    -- sha256(eco|name|v_from|v_to|extractor)
  ecosystem TEXT NOT NULL, name TEXT NOT NULL, v_from TEXT NOT NULL, v_to TEXT NOT NULL,
  status TEXT NOT NULL,                   -- OK|FAILED|OPAQUE
  n_breaking INTEGER NOT NULL DEFAULT 0,
  flags_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE api_change (
  id TEXT PRIMARY KEY,
  api_delta_id TEXT NOT NULL REFERENCES api_delta(id),
  path TEXT NOT NULL,                     -- fq symbol
  kind TEXT NOT NULL,                     -- Section 19.2
  breaking INTEGER NOT NULL,
  behavioral INTEGER NOT NULL DEFAULT 0,
  old_json TEXT, new_json TEXT, detail_json TEXT,
  source TEXT NOT NULL                    -- griffe|rule:<id>|tsd|japicmp
);
CREATE INDEX ix_api_change_path ON api_change(api_delta_id, path);

CREATE TABLE usage_file (                 -- per source file content hash (incremental)
  content_hash TEXT PRIMARY KEY,
  analyzer_version TEXT NOT NULL,
  status TEXT NOT NULL                    -- OK|PARSE_ERROR
);

CREATE TABLE snapshot_file (              -- maps snapshot paths to usage_file hashes
  snapshot_id TEXT NOT NULL REFERENCES snapshot(id),
  path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',          -- GENERATED,NOTEBOOK,TEST,VENDORED
  PRIMARY KEY (snapshot_id, path)
);

CREATE TABLE usage_ref (
  id TEXT PRIMARY KEY,
  content_hash TEXT NOT NULL REFERENCES usage_file(content_hash),
  line INTEGER NOT NULL, col INTEGER NOT NULL,
  target TEXT,                            -- fq symbol (NULL if DYNAMIC/UNRESOLVED)
  root_package TEXT,                      -- import root (for refs_to(D))
  status TEXT NOT NULL,                   -- RESOLVED|LOW_CONFIDENCE|DYNAMIC|UNRESOLVED|OBSERVED
  ref_kind TEXT NOT NULL,                 -- IMPORT|CALL|ATTR|BASE|DECORATOR|ANNOTATION|STRING_PATH
  call_shape_json TEXT,                   -- {"n_pos":1,"kw":["x"],"star":false,"dstar":false,"literals":[...]}
  tags TEXT NOT NULL DEFAULT ''           -- TYPE_ONLY,OPTIONAL_PATH,GENERATED,NOTEBOOK
);
CREATE INDEX ix_usage_root ON usage_ref(content_hash, root_package);

CREATE TABLE import_index (               -- global transitive cache
  importer_pv_id TEXT NOT NULL REFERENCES package_version(id),
  target_name TEXT NOT NULL,
  symbols_json TEXT NOT NULL, reexports_json TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (importer_pv_id, target_name)
);

CREATE TABLE exposure (
  id TEXT PRIMARY KEY,
  cell_id TEXT NOT NULL REFERENCES cell(id),
  usage_ref_id TEXT REFERENCES usage_ref(id),       -- NULL for transitive (see importer fields)
  importer_pv_id TEXT REFERENCES package_version(id),
  api_change_id TEXT NOT NULL REFERENCES api_change(id),
  static_ok INTEGER,                      -- binding simulation result (NULL unknown)
  depth INTEGER NOT NULL DEFAULT 0,
  exercised INTEGER NOT NULL DEFAULT 0    -- set when an oracle covered it
);

-- ============ EXECUTION & EVIDENCE ============
CREATE TABLE oracle_job (
  id TEXT PRIMARY KEY,                    -- 'oj_…'
  analysis_id TEXT NOT NULL REFERENCES analysis(id),
  cell_id TEXT REFERENCES cell(id),
  oracle TEXT NOT NULL, oracle_version TEXT NOT NULL,
  world_hash TEXT NOT NULL REFERENCES resolved_world(world_hash),
  side TEXT NOT NULL CHECK (side IN ('ref','test','forced')),
  spec_json TEXT NOT NULL,
  cache_key TEXT NOT NULL,                -- sha256(WitnessKey-like tuple + run_index)
  status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED')),                   -- QUEUED|RUNNING|DONE|FAILED
  priority INTEGER NOT NULL DEFAULT 100,
  attempts INTEGER NOT NULL DEFAULT 0,
  worker TEXT, queued_at TEXT, started_at TEXT, finished_at TEXT
);
CREATE INDEX ix_job_queue ON oracle_job(status, priority, queued_at);
CREATE UNIQUE INDEX ux_job_cache ON oracle_job(cache_key);

CREATE TABLE oracle_run (
  id TEXT PRIMARY KEY,
  oracle_job_id TEXT NOT NULL REFERENCES oracle_job(id),
  run_index INTEGER NOT NULL,             -- 1..3
  provenance TEXT NOT NULL CHECK (provenance IN ('FRESH_EXECUTION','REUSED_RESULT')),
  created_at TEXT NOT NULL,
  env_fingerprint TEXT,
  exit_code INTEGER, duration_ms INTEGER,
  failure_class TEXT NOT NULL CHECK (failure_class IN ('NONE', 'ARTIFACT_FAILURE', 'HARNESS_FAILURE', 'RESOLUTION_FAILURE', 'BUILD_FAILURE', 'SANDBOX_FAILURE', 'RESOURCE_LIMIT', 'TIMEOUT', 'NEEDS_EXTERNAL', 'UNSUPPORTED')),            -- NONE|ARTIFACT_FAILURE|HARNESS_FAILURE|SANDBOX_FAILURE|RESOURCE_LIMIT|TIMEOUT|NEEDS_EXTERNAL|...
  result_json TEXT NOT NULL,              -- per-entry outcomes (per module / per test id / per input)
  stdout_path TEXT, stderr_path TEXT
);

CREATE TABLE witness (
  id TEXT PRIMARY KEY,                    -- 'wit_…'
  analysis_id TEXT NOT NULL REFERENCES analysis(id),
  cell_id TEXT NOT NULL REFERENCES cell(id),
  consumer_cell_id TEXT REFERENCES cell(id),        -- contract witnesses: producer cell + consumer cell
  class TEXT NOT NULL CHECK (class IN ('BREAK', 'SILENT_DIVERGENCE')),                    -- BREAK|SILENT_DIVERGENCE
  divergence TEXT NOT NULL,
  oracle TEXT NOT NULL, oracle_version TEXT NOT NULL,
  entry_point TEXT NOT NULL,
  input_tier TEXT, input_hash TEXT,
  witness_key TEXT NOT NULL UNIQUE,
  signature_json TEXT NOT NULL,
  ref_pass INTEGER NOT NULL, test_fail INTEGER NOT NULL,
  body_json TEXT NOT NULL                 -- full witness object (Section 28.1)
);

CREATE TABLE attribution (
  id TEXT PRIMARY KEY,
  witness_id TEXT NOT NULL UNIQUE REFERENCES witness(id),
  status TEXT NOT NULL CHECK (status IN ('COMPLETE', 'PARTIAL', 'BUDGET_LIMITED', 'UNSTABLE', 'UNAVAILABLE')),                   -- COMPLETE|PARTIAL|UNSTABLE|FAILED
  minimal_set_json TEXT NOT NULL,
  sidedness TEXT NOT NULL CHECK (sidedness IN ('two_sided', 'one_sided', 'untestable')),                -- two_sided|one_sided|untestable
  forced_worlds_used INTEGER NOT NULL,
  runs INTEGER NOT NULL, notes_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE evidence_bundle (
  id TEXT PRIMARY KEY,
  witness_id TEXT NOT NULL UNIQUE REFERENCES witness(id),
  path TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE finding (
  id TEXT PRIMARY KEY,                    -- 'fnd_…'
  analysis_id TEXT NOT NULL REFERENCES analysis(id),
  scope_kind TEXT NOT NULL,               -- ARTIFACT_CELL|CONTRACT_PAIR|HYGIENE|SCHEMA_DRIFT
  cell_id TEXT REFERENCES cell(id),
  relationship_id TEXT REFERENCES relationship(id),
  verdict TEXT NOT NULL CHECK (verdict IN ('BREAK_WITNESSED', 'SILENT_DIVERGENCE_WITNESSED', 'NO_DIVERGENCE_OBSERVED', 'EXPOSED', 'POTENTIAL', 'NOT_EXPOSED', 'INCONCLUSIVE', 'HYGIENE')),                  -- BREAK_WITNESSED|SILENT_DIVERGENCE_WITNESSED|NO_DIVERGENCE_OBSERVED|EXPOSED|POTENTIAL|NOT_EXPOSED|INCONCLUSIVE|HYGIENE
  sub_label TEXT,                         -- static-confirmed, reason codes, ...
  headline TEXT NOT NULL,                 -- templated (Section 30.4)
  scope_json TEXT NOT NULL,               -- exercised / not checked
  coverage REAL,                          -- for NOT_EXPOSED / POTENTIAL
  priority INTEGER NOT NULL,              -- ordinal for sorting only
  created_at TEXT NOT NULL
);
CREATE INDEX ix_finding_analysis ON finding(analysis_id, verdict, priority);

CREATE TABLE finding_evidence (
  finding_id TEXT NOT NULL REFERENCES finding(id),
  evidence_kind TEXT NOT NULL,            -- WITNESS|EXPOSURE|API_CHANGE|DIAGNOSTIC|ORACLE_RUN|RELATIONSHIP|CLAIM
  evidence_id TEXT NOT NULL,
  PRIMARY KEY (finding_id, evidence_kind, evidence_id)
);

CREATE TABLE remediation_plan (
  id TEXT PRIMARY KEY,
  finding_id TEXT NOT NULL REFERENCES finding(id),
  moves_json TEXT NOT NULL,
  gates_json TEXT NOT NULL,               -- {"G1":true,"G2":true,"G3":true,"G4":null}
  label TEXT NOT NULL CHECK (label IN ('VERIFIED', 'PARTIALLY_VERIFIED', 'SUGGESTED')),                    -- VERIFIED|PARTIALLY_VERIFIED|SUGGESTED
  rank INTEGER NOT NULL,
  diff_path TEXT,                         -- for CODE_CHANGE moves
  world_hashes_json TEXT NOT NULL
);

CREATE TABLE event_log (                  -- failures & progress (UI + debugging)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  analysis_id TEXT, at TEXT NOT NULL, level TEXT NOT NULL,
  code TEXT NOT NULL,                     -- Section 46 failure codes
  subject_kind TEXT, subject_id TEXT, message TEXT NOT NULL, data_json TEXT
);
