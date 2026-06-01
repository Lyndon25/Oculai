"""Candidate management — upsert, identity linking, listing, retrieval."""

import re
from typing import Any
from uuid import UUID, uuid4

from oculai_mcp.db import identities, runs
from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry, fetchval_with_retry, get_db_pool


# ---------------------------------------------------------------------------
# Person name validation — reject garbage before it enters the database
# ---------------------------------------------------------------------------

# Patterns that strongly indicate the "name" is NOT a person
_NAME_REJECTION_PATTERNS = [
    # Job postings
    re.compile(r"招聘|实习|职位|年薪|待遇|薪资|五险一金|社招|校招|内推|急聘|诚聘|高薪"
               r"|招聘信息| hiring | internship |职位描述|岗位职责|任职要求", re.I),
    # Article / tutorial titles
    re.compile(r"详解|教程|指南|入门|速览|解析|全解析|深度解析|原理|实战"
               r"|从.*到.*|如何.*|怎么.*|是什么|介绍|必读|系列|合集", re.I),
    # Chinese article title markers
    re.compile(r"[:：].{3,}"),  # colon with content after = almost certainly an article title
    re.compile(r"[《》「」『』]"),  # Chinese book/article quote marks
    re.compile(r"[@＠]"),  # social media handles / mentions
    # Generic / non-person
    re.compile(r"^\d+$"),  # pure numbers
    re.compile(r"^\d{4,}_\d+"),  # IDs like 2401_84419493
    re.compile(r"开心文库|哔哩哔哩|知乎|CSDN|掘金|博客园|简书"),  # platform names as "name"
]

# Minimum signals required for a new Person to be considered valid
_MINIMUM_SIGNAL_FIELDS = {"institution", "github_id", "orcid", "google_scholar_id",
                          "linkedin_url", "dblp_key", "email"}


def _is_reasonable_person_name(name: str) -> tuple[bool, str]:
    """Return (is_valid, reason_if_invalid).

    Heuristic validation for person names.  Not perfect, but catches the
    bulk of article titles, job postings, and platform noise that currently
    pollutes the database.
    """
    if not name or not isinstance(name, str):
        return False, "name is empty or not a string"

    name = name.strip()
    if len(name) < 2:
        return False, "name too short (less than 2 characters)"

    # Check rejection patterns
    for pat in _NAME_REJECTION_PATTERNS:
        if pat.search(name):
            return False, f"name matches garbage pattern: '{name[:40]}...' looks like an article title, job posting, or platform noise"

    # Chinese names: typically 2-4 hanzi, or hanzi + English name
    hanzi_count = sum(1 for ch in name if "一" <= ch <= "鿿")
    if hanzi_count > 0:
        # If it's mostly Chinese but has strong article markers, reject
        if hanzi_count >= 5 and any(c in name for c in "：:"):
            return False, "name looks like a Chinese article title (contains colon and many characters)"
        # Reasonable Chinese name length
        if hanzi_count > 6 and len(name) > 12:
            return False, "name too long for a Chinese person name (>6 hanzi)"

    # English names: should not be all lowercase (very short) or all uppercase
    alpha_chars = [c for c in name if c.isalpha()]
    if alpha_chars and all(c.islower() for c in alpha_chars):
        # Allow lowercase usernames that are 3+ chars (GitHub, Juejin, CSDN handles)
        if len(name) < 3:
            return False, "name is all lowercase and too short (<3 characters)"
    if alpha_chars and all(c.isupper() for c in alpha_chars):
        return False, "name is all uppercase — probably an acronym or title"

    # Must contain at least some alphabetic or CJK characters
    if not any(c.isalpha() or ("一" <= c <= "鿿") for c in name):
        return False, "name contains no recognizable alphabetic or Chinese characters"

    return True, ""


