// cfg.buildCmd for design-sync (run from the ui/ package root). Four steps:
//   1. regenerate the Vite lib entry + componentSrcMap from the component tree
//   2. vite lib build → clean ESM dist (index.js) + extracted style.css
//   3. tsc declaration pass → real component prop contracts beside the bundle
//   4. rewrite the 20 brand @font-face "/fonts/" urls (absolute app/public paths,
//      unresolvable in the bundle) to paths the converter can resolve from the
//      css dir, so it copies the TTFs into the bundle's fonts/.
// NOTE: re-sync also re-runs gen-entry here, so componentSrcMap.json regenerates
// — but config.json's committed componentSrcMap is static; on a component add,
// re-merge it (see .design-sync/NOTES.md).
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const run = (cmd, args) => execFileSync(cmd, args, { stdio: "inherit" });

run("node", [".design-sync/gen-entry.mjs"]);
run("npx", ["vite", "build", "--config", ".design-sync/vite.lib.config.mts"]);
run("npx", ["tsc", "--project", ".design-sync/tsconfig.lib.json"]);

const CSS = ".design-sync/.cache/lib-dist/style.css";
const CONFIG = ".design-sync/config.json";
const DTS_DIR = ".design-sync/.cache/lib-dist";
const DTS_ENTRY = ".design-sync/.cache/lib-dist/index.d.ts";
if (!existsSync(CSS)) {
  throw new Error(
    `[build] expected Vite stylesheet at ${CSS} but it's missing — did the lib build emit CSS? ` +
      `Check cssCodeSplit:false in vite.lib.config.mts.`,
  );
}
// package.json#types points at a top-level declaration barrel so the
// converter treats lib-dist itself as the declaration root. Export exactly
// the curated componentSrcMap surface: the runtime barrel intentionally has
// hundreds of compound exports, while the design system has 97 root cards.
const { componentSrcMap } = JSON.parse(readFileSync(CONFIG, "utf8"));
const dtsExports = Object.entries(componentSrcMap)
  .filter(([, source]) => source !== null)
  .map(([name, source]) => {
    const declaration = `${DTS_DIR}/${source.replace(/\.(tsx|jsx)$/, ".d.ts")}`;
    if (!existsSync(declaration)) {
      throw new Error(`[build] missing declaration for ${name}: ${declaration}`);
    }
    const modulePath = `./${source.replace(/\.(tsx|jsx)$/, "")}`;
    const exportName = /\bexport\s+default\b/.test(
      readFileSync(declaration, "utf8"),
    )
      ? `default as ${name}`
      : name;
    return `export { ${exportName} } from ${JSON.stringify(modulePath)};`;
  });
writeFileSync(DTS_ENTRY, `${dtsExports.join("\n")}\n`);

let css = readFileSync(CSS, "utf8");
// "/fonts/X.ttf" -> "../../../client/public/fonts/X.ttf" (relative to the css dir
// ui/.design-sync/.cache/lib-dist/ -> ui/client/public/fonts/)
css = css.replace(/url\((['"]?)\/fonts\//g, "url($1../../../client/public/fonts/");
writeFileSync(CSS, css);
console.log(
  "[build] dist/index.js + style.css + declarations ready (brand font urls rewritten)",
);
