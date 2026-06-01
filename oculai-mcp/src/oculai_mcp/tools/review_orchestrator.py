"""Multi-pass candidate review orchestrator.

Manages a state machine for the review pipeline:
  enrichment → initial_scoring → audit → adjustment → complete

The orchestrator does NOT directly invoke subagents. Instead, it:
1. Creates and tracks ReviewSession state in PostgreSQL
2. Manages which candidates are in which pass
3. Records timing and findings
4. Applies auditor-recommended adjustments with history tracking

The main Agent reads progress via oculai_get_review_progress and decides
when to launch Profile Enricher / Fit Evaluator / Quality Auditor subagents.
"""

from typing import Any
from uuid import UUID, uuid4

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry


async def create_review_session(
    run_id: UUID,
    role_type: str,
    candidate_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """Create a review session for a run.

    If candidate_ids is None, all candidates in the run are included.
    """
    if candidate_ids is None:
        rows = await fetch_with_retry(
            "SELECT person_id FROM candidaterecord WHERE run_id = $1",
            run_id,
        )
        candidate_ids = [r["person_id"] for r in rows]

    if not candidate_ids:
        return {"status": "error", "reason": "No candidates found for review", "session_id": None}

    row = await fetchrow_with_retry(
        """
        INSERT INTO reviewsession (run_id, role_type, target_candidate_ids, current_pass, status)
        VALUES ($1, $2, $3, 'enrichment', 'active')
        RETURNING session_id
        """,
        run_id, role_type, candidate_ids,
    )
    session_id = row["session_id"] if row else None

    return {
        "session_id": str(session_id) if session_id else None,
        "run_id": str(run_id),
        "role_type": role_type,
        "total_candidates": len(candidate_ids),
        "target_candidate_ids": [str(c) for c in candidate_ids],
        "current_pass": "enrichment",
        "status": "active",
    }


async def execute_review_pass(
    session_id: UUID,
    pass_type: str,
    completed_candidate_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """Execute (advance) a single review pass.

    Args:
        session_id: Review session UUID
        pass_type: One of enrichment, initial_scoring, audit, adjustment, complete
        completed_candidate_ids: Candidates that finished this pass (for enrichment/initial_scoring/adjustment)

    Returns updated progress.
    """
    session = await fetchrow_with_retry(
        "SELECT * FROM reviewsession WHERE session_id = $1",
        session_id,
    )
    if not session:
        return {"status": "error", "reason": "Review session not found"}

    if session["status"] not in ("active", "paused"):
        return {"status": "error", "reason": f"Session is {session['status']}"}

    # Update timing for the *previous* pass
    pass_timings = session.get("pass_timings") or {}
    if isinstance(pass_timings, dict) and session["current_pass"] != pass_type:
        # If advancing to a new pass, record elapsed for previous
        import time
        now_ts = time.time()
        # We don't have start timestamps per pass; use a simple incremental approach
        # Store duration_seconds in pass_timings
        pass_timings[session["current_pass"]] = pass_timings.get(session["current_pass"], 0) + 1

    # Merge completed candidates
    existing_completed = set(session.get("completed_candidate_ids") or [])
    if completed_candidate_ids:
        existing_completed.update(completed_candidate_ids)

    # Determine next pass automatically if all candidates are done
    target_ids = set(session.get("target_candidate_ids") or [])
    all_done = target_ids.issubset(existing_completed)

    next_pass = pass_type
    if all_done and pass_type != "complete":
        next_pass = _next_pass(pass_type)
        existing_completed = set()  # reset for next pass

    await execute_with_retry(
        """
        UPDATE reviewsession
        SET current_pass = $2,
            completed_candidate_ids = $3,
            pass_timings = $4,
            updated_at = now()
        WHERE session_id = $1
        """,
        session_id, next_pass, list(existing_completed), pass_timings,
    )

    return await get_review_progress(session_id)


async def get_review_progress(session_id: UUID) -> dict[str, Any]:
    """Get current progress: which pass, which candidates done, timing."""
    session = await fetchrow_with_retry(
        """
        SELECT session_id, run_id, status, current_pass, role_type,
               target_candidate_ids, completed_candidate_ids, failed_candidate_ids,
               audit_findings, pass_timings, created_at, completed_at
        FROM reviewsession
        WHERE session_id = $1
        """,
        session_id,
    )
    if not session:
        return {"status": "error", "reason": "Review session not found"}

    target = set(session.get("target_candidate_ids") or [])
    completed = set(session.get("completed_candidate_ids") or [])
    failed = set(session.get("failed_candidate_ids") or [])
    pending = target - completed - failed

    # Per-candidate status summary
    candidate_status = []
    for cid in target:
        if cid in completed:
            status = "completed"
        elif cid in failed:
            status = "failed"
        else:
            status = "pending"
        candidate_status.append({"person_id": str(cid), "status": status})

    return {
        "session_id": str(session_id),
        "run_id": str(session["run_id"]),
        "status": session["status"],
        "current_pass": session["current_pass"],
        "role_type": session["role_type"],
        "total_candidates": len(target),
        "completed_count": len(completed),
        "pending_count": len(pending),
        "failed_count": len(failed),
        "pending_candidate_ids": [str(c) for c in pending],
        "completed_candidate_ids": [str(c) for c in completed],
        "candidate_status": candidate_status,
        "audit_findings": session.get("audit_findings") or {},
        "pass_timings": session.get("pass_timings") or {},
    }


async def apply_audit_adjustments(
    session_id: UUID,
    adjustments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply auditor-recommended score adjustments with history tracking.

    Each adjustment dict:
    {
        "person_id": "uuid",
        "dimension": "academic",
        "new_score": 7.5,
        "reason": "Auditor found additional evidence from zhihu",
        "assessor_agent": "quality_auditor",
    }
    """
    from oculai_mcp.tools import assessment as assessment_tool

    session = await fetchrow_with_retry(
        "SELECT run_id, role_type FROM reviewsession WHERE session_id = $1",
        session_id,
    )
    if not session:
        return {"status": "error", "reason": "Review session not found"}

    run_id = session["run_id"]
    role_type = session["role_type"]
    applied = []
    errors = []

    for adj in adjustments:
        try:
            person_id = UUID(adj["person_id"])
            dimension = adj["dimension"]
            new_score = float(adj["new_score"])
            reason = adj.get("reason", "Audit adjustment")
            agent = adj.get("assessor_agent", "quality_auditor")

            result = await assessment_tool.record_assessment(
                run_id=run_id,
                person_id=person_id,
                assessor_agent=agent,
                dimension=dimension,
                score=new_score,
                confidence=adj.get("confidence", 0.9),
                rationale=reason,
                evidence_ids=adj.get("evidence_ids"),
                role_type=role_type,
            )
            applied.append({
                "person_id": str(person_id),
                "dimension": dimension,
                "new_score": new_score,
                "overall_score": result.get("overall_score"),
            })
        except Exception as e:
            errors.append({"adjustment": adj, "error": str(e)})

    # Store findings in session
    current_findings = await fetchrow_with_retry(
        "SELECT audit_findings FROM reviewsession WHERE session_id = $1", session_id
    )
    findings = (current_findings.get("audit_findings") or {}) if current_findings else {}
    if isinstance(findings, dict):
        findings["adjustments_applied"] = findings.get("adjustments_applied", 0) + len(applied)
        findings["adjustment_errors"] = findings.get("adjustment_errors", 0) + len(errors)

    await execute_with_retry(
        "UPDATE reviewsession SET audit_findings = $2, updated_at = now() WHERE session_id = $1",
        session_id, findings,
    )

    return {
        "session_id": str(session_id),
        "applied": len(applied),
        "errors": len(errors),
        "adjustments": applied,
        "error_details": errors,
    }


async def finalize_review_session(session_id: UUID) -> dict[str, Any]:
    """Mark session complete, compute final rankings, return summary."""
    session = await fetchrow_with_retry(
        "SELECT run_id, role_type FROM reviewsession WHERE session_id = $1",
        session_id,
    )
    if not session:
        return {"status": "error", "reason": "Review session not found"}

    run_id = session["run_id"]

    # Compute aggregate stats
    stats = await fetchrow_with_retry(
        """
        SELECT
            COUNT(*) as total_candidates,
            AVG(quality_score) as avg_score,
            MAX(quality_score) as max_score,
            MIN(quality_score) as min_score,
            COUNT(*) FILTER (WHERE quality_score >= 80) as excellent_count,
            COUNT(*) FILTER (WHERE quality_score >= 50 AND quality_score < 80) as good_count,
            COUNT(*) FILTER (WHERE quality_score < 50) as poor_count
        FROM candidaterecord
        WHERE run_id = $1
        """,
        run_id,
    )

    # Score distribution by dimension
    dim_stats = await fetch_with_retry(
        """
        SELECT dimension, AVG(score) as avg_dim_score, COUNT(*) as count
        FROM candidateassessment
        WHERE run_id = $1
        GROUP BY dimension
        """,
        run_id,
    )

    await execute_with_retry(
        """
        UPDATE reviewsession
        SET status = 'completed', current_pass = 'complete', completed_at = now(), updated_at = now()
        WHERE session_id = $1
        """,
        session_id,
    )

    return {
        "session_id": str(session_id),
        "status": "completed",
        "run_id": str(run_id),
        "summary": {
            "total_candidates": stats["total_candidates"] if stats else 0,
            "average_score": round(float(stats["avg_score"]) / 10.0, 1) if stats and stats["avg_score"] else 0.0,
            "max_score": float(stats["max_score"]) / 10.0 if stats and stats["max_score"] else 0.0,
            "min_score": float(stats["min_score"]) / 10.0 if stats and stats["min_score"] else 0.0,
            "excellent_count": stats["excellent_count"] if stats else 0,
            "good_count": stats["good_count"] if stats else 0,
            "poor_count": stats["poor_count"] if stats else 0,
        },
        "dimension_averages": {
            r["dimension"]: round(r["avg_dim_score"], 2) if r["avg_dim_score"] else 0.0
            for r in dim_stats
        },
    }


def _next_pass(current: str) -> str:
    """Determine the next pass in the pipeline."""
    order = ["enrichment", "initial_scoring", "audit", "adjustment", "complete"]
    try:
        idx = order.index(current)
        return order[min(idx + 1, len(order) - 1)]
    except ValueError:
        return "complete"
