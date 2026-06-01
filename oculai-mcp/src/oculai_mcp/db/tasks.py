"""DAG task queue operations. (Adapted from Phase7 for new schema)"""

import logging
import re
from typing import Any
from uuid import UUID

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry
from oculai_mcp.db.iterations import get_task_iterations

logger = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"^\$(\w[\w-]*)\.(\w+)$")


async def claim_task_batch(
    run_id: UUID,
    task_types: list[str],
    batch_size: int,
    agent_id: str,
    timeout_minutes: int = 10,
) -> list[dict[str, Any]]:
    """Claim a batch of ready tasks using FOR UPDATE SKIP LOCKED.

    If a task has retry_count > 0, its previous TaskIteration history is
    injected into the returned record under 'previous_iterations' so the
    new agent instance can resume from where the previous one left off.
    """
    rows = await fetch_with_retry(
        "SELECT * FROM claim_task_batch($1, $2, $3, $4, $5)",
        run_id, task_types, batch_size, agent_id, timeout_minutes,
    )
    result = [dict(row) for row in rows]

    # Resume enhancement: inject previous iteration history for retried tasks
    for task in result:
        if task.get("retry_count", 0) > 0:
            iterations = await get_task_iterations(task["task_id"])
            if iterations:
                task["previous_iterations"] = iterations
                task["resume_hint"] = (
                    f"This task was previously attempted {task['retry_count']} time(s). "
                    f"Review previous_iterations ({len(iterations)} steps) and continue "
                    f"from where it left off. Do NOT repeat searches already performed."
                )
                logger.info(
                    "Injected %d previous iterations into task=%s for resume by %s",
                    len(iterations), task["task_id"], agent_id,
                )

    if result:
        logger.info("Agent %s claimed %d tasks for run=%s", agent_id, len(result), run_id)
    return result


async def complete_task(task_id: UUID, agent_id: str, output_data: dict[str, Any]) -> None:
    await execute_with_retry("SELECT complete_task($1, $2, $3)", task_id, output_data, agent_id)
    logger.info("Agent %s completed task_id=%s", agent_id, task_id)


async def fail_task(task_id: UUID, error_msg: str, agent_id: str = "system") -> None:
    await execute_with_retry("SELECT fail_task($1, $2, $3)", task_id, error_msg, agent_id)
    logger.warning("Task %s failed: %s", task_id, error_msg)


async def release_stale_tasks() -> list[dict[str, Any]]:
    rows = await fetch_with_retry("SELECT * FROM release_stale_tasks()")
    result = [dict(row) for row in rows]
    if result:
        logger.warning("Released %d stale tasks", len(result))
    return result


async def create_task(
    plan_id: UUID,
    run_id: UUID,
    task_type: str,
    task_name: str,
    input_data: dict[str, Any],
    step_key: str | None = None,
    priority: int = 5,
    created_by_agent: str = "system",
    max_retries: int = 3,
) -> UUID:
    row = await fetchrow_with_retry(
        """
        INSERT INTO task (plan_id, run_id, task_type, task_name, step_key, priority,
                          input_data, max_retries, created_by_agent, updated_by_agent)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)
        RETURNING task_id
        """,
        plan_id, run_id, task_type, task_name, step_key, priority,
        input_data, max_retries, created_by_agent,
    )
    task_id = row["task_id"]
    logger.info("Created task %s: %s (%s)", task_id, task_name, task_type)
    return task_id


async def create_task_dependency(plan_id: UUID, task_id: UUID, depends_on_task_id: UUID, input_mapping: dict[str, Any] | None = None) -> None:
    await execute_with_retry(
        """
        INSERT INTO taskdependency (plan_id, task_id, depends_on_task_id, input_mapping)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (task_id, depends_on_task_id) DO NOTHING
        """,
        plan_id, task_id, depends_on_task_id, input_mapping or {},
    )


async def get_task(task_id: UUID) -> dict[str, Any] | None:
    row = await fetchrow_with_retry("SELECT * FROM task WHERE task_id = $1", task_id)
    return dict(row) if row else None


async def get_plan(plan_id: UUID) -> dict[str, Any] | None:
    row = await fetchrow_with_retry("SELECT * FROM plan WHERE plan_id = $1", plan_id)
    return dict(row) if row else None


async def create_plan(
    run_id: UUID,
    planner_state_json: dict[str, Any],
    strategy_summary: str = "",
    replan_triggers: list[str] | None = None,
    created_by_agent: str = "system",
) -> UUID:
    row = await fetchrow_with_retry(
        """INSERT INTO plan (run_id, planner_state_json, strategy_summary, replan_triggers, created_by_agent, updated_by_agent)
           VALUES ($1, $2, $3, $4, $5, $5) RETURNING plan_id""",
        run_id, planner_state_json, strategy_summary, replan_triggers or [],
        created_by_agent,
    )
    plan_id = row["plan_id"]
    logger.info("Created plan %s for run %s", plan_id, run_id)
    return plan_id


async def update_plan_status(plan_id: UUID, status: str) -> None:
    await execute_with_retry(
        "UPDATE plan SET status = $2, updated_at = now(), updated_by_agent = 'system' WHERE plan_id = $1",
        plan_id, status,
    )


async def update_run_active_plan(run_id: UUID, plan_id: UUID) -> None:
    await execute_with_retry(
        "UPDATE sourcingrun SET active_plan_id = $2, updated_at = now(), updated_by_agent = 'system' WHERE run_id = $1",
        run_id, plan_id,
    )


async def get_task_depths(plan_id: UUID) -> dict[str, dict[str, int]]:
    rows = await fetch_with_retry(
        "SELECT task_type, status, COUNT(*) as cnt FROM task WHERE plan_id = $1 GROUP BY task_type, status",
        plan_id,
    )
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        tt = str(row["task_type"])
        result.setdefault(tt, {})[row["status"]] = row["cnt"]
    return result
