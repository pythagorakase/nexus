// Generates the Vite lib entry + componentSrcMap from the NEXUS component tree.
//   - lib-entry.tsx: `export *` from every component module (all exports land on
//     window.NexusIris) + `import "@/index.css"` so Tailwind/tokens/fonts are
//     pulled into the extracted stylesheet.
//   - componentSrcMap.json: the ~90 PRIMARY components (one per file) that get
//     hand-authored cards — merged into .design-sync/config.json.
// ts-morph is resolved from the staged converter deps (.ds-sync/node_modules).
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve, relative, basename } from "node:path";
import { execSync } from "node:child_process";

const UI = fileURLToPath(new URL("..", import.meta.url)); // ui/
const SRC = resolve(UI, "client/src");
const require = createRequire(resolve(UI, ".ds-sync/package.json"));
let Project, Node, ts;
try {
  ({ Project, Node, ts } = require("ts-morph"));
} catch {
  console.error(
    "[gen-entry] ts-morph not found under .ds-sync/ — run the design-sync setup first:\n" +
      "  (cd .ds-sync && npm i esbuild ts-morph @types/react)\n" +
      "See .design-sync/NOTES.md.",
  );
  process.exit(1);
}

const files = execSync(
  `find "${SRC}/components" "${SRC}/pages" -type f \\( -name '*.tsx' -o -name '*.jsx' \\)`,
  { encoding: "utf8" },
)
  .split("\n")
  .filter(Boolean)
  .filter((p) => !/\.(test|spec|stories)\./.test(p))
  // pages/dev-orrery/ is the internal /dev/orrery audit dashboard (a separate
  // "design-package port", NOT part of the IRIS customer design system). Keep
  // its heavy viz deps out of the synced bundle. See .design-sync/NOTES.md.
  .filter((p) => !/\/pages\/dev-orrery\//.test(p))
  .sort();

const project = new Project({
  skipAddingFilesFromTsConfig: true,
  compilerOptions: { jsx: ts.JsxEmit.Preserve, allowJs: true, skipLibCheck: true },
});
const isComp = (n) =>
  /^[A-Z][A-Za-z0-9]*$/.test(n) && !n.endsWith("Props") && !/^[A-Z][A-Z0-9_]+$/.test(n);
const pascal = (s) =>
  s.replace(/\.(tsx|jsx)$/, "").split(/[^A-Za-z0-9]/).filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1)).join("");

const srcMap = {};
const entry = ['import "@/index.css";'];
const skipped = [];
for (const f of files) {
  const sf = project.addSourceFileAtPath(f);
  const named = new Set();
  let def = null;
  for (const [name, decls] of sf.getExportedDeclarations()) {
    const real =
      name === "default"
        ? decls.map((d) => d.getName?.()).find((n) => n && n !== "default")
        : name;
    if (!real || !isComp(real)) continue;
    const isComponentDecl = decls.some((d) => {
      if (Node.isFunctionDeclaration(d) || Node.isClassDeclaration(d)) return true;
      if (Node.isVariableDeclaration(d)) {
        const init = d.getInitializer?.();
        if (!init) return false;
        // Allowlist of component-shaped initializers: functions/arrows,
        // forwardRef|memo|cva calls, and `const X = Ns.Root` re-exports. An
        // allowlist (vs excluding known scalar literals) can't silently admit a
        // PascalCase `= {}` / `= true` / `= null` constant as a component.
        return (
          Node.isArrowFunction(init) ||
          Node.isFunctionExpression(init) ||
          Node.isCallExpression(init) ||
          Node.isPropertyAccessExpression(init)
        );
      }
      return false;
    });
    if (!isComponentDecl) continue;
    if (name === "default") def = real;
    else named.add(real);
  }
  const all = [...named, ...(def && !named.has(def) ? [def] : [])];
  if (!all.length) {
    skipped.push(relative(SRC, f));
    continue;
  }
  const rel = "@/" + relative(SRC, f).replace(/\.(tsx|jsx)$/, "");
  entry.push(`export * from ${JSON.stringify(rel)};`);
  // `export *` skips default exports — re-export a default-only component by name.
  if (def && !named.has(def)) entry.push(`export { default as ${def} } from ${JSON.stringify(rel)};`);
  const stem = pascal(basename(f));
  const primary = all.includes(stem) ? stem : def ?? all[0];
  srcMap[primary] = relative(UI, f);
}

// The preview provider (cfg.provider) rides the Vite bundle so window.NexusIris
// exposes it; it imports app contexts, so it can't go through the converter's esbuild.
entry.push('export { DesignThemeRoot } from "../ds-provider";');
// .design-sync/.cache/ is gitignored and absent on a fresh checkout — create it
// before writing the generated entry/srcMap (Codex review).
mkdirSync(resolve(UI, ".design-sync/.cache"), { recursive: true });
writeFileSync(resolve(UI, ".design-sync/.cache/lib-entry.tsx"), entry.join("\n") + "\n");
writeFileSync(
  resolve(UI, ".design-sync/.cache/componentSrcMap.json"),
  JSON.stringify(srcMap, null, 2) + "\n",
);
console.log(`entry: ${entry.length - 1} component files exported`);
console.log(`componentSrcMap: ${Object.keys(srcMap).length} primary components`);
console.log(`skipped (no component export): ${skipped.length}${skipped.length ? " — " + skipped.join(", ") : ""}`);
