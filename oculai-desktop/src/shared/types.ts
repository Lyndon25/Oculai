/** Shared domain types between main and renderer processes. */

export interface SourcingRun {
  run_id: string;
  title: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  candidate_count?: number;
  task_count?: number;
  completed_task_count?: number;
  active_plan_id?: string;
}

export type RunStatus = "draft" | "running" | "paused" | "reviewing" | "completed" | "aborted";

export interface Candidate {
  person_id: string;
  canonical_name: string;
  latest_institution?: string;
  latest_position?: string;
  h_index?: number;
  total_papers?: number;
  total_citations?: number;
  status: CandidateStatus;
  quality_score?: number;
  research_areas?: string[];
  github_id?: string;
  google_scholar_id?: string;
  identities?: PersonIdentity[];
}

export type CandidateStatus =
  | "pending"
  | "processing"
  | "reviewing"
  | "shortlisted"
  | "rejected"
  | "contacted"
  | "hired";

export interface PersonIdentity {
  source_type: string;
  external_id: string;
  external_url?: string;
  is_primary: boolean;
  confidence: number;
}

export interface Evidence {
  evidence_id: string;
  person_id: string;
  evidence_type: string;
  title: string;
  description?: string;
  source_name: string;
  source_url?: string;
  confidence: number;
  tier: number;
  quality_flags?: string[];
  captured_at: string;
}

export interface Assessment {
  assessment_id: string;
  run_id: string;
  person_id: string;
  assessor_agent: string;
  dimension: string;
  score: number;
  confidence: number;
  rationale?: string;
  evidence_ids?: string[];
}

export interface CandidateDetail extends Candidate {
  identities: PersonIdentity[];
  evidence: Evidence[];
  assessments: Assessment[];
  academic_works?: AcademicWork[];
  career_events?: CareerEvent[];
  score_history?: ScoreHistoryEntry[];
}

export interface AcademicWork {
  work_id: string;
  title: string;
  type: string;
  venue?: string;
  year?: number;
  citations?: number;
  doi?: string;
  url?: string;
}

export interface CareerEvent {
  event_id: string;
  event_type: string;
  institution?: string;
  role?: string;
  start_date?: string;
  end_date?: string;
  is_current: boolean;
}

export interface ScoreHistoryEntry {
  history_id: string;
  dimension: string;
  previous_score?: number;
  new_score: number;
  previous_confidence?: number;
  new_confidence: number;
  assessor_agent: string;
  changed_at: string;
  change_reason?: string;
}

export interface PlanTask {
  task_id: string;
  task_type: string;
  task_name: string;
  step_key?: string;
  status: TaskStatus;
  priority: number;
  agent_id?: string;
  claimed_by?: string;
  retry_count: number;
  max_retries: number;
  error_message?: string;
}

export type TaskStatus = "pending" | "claimed" | "processing" | "done" | "error" | "timeout" | "skipped";

export interface PipelineState {
  run_id: string;
  phase: PipelinePhase;
  plan_id?: string;
  tasks: PlanTask[];
  task_progress: { total: number; completed: number; failed: number; pending: number };
  subagents: SubagentState[];
  metrics: QualityMetrics;
}

export type PipelinePhase =
  | "init"
  | "strategy"
  | "searching"
  | "identity_resolution"
  | "enrichment"
  | "evaluation"
  | "audit"
  | "shortlist"
  | "outreach"
  | "complete";

export interface SubagentState {
  name: string;
  status: "idle" | "running" | "done" | "error";
  task_count?: number;
  iterations?: number;
  last_output?: string;
}

export interface QualityMetrics {
  extraction_quality_score?: number;
  cross_source_verified?: number;
  false_positive_rate?: number;
  china_platform_coverage?: number;
  total_candidates?: number;
}

export interface SourceCapability {
  name: string;
  type: string;
  supported_operations: string[];
  auth_required: boolean;
  capabilities: Record<string, unknown>;
}

export interface SystemStatus {
  db: "disconnected" | "connecting" | "connected" | "error";
  python: "stopped" | "starting" | "ready" | "error";
  llm: "unconfigured" | "configured" | "error";
  dbPort?: number;
  pythonPid?: number;
}
