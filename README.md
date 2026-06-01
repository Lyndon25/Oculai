# Oculai — 多智能体人才寻聘系统

Claude Code 为唯一编排中枢、PostgreSQL 为全局异步状态池的 **多Agent智能人才寻聘系统**。将传统猎头数周工作压缩至分钟级：JD 解析 → 多源搜索 → 语义匹配 → 深度调研 → 评估打分 → 外联策略。

**核心特性**：7 个专用 Subagent 并行协作，14+ 数据源（学术/技术/中文社区），三层身份去重，9 维度量化评估，人类审批外联，一键 `/oculai` 启动，输出精美 HTML 报告。

## 架构

```
Claude Code（决策 / 编排）
    ↕ stdio MCP
FastMCP Server（仅确定性函数）
    ↕ asyncpg
PostgreSQL 16 + pgvector（唯一状态源）
```

- Main Agent 做所有决策，MCP 层只暴露确定性工具
- Subagents 是 Markdown prompt，不是 Python class
- Task DAG 通过 PostgreSQL `FOR UPDATE SKIP LOCKED` 实现并发
- 外联动作须经人类审批，系统绝不自主发消息

## 快速开始

### 1. 启动数据库

```bash
cd oculai-db && docker compose up -d
```

### 2. 配置环境

```bash
cd oculai-mcp
cp .env.example .env
# 按需填写 API Key
```

| 环境变量 | 用途 | 免费额度 |
|---|---|---|
| `GITHUB_TOKEN` | GitHub 搜索 | 无 Token 60 req/h，有 Token 5000 req/h |
| `SEMANTIC_SCHOLAR_API_KEY` | 学术论文 | 无 Key 100 req/5min |
| `OPENALEX_EMAIL` | 学术图谱 | 填邮箱获更好限流 |
| `BAIDU_API_KEY` | 百度搜索 + 百度学术 | 100 次/天 |
| `TAVILY_API_KEY` / `EXA_API_KEY` | 通用 Web 搜索 | 1000 次/月 / 2000 次一次性 |

无需 API Key：arXiv、DBLP、OpenAlex、百度网页抓取、掘金、知乎、CSDN、个人主页。

### 3. 安装依赖

```bash
cd oculai-mcp && pip install -e .
```

### 4. 启动

推荐：输入 `/oculai`，Claude 自动检测状态并完成初始化。

手动：
```bash
cd oculai-db && docker compose up -d
cd oculai-mcp && fastmcp run src/oculai_mcp/server.py
```

## 项目结构

```
Oculai/
├── oculai/                      # Skill 定义 + Subagent + 命令
│   ├── skills/
│   ├── agents/                  # 7 个 Subagent Markdown
│   └── commands/                # 5 个斜杠命令
├── oculai-db/                   # Docker Compose + PostgreSQL schema
├── oculai-mcp/                  # Python MCP Server
│   └── src/oculai_mcp/
│       ├── server.py            # 26 个 MCP Tools
│       ├── db/                  # 数据库访问层
│       ├── tools/               # 领域工具
│       └── sources/             # 数据源连接器
└── scripts/                     # 一键启动脚本
```

## 工作流

| 阶段 | Subagent | 职责 |
|---|---|---|
| 0 | Main Agent | 解析 JD、制定策略、构建 Task DAG |
| 1 | Search Strategist | 选择数据源、设计搜索查询 |
| 2 | Source Researcher | 并行搜索各数据源 |
| 3 | Identity Resolver | 消歧、合并重复候选人 |
| 4 | Profile Enricher | 补充论文/开源/职业证据 |
| 5 | Fit Evaluator | 多维度评分、排序 |
| 6 | Quality Auditor | 独立审核、风险标注 |
| 7 | Outreach Strategist | 生成外联草稿（须人类审批） |

## 数据源

| 类别 | 数据源 | 需 API Key |
|---|---|---|
| 学术 | arXiv, DBLP, OpenAlex, Semantic Scholar, 百度学术, Conference | Semantic Scholar 推荐；百度学术需 `BAIDU_API_KEY` |
| 技术 | GitHub | `GITHUB_TOKEN` 强烈推荐 |
| 中文社区 | 百度、掘金、知乎、CSDN | 百度需 `BAIDU_API_KEY` |
| 主页 | 个人学术主页 | 否 |
| Web | Tavily / Exa | 对应 API Key |

## MCP 工具（26 个）

- **Run**：`create_run`, `get_run_state`, `checkpoint_plan`, `claim_tasks`, `complete_task`, `fail_task`
- **候选人**：`upsert_candidate`, `link_identity`, `list_candidates`, `get_candidate`
- **证据**：`attach_evidence`, `get_evidence`
- **评估**：`score_candidate`, `record_assessment`, `get_shortlist`
- **数据源**：`list_source_capabilities`, `search_source`, `fetch_source_detail`
- **外联**：`create_outreach_draft`, `request_human_approval`, `check_approval_status`, `list_pending_approvals`, `get_outreach_history`
- **其他**：`export_report`, `search_web`, `capture_page_evidence`

## 技术栈

- **编排**：Claude Code
- **MCP**：FastMCP >= 2.0.0
- **数据库**：PostgreSQL 16 + pgvector + pg_trgm，asyncpg 驱动
- **配置**：pydantic-settings（mtime 热重载）
- **抓取**：Playwright（可选）/ httpx 回退
- **Python**：>= 3.11

> 安全设计：外联草稿必须通过 `request_human_approval` 获得人类审批后方可执行。

## 运行测试

```bash
cd oculai-db && docker compose up -d
cd oculai-mcp && python tests/integration_test.py
```
