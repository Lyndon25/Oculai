"""M4 End-to-End Integration Test for Oculai MCP Server."""
import asyncio
import json
import sys
from uuid import UUID
sys.path.insert(0, 'src')

from oculai_mcp.db.client import get_db_pool, close_db_pool
from oculai_mcp.db import runs, tasks


async def main():
    agent = 'integration-test'

    # ==================== STEP 1: Create Run ====================
    print('=== STEP 1: Create Run ===')
    jd = {
        'title': 'Senior NLP Researcher',
        'description': (
            'Looking for an experienced NLP researcher with deep expertise '
            'in large language model pretraining. 3-5 years experience, '
            'publications at top venues.'
        ),
        'requirements': [
            'LLM pretraining', 'PyTorch', 'Transformers',
            '3+ years', 'PhD preferred',
        ],
    }
    run_id = await runs.create_run(
        title='Test: Senior NLP Researcher',
        target_profile=jd,
        target_keywords=['NLP', 'LLM', 'pretraining', 'transformers', 'deep learning'],
        target_domains=['AI/ML', 'NLP'],
        created_by=agent,
    )
    print(f'  Created run: {run_id}')

    run = await runs.get_run(run_id)
    print(f'  Run status: {run["status"]}')
    assert run['status'] == 'draft', f'Expected draft, got {run["status"]}'

    # ==================== STEP 2: Checkpoint Plan ====================
    print('=== STEP 2: Checkpoint Plan ===')
    plan_json = {
        'strategy': 'Multi-source search across arXiv, Semantic Scholar, and GitHub',
        'tasks': [
            {
                'step_key': 'search_arxiv',
                'task_type': 'source_research',
                'task_name': 'Search arXiv for NLP researchers',
                'priority': 10,
                'input': {
                    'source': 'arxiv',
                    'query': 'large language model pretraining',
                    'max_results': 20,
                },
            },
            {
                'step_key': 'search_s2',
                'task_type': 'source_research',
                'task_name': 'Search Semantic Scholar',
                'priority': 10,
                'input': {
                    'source': 'semantic_scholar',
                    'query': 'LLM pretraining efficiency',
                    'max_results': 20,
                },
            },
            {
                'step_key': 'enrich_profiles',
                'task_type': 'enrich_profiles',
                'task_name': 'Enrich candidate profiles',
                'priority': 5,
                'input': {},
                'depends_on': ['search_arxiv', 'search_s2'],
            },
            {
                'step_key': 'evaluate_candidates',
                'task_type': 'evaluate_candidates',
                'task_name': 'Evaluate candidate fit',
                'priority': 5,
                'input': {},
                'depends_on': ['enrich_profiles'],
            },
            {
                'step_key': 'generate_report',
                'task_type': 'generate_report',
                'task_name': 'Generate final report',
                'priority': 1,
                'input': {},
                'depends_on': ['evaluate_candidates'],
            },
        ],
    }

    plan_id = await tasks.create_plan(
        run_id=run_id,
        planner_state_json=plan_json,
        strategy_summary=plan_json['strategy'],
        created_by_agent=agent,
    )
    print(f'  Created plan: {plan_id}')

    await tasks.update_run_active_plan(run_id, plan_id)
    await runs.update_run_status(run_id, 'running')

    created_tasks: dict = {}
    for t in plan_json['tasks']:
        task_id = await tasks.create_task(
            plan_id=plan_id,
            run_id=run_id,
            task_type=t['task_type'],
            task_name=t['task_name'],
            input_data=t.get('input', {}),
            step_key=t['step_key'],
            priority=t.get('priority', 5),
            created_by_agent=agent,
        )
        created_tasks[t['step_key']] = task_id
        print(f'  Created task: {t["step_key"]} -> {task_id}')

    for t in plan_json['tasks']:
        if 'depends_on' in t:
            for dep_key in t['depends_on']:
                dep_task_id = created_tasks.get(dep_key)
                task_id = created_tasks[t['step_key']]
                if dep_task_id:
                    await tasks.create_task_dependency(
                        plan_id=plan_id,
                        task_id=task_id,
                        depends_on_task_id=dep_task_id,
                    )
                    print(f'  Dependency: {t["step_key"]} depends on {dep_key}')

    # ==================== STEP 3: Get Run State ====================
    print('=== STEP 3: Get Run State ===')
    state = await runs.get_run_state_summary(run_id)
    print(f'  Run status: {state["run"]["status"]}')
    print(f'  Active plan: {"yes" if state["plan"] else "no"}')
    print(f'  Candidate count: {state["candidate_count"]}')
    print(f'  Task stats: {json.dumps(state["task_stats"], default=str)}')
    assert state['run']['status'] == 'running'
    assert state['plan'] is not None
    assert len(state['task_stats']) >= 4  # 4 distinct task_type+status combos

    # ==================== STEP 4: Claim Tasks ====================
    print('=== STEP 4: Claim Tasks ===')
    claimed = await tasks.claim_task_batch(
        run_id=run_id,
        task_types=['source_research'],
        batch_size=3,
        agent_id='test-researcher-1',
    )
    print(f'  Claimed {len(claimed)} source_research tasks')
    for t in claimed:
        print(f'    - {t["task_name"]} ({t["task_id"]})')
    assert len(claimed) == 2

    claimed2 = await tasks.claim_task_batch(
        run_id=run_id,
        task_types=['source_research'],
        batch_size=3,
        agent_id='test-researcher-2',
    )
    print(f'  Second claim (should be 0): {len(claimed2)}')
    assert len(claimed2) == 0, f'Expected 0 claimed, got {len(claimed2)}'

    # ==================== STEP 5: Complete Tasks ====================
    print('=== STEP 5: Complete Tasks ===')
    arxiv_task = next(t for t in claimed if 'arxiv' in t['task_name'].lower())
    await tasks.complete_task(
        task_id=arxiv_task['task_id'],
        agent_id='test-researcher-1',
        output_data={
            'candidates_found': 15,
            'source': 'arxiv',
            'search_query': 'LLM pretraining',
        },
    )
    print(f'  Completed: {arxiv_task["task_name"]}')

    s2_task = next(t for t in claimed if 'scholar' in t['task_name'].lower())
    await tasks.complete_task(
        task_id=s2_task['task_id'],
        agent_id='test-researcher-1',
        output_data={
            'candidates_found': 12,
            'source': 'semantic_scholar',
            'search_query': 'LLM pretraining efficiency',
        },
    )
    print(f'  Completed: {s2_task["task_name"]}')

    for tid in [arxiv_task['task_id'], s2_task['task_id']]:
        t = await tasks.get_task(tid)
        assert t['status'] == 'done', f'Task {tid} should be done, got {t["status"]}'
        print(f'  Verified task {t["task_name"]} status: {t["status"]}')

    # But enrich_profiles should still be pending (not unblocked yet, need resolve_task_inputs)
    enrich_tid = created_tasks['enrich_profiles']
    enrich_task = await tasks.get_task(enrich_tid)
    print(f'  Enrich task status after deps done: {enrich_task["status"]}')

    # ==================== STEP 6: Candidate Operations ====================
    print('=== STEP 6: Candidate Operations ===')
    from oculai_mcp.tools.candidates import upsert_candidate, get_candidate, list_candidates

    candidates = [
        {'name': 'Alice Chen', 'institution': 'Stanford University'},
        {'name': 'Bob Zhang', 'institution': 'Tsinghua University'},
        {'name': 'Carol Wang', 'institution': 'CMU'},
    ]

    person_ids = []
    for c in candidates:
        result = await upsert_candidate(
            run_id=run_id,
            person_data=c,
            source_name='arxiv',
            agent_id=agent,
        )
        pid = UUID(result['person_id'])
        person_ids.append(pid)
        print(f'  Upserted: {c["name"]} -> {pid} (match: {result["match_type"]})')

    for pid in person_ids:
        cand = await get_candidate(pid)
        assert cand is not None
        inst = cand["person"].get('latest_institution', 'unknown')
        print(f'  Retrieved: {cand["person"]["canonical_name"]} from {inst}')

    all_candidates = await list_candidates(run_id=run_id)
    print(f'  Listed {len(all_candidates)} candidates for run')
    assert len(all_candidates) >= 3

    # ==================== STEP 7: Evidence Operations ====================
    print('=== STEP 7: Evidence Operations ===')
    from oculai_mcp.tools.evidence import attach_evidence, get_evidence

    await attach_evidence(
        person_id=person_ids[0],
        evidence_type='paper',
        title='Scaling Laws for Neural Language Models',
        source_name='arxiv',
        content={
            'doi': '10.1234/example.2024',
            'year': 2024,
            'citations': 150,
        },
        source_url='https://arxiv.org/abs/2401.12345',
        run_id=run_id,
        captured_by_agent=agent,
    )
    print(f'  Attached evidence to {person_ids[0]}')

    ev_result = await get_evidence(person_ids[0])
    print(f'  Retrieved {ev_result["total"]} evidence items for {person_ids[0]}')
    assert ev_result['total'] >= 1

    # ==================== STEP 8: Assessment ====================
    print('=== STEP 8: Assessment ===')
    from oculai_mcp.tools.assessment import score_candidate, record_assessment, get_shortlist

    await score_candidate(
        run_id=run_id,
        person_id=person_ids[0],
        dimensions={
            'academic': 8.5,
            'engineering': 9.0,
            'leadership': 7.5,
            'culture_fit': 8.0,
        },
        assessor_agent=agent,
    )
    print(f'  Scored {person_ids[0]}: 4 dimensions')

    await score_candidate(
        run_id=run_id,
        person_id=person_ids[1],
        dimensions={
            'academic': 7.0,
            'engineering': 7.5,
            'leadership': 8.5,
            'culture_fit': 7.0,
        },
        assessor_agent=agent,
    )
    print(f'  Scored {person_ids[1]}: 4 dimensions')

    await score_candidate(
        run_id=run_id,
        person_id=person_ids[2],
        dimensions={
            'academic': 9.0,
            'engineering': 8.5,
            'leadership': 6.5,
            'culture_fit': 8.5,
        },
        assessor_agent=agent,
    )
    print(f'  Scored {person_ids[2]}: 4 dimensions')

    # Record a single-dimension assessment
    await record_assessment(
        run_id=run_id,
        person_id=person_ids[0],
        assessor_agent=agent,
        dimension='overall',
        score=8.2,
        rationale='Strong candidate with excellent publication record',
    )
    print(f'  Recorded assessment for {person_ids[0]}')

    shortlist = await get_shortlist(run_id=run_id, min_score=0, limit=10)
    print(f'  Shortlist (all candidates): {shortlist["count"]} candidates')
    for s in shortlist['shortlist']:
        print(f'    - {s["name"]}: score={s.get("overall_score", "N/A")}')
    assert shortlist['count'] >= 2, f'Expected 2+ in shortlist, got {shortlist["count"]}'

    # ==================== STEP 9: Report ====================
    print('=== STEP 9: Report ===')
    from oculai_mcp.tools.report import export_report

    report = await export_report(run_id=run_id, format='json')
    print(f'  Report generated: {report.get("candidate_count", 0)} candidates')
    assert 'run_id' in report or 'candidates' in report

    # ==================== STEP 10: Final Run State ====================
    print('=== STEP 10: Final Run State ===')
    final_state = await runs.get_run_state_summary(run_id)
    print(f'  Run: {final_state["run"]["title"]}')
    print(f'  Status: {final_state["run"]["status"]}')
    print(f'  Candidates: {final_state["candidate_count"]}')
    print('  Task stats:')
    for ts in final_state['task_stats']:
        print(f'    {ts["task_type"]}: {ts["status"]} = {ts["cnt"]}')

    # ==================== PASS ====================
    print()
    print('=' * 50)
    print('ALL INTEGRATION TESTS PASSED')
    print('=' * 50)

    await close_db_pool()


if __name__ == '__main__':
    asyncio.run(main())
