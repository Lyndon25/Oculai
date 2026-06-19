"""Web search tool — Exa / Tavily / Firecrawl abstraction for candidate discovery.

Provides unified search across Western web sources for discovering
candidates mentioned in news, blogs, company pages, and tech forums.

Firecrawl can be used keyless (no API key required) — rate-limited per IP.
"""

import time
from typing import Any

import httpx

from oculai_mcp.config import get_settings
from oculai_mcp.db.provenance import log_source_call

EXA_API_BASE = "https://api.exa.ai"
TAVILY_API_BASE = "https://api.tavily.com"
FIRECRAWL_API_BASE = "https://api.firecrawl.dev/v1"


async def search_web(
    keywords: list[str],
    provider: str = "tavily",
    run_id: Any = None,
    limit: int = 20,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Search the web for candidate-related content.

    Supports Exa, Tavily, and Firecrawl as backends. Firecrawl works
    keyless (no API key required) — rate-limited per IP. Set
    FIRECRAWL_API_KEY for higher rate limits.

    Args:
        keywords: Search keyword list
        provider: "tavily" (default), "exa", or "firecrawl"
        run_id: Optional run UUID for provenance
        limit: Max results
        include_domains: Whitelist domains (e.g. linkedin.com, github.com)
        exclude_domains: Blacklist domains
    """
    if not keywords:
        return {
            "status": "error",
            "error": {"code": "empty_query", "message": "Keywords list must not be empty."},
        }

    settings = get_settings()
    start = time.monotonic()

    if provider == "tavily":
        api_key = getattr(settings, "tavily_api_key", None)
    elif provider == "exa":
        api_key = getattr(settings, "exa_api_key", None)
    elif provider == "firecrawl":
        api_key = getattr(settings, "firecrawl_api_key", None)
        # Firecrawl works keyless — api_key is optional for higher rate limits
    else:
        return {"status": "error", "error": {"code": "unknown_provider", "message": f"Provider '{provider}' not supported. Use 'tavily', 'exa', or 'firecrawl'."}}

    # Firecrawl works keyless; Tavily/Exa require keys
    if provider != "firecrawl" and not api_key:
        return {
            "status": "error",
            "error": {
                "code": "no_api_key",
                "message": f"No API key configured for {provider}. Set {provider.upper()}_API_KEY env var.",
            },
        }

    query = " ".join(keywords)

    try:
        if provider == "tavily":
            results = await _search_tavily(api_key, query, limit, include_domains, exclude_domains)
        elif provider == "exa":
            results = await _search_exa(api_key, query, limit, include_domains, exclude_domains)
        else:
            results = await _search_firecrawl(api_key, query, limit, include_domains, exclude_domains)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        await log_source_call(
            source_name=f"web_{provider}",
            source_type="api",
            query_params={"keywords": keywords, "limit": limit, "provider": provider},
            status="success",
            duration_ms=elapsed_ms,
            run_id=run_id,
            records_count=len(results),
        )

        return {
            "status": "success",
            "provider": provider,
            "query": query,
            "results": results,
            "meta": {"count": len(results), "latency_ms": elapsed_ms},
        }

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        await log_source_call(
            source_name=f"web_{provider}",
            source_type="api",
            query_params={"keywords": keywords},
            status="failed",
            duration_ms=elapsed_ms,
            error_message=str(e),
            run_id=run_id,
        )
        return {"status": "error", "error": {"code": "search_failed", "message": str(e), "provider": provider}}


async def _search_tavily(
    api_key: str,
    query: str,
    limit: int,
    include_domains: list[str] | None,
    exclude_domains: list[str] | None,
) -> list[dict[str, Any]]:
    """Execute a Tavily search."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        body: dict[str, Any] = {
            "api_key": api_key,
            "query": query,
            "max_results": min(limit, 20),
            "search_depth": "advanced",
        }
        if include_domains:
            body["include_domains"] = include_domains
        if exclude_domains:
            body["exclude_domains"] = exclude_domains

        resp = await client.post(f"{TAVILY_API_BASE}/search", json=body)
        resp.raise_for_status()
        data = resp.json()

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "score": r.get("score", 0),
                "raw_metadata": {"source": "tavily"},
            }
            for r in data.get("results", [])[:limit]
        ]


async def _search_exa(
    api_key: str,
    query: str,
    limit: int,
    include_domains: list[str] | None,
    exclude_domains: list[str] | None,
) -> list[dict[str, Any]]:
    """Execute an Exa search."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"x-api-key": api_key, "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "query": query,
            "numResults": min(limit, 20),
            "type": "neural",
            "contents": {"text": {"maxCharacters": 500}},
        }
        if include_domains:
            body["includeDomains"] = include_domains
        if exclude_domains:
            body["excludeDomains"] = exclude_domains

        resp = await client.post(f"{EXA_API_BASE}/search", json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("text", ""),
                "score": r.get("score", 0),
                "published_date": r.get("publishedDate"),
                "author": r.get("author"),
                "raw_metadata": {"source": "exa"},
            }
            for r in data.get("results", [])[:limit]
        ]


async def _search_firecrawl(
    api_key: str | None,
    query: str,
    limit: int,
    include_domains: list[str] | None,
    exclude_domains: list[str] | None,
) -> list[dict[str, Any]]:
    """Execute a Firecrawl search. Uses keyless mode if no API key."""
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": "Oculai/1.0 (+https://github.com/oculai)"},
    ) as client:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 20),
        }
        if include_domains:
            body["includeDomains"] = include_domains
        if exclude_domains:
            body["excludeDomains"] = exclude_domains

        resp = await client.post(
            f"{FIRECRAWL_API_BASE}/search", json=body, headers=headers
        )
        if resp.status_code == 403 and not api_key:
            try:
                data = resp.json()
                error_detail = data.get("error", "")
            except ValueError:
                error_detail = resp.text[:200]
            raise RuntimeError(
                f"Firecrawl keyless blocked (TLS fingerprint). {error_detail} "
                "Get a free API key at https://firecrawl.dev/app/api-keys "
                "and set FIRECRAWL_API_KEY in .env"
            )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success"):
            raise RuntimeError(
                data.get("error", "Firecrawl search returned unsuccessful response")
            )

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
                "score": r.get("score", 0),
                "raw_metadata": {"source": "firecrawl"},
            }
            for r in (data.get("data") or [])[:limit]
        ]
