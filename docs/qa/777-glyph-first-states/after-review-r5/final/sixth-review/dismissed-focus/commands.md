# Sixth Review Dismissed-Focus Commands

The one complete full regeneration is recorded in regeneration.log with its 4123-second internal bound. The initial missing-import attempt is preserved separately. Plant commands are in plants/plants-proof.json, bounded at 589 seconds per stage. Reachability unsets gateway/API URL, slot and PG/live/secret-store flags, uses this worktree on PYTHONPATH, and preserves the guard. No new whole-tree Python result is claimed.

## Unit

```sh
npm --prefix ui test -- media-state-shades
```

Exit 0; measured 0.665s; bound 589s; timed out: False.

```text

> nexus-ui@1.0.0 test
> vitest run media-state-shades


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ media-state-shades.test.ts (5 tests) 4ms

 Test Files  1 passed (1)
      Tests  5 passed (5)
   Start at  19:46:44
   Duration  388ms (transform 25ms, setup 27ms, collect 23ms, tests 4ms, environment 160ms, prepare 27ms)

```

## Focused

```sh
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
```

Exit 0; measured 50.490s; bound 589s; timed out: False.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades StateGlyphs shell-accessibility


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ media-state-shades.test.ts (5 tests) 5ms
 ✓ src/shell-accessibility.test.ts (9 tests) 58ms
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 407ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":156,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 48544ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1242ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 13028ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 32111ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1869ms

 Test Files  4 passed (4)
      Tests  31 passed (31)
   Start at  20:18:49
   Duration  50.23s (transform 239ms, setup 112ms, collect 1.70s, tests 49.01s, environment 723ms, prepare 126ms)

```

## Full

```sh
npm --prefix ui test
```

Exit 0; measured 51.667s; bound 589s; timed out: False.

```text

stderr | src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx > genesis strangeness > starts no transition when a save in flight at Confirm is refused
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

stderr | src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx > genesis strangeness > appears only on the Introduction
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

 ✓ src/components/NewStoryWizard/InteractiveWizard.transition.test.tsx (42 tests) 4440ms
   ✓ genesis stage waiter > tracks each stage while the transition is in flight, then glows bootstrap until the session returns 438ms
stderr | src/pages/ContinuePage.resume.test.tsx > resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true)
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

