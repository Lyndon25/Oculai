import { useStore } from "../../store/index.js";
import { Plus, Clock, Settings } from "lucide-react";
import { RunStatusBadge, cx } from "../ui/primitives.js";

export function Sidebar() {
  const runs = useStore((s) => s.runs);
  const activeRunId = useStore((s) => s.activeRunId);
  const setActiveRun = useStore((s) => s.setActiveRun);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const resetRunScopedState = useStore((s) => s.resetRunScopedState);

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-[var(--oc-border)] bg-[var(--oc-surface)]">
      {/* New Run · Prominent CTA */}
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

      {/* History · Refined list */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        <div className="px-2.5 py-2">
          <h3 className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-ink-muted">
            <Clock className="h-3 w-3" aria-hidden="true" />
            历史
          </h3>
        </div>

        <div className="space-y-0.5">
          {runs.length === 0 ? (
            <div className="mx-1 rounded-xl border border-dashed border-rule px-3 py-10 text-center">
              <p className="text-[12px] leading-5 text-ink-muted">
                暂无任务
              </p>
            </div>
          ) : (
            runs.map((run) => {
              const isActive = activeRunId === run.run_id;
              return (
                <button
                  key={run.run_id}
                  type="button"
                  onClick={() => setActiveRun(run.run_id)}
                  className={cx(
                    "w-full rounded-xl px-3 py-2.5 text-left transition-all duration-200 ease-[var(--oc-spring-smooth)]",
                    isActive
                      ? "bg-accent-soft ring-1 ring-accent/15"
                      : "text-ink-secondary hover:bg-surface-hover hover:text-ink",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0 flex-1 truncate text-[13px] font-medium tracking-tight">
                      {run.title}
                    </span>
                  </div>
                  <div className="mt-1.5">
                    <RunStatusBadge status={run.status} />
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Settings · Subtle footer */}
      <div className="border-t border-rule p-3">
        <button
          type="button"
          className="btn-ghost w-full justify-start text-[12px]"
          onClick={() => setSettingsOpen(true)}
        >
          <Settings className="h-3.5 w-3.5" aria-hidden="true" />
          <span>设置</span>
        </button>
      </div>
    </aside>
  );
}
