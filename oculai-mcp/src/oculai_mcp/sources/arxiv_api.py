"""arXiv API data source.

Implements the arXiv API as documented at:
  https://info.arxiv.org/help/api/user-manual.html

Endpoint: https://export.arxiv.org/api/query
Response: Atom 1.0 XML with arXiv and OpenSearch extensions.

Note: arXiv returns papers, not author profiles. We aggregate by author name
to produce RawCandidate objects.
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery
from oculai_mcp.utils.chinese_names import has_china_affiliation

logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

# arXiv recommends a descriptive User-Agent.
USER_AGENT = "Oculai-TalentBot/1.0 (https://github.com/oculai; contact@oculai.ai)"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}

# API limits per https://info.arxiv.org/help/api/user-manual.html
MAX_RESULTS_PER_SLICE = 2000
MAX_RESULTS_TOTAL = 30000


class ArxivAPISource(IDataSource):
    """Real arXiv API data source.

    Returns candidates aggregated by author from paper search results.
    """

    name = "arxiv"
    source_type = "api"
    description = "Search arXiv papers by keyword and aggregate by author. Returns paper counts, venues, and co-author information. No API key required."
    supported_operations = ["search", "get_detail"]
    id_field_map = {"arxiv": "author_name"}
    example_queries = [
        "transformer architecture",
        "reinforcement learning robotics",
        "natural language processing",
        "computer vision deep learning",
        "federated learning",
    ]
    auth_required = False
    rate_limit_notes = "No API key required. Be polite with request frequency. Recommended: 1 request per 3 seconds."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0, headers=DEFAULT_HEADERS)
        return self._client

    def _build_search_query(self, keywords: list[str], mode: str = "and") -> str:
        """Build a proper arXiv search_query string.

        Official syntax: field_prefix:term combined with AND/OR/ANDNOT.
        We prefix every keyword with ``all:`` so the boolean scope is explicit.
        Spaces inside keywords are preserved; httpx will URL-encode them.
        """
        terms = [f"all:{kw}" for kw in keywords]
        joiner = " AND " if mode == "and" else " OR "
        return joiner.join(terms)

    async def _execute_search(
        self,
        client: httpx.AsyncClient,
        query: SearchQuery,
        search_query: str,
    ) -> list[RawCandidate]:
        """Execute a single arXiv search and return parsed candidates."""
        max_results = min(max(query.limit * 5, 500), MAX_RESULTS_PER_SLICE)

        params: dict[str, str | int] = {
            "search_query": search_query,
            "start": query.offset,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        resp = await client.get(ARXIV_API_URL, params=params)
        resp.raise_for_status()

        total_results = self._parse_total_results(resp.text)
        candidates = self._parse_feed(resp.text, query.limit, year_filter=query.years)
        logger.info(
            "arXiv query '%s' returned %d candidates (total_results=%s)",
            search_query,
            len(candidates),
            total_results,
        )
        return candidates

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search arXiv papers by keywords and aggregate by author."""
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

        candidates: list[RawCandidate] = []

        try:
            client = await self._get_client()

            # Model controls AND/OR via query.extra["mode"]; default is "and".
            mode = (query.extra or {}).get("mode", "and")
            search_query = self._build_search_query(query.keywords, mode=mode)
            candidates = await self._execute_search(
                client, query, search_query,
            )

            # Only auto-fallback when model did not explicitly pick a mode.
            if not candidates and len(query.keywords) > 1 and "mode" not in (query.extra or {}):
                logger.info("arXiv AND query returned no results, trying OR fallback")
                search_query = self._build_search_query(query.keywords, mode="or")
                candidates = await self._execute_search(
                    client, query, search_query,
                )

            await consume_quota(self.name, amount=len(candidates))

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={
                    "keywords": query.keywords,
                    "limit": query.limit,
                },
                status="success",
                duration_ms=duration_ms,
                records_count=len(candidates),
            )

            logger.info(
                "arXiv API search returned %d candidates",
                len(candidates),
            )

        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords},
                status="failed",
                duration_ms=duration_ms,
                error_message=str(e),
            )
            logger.exception("arXiv API search failed")

        # --- China-First soft sorting ---
        if (query.extra or {}).get("china_first", True):
            china = [c for c in candidates if has_china_affiliation(c.institution, c.name)]
            non_china = [c for c in candidates if c not in china]
            candidates = china + non_china
            candidates = candidates[:query.limit]

        return candidates

    def _parse_total_results(self, xml_text: str) -> int | None:
        """Extract opensearch:totalResults from the feed."""
        try:
            root = ET.fromstring(xml_text.encode("utf-8"))
        except ET.ParseError:
            return None

        total_el = root.find("opensearch:totalResults", NAMESPACES)
        if total_el is not None and total_el.text:
            try:
                return int(total_el.text)
            except ValueError:
                return None
        return None

    def _parse_feed(
        self,
        xml_text: str,
        limit: int,
        year_filter: tuple[int, int] | None = None,
    ) -> list[RawCandidate]:
        """Parse arXiv Atom feed and aggregate authors."""
        try:
            root = ET.fromstring(xml_text.encode("utf-8"))
        except ET.ParseError as e:
            logger.error("Failed to parse arXiv XML: %s", e)
            return []

        # Map: author_name -> {paper_count, papers: [], institution: str | None, categories: [], co_authors: set}
        authors: dict[str, dict[str, Any]] = {}

        for entry in root.findall("atom:entry", NAMESPACES):
            title_el = entry.find("atom:title", NAMESPACES)
            title = title_el.text.strip() if title_el is not None and title_el.text else ""

            summary_el = entry.find("atom:summary", NAMESPACES)
            summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

            published_el = entry.find("atom:published", NAMESPACES)
            year = 0
            if published_el is not None and published_el.text:
                try:
                    year = int(published_el.text[:4])
                except ValueError:
                    year = 0

            if year_filter and year:
                start_year, end_year = year_filter
                if not (start_year <= year <= end_year):
                    continue

            # Extract arXiv primary category and all categories
            primary_cat = ""
            categories: list[str] = []
            for cat_el in entry.findall("atom:category", NAMESPACES):
                term = cat_el.get("term", "")
                if term:
                    categories.append(term)
            if not categories:
                # Try arxiv:primary_category
                pc_el = entry.find("arxiv:primary_category", NAMESPACES)
                if pc_el is not None:
                    primary_cat = pc_el.get("term", "")
                    if primary_cat:
                        categories.append(primary_cat)

            # Collect all authors on this paper for co-author tracking
            paper_authors: list[str] = []
            for author_el in entry.findall("atom:author", NAMESPACES):
                name_el = author_el.find("atom:name", NAMESPACES)
                if name_el is not None and name_el.text:
                    paper_authors.append(name_el.text.strip())

            for author_el in entry.findall("atom:author", NAMESPACES):
                name_el = author_el.find("atom:name", NAMESPACES)
                if name_el is None or not name_el.text:
                    continue
                name = name_el.text.strip()

                # arXiv extension: <arxiv:affiliation>
                affil_el = author_el.find("arxiv:affiliation", NAMESPACES)
                institution = affil_el.text.strip() if affil_el is not None and affil_el.text else None

                if name not in authors:
                    authors[name] = {
                        "paper_count": 0,
                        "papers": [],
                        "institution": institution,
                        "categories": [],
                        "co_authors": set(),
                        "summaries": [],
                    }

                authors[name]["paper_count"] += 1
                authors[name]["papers"].append({
                    "title": title,
                    "year": year,
                    "categories": categories,
                    "summary": summary[:500] if summary else "",
                })
                authors[name]["categories"].extend(categories)
                authors[name]["summaries"].append(summary[:300] if summary else "")
                # Add co-authors (other authors on same paper)
                for coa in paper_authors:
                    if coa != name:
                        authors[name]["co_authors"].add(coa)

                # Keep the first non-empty institution we see.
                if institution and not authors[name]["institution"]:
                    authors[name]["institution"] = institution

        # Sort by paper count, take top `limit`
        sorted_authors = sorted(
            authors.items(), key=lambda x: x[1]["paper_count"], reverse=True
        )

        candidates = []
        for name, data in sorted_authors[:limit]:
            research_areas = self._extract_research_areas(
                data["papers"], data.get("summaries", [])
            )
            # Deduplicate and count categories
            cat_counts: dict[str, int] = {}
            for c in data.get("categories", []):
                cat_counts[c] = cat_counts.get(c, 0) + 1
            top_categories = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            # Build an arXiv author search URL as a verifiable profile link
            from urllib.parse import quote_plus
            arxiv_search_url = f"https://arxiv.org/search/?searchtype=author&query={quote_plus(name)}"

            candidates.append(
                RawCandidate(
                    name=name,
                    institution=data.get("institution"),
                    paper_count=data["paper_count"],
                    h_index=0,  # arXiv does not provide h-index
                    citation_count=0,  # arXiv does not provide citation counts
                    research_areas=research_areas if research_areas else None,
                    profile_url=arxiv_search_url,
                    raw_metadata={
                        "source": "arxiv_api",
                        "recent_papers": data["papers"][:5],
                        "top_categories": [c[0] for c in top_categories],
                        "category_counts": dict(top_categories),
                        "co_authors_sample": sorted(data.get("co_authors", set()))[:10],
                        "co_author_count": len(data.get("co_authors", set())),
                        "data_quality_note": (
                            "Aggregated from arXiv paper search. h-index and citation counts "
                            "are not available from arXiv; use Semantic Scholar or OpenAlex "
                            "for bibliometric enrichment."
                        ),
                    },
                )
            )

        return candidates

    def _extract_research_areas(
        self, papers: list[dict[str, Any]], summaries: list[str] | None = None
    ) -> list[str]:
        """Extract research areas from paper titles, categories, and abstracts."""
        keywords = {
            "nlp": "natural_language_processing",
            "language model": "large_language_models",
            "transformer": "deep_learning",
            "llm": "large_language_models",
            "large language": "large_language_models",
            "vision": "computer_vision",
            "image": "computer_vision",
            "reinforcement": "reinforcement_learning",
            "rl": "reinforcement_learning",
            "robot": "robotics",
            "graph": "graph_neural_networks",
            "federated": "federated_learning",
            "optimization": "optimization",
            "generation": "generative_models",
            "diffusion": "generative_models",
            "retrieval": "information_retrieval",
            "recommendation": "recommendation_systems",
            "inference": "llm_inference",
            "serving": "llm_inference",
            "quantization": "model_quantization",
            "speculative": "speculative_decoding",
            "batching": "llm_inference",
            "attention": "transformer_architecture",
            "cuda": "gpu_acceleration",
            "kernel": "gpu_acceleration",
            "distributed": "distributed_systems",
        }
        found: set[str] = set()
        text = " ".join(p.get("title", "").lower() for p in papers)
        # Also include arXiv categories (e.g., cs.CL, cs.LG, cs.CV)
        for p in papers:
            for cat in p.get("categories", []):
                text += " " + cat.lower()
        if summaries:
            text += " " + " ".join(s.lower() for s in summaries)
        for kw, area in keywords.items():
            if kw in text:
                found.add(area)
        return sorted(found)[:5]

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch detailed info for an author by name.

        arXiv has no per-author ID endpoint, so ``external_id`` is treated as
        the author's display name. We search with ``au:`` prefix and aggregate.
        """
        start = time.perf_counter()

        try:
            client = await self._get_client()
            params: dict[str, str | int] = {
                "search_query": f"au:{external_id}",
                "start": 0,
                "max_results": 50,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }

            resp = await client.get(ARXIV_API_URL, params=params)
            resp.raise_for_status()

            candidates = self._parse_feed(resp.text, limit=1)
            if not candidates:
                return None

            candidate = candidates[0]
            if candidate.name.lower() != external_id.lower():
                logger.warning(
                    "arXiv author mismatch: expected %s, got %s",
                    external_id,
                    candidate.name,
                )

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"author": external_id},
                status="success",
                duration_ms=duration_ms,
                records_count=1,
            )

            return candidate

        except Exception:
            logger.exception("arXiv API detail failed for %s", external_id)
            return None

    async def check_health(self) -> HealthStatus:
        """Check arXiv API health with a minimal query."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get(
                ARXIV_API_URL,
                params={"search_query": "all:test", "max_results": 1},
            )
            resp.raise_for_status()
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(healthy=True, latency_ms=latency_ms)

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                healthy=False,
                latency_ms=latency_ms,
                error_message=str(e),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
