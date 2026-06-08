import { useStore } from "../../store/index.js";
import { useState, useEffect } from "react";
import type React from "react";
import { X, Key, Database, ToggleLeft, Sliders, ShieldCheck } from "lucide-react";
import { Switch, cx } from "../ui/primitives.js";

type SettingsTab = "llm" | "api-keys" | "database" | "sources" | "advanced";

const SOURCE_LABELS: Record<string, { label: string; description: string; chinaFirst?: boolean }> = {
  arxiv: { label: "arXiv", description: "论文预印本，适合科研候选人" },
  dblp: { label: "DBLP", description: "计算机科学发表记录" },
  github: { label: "GitHub", description: "工程能力、开源项目与代码信号" },
  semantic_scholar: { label: "Semantic Scholar", description: "学术影响力与引用数据" },
  openalex: { label: "OpenAlex", description: "开放学术图谱" },
  industry: { label: "Industry", description: "产业工程师搜索封装" },
  acl_anthology: { label: "ACL Anthology", description: "NLP/LLM 论文来源" },
  pmlr: { label: "PMLR", description: "机器学习会议论文" },
  conference: { label: "Conference", description: "会议与赛事公开资料" },
  baidu_scholar: { label: "百度学术", description: "中文学术搜索", chinaFirst: true },
  baidu: { label: "百度", description: "中文 Web 搜索与实名线索", chinaFirst: true },
  personal_homepage: { label: "个人主页", description: "高校/实验室/个人主页证据" },
  juejin: { label: "掘金", description: "中国开发者社区", chinaFirst: true },
  zhihu: { label: "知乎", description: "中文专业问答与个人主页", chinaFirst: true },
  csdn: { label: "CSDN", description: "中文技术博客与工程实践", chinaFirst: true },
  duckduckgo: { label: "DuckDuckGo", description: "通用 Web 搜索补充" },
};

const API_KEY_PROVIDERS = [
  { id: "anthropic", label: "Anthropic / Claude", description: "驱动 Pi 编码代理与多 Agent 推理" },
  { id: "openai", label: "OpenAI", description: "可选 LLM Provider" },
  { id: "deepseek", label: "DeepSeek", description: "可选中文/推理模型 Provider" },
  { id: "zhipu", label: "智谱 GLM", description: "可选国产模型 Provider" },
  { id: "github", label: "GitHub Token", description: "提升 GitHub / industry 来源限额" },
  { id: "semantic_scholar", label: "Semantic Scholar", description: "提升 Semantic Scholar 请求限额" },
  { id: "baidu", label: "百度 Qianfan", description: "百度 AI Search / Scholar Bearer Token" },
  { id: "tavily", label: "Tavily", description: "Web search 工具" },
  { id: "exa", label: "Exa", description: "Web search 工具" },
];

