"""Deep Search Orchestrator — iterative, budget-aware, saturation-driven search.

Manages the full search loop: probe → budget → iterate → detect gaps → terminate.
No LLM calls. All decisions are deterministic heuristics.
"""

import asyncio
import logging
import time
from typing import Any
from uuid import UUID

from oculai_mcp.db import search_state
from oculai_mcp.db.client import fetch_with_retry
from oculai_mcp.tools import candidates as candidates_tool
from oculai_mcp.tools.sources import search_source
from oculai_mcp.tools.site_crawler import crawl_site

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "max_duration_minutes": 30,
    "max_total_calls": 200,
    "source_call_budget": {
        "github": 40,
        "openalex": 30,
        "arxiv": 30,
        "juejin": 30,
        "csdn": 30,
        "semantic_scholar": 20,
        "dblp": 20,
        "zhihu": 20,
        "baidu_scholar": 20,
        "baidu": 20,
        "duckduckgo": 20,
        "personal_homepage": 10,
        "industry": 10,
        "conference": 10,
    },
    "saturation_threshold": 0.7,
    "min_signal_quality": 0.15,
    "low_signal_cutoff": 0.05,
    "gap_fill_enabled": True,
    "probe_rounds_per_combo": 2,
    "max_concurrent_sources": 4,
    "batch_upsert_interval": 10,  # upsert every N search calls
    # Site crawl enrichment (Phase 5.5)
    "site_crawl_enabled": False,
    "site_crawl_max_candidates": 5,
    "site_crawl_max_pages": 10,
    "site_crawl_max_depth": 2,
    "site_crawl_min_quality_score": 0,
}

# China-first source weights for initial budget allocation
_SOURCE_PRIORITY_WEIGHTS = {
    "baidu_scholar": 1.4,
    "zhihu": 1.4,
    "juejin": 1.3,
    "csdn": 1.3,
    "baidu": 1.2,
    "github": 1.1,
    "duckduckgo": 1.0,
    "openalex": 1.0,
    "arxiv": 1.0,
    "semantic_scholar": 0.9,
    "dblp": 0.8,
    "conference": 0.7,
    "personal_homepage": 0.6,
    "industry": 0.6,
    "acl_anthology": 0.7,
    "pmlr": 0.7,
}


# ---------------------------------------------------------------------------
# Saturation detection
# ---------------------------------------------------------------------------

def _compute_diversity(current_names: set[str], previous_names: set[str]) -> float:
    """Jaccard similarity between two name sets. Higher = more overlap = more saturated."""
    if not current_names or not previous_names:
        return 0.0
    intersection = len(current_names & previous_names)
    union = len(current_names | previous_names)
    return intersection / union if union > 0 else 0.0


def _check_saturation(
    rounds_history: list[dict[str, Any]],
    threshold: float,
) -> tuple[bool, str]:
    """Check if a source+hypothesis combo is saturated.

    Returns (is_saturated, reason).
    """
    if len(rounds_history) < 2:
        return False, ""

    # Check 1: Low diversity (high Jaccard) for last 2 rounds
    last = rounds_history[-1]
    prev = rounds_history[-2]
    current_names = set(last.get("candidate_names", []))
    previous_names = set(prev.get("candidate_names", []))
    diversity = _compute_diversity(current_names, previous_names)

    if diversity >= threshold and len(rounds_history) >= 2:
        return True, f"diversity={diversity:.2f} >= threshold={threshold}"

    # Check 2: Consecutive very low results
    low_result_count = sum(
        1 for r in rounds_history[-3:]
        if r.get("results_count", 0) < 3
    )
    if low_result_count >= 2 and len(rounds_history) >= 3:
        return True, "consecutive_low_results<3"

    # Check 3: Zero verified for 3+ consecutive rounds
    zero_verified = sum(
        1 for r in rounds_history[-3:]
        if r.get("verified_count", 0) == 0
    )
    if zero_verified >= 3 and len(rounds_history) >= 3:
        return True, "consecutive_zero_verified"

    return False, ""


# ---------------------------------------------------------------------------
# Query evolution
# ---------------------------------------------------------------------------

