// Vite library build for design-sync: bundles the NEXUS components into a clean
// ESM dist (React externalized) with one extracted stylesheet, using the app's
// own resolver (so @/ aliases, barrel imports, CSS, and font assets all resolve
// the way the app builds). The converter then consumes this clean dist via
// --entry, never touching raw app source. Run via cfg.buildCmd.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const UI = fileURLToPath(new URL("..", import.meta.url)); // ui/

export default defineConfig({
  configFile: false,
  root: UI,
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(UI, "client/src"),
      "@shared": resolve(UI, "shared"),
    },
  },
  build: {
    outDir: resolve(UI, ".design-sync/.cache/lib-dist"),
    emptyOutDir: true,
    cssCodeSplit: false,
    sourcemap: false,
    lib: {
      entry: resolve(UI, ".design-sync/.cache/lib-entry.tsx"),
      formats: ["es"],
      fileName: () => "index.js",
    },
    rollupOptions: {
      // Keep React (and the pieces the converter's reactShim re-points to
      // window.React) external so the IIFE the converter emits binds to the
      // single window.React instance the preview cards load.
      external: [
        "react",
        "react-dom",
        "react-dom/client",
        "react/jsx-runtime",
        "react/jsx-dev-runtime",
        "react-is",
        "scheduler",
      ],
    },
  },
});
