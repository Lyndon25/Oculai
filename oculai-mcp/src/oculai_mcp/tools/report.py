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

    # Build report
    candidate_list = []
    for c in candidates:
        assessments = await fetch_with_retry(
            "SELECT dimension, score, confidence, rationale FROM candidateassessment WHERE run_id = $1 AND person_id = $2",
            run_id, c["person_id"],
        )
        evidence_count = await fetchrow_with_retry(
            "SELECT COUNT(*) as cnt FROM evidence WHERE person_id = $1", c["person_id"],
        )

        candidate_list.append({
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
            "evidence_count": evidence_count["cnt"] if evidence_count else 0,
        })

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
        "shortlist_cutoff": None,
    }

    if format == "markdown":
        report["markdown"] = _render_markdown(report)
    elif format == "html":
        report["html"] = _render_html(report)

    return report


def _render_markdown(report: dict[str, Any]) -> str:
    """Render report as Markdown."""
    r = report["run"]
    lines = [
        f"# {r['title']}",
        f"",
        f"**Status**: {r['status']} | **Created**: {r['created_at']}",
        f"",
        f"## Strategy",
        f"",
        f"{report['plan'].get('strategy_summary', 'No strategy recorded.')}",
        f"",
        f"## Task Summary",
        f"",
    ]
    for t in report["task_summary"]:
        lines.append(f"- {t['task_type']}: {t['cnt']} ({t['status']})")

    lines.extend(["", "## Candidates", ""])
    for i, c in enumerate(report["candidates"], 1):
        lines.extend([
            f"### {i}. {c['name']} — Score: {c['overall_score']}/100",
            f"",
            f"- **Institution**: {c['institution'] or 'N/A'}",
            f"- **h-index**: {c['h_index']} | **Citations**: {c['total_citations']} | **Papers**: {c['total_papers']}",
            f"- **Status**: {c['status']} | **Evidence items**: {c['evidence_count']}",
        ])
        if c["dimension_scores"]:
            lines.append("- **Scores**:")
            for dim, s in c["dimension_scores"].items():
                lines.append(f"  - {dim}: {s['score']}/10 (confidence: {s['confidence']})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML report — polished, self-contained, print-ready
# ---------------------------------------------------------------------------

_CSS = r"""
:root {
    --bg: #f5f6fa;
    --card-bg: #ffffff;
    --text: #1a1a2e;
    --text-secondary: #6b7280;
    --border: #e5e7eb;
    --accent: #4f46e5;
    --accent-light: #eef2ff;
    --green: #10b981;
    --green-bg: #ecfdf5;
    --yellow: #f59e0b;
    --yellow-bg: #fffbeb;
    --orange: #f97316;
    --orange-bg: #fff7ed;
    --red: #ef4444;
    --red-bg: #fef2f2;
    --radius: 10px;
    --shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
    --shadow-md: 0 4px 12px rgba(0,0,0,.06);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, "Noto Sans SC", "PingFang SC",
                 "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
}

.container { max-width: 1100px; margin: 0 auto; padding: 32px 24px 64px; }

/* ---- Header ---- */
.header {
    background: linear-gradient(135deg, #312e81 0%, #4f46e5 50%, #7c3aed 100%);
    color: #fff;
    padding: 40px 48px;
    border-radius: var(--radius);
    margin-bottom: 28px;
    box-shadow: var(--shadow-md);
}
.header h1 { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }
.header .meta {
    display: flex; gap: 24px; margin-top: 12px;
    font-size: 14px; opacity: 0.85; flex-wrap: wrap;
}
.header .meta span { display: flex; align-items: center; gap: 6px; }
.header .badge {
    display: inline-block; padding: 3px 12px; border-radius: 99px;
    font-size: 12px; font-weight: 600; letter-spacing: 0.3px;
    text-transform: uppercase;
}
.badge-active { background: rgba(255,255,255,.2); color: #fff; }
.badge-done   { background: var(--green); color: #fff; }
.badge-draft  { background: rgba(255,255,255,.15); color: #fff; }

/* ---- Section cards ---- */
.section {
    background: var(--card-bg);
    border-radius: var(--radius);
    padding: 28px 32px;
    margin-bottom: 20px;
    box-shadow: var(--shadow);
    border: 1px solid var(--border);
}
.section h2 {
    font-size: 18px; font-weight: 700; margin-bottom: 14px;
    display: flex; align-items: center; gap: 8px;
    letter-spacing: -0.3px;
}
.section h2 .icon { font-size: 20px; }

/* ---- Dashboard grid ---- */
.dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 20px; }
.stat-card {
    background: var(--card-bg); border-radius: var(--radius);
    padding: 20px 24px; text-align: center;
    box-shadow: var(--shadow); border: 1px solid var(--border);
}
.stat-card .value { font-size: 32px; font-weight: 800; letter-spacing: -1px; }
.stat-card .label { font-size: 13px; color: var(--text-secondary); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.stat-card.accent .value { color: var(--accent); }
.stat-card.green .value { color: var(--green); }
.stat-card.orange .value { color: var(--orange); }

/* ---- Task summary ---- */
.task-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
.task-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 14px; background: var(--bg); border-radius: 6px;
    font-size: 14px;
}
.task-item .task-type { font-weight: 500; }
.task-item .task-cnt  { font-size: 13px; color: var(--text-secondary); }

/* ---- Candidate card ---- */
.candidate-card {
    background: var(--card-bg); border-radius: var(--radius);
    padding: 28px 32px; margin-bottom: 20px;
    box-shadow: var(--shadow); border: 1px solid var(--border);
    position: relative; overflow: hidden;
}
.candidate-card.top-pick { border-left: 4px solid var(--accent); }

.candidate-header {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 20px; flex-wrap: wrap;
}
.candidate-header .rank {
    font-size: 13px; font-weight: 600; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.5px;
}
.candidate-header h3 { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
.candidate-header .institution { font-size: 14px; color: var(--text-secondary); margin-top: 2px; }
.candidate-header .position  { font-size: 13px; color: var(--accent); font-weight: 500; margin-top: 2px; }

.overall-score {
    display: flex; flex-direction: column; align-items: center;
    min-width: 72px;
}
.overall-score .score-ring {
    width: 64px; height: 64px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; font-weight: 800;
    border: 3px solid;
}
.overall-score .score-label { font-size: 11px; color: var(--text-secondary); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }

/* Score ring colors */
.score-high   { background: var(--green-bg); color: #065f46; border-color: var(--green) !important; }
.score-mid    { background: var(--yellow-bg); color: #92400e; border-color: var(--yellow) !important; }
.score-low    { background: var(--orange-bg); color: #9a3412; border-color: var(--orange) !important; }
.score-poor   { background: var(--red-bg); color: #991b1b; border-color: var(--red) !important; }

/* ---- Score bars ---- */
.score-bars { margin-top: 20px; }
.score-bar {
    display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
}
.score-bar .dim-label {
    width: 120px; font-size: 13px; font-weight: 500;
    text-align: right; flex-shrink: 0;
    text-transform: capitalize;
}
.score-bar .bar-track {
    flex: 1; height: 8px; background: var(--bg); border-radius: 99px;
    position: relative; overflow: hidden;
}
.score-bar .bar-fill {
    height: 100%; border-radius: 99px;
    transition: width 0.4s ease;
}
.score-bar .bar-val {
    width: 48px; text-align: right; font-size: 13px;
    font-weight: 700; font-variant-numeric: tabular-nums;
}

/* Bar colors (mapped per tier) */
.bar-high  { background: var(--green); }
.bar-mid   { background: var(--yellow); }
.bar-low   { background: var(--orange); }
.bar-poor  { background: var(--red); }

/* ---- Metrics row ---- */
.metrics-row {
    display: flex; gap: 20px; margin-top: 18px; flex-wrap: wrap;
}
.metric {
    display: flex; flex-direction: column; align-items: center;
    padding: 10px 18px; background: var(--bg); border-radius: 8px;
    min-width: 80px;
}
.metric .val { font-size: 18px; font-weight: 700; }
.metric .lbl { font-size: 11px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.3px; }

/* ---- Evidence badge ---- */
.evidence-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; border-radius: 99px; font-size: 12px;
    font-weight: 600; margin-top: 14px;
}
.evidence-good { background: var(--green-bg); color: #065f46; }
.evidence-ok   { background: var(--yellow-bg); color: #92400e; }
.evidence-low  { background: var(--red-bg); color: #991b1b; }

/* ---- IDs row ---- */
.ids-row {
    display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap;
}
.id-tag {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 10px; border-radius: 99px;
    font-size: 11px; background: var(--accent-light);
    color: var(--accent); font-weight: 500;
}
.id-tag .id-type { opacity: 0.7; }

/* ---- Empty state ---- */
.empty-state {
    text-align: center; padding: 48px 24px; color: var(--text-secondary);
}
.empty-state .empty-icon { font-size: 40px; margin-bottom: 12px; }

/* ---- Footer ---- */
.footer {
    text-align: center; padding: 24px; color: var(--text-secondary);
    font-size: 12px;
}

/* ---- Print ---- */
@media print {
    :root { --bg: #fff; }
    body { font-size: 12px; }
    .container { max-width: 100%; padding: 16px; }
    .header { background: #312e81 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .candidate-card, .section, .stat-card {
        box-shadow: none; break-inside: avoid; border: 1px solid #ddd;
    }
    .score-bars { break-inside: avoid; }
}
"""


def _render_html(report: dict[str, Any]) -> str:
    """Render a polished, self-contained HTML report."""
    r = report["run"]
    candidates = report["candidates"]

    # -- Header --
    status_class = {"completed": "badge-done", "active": "badge-active"}.get(
        r["status"], "badge-draft"
    )
    status_text = (r["status"] or "unknown").upper()

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>Oculai — {_esc(r['title'])}</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        '<div class="container">',
        # --- Header ---
        '<div class="header">',
        f"<h1>{_esc(r['title'])}</h1>",
        '<div class="meta">',
        f"<span class='badge {status_class}'>{_esc(status_text)}</span>",
        f"<span>&#128197; {_esc(r['created_at'])}</span>",
        f"<span>&#127919; {_esc(r.get('target_profile') or '—')}</span>",
        "</div>",
        "</div>",
    ]

    # -- Dashboard --
    shortlisted = sum(1 for c in candidates if c["status"] == "shortlisted")
    avg_score = (
        sum(c["overall_score"] or 0 for c in candidates) / len(candidates)
        if candidates else 0
    )

    parts.extend([
        '<div class="dashboard">',
        f"<div class='stat-card accent'><div class='value'>{len(candidates)}</div><div class='label'>Candidates</div></div>",
        f"<div class='stat-card green'><div class='value'>{shortlisted}</div><div class='label'>Shortlisted</div></div>",
        f"<div class='stat-card accent'><div class='value'>{avg_score:.0f}</div><div class='label'>Avg Score</div></div>",
        f"<div class='stat-card orange'><div class='value'>{sum(t['cnt'] for t in report['task_summary'])}</div><div class='label'>Tasks</div></div>",
        "</div>",
    ])

    # -- Strategy --
    strategy = report["plan"].get("strategy_summary") or "No strategy recorded."
    parts.extend([
        '<div class="section">',
        '<h2><span class="icon">&#128161;</span> Strategy</h2>',
        f"<p style='font-size:14px;line-height:1.7;'>{_esc(strategy)}</p>",
        "</div>",
    ])

    # -- Task Summary --
    if report["task_summary"]:
        parts.append('<div class="section">')
        parts.append('<h2><span class="icon">&#128203;</span> Task Summary</h2>')
        parts.append('<div class="task-grid">')
        for t in report["task_summary"]:
            parts.append(
                '<div class="task-item">'
                f"<span class='task-type'>{_esc(t['task_type'])}</span>"
                f"<span class='task-cnt'>{t['cnt']} &#183; {_esc(t['status'])}</span>"
                "</div>"
            )
        parts.append("</div></div>")

    # -- Candidates --
    parts.append('<div class="section">')
    parts.append(f'<h2><span class="icon">&#128100;</span> Candidates ({len(candidates)})</h2>')

    if not candidates:
        parts.append(
            '<div class="empty-state">'
            '<div class="empty-icon">&#128269;</div>'
            "<p>No candidates found in this run.</p>"
            "</div>"
        )
    else:
        for idx, c in enumerate(candidates, 1):
            parts.append(_candidate_card(idx, c))

    parts.append("</div>")  # close section

    # -- Footer --
    parts.extend([
        '<div class="footer">',
        f"Generated by Oculai Agent-Native Talent Sourcing &middot; {_esc(r['created_at'])}",
        "</div>",
        "</div>",  # close container
        "</body>",
        "</html>",
    ])

    return "\n".join(parts)


