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
    await execute_with_retry(
        "SELECT merge_person_data($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
        person_id,
        getattr(candidate, "institution", None),
        getattr(candidate, "paper_count", None),
        getattr(candidate, "h_index", None),
        getattr(candidate, "citation_count", None),
        getattr(candidate, "orcid", None),
        getattr(candidate, "google_scholar_id", None),
        getattr(candidate, "github_id", None),
        getattr(candidate, "linkedin_url", None),
        agent_id,
    )
