# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Oculai is an **Agent-Native multi-agent talent sourcing system**. Claude Code is the sole orchestrator/decision-maker. PostgreSQL is the global async state pool. The Python/MCP layer exposes only deterministic functions — **no LLM calls, no autonomous decisions**.

Target environment: Chinese candidates + global evidence, Baidu as important component, aggressive/forward-looking tech stack.

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
- DB credentials default: `oculai` / `oculai_dev` on `localhost:5432`
- PostgreSQL config at `oculai-db/postgresql.conf` — must include `listen_addresses = '*'` for Docker Desktop on Windows
- Container healthcheck via `pg_isready` every 10s

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
- `get_tool_schema()` — JSON Schema for the search parameters
- `get_capabilities()` — What this source can do
- `search(SearchQuery)` → `list[RawCandidate]`

Sources auto-register in `sources/registry.py` on import. Adding a new source requires:
1. Implement `IDataSource` in a new `sources/*.py` file
2. Import and `register_source()` in `registry.py`

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
| `oculai-mcp/src/oculai_mcp/sources/` | Source connectors (arXiv, DBLP, GitHub, Semantic Scholar, OpenAlex, Baidu, etc.) |
| `oculai-mcp/tests/` | Integration tests |
