# Oculai Agent-Native 架构调研与初始建议

> 记录时间：2026-05-26  
> 目的：沉淀第一轮上下文阅读后的关键判断，作为后续开发 Oculai 初始版 skill / plugin / MCP 后端的设计依据。

## 1. 当前任务目标

Oculai 的目标不是实现一个传统的固定 Pipeline 程序，而是构建一个能够接入 Claude Code 这类宿主 Agent 的 **Agent-Native 人才寻聘系统**。

核心设想：

- 主 Agent 作为 planner / coordinator / reviewer，负责理解需求、拆解目标、分配任务、汇总结果、动态 replan。
- 多个 subagent 可在不同阶段并行工作，尤其是搜索阶段可以并行探索不同数据源、不同假设、不同候选人发现策略。
- PostgreSQL 作为全局状态池和异步数据流转中心，支持多 Agent 并发读写。
- Python / MCP / 工具层只暴露确定性能力，不隐藏 LLM 决策。
- Skill 的 Markdown 和 system prompt 应给主 Agent 最大自由度，而不是把执行路径写死。

## 2. 已阅读上下文

### 当前项目

- `Oculai-Native/项目概述.md`

该文档定义了最终目标：以 Claude Code 为编排中枢、PostgreSQL 为全局状态中心，实现从 JD 解析到闭环反馈的端到端自动化。

其中最重要的原则是：

> Claude Code 做所有决策；Python 工具层只暴露确定性函数，不调用 LLM API，不做自主决策。

### 早期版本 1：`Oculai-origin`

重点阅读：

- `REQUIREMENTS.md`
- `CLAUDE.md`
- `docs/feishu-export/00-Pipeline设计.md`
- `docs/feishu-export/01-Pipeline执行架构讨论纪要.md`
- `docs/feishu-export/02-数据库与定时任务架构设计.md`
- `docs/final_recommendation.md`
- `oculai-db/schema/*.sql`
- `oculai-skill/src/oculai_skill/tools/*`
- `oculai-skill/src/oculai_skill/sources/base.py`

关键价值：

- 明确强调 Claude Code 是 orchestrator。
- Python 层是 pure tool layer。
- 数据源有自描述能力：`description`、`supported_operations`、`id_field_map`、`get_tool_schema()`、`get_capabilities()`。
- 工具层拆得较细，包含 atomic search、detail fetch、dedupe、matching、evaluation、research、outreach、conflict、lineage、reporting 等。

主要问题：

- 仍残留旧式 pipeline / queue 思维。
- Skill 形态还没有完全转化为 Claude Code 原生 plugin / subagent / MCP 体系。

### 早期版本 2：`Oculai-Phase7`

重点阅读：

- `docs/context-planner-subagent-migration.md`
- `oculai-skill/src/oculai_skill/planner/core.py`
- `oculai-skill/src/oculai_skill/orchestrator/planner_orchestrator.py`
- `oculai-skill/src/oculai_skill/agents/subagents/*`
- `oculai-db/schema/003_tables.sql`
- `oculai-db/schema/003b_supporting_tables.sql`
- `oculai-db/schema/006_functions.sql`
- `oculai-db/schema/007_triggers.sql`
- `oculai-db/schema/009_planner_tables.sql`

关键价值：

- 已经尝试从固定 Phase Pipeline 迁移到 Planner-Subagent 架构。
- 引入了 `Plan`、`Task`、`TaskDependency` 通用 DAG 模型。
- 数据库中的 queue claim、stale release、task dependency、LISTEN/NOTIFY、provenance、conflict、changelog、lineage 等机制值得复用。

主要问题：

- Planner 被写进 Python，并直接调用 Anthropic SDK，形成 Claude Code 外的“第二个大脑”。
- Orchestrator 仍是 tick-based scheduler，主 Agent 自主性不足。
- Subagents 是 Python class，而不是 Claude Code / Agent SDK 层的认知 worker。
- 仍存在 legacy phase leakage，例如 search subagent 写 `phase_1_status='done'` 触发旧队列。
- task type 是封闭枚举，限制主 Agent 自由拆解任务。

## 3. 核心判断

新版 Oculai 不应继承 Phase7 的 Python 内置 Planner，也不应回到固定 Phase 0-6 流水线。

推荐方向：

> **Oculai 应被设计为 Claude Code 原生多 Agent 工作协议，而不是 Python pipeline 程序。**

也就是说：

