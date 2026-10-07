# Paint-Suppression Commands and Verbatim Tails

All commands run from the order worktree. Each logged command used the existing 589-second foreground guard. The wrapper commands below are exact.

```text
/Users/pythagor/nexus/.venv/bin/python docs/qa/777-glyph-first-states/after-review-r4/control-backdrop/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/probe.log env STATE_SURFACES_SCRATCH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/probe STATE_SURFACES_OUTPUT=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/probe.json STATE_SURFACES_PROBE=1 STATE_SURFACES_CONDITION=default npm --prefix ui run resolve-state-surfaces

> nexus-ui@1.0.0 resolve-state-surfaces
> node scripts/resolve-state-surfaces.mjs

[33mThe CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
Browserslist: browsers data (caniuse-lite) is 12 months old. Please run:
  npx update-browserslist-db@latest
  Why you should do it regularly: https://github.com/browserslist/update-db#readme
node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js (9:18): Use of eval in "node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js" is strongly discouraged as it poses security risks and may cause issues with minification.
Resolving default/Gilded…
Resolving default/Vector…
Resolving default/Veil…
Incomplete painted probe: renders=105; wall=12.302s; acceptanceComplete=false
file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/state-surfaces/png.mjs:75
    throw new Error(`Measurement failure ${label}: weak foreground mask; mode=${modeFraction.toFixed(6)} < ${minimumModeFraction}; top8=${JSON.stringify(histogram.slice(0, 8))}`);
          ^

Error: Measurement failure default/Vector/shipped/key/required/rest/verified/hsl(185 100% 70%): weak foreground mask; mode=0.126302 < 0.3; top8=[{"rgb":[102,242,255],"count":291},{"rgb":[17,40,42],"count":158},{"rgb":[17,39,41],"count":147},{"rgb":[97,230,242],"count":132},{"rgb":[14,31,32],"count":112},{"rgb":[18,42,44],"count":109},{"rgb":[14,30,31],"count":108},{"rgb":[16,38,40],"count":87}]
    at foreground (file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/state-surfaces/png.mjs:75:11)
    at sample (file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:141:24)
    at runNextTicks (node:internal/process/task_queues:65:5)
    at process.processImmediate (node:internal/timers:473:9)
    at async captureValues (file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:210:28)
    at async file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:254:11
    at async Promise.all (index 2)
    at async file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:81:5
    at async Promise.all (index 0)
    at async file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:77:3

Node.js v24.3.0
```

```text
/Users/pythagor/nexus/.venv/bin/python docs/qa/777-glyph-first-states/after-review-r4/control-backdrop/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/diagnostic-final.log env STATE_SURFACES_SCRATCH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/diagnostic node docs/qa/777-glyph-first-states/after-review-r4/paint-control/diagnostic.mjs
veil-neutral-1: mask=0; mode=null; FAIL
veil-prescribed-1: mask=2304; mode=0.18359375; FAIL
veil-prescribed-2: mask=2304; mode=0.18359375; FAIL
veil-prescribed-3: mask=2304; mode=0.18359375; FAIL
veil-tag-status-same-clip-1: mask=2304; mode=0.18359375; FAIL
veil-diagnostic-ancestor-filter-none-1: mask=723; mode=0.5822959889349931; PASS
gilded-neutral-1: mask=0; mode=null; FAIL
gilded-prescribed-1: mask=2304; mode=0.18359375; FAIL
gilded-prescribed-2: mask=2304; mode=0.18359375; FAIL
gilded-prescribed-3: mask=2304; mode=0.18359375; FAIL
gilded-tag-status-same-clip-1: mask=2304; mode=0.18359375; FAIL
gilded-diagnostic-ancestor-filter-none-1: mask=723; mode=0.5822959889349931; PASS
vector-neutral-1: mask=0; mode=null; FAIL
vector-prescribed-1: mask=2304; mode=0.12630208333333334; FAIL
vector-prescribed-2: mask=2304; mode=0.12630208333333334; FAIL
vector-prescribed-3: mask=2304; mode=0.12630208333333334; FAIL
vector-tag-status-same-clip-1: mask=2304; mode=0.12630208333333334; FAIL
vector-diagnostic-ancestor-filter-none-1: mask=726; mode=0.38980716253443526; PASS
Repeated prescribed comparisons=9; errors=0; networkRequests=0
```

