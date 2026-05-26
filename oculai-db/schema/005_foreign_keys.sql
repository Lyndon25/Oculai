-- 005_foreign_keys.sql
-- All foreign key constraints. CandidateQueue FKs removed.
-- Task DAG FKs added.

-- PersonProfile → Person
ALTER TABLE PersonProfile
    ADD CONSTRAINT fk_profile_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- AcademicWork → Person
ALTER TABLE AcademicWork
    ADD CONSTRAINT fk_work_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- NetworkEdge → Person (both directions)
ALTER TABLE NetworkEdge
    ADD CONSTRAINT fk_edge_source FOREIGN KEY (source_person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_edge_target FOREIGN KEY (target_person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE,
    ADD CONSTRAINT chk_no_self_loop CHECK (source_person_id <> target_person_id);

-- CareerEvent → Person
ALTER TABLE CareerEvent
    ADD CONSTRAINT fk_event_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- CandidateRecord → SourcingRun
ALTER TABLE CandidateRecord
    ADD CONSTRAINT fk_cr_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE CASCADE;

-- CandidateRecord → Person
ALTER TABLE CandidateRecord
    ADD CONSTRAINT fk_cr_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- Plan → SourcingRun
ALTER TABLE Plan
    ADD CONSTRAINT fk_plan_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE CASCADE;

-- SourcingRun.active_plan_id → Plan (nullable, set after plan generation)
ALTER TABLE SourcingRun
    ADD CONSTRAINT fk_run_active_plan FOREIGN KEY (active_plan_id)
        REFERENCES Plan (plan_id) ON DELETE SET NULL;

-- Task → Plan
ALTER TABLE Task
    ADD CONSTRAINT fk_task_plan FOREIGN KEY (plan_id)
        REFERENCES Plan (plan_id) ON DELETE CASCADE;

-- Task → SourcingRun
ALTER TABLE Task
    ADD CONSTRAINT fk_task_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE CASCADE;

-- TaskDependency → Plan
ALTER TABLE TaskDependency
    ADD CONSTRAINT fk_taskdep_plan FOREIGN KEY (plan_id)
        REFERENCES Plan (plan_id) ON DELETE CASCADE;

-- TaskDependency → Task (task)
ALTER TABLE TaskDependency
    ADD CONSTRAINT fk_taskdep_task FOREIGN KEY (task_id)
        REFERENCES Task (task_id) ON DELETE CASCADE;

-- TaskDependency → Task (depends_on)
ALTER TABLE TaskDependency
    ADD CONSTRAINT fk_taskdep_depends FOREIGN KEY (depends_on_task_id)
        REFERENCES Task (task_id) ON DELETE CASCADE,
    ADD CONSTRAINT chk_no_self_dep CHECK (task_id <> depends_on_task_id);

-- Evidence → Person
ALTER TABLE Evidence
    ADD CONSTRAINT fk_evidence_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- Evidence → SourcingRun (optional)
ALTER TABLE Evidence
    ADD CONSTRAINT fk_evidence_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE SET NULL;

-- CandidateAssessment → SourcingRun
ALTER TABLE CandidateAssessment
    ADD CONSTRAINT fk_assess_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE CASCADE;

-- CandidateAssessment → Person
ALTER TABLE CandidateAssessment
    ADD CONSTRAINT fk_assess_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- OutreachRecord → Person
ALTER TABLE OutreachRecord
    ADD CONSTRAINT fk_or_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- OutreachRecord → SourcingRun
ALTER TABLE OutreachRecord
    ADD CONSTRAINT fk_or_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE CASCADE;

-- HumanApproval → SourcingRun
ALTER TABLE HumanApproval
    ADD CONSTRAINT fk_approval_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE CASCADE;

-- FeedbackEvent → Person
ALTER TABLE FeedbackEvent
    ADD CONSTRAINT fk_fe_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- FeedbackEvent → SourcingRun
ALTER TABLE FeedbackEvent
    ADD CONSTRAINT fk_fe_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE CASCADE;

-- PersonExternalIdentity → Person
ALTER TABLE PersonExternalIdentity
    ADD CONSTRAINT fk_pei_person FOREIGN KEY (person_id)
        REFERENCES Person (person_id) ON DELETE CASCADE;

-- SearchQueryLog → SourcingRun (optional)
ALTER TABLE SearchQueryLog
    ADD CONSTRAINT fk_sql_run FOREIGN KEY (run_id)
        REFERENCES SourcingRun (run_id) ON DELETE SET NULL;
