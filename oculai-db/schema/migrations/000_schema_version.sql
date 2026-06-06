-- 000_schema_version.sql
-- Migration tracking table — records which schema migrations have been applied.
-- This is the FIRST migration and must run before any other migration logic.

CREATE TABLE IF NOT EXISTS schema_version (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum    TEXT,
    description TEXT
);

-- Record this migration itself
INSERT INTO schema_version (version, description)
VALUES ('000_schema_version', 'Migration tracking table')
ON CONFLICT (version) DO NOTHING;
