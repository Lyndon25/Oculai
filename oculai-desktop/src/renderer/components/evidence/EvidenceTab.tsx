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
          <h2 className="flex items-center gap-2.5 text-[15px] font-semibold text-ink tracking-tight">
            <FileSearch className="h-4.5 w-4.5 text-accent" aria-hidden="true" />
            证据概览
          </h2>
          <p className="mt-1 text-[12px] text-ink-muted">
            {selectedCandidate
              ? `${selectedCandidate.canonical_name} 的证据链`
              : "选择候选人后查看证据质量与来源分布"}
          </p>
        </div>

        {/* Tier summary · Visual cards */}
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <TierCard label="T1 · Primary" count={byTier.t1} color="success" />
          <TierCard label="T2 · Secondary" count={byTier.t2} color="blue" />
          <TierCard label="T3 · Indirect" count={byTier.t3} color="warning" />
          <TierCard label="T4 · Inferred" count={byTier.t4} color="neutral" />
        </div>

        <div className="grid gap-5 xl:grid-cols-[22rem_1fr]">
          {/* By type */}
          <div className="card overflow-hidden">
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
                        <div className="mb-1 flex items-center justify-between gap-3 text-[12px]">
                          <span className="truncate text-ink-secondary font-medium">{type}</span>
                          <span className="font-mono text-[11px] text-ink-muted">{count}</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-rule overflow-hidden">
                          <div
                            className="h-1.5 rounded-full bg-accent transition-all duration-500 ease-[var(--oc-spring-smooth)]"
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
          <div className="card overflow-hidden">
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
                    <tr className="border-b border-rule text-left text-[11px] font-semibold text-ink-muted uppercase tracking-wider">
                      <th className="px-4 py-2.5 font-medium">Title</th>
                      <th className="px-4 py-2.5 font-medium">Type</th>
                      <th className="px-4 py-2.5 font-medium">Source</th>
                      <th className="px-4 py-2.5 font-medium">Tier</th>
                      <th className="px-4 py-2.5 font-medium">Conf</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidence.map((ev, i) => (
                      <tr key={`${ev.evidence_id}-${i}`} className="border-b border-rule hover:bg-surface-hover transition-colors">
                        <td className="max-w-md px-4 py-2.5 text-ink text-[12px]">
                          {ev.source_url ? (
                            <a href={ev.source_url} target="_blank" rel="noreferrer" className="hover:text-accent transition-colors">
                              {ev.title}
                            </a>
                          ) : (
                            ev.title
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-[11px] text-ink-muted">{ev.evidence_type}</td>
                        <td className="px-4 py-2.5 text-[11px] text-ink-muted">{ev.source_name}</td>
                        <td className="px-4 py-2.5"><EvidenceTierBadge tier={ev.tier} /></td>
                        <td className="px-4 py-2.5 font-mono text-[11px] text-ink-muted">{(ev.confidence * 100).toFixed(0)}%</td>
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
  color,
}: {
  label: string;
  count: number;
  color: "success" | "blue" | "warning" | "neutral";
}) {
  const colors = {
    success: "bg-success-soft border-success-muted text-success",
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    warning: "bg-warning-soft border-warning-muted text-warning",
    neutral: "bg-surface-hover border-rule text-ink-muted",
  };
  return (
    <div className={`card p-4 text-center border ${colors[color]}`}>
      <div className="font-mono text-2xl font-bold">{count}</div>
      <div className="mt-1 text-[11px] font-medium">{label}</div>
    </div>
  );
}
