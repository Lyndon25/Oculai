"""OpenAlex API data source.

Endpoint: https://api.openalex.org/
Docs: https://docs.openalex.org/

Completely free and open. No API key required.
Covers 250M+ scholarly works, 90M+ authors, institutions, topics, etc.
"""

import asyncio
import logging
import time
from typing import Any, Callable, TypeVar

import httpx

from oculai_mcp.config import get_settings
from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery
from oculai_mcp.utils.chinese_names import has_china_affiliation

logger = logging.getLogger(__name__)

OA_API_BASE = "https://api.openalex.org"

T = TypeVar("T")


async def _with_retry(
    coro: Callable[[], Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable: tuple[type, ...] = (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError),
) -> Any:
    """Execute coroutine with exponential backoff retry."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await coro()
        except retryable as e:
            last_exc = e
            delay = base_delay * (2 ** attempt)
            logger.warning("OpenAlex request failed (%s), retrying in %.1fs...", e, delay)
            await asyncio.sleep(delay)
    raise last_exc or RuntimeError("Retry exhausted")


class OpenAlexAPISource(IDataSource):
    """OpenAlex open academic data source.

    Search strategy:
    1. Search works by keyword → extract unique authors.
    2. Enrich top authors with detail endpoint (h-index, works count, ORCID, topics).
    Falls back to /authors/search if work search yields no results.
    """

    name = "openalex"
    source_type = "api"
    description = (
        "Search OpenAlex for academic authors by research keywords. "
        "Returns author profiles with works count, citation counts, h-index, "
        "ORCID, research topics, and institutional affiliations. "
        "Completely free and open — no API key required."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"openalex": "author_id"}
    example_queries = [
        "machine learning",
        "natural language processing",
        "computer vision",
        "reinforcement learning",
        "computational biology",
    ]
    auth_required = False
    rate_limit_notes = "100k calls/day (free). Polite use requested: set mailto in User-Agent."

    def __init__(self) -> None:
        settings = get_settings()
        email = settings.openalex_email or "contact@oculai.ai"
        self._user_agent = f"Oculai-TalentBot/1.0 (mailto:{email})"
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=OA_API_BASE,
                headers={"User-Agent": self._user_agent},
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    # ── search ──────────────────────────────────────────────────────────

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search works by keyword and aggregate unique authors."""
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
            papers = await self._search_works(client, query)
            if not papers:
                logger.info(
                    "OpenAlex work search returned 0 results for '%s'",
                    " ".join(query.keywords),
                )
                candidates = await self._search_authors_direct(client, query)
            else:
                authors = self._extract_authors_from_works(papers, query.limit)
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
            logger.info("OpenAlex search returned %d candidates", len(candidates))

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
            logger.exception("OpenAlex search failed")

        # --- China-First soft sorting ---
        if (query.extra or {}).get("china_first", True):
            china = [c for c in candidates if has_china_affiliation(c.institution, c.name)]
            non_china = [c for c in candidates if c not in china]
            candidates = china + non_china
            candidates = candidates[:query.limit]

        return candidates

    async def _search_works(
        self, client: httpx.AsyncClient, query: SearchQuery
    ) -> list[dict[str, Any]]:
        """Search works by keyword via /works."""
        keywords = " ".join(query.keywords)
        params: dict[str, str | int] = {
            "search": keywords,
            "per_page": min(query.limit * 5, 200),
            "sort": "cited_by_count:desc",
        }
        if query.years:
            start_year, end_year = query.years
            filter_parts = []
            if start_year:
                filter_parts.append(f"publication_year:{start_year}")
            if end_year:
                filter_parts.append(f"publication_year:{end_year}")
            if filter_parts:
                params["filter"] = ",".join(filter_parts)

        resp = await _with_retry(lambda: client.get("/works", params=params))
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    def _extract_authors_from_works(
        self, works: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        """Extract unique authors from work search results."""
        seen: dict[str, dict[str, Any]] = {}
        for work in works:
            primary_location = work.get("primary_location", {}) or {}
            source_info = primary_location.get("source", {}) or {}
            journal = source_info.get("display_name") if source_info else None

            for authorship in work.get("authorships", []):
                author_info = authorship.get("author", {})
                author_id_raw = author_info.get("id")
                if not author_id_raw:
                    continue

                # OpenAlex IDs are full URLs like https://openalex.org/A5023888391
                author_id = author_id_raw.split("/")[-1] if "/" in author_id_raw else author_id_raw
                if author_id in seen:
                    seen[author_id]["work_count"] += 1
                    cited = (work.get("cited_by_count") or 0)
                    seen[author_id]["total_citations"] += cited
                    continue

                orcid = author_info.get("orcid") or None
                # OpenAlex returns ORCID as full URL, extract just the ID
                if orcid and "/" in str(orcid):
                    orcid = str(orcid).split("/")[-1]

                institution = None
                institutions = authorship.get("institutions", []) or []
                if institutions:
                    institution = institutions[0].get("display_name")

                seen[author_id] = {
                    "id": author_id,
                    "name": author_info.get("display_name", ""),
                    "orcid": orcid,
                    "institution": institution,
                    "work_count": 1,
                    "total_citations": (work.get("cited_by_count") or 0),
                    "journal": journal,
                }

        sorted_authors = sorted(
            seen.values(), key=lambda a: a["total_citations"], reverse=True
        )
        return sorted_authors[: min(limit * 2, len(sorted_authors))]

    async def _enrich_authors(
        self,
        client: httpx.AsyncClient,
        authors: list[dict[str, Any]],
        limit: int,
    ) -> list[RawCandidate]:
        """Enrich basic author data with detail endpoint."""

        async def _fetch_one(a: dict[str, Any]) -> RawCandidate | None:
            try:
                resp = await _with_retry(lambda: client.get(f"/authors/{a['id']}"))
                resp.raise_for_status()
                detail = resp.json()
            except Exception:
                return _basic_candidate(a)

            h_index = detail.get("summary_stats", {}).get("h_index") or 0
            topics = []
            for topic in detail.get("topics", []) or []:
                t = topic if isinstance(topic, dict) else {}
                name = t.get("display_name") or t.get("subfield", {}).get("display_name")
                if name:
                    topics.append(name)

            return RawCandidate(
                name=detail.get("display_name") or a["name"],
                institution=_last_institution(detail) or a.get("institution"),
                orcid=_extract_orcid(detail) or a.get("orcid"),
                paper_count=detail.get("works_count") or a["work_count"],
                h_index=h_index,
                citation_count=detail.get("cited_by_count") or a["total_citations"],
                profile_url=detail.get("id"),
                raw_metadata={
                    "source": "openalex_api",
                    "author_id": a["id"],
                    "orcid": _extract_orcid(detail) or a.get("orcid"),
                    "topics": topics[:5],
                    "last_known_institution": _last_institution(detail),
                    "works_api_url": detail.get("works_api_url"),
                    "updated_date": detail.get("updated_date"),
                },
            )

        def _basic_candidate(a: dict[str, Any]) -> RawCandidate:
            return RawCandidate(
                name=a["name"],
                institution=a.get("institution"),
                orcid=a.get("orcid"),
                paper_count=a.get("work_count", 0),
                h_index=0,
                citation_count=a.get("total_citations", 0),
                profile_url=f"https://openalex.org/{a['id']}",
                raw_metadata={
                    "source": "openalex_api",
                    "author_id": a["id"],
                    "from_work_search": True,
                },
            )

        def _last_institution(detail: dict[str, Any]) -> str | None:
            insts = detail.get("last_known_institutions", []) or []
            if insts and isinstance(insts[0], dict):
                return insts[0].get("display_name")
            return None

        def _extract_orcid(detail: dict[str, Any]) -> str | None:
            raw = detail.get("orcid") or ""
            if raw and "/" in str(raw):
                return str(raw).split("/")[-1]
            return raw or None

        batch_size = 10
        results: list[RawCandidate] = []
        for i in range(0, len(authors), batch_size):
            batch = authors[i : i + batch_size]
            batch_results = await asyncio.gather(
                *(_fetch_one(a) for a in batch), return_exceptions=True
            )
            for r in batch_results:
                if isinstance(r, RawCandidate):
                    results.append(r)
            if len(results) >= limit:
                break

        return results[:limit]

    async def _search_authors_direct(
        self, client: httpx.AsyncClient, query: SearchQuery
    ) -> list[RawCandidate]:
        """Fallback: search authors directly via /authors/search."""
        keywords = " ".join(query.keywords)
        params: dict[str, str | int] = {
            "search": keywords,
            "per_page": min(query.limit, 200),
        }
        resp = await _with_retry(lambda: client.get("/authors", params=params))
        resp.raise_for_status()
        data = resp.json()

        candidates: list[RawCandidate] = []
        for item in data.get("results", [])[: query.limit]:
            h_index = item.get("summary_stats", {}).get("h_index") or 0

            topics = []
            for topic in item.get("topics", []) or []:
                name = (topic.get("display_name") or "" if isinstance(topic, dict) else "")
                if name:
                    topics.append(name)

            last_inst = None
            insts = item.get("last_known_institutions", []) or []
            if insts and isinstance(insts[0], dict):
                last_inst = insts[0].get("display_name")

            raw_orcid = item.get("orcid") or ""
            orcid = raw_orcid.split("/")[-1] if "/" in str(raw_orcid) else (raw_orcid or None)

            candidates.append(
                RawCandidate(
                    name=item.get("display_name", ""),
                    institution=last_inst,
                    orcid=orcid,
                    paper_count=item.get("works_count", 0),
                    h_index=h_index,
                    citation_count=item.get("cited_by_count", 0),
                    profile_url=item.get("id"),
                    raw_metadata={
                        "source": "openalex_api",
                        "author_id": item.get("id", "").split("/")[-1]
                        if "/" in (item.get("id") or "")
                        else item.get("id"),
                        "orcid": orcid,
                        "topics": topics[:5],
                        "fallback_search": True,
                    },
                )
            )
        return candidates

    # ── get_detail ──────────────────────────────────────────────────────

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch detailed author profile by OpenAlex author ID."""
        start = time.perf_counter()

        try:
            client = await self._get_client()
            resp = await _with_retry(lambda: client.get(f"/authors/{external_id}"))
            resp.raise_for_status()
            detail = resp.json()

            h_index = detail.get("summary_stats", {}).get("h_index") or 0

            topics = []
            for topic in detail.get("topics", []) or []:
                name = (topic.get("display_name") or "" if isinstance(topic, dict) else "")
                if name:
                    topics.append(name)

            last_inst = None
            insts = detail.get("last_known_institutions", []) or []
            if insts and isinstance(insts[0], dict):
                last_inst = insts[0].get("display_name")

            raw_orcid = detail.get("orcid") or ""
            orcid = raw_orcid.split("/")[-1] if "/" in str(raw_orcid) else (raw_orcid or None)

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
                name=detail.get("display_name", ""),
                institution=last_inst,
                orcid=orcid,
                paper_count=detail.get("works_count", 0),
                h_index=h_index,
                citation_count=detail.get("cited_by_count", 0),
                profile_url=detail.get("id"),
                raw_metadata={
                    "source": "openalex_api",
                    "author_id": external_id,
                    "orcid": orcid,
                    "topics": topics[:5],
                    "last_known_institution": last_inst,
                    "works_api_url": detail.get("works_api_url"),
                    "updated_date": detail.get("updated_date"),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("OpenAlex author not found: %s", external_id)
                return None
            logger.error("OpenAlex API detail failed: HTTP %s", e.response.status_code)
            return None
        except Exception:
            logger.exception("OpenAlex API detail failed for %s", external_id)
            return None

    # ── health ──────────────────────────────────────────────────────────

    async def check_health(self) -> HealthStatus:
        """Check OpenAlex API health."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await _with_retry(
                lambda: client.get("/works", params={"search": "test", "per_page": 1}),
                max_retries=2,
                base_delay=0.5,
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
