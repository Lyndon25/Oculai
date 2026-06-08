import { useStore } from "../../store/index.js";
import { Sparkles } from "lucide-react";
import { HealthDot, RunStatusBadge } from "../ui/primitives.js";

export function TitleBar() {
  const systemStatus = useStore((s) => s.systemStatus);
  const activeRunId = useStore((s) => s.activeRunId);
  const runs = useStore((s) => s.runs);
  const activeRun = runs.find((r) => r.run_id === activeRunId);

  return (
    <div className="app-drag flex h-11 select-none items-center border-b border-[var(--oc-border)] bg-[var(--oc-surface-glass)] backdrop-blur-xl px-5">
      {/* Logo · Serif wordmark */}
      <div className="flex items-center gap-2.5 pr-6">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/10">
          <Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
        </div>
        <span className="font-display text-[15px] italic font-normal tracking-tight text-ink">
          Oculai
        </span>
      </div>

      {/* Active run chip */}
      {activeRun && (
        <div className="app-no-drag hidden min-w-0 items-center gap-2 rounded-lg bg-surface-hover px-3 py-1 md:flex">
          <span className="max-w-[320px] truncate text-[12px] font-medium text-ink-secondary">
            {activeRun.title}
          </span>
          <RunStatusBadge status={activeRun.status} />
        </div>
      )}

      <div className="flex-1" />

      {/* System status · Visual dots */}
      <div className="app-no-drag flex items-center gap-3" aria-label="系统状态">
        <HealthDot label="DB" status={systemStatus.db} />
        <HealthDot label="PY" status={systemStatus.python} />
        <HealthDot label="AI" status={systemStatus.llm} />
      </div>
    </div>
  );
}
