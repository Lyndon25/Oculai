import { useStore } from "../../store/index.js";
import { useState, useEffect } from "react";
import { X, Key, Database, ToggleLeft, Sliders } from "lucide-react";

type SettingsTab = "llm" | "api-keys" | "database" | "sources" | "advanced";

export function SettingsView() {
  const setSettingsOpen = useStore((s) => s.setSettingsOpen);
  const [activeTab, setActiveTab] = useState<SettingsTab>("llm");
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({
    anthropic: "",
    openai: "",
    github: "",
    semantic_scholar: "",
    baidu: "",
    tavily: "",
    exa: "",
  });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    window.oculai.getSettings().then((s) => setSettings(s as Record<string, unknown>));
  }, []);

  const handleSave = async () => {
    // Save general settings
    await window.oculai.setSettings(settings);

    // Save API keys (one by one for security)
    for (const [provider, key] of Object.entries(apiKeys)) {
      if (key) {
        await window.oculai.setSettings({ [`apiKey_${provider}`]: key });
      }
    }

    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const updateSetting = (key: string, value: unknown) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const TABS: { id: SettingsTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: "llm", label: "LLM", icon: Key },
    { id: "api-keys", label: "API Keys", icon: Key },
    { id: "database", label: "Database", icon: Database },
    { id: "sources", label: "Sources", icon: ToggleLeft },
    { id: "advanced", label: "Advanced", icon: Sliders },
  ];

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-800 rounded-xl w-[640px] max-h-[80vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-gray-200">Settings</h2>
          <button
            className="btn-ghost p-1 rounded-md"
            onClick={() => setSettingsOpen(false)}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Tab sidebar */}
          <div className="w-40 border-r border-gray-800 p-2 space-y-1">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                    activeTab === tab.id
                      ? "bg-blue-600/20 text-blue-300"
                      : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div className="flex-1 p-6 overflow-y-auto">
            {activeTab === "llm" && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-gray-300">LLM Configuration</h3>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Provider</label>
                  <select
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
                  <label className="block text-xs text-gray-500 mb-1">Model</label>
                  <input
                    type="text"
                    className="input"
                    value={(settings.llmModel as string) || "claude-sonnet-4-20250514"}
                    onChange={(e) => updateSetting("llmModel", e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Thinking Level</label>
                  <select
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
              </div>
            )}

            {activeTab === "api-keys" && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-gray-300">API Keys</h3>
                <p className="text-xs text-gray-500">
                  Keys are encrypted and stored securely using the system keychain.
                </p>
                {Object.entries(apiKeys).map(([provider, value]) => (
                  <div key={provider}>
                    <label className="block text-xs text-gray-500 mb-1 capitalize">
                      {provider.replace(/_/g, " ")}
                    </label>
                    <input
                      type="password"
                      className="input"
                      placeholder="••••••••"
                      value={value}
                      onChange={(e) =>
                        setApiKeys((prev) => ({ ...prev, [provider]: e.target.value }))
                      }
                    />
                  </div>
                ))}
              </div>
            )}

            {activeTab === "database" && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-gray-300">Database Configuration</h3>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Port</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="Auto-assign (0)"
                    value={(settings.dbPort as number) || 0}
                    onChange={(e) => updateSetting("dbPort", parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">Auto-start on launch</span>
                  <button
                    className={`w-10 h-5 rounded-full transition-colors ${
                      settings.dbAutoStart !== false ? "bg-blue-600" : "bg-gray-700"
                    }`}
                    onClick={() => updateSetting("dbAutoStart", !settings.dbAutoStart)}
                  >
                    <div
                      className={`w-4 h-4 rounded-full bg-white transition-transform ${
                        settings.dbAutoStart !== false ? "translate-x-5" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                </div>
              </div>
            )}

            {activeTab === "sources" && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-gray-300">Source Toggles</h3>
                <p className="text-xs text-gray-500">
                  Enable or disable individual data sources.
                </p>
                {[
                  "arxiv",
                  "dblp",
                  "github",
                  "semantic_scholar",
                  "openalex",
                  "industry",
                  "acl_anthology",
                  "pmlr",
                  "conference",
                  "baidu_scholar",
                  "baidu",
                  "personal_homepage",
                  "juejin",
                  "zhihu",
                  "csdn",
                  "duckduckgo",
                ].map((source) => (
                  <div key={source} className="flex items-center justify-between">
                    <span className="text-xs text-gray-400 capitalize">
                      {source.replace(/_/g, " ")}
                    </span>
                    <button
                      className={`w-10 h-5 rounded-full transition-colors ${
                        (settings as Record<string, boolean>)[`source_enable_${source}`] !== false
                          ? "bg-blue-600"
                          : "bg-gray-700"
                      }`}
                      onClick={() =>
                        updateSetting(
                          `source_enable_${source}`,
                          !(settings as Record<string, boolean>)[`source_enable_${source}`],
                        )
                      }
                    >
                      <div
                        className={`w-4 h-4 rounded-full bg-white transition-transform ${
                          (settings as Record<string, boolean>)[`source_enable_${source}`] !== false
                            ? "translate-x-5"
                            : "translate-x-0.5"
                        }`}
                      />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {activeTab === "advanced" && (
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-gray-300">Advanced Settings</h3>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Max Iterations</label>
                  <input
                    type="number"
                    className="input"
                    value={(settings.maxIterations as number) || 50}
                    onChange={(e) => updateSetting("maxIterations", parseInt(e.target.value) || 50)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Token Budget</label>
                  <input
                    type="number"
                    className="input"
                    value={(settings.tokenBudget as number) || 500000}
                    onChange={(e) => updateSetting("tokenBudget", parseInt(e.target.value) || 500000)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Subagent Concurrency</label>
                  <input
                    type="number"
                    className="input"
                    min={1}
                    max={8}
                    value={(settings.concurrency as number) || 4}
                    onChange={(e) => updateSetting("concurrency", parseInt(e.target.value) || 4)}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-800">
          {saved && <span className="text-xs text-green-400">Settings saved!</span>}
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <button className="btn-secondary" onClick={() => setSettingsOpen(false)}>
              Cancel
            </button>
            <button className="btn-primary" onClick={handleSave}>
              Save Changes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
