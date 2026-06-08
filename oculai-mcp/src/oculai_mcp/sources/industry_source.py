"""Industry candidate data source combining GitHub repos/users with tech stack signals.

Wraps GitHubAPISource to provide an aggregated industry search that enriches GitHub
results with tech stack, repo stars, and open source contribution metadata.
"""

import logging
import time
from typing import Any

from oculai_mcp.config import get_settings
from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, try_consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery
from oculai_mcp.sources.github_api import GitHubAPISource

logger = logging.getLogger(__name__)

# Known tech stack keywords mapped to research areas
_TECH_STACK_AREA_MAP: dict[str, str] = {
    "python": "machine_learning",
    "tensorflow": "deep_learning",
    "pytorch": "deep_learning",
    "jax": "deep_learning",
    "rust": "systems_programming",
    "go": "systems_programming",
    "c++": "systems_programming",
    "c": "systems_programming",
    "typescript": "frontend_development",
    "javascript": "frontend_development",
    "react": "frontend_development",
    "vue": "frontend_development",
    "kubernetes": "devops_infrastructure",
    "docker": "devops_infrastructure",
    "terraform": "devops_infrastructure",
    "java": "enterprise_development",
    "kotlin": "mobile_development",
    "swift": "mobile_development",
    "scala": "data_engineering",
}


class IndustrySource(IDataSource):
    """Aggregated industry candidate search via GitHub repository analysis.

    Wraps GitHubAPISource to search for repositories and contributors, then enriches
    results with industry-specific metadata: repo stars, tech stack signals from
    repository languages, and open source contribution metrics.

    Falls back gracefully to user search when no repositories match.
    """

    name = "industry"
    source_type = "api"
    description = (
        "Aggregated industry candidate search combining GitHub repository analysis "
        "with tech stack and open source contribution signals."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"github": "github_id"}
    example_queries = [
        "python machine learning engineer",
        "rust systems developer",
        "react frontend developer",
        "kubernetes devops engineer",
    ]
    auth_required = False
    rate_limit_notes = (
        "Delegates to GitHub REST API. 60 requests/hour without token, "
        "5000/hour with GITHUB_TOKEN."
    )

    def __init__(self) -> None:
        settings = get_settings()
        self._github = GitHubAPISource()
        self._token = settings.github_token

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search for industry candidates via GitHub repo/contributor discovery.

        Enriches GitHub results with industry-specific metadata:
          - tech_stack: inferred languages/tools from repo languages
          - industry_signals: repo stars, followers as quality signals
          - contribution_score: composite metric from contributions + stars
        """
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

        try:
            raw_candidates = await self._github.search(query)

            enriched: list[RawCandidate] = []
            for c in raw_candidates:
                enriched.append(self._enrich_candidate(c))

            await try_consume_quota(self.name, amount=len(enriched))
            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords, "limit": query.limit},
                status="success",
                duration_ms=duration_ms,
                records_count=len(enriched),
            )
            logger.info("Industry search returned %d candidates", len(enriched))
            return enriched

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
            logger.exception("Industry search failed")
            return []

    def _enrich_candidate(self, candidate: RawCandidate) -> RawCandidate:
        """Add industry-specific metadata to a GitHub-derived candidate.

        Extracts:
          - tech_stack: unique languages/tools from repo metadata
          - num_stars: total stars from all related repos
          - contributions: total contributions to top repos
          - industry_signals: composite quality indicators
        """
        meta = candidate.raw_metadata or {}

        top_repo_language = meta.get("top_repo_language")
        tech_stack: set[str] = set()

        # Infer tech stack from the repository language
        if top_repo_language and isinstance(top_repo_language, str):
            lang_lower = top_repo_language.lower()
            tech_stack.add(lang_lower)
            # Map to research area if known
            area = _TECH_STACK_AREA_MAP.get(lang_lower)
            if area:
                tech_stack.add(area)

        # Collect industry signals
        top_repo_stars = meta.get("top_repo_stars", 0) or 0
        contributions = meta.get("contributions_to_top_repo", 0) or 0
        followers = meta.get("followers", 0) or 0
        public_repos = meta.get("public_repos", 0) or 0

        # Composite contribution score (simple unweighted metric)
        contribution_score = 0
        if top_repo_stars > 0:
            contribution_score += min(top_repo_stars / 100, 50)  # cap at 50
        if contributions > 0:
            contribution_score += min(contributions, 50)  # cap at 50

        # Compose research areas from existing areas + tech stack
        existing_areas = set(candidate.research_areas or [])
        all_areas = sorted(existing_areas | tech_stack)

        enriched_meta: dict[str, Any] = {
            **meta,
            "source": "industry",
            "original_source": meta.get("source", "github_api"),
            "tech_stack": sorted(tech_stack),
            "industry_signals": {
                "top_repo_stars": top_repo_stars,
                "contributions": contributions,
                "followers": followers,
                "public_repos": public_repos,
                "contribution_score": round(contribution_score, 1),
            },
        }

        return RawCandidate(
            name=candidate.name,
            institution=candidate.institution,
            email=candidate.email,
            github_id=candidate.github_id,
            paper_count=candidate.paper_count,
            h_index=candidate.h_index,
            citation_count=candidate.citation_count,
            research_areas=all_areas if all_areas else None,
            profile_url=candidate.profile_url,
            raw_metadata=enriched_meta,
        )

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch detailed industry profile by GitHub username.

        Delegates to GitHubAPISource.get_detail and enriches the result
        with industry metadata.
        """
        try:
            raw = await self._github.get_detail(external_id)
            if raw is None:
                return None
            return self._enrich_candidate(raw)
        except Exception:
            logger.exception("Industry get_detail failed for %s", external_id)
            return None

    async def check_health(self) -> HealthStatus:
        """Check data source health by delegating to GitHub API health."""
        try:
            gh_health = await self._github.check_health()
            return HealthStatus(
                healthy=gh_health.healthy,
                latency_ms=gh_health.latency_ms,
                quota_remaining=gh_health.quota_remaining,
                error_message=gh_health.error_message,
            )
        except Exception as e:
            return HealthStatus(
                healthy=False,
                latency_ms=0.0,
                error_message=str(e),
            )

    async def close(self) -> None:
        """Close underlying GitHub API client."""
        await self._github.close()
