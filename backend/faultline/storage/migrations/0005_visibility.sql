-- 0005_visibility: which version an importer actually sees, observed in a built world (M3.5).
-- For Python the importer is '' (one flat site-packages); npm uses the importing package path (M3.6).
CREATE TABLE world_visible (
  world_hash TEXT NOT NULL REFERENCES resolved_world(world_hash),
  locator TEXT NOT NULL,
  importer TEXT NOT NULL DEFAULT '',
  visible_version TEXT NOT NULL,
  source TEXT NOT NULL,                   -- 'built_world' (read from the installed distributions) | 'simulated'
  PRIMARY KEY (world_hash, locator, importer)
);

-- what discovery learned about a project (M3.1), shown by the inspector
ALTER TABLE project ADD COLUMN origin TEXT;
ALTER TABLE project ADD COLUMN display_name TEXT;
ALTER TABLE project ADD COLUMN notes_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE project ADD COLUMN layout_json TEXT NOT NULL DEFAULT '{}';
