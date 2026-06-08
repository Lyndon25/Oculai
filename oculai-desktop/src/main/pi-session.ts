// @ts-nocheck — Pi SDK API surface has breaking changes in v0.78.x.
// Runtime compatibility is maintained; type-checking is deferred to SDK upgrade.
/**
 * Pi Session — creates and manages a Pi AgentSession with Oculai tools.
 *
 * Uses the Pi SDK (createAgentSession) to embed Pi directly in the Electron
 * main process. Registers all 41 Oculai tools as Pi extension tools that
 * delegate to the Python sidecar via ToolBridge.
 *
 * Reference: pi-windows-x64/examples/sdk/12-full-control.ts
 */
import "./runtime-compat.js";
import { app } from "electron";
import { join } from "path";
import { existsSync, mkdirSync } from "fs";
import { getSettingsStore } from "./settings-store.js";
import { stateBus } from "./state-bus.js";
import { ToolBridge } from "./tool-bridge.js";
import { PostgresManager } from "./postgres-manager.js";
import { getOculaiSystemPrompt } from "../shared/prompts.js";
import { OCULAI_TOOLS } from "./generated-tools.js";

let session: any = null;
let agentDir: string;
let createExtensionRuntimeImpl: any = null;

async function loadPiRuntime() {
  const [{ getModel }, sdk] = await Promise.all([
    import("@earendil-works/pi-ai"),
    import("@earendil-works/pi-coding-agent"),
  ]);
  createExtensionRuntimeImpl = sdk.createExtensionRuntime;
  return { getModel, ...sdk };
}

export function getSession() {
  return session;
}

/**
 * Initialize the Pi AgentSession with all Oculai tools registered.
 * Must be called after ToolBridge and PostgresManager are started.
 */
