"""DataSourceQuota operations. (Adapted from Phase7)"""

import logging
from typing import Any

from oculai_mcp.db.client import execute_with_retry, fetchval_with_retry, fetchrow_with_retry

logger = logging.getLogger(__name__)


async def check_quota(source_name: str) -> bool:
    """Check if source has remaining quota. Prefer try_consume_quota() to avoid TOCTOU races."""
    result = await fetchval_with_retry("SELECT check_datasource_quota($1)", source_name)
    return bool(result)


async def consume_quota(source_name: str, amount: int = 1) -> None:
    """Consume quota. Prefer try_consume_quota() for atomic check-and-consume."""
    await execute_with_retry("SELECT consume_datasource_quota($1, $2)", source_name, amount)
    logger.debug("Consumed %d quota for %s", amount, source_name)


async def try_consume_quota(source_name: str, amount: int = 1) -> bool:
    """Atomically check and consume quota in a single DB call.

    Uses SELECT ... FOR UPDATE to prevent the TOCTOU race between
    check_quota() and consume_quota().

    Returns True if quota was available and consumed, False if exceeded.
    """
    result = await fetchval_with_retry(
        "SELECT try_consume_datasource_quota($1, $2)", source_name, amount
    )
    if result:
        logger.debug("Consumed %d quota for %s (atomic)", amount, source_name)
    return bool(result)


async def get_quota_status(source_name: str) -> dict[str, Any] | None:
    row = await fetchrow_with_retry("SELECT * FROM datasourcequota WHERE source_name = $1", source_name)
    return dict(row) if row else None


async def set_quota(source_name: str, daily_limit: int) -> None:
    await execute_with_retry(
        "INSERT INTO datasourcequota (source_name, daily_limit) VALUES ($1, $2) ON CONFLICT (source_name) DO UPDATE SET daily_limit = EXCLUDED.daily_limit, updated_at = now()",
        source_name, daily_limit,
    )
