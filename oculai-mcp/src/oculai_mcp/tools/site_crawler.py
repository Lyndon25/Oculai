"""Site crawler tool — BFS-based multi-page crawling with fit_markdown denoising.

Inspired by crawl4ai's crawl-site capability. Explores a candidate's entire
website (or a section of it) to discover hidden projects, publications, and
background information beyond the homepage.

Uses httpx for speed, with optional Playwright fallback for dynamic pages.
All pages are denoised via html_denoise.fit_markdown for LLM-optimized output.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.utils.html_denoise import html_to_fit_markdown, is_likely_dynamic_page

logger = logging.getLogger(__name__)

_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright  # type: ignore[import-untyped]
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# URL patterns to skip (assets, auth, admin, etc.)
_SKIP_PATTERNS = [
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf",
    ".zip", ".tar", ".gz", ".mp4", ".mp3", ".wav",
    "login", "logout", "signin", "signout", "auth",
    "admin", "wp-admin", "wp-login",
    "cart", "checkout", "payment",
    "javascript:", "mailto:", "tel:",
]

# Maximum content length per page (characters)
_MAX_PAGE_CONTENT = 15000

# Request timeout
_FETCH_TIMEOUT = 15.0


def _should_skip_url(url: str) -> bool:
    """Check if a URL should be skipped."""
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in _SKIP_PATTERNS)


def _is_same_domain(url: str, base_domain: str) -> bool:
    """Check if URL belongs to the same domain (or subdomain)."""
    parsed = urlparse(url)
    domain = parsed.netloc
    # Allow subdomains of base domain
    return domain == base_domain or domain.endswith("." + base_domain)


def _extract_links(html: str, base_url: str) -> set[str]:
    """Extract all href links from HTML, resolving relative URLs."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if href.startswith("#"):
            continue
        absolute = urljoin(base_url, href)
        links.add(absolute)
    return links


async def _fetch_page(
    client: httpx.AsyncClient,
    url: str,
    use_dynamic: bool = False,
) -> tuple[str | None, bool]:
    """Fetch a single page. Returns (html, used_dynamic)."""
    try:
        resp = await client.get(url, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        html = resp.text

        if html and is_likely_dynamic_page(html) and use_dynamic and _PLAYWRIGHT_AVAILABLE:
            logger.debug("Page %s appears dynamic — using Playwright", url)
            dynamic_html = await _fetch_dynamic(url)
            if dynamic_html:
                return dynamic_html, True

        return html, False

    except httpx.HTTPStatusError as e:
        logger.debug("HTTP error %s for %s", e.response.status_code, url)
        return None, False
    except Exception as e:
        logger.debug("Fetch error for %s: %s", url, e)
        return None, False


async def _fetch_dynamic(url: str) -> str | None:
    """Fetch page HTML after JavaScript rendering via Playwright."""
    if not _PLAYWRIGHT_AVAILABLE:
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(500)
                return await page.content()
            finally:
                await browser.close()
    except Exception as e:
        logger.debug("Dynamic fetch failed for %s: %s", url, e)
        return None


async def crawl_site(
    start_url: str,
    max_pages: int = 20,
    max_depth: int = 2,
    same_domain_only: bool = True,
    run_id: UUID | None = None,
    enable_dynamic: bool = True,
) -> dict[str, Any]:
    """Crawl a website starting from a URL using BFS.

    Discovers linked pages within the same domain, extracts clean Markdown
    content from each, and returns a structured summary. Useful for deep
    exploration of a candidate's personal website, lab page, or portfolio.

    Args:
        start_url: Starting URL for the crawl
        max_pages: Maximum number of pages to fetch (default 20)
        max_depth: Maximum link depth from start_url (default 2)
        same_domain_only: Only follow links within the same domain
        run_id: Optional run UUID for provenance
        enable_dynamic: Use Playwright for JavaScript-heavy pages

    Returns:
        Dict with crawl summary, per-page content, and link graph.
    """
    start_time = time.monotonic()
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc

    if not base_domain:
        return {
            "status": "error",
            "error": {"code": "invalid_url", "message": f"Invalid start URL: {start_url}"},
        }

    # BFS queue: (url, depth)
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    visited: set[str] = set()
    pages: list[dict[str, Any]] = []
    link_graph: dict[str, list[str]] = {}
    dynamic_count = 0

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        },
        follow_redirects=True,
    ) as client:
        while queue and len(pages) < max_pages:
            url, depth = queue.popleft()

            if url in visited:
                continue
            visited.add(url)

            if _should_skip_url(url):
                continue

            # Fetch page
            html, used_dynamic = await _fetch_page(client, url, use_dynamic=enable_dynamic)
            if html is None:
                continue
            if used_dynamic:
                dynamic_count += 1

            # Convert to denoised markdown
            markdown = html_to_fit_markdown(html, url=url, max_length=_MAX_PAGE_CONTENT)

            # Extract links for BFS (only if we haven't reached max depth)
            page_links: list[str] = []
            if depth < max_depth:
                try:
                    raw_links = _extract_links(html, url)
                    for link in raw_links:
                        if link in visited:
                            continue
                        if _should_skip_url(link):
                            continue
                        if same_domain_only and not _is_same_domain(link, base_domain):
                            continue
                        page_links.append(link)
                        queue.append((link, depth + 1))
                except Exception:
                    pass

            link_graph[url] = page_links

            pages.append({
                "url": url,
                "depth": depth,
                "title": _extract_title(html),
                "markdown": markdown,
                "markdown_length": len(markdown),
                "links_found": len(page_links),
                "dynamic_rendered": used_dynamic,
            })

            # Small delay to be polite
            await asyncio.sleep(0.3)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    await log_source_call(
        source_name="site_crawler",
        source_type="crawl",
        query_params={
            "start_url": start_url,
            "max_pages": max_pages,
            "max_depth": max_depth,
        },
        status="success",
        duration_ms=elapsed_ms,
        run_id=run_id,
        records_count=len(pages),
    )

    # Build combined summary text from all pages
    combined_text = "\n\n---\n\n".join(
        f"# {p['title'] or 'Untitled'}\n\n{p['markdown'][:3000]}"
        for p in pages
    )

    return {
        "status": "success",
        "start_url": start_url,
        "pages_crawled": len(pages),
        "max_depth_reached": max(p["depth"] for p in pages) if pages else 0,
        "dynamic_pages": dynamic_count,
        "duration_ms": elapsed_ms,
        "pages": [
            {
                "url": p["url"],
                "depth": p["depth"],
                "title": p["title"],
                "markdown_length": p["markdown_length"],
                "links_found": p["links_found"],
                "dynamic_rendered": p["dynamic_rendered"],
            }
            for p in pages
        ],
        "page_contents": {p["url"]: p["markdown"] for p in pages},
        "combined_text": combined_text[:50000],
        "link_graph": link_graph,
    }


def _extract_title(html: str) -> str | None:
    """Extract page title from HTML."""
    import re
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None
