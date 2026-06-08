import { useStore } from "../../store/index.js";
import { Activity } from "lucide-react";
import { HealthDot, RunStatusBadge } from "../ui/primitives.js";

export function TitleBar() {
  const systemStatus = useStore((s) => s.systemStatus);
  const activeRunId = useStore((s) => s.activeRunId);
  const runs = useStore((s) => s.runs);
  const activeRun = runs.find((r) => r.run_id === activeRunId);

  return (
    <div className="app-drag flex h-10 select-none items-center border-b border-rule bg-canvas/90 px-5 backdrop-blur-sm">
      {/* Logo */}
      <div className="flex items-center gap-2.5 pr-6">
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/10">
          <Activity className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
        </div>
        <span className="font-display text-[13px] font-semibold tracking-tight text-ink">
          Oculai
        </span>
      </div>

      {/* Active run info */}
      {activeRun && (
        <div className="app-no-drag hidden min-w-0 items-center gap-2 rounded-lg border border-rule bg-surface px-3 py-1 md:flex">
          <span className="max-w-[320px] truncate text-xs font-medium text-ink-secondary">
            {activeRun.title}
          </span>
          <RunStatusBadge status={activeRun.status} />
        </div>
      )}

      <div className="flex-1" />

      {/* System status */}
      <div className="app-no-drag flex items-center gap-3" aria-label="System status">
        <HealthDot label="DB" status={systemStatus.db} />
        <HealthDot label="PY" status={systemStatus.python} />
        <HealthDot label="AI" status={systemStatus.llm} />
      </div>
    </div>
  );
}
