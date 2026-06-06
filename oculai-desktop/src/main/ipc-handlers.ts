/**
 * IPC Handlers — registers ipcMain.handle() for renderer → main actions.
 *
 * Each handler receives a typed payload from the renderer, delegates to
 * the Pi session or directly to the Python sidecar, and returns results.
 */
import { app, ipcMain } from "electron";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";
import { IPC_CHANNELS } from "../shared/ipc-channels.js";
import type {
  ExportReportPayload,
  GetCandidateDetailPayload,
  GetCandidatesPayload,
  GetRunStatePayload,
  StartRunPayload,
} from "../shared/events.js";
import { getSession } from "./pi-session.js";
import { ToolBridge } from "./tool-bridge.js";
import { getSettingsStore } from "./settings-store.js";
import { stateBus } from "./state-bus.js";
import type { SourcingRun } from "../shared/types.js";

// ---- Recent Runs persistence (local JSON file, survives app restarts) ----

interface RecentRunEntry {
  run_id: string;
  title: string;
  status: string;
  created_at: string;
  candidate_count?: number;
}

function recentRunsPath(): string {
  const userData = app.getPath("userData");
  if (!existsSync(userData)) {
    mkdirSync(userData, { recursive: true });
  }
  return join(userData, "recent-runs.json");
}

function readRecentRuns(): RecentRunEntry[] {
  const path = recentRunsPath();
  try {
    if (existsSync(path)) {
      const raw = readFileSync(path, "utf-8");
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed;
      }
    }
  } catch {
    // Corrupt file — return empty
  }
  return [];
}

function saveRunToRecent(run: RecentRunEntry): void {
  const runs = readRecentRuns();
  // Remove existing entry for the same run_id, then prepend
  const filtered = runs.filter((r) => r.run_id !== run.run_id);
  filtered.unshift(run);
  // Keep at most 50 runs
  const trimmed = filtered.slice(0, 50);
  writeFileSync(recentRunsPath(), JSON.stringify(trimmed, null, 2), "utf-8");
}

export function registerIpcHandlers(toolBridge: ToolBridge): void {
  // ---- Run lifecycle ----

  ipcMain.handle(IPC_CHANNELS.START_RUN, async (_event, payload: StartRunPayload) => {
    try {
      stateBus.emitSystemLog("info", `Starting new run: ${payload.jobTitle}`);

      // Use the direct tool bridge for oculai_create_run
      const result = await toolBridge.callTool("oculai_create_run", {
        job_title: payload.jobTitle,
        jd_text: payload.jdText,
        required_skills: payload.requiredSkills || [],
        target_domains: payload.targetDomains || [],
        config: payload.config || {},
      });

      stateBus.emitRunCreated(
        result.run_id as string,
        payload.jobTitle,
        "draft",
      );

      // Persist run metadata to recent-runs.json for cross-session history
      saveRunToRecent({
        run_id: result.run_id as string,
        title: payload.jobTitle,
        status: "draft",
        created_at: new Date().toISOString(),
        candidate_count: 0,
      });

      // Kick off the Pi agent to run the full pipeline
      const session = getSession();
      if (session) {
        const runId = result.run_id as string;
        const prompt = buildPipelinePrompt(runId, payload);
        session.prompt(prompt).catch((err) => {
          stateBus.emitRunError(runId, err.message, "pipeline");
        });
      }

      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      stateBus.emitSystemLog("error", `Failed to start run: ${msg}`);
      throw err;
    }
  });

  ipcMain.handle(IPC_CHANNELS.GET_RUN_STATE, async (_event, payload: GetRunStatePayload) => {
    return toolBridge.callTool("oculai_get_run_state", { run_id: payload.runId });
  });

  ipcMain.handle(IPC_CHANNELS.ABORT_RUN, async (_event, payload: { runId: string }) => {
    stateBus.emitSystemLog("info", `Aborting run: ${payload.runId}`);
    // The run can be aborted by stopping the session prompt
    const session = getSession();
    if (session) {
      session.abort();
    }
    return { status: "aborted" };
  });

  ipcMain.handle(IPC_CHANNELS.RESUME_RUN, async (_event, payload: { runId: string }) => {
    stateBus.emitSystemLog("info", `Resuming run: ${payload.runId}`);
    const state = await toolBridge.callTool("oculai_get_run_state", { run_id: payload.runId });
    return state;
  });

  // ---- Candidates ----

  ipcMain.handle(IPC_CHANNELS.GET_CANDIDATES, async (_event, payload: GetCandidatesPayload) => {
    return toolBridge.callTool("oculai_list_candidates", {
      run_id: payload.runId,
      status: payload.status,
      limit: payload.limit || 50,
      offset: payload.offset || 0,
    });
  });

  ipcMain.handle(IPC_CHANNELS.GET_CANDIDATE_DETAIL, async (_event, payload: GetCandidateDetailPayload) => {
    return toolBridge.callTool("oculai_get_candidate", { person_id: payload.personId });
  });

  // ---- Report ----

  ipcMain.handle(IPC_CHANNELS.EXPORT_REPORT, async (_event, payload: ExportReportPayload) => {
    const result = await toolBridge.callTool("oculai_export_report", {
      run_id: payload.runId,
      format: payload.format || "html",
    });
    if (result.html_content) {
      stateBus.emitReportReady(payload.runId, result.html_content as string, payload.format || "html");
    }
    return result;
  });

  // ---- Recent Runs ----

  ipcMain.handle(IPC_CHANNELS.LIST_RUNS, async () => {
    return readRecentRuns();
  });

  // ---- Settings ----

  ipcMain.handle(IPC_CHANNELS.SETTINGS_GET, async () => {
    return getSettingsStore().getAll();
  });

  ipcMain.handle(IPC_CHANNELS.SETTINGS_SET, async (_event, settings: Record<string, unknown>) => {
    const store = getSettingsStore();
    for (const [key, value] of Object.entries(settings)) {
      store.set(key as never, value as never);
    }
    return { ok: true };
  });

  stateBus.emitSystemLog("info", "IPC handlers registered");
}

/**
 * Build the initial prompt that kicks off the Oculai pipeline.
 * The Pi session reads this and begins autonomous orchestration.
 */
function buildPipelinePrompt(runId: string, payload: StartRunPayload): string {
  const skills = payload.requiredSkills?.length
    ? `\nRequired skills: ${payload.requiredSkills.join(", ")}`
    : "";
  const domains = payload.targetDomains?.length
    ? `\nTarget domains: ${payload.targetDomains.join(", ")}`
    : "";

  return `## New Talent Sourcing Task

Run ID: ${runId}
Job Title: ${payload.jobTitle}

### Job Description
${payload.jdText}
${skills}${domains}

The run has been created (run_id="${runId}"). Begin orchestrating the talent sourcing pipeline.
Analyze the JD, design your search strategy, spawn subagents as needed, and find the best
China-based candidates for this role.`;
}
