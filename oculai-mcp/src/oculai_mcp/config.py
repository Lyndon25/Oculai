"""Pydantic V2 BaseSettings with mtime-aware cache reload."""

import os
import time
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to .env so it works regardless of cwd
# config.py is at src/oculai_mcp/config.py, .env is at oculai-mcp/.env
_ENV_FILE_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "oculai"
    db_user: str = "oculai"
    db_password: str = "oculai_dev"
    db_pool_min: int = 1
    db_pool_max: int = 10

    @property
    def db_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # API keys
    semantic_scholar_api_key: str | None = None
    openalex_email: str | None = None
    baidu_api_key: str | None = None
    github_token: str | None = None
    tavily_api_key: str | None = None
    exa_api_key: str | None = None

    @property
    def s2_api_key(self) -> str | None:
        """Alias for semantic_scholar_api_key used by Semantic Scholar source."""
        return self.semantic_scholar_api_key

    # China-First mandate toggle
    china_first_enabled: bool = True

    # Source enable/disable toggles
    source_enable_arxiv: bool = True
    source_enable_dblp: bool = True
    source_enable_github: bool = True
    source_enable_semantic_scholar: bool = True
    source_enable_openalex: bool = True
    source_enable_industry: bool = True
    source_enable_acl_anthology: bool = True
    source_enable_pmlr: bool = True
    source_enable_conference: bool = True
    source_enable_baidu_scholar: bool = True
    source_enable_baidu: bool = True
    source_enable_personal_homepage: bool = True
    source_enable_juejin: bool = True
    source_enable_zhihu: bool = True
    source_enable_csdn: bool = True

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE_PATH), env_file_encoding="utf-8"
    )


_settings_cache: tuple[float, Settings] | None = None


def get_settings() -> Settings:
    """Return cached Settings, reload if .env mtime changed."""
    global _settings_cache
    env_file = _ENV_FILE_PATH
    if env_file.exists():
        mtime = env_file.stat().st_mtime
        if _settings_cache is None or _settings_cache[0] < mtime:
            _settings_cache = (mtime, Settings())
        return _settings_cache[1]
    if _settings_cache is None:
        _settings_cache = (0.0, Settings())
    return _settings_cache[1]
