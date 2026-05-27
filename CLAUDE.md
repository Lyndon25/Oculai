# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Oculai is a **multi-Agent collaborative talent sourcing system** for **Chinese company HRs**. Claude Code is the sole orchestrator/decision-maker. PostgreSQL is the global async state pool. The Python/MCP layer exposes only deterministic functions — **no LLM calls, no autonomous decisions**.

**Core constraint: Only search for Chinese/China-based candidates.** All sources, queries, and evidence gathering must target Chinese talent. See `oculai/skills/oculai-talent-sourcing/SKILL.md` for the China-First Mandate.

## Architecture Principle

```
Claude Code (decides everything)
    ↕ stdio MCP
FastMCP Server (deterministic tools only)
    ↕ asyncpg
PostgreSQL 16 + pgvector (single source of truth)
```

- Main Agent reads `oculai/skills/oculai-talent-sourcing/SKILL.md` for the orchestration protocol
- 7 subagents in `oculai/agents/` are Markdown prompts, not Python classes
- 5 slash commands in `oculai/commands/` activate the skill
- Workflows are DAG-based: Plan → Task (free-form TEXT type) → TaskDependency
- Concurrent task claiming uses PostgreSQL `FOR UPDATE SKIP LOCKED`

## Common Commands

### Database
```bash
# Start PostgreSQL (run from oculai-db/)
cd oculai-db && docker compose up -d

# Restart after config changes
cd oculai-db && docker compose restart

# Connect via psql
docker exec oculai-postgres psql -U oculai -d oculai

# Full reset (destroy data, re-init from schema/)
cd oculai-db && docker compose down -v && docker compose up -d
```

### MCP Server
```bash
# Install dependencies
cd oculai-mcp && pip install -e .

# Run via fastmcp (for Claude Code integration)
cd oculai-mcp && fastmcp run src/oculai_mcp/server.py

# Dev mode (MCP Inspector at localhost:5173)
cd oculai-mcp && fastmcp dev src/oculai_mcp/server.py
```

### Tests
```bash
# Run the integration test (requires running PostgreSQL)
cd oculai-mcp && python tests/integration_test.py

# Compile-check all Python modules (no DB needed)
cd oculai-mcp && python -c "
import py_compile
from pathlib import Path
for f in Path('src/oculai_mcp').rglob('*.py'):
    py_compile.compile(str(f), doraise=True)
print('OK')
"
```

## Environment

- `.env` file at `oculai-mcp/.env` — read by `pydantic-settings` (mtime-aware cache reload)
- `.env.example` at `oculai-mcp/.env.example` — documents all available keys with signup URLs
- DB credentials default: `oculai` / `oculai_dev` on `localhost:5432`
- PostgreSQL config at `oculai-db/postgresql.conf` — must include `listen_addresses = '*'` for Docker Desktop on Windows
- Container healthcheck via `pg_isready` every 10s
- API keys in `config.py` Settings class: `github_token`, `semantic_scholar_api_key` (alias: `s2_api_key`), `openalex_email`, `baidu_api_key`, `tavily_api_key`, `exa_api_key`
- `BAIDU_API_KEY` uses the Qianfan AppBuilder Bearer token format (`bce-v3/ALTAK-xxx/xxx`) and powers both `baidu_qianfan` and `baidu_scholar` sources

## Key Implementation Details

### asyncpg JSONB handling
The `db/client.py` registers codecs for JSON/JSONB columns. **Never call `json.dumps()` on values passed to asyncpg** — the codec handles serialization. Passing `json.dumps()` output causes double-encoding. Pass raw Python dicts/lists.

### Tool registration pattern
All MCP tools are `@mcp.tool` decorated async functions in `server.py`. Each tool converts `str` → `UUID`, delegates to a `tools/` or `db/` module, and returns `dict[str, Any]`. Tool names are prefixed `oculai_`.

To add a new tool:
1. Implement the logic in `src/oculai_mcp/tools/` or `src/oculai_mcp/db/`
2. Register a `@mcp.tool` wrapper in `server.py`

