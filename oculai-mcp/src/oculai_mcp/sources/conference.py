"""Conference proceedings data source.

Wraps OpenAlex and DBLP with conference-specific filters.
Searches for authors who have published in top-tier conferences
(NeurIPS, ICML, ICLR, CVPR, ACL, SIGGRAPH, etc.).

Does NOT depend on external conference API — it uses existing
OpenAlex and DBLP connectors with venue filters.
"""

import logging
import time
from typing import Any

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery
from oculai_mcp.sources.registry import create_source

logger = logging.getLogger(__name__)

# Top-tier conference venue identifiers for OpenAlex
TOP_CONFERENCES: dict[str, list[str]] = {
    "machine_learning": [
        "NeurIPS", "ICML", "ICLR", "AISTATS", "UAI", "JMLR",
        "Advances in Neural Information Processing Systems",
        "International Conference on Machine Learning",
        "International Conference on Learning Representations",
    ],
    "computer_vision": [
        "CVPR", "ICCV", "ECCV", "WACV", "BMVC",
        "Conference on Computer Vision and Pattern Recognition",
        "International Conference on Computer Vision",
    ],
    "natural_language_processing": [
        "ACL", "EMNLP", "NAACL", "EACL", "COLING", "TACL",
        "Association for Computational Linguistics",
        "Conference on Empirical Methods in Natural Language Processing",
    ],
    "robotics": [
        "ICRA", "IROS", "RSS", "CoRL",
        "International Conference on Robotics and Automation",
    ],
    "systems": [
        "OSDI", "SOSP", "NSDI", "ATC", "EuroSys", "ASPLOS",
        "Symposium on Operating Systems Principles",
    ],
    "security": [
        "CCS", "S&P", "USENIX Security", "NDSS",
        "Conference on Computer and Communications Security",
    ],
    "graphics": [
        "SIGGRAPH", "SIGGRAPH Asia", "Eurographics",
        "ACM Transactions on Graphics",
    ],
    "databases": [
        "VLDB", "SIGMOD", "ICDE", "PODS",
        "Very Large Data Bases",
    ],
    "theory": [
        "STOC", "FOCS", "SODA", "ICALP", "LICS",
        "Symposium on Theory of Computing",
    ],
    "human_computer_interaction": [
        "CHI", "UIST", "CSCW", "IMWUT",
        "Conference on Human Factors in Computing Systems",
    ],
}

CONF_VENUE_IDS: dict[str, list[str]] = {
    # OpenAlex venue IDs for top AI/CS conferences
    "ml": [
        "V1985057772",  # NeurIPS
        "V62064948",    # ICML
        "V53714991",    # ICLR
        "V146601267",   # JMLR
        "V118263185",   # AISTATS
    ],
    "cv": [
        "V305832705",   # CVPR
        "V7628591",     # ICCV
        "V192954279",   # ECCV
    ],
    "nlp": [
        "V1069528586",  # ACL
        "V92362120",    # EMNLP
        "V15750028",    # NAACL
    ],
    "robotics": [
        "V120634652",   # ICRA
        "V68963513",    # IROS
    ],
}

