# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Oculai is a **multi-Agent collaborative talent sourcing system** for **Chinese company HRs**. The Pi AI agent (embedded via `@earendil-works/pi-coding-agent` SDK) is the orchestrator — it decides search strategy, spawns specialized subagents, evaluates candidates, and produces reports. PostgreSQL is the global async state pool. The Python/MCP layer exposes only deterministic functions — **no LLM calls, no autonomous decisions**.

**Core constraint: Only search for Chinese/China-based candidates.** All sources, queries, and evidence gathering must target Chinese talent (China-First Mandate).

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

**Mode B: Electron Desktop App (Primary)**
```
Oculai Desktop (Electron + React)
    └── Electron Main Process
        ├── embedded PostgreSQL (PostgresManager, port 15432)
        ├── Python sidecar (jsonl_server.py, child_process.spawn)
        │   └── JSONL protocol over stdin/stdout
        └── Pi AgentSession (pi-coding-agent SDK)
            ├── System prompt: role + constraints (~150 lines, src/shared/prompts.ts)
            ├── 41 Oculai tools as extension tools (via createExtensionRuntime)
            └── 8 inline subagent profiles (via ResourceLoader.getAgentsFiles)
```

- Pi decides orchestration dynamically — no fixed 15-step pipeline. It analyzes the JD, spawns subagents in parallel, and adapts based on results.
- 8 subagent types are defined inline in `pi-session.ts` (not separate markdown files):
  Search Strategist, Source Researcher, Query Optimizer, Identity Resolver,
  Profile Enricher, Fit Evaluator, Quality Auditor, Outreach Strategist
- Workflows are DAG-based: Plan → Task (free-form TEXT type) → TaskDependency
- Concurrent task claiming uses PostgreSQL `FOR UPDATE SKIP LOCKED`
- ReAct iteration logs and cross-agent discovery broadcasts are persisted for auditability and resume
- The desktop app bundles schema SQL under `oculai-desktop/resources/schema/`

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

# Dev mode (Vite HMR + Electron via concurrently)
cd oculai-desktop && npm run dev

# Generate Pi extension tool stubs from the Python tool registry
cd oculai-desktop && npm run generate-tools

# Type check (no emit)
cd oculai-desktop && npm run typecheck

# Production build (generate-tools → tsc → vite → electron-builder)
cd oculai-desktop && npm run build

# Launch packaged app (after build)
cd oculai-desktop && npm run start
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

### Utility Scripts
```bash
# Check if schema SQL has drifted from the DB client expectations
python scripts/check_schema_drift.py

# Generate Pi extension tool TypeScript stubs (called by npm run generate-tools)
python scripts/generate_pi_tools.py
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

Run the complete Oculai pipeline (Pi orchestrates dynamically, not a fixed 15-step sequence):

```
1. oculai_create_run — Initialize run with JD
2. oculai_list_source_capabilities — Confirm available sources
3. Pi analyzes JD and designs search strategy (autonomous)
4. oculai_checkpoint_plan — Persist strategy + task DAG
5. Pi spawns Source Researchers in parallel across independent sources
6. oculai_upsert_candidate / oculai_upsert_candidates_batch — Persist candidates
7. oculai_broadcast_discovery — Share terminology across agents
8. Identity Resolver — Merge duplicates, link identities
9. Profile Enrichers in parallel — Deep-dive candidate profiles
10. Fit Evaluators in parallel — Score candidates on dimensions
11. Quality Auditor — Audit shortlist quality, bias, compliance
12. oculai_export_report (format=html) — Generate deliverable
13. (optional) Outreach Strategist — Draft outreach (requires human approval)
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
- Dashboard (JD submission form) + Agent Orchestration Dashboard (real-time agent grid, activity feed)
- Bottom drawer: Candidates, Evidence, Report, Logs tabs
- State management via Zustand (`store/index.ts`)
- Real-time streaming of agent thinking/messages/tool calls/subagent lifecycles via IPC events
- Charts via Recharts, UI components with Tailwind CSS

