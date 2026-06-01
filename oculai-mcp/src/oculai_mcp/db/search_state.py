"""SearchRoundState operations for deep search orchestrator."""

import logging
from typing import Any
from uuid import UUID

from oculai_mcp.db.client import execute_with_retry, fetch_with_retry, fetchrow_with_retry

logger = logging.getLogger(__name__)


async def record_search_round(
    run_id: UUID,
    hypothesis_id: str,
    source_name: str,
    round_number: int,
    query_used: dict[str, Any],
    results_count: int = 0,
    verified_count: int = 0,
    persisted_count: int = 0,
    signal_quality: float | None = None,
    result_diversity: float | None = None,
    is_saturated: bool = False,
    terminated_reason: str | None = None,
) -> UUID:
    """Record a search round's metrics."""
    row = await fetchrow_with_retry(
        """
        INSERT INTO searchroundstate (
            run_id, hypothesis_id, source_name, round_number, query_used,
            results_count, verified_count, persisted_count,
            signal_quality, result_diversity, is_saturated, terminated_reason
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (run_id, hypothesis_id, source_name, round_number) DO UPDATE SET
            query_used = EXCLUDED.query_used,
            results_count = EXCLUDED.results_count,
            verified_count = EXCLUDED.verified_count,
            persisted_count = EXCLUDED.persisted_count,
            signal_quality = EXCLUDED.signal_quality,
            result_diversity = EXCLUDED.result_diversity,
            is_saturated = EXCLUDED.is_saturated,
            terminated_reason = EXCLUDED.terminated_reason
        RETURNING round_id
        """,
        run_id, hypothesis_id, source_name, round_number, query_used,
        results_count, verified_count, persisted_count,
        signal_quality, result_diversity, is_saturated, terminated_reason,
    )
    return row["round_id"]


async def get_source_stats(run_id: UUID, source_name: str, hypothesis_id: str | None = None) -> dict[str, Any]:
    """Get aggregated stats for a source (or source+hypothesis)."""
    if hypothesis_id:
        rows = await fetch_with_retry(
            """
            SELECT * FROM searchroundstate
            WHERE run_id = $1 AND source_name = $2 AND hypothesis_id = $3
            ORDER BY round_number
            """,
            run_id, source_name, hypothesis_id,
        )
    else:
        rows = await fetch_with_retry(
            """
            SELECT * FROM searchroundstate
            WHERE run_id = $1 AND source_name = $2
            ORDER BY hypothesis_id, round_number
            """,
            run_id, source_name,
        )

    rounds = [dict(r) for r in rows]
    if not rounds:
        return {
            "calls_used": 0,
            "total_results": 0,
            "total_verified": 0,
            "total_persisted": 0,
            "avg_signal_quality": None,
            "is_saturated": False,
            "rounds": [],
        }

    total_results = sum(r["results_count"] for r in rounds)
    total_verified = sum(r["verified_count"] for r in rounds)
    total_persisted = sum(r["persisted_count"] for r in rounds)

    sq_values = [r["signal_quality"] for r in rounds if r["signal_quality"] is not None]
    avg_sq = sum(sq_values) / len(sq_values) if sq_values else None

    # Saturation: any round explicitly marked, or all rounds have low diversity
    is_saturated = any(r["is_saturated"] for r in rounds)
    low_diversity_count = sum(
        1 for r in rounds
        if r["result_diversity"] is not None and r["result_diversity"] < 0.7
    )
    if low_diversity_count >= 3:
        is_saturated = True

    return {
        "calls_used": len(rounds),
        "total_results": total_results,
        "total_verified": total_verified,
        "total_persisted": total_persisted,
        "avg_signal_quality": avg_sq,
        "is_saturated": is_saturated,
        "rounds": rounds,
    }


async def mark_source_saturated(
    run_id: UUID,
    source_name: str,
    hypothesis_id: str,
    round_number: int,
    reason: str = "diversity_threshold",
) -> None:
    """Mark a specific round as saturated."""
    await execute_with_retry(
        """
        UPDATE searchroundstate
        SET is_saturated = true, terminated_reason = $1
        WHERE run_id = $2 AND source_name = $3 AND hypothesis_id = $4 AND round_number = $5
        """,
        reason, run_id, source_name, hypothesis_id, round_number,
    )
    logger.info("Marked saturated: run=%s source=%s hypo=%s round=%s reason=%s",
                run_id, source_name, hypothesis_id, round_number, reason)


async def get_run_search_progress(run_id: UUID) -> dict[str, Any]:
    """Get overall search progress for a run."""
    row = await fetchrow_with_retry(
        """
        SELECT
            COUNT(*) AS total_rounds,
            COUNT(DISTINCT source_name) AS sources_used,
            COUNT(DISTINCT hypothesis_id) AS hypotheses_used,
            SUM(results_count) AS total_results,
            SUM(verified_count) AS total_verified,
            SUM(persisted_count) AS total_persisted,
            SUM(CASE WHEN is_saturated THEN 1 ELSE 0 END) AS saturated_rounds,
            AVG(signal_quality) FILTER (WHERE signal_quality IS NOT NULL) AS avg_signal_quality
        FROM searchroundstate
        WHERE run_id = $1
        """,
        run_id,
    )

    # Per-source breakdown
    source_rows = await fetch_with_retry(
        """
        SELECT
            source_name,
            COUNT(*) AS rounds,
            SUM(results_count) AS results,
            SUM(persisted_count) AS persisted,
            AVG(signal_quality) FILTER (WHERE signal_quality IS NOT NULL) AS avg_quality,
            BOOL_OR(is_saturated) AS is_saturated
        FROM searchroundstate
        WHERE run_id = $1
        GROUP BY source_name
        ORDER BY results DESC
        """,
        run_id,
    )

    return {
        "run_id": str(run_id),
        "total_rounds": row["total_rounds"] or 0,
        "sources_used": row["sources_used"] or 0,
        "hypotheses_used": row["hypotheses_used"] or 0,
        "total_results": row["total_results"] or 0,
        "total_verified": row["total_verified"] or 0,
        "total_persisted": row["total_persisted"] or 0,
        "saturated_rounds": row["saturated_rounds"] or 0,
        "avg_signal_quality": float(row["avg_signal_quality"]) if row["avg_signal_quality"] else None,
        "per_source": [
            {
                "source_name": r["source_name"],
                "rounds": r["rounds"],
                "results": r["results"],
                "persisted": r["persisted"],
                "avg_signal_quality": float(r["avg_quality"]) if r["avg_quality"] else None,
                "is_saturated": r["is_saturated"],
            }
            for r in source_rows
        ],
    }


async def get_last_two_rounds(
    run_id: UUID,
    source_name: str,
    hypothesis_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Get the last two rounds for a source+hypothesis for diversity comparison."""
    rows = await fetch_with_retry(
        """
        SELECT * FROM searchroundstate
        WHERE run_id = $1 AND source_name = $2 AND hypothesis_id = $3
        ORDER BY round_number DESC
        LIMIT 2
        """,
        run_id, source_name, hypothesis_id,
    )
    results = [dict(r) for r in rows]
    if len(results) >= 2:
        return results[1], results[0]  # (previous, current)
    if len(results) == 1:
        return None, results[0]
    return None, None
