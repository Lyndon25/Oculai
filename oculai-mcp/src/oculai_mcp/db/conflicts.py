"""DataConflict operations. (Adapted from Phase7)"""

import json
from typing import Any
from uuid import UUID

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry


async def record_conflict(entity_type: str, entity_id: UUID, field_name: str, values_json: list[dict[str, Any]]) -> UUID:
    result = await fetch_with_retry(
        "SELECT record_conflict($1, $2, $3, $4::jsonb) as conflict_id",
        entity_type, entity_id, field_name, json.dumps(values_json),
    )
    return result[0]["conflict_id"]


async def get_conflicts(entity_type: str | None = None, entity_id: UUID | None = None, resolved: bool | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conditions = []
    values = []
    idx = 1

    if entity_type:
        conditions.append(f"entity_type = ${idx}"); values.append(entity_type); idx += 1
    if entity_id:
        conditions.append(f"entity_id = ${idx}"); values.append(entity_id); idx += 1
    if resolved is not None:
        conditions.append(f"resolved_by {'IS NOT NULL' if resolved else 'IS NULL'}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM dataconflict {where_clause} ORDER BY created_at DESC LIMIT ${idx}"
    values.append(limit)

    rows = await fetch_with_retry(query, *values)
    return [dict(row) for row in rows]


async def resolve_conflict(conflict_id: UUID, resolved_by: str, resolved_value: dict[str, Any] | None = None) -> bool:
    result = await execute_with_retry(
        "UPDATE dataconflict SET resolved_by = $2, resolved_at = now(), suggested_value = COALESCE($3, suggested_value) WHERE conflict_id = $1",
        conflict_id, resolved_by, resolved_value,
    )
    return "UPDATE 1" in result