### IPC Channel Design
Typed IPC channels in `src/shared/ipc-channels.ts` split into:
- **Run lifecycle**: `run:created`, `run:error`
- **Orchestrator**: `orchestrator:phase` — pipeline phase transitions
- **Subagent lifecycle**: `subagent:spawned`, `subagent:progress`, `subagent:completed`
- **Agent streaming**: `agent:thinking`, `agent:message`, `agent:tool_call`, `agent:tool_result`
- **Candidates**: `candidate:upserted` — live candidate discovery
- **System**: `system:status`, `system:log`
- **Actions** (renderer→main): `action:startRun`, `action:resumeRun`, `action:abortRun`, `action:getRunState`, `action:exportReport`, `action:listRuns`, `action:getCandidates`, `action:getCandidateDetail`

### Build & Package
- `vite build` for renderer, `tsc -p tsconfig.main.json` for main process
- `electron-builder` produces NSIS installer (Windows), DMG (macOS), AppImage (Linux)
- Schema SQL is bundled under `resources/schema/`. Subagent profiles are defined inline in `pi-session.ts`.
- **`pi-windows-x64/` is also an `extraResource`** — the pi.exe binary is included in the final installer even though it's gitignored (see `electron-builder.yml` for the full config)
- Installer outputs go to `oculai-desktop/dist-electron/`

### Shared IPC Layer (`oculai-desktop/src/shared/`)
The `src/shared/` directory defines the typed contract between the Electron main process and the React renderer:

| Module | Role |
|---|---|
| `ipc-channels.ts` | Typed IPC channel constants (main↔renderer event names) |
| `types.ts` | Shared TypeScript interfaces (Run, Candidate, SubagentState, ActivityEntry, SystemStatus) |
| `events.ts` | Event payload type definitions (including subagent lifecycle events) |
| `prompts.ts` | System prompt — role definition + constraints (~150 lines) |

The renderer never imports from `src/main/` and vice versa — all cross-process communication goes through the IPC channels defined here.

### System Prompt & Subagent Profiles
The system prompt (`src/shared/prompts.ts`) is a concise ~150-line role definition with constraints (China-First Mandate, evidence tiers, assessment dimensions, source priorities). It no longer prescribes a fixed 15-step workflow — Pi decides the orchestration dynamically.

Subagent profiles are defined inline in `pi-session.ts` via Pi's `ResourceLoader.getAgentsFiles()`. The old `resource-loader.ts` (filesystem-based skill/agent discovery) has been removed. 8 subagent types are defined as concise role descriptions directly in TypeScript.

### Pi Runtime
`pi-windows-x64/` contains the Pi CLI runtime binary (`pi.exe`, ~121MB) and SDK examples. The Electron app's `@earendil-works/pi-ai` and `@earendil-works/pi-coding-agent` npm packages wrap this runtime. The runtime handles LLM communication, context management, tool execution, and session persistence — Oculai provides the tools and system prompt on top.

> **Note:** `pi.exe` is currently gitignored (not tracked in version control). The npm dependency should download the appropriate runtime automatically. If you need to version the binary in the repo, switch to Git LFS: `git lfs track "pi-windows-x64/pi.exe"` and remove the `pi-windows-x64/` line from `.gitignore`.

**Current pin:** `@earendil-works/pi-ai` + `@earendil-works/pi-coding-agent` at `^0.78.1`. Upgrading these is a key maintenance operation:
- Minor bumps (`^0.78.x` → `^0.79.x`) may introduce API changes to `AgentSession`, tool registration, or event subscription
- Always review Pi's release notes before bumping
- The pi.exe binary version is coupled to the npm package version — `npm update` pulls the matching binary

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
| `oculai/skills/` | (deprecated — removed, now inline in `prompts.ts`) |
| `oculai/agents/` | (deprecated — removed, now inline in `pi-session.ts`) |
| `oculai/commands/` | (deprecated — removed, replaced by GUI actions) |
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
| `oculai-desktop/src/shared/` | IPC contract types, channel constants, event payloads |
| `oculai-desktop/src/main/` | Electron main process (PostgresManager, ToolBridge, Pi session, IPC handlers) |
| `oculai-desktop/src/renderer/` | React UI (Dashboard, Pipeline, Candidates, Evidence, Report, Logs, Settings tabs) |
| `oculai-desktop/resources/` | Bundled schema SQL files only |
| `scripts/` | Python utility scripts (schema drift check, Pi tool stubs generation) |
| `pi-windows-x64/` | Pi CLI runtime binary (`pi.exe`) + TypeScript SDK examples — powers the Electron app's AI agent |
