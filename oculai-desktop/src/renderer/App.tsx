import { useEffect } from "react";
import { useStore } from "./store/index.js";
import { TitleBar } from "./components/layout/TitleBar.js";
import { Sidebar } from "./components/layout/Sidebar.js";
import { MainPanel } from "./components/layout/MainPanel.js";
import { SettingsView } from "./components/settings/SettingsView.js";
import type {
  SubagentSpawnedEvent,
  SubagentProgressEvent,
  SubagentCompletedEvent,
  CandidateUpsertedEvent,
  OrchestratorPhaseEvent,
  RunErrorEvent,
  SystemLogEvent,
} from "../shared/events.js";
import type { Candidate, SourcingRun } from "../shared/types.js";

export default function App() {
  const settingsOpen = useStore((s) => s.settingsOpen);
  const activeRunId = useStore((s) => s.activeRunId);
  const setSystemStatus = useStore((s) => s.setSystemStatus);
  const addMessage = useStore((s) => s.addMessage);
  const addSubagent = useStore((s) => s.addSubagent);
  const updateSubagent = useStore((s) => s.updateSubagent);
  const addActivity = useStore((s) => s.addActivity);
  const setOrchestratorPhase = useStore((s) => s.setOrchestratorPhase);
  const upsertCandidateSummary = useStore((s) => s.upsertCandidateSummary);
  const resetRunScopedState = useStore((s) => s.resetRunScopedState);

  // On mount: hydrate runs from persisted recent-runs.json
  useEffect(() => {
    window.oculai.listRuns().then((runs: unknown) => {
      const entries = runs as Array<{
        run_id: string;
        title: string;
        status: string;
        created_at: string;
        candidate_count?: number;
      }>;
      if (Array.isArray(entries) && entries.length > 0) {
        useStore.getState().setRuns(
          entries.map((r) => ({
            run_id: r.run_id,
            title: r.title,
            status: r.status as never,
            created_at: r.created_at,
            updated_at: r.created_at,
            candidate_count: r.candidate_count,
            task_count: undefined,
            completed_task_count: undefined,
            active_plan_id: undefined,
          })),
        );
      }
    }).catch(() => {
      // Silently ignore — recent-runs.json may not exist yet
    });
  }, []);

  // Keep active run metadata fresh when switching/resuming runs.
  useEffect(() => {
    if (!activeRunId) return;
    let cancelled = false;
    window.oculai.getRunState({ runId: activeRunId }).then((result: unknown) => {
      if (cancelled) return;
      const data = result as {
        run?: Partial<SourcingRun>;
        candidate_count?: number;
        task_count?: number;
        completed_task_count?: number;
      };
      if (data.run?.run_id) {
        useStore.getState().updateRun(data.run.run_id, {
          status: data.run.status as never,
          title: data.run.title,
          updated_at: data.run.updated_at,
          candidate_count: data.candidate_count ?? data.run.candidate_count,
          task_count: data.task_count ?? data.run.task_count,
          completed_task_count: data.completed_task_count ?? data.run.completed_task_count,
          active_plan_id: data.run.active_plan_id,
        });
      }
    }).catch((err: unknown) => {
      addMessage({
        role: "system",
        content: `Failed to refresh run state: ${err instanceof Error ? err.message : String(err)}`,
        timestamp: new Date().toISOString(),
        isError: true,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [activeRunId]);

  // Subscribe to IPC events from main process
  useEffect(() => {
    const unsubs: (() => void)[] = [];

    // System status updates
    unsubs.push(
      window.oculai.on("system:status", (payload: unknown) => {
        const data = payload as { status: Record<string, unknown> };
        setSystemStatus(data.status);
      }),
    );

    // System logs
    unsubs.push(
      window.oculai.on("system:log", (payload: unknown) => {
        const data = payload as SystemLogEvent;
        addMessage({
          role: "system",
          content: data.message,
          timestamp: data.timestamp,
          isError: data.level === "error" || data.level === "warn",
        });
        if (data.level === "error" || data.level === "warn") {
          addActivity({
            timestamp: data.timestamp,
            action: data.level === "error" ? "error" : "audit",
            message: data.message,
            detail: "system",
          });
        }
      }),
    );

    // Run errors
    unsubs.push(
      window.oculai.on("run:error", (payload: unknown) => {
        const data = payload as RunErrorEvent;
        addMessage({
          role: "system",
          content: `Run ${data.runId} failed during ${data.phase}: ${data.error}`,
          timestamp: new Date().toISOString(),
          isError: true,
        });
        addActivity({
          timestamp: new Date().toISOString(),
          action: "error",
          message: data.error,
          detail: data.phase,
        });
        useStore.getState().updateRun(data.runId, { status: "aborted" as never });
      }),
    );

    // Agent messages
    unsubs.push(
      window.oculai.on("agent:message", (payload: unknown) => {
        const data = payload as { text: string };
        addMessage({
          role: "assistant",
          content: data.text,
          timestamp: new Date().toISOString(),
        });
      }),
    );

    // Agent thinking
    unsubs.push(
      window.oculai.on("agent:thinking", (payload: unknown) => {
        const data = payload as { delta: string };
        addMessage({
          role: "assistant",
          content: data.delta,
          timestamp: new Date().toISOString(),
          isThinking: true,
        });
      }),
    );

    // Tool calls
    unsubs.push(
      window.oculai.on("agent:tool_call", (payload: unknown) => {
        const data = payload as { toolName: string; input: Record<string, unknown> };
        addMessage({
          role: "tool",
          content: `${data.toolName}(${JSON.stringify(data.input).slice(0, 100)}...)`,
          timestamp: new Date().toISOString(),
          toolName: data.toolName,
        });
      }),
    );

    // Tool results
    unsubs.push(
      window.oculai.on("agent:tool_result", (payload: unknown) => {
        const data = payload as {
          toolName: string;
          output: Record<string, unknown>;
          isError: boolean;
        };
        addMessage({
          role: "tool",
          content: data.isError
            ? `${data.toolName} failed`
            : `${data.toolName} completed`,
          timestamp: new Date().toISOString(),
          toolName: data.toolName,
          isError: data.isError,
        });
      }),
    );

    // Run created
    unsubs.push(
      window.oculai.on("run:created", (payload: unknown) => {
        const data = payload as { runId: string; title: string; status: string };
        resetRunScopedState();
        useStore.getState().addRun({
          run_id: data.runId,
          title: data.title,
          status: data.status as never,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          candidate_count: 0,
        });
        useStore.getState().setActiveRun(data.runId);
      }),
    );

    // Orchestrator phase changes
    unsubs.push(
      window.oculai.on("orchestrator:phase", (payload: unknown) => {
        const data = payload as OrchestratorPhaseEvent;
        setOrchestratorPhase(data.phase);
      }),
    );

    // Subagent spawned
    unsubs.push(
      window.oculai.on("subagent:spawned", (payload: unknown) => {
        const data = payload as SubagentSpawnedEvent;
        addSubagent({
          agentId: data.agentId,
          agentType: data.agentType,
          target: data.target,
          status: data.status,
          spawnedAt: new Date().toISOString(),
        });
        addActivity({
          timestamp: new Date().toISOString(),
          agentId: data.agentId,
          agentType: data.agentType,
          action: "search",
          message: `${data.agentType} spawned for ${data.target}`,
        });
      }),
    );

    // Subagent progress
    unsubs.push(
      window.oculai.on("subagent:progress", (payload: unknown) => {
        const data = payload as SubagentProgressEvent;
        addActivity(data.activity);
      }),
    );

    // Subagent completed
    unsubs.push(
      window.oculai.on("subagent:completed", (payload: unknown) => {
        const data = payload as SubagentCompletedEvent;
        updateSubagent(data.agentId, {
          status: data.status,
          resultCount: data.resultCount,
          error: data.error,
          completedAt: new Date().toISOString(),
        });
        addActivity({
          timestamp: new Date().toISOString(),
          agentId: data.agentId,
          agentType: data.agentType,
          action: data.status === "error" ? "error" : "found",
          message: data.status === "done"
            ? `${data.agentType} completed with ${data.resultCount ?? 0} results`
            : `${data.agentType} failed: ${data.error ?? "unknown error"}`,
        });
      }),
    );

    // Candidate upserted
    unsubs.push(
      window.oculai.on("candidate:upserted", (payload: unknown) => {
        const data = payload as CandidateUpsertedEvent;
        const candidate: Candidate = {
          person_id: data.personId,
          canonical_name: data.name,
          latest_institution: data.institution || undefined,
          status: "pending",
          created_at: new Date().toISOString(),
        };
        upsertCandidateSummary(candidate);
        const activeRunId = useStore.getState().activeRunId;
        if (activeRunId) {
          const current = useStore.getState().runs.find((r) => r.run_id === activeRunId);
          const nextCount = useStore.getState().candidates.length;
          useStore.getState().updateRun(activeRunId, {
            candidate_count: Math.max(current?.candidate_count ?? 0, nextCount),
          });
        }
        addActivity({
          timestamp: new Date().toISOString(),
          action: "upsert",
          message: `新增候选人：${data.name}${data.institution ? `（${data.institution}）` : ""}`,
          detail: data.sourceName ? `via ${data.sourceName}` : undefined,
        });
      }),
    );

    // Report ready
    unsubs.push(
      window.oculai.on("report:ready", (payload: unknown) => {
        const data = payload as { runId: string; html: string; format: string };
        useStore.getState().setReportHtml(data.html);
        useStore.getState().setActiveTab("report");
        addActivity({
          timestamp: new Date().toISOString(),
          action: "export",
          message: `Report exported (${data.format})`,
        });
      }),
    );

    return () => {
      unsubs.forEach((fn) => fn());
    };
  }, []);

  return (
    <div className="h-full flex flex-col bg-canvas text-ink">
      <TitleBar />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
        <MainPanel />
      </div>
      {settingsOpen && <SettingsView />}
    </div>
  );
}
