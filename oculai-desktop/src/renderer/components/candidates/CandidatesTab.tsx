import { useStore } from "../../store/index.js";
import { useState, useEffect, useMemo, useRef } from "react";
import type React from "react";
import type { Candidate, CandidateDetail } from "../../../shared/types.js";
import { ExternalLink, Star, MapPin, BookOpen, Code, Search, UserRound, BriefcaseBusiness } from "lucide-react";
import { EmptyState, EvidenceTierBadge, LoadingInline, ScorePill, cx } from "../ui/primitives.js";

export function CandidatesTab() {
  const candidates = useStore((s) => s.candidates);
  const selectedCandidate = useStore((s) => s.selectedCandidate);
  const setSelectedCandidate = useStore((s) => s.setSelectedCandidate);
  const activeRunId = useStore((s) => s.activeRunId);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const loadingPersonId = useRef<string | null>(null);

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
    loadingPersonId.current = personId;
    setLoading(true);
    try {
      const detail = await window.oculai.getCandidateDetail({ personId });
      // Only apply if this is still the most recently requested candidate
      if (loadingPersonId.current === personId) {
        setSelectedCandidate((detail as CandidateDetail | null) ?? null);
      }
    } finally {
      if (loadingPersonId.current === personId) {
        setLoading(false);
      }
    }
  };

  const normalizedFilter = filter.trim().toLowerCase();
  const filtered = useMemo(() => {
    const base = normalizedFilter
      ? candidates.filter((c) => {
          const haystack = [c.canonical_name, c.latest_institution, c.latest_position, ...(c.research_areas ?? [])]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          return haystack.includes(normalizedFilter);
        })
      : candidates;
    return [...base].sort((a, b) => (b.quality_score ?? -1) - (a.quality_score ?? -1));
  }, [candidates, normalizedFilter]);

  return (
    <div className="flex h-full min-w-0">
      {/* Left: Candidate List */}
      <div className="flex w-80 shrink-0 flex-col border-r border-rule xl:w-96">
        <div className="border-b border-rule p-3">
          <label htmlFor="candidate-filter" className="sr-only">筛选候选人</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-muted" aria-hidden="true" />
            <input
              id="candidate-filter"
              type="text"
              className="input pl-9 text-xs"
              placeholder="按姓名、机构、职位筛选…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <p className="mt-1 text-[11px] text-ink-muted">
            {filtered.length} / {candidates.length}
          </p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {loading && candidates.length === 0 ? (
            <div className="p-4 text-center"><LoadingInline label="加载中" /></div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={UserRound}
              title={candidates.length === 0 ? "暂无候选人" : "无匹配结果"}
              description={candidates.length === 0 ? "搜索阶段会实时填充候选人列表。" : "尝试减少筛选关键词。"}
            />
          ) : (
            filtered.map((candidate) => (
              <CandidateListItem
                key={candidate.person_id}
                candidate={candidate}
                selected={selectedCandidate?.person_id === candidate.person_id}
                onSelect={() => handleSelectCandidate(candidate.person_id)}
              />
            ))
          )}
        </div>
      </div>

      {/* Right: Detail */}
      <div className="min-w-0 flex-1 overflow-y-auto p-5">
        {!selectedCandidate ? (
          <EmptyState
            icon={UserRound}
            title="选择候选人查看详情"
            description="右侧展示身份、证据、评分与论文等结构化信息。"
          />
        ) : (
          <CandidateDetailView candidate={selectedCandidate} />
        )}
      </div>
    </div>
  );
}

