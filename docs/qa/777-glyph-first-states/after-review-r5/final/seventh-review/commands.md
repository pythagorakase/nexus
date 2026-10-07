# Seventh Review Commands

All commands below exit 0. Focused/full invocations are bounded at 589 seconds each; the single full regeneration uses its checked-in 4123-second bound and writes to scratch before comparison. Reachability preserves the secret-store guard and unsets PG/live/secret-store flags. The coordinator gate at `198e4e03` stands for the `ui/` and `docs/` scope.

## Unit

```sh
npm --prefix ui test -- media-state-shades
```

[Complete output](unit.log).

```text

> nexus-ui@1.0.0 test
> vitest run media-state-shades


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ media-state-shades.test.ts (46 tests) 9ms

 Test Files  1 passed (1)
      Tests  46 passed (46)
   Start at  20:47:40
   Duration  341ms (transform 23ms, setup 22ms, collect 22ms, tests 9ms, environment 139ms, prepare 32ms)

```

## Focused

```sh
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
```

[Complete output](focused.log).

```text
 ✓ src/shell-accessibility.test.ts (9 tests) 58ms
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 404ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":156,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 48765ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1249ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 13026ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 32332ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1858ms

 Test Files  4 passed (4)
      Tests  72 passed (72)
   Start at  21:21:49
   Duration  50.46s (transform 236ms, setup 123ms, collect 1.71s, tests 49.24s, environment 729ms, prepare 174ms)

```

## Full

```sh
npm --prefix ui test
```

[Complete output](full.log).

```text
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'character' card (accepted: true) 837ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true) 832ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":156,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 48912ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1343ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 13216ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 32191ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1867ms

 Test Files  38 passed (38)
      Tests  550 passed (550)
   Start at  21:22:40
   Duration  51.55s (transform 2.31s, setup 1.87s, collect 12.05s, tests 64.47s, environment 12.53s, prepare 1.69s)

```

## Check

```sh
npm --prefix ui run check
```

[Complete output](check.log).

```text

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

```

## Build

```sh
npm --prefix ui run build
```

[Complete output](build.log).

```text
../dist/public/assets/KaTeX_Main-Regular-ypZvNtVU.ttf              53.58 kB
../dist/public/assets/KaTeX_AMS-Regular-DRggAlZN.ttf               63.63 kB
../dist/public/assets/r1c1-CzjRNMRW.png                            95.61 kB
../dist/public/assets/index-Ddk7DCvv.css                          201.53 kB │ gzip:  36.92 kB
../dist/public/assets/index-CTjDzXAZ.js                         1,767.86 kB │ gzip: 527.80 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 2.55s

PWA v1.0.3
mode      generateSW
precache  22 entries (2314.47 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## Reachability

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_SECRET_STORE PYTHONPATH="$PWD" /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

[Complete output](reachability.log).

```text
......................................................                   [100%]
=============================== warnings summary ===============================
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_reachability.py::test_static_graph_follows_relative_namespace_and_literal_dynamic_imports
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.68s
```

## Regeneration

```sh
STATE_SURFACES_SCRATCH="$PWD/scratchpad/777-S2/after-review-r7/capture" STATE_SURFACES_OUTPUT="$PWD/scratchpad/777-S2/after-review-r7/regenerated.json" npm --prefix ui run resolve-state-surfaces
```

[Complete output](regeneration.log).

```text
Completed w1281-1535/motion/trough/Veil; renders=91329; wall=1735.944s
Painted capture progress: renders=91914; wall=1758.447s
Painted capture progress: renders=93066; wall=1803.448s
Painted capture progress: renders=95402; wall=1848.448s
Painted capture progress: renders=97990; wall=1893.449s
Completed w1536+/reduce/Vector; renders=99096; wall=1912.272s
Completed w1536+/motion/start/Vector; renders=100029; wall=1929.667s
Completed w1536+/motion/trough/Vector; renders=100339; wall=1936.037s
Painted capture progress: renders=100433; wall=1938.448s
Completed w1536+/reduce/Gilded; renders=101286; wall=1958.966s
Completed w1536+/reduce/Veil; renders=101289; wall=1958.986s
Completed w1536+/motion/start/Gilded; renders=101592; wall=1970.358s
Completed w1536+/motion/start/Veil; renders=101593; wall=1970.387s
Completed w1536+/motion/trough/Veil; renders=101730; wall=1980.399s
Completed w1536+/motion/trough/Gilded; renders=101742; wall=1981.916s
Resolved painted state surfaces: renders=101742; wall=1981.920s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 27 media conditions; file://; network aborted; requests=0; errors=0
Wrote /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/scratchpad/777-S2/after-review-r7/regenerated.json; module graph=2095 inputs; SHA-256 70f2d64239c57d51435eadfd558bf0dd5f34f4af5266507c09e99efb5122337b
```

## Receipt Comparison

`node --max-old-space-size=8192 scratchpad/777-S2/after-review-r7/compare.mjs` exits 0. [Comparison](receipt-comparison.json): 27 identical conditions, 101,742 compared samples, zero measured differences, no missing/additional samples. The baseline content hash agrees with `bc1af7ba`'s LFS OID. Every paint, mask, geometry, opacity and settled-state field agrees. Runtime settle times, Escape-needed flags and the exact action-description suffix for that same branch are excluded. [Runtime observation diff](runtime-observation-comparison.json) records all 415 action-description changes; all other compared sample fields agree. [Initial strict comparison log](runtime-observation-comparison.log) and [measurement comparison log](comparison.log) preserve both checks. The shipping receipt was replaced only after the measurement comparison passed.

## Restored

```sh
npm --prefix ui test -- state-shades
```

Exit 0; bounded at 589 seconds. [Complete output](restored.log).

```text
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":156,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 48606ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1254ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 13078ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 32116ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1865ms

 Test Files  2 passed (2)
      Tests  57 passed (57)
   Start at  21:31:43
   Duration  50.20s (transform 61ms, setup 55ms, collect 1.22s, tests 48.62s, environment 332ms, prepare 134ms)

```

## Plant

```sh
STATE_SURFACES_SCRATCH="$PWD/scratchpad/777-S2/after-review-r7/plants" node ui/scripts/state-surfaces/plants.mjs --stage control
# Then use --plant nested-not-print-width with each stage in order:
# --stage stale, --stage capture, --stage fresh, --stage restore
```

The checked-in protocol bounds each child at 589 seconds. Every protocol stage exits 0; the stale and fresh Vitest children exit 1 as required. [Ledger](plants/plants-proof.json) retains exact invocations, exits and tails; [before hashes](plants/before-plants.json), [changed means](plants/optional-key-means.json), and the [uncertified partial receipt](plants/partial-receipt.json) retain the proof. The fresh recorded-table assertion fails, four other diagnostics pass and six full-inventory assertions are intentionally skipped. Restoration compares the saved snapshot with live worktree, scratch and HEAD before writing.

## Main Integration

`git fetch origin` and `git merge origin/main` both exit 0; merge reports `Already up to date.` No rebase or stash was used.

Codex, GPT-6.
