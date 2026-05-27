"""Baidu Qianfan (千帆) AI Search data source.

Uses the official Baidu Qianfan AppBuilder AI Search API for web search
across Chinese web sources. This is the official Baidu Cloud API — far more
reliable than third-party scrapers.

Endpoint: https://qianfan.baidubce.com/v2/ai_search/web_search
Docs: https://cloud.baidu.com/doc/qianfan-api/s/Hmbu8m06u

Free tier: 100 calls/day. Paid: up to 100,000 calls/day.

Auth: Bearer token (bce-v3/ALTAK-xxx/xxx format).
Set BAIDU_API_KEY in .env to enable.
"""

import logging
import time
from typing import Any

import httpx

from oculai_mcp.config import get_settings
from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

QIANFAN_SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"


class BaiduQianfanSource(IDataSource):
    """Baidu Qianfan (千帆) AI Search data source.

    Uses Baidu's official search API via the Qianfan AppBuilder platform.
    Covers the entire Chinese web indexed by Baidu — news, company pages,
    personal homepages, tech forums, and academic institution sites.

    Requires BAIDU_API_KEY set in .env (bce-v3/ALTAK-xxx/xxx format).
    Get key at: https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application
    """

    name = "baidu_qianfan"
    source_type = "api"
    description = (
        "Search Baidu via the official Qianfan (千帆) AI Search API. "
        "Covers Chinese web sources including news, company pages, tech forums, "
        "academic institution sites, and personal homepages. Ideal for discovering "
        "candidates in the Chinese tech ecosystem. "
        "Requires BAIDU_API_KEY (free: 100 calls/day)."
    )
    supported_operations = ["search"]
    id_field_map = {}
    example_queries = [
        "大模型研究员 清华大学",
        "算法工程师 阿里巴巴 达摩院",
        "NLP 科学家 北京大学",
        "AI 技术总监 字节跳动 百度",
        "计算机视觉 研究员 上海人工智能实验室",
    ]
    auth_required = True
    rate_limit_notes = "Free: 100 calls/day. Paid: up to 100,000 calls/day."

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.baidu_api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                timeout=30.0,
            )
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search Baidu via Qianfan AI Search API."""
        start = time.perf_counter()

        if not self._api_key:
            logger.warning("BAIDU_API_KEY not configured")
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=0,
                error_message="BAIDU_API_KEY not configured in .env",
            )
            return []

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
            keywords = " ".join(query.keywords)

            body: dict[str, Any] = {
                "messages": [{"content": keywords, "role": "user"}],
                "search_source": "baidu_search_v2",
                "resource_type_filter": [
                    {"type": "web", "top_k": min(query.limit, 20)}
                ],
            }

            # Add institution filter if provided
            if query.institutions:
                body["messages"][0]["content"] = (
                    f"{keywords} " + " OR ".join(query.institutions)
                )

            resp = await client.post(QIANFAN_SEARCH_URL, json=body)
            resp.raise_for_status()
            data = resp.json()

            results = self._extract_results(data)
            for r in results[: query.limit]:
                title = r.get("title", "") or ""
                url = r.get("url", "") or ""
                snippet = r.get("snippet") or r.get("content", "") or ""
                website = r.get("website", "")
                date = r.get("date", "")
                rerank_score = r.get("rerank_score", 0)
                authority_score = r.get("authority_score", 0)

                candidates.append(
                    RawCandidate(
                        name=title[:200] if title else "Unknown",
                        profile_url=url or None,
                        raw_metadata={
                            "source": "baidu_qianfan",
                            "title": title,
                            "snippet": snippet,
                            "url": url,
                            "website": website,
                            "date": date,
                            "rerank_score": rerank_score,
                            "authority_score": authority_score,
                            "type": r.get("type", "web"),
                        },
                    )
                )

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

        except httpx.HTTPStatusError as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=duration_ms,
                error_message=error_msg,
            )
            logger.error("Qianfan search failed: %s", error_msg)

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
            logger.exception("Qianfan search failed")

        return candidates

    def _extract_results(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract search results from Qianfan API response.

        The web_search endpoint returns: {"request_id": "...", "references": [...]}
        Each reference has: id, url, title, date, content, snippet, type, website,
        rerank_score, authority_score.
        """
        # Primary format: references array (web_search endpoint)
        if "references" in data:
            return data["references"]

        # Alternative formats for other Qianfan endpoints
        if "results" in data:
            return data["results"]
        if "message" in data:
            msg = data["message"]
            if isinstance(msg, dict) and "search_results" in msg:
                return msg["search_results"]

        logger.warning("Unknown Qianfan response format: %s", list(data.keys())[:5])
        return []

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Qianfan search does not support detail lookup."""
        return None

    async def check_health(self) -> HealthStatus:
        """Check Qianfan API health with a minimal query."""
        if not self._api_key:
            return HealthStatus(
                healthy=False, latency_ms=0,
                error_message="BAIDU_API_KEY not configured",
            )
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.post(
                QIANFAN_SEARCH_URL,
                json={
                    "messages": [{"content": "test", "role": "user"}],
                    "search_source": "baidu_search_v2",
                    "resource_type_filter": [{"type": "web", "top_k": 1}],
                },
            )
            resp.raise_for_status()
            latency_ms = int((time.perf_counter() - start) * 1000)
            return HealthStatus(healthy=True, latency_ms=latency_ms)
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return HealthStatus(
                healthy=False, latency_ms=latency_ms, error_message=str(e),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
