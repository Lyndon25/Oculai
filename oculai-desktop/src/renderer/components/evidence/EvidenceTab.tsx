import { useStore } from "../../store/index.js";

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
    <div className="h-full overflow-y-auto p-6">
      <h2 className="text-lg font-semibold text-gray-200 mb-6">Evidence Overview</h2>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <TierCard label="Tier 1 (Primary)" count={byTier.t1} color="green" />
        <TierCard label="Tier 2 (Secondary)" count={byTier.t2} color="blue" />
        <TierCard label="Tier 3 (Indirect)" count={byTier.t3} color="yellow" />
        <TierCard label="Tier 4 (Inferred)" count={byTier.t4} color="gray" />
      </div>

      {/* By type */}
      <div className="panel p-4 mb-6">
        <h3 className="panel-header -mx-4 -mt-4 mb-4">By Evidence Type</h3>
        {Object.keys(byType).length === 0 ? (
          <p className="text-sm text-gray-600">No evidence recorded yet.</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(byType)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <div key={type} className="flex items-center justify-between text-sm">
                  <span className="text-gray-400">{type}</span>
                  <div className="flex items-center gap-3">
                    <div className="w-32 bg-gray-800 rounded-full h-1.5">
                      <div
                        className="bg-blue-500 h-1.5 rounded-full"
                        style={{ width: `${Math.min(100, (count / evidence.length) * 100)}%` }}
                      />
                    </div>
                    <span className="text-gray-300 font-mono text-xs">{count}</span>
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* All evidence table */}
      <div className="panel p-4">
        <h3 className="panel-header -mx-4 -mt-4 mb-4">
          All Evidence ({evidence.length})
        </h3>
        {evidence.length === 0 ? (
          <p className="text-sm text-gray-600">
            Select a candidate to view their evidence, or wait for the enrichment phase.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                  <th className="pb-2 pr-4">Title</th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Source</th>
                  <th className="pb-2 pr-4">Tier</th>
                  <th className="pb-2 pr-4">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {evidence.map((ev, i) => (
                  <tr key={i} className="border-b border-gray-800/50">
                    <td className="py-2 pr-4 text-gray-300">{ev.title}</td>
                    <td className="py-2 pr-4 text-gray-400 text-xs">{ev.evidence_type}</td>
                    <td className="py-2 pr-4 text-gray-400 text-xs">{ev.source_name}</td>
                    <td className="py-2 pr-4">
                      <span className={`badge text-[10px] ${
                        ev.tier <= 1
                          ? "badge-green"
                          : ev.tier === 2
                            ? "badge-blue"
                            : ev.tier === 3
                              ? "badge-yellow"
                              : "badge-gray"
                      }`}>
                        T{ev.tier}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-500 text-xs">
                      {(ev.confidence * 100).toFixed(0)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
  color: "green" | "blue" | "yellow" | "gray";
}) {
  const colors = {
    green: "border-green-800 bg-green-900/20 text-green-400",
    blue: "border-blue-800 bg-blue-900/20 text-blue-400",
    yellow: "border-yellow-800 bg-yellow-900/20 text-yellow-400",
    gray: "border-gray-700 bg-gray-900/50 text-gray-500",
  };
  return (
    <div className={`panel p-4 text-center border ${colors[color]}`}>
      <div className="text-2xl font-bold">{count}</div>
      <div className="text-xs mt-1">{label}</div>
    </div>
  );
}
