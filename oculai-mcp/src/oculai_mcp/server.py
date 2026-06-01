"""Oculai MCP Server — Multi-Agent Talent Sourcing Tools.

Exposes deterministic domain tools for Claude Code main Agent.
No LLM calls. No autonomous decisions. Just execution.
"""

from typing import Any

from fastmcp import FastMCP

from oculai_mcp.config import get_settings
from oculai_mcp.db import runs, tasks
from oculai_mcp.db import iterations as iteration_db
from oculai_mcp.db import broadcasts as broadcast_db
from oculai_mcp.tools import candidates, evidence, assessment, sources, report
from oculai_mcp.tools import web_search, outreach, browser, deep_search as deep_search_tool
from oculai_mcp.tools import review_orchestrator as review

mcp = FastMCP(
    "Oculai Talent Sourcing",
)


# ============================================================
# M1: First 3 tools — Run lifecycle + Plan checkpoint
# ============================================================

@mcp.tool
async def oculai_create_run(
    job_title: str,
    jd_text: str,
    required_skills: list[str] | None = None,
    target_domains: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new talent sourcing run.

    This is the first tool called by the main Agent when starting a new
    sourcing job. It creates a SourcingRun row in PostgreSQL and returns
    the run_id that all subsequent tools reference.

    Args:
        job_title: The job title (e.g. "Senior NLP Researcher")
        jd_text: Full job description text
        required_skills: List of required skills extracted from JD
        target_domains: Academic/tech domains (e.g. ["cs.AI", "cs.CL"])
        config: Optional sourcing configuration (sources, concurrency, etc.)
    """
    target_profile = {
        "title": job_title,
        "jd_text": jd_text,
        "required_skills": required_skills or [],
    }
    run_id = await runs.create_run(
        title=job_title,
        target_profile=target_profile,
        config=config or {},
        target_keywords=required_skills or [],
        target_domains=target_domains or [],
    )
    return {"run_id": str(run_id), "status": "draft", "title": job_title}


@mcp.tool
async def oculai_get_run_state(run_id: str) -> dict[str, Any]:
    """Get the current state of a sourcing run.

    Returns the run metadata, active plan, task statistics grouped by
    type and status, and candidate count. The main Agent calls this to
    understand what has been done and what remains.

    Args:
        run_id: The run UUID returned by oculai_create_run
    """
    from uuid import UUID
    return await runs.get_run_state_summary(UUID(run_id))


@mcp.tool
async def oculai_checkpoint_plan(
    run_id: str,
    plan_json: dict[str, Any],
    strategy_summary: str = "",
) -> dict[str, Any]:
    """Write a Plan + Task DAG to the database.

    The main Agent calls this after generating the search strategy and
    task decomposition. This persists the plan as a Plan row and all
    tasks as Task rows with their dependency edges.

    plan_json structure:
    {
        "tasks": [
            {
                "step_key": "strategy",
                "task_type": "search_strategy",
                "task_name": "Generate search strategy",
                "priority": 10,
                "input_data": {...}
            },
            {
                "step_key": "search_arxiv",
                "task_type": "search",
                "task_name": "Search arXiv",
                "priority": 9,
                "input_data": {"source": "arxiv"},
                "depends_on": ["strategy"]
            },
            ...
        ]
    }

    Args:
        run_id: The run UUID
        plan_json: Full plan with tasks and dependencies
        strategy_summary: Human-readable summary of the strategy
    """
    from uuid import UUID

    run_uuid = UUID(run_id)

    # Create Plan
    plan_id = await tasks.create_plan(
        run_id=run_uuid,
        planner_state_json=plan_json,
        strategy_summary=strategy_summary,
    )

    # Update run's active plan
    await tasks.update_run_active_plan(run_uuid, plan_id)

    # Mark run as running
    await runs.update_run_status(run_uuid, "running")

    # Create Tasks from plan_json
    task_list = plan_json.get("tasks", [])
    created_tasks: dict[str, UUID] = {}  # step_key → task_id

    for t in task_list:
        task_id = await tasks.create_task(
            plan_id=plan_id,
            run_id=run_uuid,
            task_type=t["task_type"],
            task_name=t["task_name"],
            input_data=t.get("input_data", {}),
            step_key=t.get("step_key"),
            priority=t.get("priority", 5),
        )
        if t.get("step_key"):
            created_tasks[t["step_key"]] = task_id

    # Create TaskDependency edges
    for t in task_list:
        depends_on = t.get("depends_on", [])
        if depends_on:
            task_id = created_tasks.get(t.get("step_key"))
            if task_id:
                for dep_step_key in depends_on:
                    dep_task_id = created_tasks.get(dep_step_key)
                    if dep_task_id:
                        await tasks.create_task_dependency(
                            plan_id=plan_id,
                            task_id=task_id,
                            depends_on_task_id=dep_task_id,
                        )

    return {
        "run_id": run_id,
        "plan_id": str(plan_id),
        "status": "active",
        "task_count": len(task_list),
        "strategy_summary": strategy_summary,
    }


# ============================================================
# M1 bonus: Task claim tool (needed for subagent dispatch)
# ============================================================

@mcp.tool
async def oculai_claim_tasks(
    run_id: str,
    task_types: list[str],
    agent_id: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Claim pending tasks for a subagent to execute.

    Uses FOR UPDATE SKIP LOCKED for safe concurrent claiming across
    multiple subagents. Only claims tasks whose dependencies are all done.

    Args:
        run_id: The run UUID
        task_types: Task types to claim (e.g. ["search", "evaluate"])
        agent_id: Identifier for the claiming agent/subagent
        limit: Max number of tasks to claim
    """
    from uuid import UUID

    claimed = await tasks.claim_task_batch(
        run_id=UUID(run_id),
        task_types=task_types,
        batch_size=limit,
        agent_id=agent_id,
    )
    return {"claimed": len(claimed), "tasks": claimed}


@mcp.tool
async def oculai_complete_task(
    task_id: str,
    output_data: dict[str, Any],
    agent_id: str,
) -> dict[str, Any]:
    """Mark a task as completed with output data.

    After completion, downstream tasks are auto-resolved with input
    references if their dependencies are all satisfied.

    Args:
        task_id: The task UUID
        output_data: Task output (candidates, scores, etc.)
        agent_id: Identifier for the completing agent
    """
    from uuid import UUID

    await tasks.complete_task(UUID(task_id), agent_id, output_data)
    return {"task_id": task_id, "status": "done"}


@mcp.tool
async def oculai_fail_task(
    task_id: str,
    error_message: str,
    agent_id: str = "system",
) -> dict[str, Any]:
    """Mark a task as failed. Auto-retries if retry_count < max_retries.

    Args:
        task_id: The task UUID
        error_message: Description of the failure
        agent_id: Identifier for the failing agent
    """
    from uuid import UUID

    await tasks.fail_task(UUID(task_id), error_message, agent_id)
    return {"task_id": task_id, "status": "failed or re-pending"}


# ============================================================
# M1 bonus: Iteration recording and retrieval (ReAct audit)
# ============================================================

@mcp.tool
async def oculai_record_iteration(
    task_id: str,
    iteration_number: int,
    iteration_type: str,
    reasoning_text: str | None = None,
    action_taken: str | None = None,
    action_params: dict[str, Any] | None = None,
    observation_text: str | None = None,
    observation_data: dict[str, Any] | None = None,
    decision: str | None = None,
    decision_rationale: str | None = None,
) -> dict[str, Any]:
    """Persist one step of an agent's reasoning loop to the database.

    Subagents call this after EVERY ReAct step (THINK, SEARCH, OBSERVE,
    CLASSIFY, DETAIL, ADJUST, STOP, etc.) to create an auditable trace.
    The main agent can later retrieve these iterations via
    oculai_get_task_iterations to inspect reasoning and detect issues.

    Args:
        task_id: The Task UUID this iteration belongs to
        iteration_number: Auto-incrementing step number within the task
        iteration_type: think | search | observe | classify | detail | adjust | stop | gather | assess | reprioritize | initialize
        reasoning_text: Pre-action reasoning (for THINK steps)
        action_taken: Tool/action name (for SEARCH, DETAIL steps)
        action_params: JSON parameters passed to the action
        observation_text: Post-action analysis (for OBSERVE steps)
        observation_data: Structured observation metadata
        decision: High-level decision (NARROW, PIVOT, DEEPEN, STOP, etc.)
        decision_rationale: Why this decision was made
    """
    from uuid import UUID

    iteration_id = await iteration_db.record_iteration(
        task_id=UUID(task_id),
        iteration_number=iteration_number,
        iteration_type=iteration_type,
        reasoning_text=reasoning_text,
        action_taken=action_taken,
        action_params=action_params or {},
        observation_text=observation_text,
        observation_data=observation_data or {},
        decision=decision,
        decision_rationale=decision_rationale,
    )
    return {
        "iteration_id": str(iteration_id),
        "task_id": task_id,
        "iteration_number": iteration_number,
        "iteration_type": iteration_type,
    }


@mcp.tool
async def oculai_get_task_iterations(
    task_id: str,
) -> dict[str, Any]:
    """Get all recorded iterations for a task, ordered by step number.

    The main agent uses this to inspect a subagent's reasoning chain,
    detect premature stops, excessive pivots, stuck loops, and
    confidence degradation.

    Args:
        task_id: The task UUID
    """
    from uuid import UUID

    iterations = await iteration_db.get_task_iterations(UUID(task_id))
    return {
        "task_id": task_id,
        "count": len(iterations),
        "iterations": iterations,
    }


@mcp.tool
async def oculai_broadcast_discovery(
    run_id: str,
    discovery_type: str,
    content: str,
    discovered_by_agent: str,
) -> dict[str, Any]:
    """Broadcast a discovery to all parallel agents in this run.

    Use this to share terminology discoveries, population insights,
    or source quality observations across concurrently running agents.

    Args:
        run_id: The SourcingRun UUID
        discovery_type: terminology | population_insight | source_quality
        content: The discovery text
        discovered_by_agent: Agent identifier (e.g., "source-researcher-juejin")
    """
    from uuid import UUID

    broadcast_id = await broadcast_db.broadcast_discovery(
        run_id=UUID(run_id),
        discovery_type=discovery_type,
        content=content,
        discovered_by=discovered_by_agent,
    )
    return {
        "broadcast_id": str(broadcast_id),
        "run_id": run_id,
        "discovery_type": discovery_type,
        "content": content,
    }


@mcp.tool
async def oculai_get_broadcasts(
    run_id: str,
    agent_id: str,
) -> dict[str, Any]:
    """Get all unconsumed broadcasts from other agents in this run.

    Automatically marks returned broadcasts as consumed by the requesting
    agent to prevent duplicate processing.

    Args:
        run_id: The SourcingRun UUID
        agent_id: The requesting agent's identifier
    """
    from uuid import UUID

    broadcasts = await broadcast_db.get_broadcasts(
        run_id=UUID(run_id),
        agent_id=agent_id,
    )
    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "count": len(broadcasts),
        "broadcasts": broadcasts,
    }


