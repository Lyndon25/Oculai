import { useStore } from "../../store/index.js";
import {
  Sparkles,
  ArrowRight,
  RotateCcw,
  Calendar,
  Users,
  CheckCircle2,
  ClipboardList,
  Zap,
  Globe,
  FileText,
} from "lucide-react";
import { useState } from "react";
import type React from "react";
import type { StartRunPayload } from "../../../shared/events.js";
import type { RunStatus } from "../../../shared/types.js";
import { EmptyState, HealthDot, LoadingInline, RunStatusBadge, cx } from "../ui/primitives.js";

const ROLE_TEMPLATES = [
  {
    title: "NLP / LLM 研究科学家",
    skills: "NLP, LLM, PyTorch, Transformer, 中文语料",
    jd: `公司背景：一家中国 AI 产品公司，正在建设面向企业知识工作的中文大模型应用。

岗位职责：
- 负责中文 NLP / LLM 训练、微调、评测与应用落地
- 设计检索增强生成、领域适配、自动评测和数据治理方案
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
      <div className="mx-auto max-w-5xl px-8 py-10">
        {/* ─── Hero ─── */}
        <header className="mb-10">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-soft">
              <Sparkles className="h-5 w-5 text-accent" aria-hidden="true" />
            </div>
            <span className="font-display text-[11px] font-semibold uppercase tracking-[0.28em] text-accent">
              Oculai Talent Intelligence
            </span>
          </div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-ink">
            中国候选人优先的
            <br />
            多 Agent 智能寻访
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-ink-secondary">
            粘贴 JD，Pi 自主规划搜索策略，并行调用来源，沉淀证据与评分，生成可交付报告。
          </p>

          {/* Status inline */}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <HealthDot label="数据库" status={systemStatus.db} />
            <HealthDot label="Python" status={systemStatus.python} />
            <HealthDot label="AI 模型" status={systemStatus.llm} />
            {!isReady && (
              <span className="text-xs text-semantic-warning">
                请先在设置中完成配置
              </span>
            )}
          </div>
        </header>

        {/* ─── Main Grid ─── */}
        <div className="grid gap-8 lg:grid-cols-[1fr_18rem]">
          {/* ─── JD Form ─── */}
          <section className="space-y-5">
            <div className="panel p-6">
              <div className="space-y-5">
                <div>
                  <label
                    htmlFor="job-title"
                    className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted"
                  >
                    岗位名称
                  </label>
                  <input
                    id="job-title"
                    type="text"
                    className="input text-[15px]"
                    placeholder="资深 NLP 研究员、平台工程师…"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                  />
                </div>

                <div>
                  <label
                    htmlFor="jd-text"
                    className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted"
                  >
                    Job Description
                  </label>
                  <textarea
                    id="jd-text"
                    className="input min-h-[280px] resize-y font-mono text-[13px] leading-relaxed"
                    placeholder="公司背景 · 职责 · 硬性要求 · 加分项 · 资深度 · 地点偏好…"
                    value={jdText}
                    onChange={(e) => setJdText(e.target.value)}
                  />
                </div>

                <div>
                  <label
                    htmlFor="skills"
                    className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted"
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
              </div>

              {error && (
                <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3" role="alert">
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}

              <div className="mt-6 flex items-center justify-between border-t border-rule pt-5">
                <p className="text-xs leading-5 text-ink-muted">
                  {isReady ? "就绪 — Pi 将自主规划搜索与评估" : "请完成数据库、Python 与模型配置"}
                </p>
                <button
                  type="button"
                  className="btn-primary min-w-[140px]"
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

          {/* ─── Right Rail ─── */}
          <aside className="space-y-4">
            {/* JD Checklist */}
            <div className="panel p-4">
              <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">
                <ClipboardList className="h-3.5 w-3.5" aria-hidden="true" />
                JD 完整度
              </h3>
              <ChecklistItem ok={Boolean(jobTitle.trim())} label="岗位名称" />
              <ChecklistItem ok={jdText.length >= 300} label="JD ≥ 300 字" />
              <ChecklistItem ok={skillCount >= 3} label={`技能 ≥ 3 项（${skillCount}）`} />
              <ChecklistItem ok={hasLocation} label="中国地点/时区" />
            </div>

            {/* Templates */}
            <div className="panel p-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-muted">
                快速模板
              </h3>
              <div className="space-y-1.5">
                {ROLE_TEMPLATES.map((template) => (
                  <button
                    key={template.title}
                    type="button"
                    className="w-full rounded-lg px-3 py-2 text-left text-xs text-ink-secondary transition-colors hover:bg-surface-hover hover:text-ink"
                    onClick={() => applyTemplate(template)}
                  >
                    {template.title}
                  </button>
                ))}
              </div>
            </div>

            {/* Guide — minimal icons */}
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <GuideCard icon={Globe} title="多来源搜索" />
              <GuideCard icon={Zap} title="智能评估" />
              <GuideCard icon={FileText} title="报告交付" />
            </div>
          </aside>
        </div>

        {/* ─── Recent Runs ─── */}
        <section className="mt-10">
          <div className="mb-4 flex items-center gap-2">
            <Calendar className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-ink">最近任务</h2>
            {runs.length > 0 && (
              <span className="text-xs text-ink-muted">({runs.length})</span>
            )}
          </div>

          {runs.length === 0 ? (
            <div className="panel">
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
                  className="panel w-full p-4 text-left transition-colors hover:border-rule-hover disabled:opacity-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1.5 flex items-center gap-2">
                        <h3 className="truncate text-sm font-semibold text-ink">{run.title}</h3>
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
                    <div className="flex shrink-0 items-center gap-1 text-xs font-semibold text-accent">
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

/* ─── Helpers ─── */

function ChecklistItem({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 py-1.5 text-xs">
      <CheckCircle2
        className={cx("h-3.5 w-3.5", ok ? "text-semantic-success" : "text-rule-strong")}
        aria-hidden="true"
      />
      <span className={ok ? "text-ink" : "text-ink-muted"}>{label}</span>
    </div>
  );
}

function GuideCard({
  icon: Icon,
  title,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
}) {
  return (
    <div className="panel flex items-center gap-3 p-4">
      <Icon className="h-4 w-4 text-accent shrink-0" aria-hidden="true" />
      <span className="text-xs font-medium text-ink">{title}</span>
    </div>
  );
}

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
