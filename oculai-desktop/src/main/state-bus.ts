/**
 * State Bus — EventEmitter that bridges agent events to renderer IPC.
 *
 * The Pi AgentSession produces events (message_update, tool_execution_start, etc.).
 * The StateBus translates these into typed IPC events and sends them to the
 * renderer process via BrowserWindow.webContents.send().
 */
import { BrowserWindow } from "electron";
import { IPC_CHANNELS } from "../shared/ipc-channels.js";
import type {
  AgentMessageEvent,
  AgentThinkingEvent,
  AgentToolCallEvent,
  AgentToolResultEvent,
  CandidateUpsertedEvent,
  OrchestratorPhaseEvent,
  ReportReadyEvent,
  RunCreatedEvent,
  RunErrorEvent,
  SubagentCompletedEvent,
  SubagentProgressEvent,
  SubagentSpawnedEvent,
  SystemLogEvent,
  SystemStatusEvent,
} from "../shared/events.js";
import type { PipelinePhase, SubagentState, SystemStatus, ActivityEntry } from "../shared/types.js";

export class StateBus {
  private mainWindow: BrowserWindow | null = null;

  setWindow(win: BrowserWindow): void {
    this.mainWindow = win;
  }

  private send(channel: string, payload: unknown): void {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send(channel, payload);
    }
  }

  // ---- Agent streaming ----

  emitThinking(delta: string): void {
    this.send(IPC_CHANNELS.AGENT_THINKING, { delta } satisfies AgentThinkingEvent);
  }

  emitMessage(text: string): void {
    this.send(IPC_CHANNELS.AGENT_MESSAGE, { text } satisfies AgentMessageEvent);
  }

  emitToolCall(toolName: string, input: Record<string, unknown>): void {
    this.send(IPC_CHANNELS.AGENT_TOOL_CALL, { toolName, input } satisfies AgentToolCallEvent);
  }

  emitToolResult(toolName: string, output: Record<string, unknown>, isError = false): void {
    this.send(IPC_CHANNELS.AGENT_TOOL_RESULT, {
      toolName,
      output,
      isError,
    } satisfies AgentToolResultEvent);
  }

  // ---- Run events ----

  emitRunCreated(runId: string, title: string, status: string): void {
    this.send(IPC_CHANNELS.RUN_CREATED, { runId, title, status } satisfies RunCreatedEvent);
  }

  emitRunError(runId: string, error: string, phase: string): void {
    this.send(IPC_CHANNELS.RUN_ERROR, { runId, error, phase } satisfies RunErrorEvent);
  }

  // ---- Orchestrator ----

  emitPhaseChange(runId: string, phase: PipelinePhase, metrics?: OrchestratorPhaseEvent["metrics"]): void {
    this.send(IPC_CHANNELS.ORCHESTRATOR_PHASE, {
      runId,
      phase,
      metrics,
    } satisfies OrchestratorPhaseEvent);
  }

  // ---- Subagent lifecycle ----

  emitSubagentSpawned(agentId: string, agentType: string, target: string): void {
    this.send(IPC_CHANNELS.SUBAGENT_SPAWNED, {
      agentId,
      agentType,
      target,
      status: "active" as SubagentState["status"],
    } satisfies SubagentSpawnedEvent);
  }

  emitSubagentProgress(agentId: string, activity: ActivityEntry): void {
    this.send(IPC_CHANNELS.SUBAGENT_PROGRESS, {
      agentId,
      activity,
    } satisfies SubagentProgressEvent);
  }

  emitSubagentCompleted(
    agentId: string,
    agentType: string,
    target: string,
    status: "done" | "error",
    resultCount?: number,
    error?: string,
  ): void {
    this.send(IPC_CHANNELS.SUBAGENT_COMPLETED, {
      agentId,
      agentType,
      target,
      status,
      resultCount,
      error,
    } satisfies SubagentCompletedEvent);
  }

  // ---- Candidates ----

  emitCandidateUpserted(personId: string, name: string, institution?: string, sourceName?: string): void {
    this.send(IPC_CHANNELS.CANDIDATE_UPSERTED, {
      personId,
      name,
      institution: institution ?? "",
      sourceName: sourceName ?? "",
    } satisfies CandidateUpsertedEvent);
  }

  // ---- Report ----

  emitReportReady(runId: string, html: string, format: string): void {
    this.send(IPC_CHANNELS.REPORT_READY, { runId, html, format } satisfies ReportReadyEvent);
  }

  // ---- System ----

  emitSystemStatus(status: SystemStatus): void {
    this.send(IPC_CHANNELS.SYSTEM_STATUS, { status } satisfies SystemStatusEvent);
  }

  emitSystemLog(level: SystemLogEvent["level"], message: string): void {
    this.send(IPC_CHANNELS.SYSTEM_LOG, {
      level,
      message,
      timestamp: new Date().toISOString(),
    } satisfies SystemLogEvent);
  }
}

/** Singleton state bus instance. */
export const stateBus = new StateBus();
