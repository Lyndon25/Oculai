"""Report export — HTML and Markdown report generation."""

from typing import Any
from uuid import UUID

from oculai_mcp.db.client import fetch_with_retry, fetchrow_with_retry


async def export_report(run_id: UUID, format: str = "markdown") -> dict[str, Any]:
    """Export a sourcing run report.

    Args:
        run_id: The run UUID
        format: "markdown" or "html"
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


def _render_html(report: dict[str, Any]) -> str:
    """Render report as basic HTML."""
    md = _render_markdown(report)
    # Basic markdown → HTML conversion for common elements
    html = md
    html = f"<html><body><pre>{html}</pre></body></html>"
    return html
