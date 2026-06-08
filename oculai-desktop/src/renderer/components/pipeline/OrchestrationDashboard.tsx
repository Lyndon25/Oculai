import { useStore } from "../../store/index.js";
import { useMemo } from "react";
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
  Clock,
  AlertTriangle,
  Radio,
  Tags,
  UserPlus,
  BarChart3,
  Microscope,
  FileOutput,
  Zap,
} from "lucide-react";
import type React from "react";
import type { PipelinePhase, SubagentState } from "../../../shared/types.js";
import { EmptyState, cx } from "../ui/primitives.js";

const PHASE_LABELS: Record<PipelinePhase, string> = {
  init: "初始化",
  strategy: "策略",
  searching: "搜索",
  identity_resolution: "身份合并",
  enrichment: "证据补全",
  evaluation: "评估",
  audit: "审计",
  shortlist: "短名单",
  outreach: "触达",
  complete: "完成",
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

const STATUS_STYLE: Record<SubagentState["status"], string> = {
  idle: "border-rule bg-surface",
  active: "border-accent/30 bg-accent-soft",
  done: "border-emerald-200 bg-emerald-50/60",
  error: "border-red-200 bg-red-50/60",
};

const STATUS_DOT: Record<SubagentState["status"], string> = {
  idle: "bg-rule-strong",
  active: "bg-accent animate-pulse",
  done: "bg-emerald-500",
  error: "bg-red-500",
};

export function OrchestrationDashboard() {
  const orchestratorPhase = useStore((s) => s.orchestratorPhase);
  const subagents = useStore((s) => s.subagents);
  const activityFeed = useStore((s) => s.activityFeed);
  const candidates = useStore((s) => s.candidates);

  const currentPhaseIdx = Math.max(0, PHASE_ORDER.indexOf(orchestratorPhase));
  const activeCount = subagents.filter((a) => a.status === "active").length;
  const doneCount = subagents.filter((a) => a.status === "done").length;
  const errorCount = subagents.filter((a) => a.status === "error").length;
  const toolEvents = activityFeed.filter((entry) => entry.agentType === "Oculai Tool").length;
  const reversedActivity = useMemo(() => [...activityFeed].reverse(), [activityFeed]);

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="mx-auto max-w-7xl space-y-5">
        {/* KPI Row */}
        <div className="grid gap-3 md:grid-cols-4">
          <KpiCard icon={Activity} label="当前阶段" value={PHASE_LABELS[orchestratorPhase]} />
          <KpiCard icon={Zap} label="运行中 Agent" value={String(activeCount)} />
          <KpiCard icon={Users} label="候选人" value={String(candidates.length)} />
          <KpiCard icon={Radio} label="工具事件" value={String(toolEvents)} />
        </div>

        {/* Phase Indicator */}
        <div className="panel p-4">
          <div className="mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4 text-accent" aria-hidden="true" />
            <span className="text-sm font-semibold text-ink">
              {PHASE_LABELS[orchestratorPhase]}
            </span>
            <span className="ml-auto text-xs text-ink-muted">
              {activeCount} active · {doneCount} done · {candidates.length} candidates
            </span>
          </div>
          <div className="grid grid-cols-5 gap-2 lg:grid-cols-10">
            {PHASE_ORDER.map((phase, idx) => {
              const isCurrent = idx === currentPhaseIdx;
              const isDone = idx < currentPhaseIdx;
              return (
                <div key={phase} className="min-w-0">
                  <div
                    className={cx(
                      "h-1.5 rounded-full transition-all duration-300",
                      isCurrent
                        ? "bg-accent"
                        : isDone
                          ? "bg-emerald-400"
                          : "bg-rule",
                    )}
                  />
                  <div
                    className={cx(
                      "mt-1 truncate text-[10px] font-medium transition-colors",
                      isCurrent
                        ? "text-accent"
                        : isDone
                          ? "text-emerald-600"
                          : "text-ink-muted",
                    )}
                    title={PHASE_LABELS[phase]}
                  >
                    {PHASE_LABELS[phase]}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Two-column */}
        <div className="grid gap-5 xl:grid-cols-[1fr_24rem]">
          {/* Agent Grid */}
          <div className="panel p-4">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <Brain className="h-4 w-4 text-accent" aria-hidden="true" />
              Agent Pool
              <span className="ml-auto text-xs font-normal text-ink-muted">
                {subagents.length} total · {activeCount} running · {doneCount} done
                {errorCount > 0 ? ` · ${errorCount} failed` : ""}
              </span>
            </h3>

            {subagents.length === 0 ? (
              <EmptyState
                icon={Brain}
                title="等待 Pi 派生专业 Agent"
                description="当前通过工具事件展示 pipeline 进展，Agent 生命周期数据会实时显示。"
              />
            ) : (
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-4">
                {subagents.map((agent) => {
                  const Icon = AGENT_ICONS[agent.agentType] || Brain;
                  return (
                    <div
                      key={agent.agentId}
                      className={cx("rounded-xl border p-3 transition-all duration-200", STATUS_STYLE[agent.status])}
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <Icon
                          className={cx(
                            "h-4 w-4",
                            agent.status === "active"
                              ? "text-accent"
                              : agent.status === "done"
                                ? "text-emerald-600"
                                : agent.status === "error"
                                  ? "text-red-500"
                                  : "text-ink-muted",
                          )}
                          aria-hidden="true"
                        />
                        <span className={cx("inline-block h-2 w-2 rounded-full", STATUS_DOT[agent.status])} />
                      </div>
                      <div className="truncate text-xs font-semibold text-ink">{agent.agentType}</div>
                      <div className="mt-0.5 truncate text-[11px] text-ink-muted">{agent.target}</div>
                      {agent.resultCount !== undefined && agent.status === "done" && (
                        <div className="mt-1 text-[11px] font-medium text-emerald-600">{agent.resultCount} results</div>
                      )}
                      {agent.status === "error" && agent.error && (
                        <div className="mt-1 truncate text-[11px] text-red-500">{agent.error}</div>
                      )}
                      {agent.spawnedAt && (
                        <div className="mt-2 flex items-center gap-1 text-[10px] text-ink-muted">
                          <Clock className="h-3 w-3" aria-hidden="true" />
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
          <div className="panel flex min-h-[28rem] flex-col p-4">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
              <Activity className="h-4 w-4 text-accent" aria-hidden="true" />
              Live Activity
              <span className="ml-auto text-xs font-normal text-ink-muted">{activityFeed.length} events</span>
            </h3>

            <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
              {activityFeed.length === 0 ? (
                <EmptyState
                  icon={Activity}
                  title="暂无活动"
                  description="搜索、证据、评分和系统日志会在这里实时显示。"
                />
              ) : (
                reversedActivity.map((entry, i) => (
                  <ActivityRow key={`${entry.timestamp}-${i}-${entry.agentId ?? ""}`} entry={entry} />
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── KPI Card ─── */
function KpiCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{label}</div>
          <div className="mt-1 font-display text-2xl font-bold text-ink">{value}</div>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-soft">
          <Icon className="h-5 w-5 text-accent" aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}

/* ─── Activity Row ─── */
function ActivityRow({ entry }: { entry: import("../../../shared/types.js").ActivityEntry }) {
  const actionMeta: Record<string, { icon: React.ComponentType<{ className?: string }>; className: string; label: string }> = {
    think: { icon: Brain, label: "思考", className: "border-purple-200 bg-purple-50/60" },
    search: { icon: Search, label: "搜索", className: "border-blue-200 bg-blue-50/60" },
    found: { icon: CheckCircle, label: "发现", className: "border-emerald-200 bg-emerald-50/60" },
    classify: { icon: Tags, label: "分类", className: "border-amber-200 bg-amber-50/60" },
    broadcast: { icon: Radio, label: "广播", className: "border-cyan-200 bg-cyan-50/60" },
    upsert: { icon: UserPlus, label: "入库", className: "border-emerald-200 bg-emerald-50/60" },
    score: { icon: BarChart3, label: "评分", className: "border-orange-200 bg-orange-50/60" },
    audit: { icon: Microscope, label: "审计", className: "border-pink-200 bg-pink-50/60" },
    export: { icon: FileOutput, label: "导出", className: "border-indigo-200 bg-indigo-50/60" },
    error: { icon: AlertTriangle, label: "错误", className: "border-red-200 bg-red-50/60" },
  };

  const meta = actionMeta[entry.action] || {
    icon: Activity,
    label: entry.action,
    className: "border-rule bg-surface-hover",
  };
  const Icon = meta.icon;

  return (
    <div className={cx("rounded-lg border p-2 text-xs", meta.className)}>
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[10px] text-ink-muted">
            <span className="font-mono">{new Date(entry.timestamp).toLocaleTimeString()}</span>
            <span className="font-medium">{meta.label}</span>
            {entry.agentType && <span className="truncate">{entry.agentType}</span>}
          </div>
          <div className="mt-0.5 break-words text-ink-secondary">{entry.message}</div>
          {entry.detail && (
            <div className="mt-0.5 truncate text-[11px] text-ink-muted">{entry.detail}</div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatRelativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const secs = Math.floor(diff / 1000);
    if (secs < 60) return `${secs}s`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m`;
    return `${Math.floor(mins / 60)}h`;
  } catch {
    return "";
  }
}
