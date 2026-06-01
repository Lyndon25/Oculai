"""TaskIteration CRUD — persist agent reasoning steps for resume and audit."""

import logging
from typing import Any
from uuid import UUID

from oculai_mcp.db.client import fetch_with_retry, fetchrow_with_retry, execute_with_retry

logger = logging.getLogger(__name__)


async def record_iteration(
    task_id: UUID,
    iteration_number: int,
    iteration_type: str,
    reasoning_text: str | None = None,
    action_taken: str | None = None,
    action_params: dict[str, Any] | None = None,
    observation_text: str | None = None,
    observation_data: dict[str, Any] | None = None,
    decision: str | None = None,
    decision_rationale: str | None = None,
) -> UUID:
    """Persist one step of an agent's ReAct loop.

    Args:
        task_id: The Task UUID this iteration belongs to
        iteration_number: Auto-incrementing step number within the task
        iteration_type: One of: think, search, observe, classify, detail, adjust, stop, gather, assess, reprioritize, initialize
        reasoning_text: Pre-action reasoning (for THINK steps)
        action_taken: Tool/action name (for SEARCH, DETAIL steps)
        action_params: JSON parameters passed to the action
        observation_text: Post-action analysis (for OBSERVE steps)
        observation_data: Structured observation metadata (signal_quality, result_type_distribution, etc.)
        decision: High-level decision (NARROW, PIVOT, DEEPEN, STOP, etc.)
        decision_rationale: Why this decision was made
    Returns:
        The iteration_id UUID
    """
    row = await fetchrow_with_retry(
        """
        INSERT INTO taskiteration (
            task_id, iteration_number, iteration_type,
            reasoning_text, action_taken, action_params,
            observation_text, observation_data, decision, decision_rationale
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (task_id, iteration_number) DO UPDATE SET
            iteration_type = EXCLUDED.iteration_type,
            reasoning_text = EXCLUDED.reasoning_text,
            action_taken = EXCLUDED.action_taken,
            action_params = EXCLUDED.action_params,
            observation_text = EXCLUDED.observation_text,
            observation_data = EXCLUDED.observation_data,
            decision = EXCLUDED.decision,
            decision_rationale = EXCLUDED.decision_rationale,
            created_at = now()
        RETURNING iteration_id
        """,
        task_id, iteration_number, iteration_type,
        reasoning_text, action_taken, action_params or {},
        observation_text, observation_data or {}, decision, decision_rationale,
    )
    iteration_id = row["iteration_id"]
    logger.debug("Recorded iteration %s for task=%s step=%s type=%s", iteration_id, task_id, iteration_number, iteration_type)
    return iteration_id


async def get_task_iterations(task_id: UUID) -> list[dict[str, Any]]:
    """Get all iterations for a task, ordered by iteration_number ascending."""
    rows = await fetch_with_retry(
        """
        SELECT iteration_id, task_id, iteration_number, iteration_type,
               reasoning_text, action_taken, action_params,
               observation_text, observation_data, decision, decision_rationale,
               created_at
        FROM taskiteration
        WHERE task_id = $1
        ORDER BY iteration_number ASC
        """,
        task_id,
    )
    return [dict(row) for row in rows]


async def get_latest_iteration(task_id: UUID) -> dict[str, Any] | None:
    """Get the most recent iteration for a task."""
    row = await fetchrow_with_retry(
        """
        SELECT iteration_id, task_id, iteration_number, iteration_type,
               reasoning_text, action_taken, action_params,
               observation_text, observation_data, decision, decision_rationale,
               created_at
        FROM taskiteration
        WHERE task_id = $1
        ORDER BY iteration_number DESC
        LIMIT 1
        """,
        task_id,
    )
    return dict(row) if row else None
