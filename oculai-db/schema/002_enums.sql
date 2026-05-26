-- 002_enums.sql
-- All enum-like CHECK constraint types used across the schema.
-- Phase-era phase_status and queue_status domains are REMOVED.
-- task_type_t enum is REMOVED — task_type is now free-form TEXT.

-- Plan / Task DAG status domains
DO $$ BEGIN
    CREATE DOMAIN plan_status_t AS TEXT
        CHECK (VALUE IN ('draft','active','completed','failed','aborted'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN task_status_t AS TEXT
        CHECK (VALUE IN ('pending','claimed','processing','done','error','timeout','skipped'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Sourcing run lifecycle
DO $$ BEGIN
    CREATE DOMAIN run_status_t AS TEXT
        CHECK (VALUE IN ('draft','running','paused','reviewing','completed','aborted'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Candidate record state within a run
DO $$ BEGIN
    CREATE DOMAIN candidate_status_t AS TEXT
        CHECK (VALUE IN ('pending','processing','reviewing','shortlisted','rejected','contacted','hired'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Approval gate states
DO $$ BEGIN
    CREATE DOMAIN approval_status_t AS TEXT
        CHECK (VALUE IN ('pending','approved','denied','expired'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Retained from Phase7 (no phase dependency)
DO $$ BEGIN
    CREATE DOMAIN watch_level_t AS TEXT
        CHECK (VALUE IN ('high','medium','low','dormant'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN career_stage_t AS TEXT
        CHECK (VALUE IN ('student','postdoc','junior','senior','lead','executive'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN work_type_t AS TEXT
        CHECK (VALUE IN ('paper','patent','book','chapter','preprint'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN relation_type_t AS TEXT
        CHECK (VALUE IN ('co_author','mentor','mentee','colleague','cited_by'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN event_type_t AS TEXT
        CHECK (VALUE IN ('education','employment','promotion','funding','award','publication_burst'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN channel_t AS TEXT
        CHECK (VALUE IN ('email','linkedin','twitter','github_issue','wechat','phone','meeting'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN outreach_status_t AS TEXT
        CHECK (VALUE IN ('draft','scheduled','sent','delivered','opened','replied','bounced'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN feedback_event_type_t AS TEXT
        CHECK (VALUE IN ('reply','interview','offer','hire','retention_3m','retention_6m','rejection','departure'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN source_type_t AS TEXT
        CHECK (VALUE IN ('api','crawl','rss','feed','browser'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN source_status_t AS TEXT
        CHECK (VALUE IN ('success','partial','failed','rate_limited'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN severity_t AS TEXT
        CHECK (VALUE IN ('minor','medium','major'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN sentiment_t AS TEXT
        CHECK (VALUE IN ('positive','neutral','negative'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN evidence_type_t AS TEXT
        CHECK (VALUE IN ('paper','patent','code','profile','web_page','screenshot','email','interview','reference','blog_post','social_media','conference_talk','award','certification'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE DOMAIN assessment_dimension_t AS TEXT
        CHECK (VALUE IN ('academic','engineering','leadership','communication','culture_fit','skill_match','location','career_stage','mobility','overall'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
