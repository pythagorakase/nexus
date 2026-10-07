# Round-5 Completion Commands

All Python proof commands unset `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT`, `NEXUS_RUN_LIVE_LLM` and `NEXUS_RUN_SECRET_STORE`, set `PYTHONPATH` to this worktree, and keep the secret-store guard active. Offline/reachability commands also unset `NEXUS_RUN_POSTGRES`; the owner-target guard alone sets it to 1 and loads `-p tests.dbname_audit`. The offline suite is partitioned only to keep each invocation within its 589-second bound. It covers every default-discoverable test file once; the separate required guard and reachability checks intentionally repeat their targets. No paid model or owner-database access was requested.

## focused

```sh
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
```

Exit 0; measured 47.217s; bound 589s; timed out: False.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades StateGlyphs shell-accessibility


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ src/shell-accessibility.test.ts (9 tests) 54ms
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 406ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":152,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 45922ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1209ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 10562ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 32040ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1822ms

 Test Files  3 passed (3)
      Tests  26 passed (26)
   Start at  15:51:46
   Duration  46.98s (transform 213ms, setup 80ms, collect 1.03s, tests 46.38s, environment 511ms, prepare 98ms)

```

## frontend-build-final

```sh
npm --prefix ui run build
```

Exit 0; measured 3.995s; bound 589s; timed out: False.

```text
../dist/public/assets/KaTeX_Fraktur-Regular-CB_wures.ttf           19.57 kB
../dist/public/assets/KaTeX_Fraktur-Bold-BdnERNNW.ttf              19.58 kB
../dist/public/assets/KaTeX_Main-Italic-BMLOBm91.woff              19.68 kB
../dist/public/assets/KaTeX_SansSerif-Italic-YYjJ1zSn.ttf          22.36 kB
../dist/public/assets/KaTeX_SansSerif-Bold-CFMepnvq.ttf            24.50 kB
../dist/public/assets/KaTeX_Main-Bold-Cx986IdX.woff2               25.32 kB
../dist/public/assets/KaTeX_Main-Regular-B22Nviop.woff2            26.27 kB
../dist/public/assets/KaTeX_Typewriter-Regular-D3Ib7_Hf.ttf        27.56 kB
../dist/public/assets/KaTeX_AMS-Regular-BQhdFMY1.woff2             28.08 kB
../dist/public/assets/KaTeX_Main-Bold-Jm3AIy58.woff                29.91 kB
../dist/public/assets/KaTeX_Main-Regular-Dr94JaBh.woff             30.77 kB
../dist/public/assets/KaTeX_Math-BoldItalic-B3XSjfu4.ttf           31.20 kB
../dist/public/assets/KaTeX_Math-Italic-flOr_0UB.ttf               31.31 kB
../dist/public/assets/KaTeX_Main-BoldItalic-DzxPMmG6.ttf           32.97 kB
../dist/public/assets/KaTeX_AMS-Regular-DMm9YOAa.woff              33.52 kB
../dist/public/assets/KaTeX_Main-Italic-3WenGoN9.ttf               33.58 kB
../dist/public/assets/KaTeX_Main-Bold-waoOVXN0.ttf                 51.34 kB
../dist/public/assets/KaTeX_Main-Regular-ypZvNtVU.ttf              53.58 kB
../dist/public/assets/KaTeX_AMS-Regular-DRggAlZN.ttf               63.63 kB
../dist/public/assets/r1c1-CzjRNMRW.png                            95.61 kB
../dist/public/assets/index-Ddk7DCvv.css                          201.53 kB │ gzip:  36.92 kB
../dist/public/assets/index-CTjDzXAZ.js                         1,767.86 kB │ gzip: 527.80 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 2.92s

PWA v1.0.3
mode      generateSW
precache  22 entries (2314.47 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## frontend-check-final

```sh
npm --prefix ui run check
```

Exit 0; measured 2.232s; bound 589s; timed out: False.

```text

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

```

## frontend-focused-final

```sh
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
```

Exit 0; measured 51.671s; bound 589s; timed out: False.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades StateGlyphs shell-accessibility


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ src/shell-accessibility.test.ts (9 tests) 57ms
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 422ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":153,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 49772ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1309ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 11180ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 35048ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1944ms

 Test Files  3 passed (3)
      Tests  26 passed (26)
   Start at  18:23:23
   Duration  51.37s (transform 238ms, setup 103ms, collect 1.57s, tests 50.25s, environment 587ms, prepare 140ms)

```

## frontend-full-final

```sh
npm --prefix ui test
```

Exit 0; measured 52.736s; bound 589s; timed out: False.

```text
stderr | src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx > genesis strangeness > appears only on the Introduction
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

 ✓ src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx (42 tests) 4765ms
   ✓ genesis stage waiter > tracks each stage while the transition is in flight, then glows bootstrap until the session returns 476ms
stderr | src/pages/ContinuePage.resume.test.tsx > resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true)
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

