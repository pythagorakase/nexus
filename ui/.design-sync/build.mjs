// cfg.buildCmd for design-sync (run from the ui/ package root). Three steps:
//   1. regenerate the Vite lib entry + componentSrcMap from the component tree
//   2. vite lib build → clean ESM dist (index.js) + extracted style.css
//   3. rewrite the 20 brand @font-face "/fonts/" urls (absolute app/public paths,
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

const CSS = ".design-sync/.cache/lib-dist/style.css";
if (!existsSync(CSS)) {
  throw new Error(
    `[build] expected Vite stylesheet at ${CSS} but it's missing — did the lib build emit CSS? ` +
      `Check cssCodeSplit:false in vite.lib.config.mts.`,
  );
}
let css = readFileSync(CSS, "utf8");
// "/fonts/X.ttf" -> "../../../client/public/fonts/X.ttf" (relative to the css dir
// ui/.design-sync/.cache/lib-dist/ -> ui/client/public/fonts/)
css = css.replace(/url\((['"]?)\/fonts\//g, "url($1../../../client/public/fonts/");
writeFileSync(CSS, css);
console.log("[build] dist/index.js + style.css ready (brand font urls rewritten)");
