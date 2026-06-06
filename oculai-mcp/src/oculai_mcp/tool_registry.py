"""Oculai Tool Registry — Flat dictionary of all 41 MCP tools.

Extracts every @mcp.tool-decorated async function from server.py into a
TOOL_REGISTRY dict[str, Callable] where:
  - Keys are tool names like "oculai_create_run"
  - Values are async callables accepting a single params: dict[str, Any]
    and returning dict[str, Any]
  - Each handler converts string UUIDs to UUID objects and delegates to
    the same db/tools modules that server.py uses.

Usage:
    from oculai_mcp.tool_registry import get_tool, list_tools, TOOL_REGISTRY

    handler = get_tool("oculai_create_run")
    result = await handler({"job_title": "...", "jd_text": "..."})
"""

from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from oculai_mcp.db import runs, tasks
from oculai_mcp.db import iterations as iteration_db
from oculai_mcp.db import broadcasts as broadcast_db
from oculai_mcp.tools import candidates, evidence, assessment, sources, report
from oculai_mcp.tools import web_search, outreach, browser
from oculai_mcp.tools import deep_search as deep_search_tool
from oculai_mcp.tools import site_crawler
from oculai_mcp.tools import review_orchestrator as review


# ============================================================================
# Handler functions — one per tool, each accepting params: dict[str, Any]
# and returning dict[str, Any]
# ============================================================================


# --- Run Lifecycle & Plan Checkpoint (3 tools) -------------------------------