def _has_minimum_signal(person_data: dict[str, Any]) -> tuple[bool, str]:
    """Return (has_signal, reason_if_not).

    A candidate needs at least ONE verifiable signal beyond just a name
    to be worth tracking.  This prevents random web pages from becoming
    Person rows.
    """
    present = {k for k in _MINIMUM_SIGNAL_FIELDS if person_data.get(k)}
    if present:
        return True, ""

    # Academic output is a verifiable signal (e.g. arXiv, DBLP)
    if person_data.get("paper_count", 0) > 0:
        return True, ""

    # Also accept if there is a profile_url that looks like a real profile page
    profile_url = person_data.get("profile_url", "")
    if profile_url and any(d in profile_url.lower() for d in (
        "github.com", "juejin.cn/user", "zhihu.com/people",
        "blog.csdn.net", "scholar.google", "orcid.org",
        "arxiv.org",
    )):
        return True, ""

    # Community contribution signals in raw_metadata (GitHub, Juejin, CSDN, Zhihu)
    raw_md = person_data.get("raw_metadata", {}) or {}
    if isinstance(raw_md, dict):
        if raw_md.get("public_repos", 0) > 0 or raw_md.get("followers", 0) > 5:
            return True, ""
        if raw_md.get("article_count", 0) > 0 or raw_md.get("fans_count", 0) > 5:
            return True, ""
        if raw_md.get("followers_count", 0) > 5 or raw_md.get("digg_count", 0) > 10:
            return True, ""
        if raw_md.get("total_visits", 0) > 100:
            return True, ""

    return False, (
        "candidate lacks minimum verifiable signals. "
        "Need at least one of: institution, github_id, orcid, google_scholar_id, "
        "linkedin_url, dblp_key, or a recognized profile page URL. "
        "Raw search results without structured data must be enriched before upsert."
    )


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

    ENFORCED VALIDATION (rejects garbage at the gate):
    - name must pass person-name heuristics (no article titles, job postings, etc.)
    - new persons must have at least one verifiable signal (institution, external id, etc.)
    - result_type=job_posting is always rejected
    """
    # --- Gate 1: result_type filter ---
    result_type = person_data.get("result_type", "unknown")
    if result_type == "job_posting":
        return {
            "person_id": None,
            "record_id": None,
            "match_type": "rejected",
            "action": "rejected",
            "reason": "result_type='job_posting' is not a person — DISCARD per Decision Matrix",
        }

    # --- Gate 2: name validation ---
    name = person_data.get("name", "")
    name_ok, name_reason = _is_reasonable_person_name(name)
    if not name_ok:
        return {
            "person_id": None,
            "record_id": None,
            "match_type": "rejected",
            "action": "rejected",
            "reason": f"INVALID_NAME: {name_reason}",
        }

    # --- Gate 3: check if this is a merge into existing person ---
    # If we matched an existing person by external ID, we allow lower signal
    # because the person already passed validation once.
    external_ids = {
        "orcid": person_data.get("orcid"),
        "google_scholar": person_data.get("google_scholar_id"),
        "github": person_data.get("github_id"),
        "linkedin": person_data.get("linkedin_url"),
        "dblp": person_data.get("dblp_key"),
    }

    person_id = None
    match_type = "new"
    for source_type, ext_id in external_ids.items():
        if ext_id:
            person_id = await identities.find_person_by_identity(source_type, ext_id)
            if person_id:
                match_type = f"external_id:{source_type}"
                break

    if person_id is None:
        person_id = await identities.find_person_by_name_institution(
            name, person_data.get("institution")
        )
        if person_id:
            match_type = "name_institution"

    if person_id is None:
        person_id = await identities.find_person_by_fuzzy_name(
            name, person_data.get("institution")
        )
        if person_id:
            match_type = "fuzzy_name"

    is_existing = person_id is not None

    # --- Gate 4: minimum signal for NEW persons ---
    if not is_existing:
        signal_ok, signal_reason = _has_minimum_signal(person_data)
        if not signal_ok:
            return {
                "person_id": None,
                "record_id": None,
                "match_type": "rejected",
                "action": "rejected",
                "reason": f"MINIMUM_SIGNAL_REQUIRED: {signal_reason}",
            }

    # --- Proceed with upsert ---
    institution = person_data.get("institution")

    if not is_existing:
        # Create new Person (already validated above)
        person_id = uuid4()
        aliases = person_data.get("aliases")
        position = person_data.get("position") or person_data.get("job_title")
        pool_tags = person_data.get("pool_tags")
        await execute_with_retry(
            """
            INSERT INTO person (person_id, canonical_name, aliases, latest_institution,
                latest_position, total_papers, h_index, total_citations,
                orcid, google_scholar_id, github_id, linkedin_url,
                pool_tags, created_by_agent, updated_by_agent)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $14)
            """,
            person_id, name, aliases, institution,
            position,
            person_data.get("paper_count", 0),
            person_data.get("h_index", 0),
            person_data.get("citation_count", 0),
            external_ids["orcid"], external_ids["google_scholar"],
            external_ids["github"], external_ids["linkedin"],
            pool_tags,
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

    # Create CandidateRecord with rich extraction metadata
    raw_data = {
        "source": source_name,
        "original": person_data,
        "extraction": {
            "result_type": person_data.get("result_type", "unknown"),
            "confidence": person_data.get("confidence", "medium"),
            "extraction_method": person_data.get("extraction_method", "direct"),
            "verified_by": agent_id,
        },
    }
    record_id = await runs.create_candidate_record(
        run_id, person_id,
        raw_data=raw_data,
        created_by_agent=agent_id,
    )

    return {
        "person_id": str(person_id),
        "record_id": str(record_id) if record_id else None,
        "match_type": match_type,
        "action": "merged" if match_type != "new" else "created",
    }


async def _resolve_identity(conn, person_data: dict[str, Any]) -> tuple[UUID | None, str]:
    """Resolve identity for a single candidate using an existing DB connection."""
    external_ids = {
        "orcid": person_data.get("orcid"),
        "google_scholar": person_data.get("google_scholar_id"),
        "github": person_data.get("github_id"),
        "linkedin": person_data.get("linkedin_url"),
        "dblp": person_data.get("dblp_key"),
    }
    person_id = None
    match_type = "new"
    for source_type, ext_id in external_ids.items():
        if ext_id:
            person_id = await conn.fetchval(
                "SELECT find_person_by_identity($1, $2)", source_type, ext_id
            )
            if person_id:
                match_type = f"external_id:{source_type}"
                break
    if person_id is None:
        person_id = await conn.fetchval(
            "SELECT find_person_by_name_institution($1, $2)",
            person_data.get("name", ""), person_data.get("institution"),
        )
        if person_id:
            match_type = "name_institution"
    if person_id is None:
        person_id = await conn.fetchval(
            "SELECT find_person_by_fuzzy_name($1, $2, $3)",
            person_data.get("name", ""), person_data.get("institution"), 0.7,
        )
        if person_id:
            match_type = "fuzzy_name"
    return person_id, match_type


async def upsert_candidates_batch(
    run_id: UUID,
    candidates_list: list[dict[str, Any]],
    source_name: str = "unknown",
    agent_id: str = "system",
) -> dict[str, Any]:
    """Batch upsert candidates using a single DB transaction.

    Eliminates per-candidate connection-pool overhead.  Still runs full
    validation and identity resolution for each candidate.
    """
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for person_data in candidates_list:
                name = person_data.get("name", "")
                result_type = person_data.get("result_type", "unknown")

                # Gate 1: job posting
                if result_type == "job_posting":
                    rejected.append({
                        "name": name, "action": "rejected",
                        "reason": "result_type='job_posting' is not a person",
                    })
                    continue

                # Gate 2: name validation
                name_ok, name_reason = _is_reasonable_person_name(name)
                if not name_ok:
                    rejected.append({
                        "name": name, "action": "rejected",
                        "reason": f"INVALID_NAME: {name_reason}",
                    })
                    continue

                # Gate 3: identity resolution
                person_id, match_type = await _resolve_identity(conn, person_data)
                is_existing = person_id is not None

                # Gate 4: minimum signal for new persons
                if not is_existing:
                    signal_ok, signal_reason = _has_minimum_signal(person_data)
                    if not signal_ok:
                        rejected.append({
                            "name": name, "action": "rejected",
                            "reason": f"MINIMUM_SIGNAL_REQUIRED: {signal_reason}",
                        })
                        continue

                # Proceed with upsert
                institution = person_data.get("institution")
                external_ids = {
                    "orcid": person_data.get("orcid"),
                    "google_scholar": person_data.get("google_scholar_id"),
                    "github": person_data.get("github_id"),
                    "linkedin": person_data.get("linkedin_url"),
                    "dblp": person_data.get("dblp_key"),
                }

                if not is_existing:
                    person_id = uuid4()
                    aliases = person_data.get("aliases")
                    position = person_data.get("position") or person_data.get("job_title")
                    pool_tags = person_data.get("pool_tags")
                    await conn.execute(
                        """
                        INSERT INTO person (person_id, canonical_name, aliases, latest_institution,
                            latest_position, total_papers, h_index, total_citations,
                            orcid, google_scholar_id, github_id, linkedin_url,
                            pool_tags, created_by_agent, updated_by_agent)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $14)
                        """,
                        person_id, name, aliases, institution, position,
                        person_data.get("paper_count", 0),
                        person_data.get("h_index", 0),
                        person_data.get("citation_count", 0),
                        external_ids["orcid"], external_ids["google_scholar"],
                        external_ids["github"], external_ids["linkedin"],
                        pool_tags, agent_id,
                    )
                    match_type = "new"
                    for st, eid in external_ids.items():
                        if eid:
                            await conn.execute(
                                """
                                INSERT INTO personexternalidentity
                                    (identity_id, person_id, source_type, external_id, external_url, confidence, verified_by_agent)
                                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6)
                                ON CONFLICT (source_type, external_id) DO NOTHING
                                """,
                                person_id, st, eid, None, 1.0, agent_id,
                            )
                else:
                    # Merge data into existing Person (stored procedure)
                    await conn.execute(
                        "SELECT merge_person_data($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                        person_id, institution,
                        person_data.get("paper_count"),
                        person_data.get("h_index"),
                        person_data.get("citation_count"),
                        external_ids["orcid"],
                        external_ids["google_scholar"],
                        external_ids["github"],
                        external_ids["linkedin"],
                        agent_id,
                    )
                    aliases = person_data.get("aliases")
                    position = person_data.get("position") or person_data.get("job_title")
                    pool_tags = person_data.get("pool_tags")
                    if aliases is not None or position is not None or pool_tags is not None:
                        await conn.execute(
                            """
                            UPDATE person
                            SET aliases = COALESCE(aliases, $2),
                                latest_position = COALESCE(latest_position, $3),
                                pool_tags = COALESCE(pool_tags, $4),
                                updated_at = now(),
                                updated_by_agent = $5,
                                data_version = data_version + 1
                            WHERE person_id = $1
                            """,
                            person_id, aliases, position, pool_tags, agent_id,
                        )

                # Create CandidateRecord
                raw_data = {
                    "source": source_name,
                    "original": person_data,
                    "extraction": {
                        "result_type": person_data.get("result_type", "unknown"),
                        "confidence": person_data.get("confidence", "medium"),
                        "extraction_method": person_data.get("extraction_method", "direct"),
                        "verified_by": agent_id,
                    },
                }
                record_row = await conn.fetchrow(
                    """INSERT INTO candidaterecord (record_id, run_id, person_id, raw_data, created_by_agent, updated_by_agent)
                       VALUES (gen_random_uuid(), $1, $2, $3, $4, $4)
                       ON CONFLICT (run_id, person_id) DO NOTHING RETURNING record_id""",
                    run_id, person_id, raw_data, agent_id,
                )
                record_id = record_row["record_id"] if record_row else None
                if record_id is None:
                    existing = await conn.fetchrow(
                        "SELECT record_id FROM candidaterecord WHERE run_id = $1 AND person_id = $2",
                        run_id, person_id,
                    )
                    record_id = existing["record_id"] if existing else None

                accepted.append({
                    "person_id": str(person_id),
                    "record_id": str(record_id) if record_id else None,
                    "match_type": match_type,
                    "action": "merged" if match_type != "new" else "created",
                    "name": name,
                })

    return {
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
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