### Source connectors
Sources follow the `IDataSource` ABC (`sources/base.py`):
- `search(SearchQuery)` → `list[RawCandidate]` — keyword search (required)
- `get_detail(external_id)` → `RawCandidate | None` — profile lookup (required)
- `check_health()` → `HealthStatus` — endpoint health (required)
- `get_capabilities()` → `dict` — metadata descriptor (implemented on base)
- `auth_required: bool` — set `True` if the source reads an API key
- `supported_operations: list[str]` — `["search"]` or `["search", "get_detail"]`

Sources auto-register in `sources/registry.py` on import. Adding a new source requires:
1. Implement `IDataSource` in a new `sources/*.py` file
2. Import and `register_source()` in `registry.py`
3. If it needs an API key, add a field to `config.py` Settings class

**Source availability quick reference:**

| Source | Key Required | Notes |
|---|---|---|
| arxiv, dblp, openalex, conference | None | Always available |
| github | `GITHUB_TOKEN` | 60 req/h without, 5000 req/h with |
| semantic_scholar | `SEMANTIC_SCHOLAR_API_KEY` | Optional, increases rate limit |
| baidu_qianfan | `BAIDU_API_KEY` | Official Qianfan AI Search API, 100 calls/day free |
| baidu_scholar | `BAIDU_API_KEY` | Qianfan Scholar Search API (beta endpoint, may 404) |
| baidu | None | Unofficial `baidusearch` PyPI scraper (`pip install baidusearch`) |
| industry | `GITHUB_TOKEN` | Wraps GitHub for industry-focused search |
| personal_homepage | None | HTML scraping, limited to domain-mapped universities |
| juejin (掘金) | None | Public API (api.juejin.cn), user search + profile, Chinese dev community |
| zhihu (知乎) | None | Public API (zhihu.com/api/v4), people search + profile, may need browser UA |
| csdn (中国开发者网络) | None | Search API + profile HTML scraping, technical blog platform |
| web_search (tool) | `TAVILY_API_KEY` or `EXA_API_KEY` | Not a source; MCP tool in `tools/web_search.py` |

### Database migrations
Schema is managed via numbered SQL files in `oculai-db/schema/` that run on container init (`docker-entrypoint-initdb.d`). Files execute in alphabetical order:
- `001_extensions.sql` — pgvector, uuid-ossp, pg_trgm
- `002_enums.sql` — domains and type enums
- `003_tables.sql` — core entity tables (Person, SourcingJob, etc.)
- `003b_supporting_tables.sql` — DataConflict, ChangeLog, BrowserEvidence, etc.
- `004_indexes.sql`, `005_foreign_keys.sql`, `006_functions.sql`, `007_triggers.sql`, `008_seed.sql`

To change the schema: edit the relevant SQL file, then `docker compose down -v && docker compose up -d` for a clean rebuild.

### Identity resolution chain
When upserting a candidate (`candidates.py`), the system runs a 3-step resolution:
1. Hard match by external ID (ORCID, GitHub, DBLP, etc.)
2. Name + institution match (ILIKE)
3. Fuzzy trigram match (similarity > 0.7, configurable)

If no match, a new Person is created. Conflicting non-NULL values during merge trigger `DataConflict` records.

### Assessment dimensions
Valid assessment dimensions are domain-constrained: `academic`, `engineering`, `leadership`, `communication`, `culture_fit`, `skill_match`, `location`, `career_stage`, `mobility`, `overall`.

### Human approval gate
All external actions (outreach, data export) must pass through `request_human_approval`. The system **never sends messages autonomously**. Outreach drafts are created with `create_outreach_draft` and blocked until a human approves via the database.

## Testing Specification

The project is tested exclusively through **end-to-end full-pipeline runs**. There are no unit tests or integration tests — every test is a complete sourcing run through the skill pipeline.

### Test Directory Structure

```
temp/                       # gitignored — all test artifacts live here
└── test/
    ├── 001-ml-engineer/    # Test round 1
    ├── 002-nlp-scientist/  # Test round 2
    ├── 003-.../            # Test round 3+
    └── ...
```

