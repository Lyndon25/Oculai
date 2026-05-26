"""Evidence management — attach and retrieve structured evidence."""

from typing import Any
from uuid import UUID, uuid4

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry


async def attach_evidence(
    person_id: UUID,
    evidence_type: str,
    title: str,
    source_name: str,
    source_url: str | None = None,
    description: str | None = None,
    content: dict[str, Any] | None = None,
    confidence: float = 1.0,
    run_id: UUID | None = None,
    captured_by_agent: str = "system",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach a piece of evidence to a candidate."""
    evidence_id = uuid4()

    await execute_with_retry(
        """
        INSERT INTO evidence (evidence_id, person_id, run_id, evidence_type, title,
            description, source_url, source_name, content, confidence,
            captured_by_agent, metadata, created_by_agent, updated_by_agent)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $13)
        """,
        evidence_id, person_id, run_id, evidence_type, title,
        description, source_url, source_name,
        content or {},
        confidence, captured_by_agent,
        metadata or {},
        captured_by_agent,
    )

    return {
        "evidence_id": str(evidence_id),
        "person_id": str(person_id),
        "evidence_type": evidence_type,
        "title": title,
    }


async def get_evidence(person_id: UUID, evidence_type: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Get all evidence for a candidate, optionally filtered by type."""
    if evidence_type:
        rows = await fetch_with_retry(
            "SELECT * FROM evidence WHERE person_id = $1 AND evidence_type = $2 ORDER BY captured_at DESC LIMIT $3",
            person_id, evidence_type, limit,
        )
    else:
        rows = await fetch_with_retry(
            "SELECT * FROM evidence WHERE person_id = $1 ORDER BY captured_at DESC LIMIT $2",
            person_id, limit,
        )

    evidence_list = []
    for row in rows:
        d = dict(row)
        # Convert timestamps
        for k in ("captured_at", "created_at", "updated_at"):
            if d.get(k):
                d[k] = str(d[k])
        evidence_list.append(d)

    # Summary stats
    type_counts = await fetch_with_retry(
        "SELECT evidence_type, COUNT(*) as cnt FROM evidence WHERE person_id = $1 GROUP BY evidence_type",
        person_id,
    )

    return {
        "person_id": str(person_id),
        "evidence": evidence_list,
        "total": len(evidence_list),
        "by_type": {r["evidence_type"]: r["cnt"] for r in type_counts},
    }
