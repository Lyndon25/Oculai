import { useStore } from "../../store/index.js";
import { Sparkles, Search, Users, FileText, ArrowRight, RotateCcw, Calendar, Clock } from "lucide-react";
import { useState } from "react";
import type { StartRunPayload } from "../../../shared/events.js";
import type { RunStatus } from "../../../shared/types.js";

export function DashboardView() {
  const systemStatus = useStore((s) => s.systemStatus);
  const runs = useStore((s) => s.runs);
  const setActiveRun = useStore((s) => s.setActiveRun);
  const [jobTitle, setJobTitle] = useState("");
  const [jdText, setJdText] = useState("");
  const [skills, setSkills] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumingRunId, setResumingRunId] = useState<string | null>(null);

  const canStart =
    jobTitle.trim() &&
    jdText.trim() &&
    systemStatus.db === "connected" &&
    systemStatus.python === "ready" &&
    systemStatus.llm === "configured" &&
    !isStarting;

  const handleStart = async () => {
    if (!canStart) return;
    setIsStarting(true);
    setError(null);

    try {
      const payload: StartRunPayload = {
        jobTitle: jobTitle.trim(),
        jdText: jdText.trim(),
        requiredSkills: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      await window.oculai.startRun(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsStarting(false);
    }
  };

  const handleResume = async (runId: string, _title: string) => {
    setResumingRunId(runId);
    try {
      await window.oculai.resumeRun(runId);
      setActiveRun(runId);
    } catch (err) {
      // If resume fails, try direct navigation anyway
      setActiveRun(runId);
    } finally {
      setResumingRunId(null);
    }
  };

  const isReady =
    systemStatus.db === "connected" &&
    systemStatus.python === "ready" &&
    systemStatus.llm === "configured";

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto py-12 px-6">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl bg-blue-600/20 flex items-center justify-center">
              <Sparkles className="w-6 h-6 text-blue-400" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-gray-100 mb-2">
            Oculai Talent Sourcing
          </h1>
          <p className="text-sm text-gray-500 max-w-md mx-auto">
            Multi-agent AI-powered talent sourcing for Chinese HRs.
            Enter a job description below to discover top candidates
            across academic, industry, and Chinese platforms.
          </p>
        </div>

        {/* System status */}
        {!isReady && (
          <div className="panel p-4 mb-6 border-yellow-800">
            <p className="text-sm text-yellow-400 font-medium mb-2">
              System not fully ready
            </p>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <StatusItem label="Database" status={systemStatus.db} />
              <StatusItem label="Python Engine" status={systemStatus.python} />
              <StatusItem label="AI Model" status={systemStatus.llm} />
            </div>
          </div>
        )}

        {/* JD Input Form */}
        <div className="panel p-6 mb-6">
          <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <Search className="w-4 h-4" /> Job Description
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Job Title
              </label>
              <input
                type="text"
                className="input"
                placeholder="e.g. Senior NLP Researcher, ML Engineer..."
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Job Description (JD)
              </label>
              <textarea
                className="input min-h-[200px] resize-y font-mono text-xs"
                placeholder="Paste the full job description here...
Include: company context, responsibilities, required qualifications,
preferred experience, location, etc."
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs text-gray-500 mb-1">
                Required Skills (comma-separated)
              </label>
              <input
                type="text"
                className="input"
                placeholder="e.g. PyTorch, Transformer, NLP, CUDA, LLM"
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
              />
            </div>
          </div>

          {error && (
            <div className="mt-4 p-3 bg-red-900/30 border border-red-800 rounded-lg">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          <div className="mt-6 flex items-center justify-between">
            <p className="text-xs text-gray-600">
              {isReady
                ? "Ready — AI agent will orchestrate the full pipeline"
                : "Configure API keys in Settings to enable AI agent"}
            </p>
            <button
              className="btn-primary flex items-center gap-2"
              disabled={!canStart}
              onClick={handleStart}
            >
              {isStarting ? (
                <>Starting...</>
              ) : (
                <>
                  Start Sourcing
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>

        {/* Quick guide */}
        <div className="grid grid-cols-3 gap-4">
          <GuideCard
            icon={Search}
            title="1. Multi-Source Search"
            desc="Searches across 16 sources including Chinese platforms (Zhihu, Juejin, CSDN)"
          />
          <GuideCard
            icon={Users}
            title="2. Smart Evaluation"
            desc="AI-powered multi-dimensional assessment with China-market calibration"
          />
          <GuideCard
            icon={FileText}
            title="3. Polished Report"
            desc="Self-contained HTML dashboard with score charts and candidate cards"
          />
        </div>

        {/* Recent Runs */}
        <div className="mt-10">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-4 h-4 text-gray-400" />
            <h2 className="text-sm font-semibold text-gray-300">Recent Runs</h2>
            {runs.length > 0 && (
              <span className="text-xs text-gray-600 ml-1">({runs.length})</span>
            )}
          </div>

          {runs.length === 0 ? (
            <div className="panel p-8 text-center">
              <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center mx-auto mb-3">
                <RotateCcw className="w-5 h-5 text-gray-500" />
              </div>
              <p className="text-sm text-gray-400 mb-1">No previous runs</p>
              <p className="text-xs text-gray-600">
                Start your first sourcing run above.
              </p>
            </div>
          ) : (
            <div className="grid gap-3">
              {runs.slice(0, 10).map((run) => (
                <button
                  key={run.run_id}
                  onClick={() => handleResume(run.run_id, run.title)}
                  disabled={resumingRunId === run.run_id}
                  className="panel p-4 text-left hover:border-gray-600 transition-colors w-full"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-gray-200 truncate">
                          {run.title}
                        </h3>
                        <StatusBadge status={run.status} />
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-gray-500">
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {formatDate(run.created_at)}
                        </span>
                        {run.candidate_count !== undefined && run.candidate_count > 0 && (
                          <span className="flex items-center gap-1">
                            <Users className="w-3 h-3" />
                            {run.candidate_count} candidate{run.candidate_count !== 1 ? "s" : ""}
                          </span>
                        )}
                        {run.task_count !== undefined && (
                          <span>
                            {run.completed_task_count ?? 0}/{run.task_count} tasks
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex-shrink-0 flex items-center gap-1 text-xs text-gray-500">
                      {resumingRunId === run.run_id ? (
                        <span className="text-blue-400">Loading...</span>
                      ) : (
                        <>
                          <span className="text-blue-400">Resume</span>
                          <ArrowRight className="w-3 h-3 text-blue-400" />
                        </>
                      )}
                    </div>
                  </div>
                </button>
              ))}
              {runs.length > 10 && (
                <p className="text-[11px] text-gray-600 text-center mt-1">
                  Showing 10 of {runs.length} runs. Older runs are available in the sidebar.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusItem({ label, status }: { label: string; status: string }) {
  const color =
    status === "connected" || status === "ready" || status === "configured"
      ? "text-green-400"
      : status === "connecting" || status === "starting"
        ? "text-yellow-400"
        : "text-red-400";
  return (
    <div>
      <span className="text-gray-500">{label}: </span>
      <span className={color}>{status}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: RunStatus }) {
  const colorMap: Record<RunStatus, string> = {
    draft: "bg-gray-700 text-gray-300 border-gray-600",
    running: "bg-green-900/40 text-green-400 border-green-800",
    paused: "bg-yellow-900/40 text-yellow-400 border-yellow-800",
    reviewing: "bg-purple-900/40 text-purple-400 border-purple-800",
    completed: "bg-blue-900/40 text-blue-400 border-blue-800",
    aborted: "bg-red-900/40 text-red-400 border-red-800",
  };

  const labelMap: Record<RunStatus, string> = {
    draft: "Draft",
    running: "Running",
    paused: "Paused",
    reviewing: "Review",
    completed: "Done",
    aborted: "Aborted",
  };

  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${colorMap[status] ?? colorMap.draft}`}>
      {labelMap[status] ?? status}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: d.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function GuideCard({
  icon: Icon,
  title,
  desc,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  desc: string;
}) {
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-medium text-gray-300">{title}</h3>
      </div>
      <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
    </div>
  );
}
