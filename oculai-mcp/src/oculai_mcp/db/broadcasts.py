"""AgentBroadcast CRUD — cross-agent knowledge sharing."""

import logging
from typing import Any
from uuid import UUID

from oculai_mcp.db.client import fetch_with_retry, fetchrow_with_retry, execute_with_retry

logger = logging.getLogger(__name__)


async def broadcast_discovery(
    run_id: UUID,
    discovery_type: str,
    content: str,
    discovered_by: str,
) -> UUID:
    """Broadcast a discovery to all parallel agents in this run.

    Args:
        run_id: The SourcingRun UUID
        discovery_type: One of: terminology, population_insight, source_quality
        content: The discovery text (e.g., "Target population calls themselves '推理引擎开发'")
        discovered_by: Agent identifier (e.g., "source-researcher-juejin")
    Returns:
        The broadcast_id UUID
    """
    row = await fetchrow_with_retry(
        """
        INSERT INTO agentbroadcast (run_id, discovery_type, content, discovered_by)
        VALUES ($1, $2, $3, $4)
        RETURNING broadcast_id
        """,
        run_id, discovery_type, content, discovered_by,
    )
    broadcast_id = row["broadcast_id"]
    logger.info("Broadcast %s from %s: %s", broadcast_id, discovered_by, content[:80])
    return broadcast_id


async def get_broadcasts(run_id: UUID, agent_id: str) -> list[dict[str, Any]]:
    """Get all unconsumed broadcasts for this run.

    Returns broadcasts where consumed_by does NOT contain the requesting agent_id.
    Automatically marks returned broadcasts as consumed by this agent.

    Args:
        run_id: The SourcingRun UUID
        agent_id: The requesting agent's identifier
    """
    # Fetch unconsumed broadcasts
    rows = await fetch_with_retry(
        """
        SELECT broadcast_id, run_id, discovery_type, content, discovered_by, created_at
        FROM agentbroadcast
        WHERE run_id = $1
          AND NOT (consumed_by @> ARRAY[$2])
        ORDER BY created_at ASC
        """,
        run_id, agent_id,
    )
    broadcasts = [dict(row) for row in rows]

    # Mark them as consumed
    if broadcasts:
        broadcast_ids = [b["broadcast_id"] for b in broadcasts]
        await execute_with_retry(
            """
            UPDATE agentbroadcast
            SET consumed_by = array_append(consumed_by, $2)
            WHERE broadcast_id = ANY($1)
            """,
            broadcast_ids, agent_id,
        )
        logger.info("Agent %s consumed %d broadcasts for run=%s", agent_id, len(broadcasts), run_id)

    return broadcasts


async def list_broadcasts(run_id: UUID) -> list[dict[str, Any]]:
    """List all broadcasts for a run (for main agent inspection, does not mark consumed)."""
    rows = await fetch_with_retry(
        """
        SELECT broadcast_id, run_id, discovery_type, content, discovered_by, consumed_by, created_at
        FROM agentbroadcast
        WHERE run_id = $1
        ORDER BY created_at ASC
        """,
        run_id,
    )
    return [dict(row) for row in rows]
