import { useStore } from "../../store/index.js";
import { Plus, Clock, Settings, ChevronRight } from "lucide-react";

export function Sidebar() {
  const runs = useStore((s) => s.runs);
  const activeRunId = useStore((s) => s.activeRunId);
  const setActiveRun = useStore((s) => s.setActiveRun);
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "running":
        return "badge-green";
      case "completed":
        return "badge-blue";
      case "draft":
        return "badge-gray";
      case "aborted":
        return "badge-red";
      default:
        return "badge-gray";
    }
  };

  return (
    <div className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* New Run button */}
      <div className="p-3">
        <button
          className="w-full flex items-center justify-center gap-2 btn-primary"
          onClick={() => setActiveRun(null)}
        >
          <Plus className="w-4 h-4" />
          <span>New Sourcing Run</span>
        </button>
      </div>

      {/* Run history */}
      <div className="flex-1 overflow-y-auto">
        <div className="px-3 py-2">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider flex items-center gap-1">
            <Clock className="w-3 h-3" /> History
          </h3>
        </div>
        <div className="space-y-0.5 px-2">
          {runs.length === 0 ? (
            <p className="text-xs text-gray-600 px-2 py-4 text-center">
              No runs yet. Start your first talent sourcing run!
            </p>
          ) : (
            runs.map((run) => (
              <button
                key={run.run_id}
                onClick={() => setActiveRun(run.run_id)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                  activeRunId === run.run_id
                    ? "bg-blue-600/20 text-blue-300 border border-blue-800/50"
                    : "hover:bg-gray-800 text-gray-400 hover:text-gray-200"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate font-medium">{run.title}</span>
                  <ChevronRight className="w-3 h-3 flex-shrink-0 opacity-50" />
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`badge text-[10px] ${getStatusBadge(run.status)}`}>
                    {run.status}
                  </span>
                  {run.candidate_count !== undefined && (
                    <span className="text-[10px] text-gray-600">
                      {run.candidate_count} candidates
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Settings */}
      <div className="p-3 border-t border-gray-800">
        <button
          className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-gray-400 hover:bg-gray-800 hover:text-gray-200 transition-colors"
          onClick={() => setSettingsOpen(true)}
        >
          <Settings className="w-4 h-4" />
          <span>Settings</span>
        </button>
      </div>
    </div>
  );
}
