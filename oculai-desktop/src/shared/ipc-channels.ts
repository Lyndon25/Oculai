/** Typed IPC channel definitions for main ↔ renderer communication. */

export const IPC_CHANNELS = {
  // Run lifecycle
  RUN_CREATE: "run:create",
  RUN_CREATED: "run:created",
  RUN_STATE: "run:state",
  RUN_ERROR: "run:error",

  // Pipeline
  PIPELINE_UPDATE: "pipeline:update",
  TASK_UPDATED: "task:updated",
  ITERATION_RECORDED: "iteration:recorded",

  // Candidates
  CANDIDATE_UPSERTED: "candidate:upserted",
  CANDIDATE_SCORED: "candidate:scored",
  CANDIDATES_LIST: "candidates:list",
  CANDIDATE_DETAIL: "candidate:detail",

  // Evidence
  EVIDENCE_ATTACHED: "evidence:attached",
  EVIDENCE_LIST: "evidence:list",

  // Agent streaming
  AGENT_THINKING: "agent:thinking",
  AGENT_MESSAGE: "agent:message",
  AGENT_TOOL_CALL: "agent:tool_call",
  AGENT_TOOL_RESULT: "agent:tool_result",

  // Report
  REPORT_READY: "report:ready",

  // System
  SYSTEM_STATUS: "system:status",
  SYSTEM_LOG: "system:log",

  // Settings
  SETTINGS_GET: "settings:get",
  SETTINGS_SET: "settings:set",

  // Actions from renderer
  START_RUN: "action:startRun",
  RESUME_RUN: "action:resumeRun",
  ABORT_RUN: "action:abortRun",
  GET_RUN_STATE: "action:getRunState",
  GET_CANDIDATES: "action:getCandidates",
  GET_CANDIDATE_DETAIL: "action:getCandidateDetail",
  EXPORT_REPORT: "action:exportReport",
  LIST_RUNS: "action:listRuns",
} as const;

export type IpcChannel = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS];
