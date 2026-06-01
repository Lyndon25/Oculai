"""PersonExternalIdentity CRUD operations. (Adapted from Phase7)"""

import logging
from typing import Any
from uuid import UUID

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchval_with_retry

logger = logging.getLogger(__name__)


async def link_person_identity(
    person_id: UUID,
    source_type: str,
    external_id: str,
    external_url: str | None = None,
    is_primary: bool = False,
    confidence: float = 1.0,
    verified_by_agent: str = "system",
) -> UUID | None:
    if not external_id:
        return None
    result = await fetchval_with_retry(
        """SELECT link_person_identity($1, $2, $3, $4, $5, $6, $7)""",
        person_id, source_type, external_id, external_url, is_primary, confidence, verified_by_agent,
    )
    return result


async def find_person_by_identity(source_type: str, external_id: str) -> UUID | None:
    if not external_id:
        return None
    return await fetchval_with_retry(
        "SELECT find_person_by_identity($1, $2)", source_type, external_id,
    )


async def find_person_by_name_institution(name: str, institution: str | None) -> UUID | None:
    return await fetchval_with_retry(
        "SELECT find_person_by_name_institution($1, $2)", name, institution,
    )


async def find_person_by_fuzzy_name(name: str, institution: str | None, similarity_threshold: float = 0.7) -> UUID | None:
    return await fetchval_with_retry(
        "SELECT find_person_by_fuzzy_name($1, $2, $3)", name, institution, similarity_threshold,
    )


async def merge_person_data(person_id: UUID, candidate: Any, agent_id: str) -> None:
    # Core fields via stored procedure
    await execute_with_retry(
        "SELECT merge_person_data($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
        person_id,
        candidate.get("institution") if isinstance(candidate, dict) else getattr(candidate, "institution", None),
        candidate.get("paper_count") if isinstance(candidate, dict) else getattr(candidate, "paper_count", None),
        candidate.get("h_index") if isinstance(candidate, dict) else getattr(candidate, "h_index", None),
        candidate.get("citation_count") if isinstance(candidate, dict) else getattr(candidate, "citation_count", None),
        candidate.get("orcid") if isinstance(candidate, dict) else getattr(candidate, "orcid", None),
        candidate.get("google_scholar_id") if isinstance(candidate, dict) else getattr(candidate, "google_scholar_id", None),
        candidate.get("github_id") if isinstance(candidate, dict) else getattr(candidate, "github_id", None),
        candidate.get("linkedin_url") if isinstance(candidate, dict) else getattr(candidate, "linkedin_url", None),
        agent_id,
    )

    # Extended fields not handled by the stored procedure
    def _get(field: str):
        if isinstance(candidate, dict):
            return candidate.get(field)
        return getattr(candidate, field, None)

    aliases = _get("aliases")
    position = _get("position") or _get("job_title")
    pool_tags = _get("pool_tags")

    if aliases is not None or position is not None or pool_tags is not None:
        await execute_with_retry(
            """
            UPDATE person
            SET aliases = COALESCE(aliases, $2),
                latest_position = COALESCE(latest_position, $3),
                pool_tags = COALESCE(pool_tags, $4),
                updated_at = now(),
                updated_by_agent = $5,
                data_version = data_version + 1
            WHERE person_id = $1
            """,
            person_id, aliases, position, pool_tags, agent_id,
        )
