/**
 * PostgreSQL Manager — manages an embedded PostgreSQL 16 + pgvector instance.
 *
 * Uses pg_ctl for lifecycle management. On first launch, initializes a data
 * directory and runs schema migration SQL files.
 */
import { app } from "electron";
import { ChildProcess, execFile, spawn } from "child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync } from "fs";
import { join } from "path";
import { stateBus } from "./state-bus.js";
import { getSettingsStore } from "./settings-store.js";

export interface PostgresConfig {
  port: number;
  host: string;
  user: string;
  password: string;
  database: string;
}

export class PostgresManager {
  private process: ChildProcess | null = null;
  private dataDir: string;
  private binDir: string;
  private config: PostgresConfig = {
    port: 0,
    host: "localhost",
    user: "oculai",
    password: "oculai_dev",
    database: "oculai",
  };

  constructor() {
    const userData = app.getPath("userData");
    this.dataDir = join(userData, "postgres", "data");
    this.binDir = join(userData, "postgres", "bin");
  }

  getConfig(): PostgresConfig {
    return { ...this.config };
  }

  getConnectionString(): string {
    return `postgresql://${this.config.user}:${this.config.password}@${this.config.host}:${this.config.port}/${this.config.database}`;
  }

  /** Full lifecycle: init if needed, start, migrate schema. */
  async initialize(): Promise<void> {
    const settings = getSettingsStore();

    // Determine port
    this.config.port = settings.get("dbPort") || (await this.findFreePort());

    // Ensure directories exist
    if (!existsSync(this.dataDir)) {
      mkdirSync(this.dataDir, { recursive: true });
    }

    // Initialize data directory if needed
    const isNew = !existsSync(join(this.dataDir, "PG_VERSION"));
    if (isNew) {
      stateBus.emitSystemLog("info", "Initializing PostgreSQL data directory...");
      await this.initDB();
    }

    // Start PostgreSQL
    stateBus.emitSystemLog("info", `Starting PostgreSQL on port ${this.config.port}...`);
    await this.start();

    // Run incremental schema migration on every startup
    await this.runSchemaMigration(isNew);
  }

  private async initDB(): Promise<void> {
    return new Promise((resolve, reject) => {
      const proc = spawn(
        this.pgCtlPath(),
        [
          "init",
          "-D", this.dataDir,
          "-o", `--username=${this.config.user} --pwfile=${this.writePwFile()}`,
        ],
        { shell: true, stdio: "pipe" }
      );

      let stderr = "";
      proc.stderr.on("data", (d) => (stderr += d.toString()));

      proc.on("close", (code) => {
        if (code === 0) {
          stateBus.emitSystemLog("info", "PostgreSQL data directory initialized");
          resolve();
        } else {
          reject(new Error(`pg_ctl init failed (code ${code}): ${stderr}`));
        }
      });

      proc.on("error", reject);
    });
  }

  private writePwFile(): string {
    const pwPath = join(this.dataDir, "pgpass.tmp");
    const { writeFileSync, unlinkSync } = require("fs");
    writeFileSync(pwPath, this.config.password, "utf-8");
    // Schedule cleanup after a short delay
    setTimeout(() => {
      try { require("fs").unlinkSync(pwPath); } catch { /* ok */ }
    }, 10000);
    return pwPath;
  }

