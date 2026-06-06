/** Event payload types for IPC communication. */

import type {
  Candidate,
  CandidateDetail,
  Evidence,
  PipelineState,
  QualityMetrics,
  SourcingRun,
  SubagentState,
  SystemStatus,
} from "./types.js";

// ---- Agent streaming events ----

export interface AgentThinkingEvent {
  delta: string;
}

export interface AgentMessageEvent {
  text: string;
}

export interface AgentToolCallEvent {
  toolName: string;
  input: Record<string, unknown>;
}

export interface AgentToolResultEvent {
  toolName: string;
  output: Record<string, unknown>;
  isError: boolean;
}

// ---- Run events ----

export interface RunCreatedEvent {
  runId: string;
  title: string;
  status: string;
}

export interface RunStateEvent {
  run: SourcingRun;
  pipeline?: PipelineState;
}

export interface RunErrorEvent {
  runId: string;
  error: string;
  phase: string;
}

// ---- Candidate events ----

export interface CandidateUpsertedEvent {
  personId: string;
  name: string;
  institution?: string;
  sourceName: string;
}

export interface CandidateScoredEvent {
  personId: string;
  scores: Record<string, number>;
  overall: number;
  assessorAgent: string;
}

// ---- Evidence events ----

export interface EvidenceAttachedEvent {
  evidenceId: string;
  personId: string;
  type: string;
  tier: number;
  sourceName: string;
}

// ---- Pipeline events ----

export interface PipelineUpdateEvent {
  runId: string;
  phase: string;
  taskProgress: { total: number; completed: number; failed: number; pending: number };
  subagents: SubagentState[];
  metrics: QualityMetrics;
}

export interface TaskUpdatedEvent {
  taskId: string;
  taskType: string;
  taskName: string;
  status: string;
  agentId?: string;
}

export interface IterationRecordedEvent {
  taskId: string;
  iterationNumber: number;
  iterationType: string;
  decision?: string;
}

// ---- Report events ----

export interface ReportReadyEvent {
  runId: string;
  html: string;
  format: string;
}

// ---- System events ----

export interface SystemStatusEvent {
  status: SystemStatus;
}

export interface SystemLogEvent {
  level: "info" | "warn" | "error" | "debug";
  message: string;
  timestamp: string;
}

// ---- Renderer action payloads ----

export interface StartRunPayload {
  jobTitle: string;
  jdText: string;
  requiredSkills?: string[];
  targetDomains?: string[];
  config?: Record<string, unknown>;
}

export interface GetRunStatePayload {
  runId: string;
}

export interface GetCandidatesPayload {
  runId: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export interface GetCandidateDetailPayload {
  personId: string;
}

export interface ExportReportPayload {
  runId: string;
  format?: "html" | "markdown";
}
