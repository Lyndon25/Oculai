"""Firecrawl Web Search data source.

General web search via Firecrawl for discovering candidates mentioned in
news, blogs, company pages, and tech forums.

Supports keyless mode (rate-limited per IP, works from Node.js/browsers).
For Python access, get a free API key at https://firecrawl.dev/app/api-keys
(1000 credits/month free).
"""

import logging
import re
import time
from typing import Any

import httpx

from oculai_mcp.config import get_settings
from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, try_consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

FIRECRAWL_API_BASE = "https://api.firecrawl.dev/v1"

# ---------------------------------------------------------------------------
# Person-name extraction helpers (shared pattern with DuckDuckGo source)
# ---------------------------------------------------------------------------

_NAME_SEPARATOR_RE = re.compile(r"^(.{1,60}?)\s+[|·-]\s+")
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


class FirecrawlSource(IDataSource):
    """Firecrawl Web Search data source.

    Uses Firecrawl's search API to discover candidates across the web.
    Supports keyless mode (rate-limited per IP) and authenticated mode
    (higher rate limits, 1000 free credits/month).

    Keyless mode works from browsers and Node.js. For Python access,
    set FIRECRAWL_API_KEY in .env (free key from firecrawl.dev).
    """

    name = "firecrawl"
    source_type = "api"
    description = (
        "Search the web via Firecrawl for candidate discovery across global "
        "web sources. Useful for finding candidates mentioned in news, blogs, "
        "company sites, and personal homepages. Keyless mode available "
        "(rate-limited per IP). Free API key gives 1000 credits/month. "
        "Get a key at: https://firecrawl.dev/app/api-keys"
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {}
    example_queries = [
        "machine learning researcher Stanford",
        "NLP scientist Google DeepMind",
        "AI engineer Beijing",
        "computer vision professor Tsinghua",
    ]
    auth_required = False
    rate_limit_notes = (
        "Keyless: rate-limited per IP (~10 req/min). "
        "With API key: 1000 free credits/month, higher limits."
    )

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search Firecrawl web for candidate mentions."""
        start = time.monotonic()

        if not await check_quota(self.name):
            msg = f"Firecrawl quota exceeded for {self.name}"
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="rate_limited",
                duration_ms=0,
                error_message=msg,
            )
            raise RuntimeError(msg)

        settings = get_settings()
        api_key = getattr(settings, "firecrawl_api_key", None)

        candidates: list[RawCandidate] = []
        try:
            keywords = " ".join(query.keywords)
            max_results = min(query.limit, 20)

            async with httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "Oculai/1.0 (+https://github.com/oculai)"},
            ) as client:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                body: dict[str, Any] = {"query": keywords, "limit": max_results}

                resp = await client.post(
                    f"{FIRECRAWL_API_BASE}/search", json=body, headers=headers
                )

                if resp.status_code == 403 and not api_key:
                    msg = (
                        "Firecrawl keyless blocked from Python (TLS fingerprint). "
                        "Get a free API key at https://firecrawl.dev/app/api-keys"
                    )
                    logger.warning(msg)
                    await log_source_call(
                        source_name=self.name,
                        source_type=self.source_type,
                        query_params={"keywords": query.keywords},
                        status="failed",
                        duration_ms=int((time.monotonic() - start) * 1000),
                        error_message=msg,
                    )
                    raise RuntimeError(msg)

                resp.raise_for_status()
                data = resp.json()

                if not data.get("success"):
                    raise RuntimeError(
                        data.get("error", "Firecrawl search returned unsuccessful response")
                    )

                for r in data.get("data", [])[:max_results]:
                    title = r.get("title", "")
                    url = r.get("url", "")
                    snippet = r.get("description", "")

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
                                "source": "firecrawl",
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
            duration_ms = int((time.monotonic() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords, "limit": query.limit},
                status="success",
                duration_ms=duration_ms,
                records_count=len(candidates),
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=duration_ms,
                error_message=str(e),
            )
            logger.exception("Firecrawl search failed")

        return candidates

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Scrape a profile URL via Firecrawl and extract candidate details."""
        start = time.monotonic()
        settings = get_settings()
        api_key = getattr(settings, "firecrawl_api_key", None)

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "Oculai/1.0 (+https://github.com/oculai)"},
            ) as client:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                body = {"url": external_id, "formats": ["markdown"]}
                resp = await client.post(
                    f"{FIRECRAWL_API_BASE}/scrape", json=body, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()

                if not data.get("success"):
                    return None

                markdown = (data.get("data") or {}).get("markdown", "")
                metadata = (data.get("data") or {}).get("metadata", {})
                title = metadata.get("title", "")

                # Try to extract name from title
                name = _extract_person_name_from_title(title, "") or title or "Unknown"

                duration_ms = int((time.monotonic() - start) * 1000)
                await log_source_call(
                    source_name=f"{self.name}_detail",
                    source_type=self.source_type,
                    query_params={"external_id": external_id},
                    status="success",
                    duration_ms=duration_ms,
                )

                return RawCandidate(
                    name=name,
                    profile_url=external_id,
                    raw_metadata={
                        "source": "firecrawl",
                        "title": title,
                        "markdown_preview": markdown[:500],
                        "url": external_id,
                    },
                    result_type="profile_page",
                    confidence="medium",
                    extraction_method="direct",
                )

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            await log_source_call(
                source_name=f"{self.name}_detail",
                source_type=self.source_type,
                query_params={"external_id": external_id},
                status="failed",
                duration_ms=duration_ms,
                error_message=str(e),
            )
            logger.exception("Firecrawl get_detail failed")
            return None

    async def check_health(self) -> HealthStatus:
        """Ping Firecrawl API to verify connectivity."""
        start = time.monotonic()
        settings = get_settings()
        api_key = getattr(settings, "firecrawl_api_key", None)

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "Oculai/1.0 (+https://github.com/oculai)"},
            ) as client:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                body = {"query": "test", "limit": 1}
                resp = await client.post(
                    f"{FIRECRAWL_API_BASE}/search", json=body, headers=headers
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code == 200:
                    return HealthStatus(healthy=True, latency_ms=latency_ms)
                return HealthStatus(
                    healthy=False,
                    latency_ms=latency_ms,
                    error_message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return HealthStatus(
                healthy=False,
                latency_ms=latency_ms,
                error_message=str(e),
            )
