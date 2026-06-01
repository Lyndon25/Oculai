"""Baidu Search and Baidu Scholar data sources.

BaiduSearch uses the `baidusearch` PyPI package (unofficial web scraper by
amazingcoderxyz). It wraps the synchronous scraper in asyncio.to_thread.

BaiduScholar uses the official Baidu Qianfan (千帆) Scholar Search API:
  GET https://qianfan.baidubce.com/v2/tools/baidu_scholar/search

Requirements:
    pip install baidusearch    # for BaiduSearchSource only
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

# baidusearch (no hyphen) is the actual package on PyPI.
_BAIDU_SEARCH_AVAILABLE = False
try:
    from baidusearch.baidusearch import search as _baidusearch_sync  # type: ignore[import-untyped]
    _BAIDU_SEARCH_AVAILABLE = True
except ImportError:
    pass

QIANFAN_SCHOLAR_URL = "https://qianfan.baidubce.com/v2/tools/baidu_scholar/search"


class BaiduScholarSource(IDataSource):
    """Baidu Scholar (百度学术) via Qianfan API.

    Uses Baidu's official Qianfan Scholar Search API to search Chinese and
    English academic literature. Covers journals, conference papers, theses,
    and dissertations indexed by Baidu Scholar (xueshu.baidu.com).

    Requires BAIDU_API_KEY set in .env (same key as BaiduQianfanSource).
    Endpoint: GET /v2/tools/baidu_scholar/search
    """

    name = "baidu_scholar"
    source_type = "api"
    description = (
        "Search Baidu Scholar (百度学术) via the Qianfan API for Chinese and "
        "English academic literature. Covers journals, conference papers, theses, "
        "and dissertations. Essential for discovering Chinese academic candidates. "
        "Requires BAIDU_API_KEY."
    )
    supported_operations = ["search"]
    id_field_map = {"baidu_scholar": "paper_id"}
    example_queries = [
        "大语言模型 预训练",
        "自然语言处理 深度学习",
        "计算机视觉 目标检测",
        "强化学习 机器人",
        "图神经网络 表示学习",
    ]
    auth_required = True
    rate_limit_notes = "QPS-based rate limiting. Use conservative rates (~1 req/3s)."

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.baidu_api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                },
                timeout=30.0,
            )
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search Baidu Scholar for academic literature by keywords."""
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

            resp = await client.get(
                QIANFAN_SCHOLAR_URL,
                params={
                    "wd": keywords,
                    "pageNum": 0,
                    "enable_abstract": "true",
                },
            )

            if resp.status_code == 404:
                logger.warning("Baidu Scholar API endpoint not available (404)")
                await log_source_call(
                    source_name=self.name,
                    source_type=self.source_type,
                    query_params={"keywords": query.keywords},
                    status="failed",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    error_message="Baidu Scholar endpoint unavailable (may be in beta)",
                )
                return []

            if resp.status_code == 429:
                logger.warning("Baidu Scholar rate limited (429)")
                await log_source_call(
                    source_name=self.name,
                    source_type=self.source_type,
                    query_params={"keywords": query.keywords},
                    status="rate_limited",
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    error_message="Baidu Scholar QPS limit exceeded",
                )
                return []

            resp.raise_for_status()
            data = resp.json()

            # Parse scholar results — expected format: {"results": [...], "total": N}
            items = data.get("results", data.get("data", []))
            for item in items[: query.limit]:
                title = item.get("title", "") or ""
                authors = item.get("authors") or item.get("author_name", "")
                abstract = item.get("abstract") or item.get("snippet", "") or ""
                paper_id = item.get("paperId") or item.get("paper_id", "")
                year = item.get("year") or item.get("pub_year", "")
                journal = item.get("journal") or item.get("publication", "")
                url = item.get("url") or item.get("paper_url", "")

                # Never fall back to paper title as a person's name.
                if authors:
                    name = str(authors)
                    confidence = "high"
                    extraction_method = "direct"
                else:
                    name = "Unknown"
                    confidence = "low"
                    extraction_method = "unverified"

                candidates.append(
                    RawCandidate(
                        name=name,
                        institution=journal,
                        research_areas=[abstract[:500]] if abstract else None,
                        profile_url=url or None,
                        raw_metadata={
                            "source": "baidu_scholar",
                            "title": title,
                            "authors": authors,
                            "abstract": abstract,
                            "paper_id": paper_id,
                            "year": year,
                            "journal": journal,
                            "url": url,
                        },
                        result_type="paper",
                        confidence=confidence,
                        extraction_method=extraction_method,
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
            logger.error("Baidu Scholar search failed: %s", error_msg)

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
            logger.exception("Baidu Scholar search failed")

        return candidates

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch paper details by paper_id from Baidu Scholar."""
        if not self._api_key:
            return None
        try:
            client = await self._get_client()
            resp = await client.get(
                QIANFAN_SCHOLAR_URL,
                params={"wd": external_id, "pageNum": 0, "enable_abstract": "true"},
            )
            if resp.status_code in (404, 429):
                return None
            resp.raise_for_status()
            data = resp.json()
            items = data.get("results", data.get("data", []))
            if items:
                item = items[0]
                authors = item.get("authors")
                title = item.get("title", "")
                if authors:
                    name = authors
                    confidence = "high"
                    extraction_method = "direct"
                else:
                    name = "Unknown"
                    confidence = "low"
                    extraction_method = "unverified"
                return RawCandidate(
                    name=name,
                    profile_url=item.get("url"),
                    raw_metadata={
                        "source": "baidu_scholar",
                        "paper_id": external_id,
                        "title": title,
                        "abstract": item.get("abstract"),
                    },
                    result_type="paper",
                    confidence=confidence,
                    extraction_method=extraction_method,
                )
            return None
        except Exception:
            logger.exception("Baidu Scholar get_detail failed for %s", external_id)
            return None

    async def check_health(self) -> HealthStatus:
        """Check Baidu Scholar API health with a minimal query."""
        if not self._api_key:
            return HealthStatus(
                healthy=False, latency_ms=0,
                error_message="BAIDU_API_KEY not configured",
            )
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get(
                QIANFAN_SCHOLAR_URL,
                params={"wd": "test", "pageNum": 0},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code == 200:
                return HealthStatus(healthy=True, latency_ms=latency_ms)
            elif resp.status_code == 429:
                return HealthStatus(healthy=True, latency_ms=latency_ms)
            elif resp.status_code == 404:
                return HealthStatus(
                    healthy=False, latency_ms=latency_ms,
                    error_message="Baidu Scholar endpoint not available (may be in beta)",
                )
            else:
                return HealthStatus(
                    healthy=False, latency_ms=latency_ms,
                    error_message=f"HTTP {resp.status_code}",
                )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return HealthStatus(
                healthy=False, latency_ms=latency_ms, error_message=str(e),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class BaiduSearchSource(IDataSource):
    """Baidu Web Search (百度搜索) data source.

    General web search via Baidu for discovering candidates mentioned in
    news, company pages, personal homepages, and Chinese tech media.

    Uses the baidusearch PyPI package (unofficial web scraper).
    Install: pip install baidusearch
    """

    name = "baidu"
    source_type = "api"
    description = (
        "Search Baidu (百度) for candidate discovery across Chinese web sources. "
        "Useful for finding candidates mentioned in news, company sites, tech forums, "
        "and personal homepages that are not indexed by Western search engines. "
        "Requires: pip install baidusearch"
    )
    supported_operations = ["search"]
    id_field_map = {}
    example_queries = [
        "大模型研究员 清华大学",
        "算法工程师 阿里巴巴 达摩院",
        "NLP 研究员 北京大学",
        "AI 科学家 字节跳动",
    ]
    auth_required = False
    rate_limit_notes = "Unofficial scraper — use conservatively (~1 req/5s) to avoid IP bans."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": "Oculai-TalentBot/1.0"},
                timeout=30.0,
            )
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search Baidu web for candidate mentions."""
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

        if not _BAIDU_SEARCH_AVAILABLE:
            logger.warning(
                "baidusearch not installed. Install with: pip install baidusearch"
            )
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=0,
                error_message="baidusearch package not installed — pip install baidusearch",
            )
            return []

        candidates: list[RawCandidate] = []
        try:
            keywords = " ".join(query.keywords)
            # baidusearch is synchronous — run in thread to avoid blocking
            results = await asyncio.to_thread(
                _baidusearch_sync, keywords
            )

            for r in results[: min(query.limit, 30)]:
                title = r.get("title", "") if isinstance(r, dict) else str(r)
                url = r.get("url", "") if isinstance(r, dict) else ""
                snippet = r.get("abstract", "") if isinstance(r, dict) else ""

                candidates.append(
                    RawCandidate(
                        name=title[:200],
                        profile_url=url or None,
                        raw_metadata={
                            "source": "baidu_search",
                            "snippet": snippet,
                            "url": url,
                        },
                        result_type="web_page",
                        confidence="low",
                        extraction_method="unverified",
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
            logger.exception("Baidu search failed")

        return candidates

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Baidu search has no detail endpoint — URLs can be fetched with homepage source."""
        return None

    async def check_health(self) -> HealthStatus:
        if not _BAIDU_SEARCH_AVAILABLE:
            return HealthStatus(
                healthy=False, latency_ms=0,
                error_message="baidusearch package not installed — pip install baidusearch",
            )
        return HealthStatus(healthy=True, latency_ms=0)
