/**
 * Resource Loader — discovers Oculai Skills and Agents from the filesystem.
 *
 * Skills live in resources/skills/<skill-name>/SKILL.md (directory-per-skill layout).
 * Agents live in resources/agents/*.md (flat layout, one file per agent).
 *
 * Both dev (cwd = oculai-desktop/) and production (extraResources in electron-builder)
 * environments are supported via a 3-path fallback in findResourceDir().
 */
import { createSyntheticSourceInfo } from "@earendil-works/pi-coding-agent";
import { app } from "electron";
import {
  existsSync,
  readFileSync,
  readdirSync,
  statSync,
} from "fs";
import { join, resolve } from "path";
import { stateBus } from "./state-bus.js";

// ── Types ───────────────────────────────────────────────────────────────────

/**
 * A discovered Skill definition, compatible with the Pi SDK ResourceLoader.
 * Matches the shape expected by getSkills() → { skills: SkillDef[], diagnostics }.
 */
export interface SkillDef {
  name: string;
  description: string;
  filePath: string;
  baseDir: string;
  /** Array of reference file paths relative to the skill directory. */
  referenceFiles: string[];
  sourceInfo: ReturnType<typeof createSyntheticSourceInfo>;
  /** Whether the model is disallowed from invoking this skill. Always false for Oculai skills. */
  disableModelInvocation: boolean;
}

/**
 * A discovered Agent file, compatible with the Pi SDK ResourceLoader.
 * Matches the shape expected by getAgentsFiles() → { agentsFiles: AgentFileDef[] }.
 */
export interface AgentFileDef {
  /** Absolute path to the agent .md file. */
  path: string;
  /** Full content of the agent .md file. */
  content: string;
}

// ── Path Resolution ─────────────────────────────────────────────────────────

/**
 * Find the resources/<subdir> directory using a 3-path fallback that works
 * in both development and production environments.
 *
 *  1. app.getAppPath()/resources/<subdir>  — production (ASAR / extraResources)
 *  2. app.getAppPath()/../resources/<subdir> — production unpacked fallback
 *  3. cwd/resources/<subdir>                — development (electron . from project root)
 *
 * Returns the absolute path if found, or null if no candidate exists.
 */
export function findResourceDir(subdir: string): string | null {
  const candidates = [
    join(app.getAppPath(), "resources", subdir),
    join(app.getAppPath(), "..", "resources", subdir),
    join(process.cwd(), "resources", subdir),
  ];
  for (const c of candidates) {
    try {
      const resolved = resolve(c);
      if (existsSync(resolved)) return resolved;
    } catch {
      // Permission error, symlink loop, etc. — skip this candidate
      continue;
    }
  }
  return null;
}

// ── Skill Discovery ─────────────────────────────────────────────────────────

/**
 * Parse a SKILL.md file to extract the skill name and description.
 *
 * - name:  the first # heading (strips the leading "# " prefix)
 * - description: the first non-empty, non-heading text paragraph after the name
 *
 * A "text paragraph" is a contiguous block of non-heading lines delimited by
 * blank lines. We collect lines until we hit a blank line or another heading.
 */
function parseSkillMarkdown(
  content: string,
  filePath: string,
): { name: string; description: string } {
  const lines = content.split(/\r?\n/);

  // Find the first # heading for the name
  let nameIndex = -1;
  let name = "";
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith("# ") && !line.startsWith("## ")) {
      name = line.slice(2).trim();
      nameIndex = i;
      break;
    }
  }

  if (!name) {
    // Fallback: use the filename if no # heading found
    name = filePath.split(/[/\\]/).pop()?.replace(/\.md$/i, "") ?? "Unknown Skill";
  }

  // Find the first non-empty, non-heading text paragraph after the name heading
  let description = "";
  let inParagraph = false;
  const paragraphLines: string[] = [];

  for (let i = nameIndex + 1; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Skip headings
    if (trimmed.startsWith("#")) {
      if (inParagraph) break; // paragraph ended at a heading
      continue;
    }

    if (trimmed === "") {
      if (inParagraph) break; // paragraph ended at a blank line
      continue;
    }

    // Non-empty, non-heading line — start or continue paragraph
    inParagraph = true;
    paragraphLines.push(trimmed);
  }

  description = paragraphLines.join(" ").trim();

  // If no body paragraph found, use a sensible fallback
  if (!description) {
    description = `${name} — Oculai talent sourcing skill`;
  }

  return { name, description };
}

