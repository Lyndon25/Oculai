import { useStore } from "../../store/index.js";
import { DashboardView } from "../dashboard/DashboardView.js";
import { OrchestrationDashboard } from "../pipeline/OrchestrationDashboard.js";
import { CandidatesTab } from "../candidates/CandidatesTab.js";
import { EvidenceTab } from "../evidence/EvidenceTab.js";
import { ReportTab } from "../report/ReportTab.js";
import { LogsTab } from "../logs/LogsTab.js";
import { Users, FileSearch, FileText, ScrollText, ChevronUp, ChevronDown } from "lucide-react";
import { useState } from "react";
import { cx } from "../ui/primitives.js";

const BOTTOM_TABS = [
  { id: "candidates" as const, label: "候选人", icon: Users },
  { id: "evidence" as const, label: "证据", icon: FileSearch },
  { id: "report" as const, label: "报告", icon: FileText },
  { id: "logs" as const, label: "日志", icon: ScrollText },
];

export function MainPanel() {
  const activeRunId = useStore((s) => s.activeRunId);
  const activeBottomTab = useStore((s) => s.activeTab);
  const setActiveTab = useStore((s) => s.setActiveTab);
  const candidates = useStore((s) => s.candidates);
  const messages = useStore((s) => s.messages);
  const [drawerOpen, setDrawerOpen] = useState(true);

  if (!activeRunId) {
    return (
      <main className="min-w-0 flex-1 overflow-hidden bg-canvas">
        <DashboardView />
      </main>
    );
  }

  return (
    <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-canvas">
      {/* Agent Dashboard */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <OrchestrationDashboard />
      </div>

      {/* Tab bar */}
      <div className="flex items-center justify-between border-t border-rule bg-surface px-4 py-1.5">
        <div className="flex items-center gap-1" role="tablist" aria-label="Run detail tabs">
          {BOTTOM_TABS.map((tab) => {
            const Icon = tab.icon;
            const badge =
              tab.id === "candidates"
                ? candidates.length
                : tab.id === "logs"
                  ? messages.length
                  : undefined;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={activeBottomTab === tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (!drawerOpen) setDrawerOpen(true);
                }}
                className={cx(
                  "flex min-h-[30px] items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-all duration-150",
                  activeBottomTab === tab.id
                    ? "bg-accent-soft text-accent"
                    : "text-ink-muted hover:bg-surface-hover hover:text-ink-secondary",
                )}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {tab.label}
                {badge !== undefined && badge > 0 && (
                  <span className="rounded-full bg-rule px-1.5 py-0.5 font-mono text-[10px] text-ink-secondary">
                    {badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => setDrawerOpen(!drawerOpen)}
          className="btn-ghost min-h-0 p-1.5"
          aria-label={drawerOpen ? "收起" : "展开"}
          aria-expanded={drawerOpen}
        >
          {drawerOpen ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronUp className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Bottom Drawer */}
      {drawerOpen && (
        <div className="h-[22rem] min-h-0 overflow-hidden border-t border-rule bg-surface xl:h-96">
          {activeBottomTab === "candidates" && <CandidatesTab />}
          {activeBottomTab === "evidence" && <EvidenceTab />}
          {activeBottomTab === "report" && <ReportTab />}
          {activeBottomTab === "logs" && <LogsTab />}
          {activeBottomTab === "pipeline" && <CandidatesTab />}
        </div>
      )}
    </main>
  );
}
