"""Firecrawl scrape tool — single-page web scraping via Firecrawl API.

Provides high-quality single-page scraping with native markdown output,
supporting static HTML, JavaScript SPAs, and PDF parsing.

Supports keyless mode (rate-limited per IP, works from Node.js/browsers).
For Python access, set FIRECRAWL_API_KEY in .env.
"""

import time
from typing import Any

import httpx

from oculai_mcp.config import get_settings
from oculai_mcp.db.provenance import log_source_call

FIRECRAWL_API_BASE = "https://api.firecrawl.dev/v1"


async def scrape_page(
    url: str,
    formats: list[str] | None = None,
    wait_for: int | None = None,
    run_id: Any = None,
) -> dict[str, Any]:
    """Scrape a single web page via Firecrawl and return clean markdown.

    Supports static HTML, JavaScript SPAs (with waitFor), and PDF parsing.
    Uses keyless mode when no API key is configured.

    Args:
        url: The URL to scrape
        formats: Output formats — ["markdown"] (default), ["html"], ["screenshot"], etc.
        wait_for: Milliseconds to wait for JS rendering (SPA pages)
        run_id: Optional run UUID for provenance tracking

    Returns:
        {"status": "success", "data": {"markdown": "...", "metadata": {...}}}
    """
    if not url:
        return {"status": "error", "error": {"code": "empty_url", "message": "URL must not be empty."}}

    settings = get_settings()
    api_key = getattr(settings, "firecrawl_api_key", None)
    start = time.monotonic()

    if formats is None:
        formats = ["markdown"]

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Oculai/1.0 (+https://github.com/oculai)"},
        ) as client:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            body: dict[str, Any] = {"url": url, "formats": formats}
            if wait_for is not None:
                body["waitFor"] = wait_for

            resp = await client.post(
                f"{FIRECRAWL_API_BASE}/scrape", json=body, headers=headers
            )

            if resp.status_code == 403 and not api_key:
                try:
                    data = resp.json()
                    error_detail = data.get("error", "")
                except ValueError:
                    error_detail = resp.text[:200]
                elapsed_ms = int((time.monotonic() - start) * 1000)
                await log_source_call(
                    source_name="firecrawl_scrape",
                    source_type="api",
                    query_params={"url": url, "formats": formats},
                    status="failed",
                    duration_ms=elapsed_ms,
                    error_message=f"Keyless blocked: {error_detail}",
                    run_id=run_id,
                )
                return {
                    "status": "error",
                    "error": {
                        "code": "keyless_blocked",
                        "message": (
                            f"Firecrawl keyless blocked from Python (TLS fingerprint). "
                            f"{error_detail} "
                            "Get a free API key at https://firecrawl.dev/app/api-keys "
                            "and set FIRECRAWL_API_KEY in .env"
                        ),
                    },
                }

            resp.raise_for_status()
            data = resp.json()

            elapsed_ms = int((time.monotonic() - start) * 1000)
            await log_source_call(
                source_name="firecrawl_scrape",
                source_type="api",
                query_params={"url": url, "formats": formats},
                status="success" if data.get("success") else "failed",
                duration_ms=elapsed_ms,
                run_id=run_id,
            )

            if not data.get("success"):
                return {
                    "status": "error",
                    "error": {
                        "code": "scrape_failed",
                        "message": data.get("error", "Unknown error"),
                    },
                }

            return {
                "status": "success",
                "data": {
                    "markdown": (data.get("data") or {}).get("markdown", ""),
                    "metadata": (data.get("data") or {}).get("metadata", {}),
                },
                "meta": {"latency_ms": elapsed_ms, "provider": "firecrawl"},
            }

    except httpx.HTTPStatusError as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        await log_source_call(
            source_name="firecrawl_scrape",
            source_type="api",
            query_params={"url": url},
            status="failed",
            duration_ms=elapsed_ms,
            error_message=str(e),
            run_id=run_id,
        )
        return {
            "status": "error",
            "error": {
                "code": "http_error",
                "message": str(e),
                "status_code": e.response.status_code,
            },
        }

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        await log_source_call(
            source_name="firecrawl_scrape",
            source_type="api",
            query_params={"url": url},
            status="failed",
            duration_ms=elapsed_ms,
            error_message=str(e),
            run_id=run_id,
        )
        return {"status": "error", "error": {"code": "scrape_failed", "message": str(e)}}
