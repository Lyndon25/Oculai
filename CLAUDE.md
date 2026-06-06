# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Oculai is a **multi-Agent collaborative talent sourcing system** for **Chinese company HRs**. Claude Code is the sole orchestrator/decision-maker. PostgreSQL is the global async state pool. The Python/MCP layer exposes only deterministic functions — **no LLM calls, no autonomous decisions**.

**Core constraint: Only search for Chinese/China-based candidates.** All sources, queries, and evidence gathering must target Chinese talent. See `oculai/skills/oculai-talent-sourcing/SKILL.md` for the China-First Mandate.

## Architecture Principle

The system has two deployment modes:

**Mode A: Claude Code MCP (CLI)**
```
Claude Code (decides everything)
    ↕ stdio MCP (JSON-RPC)
FastMCP Server (deterministic tools only)
    ↕ asyncpg
PostgreSQL 16 + pgvector (single source of truth)
```

**Mode B: Electron Desktop App**
```
Oculai Desktop (Electron + React)
    └── Electron Main Process
        ├── embedded PostgreSQL (PostgresManager, port 15432)
        ├── Python sidecar (jsonl_server.py, child_process.spawn)
        │   └── JSONL protocol over stdin/stdout
        └── Pi AI AgentSession (pi-coding-agent SDK)
            └── 41 Oculai tools registered as Pi extension tools
```

- Main Agent reads `oculai/skills/oculai-talent-sourcing/SKILL.md` for the orchestration protocol
- 8 subagents in `oculai/agents/` are Markdown prompts, not Python classes; Query Optimizer handles iterative search refinement
- 5 slash commands in `oculai/commands/` activate the skill
- Workflows are DAG-based: Plan → Task (free-form TEXT type) → TaskDependency
- Concurrent task claiming uses PostgreSQL `FOR UPDATE SKIP LOCKED`
- ReAct iteration logs and cross-agent discovery broadcasts are persisted for auditability and resume
- The desktop app bundles all resources (schema, agents, skills, commands) under `oculai-desktop/resources/`

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
# Install core dependencies
cd oculai-mcp && pip install -e .

# Install development dependencies from pyproject.toml
cd oculai-mcp && pip install -e ".[dev]"

# Optional source/browser extras
cd oculai-mcp && pip install -e ".[playwright,baidu,duckduckgo]" && python -m playwright install chromium

# Run via fastmcp (for Claude Code integration)
cd oculai-mcp && fastmcp run src/oculai_mcp/server.py

# Dev mode (MCP Inspector at localhost:5173)
cd oculai-mcp && fastmcp dev src/oculai_mcp/server.py
```

### Desktop App (Electron)
```bash
# Install dependencies
cd oculai-desktop && npm install

# Dev mode (Vite HMR + Electron)
cd oculai-desktop && npm run dev

# Type check
cd oculai-desktop && npm run typecheck

# Production build
cd oculai-desktop && npm run build
```

The Electron app embeds its own PostgreSQL (via `postgres-manager.ts`) and spawns the Python JSONL server as a child process. It does NOT require Docker.

### JSONL Server (Python Sidecar)
```bash
# Run the JSONL server directly (used by Electron app, not Claude Code)
cd oculai-mcp && python -m oculai_mcp.jsonl_server
```

The JSONL server reads tool calls from stdin (one JSON object per line) and writes responses to stdout. Stderr carries system/status messages. This is the protocol the Electron main process uses to call Oculai tools without MCP JSON-RPC framing. See `jsonl_server.py` and `tool_registry.py`.

### Tests / Checks
```bash
# Compile-check all Python modules (no DB needed)
cd oculai-mcp && python -c "
import py_compile
from pathlib import Path
for f in Path('src/oculai_mcp').rglob('*.py'):
    py_compile.compile(str(f), doraise=True)
print('OK')
"