Each test round creates a **numbered subdirectory** under `temp/test/` (zero-padded 3-digit prefix). The directory contains all process artifacts and deliverables for that round.

**Per-round contents:**
- `jd.md` — the crafted JD for this round
- `output.html` — the final polished HTML report (primary deliverable)
- `test-report.html` — a polished HTML test report describing the test execution, results summary, and any issues found
- `artifacts/` — intermediate outputs (agent outputs, plan snapshots, search results)

### Test Protocol

**1. Each round requires a fresh JD**

Before every test run, draft a new JD targeting a different domain or role from previous rounds. Rotate across categories:

| Category | Example Roles |
|---|---|
| AI/ML Research | NLP Scientist, CV Researcher, RL Engineer, LLM Alignment Researcher |
| Systems/Infra | Distributed Systems Engineer, Database Engineer, SRE, Platform Engineer |
| Full-Stack/Product | Frontend Architect, Backend Engineer, Mobile Developer, DevTools Engineer |
| Cross-Domain | Bioinformatics Researcher, Quantitative Trader, Robotics Engineer, Chip Designer |

The JD must include: role title, company context, required skills, nice-to-haves, seniority level, and location preference.

**2. Execute the full skill pipeline**

Run the complete pipeline as defined in `oculai/skills/oculai-talent-sourcing/SKILL.md`:

```
1. oculai_create_run
2. oculai_list_source_capabilities
3. Launch Search Strategist subagent
4. oculai_checkpoint_plan
5. Launch Source Researchers (parallel)
6. oculai_upsert_candidate (per candidate)
7. Launch Identity Resolver
8. Launch Profile Enricher
9. Launch Fit Evaluator
10. Launch Quality Auditor
11. oculai_export_report (format=html)
12. (optional) Launch Outreach Strategist
13. Present results
```

**3. Save all deliverables**

After the pipeline completes:
- Write `output.html` from `oculai_export_report` result to the test round directory
- Write `test-report.html` summarizing: JD used, candidates found, scores distribution, pipeline performance, issues/regressions, and observations
- Save any notable intermediate outputs to `artifacts/`

**4. Test report format**

The `test-report.html` is a polished, self-contained HTML file (same design philosophy as the main deliverable) containing:

| Section | Content |
|---|---|
| Header | Test round number, role, date, run status |
| JD | The full job description used |
| Pipeline Summary | Steps completed, timing per phase, task counts |
| Candidate Overview | Ranking table with scores, evidence counts |
| Quality Assessment | Auditor findings, bias risks, data gaps |
| Issues & Observations | What went wrong, what was surprising, regressions |
| Source Performance | Per-source: query strategy, results returned, quality |

### Pre-Test Checklist

Before starting a test run:
- [ ] PostgreSQL is running (`cd oculai-db && docker compose up -d`)
- [ ] MCP server is connectable
- [ ] New JD is drafted and saved to `temp/test/<NNN>-<name>/jd.md`
- [ ] Test round directory is created with `artifacts/` subdirectory

## Directory Map

| Directory | Purpose |
|---|---|
| `oculai/skills/` | Claude Code skill definition (trigger, protocol, references) |
| `oculai/agents/` | 7 subagent Markdown prompt files |
| `oculai/commands/` | 5 slash command definitions |
| `oculai-db/` | Docker Compose, PostgreSQL config, SQL schema migrations |
| `oculai-mcp/src/oculai_mcp/` | Python MCP server source |
| `oculai-mcp/src/oculai_mcp/db/` | Database access layer (asyncpg, CRUD, retry logic) |
| `oculai-mcp/src/oculai_mcp/tools/` | Domain tool implementations (candidates, evidence, assessment, etc.) |
| `oculai-mcp/src/oculai_mcp/sources/` | Source connectors (arXiv, DBLP, GitHub, Semantic Scholar, OpenAlex, Baidu scrapers, Baidu Qianfan, homepage, Juejin, Zhihu, CSDN) |
| `oculai-mcp/src/oculai_mcp/tools/web_search.py` | Tavily/Exa web search MCP tool (separate from source connectors) |
| `oculai-mcp/tests/` | Integration tests |