/**
 * Discover all skills from resources/skills/.
 *
 * Each subdirectory under skills/ is a skill. The main content comes from
 * SKILL.md in that directory. Additional .md files in a references/ subdirectory
 * are collected as reference files.
 */
export function discoverOculaiSkills(): SkillDef[] {
  const skillsDir = findResourceDir("skills");
  if (!skillsDir) {
    stateBus.emitSystemLog(
      "warn",
      "Skills directory not found in any of the expected locations. Skills will be empty.",
    );
    return [];
  }

  const skills: SkillDef[] = [];

  let entries: string[];
  try {
    entries = readdirSync(skillsDir);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    stateBus.emitSystemLog("error", `Failed to read skills directory '${skillsDir}': ${msg}`);
    return [];
  }

  for (const entry of entries) {
    const skillDirPath = join(skillsDir, entry);
    try {
      if (!statSync(skillDirPath).isDirectory()) continue;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      stateBus.emitSystemLog("warn", `Failed to stat skill directory '${skillDirPath}': ${msg}`);
      continue;
    }

    // Skill name from directory name (strip oculai- prefix if present, or use as-is)
    // e.g. "oculai-talent-sourcing" → displayed name comes from SKILL.md heading

    const skillMdPath = join(skillDirPath, "SKILL.md");
    if (!existsSync(skillMdPath)) {
      stateBus.emitSystemLog(
        "warn",
        `Skill directory '${entry}' has no SKILL.md — skipping`,
      );
      continue;
    }

    try {
      const content = readFileSync(skillMdPath, "utf-8");
      const { name, description } = parseSkillMarkdown(content, skillMdPath);

      // Collect reference files from references/ subdirectory
      const referenceFiles: string[] = [];
      const refsDir = join(skillDirPath, "references");
      if (existsSync(refsDir)) {
        try {
          const refEntries = readdirSync(refsDir);
          for (const ref of refEntries) {
            if (ref.endsWith(".md")) {
              referenceFiles.push(join(refsDir, ref));
            }
          }
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          stateBus.emitSystemLog(
            "warn",
            `Failed to read references for skill '${entry}': ${msg}`,
          );
        }
      }

      const sourceInfo = createSyntheticSourceInfo(skillMdPath, {
        source: "oculai",
      });

      skills.push({
        name,
        description,
        filePath: skillMdPath,
        baseDir: skillDirPath,
        referenceFiles,
        sourceInfo,
        disableModelInvocation: false,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      stateBus.emitSystemLog(
        "error",
        `Failed to load skill from '${skillMdPath}': ${msg}`,
      );
      // Continue with next skill — don't fail the entire discovery
    }
  }

  stateBus.emitSystemLog(
    "info",
    `Discovered ${skills.length} skill(s): ${skills.map((s) => s.name).join(", ") || "(none)"}`,
  );

  return skills;
}

// ── Agent Discovery ──────────────────────────────────────────────────────────

/**
 * Discover all agent files from resources/agents/.
 *
 * Each .md file in the agents/ directory is an agent definition.
 * Returns an array of { path, content } objects matching the Pi SDK AgentFileDef shape.
 */
export function discoverOculaiAgents(): AgentFileDef[] {
  const agentsDir = findResourceDir("agents");
  if (!agentsDir) {
    stateBus.emitSystemLog(
      "warn",
      "Agents directory not found in any of the expected locations. Agents will be empty.",
    );
    return [];
  }

  const agentsFiles: AgentFileDef[] = [];

  let entries: string[];
  try {
    entries = readdirSync(agentsDir);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    stateBus.emitSystemLog("error", `Failed to read agents directory '${agentsDir}': ${msg}`);
    return [];
  }

  for (const entry of entries) {
    if (!entry.endsWith(".md")) continue;

    const filePath = join(agentsDir, entry);
    try {
      if (!statSync(filePath).isFile()) continue;

      const content = readFileSync(filePath, "utf-8");
      agentsFiles.push({
        path: filePath,
        content,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      stateBus.emitSystemLog(
        "warn",
        `Failed to read agent file '${filePath}': ${msg}. Skipping.`,
      );
      // Continue with next agent — don't fail the entire discovery
    }
  }

  // Sort by filename for deterministic ordering
  agentsFiles.sort((a, b) => a.path.localeCompare(b.path));

  stateBus.emitSystemLog(
    "info",
    `Discovered ${agentsFiles.length} agent file(s): ${agentsFiles.map((a) => a.path.split(/[/\\]/).pop()).join(", ") || "(none)"}`,
  );

  return agentsFiles;
}
