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
  active: "border-accent/25 bg-accent-soft shadow-[0_2px_8px_rgba(232,93,63,0.08)]",
  done: "border-success-muted bg-success-soft/50",
  error: "border-error-muted bg-error-soft/50",
};

const STATUS_DOT_COLOR: Record<SubagentState["status"], string> = {
  idle: "bg-rule-strong",
  active: "bg-accent",
  done: "bg-success",
  error: "bg-error",
};

const AGENT_COLORS: Record<string, string> = {
  "Search Strategist": "border-l-accent",
  "Source Researcher": "border-l-blue-400",
  "Query Optimizer": "border-l-purple-400",
  "Identity Resolver": "border-l-emerald-400",
  "Profile Enricher": "border-l-amber-400",
  "Fit Evaluator": "border-l-rose-400",
  "Quality Auditor": "border-l-cyan-400",
  "Outreach Strategist": "border-l-indigo-400",
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
        {/* KPI Row · Visual cards */}
        <div className="grid gap-3 md:grid-cols-4">
          <KpiCard icon={Activity} label="当前阶段" value={PHASE_LABELS[orchestratorPhase]} accent />
          <KpiCard icon={Zap} label="运行中 Agent" value={String(activeCount)} />
          <KpiCard icon={Users} label="候选人" value={String(candidates.length)} />
          <KpiCard icon={Radio} label="工具事件" value={String(toolEvents)} />
        </div>

        {/* Phase River · Visual timeline */}
        <div className="card p-4">
          <div className="mb-3 flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-accent/8">
              <Activity className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
            </div>
            <span className="text-[13px] font-semibold text-ink tracking-tight">
              {PHASE_LABELS[orchestratorPhase]}
            </span>
            <span className="ml-auto text-[11px] text-ink-muted font-medium">
              {activeCount} active · {doneCount} done · {candidates.length} candidates
            </span>
          </div>
          <div className="grid grid-cols-5 gap-2 lg:grid-cols-10">
            {PHASE_ORDER.map((phase, idx) => {
              const isCurrent = idx === currentPhaseIdx;
              const isDone = idx < currentPhaseIdx;
              return (
                <div key={phase} className="min-w-0">
                  <div className="relative h-2 rounded-full bg-rule overflow-hidden">
                    <div
                      className={cx(
                        "absolute inset-0 rounded-full transition-all duration-500 ease-[var(--oc-spring-smooth)]",
                        isCurrent && "bg-accent",
                        isDone && "bg-success",
                      )}
                      style={{
                        width: isCurrent || isDone ? "100%" : "0%",
                      }}
                    />
                  </div>
                  <div
                    className={cx(
                      "mt-1.5 truncate text-[10px] font-medium transition-colors duration-300",
                      isCurrent && "text-accent",
                      isDone && "text-success",
                      !isCurrent && !isDone && "text-ink-muted",
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
        <div className="grid gap-5 xl:grid-cols-[1fr_26rem]">
          {/* Agent Grid */}
          <div className="card p-4">
            <div className="mb-3 flex items-center gap-2.5">
              <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-accent/8">
                <Brain className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
              </div>
              <h3 className="text-[13px] font-semibold text-ink tracking-tight">Agent Pool</h3>
              <span className="ml-auto text-[11px] text-ink-muted">
                {subagents.length} total · {activeCount} running · {doneCount} done
                {errorCount > 0 ? ` · ${errorCount} failed` : ""}
              </span>
            </div>

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
                  const agentColor = AGENT_COLORS[agent.agentType] || "border-l-accent";
                  return (
                    <div
                      key={agent.agentId}
                      className={cx(
                        "rounded-xl border-l-[3px] p-3 transition-all duration-300 ease-[var(--oc-spring-smooth)]",
                        agentColor,
                        STATUS_STYLE[agent.status],
                      )}
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <Icon
                          className={cx(
                            "h-4 w-4",
                            agent.status === "active"
                              ? "text-accent"
                              : agent.status === "done"
                                ? "text-success"
                                : agent.status === "error"
                                  ? "text-error"
                                  : "text-ink-muted",
                          )}
                          aria-hidden="true"
                        />
                        <span
                          className={cx(
                            "inline-block h-2 w-2 rounded-full",
                            STATUS_DOT_COLOR[agent.status],
                            agent.status === "active" && "animate-breathe shadow-[0_0_6px_rgba(232,93,63,0.3)]",
                          )}
                        />
                      </div>
                      <div className="truncate text-[12px] font-semibold text-ink tracking-tight">
                        {agent.agentType}
                      </div>
                      <div className="mt-0.5 truncate text-[11px] text-ink-muted">
                        {agent.target}
                      </div>
                      {agent.resultCount !== undefined && agent.status === "done" && (
                        <div className="mt-1.5 text-[11px] font-semibold text-success">
                          {agent.resultCount} results
                        </div>
                      )}
                      {agent.status === "error" && agent.error && (
                        <div className="mt-1 truncate text-[11px] text-error">{agent.error}</div>
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
          <div className="card flex min-h-[28rem] flex-col p-4">
            <div className="mb-3 flex items-center gap-2.5">
              <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-accent/8">
                <Activity className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
              </div>
              <h3 className="text-[13px] font-semibold text-ink tracking-tight">Live Activity</h3>
              <span className="ml-auto text-[11px] text-ink-muted">{activityFeed.length} events</span>
            </div>

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

/* ─── KPI Card · Visual ─── */
function KpiCard({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="card p-4 transition-all duration-200 hover:shadow-md">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted">{label}</div>
          <div className={cx(
            "mt-1 font-display text-[1.75rem] font-bold tracking-tight",
            accent ? "text-accent italic" : "text-ink",
          )}>
            {value}
          </div>
        </div>
        <div className={cx(
          "flex h-10 w-10 items-center justify-center rounded-xl",
          accent ? "bg-accent-soft" : "bg-warm-100",
        )}>
          <Icon className={cx("h-5 w-5", accent ? "text-accent" : "text-warm-700")} aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}

/* ─── Activity Row ─── */
function ActivityRow({ entry }: { entry: import("../../../shared/types.js").ActivityEntry }) {
  const actionMeta: Record<string, { icon: React.ComponentType<{ className?: string }>; color: string; label: string }> = {
    think:     { icon: Brain,         color: "text-purple-500",   label: "思考" },
    search:    { icon: Search,        color: "text-blue-500",     label: "搜索" },
    found:     { icon: CheckCircle,   color: "text-success",      label: "发现" },
    classify:  { icon: Tags,          color: "text-amber-500",    label: "分类" },
    broadcast: { icon: Radio,         color: "text-cyan-500",     label: "广播" },
    upsert:    { icon: UserPlus,      color: "text-success",      label: "入库" },
    score:     { icon: BarChart3,     color: "text-orange-500",   label: "评分" },
    audit:     { icon: Microscope,    color: "text-pink-500",     label: "审计" },
    export:    { icon: FileOutput,    color: "text-indigo-500",   label: "导出" },
    error:     { icon: AlertTriangle, color: "text-error",        label: "错误" },
  };

  const meta = actionMeta[entry.action] || {
    icon: Activity,
    color: "text-ink-muted",
    label: entry.action,
  };
  const Icon = meta.icon;

  return (
    <div className="rounded-lg p-2 text-xs transition-colors duration-150 hover:bg-surface-hover">
      <div className="flex items-start gap-2">
        <Icon className={cx("mt-0.5 h-3.5 w-3.5 shrink-0", meta.color)} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[10px] text-ink-muted">
            <span className="font-mono">{new Date(entry.timestamp).toLocaleTimeString()}</span>
            <span className="font-medium">{meta.label}</span>
            {entry.agentType && <span className="truncate opacity-70">{entry.agentType}</span>}
          </div>
          <div className="mt-0.5 break-words text-ink-secondary leading-5">{entry.message}</div>
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
