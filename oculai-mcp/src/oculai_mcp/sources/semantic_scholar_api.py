"""Semantic Scholar API data source.

Endpoint: https://api.semanticscholar.org/graph/v1/
Docs: https://api.semanticscholar.org/api-docs/

Free tier: 100 requests per 5 minutes without API key.
With API key: higher rate limits.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from oculai_mcp.config import get_settings
from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"
DEFAULT_LIMIT = 20
PAPER_SEARCH_FIELDS = "title,year,authors,externalIds,citationCount"
AUTHOR_SEARCH_FIELDS = "name,affiliations,hIndex,citationCount,paperCount,url,externalIds,homepage"


class SemanticScholarAPISource(IDataSource):
    """Semantic Scholar Academic Graph API data source.

    Search strategy:
    1. Search papers by keyword → extract unique authors.
    2. Enrich top authors with detail endpoint (h-index, citation count, papers).
    """

    name = "semantic_scholar"
    source_type = "api"
    description = (
        "Search Semantic Scholar for academic authors by paper keywords. "
        "Returns author profiles with h-index, citation counts, paper counts, "
        "affiliations, and ORCID. Free API, no key required for basic usage."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"semantic_scholar": "author_id"}
    example_queries = [
        "transformer architecture attention mechanism",
        "reinforcement learning robotics control",
        "natural language processing large language models",
        "computer vision object detection segmentation",
        "graph neural networks representation learning",
    ]
    auth_required = False
    rate_limit_notes = "100 requests per 5 min without API key. Set S2_API_KEY for higher limits."

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str | None = getattr(settings, "s2_api_key", None) or None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["x-api-key"] = self._api_key
            self._client = httpx.AsyncClient(
                base_url=S2_API_BASE,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    # ── search ──────────────────────────────────────────────────────────

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search papers by keyword and aggregate unique authors."""
        start = time.perf_counter()

        if not await check_quota(self.name):
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="rate_limited",
                duration_ms=0,
            )
            return []

        candidates: list[RawCandidate] = []
        try:
            client = await self._get_client()
            papers = await self._search_papers(client, query)
            if not papers:
                logger.info("S2 paper search returned 0 results for '%s'", " ".join(query.keywords))
                candidates = await self._search_authors_fallback(client, query)
            else:
                authors = self._extract_authors_from_papers(papers, query.limit)
                candidates = await self._enrich_authors(client, authors, query.limit)

            await consume_quota(self.name, amount=len(candidates))
            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords, "limit": query.limit},
                status="success",
                duration_ms=duration_ms,
                records_count=len(candidates),
            )
            logger.info("Semantic Scholar search returned %d candidates", len(candidates))

        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=duration_ms,
                error_message=str(e),
            )
            logger.exception("Semantic Scholar search failed")

        return candidates

    async def _search_papers(
        self, client: httpx.AsyncClient, query: SearchQuery
    ) -> list[dict[str, Any]]:
        """Search papers by keyword via /paper/search."""
        keywords = " ".join(query.keywords)
        params: dict[str, str | int] = {
            "query": keywords,
            "limit": min(query.limit * 5, 100),
            "fields": PAPER_SEARCH_FIELDS,
        }
        if query.years:
            start_year, end_year = query.years
            if start_year:
                params["year"] = f"{start_year}-{end_year or ''}"

        resp = await client.get("/paper/search", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    def _extract_authors_from_papers(
        self, papers: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        """Extract unique authors from paper search results."""
        seen: dict[str, dict[str, Any]] = {}
        for paper in papers:
            for author in paper.get("authors", []):
                author_id = author.get("authorId")
                if not author_id or author_id in seen:
                    continue
                seen[author_id] = {
                    "authorId": author_id,
                    "name": author.get("name", ""),
                    "paper_count": 1,
                    "citation_count": paper.get("citationCount", 0) or 0,
                    "top_paper_title": paper.get("title", ""),
                    "top_paper_year": paper.get("year"),
                }
        # Sort by citation count descending
        sorted_authors = sorted(
            seen.values(), key=lambda a: a["citation_count"], reverse=True
        )
        return sorted_authors[: min(limit * 2, len(sorted_authors))]

    async def _enrich_authors(
        self,
        client: httpx.AsyncClient,
        authors: list[dict[str, Any]],
        limit: int,
    ) -> list[RawCandidate]:
        """Enrich basic author data with detail endpoint (h-index, affiliations, ORCID)."""

        async def _fetch_detail(author: dict[str, Any]) -> RawCandidate | None:
            try:
                resp = await client.get(
                    f"/author/{author['authorId']}",
                    params={"fields": AUTHOR_SEARCH_FIELDS},
                )
                resp.raise_for_status()
                detail = resp.json()
            except Exception:
                # Fall back to basic info from paper search
                return RawCandidate(
                    name=author["name"],
                    paper_count=author["paper_count"],
                    citation_count=author["citation_count"],
                    profile_url=f"https://api.semanticscholar.org/author/{author['authorId']}",
                    raw_metadata={
                        "source": "semantic_scholar_api",
                        "author_id": author["authorId"],
                        "from_paper_search": True,
                    },
                )

            external_ids = detail.get("externalIds", {}) or {}
            affiliations = detail.get("affiliations", []) or []
            institution = affiliations[0] if affiliations else None

            orcid = external_ids.get("ORCID") or None

            return RawCandidate(
                name=detail.get("name") or author["name"],
                institution=institution,
                orcid=orcid,
                paper_count=detail.get("paperCount") or author["paper_count"],
                h_index=detail.get("hIndex") or 0,
                citation_count=detail.get("citationCount") or author["citation_count"],
                profile_url=detail.get("url"),
                research_areas=self._infer_research_areas(detail),
                raw_metadata={
                    "source": "semantic_scholar_api",
                    "author_id": author["authorId"],
                    "external_ids": external_ids,
                    "affiliations": affiliations,
                    "homepage": detail.get("homepage"),
                    "papers": detail.get("papers", [])[:10],
                },
            )

        batch_size = 10
        results: list[RawCandidate] = []
        for i in range(0, len(authors), batch_size):
            batch = authors[i : i + batch_size]
            batch_results = await asyncio.gather(
                *(_fetch_detail(a) for a in batch), return_exceptions=True
            )
            for r in batch_results:
                if isinstance(r, RawCandidate):
                    results.append(r)
            if len(results) >= limit:
                break

        return results[:limit]

    async def _search_authors_fallback(
        self, client: httpx.AsyncClient, query: SearchQuery
    ) -> list[RawCandidate]:
        """Fallback: search authors directly via /author/search."""
        keywords = " ".join(query.keywords)
        params: dict[str, str | int] = {
            "query": keywords,
            "limit": min(query.limit, 100),
            "fields": AUTHOR_SEARCH_FIELDS,
        }
        resp = await client.get("/author/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        candidates: list[RawCandidate] = []
        for item in data.get("data", [])[: query.limit]:
            external_ids = item.get("externalIds", {}) or {}
            affiliations = item.get("affiliations", []) or []

            candidates.append(
                RawCandidate(
                    name=item.get("name", ""),
                    institution=affiliations[0] if affiliations else None,
                    orcid=external_ids.get("ORCID"),
                    paper_count=item.get("paperCount", 0),
                    h_index=item.get("hIndex", 0),
                    citation_count=item.get("citationCount", 0),
                    profile_url=item.get("url"),
                    raw_metadata={
                        "source": "semantic_scholar_api",
                        "author_id": item.get("authorId"),
                        "external_ids": external_ids,
                        "affiliations": affiliations,
                        "homepage": item.get("homepage"),
                        "fallback_search": True,
                    },
                )
            )
        return candidates

    def _infer_research_areas(self, author_detail: dict[str, Any]) -> list[str] | None:
        """Infer research areas from paper titles in author detail."""
        papers = author_detail.get("papers", []) or []
        if not papers:
            return None

        keyword_map = {
            "nlp": "natural_language_processing",
            "language": "natural_language_processing",
            "transformer": "deep_learning",
            "llm": "large_language_models",
            "vision": "computer_vision",
            "image": "computer_vision",
            "reinforcement": "reinforcement_learning",
            "robot": "robotics",
            "graph": "graph_neural_networks",
            "federated": "federated_learning",
            "optimization": "optimization",
            "generation": "generative_models",
            "diffusion": "generative_models",
            "retrieval": "information_retrieval",
            "recommendation": "recommendation_systems",
            "speech": "speech_processing",
            "multimodal": "multimodal_learning",
            "segmentation": "computer_vision",
            "detection": "computer_vision",
        }
        found: set[str] = set()
        text = " ".join((p.get("title") or "").lower() for p in papers)
        for kw, area in keyword_map.items():
            if kw in text:
                found.add(area)
        return sorted(found)[:5] if found else None

    # ── get_detail ──────────────────────────────────────────────────────

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch detailed author profile by Semantic Scholar author ID."""
        start = time.perf_counter()

        try:
            client = await self._get_client()
            resp = await client.get(
                f"/author/{external_id}",
                params={"fields": AUTHOR_SEARCH_FIELDS},
            )
            resp.raise_for_status()
            detail = resp.json()

            external_ids = detail.get("externalIds", {}) or {}
            affiliations = detail.get("affiliations", []) or []

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"author_id": external_id},
                status="success",
                duration_ms=duration_ms,
                records_count=1,
            )

            return RawCandidate(
                name=detail.get("name", ""),
                institution=affiliations[0] if affiliations else None,
                orcid=external_ids.get("ORCID"),
                paper_count=detail.get("paperCount", 0),
                h_index=detail.get("hIndex", 0),
                citation_count=detail.get("citationCount", 0),
                profile_url=detail.get("url"),
                research_areas=self._infer_research_areas(detail),
                raw_metadata={
                    "source": "semantic_scholar_api",
                    "author_id": detail.get("authorId"),
                    "external_ids": external_ids,
                    "affiliations": affiliations,
                    "homepage": detail.get("homepage"),
                    "papers": detail.get("papers", [])[:10],
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("S2 author not found: %s", external_id)
                return None
            logger.error("S2 API detail failed: HTTP %s", e.response.status_code)
            return None
        except Exception:
            logger.exception("S2 API detail failed for %s", external_id)
            return None

    # ── health ──────────────────────────────────────────────────────────

    async def check_health(self) -> HealthStatus:
        """Check Semantic Scholar API health."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get(
                "/paper/search",
                params={"query": "test", "limit": 1},
            )
            resp.raise_for_status()
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(healthy=True, latency_ms=latency_ms)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(healthy=False, latency_ms=latency_ms, error_message=str(e))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
