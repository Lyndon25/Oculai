# Database State Model (Conceptual)

This is a conceptual overview. Full schema is in `oculai-db/schema/`. The main Agent interacts with the database exclusively through MCP tools — never raw SQL.

## Core Entities

### SourcingRun
One complete sourcing execution. Created by `oculai_create_run`.
- `run_id`, `title`, `status`, `target_profile`, `config`
- `active_plan_id` → references the current Plan

### Plan
Execution plan with task DAG. Created by `oculai_checkpoint_plan`.
- `plan_id`, `run_id`, `planner_state_json`, `status`, `strategy_summary`
- One Plan per Run (re-plan creates a new Plan)

### Task
Individual unit of work. Created as part of `oculai_checkpoint_plan`.
- `task_id`, `plan_id`, `run_id`, `task_type` (free-form TEXT), `task_name`, `step_key`
- `status`: pending → claimed → done (or error)
- `input_data`, `output_data` (JSONB)
- `priority`, `retry_count`, `max_retries`
- Claimed via `FOR UPDATE SKIP LOCKED` — safe for concurrent agents

### TaskDependency
DAG edge. Created as part of `oculai_checkpoint_plan`.
- `task_id` → `depends_on_task_id`
- `input_mapping`: maps upstream output keys to downstream input keys

### Person
Lifelong candidate entity. Created/updated by `oculai_upsert_candidate`.
- `person_id`, `canonical_name`, `aliases`
- `orcid`, `google_scholar_id`, `github_id`, `linkedin_url`
- Aggregated metrics: `h_index`, `total_papers`, `total_citations`
- `research_direction_embedding` (vector for semantic search)

### CandidateRecord
Links a Person to a SourcingRun. Created by `oculai_upsert_candidate`.
- `record_id`, `run_id`, `person_id`
- `status`: pending → shortlisted → contacted → hired
- `raw_data`, `enriched_data`, `match_scores`

### Evidence
Structured evidence for a candidate. Created by `oculai_attach_evidence`.
- `evidence_id`, `person_id`, `run_id`, `evidence_type`
- `title`, `source_url`, `source_name`, `content` (JSONB), `confidence`

### CandidateAssessment
Scored evaluation. Created by `oculai_record_assessment`.
- `assessment_id`, `run_id`, `person_id`, `assessor_agent`
- `dimension`, `score` (0-10), `confidence`, `rationale`, `evidence_ids`

### HumanApproval
Approval gate. Created by `oculai_request_human_approval`.
- `approval_id`, `run_id`, `action_type`, `action_context`
- `status`: pending → approved / denied

## Supporting Entities

- **PersonExternalIdentity**: Cross-platform identity linking (ORCID, GitHub, etc.)
- **PersonProfile**: Versioned snapshots of candidate profiles
- **AcademicWork**: Papers, patents, books
- **NetworkEdge**: Collaboration graph
- **CareerEvent**: Education/employment timeline
- **OutreachRecord**: Communication tracking
- **FeedbackEvent**: Closed-loop feedback
- **DataConflict**: Multi-source disagreements
- **ChangeLog**: Field-level change history
- **DataLineage**: Upstream→downstream dependency tracking
- **DataSourceQuota**: Rate limiting per source
- **SearchQueryLog**: Observability

## State Transitions

### Task Lifecycle
```
pending → claimed → done
                  → error (retry) → pending
                  → error (max retries) → terminal error
```

### CandidateRecord Lifecycle
```
pending → processing → reviewing → shortlisted → contacted → hired
                                       ↘ rejected
```

### Run Lifecycle
```
draft → running → reviewing → completed
                → paused
                → aborted
```
