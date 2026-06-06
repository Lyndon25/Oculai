"""HTML denoising and markdown extraction — inspired by crawl4ai's fit_markdown.

Extracts main content from noisy HTML, removing navigation, sidebars, ads,
footers, and scripts. Outputs clean Markdown optimized for LLM consumption.
"""

import re
from typing import Any
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup, Comment, NavigableString, Tag
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False

# CSS selectors for noise elements to remove
_NOISE_SELECTORS = [
    "nav", "header", "footer", "aside",
    ".sidebar", ".side-bar", ".menu", ".navigation",
    ".ad", ".ads", ".advertisement", ".banner",
    ".cookie-banner", ".cookie-consent", ".gdpr",
    ".social-share", ".share-buttons", ".follow-us",
    ".related-posts", ".recommended", ".you-may-like",
    ".comments", ".comment-section", ".disqus",
    ".newsletter", ".subscribe", ".mailing-list",
    ".pagination", ".pager", ".page-nav",
    "[role='banner']", "[role='navigation']", "[role='complementary']",
    "script", "style", "noscript", "iframe",
]

# Selectors for main content (in priority order)
_CONTENT_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    ".content", ".post-content", ".entry-content",
    ".article-body", ".post-body", ".main-content",
    "#content", "#main", "#main-content",
]

# Minimum meaningful text length
_MIN_CONTENT_LENGTH = 200


def _is_noise_element(tag: Tag) -> bool:
    """Check if a tag is likely noise based on class/id/role attributes."""
    attrs = " ".join([
        tag.get("class", ""),
        tag.get("id", ""),
        tag.get("role", ""),
    ]).lower()

    noise_keywords = [
        "nav", "menu", "sidebar", "side-bar", "footer", "header",
        "ad-", "ads", "advert", "banner", "cookie", "gdpr",
        "social", "share", "follow", "related", "recommended",
        "comment", "disqus", "newsletter", "subscribe",
        "pagination", "pager", "breadcrumb",
    ]
    return any(kw in attrs for kw in noise_keywords)


def _clean_soup(soup: BeautifulSoup) -> None:
    """Remove noise elements from the soup in-place."""
    # Remove by CSS selectors
    for selector in _NOISE_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove remaining noise by heuristic
    for tag in soup.find_all(_is_noise_element):
        tag.decompose()

    # Remove empty tags
    for tag in soup.find_all():
        if tag.name and tag.name not in ("br", "hr", "img"):
            if not tag.get_text(strip=True):
                tag.decompose()


def _find_main_content(soup: BeautifulSoup) -> Tag | None:
    """Find the main content container using heuristics."""
    for selector in _CONTENT_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text_len = len(el.get_text(strip=True))
            if text_len >= _MIN_CONTENT_LENGTH:
                return el

    # Fallback: find the div with the most text content
    candidates = []
    for div in soup.find_all("div"):
        text = div.get_text(strip=True)
        if len(text) >= _MIN_CONTENT_LENGTH:
            # Prefer elements that are not too deep in the tree
            depth = len(list(div.parents))
            candidates.append((len(text), depth, div))

    if candidates:
        # Sort by text length descending, then by depth ascending
        candidates.sort(key=lambda x: (-x[0], x[1]))
        return candidates[0][2]

    return None


def _tag_to_markdown(tag: Tag | NavigableString, base_url: str = "") -> str:
    """Convert a BeautifulSoup tag tree to Markdown."""
    if isinstance(tag, NavigableString):
        text = str(tag)
        # Collapse whitespace but preserve newlines from block elements
        return text

    if tag.name is None:
        return ""

    # Skip hidden elements
    if tag.get("hidden") or tag.get("aria-hidden") == "true":
        return ""

    # Process children
    children_md = ""
    for child in tag.children:
        children_md += _tag_to_markdown(child, base_url)

    # Block-level formatting
    match tag.name:
        case "h1":
            return f"\n\n# {children_md.strip()}\n\n"
        case "h2":
            return f"\n\n## {children_md.strip()}\n\n"
        case "h3":
            return f"\n\n### {children_md.strip()}\n\n"
        case "h4":
            return f"\n\n#### {children_md.strip()}\n\n"
        case "h5":
            return f"\n\n##### {children_md.strip()}\n\n"
        case "h6":
            return f"\n\n###### {children_md.strip()}\n\n"
        case "p":
            text = children_md.strip()
            return f"\n\n{text}\n\n" if text else ""
        case "br":
            return "\n"
        case "hr":
            return "\n\n---\n\n"
        case "blockquote":
            text = children_md.strip()
            lines = text.splitlines()
            quoted = "\n".join(f"> {line}" for line in lines if line.strip())
            return f"\n\n{quoted}\n\n" if quoted else ""
        case "pre":
            text = children_md.strip()
            return f"\n\n```\n{text}\n```\n\n" if text else ""
        case "code":
            text = children_md.strip()
            # Inline code if parent is not pre
            if tag.parent and tag.parent.name == "pre":
                return text
            return f"`{text}`" if text else ""
        case "ul":
            items = []
            for li in tag.find_all("li", recursive=False):
                li_text = _tag_to_markdown(li, base_url).strip()
                if li_text:
                    items.append(f"- {li_text}")
            return "\n\n" + "\n".join(items) + "\n\n" if items else ""
        case "ol":
            items = []
            for i, li in enumerate(tag.find_all("li", recursive=False), 1):
                li_text = _tag_to_markdown(li, base_url).strip()
                if li_text:
                    items.append(f"{i}. {li_text}")
            return "\n\n" + "\n".join(items) + "\n\n" if items else ""
        case "li":
            return children_md
        case "table":
            return _table_to_markdown(tag)
        case "a":
            href = tag.get("href", "")
            if href and base_url:
                href = urljoin(base_url, href)
            text = children_md.strip()
            if href and text and not href.startswith("javascript:"):
                return f"[{text}]({href})"
            return text
        case "img":
            src = tag.get("src", "")
            alt = tag.get("alt", "")
            if src and base_url:
                src = urljoin(base_url, src)
            return f"![{alt}]({src})" if src else ""
        case "strong" | "b":
            text = children_md.strip()
            return f"**{text}**" if text else ""
        case "em" | "i":
            text = children_md.strip()
            return f"*{text}*" if text else ""
        case "span" | "div" | "section":
            text = children_md.strip()
            return f"\n\n{text}\n\n" if text else ""
        case _:
            return children_md