def _evolve_query(
    base_keywords: list[str],
    round_number: int,
    source_name: str,
    hypothesis: dict[str, Any],
) -> list[str]:
    """Generate the next query by varying keywords.

    Uses pre-defined query families from the hypothesis when available.
    Falls back to simple keyword rotation.
    """
    query_families = hypothesis.get("query_families", [])
    if query_families and round_number <= len(query_families):
        family = query_families[round_number - 1]
        source_query = family.get(source_name)
        if source_query:
            if isinstance(source_query, str):
                return [source_query]
            return source_query if isinstance(source_query, list) else [str(source_query)]

    # Fallback: rotate through initial_queries angles
    initial_queries = hypothesis.get("initial_queries", {})
    source_queries = initial_queries.get(source_name, base_keywords)
    if isinstance(source_queries, str):
        source_queries = [source_queries]
    elif not isinstance(source_queries, list):
        source_queries = base_keywords

    if len(source_queries) <= 1:
        # Try broader/narrower variations
        if round_number == 2:
            return [f"{kw} 简历 主页" for kw in source_queries]
        elif round_number == 3:
            return [f"{kw} GitHub ORCID" for kw in source_queries]
        return source_queries

    idx = (round_number - 1) % len(source_queries)
    return [source_queries[idx]] if isinstance(source_queries[idx], str) else source_queries[idx]


# ---------------------------------------------------------------------------
# Budget allocation
# ---------------------------------------------------------------------------

def _allocate_budget(
    source_stats: dict[str, dict[str, Any]],
    remaining_budget: int,
    config: dict[str, Any],
) -> dict[str, int]:
    """Allocate remaining budget across sources based on signal quality.

    Higher signal quality = more budget. Saturated sources get 0.
    China-first sources get a base weight multiplier.
    """
    weights = {}
    for source_name, stats in source_stats.items():
        if stats.get("is_saturated", False):
            weights[source_name] = 0.0
            continue

        sq = stats.get("avg_signal_quality", 0.3)
        if sq is None:
            sq = 0.3

        # Diversity bonus: more diverse = higher weight
        diversity_score = stats.get("diversity_score", 1.0)
        if diversity_score is None:
            diversity_score = 1.0

        # China-first priority weight
        priority = _SOURCE_PRIORITY_WEIGHTS.get(source_name, 1.0)

        # Weight formula: signal quality squared × diversity × priority
        weight = (max(sq, 0.01) ** 2) * max(diversity_score, 0.1) * priority
        weights[source_name] = weight

    total_weight = sum(weights.values())
    allocation = {}
    for source_name, w in weights.items():
        if total_weight <= 0:
            allocation[source_name] = 0
            continue

        share = int((w / total_weight) * remaining_budget)
        cap = config["source_call_budget"].get(source_name, 30)
        used = source_stats[source_name].get("calls_used", 0)
        allocation[source_name] = min(share, cap - used, max(0, cap - used))

    return allocation


# ---------------------------------------------------------------------------
# Core search loop for one source + hypothesis combo
# ---------------------------------------------------------------------------

