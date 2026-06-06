/**
 * Tool Bridge — spawns the Python JSONL sidecar and provides a typed
 * callTool() interface for Pi extension tools.
 *
 * Protocol: stdin/stdout JSONL (one JSON object per line)
 *   → {"id":"req-1","method":"oculai_create_run","params":{...}}
 *   ← {"id":"req-1","ok":true,"result":{...}}
 *   ← {"id":"req-1","ok":false,"error":{"code":"...","message":"..."}}
 *
 * System messages on stderr: {"type":"ready","tools":41,"pid":12345}
 */
import { ChildProcess, spawn } from "child_process";
import { createInterface, Interface } from "readline";
import { stateBus } from "./state-bus.js";

export interface ToolResponse {
  ok: boolean;
  result?: Record<string, unknown>;
  error?: { code: string; message: string; traceback?: string };
}

interface PendingRequest {
  resolve: (value: ToolResponse) => void;
  reject: (reason: Error) => void;
  timer: NodeJS.Timeout;
}

const DEFAULT_TIMEOUT_MS = 120_000; // 2 minutes
const SHUTDOWN_TIMEOUT_MS = 10_000;

export class ToolBridge {
  private process: ChildProcess | null = null;
  private pending = new Map<string, PendingRequest>();
  private reqCounter = 0;
  private rl: Interface | null = null;
  private ready = false;
  private shutdownPromise: Promise<void> | null = null;

  /**
   * Start the Python JSONL server process.
   * @param pythonCmd — path to python or PyInstaller executable
   * @param serverModule — path or module name of jsonl_server.py
   */
  async start(pythonCmd = "python", serverModule?: string): Promise<void> {
    if (this.process) return;

    const args = serverModule
      ? [serverModule]
      : ["-m", "oculai_mcp.jsonl_server"];

    stateBus.emitSystemLog("info", `Starting Python sidecar: ${pythonCmd} ${args.join(" ")}`);

    this.process = spawn(pythonCmd, args, {
      stdio: ["pipe", "pipe", "pipe"],
      shell: false,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    // Parse stdout — JSONL tool responses
    this.rl = createInterface({ input: this.process.stdout! });
    this.rl.on("line", (line: string) => {
      if (!line.trim()) return;
      try {
        const msg = JSON.parse(line);
        const reqId = msg.id;
        if (reqId && this.pending.has(reqId)) {
          const { resolve, timer } = this.pending.get(reqId)!;
          clearTimeout(timer);
          this.pending.delete(reqId);
          resolve(msg as ToolResponse);
        }
      } catch {
        // Non-JSON stdout is ignored
      }
    });

    // Parse stderr — system messages (JSONL)
    const errRl = createInterface({ input: this.process.stderr! });
    errRl.on("line", (line: string) => {
      if (!line.trim()) return;
      try {
        const msg = JSON.parse(line);
        if (msg.type === "ready") {
          this.ready = true;
          stateBus.emitSystemLog("info", `Python sidecar ready: ${msg.tools} tools, pid ${msg.pid}`);
        } else if (msg.type === "shutdown") {
          stateBus.emitSystemLog("info", `Python sidecar shutdown: ${msg.reason}`);
          this.ready = false;
        }
      } catch {
        // Non-JSON stderr → system log
        stateBus.emitSystemLog("debug", `[python] ${line}`);
      }
    });

    this.process.on("error", (err) => {
      stateBus.emitSystemLog("error", `Python sidecar error: ${err.message}`);
      this.ready = false;
    });

    this.process.on("close", (code) => {
      stateBus.emitSystemLog("info", `Python sidecar exited with code ${code}`);
      this.ready = false;
      // Reject all pending requests
      for (const [id, { reject, timer }] of this.pending) {
        clearTimeout(timer);
        reject(new Error(`Python sidecar exited (code ${code})`));
        this.pending.delete(id);
      }
    });

    // Wait for ready signal
    await this.waitForReady(15000);
  }

  private waitForReady(timeoutMs: number): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ready) return resolve();
      const start = Date.now();
      const interval = setInterval(() => {
        if (this.ready) {
          clearInterval(interval);
          resolve();
        } else if (Date.now() - start > timeoutMs) {
          clearInterval(interval);
          reject(new Error("Python sidecar did not become ready within timeout"));
        }
      }, 100);
    });
  }

  /** Call a tool by name with parameters. Returns the tool's result dict. */
  async callTool(
    method: string,
    params: Record<string, unknown> = {},
    timeoutMs = DEFAULT_TIMEOUT_MS,
  ): Promise<Record<string, unknown>> {
    if (!this.process || !this.ready) {
      throw new Error("Python sidecar not running");
    }

    const id = `req-${++this.reqCounter}`;
    const request = JSON.stringify({ id, method, params });

    const response = await new Promise<ToolResponse>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Tool call '${method}' timed out after ${timeoutMs}ms`));
      }, timeoutMs);

      this.pending.set(id, { resolve, reject, timer });
      this.process!.stdin!.write(request + "\n");
    });

    if (!response.ok) {
      const err = response.error || { code: "UNKNOWN", message: "Unknown error" };
      throw new Error(`Tool '${method}' failed: [${err.code}] ${err.message}`);
    }

    return response.result || {};
  }

  /** Check if the sidecar is running and ready. */
  isReady(): boolean {
    return this.ready;
  }

  /** Gracefully shut down the Python process. */
  async stop(): Promise<void> {
    if (!this.process) return;
    if (this.shutdownPromise) return this.shutdownPromise;

    this.shutdownPromise = new Promise<void>((resolve) => {
      const closeTimeout = setTimeout(() => {
        if (this.process && !this.process.killed) {
          this.process.kill("SIGKILL");
        }
        resolve();
      }, SHUTDOWN_TIMEOUT_MS);

      this.process!.on("close", () => {
        clearTimeout(closeTimeout);
        resolve();
      });

      // Send EOF to stdin to trigger graceful shutdown
      if (this.process!.stdin) {
        this.process!.stdin.end();
      }
    });

    return this.shutdownPromise;
  }
}
