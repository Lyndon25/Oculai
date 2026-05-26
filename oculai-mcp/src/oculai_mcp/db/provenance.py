"""SearchQueryLog operations. (Adapted from Phase7 DataSourceLog)"""

import logging
from typing import Any
from uuid import UUID, uuid4

from oculai_mcp.db.client import execute_with_retry

logger = logging.getLogger(__name__)


async def log_source_call(
    source_name: str,
    source_type: str,
    query_params: dict[str, Any],
    status: str,
    duration_ms: int,
    run_id: UUID | None = None,
    records_count: int = 0,
    error_message: str | None = None,
    raw_data_checksum: str | None = None,
    raw_data_size_bytes: int | None = None,
    retry_count: int = 0,
) -> UUID:
    log_id = uuid4()
    await execute_with_retry(
        """
        INSERT INTO searchquerylog (
            log_id, run_id, source_name, source_type, query_params,
            status, duration_ms, records_count, error_message,
            raw_data_checksum, raw_data_size_bytes, retry_count
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
        log_id, run_id, source_name, source_type, query_params,
        status, duration_ms, records_count, error_message,
        raw_data_checksum, raw_data_size_bytes, retry_count,
    )
    logger.debug("Logged source call: %s status=%s records=%d", source_name, status, records_count)
    return log_id