stderr | src/pages/ContinuePage.resume.test.tsx > resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true)
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering
WARNING: Panel defaultSize prop recommended to avoid layout shift after server rendering

 ✓ src/pages/ContinuePage.resume.test.tsx (4 tests) 3469ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'character' card (accepted: false) 957ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: false) 839ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'character' card (accepted: true) 842ms
   ✓ resuming a wizard at a confirmation boundary (#955) > reload, Home → Continue and history keep the 'setting' card (accepted: true) 829ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":156,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 48901ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1346ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 13084ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 32317ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1862ms

 Test Files  38 passed (38)
      Tests  509 passed (509)
   Start at  20:19:39
   Duration  51.40s (transform 2.05s, setup 2.13s, collect 11.60s, tests 64.49s, environment 13.62s, prepare 1.65s)

```

## Check

```sh
npm --prefix ui run check
```

Exit 0; measured 1.750s; bound 589s; timed out: False.

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

Exit 0; measured 3.365s; bound 589s; timed out: False.

```text
../dist/public/assets/KaTeX_Main-Italic-NWA7e6Wa.woff2             16.99 kB
../dist/public/assets/KaTeX_Math-BoldItalic-iY-2wyZ7.woff          18.67 kB
../dist/public/assets/KaTeX_Math-Italic-DA0__PXp.woff              18.75 kB
../dist/public/assets/KaTeX_Main-BoldItalic-SpSLRI95.woff          19.41 kB
../dist/public/assets/KaTeX_SansSerif-Regular-BNo7hRIc.ttf         19.44 kB
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
✓ built in 2.45s

PWA v1.0.3
mode      generateSW
precache  22 entries (2314.47 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## Reachability

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

Exit 0; measured 16.983s; bound 589s; timed out: False.

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
54 passed, 5 warnings in 10.83s
```

## Restored

```sh
npm --prefix ui test -- state-shades
```

Exit 0; measured 50.546s; bound 589s; timed out: False.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ media-state-shades.test.ts (5 tests) 5ms
stdout | src/state-shades.test.ts > 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures
{"theme":"Veil","sizes":[15,15,18,15,15,15,18,18,18,15,18,12],"count":"258280326000000","feasible":"0","best":5.9942603943504995,"changes":7,"assignment":{"--state-mem-normal":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)","--state-mem-over":"hsl(15 75% 60%)","--state-delete-unarmed":"hsl(42 30% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(15 75% 60%)","--state-map-current":"hsl(330.2439024390244 60% 70%)","--state-map-selected":"hsl(330.2439024390244 50.20408163265306% 30%)","--state-map-hovered":"hsl(330.2439024390244 80% 50%)","--state-key-absent":"hsl(42 40% 70%)","--state-key-missing":"hsl(15 75% 60%)","--state-key-present":"hsl(42 50% 30%)","--state-key-verified":"hsl(330.2439024390244 50.20408163265306% 48.03921568627451%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":270,"unique":270,"expected":270},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":60750,"unique":60750,"expected":60750},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":72900,"unique":72900,"expected":72900}],"factorMaxima":[{"surface":"memory","best":48.282053187753654,"threshold":15,"feasible":270,"shippedMinimum":28.723129322326244,"changes":0},{"surface":"delete","best":14.631357904466427,"threshold":14.631357904466427,"feasible":0,"shippedMinimum":14.631357904466427,"changes":2},{"surface":"map","best":5.9942603943504995,"threshold":5.9942603943504995,"feasible":0,"shippedMinimum":5.9942603943504995,"changes":3},{"surface":"key","best":18.445796640599227,"threshold":15,"feasible":1930,"shippedMinimum":17.266563526815094,"changes":2}]}
{"theme":"Gilded","sizes":[18,15,18,15,15,18,18,18,18,18,18,12],"count":"446308403328000","feasible":"0","best":7.4977986569476665,"changes":10,"assignment":{"--state-mem-normal":"hsl(43 74% 47%)","--state-mem-over":"hsl(30 50% 30%)","--state-delete-unarmed":"hsl(43 40% 70%)","--state-delete-armed":"hsl(0 100% 50%)","--state-map-rest":"hsl(30 60% 60%)","--state-map-current":"hsl(45 55% 70%)","--state-map-selected":"hsl(43 74% 30%)","--state-map-hovered":"hsl(45 75% 50%)","--state-key-absent":"hsl(43 30% 70%)","--state-key-missing":"hsl(30 50% 45%)","--state-key-present":"hsl(43 40% 30%)","--state-key-verified":"hsl(43 94% 50%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":324,"unique":324,"expected":324},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":72900,"unique":72900,"expected":72900},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":87480,"unique":87480,"expected":87480}],"factorMaxima":[{"surface":"memory","best":43.175673440597784,"threshold":15,"feasible":150,"shippedMinimum":33.21169132170665,"changes":1},{"surface":"delete","best":12.156103621093418,"threshold":12.156103621093418,"feasible":0,"shippedMinimum":12.156103621093418,"changes":2},{"surface":"map","best":7.4977986569476665,"threshold":7.4977986569476665,"feasible":0,"shippedMinimum":7.4977986569476665,"changes":4},{"surface":"key","best":16.25619391235776,"threshold":15,"feasible":22,"shippedMinimum":16.15062592576154,"changes":3}]}
{"theme":"Vector","sizes":[12,15,5,15,15,12,18,5,5,12,18,12],"count":"2834352000000","feasible":"0","best":5.900185376139648,"changes":7,"assignment":{"--state-mem-normal":"hsl(185 100% 50%)","--state-mem-over":"hsl(200 90% 30%)","--state-delete-unarmed":"hsl(185 40% 55%)","--state-delete-armed":"hsl(350 80% 55%)","--state-map-rest":"hsl(200 90% 55%)","--state-map-current":"hsl(190 100% 50%)","--state-map-selected":"hsl(185 100% 70%)","--state-map-hovered":"hsl(190 90% 40%)","--state-key-absent":"hsl(185 30% 30%)","--state-key-missing":"hsl(200 90% 55%)","--state-key-present":"hsl(185 40% 50%)","--state-key-verified":"hsl(185 100% 70%)"},"coverage":[{"surface":"memory","roots":["--state-mem-normal","--state-mem-over"],"visited":60,"unique":60,"expected":60},{"surface":"delete","roots":["--state-delete-unarmed","--state-delete-armed"],"visited":216,"unique":216,"expected":216},{"surface":"map","roots":["--state-map-rest","--state-map-current","--state-map-selected","--state-map-hovered"],"visited":13500,"unique":13500,"expected":13500},{"surface":"key","roots":["--state-key-absent","--state-key-missing","--state-key-present","--state-key-verified"],"visited":16200,"unique":16200,"expected":16200}],"factorMaxima":[{"surface":"memory","best":41.81562267183395,"threshold":15,"feasible":36,"shippedMinimum":39.07275879212985,"changes":1},{"surface":"delete","best":23.28801782847145,"threshold":15,"feasible":156,"shippedMinimum":15.764553113030438,"changes":0},{"surface":"map","best":5.900185376139648,"threshold":5.900185376139648,"feasible":0,"shippedMinimum":5.900185376139648,"changes":3},{"surface":"key","best":11.468145729494452,"threshold":11.468145729494452,"feasible":0,"shippedMinimum":11.468145729494452,"changes":3}]}

 ✓ src/state-shades.test.ts (11 tests) 48624ms
   ✓ 777-S2 state shades > every_state_pair_is_measured_under_every_declared_media_condition 1256ms
   ✓ 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled 13239ms
   ✓ 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean 31981ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 1859ms

 Test Files  2 passed (2)
      Tests  16 passed (16)
   Start at  20:28:00
   Duration  50.28s (transform 57ms, setup 55ms, collect 1.29s, tests 48.63s, environment 334ms, prepare 93ms)

```

Codex, GPT-6.