# ============================================================
# M2: Source tools
# ============================================================

@mcp.tool
async def oculai_list_source_capabilities() -> dict[str, Any]:
    """List all registered data sources and their capabilities.

    Returns each source's name, type, supported operations, and metadata,
    so the main Agent can make informed search strategy decisions.
    """
    return await sources.list_source_capabilities()


@mcp.tool
async def oculai_search_source(
    source_name: str,
    keywords: list[str],
    run_id: str | None = None,
    source_specific_query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search a specific data source and return structured candidates.

    Routes to the appropriate API connector (arXiv, Semantic Scholar, DBLP,
    OpenAlex, GitHub, etc.) and logs the call for provenance tracking.

    Args:
        source_name: Source identifier (e.g. "arxiv", "semantic_scholar")
        keywords: Search keyword list
        run_id: Optional run UUID for provenance tracking
        source_specific_query: Advanced query string (source-specific syntax)
        limit: Max results (default 20)
        offset: Pagination offset
    """
    from uuid import UUID
    run_uuid = UUID(run_id) if run_id else None
    return await sources.search_source(
        source_name=source_name,
        keywords=keywords,
        run_id=run_uuid,
        source_specific_query=source_specific_query,
        limit=limit,
        offset=offset,
    )


@mcp.tool
async def oculai_deep_search(
    run_id: str,
    hypotheses: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute deep iterative search across hypotheses and sources.

    Manages the full search loop: signal probe → budget allocation →
    deep iteration → gap detection → gap fill → termination.
    Stops when sources saturate, budget exhausts, or time limit reached.

    Args:
        run_id: The run UUID
        hypotheses: Search hypotheses from Search Strategist
        config: Optional overrides for depth limits, budgets, thresholds
    """
    from uuid import UUID
    return await deep_search_tool.deep_search(
        run_id=UUID(run_id),
        hypotheses=hypotheses,
        config=config,
    )


@mcp.tool
async def oculai_get_search_progress(run_id: str) -> dict[str, Any]:
    """Get current deep search progress for a run.

    Returns per-source stats: rounds executed, results found,
    signal quality, saturation status, and overall progress.
    """
    from uuid import UUID
    return await deep_search_tool.get_search_progress(UUID(run_id))


@mcp.tool
async def oculai_fetch_source_detail(
    source_name: str,
    external_id: str,
) -> dict[str, Any]:
    """Fetch detailed information for a single candidate from a source.

    Args:
        source_name: Source identifier (e.g. "semantic_scholar", "dblp")
        external_id: External identifier (author ID, ORCID, etc.)
    """
    return await sources.fetch_source_detail(source_name, external_id)


# ============================================================
# M2: Candidate tools
# ============================================================

@mcp.tool
async def oculai_upsert_candidate(
    run_id: str,
    person_data: dict[str, Any],
    source_name: str = "unknown",
    agent_id: str = "system",
) -> dict[str, Any]:
    """Idempotent candidate upsert with identity resolution.

    Checks for existing Person by external IDs (ORCID, Google Scholar, GitHub,
    LinkedIn, DBLP), then by name+institution, then by fuzzy name match.
    Creates new Person if no match found. Creates CandidateRecord linking
    Person to Run.

    Args:
        run_id: The run UUID
        person_data: Dict with name, institution, h_index, paper_count,
                     citation_count, orcid, google_scholar_id, github_id,
                     linkedin_url, dblp_key, research_areas
        source_name: Which source this candidate came from
        agent_id: Identifier for the agent doing the upsert
    """
    from uuid import UUID
    return await candidates.upsert_candidate(
        run_id=UUID(run_id),
        person_data=person_data,
        source_name=source_name,
        agent_id=agent_id,
    )


@mcp.tool
async def oculai_upsert_candidates_batch(
    run_id: str,
    candidates_list: list[dict[str, Any]],
    source_name: str = "unknown",
    agent_id: str = "system",
) -> dict[str, Any]:
    """Batch upsert multiple candidates in a single DB transaction.

    Much faster than individual oculai_upsert_candidate calls because it
    eliminates per-candidate connection-pool overhead.  Still runs full
    validation and identity resolution for each candidate.

    Args:
        run_id: The run UUID
        candidates_list: List of person_data dicts (same shape as oculai_upsert_candidate)
        source_name: Which source these candidates came from
        agent_id: Identifier for the agent doing the upsert
    """
    from uuid import UUID
    return await candidates.upsert_candidates_batch(
        run_id=UUID(run_id),
        candidates_list=candidates_list,
        source_name=source_name,
        agent_id=agent_id,
    )


@mcp.tool
async def oculai_link_identity(
    person_id: str,
    source_type: str,
    external_id: str,
    external_url: str | None = None,
    confidence: float = 1.0,
    verified_by_agent: str = "system",
) -> dict[str, Any]:
    """Link an external identity (ORCID, Google Scholar, etc.) to a Person.

    Args:
        person_id: Internal Person UUID
        source_type: Identity source type (orcid, google_scholar, github, linkedin, dblp)
        external_id: The external identifier string
        external_url: Optional profile URL
        confidence: Match confidence (0.0-1.0)
        verified_by_agent: Agent that verified this link
    """
    from uuid import UUID
    return await candidates.link_identity(
        person_id=UUID(person_id),
        source_type=source_type,
        external_id=external_id,
        external_url=external_url,
        confidence=confidence,
        verified_by_agent=verified_by_agent,
    )


@mcp.tool
async def oculai_list_candidates(
    run_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List candidates in a sourcing run with basic person info.

    Args:
        run_id: The run UUID
        status: Filter by candidate status (new, shortlisted, rejected, contacted, etc.)
        limit: Max results (default 100)
        offset: Pagination offset
    """
    from uuid import UUID
    return await candidates.list_candidates(
        run_id=UUID(run_id),
        status=status,
        limit=limit,
        offset=offset,
    )


@mcp.tool
async def oculai_get_candidate(person_id: str) -> dict[str, Any] | None:
    """Get full candidate profile: person, identities, publications, career, evidence, assessments.

    Args:
        person_id: Internal Person UUID
    """
    from uuid import UUID
    return await candidates.get_candidate(UUID(person_id))


# ============================================================
# M2: Evidence tools
# ============================================================

@mcp.tool
async def oculai_attach_evidence(
    person_id: str,
    evidence_type: str,
    title: str,
    source_name: str,
    source_url: str | None = None,
    description: str | None = None,
    content: dict[str, Any] | None = None,
    confidence: float = 1.0,
    run_id: str | None = None,
    captured_by_agent: str = "system",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach a piece of evidence to a candidate.

    Evidence is the foundation of all assessments. Every claim about a
    candidate must be backed by at least one evidence record.

    Args:
        person_id: Internal Person UUID
        evidence_type: Type (publication, code_repo, patent, award, career_history, etc.)
        title: Human-readable evidence title
        source_name: Where the evidence came from
        source_url: Source URL for traceability
        description: Short description
        content: Structured content (paper abstract, repo stats, etc.)
        confidence: Evidence confidence (0.0-1.0)
        run_id: Optional run UUID for scoping
        captured_by_agent: Which agent captured this evidence
        metadata: Arbitrary metadata
    """
    from uuid import UUID
    return await evidence.attach_evidence(
        person_id=UUID(person_id),
        evidence_type=evidence_type,
        title=title,
        source_name=source_name,
        source_url=source_url,
        description=description,
        content=content,
        confidence=confidence,
        run_id=UUID(run_id) if run_id else None,
        captured_by_agent=captured_by_agent,
        metadata=metadata,
    )


@mcp.tool
async def oculai_get_evidence(
    person_id: str,
    evidence_type: str | None = None,
    limit: int = 100,
    min_tier: int | None = None,
) -> dict[str, Any]:
    """Get all evidence for a candidate, optionally filtered by type.

    Returns evidence list plus summary counts by type.

    Args:
        person_id: Internal Person UUID
        evidence_type: Optional filter (publication, code_repo, award, etc.)
        limit: Max results (default 100)
        min_tier: Minimum evidence tier to include (1-4, optional)
    """
    from uuid import UUID
    return await evidence.get_evidence(
        person_id=UUID(person_id),
        evidence_type=evidence_type,
        limit=limit,
        min_tier=min_tier,
    )


# ============================================================
# M2: Assessment tools
# ============================================================

@mcp.tool
async def oculai_score_candidate(
    run_id: str,
    person_id: str,
    dimensions: dict[str, float],
    assessor_agent: str,
    evidence_ids: list[str] | None = None,
    confidence: float = 1.0,
    rationale: str = "",
    role_type: str = "default",
) -> dict[str, Any]:
    """Score a candidate across multiple dimensions simultaneously.

    Each dimension is scored 0.0-10.0. Uses upsert (ON CONFLICT DO UPDATE)
    so repeated scoring by the same agent for the same dimension is idempotent.
    Computes overall score with role-type weights, confidence weighting,
    and must-pass gate enforcement.

    Args:
        run_id: The run UUID
        person_id: Internal Person UUID
        dimensions: Dict of dimension_name → score (0.0-10.0)
        assessor_agent: Which agent performed the assessment
        evidence_ids: UUIDs of evidence records supporting the scores
        confidence: Overall assessment confidence (0.0-1.0)
        rationale: Free-text rationale
        role_type: Role type for weight calibration (research_scientist, engineer, tech_lead, ml_engineer, product_manager, data_scientist, default)
    """
    from uuid import UUID
    return await assessment.score_candidate(
        run_id=UUID(run_id),
        person_id=UUID(person_id),
        dimensions=dimensions,
        assessor_agent=assessor_agent,
        evidence_ids=evidence_ids,
        confidence=confidence,
        rationale=rationale,
        role_type=role_type,
    )


@mcp.tool
async def oculai_record_assessment(
    run_id: str,
    person_id: str,
    assessor_agent: str,
    dimension: str,
    score: float,
    confidence: float = 1.0,
    rationale: str = "",
    evidence_ids: list[str] | None = None,
    role_type: str = "default",
) -> dict[str, Any]:
    """Record a single dimension assessment for a candidate.

    Args:
        run_id: The run UUID
        person_id: Internal Person UUID
        assessor_agent: Which agent performed the assessment
        dimension: Dimension name (skill_match, research_output, industry_impact, etc.)
        score: Score 0.0-10.0
        confidence: Assessment confidence (0.0-1.0)
        rationale: Free-text rationale
        evidence_ids: UUIDs of evidence records supporting this score
        role_type: Role type for weight calibration
    """
    from uuid import UUID
    return await assessment.record_assessment(
        run_id=UUID(run_id),
        person_id=UUID(person_id),
        assessor_agent=assessor_agent,
        dimension=dimension,
        score=score,
        confidence=confidence,
        rationale=rationale,
        evidence_ids=evidence_ids,
        role_type=role_type,
    )


@mcp.tool
async def oculai_get_shortlist(
    run_id: str,
    min_score: float = 0,
    limit: int = 20,
) -> dict[str, Any]:
    """Get shortlisted candidates ranked by overall quality score.

    Only returns candidates with quality_score >= min_score (0 = no filter).

    Args:
        run_id: The run UUID
        min_score: Minimum quality score threshold (default 0 = all)
        limit: Max candidates to return
    """
    from uuid import UUID
    return await assessment.get_shortlist(
        run_id=UUID(run_id),
        min_score=min_score,
        limit=limit,
    )


@mcp.tool
async def oculai_get_score_history(
    run_id: str,
    person_id: str | None = None,
    dimension: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Get score change history for auditing.

    Tracks every time a dimension score was updated, including previous/new
    values, confidence, and the agent that made the change.

    Args:
        run_id: The run UUID
        person_id: Optional person UUID to filter by
        dimension: Optional dimension name to filter by
        limit: Max history entries to return
    """
    from uuid import UUID
    return await assessment.get_score_history(
        run_id=UUID(run_id),
        person_id=UUID(person_id) if person_id else None,
        dimension=dimension,
        limit=limit,
    )


@mcp.tool
async def oculai_get_evidence_by_tier(
    run_id: str,
    person_id: str,
    max_tier: int = 2,
) -> dict[str, Any]:
    """Get evidence up to a given quality tier.

    Tier 1 = primary (publication, repo contribution, CV)
    Tier 2 = secondary (profile, blog post)
    Tier 3 = indirect (comment, starred repo)
    Tier 4 = inferred

    Useful for validating that high scores have supporting Tier 1 evidence.

    Args:
        run_id: The run UUID
        person_id: Internal Person UUID
        max_tier: Maximum tier to include (default 2 = primary + secondary)
    """
    from uuid import UUID
    return await evidence.get_evidence_by_tier(
        run_id=UUID(run_id),
        person_id=UUID(person_id),
        max_tier=max_tier,
    )


# ============================================================
# M2: Report tools
# ============================================================

# ============================================================
# M3: Review Orchestrator tools
# ============================================================

@mcp.tool
async def oculai_create_review_session(
    run_id: str,
    role_type: str = "default",
    candidate_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Create a multi-pass review session for a run's candidate pool.

    The review pipeline runs: enrichment → initial_scoring → audit → adjustment → complete.
    The main Agent checks progress via oculai_get_review_progress and decides
    when to launch Profile Enricher / Fit Evaluator / Quality Auditor subagents.

    Args:
        run_id: The run UUID
        role_type: Role type for weight calibration (research_scientist, engineer, tech_lead, ml_engineer, product_manager, data_scientist, default)
        candidate_ids: Optional list of person UUIDs to review. If None, all candidates in the run are included.
    """
    from uuid import UUID
    parsed_ids = [UUID(c) for c in candidate_ids] if candidate_ids else None
    return await review.create_review_session(
        run_id=UUID(run_id),
        role_type=role_type,
        candidate_ids=parsed_ids,
    )


@mcp.tool
async def oculai_execute_review_pass(
    session_id: str,
    pass_type: str,
    completed_candidate_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Advance a review session to the next pass.

    Call this after subagents have finished processing candidates in the
    current pass. If all candidates are done, the session auto-advances
    to the next pass.

    Args:
        session_id: Review session UUID
        pass_type: Current pass (enrichment, initial_scoring, audit, adjustment, complete)
        completed_candidate_ids: Candidates that finished this pass
    """
    from uuid import UUID
    parsed_ids = [UUID(c) for c in completed_candidate_ids] if completed_candidate_ids else None
    return await review.execute_review_pass(
        session_id=UUID(session_id),
        pass_type=pass_type,
        completed_candidate_ids=parsed_ids,
    )


@mcp.tool
async def oculai_get_review_progress(session_id: str) -> dict[str, Any]:
    """Get current review session progress.

    Returns: current pass, pending/completed/failed counts, per-candidate status,
    audit findings, and pass timings.

    Args:
        session_id: Review session UUID
    """
    from uuid import UUID
    return await review.get_review_progress(UUID(session_id))


@mcp.tool
async def oculai_apply_audit_adjustments(
    session_id: str,
    adjustments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply auditor-recommended score adjustments with history tracking.

    Each adjustment dict must contain:
    - person_id: Person UUID
    - dimension: Dimension name
    - new_score: New score 0.0-10.0
    - reason: Why the adjustment was made
    - assessor_agent: "quality_auditor" or similar
    - confidence: Optional confidence (default 0.9)
    - evidence_ids: Optional supporting evidence UUIDs

    Args:
        session_id: Review session UUID
        adjustments: List of adjustment dicts
    """
    from uuid import UUID
    return await review.apply_audit_adjustments(
        session_id=UUID(session_id),
        adjustments=adjustments,
    )


@mcp.tool
async def oculai_finalize_review_session(session_id: str) -> dict[str, Any]:
    """Mark a review session as complete and compute final rankings.

    Returns aggregate statistics: total candidates, score distribution,
    dimension averages.

    Args:
        session_id: Review session UUID
    """
    from uuid import UUID
    return await review.finalize_review_session(UUID(session_id))


@mcp.tool
async def oculai_export_report(
    run_id: str,
    format: str = "html",
) -> dict[str, Any]:
    """Export a sourcing run report in HTML (default) or Markdown format.

    The HTML format is the primary deliverable: a polished, self-contained
    visual dashboard with score charts, candidate cards, and evidence
    summaries. The Markdown format is available for plain-text use cases.

    Args:
        run_id: The run UUID
        format: "html" (default) or "markdown"
    """
    from uuid import UUID
    return await report.export_report(
        run_id=UUID(run_id),
        format=format,
    )


# ============================================================
# M5-M6: Web Search, Outreach, Browser tools
# ============================================================

@mcp.tool
async def oculai_search_web(
    keywords: list[str],
    provider: str = "tavily",
    run_id: str | None = None,
    limit: int = 20,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Search the web for candidate-related content via Exa or Tavily.

    Useful for discovering candidates mentioned in news, company pages,
    tech blogs, and forums that academic databases miss.

    Args:
        keywords: Search keyword list
        provider: "tavily" (default) or "exa"
        run_id: Optional run UUID for provenance tracking
        limit: Max results (default 20)
        include_domains: Optional domain whitelist (e.g. ["linkedin.com"])
        exclude_domains: Optional domain blacklist
    """
    from uuid import UUID
    return await web_search.search_web(
        keywords=keywords,
        provider=provider,
        run_id=UUID(run_id) if run_id else None,
        limit=limit,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
    )


@mcp.tool
async def oculai_create_outreach_draft(
    run_id: str,
    person_id: str,
    strategy: str,
    template: str = "standard",
    channel: str = "email",
    draft_content: str = "",
    subject: str = "",
    agent_id: str = "system",
) -> dict[str, Any]:
    """Create an outreach draft for a candidate. DOES NOT SEND.

    All outreach messages must pass through the human approval gate
    (oculai_request_human_approval) before being sent.

    Args:
        run_id: The run UUID
        person_id: Target candidate Person UUID
        strategy: Outreach strategy (warm_intro, cold_email, linkedin_inmail, etc.)
        template: Template name to base the draft on
        channel: Contact channel (email, linkedin, wechat)
        draft_content: The draft message body
        subject: Email subject line
        agent_id: Agent creating the draft
    """
    from uuid import UUID
    return await outreach.create_outreach_draft(
        run_id=UUID(run_id),
        person_id=UUID(person_id),
        strategy=strategy,
        template=template,
        channel=channel,
        draft_content=draft_content,
        subject=subject,
        agent_id=agent_id,
    )


@mcp.tool
async def oculai_request_human_approval(
    run_id: str,
    action_type: str,
    action_context: dict[str, Any],
    draft_content: str = "",
    agent_id: str = "system",
) -> dict[str, Any]:
    """Request human approval for an action with external side effects.

    This is the MANDATORY GATE for: sending outreach messages, exporting
    data externally, or any write to external systems. Actions are
    BLOCKED until a human approves.

    Args:
        run_id: The run UUID
        action_type: Type (send_email, send_linkedin_message, etc.)
        action_context: Full context dict describing what, who, and why
        draft_content: The draft content to be approved
        agent_id: Agent requesting approval
    """
    from uuid import UUID
    return await outreach.request_human_approval(
        run_id=UUID(run_id),
        action_type=action_type,
        action_context=action_context,
        draft_content=draft_content,
        agent_id=agent_id,
    )


@mcp.tool
async def oculai_check_approval_status(approval_id: str) -> dict[str, Any]:
    """Check the status of a human approval request.

    Args:
        approval_id: The approval UUID
    """
    from uuid import UUID
    return await outreach.check_approval_status(UUID(approval_id))


@mcp.tool
async def oculai_list_pending_approvals(run_id: str | None = None) -> dict[str, Any]:
    """List all pending human approval requests.

    Args:
        run_id: Optional run UUID to filter by
    """
    from uuid import UUID
    return await outreach.list_pending_approvals(
        run_id=UUID(run_id) if run_id else None,
    )


@mcp.tool
async def oculai_get_outreach_history(
    person_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Get outreach history for a candidate.

    Args:
        person_id: Internal Person UUID
        limit: Max records to return
    """
    from uuid import UUID
    return await outreach.get_outreach_history(
        person_id=UUID(person_id),
        limit=limit,
    )


@mcp.tool
async def oculai_capture_page_evidence(
    url: str,
    person_id: str | None = None,
    run_id: str | None = None,
    mode: str = "text",
    captured_by_agent: str = "system",
    selector: str | None = None,
) -> dict[str, Any]:
    """Capture evidence from a web page (text content and/or screenshot).

    Useful for capturing personal homepages, lab pages, company profiles,
    and other web-based evidence.

    Args:
        url: Web page URL to capture
        person_id: Optional Person UUID to attach evidence to
        run_id: Optional Run UUID for provenance
        mode: "text" (lightweight, default), "screenshot" (needs Playwright), or "full"
        captured_by_agent: Agent capturing the evidence
        selector: Optional CSS selector to extract only part of the page
    """
    from uuid import UUID
    return await browser.capture_page_evidence(
        url=url,
        person_id=UUID(person_id) if person_id else None,
        run_id=UUID(run_id) if run_id else None,
        mode=mode,
        captured_by_agent=captured_by_agent,
        selector=selector,
    )


def main() -> None:
    """Entry point for `fastmcp run`."""
    settings = get_settings()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
