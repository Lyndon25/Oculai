import { useStore } from "../../store/index.js";
import {
  Play,
  CheckCircle,
  Circle,
  AlertTriangle,
  Clock,
  Search,
  Users,
  FileSearch,
  Brain,
  Target,
  FileText,
  Send,
} from "lucide-react";

const PHASES = [
  { id: "init", label: "Initialize", icon: Play },
  { id: "strategy", label: "Strategy", icon: Brain },
  { id: "searching", label: "Search", icon: Search },
  { id: "identity_resolution", label: "Identity", icon: Users },
  { id: "enrichment", label: "Enrichment", icon: FileSearch },
  { id: "evaluation", label: "Evaluation", icon: Target },
  { id: "audit", label: "Audit", icon: CheckCircle },
  { id: "shortlist", label: "Shortlist", icon: FileText },
  { id: "outreach", label: "Outreach", icon: Send },
  { id: "complete", label: "Complete", icon: CheckCircle },
];

export function PipelineTab() {
  const pipeline = useStore((s) => s.pipeline);
  const messages = useStore((s) => s.messages);

  const currentPhaseIdx = pipeline
    ? PHASES.findIndex((p) => p.id === pipeline.phase)
    : -1;

  if (!pipeline) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <Clock className="w-12 h-12 text-gray-700 mx-auto mb-3" />
          <p className="text-gray-500 text-sm">
            Pipeline will appear here once the sourcing run starts.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Phase Timeline */}
      <div className="panel p-4 mb-6">
        <h3 className="panel-header -mx-4 -mt-4 mb-4">Pipeline Progress</h3>
        <div className="flex items-center gap-1 overflow-x-auto pb-2">
          {PHASES.map((phase, idx) => {
            const Icon = phase.icon;
            const isCurrent = idx === currentPhaseIdx;
            const isDone = idx < currentPhaseIdx;
            const isPending = idx > currentPhaseIdx;

            return (
              <div key={phase.id} className="flex items-center gap-1">
                <div
                  className={`flex flex-col items-center px-2 py-1.5 rounded-md min-w-[80px] transition-colors ${
                    isCurrent
                      ? "bg-blue-600/20 border border-blue-800/50"
                      : isDone
                        ? "bg-green-900/20 border border-green-800/30"
                        : "bg-gray-900 border border-gray-800"
                  }`}
                >
                  <Icon
                    className={`w-4 h-4 ${
                      isCurrent
                        ? "text-blue-400"
                        : isDone
                          ? "text-green-400"
                          : "text-gray-600"
                    }`}
                  />
                  <span
                    className={`text-[10px] mt-1 font-medium ${
                      isCurrent
                        ? "text-blue-300"
                        : isDone
                          ? "text-green-400"
                          : "text-gray-600"
                    }`}
                  >
                    {phase.label}
                  </span>
                </div>
                {idx < PHASES.length - 1 && (
                  <div
                    className={`w-4 h-px ${
                      idx < currentPhaseIdx ? "bg-green-800" : "bg-gray-800"
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Task Progress + Metrics */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="panel p-4">
          <h3 className="panel-header -mx-4 -mt-4 mb-4">Task Progress</h3>
          {pipeline.task_progress ? (
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-400">
                  {pipeline.task_progress.completed} / {pipeline.task_progress.total} completed
                </span>
                {pipeline.task_progress.failed > 0 && (
                  <span className="text-red-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    {pipeline.task_progress.failed} failed
                  </span>
                )}
              </div>
              <div className="w-full bg-gray-800 rounded-full h-2">
                <div
                  className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                  style={{
                    width: `${
                      pipeline.task_progress.total > 0
                        ? (pipeline.task_progress.completed / pipeline.task_progress.total) * 100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-600">Waiting for plan...</p>
          )}
        </div>

        <div className="panel p-4">
          <h3 className="panel-header -mx-4 -mt-4 mb-4">Quality Metrics</h3>
          {pipeline.metrics ? (
            <div className="space-y-2 text-sm">
              <MetricRow
                label="Extraction Quality"
                value={pipeline.metrics.extraction_quality_score}
              />
              <MetricRow
                label="Cross-Source Verified"
                value={pipeline.metrics.cross_source_verified}
                suffix="candidates"
              />
              <MetricRow
                label="False Positive Rate"
                value={pipeline.metrics.false_positive_rate}
                isPercent
                invert
              />
              <MetricRow
                label="China Coverage"
                value={pipeline.metrics.china_platform_coverage}
                isPercent
              />
            </div>
          ) : (
            <p className="text-sm text-gray-600">Metrics available after search phase...</p>
          )}
        </div>
      </div>

      {/* Subagent Status */}
      {pipeline.subagents && pipeline.subagents.length > 0 && (
        <div className="panel p-4 mb-6">
          <h3 className="panel-header -mx-4 -mt-4 mb-4">Subagent Status</h3>
          <div className="grid grid-cols-4 gap-3">
            {pipeline.subagents.map((agent) => (
              <div
                key={agent.name}
                className={`p-3 rounded-lg border text-sm ${
                  agent.status === "running"
                    ? "bg-blue-900/10 border-blue-800/50"
                    : agent.status === "done"
                      ? "bg-green-900/10 border-green-800/30"
                      : agent.status === "error"
                        ? "bg-red-900/10 border-red-800/30"
                        : "bg-gray-900 border-gray-800"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-gray-300 text-xs">{agent.name}</span>
                  <StatusDot status={agent.status} />
                </div>
                {agent.iterations !== undefined && (
                  <span className="text-[10px] text-gray-500">
                    {agent.iterations} iterations
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live Agent Messages */}
      <div className="panel p-4">
        <h3 className="panel-header -mx-4 -mt-4 mb-4">Latest Activity</h3>
        <div className="space-y-2 max-h-60 overflow-y-auto">
          {messages.length === 0 ? (
            <p className="text-sm text-gray-600">No messages yet...</p>
          ) : (
            messages.slice(-20).map((msg, i) => (
              <div
                key={i}
                className={`text-xs p-2 rounded ${
                  msg.isError
                    ? "bg-red-900/20 text-red-400"
                    : msg.isThinking
                      ? "bg-gray-800/50 text-gray-500 italic"
                      : msg.role === "tool"
                        ? "bg-gray-800/50 text-gray-400"
                        : "text-gray-300"
                }`}
              >
                {msg.toolName && (
                  <span className="text-blue-400 font-mono">{msg.toolName}</span>
                )}
                {msg.toolName && " — "}
                <span>{msg.content.slice(0, 200)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function MetricRow({
  label,
  value,
  suffix,
  isPercent,
  invert,
}: {
  label: string;
  value?: number;
  suffix?: string;
  isPercent?: boolean;
  invert?: boolean;
}) {
  if (value === undefined) {
    return (
      <div className="flex justify-between">
        <span className="text-gray-500">{label}</span>
        <span className="text-gray-700">—</span>
      </div>
    );
  }

  const display = isPercent ? `${(value * 100).toFixed(0)}%` : `${value}${suffix ? ` ${suffix}` : ""}`;
  const isGood = invert ? value < 0.3 : value > 0.7;
  const color = isGood ? "text-green-400" : value > 0.3 ? "text-yellow-400" : "text-red-400";

  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className={color}>{display}</span>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "running"
      ? "bg-yellow-400"
      : status === "done"
        ? "bg-green-400"
        : status === "error"
          ? "bg-red-400"
          : "bg-gray-600";

  return (
    <span className={`inline-block w-2 h-2 rounded-full ${color} ${
      status === "running" ? "animate-pulse" : ""
    }`} />
  );
}