export async function initPiSession(
  toolBridge: ToolBridge,
  postgresManager: PostgresManager,
): Promise<void> {
  const {
    getModel,
    AuthStorage,
    createAgentSession,
    ModelRegistry,
    SessionManager,
    SettingsManager,
  } = await loadPiRuntime();
  const settings = getSettingsStore();
  const userData = app.getPath("userData");
  agentDir = join(userData, "pi-agent");
  if (!existsSync(agentDir)) {
    mkdirSync(agentDir, { recursive: true });
  }

  // ---- Auth & Model ----
  const authStorage = AuthStorage.create(join(agentDir, "auth.json"));

  // Set API keys from settings
  const llmProvider = settings.get("llmProvider");
  const apiKey = settings.getApiKey(llmProvider);
  if (apiKey) {
    authStorage.setRuntimeApiKey(llmProvider, apiKey);
  }

  const modelRegistry = ModelRegistry.inMemory(authStorage);
  const modelName = settings.get("llmModel");
  const model = getModel(llmProvider, modelName);
  if (!model) {
    stateBus.emitSystemLog("error", `Model not found: ${llmProvider}/${modelName}`);
    throw new Error(`Model not found: ${llmProvider}/${modelName}`);
  }

  // ---- Settings ----
  const settingsManager = SettingsManager.inMemory({
    compaction: { enabled: true },
    retry: { enabled: true, maxRetries: 3 },
  });

// ---- Inline Oculai Subagent Profiles ----
// These concise role definitions replace the deleted markdown files in
// oculai/agents/ and oculai-desktop/resources/agents/. They are passed to
// Pi's ResourceLoader.getAgentsFiles() for subagent discovery.

interface AgentFileDef {
  path: string;
  content: string;
}

function getOculaiAgentFiles(): AgentFileDef[] {
  return [
    {
      path: "oculai-search-strategist.md",
      content: `# Search Strategist
Analyze a job description and design a multi-source search strategy for Chinese talent sourcing.

## Input
- Job title, JD text, required skills, target domains

## Output
- 2-4 talent profiles (target persona, why they match, initial queries, expected signals)
- Source hypotheses per profile (at least 2 targeting Tier 1 Chinese platforms: zhihu, juejin, csdn, baidu_qianfan)
- Query terminology in both Chinese and English
- Pivot strategies for low-yield searches

## Rules
- At least 50% of hypotheses must be discoverable via Chinese platforms
- Include Chinese-language query terms alongside English equivalents
- Target Chinese institutions when proposing Western academic sources`,
    },
    {
      path: "oculai-source-researcher.md",
      content: `# Source Researcher
Search a specific data source for candidates matching a given hypothesis. Operate in iterative think-search-refine mode.

## Available Tools
- oculai_search_source — search the source with keywords
- oculai_fetch_source_detail — get detailed profile for a specific entity
- oculai_record_iteration — log each think/search/classify step
- oculai_broadcast_discovery — share terminology findings with parallel agents

## Process
1. THINK: 2-4 sentences on the hypothesis and expected signals
2. SEARCH: Execute query with Chinese+English terms
3. OBSERVE: Classify results by type (profile_page/article/web_page/etc.) and confidence
4. ADJUST: Refine query based on results — discover new terminology, pivot if noisy
5. VERIFY: Cross-source confirm high-value candidates before upserting

## Rules
- Max 6 search calls per source to avoid quota exhaustion
- Prioritize result_type='profile_page' over articles/web_pages
- Search Chinese platforms with Chinese queries, Western sources with bilingual queries
- Broadcast discovered terminology via oculai_broadcast_discovery`,
    },
    {
      path: "oculai-query-optimizer.md",
      content: `# Query Optimizer
Refine search queries when initial results are noisy, sparse, skewed, or show terminology mismatches.

## When to Invoke
- High false positive rate (>50% non-person results)
- Terminology mismatch (HR terms vs. candidate self-descriptions)
- Population skew (e.g., 80% academics when JD needs industry engineers)
- Source saturation (same candidates across iterations)

## Process
1. Review current query performance and result quality
2. Identify mismatch patterns (wrong result types, wrong populations, wrong terminology)
3. Propose refined queries with adjusted terminology, signals, and source targeting
4. Recommend source switches if a source is fundamentally unsuited`,
    },
    {
      path: "oculai-identity-resolver.md",
      content: `# Identity Resolver
Merge duplicate candidates across sources and link external identities.

## Process
1. Cross-reference candidates by external IDs (ORCID, GitHub, DBLP, etc.)
2. Match by name + institution (ILIKE)
3. Fuzzy trigram matching for Chinese name variations (simplified/traditional, English variants)
4. Link confirmed identities via oculai_link_identity

## Rules
- Handle Chinese name variations: simplified/traditional characters, English transliteration variants
- Flag conflicts for manual review (conflicting non-NULL values → DataConflict records)
- Confidence threshold: similarity > 0.7 for automatic linking`,
    },
    {
      path: "oculai-profile-enricher.md",
      content: `# Profile Enricher
Deep-dive candidate profiles to gather comprehensive evidence. Chinese platforms first, then Western.

## Available Tools
- oculai_fetch_source_detail — deep profile lookups on specific platforms
- oculai_crawl_site — BFS crawl personal homepages, lab pages
- oculai_capture_page_evidence — capture web-based profiles as evidence
- oculai_attach_evidence — attach findings with auto-assigned quality tier

## Priority Order
1. Chinese platforms: zhihu, juejin, csdn, baidu_scholar (T2 evidence)
2. Chinese institution homepages (.edu.cn, lab pages) (T1 evidence)
3. GitHub repositories with substantive contributions (T1 evidence)
4. Western academic sources: Semantic Scholar, DBLP, Google Scholar (T2-T3 evidence)

## Rules
- Every candidate MUST have ≥1 Chinese platform evidence item
- Flag candidates with china_evidence: missing
- Record each enrichment cycle via oculai_record_iteration`,
    },
    {
      path: "oculai-fit-evaluator.md",
      content: `# Fit Evaluator
Score candidates on multiple assessment dimensions against the JD requirements.

## Process
1. Create a review session via oculai_create_review_session
2. Score each candidate on relevant dimensions (academic, engineering, leadership, etc.)
3. Use role-type appropriate weights from the assessment module
4. Enforce must-pass gates (skill_match < 4 caps overall score)
5. All scores MUST reference specific evidence IDs

## Assessment Dimensions
academic, engineering, leadership, communication, culture_fit, skill_match, location, career_stage, mobility, overall

## Rules
- Confidence bands: High (0.8-1.0), Medium (0.5-0.8), Low (0.2-0.5), None (<0.2)
- Include key uncertainties and evidence gaps for each assessment
- Default location preference: China`,
    },
    {
      path: "oculai-quality-auditor.md",
      content: `# Quality Auditor
Audit the final shortlist for quality, compliance, bias, and completeness.

## Audit Dimensions
1. Chinese candidate coverage — non-Chinese ratio must be <10%
2. Evidence completeness — high scores (≥80) must have ≥1 T1 evidence
3. Identity merge accuracy — no duplicates or incorrectly merged candidates
4. Bias risks — institutional clustering, regional concentration, gender balance
5. Score consistency — outlier detection across evaluators
6. Diversity — institution, geography, background distribution
7. Compliance — data source usage, PII handling

## Actions
- Apply adjustments via oculai_apply_audit_adjustments
- Finalize via oculai_finalize_review_session
- Flag any non-Chinese candidates with justification for the <10% exception rule`,
    },
    {
      path: "oculai-outreach-strategist.md",
      content: `# Outreach Strategist
Generate outreach drafts for shortlisted candidates. NEVER send without human approval.

## Process
1. Review each candidate's profile, evidence, and assessment
2. Draft personalized outreach in Chinese (use 老师 honorific for senior researchers)
3. Reference specific evidence (publications, projects, expertise)
4. Create drafts via oculai_create_outreach_draft
5. Submit for human approval via oculai_request_human_approval

## Rules
- NEVER send outreach autonomously — human approval is MANDATORY
- Default language: Chinese
- Personalize each message with candidate-specific details
- Check approval status via oculai_check_approval_status`,
    },
  ];
}

// ---- Pi ResourceLoader ----

const oculaiAgentFiles = getOculaiAgentFiles();

  // ---- Resource Loader (custom for Oculai) ----
  const systemPrompt = getOculaiSystemPrompt(postgresManager.getConnectionString());
  const resourceLoader = {
    getExtensions: () => ({
      extensions: [],
      errors: [],
      runtime: createOculaiExtensionRuntime(toolBridge),
    }),
    getSkills: () => ({ skills: [], diagnostics: [] }),
    getPrompts: () => ({ prompts: [], diagnostics: [] }),
    getThemes: () => ({ themes: [], diagnostics: [] }),
    getAgentsFiles: () => ({ agentsFiles: oculaiAgentFiles }),
    getSystemPrompt: () => systemPrompt,
    getAppendSystemPrompt: () => [],
    extendResources: () => {},
    reload: async () => {},
  };

  // ---- Create Session ----
  const result = await createAgentSession({
    cwd: app.getPath("userData"),
    agentDir,
    model,
    thinkingLevel: settings.get("thinkingLevel"),
    authStorage,
    modelRegistry,
    resourceLoader,
    tools: [], // We register all tools via the extension runtime
    sessionManager: SessionManager.create(join(agentDir, "sessions")),
    settingsManager,
  });

  session = result.session;

  // ---- Subscribe to agent events → IPC ----
  session.subscribe((event) => {
    if (event.type === "message_update") {
      const msgEvent = event.assistantMessageEvent;
      if (msgEvent.type === "text_delta") {
        stateBus.emitMessage(msgEvent.delta);
      } else if (msgEvent.type === "thinking_delta") {
        stateBus.emitThinking(msgEvent.delta);
      }
    } else if (event.type === "tool_execution_start") {
      const params = event.toolCall.arguments as Record<string, unknown>;
      stateBus.emitToolCall(
        event.toolCall.name,
        params,
      );
      emitDashboardSignalForToolStart(event.toolCall.name, params);
    } else if (event.type === "tool_execution_end") {
      const result = event.toolResult?.result as Record<string, unknown> | undefined;
      stateBus.emitToolResult(
        event.toolCall.name,
        result || {},
        event.toolResult?.isError || false,
      );
      emitDashboardSignalForToolEnd(
        event.toolCall.name,
        event.toolCall.arguments as Record<string, unknown>,
        result || {},
        event.toolResult?.isError || false,
      );
    }
  });

  stateBus.emitSystemLog("info", `Pi AgentSession initialized with model ${modelName}`);
}

