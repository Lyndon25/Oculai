import { useStore } from "../../store/index.js";
import {
  Sparkles,
  ArrowRight,
  RotateCcw,
  Calendar,
  Users,
  CheckCircle2,
  Zap,
  Globe,
  FileText,
  BookOpen,
  Cpu,
  Bot,
} from "lucide-react";
import { useState } from "react";
import type React from "react";
import type { StartRunPayload } from "../../../shared/events.js";
import { EmptyState, HealthDot, LoadingInline, RunStatusBadge, cx } from "../ui/primitives.js";

const ROLE_TEMPLATES = [
  {
    title: "NLP / LLM 研究科学家",
    skills: "NLP, LLM, PyTorch, Transformer, 中文语料",
    icon: Bot,
    jd: `公司背景：一家中国 AI 产品公司，正在建设面向企业知识工作的中文大模型应用。

岗位职责：
- 负责中文 NLP / LLM 训练、微调、评测与应用落地
- 设计检索增强生成、领域适配、自动评估和数据治理方案
- 与产品、工程团队协作，将研究成果转化为稳定服务

硬性要求：
- 3 年以上 NLP/LLM 研究或工程经验
- 熟悉 Transformer、PyTorch、分布式训练/推理优化
- 有中文语义理解、信息抽取、RAG 或 Agent 项目经验
- 候选人需在中国大陆工作或有明确回国/远程协作可行性

加分项：ACL/EMNLP/NeurIPS/ICLR 论文，开源模型或中文技术社区影响力。

地点偏好：北京、上海、深圳、杭州，或中国时区远程。`,
  },
  {
    title: "资深平台 / SRE 工程师",
    skills: "Kubernetes, Linux, Observability, Go, Python",
    icon: Cpu,
    jd: `公司背景：中国 B2B SaaS 公司，服务大规模企业客户，正在升级多云基础设施。

岗位职责：
- 设计高可用平台、自动化发布、监控告警与容量治理体系
- 建设 Kubernetes / Linux / 网络相关基础设施
- 推动故障复盘、SLO、成本优化和平台工程最佳实践

硬性要求：
- 5 年以上后端、基础设施或 SRE 经验
- 熟悉 Kubernetes、Linux、可观测性、CI/CD 和事故响应
- 能用 Go/Python 编写自动化工具
- 候选人需在中国大陆或有中国团队协作经验

加分项：大型互联网/云厂商经验，开源贡献，技术博客。

地点偏好：上海、杭州、北京、深圳。`,
  },
  {
    title: "机器人感知算法工程师",
    skills: "Computer Vision, SLAM, ROS, Sensor Fusion, C++, Python",
    icon: Zap,
    jd: `公司背景：中国智能制造/机器人公司，正在招聘负责多传感器感知与定位的算法工程师。

岗位职责：
- 研发视觉、激光雷达、IMU 等多传感器融合算法
- 负责 SLAM、目标检测、场景理解与部署优化
- 与硬件、嵌入式、产品团队协作完成量产验证

硬性要求：
- 3 年以上机器人、自动驾驶或工业视觉经验
- 熟悉 C++/Python、ROS、SLAM、深度学习或传统视觉算法
- 有真实机器人/车辆/工业设备部署经验
- 候选人优先中国大陆工作地点

加分项：顶会论文、竞赛经历、开源项目、量产经验。

地点偏好：深圳、上海、苏州、北京。`,
  },
];

