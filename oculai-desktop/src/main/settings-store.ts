/**
 * Settings Store — persistent user configuration using electron-store.
 *
 * Stores: LLM provider/model, API keys (encrypted via safeStorage), source toggles,
 * database preferences, and advanced settings.
 */
import { app, safeStorage } from "electron";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";

export interface AppSettings {
  // LLM
  llmProvider: string;
  llmModel: string;
  thinkingLevel: "off" | "low" | "medium" | "high";

  // API keys (stored encrypted)
  apiKeys: Record<string, string>;

  // Source toggles
  enabledSources: Record<string, boolean>;

  // Database
  dbPort: number;
  dbAutoStart: boolean;

  // Advanced
  maxIterations: number;
  tokenBudget: number;
  concurrency: number;
}

const DEFAULT_SETTINGS: AppSettings = {
  llmProvider: "anthropic",
  llmModel: "claude-sonnet-4-20250514",
  thinkingLevel: "medium",

  apiKeys: {},

  enabledSources: {
    arxiv: true,
    dblp: true,
    github: true,
    semantic_scholar: true,
    openalex: true,
    industry: true,
    acl_anthology: true,
    pmlr: true,
    conference: true,
    baidu_scholar: true,
    baidu: true,
    personal_homepage: true,
    juejin: true,
    zhihu: true,
    csdn: true,
    duckduckgo: true,
  },

  dbPort: 0, // 0 = auto-assign
  dbAutoStart: true,

  maxIterations: 50,
  tokenBudget: 500000,
  concurrency: 4,
};

function settingsPath(): string {
  const userData = app.getPath("userData");
  if (!existsSync(userData)) {
    mkdirSync(userData, { recursive: true });
  }
  return join(userData, "oculai-settings.json");
}

export class SettingsStore {
  private settings: AppSettings;

  constructor() {
    this.settings = this.load();
  }

  private load(): AppSettings {
    try {
      const path = settingsPath();
      if (existsSync(path)) {
        const raw = readFileSync(path, "utf-8");
        const parsed = JSON.parse(raw);
        return { ...DEFAULT_SETTINGS, ...parsed };
      }
    } catch {
      // Use defaults on any error
    }
    return { ...DEFAULT_SETTINGS };
  }

  save(): void {
    const toSave = { ...this.settings };
    // Never persist API keys in plaintext
    delete (toSave as Record<string, unknown>).apiKeys;
    writeFileSync(settingsPath(), JSON.stringify(toSave, null, 2), "utf-8");
  }

  getAll(): AppSettings {
    return { ...this.settings };
  }

  get<K extends keyof AppSettings>(key: K): AppSettings[K] {
    return this.settings[key];
  }

  set<K extends keyof AppSettings>(key: K, value: AppSettings[K]): void {
    (this.settings as unknown as Record<string, unknown>)[key] = value;
    this.save();
  }

  // ---- API key management with encryption ----

  setApiKey(provider: string, key: string): void {
    if (safeStorage.isEncryptionAvailable()) {
      const encrypted = safeStorage.encryptString(key);
      this.settings.apiKeys[provider] = encrypted.toString("base64");
    } else {
      // Fallback: store with simple obfuscation (not secure, but better than plaintext)
      this.settings.apiKeys[provider] = Buffer.from(key).toString("base64");
    }
    this.save();
  }

  getApiKey(provider: string): string | null {
    const stored = this.settings.apiKeys[provider];
    if (!stored) return null;
    try {
      if (safeStorage.isEncryptionAvailable()) {
        return safeStorage.decryptString(Buffer.from(stored, "base64"));
      }
      return Buffer.from(stored, "base64").toString("utf-8");
    } catch {
      return null;
    }
  }

  isSourceEnabled(name: string): boolean {
    return this.settings.enabledSources[name] ?? true;
  }
}

let _store: SettingsStore | null = null;

export function getSettingsStore(): SettingsStore {
  if (!_store) {
    _store = new SettingsStore();
  }
  return _store;
}
