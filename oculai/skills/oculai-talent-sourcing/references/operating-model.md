# Operating Model

## System Architecture

Oculai is an Agent-Native multi-agent talent sourcing system:

```
Claude Code Main Agent (You)
  → Planner / Coordinator / Reviewer
  → Makes ALL decisions

7 Cognitive Subagents (Markdown prompts)
  → Search Strategist
  → Source Researcher (parallel, multi-instance)
  → Identity Resolver
  → Profile Enricher
  → Fit Evaluator
  → Outreach Strategist
  → Quality Auditor

MCP Tool Layer (Python/FastMCP)
  → Deterministic domain functions only
  → No LLM calls, no autonomous decisions

PostgreSQL
  → Global state pool
  → Plan → Task → TaskDependency DAG model
  → FOR UPDATE SKIP LOCKED for concurrency
  → Full provenance, lineage, changelog, conflict tracking
```

## Core Principles

1. **Claude Code is the only decision-maker.** No Python LLM calls. No "second brain."
2. **State-first.** Everything persisted via MCP tools. Database is single source of truth.
3. **Evidence-first.** Every claim backed by evidence with IDs and provenance.
4. **Subagents are cognitive collaborators, not Python classes.** Each has its own Markdown prompt.
5. **Task DAG, not fixed phases.** Different roles need different execution graphs.
6. **Human approval for external actions.** No autonomous outreach or external writes.

## Task DAG Model

Instead of fixed Phase 0-6 pipeline, Oculai uses a dynamic DAG:

- **Plan**: A sourcing run's execution plan (one per run)
- **Task**: Individual unit of work with type, inputs, outputs, status, priority
- **TaskDependency**: Edge from task to its prerequisite

Task types are free-form TEXT, not a closed enum — the main Agent defines whatever types make sense for the current JD.

Common task types: `search_strategy`, `search`, `identity_resolution`, `profile_enrichment`, `evaluate`, `quality_audit`, `outreach_draft`

## Concurrency Model

- Multiple Source Researchers claim and execute search tasks in parallel
- `FOR UPDATE SKIP LOCKED` ensures no two agents claim the same task
- Stale claimed tasks (>10 min) are auto-released and retried
- All state changes flow through PostgreSQL

## Data Flow

```
JD Text
  → Search Strategist → Search Strategy JSON
  → Plan + Task DAG (persisted)
  → Source Researchers × N → RawCandidate lists
  → upsert_candidate (identity resolution, dedup)
  → Identity Resolver → merged, linked identities
  → Profile Enricher → enriched profiles with evidence
  → Fit Evaluator → scored assessments
  → Quality Auditor → audit report
  → Main Agent → shortlist + outreach drafts → Human Approval
```
