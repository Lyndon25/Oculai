import { useStore } from "../../store/index.js";
import { DashboardView } from "../dashboard/DashboardView.js";
import { OrchestrationDashboard } from "../pipeline/OrchestrationDashboard.js";
import { CandidatesTab } from "../candidates/CandidatesTab.js";
import { EvidenceTab } from "../evidence/EvidenceTab.js";
import { ReportTab } from "../report/ReportTab.js";
import { LogsTab } from "../logs/LogsTab.js";
import { GitBranch, Users, FileSearch, FileText, ScrollText, ChevronUp, ChevronDown } from "lucide-react";
import { useState } from "react";

const BOTTOM_TABS = [
  { id: "candidates" as const, label: "Candidates", icon: Users },
  { id: "evidence" as const, label: "Evidence", icon: FileSearch },
  { id: "report" as const, label: "Report", icon: FileText },
  { id: "logs" as const, label: "Logs", icon: ScrollText },
];

export function MainPanel() {
  const activeRunId = useStore((s) => s.activeRunId);
  const activeBottomTab = useStore((s) => s.activeTab);
  const setActiveTab = useStore((s) => s.setActiveTab);
  const [drawerOpen, setDrawerOpen] = useState(true);

  if (!activeRunId) {
    return (
      <div className="flex-1 overflow-hidden">
        <DashboardView />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Agent Dashboard */}
      <div className="flex-1 overflow-hidden">
        <OrchestrationDashboard />
      </div>

      {/* Bottom Drawer Toggle */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-gray-900 border-t border-gray-800">
        <div className="flex items-center gap-1">
          {BOTTOM_TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (!drawerOpen) setDrawerOpen(true);
                }}
                className={`flex items-center gap-1.5 px-3 py-1 text-xs rounded transition-colors ${
                  activeBottomTab === tab.id
                    ? "bg-blue-600/20 text-blue-300"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                <Icon className="w-3 h-3" />
                {tab.label}
              </button>
            );
          })}
        </div>
        <button
          onClick={() => setDrawerOpen(!drawerOpen)}
          className="text-gray-500 hover:text-gray-300 p-1"
        >
          {drawerOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </button>
      </div>

      {/* Bottom Drawer */}
      {drawerOpen && (
        <div className="h-72 border-t border-gray-800 overflow-hidden">
          {activeBottomTab === "candidates" && <CandidatesTab />}
          {activeBottomTab === "evidence" && <EvidenceTab />}
          {activeBottomTab === "report" && <ReportTab />}
          {activeBottomTab === "logs" && <LogsTab />}
          {activeBottomTab === "pipeline" && <CandidatesTab />}
        </div>
      )}
    </div>
  );
}