async def _oculai_create_run(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_create_run."""
    job_title: str = params["job_title"]
    jd_text: str = params["jd_text"]
    required_skills: list[str] | None = params.get("required_skills")
    target_domains: list[str] | None = params.get("target_domains")
    config: dict[str, Any] | None = params.get("config")

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


async def _oculai_get_run_state(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_run_state."""
    run_id: str = params["run_id"]
    return await runs.get_run_state_summary(UUID(run_id))


async def _oculai_checkpoint_plan(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_checkpoint_plan."""
    run_id: str = params["run_id"]
    plan_json: dict[str, Any] = params["plan_json"]
    strategy_summary: str = params.get("strategy_summary", "")

    run_uuid = UUID(run_id)

    plan_id = await tasks.create_plan(
        run_id=run_uuid,
        planner_state_json=plan_json,
        strategy_summary=strategy_summary,
    )
    await tasks.update_run_active_plan(run_uuid, plan_id)
    await runs.update_run_status(run_uuid, "running")

    task_list = plan_json.get("tasks", [])
    created_tasks: dict[str, UUID] = {}

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


# --- Task Claiming & Completion (3 tools) ------------------------------------

async def _oculai_claim_tasks(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_claim_tasks."""
    run_id: str = params["run_id"]
    task_types: list[str] = params["task_types"]
    agent_id: str = params["agent_id"]
    limit: int = params.get("limit", 5)

    result = await tasks.claim_task_batch(
        run_id=UUID(run_id),
        task_types=task_types,
        batch_size=limit,
        agent_id=agent_id,
    )
    return {"claimed": len(result), "tasks": result}


async def _oculai_complete_task(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_complete_task."""
    task_id: str = params["task_id"]
    output_data: dict[str, Any] = params["output_data"]
    agent_id: str = params["agent_id"]

    await tasks.complete_task(UUID(task_id), agent_id, output_data)
    return {"task_id": task_id, "status": "done"}


async def _oculai_fail_task(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_fail_task."""
    task_id: str = params["task_id"]
    error_message: str = params["error_message"]
    agent_id: str = params.get("agent_id", "system")

    await tasks.fail_task(UUID(task_id), error_message, agent_id)
    return {"task_id": task_id, "status": "failed or re-pending"}


# --- ReAct Iteration Recording & Retrieval (2 tools) ------------------------

async def _oculai_record_iteration(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_record_iteration."""
    task_id: str = params["task_id"]
    iteration_number: int = params["iteration_number"]
    iteration_type: str = params["iteration_type"]
    reasoning_text: str | None = params.get("reasoning_text")
    action_taken: str | None = params.get("action_taken")
    action_params: dict[str, Any] | None = params.get("action_params")
    observation_text: str | None = params.get("observation_text")
    observation_data: dict[str, Any] | None = params.get("observation_data")
    decision: str | None = params.get("decision")
    decision_rationale: str | None = params.get("decision_rationale")

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


async def _oculai_get_task_iterations(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_task_iterations."""
    task_id: str = params["task_id"]

    iterations = await iteration_db.get_task_iterations(UUID(task_id))
    return {
        "task_id": task_id,
        "count": len(iterations),
        "iterations": iterations,
    }


# --- Cross-Agent Broadcasts (2 tools) ----------------------------------------

async def _oculai_broadcast_discovery(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_broadcast_discovery."""
    run_id: str = params["run_id"]
    discovery_type: str = params["discovery_type"]
    content: str = params["content"]
    discovered_by_agent: str = params["discovered_by_agent"]

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


async def _oculai_get_broadcasts(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_broadcasts."""
    run_id: str = params["run_id"]
    agent_id: str = params["agent_id"]

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


# --- Source Tools (5 tools) --------------------------------------------------

async def _oculai_list_source_capabilities(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_list_source_capabilities."""
    return await sources.list_source_capabilities()


async def _oculai_search_source(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_search_source."""
    source_name: str = params["source_name"]
    keywords: list[str] = params["keywords"]
    run_id: str | None = params.get("run_id")
    source_specific_query: str | None = params.get("source_specific_query")
    limit: int = params.get("limit", 20)
    offset: int = params.get("offset", 0)

    run_uuid = UUID(run_id) if run_id else None
    return await sources.search_source(
        source_name=source_name,
        keywords=keywords,
        run_id=run_uuid,
        source_specific_query=source_specific_query,
        limit=limit,
        offset=offset,
    )


async def _oculai_deep_search(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_deep_search."""
    run_id: str = params["run_id"]
    hypotheses: list[dict[str, Any]] = params["hypotheses"]
    config: dict[str, Any] | None = params.get("config")

    return await deep_search_tool.deep_search(
        run_id=UUID(run_id),
        hypotheses=hypotheses,
        config=config,
    )


async def _oculai_get_search_progress(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_search_progress."""
    run_id: str = params["run_id"]
    return await deep_search_tool.get_search_progress(UUID(run_id))


async def _oculai_crawl_site(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_crawl_site."""
    start_url: str = params["start_url"]
    max_pages: int = params.get("max_pages", 20)
    max_depth: int = params.get("max_depth", 2)
    same_domain_only: bool = params.get("same_domain_only", True)
    run_id: str | None = params.get("run_id")

    return await site_crawler.crawl_site(
        start_url=start_url,
        max_pages=max_pages,
        max_depth=max_depth,
        same_domain_only=same_domain_only,
        run_id=UUID(run_id) if run_id else None,
    )


# --- Source Detail (1 tool) --------------------------------------------------

async def _oculai_fetch_source_detail(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_fetch_source_detail."""
    source_name: str = params["source_name"]
    external_id: str = params["external_id"]
    return await sources.fetch_source_detail(source_name, external_id)


# --- Candidate Tools (6 tools) -----------------------------------------------

async def _oculai_upsert_candidate(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_upsert_candidate."""
    run_id: str = params["run_id"]
    person_data: dict[str, Any] = params["person_data"]
    source_name: str = params.get("source_name", "unknown")
    agent_id: str = params.get("agent_id", "system")

    return await candidates.upsert_candidate(
        run_id=UUID(run_id),
        person_data=person_data,
        source_name=source_name,
        agent_id=agent_id,
    )


async def _oculai_upsert_candidates_batch(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_upsert_candidates_batch."""
    run_id: str = params["run_id"]
    candidates_list: list[dict[str, Any]] = params["candidates_list"]
    source_name: str = params.get("source_name", "unknown")
    agent_id: str = params.get("agent_id", "system")

    return await candidates.upsert_candidates_batch(
        run_id=UUID(run_id),
        candidates_list=candidates_list,
        source_name=source_name,
        agent_id=agent_id,
    )


async def _oculai_link_identity(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_link_identity."""
    person_id: str = params["person_id"]
    source_type: str = params["source_type"]
    external_id: str = params["external_id"]
    external_url: str | None = params.get("external_url")
    confidence: float = params.get("confidence", 1.0)
    verified_by_agent: str = params.get("verified_by_agent", "system")

    return await candidates.link_identity(
        person_id=UUID(person_id),
        source_type=source_type,
        external_id=external_id,
        external_url=external_url,
        confidence=confidence,
        verified_by_agent=verified_by_agent,
    )


async def _oculai_list_candidates(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_list_candidates."""
    run_id: str = params["run_id"]
    status: str | None = params.get("status")
    limit: int = params.get("limit", 100)
    offset: int = params.get("offset", 0)

    return await candidates.list_candidates(
        run_id=UUID(run_id),
        status=status,
        limit=limit,
        offset=offset,
    )


async def _oculai_get_candidate(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_candidate."""
    person_id: str = params["person_id"]
    return await candidates.get_candidate(UUID(person_id))


# --- Evidence Tools (3 tools) -------------------------------------------------

async def _oculai_attach_evidence(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_attach_evidence."""
    person_id: str = params["person_id"]
    evidence_type: str = params["evidence_type"]
    title: str = params["title"]
    source_name: str = params["source_name"]
    source_url: str | None = params.get("source_url")
    description: str | None = params.get("description")
    content: dict[str, Any] | None = params.get("content")
    confidence: float = params.get("confidence", 1.0)
    run_id: str | None = params.get("run_id")
    captured_by_agent: str = params.get("captured_by_agent", "system")
    metadata: dict[str, Any] | None = params.get("metadata")

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


async def _oculai_get_evidence(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_evidence."""
    person_id: str = params["person_id"]
    evidence_type: str | None = params.get("evidence_type")
    limit: int = params.get("limit", 100)
    min_tier: int | None = params.get("min_tier")

    return await evidence.get_evidence(
        person_id=UUID(person_id),
        evidence_type=evidence_type,
        limit=limit,
        min_tier=min_tier,
    )


async def _oculai_get_evidence_by_tier(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_evidence_by_tier."""
    run_id: str = params["run_id"]
    person_id: str = params["person_id"]
    max_tier: int = params.get("max_tier", 2)

    return await evidence.get_evidence_by_tier(
        run_id=UUID(run_id),
        person_id=UUID(person_id),
        max_tier=max_tier,
    )


# --- Assessment Tools (4 tools) -----------------------------------------------

async def _oculai_score_candidate(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_score_candidate."""
    run_id: str = params["run_id"]
    person_id: str = params["person_id"]
    dimensions: dict[str, float] = params["dimensions"]
    assessor_agent: str = params["assessor_agent"]
    evidence_ids: list[str] | None = params.get("evidence_ids")
    confidence: float = params.get("confidence", 1.0)
    rationale: str = params.get("rationale", "")
    role_type: str = params.get("role_type", "default")

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


async def _oculai_record_assessment(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_record_assessment."""
    run_id: str = params["run_id"]
    person_id: str = params["person_id"]
    assessor_agent: str = params["assessor_agent"]
    dimension: str = params["dimension"]
    score: float = params["score"]
    confidence: float = params.get("confidence", 1.0)
    rationale: str = params.get("rationale", "")
    evidence_ids: list[str] | None = params.get("evidence_ids")
    role_type: str = params.get("role_type", "default")

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


async def _oculai_get_shortlist(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_shortlist."""
    run_id: str = params["run_id"]
    min_score: float = params.get("min_score", 0)
    limit: int = params.get("limit", 20)

    return await assessment.get_shortlist(
        run_id=UUID(run_id),
        min_score=min_score,
        limit=limit,
    )


async def _oculai_get_score_history(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_score_history."""
    run_id: str = params["run_id"]
    person_id: str | None = params.get("person_id")
    dimension: str | None = params.get("dimension")
    limit: int = params.get("limit", 100)

    return await assessment.get_score_history(
        run_id=UUID(run_id),
        person_id=UUID(person_id) if person_id else None,
        dimension=dimension,
        limit=limit,
    )


# --- Review Orchestrator Tools (5 tools) -------------------------------------

async def _oculai_create_review_session(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_create_review_session."""
    run_id: str = params["run_id"]
    role_type: str = params.get("role_type", "default")
    candidate_ids: list[str] | None = params.get("candidate_ids")

    parsed_ids = [UUID(c) for c in candidate_ids] if candidate_ids else None
    return await review.create_review_session(
        run_id=UUID(run_id),
        role_type=role_type,
        candidate_ids=parsed_ids,
    )


async def _oculai_execute_review_pass(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_execute_review_pass."""
    session_id: str = params["session_id"]
    pass_type: str = params["pass_type"]
    completed_candidate_ids: list[str] | None = params.get("completed_candidate_ids")

    parsed_ids = [UUID(c) for c in completed_candidate_ids] if completed_candidate_ids else None
    return await review.execute_review_pass(
        session_id=UUID(session_id),
        pass_type=pass_type,
        completed_candidate_ids=parsed_ids,
    )


async def _oculai_get_review_progress(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_review_progress."""
    session_id: str = params["session_id"]
    return await review.get_review_progress(UUID(session_id))


async def _oculai_apply_audit_adjustments(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_apply_audit_adjustments."""
    session_id: str = params["session_id"]
    adjustments: list[dict[str, Any]] = params["adjustments"]

    return await review.apply_audit_adjustments(
        session_id=UUID(session_id),
        adjustments=adjustments,
    )


async def _oculai_finalize_review_session(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_finalize_review_session."""
    session_id: str = params["session_id"]
    return await review.finalize_review_session(UUID(session_id))


# --- Report Tools (1 tool) ---------------------------------------------------

async def _oculai_export_report(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_export_report."""
    run_id: str = params["run_id"]
    format: str = params.get("format", "html")

    return await report.export_report(
        run_id=UUID(run_id),
        format=format,
    )


# --- Web Search & Outreach & Browser Tools (7 tools) -------------------------

async def _oculai_search_web(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_search_web."""
    keywords: list[str] = params["keywords"]
    provider: str = params.get("provider", "tavily")
    run_id: str | None = params.get("run_id")
    limit: int = params.get("limit", 20)
    include_domains: list[str] | None = params.get("include_domains")
    exclude_domains: list[str] | None = params.get("exclude_domains")

    return await web_search.search_web(
        keywords=keywords,
        provider=provider,
        run_id=UUID(run_id) if run_id else None,
        limit=limit,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
    )


async def _oculai_create_outreach_draft(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_create_outreach_draft."""
    run_id: str = params["run_id"]
    person_id: str = params["person_id"]
    strategy: str = params["strategy"]
    template: str = params.get("template", "standard")
    channel: str = params.get("channel", "email")
    draft_content: str = params.get("draft_content", "")
    subject: str = params.get("subject", "")
    agent_id: str = params.get("agent_id", "system")

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


async def _oculai_request_human_approval(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_request_human_approval."""
    run_id: str = params["run_id"]
    action_type: str = params["action_type"]
    action_context: dict[str, Any] = params["action_context"]
    draft_content: str = params.get("draft_content", "")
    agent_id: str = params.get("agent_id", "system")

    return await outreach.request_human_approval(
        run_id=UUID(run_id),
        action_type=action_type,
        action_context=action_context,
        draft_content=draft_content,
        agent_id=agent_id,
    )


async def _oculai_check_approval_status(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_check_approval_status."""
    approval_id: str = params["approval_id"]
    return await outreach.check_approval_status(UUID(approval_id))


async def _oculai_list_pending_approvals(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_list_pending_approvals."""
    run_id: str | None = params.get("run_id")
    return await outreach.list_pending_approvals(
        run_id=UUID(run_id) if run_id else None,
    )


async def _oculai_get_outreach_history(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_get_outreach_history."""
    person_id: str = params["person_id"]
    limit: int = params.get("limit", 50)
    return await outreach.get_outreach_history(
        person_id=UUID(person_id),
        limit=limit,
    )


async def _oculai_capture_page_evidence(params: dict[str, Any]) -> dict[str, Any]:
    """Handler for oculai_capture_page_evidence."""
    url: str = params["url"]
    person_id: str | None = params.get("person_id")
    run_id: str | None = params.get("run_id")
    mode: str = params.get("mode", "text")
    captured_by_agent: str = params.get("captured_by_agent", "system")
    selector: str | None = params.get("selector")

    return await browser.capture_page_evidence(
        url=url,
        person_id=UUID(person_id) if person_id else None,
        run_id=UUID(run_id) if run_id else None,
        mode=mode,
        captured_by_agent=captured_by_agent,
        selector=selector,
    )


# ============================================================================
# Tool Registry — flat dict of all 41 tools
# ============================================================================

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    # Run Lifecycle & Plan Checkpoint (3)
    "oculai_create_run": _oculai_create_run,
    "oculai_get_run_state": _oculai_get_run_state,
    "oculai_checkpoint_plan": _oculai_checkpoint_plan,
    # Task Claiming & Completion (3)
    "oculai_claim_tasks": _oculai_claim_tasks,
    "oculai_complete_task": _oculai_complete_task,
    "oculai_fail_task": _oculai_fail_task,
    # ReAct Iteration Recording & Retrieval (2)
    "oculai_record_iteration": _oculai_record_iteration,
    "oculai_get_task_iterations": _oculai_get_task_iterations,
    # Cross-Agent Broadcasts (2)
    "oculai_broadcast_discovery": _oculai_broadcast_discovery,
    "oculai_get_broadcasts": _oculai_get_broadcasts,
    # Source Tools (5)
    "oculai_list_source_capabilities": _oculai_list_source_capabilities,
    "oculai_search_source": _oculai_search_source,
    "oculai_deep_search": _oculai_deep_search,
    "oculai_get_search_progress": _oculai_get_search_progress,
    "oculai_crawl_site": _oculai_crawl_site,
    # Source Detail (1)
    "oculai_fetch_source_detail": _oculai_fetch_source_detail,
    # Candidate Tools (6)
    "oculai_upsert_candidate": _oculai_upsert_candidate,
    "oculai_upsert_candidates_batch": _oculai_upsert_candidates_batch,
    "oculai_link_identity": _oculai_link_identity,
    "oculai_list_candidates": _oculai_list_candidates,
    "oculai_get_candidate": _oculai_get_candidate,
    # Evidence Tools (3)
    "oculai_attach_evidence": _oculai_attach_evidence,
    "oculai_get_evidence": _oculai_get_evidence,
    "oculai_get_evidence_by_tier": _oculai_get_evidence_by_tier,
    # Assessment Tools (4)
    "oculai_score_candidate": _oculai_score_candidate,
    "oculai_record_assessment": _oculai_record_assessment,
    "oculai_get_shortlist": _oculai_get_shortlist,
    "oculai_get_score_history": _oculai_get_score_history,
    # Review Orchestrator Tools (5)
    "oculai_create_review_session": _oculai_create_review_session,
    "oculai_execute_review_pass": _oculai_execute_review_pass,
    "oculai_get_review_progress": _oculai_get_review_progress,
    "oculai_apply_audit_adjustments": _oculai_apply_audit_adjustments,
    "oculai_finalize_review_session": _oculai_finalize_review_session,
    # Report Tools (1)
    "oculai_export_report": _oculai_export_report,
    # Web Search & Outreach & Browser Tools (7)
    "oculai_search_web": _oculai_search_web,
    "oculai_create_outreach_draft": _oculai_create_outreach_draft,
    "oculai_request_human_approval": _oculai_request_human_approval,
    "oculai_check_approval_status": _oculai_check_approval_status,
    "oculai_list_pending_approvals": _oculai_list_pending_approvals,
    "oculai_get_outreach_history": _oculai_get_outreach_history,
    "oculai_capture_page_evidence": _oculai_capture_page_evidence,
}


# ============================================================================
# Public API
# ============================================================================

def get_tool(name: str) -> Callable[..., Any] | None:
    """Look up a tool handler by name.

    Args:
        name: Tool name (e.g. "oculai_create_run")

    Returns:
        The async handler callable, or None if not found.
    """
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[str]:
    """Return the sorted list of all registered tool names."""
    return sorted(TOOL_REGISTRY.keys())
