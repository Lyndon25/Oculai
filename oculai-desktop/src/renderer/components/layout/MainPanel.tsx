import { useStore } from "../../store/index.js";
import { DashboardView } from "../dashboard/DashboardView.js";
import { PipelineTab } from "../pipeline/PipelineTab.js";
import { CandidatesTab } from "../candidates/CandidatesTab.js";
import { EvidenceTab } from "../evidence/EvidenceTab.js";
import { ReportTab } from "../report/ReportTab.js";
import { LogsTab } from "../logs/LogsTab.js";
import { GitBranch, Users, FileSearch, FileText, ScrollText } from "lucide-react";

const TABS = [
  { id: "pipeline" as const, label: "Pipeline", icon: GitBranch },
  { id: "candidates" as const, label: "Candidates", icon: Users },
  { id: "evidence" as const, label: "Evidence", icon: FileSearch },
  { id: "report" as const, label: "Report", icon: FileText },
  { id: "logs" as const, label: "Logs", icon: ScrollText },
];

export function MainPanel() {
  const activeRunId = useStore((s) => s.activeRunId);
  const activeTab = useStore((s) => s.activeTab);
  const setActiveTab = useStore((s) => s.setActiveTab);

  if (!activeRunId) {
    return (
      <div className="flex-1 overflow-hidden">
        <DashboardView />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="flex items-center px-2 pt-2 gap-1 bg-gray-950">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-t-md transition-colors ${
                activeTab === tab.id
                  ? "bg-gray-900 text-gray-200 border-t border-l border-r border-gray-800"
                  : "text-gray-500 hover:text-gray-300 hover:bg-gray-900/50"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "pipeline" && <PipelineTab />}
        {activeTab === "candidates" && <CandidatesTab />}
        {activeTab === "evidence" && <EvidenceTab />}
        {activeTab === "report" && <ReportTab />}
        {activeTab === "logs" && <LogsTab />}
      </div>
    </div>
  );
}
