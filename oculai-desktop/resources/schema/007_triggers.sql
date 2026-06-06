-- 007_triggers.sql
-- All triggers: audit, cache invalidation, changelog, lineage recalculation.
-- Phase-era queue auto-generation trigger REMOVED.

-- ============================================================
-- 1. Universal audit trigger: auto-maintain updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION trg_audit_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Register on all core tables
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY[
            'person','personprofile','academicwork','networkedge','careerevent',
            'sourcingrun','candidaterecord','plan','task','evidence',
            'candidateassessment','outreachrecord','humanapproval','feedbackevent','searchquerylog'
        ])
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS %I ON %I; CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trg_audit_updated_at()',
            'trg_audit_' || t, t, 'trg_audit_' || t, t
        );
    END LOOP;
END;
$$;

-- ============================================================
-- 2. data_version auto-increment on every UPDATE
-- ============================================================
CREATE OR REPLACE FUNCTION trg_increment_data_version()
RETURNS TRIGGER AS $$
BEGIN
    NEW.data_version := OLD.data_version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY[
            'person','personprofile','academicwork','networkedge','careerevent',
            'sourcingrun','candidaterecord','plan','task','evidence',
            'candidateassessment','outreachrecord','humanapproval','feedbackevent','searchquerylog'
        ])
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS %I ON %I; CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION trg_increment_data_version()',
            'trg_dv_' || t, t, 'trg_dv_' || t, t
        );
    END LOOP;
END;
$$;

