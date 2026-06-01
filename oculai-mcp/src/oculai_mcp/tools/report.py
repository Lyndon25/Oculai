"""Report export — Markdown and polished HTML visualization.

The HTML report is the primary project deliverable: a self-contained,
print-ready, visually rich dashboard presenting the complete sourcing
run results (strategy, task summary, ranked candidates with score
breakdowns and evidence counts).
"""

from typing import Any
from uuid import UUID

from oculai_mcp.db.client import fetch_with_retry, fetchrow_with_retry


async def export_report(run_id: UUID, format: str = "html") -> dict[str, Any]:
    """Export a sourcing run report.

    Args:
        run_id: The run UUID
        format: "html" (default) or "markdown"
    """
    run = await fetchrow_with_retry("SELECT * FROM sourcingrun WHERE run_id = $1", run_id)
    if not run:
        return {"error": "run not found"}

    # Get plan
    plan = None
    if run.get("active_plan_id"):
        plan_row = await fetchrow_with_retry("SELECT * FROM plan WHERE plan_id = $1", run["active_plan_id"])
        plan = dict(plan_row) if plan_row else None

    # Get all candidates with assessments
    candidates = await fetch_with_retry(
        """
        SELECT cr.record_id, cr.person_id, cr.status, cr.quality_score, cr.raw_data, cr.enriched_data, cr.match_scores,
               p.canonical_name, p.latest_institution, p.latest_position, p.h_index, p.total_citations, p.total_papers,
               p.orcid, p.google_scholar_id, p.github_id, p.linkedin_url
        FROM candidaterecord cr
        JOIN person p ON p.person_id = cr.person_id
        WHERE cr.run_id = $1
        ORDER BY cr.quality_score DESC
        """,
        run_id,
    )

    # Get task summary
    task_summary = await fetch_with_retry(
        "SELECT task_type, status, COUNT(*) as cnt FROM task WHERE run_id = $1 GROUP BY task_type, status",
        run_id,
    )

    # Build report — with filtering of garbage candidates
    candidate_list = []
    filtered_candidates = []
    for c in candidates:
        assessments = await fetch_with_retry(
            "SELECT dimension, score, confidence, rationale FROM candidateassessment WHERE run_id = $1 AND person_id = $2",
            run_id, c["person_id"],
        )
        evidence_count = await fetchrow_with_retry(
            "SELECT COUNT(*) as cnt FROM evidence WHERE person_id = $1", c["person_id"],
        )
        ev_count = evidence_count["cnt"] if evidence_count else 0

        # Gate status from match_scores JSONB
        gate_status = "unknown"
        match_scores = c.get("match_scores") or {}
        if isinstance(match_scores, dict):
            gate_status = match_scores.get("gate_status", "unknown")

        # Evidence details with tier
        ev_rows = await fetch_with_retry(
            "SELECT tier, source_name, title, confidence, quality_flags FROM evidence WHERE person_id = $1 ORDER BY tier ASC, confidence DESC LIMIT 10",
            c["person_id"],
        )
        evidence_details = [dict(r) for r in ev_rows]

        # Score history
        hist_rows = await fetch_with_retry(
            "SELECT new_score as score, dimension, changed_at FROM assessmentscorehistory WHERE run_id = $1 AND person_id = $2 ORDER BY changed_at ASC",
            run_id, c["person_id"],
        )
        score_history = [{"score": r["score"], "dimension": r["dimension"], "at": str(r["changed_at"])} for r in hist_rows]

        candidate_item = {
            "name": c["canonical_name"],
            "institution": c["latest_institution"],
            "position": c["latest_position"],
            "h_index": c["h_index"],
            "total_citations": c["total_citations"],
            "total_papers": c["total_papers"],
            "external_ids": {
                "orcid": c["orcid"], "google_scholar": c["google_scholar_id"],
                "github": c["github_id"], "linkedin": c["linkedin_url"],
            },
            "status": c["status"],
            "overall_score": c["quality_score"],
            "dimension_scores": {a["dimension"]: {"score": a["score"], "confidence": a["confidence"], "rationale": a["rationale"]} for a in assessments},
            "evidence_count": ev_count,
            "evidence_details": evidence_details,
            "score_history": score_history,
            "gate_status": gate_status,
            "audit_flags": [],
        }

        # Filter check
        filter_reason = _filter_reason(candidate_item)
        if filter_reason:
            filtered_candidates.append({"name": candidate_item["name"], "reason": filter_reason})
        else:
            candidate_list.append(candidate_item)

    report = {
        "run": {
            "run_id": str(run_id),
            "title": run["title"],
            "status": run["status"],
            "created_at": str(run["created_at"]),
            "target_profile": run["target_profile"],
        },
        "plan": {
            "strategy_summary": plan["strategy_summary"] if plan else None,
        },
        "task_summary": [dict(t) for t in task_summary],
        "candidates": candidate_list,
        "candidate_count": len(candidate_list),
        "filtered_candidates": filtered_candidates,
        "filtered_count": len(filtered_candidates),
        "shortlist_cutoff": None,
    }

    if format == "markdown":
        report["markdown"] = _render_markdown(report)
    elif format == "html":
        report["html"] = _render_html(report)

    return report


