-- 004_indexes.sql
-- Performance-critical indexes for Oculai multi-Agent system.
-- Phase-era indexes on JobRecord and CandidateQueue removed.
-- New Task-focused indexes added.

-- ============================================================
-- Person indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_person_pool_tags ON Person USING GIN (pool_tags);
CREATE INDEX IF NOT EXISTS idx_person_aliases ON Person USING GIN (aliases);
CREATE INDEX IF NOT EXISTS idx_person_email_hashes ON Person USING GIN (email_hashes);
CREATE INDEX IF NOT EXISTS idx_person_name_trgm ON Person USING GIN (canonical_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_person_watch_level ON Person (watch_level);
CREATE INDEX IF NOT EXISTS idx_person_freshness_score ON Person (freshness_score);
CREATE INDEX IF NOT EXISTS idx_person_confidence_score ON Person (confidence_score);
CREATE INDEX IF NOT EXISTS idx_person_h_index ON Person (h_index DESC);
CREATE INDEX IF NOT EXISTS idx_person_total_citations ON Person (total_citations DESC);
CREATE INDEX IF NOT EXISTS idx_person_last_active_date ON Person (last_active_date DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_person_orcid ON Person (orcid) WHERE orcid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_person_google_scholar ON Person (google_scholar_id) WHERE google_scholar_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_person_linkedin ON Person (linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_person_github ON Person (github_id) WHERE github_id IS NOT NULL;

-- ============================================================
-- PersonProfile indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_profile_person ON PersonProfile (person_id);
CREATE INDEX IF NOT EXISTS idx_profile_captured_at ON PersonProfile (captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_profile_hash ON PersonProfile (raw_data_hash);
CREATE INDEX IF NOT EXISTS idx_profile_career_stage ON PersonProfile (career_stage);

-- ============================================================
-- AcademicWork indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_work_person ON AcademicWork (person_id);
CREATE INDEX IF NOT EXISTS idx_work_type ON AcademicWork (type);
CREATE INDEX IF NOT EXISTS idx_work_year ON AcademicWork (year DESC);
CREATE INDEX IF NOT EXISTS idx_work_citations ON AcademicWork (citations DESC);
CREATE INDEX IF NOT EXISTS idx_work_venue ON AcademicWork (venue);
CREATE INDEX IF NOT EXISTS idx_work_relevance ON AcademicWork (relevance_score DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_doi ON AcademicWork (doi) WHERE doi IS NOT NULL;

-- ============================================================
-- NetworkEdge indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_edge_source ON NetworkEdge (source_person_id);
CREATE INDEX IF NOT EXISTS idx_edge_target ON NetworkEdge (target_person_id);
CREATE INDEX IF NOT EXISTS idx_edge_relation_type ON NetworkEdge (relation_type);
CREATE INDEX IF NOT EXISTS idx_edge_strength ON NetworkEdge (strength DESC);
CREATE INDEX IF NOT EXISTS idx_edge_active ON NetworkEdge (is_active) WHERE is_active = true;

-- ============================================================
-- CareerEvent indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_event_person ON CareerEvent (person_id);
CREATE INDEX IF NOT EXISTS idx_event_type ON CareerEvent (event_type);
CREATE INDEX IF NOT EXISTS idx_event_dates ON CareerEvent (start_date DESC, end_date DESC);
CREATE INDEX IF NOT EXISTS idx_event_current ON CareerEvent (person_id) WHERE is_current = true;
CREATE INDEX IF NOT EXISTS idx_event_verified ON CareerEvent (verified_by_human) WHERE verified_by_human = false;

-- ============================================================
-- SourcingRun indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_run_status ON SourcingRun (status);
CREATE INDEX IF NOT EXISTS idx_run_created_by ON SourcingRun (created_by);
CREATE INDEX IF NOT EXISTS idx_run_created_at ON SourcingRun (created_at DESC);

-- ============================================================
-- CandidateRecord indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_cr_run ON CandidateRecord (run_id);
CREATE INDEX IF NOT EXISTS idx_cr_person ON CandidateRecord (person_id);
CREATE INDEX IF NOT EXISTS idx_cr_status ON CandidateRecord (run_id, status);
CREATE INDEX IF NOT EXISTS idx_cr_quality ON CandidateRecord (quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_cr_locked_by ON CandidateRecord (locked_by_agent) WHERE locked_by_agent IS NOT NULL;

-- ============================================================
-- Plan indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_plan_run ON Plan (run_id);
CREATE INDEX IF NOT EXISTS idx_plan_status ON Plan (status);

-- ============================================================
-- Task indexes (concurrency-sensitive)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_task_plan_status ON Task (plan_id, status);
CREATE INDEX IF NOT EXISTS idx_task_run_type ON Task (run_id, task_type, status);
CREATE INDEX IF NOT EXISTS idx_task_claim ON Task (run_id, status, priority DESC, created_at ASC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_task_claimed ON Task (claimed_by, status) WHERE claimed_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_task_failed ON Task (status, retry_count) WHERE status = 'error';

-- ============================================================
-- TaskDependency indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_taskdep_plan ON TaskDependency (plan_id);
CREATE INDEX IF NOT EXISTS idx_taskdep_task ON TaskDependency (task_id);
CREATE INDEX IF NOT EXISTS idx_taskdep_depends ON TaskDependency (depends_on_task_id);

-- ============================================================
-- Evidence indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_evidence_person ON Evidence (person_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON Evidence (run_id) WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_type ON Evidence (evidence_type);

-- ============================================================
-- CandidateAssessment indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_assess_run_person ON CandidateAssessment (run_id, person_id);
CREATE INDEX IF NOT EXISTS idx_assess_dimension ON CandidateAssessment (dimension);

-- ============================================================
-- OutreachRecord indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_or_person ON OutreachRecord (person_id);
CREATE INDEX IF NOT EXISTS idx_or_run ON OutreachRecord (run_id);
CREATE INDEX IF NOT EXISTS idx_or_status ON OutreachRecord (status);
CREATE INDEX IF NOT EXISTS idx_or_channel ON OutreachRecord (channel);
CREATE INDEX IF NOT EXISTS idx_or_sent_at ON OutreachRecord (sent_at DESC);

-- ============================================================
-- HumanApproval indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_approval_run ON HumanApproval (run_id);
CREATE INDEX IF NOT EXISTS idx_approval_status ON HumanApproval (status);

-- ============================================================
-- FeedbackEvent indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_fe_person ON FeedbackEvent (person_id);
CREATE INDEX IF NOT EXISTS idx_fe_run ON FeedbackEvent (run_id);
CREATE INDEX IF NOT EXISTS idx_fe_type ON FeedbackEvent (event_type);
CREATE INDEX IF NOT EXISTS idx_fe_provided_at ON FeedbackEvent (provided_at DESC);

-- ============================================================
-- TaskIteration indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_task_iteration_task ON TaskIteration (task_id, iteration_number);
CREATE INDEX IF NOT EXISTS idx_task_iteration_type ON TaskIteration (iteration_type, created_at);
CREATE INDEX IF NOT EXISTS idx_task_iteration_decision ON TaskIteration (decision, created_at);

-- ============================================================
-- AgentBroadcast indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_broadcast_run ON AgentBroadcast (run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_broadcast_discovered_by ON AgentBroadcast (run_id, discovered_by, created_at DESC);

-- ============================================================
-- SearchQueryLog indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_sql_source ON SearchQueryLog (source_name, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_sql_status ON SearchQueryLog (status);
CREATE INDEX IF NOT EXISTS idx_sql_run ON SearchQueryLog (run_id) WHERE run_id IS NOT NULL;

-- ============================================================
-- Vector indexes (IVFFlat for semantic search)
-- ============================================================
DO $$
BEGIN
    CREATE INDEX IF NOT EXISTS idx_person_embedding ON Person USING ivfflat (research_direction_embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_work_abstract_embedding ON AcademicWork USING ivfflat (abstract_embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_work_title_embedding ON AcademicWork USING ivfflat (title_embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_work_topic_vector ON AcademicWork USING ivfflat (topic_vector vector_cosine_ops);
EXCEPTION WHEN undefined_object THEN
    RAISE NOTICE 'pgvector not available, skipping IVFFlat indexes';
END;
$$;
