import { useStore } from "../../store/index.js";
import { useState } from "react";
import {
  Brain,
  Search,
  Users,
  FileSearch,
  Target,
  CheckCircle,
  Send,
  Wand2,
  Activity,
  ChevronDown,
  ChevronUp,
  Clock,
} from "lucide-react";
import type { PipelinePhase, SubagentState } from "../../../shared/types.js";

const PHASE_LABELS: Record<PipelinePhase, string> = {
  init: "Initializing",
  strategy: "Strategy",
  searching: "Searching",
  identity_resolution: "Identity Resolution",
  enrichment: "Enrichment",
  evaluation: "Evaluation",
  audit: "Audit",
  shortlist: "Shortlist",
  outreach: "Outreach",
  complete: "Complete",
};

const PHASE_ORDER: PipelinePhase[] = [
  "init", "strategy", "searching", "identity_resolution",
  "enrichment", "evaluation", "audit", "shortlist", "outreach", "complete",
];

const AGENT_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  "Search Strategist": Brain,
  "Source Researcher": Search,
  "Query Optimizer": Wand2,
  "Identity Resolver": Users,
  "Profile Enricher": FileSearch,
  "Fit Evaluator": Target,
  "Quality Auditor": CheckCircle,
  "Outreach Strategist": Send,
};

const STATUS_COLORS: Record<SubagentState["status"], string> = {
  idle: "border-gray-700 bg-gray-900/50",
  active: "border-blue-500/50 bg-blue-900/20 animate-pulse",
  done: "border-green-500/30 bg-green-900/20",
  error: "border-red-500/30 bg-red-900/20",
};

const STATUS_DOTS: Record<SubagentState["status"], string> = {
  idle: "bg-gray-600",
  active: "bg-blue-400 animate-pulse",
  done: "bg-green-400",
  error: "bg-red-400",
};

