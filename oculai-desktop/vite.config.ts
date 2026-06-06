import react from "@vitejs/plugin-react";
import { cpSync, existsSync, mkdirSync } from "fs";
import { resolve } from "path";
import { defineConfig, type Plugin } from "vite";

/**
 * Vite plugin that copies resources/ to dist/resources/ during production builds.
 *
 * In development, the Electron main process runs from the project root (cwd)
 * and finds resources/ via the 3rd fallback in findResourceDir().
 * In production, electron-builder copies resources/ via the extraResources
 * config in electron-builder.yml. This plugin ensures resources/ is also
 * available under dist/ for direct "npm start" / "electron ." runs after build.
 */
function copyResourcesPlugin(): Plugin {
  return {
    name: "copy-resources",
    apply: "build",
    writeBundle() {
      const src = resolve(__dirname, "resources");
      const dest = resolve(__dirname, "dist", "resources");

      if (!existsSync(src)) {
        console.warn("[copy-resources] Source resources/ directory not found at:", src);
        return;
      }

      try {
        if (!existsSync(dest)) {
          mkdirSync(dest, { recursive: true });
        }
        cpSync(src, dest, { recursive: true });
        console.log("[copy-resources] Copied resources/ → dist/resources/");
      } catch (err) {
        console.error("[copy-resources] Failed to copy resources:", err);
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), copyResourcesPlugin()],
  root: "src/renderer",
  base: "./",
  build: {
    outDir: "../../dist/renderer",
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      "@shared": resolve(__dirname, "src/shared"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
