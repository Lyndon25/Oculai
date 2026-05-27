"""Zhihu (知乎) data source — Chinese Q&A and knowledge community.

Uses the public Zhihu API (zhihu.com/api/v4) for people search and profile
lookup. Read-only access with browser User-Agent headers — no login required.

Search: GET /api/v4/search_v3 (t=people)
Profile: GET /api/v4/people/{url_token}
"""

import logging
import time
from typing import Any

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

ZHIHU_SEARCH_URL = "https://www.zhihu.com/api/v4/search_v3"
ZHIHU_PEOPLE_URL = "https://www.zhihu.com/api/v4/people"

# Zhihu requires realistic browser headers to avoid 400/403 anti-bot responses
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.zhihu.com/search?type=people",
    "Origin": "https://www.zhihu.com",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "fetch",
}


class ZhihuSource(IDataSource):
    """Zhihu (知乎) Chinese knowledge community data source.

    Searches Zhihu user profiles via the public API. Covers Chinese
    professionals, researchers, and engineers with detailed profiles
    including education, employment history, and topical expertise.

    No API key required. Uses browser User-Agent for API access.
    """

    name = "zhihu"
    source_type = "api"
    description = (
        "Search Zhihu (知乎), a Chinese Q&A and knowledge platform, for "
        "candidate profiles. Covers professionals, researchers, and domain "
        "experts with education, employment history, topic expertise, and "
        "content contribution metrics. No API key required."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"zhihu": "url_token"}
    example_queries = [
        "大模型 算法工程师",
        "计算机视觉 研究员 博士",
        "自然语言处理 技术专家",
        "AI 架构师 字节跳动",
        "强化学习 机器人",
    ]
    auth_required = False
    rate_limit_notes = "Public API — use ~1 req/s to avoid rate limiting."

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
        """Search Zhihu people by keywords."""
        start = time.perf_counter()
        candidates: list[RawCandidate] = []

        try:
            client = await self._get_client()
            keywords = " ".join(query.keywords)

            resp = await client.get(
                ZHIHU_SEARCH_URL,
                params={
                    "q": keywords,
                    "t": "people",
                    "correction": "1",
                    "show_all_topics": "0",
                    "limit": min(query.limit, 20),
                    "offset": query.offset or 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            raw_items = data.get("data", [])

            for item in raw_items[: query.limit]:
                obj = item.get("object", {})
                if not obj.get("id"):
                    continue

                url_token = str(obj.get("id", ""))
                name = obj.get("name", "") or ""
                headline = obj.get("headline", "") or ""
                url = obj.get("url", "")

                # Extract employment/education from search result if available
                business = obj.get("business", {}) or {}
                company = business.get("name", "") if isinstance(business, dict) else ""

                candidates.append(
                    RawCandidate(
                        name=name,
                        institution=company,
                        profile_url=url or f"https://www.zhihu.com/people/{url_token}",
                        raw_metadata={
                            "source": "zhihu",
                            "url_token": url_token,
                            "headline": headline,
                            "gender": obj.get("gender", -1),
                            "follower_count": obj.get("follower_count", 0),
                            "answer_count": obj.get("answer_count", 0),
                            "article_count": obj.get("article_count", 0),
                            "voteup_count": obj.get("voteup_count", 0),
                            "avatar_url": obj.get("avatar_url", ""),
                        },
                    )
                )

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
            status_code = e.response.status_code
            if status_code == 400:
                error_msg = (
                    "Zhihu API returned HTTP 400 (anti-bot). "
                    "The search endpoint now requires authenticated session cookies. "
                    "Consider providing zhihu cookies via environment or disable zhihu source."
                )
            elif status_code == 403:
                error_msg = (
                    "Zhihu API returned HTTP 403 (access denied). "
                    "Anti-bot protection active. Cookies or CAPTCHA bypass may be required."
                )
            else:
                error_msg = f"HTTP {status_code}: {e.response.text[:200]}"
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=duration_ms,
                error_message=error_msg,
            )
            logger.error("Zhihu search failed: %s", error_msg)

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
            logger.exception("Zhihu search failed")

        return candidates

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch detailed Zhihu profile by url_token."""
        try:
            client = await self._get_client()
            resp = await client.get(f"{ZHIHU_PEOPLE_URL}/{external_id}")
            resp.raise_for_status()
            data = resp.json()
            if not data or not data.get("id"):
                return None

            url_token = str(data.get("id", ""))
            name = data.get("name", "") or ""
            headline = data.get("headline", "") or ""
            description = data.get("description", "") or ""

            # Extract company from employment history
            employments = data.get("employments", []) or []
            current_company = ""
            current_job = ""
            if employments:
                emp = employments[0]
                company_obj = emp.get("company", {}) or {}
                job_obj = emp.get("job", {}) or {}
                current_company = (
                    company_obj.get("name", "") if isinstance(company_obj, dict) else ""
                )
                current_job = (
                    job_obj.get("name", "") if isinstance(job_obj, dict) else ""
                )

            # Extract education
            educations = data.get("educations", []) or []
            schools = []
            for edu in educations:
                school_obj = edu.get("school", {}) or {}
                major_obj = edu.get("major", {}) or {}
                school_name = school_obj.get("name", "") if isinstance(school_obj, dict) else ""
                major_name = major_obj.get("name", "") if isinstance(major_obj, dict) else ""
                parts = [s for s in [school_name, major_name] if s]
                schools.append(" ".join(parts))

            # Extract topics of expertise
            topics = data.get("topics", []) or []
            topic_names = [t.get("name", "") for t in topics if isinstance(t, dict) and t.get("name")]

            business = data.get("business", {}) or {}
            business_name = business.get("name", "") if isinstance(business, dict) else ""

            return RawCandidate(
                name=name,
                institution=current_company or business_name,
                profile_url=f"https://www.zhihu.com/people/{url_token}",
                research_areas=topic_names if topic_names else None,
                raw_metadata={
                    "source": "zhihu",
                    "url_token": url_token,
                    "name": name,
                    "headline": headline,
                    "description": description,
                    "gender": data.get("gender", -1),
                    "company": current_company,
                    "job_title": current_job,
                    "business": business_name,
                    "education": schools,
                    "topics": topic_names,
                    "follower_count": data.get("follower_count", 0),
                    "following_count": data.get("following_count", 0),
                    "answer_count": data.get("answer_count", 0),
                    "article_count": data.get("article_count", 0),
                    "voteup_count": data.get("voteup_count", 0),
                    "thank_count": data.get("thank_count", 0),
                    "locations": [
                        loc.get("name", "") for loc in (data.get("locations", []) or [])
                        if isinstance(loc, dict) and loc.get("name")
                    ],
                    "user_type": data.get("user_type", ""),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("Zhihu API access denied for %s (may need cookie)", external_id)
            elif e.response.status_code == 404:
                logger.warning("Zhihu profile not found: %s", external_id)
            else:
                logger.error("Zhihu get_detail HTTP %d for %s", e.response.status_code, external_id)
            return None

        except Exception:
            logger.exception("Zhihu get_detail failed for %s", external_id)
            return None

    async def check_health(self) -> HealthStatus:
        """Check Zhihu API health with a minimal query."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get(
                ZHIHU_SEARCH_URL,
                params={"q": "test", "t": "people", "limit": 1},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            if resp.status_code == 200:
                return HealthStatus(healthy=True, latency_ms=latency_ms)
            elif resp.status_code in (400, 403):
                return HealthStatus(
                    healthy=False, latency_ms=latency_ms,
                    error_message=(
                        f"Zhihu API blocked ({resp.status_code}) — "
                        "anti-bot protection requires authenticated cookies"
                    ),
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
