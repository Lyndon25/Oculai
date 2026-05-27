# Oculai — 多智能体人才寻聘系统

Claude Code 为唯一编排中枢、PostgreSQL 为全局异步状态池的 **多Agent智能人才寻聘系统**。将传统猎头数周工作压缩至分钟级：JD 解析 → 多源搜索 → 语义匹配 → 深度调研 → 评估打分 → 外联策略。

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
# 编辑 .env，填写数据库连接信息和你拥有的 API Key
```

**必需**：PostgreSQL 连接信息（默认已填好 Docker 本地配置）。

**强烈建议配置**（决定数据源覆盖广度）：

| 环境变量 | 用途 | 获取方式 | 免费额度 |
|---|---|---|---|
| `GITHUB_TOKEN` | GitHub 搜索（开源贡献、工程能力） | [GitHub Settings](https://github.com/settings/tokens) | 无 Token 时 60 req/h，有 Token 时 5000 req/h |
| `SEMANTIC_SCHOLAR_API_KEY` | 学术论文搜索 | [Semantic Scholar](https://api.semanticscholar.org/api-docs/) | 无 Key 时 100 req/5min，有 Key 时限更高 |
| `OPENALEX_EMAIL` | 学术图谱查询（ polite pool 优待） | 任意有效邮箱，无需注册 | 标准限流 vs 优待限流 |
| `BAIDU_API_KEY` | 百度搜索 + 百度学术（中国候选人） | [百度千帆控制台](https://console.bce.baidu.com/qianfan/) | 100 次/天 |
| `TAVILY_API_KEY` | 通用 Web 搜索（Tavily） | [tavily.com](https://tavily.com) | 1000 次/月 |
| `EXA_API_KEY` | 通用 Web 搜索（Exa） | [exa.ai](https://exa.ai) | 2000 次一次性额度 |

无需 API Key 即可使用：arXiv、DBLP、OpenAlex（基础限流）、百度网页抓取、掘金、知乎、CSDN、个人学术主页抓取。

### 3. 安装依赖

```bash
cd oculai-mcp
pip install -e .
```

### 4. 一键启动（推荐）

只需记住一条命令：

```
/oculai
```

Claude 会自动检测环境状态并执行对应操作：

| 状态 | 行为 |
|---|---|
| **首次使用** | 检查依赖 → 复制 `.env` → 启动数据库 → 安装 Python 包 → 验证 MCP → 询问 JD 开始寻聘 |
| **已初始化但服务未启动** | 启动数据库 → 验证依赖 → 询问 JD 开始寻聘 |
| **全部就绪** | 直接询问 JD 开始寻聘 |

所有步骤自动完成，无需手动敲命令。

### 5. 手动启动（备选）

如需独立控制各组件：

```bash
# 启动数据库
cd oculai-db && docker compose up -d

# 启动 MCP Server
cd oculai-mcp && fastmcp run src/oculai_mcp/server.py
```

或运行独立初始化脚本：

```bash
# Windows PowerShell
.\scripts\setup.ps1

# Unix/Mac
bash scripts/setup.sh
```

## 项目结构

```
Oculai/
├── .claude/
│   └── commands/                # Claude Code Project Commands
│       └── oculai.md            # /oculai — 唯一入口：自动检测状态，init/start/sourcing 三态合一
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
├── scripts/                     # 独立启动脚本
│   ├── setup.ps1                # Windows 一键初始化
│   └── setup.sh                 # Unix/Mac 一键初始化
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

| 类别 | 数据源 | 用途 | 需 API Key |
|---|---|---|---|
| 学术 | arXiv, DBLP, OpenAlex | 论文发现、引用分析、学者画像 | 否（OpenAlex 填邮箱可获更好限流） |
| 学术 | Semantic Scholar | 学术论文语义搜索 | 推荐（限流更高） |
| 学术 | 百度学术（千帆） | 中文学术搜索 | `BAIDU_API_KEY` |
| 学术 | Conference（顶会过滤） | 基于 OpenAlex/DBLP 的 NeurIPS/ICML/CVPR 等顶会筛选 | 否 |
| 技术 | GitHub | 开源贡献、技术栈、工程能力 | `GITHUB_TOKEN`（强烈推荐） |
| 中文社区 | 百度搜索（千帆） | 通用中文搜索 | `BAIDU_API_KEY` |
| 中文社区 | 掘金 | 中文开发者社区用户搜索 | 否 |
| 中文社区 | 知乎 | 中文问答社区人才发现 | 否 |
| 中文社区 | CSDN | 技术博客平台 | 否 |
| 主页 | 个人学术主页 | HTML 抓取，覆盖部分高校域名映射 | 否 |
| 网络搜索 | Tavily / Exa | 通用 Web 搜索补充（MCP 工具） | `TAVILY_API_KEY` 或 `EXA_API_KEY` |

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
- **浏览器抓取**：Playwright（可选，安装后可截屏取证；无安装时回退到 httpx 文本抓取）
- **Python**：>= 3.11

> **安全设计**：系统绝不自主发送外联消息。`create_outreach_draft` 仅生成草稿，必须通过 `request_human_approval` 获得人类审批后方可执行任何外部动作。

## 运行测试

```bash
# 确保 PostgreSQL 已启动
cd oculai-db && docker compose up -d

# 运行集成测试
cd oculai-mcp && python tests/integration_test.py
```
