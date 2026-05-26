"""Baidu Scholar and Baidu Search data sources.

Uses the `baidu-search` and `baidu-scholar-search` packages when available,
with a graceful fallback to plain HTTP search.

Requirements (optional):
    pip install baidu-search baidu-scholar-search

Without these packages, search returns an empty result set with a
helpful error message pointing to installation instructions.
"""

import logging
import time
from typing import Any

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

_BAIDU_SCHOLAR_AVAILABLE = False
try:
    import baidu_scholar_search  # type: ignore[import-untyped]
    _BAIDU_SCHOLAR_AVAILABLE = True
except ImportError:
    pass

_BAIDU_SEARCH_AVAILABLE = False
try:
    import baidu_search  # type: ignore[import-untyped]
    _BAIDU_SEARCH_AVAILABLE = True
except ImportError:
    pass


class BaiduScholarSource(IDataSource):
    """Baidu Scholar (百度学术) data source.

    Searches Chinese academic literature for authors, papers, and citations.
    Baidu Scholar indexes Chinese-language academic content that is often
    underrepresented in English-only databases like Semantic Scholar or OpenAlex.

    Requires: pip install baidu-scholar-search
    """

    name = "baidu_scholar"
    source_type = "api"
    description = (
        "Search Baidu Scholar (百度学术) for Chinese-language academic authors "
        "and publications. Covers Chinese journals, theses, and conference papers "
        "indexed by Baidu. Essential for Chinese candidate discovery."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"baidu_scholar": "profile_url"}
    example_queries = [
        "大语言模型 预训练",
        "自然语言处理 深度学习",
        "计算机视觉 目标检测",
        "强化学习 机器人",
        "图神经网络 表示学习",
    ]
    auth_required = False
    rate_limit_notes = "Baidu Scholar rate limits not documented. Use conservative rates (~1 req/3s)."

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
        """Search Baidu Scholar for academic authors by keywords."""
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

        if not _BAIDU_SCHOLAR_AVAILABLE:
            logger.warning(
                "baidu-scholar-search not installed. Install with: "
                "pip install baidu-scholar-search"
            )
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=0,
                error_message="baidu-scholar-search package not installed",
            )
            return []

        candidates: list[RawCandidate] = []
        try:
            keywords = " ".join(query.keywords)
            results = await baidu_scholar_search.search(
                keywords, topk=min(query.limit, 30)
            )

            for r in results:
                candidates.append(
                    RawCandidate(
                        name=r.get("author_name", "Unknown") if isinstance(r, dict) else str(r),
                        institution=None,
                        paper_count=0,
                        profile_url=None,
                        raw_metadata={
                            "source": "baidu_scholar",
                            "raw_result": r if isinstance(r, dict) else str(r),
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
        """Fetch detailed profile from Baidu Scholar."""
        if not _BAIDU_SCHOLAR_AVAILABLE:
            return None
        try:
            # Baidu Scholar detail lookup — external_id is typically a profile URL
            results = await baidu_scholar_search.search(external_id, topk=1)
            if results and isinstance(results[0], dict):
                r = results[0]
                return RawCandidate(
                    name=r.get("author_name", "Unknown"),
                    institution=r.get("affiliation"),
                    paper_count=r.get("paper_count", 0),
                    citation_count=r.get("citation_count", 0),
                    profile_url=r.get("profile_url"),
                    raw_metadata={"source": "baidu_scholar", "raw_result": r},
                )
            return None
        except Exception:
            logger.exception("Baidu Scholar get_detail failed for %s", external_id)
            return None

    async def check_health(self) -> HealthStatus:
        if not _BAIDU_SCHOLAR_AVAILABLE:
            return HealthStatus(
                healthy=False, latency_ms=0,
                error_message="baidu-scholar-search package not installed",
            )
        return HealthStatus(healthy=True, latency_ms=0)


class BaiduSearchSource(IDataSource):
    """Baidu Web Search (百度搜索) data source.

    General web search via Baidu for discovering candidates mentioned in
    news, company pages, personal homepages, and Chinese tech media.

    Requires: pip install baidu-search
    """

    name = "baidu"
    source_type = "api"
    description = (
        "Search Baidu (百度) for candidate discovery across Chinese web sources. "
        "Useful for finding candidates mentioned in news, company sites, tech forums, "
        "and personal homepages that are not indexed by Western search engines."
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
    rate_limit_notes = "Baidu web search may impose rate limits. Use conservatively."

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
            logger.warning("baidu-search not installed. Install with: pip install baidu-search")
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=0,
                error_message="baidu-search package not installed",
            )
            return []

        candidates: list[RawCandidate] = []
        try:
            keywords = " ".join(query.keywords)
            results = await baidu_search.search(keywords, topk=min(query.limit, 30))

            for r in results:
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
        return None

    async def check_health(self) -> HealthStatus:
        if not _BAIDU_SEARCH_AVAILABLE:
            return HealthStatus(
                healthy=False, latency_ms=0,
                error_message="baidu-search package not installed",
            )
        return HealthStatus(healthy=True, latency_ms=0)
