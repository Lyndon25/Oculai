"""Candidate assessment — scoring, recording, shortlist generation."""

from typing import Any
from uuid import UUID

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry


async def score_candidate(
    run_id: UUID,
    person_id: UUID,
    dimensions: dict[str, float],
    assessor_agent: str,
    evidence_ids: list[str] | None = None,
    confidence: float = 1.0,
    rationale: str = "",
) -> dict[str, Any]:
    """Score a candidate across multiple dimensions. Each dimension is scored."""
    assessment_ids = []
    for dim, score in dimensions.items():
        row = await fetchrow_with_retry(
            """
            INSERT INTO candidateassessment
                (run_id, person_id, assessor_agent, dimension, score, confidence, rationale, evidence_ids)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (run_id, person_id, assessor_agent, dimension)
            DO UPDATE SET score = EXCLUDED.score, confidence = EXCLUDED.confidence,
                          rationale = EXCLUDED.rationale, evidence_ids = EXCLUDED.evidence_ids,
                          updated_at = now()
            RETURNING assessment_id
            """,
            run_id, person_id, assessor_agent, dim, score, confidence, rationale,
            [UUID(e) for e in evidence_ids] if evidence_ids else [],
        )
        if row:
            assessment_ids.append(str(row["assessment_id"]))

    # Compute and update overall score on CandidateRecord
    overall = await _compute_overall_score(person_id, run_id)

    return {
        "person_id": str(person_id),
        "assessment_ids": assessment_ids,
        "dimensions_scored": list(dimensions.keys()),
        "overall_score": overall,
    }


async def record_assessment(
    run_id: UUID,
    person_id: UUID,
    assessor_agent: str,
    dimension: str,
    score: float,
    confidence: float = 1.0,
    rationale: str = "",
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Record a single dimension assessment."""
    row = await fetchrow_with_retry(
        """
        INSERT INTO candidateassessment (run_id, person_id, assessor_agent, dimension, score, confidence, rationale, evidence_ids)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (run_id, person_id, assessor_agent, dimension)
        DO UPDATE SET score = EXCLUDED.score, confidence = EXCLUDED.confidence,
                      rationale = EXCLUDED.rationale, evidence_ids = EXCLUDED.evidence_ids,
                      updated_at = now()
        RETURNING assessment_id
        """,
        run_id, person_id, assessor_agent, dimension, score, confidence, rationale,
        [UUID(e) for e in evidence_ids] if evidence_ids else [],
    )
    assessment_id = str(row["assessment_id"]) if row else None
    return {"assessment_id": assessment_id, "person_id": str(person_id), "dimension": dimension, "score": score}


async def get_shortlist(
    run_id: UUID,
    min_score: float = 0,
    limit: int = 20,
) -> dict[str, Any]:
    """Get shortlisted candidates ranked by overall score."""
    rows = await fetch_with_retry(
        """
        SELECT cr.record_id, cr.person_id, cr.status, cr.quality_score,
               p.canonical_name, p.latest_institution, p.h_index, p.total_citations, p.total_papers
        FROM candidaterecord cr
        JOIN person p ON p.person_id = cr.person_id
        WHERE cr.run_id = $1
          AND (cr.quality_score >= $2 OR $2 = 0)
        ORDER BY cr.quality_score DESC
        LIMIT $3
        """,
        run_id, min_score, limit,
    )

    shortlist = []
    for r in rows:
        # Get dimension scores
        scores = await fetch_with_retry(
            "SELECT dimension, score, confidence FROM candidateassessment WHERE run_id = $1 AND person_id = $2",
            run_id, r["person_id"],
        )
        shortlist.append({
            "record_id": str(r["record_id"]),
            "person_id": str(r["person_id"]),
            "name": r["canonical_name"],
            "institution": r["latest_institution"],
            "h_index": r["h_index"],
            "total_citations": r["total_citations"],
            "total_papers": r["total_papers"],
            "overall_score": r["quality_score"],
            "dimensions": {s["dimension"]: {"score": s["score"], "confidence": s["confidence"]} for s in scores},
        })

    return {"run_id": str(run_id), "shortlist": shortlist, "count": len(shortlist)}


async def _compute_overall_score(person_id: UUID, run_id: UUID) -> float:
    """Compute weighted overall score from dimension assessments."""
    row = await fetchrow_with_retry(
        "SELECT AVG(score) as overall FROM candidateassessment WHERE run_id = $1 AND person_id = $2",
        run_id, person_id,
    )
    overall = round(row["overall"], 1) if row and row["overall"] else 0.0

    # Update CandidateRecord quality_score
    await execute_with_retry(
        "UPDATE candidaterecord SET quality_score = $3, updated_at = now(), updated_by_agent = 'system' WHERE run_id = $1 AND person_id = $2",
        run_id, person_id, int(overall * 10),
    )
    return overall