const TOOL_PHASES: Record<string, string> = {
  oculai_create_run: "init",
  oculai_list_source_capabilities: "strategy",
  oculai_checkpoint_plan: "strategy",
  oculai_search_source: "searching",
  oculai_fetch_source_detail: "searching",
  oculai_deep_search: "searching",
  oculai_upsert_candidate: "searching",
  oculai_upsert_candidates_batch: "searching",
  oculai_link_identity: "identity_resolution",
  oculai_get_candidate: "enrichment",
  oculai_capture_page_evidence: "enrichment",
  oculai_attach_evidence: "enrichment",
  oculai_get_evidence: "enrichment",
  oculai_record_assessment: "evaluation",
  oculai_score_candidate: "evaluation",
  oculai_create_review_session: "audit",
  oculai_finalize_review_session: "shortlist",
  oculai_export_report: "complete",
  oculai_create_outreach_draft: "outreach",
  oculai_request_human_approval: "outreach",
};

const TOOL_ACTIONS: Record<string, string> = {
  oculai_record_iteration: "think",
  oculai_search_source: "search",
  oculai_fetch_source_detail: "search",
  oculai_deep_search: "search",
  oculai_broadcast_discovery: "broadcast",
  oculai_upsert_candidate: "upsert",
  oculai_upsert_candidates_batch: "upsert",
  oculai_attach_evidence: "found",
  oculai_record_assessment: "score",
  oculai_score_candidate: "score",
  oculai_create_review_session: "audit",
  oculai_finalize_review_session: "audit",
  oculai_export_report: "export",
};

