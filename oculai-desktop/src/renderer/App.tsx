import { useEffect } from "react";
import { useStore } from "./store/index.js";
import { TitleBar } from "./components/layout/TitleBar.js";
import { Sidebar } from "./components/layout/Sidebar.js";
import { MainPanel } from "./components/layout/MainPanel.js";
import { SettingsView } from "./components/settings/SettingsView.js";

export default function App() {
  const settingsOpen = useStore((s) => s.settingsOpen);
  const setSystemStatus = useStore((s) => s.setSystemStatus);
  const addMessage = useStore((s) => s.addMessage);

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
          content: `Calling ${data.toolName}(${JSON.stringify(data.input).slice(0, 100)}...)`,
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

    // Run events
    unsubs.push(
      window.oculai.on("run:created", (payload: unknown) => {
        const data = payload as { runId: string; title: string; status: string };
        useStore.getState().addRun({
          run_id: data.runId,
          title: data.title,
          status: data.status as never,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
        useStore.getState().setActiveRun(data.runId);
      }),
    );

    // Report ready
    unsubs.push(
      window.oculai.on("report:ready", (payload: unknown) => {
        const data = payload as { runId: string; html: string };
        useStore.getState().setReportHtml(data.html);
        useStore.getState().setActiveTab("report");
      }),
    );

    return () => {
      unsubs.forEach((fn) => fn());
    };
  }, []);

  return (
    <div className="h-full flex flex-col bg-gray-950">
      <TitleBar />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
        <MainPanel />
      </div>
      {settingsOpen && <SettingsView />}
    </div>
  );
}
