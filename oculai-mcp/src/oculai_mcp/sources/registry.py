"""Data source registry.

Auto-registers all known API and browser data sources on import.
Sources can also be registered manually via register_source().
"""

import logging
from typing import Type

from oculai_mcp.sources.base import IDataSource

logger = logging.getLogger(__name__)

_registry: dict[str, Type[IDataSource]] = {}


def register_source(name: str, cls: Type[IDataSource]) -> None:
    """Register a data source class."""
    _registry[name] = cls
    logger.info("Registered data source: %s", name)


def get_source(name: str) -> Type[IDataSource] | None:
    """Get a registered data source class by name."""
    return _registry.get(name)


def list_sources() -> list[str]:
    """List all registered source names."""
    return list(_registry.keys())


def create_source(name: str) -> IDataSource | None:
    """Create an instance of a registered source."""
    cls = get_source(name)
    if cls is None:
        return None
    return cls()


def get_all_capabilities() -> list[dict]:
    """Get capability descriptors for all registered sources."""
    caps = []
    for name in _registry:
        try:
            source = create_source(name)
            if source:
                caps.append(source.get_capabilities())
        except Exception:
            caps.append({"name": name, "source_type": "api", "description": "Source capability unavailable", "supported_operations": [], "error": "Failed to initialize"})
    return caps


# ── Auto-register API sources ────────────────────────────────────────────

def _register_api_sources() -> None:
    try:
        from oculai_mcp.sources.arxiv_api import ArxivAPISource
        from oculai_mcp.sources.dblp_api import DblpAPISource
        from oculai_mcp.sources.github_api import GitHubAPISource
        from oculai_mcp.sources.semantic_scholar_api import SemanticScholarAPISource
        from oculai_mcp.sources.openalex_api import OpenAlexAPISource
        from oculai_mcp.sources.industry_source import IndustrySource
        from oculai_mcp.sources.conference import ConferenceSource
        from oculai_mcp.sources.baidu import BaiduScholarSource, BaiduSearchSource
        from oculai_mcp.sources.homepage import PersonalHomepageSource

        register_source("arxiv", ArxivAPISource)
        register_source("dblp", DblpAPISource)
        register_source("github", GitHubAPISource)
        register_source("semantic_scholar", SemanticScholarAPISource)
        register_source("openalex", OpenAlexAPISource)
        register_source("industry", IndustrySource)
        register_source("conference", ConferenceSource)
        register_source("baidu_scholar", BaiduScholarSource)
        register_source("baidu", BaiduSearchSource)
        register_source("personal_homepage", PersonalHomepageSource)
        logger.info(
            "Registered sources: arxiv, dblp, github, semantic_scholar, openalex, "
            "industry, conference, baidu_scholar, baidu, personal_homepage"
        )
    except ImportError as e:
        logger.warning("Some sources unavailable: %s", e)


_register_api_sources()
