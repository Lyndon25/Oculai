/**
 * Oculai Desktop — Electron Main Process Entry Point
 *
 * Lifecycle:
 * 1. Create BrowserWindow
 * 2. Start embedded PostgreSQL
 * 3. Start Python sidecar (JSONL server)
 * 4. Initialize Pi AgentSession with Oculai tools
 * 5. Register IPC handlers
 * 6. Ready for user interaction
 */
import { app, BrowserWindow, shell } from "electron";
import { join } from "path";
import { existsSync, mkdirSync } from "fs";
import { PostgresManager } from "./postgres-manager.js";
import { ToolBridge } from "./tool-bridge.js";
import { initPiSession, disposeSession } from "./pi-session.js";
import { registerIpcHandlers } from "./ipc-handlers.js";
import { stateBus } from "./state-bus.js";
import { getSettingsStore } from "./settings-store.js";

// Prevent multiple instances
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

let mainWindow: BrowserWindow | null = null;
const postgresManager = new PostgresManager();
const toolBridge = new ToolBridge();

const isDev = !app.isPackaged;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: "Oculai Desktop",
    titleBarStyle: "hiddenInset",
    frame: process.platform === "darwin" ? false : true,
    webPreferences: {
      preload: join(__dirname, "..", "preload", "index.js"),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  });

  stateBus.setWindow(mainWindow);

  // Load the renderer
  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(join(__dirname, "..", "renderer", "index.html"));
  }

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  // Open external links in browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });
}

async function startBackend(): Promise<void> {
  // 1. Start PostgreSQL
  try {
    stateBus.emitSystemStatus({ db: "connecting", python: "stopped", llm: "unconfigured" });
    await postgresManager.initialize();
    const dbConfig = postgresManager.getConfig();
    stateBus.emitSystemStatus({
      db: "connected",
      python: "stopped",
      llm: "unconfigured",
      dbPort: dbConfig.port,
    });
    stateBus.emitSystemLog("info", `PostgreSQL ready on port ${dbConfig.port}`);

    // Set DB env for Python sidecar
    process.env.DB_HOST = dbConfig.host;
    process.env.DB_PORT = String(dbConfig.port);
    process.env.DB_NAME = dbConfig.database;
    process.env.DB_USER = dbConfig.user;
    process.env.DB_PASSWORD = dbConfig.password;
  } catch (err) {
    stateBus.emitSystemLog("error", `PostgreSQL failed: ${err}`);
    stateBus.emitSystemStatus({ db: "error", python: "stopped", llm: "unconfigured" });
    // Continue without DB — user can configure later
  }

  // 2. Start Python sidecar
  try {
    stateBus.emitSystemStatus({
      db: "connected",
      python: "starting",
      llm: "unconfigured",
    });

    const pythonCmd = process.platform === "win32" ? "python" : "python3";
    await toolBridge.start(pythonCmd);
    stateBus.emitSystemStatus({
      db: "connected",
      python: "ready",
      llm: "unconfigured",
      pythonPid: process.pid,
    });
  } catch (err) {
    stateBus.emitSystemLog("error", `Python sidecar failed: ${err}`);
    stateBus.emitSystemStatus({ db: "connected", python: "error", llm: "unconfigured" });
    // Continue — user can retry
  }

  // 3. Initialize Pi session (if API keys configured)
  const settings = getSettingsStore();
  const apiKey = settings.getApiKey(settings.get("llmProvider"));
  if (apiKey) {
    try {
      await initPiSession(toolBridge, postgresManager);
      stateBus.emitSystemStatus({
        db: "connected",
        python: "ready",
        llm: "configured",
      });
    } catch (err) {
      stateBus.emitSystemLog("error", `Pi session init failed: ${err}`);
      stateBus.emitSystemStatus({ db: "connected", python: "ready", llm: "error" });
    }
  } else {
    stateBus.emitSystemLog("warn", "No API key configured. Set one in Settings to enable AI agent.");
    stateBus.emitSystemStatus({ db: "connected", python: "ready", llm: "unconfigured" });
  }

  // 4. Register IPC handlers
  registerIpcHandlers(toolBridge);

  stateBus.emitSystemLog("info", "Oculai Desktop backend ready");
}

async function shutdownBackend(): Promise<void> {
  stateBus.emitSystemLog("info", "Shutting down...");

  disposeSession();

  try {
    await toolBridge.stop();
  } catch {
    // Ignore
  }

  try {
    await postgresManager.stop();
  } catch {
    // Ignore
  }

  stateBus.emitSystemLog("info", "Shutdown complete");
}

// ---- App Lifecycle ----

app.whenReady().then(async () => {
  // Ensure user data directory exists
  const userData = app.getPath("userData");
  if (!existsSync(userData)) {
    mkdirSync(userData, { recursive: true });
  }

  createWindow();
  await startBackend();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", async () => {
  await shutdownBackend();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  await shutdownBackend();
});

// Handle second instance
app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});
