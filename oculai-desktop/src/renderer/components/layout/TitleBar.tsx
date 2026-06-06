import { useStore } from "../../store/index.js";
import { Activity, Wifi, Server, Brain } from "lucide-react";

export function TitleBar() {
  const systemStatus = useStore((s) => s.systemStatus);
  const activeRunId = useStore((s) => s.activeRunId);
  const runs = useStore((s) => s.runs);
  const activeRun = runs.find((r) => r.run_id === activeRunId);

  const statusColor = (status: string) => {
    switch (status) {
      case "connected":
      case "ready":
      case "configured":
        return "text-green-400";
      case "connecting":
      case "starting":
        return "text-yellow-400";
      case "error":
        return "text-red-400";
      default:
        return "text-gray-500";
    }
  };

  return (
    <div className="h-10 bg-gray-900 border-b border-gray-800 flex items-center px-4 select-none draggable">
      {/* Logo & App name */}
      <div className="flex items-center gap-2 mr-6">
        <Activity className="w-4 h-4 text-blue-500" />
        <span className="text-sm font-semibold text-gray-200">Oculai Desktop</span>
        <span className="text-xs text-gray-600 font-mono">v0.1.0</span>
      </div>

      {/* Run info */}
      {activeRun && (
        <div className="flex items-center gap-2 px-3 py-1 bg-gray-800 rounded-md">
          <span className="text-xs text-gray-400">{activeRun.title}</span>
          <span className={`badge text-xs px-1.5 py-0 ${
            activeRun.status === "running"
              ? "badge-green"
              : activeRun.status === "completed"
                ? "badge-blue"
                : "badge-gray"
          }`}>
            {activeRun.status}
          </span>
        </div>
      )}

      <div className="flex-1" />

      {/* System status indicators */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1" title={`Database: ${systemStatus.db}`}>
          <Server className={`w-3.5 h-3.5 ${statusColor(systemStatus.db)}`} />
          <span className="text-[10px] text-gray-500">
            {systemStatus.dbPort ? `:${systemStatus.dbPort}` : "DB"}
          </span>
        </div>
        <div className="flex items-center gap-1" title={`Python: ${systemStatus.python}`}>
          <Wifi className={`w-3.5 h-3.5 ${statusColor(systemStatus.python)}`} />
          <span className="text-[10px] text-gray-500">PY</span>
        </div>
        <div className="flex items-center gap-1" title={`LLM: ${systemStatus.llm}`}>
          <Brain className={`w-3.5 h-3.5 ${statusColor(systemStatus.llm)}`} />
          <span className="text-[10px] text-gray-500">AI</span>
        </div>
      </div>
    </div>
  );
}