def _table_to_markdown(table: Tag) -> str:
    """Convert a table to Markdown."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    md_rows = []
    for i, row in enumerate(rows):
        cells = row.find_all(["td", "th"])
        cell_texts = [c.get_text(strip=True) for c in cells]
        md_rows.append("| " + " | ".join(cell_texts) + " |")
        if i == 0 and any(c.name == "th" for c in cells):
            md_rows.append("|" + "|".join(" --- " for _ in cells) + "|")

    return "\n\n" + "\n".join(md_rows) + "\n\n"


def html_to_fit_markdown(html: str, url: str = "", max_length: int = 30000) -> str:
    """Convert raw HTML to clean, denoised Markdown optimized for LLMs.

    Args:
        html: Raw HTML string
        url: Source URL (for resolving relative links)
        max_length: Maximum output length in characters

    Returns:
        Clean Markdown string with navigation, ads, and noise removed.
    """
    if not _BS4_AVAILABLE:
        # Fallback to regex-based basic extraction
        return _fallback_extract(html, max_length)

    soup = BeautifulSoup(html, "html.parser")

    # Try to get page title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Remove noise
    _clean_soup(soup)

    # Find main content
    main = _find_main_content(soup)
    if main is None:
        main = soup.find("body") or soup

    # Convert to markdown
    md = _tag_to_markdown(main, url)

    # Add title if found and not already in content
    if title and title not in md[:500]:
        md = f"# {title}\n\n{md}"

    # Post-process: collapse excessive whitespace
    md = re.sub(r"\n{4,}", "\n\n\n", md)
    md = md.strip()

    # Truncate if too long
    if len(md) > max_length:
        md = md[:max_length].rsplit("\n", 1)[0] + "\n\n..."

    return md


def _fallback_extract(html: str, max_length: int) -> str:
    """Fallback regex-based extraction when BeautifulSoup is unavailable."""
    import re

    # Remove scripts and styles
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Try to extract title
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    # Remove remaining tags
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()

    result = f"# {title}\n\n{text}" if title else text
    if len(result) > max_length:
        result = result[:max_length] + "..."
    return result


def extract_text_density(html: str) -> float:
    """Return the ratio of visible text to HTML markup length.

    A low ratio suggests a page is heavy on scripts/styles/ads.
    """
    if not html:
        return 0.0

    if _BS4_AVAILABLE:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
    else:
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

    return len(text) / max(len(html), 1)


def is_likely_dynamic_page(html: str) -> bool:
    """Heuristic: does the page likely require JavaScript to render meaningful content?

    Checks for:
    - Very low text-to-HTML ratio (heavy JS frameworks)
    - Presence of common JS framework markers
    - Empty body or placeholder content
    """
    density = extract_text_density(html)
    if density < 0.05:
        return True

    # Check for common SPA/framework markers
    js_frameworks = [
        "react", "vue", "angular", "next.js", "nuxt",
        "data-reactroot", "data-v-", "ng-",
        "window.__INITIAL_STATE__", "window.__DATA__",
    ]
    html_lower = html.lower()
    if any(marker in html_lower for marker in js_frameworks):
        return True

    # Check if body is essentially empty
    if _BS4_AVAILABLE:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("body")
        if body:
            body_text = body.get_text(strip=True)
            if len(body_text) < _MIN_CONTENT_LENGTH:
                return True

    return False
