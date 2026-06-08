"""DBLP API data source.

Uses the DBLP search API (https://dblp.org/search/author/api) which returns JSON.
"""

import logging
import time

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, try_consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery
from oculai_mcp.utils.chinese_names import has_china_affiliation

logger = logging.getLogger(__name__)

DBLP_SEARCH_API = "https://dblp.org/search/author/api"


class DblpAPISource(IDataSource):
    """Real DBLP API data source."""

    name = "dblp"
    source_type = "api"
    description = "Search DBLP computer science bibliography for authors and publications. Returns paper counts, venues, and publication history. No API key required."
    supported_operations = ["search", "get_detail"]
    id_field_map = {"dblp": "dblp_key"}
    example_queries = [
        "machine learning",
        "distributed systems",
        "programming languages",
        "computer vision",
        "natural language processing",
    ]
    auth_required = False
    rate_limit_notes = "No API key required. Be polite with request frequency."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search DBLP authors by keywords."""
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

        keywords = " ".join(query.keywords)
        candidates: list[RawCandidate] = []

        try:
            client = await self._get_client()
            params = {
                "q": keywords,
                "format": "json",
                "h": str(min(query.limit, 30)),
                "f": str(query.offset),
            }

            resp = await client.get(DBLP_SEARCH_API, params=params)
            resp.raise_for_status()
            data = resp.json()

            for hit in data.get("result", {}).get("hits", {}).get("hit", []):
                info = hit.get("info", {})
                if not info:
                    continue

                author_name = info.get("author", "Unknown")
                url = info.get("url", "")

                # DBLP sometimes returns a list of authors for a single hit
                # We treat each as a separate candidate
                candidates.append(
                    RawCandidate(
                        name=author_name,
                        profile_url=url if url else None,
                        paper_count=info.get("count", 0),
                        raw_metadata={
                            "source": "dblp_api",
                            "dblp_key": info.get("key"),
                            "dblp_id": info.get("id"),
                        },
                    )
                )

            await try_consume_quota(self.name, amount=len(candidates))

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords, "limit": query.limit},
                status="success",
                duration_ms=duration_ms,
                records_count=len(candidates),
            )

            logger.info("DBLP API search returned %d candidates", len(candidates))

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
            logger.exception("DBLP API search failed")

        # --- China-First soft sorting ---
        if (query.extra or {}).get("china_first", True):
            china = [c for c in candidates if has_china_affiliation(c.institution, c.name)]
            non_china = [c for c in candidates if c not in china]
            candidates = china + non_china
            candidates = candidates[:query.limit]

        return candidates

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch DBLP author details.

        external_id is expected to be the author's DBLP key or URL path.
        """
        start = time.perf_counter()

        try:
            client = await self._get_client()
            # DBLP author detail can be fetched via the author API
            # external_id might be a URL like "https://dblp.org/pid/xx/xxxx.html"
            # or a key like "pid/xx/xxxx"
            search_key = external_id.replace("https://dblp.org/", "").replace(".html", "")
            params = {
                "q": search_key,
                "format": "json",
                "h": "1",
            }

            resp = await client.get(DBLP_SEARCH_API, params=params)
            resp.raise_for_status()
            data = resp.json()

            hits = data.get("result", {}).get("hits", {}).get("hit", [])
            if not hits:
                return None

            info = hits[0].get("info", {})
            author_name = info.get("author", "Unknown")

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"dblp_key": external_id},
                status="success",
                duration_ms=duration_ms,
                records_count=1,
            )

            return RawCandidate(
                name=author_name,
                paper_count=info.get("count", 0),
                profile_url=info.get("url"),
                raw_metadata={
                    "source": "dblp_api",
                    "dblp_key": info.get("key"),
                    "dblp_id": info.get("id"),
                },
            )

        except Exception:
            logger.exception("DBLP API detail failed for %s", external_id)
            return None

    async def check_health(self) -> HealthStatus:
        """Check DBLP API health."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get(DBLP_SEARCH_API, params={"q": "test", "format": "json", "h": 1})
            resp.raise_for_status()
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(healthy=True, latency_ms=latency_ms)

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                healthy=False,
                latency_ms=latency_ms,
                error_message=str(e),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
