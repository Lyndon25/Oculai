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
  record_id?: string;
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
  created_at?: string;
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

// ---- Live Agent Dashboard Types ----

export interface SubagentState {
  agentId: string;
  agentType: string;
  target: string;
  status: "idle" | "active" | "done" | "error";
  resultCount?: number;
  spawnedAt?: string;
  completedAt?: string;
  error?: string;
}

export interface ActivityEntry {
  timestamp: string;
  agentId?: string;
  agentType?: string;
  action: "think" | "search" | "found" | "classify" | "broadcast" | "upsert" | "score" | "audit" | "export" | "error";
  message: string;
  detail?: string;
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
