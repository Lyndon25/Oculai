"""Juejin (掘金) data source — Chinese developer community.

Uses the public Juejin API (api.juejin.cn) for user search and profile
lookup. No authentication required for read-only access.

Search: POST https://api.juejin.cn/search_api/v1/search (type=user)
Profile: GET https://api.juejin.cn/user_api/v1/user/get?user_id={id}
"""

import logging
import time
from typing import Any

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

JUJUE_SEARCH_URL = "https://api.juejin.cn/search_api/v1/search"
JUJUE_USER_URL = "https://api.juejin.cn/user_api/v1/user/get"
JUJUE_ARTICLE_STAT_URL = "https://api.juejin.cn/user_api/v1/user/article/count"


class JuejinSource(IDataSource):
    """Juejin (掘金) Chinese developer community data source.

    Searches Juejin user profiles via the official public API. Covers Chinese
    developers with profiles on juejin.cn — includes job title, company,
    tech tags, follower counts, and article history.

    No API key required.
    """

    name = "juejin"
    source_type = "api"
    description = (
        "Search Juejin (掘金), a Chinese developer community, for candidate "
        "profiles. Covers tech-company employees, open-source contributors, "
        "and article authors. Returns job title, company, follower counts, "
        "tech tags, and article statistics. No API key required."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"juejin": "user_id"}
    example_queries = [
        "大模型工程师",
        "前端架构师 字节跳动",
        "后端资深开发",
        "算法工程师 推荐系统",
    ]
    auth_required = False
    rate_limit_notes = "Public API, ~10 req/s should be fine."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "User-Agent": "Oculai-TalentBot/1.0",
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search Juejin users by keywords."""
        start = time.perf_counter()
        candidates: list[RawCandidate] = []

        try:
            client = await self._get_client()
            keywords = " ".join(query.keywords)

            resp = await client.post(
                JUJUE_SEARCH_URL,
                json={
                    "key_word": keywords,
                    "type": "user",
                    "limit": min(query.limit, 20),
                },
            )
            resp.raise_for_status()
            data = resp.json()

            raw_list = []
            # Response data can be a dict with 'data' key or a list
            if isinstance(data, dict):
                raw_list = data.get("data", [])
            elif isinstance(data, list):
                raw_list = data

            seen_user_ids = set()
            for item in raw_list:
                if len(candidates) >= query.limit:
                    break

                # Juejin search returns articles; author info is in result_model.author_user_info
                result_model = item.get("result_model", {}) if isinstance(item, dict) else {}
                if not result_model:
                    continue

                # Try author_user_info first (article search), then user_info (direct user search)
                user_info = result_model.get("author_user_info") or result_model.get("user_info") or item.get("user_info", item)
                if not isinstance(user_info, dict):
                    continue

                user_id = str(user_info.get("user_id", ""))
                if not user_id or user_id in seen_user_ids:
                    continue
                seen_user_ids.add(user_id)

                # Fetch author details to get accurate company/job_title
                author_detail = await self._fetch_author_detail(user_id)
                if author_detail:
                    user_name = author_detail.get("user_name", "") or user_info.get("user_name", "") or ""
                    job_title = author_detail.get("position", "") or user_info.get("job_title", "") or user_info.get("position", "") or ""
                    company = author_detail.get("company", "") or user_info.get("company", "") or ""
                    description = author_detail.get("description", "") or user_info.get("description", "") or ""
                else:
                    user_name = user_info.get("user_name", "") or ""
                    job_title = user_info.get("job_title", "") or user_info.get("position", "") or ""
                    company = user_info.get("company", "") or ""
                    description = user_info.get("description", "") or ""

                short_intro = f"{job_title} @ {company}" if job_title and company else (job_title or company or "")

                # Handle-like name check
                _is_handle = False
                if user_name:
                    alpha = [c for c in user_name if c.isalpha()]
                    if (len(user_name) < 4 and alpha and all(c.islower() for c in alpha)) or user_name.startswith("@") or user_name.isdigit():
                        _is_handle = True

                candidates.append(
                    RawCandidate(
                        name=user_name,
                        institution=company,
                        research_areas=[description[:500]] if description else None,
                        profile_url=f"https://juejin.cn/user/{user_id}" if user_id else None,
                        raw_metadata={
                            "source": "juejin",
                            "user_id": user_id,
                            "user_name": user_name,
                            "job_title": job_title,
                            "company": company,
                            "description": description,
                            "short_intro": short_intro,
                            "followers_count": user_info.get("follower_count", 0) or user_info.get("followers_count", 0),
                            "article_count": user_info.get("post_article_count", 0) or user_info.get("article_count", 0),
                            "digg_count": user_info.get("got_digg_count", 0) or user_info.get("digg_count", 0),
                            "article_title": result_model.get("article_info", {}).get("title", ""),
                        },
                        result_type="web_page" if _is_handle else "profile_page",
                        confidence="low" if _is_handle else "medium",
                        extraction_method="unverified" if _is_handle else "direct",
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
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=duration_ms,
                error_message=error_msg,
            )
            logger.error("Juejin search failed: %s", error_msg)

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
            logger.exception("Juejin search failed")

        return candidates

    async def _fetch_author_detail(self, user_id: str) -> dict[str, Any] | None:
        """Fetch Juejin user details by user_id (internal helper for search)."""
        try:
            client = await self._get_client()
            resp = await client.get(
                JUJUE_USER_URL,
                params={"user_id": user_id},
            )
            resp.raise_for_status()
            data = resp.json()
            user = data.get("data", {})
            if not user:
                return None
            return {
                "user_name": user.get("user_name", ""),
                "position": user.get("position", ""),
                "company": user.get("company", ""),
                "description": user.get("description", ""),
            }
        except Exception:
            logger.debug("Juejin _fetch_author_detail failed for %s", user_id)
            return None

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch detailed Juejin user profile by user_id."""
        try:
            client = await self._get_client()

            # Get user profile
            resp = await client.get(
                JUJUE_USER_URL,
                params={"user_id": external_id},
            )
            resp.raise_for_status()
            data = resp.json()
            user = data.get("data", {})
            if not user:
                return None

            user_id = str(user.get("user_id", ""))
            user_name = user.get("user_name", "") or ""
            job_title = user.get("position", "") or ""
            company = user.get("company", "") or ""
            description = user.get("description", "") or ""

            # Get article stats
            try:
                stat_resp = await client.get(
                    JUJUE_ARTICLE_STAT_URL,
                    params={"user_id": external_id},
                )
                stat_resp.raise_for_status()
                stat_data = stat_resp.json()
                stats = stat_data.get("data", {}) if isinstance(stat_data, dict) else {}
            except Exception:
                stats = {}

            return RawCandidate(
                name=user_name,
                institution=company,
                profile_url=f"https://juejin.cn/user/{user_id}" if user_id else None,
                raw_metadata={
                    "source": "juejin",
                    "user_id": user_id,
                    "user_name": user_name,
                    "job_title": job_title,
                    "company": company,
                    "description": description,
                    "short_intro": f"{job_title} @ {company}" if job_title and company else "",
                    "followers_count": user.get("followers_count", 0),
                    "following_count": user.get("following_count", 0),
                    "article_count": stats.get("article_count", 0),
                    "digg_count": user.get("digg_count", 0) or stats.get("digg_count", 0),
                    "view_count": stats.get("view_count", 0),
                    "tags": user.get("tags", []),
                    "skill_tags": [t.get("tag_name", "") for t in (user.get("tags") or []) if t],
                },
                result_type="profile_page",
                confidence="medium",
                extraction_method="direct",
            )

        except Exception:
            logger.exception("Juejin get_detail failed for %s", external_id)
            return None

    async def check_health(self) -> HealthStatus:
        """Check Juejin API health with a minimal search."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.post(
                JUJUE_SEARCH_URL,
                json={"key_word": "test", "type": "user", "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()
            latency_ms = int((time.perf_counter() - start) * 1000)
            raw = data.get("data", []) if isinstance(data, dict) else []
            return HealthStatus(
                healthy=True,
                latency_ms=latency_ms,
                quota_remaining=len(raw),
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return HealthStatus(
                healthy=False,
                latency_ms=latency_ms,
                error_message=str(e),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
