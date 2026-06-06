"""Data source registry.

Auto-registers all known API and browser data sources on import.
Sources can also be registered manually via register_source().
"""

import logging
from typing import Type

from oculai_mcp.config import get_settings
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
        settings = get_settings()

        from oculai_mcp.sources.arxiv_api import ArxivAPISource
        from oculai_mcp.sources.dblp_api import DblpAPISource
        from oculai_mcp.sources.github_api import GitHubAPISource
        from oculai_mcp.sources.semantic_scholar_api import SemanticScholarAPISource
        from oculai_mcp.sources.openalex_api import OpenAlexAPISource
        from oculai_mcp.sources.industry_source import IndustrySource
        from oculai_mcp.sources.acl_anthology import ACLAnthologySource
        from oculai_mcp.sources.pmlr import PMLRSource
        from oculai_mcp.sources.conference import ConferenceSource
        from oculai_mcp.sources.baidu import BaiduScholarSource, BaiduSearchSource
        from oculai_mcp.sources.homepage import PersonalHomepageSource
        from oculai_mcp.sources.juejin import JuejinSource
        from oculai_mcp.sources.zhihu import ZhihuSource
        from oculai_mcp.sources.csdn import CSDNSource
        from oculai_mcp.sources.duckduckgo import DuckDuckGoSource

        registered = []
        if settings.source_enable_arxiv:
            register_source("arxiv", ArxivAPISource); registered.append("arxiv")
        if settings.source_enable_dblp:
            register_source("dblp", DblpAPISource); registered.append("dblp")
        if settings.source_enable_github:
            register_source("github", GitHubAPISource); registered.append("github")
        if settings.source_enable_semantic_scholar:
            register_source("semantic_scholar", SemanticScholarAPISource); registered.append("semantic_scholar")
        if settings.source_enable_openalex:
            register_source("openalex", OpenAlexAPISource); registered.append("openalex")
        if settings.source_enable_industry:
            register_source("industry", IndustrySource); registered.append("industry")
        if settings.source_enable_acl_anthology:
            register_source("acl_anthology", ACLAnthologySource); registered.append("acl_anthology")
        if settings.source_enable_pmlr:
            register_source("pmlr", PMLRSource); registered.append("pmlr")
        if settings.source_enable_conference:
            register_source("conference", ConferenceSource); registered.append("conference")
        if settings.source_enable_baidu_scholar:
            register_source("baidu_scholar", BaiduScholarSource); registered.append("baidu_scholar")
        if settings.source_enable_baidu:
            register_source("baidu", BaiduSearchSource); registered.append("baidu")
        if settings.source_enable_personal_homepage:
            register_source("personal_homepage", PersonalHomepageSource); registered.append("personal_homepage")
        if settings.source_enable_juejin:
            register_source("juejin", JuejinSource); registered.append("juejin")
        if settings.source_enable_zhihu:
            register_source("zhihu", ZhihuSource); registered.append("zhihu")
        if settings.source_enable_csdn:
            register_source("csdn", CSDNSource); registered.append("csdn")
        if settings.source_enable_duckduckgo:
            register_source("duckduckgo", DuckDuckGoSource); registered.append("duckduckgo")

        logger.info("Registered sources: %s", ", ".join(registered))
    except ImportError as e:
        logger.warning("Some sources unavailable: %s", e)


_register_api_sources()
