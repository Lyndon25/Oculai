-- 003b_supporting_tables.sql
-- Supporting tables: conflicts, changelog, lineage, quotas, metrics, identities.
-- All retained from Phase7. CandidateQueue removed.

-- ============================================================
-- DataConflict: multi-source conflict records
-- ============================================================
CREATE TABLE IF NOT EXISTS DataConflict (
    conflict_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    field_name      TEXT NOT NULL,
    values_json     JSONB NOT NULL,
    auto_score      REAL,
    suggested_value JSONB,
    resolved_by     TEXT,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conflict_entity ON DataConflict (entity_type, entity_id);

-- ============================================================
-- ChangeLog: field-level change history with severity
-- ============================================================
CREATE TABLE IF NOT EXISTS ChangeLog (
    change_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type       TEXT NOT NULL,
    entity_id         UUID NOT NULL,
    field_name        TEXT NOT NULL,
    old_value         JSONB,
    new_value         JSONB,
    severity          severity_t NOT NULL,
    diff_summary      TEXT,
    detected_by_agent TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_changelog_entity ON ChangeLog (entity_type, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_changelog_severity ON ChangeLog (severity, created_at DESC);

-- ============================================================
-- DataLineage: upstream → downstream dependency tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS DataLineage (
    lineage_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upstream_entity   TEXT NOT NULL,
    upstream_id       UUID NOT NULL,
    upstream_field    TEXT NOT NULL,
    downstream_entity TEXT NOT NULL,
    downstream_id     UUID NOT NULL,
    downstream_field  TEXT NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT now(),
    UNIQUE (upstream_entity, upstream_id, upstream_field, downstream_entity, downstream_id, downstream_field)
);

CREATE INDEX IF NOT EXISTS idx_lineage_upstream ON DataLineage (upstream_entity, upstream_id);
CREATE INDEX IF NOT EXISTS idx_lineage_downstream ON DataLineage (downstream_entity, downstream_id);

-- ============================================================
-- RecalculationQueue: pending recalculations due to upstream changes
-- ============================================================
CREATE TABLE IF NOT EXISTS RecalculationQueue (
    recalc_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id       UUID NOT NULL,
    reason          TEXT,
    priority        INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    status          TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','done','error')),
    created_at      TIMESTAMPTZ DEFAULT now(),
    processed_at    TIMESTAMPTZ,

    UNIQUE (record_id, reason)
);

CREATE INDEX IF NOT EXISTS idx_recalc_status ON RecalculationQueue (status, priority DESC, created_at ASC);

-- ============================================================
-- DataSourceQuota: API rate limiting per data source
-- ============================================================
CREATE TABLE IF NOT EXISTS DataSourceQuota (
    source_name     TEXT PRIMARY KEY,
    daily_limit     INTEGER NOT NULL,
    used_today      INTEGER DEFAULT 0,
    last_reset_at   DATE DEFAULT CURRENT_DATE,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- CronJobRun: task execution record with anti-reentry
-- ============================================================
CREATE TABLE IF NOT EXISTS CronJobRun (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('running','success','failed','degraded')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    affected_rows   INTEGER,
    error_message   TEXT,
    error_stack     TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cron_running ON CronJobRun (job_name) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS idx_cron_started ON CronJobRun (started_at DESC);

-- ============================================================
-- AgentMetric: agent-reported performance metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS AgentMetric (
    metric_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id      TEXT NOT NULL,
    metric_name   TEXT NOT NULL,
    metric_value  REAL NOT NULL,
    recorded_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metric_agent ON AgentMetric (agent_id, metric_name, recorded_at DESC);

-- ============================================================
-- BrowserEvidence: screenshot/snapshot evidence from browser automation
-- ============================================================
CREATE TABLE IF NOT EXISTS BrowserEvidence (
    evidence_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id         UUID,
    run_id            UUID,
    source_url        TEXT NOT NULL,
    captured_content  JSONB NOT NULL DEFAULT '{}',
    capture_mode      TEXT NOT NULL DEFAULT 'text',
    captured_at       TIMESTAMPTZ DEFAULT now(),
    captured_by_agent TEXT NOT NULL,
    created_by_agent  TEXT NOT NULL DEFAULT 'system',
    updated_by_agent  TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_bev_person ON BrowserEvidence (person_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_bev_url ON BrowserEvidence (source_url, capture_mode);

-- ============================================================
-- ============================================================
-- PersonExternalIdentity: multi-source identity linking
-- ============================================================
CREATE TABLE IF NOT EXISTS PersonExternalIdentity (
    identity_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id         UUID NOT NULL,
    source_type       TEXT NOT NULL,
    external_id       TEXT NOT NULL,
    external_url      TEXT,
    is_primary        BOOLEAN DEFAULT false,
    confidence        REAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    verified_at       TIMESTAMPTZ,
    verified_by_agent TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (source_type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_pei_person ON PersonExternalIdentity (person_id);
CREATE INDEX IF NOT EXISTS idx_pei_source ON PersonExternalIdentity (source_type, external_id);
CREATE INDEX IF NOT EXISTS idx_pei_primary ON PersonExternalIdentity (person_id, is_primary) WHERE is_primary = true;

-- ============================================================
-- SearchRoundState: per-round search metrics for deep search orchestrator
-- ============================================================
CREATE TABLE IF NOT EXISTS searchroundstate (
    round_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID NOT NULL REFERENCES sourcingrun(run_id) ON DELETE CASCADE,
    hypothesis_id    TEXT NOT NULL,
    source_name      TEXT NOT NULL,
    round_number     INT NOT NULL,
    query_used       JSONB NOT NULL DEFAULT '{}',
    results_count    INT NOT NULL DEFAULT 0,
    verified_count   INT NOT NULL DEFAULT 0,
    persisted_count  INT NOT NULL DEFAULT 0,
    signal_quality   REAL,
    result_diversity REAL,
    is_saturated     BOOLEAN DEFAULT false,
    terminated_reason TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (run_id, hypothesis_id, source_name, round_number)
);

CREATE INDEX IF NOT EXISTS idx_srs_run ON searchroundstate (run_id);
CREATE INDEX IF NOT EXISTS idx_srs_source ON searchroundstate (source_name, is_saturated);
CREATE INDEX IF NOT EXISTS idx_srs_hypo ON searchroundstate (run_id, hypothesis_id);

-- ============================================================
-- AssessmentScoreHistory — tracks every score change per dimension
-- ============================================================
CREATE TABLE IF NOT EXISTS AssessmentScoreHistory (
    history_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL REFERENCES SourcingRun(run_id) ON DELETE CASCADE,
    person_id         UUID NOT NULL REFERENCES Person(person_id) ON DELETE CASCADE,
    dimension         assessment_dimension_t NOT NULL,
    previous_score    REAL,
    new_score         REAL NOT NULL,
    previous_confidence REAL,
    new_confidence    REAL NOT NULL,
    assessor_agent    TEXT NOT NULL,
    changed_at        TIMESTAMPTZ DEFAULT now(),
    change_reason     TEXT,
    evidence_snapshot JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_score_history_run_person ON AssessmentScoreHistory(run_id, person_id);
CREATE INDEX IF NOT EXISTS idx_score_history_changed_at ON AssessmentScoreHistory(changed_at DESC);

-- ============================================================
-- ReviewSession — multi-pass review orchestrator state machine
-- ============================================================
DO $$ BEGIN
    CREATE DOMAIN review_pass_t AS TEXT
        CHECK (VALUE IN ('enrichment','initial_scoring','audit','adjustment','complete'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS ReviewSession (
    session_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                UUID NOT NULL REFERENCES SourcingRun(run_id) ON DELETE CASCADE,
    status                TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','completed','failed')),
    current_pass          review_pass_t NOT NULL DEFAULT 'enrichment',
    role_type             TEXT NOT NULL DEFAULT 'default',
    target_candidate_ids  UUID[] NOT NULL DEFAULT '{}',
    completed_candidate_ids UUID[] NOT NULL DEFAULT '{}',
    failed_candidate_ids  UUID[] NOT NULL DEFAULT '{}',
    audit_findings        JSONB DEFAULT '{}',
    pass_timings          JSONB DEFAULT '{}',
    created_at            TIMESTAMPTZ DEFAULT now(),
    completed_at          TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_review_session_run ON ReviewSession(run_id);
CREATE INDEX IF NOT EXISTS idx_review_session_status ON ReviewSession(status, current_pass);
