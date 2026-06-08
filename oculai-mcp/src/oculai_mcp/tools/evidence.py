"""Evidence management — attach and retrieve structured evidence.

Upgraded with automatic tier assignment and quality flag detection.
"""

from typing import Any
from uuid import UUID, uuid4

import asyncpg

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry
from oculai_mcp.tools.errors import (
    ConflictError,
    InternalError,
    NotFoundError,
    ValidationError,
    ok,
)

# Valid evidence types (must match evidence_type_t domain in 002_enums.sql)
_VALID_EVIDENCE_TYPES = frozenset({
    'paper', 'patent', 'code', 'profile', 'web_page', 'screenshot',
    'email', 'interview', 'reference', 'blog_post', 'social_media',
    'conference_talk', 'award', 'certification',
})


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
    """Attach a piece of evidence to a candidate.

    Upgraded behavior:
    - Auto-assigns quality tier based on source + evidence_type
    - Auto-detects quality flags from content heuristics
    """
    # ---- Validation ----
    if not title or not title.strip():
        raise ValidationError("title is required and must not be empty")
    if evidence_type not in _VALID_EVIDENCE_TYPES:
        raise ValidationError(
            f"invalid evidence_type {evidence_type!r}; "
            f"must be one of {sorted(_VALID_EVIDENCE_TYPES)}"
        )
    if confidence < 0.0 or confidence > 1.0:
        raise ValidationError("confidence must be between 0.0 and 1.0")

    try:
        evidence_id = uuid4()
        content_dict = content or {}
        metadata_dict = metadata or {}

        # Auto-assign tier and quality flags
        from oculai_mcp.tools.evidence_tier import get_tier, _detect_quality_flags
        tier = get_tier(source_name, evidence_type)
        quality_flags = _detect_quality_flags(source_name, content_dict)

        await execute_with_retry(
            """
            INSERT INTO evidence (evidence_id, person_id, run_id, evidence_type, title,
                description, source_url, source_name, content, confidence,
                captured_by_agent, metadata, tier, quality_flags,
                created_by_agent, updated_by_agent)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $15)
            """,
            evidence_id, person_id, run_id, evidence_type, title,
            description, source_url, source_name,
            content_dict,
            confidence, captured_by_agent,
            metadata_dict,
            tier,
            quality_flags,
            captured_by_agent,
        )

        return {
            "evidence_id": str(evidence_id),
            "person_id": str(person_id),
            "evidence_type": evidence_type,
            "title": title,
            "tier": tier,
            "quality_flags": quality_flags,
        }
    except (asyncpg.CheckViolationError, asyncpg.NotNullViolationError) as e:
        raise ValidationError(str(e), details={"db_error": type(e).__name__}) from e
    except asyncpg.UniqueViolationError as e:
        raise ConflictError(str(e), details={"db_error": type(e).__name__}) from e
    except asyncpg.ForeignKeyViolationError as e:
        raise ValidationError(str(e), details={"db_error": type(e).__name__}) from e
    except asyncpg.PostgresError as e:
        raise InternalError(str(e), details={"db_error": type(e).__name__}) from e


async def get_evidence(
    person_id: UUID, evidence_type: str | None = None, limit: int = 100,
    min_tier: int | None = None,
) -> dict[str, Any]:
    """Get all evidence for a candidate, optionally filtered by type and tier."""
    # ---- Validation ----
    if evidence_type is not None and evidence_type not in _VALID_EVIDENCE_TYPES:
        raise ValidationError(
            f"invalid evidence_type {evidence_type!r}; "
            f"must be one of {sorted(_VALID_EVIDENCE_TYPES)}"
        )

    try:
        base_query = "SELECT * FROM evidence WHERE person_id = $1"
        args: list[Any] = [person_id]

        if evidence_type:
            base_query += " AND evidence_type = $2"
            args.append(evidence_type)
        if min_tier is not None:
            base_query += f" AND tier <= ${len(args) + 1}"
            args.append(min_tier)

        base_query += f" ORDER BY captured_at DESC LIMIT ${len(args) + 1}"
        args.append(limit)

        rows = await fetch_with_retry(base_query, *args)

        evidence_list = []
        for row in rows:
            d = dict(row)
            for k in ("captured_at", "created_at", "updated_at"):
                if d.get(k):
                    d[k] = str(d[k])
            evidence_list.append(d)

        # Summary stats by type
        type_counts = await fetch_with_retry(
            "SELECT evidence_type, COUNT(*) as cnt FROM evidence WHERE person_id = $1 GROUP BY evidence_type",
            person_id,
        )

        # Summary stats by tier
        tier_counts = await fetch_with_retry(
            "SELECT tier, COUNT(*) as cnt FROM evidence WHERE person_id = $1 GROUP BY tier",
            person_id,
        )

        return {
            "person_id": str(person_id),
            "evidence": evidence_list,
            "total": len(evidence_list),
            "by_type": {r["evidence_type"]: r["cnt"] for r in type_counts},
            "by_tier": {r["tier"]: r["cnt"] for r in tier_counts},
        }
    except asyncpg.PostgresError as e:
        raise InternalError(str(e), details={"db_error": type(e).__name__}) from e


async def get_evidence_by_tier(
    run_id: UUID,
    person_id: UUID,
    max_tier: int = 2,
) -> dict[str, Any]:
    """Get evidence up to a given tier (1=primary, 2=secondary, etc.).

    Useful for scoring validation: score >= 7 should have tier 1 evidence.
    """
    try:
        rows = await fetch_with_retry(
            """
            SELECT evidence_id, evidence_type, title, source_name, source_url,
                   confidence, tier, quality_flags, content, captured_at
            FROM evidence
            WHERE run_id = $1 AND person_id = $2 AND tier <= $3
            ORDER BY tier ASC, confidence DESC
            """,
            run_id, person_id, max_tier,
        )
        return {
            "person_id": str(person_id),
            "run_id": str(run_id),
            "max_tier": max_tier,
            "evidence": [dict(r) for r in rows],
            "count": len(rows),
        }
    except asyncpg.PostgresError as e:
        raise InternalError(str(e), details={"db_error": type(e).__name__}) from e
