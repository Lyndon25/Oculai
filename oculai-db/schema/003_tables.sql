-- 003_tables.sql
-- Core tables for Oculai multi-Agent Database.
-- Phase columns removed. DAG-based Plan/Task model replaces fixed pipeline.
-- All tables share audit columns: created_at, updated_at, created_by_agent, updated_by_agent, data_version.

-- ============================================================
-- 1. Person — core entity, lifelong tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS Person (
    person_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name    TEXT NOT NULL,
    aliases           TEXT[] DEFAULT '{}',
    orcid             TEXT,
    google_scholar_id TEXT,
    linkedin_url      TEXT,
    github_id         TEXT,
    email_hashes      TEXT[] DEFAULT '{}',

    latest_institution       TEXT,
    latest_position          TEXT,
    total_papers             INTEGER DEFAULT 0,
    total_patents            INTEGER DEFAULT 0,
    h_index                  INTEGER DEFAULT 0,
    total_citations          INTEGER DEFAULT 0,
    last_active_date         DATE,

    h_index_provenance         JSONB,
    total_papers_provenance    JSONB,
    total_citations_provenance JSONB,

    research_direction_embedding VECTOR(1536),

    pool_tags           TEXT[] DEFAULT '{}',
    watch_level         watch_level_t DEFAULT 'medium',
    freshness_score     REAL DEFAULT 1.0 CHECK (freshness_score >= 0 AND freshness_score <= 1),
    confidence_score    REAL DEFAULT 1.0 CHECK (confidence_score >= 0 AND confidence_score <= 1),
    merge_status        TEXT DEFAULT 'independent',
    duplicate_candidates UUID[] DEFAULT '{}',

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 2. PersonProfile — versioned snapshot
-- ============================================================
CREATE TABLE IF NOT EXISTS PersonProfile (
    profile_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id      UUID NOT NULL,
    version        INTEGER NOT NULL DEFAULT 1,
    captured_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_agent   TEXT NOT NULL,
    raw_data_hash  TEXT NOT NULL,

    institution      JSONB,
    department       JSONB,
    position         JSONB,
    location         JSONB,
    email_domain     JSONB,
    personal_website JSONB,
    social_links     JSONB,
    research_areas   JSONB,
    skill_tags       JSONB,

    career_stage  career_stage_t,
    mobility_score REAL CHECK (mobility_score IS NULL OR (mobility_score >= 0 AND mobility_score <= 1)),

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1,

    UNIQUE (person_id, version)
);

-- ============================================================
-- 3. AcademicWork — papers, patents, books
-- ============================================================
CREATE TABLE IF NOT EXISTS AcademicWork (
    work_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id      UUID NOT NULL,
    type           work_type_t NOT NULL,

    title          TEXT,
    abstract       TEXT,
    venue          TEXT,
    publisher      TEXT,
    year           INTEGER,
    month          INTEGER,
    doi            TEXT,
    url            TEXT,
    pdf_url        TEXT,
    language       TEXT DEFAULT 'en',

    citations        INTEGER DEFAULT 0,
    altmetric_score  REAL DEFAULT 0,
    impact_factor    REAL,
    relevance_score  REAL DEFAULT 0,

    citations_provenance JSONB,

    abstract_embedding VECTOR(1536),
    title_embedding    VECTOR(1536),
    topic_vector       VECTOR(1536),

    source_db    TEXT,
    source_url   TEXT,
    fetched_at   TIMESTAMPTZ,
    raw_bibtex   JSONB,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 4. NetworkEdge — collaboration graph edges
-- ============================================================
CREATE TABLE IF NOT EXISTS NetworkEdge (
    edge_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_person_id   UUID NOT NULL,
    target_person_id   UUID NOT NULL,
    relation_type      relation_type_t NOT NULL,
    strength           REAL DEFAULT 0.5 CHECK (strength >= 0 AND strength <= 1),
    first_seen         DATE,
    last_seen          DATE,
    is_active          BOOLEAN DEFAULT true,
    evidence           JSONB DEFAULT '[]',

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 5. CareerEvent — timeline events
-- ============================================================
CREATE TABLE IF NOT EXISTS CareerEvent (
    event_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id     UUID NOT NULL,
    event_type    event_type_t NOT NULL,
    institution   TEXT,
    role          TEXT,
    department    TEXT,
    location      TEXT,
    start_date    DATE,
    end_date      DATE,
    is_current    BOOLEAN DEFAULT false,
    description   TEXT,
    source        TEXT,
    confidence    REAL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    verified_by_human BOOLEAN DEFAULT false,

    event_provenance JSONB,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1,

    CHECK (end_date IS NULL OR end_date >= start_date),
    UNIQUE (person_id, event_type, institution, start_date)
);

-- ============================================================
-- 6. SourcingRun — one complete sourcing execution
-- ============================================================
CREATE TABLE IF NOT EXISTS SourcingRun (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    status          run_status_t DEFAULT 'draft',
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,

    target_profile  JSONB DEFAULT '{}',
    target_keywords TEXT[] DEFAULT '{}',
    target_domains  TEXT[] DEFAULT '{}',
    config          JSONB DEFAULT '{}',
    result_summary  JSONB DEFAULT '{}',

    -- Active plan reference
    active_plan_id  UUID,

    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 7. CandidateRecord — links a Person to a SourcingRun
-- ============================================================
CREATE TABLE IF NOT EXISTS CandidateRecord (
    record_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL,
    person_id       UUID NOT NULL,

    status          candidate_status_t DEFAULT 'pending',

    raw_data        JSONB,
    enriched_data   JSONB,
    match_scores    JSONB,
    outreach_data   JSONB,

    quality_score   INTEGER DEFAULT 0 CHECK (quality_score >= 0 AND quality_score <= 100),

    -- Optimistic locking
    version         INTEGER NOT NULL DEFAULT 1,
    locked_by_agent TEXT,
    locked_at       TIMESTAMPTZ,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1,

    UNIQUE (run_id, person_id)
);

-- ============================================================
-- 8. Plan — DAG execution plan for a run
-- ============================================================
CREATE TABLE IF NOT EXISTS Plan (
    plan_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             UUID NOT NULL,
    planner_state_json JSONB NOT NULL DEFAULT '{}',
    status             plan_status_t DEFAULT 'draft',
    strategy_summary   TEXT,
    replan_triggers    TEXT[] DEFAULT '{}',

    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 9. Task — generic DAG task (replaces CandidateQueue)
-- ============================================================
CREATE TABLE IF NOT EXISTS Task (
    task_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id            UUID NOT NULL,
    run_id             UUID NOT NULL,
    task_type          TEXT NOT NULL,
    task_name          TEXT NOT NULL,
    step_key           TEXT,
    status             task_status_t DEFAULT 'pending',
    priority           INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),

    input_data         JSONB DEFAULT '{}',
    output_data        JSONB DEFAULT '{}',

    agent_id           TEXT,
    claimed_by         TEXT,
    claimed_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    failed_at          TIMESTAMPTZ,
    error_message      TEXT,

    retry_count        INTEGER DEFAULT 0,
    max_retries        INTEGER DEFAULT 3,

    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 10. TaskDependency — DAG edges
-- ============================================================
CREATE TABLE IF NOT EXISTS TaskDependency (
    dependency_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id            UUID NOT NULL,
    task_id            UUID NOT NULL,
    depends_on_task_id UUID NOT NULL,
    input_mapping      JSONB DEFAULT '{}',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (task_id, depends_on_task_id)
);

-- ============================================================
-- 11. Evidence — structured evidence attached to candidates
-- ============================================================
CREATE TABLE IF NOT EXISTS Evidence (
    evidence_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id         UUID NOT NULL,
    run_id            UUID,
    evidence_type     evidence_type_t NOT NULL,
    title             TEXT NOT NULL,
    description       TEXT,
    source_url        TEXT,
    source_name       TEXT NOT NULL,
    content           JSONB DEFAULT '{}',
    confidence        REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    captured_at       TIMESTAMPTZ DEFAULT now(),
    captured_by_agent TEXT NOT NULL,
    metadata          JSONB DEFAULT '{}',

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 12. CandidateAssessment — scored evaluation for a candidate in a run
-- ============================================================
CREATE TABLE IF NOT EXISTS CandidateAssessment (
    assessment_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL,
    person_id         UUID NOT NULL,
    assessor_agent    TEXT NOT NULL,

    dimension         assessment_dimension_t NOT NULL,
    score             REAL NOT NULL CHECK (score >= 0 AND score <= 10),
    confidence        REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    rationale         TEXT,
    evidence_ids      UUID[] DEFAULT '{}',

    assessment_json   JSONB DEFAULT '{}',

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1,

    UNIQUE (run_id, person_id, assessor_agent, dimension)
);

-- ============================================================
-- 13. OutreachRecord — external communication tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS OutreachRecord (
    record_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id       UUID NOT NULL,
    run_id          UUID NOT NULL,
    sequence_number INTEGER DEFAULT 1,

    channel         channel_t NOT NULL,
    strategy        TEXT,
    subject         TEXT,
    sent_at         TIMESTAMPTZ,
    sender_id       TEXT,
    content_preview TEXT,
    content_full    TEXT,
    template_id     TEXT,

    opened_at        TIMESTAMPTZ,
    clicked_at       TIMESTAMPTZ,
    replied_at       TIMESTAMPTZ,
    reply_content    TEXT,
    reply_sentiment  sentiment_t,

    status          outreach_status_t DEFAULT 'draft',

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 14. HumanApproval — approval gate for external actions
-- ============================================================
CREATE TABLE IF NOT EXISTS HumanApproval (
    approval_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL,
    action_type       TEXT NOT NULL,
    action_context    JSONB NOT NULL DEFAULT '{}',
    draft_content     TEXT,
    requested_by      TEXT NOT NULL,
    requested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status            approval_status_t DEFAULT 'pending',
    reviewed_by       TEXT,
    reviewed_at       TIMESTAMPTZ,
    review_notes      TEXT,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 15. FeedbackEvent — closed-loop feedback
-- ============================================================
CREATE TABLE IF NOT EXISTS FeedbackEvent (
    event_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id            UUID NOT NULL,
    run_id               UUID NOT NULL,
    event_type           feedback_event_type_t NOT NULL,
    feedback_provider_id TEXT,
    provided_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    rating               INTEGER CHECK (rating >= 1 AND rating <= 5),
    dimensions           JSONB DEFAULT '{}',
    notes                TEXT,
    ai_prediction_bias   REAL,
    model_update_applied BOOLEAN DEFAULT false,
    applied_at           TIMESTAMPTZ,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- 16. SearchQueryLog — observability for every search
-- ============================================================
CREATE TABLE IF NOT EXISTS SearchQueryLog (
    log_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID,
    source_name      TEXT NOT NULL,
    source_type      source_type_t NOT NULL,
    query_params     JSONB DEFAULT '{}',
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms      INTEGER,
    records_count    INTEGER DEFAULT 0,
    status           source_status_t NOT NULL,
    error_message    TEXT,
    retry_count      INTEGER DEFAULT 0,
    raw_data_checksum TEXT,
    raw_data_size_bytes BIGINT,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_agent   TEXT NOT NULL DEFAULT 'system',
    updated_by_agent   TEXT NOT NULL DEFAULT 'system',
    data_version       INTEGER NOT NULL DEFAULT 1
);