stderr | src/pages/ContinuePage.resume.test.tsx > resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true)
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

 ✓ src/pages/ContinuePage.resume.test.tsx (4 tests) 3538ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'character' card (accepted: false) 987ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: false) 853ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'character' card (accepted: true) 859ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true) 838ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":153,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 49793ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1489ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 11140ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 34944ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1925ms

 Test Files  37 passed (37)
      Tests  504 passed (504)
   Start at  18:24:15
   Duration  52.45s (transform 2.23s, setup 2.43s, collect 12.87s, tests 67.18s, environment 15.59s, prepare 2.05s)

```

## offline-api-orrery

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
```

Exit 0; measured 45.392s; bound 589s; timed out: False.

```text
sssssssssssss....................s........................ssssssssssssss [ 73%]
sssssssssssss..s.........sss...........ssss........................sss.. [ 75%]
...ssssssssssssssssssssss......sssss..s...................ssssssssssssss [ 77%]
ssssssssssssssssssssssssssssssss........................................ [ 80%]
..................................................................ssssss [ 82%]
ss...................................................................... [ 84%]
...............s.................sssss...s.............................. [ 86%]
................sssssssssssssssssssssssss............................... [ 89%]
.........................sssssssssssss.s......s...................s....s [ 91%]
ssssssssssssssssssss.......ss...............ssss........................ [ 93%]
..............ss....sssssssssss......................................... [ 95%]
............................................sssssssssss................. [ 97%]
.......sssssssssssssss.............sssss..........s.ssssssssssssss       [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1865 passed, 1369 skipped, 7 warnings in 44.08s
```

