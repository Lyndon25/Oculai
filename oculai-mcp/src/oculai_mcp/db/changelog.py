"""ChangeLog operations. (Adapted from Phase7)"""

from typing import Any
from uuid import UUID

from oculai_mcp.db.client import fetch_with_retry


async def query_changes(
    entity_type: str | None = None, entity_id: UUID | None = None,
    severity: str | None = None, since: str | None = None, limit: int = 100,
) -> list[dict[str, Any]]:
    conditions = []
    values = []
    idx = 1

    if entity_type:
        conditions.append(f"entity_type = ${idx}"); values.append(entity_type); idx += 1
    if entity_id:
        conditions.append(f"entity_id = ${idx}"); values.append(entity_id); idx += 1
    if severity:
        conditions.append(f"severity = ${idx}"); values.append(severity); idx += 1
    if since:
        conditions.append(f"created_at >= ${idx}"); values.append(since); idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM changelog {where_clause} ORDER BY created_at DESC LIMIT ${idx}"
    values.append(limit)

    rows = await fetch_with_retry(query, *values)
    return [dict(row) for row in rows]