def _render_markdown(report: dict[str, Any]) -> str:
    """Render report as Markdown (Chinese)."""
    r = report["run"]
    candidates = report["candidates"]
    shortlisted = sum(1 for c in candidates if c["status"] == "shortlisted")
    avg_score = (
        sum(c["overall_score"] or 0 for c in candidates) / len(candidates)
        if candidates else 0
    )

    lines = [
        f"# {r['title']}",
        f"",
        f"**状态**: {r['status']} | **创建时间**: {r['created_at']}",
        f"",
        f"## 执行概览",
        f"",
        f"- 候选人总数: {len(candidates)}",
        f"- 已入围: {shortlisted}",
        f"- 平均综合评分: {avg_score:.0f}",
        f"",
        f"## 搜索策略",
        f"",
        f"{report['plan'].get('strategy_summary', '未记录搜索策略。')}",
        f"",
        f"## 任务汇总",
        f"",
    ]
    for t in report["task_summary"]:
        lines.append(f"- {t['task_type']}: {t['cnt']} ({t['status']})")

    lines.extend(["", "## 候选人详情", ""])
    for i, c in enumerate(candidates, 1):
        lines.extend([
            f"### {i}. {c['name']} — 综合评分: {c['overall_score']}/100",
            f"",
            f"- **机构**: {c['institution'] or '—'}",
            f"- **H-Index**: {c['h_index']} | **被引次数**: {c['total_citations']} | **论文数**: {c['total_papers']}",
            f"- **状态**: {c['status']} | **证据条目**: {c['evidence_count']}",
        ])
        if c["dimension_scores"]:
            lines.append("- **维度评分**:")
            for dim, s in c["dimension_scores"].items():
                dim_name = _DIM_LABELS.get(dim, dim)
                lines.append(f"  - {dim_name}: {s['score']}/10 (置信度: {s['confidence']:.0%})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML report — polished, self-contained, print-ready
# ---------------------------------------------------------------------------

_CSS = r"""
/* ========================================================================
   Oculai Report — Swiss Precision / Modern Flat Premium
   Flat, geometric, restrained elegance. Light interface. Thin 1px borders.
   ======================================================================== */

:root {
    /* Base */
    --bg: #f6f6f4;
    --surface: #ffffff;
    --surface-raised: #fafaf9;
    --text: #0f172a;
    --text-secondary: #64748b;
    --text-muted: #94a3b8;
    --border: #e2e8f0;
    --border-strong: #cbd5e1;
    --grid-line: rgba(148,163,184,0.12);

    /* Accent — single disciplined indigo family */
    --accent: #4f46e5;
    --accent-soft: #e0e7ff;
    --accent-text: #3730a3;

    /* Semantic — flat, no pastels */
    --good: #059669;
    --good-soft: #d1fae5;
    --warn: #d97706;
    --warn-soft: #fef3c7;
    --caution: #ea580c;
    --caution-soft: #ffedd5;
    --bad: #dc2626;
    --bad-soft: #fee2e2;

    --radius: 6px;
    --radius-sm: 3px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

html { scroll-behavior: smooth; }

body {
    font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei",
                 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
    font-size: 14px;
}

/* Subtle dot-grid texture on body */
body::before {
    content: "";
    position: fixed; inset: 0; pointer-events: none; z-index: 0;
    background-image: radial-gradient(circle, var(--grid-line) 0.6px, transparent 0.6px);
    background-size: 24px 24px;
}

.container {
    position: relative; z-index: 1;
    max-width: 1200px; margin: 0 auto;
    padding: 40px 32px 80px;
}

/* ========================================================================
   Typography
   ======================================================================== */

h1, h2, h3, h4 {
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.25;
}

.mono {
    font-family: "SF Mono", "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
}

/* ========================================================================
   Header
   ======================================================================== */

.report-header {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 36px 40px;
    margin-bottom: 24px;
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 24px; flex-wrap: wrap;
}

.report-header .brand {
    font-size: 11px; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--accent);
    margin-bottom: 10px;
}

.report-header h1 {
    font-size: 30px; font-weight: 800;
    color: var(--text); max-width: 700px;
}

.report-header .header-meta {
    display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px;
}

.badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: var(--radius-sm);
    font-size: 12px; font-weight: 600; line-height: 1;
}

.badge-done   { background: var(--good-soft); color: var(--good); }
.badge-active { background: var(--accent-soft); color: var(--accent-text); }
.badge-draft  { background: var(--surface-raised); color: var(--text-secondary); border: 1px solid var(--border); }
.badge-plain  { background: var(--surface-raised); color: var(--text-secondary); border: 1px solid var(--border); }

.header-right {
    text-align: right; flex-shrink: 0;
    display: flex; flex-direction: column; align-items: flex-end; gap: 6px;
}

.header-right .meta-label {
    font-size: 11px; color: var(--text-muted); font-weight: 500;
    letter-spacing: 0.05em; text-transform: uppercase;
}

.header-right .meta-value {
    font-size: 13px; color: var(--text-secondary); font-weight: 500;
}

/* ========================================================================
   Section Cards
   ======================================================================== */

.section-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px 32px;
    margin-bottom: 20px;
}

.section-title {
    font-size: 13px; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 20px;
    display: flex; align-items: center; gap: 10px;
}

.section-title::before {
    content: "";
    display: inline-block; width: 4px; height: 16px;
    background: var(--accent); border-radius: 2px;
}

/* ========================================================================
   KPI Dashboard
   ======================================================================== */

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 14px;
}

@media (max-width: 1024px) {
    .kpi-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 640px) {
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}

.kpi-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 18px;
    display: flex; flex-direction: column; gap: 6px;
    transition: border-color 0.15s, box-shadow 0.15s;
}

.kpi-card:hover {
    border-color: var(--border-strong);
    box-shadow: 0 2px 8px rgba(15,23,42,0.04);
}

.kpi-card .kpi-value {
    font-size: 26px; font-weight: 800;
    letter-spacing: -0.03em; line-height: 1.1;
}

.kpi-card .kpi-label {
    font-size: 11px; font-weight: 600;
    color: var(--text-muted); letter-spacing: 0.04em;
    text-transform: uppercase;
}

.kpi-card .kpi-delta {
    font-size: 11px; font-weight: 600; margin-top: 2px;
}

.kpi-accent .kpi-value { color: var(--accent); }
.kpi-good   .kpi-value { color: var(--good); }
.kpi-warn   .kpi-value { color: var(--warn); }
.kpi-caution .kpi-value { color: var(--caution); }

/* ========================================================================
   Visualization Panels
   ======================================================================== */

.viz-grid {
    display: grid;
    grid-template-columns: 1.3fr 1fr 1fr;
    gap: 16px; margin-bottom: 20px;
}

@media (max-width: 1024px) {
    .viz-grid { grid-template-columns: 1fr; }
}

.viz-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px 24px;
}

.viz-panel h3 {
    font-size: 12px; font-weight: 700;
    letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 18px;
}

/* ---- Histogram ---- */
.histogram { display: flex; flex-direction: column; gap: 8px; }
.hist-row {
    display: flex; align-items: center; gap: 10px;
    font-size: 12px;
}
.hist-label {
    width: 36px; text-align: right;
    color: var(--text-muted); font-weight: 600;
    font-family: "SF Mono", monospace; font-size: 11px;
}
.hist-track {
    flex: 1; height: 20px; background: var(--surface-raised);
    border-radius: var(--radius-sm); position: relative; overflow: hidden;
}
.hist-bar {
    height: 100%; border-radius: var(--radius-sm);
    transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
    position: relative;
}
.hist-bar::after {
    content: attr(data-count);
    position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
    font-size: 10px; font-weight: 700; color: #fff;
    font-family: "SF Mono", monospace;
    text-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
.hist-bar-accent { background: var(--accent); }
.hist-bar-good   { background: var(--good); }
.hist-bar-warn   { background: var(--warn); }
.hist-bar-caution{ background: var(--caution); }
.hist-bar-empty  { background: var(--border-strong); }

/* ---- Task Stacked Bars ---- */
.task-viz { display: flex; flex-direction: column; gap: 14px; }
.task-viz-row { display: flex; flex-direction: column; gap: 5px; }
.task-viz-header {
    display: flex; justify-content: space-between;
    font-size: 12px; font-weight: 500;
}
.task-viz-header .task-name { color: var(--text); }
.task-viz-header .task-count { color: var(--text-muted); font-family: "SF Mono", monospace; }

.stacked-track {
    height: 8px; background: var(--surface-raised);
    border-radius: 99px; display: flex; overflow: hidden;
}
.stacked-seg {
    height: 100%;
    transition: width 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}
.stacked-done { background: var(--good); }
.stacked-active { background: var(--accent); }
.stacked-pending { background: var(--border-strong); }

.task-legend {
    display: flex; gap: 14px; margin-top: 10px;
    font-size: 11px; color: var(--text-muted);
}
.task-legend span { display: flex; align-items: center; gap: 5px; }
.task-legend .dot { width: 7px; height: 7px; border-radius: 50%; }

/* ---- Source Performance ---- */
.source-viz { display: flex; flex-direction: column; gap: 10px; }
.source-row {
    display: flex; align-items: center; gap: 10px; font-size: 12px;
}
.source-name {
    width: 80px; text-align: right; font-weight: 500;
    color: var(--text-secondary); white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis;
}
.source-track {
    flex: 1; height: 10px; background: var(--surface-raised);
    border-radius: 99px; overflow: hidden;
}
.source-bar {
    height: 100%; border-radius: 99px;
    transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
    background: var(--accent);
    opacity: 0.85;
}
.source-count {
    width: 28px; text-align: right;
    font-family: "SF Mono", monospace; font-size: 11px;
    color: var(--text-muted); font-weight: 600;
}

/* ========================================================================
   Strategy Block
   ======================================================================== */

.strategy-text {
    font-size: 14px; line-height: 1.85;
    color: var(--text-secondary);
    white-space: pre-wrap;
}

/* ========================================================================
   Candidate Cards
   ======================================================================== */

.candidate-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0;
    margin-bottom: 16px;
    overflow: hidden;
    display: grid;
    grid-template-columns: 52px 1fr 180px;
    transition: border-color 0.15s, box-shadow 0.15s;
}

.candidate-card:hover {
    border-color: var(--border-strong);
    box-shadow: 0 4px 16px rgba(15,23,42,0.05);
}

@media (max-width: 860px) {
    .candidate-card { grid-template-columns: 44px 1fr; }
    .candidate-right { display: none; }
}

.candidate-rank-bar {
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 800; color: var(--text-muted);
    border-right: 1px solid var(--border);
    background: var(--surface-raised);
    font-family: "SF Mono", monospace;
}

.candidate-card.top-pick .candidate-rank-bar {
    background: var(--accent); color: #fff;
    border-right-color: var(--accent);
}

.candidate-main {
    padding: 22px 26px;
    display: flex; flex-direction: column; gap: 14px;
}

.candidate-right {
    border-left: 1px solid var(--border);
    background: var(--surface-raised);
    padding: 22px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 10px;
}

.candidate-header {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 16px; flex-wrap: wrap;
}

.candidate-name-group {}

.candidate-name-group h3 {
    font-size: 18px; font-weight: 700; color: var(--text);
}

.candidate-name-group .institution {
    font-size: 13px; color: var(--text-secondary); margin-top: 2px;
}

.candidate-name-group .position {
    font-size: 12px; color: var(--accent-text); font-weight: 600; margin-top: 3px;
}

.status-tag {
    display: inline-block; padding: 2px 8px; border-radius: var(--radius-sm);
    font-size: 11px; font-weight: 600;
}

.status-shortlisted { background: var(--good-soft); color: var(--good); }
.status-new         { background: var(--accent-soft); color: var(--accent-text); }
.status-contacted   { background: var(--warn-soft); color: var(--warn); }
.status-default     { background: var(--surface-raised); color: var(--text-muted); border: 1px solid var(--border); }

/* ---- Score Donut ---- */
.donut-chart {
    position: relative; width: 90px; height: 90px;
}
.donut-chart svg { transform: rotate(-90deg); }
.donut-chart .donut-bg { fill: none; stroke: var(--border); stroke-width: 8; }
.donut-chart .donut-fill {
    fill: none; stroke-width: 8; stroke-linecap: round;
    transition: stroke-dashoffset 0.8s cubic-bezier(0.22, 1, 0.36, 1);
}
.donut-text {
    position: absolute; inset: 0; display: flex;
    flex-direction: column; align-items: center; justify-content: center;
}
.donut-value { font-size: 20px; font-weight: 800; line-height: 1; }
.donut-label { font-size: 10px; color: var(--text-muted); font-weight: 600; margin-top: 2px; letter-spacing: 0.05em; }

.donut-good   .donut-fill { stroke: var(--good); }
.donut-good   .donut-value { color: var(--good); }
.donut-warn   .donut-fill { stroke: var(--warn); }
.donut-warn   .donut-value { color: var(--warn); }
.donut-caution .donut-fill { stroke: var(--caution); }
.donut-caution .donut-value { color: var(--caution); }
.donut-bad    .donut-fill { stroke: var(--bad); }
.donut-bad    .donut-value { color: var(--bad); }

/* ---- Metrics ---- */
.metrics-row {
    display: flex; gap: 24px; flex-wrap: wrap;
}
.metric-item {
    display: flex; align-items: baseline; gap: 6px;
}
.metric-item .m-val {
    font-size: 16px; font-weight: 700;
    font-family: "SF Mono", monospace;
    color: var(--text);
}
.metric-item .m-lbl {
    font-size: 11px; color: var(--text-muted); font-weight: 500;
    text-transform: uppercase; letter-spacing: 0.03em;
}

/* ---- Dimension Mini-Bars ---- */
.dim-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 10px;
}

.dim-item {
    display: flex; flex-direction: column; gap: 5px;
}

.dim-item-header {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 11px;
}
.dim-item-header .dim-name {
    font-weight: 600; color: var(--text-secondary);
    text-transform: capitalize;
}
.dim-item-header .dim-score {
    font-family: "SF Mono", monospace; font-weight: 700;
    font-size: 11px;
}

.dim-track {
    height: 5px; background: var(--surface-raised);
    border-radius: 99px; overflow: hidden;
}
.dim-fill {
    height: 100%; border-radius: 99px;
    transition: width 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}

.dim-fill-good  { background: var(--good); }
.dim-fill-warn   { background: var(--warn); }
.dim-fill-caution   { background: var(--caution); }
.dim-fill-bad  { background: var(--bad); }

.dim-note {
    font-size: 10px; color: var(--text-muted);
    font-style: italic;
}

/* ---- Evidence & IDs ---- */
.candidate-footer {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap; margin-top: 4px;
    padding-top: 12px; border-top: 1px solid var(--border);
}

.evidence-pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: var(--radius-sm);
    font-size: 11px; font-weight: 600;
}
.evidence-good   { background: var(--good-soft); color: var(--good); }
.evidence-ok     { background: var(--warn-soft); color: var(--warn); }
.evidence-low    { background: var(--bad-soft); color: var(--bad); }

.id-pills {
    display: flex; gap: 6px; flex-wrap: wrap;
}
.id-pill {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: var(--radius-sm);
    font-size: 10px; font-weight: 600;
    background: var(--surface-raised); color: var(--text-muted);
    border: 1px solid var(--border);
}
.id-pill .id-key { opacity: 0.7; font-weight: 500; }

/* ---- Empty state ---- */
.empty-state {
    text-align: center; padding: 60px 24px; color: var(--text-muted);
}
.empty-state .empty-icon {
    font-size: 36px; margin-bottom: 14px; opacity: 0.5;
}
.empty-state p { font-size: 14px; }

/* ---- Gate Status Indicator ---- */
.gate-status {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: var(--radius-sm);
    font-size: 10px; font-weight: 700; letter-spacing: 0.03em;
    text-transform: uppercase;
}
.gate-passed { background: var(--good-soft); color: var(--good); }
.gate-failed { background: var(--bad-soft); color: var(--bad); }

/* ---- Audit Badge ---- */
.audit-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: var(--radius-sm);
    font-size: 10px; font-weight: 700;
    background: var(--warn-soft); color: var(--warn);
}

/* ---- Evidence Detail Panel (CSS-only expand) ---- */
.evidence-panel { margin-top: 10px; }
.evidence-toggle {
    display: none;
}
.evidence-label {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 600; color: var(--accent);
    cursor: pointer; padding: 4px 0;
}
.evidence-label::after {
    content: "+"; font-size: 13px; font-weight: 700;
}
.evidence-toggle:checked + .evidence-label::after {
    content: "-";
}
.evidence-details {
    display: none;
    margin-top: 8px;
    padding: 10px 12px;
    background: var(--surface-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
}
.evidence-toggle:checked ~ .evidence-details {
    display: block;
}
.evidence-item {
    display: flex; align-items: center; gap: 8px;
    padding: 5px 0; font-size: 11px;
    border-bottom: 1px solid var(--border);
}
.evidence-item:last-child { border-bottom: none; }
.evidence-tier {
    display: inline-flex; align-items: center; justify-content: center;
    width: 22px; height: 16px; border-radius: 3px;
    font-size: 9px; font-weight: 800; color: #fff;
    flex-shrink: 0;
}
.tier-1 { background: var(--good); }
.tier-2 { background: var(--accent); }
.tier-3 { background: var(--warn); }
.tier-4 { background: var(--caution); }
.tier-0 { background: var(--text-muted); }
.evidence-source { font-weight: 600; color: var(--text-secondary); min-width: 60px; }
.evidence-title { color: var(--text); flex: 1; }
.evidence-confidence { color: var(--text-muted); font-family: "SF Mono", monospace; }
.evidence-flags { color: var(--caution); font-style: italic; }

/* ---- Score History Sparkline ---- */
.score-history {
    font-size: 10px; color: var(--text-muted);
    margin-top: 4px; font-family: "SF Mono", monospace;
}

/* ---- Audit Findings Panel ---- */
.audit-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 24px;
    margin-bottom: 20px;
}
.audit-panel h3 {
    font-size: 12px; font-weight: 700;
    letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 14px;
}
.audit-stat-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px; margin-bottom: 16px;
}
@media (max-width: 640px) {
    .audit-stat-grid { grid-template-columns: repeat(2, 1fr); }
}
.audit-stat {
    background: var(--surface-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 12px;
    text-align: center;
}
.audit-stat .audit-stat-value {
    font-size: 20px; font-weight: 800;
    font-family: "SF Mono", monospace;
}
.audit-stat .audit-stat-label {
    font-size: 10px; color: var(--text-muted); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.03em; margin-top: 4px;
}

/* ---- Tier Distribution (CSS conic-gradient pie) ---- */
.tier-pie {
    width: 80px; height: 80px; border-radius: 50%;
    position: relative;
}
.tier-pie-label {
    position: absolute; inset: 0; display: flex;
    align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: var(--text-muted);
}

/* ---- Footer ---- */
.report-footer {
    text-align: center; padding: 32px 24px;
    color: var(--text-muted); font-size: 12px;
    border-top: 1px solid var(--border); margin-top: 8px;
}

/* ========================================================================
   Print
   ======================================================================== */

@media print {
    body { background: #fff; font-size: 11px; }
    body::before { display: none; }
    .container { max-width: 100%; padding: 16px; }
    .section-card, .candidate-card, .viz-panel, .kpi-card {
        box-shadow: none !important; break-inside: avoid;
        border: 1px solid #ddd !important;
    }
    .candidate-card { grid-template-columns: 40px 1fr 160px; }
    .candidate-right { display: flex !important; }
    .report-header { background: #fff !important; border: 1px solid #ddd !important; }
}
"""


def _render_html(report: dict[str, Any]) -> str:
    """Render a polished, self-contained HTML report."""
    r = report["run"]
    candidates = report["candidates"]
    tasks = report["task_summary"]

    # ---- Derived stats ----
    shortlisted = sum(1 for c in candidates if c["status"] == "shortlisted")
    avg_score = (
        sum(c["overall_score"] or 0 for c in candidates) / len(candidates)
        if candidates else 0
    )
    total_evidence = sum(c.get("evidence_count", 0) for c in candidates)
    avg_hindex = (
        sum((c["h_index"] or 0) for c in candidates) / len(candidates)
        if candidates else 0
    )
    total_tasks = sum(t["cnt"] for t in tasks)
    completed_tasks = sum(t["cnt"] for t in tasks if t["status"] in ("completed", "done"))
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks else 0

    # Score histogram buckets (0-20, 21-40, 41-60, 61-80, 81-100)
    buckets = [0, 0, 0, 0, 0]
    bucket_labels = ["0-20", "21-40", "41-60", "61-80", "81-100"]
    bucket_classes = ["hist-bar-poor", "hist-bar-caution", "hist-bar-warn", "hist-bar-good", "hist-bar-accent"]
    for c in candidates:
        s = c["overall_score"] or 0
        if s >= 81:
            buckets[4] += 1
        elif s >= 61:
            buckets[3] += 1
        elif s >= 41:
            buckets[2] += 1
        elif s >= 21:
            buckets[1] += 1
        else:
            buckets[0] += 1
    max_bucket = max(buckets) if any(buckets) else 1

    # Task grouped by type
    task_by_type: dict[str, dict[str, int]] = {}
    for t in tasks:
        tt = t["task_type"]
        if tt not in task_by_type:
            task_by_type[tt] = {}
        task_by_type[tt][t["status"]] = t["cnt"]

    # Source performance (task type as proxy)
    source_data = sorted(
        [(tt, sum(s.values())) for tt, s in task_by_type.items()],
        key=lambda x: x[1], reverse=True,
    )[:6]
    max_source = max((v for _, v in source_data), default=1)

    status_map = {
        "completed": ("badge-done", "已完成"),
        "active": ("badge-active", "进行中"),
        "done": ("badge-done", "已完成"),
    }
    status_class, status_label = status_map.get(r["status"], ("badge-draft", r["status"] or "未知"))

    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>Oculai 人才洞察报告 — {_esc(r['title'])}</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        '<div class="container">',
        # ========== HEADER ==========
        '<div class="report-header">',
        "<div>",
        '<div class="brand">Oculai 智能人才洞察</div>',
        f"<h1>{_esc(r['title'])}</h1>",
        '<div class="header-meta">',
        f"<span class='badge {status_class}'>{_esc(status_label)}</span>",
        f"<span class='badge badge-plain'>{_esc(r['created_at'])}</span>",
        f"<span class='badge badge-plain'>{_esc(r.get('target_profile') or '未指定目标画像')}</span>",
        "</div>",
        "</div>",
        '<div class="header-right">',
        '<div class="meta-label">报告编号</div>',
        f'<div class="meta-value mono">{str(r["run_id"])[:8].upper()}</div>',
        '<div class="meta-label" style="margin-top:8px">生成时间</div>',
        f'<div class="meta-value">{r["created_at"][:19]}</div>',
        "</div>",
        "</div>",
        # ========== KPI DASHBOARD ==========
        '<div class="kpi-grid">',
        f'<div class="kpi-card kpi-accent"><div class="kpi-value mono">{len(candidates)}</div><div class="kpi-label">候选人总数</div></div>',
        f'<div class="kpi-card kpi-good"><div class="kpi-value mono">{shortlisted}</div><div class="kpi-label">已入围</div></div>',
        f'<div class="kpi-card kpi-accent"><div class="kpi-value mono">{avg_score:.0f}</div><div class="kpi-label">平均综合评分</div></div>',
        f'<div class="kpi-card"><div class="kpi-value mono">{total_evidence}</div><div class="kpi-label">证据条目总数</div></div>',
        f'<div class="kpi-card"><div class="kpi-value mono">{avg_hindex:.0f}</div><div class="kpi-label">平均 H-Index</div></div>',
        f'<div class="kpi-card kpi-good"><div class="kpi-value mono">{completion_rate:.0f}%</div><div class="kpi-label">任务完成率</div></div>',
        "</div>",
        # ========== VISUALIZATIONS ==========
        '<div class="viz-grid">',
        # -- Score Histogram --
        '<div class="viz-panel">',
        '<h3>综合评分分布</h3>',
        '<div class="histogram">',
    ]
    for label, count, bclass in zip(bucket_labels, buckets, bucket_classes):
        width = (count / max_bucket * 100) if max_bucket else 0
        parts.append(
            '<div class="hist-row">'
            f'<div class="hist-label">{label}</div>'
            f'<div class="hist-track">'
            f'<div class="hist-bar {bclass}" style="width:{width:.0f}%" data-count="{count}"></div>'
            '</div>'
            '</div>'
        )
    parts.append('</div></div>')

    # -- Task Execution --
    parts.extend([
        '<div class="viz-panel">',
        '<h3>任务执行状态</h3>',
        '<div class="task-viz">',
    ])
    for tt, statuses in sorted(task_by_type.items(), key=lambda x: sum(x[1].values()), reverse=True)[:5]:
        total = sum(statuses.values())
        done = statuses.get("completed", 0) + statuses.get("done", 0)
        active = statuses.get("active", 0)
        pending = total - done - active
        parts.append(
            '<div class="task-viz-row">'
            '<div class="task-viz-header">'
            f'<span class="task-name">{_esc(tt)}</span>'
            f'<span class="task-count">{done}/{total}</span>'
            '</div>'
            '<div class="stacked-track">'
            f'<div class="stacked-seg stacked-done" style="width:{done/total*100:.0f}%"></div>'
            f'<div class="stacked-seg stacked-active" style="width:{active/total*100:.0f}%"></div>'
            f'<div class="stacked-seg stacked-pending" style="width:{pending/total*100:.0f}%"></div>'
            '</div>'
            '</div>'
        )
    parts.extend([
        '<div class="task-legend">',
        '<span><span class="dot" style="background:var(--good)"></span>已完成</span>',
        '<span><span class="dot" style="background:var(--accent)"></span>进行中</span>',
        '<span><span class="dot" style="background:var(--border-strong)"></span>待处理</span>',
        '</div></div></div>',
    ])

    # -- Source Performance --
    parts.extend([
        '<div class="viz-panel">',
        '<h3>数据来源效能</h3>',
        '<div class="source-viz">',
    ])
    for src, count in source_data:
        width = (count / max_source * 100) if max_source else 0
        parts.append(
            '<div class="source-row">'
            f'<div class="source-name">{_esc(src)}</div>'
            '<div class="source-track">'
            f'<div class="source-bar" style="width:{width:.0f}%"></div>'
            '</div>'
            f'<div class="source-count">{count}</div>'
            '</div>'
        )
    parts.append('</div></div>')
    parts.append('</div>')  # close viz-grid

    # ========== STRATEGY ==========
    strategy = report["plan"].get("strategy_summary") or "未记录搜索策略。"
    parts.extend([
        '<div class="section-card">',
        '<div class="section-title">搜索策略</div>',
        f'<div class="strategy-text">{_esc(strategy)}</div>',
        '</div>',
    ])

    # ========== REVIEW PROCESS SUMMARY ==========
    # Compute evidence tier stats
    tier_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    total_ev_items = 0
    gate_passed = 0
    gate_failed = 0
    for c in candidates:
        for ev in c.get("evidence_details", []):
            tier_counts[ev.get("tier", 0)] = tier_counts.get(ev.get("tier", 0), 0) + 1
            total_ev_items += 1
        gs = c.get("gate_status", "unknown")
        if gs == "passed":
            gate_passed += 1
        elif gs == "failed":
            gate_failed += 1

    parts.extend([
        '<div class="section-card">',
        '<div class="section-title">审阅流程摘要</div>',
        '<div class="audit-stat-grid">',
        f'<div class="audit-stat"><div class="audit-stat-value">{len(candidates)}</div><div class="audit-stat-label">候选人总数</div></div>',
        f'<div class="audit-stat"><div class="audit-stat-value" style="color:var(--good)">{gate_passed}</div><div class="audit-stat-label">门槛通过</div></div>',
        f'<div class="audit-stat"><div class="audit-stat-value" style="color:var(--bad)">{gate_failed}</div><div class="audit-stat-label">门槛未过</div></div>',
        f'<div class="audit-stat"><div class="audit-stat-value">{total_ev_items}</div><div class="audit-stat-label">证据条目</div></div>',
        '</div>',
        '</div>',
    ])

    # ========== EVIDENCE QUALITY DASHBOARD ==========
    if total_ev_items > 0:
        parts.extend([
            '<div class="viz-grid">',
            '<div class="viz-panel">',
            '<h3>证据层级分布</h3>',
            '<div class="source-viz">',
        ])
        tier_labels = {1: "Tier 1 (Primary)", 2: "Tier 2 (Secondary)", 3: "Tier 3 (Indirect)", 4: "Tier 4 (Inferred)", 0: "Ungraded"}
        tier_colors = {1: "var(--good)", 2: "var(--accent)", 3: "var(--warn)", 4: "var(--caution)", 0: "var(--text-muted)"}
        for tier in [1, 2, 3, 4, 0]:
            count = tier_counts.get(tier, 0)
            width = (count / max(total_ev_items, 1) * 100)
            parts.append(
                '<div class="source-row">'
                f'<div class="source-name">{tier_labels.get(tier, f"Tier {tier}")}</div>'
                '<div class="source-track">'
                f'<div class="source-bar" style="width:{width:.0f}%;background:{tier_colors.get(tier, "var(--accent)")}"></div>'
                '</div>'
                f'<div class="source-count">{count}</div>'
                '</div>'
            )
        parts.append('</div></div>')
        # Gate status pie (CSS conic-gradient)
        total_gated = gate_passed + gate_failed
        if total_gated > 0:
            pass_pct = gate_passed / total_gated * 100
            fail_pct = gate_failed / total_gated * 100
            parts.extend([
                '<div class="viz-panel">',
                '<h3>门槛通过状态</h3>',
                '<div style="display:flex;align-items:center;gap:20px">',
                f'<div class="tier-pie" style="background:conic-gradient(var(--good) 0% {pass_pct:.0f}%, var(--bad) {pass_pct:.0f}% 100%)">'
                '<div class="tier-pie-label">通过率</div></div>',
                '<div style="font-size:12px">',
                f'<div style="color:var(--good);font-weight:700">通过: {gate_passed} ({pass_pct:.0f}%)</div>',
                f'<div style="color:var(--bad);font-weight:700;margin-top:4px">未过: {gate_failed} ({fail_pct:.0f}%)</div>',
                '</div>',
                '</div>',
                '</div>',
            ])
        parts.append('</div>')  # close viz-grid

    # ========== CANDIDATES ==========
    parts.extend([
        '<div class="section-card">',
        f'<div class="section-title">候选人评估详情（共 {len(candidates)} 位）</div>',
    ])
    if not candidates:
        parts.append(
            '<div class="empty-state">'
            '<div class="empty-icon">&#128269;</div>'
            "<p>本次运行暂未发现候选人。</p>"
            "</div>"
        )
    else:
        for idx, c in enumerate(candidates, 1):
            parts.append(_candidate_card(idx, c, role_type="default"))
    parts.append("</div>")

    # ========== FILTERED CANDIDATES ==========
    filtered = report.get("filtered_candidates", [])
    if filtered:
        parts.extend([
            '<div class="section-card">',
            f'<div class="section-title">已自动过滤的低质量数据（共 {len(filtered)} 条）</div>',
            '<p style="font-size:12px;color:var(--text-muted);margin-bottom:12px">'
            '以下条目因不符合人物识别标准而被自动排除。若数量过多，说明上游 Agent 未正确执行数据验证协议。'
            '</p>',
            '<table style="width:100%;font-size:12px">',
            '<thead><tr><th style="text-align:left;padding:6px;border-bottom:1px solid var(--border)">原始名称</th>'
            '<th style="text-align:left;padding:6px;border-bottom:1px solid var(--border)">过滤原因</th></tr></thead>',
            '<tbody>',
        ])
        for f in filtered[:30]:  # cap at 30 rows
            parts.append(
                '<tr>'
                f'<td style="padding:6px;border-bottom:1px solid var(--border);color:var(--text-secondary)">{_esc(f["name"] or "—")}</td>'
                f'<td style="padding:6px;border-bottom:1px solid var(--border);color:var(--bad)">{_esc(f["reason"])}</td>'
                '</tr>'
            )
        if len(filtered) > 30:
            parts.append(
                f'<tr><td colspan="2" style="padding:6px;color:var(--text-muted)">... 还有 {len(filtered) - 30} 条未显示</td></tr>'
            )
        parts.extend(['</tbody></table>', '</div>'])

    # ========== FOOTER ==========
    parts.extend([
        '<div class="report-footer">',
        '由 Oculai 多Agent智能人才 sourcing 系统生成 &middot; 仅供内部招聘参考',
        '</div>',
        "</div>",  # container
        "</body>",
        "</html>",
    ])

    return "\n".join(parts)