export function DashboardView() {
  const systemStatus = useStore((s) => s.systemStatus);
  const runs = useStore((s) => s.runs);
  const setActiveRun = useStore((s) => s.setActiveRun);
  const [jobTitle, setJobTitle] = useState("");
  const [jdText, setJdText] = useState("");
  const [skills, setSkills] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumingRunId, setResumingRunId] = useState<string | null>(null);

  const isReady =
    systemStatus.db === "connected" &&
    systemStatus.python === "ready" &&
    systemStatus.llm === "configured";

  const canStart = Boolean(jobTitle.trim() && jdText.trim() && isReady && !isStarting);
  const skillCount = skills
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean).length;
  const hasLocation = /中国|北京|上海|深圳|杭州|广州|苏州|成都|远程|China/i.test(jdText);

  const handleStart = async () => {
    if (!canStart) return;
    setIsStarting(true);
    setError(null);
    try {
      const payload: StartRunPayload = {
        jobTitle: jobTitle.trim(),
        jdText: jdText.trim(),
        requiredSkills: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      await window.oculai.startRun(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsStarting(false);
    }
  };

  const handleResume = async (runId: string) => {
    setResumingRunId(runId);
    try {
      await window.oculai.resumeRun(runId);
      setActiveRun(runId);
    } catch (err) {
      setError(err instanceof Error ? err.message : `无法恢复任务 ${runId}`);
      setResumingRunId(null);
    }
  };

  const applyTemplate = (template: (typeof ROLE_TEMPLATES)[number]) => {
    setJobTitle(template.title);
    setSkills(template.skills);
    setJdText(template.jd);
    setError(null);
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-10 py-12">
        {/* ─── Hero · Serif Elegance ─── */}
        <header className="mb-12 animate-enter">
          <div className="flex items-center gap-3 mb-5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/8">
              <Sparkles className="h-4.5 w-4.5 text-accent" aria-hidden="true" />
            </div>
            <span className="text-[10px] font-semibold uppercase tracking-[0.25em] text-accent">
              Talent Intelligence
            </span>
          </div>
          <h1 className="font-display text-[2.5rem] leading-[1.15] tracking-tight text-ink">
            中国候选人优先的
            <br />
            <span className="italic text-accent">多 Agent</span> 智能寻访
          </h1>
          <p className="mt-4 max-w-lg text-[14px] leading-6 text-ink-secondary">
            粘贴 JD，Pi 自主规划搜索策略，并行调用来源，沉淀证据与评分，生成可交付报告。
          </p>

          {/* Status chips · Visual */}
          <div className="mt-6 flex flex-wrap items-center gap-2.5">
            <HealthDot label="数据库" status={systemStatus.db} />
            <HealthDot label="Python" status={systemStatus.python} />
            <HealthDot label="AI 模型" status={systemStatus.llm} />
            {!isReady && (
              <span className="text-[12px] text-warning font-medium ml-1">
                请先在设置中完成配置
              </span>
            )}
          </div>
        </header>

        {/* ─── Main Grid ─── */}
        <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
          {/* ─── JD Form · Elevated Card ─── */}
          <section className="space-y-0 animate-enter animate-enter-2">
            <div className="card p-6 space-y-5">
              <div>
                <label
                  htmlFor="job-title"
                  className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted"
                >
                  岗位名称
                </label>
                <input
                  id="job-title"
                  type="text"
                  className="input text-[15px] font-medium"
                  placeholder="资深 NLP 研究员、平台工程师…"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                />
              </div>

              <div>
                <label
                  htmlFor="jd-text"
                  className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted"
                >
                  Job Description
                </label>
                <textarea
                  id="jd-text"
                  className="input min-h-[300px] resize-y font-mono text-[13px] leading-relaxed"
                  placeholder="公司背景 · 职责 · 硬性要求 · 加分项 · 资深度 · 地点偏好…"
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                />
              </div>

              <div>
                <label
                  htmlFor="skills"
                  className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted"
                >
                  技能（逗号分隔）
                </label>
                <input
                  id="skills"
                  type="text"
                  className="input"
                  placeholder="PyTorch, Transformer, NLP, LLM…"
                  value={skills}
                  onChange={(e) => setSkills(e.target.value)}
                />
              </div>

              {error && (
                <div className="rounded-xl bg-error-soft border border-error-muted p-3.5" role="alert">
                  <p className="text-[13px] text-error">{error}</p>
                </div>
              )}

              <div className="flex items-center justify-between border-t border-rule pt-5">
                <p className="text-[12px] leading-5 text-ink-muted">
                  {isReady ? "就绪 — Pi 将自主规划搜索与评估" : "请完成数据库、Python 与模型配置"}
                </p>
                <button
                  type="button"
                  className="btn-primary min-w-[150px]"
                  disabled={!canStart}
                  onClick={handleStart}
                >
                  {isStarting ? (
                    <LoadingInline label="启动中" />
                  ) : (
                    <>
                      开始寻访
                      <ArrowRight className="h-4 w-4" aria-hidden="true" />
                    </>
                  )}
                </button>
              </div>
            </div>
          </section>

          {/* ─── Right Rail · Visual-First ─── */}
          <aside className="space-y-4 animate-enter animate-enter-3">
            {/* JD Checklist · Compact & visual */}
            <div className="card p-4">
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
                JD 完整度
              </h3>
              <div className="space-y-0.5">
                <ChecklistItem ok={Boolean(jobTitle.trim())} label="岗位名称" />
                <ChecklistItem ok={jdText.length >= 300} label={`JD ≥ 300 字（${Math.min(jdText.length, 999)}）`} />
                <ChecklistItem ok={skillCount >= 3} label={`技能 ≥ 3 项（${skillCount}）`} />
                <ChecklistItem ok={hasLocation} label="中国地点/时区" />
              </div>
            </div>

            {/* Templates · Visual cards */}
            <div className="card p-4">
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
                快速模板
              </h3>
              <div className="space-y-1">
                {ROLE_TEMPLATES.map((template) => {
                  const TIcon = template.icon;
                  return (
                    <button
                      key={template.title}
                      type="button"
                      className="w-full rounded-xl px-3 py-2.5 text-left transition-all duration-200 hover:bg-warm-100 group"
                      onClick={() => applyTemplate(template)}
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft group-hover:bg-accent/12 transition-colors">
                          <TIcon className="h-3.5 w-3.5 text-accent" />
                        </div>
                        <span className="text-[12px] font-medium text-ink-secondary group-hover:text-ink transition-colors">
                          {template.title}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Feature cards · Icon-first */}
            <div className="grid gap-2">
              <FeatureCard icon={Globe} label="多来源并行搜索" detail="学术 · 产业 · 中文社区" />
              <FeatureCard icon={BookOpen} label="结构化证据取证" detail="T1 至 T4 证据分级链" />
              <FeatureCard icon={FileText} label="交付级 HTML 报告" detail="评分 · 证据 · 建议" />
            </div>
          </aside>
        </div>

        {/* ─── Recent Runs · Refined ─── */}
        <section className="mt-14 animate-enter animate-enter-4">
          <div className="mb-4 flex items-center gap-2.5">
            <Calendar className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            <h2 className="text-[15px] font-semibold text-ink tracking-tight">最近任务</h2>
            {runs.length > 0 && (
              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] font-medium text-ink-muted">
                {runs.length}
              </span>
            )}
          </div>

          {runs.length === 0 ? (
            <div className="card">
              <EmptyState
                icon={RotateCcw}
                title="暂无历史任务"
                description="完成第一个 JD 后，这里会显示可恢复的寻访记录。"
              />
            </div>
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {runs.slice(0, 10).map((run) => (
                <button
                  key={run.run_id}
                  type="button"
                  onClick={() => handleResume(run.run_id)}
                  disabled={resumingRunId === run.run_id}
                  className="card-hoverable w-full p-4 text-left disabled:opacity-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-2 flex items-center gap-2">
                        <h3 className="truncate text-[14px] font-semibold text-ink tracking-tight">
                          {run.title}
                        </h3>
                        <RunStatusBadge status={run.status} />
                      </div>
                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-muted">
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" aria-hidden="true" />
                          {formatDate(run.created_at)}
                        </span>
                        {run.candidate_count !== undefined && run.candidate_count > 0 && (
                          <span className="flex items-center gap-1">
                            <Users className="h-3 w-3" aria-hidden="true" />
                            {run.candidate_count} 人
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1 text-[12px] font-semibold text-accent">
                      {resumingRunId === run.run_id ? "…" : "恢复"}
                      <ArrowRight className="h-3 w-3" aria-hidden="true" />
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

/* ─── Checklist ─── */
function ChecklistItem({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <CheckCircle2
        className={cx(
          "h-3.5 w-3.5 shrink-0 transition-colors duration-200",
          ok ? "text-success" : "text-rule-strong",
        )}
        aria-hidden="true"
      />
      <span className={cx(
        "text-[12px] transition-colors duration-200",
        ok ? "text-ink font-medium" : "text-ink-muted",
      )}>
        {label}
      </span>
    </div>
  );
}

/* ─── Feature Card ─── */
function FeatureCard({
  icon: Icon,
  label,
  detail,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  detail: string;
}) {
  return (
    <div className="card p-3.5 flex items-center gap-3 transition-all duration-200 hover:shadow-md">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-warm-100">
        <Icon className="h-4 w-4 text-warm-700" aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <div className="text-[12px] font-semibold text-ink tracking-tight">{label}</div>
        <div className="text-[11px] text-ink-muted mt-0.5">{detail}</div>
      </div>
    </div>
  );
}

/* ─── Date formatter ─── */
function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "刚刚";
    if (diffMins < 60) return `${diffMins} 分钟前`;
    if (diffHours < 24) return `${diffHours} 小时前`;
    if (diffDays < 7) return `${diffDays} 天前`;

    return d.toLocaleDateString("zh-CN", {
      month: "short",
      day: "numeric",
      year: d.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
    });
  } catch {
    return iso.slice(0, 10);
  }
}
