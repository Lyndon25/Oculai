"""DataSourceQuota operations. (Adapted from Phase7)"""

import logging
from typing import Any

from oculai_mcp.db.client import execute_with_retry, fetchval_with_retry, fetchrow_with_retry

logger = logging.getLogger(__name__)


async def check_quota(source_name: str) -> bool:
    result = await fetchval_with_retry("SELECT check_datasource_quota($1)", source_name)
    return bool(result)


async def consume_quota(source_name: str, amount: int = 1) -> None:
    await execute_with_retry("SELECT consume_datasource_quota($1, $2)", source_name, amount)
    logger.debug("Consumed %d quota for %s", amount, source_name)


async def get_quota_status(source_name: str) -> dict[str, Any] | None:
    row = await fetchrow_with_retry("SELECT * FROM datasourcequota WHERE source_name = $1", source_name)
    return dict(row) if row else None


async def set_quota(source_name: str, daily_limit: int) -> None:
    await execute_with_retry(
        "INSERT INTO datasourcequota (source_name, daily_limit) VALUES ($1, $2) ON CONFLICT (source_name) DO UPDATE SET daily_limit = EXCLUDED.daily_limit, updated_at = now()",
        source_name, daily_limit,
    )
