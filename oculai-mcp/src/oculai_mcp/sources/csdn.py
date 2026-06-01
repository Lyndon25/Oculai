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
                elif "data" in data:
                    inner = data.get("data", {})
                    if isinstance(inner, dict):
                        items = inner.get("list", inner.get("result_vos", inner.get("items", [])))
                    elif isinstance(inner, list):
                        items = inner
                elif "list" in data:
                    items = data.get("list", [])
                elif "items" in data:
                    items = data.get("items", [])
                elif "results" in data:
                    items = data.get("results", [])
            elif isinstance(data, list):
                items = data

            logger.info("CSDN search returned %d raw items for query '%s' (top-level keys: %s)",
                        len(items), keywords, list(data.keys())[:10] if isinstance(data, dict) else "list")

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

                # Try to fetch detailed profile for better name and institution
                detail = await self.get_detail(username)
                name = username
                institution: str | None = None
                extraction_method = "unverified"
                if detail:
                    if detail.name and detail.name != username:
                        name = detail.name
                    institution = detail.institution
                    extraction_method = "direct"

                title = item.get("title", "") or ""
                description = (
                    item.get("description")
                    or item.get("summary")
                    or item.get("digest")
                    or item.get("content", "")[:200]
                    or ""
                )
                article_url = item.get("url", "") or item.get("article_url", "") or ""

                raw_metadata: dict[str, Any] = {
                    "source": "csdn",
                    "username": username,
                    "article_title": title,
                    "article_description": description[:300] if description else "",
                    "article_url": article_url,
                    "article_type": item.get("type", ""),
                }
                if detail and detail.raw_metadata:
                    raw_metadata.update(detail.raw_metadata)

                candidates.append(
                    RawCandidate(
                        name=name,
                        institution=institution,
                        profile_url=f"{CSDN_BLOG_URL}/{username}",
                        raw_metadata=raw_metadata,
                        result_type="profile_page",
                        confidence="medium",
                        extraction_method=extraction_method,
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
        JSON-LD script tags. Multiple fallback patterns are tried for
        resilience against page structure changes.
        """
        profile: dict[str, Any] = {"username": username}

        # Extract nickname from title tag
        title_match = re.search(r"<title>\s*([^<]+?)(?:\s*-\s*CSDN博客)?\s*</title>", html)
        if title_match:
            profile["nickname"] = title_match.group(1).strip()

        # Fallback: nickname from meta og:title
        if not profile.get("nickname"):
            og_title_match = re.search(
                r'<meta\s+property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
                html,
            )
            if og_title_match:
                raw = og_title_match.group(1).strip()
                profile["nickname"] = raw.replace("-CSDN博客", "").replace("- CSDN博客", "").strip()

        # Fallback: nickname from JSON-LD structured data
        ld_json_match = re.search(
            r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        if ld_json_match:
            profile["has_structured_data"] = True
            ld_text = ld_json_match.group(1)
            # Try to extract name from JSON-LD
            name_m = re.search(r'"name"\s*:\s*"([^"]+)"', ld_text)
            if name_m and not profile.get("nickname"):
                profile["nickname"] = name_m.group(1).strip()
            # Try to extract description from JSON-LD
            desc_m = re.search(r'"description"\s*:\s*"([^"]+)"', ld_text)
            if desc_m and not profile.get("description"):
                profile["description"] = desc_m.group(1).strip()[:500]

        # Extract article stats from common CSDN page patterns
        # Profile statistics are often in data attributes or specific spans
        stats: dict[str, int] = {}

        # Original articles count — try multiple patterns
        for pattern in [
            r'原创[：:\s]*(\d+)',
            r'class=["\'][^"\']*?count-item[^"\']*?["\'][^>]*>\s*原创\s*[：:\s]*<[^>]*>\s*(\d+)',
            r'data-title=["\']原创["\'][^>]*>\s*(\d+)',
        ]:
            m = re.search(pattern, html)
            if m:
                stats["original_articles"] = int(m.group(1))
                break

        # Fans count — try multiple patterns
        for pattern in [
            r'粉丝[：:\s]*(\d+)',
            r'class=["\'][^"\']*?count-item[^"\']*?["\'][^>]*>\s*粉丝\s*[：:\s]*<[^>]*>\s*(\d+)',
            r'data-title=["\']粉丝["\'][^>]*>\s*(\d+)',
        ]:
            m = re.search(pattern, html)
            if m:
                stats["fans_count"] = int(m.group(1))
                break

        # Rank / level
        for pattern in [
            r'等级[：:\s]*[\w\d]*?(\d+)',
            r'class=["\'][^"\']*?level[^"\']*?["\'][^>]*>\s*(\d+)',
        ]:
            m = re.search(pattern, html)
            if m:
                stats["rank_level"] = int(m.group(1))
                break

        # Total visits
        for pattern in [
            r'访问[：:\s]*(\d+)',
            r'class=["\'][^"\']*?count-item[^"\']*?["\'][^>]*>\s*访问\s*[：:\s]*<[^>]*>\s*(\d+)',
            r'data-title=["\']访问["\'][^>]*>\s*(\d+)',
        ]:
            m = re.search(pattern, html)
            if m:
                stats["total_visits"] = int(m.group(1))
                break

        # Total articles
        for pattern in [
            r'文章[：:\s]*(\d+)',
            r'class=["\'][^"\']*?count-item[^"\']*?["\'][^>]*>\s*文章\s*[：:\s]*<[^>]*>\s*(\d+)',
            r'data-title=["\']文章["\'][^>]*>\s*(\d+)',
        ]:
            m = re.search(pattern, html)
            if m:
                stats["total_articles"] = int(m.group(1))
                break

        # Comments count
        for pattern in [
            r'评论[：:\s]*(\d+)',
            r'class=["\'][^"\']*?count-item[^"\']*?["\'][^>]*>\s*评论\s*[：:\s]*<[^>]*>\s*(\d+)',
            r'data-title=["\']评论["\'][^>]*>\s*(\d+)',
        ]:
            m = re.search(pattern, html)
            if m:
                stats["comments_count"] = int(m.group(1))
                break

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
        if not categories:
            # Try newer CSDN pattern
            categories = re.findall(
                r'class=["\'][^"\']*?tag[^"\']*?["\'][^>]*>\s*([^<]+?)\s*</a>',
                html,
            )
        profile["categories"] = list(set(c.strip() for c in categories if c.strip()))

        # Extract company from profile page (common in newer CSDN layouts)
        company_patterns = [
            r'公司[：:\s]*<[^>]*>\s*([^<]+)\s*</',
            r'class=["\'][^"\']*?company[^"\']*?["\'][^>]*>\s*([^<]+)\s*</',
            r'所在公司[：:\s]*([^<\n]+?)(?:\n|<)',
        ]
        for pattern in company_patterns:
            cm = re.search(pattern, html)
            if cm:
                company_val = cm.group(1).strip()
                if company_val and company_val not in ("暂无", "无", "-", ""):
                    profile["company"] = company_val
                    break

        # Extract description/motto from meta tag
        desc_match = re.search(
            r'<meta\s+name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
            html,
        )
        if desc_match and not profile.get("description"):
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
