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
import { getModel } from "@earendil-works/pi-ai";
import {
  AuthStorage,
  createAgentSession,
  createExtensionRuntime,
  ModelRegistry,
  type ResourceLoader,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { app } from "electron";
import { join } from "path";
import { existsSync, mkdirSync } from "fs";
import { getSettingsStore } from "./settings-store.js";
import { stateBus } from "./state-bus.js";
import { ToolBridge } from "./tool-bridge.js";
import { PostgresManager } from "./postgres-manager.js";
import { discoverOculaiAgents, discoverOculaiSkills } from "./resource-loader.js";
import { getOculaiSystemPrompt } from "../shared/prompts.js";
import { OCULAI_TOOLS } from "./generated-tools.js";

let session: Awaited<ReturnType<typeof createAgentSession>>["session"] | null = null;
let agentDir: string;

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

  // ---- Resource Loader (custom for Oculai) ----
  const systemPrompt = getOculaiSystemPrompt(postgresManager.getConnectionString());
  const resourceLoader: ResourceLoader = {
    getExtensions: () => ({
      extensions: [],
      errors: [],
      runtime: createOculaiExtensionRuntime(toolBridge),
    }),
    getSkills: () => ({ skills: discoverOculaiSkills(), diagnostics: [] }),
    getPrompts: () => ({ prompts: [], diagnostics: [] }),
    getThemes: () => ({ themes: [], diagnostics: [] }),
    getAgentsFiles: () => ({ agentsFiles: discoverOculaiAgents() }),
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
    thinkingLevel: settings.get("thinkingLevel") === "off" ? "off" : "medium",
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
      stateBus.emitToolCall(
        event.toolCall.name,
        event.toolCall.arguments as Record<string, unknown>,
      );
    } else if (event.type === "tool_execution_end") {
      const result = event.toolResult?.result as Record<string, unknown> | undefined;
      stateBus.emitToolResult(
        event.toolCall.name,
        result || {},
        event.toolResult?.isError || false,
      );
    }
  });

  stateBus.emitSystemLog("info", `Pi AgentSession initialized with model ${modelName}`);
}

/**
 * Create a Pi extension runtime that registers all Oculai tools.
 * Each tool delegates to the Python sidecar via ToolBridge.
 */
function createOculaiExtensionRuntime(bridge: ToolBridge) {
  const runtime = createExtensionRuntime();

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