  private async start(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.process = spawn(
        this.pgCtlPath(),
        [
          "start",
          "-D", this.dataDir,
          "-l", join(this.dataDir, "..", "pg.log"),
          "-o", `-p ${this.config.port}`,
        ],
        { shell: true, stdio: "pipe" }
      );

      let stdout = "";
      this.process.stdout?.on("data", (d) => (stdout += d.toString()));
      let stderr = "";
      this.process.stderr?.on("data", (d) => (stderr += d.toString()));

      const timeout = setTimeout(() => {
        reject(new Error("PostgreSQL start timed out"));
      }, 30000);

      this.process.on("close", (code) => {
        clearTimeout(timeout);
        if (code === 0) {
          stateBus.emitSystemLog("info", `PostgreSQL started on port ${this.config.port}`);
          resolve();
        } else {
          reject(new Error(`pg_ctl start failed (code ${code}): ${stdout} ${stderr}`));
        }
      });

      this.process.on("error", (err) => {
        clearTimeout(timeout);
        reject(err);
      });
    });
  }

  /** Stop PostgreSQL gracefully. */
  async stop(): Promise<void> {
    if (!this.process) return;

    stateBus.emitSystemLog("info", "Stopping PostgreSQL...");

    return new Promise((resolve) => {
      const stopper = spawn(
        this.pgCtlPath(),
        ["stop", "-D", this.dataDir, "-m", "fast"],
        { shell: true, stdio: "pipe" }
      );

      const timeout = setTimeout(() => {
        stopper.kill("SIGKILL");
        resolve();
      }, 15000);

      stopper.on("close", () => {
        clearTimeout(timeout);
        stateBus.emitSystemLog("info", "PostgreSQL stopped");
        resolve();
      });

      stopper.on("error", () => {
        clearTimeout(timeout);
        resolve();
      });
    });
  }

  /** Run incremental schema SQL migration files. Only applies previously-unapplied migrations. */
  private async runSchemaMigration(isNew: boolean): Promise<void> {
    const schemaDir = this.findSchemaDir();
    if (!schemaDir || !existsSync(schemaDir)) {
      stateBus.emitSystemLog("warn", "Schema directory not found, skipping migration");
      return;
    }

    // Find migrations directory (check both schema/ and schema/migrations/)
    const migrationsDir = join(schemaDir, "migrations");
    const migrationsExist = existsSync(migrationsDir);

    // 1. For fresh installs, run baseline schema files first (idempotent CREATE IF NOT EXISTS)
    if (isNew) {
      const baselineFiles = readdirSync(schemaDir)
        .filter((f) => f.endsWith(".sql") && !f.startsWith("postgresql"))
        .sort();

      stateBus.emitSystemLog("info", `Running ${baselineFiles.length} baseline schema files...`);

      for (const file of baselineFiles) {
        // Skip migration files in the schema root (they're in the migrations/ subdir)
        if (file.startsWith("00") && file.includes("migration")) continue;
        const sql = readFileSync(join(schemaDir, file), "utf-8");
        await this.execSQL(sql);
        stateBus.emitSystemLog("debug", `  ✓ ${file}`);
      }
    }

    // 2. Ensure schema_version tracking table exists
    const ensureTracking = `
      CREATE TABLE IF NOT EXISTS schema_version (
        version     TEXT PRIMARY KEY,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        checksum    TEXT,
        description TEXT
      );
    `;
    await this.execSQL(ensureTracking);

    // 3. Run incremental migrations from schema/migrations/
    if (migrationsExist) {
      const migrationFiles = readdirSync(migrationsDir)
        .filter((f) => f.endsWith(".sql"))
        .sort();

      if (migrationFiles.length === 0) {
        stateBus.emitSystemLog("info", "No migration files found in migrations/");
        return;
      }

      // Query already-applied migrations
      const appliedResult = await this.querySQL("SELECT version FROM schema_version");
      const applied = new Set(appliedResult.split("\n").filter(Boolean));

      const pending = migrationFiles.filter((f) => {
        const version = f.replace(/\.sql$/, "");
        return !applied.has(version);
      });

      if (pending.length === 0) {
        stateBus.emitSystemLog("info", `All ${migrationFiles.length} migrations already applied.`);
        return;
      }

      stateBus.emitSystemLog(
        "info",
        `Found ${migrationFiles.length} total, ${pending.length} pending migrations.`
      );

      for (const file of pending) {
        const version = file.replace(/\.sql$/, "");
        const sql = readFileSync(join(migrationsDir, file), "utf-8");
        stateBus.emitSystemLog("debug", `  Applying ${version}...`);

        // Apply migration and record it in a single transaction
        const wrappedSQL = `
          BEGIN;
          ${sql}
          INSERT INTO schema_version (version, description)
          VALUES ('${version}', 'Migration ${version}')
          ON CONFLICT (version) DO UPDATE SET applied_at = now();
          COMMIT;
        `;
        await this.execSQL(wrappedSQL);
        stateBus.emitSystemLog("debug", `  ✓ ${version}`);
      }

      stateBus.emitSystemLog("info", `Applied ${pending.length} migrations.`);
    }
  }

  /** Execute a SQL query and return stdout (for SELECT queries). */
  private async querySQL(sql: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const psql = spawn(
        this.psqlPath(),
        [
          "-h", this.config.host,
          "-p", String(this.config.port),
          "-U", this.config.user,
          "-d", this.config.database,
          "-t", "-A",  // tuples only, unaligned output
          "-c", sql,
        ],
        {
          shell: true,
          stdio: "pipe",
          env: { ...process.env, PGPASSWORD: this.config.password },
        }
      );

      let stdout = "";
      let stderr = "";
      psql.stdout.on("data", (d) => (stdout += d.toString()));
      psql.stderr.on("data", (d) => (stderr += d.toString()));

      psql.on("close", (code) => {
        if (code === 0) {
          resolve(stdout.trim());
        } else {
          reject(new Error(`psql query failed (code ${code}): ${stderr}`));
        }
      });

      psql.on("error", reject);
    });
  }

  /** Execute SQL via psql. */
  private async execSQL(sql: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const psql = spawn(
        this.psqlPath(),
        [
          "-h", this.config.host,
          "-p", String(this.config.port),
          "-U", this.config.user,
          "-d", this.config.database,
          "-c", sql,
        ],
        {
          shell: true,
          stdio: "pipe",
          env: { ...process.env, PGPASSWORD: this.config.password },
        }
      );

      let stderr = "";
      psql.stderr.on("data", (d) => (stderr += d.toString()));

      psql.on("close", (code) => {
        if (code === 0) {
          resolve();
        } else {
          // psql may print notices to stderr — only fail on actual errors
          if (stderr.toLowerCase().includes("error:")) {
            reject(new Error(`psql error: ${stderr}`));
          } else {
            resolve(); // warnings/notices are OK
          }
        }
      });

      psql.on("error", reject);
    });
  }

  /** Check if PostgreSQL is accepting connections. */
  async healthCheck(): Promise<boolean> {
    try {
      await this.execSQL("SELECT 1");
      return true;
    } catch {
      return false;
    }
  }

  private pgCtlPath(): string {
    return join(this.binDir, "pg_ctl");
  }

  private psqlPath(): string {
    return join(this.binDir, "psql");
  }

  private findSchemaDir(): string | null {
    // Check multiple locations for schema files
    const candidates = [
      join(app.getAppPath(), "resources", "schema"),
      join(app.getAppPath(), "..", "resources", "schema"),
      join(process.cwd(), "resources", "schema"),
      // Fallback: relative to project root during development
      join(process.cwd(), "..", "oculai-db", "schema"),
    ];
    for (const c of candidates) {
      if (existsSync(c)) return c;
    }
    return null;
  }

  private async findFreePort(): Promise<number> {
    // Use the default port, or let PostgreSQL choose
    const settings = getSettingsStore();
    const configured = settings.get("dbPort");
    if (configured && configured > 0) return configured;
    return 5433; // Default to 5433 to avoid conflicts with common PG installs
  }
}
