"""ACL Anthology data source.

Covers NLP / Computational Linguistics conferences and journals:
ACL, EMNLP, NAACL, EACL, COLING, TACL, Findings, and affiliated workshops.

Searches by venue+year (for conference-specific sourcing) or by keyword
(using Anthology's search page).  Parses paper listings and optionally
enriches author affiliations from per-paper TEI XML.

No API key required.
"""

import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

ACL_BASE = "https://aclanthology.org"

# Venue slug -> canonical name mapping
VENUE_SLUGS: dict[str, str] = {
    "acl": "ACL",
    "emnlp": "EMNLP",
    "naacl": "NAACL",
    "eacl": "EACL",
    "coling": "COLING",
    "tacl": "TACL",
    "findings": "Findings",
    "cl": "Computational Linguistics",
    "semeval": "SemEval",
    "ws": "Workshop",
}

# Default venues to search when none specified
DEFAULT_VENUES = ["acl", "emnlp", "naacl", "findings"]

# Maximum papers to fetch per venue page
MAX_PAPERS_PER_VENUE = 200

# Maximum detail fetches for affiliation enrichment
MAX_DETAIL_FETCHES = 30


class ACLAnthologySource(IDataSource):
    """ACL Anthology conference proceedings source.

    Search strategies:
    1. Venue + year browsing  -- most reliable, zero delay.
       e.g. extra={"venues": ["acl", "emnlp"], "years": [2023, 2024]}
    2. Keyword search         -- uses Anthology search page.
       e.g. keywords=["transformer", "parsing"]
    3. Hybrid                 -- keyword filter on venue pages.
    """

    name = "acl_anthology"
    source_type = "api"
    description = (
        "Search ACL Anthology for NLP / Computational Linguistics authors. "
        "Covers ACL, EMNLP, NAACL, EACL, COLING, TACL, Findings. "
        "No API key required."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"acl_anthology": "paper_id"}
    example_queries = [
        "transformer parsing acl emnlp",
        "large language models naacl 2024",
        "machine translation findings",
        "question answering coling",
    ]
    auth_required = False
    rate_limit_notes = "Be polite: 1 request per second to Anthology servers."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=ACL_BASE,
                headers={
                    "User-Agent": (
                        "Oculai-TalentBot/1.0 "
                        "(mailto:contact@oculai.ai; +https://github.com/oculai)"
                    ),
                },
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    # -- search ----------------------------------------------------------

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search ACL Anthology for authors."""
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

        extra = query.extra or {}
        venues: list[str] = extra.get("venues", [])
        years: list[int] = extra.get("years", [])
        keywords = " ".join(query.keywords).lower()

        candidates: list[RawCandidate] = []
        try:
            client = await self._get_client()

            if venues or years:
                # Strategy 1: venue + year browsing
                candidates = await self._search_by_venue(
                    client, venues, years, keywords, query.limit
                )
            elif keywords:
                # Strategy 2: keyword search via Anthology search page
                candidates = await self._search_by_keyword(
                    client, keywords, query.limit
                )
            else:
                # Default: recent top venues
                candidates = await self._search_by_venue(
                    client,
                    DEFAULT_VENUES,
                    [2023, 2024, 2025],
                    "",
                    query.limit,
                )

            await consume_quota(self.name, amount=len(candidates))
            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={
                    "keywords": query.keywords,
                    "venues": venues,
                    "years": years,
                    "limit": query.limit,
                },
                status="success",
                duration_ms=duration_ms,
                records_count=len(candidates),
            )
            logger.info("ACL Anthology search returned %d candidates", len(candidates))

        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={
                    "keywords": query.keywords,
                    "venues": venues,
                    "years": years,
                },
                status="failed",
                duration_ms=duration_ms,
                error_message=str(e),
            )
            logger.exception("ACL Anthology search failed")

        return candidates

    # -- venue browsing --------------------------------------------------

    async def _search_by_venue(
        self,
        client: httpx.AsyncClient,
        venues: list[str],
        years: list[int],
        keyword_filter: str,
        limit: int,
    ) -> list[RawCandidate]:
        """Browse venue index pages and aggregate authors."""
        venues = venues or DEFAULT_VENUES
        if not years:
            # Default to last 3 years
            from datetime import datetime

            current_year = datetime.now().year
            years = list(range(current_year - 2, current_year + 1))

        # Normalize venue slugs
        venue_slugs = []
        for v in venues:
            v_norm = v.lower().replace(" ", "_")
            if v_norm in VENUE_SLUGS:
                venue_slugs.append(v_norm)
            else:
                # Pass through unknown slugs -- Anthology may support them
                venue_slugs.append(v_norm)

        # Fetch all venue pages in parallel with small concurrency
        semaphore = asyncio.Semaphore(3)
        all_papers: list[dict[str, Any]] = []

        async def _fetch_one(slug: str, year: int) -> list[dict[str, Any]]:
            async with semaphore:
                papers = await self._fetch_venue_page(client, slug, year)
                await asyncio.sleep(0.5)  # be polite
                return papers

        tasks = [
            asyncio.create_task(_fetch_one(slug, year))
            for slug in venue_slugs
            for year in years
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_papers.extend(r)

        # Filter by keyword if provided
        if keyword_filter:
            kws = [k.strip() for k in keyword_filter.split() if k.strip()]
            filtered = []
            for p in all_papers:
                title_lower = p.get("title", "").lower()
                if all(k in title_lower for k in kws):
                    filtered.append(p)
            all_papers = filtered

        # Aggregate authors
        author_map = self._aggregate_authors(all_papers)

        # Enrich top candidates with affiliations from TEI XML
        sorted_authors = sorted(
            author_map.values(),
            key=lambda a: a["paper_count"],
            reverse=True,
        )
        top_authors = sorted_authors[: min(limit * 2, len(sorted_authors))]
        enriched = await self._enrich_affiliations(client, top_authors)

        return self._to_candidates(enriched, limit)

    async def _fetch_venue_page(
        self, client: httpx.AsyncClient, slug: str, year: int
    ) -> list[dict[str, Any]]:
        """Parse an Anthology event page for paper listings."""
        url = f"/events/{slug}-{year}/"
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                logger.debug("Venue page not found: %s", url)
                return []
            resp.raise_for_status()
        except Exception as e:
            logger.debug("Failed to fetch venue page %s: %s", url, e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        papers: list[dict[str, Any]] = []

        # Paper listings are in <p> tags with class "d-sm-flex"
        for paper_p in soup.find_all("p", class_=lambda c: c and "d-sm-flex" in c):
            link = paper_p.find("a", href=True)
            if not link:
                continue

            href = link.get("href", "").strip("/")
            title = link.get_text(strip=True)
            if not href or not title:
                continue

            # Extract authors from the muted text span
            authors: list[str] = []
            author_span = paper_p.find("span", class_=lambda c: c and "text-muted" in c)
            if author_span:
                for author_link in author_span.find_all("a", href=True):
                    name = author_link.get_text(strip=True)
                    if name:
                        authors.append(name)

            papers.append({
                "id": href,
                "title": title,
                "authors": authors,
                "venue": VENUE_SLUGS.get(slug, slug.upper()),
                "year": year,
            })

            if len(papers) >= MAX_PAPERS_PER_VENUE:
                break

        logger.debug("Fetched %d papers from %s", len(papers), url)
        return papers

    # -- keyword search --------------------------------------------------

    async def _search_by_keyword(
        self, client: httpx.AsyncClient, keywords: str, limit: int
    ) -> list[RawCandidate]:
        """Search via Anthology search page and parse results."""
        query_str = quote_plus(keywords)
        url = f"/search/?q={query_str}"

        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.debug("Keyword search failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        papers: list[dict[str, Any]] = []

        # Search results have a similar structure to venue pages
        for paper_p in soup.find_all("p", class_=lambda c: c and "d-sm-flex" in c):
            link = paper_p.find("a", href=True)
            if not link:
                continue

            href = link.get("href", "").strip("/")
            title = link.get_text(strip=True)
            if not href or not title:
                continue

            authors: list[str] = []
            author_span = paper_p.find("span", class_=lambda c: c and "text-muted" in c)
            if author_span:
                for author_link in author_span.find_all("a", href=True):
                    name = author_link.get_text(strip=True)
                    if name:
                        authors.append(name)

            # Try to infer year and venue from the paper ID
            # Anthology IDs are like: 2024.acl-long.1
            year = 0
            venue = ""
            parts = href.split(".")
            if len(parts) >= 2 and parts[0].isdigit():
                year = int(parts[0])
                venue = parts[1].split("-")[0].upper()

            papers.append({
                "id": href,
                "title": title,
                "authors": authors,
                "venue": venue,
                "year": year,
            })

            if len(papers) >= limit * 3:
                break

        author_map = self._aggregate_authors(papers)
        sorted_authors = sorted(
            author_map.values(), key=lambda a: a["paper_count"], reverse=True
        )
        top_authors = sorted_authors[: min(limit * 2, len(sorted_authors))]
        enriched = await self._enrich_affiliations(client, top_authors)
        return self._to_candidates(enriched, limit)

    # -- author aggregation ----------------------------------------------

    def _aggregate_authors(
        self, papers: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Aggregate unique authors from paper listings."""
        seen: dict[str, dict[str, Any]] = {}
        for paper in papers:
            for name in paper.get("authors", []):
                key = name.lower()
                if key not in seen:
                    seen[key] = {
                        "name": name,
                        "paper_count": 0,
                        "papers": [],
                        "venues": set(),
                        "years": set(),
                    }
                seen[key]["paper_count"] += 1
                seen[key]["papers"].append(paper.get("title", ""))
                seen[key]["venues"].add(paper.get("venue", ""))
                if paper.get("year"):
                    seen[key]["years"].add(paper["year"])
        return seen

    # -- affiliation enrichment ------------------------------------------

    async def _enrich_affiliations(
        self, client: httpx.AsyncClient, authors: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fetch TEI XML for a sample of papers to extract affiliations."""
        # NOTE: Affiliation enrichment from TEI XML requires paper IDs.
        # The current aggregation only stores paper titles.  A future
        # enhancement could store paper IDs and fetch TEI XML to extract
        # <affiliation> elements.  For now we rely on downstream
        # enrichment (OpenAlex / Semantic Scholar) for institution data.
        return authors

    def _to_candidates(
        self, authors: list[dict[str, Any]], limit: int
    ) -> list[RawCandidate]:
        """Convert aggregated author dicts to RawCandidate objects."""
        candidates: list[RawCandidate] = []
        for a in authors[:limit]:
            venues = sorted(a.get("venues", set()))
            years = sorted(a.get("years", set()))
            candidates.append(
                RawCandidate(
                    name=a["name"],
                    paper_count=a["paper_count"],
                    research_areas=["natural_language_processing"],
                    raw_metadata={
                        "source": "acl_anthology",
                        "venues": venues,
                        "years": years,
                        "recent_papers": a.get("papers", [])[:5],
                        "note": (
                            "Aggregated from ACL Anthology. "
                            "Affiliations and citation counts not available; "
                            "use OpenAlex or Semantic Scholar for enrichment."
                        ),
                    },
                )
            )
        return candidates

    # -- get_detail ------------------------------------------------------

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch paper detail by Anthology paper ID.

        external_id is expected to be an Anthology paper ID such as
        ``2024.acl-long.1``.
        """
        start = time.perf_counter()
        try:
            client = await self._get_client()
            # Fetch TEI XML for structured metadata
            resp = await client.get(f"/{external_id}.tei.xml")
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "xml")
            title_el = soup.find("title")
            title = title_el.get_text(strip=True) if title_el else ""

            authors: list[str] = []
            for author in soup.find_all("author"):
                pers = author.find("persName")
                if pers:
                    forename = pers.find("forename")
                    surname = pers.find("surname")
                    parts = []
                    if forename:
                        parts.append(forename.get_text(strip=True))
                    if surname:
                        parts.append(surname.get_text(strip=True))
                    if parts:
                        authors.append(" ".join(parts))

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"paper_id": external_id},
                status="success",
                duration_ms=duration_ms,
                records_count=1,
            )

            return RawCandidate(
                name=authors[0] if authors else "Unknown",
                paper_count=1,
                raw_metadata={
                    "source": "acl_anthology",
                    "paper_id": external_id,
                    "title": title,
                    "authors": authors,
                },
            )

        except Exception:
            logger.exception("ACL Anthology get_detail failed for %s", external_id)
            return None

    # -- health ----------------------------------------------------------

    async def check_health(self) -> HealthStatus:
        """Check ACL Anthology website health."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get("/")
            resp.raise_for_status()
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(healthy=True, latency_ms=latency_ms)
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                healthy=False, latency_ms=latency_ms, error_message=str(e)
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