async def _search_combo(
    run_id: UUID,
    hypothesis: dict[str, Any],
    source_name: str,
    config: dict[str, Any],
    global_state: dict[str, Any],
    combo_budget: int,
) -> dict[str, Any]:
    """Execute deep search for one (hypothesis, source) combination.

    Returns summary stats for this combo.
    """
    hypothesis_id = hypothesis.get("hypothesis_id", "unknown")
    base_keywords = hypothesis.get("keywords", [])
    max_rounds = combo_budget
    saturation_threshold = config["saturation_threshold"]
    min_signal_quality = config["min_signal_quality"]
    low_signal_cutoff = config["low_signal_cutoff"]

    rounds_history: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    total_persisted = 0
    start_time = time.monotonic()

    for round_num in range(1, max_rounds + 1):
        # Hard limits check
        if global_state["total_calls"] >= config["max_total_calls"]:
            logger.info("Global call limit reached. Stopping %s/%s", source_name, hypothesis_id)
            break

        elapsed_min = (time.monotonic() - global_state["start_time"]) / 60
        if elapsed_min >= config["max_duration_minutes"]:
            logger.info("Global time limit reached. Stopping %s/%s", source_name, hypothesis_id)
            break

        # Evolve query
        keywords = _evolve_query(base_keywords, round_num, source_name, hypothesis)
        limit = 25  # slightly higher than default 20 for deep search

        # Execute search
        t0 = time.monotonic()
        try:
            result = await search_source(
                source_name=source_name,
                keywords=keywords,
                run_id=run_id,
                limit=limit,
            )
        except Exception as e:
            logger.warning("Search error %s/%s round %d: %s", source_name, hypothesis_id, round_num, e)
            result = {"status": "error", "error": {"message": str(e)}, "candidates": []}

        search_latency = time.monotonic() - t0
        global_state["total_calls"] += 1

        raw_candidates = result.get("candidates", []) if result.get("status") == "success" else []
        candidate_names = [c.get("name", "") for c in raw_candidates]

        # Classify results
        verified_count = sum(
            1 for c in raw_candidates
            if c.get("confidence") == "high" or c.get("result_type") in ("profile_page", "paper")
        )

        # Compute signal quality
        results_count = len(raw_candidates)
        signal_quality = verified_count / max(results_count, 1)

        # Compute diversity vs previous round
        diversity = 0.0
        if rounds_history:
            prev_names = set(rounds_history[-1].get("candidate_names", []))
            curr_names = set(candidate_names)
            diversity = _compute_diversity(curr_names, prev_names)

        # Record round
        round_record = {
            "results_count": results_count,
            "verified_count": verified_count,
            "persisted_count": 0,
            "signal_quality": signal_quality,
            "candidate_names": candidate_names,
            "diversity": diversity,
        }
        rounds_history.append(round_record)

        # Persist to DB
        try:
            await search_state.record_search_round(
                run_id=run_id,
                hypothesis_id=hypothesis_id,
                source_name=source_name,
                round_number=round_num,
                query_used={"keywords": keywords, "limit": limit},
                results_count=results_count,
                verified_count=verified_count,
                persisted_count=0,
                signal_quality=signal_quality,
                result_diversity=diversity,
            )
        except Exception as e:
            logger.warning("Failed to record search round: %s", e)

        # Collect candidates for batch upsert
        for c in raw_candidates:
            c["_source"] = source_name
            c["_hypothesis_id"] = hypothesis_id
        all_candidates.extend(raw_candidates)

        # Check saturation
        is_saturated, saturation_reason = _check_saturation(rounds_history, saturation_threshold)
        if is_saturated:
            logger.info("Saturation detected for %s/%s: %s", source_name, hypothesis_id, saturation_reason)
            try:
                await search_state.mark_source_saturated(
                    run_id, source_name, hypothesis_id, round_num, saturation_reason,
                )
            except Exception:
                pass
            break

        # Check low signal quality - reduce budget implicitly by stopping early
        recent_sq = [r["signal_quality"] for r in rounds_history[-3:]]
        if len(recent_sq) >= 3 and all(sq < low_signal_cutoff for sq in recent_sq):
            logger.info("Low signal quality for %s/%s. Stopping.", source_name, hypothesis_id)
            break

        # Batch upsert periodically to avoid memory bloat
        if len(all_candidates) >= config.get("batch_upsert_interval", 10):
            persisted = await _batch_upsert(run_id, all_candidates, source_name)
            total_persisted += persisted
            all_candidates = []

        # Small delay to avoid hammering APIs
        await asyncio.sleep(0.5)

    # Final upsert for remaining candidates
    if all_candidates:
        persisted = await _batch_upsert(run_id, all_candidates, source_name)
        total_persisted += persisted

    # Update persisted counts in searchroundstate
    for i, r in enumerate(rounds_history):
        r["persisted_count"] = total_persisted // max(len(rounds_history), 1)

    return {
        "source_name": source_name,
        "hypothesis_id": hypothesis_id,
        "rounds_executed": len(rounds_history),
        "total_results": sum(r["results_count"] for r in rounds_history),
        "total_verified": sum(r["verified_count"] for r in rounds_history),
        "total_persisted": total_persisted,
        "is_saturated": any(r.get("is_saturated", False) for r in rounds_history),
        "avg_signal_quality": (
            sum(r["signal_quality"] for r in rounds_history) / len(rounds_history)
            if rounds_history else 0.0
        ),
    }


