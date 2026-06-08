import { useStore } from "../../store/index.js";
import { FileSearch, Layers, TableProperties } from "lucide-react";
import { EmptyState, EvidenceTierBadge } from "../ui/primitives.js";

export function EvidenceTab() {
  const selectedCandidate = useStore((s) => s.selectedCandidate);
  const evidence = selectedCandidate?.evidence || [];

  const byTier = {
    t1: evidence.filter((e) => e.tier <= 1).length,
    t2: evidence.filter((e) => e.tier === 2).length,
    t3: evidence.filter((e) => e.tier === 3).length,
    t4: evidence.filter((e) => e.tier >= 4).length,
  };

  const byType: Record<string, number> = {};
  for (const e of evidence) {
    byType[e.evidence_type] = (byType[e.evidence_type] || 0) + 1;
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="mx-auto max-w-6xl space-y-5">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
            <FileSearch className="h-5 w-5 text-accent" aria-hidden="true" />
            证据概览
          </h2>
          <p className="mt-1 text-xs text-ink-muted">
            {selectedCandidate
              ? `${selectedCandidate.canonical_name} 的证据链`
              : "选择候选人后查看证据质量与来源分布"}
          </p>
        </div>

        {/* Tier summary */}
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <TierCard label="T1 · Primary" count={byTier.t1} className="border-emerald-200 bg-emerald-50 text-emerald-700" />
          <TierCard label="T2 · Secondary" count={byTier.t2} className="border-blue-200 bg-blue-50 text-blue-700" />
          <TierCard label="T3 · Indirect" count={byTier.t3} className="border-amber-200 bg-amber-50 text-amber-700" />
          <TierCard label="T4 · Inferred" count={byTier.t4} className="border-rule bg-surface-hover text-ink-muted" />
        </div>

        <div className="grid gap-5 xl:grid-cols-[22rem_1fr]">
          {/* By type */}
          <div className="panel overflow-hidden">
            <h3 className="panel-header flex items-center gap-2">
              <Layers className="h-4 w-4 text-accent" aria-hidden="true" />
              Evidence Type
            </h3>
            <div className="p-4">
              {Object.keys(byType).length === 0 ? (
                <EmptyState icon={Layers} title="暂无证据类型" description="Enrichment 阶段会生成证据类型分布。" />
              ) : (
                <div className="space-y-3">
                  {Object.entries(byType)
                    .sort(([, a], [, b]) => b - a)
                    .map(([type, count]) => (
                      <div key={type}>
                        <div className="mb-1 flex items-center justify-between gap-3 text-sm">
                          <span className="truncate text-ink-secondary">{type}</span>
                          <span className="font-mono text-xs text-ink-muted">{count}</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-rule" aria-hidden="true">
                          <div
                            className="h-1.5 rounded-full bg-accent transition-all"
                            style={{ width: `${Math.min(100, (count / Math.max(1, evidence.length)) * 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>

          {/* All evidence table */}
          <div className="panel overflow-hidden">
            <h3 className="panel-header flex items-center gap-2">
              <TableProperties className="h-4 w-4 text-accent" aria-hidden="true" />
              All Evidence ({evidence.length})
            </h3>
            {evidence.length === 0 ? (
              <EmptyState
                icon={FileSearch}
                title="暂无证据"
                description="选择候选人，或等待 Profile Enricher 抓取线索。"
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-rule text-left text-xs text-ink-muted">
                      <th className="px-4 py-2 font-medium">Title</th>
                      <th className="px-4 py-2 font-medium">Type</th>
                      <th className="px-4 py-2 font-medium">Source</th>
                      <th className="px-4 py-2 font-medium">Tier</th>
                      <th className="px-4 py-2 font-medium">Conf</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidence.map((ev, i) => (
                      <tr key={`${ev.evidence_id}-${i}`} className="border-b border-rule hover:bg-surface-hover">
                        <td className="max-w-md px-4 py-2 text-ink">
                          {ev.source_url ? (
                            <a href={ev.source_url} target="_blank" rel="noreferrer" className="hover:text-accent">
                              {ev.title}
                            </a>
                          ) : (
                            ev.title
                          )}
                        </td>
                        <td className="px-4 py-2 text-xs text-ink-muted">{ev.evidence_type}</td>
                        <td className="px-4 py-2 text-xs text-ink-muted">{ev.source_name}</td>
                        <td className="px-4 py-2"><EvidenceTierBadge tier={ev.tier} /></td>
                        <td className="px-4 py-2 font-mono text-xs text-ink-muted">{(ev.confidence * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function TierCard({
  label,
  count,
  className,
}: {
  label: string;
  count: number;
  className: string;
}) {
  return (
    <div className={`rounded-xl border p-4 text-center ${className}`}>
      <div className="font-mono text-2xl font-bold">{count}</div>
      <div className="mt-1 text-xs font-medium">{label}</div>
    </div>
  );
}
