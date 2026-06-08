"""Browser evidence capture tool.

Captures web page screenshots and structured text content for evidence.
Uses Playwright/Patchright when available, with a graceful fallback
to httpx-based text fetching.

Supports fit_markdown denoising inspired by crawl4ai — removes navigation,
ads, sidebars, and outputs clean Markdown optimized for LLM consumption.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import httpx

from oculai_mcp.db.client import execute_with_retry
from oculai_mcp.utils.html_denoise import html_to_fit_markdown

logger = logging.getLogger(__name__)

_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright  # type: ignore[import-untyped]
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


async def capture_page_evidence(
    url: str,
    person_id: UUID | None = None,
    run_id: UUID | None = None,
    mode: str = "text",
    captured_by_agent: str = "system",
    selector: str | None = None,
) -> dict[str, Any]:
    """Capture evidence from a web page.

    Modes:
    - "text": Fetch page text content (lightweight, no browser needed)
    - "fit_markdown": Denoised Markdown — removes nav/sidebar/ads, keeps main content.
      Optimized for LLM consumption. Inspired by crawl4ai.
    - "screenshot": Full-page screenshot via Playwright (requires playwright)
    - "full": Both text + screenshot (requires playwright)

    Args:
        url: Web page URL to capture
        person_id: Optional Person UUID to attach evidence to
        run_id: Optional Run UUID for provenance
        mode: "text", "fit_markdown", "screenshot", or "full"
        captured_by_agent: Agent capturing the evidence
        selector: Optional CSS selector to extract only a portion
    """
    if mode not in ("text", "fit_markdown", "screenshot", "full"):
        return {"status": "error", "error": {"code": "invalid_mode", "message": f"Mode '{mode}' not supported. Use 'text', 'fit_markdown', 'screenshot', or 'full'."}}

    evidence_id = uuid4()
    content: dict[str, Any] = {"url": url, "mode": mode, "captured_at": datetime.now(timezone.utc).isoformat()}
    title = f"Page capture: {url[:100]}"

    text_content: str | None = None
    markdown_content: str | None = None
    screenshot_data: str | None = None  # base64

    try:
        # Capture text content
        if mode in ("text", "full"):
            text_content = await _capture_text(url, selector)
        elif mode == "fit_markdown":
            markdown_content = await _capture_fit_markdown(url, selector)

        # Screenshot requires Playwright
        if mode in ("screenshot", "full"):
            if _PLAYWRIGHT_AVAILABLE:
                screenshot_data = await _capture_screenshot(url, selector)
            else:
                logger.warning("Playwright not installed — screenshot unavailable. Install: pip install playwright && playwright install")

        # Build content
        if text_content:
            content["text"] = text_content[:50000]  # Truncate large pages
            content["text_length"] = len(text_content)
        if markdown_content:
            content["markdown"] = markdown_content[:50000]
            content["markdown_length"] = len(markdown_content)
            content["denoised"] = True
        if screenshot_data:
            content["screenshot_base64"] = screenshot_data[:500000]
            content["screenshot_format"] = "png"

        # Store as BrowserEvidence
        await execute_with_retry(
            """
            INSERT INTO browserevidence
                (evidence_id, person_id, run_id, source_url, captured_content,
                 capture_mode, captured_by_agent, created_by_agent, updated_by_agent)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $7, $7)
            """,
            evidence_id, person_id, run_id, url,
            content, mode, captured_by_agent,
        )

        return {
            "evidence_id": str(evidence_id),
            "url": url,
            "mode": mode,
            "has_text": text_content is not None,
            "has_markdown": markdown_content is not None,
            "has_screenshot": screenshot_data is not None,
            "text_length": len(text_content) if text_content else 0,
            "markdown_length": len(markdown_content) if markdown_content else 0,
            "title": title,
        }

    except Exception as e:
        logger.exception("Failed to capture page evidence from %s", url)
        return {
            "status": "error",
            "url": url,
            "error": {"code": "capture_failed", "message": str(e)},
        }


async def _capture_text(url: str, selector: str | None = None) -> str:
    """Fetch page text content via httpx + basic HTML parsing."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text

    # Basic HTML-to-text extraction using regex
    import re
    # Remove scripts and styles
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


async def _capture_fit_markdown(url: str, selector: str | None = None) -> str:
    """Fetch page and convert to denoised Markdown via fit_markdown extraction."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text

    # If a CSS selector is provided, extract only that portion
    if selector:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        el = soup.select_one(selector)
        if el:
            html = str(el)

    return html_to_fit_markdown(html, url=url, max_length=40000)


async def _capture_screenshot(url: str, selector: str | None = None) -> str | None:
    """Capture a full-page screenshot via Playwright. Returns base64 PNG."""
    if not _PLAYWRIGHT_AVAILABLE:
        return None

    import base64

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            if selector:
                element = await page.query_selector(selector)
                if element:
                    screenshot_bytes = await element.screenshot(type="png")
                else:
                    screenshot_bytes = await page.screenshot(type="png", full_page=True)
            else:
                screenshot_bytes = await page.screenshot(type="png", full_page=True)

            return base64.b64encode(screenshot_bytes).decode("utf-8")
        finally:
            await browser.close()
