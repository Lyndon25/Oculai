-- 006_functions.sql
-- Stored functions for multi-Agent DAG task operations.
-- Phase-era queue functions removed. New DAG task claim/complete/fail added.

-- ============================================================
-- Claim a batch of pending tasks (FOR UPDATE SKIP LOCKED)
-- ============================================================
CREATE OR REPLACE FUNCTION claim_task_batch(
    p_run_id      UUID,
    p_task_types  TEXT[],
    p_batch_size  INTEGER,
    p_agent_id    TEXT,
    p_timeout_min INTEGER DEFAULT 10
)
RETURNS SETOF Task
LANGUAGE plpgsql
AS $$
DECLARE
    v_deadline TIMESTAMPTZ;
BEGIN
    v_deadline := now() + (p_timeout_min || ' minutes')::INTERVAL;

    RETURN QUERY
    WITH batch AS (
        SELECT task_id
        FROM Task
        WHERE run_id = p_run_id
          AND task_type = ANY(p_task_types)
          AND status = 'pending'
          AND (retry_count < max_retries)
        ORDER BY priority DESC, created_at ASC
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE Task t
    SET status = 'claimed',
        claimed_by = p_agent_id,
        claimed_at = now(),
        updated_at = now(),
        updated_by_agent = p_agent_id,
        data_version = data_version + 1
    FROM batch
    WHERE t.task_id = batch.task_id
    RETURNING t.*;
END;
$$;

-- ============================================================
-- Complete a task and resolve downstream dependencies
-- ============================================================
CREATE OR REPLACE FUNCTION complete_task(
    p_task_id     UUID,
    p_output_data JSONB,
    p_agent_id    TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_plan_id UUID;
    v_step_key TEXT;
BEGIN
    -- Mark task as done
    UPDATE Task
    SET status = 'done',
        output_data = p_output_data,
        completed_at = now(),
        updated_at = now(),
        updated_by_agent = p_agent_id,
        data_version = data_version + 1
    WHERE task_id = p_task_id
    RETURNING plan_id, step_key INTO v_plan_id, v_step_key;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Task % not found', p_task_id;
    END IF;

    -- Resolve input references for dependent tasks
    UPDATE Task dep
    SET input_data = resolve_task_inputs(dep.task_id)
    FROM TaskDependency td
    WHERE td.task_id = dep.task_id
      AND td.depends_on_task_id = p_task_id
      AND dep.status = 'pending';

    -- Auto-unblock tasks whose dependencies are all done
    -- (status stays 'pending' — they are now claimable)
END;
$$;

-- ============================================================
-- Resolve $step_key.output_key references in a task's input_data
-- ============================================================
CREATE OR REPLACE FUNCTION resolve_task_inputs(
    p_task_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_input JSONB;
    v_dep RECORD;
BEGIN
    SELECT input_data INTO v_input FROM Task WHERE task_id = p_task_id;

    FOR v_dep IN
        SELECT td.input_mapping, t.output_data, t.step_key
        FROM TaskDependency td
        JOIN Task t ON t.task_id = td.depends_on_task_id
        WHERE td.task_id = p_task_id
    LOOP
        -- Template: $step_key.output_key → resolved value
        -- input_mapping defines {"param_name": "$step_key.field"}
        IF v_dep.input_mapping IS NOT NULL AND v_dep.input_mapping::text <> '{}' THEN
            v_input := v_input || jsonb_object_agg(
                m.key,
                jsonb_extract_path(v_dep.output_data, replace(m.value::text, '$' || v_dep.step_key || '.', ''))
            )
            FROM jsonb_each_text(v_dep.input_mapping) m;
        END IF;
    END LOOP;

    RETURN v_input;
END;
$$;

-- ============================================================
-- Mark a task as failed
-- ============================================================
CREATE OR REPLACE FUNCTION fail_task(
    p_task_id       UUID,
    p_error_message TEXT,
    p_agent_id      TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE Task
    SET status = CASE
            WHEN retry_count >= max_retries THEN 'error'::task_status_t
            ELSE 'pending'::task_status_t
        END,
        error_message = p_error_message,
        retry_count = retry_count + 1,
        failed_at = now(),
        claimed_by = NULL,
        claimed_at = NULL,
        updated_at = now(),
        updated_by_agent = p_agent_id,
        data_version = data_version + 1
    WHERE task_id = p_task_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Task % not found', p_task_id;
    END IF;
END;
$$;

-- ============================================================
-- Release stale claimed tasks (called by cron)
-- ============================================================
CREATE OR REPLACE FUNCTION release_stale_tasks()
RETURNS TABLE (
    released_id     UUID,
    released_status TEXT,
    released_retry  INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE Task t
    SET status = CASE
            WHEN retry_count >= max_retries THEN 'error'::task_status_t
            ELSE 'pending'::task_status_t
        END,
        claimed_by = NULL,
        claimed_at = NULL,
        retry_count = retry_count + 1,
        updated_at = now(),
        updated_by_agent = 'system::stale_release',
        data_version = data_version + 1
    WHERE status = 'claimed'
      AND claimed_at < (now() - INTERVAL '10 minutes')
    RETURNING t.task_id, t.status::TEXT, t.retry_count;
END;
$$;

-- ============================================================
-- Register data lineage relationship
-- ============================================================
CREATE OR REPLACE FUNCTION register_lineage(
    p_upstream_entity   TEXT,
    p_upstream_id       UUID,
    p_upstream_field    TEXT,
    p_downstream_entity TEXT,
    p_downstream_id     UUID,
    p_downstream_field  TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO DataLineage (
        upstream_entity, upstream_id, upstream_field,
        downstream_entity, downstream_id, downstream_field
    ) VALUES (
        p_upstream_entity, p_upstream_id, p_upstream_field,
        p_downstream_entity, p_downstream_id, p_downstream_field
    )
    ON CONFLICT (upstream_entity, upstream_id, upstream_field,
                 downstream_entity, downstream_id, downstream_field)
    DO NOTHING;
END;
$$;

-- ============================================================
-- Record a data conflict (multi-source disagreement)
-- ============================================================
CREATE OR REPLACE FUNCTION record_conflict(
    p_entity_type   TEXT,
    p_entity_id     UUID,
    p_field_name    TEXT,
    p_values_json   JSONB
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_conflict_id UUID;
    v_auto_score  REAL;
    v_suggested   JSONB;
BEGIN
    SELECT (v->>'confidence')::REAL, v
    INTO v_auto_score, v_suggested
    FROM jsonb_array_elements(p_values_json) v
    ORDER BY (v->>'confidence')::REAL DESC
    LIMIT 1;

    INSERT INTO DataConflict (
        entity_type, entity_id, field_name,
        values_json, auto_score, suggested_value
    ) VALUES (
        p_entity_type, p_entity_id, p_field_name,
        p_values_json, v_auto_score, v_suggested
    )
    RETURNING conflict_id INTO v_conflict_id;

    RETURN v_conflict_id;
END;
$$;

-- ============================================================
-- Classify change severity
-- ============================================================
CREATE OR REPLACE FUNCTION classify_change_severity(
    p_entity_type TEXT,
    p_field_name  TEXT,
    p_old_value   JSONB,
    p_new_value   JSONB
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_entity_type = 'CareerEvent' AND p_field_name IN ('institution', 'role') THEN
        RETURN 'major';
    END IF;

    IF p_entity_type = 'Person' AND p_field_name IN ('latest_institution', 'latest_position', 'email_hashes') THEN
        RETURN 'major';
    END IF;

    IF p_entity_type = 'AcademicWork' OR p_field_name IN ('total_papers', 'total_citations') THEN
        RETURN 'medium';
    END IF;

    RETURN 'minor';
END;
$$;

-- ============================================================
-- Check and consume data source quota
-- ============================================================
CREATE OR REPLACE FUNCTION check_datasource_quota(
    p_source_name TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_limit  INTEGER;
    v_used   INTEGER;
    v_reset  DATE;
BEGIN
    SELECT daily_limit, used_today, last_reset_at
    INTO v_limit, v_used, v_reset
    FROM DataSourceQuota
    WHERE source_name = p_source_name;

    IF NOT FOUND THEN
        RETURN true;
    END IF;

    IF v_reset < CURRENT_DATE THEN
        UPDATE DataSourceQuota
        SET used_today = 0, last_reset_at = CURRENT_DATE, updated_at = now()
        WHERE source_name = p_source_name;
        RETURN true;
    END IF;

    RETURN v_used < v_limit;
END;
$$;

CREATE OR REPLACE FUNCTION consume_datasource_quota(
    p_source_name TEXT,
    p_amount      INTEGER DEFAULT 1
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE DataSourceQuota
    SET used_today = used_today + p_amount,
        updated_at = now()
    WHERE source_name = p_source_name;
END;
$$;

-- ============================================================
-- Identity management (retained from Phase7)
-- ============================================================
CREATE OR REPLACE FUNCTION link_person_identity(
    p_person_id         UUID,
    p_source_type       TEXT,
    p_external_id       TEXT,
    p_external_url      TEXT DEFAULT NULL,
    p_is_primary        BOOLEAN DEFAULT false,
    p_confidence        REAL DEFAULT 1.0,
    p_verified_by_agent TEXT DEFAULT 'system'
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_identity_id UUID;
BEGIN
    INSERT INTO PersonExternalIdentity (
        person_id, source_type, external_id, external_url,
        is_primary, confidence, verified_at, verified_by_agent
    ) VALUES (
        p_person_id, p_source_type, p_external_id, p_external_url,
        p_is_primary, p_confidence, now(), p_verified_by_agent
    )
    ON CONFLICT (source_type, external_id)
    DO UPDATE SET
        person_id = EXCLUDED.person_id,
        external_url = COALESCE(EXCLUDED.external_url, PersonExternalIdentity.external_url),
        is_primary = EXCLUDED.is_primary,
        confidence = EXCLUDED.confidence,
        verified_at = now(),
        verified_by_agent = EXCLUDED.verified_by_agent
    RETURNING identity_id INTO v_identity_id;

    RETURN v_identity_id;
END;
$$;

CREATE OR REPLACE FUNCTION find_person_by_identity(
    p_source_type TEXT,
    p_external_id TEXT
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_person_id UUID;
BEGIN
    SELECT person_id INTO v_person_id
    FROM PersonExternalIdentity
    WHERE source_type = p_source_type
      AND external_id = p_external_id
    LIMIT 1;

    RETURN v_person_id;
END;
$$;

-- ============================================================
-- Merge candidate data into an existing Person row
-- Only overwrites NULL fields; conflicting non-NULL values → DataConflict
-- ============================================================
CREATE OR REPLACE FUNCTION merge_person_data(
    p_person_id       UUID,
    p_institution     TEXT DEFAULT NULL,
    p_total_papers    INTEGER DEFAULT NULL,
    p_h_index         INTEGER DEFAULT NULL,
    p_total_citations INTEGER DEFAULT NULL,
    p_orcid           TEXT DEFAULT NULL,
    p_gs_id           TEXT DEFAULT NULL,
    p_github_id       TEXT DEFAULT NULL,
    p_linkedin_url    TEXT DEFAULT NULL,
    p_agent_id        TEXT DEFAULT 'system'
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_old RECORD;
BEGIN
    SELECT latest_institution, total_papers, h_index, total_citations
    INTO v_old
    FROM Person
    WHERE person_id = p_person_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Person % not found', p_person_id;
    END IF;

    UPDATE Person
    SET latest_institution     = COALESCE(latest_institution, p_institution),
        total_papers           = COALESCE(total_papers, p_total_papers),
        h_index                = COALESCE(h_index, p_h_index),
        total_citations        = COALESCE(total_citations, p_total_citations),
        orcid                  = COALESCE(orcid, p_orcid),
        google_scholar_id      = COALESCE(google_scholar_id, p_gs_id),
        github_id              = COALESCE(github_id, p_github_id),
        linkedin_url           = COALESCE(linkedin_url, p_linkedin_url),
        updated_at             = now(),
        updated_by_agent       = p_agent_id,
        data_version           = data_version + 1
    WHERE person_id = p_person_id;

    -- Record conflicts for non-NULL disagreements
    IF v_old.latest_institution IS NOT NULL AND p_institution IS NOT NULL
       AND v_old.latest_institution <> p_institution THEN
        PERFORM record_conflict('Person', p_person_id, 'latest_institution',
            jsonb_build_array(
                jsonb_build_object('value', v_old.latest_institution, 'confidence', 0.8, 'source', 'existing'),
                jsonb_build_object('value', p_institution, 'confidence', 0.8, 'source', 'new')
            ));
    END IF;

    IF v_old.h_index IS NOT NULL AND p_h_index IS NOT NULL
       AND v_old.h_index <> p_h_index THEN
        PERFORM record_conflict('Person', p_person_id, 'h_index',
            jsonb_build_array(
                jsonb_build_object('value', v_old.h_index, 'confidence', 0.8, 'source', 'existing'),
                jsonb_build_object('value', p_h_index, 'confidence', 0.8, 'source', 'new')
            ));
    END IF;

    IF v_old.total_papers IS NOT NULL AND p_total_papers IS NOT NULL
       AND v_old.total_papers <> p_total_papers THEN
        PERFORM record_conflict('Person', p_person_id, 'total_papers',
            jsonb_build_array(
                jsonb_build_object('value', v_old.total_papers, 'confidence', 0.8, 'source', 'existing'),
                jsonb_build_object('value', p_total_papers, 'confidence', 0.8, 'source', 'new')
            ));
    END IF;

    IF v_old.total_citations IS NOT NULL AND p_total_citations IS NOT NULL
       AND v_old.total_citations <> p_total_citations THEN
        PERFORM record_conflict('Person', p_person_id, 'total_citations',
            jsonb_build_array(
                jsonb_build_object('value', v_old.total_citations, 'confidence', 0.8, 'source', 'existing'),
                jsonb_build_object('value', p_total_citations, 'confidence', 0.8, 'source', 'new')
            ));
    END IF;
END;
$$;

-- ============================================================
-- Find person by fuzzy name + institution (trigram similarity)
-- ============================================================
CREATE OR REPLACE FUNCTION find_person_by_fuzzy_name(
    p_name        TEXT,
    p_institution TEXT DEFAULT NULL,
    p_threshold   REAL DEFAULT 0.7
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_person_id UUID;
BEGIN
    SELECT person_id INTO v_person_id
    FROM Person
    WHERE similarity(canonical_name, p_name) > p_threshold
      AND (p_institution IS NULL OR latest_institution ILIKE '%' || p_institution || '%')
    ORDER BY similarity(canonical_name, p_name) DESC
    LIMIT 1;

    RETURN v_person_id;
END;
$$;

-- ============================================================
-- Find person by name + institution (exact-ish match)
-- ============================================================
CREATE OR REPLACE FUNCTION find_person_by_name_institution(
    p_name        TEXT,
    p_institution TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_person_id UUID;
BEGIN
    SELECT person_id INTO v_person_id
    FROM Person
    WHERE canonical_name ILIKE '%' || p_name || '%'
      AND (p_institution IS NULL OR latest_institution ILIKE '%' || p_institution || '%')
    LIMIT 1;

    RETURN v_person_id;
END;
$$;
