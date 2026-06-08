"""GitHub REST API data source.

Discovery strategy:
1. Search repositories matching keywords (sorted by stars).
2. For each top repo, fetch top contributors.
3. Fetch detailed profiles for each contributor.
4. Deduplicate and rank by repo stars + contributions + followers.

If no repositories are found, falls back to /search/users.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from oculai_mcp.config import get_settings
from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, try_consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_PER_PAGE = 30

# Bot / org accounts that should never enter the candidate pipeline
_GITHUB_BOT_DENYLIST = {
    "dependabot", "renovate", "renovate-bot", "github-actions",
    "github-actions-bot", "semantic-release", "allcontributors",
    "imgbotapp", "restyled-io", "greenkeeper", "snyk-bot",
    "codecov-io", "coveralls", "codesandbox-ci", "vercel",
    "netlify", "circleci", "travis-ci", "jenkins",
}


def _is_github_bot(login: str) -> bool:
    """Return True if the login looks like a bot or automation account."""
    if not login:
        return False
    low = login.lower()
    if low in _GITHUB_BOT_DENYLIST:
        return True
    if low.endswith("[bot]"):
        return True
    if low.endswith("-bot") or low.endswith("_bot"):
        return True
    return False


class GitHubAPISource(IDataSource):
    """Real GitHub REST API data source."""

    name = "github"
    source_type = "api"
    description = (
        "Search GitHub users by discovering contributors to top-starred repositories "
        "matching the query keywords. Returns profile details including repositories, "
        "followers, and contributions. Requires GITHUB_TOKEN for higher rate limits."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"github": "github_id"}
    example_queries = [
        "python machine learning",
        "rust systems programming",
        "react frontend",
        "transformers NLP",
        "kubernetes devops",
    ]
    auth_required = False
    rate_limit_notes = "60 requests/hour without token, 5000/hour with GITHUB_TOKEN. Token strongly recommended."

    def __init__(self) -> None:
        settings = get_settings()
        self._token = settings.github_token
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.AsyncClient(
                base_url=GITHUB_API_BASE,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search GitHub users via repository contributor discovery."""
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

            has_token = bool(self._token)
            max_repos = 15 if has_token else 5
            max_contributors_per_repo = 5 if has_token else 3
            max_total_candidates = query.limit

            repos = await self._search_repositories(client, keywords, max_repos)
            if not repos:
                logger.warning("No repositories found for '%s', falling back to user search", keywords)
                candidates = await self._search_users_fallback(client, query)
                await self._log_search(start, query, candidates, fallback=True)
                return candidates

            contributor_infos = await self._collect_contributors(
                client, repos, max_contributors_per_repo
            )
            candidates = await self._fetch_user_details(
                client, contributor_infos, max_total_candidates
            )

            await self._log_search(start, query, candidates, fallback=False)

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
            logger.error("GitHub API search failed: %s", error_msg)

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
            logger.exception("GitHub API search failed")

        return candidates

    async def _search_repositories(
        self, client: httpx.AsyncClient, keywords: str, max_repos: int
    ) -> list[dict[str, Any]]:
        """Search repositories by keywords, sorted by stars."""
        params = {
            "q": keywords,
            "sort": "stars",
            "order": "desc",
            "per_page": str(max_repos),
        }
        resp = await client.get("/search/repositories", params=params)
        resp.raise_for_status()
        return resp.json().get("items", [])[:max_repos]

    async def _collect_contributors(
        self,
        client: httpx.AsyncClient,
        repos: list[dict[str, Any]],
        max_per_repo: int,
    ) -> list[dict[str, Any]]:
        """Fetch top contributors for each repository."""
        seen_logins: set[str] = set()
        contributor_infos: list[dict[str, Any]] = []

        for repo in repos:
            owner = repo.get("owner", {}).get("login")
            repo_name = repo.get("name")
            if not owner or not repo_name:
                continue

            try:
                resp = await client.get(
                    f"/repos/{owner}/{repo_name}/contributors",
                    params={"per_page": str(max_per_repo)},
                )
                resp.raise_for_status()
                contributors = resp.json()
            except httpx.HTTPStatusError:
                continue

            for c in contributors:
                login = c.get("login")
                if not login or login in seen_logins:
                    continue
                if _is_github_bot(login):
                    continue
                if c.get("type") != "User":
                    continue
                seen_logins.add(login)
                contributor_infos.append({
                    "login": login,
                    "contributions": c.get("contributions", 0),
                    "repo_name": repo_name,
                    "repo_stars": repo.get("stargazers_count", 0),
                    "repo_language": repo.get("language"),
                })

        return contributor_infos

    async def _fetch_user_details(
        self,
        client: httpx.AsyncClient,
        contributor_infos: list[dict[str, Any]],
        max_candidates: int,
    ) -> list[RawCandidate]:
        """Fetch user details in small parallel batches.

        Always calls get_detail() for each contributor so that real names,
        company, bio, and location are populated. Falls back to login when
        the real name is unavailable.
        """

        async def _fetch_one(info: dict[str, Any]) -> RawCandidate | None:
            detail = await self.get_detail(info["login"])
            if detail is None:
                return None

            # Merge contributor-specific repo metadata into the detail record
            raw_meta = detail.raw_metadata or {}
            raw_meta.update({
                "top_repo": info["repo_name"],
                "top_repo_stars": info["repo_stars"],
                "contributions_to_top_repo": info["contributions"],
                "top_repo_language": info["repo_language"],
            })
            detail.raw_metadata = raw_meta
            return detail

        batch_size = 10
        results: list[RawCandidate] = []
        for i in range(0, len(contributor_infos), batch_size):
            batch = contributor_infos[i : i + batch_size]
            batch_results = await asyncio.gather(
                *(_fetch_one(info) for info in batch),
                return_exceptions=True,
            )
            for r in batch_results:
                if isinstance(r, RawCandidate):
                    results.append(r)
            if len(results) >= max_candidates:
                break

        return results[:max_candidates]

    async def _search_users_fallback(
        self, client: httpx.AsyncClient, query: SearchQuery
    ) -> list[RawCandidate]:
        """Fallback: search users directly with basic query.

        Calls get_detail() for each result so that real names, company, bio,
        and location are populated. Falls back to login when the real name is
        unavailable.
        """
        keywords = " ".join(query.keywords)
        params = {
            "q": keywords,
            "per_page": str(min(query.limit, DEFAULT_PER_PAGE)),
        }
        resp = await client.get("/search/users", params=params)
        resp.raise_for_status()
        data = resp.json()

        candidates: list[RawCandidate] = []
        for item in data.get("items", [])[: query.limit]:
            login = item.get("login")
            if not login:
                continue
            if _is_github_bot(login):
                continue
            if item.get("type") != "User":
                continue

            detail = await self.get_detail(login)
            if detail is not None:
                raw_meta = detail.raw_metadata or {}
                raw_meta["fallback_search"] = True
                detail.raw_metadata = raw_meta
                candidates.append(detail)
            else:
                # Graceful degradation if detail fetch fails
                candidates.append(
                    RawCandidate(
                        name=login,
                        github_id=login,
                        profile_url=item.get("html_url"),
                        raw_metadata={
                            "source": "github_api",
                            "avatar_url": item.get("avatar_url"),
                            "type": item.get("type"),
                            "fallback_search": True,
                        },
                        result_type="profile_page",
                        confidence="high",
                        extraction_method="fallback",
                    )
                )
        return candidates

    async def _log_search(
        self,
        start: float,
        query: SearchQuery,
        candidates: list[RawCandidate],
        fallback: bool,
    ) -> None:
        await try_consume_quota(self.name, amount=len(candidates))
        duration_ms = int((time.perf_counter() - start) * 1000)
        await log_source_call(
            source_name=self.name,
            source_type=self.source_type,
            query_params={
                "keywords": query.keywords,
                "limit": query.limit,
                "fallback": fallback,
            },
            status="success",
            duration_ms=duration_ms,
            records_count=len(candidates),
        )
        logger.info(
            "GitHub API search returned %d candidates (fallback=%s)",
            len(candidates),
            fallback,
        )

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch detailed GitHub user profile."""
        start = time.perf_counter()

        # Normalize external_id: strip URL prefixes, extract login from full URLs
        login = external_id
        if "/" in login:
            # Could be https://github.com/username or just username
            login = login.rstrip("/").split("/")[-1]
        login = login.strip()
        if not login:
            logger.warning("GitHub get_detail received empty login")
            return None

        try:
            client = await self._get_client()
            resp = await client.get(f"/users/{login}")
            resp.raise_for_status()
            data = resp.json()

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"github_id": external_id},
                status="success",
                duration_ms=duration_ms,
                records_count=1,
            )

            if data.get("type") == "Organization":
                logger.debug("Skipping GitHub organization: %s", login)
                return None

            real_name = data.get("name")
            name = real_name if real_name else (data.get("login") or login)
            company = data.get("company")
            if company:
                company = company.strip().lstrip("@")

            return RawCandidate(
                name=name,
                github_id=login,
                institution=company,
                profile_url=data.get("html_url"),
                raw_metadata={
                    "source": "github_api",
                    "bio": data.get("bio"),
                    "location": data.get("location"),
                    "public_repos": data.get("public_repos", 0),
                    "followers": data.get("followers", 0),
                    "following": data.get("following", 0),
                    "created_at": data.get("created_at"),
                    "hireable": data.get("hireable"),
                },
                result_type="profile_page",
                confidence="high",
                extraction_method="direct",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("GitHub user not found: %s", login)
                return None
            logger.error("GitHub API detail failed: HTTP %s", e.response.status_code)
            return None

        except Exception:
            logger.exception("GitHub API detail failed for %s", login)
            return None

    async def check_health(self) -> HealthStatus:
        """Check GitHub API health."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get("/rate_limit")
            resp.raise_for_status()
            data = resp.json()

            core = data.get("resources", {}).get("core", {})
            remaining = core.get("remaining", 0)

            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                healthy=True,
                latency_ms=latency_ms,
                quota_remaining=remaining,
            )

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
