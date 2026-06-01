"""Single-candidate deep evidence gathering across all sources.

Systematically probes every available source for additional evidence
about a candidate, using name variants and cross-linking.
"""

from typing import Any
from uuid import UUID

from oculai_mcp.db.client import fetch_with_retry, fetchrow_with_retry
from oculai_mcp.tools import evidence as evidence_tool
from oculai_mcp.tools import sources
from oculai_mcp.utils.chinese_names import build_search_probe


async def deep_dive_candidate(
    run_id: UUID,
    person_id: UUID,
    max_searches_per_source: int = 2,
) -> dict[str, Any]:
    """Perform deep evidence gathering for a single candidate.

    Steps:
    1. Read candidate's current profile + existing evidence
    2. Generate search probes (name variants, institution aliases)
    3. For each known external ID: fetch_source_detail
    4. For name + institution combos: search across sources
    5. Attach all new evidence with proper tier assignment
    6. Return summary

    Args:
        run_id: The run UUID
        person_id: The Person UUID
        max_searches_per_source: Limit to avoid quota exhaustion (default 2)
    """
    # 1. Read current profile
    person = await fetchrow_with_retry(
        """
        SELECT canonical_name, aliases, latest_institution, orcid, github_id, google_scholar_id
        FROM person WHERE person_id = $1
        """,
        person_id,
    )
    if not person:
        return {"status": "error", "reason": "Person not found", "new_evidence_count": 0}

    existing_evidence = await fetch_with_retry(
        "SELECT source_name, source_url, evidence_type FROM evidence WHERE run_id = $1 AND person_id = $2",
        run_id, person_id,
    )
    existing_keys = {(r["source_name"], r["source_url"], r["evidence_type"]) for r in existing_evidence}

    # 2. Build search probes
    chinese_name = person["canonical_name"]
    english_name = _extract_english_name(person["aliases"] or [])
    probe = build_search_probe(chinese_name, person["latest_institution"], english_name)

    new_evidence: list[dict[str, Any]] = []
    sources_probed: list[str] = []
    errors: list[str] = []

    # 3. Fetch details for known external IDs
    external_ids: dict[str, str] = {}
    if person["orcid"]:
        external_ids["orcid"] = person["orcid"]
    if person["github_id"]:
        external_ids["github"] = person["github_id"]
    if person["google_scholar_id"]:
        external_ids["google_scholar"] = person["google_scholar_id"]

    for source_type, ext_id in external_ids.items():
        try:
            detail = await sources.fetch_source_detail(source_type, ext_id)
            if detail and detail.get("raw_data"):
                ev = await evidence_tool.attach_evidence(
                    person_id=person_id,
                    run_id=run_id,
                    evidence_type="profile",
                    title=f"{source_type} profile detail",
                    source_name=source_type,
                    source_url=detail.get("url", ""),
                    content=detail.get("raw_data", {}),
                    confidence=0.9,
                    captured_by_agent="deep_dive",
                )
                new_evidence.append(ev)
                sources_probed.append(f"{source_type}:detail")
        except Exception as e:
            errors.append(f"{source_type} detail fetch failed: {e}")

    # 4. Search across sources with name variants
    search_keywords = probe["name_variants"][:3]  # Top 3 variants to avoid quota blowout
    if probe["institution_canonical"]:
        search_keywords = [f"{kw} {probe['institution_canonical']}" for kw in search_keywords]

    searchable_sources = [
        "baidu_qianfan", "github", "semantic_scholar", "openalex",
        "juejin", "csdn", "arxiv", "dblp",
    ]

    for source_name in searchable_sources:
        if len(sources_probed) >= max_searches_per_source * len(searchable_sources):
            break
        try:
            result = await sources.search_source(
                source_name=source_name,
                keywords=search_keywords,
                run_id=run_id,
                limit=5,
            )
            for candidate in result.get("candidates", []):
                # Simple dedup: skip if same source+url+type already exists
                c_url = candidate.get("source_url", "") or candidate.get("profile_url", "")
                c_type = candidate.get("result_type", "profile")
                if (source_name, c_url, c_type) in existing_keys:
                    continue

                ev = await evidence_tool.attach_evidence(
                    person_id=person_id,
                    run_id=run_id,
                    evidence_type=_map_result_type_to_evidence_type(c_type),
                    title=candidate.get("name", f"{source_name} result"),
                    source_name=source_name,
                    source_url=c_url,
                    content=candidate.get("raw_data", candidate),
                    confidence=candidate.get("confidence", 0.7),
                    captured_by_agent="deep_dive",
                )
                new_evidence.append(ev)
                existing_keys.add((source_name, c_url, c_type))

            sources_probed.append(source_name)
        except Exception as e:
            errors.append(f"{source_name} search failed: {e}")

    return {
        "status": "completed" if not errors else "partial",
        "person_id": str(person_id),
        "run_id": str(run_id),
        "new_evidence_count": len(new_evidence),
        "sources_probed": sources_probed,
        "errors": errors,
        "probe_used": probe,
    }


def _extract_english_name(aliases: list[str]) -> str | None:
    """Try to extract an English name from aliases list."""
    for alias in aliases:
        # Heuristic: English names have ASCII letters and spaces only
        if alias and all(c.isascii() and (c.isalpha() or c.isspace() or c == ".") for c in alias):
            parts = alias.strip().split()
            if 1 <= len(parts) <= 4 and len(alias) >= 3:
                return alias.strip()
    return None


def _map_result_type_to_evidence_type(result_type: str) -> str:
    """Map source result_type to evidence_type_t domain value."""
    mapping = {
        "profile_page": "profile",
        "article": "blog_post",
        "publication": "paper",
        "repo": "code",
        "web_page": "web_page",
    }
    return mapping.get(result_type, "web_page")