async def _batch_upsert(run_id: UUID, candidates_list: list[dict[str, Any]], source_name: str) -> int:
    """Batch upsert candidates and return count persisted."""
    if not candidates_list:
        return 0

    # Deduplicate by name+source within the batch
    seen = set()
    unique = []
    for c in candidates_list:
        key = (c.get("name", ""), c.get("profile_url", ""))
        if key not in seen and key[0]:
            seen.add(key)
            unique.append(c)

    try:
        result = await candidates_tool.upsert_candidates_batch(
            run_id=run_id,
            candidates_list=unique,
            source_name=source_name,
            agent_id="deep-search-orchestrator",
        )
        return len(result.get("accepted", []))
    except Exception as e:
        logger.warning("Batch upsert failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

def _detect_gaps(
    combo_results: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect which hypotheses are under-represented in the results."""
    if not combo_results:
        return []

    # Count results per hypothesis
    hypo_counts: dict[str, int] = {}
    for r in combo_results:
        hid = r.get("hypothesis_id", "unknown")
        hypo_counts[hid] = hypo_counts.get(hid, 0) + r.get("total_results", 0)

    total = sum(hypo_counts.values())
    if total == 0:
        return []

    gaps = []
    for h in hypotheses:
        hid = h.get("hypothesis_id", "unknown")
        count = hypo_counts.get(hid, 0)
        coverage = count / total
        if coverage < 0.2:  # less than 20% of total results
            gaps.append({
                "hypothesis_id": hid,
                "persona_name": h.get("persona_name", "unknown"),
                "coverage": coverage,
                "results_found": count,
                "suggested_action": "generate_gap_fill_queries",
            })

    return gaps


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def deep_search(
    run_id: UUID,
    hypotheses: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute deep iterative search across all hypotheses and sources.

    Phase 1: Signal Probe — 2-3 rounds per combo to measure baseline quality
    Phase 2: Budget Allocation — assign remaining budget based on signal quality
    Phase 3: Deep Iteration — continue high-signal combos until saturated or budget exhausted
    Phase 4: Gap Detection — identify under-represented personas
    Phase 5: Gap Fill (optional) — run additional searches for gaps
    Phase 6: Terminate — return summary
    """
    cfg = {**_DEFAULT_CONFIG, **(config or {})}
    start_time = time.monotonic()

    global_state = {
        "start_time": start_time,
        "total_calls": 0,
        "terminated": False,
        "termination_reason": None,
    }

    # Build source list from hypotheses
    all_sources: set[str] = set()
    for h in hypotheses:
        for s in h.get("source_priority", []):
            all_sources.add(s)
        for s in h.get("initial_queries", {}).keys():
            all_sources.add(s)
    # Fallback: use all available sources if none specified
    if not all_sources:
        all_sources = set(cfg["source_call_budget"].keys())

    logger.info("Deep search started: run=%s hypotheses=%d sources=%d",
                run_id, len(hypotheses), len(all_sources))

    # ================================================================
    # Phase 1: Signal Probe
    # ================================================================
    probe_results: list[dict[str, Any]] = []
    probe_tasks = []

    for h in hypotheses:
        hid = h.get("hypothesis_id", "unknown")
        for source_name in all_sources:
            # Check if source has queries for this hypothesis
            initial_queries = h.get("initial_queries", {})
            if source_name not in initial_queries and source_name not in h.get("source_priority", []):
                continue

            budget = cfg["probe_rounds_per_combo"]
            probe_tasks.append(_search_combo(run_id, h, source_name, cfg, global_state, budget))

    # Execute probes with concurrency limit
    semaphore = asyncio.Semaphore(cfg["max_concurrent_sources"])

    async def _probed(task):
        async with semaphore:
            return await task

    probe_results = await asyncio.gather(*[_probed(t) for t in probe_tasks], return_exceptions=True)
    probe_results = [r for r in probe_results if isinstance(r, dict)]

    logger.info("Probe phase complete: %d combos, %d total calls",
                len(probe_results), global_state["total_calls"])

    # ================================================================
    # Phase 2: Budget Allocation
    # ================================================================
    source_stats: dict[str, dict[str, Any]] = {}
    for r in probe_results:
        sn = r["source_name"]
        if sn not in source_stats:
            source_stats[sn] = {
                "calls_used": 0,
                "total_results": 0,
                "total_persisted": 0,
                "avg_signal_quality": None,
                "is_saturated": False,
                "diversity_score": 1.0,
            }
        source_stats[sn]["calls_used"] += r["rounds_executed"]
        source_stats[sn]["total_results"] += r["total_results"]
        source_stats[sn]["total_persisted"] += r["total_persisted"]
        # Update avg signal quality
        if source_stats[sn]["avg_signal_quality"] is None:
            source_stats[sn]["avg_signal_quality"] = r["avg_signal_quality"]
        else:
            source_stats[sn]["avg_signal_quality"] = (
                (source_stats[sn]["avg_signal_quality"] + r["avg_signal_quality"]) / 2
            )

    remaining_budget = cfg["max_total_calls"] - global_state["total_calls"]
    budget_allocation = _allocate_budget(source_stats, remaining_budget, cfg)

    logger.info("Budget allocation: %s", budget_allocation)

    # ================================================================
    # Phase 3: Deep Iteration
    # ================================================================
    deep_results: list[dict[str, Any]] = []

    deep_tasks = []
    for h in hypotheses:
        hid = h.get("hypothesis_id", "unknown")
        for source_name in all_sources:
            if source_name not in budget_allocation or budget_allocation[source_name] <= 0:
                continue
            if source_stats.get(source_name, {}).get("is_saturated", False):
                continue

            # Per-hypothesis share of source budget
            budget = max(1, budget_allocation[source_name] // max(len(hypotheses), 1))
            deep_tasks.append(_search_combo(run_id, h, source_name, cfg, global_state, budget))

    if deep_tasks:
        deep_raw = await asyncio.gather(*[_probed(t) for t in deep_tasks], return_exceptions=True)
        deep_results = [r for r in deep_raw if isinstance(r, dict)]

    all_results = probe_results + deep_results

    # ================================================================
    # Phase 4: Gap Detection
    # ================================================================
    gaps = _detect_gaps(all_results, hypotheses)

    # ================================================================
    # Phase 5: Gap Fill (if enabled and budget remains)
    # ================================================================
    if cfg["gap_fill_enabled"] and gaps and global_state["total_calls"] < cfg["max_total_calls"]:
        logger.info("Gap fill: %d personas under-represented", len(gaps))
        gap_tasks = []
        for gap in gaps[:3]:  # fill top 3 gaps max
            # Find the hypothesis for this gap
            target_h = None
            for h in hypotheses:
                if h.get("hypothesis_id") == gap["hypothesis_id"]:
                    target_h = h
                    break
            if not target_h:
                continue

            # Use the best-performing source for this hypothesis
            best_source = None
            best_sq = -1.0
            for r in all_results:
                if r["hypothesis_id"] == gap["hypothesis_id"] and r["avg_signal_quality"] > best_sq:
                    best_sq = r["avg_signal_quality"]
                    best_source = r["source_name"]

            if best_source:
                gap_tasks.append(_search_combo(run_id, target_h, best_source, cfg, global_state, 3))

        if gap_tasks:
            gap_raw = await asyncio.gather(*[_probed(t) for t in gap_tasks], return_exceptions=True)
            all_results.extend([r for r in gap_raw if isinstance(r, dict)])

    # ================================================================
    # Phase 5.5: Site Enrichment (optional)
    # ================================================================
    site_crawl_summary = await _enrich_with_site_crawl(run_id, cfg, global_state)

    # ================================================================
    # Phase 6: Terminate & Summary
    # ================================================================
    total_time = time.monotonic() - start_time
    total_results = sum(r["total_results"] for r in all_results)
    total_persisted = sum(r["total_persisted"] for r in all_results)
    total_calls = global_state["total_calls"]

    # Determine termination reason
    if total_calls >= cfg["max_total_calls"]:
        termination_reason = "max_total_calls_reached"
    elif total_time >= cfg["max_duration_minutes"] * 60:
        termination_reason = "max_duration_reached"
    elif all(r.get("is_saturated", False) for r in all_results if r["total_results"] > 0):
        termination_reason = "all_sources_saturated"
    else:
        termination_reason = "normal_completion"

    # Per-source summary
    source_summary: dict[str, dict[str, Any]] = {}
    for r in all_results:
        sn = r["source_name"]
        if sn not in source_summary:
            source_summary[sn] = {
                "rounds": 0, "results": 0, "persisted": 0,
                "is_saturated": False, "avg_signal_quality": 0.0,
            }
        source_summary[sn]["rounds"] += r["rounds_executed"]
        source_summary[sn]["results"] += r["total_results"]
        source_summary[sn]["persisted"] += r["total_persisted"]
        source_summary[sn]["is_saturated"] = source_summary[sn]["is_saturated"] or r.get("is_saturated", False)
        source_summary[sn]["avg_signal_quality"] = max(
            source_summary[sn]["avg_signal_quality"],
            r["avg_signal_quality"],
        )

    return {
        "run_id": str(run_id),
        "status": "complete",
        "termination_reason": termination_reason,
        "duration_seconds": round(total_time, 1),
        "total_search_calls": total_calls,
        "total_results_found": total_results,
        "total_persisted": total_persisted,
        "hypotheses_tested": len(hypotheses),
        "sources_used": len(source_summary),
        "gaps_detected": len(gaps),
        "site_crawl": site_crawl_summary,
        "per_source": [
            {
                "source_name": sn,
                **data,
            }
            for sn, data in sorted(
                source_summary.items(),
                key=lambda x: x[1]["results"],
                reverse=True,
            )
        ],
        "gaps": gaps,
    }


async def _enrich_with_site_crawl(
    run_id: UUID,
    config: dict[str, Any],
    global_state: dict[str, Any],
) -> dict[str, Any]:
    """Optional Phase 5.5: Crawl personal websites of top candidates.

    Queries the database for candidates in this run with profile URLs,
    selects the top-N by quality score, and performs BFS site crawling
    to discover hidden projects, publications, and background info.

    Returns a summary of crawl results.
    """
    if not config.get("site_crawl_enabled", False):
        return {"enabled": False, "pages_crawled": 0}

    max_candidates = config.get("site_crawl_max_candidates", 5)
    min_quality = config.get("site_crawl_min_quality_score", 0)

    try:
        rows = await fetch_with_retry(
            """
            SELECT cr.person_id, cr.raw_data, cr.quality_score, p.canonical_name
            FROM candidaterecord cr
            JOIN person p ON cr.person_id = p.person_id
            WHERE cr.run_id = $1
              AND cr.raw_data IS NOT NULL
              AND cr.quality_score >= $2
            ORDER BY cr.quality_score DESC, cr.created_at DESC
            LIMIT $3
            """,
            run_id, min_quality, max_candidates,
        )
    except Exception as e:
        logger.warning("Failed to query candidates for site crawl: %s", e)
        return {"enabled": True, "error": str(e), "pages_crawled": 0}

    # Extract profile URLs that look like personal homepages
    homepage_patterns = [
        ".edu", "github.io", "scholar.google", "researchgate",
        "linkedin.com/in", "dblp.org/pid", "orcid.org",
        ".ac.cn", ".edu.cn",
    ]

    crawl_targets: list[tuple[UUID, str, str]] = []  # (person_id, name, url)
    for row in rows:
        raw = row.get("raw_data", {}) or {}
        original = raw.get("original", {})
        url = original.get("profile_url", "")
        if not url:
            continue
        url_lower = url.lower()
        if any(pat in url_lower for pat in homepage_patterns):
            crawl_targets.append((row["person_id"], row["canonical_name"], url))

    if not crawl_targets:
        return {"enabled": True, "pages_crawled": 0, "reason": "no_homepage_urls_found"}

    # Check time budget
    elapsed_min = (time.monotonic() - global_state["start_time"]) / 60
    remaining_min = config["max_duration_minutes"] - elapsed_min
    if remaining_min < 2:
        return {"enabled": True, "pages_crawled": 0, "reason": "insufficient_time_budget"}

    logger.info("Site crawl enrichment: %d candidates, %d targets", len(rows), len(crawl_targets))

    results = []
    for person_id, name, url in crawl_targets:
        try:
            crawl_result = await crawl_site(
                start_url=url,
                max_pages=config.get("site_crawl_max_pages", 10),
                max_depth=config.get("site_crawl_max_depth", 2),
                same_domain_only=True,
                run_id=run_id,
                enable_dynamic=True,
            )
            if crawl_result.get("status") == "success":
                results.append({
                    "person_id": str(person_id),
                    "name": name,
                    "url": url,
                    "pages_crawled": crawl_result.get("pages_crawled", 0),
                    "combined_text_length": len(crawl_result.get("combined_text", "")),
                })
        except Exception as e:
            logger.warning("Site crawl failed for %s (%s): %s", name, url, e)
            results.append({
                "person_id": str(person_id),
                "name": name,
                "url": url,
                "error": str(e),
            })

        # Small delay between candidates
        await asyncio.sleep(0.5)

    total_pages = sum(r.get("pages_crawled", 0) for r in results if "pages_crawled" in r)
    return {
        "enabled": True,
        "candidates_crawled": len(crawl_targets),
        "pages_crawled": total_pages,
        "results": results,
    }


async def get_search_progress(run_id: UUID) -> dict[str, Any]:
    """Get current deep search progress for a run."""
    return await search_state.get_run_search_progress(run_id)