export function SettingsView() {
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const [activeTab, setActiveTab] = useState<SettingsTab>("llm");
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    window.oculai.getSettings().then((s) => setSettings(s as Record<string, unknown>));
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSettingsOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setSettingsOpen]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const { apiKeyStatus: _apiKeyStatus, ...settingsToSave } = settings;
      await window.oculai.setSettings(settingsToSave);

      for (const [provider, key] of Object.entries(apiKeys)) {
        if (key.trim()) {
          await window.oculai.setApiKey(provider, key.trim());
        }
      }

      const refreshed = await window.oculai.getSettings();
      setSettings(refreshed as Record<string, unknown>);
      setApiKeys({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = (key: string, value: unknown) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const updateSource = (source: string, enabled: boolean) => {
    const current = (settings.enabledSources as Record<string, boolean> | undefined) ?? {};
    updateSetting("enabledSources", { ...current, [source]: enabled });
  };

  const enabledSources = (settings.enabledSources as Record<string, boolean> | undefined) ?? {};
  const apiKeyStatus = (settings.apiKeyStatus as Record<string, boolean> | undefined) ?? {};

  const TABS: { id: SettingsTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: "llm", label: "模型", icon: Key },
    { id: "api-keys", label: "密钥", icon: ShieldCheck },
    { id: "database", label: "数据库", icon: Database },
    { id: "sources", label: "来源", icon: ToggleLeft },
    { id: "advanced", label: "高级", icon: Sliders },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm">
      <div
        className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-rule bg-surface shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-rule px-6 py-4">
          <div>
            <h2 id="settings-title" className="font-display text-lg font-semibold text-ink">设置</h2>
            <p className="mt-0.5 text-xs text-ink-muted">配置模型、来源与运行参数</p>
          </div>
          <button
            className="btn-ghost min-h-0 p-2"
            onClick={() => setSettingsOpen(false)}
            aria-label="关闭"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* Tab sidebar */}
          <div className="w-40 shrink-0 border-r border-rule p-2">
            <div className="space-y-0.5" role="tablist" aria-label="设置分类">
              {TABS.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={cx(
                      "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-all duration-150",
                      activeTab === tab.id
                        ? "bg-accent-soft text-accent font-semibold"
                        : "text-ink-secondary hover:bg-surface-hover hover:text-ink",
                    )}
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                    {tab.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tab content */}
          <div className="min-w-0 flex-1 overflow-y-auto p-6">
            {activeTab === "llm" && (
              <section className="space-y-5" aria-label="模型配置">
                <div>
                  <h3 className="text-sm font-semibold text-ink">LLM 配置</h3>
                  <p className="mt-1 text-xs leading-5 text-ink-muted">
                    Pi Agent 通过这里的 Provider 和 Model 启动。
                  </p>
                </div>
                <div>
                  <label htmlFor="llm-provider" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted">Provider</label>
                  <select
                    id="llm-provider"
                    className="input"
                    value={(settings.llmProvider as string) || "anthropic"}
                    onChange={(e) => updateSetting("llmProvider", e.target.value)}
                  >
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="openai">OpenAI (GPT)</option>
                    <option value="deepseek">DeepSeek</option>
                    <option value="zhipu">Zhipu AI (GLM)</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="llm-model" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted">Model</label>
                  <input
                    id="llm-model"
                    type="text"
                    className="input font-mono"
                    value={(settings.llmModel as string) || "claude-sonnet-4-20250514"}
                    onChange={(e) => updateSetting("llmModel", e.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="thinking-level" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted">Thinking Level</label>
                  <select
                    id="thinking-level"
                    className="input"
                    value={(settings.thinkingLevel as string) || "medium"}
                    onChange={(e) => updateSetting("thinkingLevel", e.target.value)}
                  >
                    <option value="off">Off</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
              </section>
            )}

            {activeTab === "api-keys" && (
              <section className="space-y-5" aria-label="API 密钥">
                <div>
                  <h3 className="text-sm font-semibold text-ink">API Keys</h3>
                  <p className="mt-1 text-xs leading-5 text-ink-muted">留空不覆盖已保存密钥。</p>
                </div>
                <div className="grid gap-3">
                  {API_KEY_PROVIDERS.map((provider) => (
                    <div key={provider.id} className="rounded-xl border border-rule bg-surface-hover/50 p-3.5">
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <div>
                          <label htmlFor={`api-key-${provider.id}`} className="text-xs font-semibold text-ink">
                            {provider.label}
                          </label>
                          <p className="mt-0.5 text-[11px] leading-4 text-ink-muted">{provider.description}</p>
                        </div>
                        <span className={cx(
                          "badge border text-[11px]",
                          apiKeyStatus[provider.id]
                            ? "badge-success"
                            : "badge-neutral",
                        )}>
                          {apiKeyStatus[provider.id] ? "已配置" : "未配置"}
                        </span>
                      </div>
                      <input
                        id={`api-key-${provider.id}`}
                        type="password"
                        className="input"
                        placeholder={apiKeyStatus[provider.id] ? "已保存；输入新值覆盖" : "粘贴 API Key"}
                        autoComplete="off"
                        value={apiKeys[provider.id] ?? ""}
                        onChange={(e) => setApiKeys((prev) => ({ ...prev, [provider.id]: e.target.value }))}
                      />
                    </div>
                  ))}
                </div>
              </section>
            )}

            {activeTab === "database" && (
              <section className="space-y-5" aria-label="数据库配置">
                <div>
                  <h3 className="text-sm font-semibold text-ink">PostgreSQL 配置</h3>
                  <p className="mt-1 text-xs leading-5 text-ink-muted">桌面版内置 PostgreSQL。端口为 0 时自动分配。</p>
                </div>
                <div>
                  <label htmlFor="db-port" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted">Port</label>
                  <input
                    id="db-port"
                    type="number"
                    className="input"
                    placeholder="Auto-assign (0)"
                    value={(settings.dbPort as number) || 0}
                    onChange={(e) => updateSetting("dbPort", parseInt(e.target.value) || 0)}
                  />
                </div>
                <Switch
                  checked={settings.dbAutoStart !== false}
                  onChange={(checked) => updateSetting("dbAutoStart", checked)}
                  label="启动时自动启动数据库"
                  description="关闭后需要手动处理数据库连接。"
                />
              </section>
            )}

            {activeTab === "sources" && (
              <section className="space-y-5" aria-label="来源开关">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-semibold text-ink">数据来源</h3>
                    <p className="mt-1 text-xs leading-5 text-ink-muted">China-First 来源已标注。</p>
                  </div>
                  <span className="badge-accent">
                    {Object.keys(enabledSources).length
                      ? Object.values(enabledSources).filter((v) => v !== false).length
                      : Object.keys(SOURCE_LABELS).length} enabled
                  </span>
                </div>
                <div className="grid gap-2 lg:grid-cols-2">
                  {Object.entries(SOURCE_LABELS).map(([source, meta]) => (
                    <Switch
                      key={source}
                      checked={enabledSources[source] !== false}
                      onChange={(checked) => updateSource(source, checked)}
                      label={`${meta.label}${meta.chinaFirst ? " · 🇨🇳" : ""}`}
                      description={meta.description}
                    />
                  ))}
                </div>
              </section>
            )}

            {activeTab === "advanced" && (
              <section className="space-y-5" aria-label="高级设置">
                <div>
                  <h3 className="text-sm font-semibold text-ink">高级运行参数</h3>
                  <p className="mt-1 text-xs leading-5 text-ink-muted">保存到本地设置；具体生效取决于 Pi 会话。</p>
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <div>
                    <label htmlFor="max-iterations" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted">Max Iterations</label>
                    <input
                      id="max-iterations"
                      type="number"
                      className="input"
                      min={1}
                      value={(settings.maxIterations as number) || 50}
                      onChange={(e) => updateSetting("maxIterations", parseInt(e.target.value) || 50)}
                    />
                  </div>
                  <div>
                    <label htmlFor="token-budget" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted">Token Budget</label>
                    <input
                      id="token-budget"
                      type="number"
                      className="input"
                      min={10000}
                      step={10000}
                      value={(settings.tokenBudget as number) || 500000}
                      onChange={(e) => updateSetting("tokenBudget", parseInt(e.target.value) || 500000)}
                    />
                  </div>
                  <div>
                    <label htmlFor="concurrency" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-ink-muted">Concurrency</label>
                    <input
                      id="concurrency"
                      type="number"
                      className="input"
                      min={1}
                      max={8}
                      value={(settings.concurrency as number) || 4}
                      onChange={(e) => updateSetting("concurrency", parseInt(e.target.value) || 4)}
                    />
                  </div>
                </div>
              </section>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-rule px-6 py-3.5">
          <div className="min-h-5">
            {saved && <span className="text-xs font-medium text-emerald-600">设置已保存</span>}
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-secondary" onClick={() => setSettingsOpen(false)} type="button">
              取消
            </button>
            <button className="btn-primary" onClick={handleSave} disabled={saving} type="button">
              {saving ? "保存中…" : "保存"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
