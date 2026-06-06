/**
 * Preload script — exposes a typed IPC API to the renderer via contextBridge.
 */
import { contextBridge, ipcRenderer } from "electron";
import { IPC_CHANNELS } from "../shared/ipc-channels.js";
import type {
  ExportReportPayload,
  GetCandidateDetailPayload,
  GetCandidatesPayload,
  GetRunStatePayload,
  StartRunPayload,
} from "../shared/events.js";

const api = {
  // ---- Actions (renderer → main) ----
  startRun: (payload: StartRunPayload) =>
    ipcRenderer.invoke(IPC_CHANNELS.START_RUN, payload),

  resumeRun: (runId: string) =>
    ipcRenderer.invoke(IPC_CHANNELS.RESUME_RUN, { runId }),

  abortRun: (runId: string) =>
    ipcRenderer.invoke(IPC_CHANNELS.ABORT_RUN, { runId }),

  getRunState: (payload: GetRunStatePayload) =>
    ipcRenderer.invoke(IPC_CHANNELS.GET_RUN_STATE, payload),

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

  // ---- Events (main → renderer) ----
  on: (channel: string, callback: (...args: unknown[]) => void) => {
    const validChannels = Object.values(IPC_CHANNELS).filter(
      (ch) =>
        !ch.startsWith("action:") &&
        ch !== IPC_CHANNELS.SETTINGS_GET &&
        ch !== IPC_CHANNELS.SETTINGS_SET
    );
    if (validChannels.includes(channel as never)) {
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
    ipcRenderer.removeAllListeners(channel);
  },
};

contextBridge.exposeInMainWorld("oculai", api);

// Type declaration for renderer
declare global {
  interface Window {
    oculai: typeof api;
  }
}
