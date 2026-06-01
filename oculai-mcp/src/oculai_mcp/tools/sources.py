"""Data source operations — listing, searching, fetching details."""

import time
from typing import Any
from uuid import UUID

from oculai_mcp.sources.base import SearchQuery
from oculai_mcp.sources.registry import create_source, get_all_capabilities, list_sources as list_registered_sources
from oculai_mcp.db.provenance import log_source_call


async def list_source_capabilities() -> dict[str, Any]:
    """List all registered data sources and their capabilities."""
    return {"sources": get_all_capabilities()}


async def search_source(
    source_name: str,
    keywords: list[str],
    run_id: UUID | None = None,
    source_specific_query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search a specific data source and return structured candidates."""
    if isinstance(keywords, str):
        keywords = [keywords]

    source = create_source(source_name)
    if source is None:
        return {"status": "error", "error": {"code": "unknown_source", "message": f"Source '{source_name}' not found"}}

    query = SearchQuery(
        keywords=keywords,
        limit=limit,
        offset=offset,
        source_specific_query=source_specific_query,
    )

    t0 = time.monotonic()
    try:
        candidates = await source.search(query)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        await log_source_call(
            source_name=source_name,
            source_type=source.source_type,
            query_params={"keywords": keywords, "limit": limit, "offset": offset},
            status="success",
            duration_ms=elapsed_ms,
            run_id=run_id,
            records_count=len(candidates),
        )

        return {
            "status": "success",
            "source_name": source_name,
            "candidates": [
                {
                    "name": c.name, "institution": c.institution, "orcid": c.orcid,
                    "google_scholar_id": c.google_scholar_id, "github_id": c.github_id,
                    "linkedin_url": c.linkedin_url, "paper_count": c.paper_count,
                    "h_index": c.h_index, "citation_count": c.citation_count,
                    "research_areas": c.research_areas, "profile_url": c.profile_url,
                    "raw_metadata": c.raw_metadata,
                    "result_type": c.result_type,
                    "confidence": c.confidence,
                    "extraction_method": c.extraction_method,
                }
                for c in candidates
            ],
            "meta": {"count": len(candidates), "latency_ms": elapsed_ms, "query": keywords},
        }

    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await log_source_call(
            source_name=source_name, source_type=source.source_type,
            query_params={"keywords": keywords, "limit": limit},
            status="failed", duration_ms=elapsed_ms, error_message=str(e),
            run_id=run_id,
        )
        return {"status": "error", "error": {"code": "search_failed", "message": str(e), "source_name": source_name}}


async def fetch_source_detail(source_name: str, external_id: str) -> dict[str, Any]:
    """Fetch detailed information for a single candidate from a source."""
    source = create_source(source_name)
    if source is None:
        return {"status": "error", "error": {"code": "unknown_source", "message": f"Source '{source_name}' not found"}}

    try:
        candidate = await source.get_detail(external_id)
        if candidate is None:
            return {"status": "error", "error": {"code": "not_found", "message": f"No result for '{external_id}'"}}

        return {
            "status": "success",
            "source_name": source_name,
            "candidate": {
                "name": candidate.name, "institution": candidate.institution,
                "orcid": candidate.orcid, "google_scholar_id": candidate.google_scholar_id,
                "github_id": candidate.github_id, "linkedin_url": candidate.linkedin_url,
                "paper_count": candidate.paper_count, "h_index": candidate.h_index,
                "citation_count": candidate.citation_count,
                "research_areas": candidate.research_areas, "profile_url": candidate.profile_url,
                "raw_metadata": candidate.raw_metadata,
                "result_type": candidate.result_type,
                "confidence": candidate.confidence,
                "extraction_method": candidate.extraction_method,
            },
        }
    except Exception as e:
        return {"status": "error", "error": {"code": "detail_failed", "message": str(e), "source_name": source_name}}
