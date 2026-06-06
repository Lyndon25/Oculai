import { useStore } from "../../store/index.js";
import { useState, useEffect } from "react";
import type { Candidate, CandidateDetail } from "../../../shared/types.js";
import { ExternalLink, Star, MapPin, BookOpen, Code } from "lucide-react";

export function CandidatesTab() {
  const candidates = useStore((s) => s.candidates);
  const selectedCandidate = useStore((s) => s.selectedCandidate);
  const setSelectedCandidate = useStore((s) => s.setSelectedCandidate);
  const activeRunId = useStore((s) => s.activeRunId);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");

  // Fetch candidates on mount
  useEffect(() => {
    if (!activeRunId) return;
    setLoading(true);
    window.oculai
      .getCandidates({ runId: activeRunId, limit: 100 })
      .then((result: unknown) => {
        const data = result as { candidates?: Candidate[] };
        if (data.candidates) {
          useStore.getState().setCandidates(data.candidates);
        }
      })
      .finally(() => setLoading(false));
  }, [activeRunId]);

  const handleSelectCandidate = async (personId: string) => {
    setLoading(true);
    try {
      const detail = await window.oculai.getCandidateDetail({ personId });
      setSelectedCandidate(detail as CandidateDetail);
    } catch {
      // Candidate already selected or error
    } finally {
      setLoading(false);
    }
  };

  const filtered = filter
    ? candidates.filter(
        (c) =>
          c.canonical_name.toLowerCase().includes(filter.toLowerCase()) ||
          c.latest_institution?.toLowerCase().includes(filter.toLowerCase()),
      )
    : candidates;

  const getScoreColor = (score?: number) => {
    if (!score) return "text-gray-600";
    if (score >= 80) return "text-green-400";
    if (score >= 60) return "text-yellow-400";
    if (score >= 40) return "text-orange-400";
    return "text-red-400";
  };

  return (
    <div className="h-full flex">
      {/* Left: Candidate List */}
      <div className="w-80 border-r border-gray-800 flex flex-col">
        <div className="p-3 border-b border-gray-800">
          <input
            type="text"
            className="input text-xs"
            placeholder="Filter by name or institution..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <p className="text-[10px] text-gray-600 mt-1">
            {filtered.length} of {candidates.length} candidates
          </p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading && candidates.length === 0 ? (
            <p className="text-sm text-gray-600 p-4 text-center">Loading candidates...</p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-gray-600 p-4 text-center">
              {candidates.length === 0
                ? "No candidates found yet. Search phase will populate this list."
                : "No matches for filter."}
            </p>
          ) : (
            filtered.map((c) => (
              <button
                key={c.person_id}
                onClick={() => handleSelectCandidate(c.person_id)}
                className={`w-full text-left p-3 border-b border-gray-800/50 hover:bg-gray-800/50 transition-colors ${
                  selectedCandidate?.person_id === c.person_id
                    ? "bg-blue-600/10 border-l-2 border-l-blue-500"
                    : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-200 truncate">
                    {c.canonical_name}
                  </span>
                  {c.quality_score !== undefined && (
                    <span className={`text-xs font-bold ${getScoreColor(c.quality_score)}`}>
                      {c.quality_score}
                    </span>
                  )}
                </div>
                {c.latest_institution && (
                  <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-1">
                    <MapPin className="w-3 h-3" />
                    {c.latest_institution}
                  </p>
                )}
                {c.research_areas && c.research_areas.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {c.research_areas.slice(0, 3).map((area, i) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 bg-gray-800 rounded text-gray-500">
                        {area}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right: Candidate Detail */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selectedCandidate ? (
          <div className="h-full flex items-center justify-center text-gray-600 text-sm">
            Select a candidate to view details
          </div>
        ) : (
          <CandidateDetailView candidate={selectedCandidate} />
        )}
      </div>
    </div>
  );
}

function CandidateDetailView({ candidate }: { candidate: CandidateDetail }) {
  const assessments = candidate.assessments || [];
  const evidence = candidate.evidence || [];
  const works = candidate.academic_works || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-gray-100">{candidate.canonical_name}</h2>
        <div className="flex items-center gap-3 mt-1">
          {candidate.latest_institution && (
            <span className="text-sm text-gray-400 flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5" />
              {candidate.latest_institution}
            </span>
          )}
          {candidate.latest_position && (
            <span className="text-sm text-gray-400">{candidate.latest_position}</span>
          )}
          {candidate.quality_score !== undefined && (
            <span className={`badge ${
              candidate.quality_score >= 80
                ? "badge-green"
                : candidate.quality_score >= 60
                  ? "badge-yellow"
                  : "badge-red"
            }`}>
              Score: {candidate.quality_score}/100
            </span>
          )}
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard icon={BookOpen} label="Papers" value={candidate.total_papers} />
        <StatCard icon={Star} label="H-Index" value={candidate.h_index} />
        <StatCard icon={Star} label="Citations" value={candidate.total_citations} />
        <StatCard icon={Code} label="Identities" value={candidate.identities?.length} />
      </div>

      {/* Identities */}
      {candidate.identities && candidate.identities.length > 0 && (
        <div className="panel p-4">
          <h3 className="panel-header -mx-4 -mt-4 mb-3">External Identities</h3>
          <div className="space-y-2">
            {candidate.identities.map((id, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-gray-400">{id.source_type}</span>
                <a
                  href={id.external_url || "#"}
                  className="text-blue-400 hover:text-blue-300 flex items-center gap-1"
                  onClick={(e) => {
                    if (!id.external_url) e.preventDefault();
                  }}
                >
                  {id.external_id.slice(0, 30)}
                  <ExternalLink className="w-3 h-3" />
                </a>
                <span className="text-xs text-gray-600">
                  conf: {(id.confidence * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Assessments */}
      {assessments.length > 0 && (
        <div className="panel p-4">
          <h3 className="panel-header -mx-4 -mt-4 mb-3">
            Assessments ({assessments.length})
          </h3>
          <div className="space-y-2">
            {assessments.map((a, i) => (
              <div key={i} className="flex items-center justify-between text-sm p-2 rounded bg-gray-800/30">
                <div>
                  <span className="text-gray-300 font-medium">{a.dimension}</span>
                  {a.assessor_agent && (
                    <span className="text-xs text-gray-600 ml-2">by {a.assessor_agent}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-blue-400 font-mono font-bold">{a.score.toFixed(1)}</span>
                  <span className="text-xs text-gray-600">
                    conf: {(a.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evidence */}
      {evidence.length > 0 && (
        <div className="panel p-4">
          <h3 className="panel-header -mx-4 -mt-4 mb-3">
            Evidence ({evidence.length})
          </h3>
          <div className="space-y-2">
            {evidence.map((ev, i) => (
              <div key={i} className="p-2 rounded bg-gray-800/30 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-gray-300 font-medium">{ev.title}</span>
                  <span className={`badge ${
                    ev.tier <= 1 ? "badge-green" : ev.tier === 2 ? "badge-blue" : ev.tier === 3 ? "badge-yellow" : "badge-gray"
                  }`}>
                    T{ev.tier}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                  <span>{ev.evidence_type}</span>
                  <span>·</span>
                  <span>{ev.source_name}</span>
                  <span>·</span>
                  <span>conf: {(ev.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Academic Works */}
      {works.length > 0 && (
        <div className="panel p-4">
          <h3 className="panel-header -mx-4 -mt-4 mb-3">
            Publications ({works.length})
          </h3>
          <div className="space-y-2">
            {works.slice(0, 5).map((w, i) => (
              <div key={i} className="text-sm">
                <span className="text-gray-300">{w.title}</span>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500">
                  {w.venue && <span>{w.venue}</span>}
                  {w.year && <span>{w.year}</span>}
                  {w.citations !== undefined && <span>{w.citations} citations</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value?: number;
}) {
  return (
    <div className="panel p-3 text-center">
      <Icon className="w-4 h-4 text-gray-500 mx-auto mb-1" />
      <div className="text-lg font-bold text-gray-200">{value ?? "—"}</div>
      <div className="text-[10px] text-gray-600">{label}</div>
    </div>
  );
}
