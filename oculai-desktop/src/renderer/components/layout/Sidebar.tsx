import { useStore } from "../../store/index.js";
import { Plus, Clock, Settings, ChevronRight } from "lucide-react";
import { RunStatusBadge, cx } from "../ui/primitives.js";

export function Sidebar() {
  const runs = useStore((s) => s.runs);
  const activeRunId = useStore((s) => s.activeRunId);
  const setActiveRun = useStore((s) => s.setActiveRun);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const resetRunScopedState = useStore((s) => s.resetRunScopedState);

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-rule bg-canvas">
      {/* New Run */}
      <div className="p-3">
        <button
          type="button"
          className="btn-primary w-full"
          onClick={() => {
            resetRunScopedState();
            setActiveRun(null);
          }}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span>新建任务</span>
        </button>
      </div>

      {/* History */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        <div className="px-2 py-2">
          <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-ink-muted">
            <Clock className="h-3 w-3" aria-hidden="true" />
            历史
          </h3>
        </div>

        <div className="space-y-1">
          {runs.length === 0 ? (
            <div className="rounded-xl border border-dashed border-rule px-3 py-8 text-center">
              <p className="text-xs leading-5 text-ink-muted">
                暂无任务
              </p>
            </div>
          ) : (
            runs.map((run) => (
              <button
                key={run.run_id}
                type="button"
                onClick={() => setActiveRun(run.run_id)}
                className={cx(
                  "w-full rounded-xl border px-3 py-2.5 text-left transition-colors duration-150",
                  activeRunId === run.run_id
                    ? "border-accent/30 bg-accent-soft"
                    : "border-transparent text-ink-secondary hover:border-rule hover:bg-surface-hover hover:text-ink",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">
                    {run.title}
                  </span>
                  <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 opacity-40" aria-hidden="true" />
                </div>
                <div className="mt-1.5">
                  <RunStatusBadge status={run.status} />
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Settings */}
      <div className="border-t border-rule p-3">
        <button
          type="button"
          className="btn-ghost w-full justify-start text-xs"
          onClick={() => setSettingsOpen(true)}
        >
          <Settings className="h-3.5 w-3.5" aria-hidden="true" />
          <span>设置</span>
        </button>
      </div>
    </aside>
  );
}
