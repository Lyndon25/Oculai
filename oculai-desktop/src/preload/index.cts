import type {
  ExportReportPayload,
  GetCandidateDetailPayload,
  GetCandidatesPayload,
  GetRunStatePayload,
  StartRunPayload,
} from "../shared/events.js";

const { contextBridge, ipcRenderer } = require("electron") as typeof import("electron");

const IPC_CHANNELS = {
  RUN_CREATED: "run:created",
  RUN_ERROR: "run:error",
  ORCHESTRATOR_PHASE: "orchestrator:phase",
  SUBAGENT_SPAWNED: "subagent:spawned",
  SUBAGENT_PROGRESS: "subagent:progress",
  SUBAGENT_COMPLETED: "subagent:completed",
  CANDIDATE_UPSERTED: "candidate:upserted",
  AGENT_THINKING: "agent:thinking",
  AGENT_MESSAGE: "agent:message",
  AGENT_TOOL_CALL: "agent:tool_call",
  AGENT_TOOL_RESULT: "agent:tool_result",
  REPORT_READY: "report:ready",
  SYSTEM_STATUS: "system:status",
  SYSTEM_LOG: "system:log",
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
  SETTINGS_SET_API_KEY: "settings:setApiKey",
} as const;

const allowedEventChannels = [
  IPC_CHANNELS.RUN_CREATED,
  IPC_CHANNELS.RUN_ERROR,
  IPC_CHANNELS.ORCHESTRATOR_PHASE,
  IPC_CHANNELS.SUBAGENT_SPAWNED,
  IPC_CHANNELS.SUBAGENT_PROGRESS,
  IPC_CHANNELS.SUBAGENT_COMPLETED,
  IPC_CHANNELS.CANDIDATE_UPSERTED,
  IPC_CHANNELS.AGENT_THINKING,
  IPC_CHANNELS.AGENT_MESSAGE,
  IPC_CHANNELS.AGENT_TOOL_CALL,
  IPC_CHANNELS.AGENT_TOOL_RESULT,
  IPC_CHANNELS.REPORT_READY,
  IPC_CHANNELS.SYSTEM_STATUS,
  IPC_CHANNELS.SYSTEM_LOG,
] as string[];

const api = {
  // ---- Actions (renderer → main) ----
  startRun: (payload: StartRunPayload) =>
    ipcRenderer.invoke(IPC_CHANNELS.START_RUN, payload),

  resumeRun: (runId: string) =>
    ipcRenderer.invoke(IPC_CHANNELS.RESUME_RUN, { runId }),

  getRunState: (payload: GetRunStatePayload) =>
    ipcRenderer.invoke(IPC_CHANNELS.GET_RUN_STATE, payload),

  abortRun: (runId: string) =>
    ipcRenderer.invoke(IPC_CHANNELS.ABORT_RUN, { runId }),

  getCandidates: (payload: GetCandidatesPayload) =>
    ipcRenderer.invoke(IPC_CHANNELS.GET_CANDIDATES, payload),

  getCandidateDetail: (payload: GetCandidateDetailPayload) =>
    ipcRenderer.invoke(IPC_CHANNELS.GET_CANDIDATE_DETAIL, payload),

  exportReport: (payload: ExportReportPayload) =>
    ipcRenderer.invoke(IPC_CHANNELS.EXPORT_REPORT, payload),

  listRuns: () =>
    ipcRenderer.invoke(IPC_CHANNELS.LIST_RUNS),

  getSettings: () =>
    ipcRenderer.invoke(IPC_CHANNELS.SETTINGS_GET),

  setSettings: (settings: Record<string, unknown>) =>
    ipcRenderer.invoke(IPC_CHANNELS.SETTINGS_SET, settings),

  setApiKey: (provider: string, key: string) =>
    ipcRenderer.invoke(IPC_CHANNELS.SETTINGS_SET_API_KEY, { provider, key }),

  // ---- Events (main → renderer) ----
  on: (channel: string, callback: (...args: unknown[]) => void) => {
    if (allowedEventChannels.includes(channel)) {
      const subscription = (_event: Electron.IpcRendererEvent, ...args: unknown[]) =>
        callback(...args);
      ipcRenderer.on(channel, subscription);
      return () => {
        ipcRenderer.removeListener(channel, subscription);
      };
    }
    return () => {};
  },

  removeAllListeners: (channel: string) => {
    if (allowedEventChannels.includes(channel)) {
      ipcRenderer.removeAllListeners(channel);
    }
  },
};

contextBridge.exposeInMainWorld("oculai", api);

declare global {
  interface Window {
    oculai: typeof api;
  }
}

export {};
