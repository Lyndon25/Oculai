# Oculai — Agent-Native 多智能体人才寻聘系统

Claude Code 为唯一编排中枢、PostgreSQL 为全局异步状态池的 **Agent-Native 人才寻聘系统**。将传统猎头数周工作压缩至分钟级：JD 解析 → 多源搜索 → 语义匹配 → 深度调研 → 评估打分 → 外联策略。

## 核心设计

```
Claude Code（全部决策 / 编排 / 评判）
    ↕ stdio MCP
FastMCP Server（仅确定性函数，无 LLM 调用）
    ↕ asyncpg
PostgreSQL 16 + pgvector（唯一状态源）
```

- **Main Agent 做所有决策**，Python/MCP 层只暴露确定性工具函数
- **Subagents 是 Markdown prompt 文件**，不是 Python class
- **Task DAG 执行模型**：Plan → Task (free-form TEXT type) → TaskDependency，通过 `FOR UPDATE SKIP LOCKED` 实现并发
- **外联动作须经人类审批**，系统绝不自主发送消息

## 快速开始

### 1. 启动数据库

```bash
cd oculai-db
docker compose up -d
```

PostgreSQL 16 + pgvector，schema 自动从 `oculai-db/schema/` 初始化。

### 2. 配置环境变量

```bash
cd oculai-mcp
cp .env.example .env
# 编辑 .env，至少填写数据库连接信息
```

### 3. 安装依赖

```bash
cd oculai-mcp
pip install -e .
```

### 4. 启动 MCP Server

```bash
cd oculai-mcp
fastmcp run src/oculai_mcp/server.py
```

在 Claude Code 中配置 MCP 连接即可使用。

### 5. 开始寻聘

在 Claude Code 中输入 `/oculai-start` 并提供 JD，Main Agent 自动完成全流程。

## 项目结构

```
Oculai/
├── CLAUDE.md                    # Claude Code 项目指南
├── oculai/                      # Claude Code Skill 定义
│   ├── skills/oculai-talent-sourcing/
│   │   ├── SKILL.md             # 主 Skill 提示词（协议、触发条件、工作流）
│   │   └── references/          # 操作模型、数据源目录、评估框架等
│   ├── agents/                  # 7 个 Subagent 提示词
│   │   ├── oculai-search-strategist.md
│   │   ├── oculai-source-researcher.md
│   │   ├── oculai-identity-resolver.md
│   │   ├── oculai-profile-enricher.md
│   │   ├── oculai-fit-evaluator.md
│   │   ├── oculai-outreach-strategist.md
│   │   └── oculai-quality-auditor.md
│   └── commands/                # 5 个斜杠命令
│       ├── oculai-start.md
│       ├── oculai-status.md
│       ├── oculai-resume.md
│       ├── oculai-audit.md
│       └── oculai-draft-outreach.md
├── oculai-db/                   # 数据库基础设施
│   ├── docker-compose.yml
│   ├── postgresql.conf
│   └── schema/                  # 9 个按序迁移 SQL 文件
├── oculai-mcp/                  # Python MCP Server
│   ├── pyproject.toml
│   ├── .env.example
│   └── src/oculai_mcp/
│       ├── server.py            # 26 个 MCP Tools
│       ├── config.py            # pydantic-settings 配置
│       ├── db/                  # 数据库访问层
│       ├── tools/               # 领域工具实现
│       └── sources/             # 数据源连接器
└── tests/                       # 集成测试
```

## 工作流

| 阶段 | Subagent | 职责 |
|---|---|---|
| 0 | Main Agent | 解析 JD、制定搜索策略、构建 Task DAG |
| 1 | Search Strategist | 选择数据源、设计搜索查询（可并行启动） |
| 2 | Source Researcher × N | 并行搜索各数据源、发现候选人 |
| 3 | Identity Resolver | 消歧、合并重复候选人 |
| 4 | Profile Enricher | 补充论文/开源/职业/学术网络证据 |
| 5 | Fit Evaluator | 多维度评分、排序 |
| 6 | Quality Auditor | 独立审核、风险标注 |
| 7 | Outreach Strategist | 生成外联草稿（须人类审批） |

## 数据源

| 类型 | 数据源 | 用途 |
|---|---|---|
| 学术 | arXiv, Semantic Scholar, OpenAlex, DBLP | 论文发现、引用分析、学者画像 |
| 技术 | GitHub | 开源贡献、技术栈、工程能力 |
| 会议 | ACM DL, OpenReview | 顶会论文、审稿记录 |
| 中文 | 百度学术、百度搜索 | 中国候选人覆盖 |
| 主页 | 个人学术主页抓取 | 最新研究、合作网络 |
| 网络 | Tavily / Exa | 通用 Web 搜索补充 |

## MCP 工具清单（26 个）

**Run 生命周期**：`create_run`, `get_run_state`, `checkpoint_plan`, `claim_tasks`, `complete_task`, `fail_task`

**候选人管理**：`upsert_candidate`, `link_identity`, `list_candidates`, `get_candidate`

**证据管理**：`attach_evidence`, `get_evidence`

**评估**：`score_candidate`, `record_assessment`, `get_shortlist`

**数据源**：`list_source_capabilities`, `search_source`, `fetch_source_detail`

**外联**：`create_outreach_draft`, `request_human_approval`, `check_approval_status`, `list_pending_approvals`, `get_outreach_history`

**其他**：`export_report`, `search_web`, `capture_page_evidence`

## 技术栈

- **编排**：Claude Code（唯一决策中枢）
- **MCP 框架**：FastMCP >= 2.0.0
- **数据库**：PostgreSQL 16 + pgvector + pg_trgm
- **数据库驱动**：asyncpg（连接池、指数退避重试、LISTEN/NOTIFY）
- **配置**：pydantic-settings（mtime 缓存热重载）
- **Email API**：SendGrid（唯一外部写操作）
- **Python**：>= 3.11

## 运行测试

```bash
# 确保 PostgreSQL 已启动
cd oculai-db && docker compose up -d

# 运行集成测试
cd oculai-mcp && python tests/integration_test.py
```