-- ============================================================
-- 3. Cache invalidation via LISTEN/NOTIFY
-- ============================================================
CREATE OR REPLACE FUNCTION trg_cache_inval_person()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('cache_inval_person', OLD.person_id::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('cache_inval_person', NEW.person_id::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cache_inval_person ON Person;
CREATE TRIGGER trg_cache_inval_person
    AFTER INSERT OR UPDATE OR DELETE ON Person
    FOR EACH ROW
    EXECUTE FUNCTION trg_cache_inval_person();

CREATE OR REPLACE FUNCTION trg_cache_inval_profile()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('cache_inval_profile', OLD.person_id::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('cache_inval_profile', NEW.person_id::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cache_inval_profile ON PersonProfile;
CREATE TRIGGER trg_cache_inval_profile
    AFTER INSERT OR UPDATE OR DELETE ON PersonProfile
    FOR EACH ROW
    EXECUTE FUNCTION trg_cache_inval_profile();

CREATE OR REPLACE FUNCTION trg_cache_inval_work()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('cache_inval_work', OLD.person_id::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('cache_inval_work', NEW.person_id::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cache_inval_work ON AcademicWork;
CREATE TRIGGER trg_cache_inval_work
    AFTER INSERT OR UPDATE OR DELETE ON AcademicWork
    FOR EACH ROW
    EXECUTE FUNCTION trg_cache_inval_work();

CREATE OR REPLACE FUNCTION trg_cache_inval_event()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('cache_inval_event', OLD.person_id::text);
        RETURN OLD;
    ELSE
        PERFORM pg_notify('cache_inval_event', NEW.person_id::text);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cache_inval_event ON CareerEvent;
CREATE TRIGGER trg_cache_inval_event
    AFTER INSERT OR UPDATE OR DELETE ON CareerEvent
    FOR EACH ROW
    EXECUTE FUNCTION trg_cache_inval_event();

-- ============================================================
-- 4. ChangeLog triggers
-- ============================================================
CREATE OR REPLACE FUNCTION trg_changelog_person()
RETURNS TRIGGER AS $$
DECLARE
    v_severity TEXT;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.h_index <> OLD.h_index THEN
            v_severity := classify_change_severity('Person', 'h_index',
                to_jsonb(OLD.h_index), to_jsonb(NEW.h_index));
            INSERT INTO ChangeLog (entity_type, entity_id, field_name, old_value, new_value, severity,
                diff_summary, detected_by_agent)
            VALUES ('Person', NEW.person_id, 'h_index',
                to_jsonb(OLD.h_index), to_jsonb(NEW.h_index), v_severity,
                'h-index: ' || OLD.h_index || ' → ' || NEW.h_index, NEW.updated_by_agent);
        END IF;

        IF NEW.latest_institution IS DISTINCT FROM OLD.latest_institution THEN
            v_severity := classify_change_severity('Person', 'latest_institution',
                to_jsonb(OLD.latest_institution), to_jsonb(NEW.latest_institution));
            INSERT INTO ChangeLog (entity_type, entity_id, field_name, old_value, new_value, severity,
                diff_summary, detected_by_agent)
            VALUES ('Person', NEW.person_id, 'latest_institution',
                to_jsonb(OLD.latest_institution), to_jsonb(NEW.latest_institution), v_severity,
                'Institution: ' || COALESCE(OLD.latest_institution, 'NULL') || ' → ' || COALESCE(NEW.latest_institution, 'NULL'),
                NEW.updated_by_agent);
        END IF;

        IF NEW.latest_position IS DISTINCT FROM OLD.latest_position THEN
            v_severity := classify_change_severity('Person', 'latest_position',
                to_jsonb(OLD.latest_position), to_jsonb(NEW.latest_position));
            INSERT INTO ChangeLog (entity_type, entity_id, field_name, old_value, new_value, severity,
                diff_summary, detected_by_agent)
            VALUES ('Person', NEW.person_id, 'latest_position',
                to_jsonb(OLD.latest_position), to_jsonb(NEW.latest_position), v_severity,
                'Position: ' || COALESCE(OLD.latest_position, 'NULL') || ' → ' || COALESCE(NEW.latest_position, 'NULL'),
                NEW.updated_by_agent);
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_changelog_person ON Person;
CREATE TRIGGER trg_changelog_person
    AFTER UPDATE OR DELETE ON Person
    FOR EACH ROW
    EXECUTE FUNCTION trg_changelog_person();

CREATE OR REPLACE FUNCTION trg_changelog_careerevent()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO ChangeLog (entity_type, entity_id, field_name, old_value, new_value, severity,
            diff_summary, detected_by_agent)
        VALUES ('CareerEvent', NEW.person_id, NEW.event_type::TEXT,
            NULL, to_jsonb(NEW), 'major',
            'New ' || NEW.event_type::TEXT || ' at ' || COALESCE(NEW.institution, 'unknown'),
            NEW.created_by_agent);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_changelog_careerevent ON CareerEvent;
CREATE TRIGGER trg_changelog_careerevent
    AFTER INSERT ON CareerEvent
    FOR EACH ROW
    EXECUTE FUNCTION trg_changelog_careerevent();

CREATE OR REPLACE FUNCTION trg_changelog_academicwork()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO ChangeLog (entity_type, entity_id, field_name, old_value, new_value, severity,
            diff_summary, detected_by_agent)
        VALUES ('AcademicWork', NEW.person_id, 'new_publication',
            NULL, jsonb_build_object('title', NEW.title, 'venue', NEW.venue, 'year', NEW.year),
            'medium',
            'New ' || NEW.type::TEXT || ': ' || COALESCE(NEW.title, 'untitled'),
            NEW.created_by_agent);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_changelog_academicwork ON AcademicWork;
CREATE TRIGGER trg_changelog_academicwork
    AFTER INSERT ON AcademicWork
    FOR EACH ROW
    EXECUTE FUNCTION trg_changelog_academicwork();

-- ============================================================
-- 5. Lineage-based recalculation trigger
-- ============================================================
CREATE OR REPLACE FUNCTION trg_lineage_recalc_person()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.h_index <> OLD.h_index OR
        NEW.total_papers <> OLD.total_papers OR
        NEW.total_citations <> OLD.total_citations OR
        NEW.research_direction_embedding IS DISTINCT FROM OLD.research_direction_embedding
    ) THEN
        INSERT INTO RecalculationQueue (record_id, reason, priority)
        SELECT cr.record_id,
               'upstream_change:Person.' ||
               CASE
                   WHEN NEW.h_index <> OLD.h_index THEN 'h_index'
                   WHEN NEW.total_papers <> OLD.total_papers THEN 'total_papers'
                   WHEN NEW.total_citations <> OLD.total_citations THEN 'total_citations'
                   ELSE 'research_direction_embedding'
               END,
               7
        FROM CandidateRecord cr
        WHERE cr.person_id = NEW.person_id
          AND cr.status IN ('pending', 'processing', 'reviewing')
        ON CONFLICT DO NOTHING;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_lineage_recalc_person ON Person;
CREATE TRIGGER trg_lineage_recalc_person
    AFTER UPDATE ON Person
    FOR EACH ROW
    EXECUTE FUNCTION trg_lineage_recalc_person();

-- ============================================================
-- 6. Task done → notify for downstream processing
-- ============================================================
CREATE OR REPLACE FUNCTION trg_task_done_notify()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'done' AND OLD.status <> 'done' THEN
        PERFORM pg_notify('task_done', json_build_object(
            'task_id', NEW.task_id,
            'plan_id', NEW.plan_id,
            'run_id', NEW.run_id,
            'task_type', NEW.task_type,
            'step_key', NEW.step_key
        )::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_task_done ON Task;
CREATE TRIGGER trg_task_done
    AFTER UPDATE ON Task
    FOR EACH ROW
    EXECUTE FUNCTION trg_task_done_notify();
