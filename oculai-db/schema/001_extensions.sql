-- 001_extensions.sql
-- Required PostgreSQL extensions for Oculai multi-Agent Database.

-- For pgvector < 0.5.0, the extension name is "vector"; for >= 0.5.0 it's "pgvector".
-- Try both so the schema works regardless of installed version.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS "vector";
EXCEPTION WHEN undefined_object THEN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS "pgvector";
    EXCEPTION WHEN undefined_object THEN
        RAISE NOTICE 'pgvector extension not available — vector indexes will be skipped';
    END;
END;
$$;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