# Run the MCP DB integration smoke test (requires running PostgreSQL)
cd oculai-mcp && python tests/integration_test.py
```

No pytest test cases are currently committed. Product acceptance testing is through full Oculai pipeline runs saved under `temp/test/<NNN>-<slug>/`.

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

Current tool groups include run lifecycle, planning/tasks, ReAct iterations, cross-agent broadcasts, source search/detail, deep search/progress, candidates/batch upsert, evidence/evidence tiers, assessment/score history, review sessions, reports, web search, outreach, approvals, and browser evidence.

To add a new tool:
1. Implement the logic in `src/oculai_mcp/tools/` or `src/oculai_mcp/db/`
2. Register a `@mcp.tool` wrapper in `server.py`
3. Add the handler function to `tool_registry.py` and add its name to the `TOOL_REGISTRY` dict
4. If the tool needs desktop-app access, also add its schema to `OCULAI_TOOLS` in `oculai-desktop/src/main/pi-session.ts`

### Tool Registry & JSONL Server
`tool_registry.py` extracts all 41 `@mcp.tool` functions into a flat `TOOL_REGISTRY` dict (`dict[str, Callable]`) where each handler accepts a plain `params: dict` and returns `dict`. This decouples the tools from FastMCP's decorator-based registration, enabling:

- **JSONL server** (`jsonl_server.py`): a stdio bridge that reads JSONL requests from stdin, dispatches to `TOOL_REGISTRY`, and writes JSONL responses to stdout. Used by the Electron desktop app's `ToolBridge` (`oculai-desktop/src/main/tool-bridge.ts`) which spawns the Python process as a sidecar.
- **Pi extension registration**: the Electron main process registers all 41 tools as Pi extension tools that delegate to the JSONL bridge.

Protocol format:
```
→ {"id": "req-1", "method": "oculai_create_run", "params": {"job_title": "...", "jd_text": "..."}}
← {"id": "req-1", "ok": true, "result": {"run_id": "...", "status": "draft"}}
```

### Site Crawler & HTML Denoising
`tools/site_crawler.py` provides BFS-based multi-page website crawling for deep candidate evidence discovery (personal homepages, lab pages, portfolios). `utils/html_denoise.py` converts raw HTML to clean Markdown ("fit_markdown"), removing navigation, ads, sidebars, and scripts — inspired by crawl4ai. The denoiser auto-detects JavaScript-heavy SPAs and falls back to Playwright rendering when needed.

New tool: `oculai_crawl_site(start_url, max_pages, max_depth, same_domain_only)` → per-page Markdown, link graph, combined summary.

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
| arxiv, dblp, openalex, conference, acl_anthology, pmlr | None | Always available academic/publication sources |
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
| duckduckgo | None | Free web search, no API key required (`pip install duckduckgo-search`). Name extraction from titles/snippets. |
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
Valid assessment dimensions are domain-constrained: `academic`, `engineering`, `leadership`, `communication`, `culture_fit`, `skill_match`, `location`, `career_stage`, `mobility`, `overall`. The assessment engine computes confidence-weighted overall scores using role-type weights from `tools/assessment_weights.py`; must-pass gate failures cap the overall score.

### Human approval gate
All external actions (outreach, data export) must pass through `request_human_approval`. The system **never sends messages autonomously**. Outreach drafts are created with `create_outreach_draft` and blocked until a human approves via the database.

## Testing Specification

The project's primary acceptance testing is through **end-to-end full-pipeline runs**. The Python `tests/integration_test.py` script is an MCP/database smoke test, not a substitute for a complete sourcing run through the skill pipeline.

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
4. oculai_checkpoint_plan (persists the Plan + Task DAG)
5. Launch Source Researchers in parallel with iterative think-search
6. Record iterations and terminology discoveries via oculai_record_iteration / oculai_broadcast_discovery
7. Launch Query Optimizer when results are noisy, skewed, or sparse
8. oculai_upsert_candidate or oculai_upsert_candidates_batch
9. Launch Identity Resolver
10. Launch Profile Enrichers
11. Launch Fit Evaluators
12. Launch Quality Auditor and apply any approved audit adjustments
13. oculai_export_report (format=html)
14. (optional) Launch Outreach Strategist and request human approval
15. Present results
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

## Electron Desktop App Architecture

The `oculai-desktop/` directory is a standalone Electron application that packages the entire Oculai pipeline into a desktop GUI.

### Startup Lifecycle
1. `Electron main process` creates a BrowserWindow
2. `PostgresManager` initializes an embedded PostgreSQL instance (port 15432)
3. `ToolBridge` spawns the Python JSONL server (`jsonl_server.py`) as a child process
4. `Pi AgentSession` is created via `@earendil-works/pi-coding-agent` SDK
5. All 41 Oculai tools are registered as Pi extension tools — each delegates to the Python sidecar via ToolBridge
6. IPC handlers are registered for renderer↔main communication
7. Renderer loads (Vite dev server in dev, bundled HTML in production)

### Key Main-Process Modules
| Module | Role |
|---|---|
| `postgres-manager.ts` | Manages embedded PostgreSQL lifecycle (init, start, stop). Uses `pg_ctl` to manage a local data directory under the app's userData path. |
| `tool-bridge.ts` | Spawns and communicates with the Python JSONL server via `child_process.spawn`. Sends JSONL requests, parses JSONL responses. |
| `pi-session.ts` | Creates and manages a Pi `AgentSession` with Oculai tools registered as extension tools. Subscribes to agent events (thinking, text, tool calls) and forwards them to the renderer via `state-bus.ts`. |
| `state-bus.ts` | Event emitter that decouples main-process subsystems and bridges to IPC for the renderer. |
| `ipc-handlers.ts` | Registers all `ipcMain.handle` listeners for renderer-initiated actions (start run, get state, export report, etc.). |
| `settings-store.ts` | Persistent settings via `electron-store` (API keys, LLM provider/model, thinking level). |

### Renderer (React)
- 7 tabs: Dashboard, Pipeline, Candidates, Evidence, Report, Logs, Settings
- State management via Zustand (`store/index.ts`)
- Real-time streaming of agent thinking/messages/tool calls via IPC events
- Charts via Recharts, UI components with Tailwind CSS

### IPC Channel Design
Typed IPC channels in `src/shared/ipc-channels.ts` split into:
- **Run lifecycle**: `run:create`, `run:state`, `run:error`
- **Pipeline streaming**: `pipeline:update`, `task:updated`, `iteration:recorded`
- **Agent streaming**: `agent:thinking`, `agent:message`, `agent:tool_call`, `agent:tool_result`
- **System**: `system:status`, `system:log`
- **Actions** (renderer→main): `action:startRun`, `action:resumeRun`, `action:abortRun`, `action:exportReport`

### Build & Package
- `vite build` for renderer, `tsc -p tsconfig.main.json` for main process
- `electron-builder` produces NSIS installer (Windows), DMG (macOS), AppImage (Linux)
- Schema SQL, agent prompts, skill definition, and slash commands are bundled as `extraResources`

### Pi Runtime
`pi-windows-x64/` contains the Pi CLI runtime binary (`pi.exe`, ~121MB) and SDK examples. The Electron app's `@earendil-works/pi-ai` and `@earendil-works/pi-coding-agent` npm packages wrap this runtime. The runtime handles LLM communication, context management, tool execution, and session persistence — Oculai provides the tools and system prompt on top.

> **Note:** `pi.exe` is currently gitignored (not tracked in version control). The npm dependency should download the appropriate runtime automatically. If you need to version the binary in the repo, switch to Git LFS: `git lfs track "pi-windows-x64/pi.exe"` and remove the `pi-windows-x64/` line from `.gitignore`.

## Git LFS & Large File Management

The following large artifacts exist in the repo tree — all are gitignored to prevent accidental commits:

| Artifact | Size | Git Status |
|---|---|---|
| `pi-windows-x64/pi.exe` | ~121 MB | Gitignored (`.gitignore`) |
| `oculai-desktop/dist-electron/` | ~721 MB | Gitignored (`.gitignore`) |
| `oculai-desktop/node_modules/` | ~834 MB | Gitignored (`.gitignore`) |

**Rules:**
- **Never** `git add` these directories — they contain build artifacts, dependencies, and large binaries
- `oculai-desktop/package-lock.json` **is** committed (it pins dependency versions for reproducible builds)
- `dist-electron/` is output from `electron-builder`; it's regenerated on every build, not committed
- If a large file (>100MB) needs to be tracked, use `git lfs track "<pattern>"` before adding it
- To check current LFS tracking: `git lfs track`

**Branch protection:** Merges between `Oculai-Pi` and `master` are prevented via a shared git hook (see `.githooks/pre-merge-commit`).

## Directory Map

| Directory | Purpose |
|---|---|
| `oculai/skills/` | Claude Code skill definition (trigger, protocol, references) |
| `oculai/agents/` | 8 subagent Markdown prompt files |
| `oculai/commands/` | 5 slash command definitions |
| `oculai-db/` | Docker Compose, PostgreSQL config, SQL schema migrations |
| `oculai-mcp/src/oculai_mcp/` | Python MCP server source |
| `oculai-mcp/src/oculai_mcp/db/` | Database access layer (asyncpg, CRUD, retry logic, task iterations, broadcasts, search state, quotas, provenance, lineage) |
| `oculai-mcp/src/oculai_mcp/tools/` | Domain tool implementations (sources, candidates, evidence, evidence tiers, assessment, assessment weights, deep search, deep dive, site crawler, review orchestrator, report, outreach, browser, web search) |
| `oculai-mcp/src/oculai_mcp/sources/` | Source connectors (arXiv, DBLP, GitHub, Semantic Scholar, OpenAlex, ACL Anthology, PMLR, Baidu, DuckDuckGo, homepage, Juejin, Zhihu, CSDN, industry, conference) |
| `oculai-mcp/src/oculai_mcp/utils/` | Utilities (Chinese name extraction, HTML denoising/markdown conversion) |
| `oculai-mcp/src/oculai_mcp/server.py` | FastMCP server — 41 `@mcp.tool` decorated functions |
| `oculai-mcp/src/oculai_mcp/jsonl_server.py` | JSONL stdio bridge for Electron sidecar communication |
| `oculai-mcp/src/oculai_mcp/tool_registry.py` | Flat `TOOL_REGISTRY` dict of all 41 tool handlers (no MCP dependency) |
| `oculai-mcp/tests/` | MCP/database smoke test script |
| `oculai-desktop/` | Electron desktop application (React + TypeScript + Vite + Tailwind) |
| `oculai-desktop/src/main/` | Electron main process (PostgresManager, ToolBridge, Pi session, IPC handlers) |
| `oculai-desktop/src/renderer/` | React UI (Dashboard, Pipeline, Candidates, Evidence, Report, Logs, Settings tabs) |
| `oculai-desktop/resources/` | Bundled schema SQL, agent prompts, skill definition, slash commands |
| `pi-windows-x64/` | Pi CLI runtime binary (`pi.exe`) + TypeScript SDK examples — powers the Electron app's AI agent |
