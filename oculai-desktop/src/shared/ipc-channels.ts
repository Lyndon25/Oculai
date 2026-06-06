/** Typed IPC channel definitions for main ↔ renderer communication. */

export const IPC_CHANNELS = {
  // Run lifecycle
  RUN_CREATED: "run:created",
  RUN_ERROR: "run:error",

  // Orchestrator
  ORCHESTRATOR_PHASE: "orchestrator:phase",

  // Subagent lifecycle
  SUBAGENT_SPAWNED: "subagent:spawned",
  SUBAGENT_PROGRESS: "subagent:progress",
  SUBAGENT_COMPLETED: "subagent:completed",

  // Candidates
  CANDIDATE_UPSERTED: "candidate:upserted",

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

  // Actions from renderer
  START_RUN: "action:startRun",
  RESUME_RUN: "action:resumeRun",
  ABORT_RUN: "action:abortRun",
  GET_RUN_STATE: "action:getRunState",
  GET_CANDIDATES: "action:getCandidates",
  GET_CANDIDATE_DETAIL: "action:getCandidateDetail",
  EXPORT_REPORT: "action:exportReport",
  LIST_RUNS: "action:listRuns",
  SETTINGS_GET: "settings:get",
  SETTINGS_SET: "settings:set",
} as const;

export type IpcChannel = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS];
