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
import { getSession, initPiSession } from "./pi-session.js";
import { ToolBridge } from "./tool-bridge.js";
import { PostgresManager } from "./postgres-manager.js";
import { getSettingsStore } from "./settings-store.js";
import { stateBus } from "./state-bus.js";
import type { AcademicWork, Assessment, Candidate, CandidateDetail, CareerEvent, Evidence, SourcingRun } from "../shared/types.js";

// ---- Recent Runs persistence (local JSON file, survives app restarts) ----

interface RecentRunEntry {
  run_id: string;
  title: string;
  status: string;
  created_at: string;
  candidate_count?: number;
}

type RawRecord = Record<string, unknown>;

function asRecord(value: unknown): RawRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as RawRecord)
    : {};
}

function asArray(value: unknown): RawRecord[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function asString(value: unknown, fallback = ""): string {
  if (value === undefined || value === null) return fallback;
  return String(value);
}

function asOptionalString(value: unknown): string | undefined {
  const text = asString(value).trim();
  return text.length > 0 ? text : undefined;
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function normalizeCandidate(rawValue: unknown): Candidate {
  const raw = asRecord(rawValue);
  const person = asRecord(raw.person);
  const personId = asString(raw.person_id ?? person.person_id);
  const canonicalName = asString(
    raw.canonical_name ?? raw.name ?? person.canonical_name ?? person.name,
    "Unknown candidate",
  );
  const status = asString(raw.status, "pending") as Candidate["status"];
  const researchAreasRaw = raw.research_areas ?? person.research_areas;

  return {
    record_id: asOptionalString(raw.record_id),
    person_id: personId,
    canonical_name: canonicalName,
    latest_institution: asOptionalString(
      raw.latest_institution ?? raw.institution ?? person.latest_institution ?? person.institution,
    ),
    latest_position: asOptionalString(
      raw.latest_position ?? raw.position ?? person.latest_position ?? person.position,
    ),
    h_index: asNumber(raw.h_index ?? person.h_index),
    total_papers: asNumber(raw.total_papers ?? raw.paper_count ?? person.total_papers ?? person.paper_count),
    total_citations: asNumber(raw.total_citations ?? raw.citations ?? person.total_citations ?? person.citations),
    status,
    quality_score: asNumber(raw.quality_score ?? person.quality_score),
    research_areas: Array.isArray(researchAreasRaw)
      ? researchAreasRaw.map((item) => String(item)).filter(Boolean)
      : undefined,
    github_id: asOptionalString(raw.github_id ?? person.github_id),
    google_scholar_id: asOptionalString(raw.google_scholar_id ?? person.google_scholar_id),
    identities: undefined,
    created_at: asOptionalString(raw.created_at),
  };
}

function normalizeEvidence(rawValue: unknown, fallbackPersonId: string): Evidence {
  const raw = asRecord(rawValue);
  return {
    evidence_id: asString(raw.evidence_id ?? raw.id),
    person_id: asString(raw.person_id, fallbackPersonId),
    evidence_type: asString(raw.evidence_type ?? raw.type, "unknown"),
    title: asString(raw.title, "Untitled evidence"),
    description: asOptionalString(raw.description ?? raw.snippet),
    source_name: asString(raw.source_name ?? raw.source, "unknown"),
    source_url: asOptionalString(raw.source_url ?? raw.url),
    confidence: asNumber(raw.confidence) ?? 0,
    tier: asNumber(raw.tier) ?? 4,
    quality_flags: Array.isArray(raw.quality_flags)
      ? raw.quality_flags.map((item) => String(item)).filter(Boolean)
      : undefined,
    captured_at: asString(raw.captured_at ?? raw.created_at, new Date().toISOString()),
  };
}

function normalizeAssessment(rawValue: unknown, fallbackPersonId: string): Assessment {
  const raw = asRecord(rawValue);
  return {
    assessment_id: asString(raw.assessment_id ?? raw.id),
    run_id: asString(raw.run_id),
    person_id: asString(raw.person_id, fallbackPersonId),
    assessor_agent: asString(raw.assessor_agent ?? raw.agent_id ?? raw.agent, "unknown"),
    dimension: asString(raw.dimension, "overall"),
    score: asNumber(raw.score) ?? 0,
    confidence: asNumber(raw.confidence) ?? 0,
    rationale: asOptionalString(raw.rationale),
    evidence_ids: Array.isArray(raw.evidence_ids)
      ? raw.evidence_ids.map((item) => String(item)).filter(Boolean)
      : undefined,
  };
}

function normalizeAcademicWork(rawValue: unknown): AcademicWork {
  const raw = asRecord(rawValue);
  return {
    work_id: asString(raw.work_id ?? raw.id ?? raw.doi ?? raw.title),
    title: asString(raw.title, "Untitled publication"),
    type: asString(raw.type, "publication"),
    venue: asOptionalString(raw.venue),
    year: asNumber(raw.year),
    citations: asNumber(raw.citations),
    doi: asOptionalString(raw.doi),
    url: asOptionalString(raw.url),
  };
}

function normalizeCareerEvent(rawValue: unknown): CareerEvent {
  const raw = asRecord(rawValue);
  return {
    event_id: asString(raw.event_id ?? raw.id ?? `${raw.institution ?? "event"}-${raw.role ?? "role"}`),
    event_type: asString(raw.event_type ?? raw.type, "career"),
    institution: asOptionalString(raw.institution),
    role: asOptionalString(raw.role ?? raw.position),
    start_date: asOptionalString(raw.start_date),
    end_date: asOptionalString(raw.end_date),
    is_current: Boolean(raw.is_current),
  };
}

function normalizeCandidateDetail(rawValue: unknown): CandidateDetail | null {
  if (!rawValue) return null;
  const raw = asRecord(rawValue);
  const person = asRecord(raw.person);
  const base = normalizeCandidate({ ...person, ...raw, person: undefined });
  const personId = base.person_id;

  return {
    ...base,
    identities: asArray(raw.identities).map((identity) => ({
      source_type: asString(identity.source_type, "unknown"),
      external_id: asString(identity.external_id),
      external_url: asOptionalString(identity.external_url),
      is_primary: Boolean(identity.is_primary),
      confidence: asNumber(identity.confidence) ?? 0,
    })),
    evidence: asArray(raw.evidence).map((item) => normalizeEvidence(item, personId)),
    assessments: asArray(raw.assessments).map((item) => normalizeAssessment(item, personId)),
    academic_works: asArray(raw.academic_works ?? raw.publications).map(normalizeAcademicWork),
    career_events: asArray(raw.career_events ?? raw.career).map(normalizeCareerEvent),
    score_history: asArray(raw.score_history).map((item) => ({
      history_id: asString(item.history_id ?? item.id),
      dimension: asString(item.dimension, "overall"),
      previous_score: asNumber(item.previous_score),
      new_score: asNumber(item.new_score) ?? 0,
      previous_confidence: asNumber(item.previous_confidence),
      new_confidence: asNumber(item.new_confidence) ?? 0,
      assessor_agent: asString(item.assessor_agent ?? item.agent, "unknown"),
      changed_at: asString(item.changed_at ?? item.created_at, new Date().toISOString()),
      change_reason: asOptionalString(item.change_reason),
    })),
  };
}

function normalizeRunStateSummary(rawValue: unknown): RawRecord {
  const raw = asRecord(rawValue);
  const run = asRecord(raw.run);
  const taskStats = asArray(raw.task_stats);
  const taskCount = taskStats.reduce((sum, item) => sum + (asNumber(item.cnt) ?? 0), 0);
  const completedTaskCount = taskStats
    .filter((item) => asString(item.status) === "done" || asString(item.status) === "completed")
    .reduce((sum, item) => sum + (asNumber(item.cnt) ?? 0), 0);

  const normalizedRun: Partial<SourcingRun> = {
    run_id: asString(run.run_id ?? raw.run_id),
    title: asString(run.title ?? run.job_title ?? raw.title, "Untitled run"),
    status: asString(run.status ?? raw.status, "draft") as SourcingRun["status"],
    created_at: asString(run.created_at ?? raw.created_at, new Date().toISOString()),
    updated_at: asString(run.updated_at ?? raw.updated_at ?? run.created_at ?? raw.created_at, new Date().toISOString()),
    candidate_count: asNumber(raw.candidate_count) ?? 0,
    task_count: taskCount || undefined,
    completed_task_count: taskCount ? completedTaskCount : undefined,
    active_plan_id: asOptionalString(run.active_plan_id),
  };

  return {
    ...raw,
    run: normalizedRun,
    candidate_count: normalizedRun.candidate_count,
    task_count: normalizedRun.task_count,
    completed_task_count: normalizedRun.completed_task_count,
  };
}

function recentRunFromState(stateValue: unknown): RecentRunEntry | null {
  const state = normalizeRunStateSummary(stateValue);
  const run = asRecord(state.run);
  const runId = asString(run.run_id);
  if (!runId) return null;
  return {
    run_id: runId,
    title: asString(run.title, "Untitled run"),
    status: asString(run.status, "draft"),
    created_at: asString(run.created_at, new Date().toISOString()),
    candidate_count: asNumber(state.candidate_count),
  };
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

export function registerIpcHandlers(toolBridge: ToolBridge, postgresManager?: PostgresManager): void {
  // ---- Run lifecycle ----

  ipcMain.handle(IPC_CHANNELS.START_RUN, async (_event, payload: StartRunPayload) => {
    try {
      stateBus.emitSystemLog("info", `Starting new run: ${payload.jobTitle}`);

      const store = getSettingsStore();
      const runtimeConfig = {
        ...(payload.config || {}),
        enabledSources: store.get("enabledSources"),
        maxIterations: store.get("maxIterations"),
        tokenBudget: store.get("tokenBudget"),
        concurrency: store.get("concurrency"),
      };

      // Use the direct tool bridge for oculai_create_run
      const result = await toolBridge.callTool("oculai_create_run", {
        job_title: payload.jobTitle,
        jd_text: payload.jdText,
        required_skills: payload.requiredSkills || [],
        target_domains: payload.targetDomains || [],
        config: runtimeConfig,
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
        const prompt = buildPipelinePrompt(runId, { ...payload, config: runtimeConfig });
        session.prompt(prompt).catch((err: unknown) => {
          stateBus.emitRunError(runId, err instanceof Error ? err.message : String(err), "pipeline");
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
    const state = normalizeRunStateSummary(
      await toolBridge.callTool("oculai_get_run_state", { run_id: payload.runId }),
    );
    const recent = recentRunFromState(state);
    if (recent) saveRunToRecent(recent);
    return state;
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
    const state = normalizeRunStateSummary(
      await toolBridge.callTool("oculai_get_run_state", { run_id: payload.runId }),
    );
    const recent = recentRunFromState(state);
    if (recent) saveRunToRecent(recent);
    return state;
  });

  // ---- Candidates ----

  ipcMain.handle(IPC_CHANNELS.GET_CANDIDATES, async (_event, payload: GetCandidatesPayload) => {
    const result = await toolBridge.callTool("oculai_list_candidates", {
      run_id: payload.runId,
      status: payload.status,
      limit: payload.limit || 50,
      offset: payload.offset || 0,
    });
    const rawCandidates = Array.isArray(result.candidates) ? result.candidates : [];
    return {
      ...result,
      candidates: rawCandidates.map(normalizeCandidate),
    };
  });

  ipcMain.handle(IPC_CHANNELS.GET_CANDIDATE_DETAIL, async (_event, payload: GetCandidateDetailPayload) => {
    const result = await toolBridge.callTool("oculai_get_candidate", { person_id: payload.personId });
    return normalizeCandidateDetail(result);
  });

  // ---- Report ----

  ipcMain.handle(IPC_CHANNELS.EXPORT_REPORT, async (_event, payload: ExportReportPayload) => {
    const result = await toolBridge.callTool("oculai_export_report", {
      run_id: payload.runId,
      format: payload.format || "html",
    });
    const html = asOptionalString(result.html_content ?? result.html);
    if (html) {
      stateBus.emitReportReady(payload.runId, html, payload.format || "html");
    }
    return { ...result, html_content: html };
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
    // Only allow known settings keys — reject ad-hoc keys (e.g. plaintext apiKey_*)
    const knownKeys = new Set([
      "llmProvider", "llmModel", "thinkingLevel",
      "enabledSources", "dbPort", "dbAutoStart",
      "maxIterations", "tokenBudget", "concurrency",
    ]);
    for (const [key, value] of Object.entries(settings)) {
      if (!knownKeys.has(key)) {
        stateBus.emitSystemLog("warn", `Rejected unknown setting key: ${key}`);
        continue;
      }
      store.set(key as never, value as never);
    }
    return { ok: true };
  });

  ipcMain.handle(IPC_CHANNELS.SETTINGS_SET_API_KEY, async (_event, payload: { provider: string; key: string }) => {
    const store = getSettingsStore();
    store.setApiKey(payload.provider, payload.key);

    if (payload.provider === store.get("llmProvider") && postgresManager && !getSession()) {
      try {
        await initPiSession(toolBridge, postgresManager);
        stateBus.emitSystemStatus({ db: "connected", python: "ready", llm: "configured" });
        stateBus.emitSystemLog("info", `LLM provider '${payload.provider}' configured for current session.`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        stateBus.emitSystemStatus({ db: "connected", python: "ready", llm: "error" });
        stateBus.emitSystemLog("error", `Failed to initialize Pi session after API key save: ${msg}`);
      }
    }

    return { ok: true, apiKeyStatus: getSettingsStore().getAll().apiKeyStatus };
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
  const config = payload.config
    ? `\nRun config: ${JSON.stringify(payload.config)}`
    : "";

  return `## New Talent Sourcing Task

Run ID: ${runId}
Job Title: ${payload.jobTitle}

### Job Description
${payload.jdText}
${skills}${domains}${config}

The run has been created (run_id="${runId}"). Begin orchestrating the talent sourcing pipeline.
Analyze the JD, design your search strategy, spawn subagents as needed, and find the best
China-based candidates for this role.`;
}