- Claude Code / 宿主 Agent 是真正的 planner。
- Skill Markdown 是操作宪法，不是数据库手册。
- Subagents 是带有明确角色、输入输出契约和证据标准的认知 worker。
- MCP / Python 工具是安全能力面。
- PostgreSQL 是 durable state pool。
- Python 不应隐藏调用 LLM 做 planner、search strategy、candidate evaluation、outreach judgment。

## 4. 建议的新架构

### 4.1 总体分层

```text
Claude Code Skill / Commands
  -> 激活条件、工作协议、主 Agent 操作规范

Claude Code / Agent SDK Subagents
  -> 搜索策略、数据源研究、身份合并、深度调研、匹配评估、外联策略、质量审核

Oculai MCP / Custom Tools
  -> 安全工具边界：创建任务、写入候选人、记录证据、查询状态、评分、导出报告

Python Backend
  -> 数据源 API、浏览器、embedding、dedupe、queue primitives、idempotency、audit

PostgreSQL
  -> 全局状态、任务 DAG、候选人、证据、冲突、血缘、变更、指标
```

### 4.2 推荐项目形态

初始版建议做成 plugin / skill bundle，而不是单一巨大 Markdown：

```text
oculai/
  skills/
    oculai-talent-sourcing/
      SKILL.md
      references/
        operating-model.md
        source-catalog.md
        db-state-model.md
        evaluation-rubric.md
        evidence-standard.md
        outreach-policy.md
  agents/
    oculai-search-strategist.md
    oculai-source-researcher.md
    oculai-identity-resolver.md
    oculai-profile-enricher.md
    oculai-fit-evaluator.md
    oculai-outreach-strategist.md
    oculai-quality-auditor.md
  commands/
    oculai-start.md
    oculai-resume.md
    oculai-status.md
    oculai-audit.md
    oculai-draft-outreach.md
  mcp/
    oculai-server/
```

### 4.3 主 Agent 职责

主 Agent 应负责：

1. 读取用户目标 / JD。
2. 判断是否需要进入 Oculai 工作协议。
3. 创建或恢复 sourcing run。
4. 将目标拆解为可并行任务。
5. 根据数据源能力自主制定搜索策略。
6. 启动多个 subagents 并行搜索或调研。
7. 汇总 subagent 输出，做去重、证据检查、候选人判断。
8. 根据结果动态 replan。
9. 输出 shortlist、评估矩阵、风险说明、外联草稿。
10. 在任何真实外联或外部系统写入前请求人工确认。

### 4.4 Subagent 初始角色

建议初始版定义 7 类 subagent：

#### Search Strategist

负责把 JD 转换成搜索策略，包括关键词、同义词、领域图谱、会议、标杆公司、实验室、技术生态和排除条件。

#### Source Researcher

可多实例并行运行。每个实例负责一个数据源或一种搜索假设，例如 arXiv、Semantic Scholar、OpenAlex、GitHub、DBLP、Google Scholar、公司/实验室主页、通用 Web。

#### Identity Resolver

负责同名消歧、跨平台身份合并、机构变体归一化、ORCID / GitHub / Scholar / OpenAlex / DBLP 关联。

#### Profile Enricher

负责候选人深度档案，包括论文、引用趋势、开源项目、职业轨迹、合作网络、可触达性、风险信号。

#### Fit Evaluator

负责基于 JD 和证据进行匹配评估，必须输出证据 ID、置信度、不确定性和反例。

#### Outreach Strategist

负责外联策略和草稿，不负责真实发送。

#### Quality Auditor

独立审核候选池质量、证据完整性、身份合并风险、偏见风险、合规风险。

## 5. 数据库设计建议

旧版数据库中值得继承的机制：

- PostgreSQL 作为唯一事实源。
- `FOR UPDATE SKIP LOCKED` 任务认领。
- 乐观锁。
- `LISTEN/NOTIFY`。
- stale task release。
- provenance。
- conflict resolution。
- changelog。
- data lineage。
- recalculation queue。
- source quota。
- browser evidence。
- agent metrics。
- external identity linking。

但新版不建议继续使用固定 `phase_0_status` 到 `phase_7_status` 作为执行主模型。

推荐最小核心表：

```text
SourcingRun / SourcingJob
Plan
Task
TaskDependency
AgentRun
Person
PersonExternalIdentity
CandidateForRun
Evidence
BrowserEvidence
SearchQueryLog
CandidateAssessment
DataConflict
ChangeLog
DataLineage
OutreachDraft
HumanApproval
```

Phase 0-6 可以作为报告视图、状态标签或默认 playbook，但不要作为数据库状态机的硬编码执行路径。

## 6. MCP / Tool 设计建议

工具应暴露领域能力，不暴露裸 SQL。