_DIM_LABELS = {
    "academic": "学术能力",
    "engineering": "工程能力",
    "leadership": "领导力",
    "communication": "沟通能力",
    "culture_fit": "文化匹配",
    "skill_match": "技能匹配",
    "location": "地点匹配",
    "career_stage": "职业阶段",
    "mobility": "流动意愿",
    "overall": "综合评分",
}


_STATUS_LABELS = {
    "shortlisted": ("已入围", "status-shortlisted"),
    "new": ("新增", "status-new"),
    "contacted": ("已联系", "status-contacted"),
}


def _candidate_card(idx: int, c: dict[str, Any], role_type: str = "default") -> str:
    """Render a single candidate card with donut chart and dim mini-bars."""
    score = c["overall_score"] or 0
    score_tier, dim_tier = _score_tier(score, role_type)
    rank_str = f"#{idx}"
    top_class = " top-pick" if idx <= 3 else ""

    # Donut chart: circumference for r=40 is ~251.327
    circumference = 251.327
    dash_offset = circumference * (1 - min(score, 100) / 100)

    status_label, status_class = _STATUS_LABELS.get(
        c["status"], ("评估中", "status-default")
    )

    # Gate status
    gate_status = c.get("gate_status", "unknown")
    gate_class = "gate-passed" if gate_status == "passed" else "gate-failed" if gate_status == "failed" else ""
    gate_text = "门槛通过" if gate_status == "passed" else "门槛未过" if gate_status == "failed" else ""

    # Audit badge
    audit_flags = c.get("audit_flags", [])
    audit_count = len(audit_flags)

    lines = [
        f'<div class="candidate-card{top_class}">',
        # -- Rank bar --
        f'<div class="candidate-rank-bar">{rank_str}</div>',
        # -- Main content --
        '<div class="candidate-main">',
        '<div class="candidate-header">',
        '<div class="candidate-name-group">',
        f"<h3>{_esc(c['name'] or '未知')}</h3>",
        f"<div class='institution'>{_esc(c['institution'] or '—')}</div>",
        f"<div class='position'>{_esc(c['position'] or '')}</div>" if c.get("position") else "",
        "</div>",
        '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">',
        f"<span class='status-tag {status_class}'>{status_label}</span>",
        f"<span class='gate-status {gate_class}'>{gate_text}</span>" if gate_text else "",
        f'<span class="audit-badge">{audit_count} 项审计发现</span>' if audit_count > 0 else "",
        "</div>",
        "</div>",
    ]

    # -- Metrics row --
    h = c["h_index"] or 0
    citations = c["total_citations"] or 0
    papers = c["total_papers"] or 0
    evidence = c.get("evidence_count", 0)

    lines.append('<div class="metrics-row">')
    lines.append(f'<div class="metric-item"><span class="m-val">{_fmt_num(h)}</span><span class="m-lbl">H-Index</span></div>')
    lines.append(f'<div class="metric-item"><span class="m-val">{_fmt_num(citations)}</span><span class="m-lbl">被引次数</span></div>')
    lines.append(f'<div class="metric-item"><span class="m-val">{_fmt_num(papers)}</span><span class="m-lbl">论文数</span></div>')
    lines.append(f'<div class="metric-item"><span class="m-val">{evidence}</span><span class="m-lbl">证据条</span></div>')
    lines.append("</div>")

    # -- Dimension mini-bars --
    dims = c.get("dimension_scores") or {}
    if dims:
        lines.append('<div class="dim-grid">')
        sorted_dims = sorted(
            dims.items(),
            key=lambda x: (0 if x[0] == "overall" else 1, x[0]),
        )
        for dim, s in sorted_dims:
            sc = s["score"] or 0
            conf = s.get("confidence", 0.0)
            _, fill_tier = _score_tier(sc, role_type)
            dim_name = _DIM_LABELS.get(dim, dim)
            dim_fill_class = f"dim-fill-{fill_tier.replace('bar-', '')}"
            conf_note = f"（置信度 {conf:.0%}）" if conf < 0.6 else ""
            lines.append(
                '<div class="dim-item">'
                '<div class="dim-item-header">'
                f'<span class="dim-name">{_esc(dim_name)}{conf_note}</span>'
                f'<span class="dim-score" style="color:var(--{fill_tier.replace('bar-', '')})">{sc:.1f}</span>'
                '</div>'
                '<div class="dim-track">'
                f'<div class="dim-fill {dim_fill_class}" style="width:{min(sc*10,100):.0f}%"></div>'
                '</div>'
                '</div>'
            )
        lines.append("</div>")

    # -- Evidence detail panel (CSS-only expand) --
    ev_details = c.get("evidence_details", [])
    if ev_details:
        toggle_id = f"ev-toggle-{idx}"
        lines.append('<div class="evidence-panel">')
        lines.append(f'<input type="checkbox" id="{toggle_id}" class="evidence-toggle"/>')
        lines.append(f'<label for="{toggle_id}" class="evidence-label">证据详情 ({len(ev_details)})</label>')
        lines.append('<div class="evidence-details">')
        for ev in ev_details[:5]:  # top 5
            tier = ev.get("tier", 0)
            tier_class = f"tier-{tier}"
            tier_label = {1: "T1", 2: "T2", 3: "T3", 4: "T4", 0: "T?"}.get(tier, "T?")
            flags = ev.get("quality_flags", [])
            flags_text = f" [{', '.join(flags)}]" if flags else ""
            lines.append(
                '<div class="evidence-item">'
                f'<span class="evidence-tier {tier_class}">{tier_label}</span>'
                f'<span class="evidence-source">{_esc(ev.get("source_name", "?"))}</span>'
                f'<span class="evidence-title">{_esc(ev.get("title", "—"))}</span>'
                f'<span class="evidence-confidence">{ev.get("confidence", 1.0):.0%}</span>'
                f'<span class="evidence-flags">{_esc(flags_text)}</span>'
                '</div>'
            )
        if len(ev_details) > 5:
            lines.append(f'<div style="font-size:10px;color:var(--text-muted);padding:4px 0">... 还有 {len(ev_details) - 5} 条</div>')
        lines.append('</div>')  # close evidence-details
        lines.append('</div>')  # close evidence-panel

    # -- Score history sparkline --
    score_history = c.get("score_history", [])
    if score_history:
        history_str = " → ".join([f"{h['score']:.1f}" for h in score_history])
        lines.append(f'<div class="score-history">评分轨迹: {history_str}</div>')

    # -- Footer: evidence pill + IDs --
    if evidence >= 10:
        ev_class = "evidence-good"
    elif evidence >= 5:
        ev_class = "evidence-ok"
    else:
        ev_class = "evidence-low"

    lines.append('<div class="candidate-footer">')
    lines.append(f'<span class="evidence-pill {ev_class}">{evidence} 条证据</span>')

    ext = c.get("external_ids") or {}
    active_ids = [
        ("ORCID", ext.get("orcid")),
        ("Scholar", ext.get("google_scholar")),
        ("GitHub", ext.get("github")),
        ("LinkedIn", ext.get("linkedin")),
    ]
    active_ids = [(k, v) for k, v in active_ids if v]
    if active_ids:
        lines.append('<div class="id-pills">')
        for id_type, id_val in active_ids:
            lines.append(
                f'<span class="id-pill"><span class="id-key">{id_type}</span> {_esc(id_val)}</span>'
            )
        lines.append("</div>")

    lines.append("</div>")  # close candidate-footer
    lines.append("</div>")  # close candidate-main

    # -- Right: Donut chart --
    lines.append(f'<div class="candidate-right">')
    lines.append(f'<div class="donut-chart donut-{score_tier.replace('score-', '')}">')
    lines.append('<svg viewBox="0 0 100 100" width="90" height="90">')
    lines.append('<circle class="donut-bg" cx="50" cy="50" r="40"/>')
    lines.append(
        f'<circle class="donut-fill" cx="50" cy="50" r="40" '
        f'stroke-dasharray="{circumference}" stroke-dashoffset="{dash_offset:.1f}"/>'
    )
    lines.append('</svg>')
    lines.append('<div class="donut-text">')
    lines.append(f'<div class="donut-value">{score:.0f}</div>')
    lines.append('<div class="donut-label">综合评分</div>')
    lines.append('</div>')
    lines.append('</div>')
    lines.append('</div>')  # close candidate-right

    lines.append("</div>")  # close candidate-card
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_reason(candidate: dict[str, Any]) -> str | None:
    """Return a reason string if this candidate should be filtered from the report.

    Last-line-of-defense filtering to hide garbage that somehow made it
    through the pipeline.  The real fix is upstream (agent + validation),
    but this prevents embarrassing reports.
    """
    name = (candidate.get("name") or "").strip()

    # Placeholder / enrichment marker
    if name.startswith("[") and "NEEDS" in name:
        return "placeholder name — source returned unenriched web page"

    # Article title markers
    if any(c in name for c in ":：") and len(name) > 15:
        return "article title (contains colon / long text)"
    if any(c in name for c in "《》「」"):
        return "article title (contains Chinese quote marks)"

    # Job posting markers
    if any(kw in name for kw in ("招聘", "实习", "职位", "年薪", "待遇", "薪资")):
        return "job posting content"

    # Numeric ID
    import re as _re
    if _re.match(r"^\d+$", name) or _re.match(r"^\d{4,}_\d+", name):
        return "numeric ID, not a person name"

    # All lowercase (probably a username without real name)
    alpha = [c for c in name if c.isalpha()]
    if alpha and all(c.islower() for c in alpha) and len(name) <= 10:
        return "all-lowercase username without real name"

    # Zero signal candidates (no evidence, no score, no external IDs)
    ev = candidate.get("evidence_count", 0)
    score = candidate.get("overall_score") or 0
    ext = candidate.get("external_ids") or {}
    has_ext = any(ext.values())
    if ev == 0 and score == 0 and not has_ext and not candidate.get("institution"):
        return "zero evidence, zero score, no identifiers"

    return None


