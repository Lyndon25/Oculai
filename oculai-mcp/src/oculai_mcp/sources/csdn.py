"""CSDN (Chinese Software Developer Network) data source.

Uses the public CSDN search API (so.csdn.net) for content discovery and
blog.csdn.net profile pages for user detail. No authentication required.

Search: GET https://so.csdn.net/api/v3/search (blog content → usernames)
Profile: GET https://blog.csdn.net/{username} (HTML parsing)
"""

import logging
import re
import time
from typing import Any
from urllib.parse import quote_plus

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

CSDN_SEARCH_URL = "https://so.csdn.net/api/v3/search"
CSDN_BLOG_URL = "https://blog.csdn.net"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class CSDNSource(IDataSource):
    """CSDN (Chinese Software Developer Network) data source.

    Searches CSDN blog content to discover Chinese developers and engineers.
    Extracts usernames from blog search results and fetches detailed profile
    info from user blog pages. Covers technical bloggers sharing code
    tutorials, project experiences, and career insights.

    No API key required.
    """

    name = "csdn"
    source_type = "api"
    description = (
        "Search CSDN (中国开发者网络), a Chinese technical blog platform, "
        "for candidate discovery. Covers Chinese developers and engineers "
        "who publish technical content. Returns blog statistics, rank, and "
        "article categories. No API key required."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"csdn": "username"}
    example_queries = [
        "大模型 深度学习 实战",
        "架构设计 微服务 高并发",
        "算法工程师 推荐系统",
        "计算机视觉 目标检测 YOLO",
        "后端开发 Go 分布式",
    ]
    auth_required = False
    rate_limit_notes = "Unofficial scraping — use ~1 req/2s to avoid IP blocks."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=_BROWSER_HEADERS,
                timeout=15.0,
            )
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search CSDN blog content and extract unique user profiles.

        CSDN search returns blog entries by various authors. This method
        deduplicates by username and returns the most relevant authors.
        """
        start = time.perf_counter()
        candidates: list[RawCandidate] = []
        seen_usernames: set[str] = set()

        try:
            client = await self._get_client()
            keywords = " ".join(query.keywords)
            # CSDN search API expects URL-encoded query string
            encoded_q = quote_plus(keywords)

            resp = await client.get(
                CSDN_SEARCH_URL,
                params={
                    "q": encoded_q,
                    "t": "blog",
                    "p": 1,
                    "s": "new",
                    "o": "desc",
                    "l": "\"\"",
                    "f": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # CSDN search API returns nested structure; try multiple paths
            items: list[Any] = []
            if isinstance(data, dict):
                if "result_vos" in data:
                    items = data.get("result_vos", [])
                else:
                    inner = data.get("data", {})
                    if isinstance(inner, dict):
                        items = inner.get("list", [])
                    elif isinstance(inner, list):
                        items = inner
            elif isinstance(data, list):
                items = data

            logger.debug("CSDN search returned %d raw items for query '%s'", len(items), keywords)

            for item in items:
                if not isinstance(item, dict):
                    continue

                # Try multiple field paths for author identification
                username = (
                    item.get("username")
                    or item.get("user_name")
                    or (item.get("author") or {}).get("username")
                    or (item.get("author") or {}).get("user_name")
                    or item.get("nickname")
                    or item.get("author_name")
                    or ""
                ).strip()
                if not username or username in seen_usernames:
                    continue
                seen_usernames.add(username)

                title = item.get("title", "") or ""
                description = (
                    item.get("description")
                    or item.get("summary")
                    or item.get("digest")
                    or item.get("content", "")[:200]
                    or ""
                )
                article_url = item.get("url", "") or item.get("article_url", "") or ""

                candidates.append(
                    RawCandidate(
                        name=username,
                        profile_url=f"{CSDN_BLOG_URL}/{username}",
                        raw_metadata={
                            "source": "csdn",
                            "username": username,
                            "article_title": title,
                            "article_description": description[:300] if description else "",
                            "article_url": article_url,
                            "article_type": item.get("type", ""),
                        },
                    )
                )

                if len(candidates) >= query.limit:
                    break

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
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
            logger.error("CSDN search failed: %s", error_msg)

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
            logger.exception("CSDN search failed")

        return candidates

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch detailed CSDN profile by username.

        Parses the user's CSDN blog page for profile statistics and
        recent article topics.
        """
        try:
            client = await self._get_client()
            resp = await client.get(f"{CSDN_BLOG_URL}/{external_id}")
            if resp.status_code != 200:
                return None

            html = resp.text
            profile = self._parse_profile_page(html, external_id)

            return RawCandidate(
                name=profile.get("nickname", external_id),
                profile_url=f"{CSDN_BLOG_URL}/{external_id}",
                raw_metadata={
                    "source": "csdn",
                    "username": external_id,
                    **profile,
                },
            )

        except Exception:
            logger.exception("CSDN get_detail failed for %s", external_id)
            return None

    def _parse_profile_page(self, html: str, username: str) -> dict[str, Any]:
        """Parse CSDN blog profile page for user info.

        Uses regex and string extraction — no HTML parser dependency.
        CSDN pages embed profile data in predictable HTML patterns and
        JSON-LD script tags.
        """
        profile: dict[str, Any] = {"username": username}

        # Extract nickname from title tag
        title_match = re.search(r"<title>\s*([^<]+?)(?:\s*-\s*CSDN博客)?\s*</title>", html)
        if title_match:
            profile["nickname"] = title_match.group(1).strip()

        # Extract article stats from common CSDN page patterns
        # Profile statistics are often in data attributes or specific spans
        stats: dict[str, int] = {}

        # Original articles count
        m = re.search(r'原创[：:\s]*(\d+)', html)
        if m:
            stats["original_articles"] = int(m.group(1))

        # Fans count
        m = re.search(r'粉丝[：:\s]*(\d+)', html)
        if m:
            stats["fans_count"] = int(m.group(1))

        # Rank
        m = re.search(r'等级[：:\s]*[\w\d]*?(\d+)', html)
        if m:
            stats["rank_level"] = int(m.group(1))

        # Total visits
        m = re.search(r'访问[：:\s]*(\d+)', html)
        if m:
            stats["total_visits"] = int(m.group(1))

        # Total articles (another common pattern)
        m = re.search(r'文章[：:\s]*(\d+)', html)
        if m:
            stats["total_articles"] = int(m.group(1))

        # Comments count
        m = re.search(r'评论[：:\s]*(\d+)', html)
        if m:
            stats["comments_count"] = int(m.group(1))

        profile["stats"] = stats

        # Extract categories/tags from the blog page
        categories = re.findall(
            r'<span\s+class=["\']?category["\']?[^>]*>\s*([^<]+)\s*</span>',
            html,
        )
        if not categories:
            # Try alternate pattern
            categories = re.findall(
                r'class="tag"[^>]*>\s*([^<]+)\s*<',
                html,
            )
        profile["categories"] = list(set(c.strip() for c in categories if c.strip()))

        # Try to extract the JSON-LD structured data
        ld_json_match = re.search(
            r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if ld_json_match:
            profile["has_structured_data"] = True

        # Extract description/motto
        desc_match = re.search(
            r'<meta\s+name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
            html,
        )
        if desc_match:
            profile["description"] = desc_match.group(1).strip()[:500]

        return profile

    async def check_health(self) -> HealthStatus:
        """Check CSDN availability with a minimal request."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get(
                CSDN_SEARCH_URL,
                params={"q": "test", "t": "blog", "p": 1, "size": 1},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            if resp.status_code == 200:
                return HealthStatus(healthy=True, latency_ms=latency_ms)
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
