-- 006_functions.sql
-- Stored functions for single-agent recruitment workflow.
-- Multi-agent DAG task claim/complete/fail functions removed.

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