```text
/Users/pythagor/nexus/.venv/bin/python docs/qa/777-glyph-first-states/after-review-r4/control-backdrop/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/focused.log npm --prefix ui test -- state-shades StateGlyphs shell-accessibility

> nexus-ui@1.0.0 test
> vitest run state-shades StateGlyphs shell-accessibility


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ src/shell-accessibility.test.ts (9 tests) 55ms
 ❯ src/state-shades.test.ts (0 test)
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 409ms

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:161:9
    159|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    160| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    161|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    162| if (receipt.proof.acceptanceComplete !== true)
    163|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed | 2 passed (3)
      Tests  15 passed (15)
   Start at  14:38:30
   Duration  1.12s (transform 228ms, setup 85ms, collect 383ms, tests 464ms, environment 512ms, prepare 120ms)

```

```text
/Users/pythagor/nexus/.venv/bin/python docs/qa/777-glyph-first-states/after-review-r4/control-backdrop/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/check.log npm --prefix ui run check

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

```

```text
/Users/pythagor/nexus/.venv/bin/python docs/qa/777-glyph-first-states/after-review-r4/control-backdrop/run_gate.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/regenerate.log env STATE_SURFACES_SCRATCH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/paint-control/full-attempt npm --prefix ui run resolve-state-surfaces
Browserslist: browsers data (caniuse-lite) is 12 months old. Please run:
  npx update-browserslist-db@latest
  Why you should do it regularly: https://github.com/browserslist/update-db#readme
node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js (9:18): Use of eval in "node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js" is strongly discouraged as it poses security risks and may cause issues with minification.
Resolving default/Gilded…
Resolving motion-start/Gilded…
Resolving motion-trough/Veil…
Resolving default/Veil…
Resolving default/Vector…
Resolving width-639/Veil…
Resolving motion-start/Veil…
Resolving motion-trough/Gilded…
Resolving motion-start/Vector…
Resolving width-639/Gilded…
Resolving motion-trough/Vector…
Resolving width-639/Vector…
Painted capture progress: renders=2041; wall=48.277s
Incomplete painted probe: renders=2317; wall=55.086s; acceptanceComplete=false
file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/state-surfaces/png.mjs:75
    throw new Error(`Measurement failure ${label}: weak foreground mask; mode=${modeFraction.toFixed(6)} < ${minimumModeFraction}; top8=${JSON.stringify(histogram.slice(0, 8))}`);
          ^

Error: Measurement failure width-639/Vector/candidate/delete/ready-exceeds/row-hover/unarmed/hsl(185 40% 40%): weak foreground mask; mode=0.131868 < 0.3; top8=[{"rgb":[21,47,49],"count":96},{"rgb":[21,46,48],"count":46},{"rgb":[23,51,53],"count":44},{"rgb":[23,52,54],"count":44},{"rgb":[22,49,51],"count":37},{"rgb":[22,48,50],"count":36},{"rgb":[22,50,52],"count":36},{"rgb":[21,48,49],"count":24}]
    at foreground (file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/state-surfaces/png.mjs:75:11)
    at sample (file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:141:24)
    at runNextTicks (node:internal/process/task_queues:65:5)
    at process.processImmediate (node:internal/timers:473:9)
    at async captureValues (file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:210:28)
    at async file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:241:13
    at async Promise.all (index 2)
    at async file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:81:5
    at async Promise.all (index 3)
    at async file:///Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/scripts/resolve-state-surfaces.mjs:77:3

Node.js v24.3.0
```

Node syntax checks and git diff --check exited zero with no output. Independent Pillow comparison reproduced 18/18 diagnostic masks and top-eight histograms, plus both original failure modes.

Codex, GPT-6.