def _score_tier(score: float, role_type: str = "default") -> tuple[str, str]:
    """Return (ring_class, bar_class) for a 0-100 overall or 0-10 dimension.

    Uses role-type-calibrated thresholds.
    """
    thresholds = {
        "research_scientist": {"excellent": 80, "good": 65, "fair": 50},
        "engineer": {"excellent": 82, "good": 68, "fair": 52},
        "ml_engineer": {"excellent": 82, "good": 68, "fair": 52},
        "tech_lead": {"excellent": 80, "good": 65, "fair": 50},
        "product_manager": {"excellent": 78, "good": 62, "fair": 48},
        "data_scientist": {"excellent": 80, "good": 65, "fair": 50},
        "default": {"excellent": 80, "good": 65, "fair": 50},
    }
    t = thresholds.get(role_type, thresholds["default"])
    if score >= t["excellent"]:
        return ("score-good", "bar-good")
    elif score >= t["good"]:
        return ("score-warn", "bar-warn")
    elif score >= t["fair"]:
        return ("score-caution", "bar-caution")
    else:
        return ("score-bad", "bar-bad")


def _esc(s: str) -> str:
    """Minimal HTML escape."""
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#39;")
    )


def _fmt_num(n: int) -> str:
    """Format large numbers compactly."""
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
