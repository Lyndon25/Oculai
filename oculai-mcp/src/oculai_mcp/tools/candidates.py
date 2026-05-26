"""Candidate management — upsert, identity linking, listing, retrieval."""

from typing import Any
from uuid import UUID, uuid4

from oculai_mcp.db import identities, runs
from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry, fetchval_with_retry


async def upsert_candidate(
    run_id: UUID,
    person_data: dict[str, Any],
    source_name: str = "unknown",
    agent_id: str = "system",
) -> dict[str, Any]:
    """Idempotent candidate upsert with identity resolution.

    Checks for existing Person by external IDs, then by name+institution,
    then by fuzzy name match. Creates new Person if no match found.
    Creates CandidateRecord linking Person to Run.
    """
    name = person_data.get("name", "")
    institution = person_data.get("institution")
    external_ids = {
        "orcid": person_data.get("orcid"),
        "google_scholar": person_data.get("google_scholar_id"),
        "github": person_data.get("github_id"),
        "linkedin": person_data.get("linkedin_url"),
        "dblp": person_data.get("dblp_key"),
    }

    # 1. Try hard match by external ID
    person_id = None
    match_type = "new"
    for source_type, ext_id in external_ids.items():
        if ext_id:
            person_id = await identities.find_person_by_identity(source_type, ext_id)
            if person_id:
                match_type = f"external_id:{source_type}"
                break

    # 2. Try name + institution match
    if person_id is None:
        person_id = await identities.find_person_by_name_institution(name, institution)
        if person_id:
            match_type = "name_institution"

    # 3. Try fuzzy name match
    if person_id is None:
        person_id = await identities.find_person_by_fuzzy_name(name, institution)
        if person_id:
            match_type = "fuzzy_name"

    # 4. Create new Person
    if person_id is None:
        person_id = uuid4()
        await execute_with_retry(
            """
            INSERT INTO person (person_id, canonical_name, latest_institution,
                total_papers, h_index, total_citations,
                orcid, google_scholar_id, github_id, linkedin_url,
                created_by_agent, updated_by_agent)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11)
            """,
            person_id, name, institution,
            person_data.get("paper_count", 0),
            person_data.get("h_index", 0),
            person_data.get("citation_count", 0),
            external_ids["orcid"], external_ids["google_scholar"],
            external_ids["github"], external_ids["linkedin"],
            agent_id,
        )
        match_type = "new"

        # Link external identities
        for source_type, ext_id in external_ids.items():
            if ext_id:
                await identities.link_person_identity(
                    person_id, source_type, ext_id,
                    verified_by_agent=agent_id,
                )
    else:
        # Merge data into existing Person
        await identities.merge_person_data(person_id, person_data, agent_id)

    # Create CandidateRecord
    record_id = await runs.create_candidate_record(
        run_id, person_id,
        raw_data={"source": source_name, "original": person_data},
        created_by_agent=agent_id,
    )

    return {
        "person_id": str(person_id),
        "record_id": str(record_id) if record_id else None,
        "match_type": match_type,
        "action": "merged" if match_type != "new" else "created",
    }


async def link_identity(
    person_id: UUID,
    source_type: str,
    external_id: str,
    external_url: str | None = None,
    confidence: float = 1.0,
    verified_by_agent: str = "system",
) -> dict[str, Any]:
    """Link an external identity to a Person."""
    identity_id = await identities.link_person_identity(
        person_id, source_type, external_id,
        external_url=external_url, confidence=confidence,
        verified_by_agent=verified_by_agent,
    )
    return {
        "identity_id": str(identity_id) if identity_id else None,
        "person_id": str(person_id),
        "source_type": source_type,
        "external_id": external_id,
    }


async def list_candidates(
    run_id: UUID,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List candidates in a run with basic person info."""
    records = await runs.get_candidate_records(run_id, status, limit, offset)

    # Enrich with person names
    result = []
    for r in records:
        person = await fetchrow_with_retry(
            "SELECT canonical_name, latest_institution, h_index, total_citations FROM person WHERE person_id = $1",
            r["person_id"],
        )
        result.append({
            "record_id": str(r["record_id"]),
            "person_id": str(r["person_id"]),
            "name": person["canonical_name"] if person else "unknown",
            "institution": person["latest_institution"] if person else None,
            "h_index": person["h_index"] if person else 0,
            "total_citations": person["total_citations"] if person else 0,
            "status": r["status"],
            "quality_score": r["quality_score"],
            "created_at": str(r["created_at"]),
        })

    params: list[Any] = [run_id]
    sql = "SELECT COUNT(*) FROM candidaterecord WHERE run_id = $1"
    if status:
        sql += f" AND status = ${len(params) + 1}"
        params.append(status)
    total = await fetchval_with_retry(sql, *params)

    return {"candidates": result, "total": total, "limit": limit, "offset": offset}


async def get_candidate(person_id: UUID) -> dict[str, Any] | None:
    """Get full candidate profile with all related data."""
    person = await fetchrow_with_retry("SELECT * FROM person WHERE person_id = $1", person_id)
    if not person:
        return None

    identities_rows = await fetch_with_retry(
        "SELECT * FROM personexternalidentity WHERE person_id = $1", person_id,
    )
    works = await fetch_with_retry(
        "SELECT work_id, type, title, venue, year, citations, doi FROM academicwork WHERE person_id = $1 ORDER BY year DESC LIMIT 50",
        person_id,
    )
    events = await fetch_with_retry(
        "SELECT * FROM careerevent WHERE person_id = $1 ORDER BY start_date DESC", person_id,
    )
    evidence = await fetch_with_retry(
        "SELECT * FROM evidence WHERE person_id = $1 ORDER BY captured_at DESC LIMIT 100", person_id,
    )
    assessments = await fetch_with_retry(
        "SELECT * FROM candidateassessment WHERE person_id = $1 ORDER BY created_at DESC", person_id,
    )

    return {
        "person": dict(person),
        "identities": [dict(r) for r in identities_rows],
        "publications": [dict(r) for r in works],
        "career": [dict(r) for r in events],
        "evidence": [dict(r) for r in evidence],
        "assessments": [dict(r) for r in assessments],
    }