function CandidateListItem({
  candidate,
  selected,
  onSelect,
}: {
  candidate: Candidate;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cx(
        "w-full border-b border-rule p-3 text-left transition-colors hover:bg-surface-hover",
        selected && "border-l-2 border-l-accent bg-accent-soft",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-ink">{candidate.canonical_name}</div>
          {candidate.latest_institution && (
            <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-ink-muted">
              <MapPin className="h-3 w-3 shrink-0" aria-hidden="true" />
              {candidate.latest_institution}
            </p>
          )}
          {candidate.latest_position && (
            <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-ink-muted">
              <BriefcaseBusiness className="h-3 w-3 shrink-0" aria-hidden="true" />
              {candidate.latest_position}
            </p>
          )}
        </div>
        <ScorePill score={candidate.quality_score} />
      </div>
      {candidate.research_areas && candidate.research_areas.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {candidate.research_areas.slice(0, 3).map((area) => (
            <span key={area} className="rounded-full bg-surface-hover px-2 py-0.5 text-[10px] text-ink-muted">
              {area}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

function CandidateDetailView({ candidate }: { candidate: CandidateDetail }) {
  const assessments = candidate.assessments || [];
  const evidence = candidate.evidence || [];
  const works = candidate.academic_works || [];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="panel p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <h2 className="truncate font-display text-2xl font-bold text-ink">{candidate.canonical_name}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              {candidate.latest_institution && (
                <span className="flex items-center gap-1 text-sm text-ink-secondary">
                  <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
                  {candidate.latest_institution}
                </span>
              )}
              {candidate.latest_position && (
                <span className="text-sm text-ink-secondary">{candidate.latest_position}</span>
              )}
              <ScorePill score={candidate.quality_score} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:w-[26rem]">
            <StatCard icon={BookOpen} label="Papers" value={candidate.total_papers} />
            <StatCard icon={Star} label="H-Index" value={candidate.h_index} />
            <StatCard icon={Star} label="Citations" value={candidate.total_citations} />
            <StatCard icon={Code} label="Identities" value={candidate.identities?.length} />
          </div>
        </div>
      </div>

      {/* Identities */}
      {candidate.identities && candidate.identities.length > 0 && (
        <Section title={`外部身份 (${candidate.identities.length})`}>
          <div className="grid gap-2">
            {candidate.identities.map((id, i) => (
              <div
                key={`${id.source_type}-${id.external_id}-${i}`}
                className="flex items-center justify-between gap-3 rounded-lg bg-surface-hover p-2 text-sm"
              >
                <span className="shrink-0 text-ink-muted">{id.source_type}</span>
                <a
                  href={id.external_url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className={cx(
                    "min-w-0 flex items-center gap-1 truncate text-accent hover:underline",
                    !id.external_url && "pointer-events-none text-ink-muted",
                  )}
                  onClick={(e) => {
                    if (!id.external_url) e.preventDefault();
                  }}
                >
                  <span className="truncate font-mono text-xs">{id.external_id}</span>
                  {id.external_url && <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />}
                </a>
                <span className="shrink-0 font-mono text-xs text-ink-muted">
                  {(id.confidence * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Assessments */}
      {assessments.length > 0 && (
        <Section title={`评估 (${assessments.length})`}>
          <div className="grid gap-2 lg:grid-cols-2">
            {assessments.map((assessment, i) => (
              <div key={`${assessment.assessment_id}-${i}`} className="rounded-lg bg-surface-hover p-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className="font-semibold text-ink">{assessment.dimension}</span>
                    {assessment.assessor_agent && (
                      <span className="ml-2 text-xs text-ink-muted">by {assessment.assessor_agent}</span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="font-mono text-sm font-bold text-accent">{assessment.score.toFixed(1)}</span>
                    <span className="font-mono text-xs text-ink-muted">
                      {(assessment.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                {assessment.rationale && (
                  <p className="mt-2 text-xs leading-5 text-ink-secondary">{assessment.rationale}</p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Evidence */}
      {evidence.length > 0 && (
        <Section title={`证据 (${evidence.length})`}>
          <div className="space-y-2">
            {evidence.map((ev, i) => (
              <div key={`${ev.evidence_id}-${i}`} className="rounded-lg bg-surface-hover p-3 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    {ev.source_url ? (
                      <a
                        href={ev.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-semibold text-ink hover:text-accent"
                      >
                        {ev.title}
                      </a>
                    ) : (
                      <span className="font-semibold text-ink">{ev.title}</span>
                    )}
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                      <span>{ev.evidence_type}</span>
                      <span>·</span>
                      <span>{ev.source_name}</span>
                      <span>·</span>
                      <span>conf {(ev.confidence * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                  <EvidenceTierBadge tier={ev.tier} />
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Academic Works */}
      {works.length > 0 && (
        <Section title={`论文 / 作品 (${works.length})`}>
          <div className="space-y-3">
            {works.slice(0, 8).map((work, i) => (
              <div key={`${work.work_id}-${i}`} className="text-sm">
                {work.url ? (
                  <a
                    href={work.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-ink hover:text-accent"
                  >
                    {work.title}
                  </a>
                ) : (
                  <span className="font-medium text-ink">{work.title}</span>
                )}
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                  {work.venue && <span>{work.venue}</span>}
                  {work.year && <span>{work.year}</span>}
                  {work.citations !== undefined && <span>{work.citations} citations</span>}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel overflow-hidden">
      <h3 className="panel-header">{title}</h3>
      <div className="p-4">{children}</div>
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
    <div className="rounded-xl border border-rule bg-surface-hover p-3 text-center">
      <Icon className="mx-auto mb-1 h-4 w-4 text-ink-muted" aria-hidden="true" />
      <div className="font-mono text-lg font-bold text-ink">{value ?? "—"}</div>
      <div className="text-[10px] text-ink-muted">{label}</div>
    </div>
  );
}