推荐初始工具：

```text
oculai.create_run
oculai.get_run_state
oculai.checkpoint_plan
oculai.create_tasks
oculai.claim_tasks
oculai.complete_task
oculai.fail_task
oculai.list_source_capabilities
oculai.search_source
oculai.fetch_source_detail
oculai.upsert_candidate
oculai.link_identity
oculai.attach_evidence
oculai.list_candidates
oculai.score_candidate
oculai.record_assessment
oculai.get_shortlist
oculai.create_outreach_draft
oculai.request_human_approval
oculai.export_report
```

工具层必须负责：

- idempotency key；
- transactionality；
- audit log；
- provenance；
- rate limit；
- PII handling；
- retry / failure semantics；
- tenant isolation；
- approval gate。

主 Agent 不应该直接操作底层数据库锁、trigger、raw SQL。

## 7. Skill Markdown 设计原则

`SKILL.md` 应该是短而强的操作协议。

应包含：

- 触发条件。
- 主 Agent 角色定义。
- 状态优先原则：所有 run/task/candidate/evidence 都必须写入工具后端。
- subagent 委派规则。
- 搜索策略自主规划规则。
- evidence-first 输出要求。
- replan 条件。
- 质量审核要求。
- 外联和外部副作用的人类审批要求。
- 不确定性表达规范。

不应包含：

- 完整数据库 schema。
- 大量 SQL。
- 具体 queue lock 细节。
- 巨型评分手册。
- 固定 Phase 执行脚本。
- 隐式假设“Python 会帮你规划”。

详细规则应拆到 `references/`。

## 8. 需要避免的反模式

### 8.1 第二个 Planner

不要在 Python backend 里再次调用 Anthropic 做 plan generation / replan。否则会出现 Claude Code 主 Agent 和 Python Planner 双重决策，难以解释和调试。

### 8.2 固定 8 阶段执行模型

8 阶段适合作为默认思维框架，不适合作为强制执行状态机。不同岗位、不同数据源、不同搜索策略需要不同任务图。

### 8.3 巨型 prompt

Skill prompt 过大，会降低主 Agent 对当前任务的聚焦能力。应使用主 prompt + references 分层。

### 8.4 无约束并行搜索

并行 10 个 Agent 是正确方向，但每个 Agent 必须有明确边界：数据源、假设、目标、输出 schema、证据标准、停止条件。

### 8.5 Subagent 只作为 Python class

Python class 可以做 deterministic worker，但不是认知 subagent。真正的 subagent 应该有自己的 prompt、工具权限和输出契约。

### 8.6 裸数据库工具

不要让主 Agent 常规调用 `execute_sql`。数据库写入必须走领域工具，确保审计、权限、幂等和事务。

## 9. 初始版建议里程碑

### Milestone 1：协议与文档

产出：

- `SKILL.md`
- subagent prompts
- references 文档
- MCP 工具契约草案
- 最小数据库状态模型

目标：先把 Agent 如何工作定义清楚。

### Milestone 2：最小 MCP / Tool 后端

实现：

- run 创建 / 查询；
- task 创建 / 认领 / 完成；
- candidate upsert；
- evidence attach；
- source capability introspection；
- search_source mock / minimal real source；
- report export。

目标：让 Claude Code 主 Agent 可以持久化状态并调度多个 subagents。

### Milestone 3：端到端 dry run

验证一个真实 JD：

1. 主 Agent 创建 run。
2. Search Strategist 生成搜索计划。
3. 多个 Source Researcher 并行搜索。
4. Identity Resolver 合并候选人。
5. Profile Enricher 补充证据。
6. Fit Evaluator 打分。
7. Quality Auditor 审核。
8. 主 Agent 输出 shortlist 和外联草稿。

目标：验证 agent-native 工作流，而不是先追求大规模抓取。

## 10. 总结建议

新版应吸收两个早期版本中最有价值的部分：

- 继承 `Oculai-origin` 的核心原则：Claude Code 决策，Python 工具化。
- 继承旧数据库的强机制：任务队列、锁、证据、冲突、血缘、变更、指标。
- 吸收 `Oculai-Phase7` 的 Task DAG 思路，但不要继承 Python 内置 Planner。

最终目标应是：

> **Claude Code skill / commands 是人机交互控制面；Claude Code subagents 是认知协作者；MCP / Python 是安全工具面；PostgreSQL 是异步状态池。**

这比传统 pipeline 更符合 Agent-Native，也更接近用户对“主 Agent 自主规划、并行 subagent 协作、动态问题解决”的设想。
