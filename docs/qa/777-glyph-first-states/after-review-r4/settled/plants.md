# Amendment 8: Nine Default-Condition Plants

The checked-in plants-default.mjs adapter reads the canonical ui/scripts/state-surfaces/plants.mjs plant list and mutates only a scratch UI copy. Emulation is default only: 1200×900, dark, reduced motion, deviceScaleFactor=4, file://, network aborted. The passing unplanted default control runs three production assertions (3 passed / 7 skipped); the full shipping suite independently passes all ten shade assertions across all 18 conditions.

Fresh diagnostics retain fingerprint verification, linear-mask measurement/real settled interaction checks, exact same-value witnesses and recorded-table checks. They omit the full-media certification guard and do not run a reduced-domain joint search. Partial receipts remain acceptanceComplete=false on disk. The diagnostic is outside the Tailwind source scan. Every stale check runs the unmodified production state-shades suite against the shipping receipt.

The media plant's original light prelude cannot affect the declared dark default. The adapter uses the prior round-3 dark prelude. An unqualified dark root initially lost to the later index.css declaration and produced a green fresh check; that ineffective attempt is retained in plants-ineffective-media.json. Qualifying the actual root as html.dark.theme-vector makes the override win the shipped cascade without !important. Only that effective retry counts as a negative proof.

The old R3 narrative named index.css for plants that actually target nexus-layout.css and gave a stale browser revision. The executed checked-in scripts/records below supersede that narrative. Chromium is 153.0.8010.12, Playwright 1.63.0; no revision guess is used.

## opaque-gradient-stop