export function OrchestrationDashboard() {
  const orchestratorPhase = useStore((s) => s.orchestratorPhase);
  const subagents = useStore((s) => s.subagents);
  const activityFeed = useStore((s) => s.activityFeed);
  const candidates = useStore((s) => s.candidates);

  const currentPhaseIdx = PHASE_ORDER.indexOf(orchestratorPhase);

  const activeCount = subagents.filter((a) => a.status === "active").length;
  const doneCount = subagents.filter((a) => a.status === "done").length;
  const errorCount = subagents.filter((a) => a.status === "error").length;

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* Phase Indicator */}
      <div className="panel p-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-semibold text-gray-300">
            {PHASE_LABELS[orchestratorPhase]}
          </span>
          <span className="text-xs text-gray-600 ml-auto">
            {activeCount} active · {doneCount} done · {candidates.length} candidates
          </span>
        </div>
        <div className="flex items-center gap-1">
          {PHASE_ORDER.map((phase, idx) => {
            const isCurrent = idx === currentPhaseIdx;
            const isDone = idx < currentPhaseIdx;
            const isPending = idx > currentPhaseIdx;

            return (
              <div key={phase} className="flex items-center gap-1 flex-1">
                <div
                  className={`flex-1 h-1.5 rounded-full transition-all ${
                    isCurrent
                      ? "bg-blue-500"
                      : isDone
                        ? "bg-green-500/50"
                        : "bg-gray-800"
                  }`}
                />
                {idx < PHASE_ORDER.length - 1 && (
                  <div className={`w-1 h-1 rounded-full ${isDone ? "bg-green-500/50" : "bg-gray-800"}`} />
                )}
              </div>
            );
          })}
        </div>
        <div className="flex items-center justify-between mt-2">
          {PHASE_ORDER.map((phase, idx) => (
            <span
              key={phase}
              className={`text-[10px] transition-colors ${
                idx === currentPhaseIdx
                  ? "text-blue-400 font-medium"
                  : idx < currentPhaseIdx
                    ? "text-green-500"
                    : "text-gray-700"
              }`}
            >
              {PHASE_LABELS[phase]}
            </span>
          ))}
        </div>
      </div>

      {/* Agent Grid */}
      <div className="panel p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <Brain className="w-4 h-4 text-purple-400" />
          Agents
          <span className="text-xs text-gray-600 ml-auto">
            {subagents.length} total · {activeCount} running · {doneCount} completed{errorCount > 0 ? ` · ${errorCount} failed` : ""}
          </span>
        </h3>

        {subagents.length === 0 ? (
          <div className="text-center py-8">
            <div className="w-10 h-10 rounded-full bg-gray-800 flex items-center justify-center mx-auto mb-2">
              <Brain className="w-5 h-5 text-gray-600" />
            </div>
            <p className="text-sm text-gray-600">Waiting for agents to spawn...</p>
            <p className="text-xs text-gray-700 mt-1">
              The orchestrator will deploy specialized subagents as the pipeline progresses.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {subagents.map((agent) => {
              const Icon = AGENT_ICONS[agent.agentType] || Brain;
              return (
                <div
                  key={agent.agentId}
                  className={`p-3 rounded-lg border transition-all ${STATUS_COLORS[agent.status]}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <Icon className={`w-4 h-4 ${
                      agent.status === "active" ? "text-blue-400" :
                      agent.status === "done" ? "text-green-400" :
                      agent.status === "error" ? "text-red-400" : "text-gray-600"
                    }`} />
                    <span className={`inline-block w-2 h-2 rounded-full ${STATUS_DOTS[agent.status]}`} />
                  </div>
                  <div className="text-xs font-medium text-gray-300 truncate">
                    {agent.agentType}
                  </div>
                  <div className="text-[10px] text-gray-500 truncate mt-0.5">
                    {agent.target}
                  </div>
                  {(agent.resultCount !== undefined && agent.status === "done") && (
                    <div className="text-[10px] text-green-400 mt-1">
                      {agent.resultCount} results
                    </div>
                  )}
                  {agent.status === "error" && agent.error && (
                    <div className="text-[10px] text-red-400 mt-1 truncate">
                      {agent.error}
                    </div>
                  )}
                  {agent.spawnedAt && (
                    <div className="text-[9px] text-gray-700 mt-1 flex items-center gap-1">
                      <Clock className="w-2.5 h-2.5" />
                      {formatRelativeTime(agent.spawnedAt)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Activity Feed */}
      <div className="panel p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <Activity className="w-4 h-4 text-yellow-400" />
          Live Activity
          <span className="text-xs text-gray-600 ml-auto">{activityFeed.length} events</span>
        </h3>

        <div className="space-y-1 max-h-80 overflow-y-auto">
          {activityFeed.length === 0 ? (
            <p className="text-sm text-gray-600 text-center py-4">
              Activity will appear here as agents work...
            </p>
          ) : (
            [...activityFeed].reverse().map((entry, i) => (
              <ActivityRow key={i} entry={entry} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function ActivityRow({ entry }: { entry: import("../../../shared/types.js").ActivityEntry }) {
  const actionColors: Record<string, string> = {
    think: "text-purple-400 border-purple-800/30 bg-purple-900/10",
    search: "text-blue-400 border-blue-800/30 bg-blue-900/10",
    found: "text-green-400 border-green-800/30 bg-green-900/10",
    classify: "text-yellow-400 border-yellow-800/30 bg-yellow-900/10",
    broadcast: "text-cyan-400 border-cyan-800/30 bg-cyan-900/10",
    upsert: "text-emerald-400 border-emerald-800/30 bg-emerald-900/10",
    score: "text-orange-400 border-orange-800/30 bg-orange-900/10",
    audit: "text-pink-400 border-pink-800/30 bg-pink-900/10",
    export: "text-indigo-400 border-indigo-800/30 bg-indigo-900/10",
    error: "text-red-400 border-red-800/30 bg-red-900/10",
  };

  const actionIcons: Record<string, string> = {
    think: "💭",
    search: "🔍",
    found: "✅",
    classify: "🏷️",
    broadcast: "📡",
    upsert: "👤",
    score: "📊",
    audit: "🔬",
    export: "📄",
    error: "❌",
  };

  return (
    <div className={`flex items-start gap-2 p-1.5 rounded text-xs border ${actionColors[entry.action] || "text-gray-400 border-gray-800/30"}`}>
      <span className="flex-shrink-0 text-[10px]">{actionIcons[entry.action] || "•"}</span>
      <span className="text-gray-600 flex-shrink-0 w-14 text-[10px]">
        {new Date(entry.timestamp).toLocaleTimeString()}
      </span>
      {entry.agentType && (
        <span className="text-gray-500 flex-shrink-0 font-medium text-[10px]">
          {entry.agentType}:
        </span>
      )}
      <span className="text-gray-300 flex-1 truncate">{entry.message}</span>
      {entry.detail && (
        <span className="text-gray-600 flex-shrink-0 text-[10px] truncate max-w-[120px]">
          {entry.detail}
        </span>
      )}
    </div>
  );
}

function formatRelativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const secs = Math.floor(diff / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    return `${Math.floor(mins / 60)}h ago`;
  } catch {
    return "";
  }
}
