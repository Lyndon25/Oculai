/** Event payload types for IPC communication. */

import type { SourcingRun, SystemStatus, SubagentState, PipelinePhase, ActivityEntry } from "./types.js";

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

export interface RunErrorEvent {
  runId: string;
  error: string;
  phase: string;
}

// ---- Orchestrator events ----

export interface OrchestratorPhaseEvent {
  runId: string;
  phase: PipelinePhase;
  metrics?: {
    candidateCount?: number;
    chinaCoverage?: number;
    qualityScore?: number;
  };
}

// ---- Subagent events ----

export interface SubagentSpawnedEvent {
  agentId: string;
  agentType: string;
  target: string;
  status: SubagentState["status"];
}

export interface SubagentProgressEvent {
  agentId: string;
  activity: ActivityEntry;
}

export interface SubagentCompletedEvent {
  agentId: string;
  agentType: string;
  target: string;
  status: "done" | "error";
  resultCount?: number;
  error?: string;
}

// ---- Candidate events ----

export interface CandidateUpsertedEvent {
  personId: string;
  name: string;
  institution: string;
  sourceName: string;
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

export interface GetCandidatesPayload {
  runId: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export interface GetCandidateDetailPayload {
  personId: string;
}

export interface GetRunStatePayload {
  runId: string;
}

export interface ExportReportPayload {
  runId: string;
  format?: "html" | "markdown";
}
