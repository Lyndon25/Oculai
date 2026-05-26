"""SourcingRun and CandidateRecord CRUD operations. (Adapted from Phase7 jobs/records)"""

import logging
from typing import Any
from uuid import UUID, uuid4

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry

logger = logging.getLogger(__name__)


async def create_run(
    title: str,
    target_profile: dict[str, Any],
    config: dict[str, Any] | None = None,
    target_keywords: list[str] | None = None,
    target_domains: list[str] | None = None,
    created_by: str = "claude-code",
) -> UUID:
    run_id = uuid4()
    config = config or {}
    await execute_with_retry(
        """
        INSERT INTO sourcingrun (run_id, title, status, target_profile, config, target_keywords, target_domains, created_by, created_by_agent, updated_by_agent)
        VALUES ($1, $2, 'draft', $3, $4, $5, $6, $7, $7, $7)
        """,
        run_id, title, target_profile, config, target_keywords or [], target_domains or [],
        created_by,
    )
    logger.info("Created run %s: %s", run_id, title)
    return run_id


async def get_run(run_id: UUID) -> dict[str, Any] | None:
    row = await fetchrow_with_retry("SELECT * FROM sourcingrun WHERE run_id = $1", run_id)
    return dict(row) if row else None


async def update_run_status(run_id: UUID, status: str) -> bool:
    result = await execute_with_retry(
        "UPDATE sourcingrun SET status = $2, updated_at = now(), updated_by_agent = 'oculai-mcp' WHERE run_id = $1",
        run_id, status,
    )
    updated = "UPDATE 1" in result
    if updated:
        logger.info("Updated run %s status to %s", run_id, status)
    return updated


async def update_run_result(run_id: UUID, result_summary: dict[str, Any]) -> None:
    await execute_with_retry(
        "UPDATE sourcingrun SET result_summary = $2, updated_at = now(), updated_by_agent = 'oculai-mcp' WHERE run_id = $1",
        run_id, result_summary,
    )


async def list_runs(status: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    if status:
        rows = await fetch_with_retry(
            "SELECT run_id, title, status, created_at, updated_at FROM sourcingrun WHERE status = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            status, limit, offset,
        )
    else:
        rows = await fetch_with_retry(
            "SELECT run_id, title, status, created_at, updated_at FROM sourcingrun ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
    return [dict(row) for row in rows]


async def create_candidate_record(run_id: UUID, person_id: UUID, raw_data: dict[str, Any] | None = None, created_by_agent: str = "oculai-mcp") -> UUID | None:
    record_id = uuid4()
    raw_data = raw_data or {}
    result = await fetchrow_with_retry(
        """INSERT INTO candidaterecord (record_id, run_id, person_id, raw_data, created_by_agent, updated_by_agent)
           VALUES ($1, $2, $3, $4, $5, $5) ON CONFLICT (run_id, person_id) DO NOTHING RETURNING record_id""",
        record_id, run_id, person_id, raw_data, created_by_agent,
    )
    if result is None:
        existing = await fetchrow_with_retry(
            "SELECT record_id FROM candidaterecord WHERE run_id = $1 AND person_id = $2",
            run_id, person_id,
        )
        if existing:
            return existing["record_id"]
        return None
    logger.info("Created CandidateRecord %s for run=%s person=%s", record_id, run_id, person_id)
    return record_id


async def get_candidate_records(run_id: UUID, status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    if status:
        rows = await fetch_with_retry(
            "SELECT * FROM candidaterecord WHERE run_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT $3 OFFSET $4",
            run_id, status, limit, offset,
        )
    else:
        rows = await fetch_with_retry(
            "SELECT * FROM candidaterecord WHERE run_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            run_id, limit, offset,
        )
    return [dict(row) for row in rows]


async def update_candidate_record(
    record_id: UUID, agent_id: str,
    raw_data: dict[str, Any] | None = None,
    enriched_data: dict[str, Any] | None = None,
    match_scores: dict[str, Any] | None = None,
    quality_score: int | None = None,
    status: str | None = None,
) -> bool:
    updates = []
    values = [record_id]
    idx = 2

    if raw_data is not None:
        updates.append(f"raw_data = ${idx}"); values.append(raw_data); idx += 1
    if enriched_data is not None:
        updates.append(f"enriched_data = ${idx}"); values.append(enriched_data); idx += 1
    if match_scores is not None:
        updates.append(f"match_scores = ${idx}"); values.append(match_scores); idx += 1
    if quality_score is not None:
        updates.append(f"quality_score = ${idx}"); values.append(quality_score); idx += 1
    if status is not None:
        updates.append(f"status = ${idx}"); values.append(status); idx += 1

    if not updates:
        return False

    updates.extend(["updated_at = now()", f"updated_by_agent = ${idx}"])
    values.append(agent_id)

    query = f"UPDATE candidaterecord SET {', '.join(updates)} WHERE record_id = $1"
    result = await execute_with_retry(query, *values)
    return "UPDATE 1" in result


async def get_run_state_summary(run_id: UUID) -> dict[str, Any]:
    """Get a summary of run state: plan, tasks, candidates."""
    run = await get_run(run_id)
    if not run:
        return {"error": "run not found"}

    plan = None
    if run.get("active_plan_id"):
        plan = await fetchrow_with_retry("SELECT * FROM plan WHERE plan_id = $1", run["active_plan_id"])
        plan = dict(plan) if plan else None

    task_stats = await fetch_with_retry(
        "SELECT task_type, status, COUNT(*) as cnt FROM task WHERE run_id = $1 GROUP BY task_type, status",
        run_id,
    )

    candidate_count = await fetchrow_with_retry(
        "SELECT COUNT(*) as total FROM candidaterecord WHERE run_id = $1", run_id,
    )

    return {
        "run": run,
        "plan": plan,
        "task_stats": [dict(r) for r in task_stats],
        "candidate_count": candidate_count["total"] if candidate_count else 0,
    }