def _candidate_card(idx: int, c: dict[str, Any]) -> str:
    """Render a single candidate card."""
    score = c["overall_score"] or 0
    score_tier, _ = _score_tier(score)
    rank_str = f"#{idx}"
    top_class = " top-pick" if idx <= 3 else ""

    lines = [
        f'<div class="candidate-card{top_class}">',
        '<div class="candidate-header">',
        "<div>",
        f"<div class='rank'>{rank_str}</div>",
        f"<h3>{_esc(c['name'] or 'Unknown')}</h3>",
        f"<div class='institution'>{_esc(c['institution'] or '—')}</div>",
        f"<div class='position'>{_esc(c['position'] or '')}</div>" if c.get("position") else "",
        "</div>",
        f"<div class='overall-score'><div class='score-ring {score_tier}'>{score:.0f}</div><div class='score-label'>Overall</div></div>",
        "</div>",
    ]

    # -- Metrics row --
    h = c["h_index"] or 0
    citations = c["total_citations"] or 0
    papers = c["total_papers"] or 0
    evidence = c.get("evidence_count", 0)

    lines.append('<div class="metrics-row">')
    lines.append(f"<div class='metric'><span class='val'>{_fmt_num(h)}</span><span class='lbl'>h-index</span></div>")
    lines.append(f"<div class='metric'><span class='val'>{_fmt_num(citations)}</span><span class='lbl'>Citations</span></div>")
    lines.append(f"<div class='metric'><span class='val'>{_fmt_num(papers)}</span><span class='lbl'>Papers</span></div>")
    lines.append("</div>")

    # -- Evidence badge --
    if evidence >= 10:
        ev_class = "evidence-good"
    elif evidence >= 5:
        ev_class = "evidence-ok"
    else:
        ev_class = "evidence-low"
    lines.append(
        f"<div class='evidence-badge {ev_class}'>&#128274; {evidence} evidence items</div>"
    )

    # -- Dimension scores --
    dims = c.get("dimension_scores") or {}
    if dims:
        lines.append('<div class="score-bars" style="margin-top:16px;">')
        # Sort: overall last, rest alphabetically
        sorted_dims = sorted(
            dims.items(),
            key=lambda x: (0 if x[0] == "overall" else 1, x[0]),
        )
        for dim, s in sorted_dims:
            sc = s["score"] or 0
            conf = s.get("confidence", 0.0)
            _, bar_class = _score_tier(sc)
            # Show confidence in the label when below 0.6
            conf_note = f" &#183; {conf:.0%}" if conf < 0.6 else ""
            lines.append(
                '<div class="score-bar">'
                f"<span class='dim-label' title='confidence: {conf:.0%}'>{_esc(dim)}{conf_note}</span>"
                f"<div class='bar-track'><div class='bar-fill {bar_class}' style='width:{sc * 10:.0f}%'></div></div>"
                f"<span class='bar-val'>{sc:.1f}</span>"
                "</div>"
            )
        lines.append("</div>")

    # -- External IDs --
    ext = c.get("external_ids") or {}
    active_ids = [
        ("ORCID", ext.get("orcid")),
        ("Scholar", ext.get("google_scholar")),
        ("GitHub", ext.get("github")),
        ("LinkedIn", ext.get("linkedin")),
    ]
    active_ids = [(k, v) for k, v in active_ids if v]
    if active_ids:
        lines.append('<div class="ids-row">')
        for id_type, id_val in active_ids:
            lines.append(
                f"<span class='id-tag'><span class='id-type'>{id_type}</span> {_esc(id_val)}</span>"
            )
        lines.append("</div>")

    lines.append("</div>")  # close candidate-card
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_tier(score: float) -> tuple[str, str]:
    """Return (ring_class, bar_class) for a 0-100 overall or 0-10 dimension."""
    if score >= 80:
        return ("score-high", "bar-high")
    elif score >= 50:
        return ("score-mid", "bar-mid")
    elif score >= 30:
        return ("score-low", "bar-low")
    else:
        return ("score-poor", "bar-poor")


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