class ConferenceSource(IDataSource):
    """Conference proceedings search via OpenAlex venue filter.

    Searches for authors who publish in specific top-tier conferences.
    This is a composite source: delegates to OpenAlex and DBLP with
    conference-specific query parameters.

    Usage:
        source = ConferenceSource()
        candidates = await source.search(SearchQuery(
            keywords=["transformer", "attention"],
            conferences=["ml", "nlp"],  # ← new field
            limit=20,
        ))
    """

    name = "conference"
    source_type = "api"
    description = (
        "Search authors by their publications in top-tier CS conferences "
        "(NeurIPS, ICML, ICLR, CVPR, ACL, SIGGRAPH, etc.). Uses OpenAlex "
        "and DBLP APIs with venue filters. No API key required."
    )
    supported_operations = ["search", "get_detail"]
    id_field_map = {"openalex": "author_id", "dblp": "dblp_key"}
    example_queries = [
        "transformer architecture neurips icml",
        "reinforcement learning icml neurips",
        "nlp large language models acl emnlp",
        "computer vision object detection cvpr",
        "robotics manipulation icra iros",
    ]
    auth_required = False
    rate_limit_notes = "Delegates to OpenAlex (100k/day) and DBLP (unlimited)."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://api.openalex.org",
                headers={"User-Agent": "Oculai-TalentBot/1.0 (mailto:contact@oculai.ai)"},
                timeout=30.0,
            )
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Search for authors via conference proceedings."""
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

        conferences = (query.extra or {}).get("conferences", [])
        keywords = " ".join(query.keywords)

        candidates: list[RawCandidate] = []
        try:
            client = await self._get_client()

            # Build venue filter
            venue_ids = self._resolve_venue_ids(conferences)
            candidates = await self._search_openalex_works(
                client, keywords, venue_ids, query.limit
            )

            # Enrich with DBLP if available
            if len(candidates) < query.limit:
                dblp_candidates = await self._search_dblp_conference(
                    keywords, conferences, query.limit - len(candidates)
                )
                # Merge/dedup by name
                existing_names = {c.name.lower() for c in candidates}
                for dc in dblp_candidates:
                    if dc.name.lower() not in existing_names:
                        candidates.append(dc)

            await consume_quota(self.name, amount=len(candidates))
            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={
                    "keywords": query.keywords,
                    "conferences": conferences,
                    "limit": query.limit,
                },
                status="success",
                duration_ms=duration_ms,
                records_count=len(candidates),
            )
            logger.info("Conference search returned %d candidates", len(candidates))

        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"keywords": query.keywords, "conferences": conferences},
                status="failed",
                duration_ms=duration_ms,
                error_message=str(e),
            )
            logger.exception("Conference search failed")

        return candidates

    def _resolve_venue_ids(self, conferences: list[str]) -> list[str]:
        """Resolve conference area names to OpenAlex venue IDs."""
        venue_ids: list[str] = []
        for area in conferences:
            area_lower = area.lower().replace(" ", "_")
            ids = CONF_VENUE_IDS.get(area_lower, [])
            venue_ids.extend(ids)
        # If no specific venues selected, use all CS venues
        if not venue_ids:
            for ids_list in CONF_VENUE_IDS.values():
                venue_ids.extend(ids_list)
        return venue_ids

    async def _search_openalex_works(
        self,
        client: httpx.AsyncClient,
        keywords: str,
        venue_ids: list[str],
        limit: int,
    ) -> list[RawCandidate]:
        """Search OpenAlex works filtered by venue IDs."""
        venue_filter = "|".join(venue_ids[:10])  # Max 10 venues per query
        params: dict[str, str | int] = {
            "search": keywords,
            "per_page": min(limit * 5, 100),
            "sort": "cited_by_count:desc",
            "filter": f"primary_location.source.id:{venue_filter}",
        }
        resp = await client.get("/works", params=params)
        resp.raise_for_status()
        data = resp.json()

        seen: dict[str, dict[str, Any]] = {}
        for work in data.get("results", []):
            for authorship in work.get("authorships", []):
                author = authorship.get("author", {})
                author_id_raw = author.get("id", "")
                author_id = author_id_raw.split("/")[-1] if "/" in author_id_raw else author_id_raw
                if not author_id or author_id in seen:
                    continue

                insts = authorship.get("institutions", []) or []
                institution = insts[0].get("display_name") if insts else None

                orcid = author.get("orcid") or ""
                if "/" in str(orcid):
                    orcid = str(orcid).split("/")[-1]

                source_info = (work.get("primary_location", {}) or {}).get("source", {}) or {}
                venue_name = source_info.get("display_name") or ""

                seen[author_id] = {
                    "name": author.get("display_name", "Unknown"),
                    "institution": institution,
                    "orcid": orcid,
                    "work_count": 1,
                    "total_citations": work.get("cited_by_count", 0) or 0,
                    "venue": venue_name,
                }

        sorted_authors = sorted(
            seen.values(), key=lambda a: a["total_citations"], reverse=True
        )
        return [
            RawCandidate(
                name=a["name"],
                institution=a.get("institution"),
                orcid=a.get("orcid"),
                paper_count=a["work_count"],
                citation_count=a["total_citations"],
                raw_metadata={
                    "source": "conference",
                    "sub_source": "openalex",
                    "top_venue": a.get("venue"),
                },
            )
            for a in sorted_authors[:limit]
        ]

    async def _search_dblp_conference(
        self,
        keywords: str,
        conferences: list[str],
        limit: int,
    ) -> list[RawCandidate]:
        """Fallback: search DBLP with conference names as venue hints."""
        try:
            source = create_source("dblp")
            if source is None:
                return []

            # Append conference names to keywords for DBLP search
            conf_keywords = []
            for area in conferences:
                area_lower = area.lower().replace("_", " ")
                names = TOP_CONFERENCES.get(area_lower, [])[:3]
                conf_keywords.extend(names)
            search_terms = f"{keywords} {' '.join(conf_keywords[:3])}"

            query = SearchQuery(keywords=[search_terms], limit=limit)
            return await source.search(query)
        except Exception:
            logger.debug("DBLP conference fallback failed", exc_info=True)
            return []

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch author detail from OpenAlex by author ID."""
        try:
            source = create_source("openalex")
            if source is None:
                return None
            return await source.get_detail(external_id)
        except Exception:
            logger.exception("Conference get_detail failed for %s", external_id)
            return None

    async def check_health(self) -> HealthStatus:
        """Check health via OpenAlex."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            resp = await client.get("/works", params={"search": "test", "per_page": 1})
            resp.raise_for_status()
            return HealthStatus(healthy=True, latency_ms=(time.perf_counter() - start) * 1000)
        except Exception as e:
            return HealthStatus(healthy=False, latency_ms=(time.perf_counter() - start) * 1000, error_message=str(e))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
