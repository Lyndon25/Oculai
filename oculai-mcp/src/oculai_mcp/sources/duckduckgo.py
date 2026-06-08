"""DuckDuckGo Web Search data source.

General web search via DuckDuckGo for discovering candidates mentioned in
news, blogs, company pages, and tech forums.

No API key required. Uses the duckduckgo-search PyPI package.
Install: pip install duckduckgo-search
"""

import asyncio
import logging
import re
import time
from typing import Any

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, try_consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

_DUCKDUCKGO_AVAILABLE = False
try:
    from duckduckgo_search import DDGS  # type: ignore[import-untyped]
    _DUCKDUCKGO_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Person-name extraction helpers
# ---------------------------------------------------------------------------

_NAME_SEPARATOR_RE = re.compile(r"^([^|\-·\-\s]{2,30})\s*[|\-·\-]\s*")
_CHINESE_NAME_RE = re.compile(r"^[一-鿿]{2,4}")
_AUTHOR_PREFIX_RE = re.compile(r"(?:作者|by|writer)[:\s]*(.{2,30})", re.I)


def _extract_person_name_from_title(title: str, snippet: str) -> str | None:
    """Try to extract a person's name from a search result title/snippet."""
    if not title:
        return None

    title = title.strip()

    # Pattern 1: name before separator (e.g., "张三 - 个人主页", "John Doe | LinkedIn")
    m = _NAME_SEPARATOR_RE.match(title)
    if m:
        candidate = m.group(1).strip()
        if _is_likely_person_name(candidate):
            return candidate

    # Pattern 2: Chinese name at the very start (2-4 hanzi)
    m = _CHINESE_NAME_RE.match(title)
    if m:
        return m.group(0)

    # Pattern 3: "作者：xxx" or "by xxx" in snippet
    if snippet:
        m = _AUTHOR_PREFIX_RE.search(snippet)
        if m:
            candidate = m.group(1).strip()
            if _is_likely_person_name(candidate):
                return candidate

    return None


def _is_likely_person_name(text: str) -> bool:
    """Quick heuristic: does this look like a person name?"""
    if not text or len(text) < 2 or len(text) > 30:
        return False
    if any(c in text for c in "《》「」『』"):
        return False
    if re.search(r"[:：].{3,}", text):
        return False
    if not re.search(r"[a-zA-Z一-鿿]", text):
        return False
    if text.isdigit():
        return False
    return True


class DuckDuckGoSource(IDataSource):
    """DuckDuckGo Web Search data source.

    General web search via DuckDuckGo for discovering candidates mentioned in
    news, blogs, company pages, personal homepages, and tech forums.

    No API key required. Free to use. Works well as a fallback when
    Tavily/Exa keys are unavailable or quotas are exhausted.
    """

    name = "duckduckgo"
    source_type = "api"
    description = (
        "Search DuckDuckGo for candidate discovery across global web sources. "
        "Useful for finding candidates mentioned in news, blogs, company sites, "
        "and personal homepages. No API key required. Free. "
        "Requires: pip install duckduckgo-search"
    )
    supported_operations = ["search"]
    id_field_map = {}
    example_queries = [
        "machine learning researcher Stanford",
        "NLP scientist Google DeepMind",
        "AI engineer Beijing",
        "computer vision professor Tsinghua",
    ]
    auth_required = False
    rate_limit_notes = "Rate limited by DuckDuckGo servers. Use conservatively (~1 req/3s)."

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search DuckDuckGo web for candidate mentions."""
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

        if not _DUCKDUCKGO_AVAILABLE:
            logger.warning(
                "duckduckgo-search not installed. Install with: pip install duckduckgo-search"
            )
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=0,
                error_message="duckduckgo-search package not installed — pip install duckduckgo-search",
            )
            return []

        candidates: list[RawCandidate] = []
        try:
            keywords = " ".join(query.keywords)
            max_results = min(query.limit, 20)

            # duckduckgo_search is synchronous — run in thread to avoid blocking
            def _do_search() -> list[dict[str, Any]]:
                with DDGS() as ddgs:
                    return list(ddgs.text(keywords, max_results=max_results))  # type: ignore[return-value]

            results = await asyncio.to_thread(_do_search)

            for r in results:
                title = r.get("title", "")
                url = r.get("href", "")
                snippet = r.get("body", "")

                name = _extract_person_name_from_title(title, snippet)
                if name:
                    result_type = "profile_page"
                    confidence = "medium"
                    extraction_method = "inferred"
                else:
                    name = "Unknown"
                    result_type = "web_page"
                    confidence = "low"
                    extraction_method = "unverified"

                candidates.append(
                    RawCandidate(
                        name=name,
                        profile_url=url or None,
                        raw_metadata={
                            "source": "duckduckgo",
                            "title": title,
                            "snippet": snippet,
                            "url": url,
                        },
                        result_type=result_type,
                        confidence=confidence,
                        extraction_method=extraction_method,
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
            logger.exception("DuckDuckGo search failed")

        return candidates

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """DuckDuckGo search has no detail endpoint — URLs can be fetched with homepage source."""
        return None

    async def check_health(self) -> HealthStatus:
        if not _DUCKDUCKGO_AVAILABLE:
            return HealthStatus(
                healthy=False,
                latency_ms=0,
                error_message="duckduckgo-search package not installed — pip install duckduckgo-search",
            )
        start = time.perf_counter()
        try:
            def _do_health_check() -> bool:
                with DDGS() as ddgs:
                    results = list(ddgs.text("test", max_results=1))
                    return len(results) > 0

            ok = await asyncio.to_thread(_do_health_check)
            latency_ms = int((time.perf_counter() - start) * 1000)
            if ok:
                return HealthStatus(healthy=True, latency_ms=latency_ms)
            return HealthStatus(
                healthy=False,
                latency_ms=latency_ms,
                error_message="DuckDuckGo returned no results for health check",
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return HealthStatus(
                healthy=False,
                latency_ms=latency_ms,
                error_message=str(e),
            )