## offline-config

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/config
```

Exit 0; measured 6.346s; bound 589s; timed out: False.

```text
........................................................................ [ 57%]
......................................................                   [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
126 passed, 5 warnings in 5.67s
```

## offline-root-1

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/live_seed_schema_test.py tests/live_set_designer_test.py tests/test_backfill_review_packet.py tests/test_bootstrap_episode_pg.py tests/test_character_identity.py tests/test_character_name_reveals.py tests/test_character_name_reveals_pg.py tests/test_character_relationship_id_types_pg.py tests/test_character_tag_manifest.py tests/test_chunk_lifecycle_columns_migration_pg.py tests/test_cli.py tests/test_cli_choice_http.py tests/test_cli_contract.py tests/test_cli_generation_http.py tests/test_cli_inspect_pg.py tests/test_cli_model_selection.py tests/test_cli_session_wait.py tests/test_cli_wizard_confirmation.py tests/test_clock_face.py tests/test_commit_choice_presence_pg.py tests/test_commit_chronology.py tests/test_commit_handler_sync.py tests/test_connection_lifecycle.py tests/test_correspondence.py tests/test_correspondence_live.py
```

Exit 0; measured 251.118s; bound 589s; timed out: False.

```text
........s......................................sssssss...ssss........... [ 15%]
........................................................................ [ 30%]
........................................................................ [ 45%]
........................................................................ [ 60%]
................................................................s....... [ 75%]
..........................................................ssssssssss.... [ 90%]
...............s....s........................s                           [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
452 passed, 28 skipped, 5 warnings in 250.62s (0:04:10)
```

## offline-root-2

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_database_contract.py tests/test_db_converters.py tests/test_dbname_audit.py tests/test_doc_front_matter.py tests/test_embedding_artifacts.py tests/test_embedding_table_ownership_pg.py tests/test_entity_reference_parity_pg.py tests/test_entity_tag_manifest_apply.py tests/test_enum_column_comment_labels_pg.py tests/test_faction_table_audit.py tests/test_gis_scripts_live.py tests/test_golden_path_live.py tests/test_idf_dictionary_pg.py tests/test_inherited_slot_isolation_pg.py tests/test_intention_revision_weight.py tests/test_interaction_boundary.py tests/test_interactions_pg.py tests/test_issue_601_wizard_live.py tests/test_jobs_cli_pg.py tests/test_live_gate_clones_pg.py tests/test_local_skald_live.py tests/test_logon_mock_integration.py tests/test_lore_adapter_metadata.py tests/test_measure_place_coordinate_costs.py tests/test_measure_place_coordinate_costs_pg.py
```

Exit 0; measured 18.644s; bound 589s; timed out: False.

```text
......................ss................s..ss..................s........ [ 24%]
...........................................sssssssssssssssssssssssssssss [ 48%]
sssssssssssssssssssssssssssssss........ssssssssssssssss.....s....s...... [ 72%]
....ss..ssssssssssssssssssssssssssssssss..........ssssssssssssssssssssss [ 96%]
ssss......s                                                              [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
154 passed, 145 skipped, 5 warnings in 17.84s
```

## offline-root-3

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_measure_place_scale_grammar.py tests/test_measure_place_scale_grammar_pg.py tests/test_memnon_cross_encoder.py tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder_dependencies.py tests/test_memnon_db_access.py tests/test_memnon_embedding_cache.py tests/test_memnon_embedding_contract.py tests/test_memnon_model_failures_pg.py tests/test_memnon_runtime_config.py tests/test_memnon_script_model_loaders.py tests/test_migration_comment_lint.py tests/test_mock_openai.py tests/test_model_artifact_lock_committed.py tests/test_model_drift.py tests/test_model_registry_live.py tests/test_name_reveal_staged_bindings.py tests/test_name_reveal_staged_bindings_pg.py tests/test_name_reveal_tag_validation.py tests/test_name_reveal_tag_validation_pg.py tests/test_native_structured_output.py tests/test_new_story_cache.py tests/test_new_story_cli.py tests/test_new_story_integration.py tests/test_new_story_schemas.py
```

Exit 0; measured 33.860s; bound 589s; timed out: False.

```text
....ss.............................s........ss.............sssssssssssss [ 17%]
sss............................................................ss....... [ 35%]
........sss....................................................ssssss... [ 53%]
..............ss........................................................ [ 71%]
........................................................................ [ 88%]
...ss..ss................................ssss                            [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

tests/test_memnon_cross_encoder_dependencies.py::test_sentencepiece_runtime_dependency_available
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

tests/test_memnon_cross_encoder_dependencies.py::test_sentencepiece_runtime_dependency_available
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
363 passed, 42 skipped, 8 warnings in 33.01s
```

## offline-root-4

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_new_story_setup.py tests/test_new_story_setup_config.py tests/test_openai_registry_capabilities.py tests/test_orrery_tag_validation.py tests/test_orrery_tag_validation_pg.py tests/test_owner_target_guard.py tests/test_pg_accepted_turn_factory.py tests/test_pg_adjudication_ledger_seed.py tests/test_pg_anchor_pair_tag_seeds.py tests/test_pg_character_pair_seed.py tests/test_pg_disposable_target.py tests/test_pg_legacy_faction_tag_seed.py tests/test_pg_target_contract.py tests/test_place_tag_manifest.py tests/test_player_identity_consumers_pg.py tests/test_postgres_tools.py tests/test_presence_audit.py tests/test_presence_boost.py tests/test_presence_boost_pg.py tests/test_presence_reconciliation.py tests/test_presence_roster.py tests/test_presence_roster_pg.py tests/test_prompt_lint.py tests/test_prompt_tag_vocabulary_pg.py tests/test_prose_metrics.py
```

Exit 0; measured 30.421s; bound 589s; timed out: False.

```text
sssssssssssss..........................................................s [ 13%]
sssssssssssssssssssssssssssssssssssssssssssssssss....................... [ 26%]
.........................................................sssssssssssssss [ 39%]
ss.........................................................s.ssssss..... [ 52%]
........................................................................ [ 66%]
...............................s.....ssssssssssssssssss........s...ss... [ 79%]
..................s..........................sssssssssssssssssssssss.... [ 92%]
..................sss...................                                 [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
408 passed, 136 skipped, 7 warnings in 29.46s
```

## offline-root-5

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_prose_metrics_pg.py tests/test_qa_shift.py tests/test_reachability.py tests/test_rebuild_memory_idf_pg.py tests/test_record_revelation_cli_pg.py tests/test_reentry_wire_ledger.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_register_drift_study.py tests/test_retrograde_summary_retrieval.py tests/test_routine_delta_grammar_probe_pg.py tests/test_runtime_home.py tests/test_scheduler_helpers_basetemp.py tests/test_scheduler_helpers_routing.py tests/test_schema_documentation_pg.py tests/test_secret_manager.py tests/test_secret_store_guard.py tests/test_secret_store_integration.py tests/test_skald_wire.py tests/test_slot_routed_entrypoints.py tests/test_slot_utils.py tests/test_summary_triggers.py tests/test_tags_audit_pg.py tests/test_trait_compiler.py tests/test_trait_compiler_integration.py tests/test_trait_input_derivation.py
```

Exit 0; measured 49.210s; bound 589s; timed out: False.

```text
s................................................sssssssss...ssssss..... [ 12%]
.........s........................................................ssssss [ 24%]
ssssssssss.ss......................s....sssss........................... [ 36%]
................................ssssssssssssssssssssssssssssssssss...... [ 48%]
........................................................................ [ 60%]
..............................ss........................................ [ 72%]
...................................................s..s................. [ 84%]
............ssss.................sssss.................................. [ 96%]
.sssss................                                                   [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
505 passed, 93 skipped, 7 warnings in 48.67s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

## offline-root-6

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_trait_menu_docs.py tests/test_travel_reachability.py tests/test_travel_reachability_pg.py tests/test_turn_observation.py tests/test_unowned_index_adoption_pg.py tests/test_usage_recorder.py tests/test_wizard_agent.py tests/test_wizard_live.py tests/test_wizard_opening_presence_pg.py tests/test_world_clock_contract_pg.py
```

Exit 0; measured 6.653s; bound 589s; timed out: False.

```text
...sss.........................................ssss..................... [ 58%]
.........................sssssssssssssssssssssssssss                     [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
90 passed, 34 skipped, 7 warnings in 6.00s
```

## offline-test_config

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_config
```

Exit 0; measured 7.788s; bound 589s; timed out: False.

```text
........................................................................ [ 79%]
...................                                                      [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
91 passed, 5 warnings in 7.06s
```

## offline-test_ir_eval_v2

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_ir_eval_v2
```

Exit 0; measured 3.097s; bound 589s; timed out: False.

```text
............                                                             [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
12 passed, 5 warnings in 2.40s
```

## offline-test_lore

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore
```

Exit 0; measured 21.641s; bound 589s; timed out: False.

```text
..................s...........sssssss................................... [ 15%]
..........ss............ssssssss...............s........................ [ 30%]
........................................................................ [ 46%]
............sssssssss....................sssss...s......sssss......sss.. [ 61%]
................s....................................................... [ 76%]
...s..ss................................................................ [ 92%]
..........sssssssss..................                                    [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
414 passed, 55 skipped, 5 warnings in 20.66s
```

## offline-test_memnon

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon
```

Exit 0; measured 7.555s; bound 589s; timed out: False.

```text
..........sss..........................ss....s..s.s                      [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
43 passed, 8 skipped, 5 warnings in 6.85s
```

## offline-test_runtime

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_runtime
```

Exit 0; measured 57.656s; bound 589s; timed out: False.

```text
........................................................................ [ 38%]
.........sssss.......................................................... [ 76%]
................................sssssssssssss                            [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
171 passed, 18 skipped, 5 warnings in 57.27s
```

## offline-test_scripts

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_scripts
```

Exit 0; measured 31.918s; bound 589s; timed out: False.

```text
........................................................................ [ 76%]
......................                                                   [100%]
=============================== warnings summary ===============================
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_scripts/test_check_exception_dispositions.py::test_new_unmarked_handler_fails[except ValueError:]
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
94 passed, 5 warnings in 26.01s
```

## offline-test_util

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_util
```

Exit 0; measured 0.854s; bound 589s; timed out: False.

```text
.......                                                                  [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_util/test_gguf_inspect.py::test_inspect_real_gguf_when_installed
tests/test_util/test_gguf_inspect.py::test_inspect_real_gguf_when_installed
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_util/test_gguf_inspect.py::test_inspect_real_gguf_when_installed
tests/test_util/test_gguf_inspect.py::test_inspect_real_gguf_when_installed
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

tests/test_util/test_gguf_inspect.py::test_inspect_real_gguf_when_installed
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
7 passed, 7 warnings in 0.52s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

## owner-target-guard

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_owner_target_guard.py
```

Exit 0; measured 3.763s; bound 589s; timed out: False.

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
........................................................................ [ 90%]
........                                                                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
80 passed in 3.12s
```

## reachability

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

Exit 0; measured 11.406s; bound 589s; timed out: False.

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
54 passed, 5 warnings in 10.76s
```

## ui-build

```sh
npm --prefix ui run build
```

Exit 0; measured 3.320s; bound 589s; timed out: False.

```text
../dist/public/assets/KaTeX_Fraktur-Regular-CB_wures.ttf           19.57 kB
../dist/public/assets/KaTeX_Fraktur-Bold-BdnERNNW.ttf              19.58 kB
../dist/public/assets/KaTeX_Main-Italic-BMLOBm91.woff              19.68 kB
../dist/public/assets/KaTeX_SansSerif-Italic-YYjJ1zSn.ttf          22.36 kB
../dist/public/assets/KaTeX_SansSerif-Bold-CFMepnvq.ttf            24.50 kB
../dist/public/assets/KaTeX_Main-Bold-Cx986IdX.woff2               25.32 kB
../dist/public/assets/KaTeX_Main-Regular-B22Nviop.woff2            26.27 kB
../dist/public/assets/KaTeX_Typewriter-Regular-D3Ib7_Hf.ttf        27.56 kB
../dist/public/assets/KaTeX_AMS-Regular-BQhdFMY1.woff2             28.08 kB
../dist/public/assets/KaTeX_Main-Bold-Jm3AIy58.woff                29.91 kB
../dist/public/assets/KaTeX_Main-Regular-Dr94JaBh.woff             30.77 kB
../dist/public/assets/KaTeX_Math-BoldItalic-B3XSjfu4.ttf           31.20 kB
../dist/public/assets/KaTeX_Math-Italic-flOr_0UB.ttf               31.31 kB
../dist/public/assets/KaTeX_Main-BoldItalic-DzxPMmG6.ttf           32.97 kB
../dist/public/assets/KaTeX_AMS-Regular-DMm9YOAa.woff              33.52 kB
../dist/public/assets/KaTeX_Main-Italic-3WenGoN9.ttf               33.58 kB
../dist/public/assets/KaTeX_Main-Bold-waoOVXN0.ttf                 51.34 kB
../dist/public/assets/KaTeX_Main-Regular-ypZvNtVU.ttf              53.58 kB
../dist/public/assets/KaTeX_AMS-Regular-DRggAlZN.ttf               63.63 kB
../dist/public/assets/r1c1-CzjRNMRW.png                            95.61 kB
../dist/public/assets/index-Ddk7DCvv.css                          201.53 kB │ gzip:  36.92 kB
../dist/public/assets/index-CTjDzXAZ.js                         1,767.86 kB │ gzip: 527.80 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 2.44s

PWA v1.0.3
mode      generateSW
precache  22 entries (2314.47 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## ui-check

```sh
npm --prefix ui run check
```

Exit 0; measured 1.762s; bound 589s; timed out: False.

```text

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

```

## ui-test

```sh
npm --prefix ui test
```

Exit 0; measured 46.463s; bound 589s; timed out: False.

```text
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

 ✓ src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx (42 tests) 4445ms
   ✓ genesis stage waiter > tracks each stage while the transition is in flight, then glows bootstrap until the session returns 447ms
   ✓ genesis stage waiter > marks the stage the gateway recorded as failed and keeps the error with Retry and Cancel 306ms
stderr | src/pages/ContinuePage.resume.test.tsx > resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true)
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

stderr | src/pages/ContinuePage.resume.test.tsx > resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true)
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

 ✓ src/pages/ContinuePage.resume.test.tsx (4 tests) 3498ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'character' card (accepted: false) 982ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: false) 840ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'character' card (accepted: true) 842ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true) 834ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":152,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 44514ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1565ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 10972ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 29863ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1825ms

 Test Files  37 passed (37)
      Tests  504 passed (504)
   Start at  15:53:11
   Duration  46.22s (transform 2.19s, setup 1.83s, collect 11.36s, tests 60.14s, environment 12.53s, prepare 1.63s)

```

The named resolver has its own condition-count-derived bound of 4123 seconds for 27 renders; its full tail is in `regeneration-after-protocol.log`. Default plant commands and tails are recorded in `plants/plants-proof.json`.

Codex, GPT-6.
