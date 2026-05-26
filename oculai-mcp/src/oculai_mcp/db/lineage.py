"""DataLineage operations. (Adapted from Phase7)"""

from typing import Any
from uuid import UUID

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry


async def register_lineage(
    upstream_entity: str, upstream_id: UUID, upstream_field: str,
    downstream_entity: str, downstream_id: UUID, downstream_field: str,
) -> None:
    await execute_with_retry(
        "SELECT register_lineage($1, $2, $3, $4, $5, $6)",
        upstream_entity, upstream_id, upstream_field,
        downstream_entity, downstream_id, downstream_field,
    )


async def get_downstream_dependencies(upstream_entity: str, upstream_id: UUID, upstream_field: str | None = None) -> list[dict[str, Any]]:
    if upstream_field:
        rows = await fetch_with_retry(
            "SELECT * FROM datalineage WHERE upstream_entity = $1 AND upstream_id = $2 AND upstream_field = $3",
            upstream_entity, upstream_id, upstream_field,
        )
    else:
        rows = await fetch_with_retry(
            "SELECT * FROM datalineage WHERE upstream_entity = $1 AND upstream_id = $2",
            upstream_entity, upstream_id,
        )
    return [dict(row) for row in rows]


async def get_upstream_dependencies(downstream_entity: str, downstream_id: UUID, downstream_field: str | None = None) -> list[dict[str, Any]]:
    if downstream_field:
        rows = await fetch_with_retry(
            "SELECT * FROM datalineage WHERE downstream_entity = $1 AND downstream_id = $2 AND downstream_field = $3",
            downstream_entity, downstream_id, downstream_field,
        )
    else:
        rows = await fetch_with_retry(
            "SELECT * FROM datalineage WHERE downstream_entity = $1 AND downstream_id = $2",
            downstream_entity, downstream_id,
        )
    return [dict(row) for row in rows]
