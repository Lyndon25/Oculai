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
import { app, BrowserWindow, shell, screen } from "electron";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
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
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Backend lifecycle state — prevents races between start and shutdown
let backendState: "stopped" | "starting" | "running" | "stopping" = "stopped";

function createWindow(): void {
  const { workAreaSize } = screen.getPrimaryDisplay();
  const initialWidth = Math.max(1024, Math.min(1400, workAreaSize.width - 48));
  const initialHeight = Math.max(680, Math.min(900, workAreaSize.height - 48));

  mainWindow = new BrowserWindow({
    width: initialWidth,
    height: initialHeight,
    minWidth: 1024,
    minHeight: 680,
    title: "Oculai Desktop",
    titleBarStyle: "hiddenInset",
    frame: process.platform === "darwin" ? false : true,
    webPreferences: {
      preload: join(__dirname, "..", "preload", "index.cjs"),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  });

  stateBus.setWindow(mainWindow);

  mainWindow.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    const levelName = ["verbose", "info", "warning", "error"][level] ?? String(level);
    console.log(`[renderer:${levelName}] ${message} (${sourceId}:${line})`);
  });

  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    console.error(`[renderer:load-failed] ${errorCode} ${errorDescription} ${validatedURL}`);
  });

  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    console.error(`[renderer:gone] ${details.reason} exitCode=${details.exitCode}`);
  });

  mainWindow.webContents.on("did-finish-load", () => {
    mainWindow?.webContents.executeJavaScript(
      "({ title: document.title, rootChildren: document.getElementById('root')?.childElementCount ?? -1, bodyText: document.body.innerText.slice(0, 300) })",
    ).then((snapshot: unknown) => {
      console.log(`[renderer:loaded] ${JSON.stringify(snapshot)}`);
    }).catch((err: unknown) => {
      console.error(`[renderer:snapshot-failed] ${err instanceof Error ? err.message : String(err)}`);
    });
  });

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
  if (backendState !== "stopped") {
    stateBus.emitSystemLog("warn", `startBackend called while state=${backendState}, ignoring`);
    return;
  }
  backendState = "starting";

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

  // 4. IPC handlers are registered during app startup before slow backend work.

  backendState = "running";
  stateBus.emitSystemLog("info", "Oculai Desktop backend ready");
}

async function shutdownBackend(): Promise<void> {
  if (backendState !== "running") {
    stateBus.emitSystemLog("warn", `shutdownBackend called while state=${backendState}, ignoring`);
    return;
  }
  backendState = "stopping";
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

  backendState = "stopped";
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
  registerIpcHandlers(toolBridge, postgresManager);
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
