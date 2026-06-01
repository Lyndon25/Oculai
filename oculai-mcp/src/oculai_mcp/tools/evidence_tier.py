"""Evidence quality tier assignment rules.

Tiers:
  1 = Primary (direct, verifiable: publication, repo contribution, CV)
  2 = Secondary (supporting: profile page, blog post, answer)
  3 = Indirect (weak signal: comment, starred repo, topic tag)
  4 = Inferred (deduced, not directly observed)
  0 = Ungraded (default, not yet classified)
"""

from typing import Any

TIER_RULES: dict[str, dict[str, int]] = {
    "github": {
        "repo_contribution": 1,
        "code": 1,
        "profile": 2,
        "starred_repo": 3,
    },
    "semantic_scholar": {
        "publication": 1,
        "paper": 1,
        "citation_metric": 1,
        "author_profile": 2,
        "profile": 2,
    },
    "openalex": {
        "work": 1,
        "paper": 1,
        "author": 2,
        "profile": 2,
        "topic": 3,
    },
    "baidu_qianfan": {
        "profile_page": 1,
        "article": 2,
        "web_page": 3,
    },
    "zhihu": {
        "profile": 1,
        "answer": 2,
        "article": 2,
        "blog_post": 2,
    },
    "juejin": {
        "profile": 1,
        "article": 2,
        "blog_post": 2,
        "comment": 3,
    },
    "csdn": {
        "profile": 1,
        "blog_post": 2,
        "blog": 2,
        "comment": 3,
    },
    "arxiv": {
        "publication": 1,
        "paper": 1,
        "author_list": 2,
        "profile": 2,
    },
    "dblp": {
        "publication": 1,
        "paper": 1,
        "author": 2,
        "profile": 2,
    },
    "personal_homepage": {
        "cv": 1,
        "publication_list": 1,
        "paper": 1,
        "profile": 2,
        "bio": 2,
    },
    "baidu_scholar": {
        "publication": 1,
        "paper": 1,
        "citation": 1,
        "profile": 2,
    },
    "baidu": {
        "web_page": 3,
    },
    "conference": {
        "publication": 1,
    },
    "industry": {
        "profile": 2,
        "repo_contribution": 1,
    },
}


def get_tier(source_name: str, evidence_type: str) -> int:
    """Get the quality tier for a given source and evidence type."""
    source_rules = TIER_RULES.get(source_name, {})
    return source_rules.get(evidence_type, 0)


def _detect_quality_flags(source_name: str, content: dict[str, Any]) -> list[str]:
    """Auto-detect quality flags based on source-specific heuristics.

    These are lightweight heuristics only — not a substitute for
    real content analysis.
    """
    flags: list[str] = []

    if source_name == "github":
        # Check if repo is old/stale
        if content.get("last_push"):
            try:
                from datetime import datetime, timezone
                last_push = datetime.fromisoformat(str(content["last_push"]).replace("Z", "+00:00"))
                days_old = (datetime.now(timezone.utc) - last_push).days
                if days_old > 365:
                    flags.append("stale_repo")
            except Exception:
                pass
        stars = content.get("stars") or content.get("stargazers_count")
        if stars is not None and int(stars) < 5:
            flags.append("low_engagement")

    elif source_name in ("zhihu", "juejin", "csdn"):
        follower_count = content.get("follower_count") or content.get("followers")
        if follower_count is not None and int(follower_count) < 10:
            flags.append("low_engagement")
        article_count = content.get("article_count") or content.get("articles")
        if article_count is not None and int(article_count) < 3:
            flags.append("sparse_content")

    elif source_name in ("semantic_scholar", "openalex", "baidu_scholar"):
        # Flag if citation count seems very low for claimed seniority
        citation_count = content.get("citation_count") or content.get("citations")
        if citation_count is not None and int(citation_count) < 5:
            flags.append("low_citation")

    # Generic flags
    if content.get("self_reported") is True:
        flags.append("self_reported")
    if content.get("outdated") is True:
        flags.append("outdated")
    if content.get("unverified") is True:
        flags.append("unverified")

    return flags
