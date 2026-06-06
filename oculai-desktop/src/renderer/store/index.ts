/**
 * Zustand store — unified state for the Oculai Desktop GUI.
 */
import { create } from "zustand";
import type {
  Candidate,
  CandidateDetail,
  PipelineState,
  SourcingRun,
  SystemStatus,
} from "../../shared/types.js";

interface AgentMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp: string;
  toolName?: string;
  isThinking?: boolean;
  isError?: boolean;
}

interface OculaiState {
  // System
  systemStatus: SystemStatus;
  setSystemStatus: (status: Partial<SystemStatus>) => void;

  // Runs
  runs: SourcingRun[];
  activeRunId: string | null;
  setActiveRun: (runId: string | null) => void;
  addRun: (run: SourcingRun) => void;
  setRuns: (runs: SourcingRun[]) => void;
  updateRun: (runId: string, updates: Partial<SourcingRun>) => void;

  // Pipeline
  pipeline: PipelineState | null;
  updatePipeline: (pipeline: Partial<PipelineState>) => void;

  // Candidates
  candidates: Candidate[];
  selectedCandidate: CandidateDetail | null;
  setCandidates: (candidates: Candidate[]) => void;
  setSelectedCandidate: (candidate: CandidateDetail | null) => void;

  // Agent messages (chat log)
  messages: AgentMessage[];
  addMessage: (msg: AgentMessage) => void;
  clearMessages: () => void;
  streamingText: string;

  // UI
  activeTab: "pipeline" | "candidates" | "evidence" | "report" | "logs";
  setActiveTab: (tab: OculaiState["activeTab"]) => void;
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;

  // Report
  reportHtml: string | null;
  setReportHtml: (html: string | null) => void;
}

export const useStore = create<OculaiState>((set) => ({
  // System
  systemStatus: {
    db: "disconnected",
    python: "stopped",
    llm: "unconfigured",
  },
  setSystemStatus: (status) =>
    set((s) => ({ systemStatus: { ...s.systemStatus, ...status } })),

  // Runs
  runs: [],
  activeRunId: null,
  setActiveRun: (runId) => set({ activeRunId: runId, activeTab: "pipeline" }),
  addRun: (run) => set((s) => ({ runs: [run, ...s.runs] })),
  setRuns: (runs) => set({ runs }),
  updateRun: (runId, updates) =>
    set((s) => ({
      runs: s.runs.map((r) => (r.run_id === runId ? { ...r, ...updates } : r)),
    })),

  // Pipeline
  pipeline: null,
  updatePipeline: (partial) =>
    set((s) => ({
      pipeline: s.pipeline ? { ...s.pipeline, ...partial } : (partial as PipelineState),
    })),

  // Candidates
  candidates: [],
  selectedCandidate: null,
  setCandidates: (candidates) => set({ candidates }),
  setSelectedCandidate: (candidate) => set({ selectedCandidate: candidate }),

  // Messages
  messages: [],
  streamingText: "",
  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, msg],
      streamingText: msg.role === "assistant" && !msg.isThinking ? "" : s.streamingText,
    })),
  clearMessages: () => set({ messages: [], streamingText: "" }),

  // UI
  activeTab: "pipeline",
  setActiveTab: (tab) => set({ activeTab: tab }),
  settingsOpen: false,
  setSettingsOpen: (open) => set({ settingsOpen: open }),

  // Report
  reportHtml: null,
  setReportHtml: (html) => set({ reportHtml: html }),
}));
