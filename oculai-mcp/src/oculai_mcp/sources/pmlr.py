"""Proceedings of Machine Learning Research (PMLR) data source.

Covers ICML, AISTATS, UAI, CoRL, and other ML conferences published through
PMLR (http://proceedings.mlr.press).

Searches by venue+year (browsing volume pages) or by keyword.
Parses paper listings from volume index pages and extracts authors.
No API key required.
"""

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, try_consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

PMLR_BASE = "https://proceedings.mlr.press"

# Known conference name fragments mapped to slugs
CONFERENCE_PATTERNS: dict[str, list[str]] = {
    "icml": [
        "international conference on machine learning",
        "icml",
    ],
    "aistats": [
        "international conference on artificial intelligence and statistics",
        "aistats",
    ],
    "uai": [
        "conference on uncertainty in artificial intelligence",
        "uai",
    ],
    "corl": [
        "conference on robot learning",
        "corl",
    ],
}

DEFAULT_CONFERENCES = ["icml", "aistats", "uai", "corl"]
MAX_PAPERS_PER_VOLUME = 200
VOLUME_FETCH_CONCURRENCY = 3


class PMLRSource(IDataSource):
    """PMLR proceedings source for ML conferences.

    Search strategies:
    1. Venue + year browsing  -- parse volume index pages.
       e.g. extra={"venues": ["icml", "aistats"], "years": [2023, 2024]}
    2. Keyword search         -- filter papers by title across recent volumes.
    """

    name = "pmlr"
    source_type = "api"
    description = (
        "Search PMLR proceedings for ML authors. "
        "Covers ICML, AISTATS, UAI, CoRL. "
        "No API key required."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"pmlr": "paper_url"}
    example_queries = [
        "reinforcement learning icml",
        "transformer architecture aistats",
        "bayesian optimization uai",
        "robot manipulation corl",
    ]
    auth_required = False
    rate_limit_notes = "Be polite: ~1 request per second to PMLR servers."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._volume_cache: dict[str, dict[str, Any]] | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=PMLR_BASE,
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
        """Search PMLR for authors."""
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

            # Build volume list (conference -> list of volume URLs + years)
            volume_map = await self._build_volume_map(client)

            if venues or years:
                candidates = await self._search_by_venue(
                    client, volume_map, venues, years, keywords, query.limit
                )
            elif keywords:
                candidates = await self._search_by_keyword(
                    client, volume_map, keywords, query.limit
                )
            else:
                # Default: recent ICML + AISTATS
                candidates = await self._search_by_venue(
                    client, volume_map, ["icml", "aistats"], [], "", query.limit
                )

            await try_consume_quota(self.name, amount=len(candidates))
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
            logger.info("PMLR search returned %d candidates", len(candidates))

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
            logger.exception("PMLR search failed")

        return candidates

    # -- volume discovery ------------------------------------------------

    async def _build_volume_map(
        self, client: httpx.AsyncClient
    ) -> dict[str, list[dict[str, Any]]]:
        """Parse the PMLR homepage to map conferences to volume URLs/years.

        Returns: {conference_slug: [{"url": str, "year": int}, ...]}
        """
        if self._volume_cache is not None:
            return self._volume_cache

        try:
            resp = await client.get("/")
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Failed to fetch PMLR volume list: %s", e)
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        volume_map: dict[str, list[dict[str, Any]]] = {slug: [] for slug in CONFERENCE_PATTERNS}

        # PMLR lists proceedings as links like /v235/ with a title
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            match = re.match(r"/v(\d+)/$", href)
            if not match:
                continue

            vol_num = int(match.group(1))
            title = link.get_text(strip=True).lower()

            # Infer year from volume number heuristic (not perfect but works for recent)
            year = self._infer_year_from_volume(vol_num)
            # Try to extract explicit year from title
            year_match = re.search(r"\b(20\d{2})\b", title)
            if year_match:
                year = int(year_match.group(1))

            for slug, patterns in CONFERENCE_PATTERNS.items():
                if any(p in title for p in patterns):
                    volume_map[slug].append({
                        "url": href,
                        "volume": vol_num,
                        "year": year,
                        "title": title,
                    })
                    break

        # Sort by year descending
        for slug in volume_map:
            volume_map[slug].sort(key=lambda x: x.get("year", 0) or 0, reverse=True)

        self._volume_cache = volume_map
        logger.debug(
            "PMLR volume map: %s",
            {k: len(v) for k, v in volume_map.items()},
        )
        return volume_map

    def _infer_year_from_volume(self, vol_num: int) -> int:
        """Rough heuristic: PMLR volumes increase over time.
        v1 ~ 2009, v200+ ~ 2023-2024."""
        if vol_num >= 230:
            return 2024
        if vol_num >= 200:
            return 2023
        if vol_num >= 160:
            return 2022
        if vol_num >= 130:
            return 2021
        if vol_num >= 100:
            return 2020
        if vol_num >= 70:
            return 2019
        return 2018

    # -- venue browsing --------------------------------------------------

    async def _search_by_venue(
        self,
        client: httpx.AsyncClient,
        volume_map: dict[str, list[dict[str, Any]]],
        venues: list[str],
        years: list[int],
        keyword_filter: str,
        limit: int,
    ) -> list[RawCandidate]:
        """Browse specific venue volumes and aggregate authors."""
        target_slugs = [v.lower() for v in venues] if venues else list(CONFERENCE_PATTERNS.keys())

        # Collect volume URLs to fetch
        volumes_to_fetch: list[dict[str, Any]] = []
        for slug in target_slugs:
            for vol in volume_map.get(slug, []):
                if not years or vol.get("year") in years:
                    volumes_to_fetch.append(vol)

        if not volumes_to_fetch:
            logger.warning("No PMLR volumes matched venues=%s years=%s", venues, years)
            return []

        # Fetch with limited concurrency
        semaphore = asyncio.Semaphore(VOLUME_FETCH_CONCURRENCY)
        all_papers: list[dict[str, Any]] = []

        async def _fetch_one(vol: dict[str, Any]) -> list[dict[str, Any]]:
            async with semaphore:
                papers = await self._fetch_volume_page(client, vol)
                await asyncio.sleep(0.5)
                return papers

        tasks = [asyncio.create_task(_fetch_one(vol)) for vol in volumes_to_fetch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_papers.extend(r)

        # Filter by keyword
        if keyword_filter:
            kws = [k.strip() for k in keyword_filter.split() if k.strip()]
            filtered = []
            for p in all_papers:
                title_lower = p.get("title", "").lower()
                if all(k in title_lower for k in kws):
                    filtered.append(p)
            all_papers = filtered

        author_map = self._aggregate_authors(all_papers)
        sorted_authors = sorted(
            author_map.values(), key=lambda a: a["paper_count"], reverse=True
        )
        return self._to_candidates(sorted_authors[:limit])

    async def _fetch_volume_page(
        self, client: httpx.AsyncClient, vol: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Parse a single PMLR volume page for paper listings."""
        url = vol.get("url", "")
        if not url:
            return []

        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
        except Exception as e:
            logger.debug("Failed to fetch PMLR volume %s: %s", url, e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        papers: list[dict[str, Any]] = []

        # PMLR volume pages list papers in div.paper elements
        for paper_div in soup.find_all("div", class_="paper"):
            title_link = paper_div.find("p", class_="title")
            title = ""
            paper_url = ""
            if title_link:
                a = title_link.find("a", href=True)
                if a:
                    title = a.get_text(strip=True)
                    paper_url = urljoin(PMLR_BASE, a.get("href", ""))

            authors: list[str] = []
            authors_p = paper_div.find("p", class_="details")
            if authors_p:
                # Authors are often in <i> or just text within details
                for span in authors_p.find_all("span", class_="authors"):
                    author_text = span.get_text(strip=True)
                    authors.extend([a.strip() for a in author_text.split(",") if a.strip()])
                if not authors:
                    # Fallback: try the whole details text
                    text = authors_p.get_text(strip=True)
                    # Often formatted as "Author One, Author Two · PDF"
                    text = text.split("·")[0]
                    authors.extend([a.strip() for a in text.split(",") if a.strip()])

            if title and authors:
                papers.append({
                    "id": paper_url or f"{vol['volume']}-{len(papers)}",
                    "title": title,
                    "authors": authors,
                    "venue": vol.get("title", ""),
                    "year": vol.get("year", 0),
                })

            if len(papers) >= MAX_PAPERS_PER_VOLUME:
                break

        logger.debug("Fetched %d papers from PMLR volume %s", len(papers), url)
        return papers

    # -- keyword search --------------------------------------------------

    async def _search_by_keyword(
        self,
        client: httpx.AsyncClient,
        volume_map: dict[str, list[dict[str, Any]]],
        keywords: str,
        limit: int,
    ) -> list[RawCandidate]:
        """Search across recent volumes by keyword in paper titles."""
        # Use the 2 most recent volumes of each conference
        volumes_to_fetch: list[dict[str, Any]] = []
        for slug, vols in volume_map.items():
            for vol in vols[:2]:
                volumes_to_fetch.append(vol)

        semaphore = asyncio.Semaphore(VOLUME_FETCH_CONCURRENCY)
        all_papers: list[dict[str, Any]] = []

        async def _fetch_one(vol: dict[str, Any]) -> list[dict[str, Any]]:
            async with semaphore:
                papers = await self._fetch_volume_page(client, vol)
                await asyncio.sleep(0.5)
                return papers

        tasks = [asyncio.create_task(_fetch_one(vol)) for vol in volumes_to_fetch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_papers.extend(r)

        kws = [k.strip() for k in keywords.split() if k.strip()]
        filtered = []
        for p in all_papers:
            title_lower = p.get("title", "").lower()
            if all(k in title_lower for k in kws):
                filtered.append(p)

        author_map = self._aggregate_authors(filtered)
        sorted_authors = sorted(
            author_map.values(), key=lambda a: a["paper_count"], reverse=True
        )
        return self._to_candidates(sorted_authors[:limit])

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

    def _to_candidates(
        self, authors: list[dict[str, Any]]
    ) -> list[RawCandidate]:
        """Convert aggregated author dicts to RawCandidate objects."""
        candidates: list[RawCandidate] = []
        for a in authors:
            venues = sorted(a.get("venues", set()))
            years = sorted(a.get("years", set()))
            candidates.append(
                RawCandidate(
                    name=a["name"],
                    paper_count=a["paper_count"],
                    research_areas=["machine_learning"],
                    raw_metadata={
                        "source": "pmlr",
                        "venues": venues,
                        "years": years,
                        "recent_papers": a.get("papers", [])[:5],
                        "note": (
                            "Aggregated from PMLR proceedings. "
                            "Affiliations and citation counts not available; "
                            "use OpenAlex or Semantic Scholar for enrichment."
                        ),
                    },
                )
            )
        return candidates

    # -- get_detail ------------------------------------------------------

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch paper detail by PMLR paper URL or ID."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            url = external_id if external_id.startswith("http") else f"{PMLR_BASE}/{external_id}"
            resp = await client.get(url)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Title is usually in an <h1> or <p class="title">
            title = ""
            title_el = soup.find("h1")
            if title_el:
                title = title_el.get_text(strip=True)
            else:
                title_p = soup.find("p", class_="title")
                if title_p:
                    title = title_p.get_text(strip=True)

            # Authors
            authors: list[str] = []
            authors_p = soup.find("p", class_="details")
            if authors_p:
                for span in authors_p.find_all("span", class_="authors"):
                    author_text = span.get_text(strip=True)
                    authors.extend([a.strip() for a in author_text.split(",") if a.strip()])
                if not authors:
                    text = authors_p.get_text(strip=True)
                    text = text.split("·")[0]
                    authors.extend([a.strip() for a in text.split(",") if a.strip()])

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"paper_url": external_id},
                status="success",
                duration_ms=duration_ms,
                records_count=1,
            )

            return RawCandidate(
                name=authors[0] if authors else "Unknown",
                paper_count=1,
                raw_metadata={
                    "source": "pmlr",
                    "paper_url": external_id,
                    "title": title,
                    "authors": authors,
                },
            )

        except Exception:
            logger.exception("PMLR get_detail failed for %s", external_id)
            return None

    # -- health ----------------------------------------------------------

    async def check_health(self) -> HealthStatus:
        """Check PMLR website health."""
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