Restored source and shipping receipt bytes: true. Fresh named failures: [' FAIL  plant-default.test.ts > 777-S2 state shades > browser_measurements_match_recorded_tables'].

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.2544503749999998 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  09:49:39
   Duration  955ms (transform 35ms, setup 28ms, collect 0ms, tests 0ms, environment 165ms, prepare 49ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 0; wall 235.726957958 seconds.

```text

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
Painted capture progress: renders=489; wall=48.810s
Painted capture progress: renders=920; wall=93.811s
Painted capture progress: renders=1829; wall=138.811s
Painted capture progress: renders=2789; wall=183.810s
Completed default/Vector; renders=2978; wall=192.646s
Painted capture progress: renders=3501; wall=228.811s
Completed default/Veil; renders=3516; wall=229.793s
Completed default/Gilded; renders=3556; wall=235.225s
Resolved painted state surfaces: renders=3556; wall=235.228s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/opaque-gradient-stop-capture/default.json; module graph=2095 inputs; SHA-256 2c7f55f40370369df0497b4ec7f00cd3754bd4d6da00e5ec6c785ec09a9b8134
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- plant-default -t 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled'
```

Exit 1; wall 3.583460333 seconds.

```text
+         0.6458712180118024,
        ],
        Array [
-         0.0822827071298148,
-         0.012983032342173012,
-         0.04375203521551294,
+         0.33053537564869656,
+         0.13690722308065364,
+         0.22394391219411838,
        ],
      ],
      "signatures": Array [
        "filled circle + circular ring",
        "filled square + square ring",
      ],
      "states": Array [
        "current",
        "selected",
      ],
      "surface": "map",
      "theme": "Veil",
    },
  ]

 ❯ plant-default.test.ts:421:49


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  1 failed | 2 passed | 7 skipped (10)
   Start at  09:53:37
   Duration  2.50s (transform 34ms, setup 42ms, collect 341ms, tests 1.61s, environment 334ms, prepare 35ms)
```

## theme-provider-opacity

Restored source and shipping receipt bytes: true. Fresh named failures: [' FAIL  plant-default.test.ts > 777-S2 state shades > browser_measurements_match_recorded_tables'].

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.22145875 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  09:53:50
   Duration  953ms (transform 35ms, setup 27ms, collect 0ms, tests 0ms, environment 165ms, prepare 26ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 0; wall 234.6889785 seconds.

```text

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
Painted capture progress: renders=491; wall=49.031s
Painted capture progress: renders=924; wall=94.032s
Painted capture progress: renders=1841; wall=139.034s
Painted capture progress: renders=2808; wall=184.035s
Completed default/Vector; renders=2987; wall=192.325s
Painted capture progress: renders=3514; wall=229.034s
Completed default/Veil; renders=3520; wall=229.339s
Completed default/Gilded; renders=3556; wall=234.155s
Resolved painted state surfaces: renders=3556; wall=234.158s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/theme-provider-opacity-capture/default.json; module graph=2095 inputs; SHA-256 785480f79efc529c86a3158cf15ae92afb30e29830ff2fa6860e195f96a85d49
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- plant-default -t 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled'
```

Exit 1; wall 2.6731832079999998 seconds.

```text
+         0.03189732311764592,
        ],
        Array [
-         0.0822827071298148,
-         0.012983032342173012,
-         0.04375203521551294,
+         0.01599629336550963,
+         0.006048833022857054,
+         0.01599629336550963,
        ],
      ],
      "signatures": Array [
        "filled circle + circular ring",
        "filled square + square ring",
      ],
      "states": Array [
        "current",
        "selected",
      ],
      "surface": "map",
      "theme": "Veil",
    },
  ]

 ❯ plant-default.test.ts:421:49


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  1 failed | 2 passed | 7 skipped (10)
   Start at  09:57:46
   Duration  2.41s (transform 36ms, setup 29ms, collect 328ms, tests 1.70s, environment 170ms, prepare 45ms)
```

## media-root-override

Restored source and shipping receipt bytes: true. Fresh named failures: [' FAIL  plant-default.test.ts > 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean', ' FAIL  plant-default.test.ts > 777-S2 state shades > browser_measurements_match_recorded_tables'].

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.226379292 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  10:02:23
   Duration  966ms (transform 38ms, setup 28ms, collect 0ms, tests 0ms, environment 168ms, prepare 29ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 0; wall 235.31631625 seconds.

```text

> nexus-ui@1.0.0 resolve-state-surfaces
> node scripts/resolve-state-surfaces.mjs

[33mThe CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
Browserslist: browsers data (caniuse-lite) is 12 months old. Please run:
  npx update-browserslist-db@latest
  Why you should do it regularly: https://github.com/browserslist/update-db#readme
node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js (9:18): Use of eval in "node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js" is strongly discouraged as it poses security risks and may cause issues with minification.
Resolving default/Vector…
Resolving default/Gilded…
Resolving default/Veil…
Painted capture progress: renders=490; wall=48.453s
Painted capture progress: renders=914; wall=93.455s
Painted capture progress: renders=1819; wall=138.455s
Painted capture progress: renders=2786; wall=183.455s
Completed default/Vector; renders=2985; wall=192.665s
Painted capture progress: renders=3502; wall=228.457s
Completed default/Veil; renders=3516; wall=229.362s
Completed default/Gilded; renders=3556; wall=234.812s
Resolved painted state surfaces: renders=3556; wall=234.814s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/media-root-override-capture/default.json; module graph=2095 inputs; SHA-256 46c7b83ef915e6ce6b5fd1a69c02ef2be0b93ea17773ff414710430ffc82e11c
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- plant-default -t 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled'
```

Exit 1; wall 2.525066959 seconds.

```text
        Array [
          0.002486117602200216,
          0.06834468904560749,
          0.09274617039318808,
        ],
        Array [
          0.048576475584514306,
          0.3373952729706493,
          0.38544957291933,
        ],
      ],
      "signatures": Array [
        "filled circle + circular ring",
        "filled square + square ring",
      ],
      "states": Array [
        "current",
        "selected",
      ],
      "surface": "map",
      "theme": "Vector",
    },
  ]

 ❯ plant-default.test.ts:421:49


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[2/2]⎯

 Test Files  1 failed (1)
      Tests  2 failed | 1 passed | 7 skipped (10)
   Start at  10:06:19
   Duration  2.20s (transform 34ms, setup 41ms, collect 351ms, tests 1.31s, environment 260ms, prepare 107ms)
```

## optional-row-opacity

Restored source and shipping receipt bytes: true. Fresh named failures: [' FAIL  plant-default.test.ts > 777-S2 state shades > browser_measurements_match_recorded_tables'].

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.236425291 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  10:06:35
   Duration  969ms (transform 34ms, setup 27ms, collect 0ms, tests 0ms, environment 162ms, prepare 50ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 0; wall 236.106311083 seconds.

```text

> nexus-ui@1.0.0 resolve-state-surfaces
> node scripts/resolve-state-surfaces.mjs

[33mThe CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
Browserslist: browsers data (caniuse-lite) is 12 months old. Please run:
  npx update-browserslist-db@latest
  Why you should do it regularly: https://github.com/browserslist/update-db#readme
node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js (9:18): Use of eval in "node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js" is strongly discouraged as it poses security risks and may cause issues with minification.
Resolving default/Gilded…
Resolving default/Veil…
Resolving default/Vector…
Painted capture progress: renders=490; wall=48.623s
Painted capture progress: renders=924; wall=93.625s
Painted capture progress: renders=1838; wall=138.625s
Painted capture progress: renders=2781; wall=183.625s
Completed default/Vector; renders=2980; wall=192.878s
Painted capture progress: renders=3495; wall=228.626s
Completed default/Veil; renders=3514; wall=229.842s
Completed default/Gilded; renders=3556; wall=235.552s
Resolved painted state surfaces: renders=3556; wall=235.563s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/optional-row-opacity-capture/default.json; module graph=2095 inputs; SHA-256 b4675b5a3427a009466e2d9446ef3ea4e2c9f2105d0169524c0eaab66e0c9474
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- plant-default -t 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled'
```

Exit 1; wall 2.578077042 seconds.

```text
        Array [
          0.21700841559070722,
          0.07368100666348679,
          0.1467179657273705,
        ],
        Array [
          0.0822827071298148,
          0.012983032342173012,
          0.04375203521551294,
        ],
      ],
      "signatures": Array [
        "filled circle + circular ring",
        "filled square + square ring",
      ],
      "states": Array [
        "current",
        "selected",
      ],
      "surface": "map",
      "theme": "Veil",
    },
  ]

 ❯ plant-default.test.ts:421:49


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  1 failed | 2 passed | 7 skipped (10)
   Start at  10:10:32
   Duration  2.30s (transform 34ms, setup 28ms, collect 319ms, tests 1.60s, environment 172ms, prepare 56ms)
```

## theme-backdrop

Restored source and shipping receipt bytes: true. Fresh named failures: [' FAIL  plant-default.test.ts > 777-S2 state shades > browser_measurements_match_recorded_tables'].

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.264227666 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  10:10:39
   Duration  993ms (transform 36ms, setup 28ms, collect 0ms, tests 0ms, environment 163ms, prepare 27ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 0; wall 235.18331408299997 seconds.

```text

> nexus-ui@1.0.0 resolve-state-surfaces
> node scripts/resolve-state-surfaces.mjs

[33mThe CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
Browserslist: browsers data (caniuse-lite) is 12 months old. Please run:
  npx update-browserslist-db@latest
  Why you should do it regularly: https://github.com/browserslist/update-db#readme
node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js (9:18): Use of eval in "node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js" is strongly discouraged as it poses security risks and may cause issues with minification.
Resolving default/Gilded…
Resolving default/Veil…
Resolving default/Vector…
Painted capture progress: renders=490; wall=48.604s
Painted capture progress: renders=922; wall=93.603s
Painted capture progress: renders=1837; wall=138.603s
Painted capture progress: renders=2795; wall=183.603s
Completed default/Vector; renders=2980; wall=192.153s
Painted capture progress: renders=3505; wall=228.605s
Completed default/Veil; renders=3516; wall=229.366s
Completed default/Gilded; renders=3556; wall=234.647s
Resolved painted state surfaces: renders=3556; wall=234.649s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/theme-backdrop-capture/default.json; module graph=2095 inputs; SHA-256 1707e56038c7c798b91086ec8bac1dc919ba860f8ea9b5306006c8b9450536f2
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- plant-default -t 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled'
```

Exit 1; wall 2.5560420830000004 seconds.

```text
        Array [
          0.002486117602200216,
          0.06834468904560749,
          0.09274617039318808,
        ],
        Array [
          0.048576475584514306,
          0.3373952729706493,
          0.38544957291933,
        ],
      ],
      "signatures": Array [
        "filled circle + circular ring",
        "filled square + square ring",
      ],
      "states": Array [
        "current",
        "selected",
      ],
      "surface": "map",
      "theme": "Vector",
    },
  ]

 ❯ plant-default.test.ts:421:49


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  1 failed | 2 passed | 7 skipped (10)
   Start at  10:14:35
   Duration  2.29s (transform 35ms, setup 28ms, collect 326ms, tests 1.60s, environment 163ms, prepare 31ms)
```

## important-state-surface

Restored source and shipping receipt bytes: true. Fresh named failures: [' FAIL  plant-default.test.ts > 777-S2 state shades > painted_mask_means_are_linear_and_interactions_are_real_and_settled', ' FAIL  plant-default.test.ts > 777-S2 state shades > same_value_has_exactly_the_same_settled_mask_mean', ' FAIL  plant-default.test.ts > 777-S2 state shades > browser_measurements_match_recorded_tables'].

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.2191295839999998 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  10:14:44
   Duration  963ms (transform 35ms, setup 29ms, collect 0ms, tests 0ms, environment 164ms, prepare 57ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 0; wall 215.881437375 seconds.

```text

> nexus-ui@1.0.0 resolve-state-surfaces
> node scripts/resolve-state-surfaces.mjs

[33mThe CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
Browserslist: browsers data (caniuse-lite) is 12 months old. Please run:
  npx update-browserslist-db@latest
  Why you should do it regularly: https://github.com/browserslist/update-db#readme
node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js (9:18): Use of eval in "node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js" is strongly discouraged as it poses security risks and may cause issues with minification.
Resolving default/Veil…
Resolving default/Gilded…
Resolving default/Vector…
Painted capture progress: renders=588; wall=48.422s
Painted capture progress: renders=1298; wall=93.424s
Painted capture progress: renders=2227; wall=138.423s
Completed default/Vector; renders=2985; wall=173.445s
Painted capture progress: renders=3130; wall=183.423s
Completed default/Veil; renders=3518; wall=210.357s
Completed default/Gilded; renders=3556; wall=215.389s
Resolved painted state surfaces: renders=3556; wall=215.391s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/important-state-surface-capture/default.json; module graph=2095 inputs; SHA-256 e4ef563958009bfefd17ae6d575e0711b0020a923abe8bb99c50f4bb7507187f
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- plant-default -t 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled'
```

Exit 1; wall 1.103971 seconds.

```text
        Array [
          0.21700841559070722,
          0.07368100666348679,
          0.1467179657273705,
        ],
        Array [
          0.0822827071298148,
          0.012983032342173012,
          0.04375203521551294,
        ],
      ],
      "signatures": Array [
        "filled circle + circular ring",
        "filled square + square ring",
      ],
      "states": Array [
        "current",
        "selected",
      ],
      "surface": "map",
      "theme": "Veil",
    },
  ]

 ❯ plant-default.test.ts:421:49


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[3/3]⎯

 Test Files  1 failed (1)
      Tests  3 failed | 7 skipped (10)
   Start at  10:18:21
   Duration  849ms (transform 35ms, setup 30ms, collect 330ms, tests 141ms, environment 166ms, prepare 43ms)
```

## has-state-surface

Restored source and shipping receipt bytes: true. Fresh named failures: [' FAIL  plant-default.test.ts > 777-S2 state shades > browser_measurements_match_recorded_tables'].

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.1301803750000001 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  10:20:14
   Duration  892ms (transform 33ms, setup 25ms, collect 0ms, tests 0ms, environment 157ms, prepare 27ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 0; wall 234.714312333 seconds.

```text

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
Painted capture progress: renders=491; wall=48.295s
Painted capture progress: renders=923; wall=93.295s
Painted capture progress: renders=1832; wall=138.296s
Painted capture progress: renders=2798; wall=183.296s
Completed default/Vector; renders=2980; wall=191.756s
Painted capture progress: renders=3508; wall=228.297s
Completed default/Veil; renders=3516; wall=228.788s
Completed default/Gilded; renders=3556; wall=234.219s
Resolved painted state surfaces: renders=3556; wall=234.222s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/has-state-surface-capture/default.json; module graph=2095 inputs; SHA-256 0ce91c7f8c18769c385a96b74e7afdf5fb98b9b04dc94ca442cefa413ed80dec
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- plant-default -t 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled'
```

Exit 1; wall 2.517490167 seconds.

```text
        Array [
          0.21700841559070722,
          0.07368100666348679,
          0.1467179657273705,
        ],
        Array [
          0.0822827071298148,
          0.012983032342173012,
          0.04375203521551294,
        ],
      ],
      "signatures": Array [
        "filled circle + circular ring",
        "filled square + square ring",
      ],
      "states": Array [
        "current",
        "selected",
      ],
      "surface": "map",
      "theme": "Veil",
    },
  ]

 ❯ plant-default.test.ts:421:49


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  1 failed | 2 passed | 7 skipped (10)
   Start at  10:24:10
   Duration  2.27s (transform 33ms, setup 26ms, collect 322ms, tests 1.59s, environment 158ms, prepare 47ms)
```

## map-blend

Restored source and shipping receipt bytes: true. Fresh named failures: [' FAIL  plant-default.test.ts > 777-S2 state shades > browser_measurements_match_recorded_tables'].

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.173430042 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  10:24:16
   Duration  920ms (transform 33ms, setup 26ms, collect 0ms, tests 0ms, environment 155ms, prepare 27ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 0; wall 233.940218833 seconds.

```text

> nexus-ui@1.0.0 resolve-state-surfaces
> node scripts/resolve-state-surfaces.mjs

[33mThe CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.[39m
[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
Browserslist: browsers data (caniuse-lite) is 12 months old. Please run:
  npx update-browserslist-db@latest
  Why you should do it regularly: https://github.com/browserslist/update-db#readme
node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js (9:18): Use of eval in "node_modules/@arwes/frames/build/esm/internal/formatFrameDimension.js" is strongly discouraged as it poses security risks and may cause issues with minification.
Resolving default/Vector…
Resolving default/Gilded…
Resolving default/Veil…
Painted capture progress: renders=490; wall=48.334s
Painted capture progress: renders=925; wall=93.334s
Painted capture progress: renders=1842; wall=138.335s
Painted capture progress: renders=2809; wall=183.336s
Completed default/Vector; renders=2983; wall=191.414s
Painted capture progress: renders=3515; wall=228.337s
Completed default/Veil; renders=3519; wall=228.578s
Completed default/Gilded; renders=3556; wall=233.446s
Resolved painted state surfaces: renders=3556; wall=233.450s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/map-blend-capture/default.json; module graph=2095 inputs; SHA-256 77653ec3d5c8e4db01e0ba68ed713523b68c0ee4402c620843b392f636b214b1
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- plant-default -t 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled'
```

Exit 1; wall 2.4842085 seconds.

```text
        Array [
          0.21700841559070722,
          0.07368100666348679,
          0.1467179657273705,
        ],
        Array [
          0.0822827071298148,
          0.012983032342173012,
          0.04375203521551294,
        ],
      ],
      "signatures": Array [
        "filled circle + circular ring",
        "filled square + square ring",
      ],
      "states": Array [
        "current",
        "selected",
      ],
      "surface": "map",
      "theme": "Veil",
    },
  ]

 ❯ plant-default.test.ts:421:49


⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  1 failed | 2 passed | 7 skipped (10)
   Start at  10:28:12
   Duration  2.23s (transform 33ms, setup 27ms, collect 320ms, tests 1.55s, environment 169ms, prepare 39ms)
```

## key-overpainting-shadow

Restored source and shipping receipt bytes: true. Fresh named failures: named empty foreground-mask measurement failure.

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui test -- state-shades
```

Exit 1; wall 1.178712708 seconds.

```text

> nexus-ui@1.0.0 test
> vitest run state-shades


 RUN  v2.1.9 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/client

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ❯ src/state-shades.test.ts (0 test)

⎯⎯⎯⎯⎯⎯ Failed Suites 1 ⎯⎯⎯⎯⎯⎯⎯

 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:164:9
    162|   [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.m…
    163| if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
    164|   throw new Error("Stale browser-resolved state surfaces: run npm --pr…
       |         ^
    165| if (receipt.proof.acceptanceComplete !== true)
    166|   throw new Error("Incomplete painted state surfaces: filtered/probe c…

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯

 Test Files  1 failed (1)
      Tests  no tests
   Start at  10:28:18
   Duration  932ms (transform 34ms, setup 27ms, collect 0ms, tests 0ms, environment 159ms, prepare 36ms)
```

```sh
npm --prefix /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui run resolve-state-surfaces
```

Exit 1; wall 112.89469825 seconds.

```text

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
Painted capture progress: renders=493; wall=48.433s
Painted capture progress: renders=928; wall=93.434s
Incomplete painted probe: renders=1318; wall=112.410s; acceptanceComplete=false
file:///private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/scripts/state-surfaces/png.mjs:72
  if (!maskSize) throw new Error(`Measurement failure ${label}: empty foreground mask`);
                       ^

Error: Measurement failure default/Vector/candidate/key/optional/rest/present/hsl(185 50% 50%): empty foreground mask
    at foreground (file:///private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/scripts/state-surfaces/png.mjs:72:24)
    at sample (file:///private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/scripts/resolve-state-surfaces.mjs:164:24)
    at async captureValues (file:///private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/scripts/resolve-state-surfaces.mjs:237:28)
    at async file:///private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/scripts/resolve-state-surfaces.mjs:281:11
    at async Promise.all (index 2)
    at async file:///private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/scripts/resolve-state-surfaces.mjs:81:5
    at async Promise.all (index 0)
    at async file:///private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/settled/default-plants/plant-copy/ui/scripts/resolve-state-surfaces.mjs:77:3

Node.js v24.3.0
```

Codex, GPT-6.
