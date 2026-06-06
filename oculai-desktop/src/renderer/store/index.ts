/**
 * Zustand store — unified state for the Oculai Desktop GUI.
 */
import { create } from "zustand";
import type {
  Candidate,
  CandidateDetail,
  PipelinePhase,
  SourcingRun,
  SystemStatus,
  SubagentState,
  ActivityEntry,
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

  // Orchestrator
  orchestratorPhase: PipelinePhase;
  setOrchestratorPhase: (phase: PipelinePhase) => void;

  // Subagents (live agent pool)
  subagents: SubagentState[];
  addSubagent: (agent: SubagentState) => void;
  updateSubagent: (agentId: string, updates: Partial<SubagentState>) => void;
  removeSubagent: (agentId: string) => void;
  clearSubagents: () => void;

  // Activity feed
  activityFeed: ActivityEntry[];
  addActivity: (entry: ActivityEntry) => void;
  clearActivity: () => void;

  // Candidates
  candidates: Candidate[];
  selectedCandidate: CandidateDetail | null;
  setCandidates: (candidates: Candidate[]) => void;
  setSelectedCandidate: (candidate: CandidateDetail | null) => void;

  // Agent messages (detailed log)
  messages: AgentMessage[];
  addMessage: (msg: AgentMessage) => void;
  clearMessages: () => void;

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

  // Orchestrator
  orchestratorPhase: "init",
  setOrchestratorPhase: (phase) => set({ orchestratorPhase: phase }),

  // Subagents
  subagents: [],
  addSubagent: (agent) =>
    set((s) => {
      const existing = s.subagents.findIndex((a) => a.agentId === agent.agentId);
      if (existing >= 0) {
        const updated = [...s.subagents];
        updated[existing] = agent;
        return { subagents: updated };
      }
      return { subagents: [...s.subagents, agent] };
    }),
  updateSubagent: (agentId, updates) =>
    set((s) => ({
      subagents: s.subagents.map((a) =>
        a.agentId === agentId ? { ...a, ...updates } : a,
      ),
    })),
  removeSubagent: (agentId) =>
    set((s) => ({
      subagents: s.subagents.filter((a) => a.agentId !== agentId),
    })),
  clearSubagents: () => set({ subagents: [] }),

  // Activity
  activityFeed: [],
  addActivity: (entry) =>
    set((s) => ({
      activityFeed: [...s.activityFeed.slice(-199), entry], // keep last 200
    })),
  clearActivity: () => set({ activityFeed: [] }),

  // Candidates
  candidates: [],
  selectedCandidate: null,
  setCandidates: (candidates) => set({ candidates }),
  setSelectedCandidate: (candidate) => set({ selectedCandidate: candidate }),

  // Messages
  messages: [],
  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, msg],
    })),
  clearMessages: () => set({ messages: [] }),

  // UI
  activeTab: "pipeline",
  setActiveTab: (tab) => set({ activeTab: tab }),
  settingsOpen: false,
  setSettingsOpen: (open) => set({ settingsOpen: open }),

  // Report
  reportHtml: null,
  setReportHtml: (html) => set({ reportHtml: html }),
}));