function getRunId(params: Record<string, unknown>, result?: Record<string, unknown>): string | null {
  const value = params.run_id ?? params.runId ?? result?.run_id ?? result?.runId;
  return value ? String(value) : null;
}

function parseToolResult(result: Record<string, unknown>): Record<string, unknown> {
  const content = result?.content;
  if (Array.isArray(content)) {
    const first = content[0] as { text?: unknown } | undefined;
    if (typeof first?.text === "string") {
      try {
        return JSON.parse(first.text) as Record<string, unknown>;
      } catch {
        return result;
      }
    }
  }
  return result;
}

function toolLabel(name: string): string {
  return name.replace(/^oculai_/, "").replace(/_/g, " ");
}

function emitDashboardSignalForToolStart(name: string, params: Record<string, unknown>): void {
  const runId = getRunId(params);
  const phase = TOOL_PHASES[name];
  if (runId && phase) {
    stateBus.emitPhaseChange(runId, phase as never);
  }

  const action = TOOL_ACTIONS[name];
  if (runId && action) {
    stateBus.emitSubagentProgress(`tool:${name}`, {
      timestamp: new Date().toISOString(),
      agentId: `tool:${name}`,
      agentType: "Oculai Tool",
      action: action as never,
      message: `开始执行 ${toolLabel(name)}`,
      detail: typeof params.source_name === "string" ? params.source_name : undefined,
    });
  }
}

function emitDashboardSignalForToolEnd(
  name: string,
  params: Record<string, unknown>,
  rawResult: Record<string, unknown>,
  isError: boolean,
): void {
  const result = parseToolResult(rawResult);
  const runId = getRunId(params, result);
  const action = isError ? "error" : TOOL_ACTIONS[name];

  if (runId && action) {
    stateBus.emitSubagentProgress(`tool:${name}`, {
      timestamp: new Date().toISOString(),
      agentId: `tool:${name}`,
      agentType: "Oculai Tool",
      action: action as never,
      message: isError ? `${toolLabel(name)} 执行失败` : `${toolLabel(name)} 执行完成`,
      detail: isError ? "查看 Logs" : undefined,
    });
  }

  if (!isError && name === "oculai_upsert_candidate") {
    const personData = (params.person_data || {}) as Record<string, unknown>;
    const personId = String(result.person_id || "");
    if (personId) {
      stateBus.emitCandidateUpserted(
        personId,
        String(personData.name || result.name || "Unknown candidate"),
        typeof personData.institution === "string" ? personData.institution : undefined,
        typeof params.source_name === "string" ? params.source_name : undefined,
      );
    }
  }

  if (!isError && name === "oculai_upsert_candidates_batch" && Array.isArray(result.accepted)) {
    for (const accepted of result.accepted as Array<Record<string, unknown>>) {
      const personId = String(accepted.person_id || "");
      if (!personId) continue;
      stateBus.emitCandidateUpserted(
        personId,
        String(accepted.name || "Unknown candidate"),
        undefined,
        typeof params.source_name === "string" ? params.source_name : undefined,
      );
    }
  }
}

/**
 * Create a Pi extension runtime that registers all Oculai tools.
 * Each tool delegates to the Python sidecar via ToolBridge.
 */
function createOculaiExtensionRuntime(bridge: ToolBridge) {
  if (!createExtensionRuntimeImpl) {
    throw new Error("Pi extension runtime is not loaded");
  }
  const runtime = createExtensionRuntimeImpl();

  // Register all 41 Oculai tools
  for (const [name, schema] of Object.entries(OCULAI_TOOLS)) {
    runtime.registerTool({
      name,
      description: schema.description,
      parameters: schema.parameters,
      async execute(_toolCallId, params) {
        try {
          stateBus.emitSystemLog("debug", `Tool call: ${name}`);
          const result = await bridge.callTool(name, params as Record<string, unknown>);
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          stateBus.emitSystemLog("error", `Tool '${name}' failed: ${msg}`);
          return {
            content: [{ type: "text", text: `Error: ${msg}` }],
            isError: true,
          };
        }
      },
    });
  }

  return runtime;
}

/** Dispose of the Pi session. */
export function disposeSession(): void {
  if (session) {
    session.dispose();
    session = null;
  }
}
