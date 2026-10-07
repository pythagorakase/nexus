# STOP-REPORT: 777-S2 Joint Shade Constraints

Date: 2026-10-01. Starting commit: `8ccd3008a48bdf8115232667399868e2bdf66f93`. Branch: `claude/777-glyph-first-states`.

**Disposition: STOP.** Required item 5 has no admissible Vector palette in its finite domain. Product code and styles remain unchanged. This is the ordered escape hatch, not a completed implementation or a passing feature gate. No PR, push or merge was performed.

## Why the Frozen Order Cannot Be Satisfied

The order requires every reachable pair to meet deutan ΔE ≥ 15. An exception is permitted only when the exhaustive individual pair maximum is below 15. Every one of Vector's six opaque map-fill pairs individually reaches 15. Nevertheless, the exhaustive Cartesian product of all four map roots has **zero jointly satisfying assignments**. Its best possible minimum pair distance is **12.49178898372119**. Thus a below-threshold pair remains in every permitted palette, and none of those pairs admits the specified exception.

This subset alone proves incompatibility: adding the memory, deletion, key, sidebar-opacity or ring constraints cannot create a solution to an already unsatisfiable subset. No conclusion of continuous-family impossibility is made. The search includes the proposed independent `--map-hovered` split even though no such token has been shipped on this branch.

For opaque interior fills, production compositing has α = 1; the foreground completely replaces any sea, land or sidebar backdrop. Neither the `--brass`-dependent land mix nor another background root influences this subset. All four influencing roots are searched jointly. Linked aliases do not add independent degrees of freedom. Rings, glows and antialiased edge pixels are not used to excuse a shortfall in the required fill-color pair.

## Fixed Method and Reference Check

Normalized sRGB is linearized with the IEC sRGB transfer function; the Machado–Oliveira–Fernandes deutan severity-1.0 matrix is applied in linear light; results are clipped to [0,1]; D65 XYZ/CIELAB is computed with reference white (0.95047, 1, 1.08883); CIEDE2000 uses kL=kC=kH=1. The helper passes all 34 independently typed Sharma supplementary reference vectors within 0.00005. Floating-point values are retained for decisions and search maxima. RGB values displayed below are rounded only for presentation.

- [Machado, Oliveira and Fernandes paper](https://profs.ic.uff.br/~laffernandes/content/publications/journal/2009_tvcg_15%286%29/machado_oliveira_fernandes-tvcg-15%286%29-2009-corrected.pdf).
- [Author-published simulation matrices](https://www.inf.ufrgs.br/~oliveira/pubs_files/CVD_Simulation/CVD_Simulation.html), deuteranomaly, severity 1.0. The downloaded table contains the helper's nine coefficients.
- [Sharma reference vectors](https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/dataNprograms/ciede2000testdata.txt), typed as literals in the test; expectations are not produced by the helper.

## Candidate Domain

The baseline CSS is read with `git show 8ccd3008a48bdf8115232667399868e2bdf66f93:ui/client/src/index.css`, then parsed with PostCSS. Duplicate saturations and lightness values are removed. Veil's fixed anchor and exact-anchor hue are honored in its search.

| Vector State | Root | Baseline HSL | Hue | Saturation Candidates (%) | Lightness Candidates (%) | Count |
|---|---|---|---:|---|---|---:|
| rest | `--bronze` | 200 90% 55% | 200 | 90, 100 | 55, 30, 40, 50, 60, 70 | 12 |
| current | `--brass-bright` | 190 80% 60% | 190 | 80, 90, 100 | 60, 30, 40, 50, 70 | 15 |
| selected | `--brass` | 185 100% 50% | 185 | 100 | 50, 30, 40, 60, 70 | 5 |
| hovered | proposed `--map-hovered` | baseline `--brass-bright` | 190 | 80, 90, 100 | 60, 30, 40, 50, 70 | 15 |

## Exhaustive Joint Search

| Theme | Domain Sizes (rest/current/selected/hovered) | Assignments Examined | Satisfying Assignments | Best Minimum ΔE |
|---|---|---:|---:|---:|
| Veil | 15 × 15 × 1 × 15 | 3375 | 180 | 15.618186802122327 |
| Gilded | 18 × 15 × 18 × 15 | 72900 | 2 | 15.734719451085242 |
| Vector | 12 × 15 × 5 × 15 | 13500 | 0 | 12.49178898372119 |

Veil and Gilded counts refer only to this opaque-fill subset; they are not claims that their complete feature gates are feasible or passed.

## Complete Six-Pair Search Table for Each Theme

Each row exhausts every candidate of both influencing roots. HSL witnesses use `[hue, saturation %, lightness %]`. A fixed Veil anchor is shown as hex.

| Theme | State Pair | Maximum Unrounded ΔE | Candidate Count | Maximizing Candidates |
|---|---|---:|---:|---|
| Veil | rest / current | 46.9393789806122 | 225 | `[15, 95, 70]` / `[330.2439024390244, 60, 30]` |
| Veil | rest / selected | 31.77890102995034 | 15 | `[15, 95, 70]` / `#b83d7a` |
| Veil | rest / hovered | 46.9393789806122 | 225 | `[15, 95, 70]` / `[330.2439024390244, 60, 30]` |
| Veil | current / selected | 17.854502924461286 | 15 | `[330.2439024390244, 60, 70]` / `#b83d7a` |
| Veil | current / hovered | 37.60960617716947 | 225 | `[330.2439024390244, 60, 30]` / `[330.2439024390244, 60, 70]` |
| Veil | selected / hovered | 17.854502924461286 | 15 | `#b83d7a` / `[330.2439024390244, 60, 70]` |
| Gilded | rest / current | 41.679314201124186 | 270 | `[30, 50, 30]` / `[45, 75, 70]` |
| Gilded | rest / selected | 43.366319139940046 | 324 | `[30, 50, 30]` / `[43, 94, 70]` |
| Gilded | rest / hovered | 41.679314201124186 | 270 | `[30, 50, 30]` / `[45, 75, 70]` |
| Gilded | current / selected | 36.62488523858307 | 270 | `[45, 55, 30]` / `[43, 94, 70]` |
| Gilded | current / hovered | 35.0132015742976 | 225 | `[45, 55, 30]` / `[45, 75, 70]` |
| Gilded | selected / hovered | 36.62488523858307 | 270 | `[43, 94, 70]` / `[45, 55, 30]` |
| Vector | rest / current | 39.36886922076322 | 180 | `[200, 90, 30]` / `[190, 100, 70]` |
| Vector | rest / selected | 41.68905520762976 | 60 | `[200, 90, 30]` / `[185, 100, 70]` |
| Vector | rest / hovered | 39.36886922076322 | 180 | `[200, 90, 30]` / `[190, 100, 70]` |
| Vector | current / selected | 35.28699590725341 | 75 | `[190, 80, 30]` / `[185, 100, 70]` |
| Vector | current / hovered | 33.23977102083307 | 225 | `[190, 80, 30]` / `[190, 100, 70]` |
| Vector | selected / hovered | 35.28699590725341 | 75 | `[185, 100, 70]` / `[190, 80, 30]` |

## Vector Best Joint Witness: Diagnostic Only, Not Shipped

The maximizing joint witness is rest `hsl(200 100% 60%)`, current `hsl(190 80% 30%)`, selected `hsl(185 100% 60%)`, hovered `hsl(190 80% 40%)`. Its respective RGB values in [0,255] are (51,187,255), (15.3,117.3,137.7), (51,238,255), (20.4,156.4,183.6). This witness retains the required cyan/blue families and is still inadmissible.

| State Pair | Joint Witness ΔE | Individual Maximum ΔE | Exception Admissible? |
|---|---:|---:|---|
| rest / current | 25.852305167006655 | 39.36886922076322 | No |
| rest / selected | 13.097148319792739 | 41.68905520762976 | No |
| rest / hovered | 12.49178898372119 | 39.36886922076322 | No |
| current / selected | 33.758254191230165 | 35.28699590725341 | No |
| current / hovered | 13.994396296541595 | 33.23977102083307 | No |
| selected / hovered | 20.37619893837457 | 35.28699590725341 | No |

## Complete 14-Pair Opaque Base Inventory Per Theme

Before and after production RGB/ΔE are identical because no product palette is changed. These are opaque interior token measurements, not the omitted opacity-context acceptance proof. Mappings are read from production CSS declarations and `MapPane.tsx`'s `PIN_COLOR`, including the unchanged current/hovered alias. The JSON preserves unrounded RGB channels and ΔE.

| Theme | Surface | State Pair | Before = After RGB A (0–255) | Before = After RGB B (0–255) | Before = After ΔE |
|---|---|---|---|---|---:|
| Veil | memory | normal / over | (189.720, 55.080, 144.840) | (229.500, 114.750, 76.500) | 38.002783748871494 |
| Veil | delete | unarmed / armed | (192.525, 176.460, 138.975) | (210.375, 44.625, 44.625) | 20.80376452918997 |
| Veil | map | rest / current | (229.500, 114.750, 76.500) | (214.200, 91.800, 173.400) | 36.519036034009964 |
| Veil | map | rest / selected | (229.500, 114.750, 76.500) | (189.720, 55.080, 144.840) | 38.002783748871494 |
| Veil | map | rest / hovered | (229.500, 114.750, 76.500) | (214.200, 91.800, 173.400) | 36.519036034009964 |
| Veil | map | current / selected | (214.200, 91.800, 173.400) | (189.720, 55.080, 144.840) | 9.571575278395933 |
| Veil | map | current / hovered | (214.200, 91.800, 173.400) | (214.200, 91.800, 173.400) | 0 |
| Veil | map | selected / hovered | (189.720, 55.080, 144.840) | (214.200, 91.800, 173.400) | 9.571575278395933 |
| Veil | key | optional-absent / required-missing | (153.000, 137.700, 102.000) | (229.500, 114.750, 76.500) | 10.828932806147856 |
| Veil | key | optional-absent / present | (153.000, 137.700, 102.000) | (192.525, 176.460, 138.975) | 11.904163763235427 |
| Veil | key | optional-absent / verified | (153.000, 137.700, 102.000) | (189.720, 55.080, 144.840) | 28.357466144039577 |
| Veil | key | required-missing / present | (229.500, 114.750, 76.500) | (192.525, 176.460, 138.975) | 11.447234141252315 |
| Veil | key | required-missing / verified | (229.500, 114.750, 76.500) | (189.720, 55.080, 144.840) | 38.002783748871494 |
| Veil | key | present / verified | (192.525, 176.460, 138.975) | (189.720, 55.080, 144.840) | 33.74473623257419 |
| Gilded | memory | normal / over | (208.539, 158.282, 31.161) | (172.125, 114.750, 57.375) | 14.337990382173535 |
| Gilded | delete | unarmed / armed | (181.560, 153.816, 83.640) | (195.075, 34.425, 34.425) | 17.039081906673687 |
| Gilded | map | rest / current | (172.125, 114.750, 57.375) | (209.100, 181.050, 96.900) | 16.800428551875378 |
| Gilded | map | rest / selected | (172.125, 114.750, 57.375) | (208.539, 158.282, 31.161) | 14.337990382173535 |
| Gilded | map | rest / hovered | (172.125, 114.750, 57.375) | (209.100, 181.050, 96.900) | 16.800428551875378 |
| Gilded | map | current / selected | (209.100, 181.050, 96.900) | (208.539, 158.282, 31.161) | 6.961704626353169 |
| Gilded | map | current / hovered | (209.100, 181.050, 96.900) | (209.100, 181.050, 96.900) | 0 |
| Gilded | map | selected / hovered | (208.539, 158.282, 31.161) | (209.100, 181.050, 96.900) | 6.961704626353169 |
| Gilded | key | optional-absent / required-missing | (132.600, 115.260, 71.400) | (172.125, 114.750, 57.375) | 7.72892192098335 |
| Gilded | key | optional-absent / present | (132.600, 115.260, 71.400) | (181.560, 153.816, 83.640) | 15.32055288939221 |
| Gilded | key | optional-absent / verified | (132.600, 115.260, 71.400) | (208.539, 158.282, 31.161) | 21.598012943420677 |
| Gilded | key | required-missing / present | (172.125, 114.750, 57.375) | (181.560, 153.816, 83.640) | 9.20305994887555 |
| Gilded | key | required-missing / verified | (172.125, 114.750, 57.375) | (208.539, 158.282, 31.161) | 14.337990382173535 |
| Gilded | key | present / verified | (181.560, 153.816, 83.640) | (208.539, 158.282, 31.161) | 8.084904016113446 |
| Vector | memory | normal / over | (0.000, 233.750, 255.000) | (36.975, 174.675, 243.525) | 14.40404073730409 |
| Vector | delete | unarmed / armed | (94.350, 178.500, 186.150) | (232.050, 48.450, 79.050) | 34.19818261757641 |
| Vector | map | rest / current | (36.975, 174.675, 243.525) | (71.400, 207.400, 234.600) | 10.395684302399912 |
| Vector | map | rest / selected | (36.975, 174.675, 243.525) | (0.000, 233.750, 255.000) | 14.40404073730409 |
| Vector | map | rest / hovered | (36.975, 174.675, 243.525) | (71.400, 207.400, 234.600) | 10.395684302399912 |
| Vector | map | current / selected | (71.400, 207.400, 234.600) | (0.000, 233.750, 255.000) | 4.965188543168605 |
| Vector | map | current / hovered | (71.400, 207.400, 234.600) | (71.400, 207.400, 234.600) | 0 |
| Vector | map | selected / hovered | (0.000, 233.750, 255.000) | (71.400, 207.400, 234.600) | 4.965188543168605 |
| Vector | key | optional-absent / required-missing | (71.400, 127.500, 132.600) | (36.975, 174.675, 243.525) | 21.78575194244601 |
| Vector | key | optional-absent / present | (71.400, 127.500, 132.600) | (94.350, 178.500, 186.150) | 16.28884750990673 |
| Vector | key | optional-absent / verified | (71.400, 127.500, 132.600) | (0.000, 233.750, 255.000) | 28.837735721157593 |
| Vector | key | required-missing / present | (36.975, 174.675, 243.525) | (94.350, 178.500, 186.150) | 13.513540821543312 |
| Vector | key | required-missing / verified | (36.975, 174.675, 243.525) | (0.000, 233.750, 255.000) | 14.40404073730409 |
| Vector | key | present / verified | (94.350, 178.500, 186.150) | (0.000, 233.750, 255.000) | 13.427931019604726 |

## Current-Behavior Evidence

- `ui/client/src/index.css:754-759`: Vector root HSL values for the candidate domain.
- `ui/client/src/components/nexus/MapPane.tsx:483-497`: actual current > selected > hovered > rest precedence and token mapping; current and hovered alias `--brass-bright` before implementation.
- `ui/client/src/components/nexus/MapPane.tsx:677-697`: opaque filled-circle pins and 0.6-opacity outline rings. Required item 2 would replace geometry while retaining opaque fills.
- `ui/client/src/components/nexus/nexus-layout.css:1200-1214`: canvas sea/land backgrounds, including the 16% brass land mix; these cannot affect an opaque interior fill.
- `ui/client/src/state-shades.test.ts`: baseline extraction, deduplicated candidate construction, all six independent pair searches and the full Cartesian-product loop; the Vector assertion explicitly checks all six maxima ≥ 15, zero solutions and the best minimum.
- `ui/client/src/state-shades-measurement.ts`: fixed simulation matrix, transfer functions, D65 Lab and unit-weight CIEDE2000.

## Shadcn Check Before Any UI Addition

On 2026-10-01, crawled [Progress](https://ui.shadcn.com/docs/components/base/progress), [Alert](https://ui.shadcn.com/docs/components/base/alert), [Button](https://ui.shadcn.com/docs/components/base/button), [Badge](https://ui.shadcn.com/docs/components/base/badge), and [Marker](https://ui.shadcn.com/docs/components/base/marker), including the component catalog. Progress provides a completion indicator; Alert provides a container with title/description slots; Button provides the existing action surface pattern; Badge wraps an icon/content in a badge; Marker is a conversation-status row or separator, not a geographic pin. None supplies the prescribed small glyph replacements or four inverse-zoom pin geometries without replacing an existing surface. Lucide and a local SVG renderer would fit the order. No component was installed, and no UI element was added before or after the stop.

## Commands and Verbatim Tails

All commands ran from the designated worktree. `npm --prefix ui ci` installed real local dependencies, with no node_modules symlink. Its tail reported `added 957 packages, and audited 958 packages in 4s` and `27 vulnerabilities (2 low, 8 moderate, 16 high, 1 critical)`; no dependency repair was attempted.

Import proof:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/nexus/__init__.py
```

Numerical preflight (four tests; not the feature gate):

```text
STATE_SHADES_EVIDENCE_DIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2 npm --prefix ui test -- state-shades
{"theme":"Vector","sizes":[12,15,5,15],"total":13500,"feasible":0,"best":12.49178898372119,"bestWitness":[[200,100,60],[190,80,30],[185,100,60],[190,80,40]],"bestWitnessRgb":[[0.19999999999999996,0.7333333333333328,1],[0.06,0.4600000000000003,0.54],[0.19999999999999996,0.9333333333333329,1],[0.07999999999999996,0.6133333333333337,0.7200000000000001]],"bestWitnessPairs":[{"states":["rest","current"],"delta":25.852305167006655},{"states":["rest","selected"],"delta":13.097148319792739},{"states":["rest","hovered"],"delta":12.49178898372119},{"states":["current","selected"],"delta":33.758254191230165},{"states":["current","hovered"],"delta":13.994396296541595},{"states":["selected","hovered"],"delta":20.37619893837457}],"maxima":[{"pair":["--bronze","--brass-bright"],"states":["rest","current"],"maximum":39.36886922076322,"count":180,"witness":[[200,90,30],[190,100,70]]},{"pair":["--bronze","--brass"],"states":["rest","selected"],"maximum":41.68905520762976,"count":60,"witness":[[200,90,30],[185,100,70]]},{"pair":["--bronze","--map-hovered"],"states":["rest","hovered"],"maximum":39.36886922076322,"count":180,"witness":[[200,90,30],[190,100,70]]},{"pair":["--brass-bright","--brass"],"states":["current","selected"],"maximum":35.28699590725341,"count":75,"witness":[[190,80,30],[185,100,70]]},{"pair":["--brass-bright","--map-hovered"],"states":["current","hovered"],"maximum":33.23977102083307,"count":225,"witness":[[190,80,30],[190,100,70]]},{"pair":["--brass","--map-hovered"],"states":["selected","hovered"],"maximum":35.28699590725341,"count":75,"witness":[[185,100,70],[190,80,30]]}]}


 Test Files  1 passed (1)
      Tests  4 passed (4)
   Start at  06:03:28
   Duration  527ms (transform 23ms, setup 25ms, collect 30ms, tests 166ms, environment 150ms, prepare 35ms)

```

Owner-target guard:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_owner_target_guard.py
........................................................................ [ 90%]
........                                                                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
80 passed in 2.67s
```

UI check:

```text
npm --prefix ui run check

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

```

Black, flake8 and mypy: not applicable; no Python files changed. No new script path or classification row.

## Work Not Performed After the Ordered Stop

No product glyphs, shade tuning, motion-guard change, spec change, narrow-width work, application/gateway run, database connection, inference or key-store action. Owner-target audit reports zero targets. No browser glyph capture or before/after swatch artifact was created because no after-palette or glyph implementation exists. No exception was accepted.

The full 14-pair **opacity-context** acceptance table, static render-signature acceptance, restored-exclusion red plant, emitted-CSS inspection, component interaction tests, full UI suite/build, offline Python suites and reachability gate were not run. They remain required for a revised implementation order. The complete 42-row opaque base table above is not represented as that omitted acceptance proof.

No rebase/push/PR: the prerequisite before any push is a rebase onto newest origin/main; there was no push. Evidence is committed locally for the coordinator to inspect.

## Coordinator Question

Will the coordinator reissue 777-S2 with jointly satisfiable finite shade constraints or an explicit joint-incompatibility disposition? This is a work-order constraint question. The owner's settled hue-family model, exact Veil anchor and bottom-rail ruling are preserved; no owner decision is reopened.

Prepared by Codex, GPT-6.

## Accepted Amendment and Resumed Implementation — 2026-10-01

The coordinator accepted the stop above and amended item 5 to a **joint, per-theme** exception criterion (`777-S2-amendment.md`). The stop-report and evidence in `a5d63ddf` are retained. The implementation resumes from that commit without rewriting it. Starting shade-domain commit remains `8ccd3008a48bdf8115232667399868e2bdf66f93`.

All seven implementation items are now represented in source: meter/delete glyphs, a shared four-shape map renderer, exported key glyph renderer, motion guard, domain-constrained theme shades, spec sections 3.1/3.2, and resumed evidence. Final gates, swatches and rebase/push receipt are appended below as they complete. No owner's color-model or bottom-rail ruling is reopened.

The prior shadcn check above precedes these new glyph elements. Progress, Alert, Button, Badge and Marker were checked; none supplies the ordered geometry within the existing surfaces. Existing Lucide imports and local SVG are used, with no installed component, dependency, label, legend, tooltip or control.

The full joint search uses exact finite-domain variable elimination, not random sampling: for fixed brass/bronze/fg-muted, the map current/hovered, key fg-dim and delete destructive assignments are independent. Every factor assignment is enumerated; maximizing each conditional minimum and then combining them represents every full Cartesian assignment. The second pass selects the fewest changed roots at the global optimum. The test recomputes from CSS and the fixed domain, not stored JSON. Individual pair/context maxima are retained in the JSON along with full witnesses and factor assignment counts. The previous map-fill-only maxima remain historical context.

The compositing convention samples opaque interiors and static ring strokes with animations disabled; it excludes edge antialiasing and glow halos. Ready-row glyphs are first composited into `--bg-elev-3`, then the whole exceeds-RAM row at .35 into its provider's `--bg`. Required/optional presence and verification are measured at rest/hover/focus. Canvas sea and land rings use .6 opacity. Sidebar backgrounds include the content wash's zero and maximum .07 endpoints, row hover, selected and current-plus-selected backgrounds. Each theme has 139 pair/context measurements, including all 14 base pairs. CSS compositing occurs before linearization and deutan simulation.

| Theme | Root Domain Sizes (brass, bronze, current, hovered, fg-muted, fg-dim, destructive) | Full Assignments | Satisfying | Maximum Minimum ΔE | Roots Changed |
|---|---|---:|---:|---:|---:|
| Veil | 1,15,15,15,18,15,12 | 10935000 | 0 | 8.464152824101713 | 5 |
| Gilded | 18,18,15,15,18,15,12 | 236196000 | 0 | 9.665520083366916 | 7 |
| Vector | 5,12,15,15,18,15,12 | 43740000 | 0 | 10.191082279599211 | 5 |

Each theme therefore records **one theme exception**, with every shipped shortfall and its distinct geometry signatures in the resumed pair table. The exact Veil `#b83d7a` anchor and linked aliases, other hue families, backgrounds and existing opacity rules are retained.

### State and Static Render Signatures

Color and animation are removed from these signatures. The monochrome capture visually confirms them at their ordered sizes.

| Surface | State | Static Signature | Source / Test |
|---|---|---|---|
| Memory | Normal | Existing meter, no warning | TopBar.tsx:198; StateGlyphs.test.tsx:74 |
| Memory | Over | Same meter plus 12px AlertTriangle | TopBar.tsx:210; StateGlyphs.test.tsx:74 |
| Delete | Unarmed | 11px Trash2 | LocalModelRows.tsx:439; StateGlyphs.test.tsx:87 |
| Delete | Armed | 11px AlertTriangle | LocalModelRows.tsx:437; StateGlyphs.test.tsx:87 |
| Map | Rest | Filled circle, no outline | MapPane.tsx:92; StateGlyphs.test.tsx:109 |
| Map | Current | Filled circle with static circular outline (bullseye) | Same renderer on canvas at :738 and sidebar at :608 |
| Map | Selected | Filled square and square outline | StateGlyphs.test.tsx:109; priority at MapPane.tsx:541 |
| Map | Hovered | Filled diamond and diamond outline | StateGlyphs.test.tsx:109; priority at MapPane.tsx:541 |
| Key | Optional Absent | 12px Circle | SettingsPane.tsx:33; StateGlyphs.test.tsx:170 |
| Key | Required Missing | 12px AlertTriangle | Same renderer; four real SVG geometries compared |
| Key | Present | 12px CircleDot | Same renderer |
| Key | Verified | 12px CircleCheck, verified-first precedence | Same renderer; all required/present Boolean combinations verified |

The real first-click/disarm path preserves button identity, accessible name and pressed state. An enabled ready exceeds-RAM delete is included, with no second click or mutation. Memory checks cover under/equal/over budget and no active model; existing TopBar tests retain GiB arithmetic and text assertions. Geometry proof checks all four shapes at two zooms, actual projection and offsetCoincidentPins per zoom, a nearby grouping that changes, leader endpoints and true-coordinate centering. Existing MapPane geometry tests remain and their pin-center reader now handles the new shapes. Existing SettingsPane key-store/status revision tests remain; the product diff only imports/extracts/uses the glyph renderer.

### Complete Measurements, Search Witnesses and Exceptions

- [Complete 417-row before/after CSV](pair-measurements.csv), with unrounded RGB and ΔE and both static signatures on every row.
- [Complete before/after tables for every theme/context](pair-measurements.md); exact numerical duplicates are grouped, with **every** context named.
- [Veil table and shipped assignment](veil-pairs.md): one theme exception, 25 below-15 contexts.
- [Gilded table and shipped assignment](gilded-pairs.md): one theme exception, 56 below-15 contexts.
- [Vector table and shipped assignment](vector-pairs.md): one theme exception, 48 below-15 contexts.
- [Veil exhaustive result](veil-joint.json), [Gilded exhaustive result](gilded-joint.json), [Vector exhaustive result](vector-joint.json): full-domain counts, joint maxima, tie-break changes, maximizing assignments, individual factor-domain maxima/witnesses, and all before/after measurements.
- [Explicit shortfall manifests](theme-exceptions.json). The test rejects missing/unlisted shortfalls, outside-domain values, remapping, non-maximal shipped assignments, non-minimal root-change ties, or coinciding static signatures. Stored JSON maxima are never the test oracle.

The theme families are retained: Veil magenta/coral and warm neutrals; Gilded gold/bronze and warm neutrals; Vector cyan/blue and cyan neutrals. Destructive retains each theme's baseline red hue inside the ordered bright/saturated domain. No continuous-family impossibility claim is made. The joint results apply only to this order's finite domain and fixed proof convention.

### Swatches and Browser Proof

![Before/After Ordinary and Deutan Swatches](swatches.png)

[Vector swatch source](swatches.svg) has all 84 labeled samples, with original CSS RGB and deutan-simulated RGB. Baseline for the added hovered token is the starting commit's brass-bright. Labels are QA artifact annotations, not product UI.

![Shipped Glyphs at Actual Sizes, Reduced Motion](glyphs-reduced-motion.png)

![Monochrome Glyphs at Actual Sizes, Reduced Motion](glyphs-monochrome-reduced-motion.png)

[Full production pane fixture capture](production-panes-reduced-motion.png) and [browser receipt](browser-proof.json). The scratch fixture bundles the real TopBar, LocalModelRows, MapPane, KeyStatusGlyph and emitted production CSS, seeds real React Query data, and uses real DOM events. It uses a `file://` page and no app server/gateway. Both memory states are rendered by TopBar. Canvas samples are cloned from the real SVG groups with their actual zoom; sidebar samples are the actual 7px SVGs. All 45 sampled SVGs use the ordered 12/11/18-frame/7px dimensions. All 12 selected/hovered pulse elements have computed `animation: none`; reduced-motion media matches. The receipt reports zero API requests and zero page errors and pins CSS/source/fixture hashes. Monochrome removes glow filters and makes all glyph fills/strokes the same color. Geometry remains distinguishable.

Scratch files remain exclusively under `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/`: `fixture.tsx`, `capture.cjs`, `swatches.cjs`, `make-tables.py`, `inspect-css.cjs`, gate wrappers, logs and PR body. No server/listener was started. A capture preflight dispatched pointerenter instead of React's pointerover and aliased wrapper themes through the root override; both fixture issues were corrected and all final captures regenerated. The final receipt asserts 12 stopped pulses and three different root palettes.

### Gates, Diagnostics and Landing Notes

[Exact commands and verbatim tails](commands.md). Final focused suite: 76 passed; full UI: 478 passed; type-check and build passed. The emitted CSS selector is minified as `[class*=animate-]` and retains `animation:none!important` in the app-wide reduced-motion media rule. The restored-exclusion scratch plant fails both the existing guard assertion and the named pin regression test; it was reverted before the green gates and build.

Owner-target proof: 80 passed, `secret-store guard: active; nexus-api: denied`, `dbname audit: owner targets: none`, zero connection targets. The complete offline split gates total **4721 passed, 1263 skipped, no failures**; the separate reachability gate passes 54. Skipped PostgreSQL/live tests are not represented as database proof; the order owes only the owner-target guard and no feature database gate. No #885 failure occurred. Black/flake8/mypy have no changed Python targets and are not applicable. UI check has no diagnostics. npm's existing audit advisory and the standard Vite large-chunk warning were reported without an out-of-scope dependency or bundle refactor. No stale fingerprint/allowlist baseline needed editing.

No paid call, inference, gateway lane, product Python, nexus.toml, migration or owner database write. The whole-tree PostgreSQL gate at the final commit belongs to the coordinator. No new scripts/ classification row is triggered. The owner-target guard and file diff substantiate the bounded work; no live story or store behavior is inferred from seeded UI data.

Landing: **no migration number, fleet application or gateway restart**. The coordinator runs `npm --prefix ui run build` after landing because the client bundle changes, then the whole-tree PostgreSQL gate at the final commit. If later authorized work expands into Python/config, the coordinator uses `nexus restart gateway` by service name. This slice does not implement narrow-width panes/rail, #767's ledger, map persistence or later layer/geography work. No merge is authorized here.

Open coordinator questions: **none**. The amendment answers the historical stop-report question; the owner's recorded Build and bottom-rail rulings remain binding.

### Final Integrated Disposition — Completed, Awaiting PR Review

`origin/main` advanced during the first proof set to `581aad0f301a65a0cee81b65222c6cbaa999a6f5`. To obey both the current-base requirement and preservation of the accepted stop commit, the branch integrated current main in `8ace1995`, then ran `git rebase --rebase-merges=no-rebase-cousins origin/main`. The original `a5d63ddf`, implementation `a3d67189`, and evidence `8a7a1051` remain unchanged ancestors. A plain rebase briefly flattened the merge; it was restored before the merge-preserving rebase. No rewritten history is shipped. The diff against main contains only this order's client, map-spec and QA files; upstream Python/config/schema changes are not changes introduced by this order.

The integrated proof reran **all** required offline tests, every root file (now 133), owner-target guard, focused/full UI, type-check, build, emitted CSS and browser captures. [Final exact commands and verbatim tails](integrated-commands.md) supersede the earlier counts for the final branch. Results: focused **76 passed**, full UI **496 passed**, offline **4739 passed / 1377 skipped / no failures**, owner-target **80 passed / zero targets**, and separate reachability **54 passed**. UI check and build pass. No new diagnostics; Python static tools remain not applicable to this order. Final emitted CSS is `index-DgHx-njr.css`; its app-wide selector retains `animation:none!important`. Final browser receipt again confirms 45 SVGs, 12 stopped pulses, three distinct theme palettes, zero API requests and zero page errors.

The joint proof now also counts actual visits and unique assignment tuples in each factor and rejects incomplete or duplicate enumeration before accepting an exception. All three JSON receipts include those coverage counts. Joint maxima, shipped assignments and all 417 measurements are unchanged. The joint coverage represents every full Cartesian assignment through exact variable elimination.

The browser fixture uses `dispatchEvent('click')` for the first delete click: the existing exceeds-RAM row marks its ancestor `aria-disabled`, while the native delete button remains enabled. Playwright's higher-level click regarded that ancestor as disabled. The ordered disabled conditions and row semantics were preserved; this capture is a glyph-render proof, not a new acceptance claim for that existing interaction. Real component click/disarm tests preserve the native button's name, identity and state. No second delete or API action was run by the fixture.

No paid call, app/gateway launch or owner database write was performed. Landing notes and scope above remain unchanged. Coordinator questions: none.


## After Amendment 2 — Stop Report, 2026-10-01

Starting branch head: `9f8f026fcf7bb96f044a1a724306c7ec0a4aa943`; open PR #1099. Amendment 2 cannot satisfy both its literal global-freeze rule and its retained exact Veil anchor rule against the pinned starting shade-domain commit, `8ccd3008a48bdf8115232667399868e2bdf66f93`. The common order's escape hatch requires a stop report when the premise is false or a hard rule cannot be satisfied. No alternate baseline or unapproved anchor exemption is used.

The pinned CSS declares **all seven** Veil brand/linked tokens as `320 55% 48%` (wrapped in `hsl()` for brass and magenta). That resolves to unrounded 0–255 sRGB `(189.72, 55.07999999999999, 144.84000000000003)`, 8-bit `#be3791`. The mandatory exact anchor is `(184, 61, 122)`, `#b83d7a`. Equality fails even before rounding. Source lines in the pinned file: sidebar-primary 417, sidebar-ring 422, primary 430, ring 451, chart-1 454, brass 482, magenta 490. Existing verification.md and state-shades.test.ts both identify that starting commit; this is not inferred from a stale screen or a comment saying “#b83d7a”.

| Frozen Global Token | Pinned Starting Value | Literal Freeze Requires | Retained Anchor Rule Requires |
|---|---|---|---|
| `--brass` | `hsl(320 55% 48%)` | `#be3791` | `#b83d7a` |
| `--magenta` | `hsl(320 55% 48%)` | `#be3791` | `#b83d7a` |
| `--primary` | `320 55% 48%` | `#be3791` | `#b83d7a` |
| `--sidebar-primary` | `320 55% 48%` | `#be3791` | `#b83d7a` |
| `--sidebar-ring` | `320 55% 48%` | `#be3791` | `#b83d7a` |
| `--ring` | `320 55% 48%` | `#be3791` | `#b83d7a` |
| `--chart-1` | `320 55% 48%` | `#be3791` | `#b83d7a` |

`global_tokens_are_unchanged_from_baseline` cannot pass alongside `veil_anchor_is_exact_b83d7a` under these literal requirements. Treating `9f8f026f` as the starting palette would instead freeze the very global shade tuning Amendment 2 rejects. A coordinator amendment must identify either a sole brand-anchor exemption/normalized baseline or withdrawal of the anchor rule. The question was sent during the run; no answer was received before this stop report.

Independent draft work mapped the twelve state consumers, renamed hovered, updated spec sections 3.1/3.2, and moved the joint proof into exact independent surface factors with BigInt full-domain counts. It is preserved as `amendment-2-independent-work.patch` in the prescribed scratch subdirectory. These incomplete product edits were restored to the accepted head before this evidence commit; the branch does not contain half-defined state tokens or an untested replacement search. Accepted glyphs, tests, measurement helper, spec and all prior evidence remain intact. No new state table, joint maximum, exception manifest, swatch or non-state pixel-equality claim is made for Amendment 2. The earlier tables and captures above remain historical Amendment 1 results, not Amendment 2 acceptance evidence.

### Exact Commands and Verbatim Tails for This Attempt

Worktree import proof:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/nexus/__init__.py
```

Node bootstrap:

```text
npm --prefix ui ci
added 957 packages, and audited 958 packages in 5s

27 vulnerabilities (2 low, 8 moderate, 16 high, 1 critical)
```

Baseline proof (PostCSS parses the real pinned CSS; the retained production-independent measurement helper converts HSL):

```text
node /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/amendment-2-baseline-proof.cjs
Baseline: 8ccd3008a48bdf8115232667399868e2bdf66f93
--brass: hsl(320 55% 48%) => RGB (189.72, 55.07999999999999, 144.84000000000003) => #be3791; required #b83d7a
--magenta: hsl(320 55% 48%) => RGB (189.72, 55.07999999999999, 144.84000000000003) => #be3791; required #b83d7a
--primary: 320 55% 48% => RGB (189.72, 55.07999999999999, 144.84000000000003) => #be3791; required #b83d7a
--sidebar-primary: 320 55% 48% => RGB (189.72, 55.07999999999999, 144.84000000000003) => #be3791; required #b83d7a
--sidebar-ring: 320 55% 48% => RGB (189.72, 55.07999999999999, 144.84000000000003) => #be3791; required #b83d7a
--ring: 320 55% 48% => RGB (189.72, 55.07999999999999, 144.84000000000003) => #be3791; required #b83d7a
--chart-1: 320 55% 48% => RGB (189.72, 55.07999999999999, 144.84000000000003) => #be3791; required #b83d7a
Contradiction proven: 7/7 pinned Veil brand tokens differ from the required exact anchor.
Literal resolved-RGB global equality and exact #b83d7a cannot both pass.
```

Required owner-target guard, run through `run-gate.py` with an explicit 589-second bound:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_owner_target_guard.py
........................................................................ [ 90%]
........                                                                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
80 passed in 2.77s
```

Offline API/Orrery proof, run through the same bounded wrapper:

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1852 passed, 821 skipped, 7 warnings in 34.19s
```

The remaining Amendment 2 UI/offline/build/browser gates were not run after the false-premise stop; no complete proof set is claimed. Black, flake8 and mypy remain not applicable: no changed Python targets. No paid call, gateway lane, Python product/config/migration change, secret-store access or owner database write. No merge. `origin/main` was fetched and remained `581aad0f301a65a0cee81b65222c6cbaa999a6f5`; the evidence-only fix is rebased onto newest main before push without rewriting any existing commit.

Coordinator question: **Does the global-freeze test preserve the accepted exact `#b83d7a` correction as the sole declared global exemption, or must it restore all globals literally to `8ccd3008` and retire the exact-anchor rule?** Until that is answered, “every global unchanged” and non-state pixel equality against that starting commit cannot be truthfully certified.

Codex, GPT-6.


## After Amendment 2 — Completed Under Amendment 3, 2026-10-01

Amendment 3 resolves the historical stop report above: exactly seven Veil global tokens may change to the owner's recorded `#b83d7a`; every other global is frozen to the pinned starting CSS `8ccd3008a48bdf8115232667399868e2bdf66f93`. The accepted glyphs, geometry, precedence, event/timer paths, status-revision guard, minimal UI and reduced-motion guard remain intact. No new element was introduced, so the preceding shadcn check remains applicable.

Product fix: `25a1aa81`; proof after merging current main: `afb5db9e9087f53ed3d5af40413cd12125572526` (origin/main `160134540517f6b74aacd1d1e1f3f584454eef86`, PR #1065). The merge preserves every previous commit ID. No rebase, amend, stash or force push. Prior sections and their artifacts are historical; this section and the `amendment-2/` artifacts supersede only their shade/global results.

### Frozen Globals and the Sole Anchor Exemption

The shared `VEIL_ANCHOR_TOKENS` list in `state-shades.test.ts` drives both `global_tokens_are_unchanged_from_baseline` and `veil_anchor_is_exact_b83d7a`. It contains `--brass`, `--magenta`, `--primary`, `--sidebar-primary`, `--sidebar-ring`, `--ring`, `--chart-1`. All seven resolve to exactly sRGB `(184,61,122)` / `#b83d7a`. The starting `(189.72,55.07999999999999,144.84000000000003)` / 8-bit `#be3791` is the expressly permitted anchor drift correction. Global `--brass-bright` and `--magenta-light` retain their original 320-degree hue. Gilded and Vector explicitly override the inherited `--magenta` with its original value, so the Veil exemption cannot leak into them. No new global pigment is introduced.

[Every frozen global value, baseline → shipped](amendment-2/global-tokens.md): 95 resolved global declarations per theme, including root defaults, backgrounds, aliases, opacity colors, fonts and shadows. All other custom declaration scopes are frozen by the test too. Exactly twelve state tokens per theme are the only new token names; `--map-hovered` is removed.

[Browser pixel receipt](amendment-2/global-proof.json), [before capture](amendment-2/globals-before.png), [shipped capture](amendment-2/globals-after.png). Both images use the emitted production CSS, with the pinned global declarations overlaid for the before image. They contain all 59 directly paintable global-color samples per theme plus non-state chevron, cancel, input and secondary-text regions. Full RGBA comparison at 1200×2310 reports **0 changed pixels for Gilded and Vector**. Veil reports **47,700 changed pixels, entirely inside the seven anchor-token swatches; 0 outside**. The sampled non-state component regions are identical in all themes. Combined with the full declaration/consumer tests, non-state surfaces remain pixel-identical in Gilded and Vector; Veil differs only where an anchor-linked token paints. This is a finite fixture/token proof, not a claim to have navigated every application screen.

![Global Before/After, Ordinary and Deutan; Veil Anchor Correction Labeled](amendment-2/global-swatches.png)

The SVG source is [global-swatches.svg](amendment-2/global-swatches.svg). Alpha samples are composited on the fixed swatch backdrop before the deutan transform. The anchor correction is labeled in the QA swatches only; no product label/legend/control was added.

### State Tokens, Search and Exceptions

[Per-theme baseline → shipped state tokens](amendment-2/state-tokens.md), with [machine-readable values](amendment-2/state-tokens.json). Veil brass-derived state baselines start at the corrected anchor, as ordered. Historical before pair measurements use the literal pinned application CSS including its old anchor; the state-token swatch/table baseline instead uses the corrected anchor for those three states. Both conventions are explicit and neither alters the fixed search domain.

The production meter fill/warning, delete pigment, key glyphs, both map surfaces and leaders read only dedicated state tokens; global surfaces read none. State tokens are static CSS values, not aliases or runtime tunables. The meter's glow uses state pigments while retaining each theme's existing shadow sizes/opacity. Cancel/chevron/download-progress colors retain global pigments. `state_surfaces_read_only_state_tokens` reads actual mappings and sweeps production CSS/TS/TSX consumers; no mocked palette is used.

Exhaustive search now has twelve independent state roots and fixed global/composited backgrounds. Each pair/context matrix visits every pair of candidates. Each surface factor enumerates its entire Cartesian product, checks visited/unique/expected counts, and the minimum of the four factor maxima gives the exact twelve-root joint maximum. A second selection chooses the fewest changed state tokens above that maximum. BigInt counts preserve full Cartesian sizes exactly. JSON evidence is never the test oracle: it recomputes from production CSS and the fixed domain.

| Theme | Joint Maximum Minimum ΔE | Full Candidate Count | Satisfying Assignments | Changed State Tokens | Shortfall Contexts |
|---|---:|---:|---:|---:|---:|
| Veil | 9.913464335675082 | 258280326000000 | 0 | 5 | 30 |
| Gilded | 11.515866170801722 | 446308403328000 | 0 | 8 | 45 |
| Vector | 10.191082279599211 | 2834352000000 | 0 | 5 | 58 |

Exactly **one joint exception per theme**. Shortfall counts by surface: Veil map 16/key 11/delete 3; Gilded map 30/key 11/delete 3/memory 1; Vector map 45/key 12/memory 1. The fewest-changes tie-break may retain a baseline shade on a surface capable of a higher independent maximum; only the joint criterion decides acceptance. The families remain fixed. Static distinctions carry every shortfall: absence/presence of memory triangle, Trash2/triangle, circle/bullseye/square/diamond, Circle/triangle/CircleDot/CircleCheck.

[All 417 unrounded before/after pair measurements](amendment-2/pair-measurements.csv), [complete grouped tables](amendment-2/pair-measurements.md), [every shortfall and its two signatures](amendment-2/exceptions.md), [explicit shortfall IDs](amendment-2/theme-exceptions.json). Every theme still has 139 pair/context measurements, including optional-key rest/hover/focus opacity, canvas/sidebar ring/background contexts, and enabled exceeds-RAM deletion's row→provider compositing. [Veil](amendment-2/veil-joint.json), [Gilded](amendment-2/gilded-joint.json), [Vector](amendment-2/vector-joint.json) record exact domains/counts, factor coverage, joint assignment, individual pair/context maxima/witnesses and all unrounded RGB/ΔE.

![State Before/After Swatches, Ordinary and Deutan](amendment-2/swatches.png)

[144 state swatch SVG samples](amendment-2/swatches.svg). No hue family was dropped or remapped. The published 34 Sharma reference vectors and the original Machado severity-1.0/D65/unit-weight CIEDE2000/compositing convention remain unchanged.

### Rendered Glyphs and Gates

![Production Glyphs at Actual Sizes, Reduced Motion](amendment-2/glyphs-reduced-motion.png)

![Monochrome Glyphs at Actual Sizes, Reduced Motion](amendment-2/glyphs-monochrome-reduced-motion.png)

[Full pane fixture](amendment-2/production-panes-reduced-motion.png) and [hashed browser receipt](amendment-2/browser-proof.json): real components/CSS, seeded React Query data, real DOM events, file origin, no gateway/server. 45 SVGs at the ordered sizes, 12 pulse elements all `animation:none`, reduced motion true, distinct palettes, zero page errors/API requests. The actual meter styles are retained in the fixture; its former scratch global-pigment override was removed. Captures were visually inspected. Standalone-SVG raster capture timed out; inline SVG in a local HTML fixture succeeded and regenerated both swatch PNGs. No product workaround was introduced.

[Exact commands and verbatim tails](amendment-2/commands.md). Focused UI **78 passed**; full UI **498 passed**; UI check/build pass. Emitted `index-BBCeaPR-.css` has the app-wide `[class*=animate-]` selector and `animation:none!important`. Restoring the exclusion in a scratch plant produces **2 failed/7 passed** including the named pin regression; reverted before green gates.

Owner-target guard **80 passed** with `secret-store guard: active; nexus-api: denied` and `dbname audit: owner targets: none`; zero targets. Every offline test file/directory was exercised in the listed bounded splits. The initial unchanged exception-baseline test failed because shared origin/main advanced to #1065 during the gates. Its exact failure is preserved; merge `afb5db9e9087f53ed3d5af40413cd12125572526` integrated main's six-entry shrink without manual baseline/Python edits. The complete affected subsystem rerun passes **517/26 skipped**, including that test, runtime-home and reachability; upstream local-inference **34 passed**, CLI **232 passed**. Separate reachability **54 passed**. All other shards pass; two live modules are skipped at collection (exit 5), not claimed as passes. No unresolved failure and no #885 failure. The whole-tree PostgreSQL gate remains the coordinator's.

Black/flake8/mypy: not applicable, no Python targets introduced/edited by this slice. No new UI diagnostics. Existing npm audit advisories and Vite chunk-size warning remain out of scope. No scripts/ classification row, runtime tunable, paid/provider call, app/gateway service, database write, migration or config/product-Python edit. Changes to Python/config in the merge are upstream #1065, absent from this slice's diff against main.

Landing notes stand: no migration/fleet application or gateway restart; coordinator builds the client after landing and runs the whole-tree PostgreSQL gate. This implementer pushes and updates PR #1099; **does not merge the PR**. Open coordinator questions: **none**; Amendment 3 answers the historical anchor question.

Codex, GPT-6.


## After the Independent Review — 2026-10-01

Fix order `1099-astra-fix.md`, reviewer frozen at `d155e53adfc2cc9755a65426adf78474dc43eecf`. Product/proof fixes committed as `9fc0b610`; `git merge origin/main` reported `Already up to date` at `160134540517f6b74aacd1d1e1f3f584454eef86`. Every previous commit remains in the ancestry. No rebase, stash, amend, force push or PR merge. Earlier sections are untouched and remain historical; the regenerated `amendment-2/` measurement/exception/swatch artifacts supersede their previous numeric results.

Optional `.key-row.optional` group opacity now composites onto its nearest painting ancestor, `.set-card-frame`, whose production background is `var(--bg-elev-2)`. The row's own `--bg` is an interior layer, not the backdrop outside the opacity group. The test traces production JSX ancestry, expands `SettingsCard` through its real children slot, and resolves background declarations from shipped CSS. It also derives the dimmed delete row's provider backdrop from the production component paths and independently checks every measured opacity context against the production layer path, including SVG terrain and sidebar row backgrounds. A new context must extend that closure. Browser computed styles independently confirm `.key-list` and `.set-card-body` are transparent before reaching `.set-card-frame` for all twelve fixture key rows; optional opacity is .5.

All three exhaustive joint searches were rerun. **No shipped state assignment changed.** Joint maxima remain Veil **9.913464335675082**, Gilded **11.515866170801722**, Vector **10.191082279599211**; full counts remain 258280326000000 / 446308403328000 / 2834352000000, with zero satisfying assignments. Exactly nine shipped rows per theme (27 total) change their RGB/ΔE, all key/rest contexts containing optional states. Historical before measurements and all influencing pair/context search maxima/witnesses were regenerated too. Vector optional/rest present–verified changes from **10.452122097547305** to **10.571462802144106**, matching the review. Shortfall IDs/counts remain 30 / 45 / 58: one joint exception per theme and the same distinct static signatures. [Correction receipt](amendment-2/backdrop-correction.json), [complete CSV](amendment-2/pair-measurements.csv), [complete tables](amendment-2/pair-measurements.md), [exception table](amendment-2/exceptions.md), and the three joint JSONs replace the dependent Amendment-2 artifacts. The state-token and global-token artifacts are invariant and remain valid; no product pigment or background declaration changed.

`state_surfaces_read_only_state_tokens` is now a closure over class identities in every production CSS selector, including compounds, descendants, pseudo-classes and pseudo-elements. The inventory includes map pin, shared fill/ring/glyph classes on both surfaces, leaders, sidebar glyph, all four key glyphs/status, memory fill/warning and delete glyph. Nonvisual class markers were added to the map's shared renderer and leaders for that enumeration; geometry, precedence, pigment mapping and pulse assignment stay unchanged. Every color-bearing declaration on a matching selector is checked even without a state reference; only state pigments and color-neutral values are accepted. Consumed custom-property dependencies are discovered transitively. Every state-token reference outside the surface closure fails. A scratch copy with `.lm-trash:hover { color: var(--brass); }` fails with the exact global-dependency diagnostic; reverting that scratch CSS passes the same command. Production CSS was never planted.

The disarm regression uses **native timers**, reads the seeded `/api/settings` shape through real `useSettingsQuery`, and passes `settings.ui.local_models` exactly as production SettingsPane does. The configured window is 250 ms; `waitFor` allows 2000 ms. First-click AlertTriangle, the same button, accessible name and pressed state are checked; restoration checks Trash2, name, identity and unpressed state. The second click is never invoked. No module, hook, fetch or action mock was added.

![Regenerated State and Optional-Key Context Swatches](amendment-2/swatches.png)

The swatch SVG/PNG now contains 192 ordinary/deutan before/after samples: the invariant token swatches plus optional-key rest colors composited onto the corrected card frame. Fresh production captures use actual card-frame/body/list wrappers around the key glyphs. [Browser receipt](amendment-2/browser-proof.json) records source/fixture/CSS hashes, computed opacity backdrops, 45 actual-sized SVGs, all 12 pulses stopped under reduced motion, three distinct palettes, zero API requests and zero page errors. Swatches and monochrome captures were visually inspected. Emitted `index-BBCeaPR-.css` retains `[class*=animate-]{animation:none!important}` in the app-wide reduced-motion rule.

[Exact commands and verbatim tails, including the red consumer plant](after-review-commands.md). Focused UI **21 passed**, full client **499 passed**, check/build pass. Owner-target guard **80 passed**, zero targets, `secret-store guard: active; nexus-api: denied`, `dbname audit: owner targets: none`. Both complete offline suites were exercised in bounded sequential partitions: **4,795 passed / 1,380 skipped / no failures**; separate reachability **54 passed**. All 411 default pytest test files are covered. The two `*_test.py` live modules skip at collection (exit 5), not represented as passing tests. No #885 exception or unresolved failure. Black/flake8/mypy remain not applicable; no Python target changed. No new client diagnostics; existing npm audit and Vite chunk warnings remain out of scope.

No paid call, gateway lane, owner-service action, Python product/config/migration edit, secret-store access or database write. No new UI label, legend, tooltip, control, dependency or runtime tunable. No migration/fleet application or gateway restart owed. Coordinator builds the client after landing and runs the whole-tree PostgreSQL gate at the final commit. PR #1099 remains open for the coordinator; it is not merged. Open coordinator questions: **none**.

Codex, GPT-6.


## After the Second Independent Review — 2026-10-01

Fix order `1099-astra-fix-r2.md`, independent review frozen at `2c2ae60d5585f72ccd2fc67c7b0b6ee7075c5862`. The accepted glyphs, twelve state tokens per theme, exact Veil anchor correction, global freeze, native-timer disarm, geometry and consumer-isolation closure remain intact. This round changes the shade resolver and its proof only; no product CSS or rendered output changes.

Backdrop and state-color lookup now match the production class/native-element ancestry under each theme root, through the actual `SettingsCard` children slot, Settings/Map/TopBar component paths and the shell's `html → body → #root` mount. Both `.dark.theme-<name>` and `.theme-<name> .dark` forms are evaluated; Veil `:root` is modeled explicitly. Class compounds, descendants, modeled hover/focus-within and CSS specificity/source order participate in resolution. The glyph's SVG presentation color is the source-derived default when no CSS override matches. The warning's sibling path, map leaders and classless native ancestors are included. Every measured state color and backdrop is resolved per theme, rather than taking an unscoped exact-selector declaration as the rendered paint.

A separate closure examines relevant color/background/opacity rules and consumed custom properties for every modeled state surface and backdrop. It rejects and names unsupported media/container/other at-rule contexts, attributes/IDs, functional pseudos (`:is`, `:where`, `:has`), unknown ancestor/compound classes, child/sibling contexts, local custom-property cascades, non-direct state-color expressions and `!important` conflicts. Relevant rules from another source stylesheet are rejected until its production ordering is explicitly modeled. Unrelated pane selectors and separate scrollbar boxes do not paint these elements. Rejection is explicit; unsupported contexts cannot silently disappear from the measurement. The emitted bundle confirms index-theme CSS precedes layout CSS, and its hash matches the existing browser receipt.

The reviewer's scratch `.dark.theme-vector .set-card-frame { background: var(--bg); }` **is measured**, producing Vector optional/rest present–verified **10.452122097547305**, then fails `opacity_backdrops_follow_the_production_painting_ancestors`: received paint is the themed override, rather than the recorded `var(--bg-elev-2)` card-frame paint. It is not treated as an unsupported selector. Additional plants prove descendant-theme and Veil-root overrides, specificity despite a later lower-specificity rule, equal-specificity source order, a themed state-color override, and each unsupported context class turn red. The consumer-isolation plant `.lm-trash:hover { color: var(--brass); }` also remains red. All **21** plants use a scratch CSS copy; the restored copy passes all **eight** shade tests. Production CSS was never planted.

All three exhaustive searches and the complete 417 before/after measurements were regenerated into the required round-two scratch directory. The three joint JSONs are **byte-identical** to the committed Amendment-2 receipts, including assignments, coverage, every pair/context maximum and witness, all RGB/ΔE values and historical before measurements. **No shipped state assignment changed after this backdrop correction.** Joint maxima remain Veil **9.913464335675082**, Gilded **11.515866170801722**, Vector **10.191082279599211**; counts remain 258280326000000 / 446308403328000 / 2834352000000; zero satisfying assignments; shortfalls remain 30 / 45 / 58. With no shipped contextual override, Vector optional/rest present–verified stays **10.571462802144106**. Dependent CSV/tables/exception manifests/swatches/captures are retained byte-for-byte because no numeric or rendered dependency changed. [Round-two proof and artifact hashes](after-review-r2-proof.json) record this equality and verify the existing browser receipt's source, fixture and newly built CSS hashes.

[Exact commands and verbatim tails, including both required red plants and every offline partition](after-review-r2-commands.md). Focused UI **22 passed**; full client **500 passed**; check/build pass. Owner-target guard **80 passed**, `secret-store guard: active; nexus-api: denied`, `dbname audit: owner targets: none`, zero connection targets. Both complete offline suites cover all **411** default test files: **4,795 passed / 1,380 skipped / no failures**. The two live modules skip at collection (exit 5); skips are not database proof. Separate reachability **54 passed**. No #885 exception or unresolved failure. Black/flake8/mypy remain not applicable; no Python target changed. No new client diagnostics. Existing npm advisories and Vite chunk-size warning remain out of scope.

`git fetch origin main` and `git merge origin/main` reported `Already up to date` at `160134540517f6b74aacd1d1e1f3f584454eef86`. Every prior commit remains in the ancestry. Fix commits only; no rebase, stash, history rewrite, force push or PR merge. No paid call, gateway/app/service lane, product Python/config/migration edit, owner-database write, secret-store action, new UI element/copy/control, dependency or runtime tunable. Landing notes stand: no migration/fleet application or gateway restart; coordinator builds the client after landing and runs the whole-tree PostgreSQL gate at the final commit. PR #1099 remains open. Open coordinator questions: **none**.

Codex, GPT-6.


## After the Third Independent Review — 2026-10-05

Fix order `1099-astra-fix-r3.md`, reviewer frozen at `3a3790ef18fdedffcce5f0918d1260609f1cecba`. Implementation commit `feb4a30d47585ee3b4e5f8c6acf22390e5726cdb`. Earlier sections remain untouched and historical. The regenerated Amendment-2 tables, exceptions, state-token metadata and swatches supersede their numeric artifacts; earlier geometry/monochrome captures and global-token proof remain historical evidence of the accepted unchanged work, not freshly captured receipts.

The browser now resolves the cascade. [Regenerator](../../../ui/scripts/resolve-state-surfaces.mjs) promotes the real TopBar, LocalModelRows, MapPane and KeyStatusGlyph/SettingsCard renderers with seeded React Query data. Esbuild bundles them and Vite uses the production PostCSS/Tailwind pipeline; no server is started. The fixture loads from `file://`, with HTTP(S) aborted, at 1200×900, `colorScheme: dark`, `reducedMotion: reduce`. Playwright **1.63.0** and Chromium **153.0.8010.12**, cached revision **1228**, resolve three themes × 29 contexts × shipped/before phases. **Zero API requests and zero page errors**. The interrupted run's overlay was MapPlaceDialog, opened by place-row selection; the script clicks the existing Close button and waits for the dialog to become hidden before its next interaction. It retains the first delete click only, real disarm, and interaction/transition settling.

Regenerate from the worktree root with `npm --prefix ui run resolve-state-surfaces`; this ordered run set `STATE_SURFACES_SCRATCH` to the round-three capture directory. The sole authorized new dependency is **playwright**, a dev dependency (lockfile pins 1.63.0); it is absent from the production runtime bundle. [Fixture instructions](../../../ui/scripts/state-surfaces/README.md) record conditions, hash sources and substitution. [Browser-resolved JSON](../../../ui/client/src/state-surfaces.resolved.json) stores exact computed paint strings and ancestor opacity/background/opacity-group flags, including the entire outer opacity group's backdrop, SVG sea/land paint and the two radial-wash endpoints. Inputs SHA-256: **`8cb19022239c60472f8affc06fe1159a0aafed6446ae5d156e8d45b62e75dcc6`**. The hash guards both stylesheet sources, all four ordered component sources, the fixture/regenerator/helper, toolchain configs and lockfile, browser revision and emulation conditions. A stale receipt fails naming the npm regeneration command. Vitest launches no browser; the focused gate passes with a nonexistent `PLAYWRIGHT_BROWSERS_PATH`.

The hand-written resolver, themed-ancestry matcher and unmodeled-context rejection scan and their tests are removed. Only numeric source-over compositing remains. The joint search substitutes a candidate's browser-serialized pigment at the surface node; all chain opacity and backgrounds remain Chromium's. The finite domain, all 14 pairs/139 expanded rows per theme, exhaustive factor counts, fewest-changes tie-break, Machado/D65/CIEDE2000 math, 34 Sharma vectors, exception criterion, distinct signatures, consumer closure, global freeze and exact Veil anchor remain intact. Table consistency independently requires browser-measured before/shipped rows to equal the checked evidence; it does not supply the optimization result. Before pigments are the immutable starting declarations rendered on current geometry, with historical sidebar ring opacity. The fixture's baseline overlay is explicitly theme-scoped so Gilded/Vector cannot retain after state tokens; an independent immutable-pigment assertion permits only Chromium's half-8-bit-channel serialization bound, not a relaxed ΔE criterion.

**The browser inputs do not reproduce the previous tables exactly.** Browser RGB serialization and actual color-mix/background/group-opacity values replace the continuous HSL/source resolver. All exhaustive searches, before/after arrays, maxima and witnesses were regenerated from the browser receipt.

| Theme | Previous Joint Maximum | Browser Joint Maximum | Full Candidate Count | Satisfying Assignments | Shortfalls |
|---|---:|---:|---:|---:|---:|
| Veil | 9.913464335675082 | 9.897315738632694 | 258280326000000 | 0 | 30 |
| Gilded | 11.515866170801722 | 11.37227292852494 | 446308403328000 | 0 | 45 |
| Vector | 10.191082279599211 | 10.192991321299218 | 2834352000000 | 0 | 58 |

Exactly **one shipped assignment changes**: Veil `--state-map-current`, `hsl(330.2439024390244 70% 50%)` → `hsl(330.2439024390244 60% 50%)`. The old assignment reaches only 9.856916632878153 under the browser's values, below the required maximizing assignment. The ordered finite domain and joint criterion require this one-token retune. Gilded/Vector assignments and every other state/global pigment remain unchanged this round. 409/417 shipped measurement rows differ by more than 1e-12 (139 Veil, 139 Gilded, 131 Vector); shortfall IDs/counts remain unchanged, with exactly one joint exception per theme and their existing distinct static signatures.

[Complete unrounded RGB/ΔE CSV](amendment-2/pair-measurements.csv), [complete tables](amendment-2/pair-measurements.md), [Veil](amendment-2/veil-joint.json), [Gilded](amendment-2/gilded-joint.json), [Vector](amendment-2/vector-joint.json), [shortfall signatures](amendment-2/exceptions.md), [state-token baseline/shipped values](amendment-2/state-tokens.md) and their JSON are regenerated. The existing exception-ID manifest is unchanged. [Round-three proof](after-review-r3-proof.json) records source/conditions hashes, table deltas, exact commands, coverage and output hashes.

![Browser-Resolved Before/After Ordinary and Deutan Swatches](amendment-2/swatches.png)

[192 SVG samples](amendment-2/swatches.svg), regenerated from the actual browser-resolved before/after paints including optional-key rest composites, then rasterized in Chromium. The PNG was visually inspected: correct old and new palettes for all three themes, readable labels and no clipping. The accepted glyph geometry, precedence, pulse assignments, accessibility and real-timer regression remain unchanged. Newly emitted `index-CuQlhIc3.css` retains the app-wide `[class*=animate-]{animation:none!important}` reduced-motion guard.

**Five scratch plants each turn red without regeneration (stale hash), turn red after successful browser regeneration, and pass all eight shade tests after restoration.** Media-root, themed opacity, round-two backdrop, `!important`, and `:has()` rules are measured by Chromium, not rejected as unsupported. Media/important/:has() collapse present–verified ΔE to **0**. The opacity plant computes **0.1**, giving optional present–verified **1.9255218435164916** in rest/hover/focus. The backdrop plant computes card frame **`rgb(5, 10, 10)`**, changing optional/rest present–verified to **10.401838316251673**, and fails recorded-table consistency even when the joint optimum stays unchanged. Regenerated failures/pass counts: media **2/6**, opacity **2/6**, backdrop **1/7**, important **3/5**, has **3/5**. Every restored copy is **8 passed** and its CSS/receipt bytes match the branch. Production CSS was never planted. [Declarations, full computed chains and restored exits](after-review-r3-proof.json); [exact commands, named failures and verbatim tails](after-review-r3-commands.md).

Final focused client **22 passed**; full client **500 passed**; check/build pass with no new UI diagnostics. Owner-target guard **80 passed**, secret-store guard active, zero database targets, owner targets none (its printed ReplicationConnection audit limitation is retained verbatim). Both complete offline suites cover all **411** default pytest files in bounded sequential partitions: **4,795 passed / 1,380 skipped / no failures**. The two live modules skip at collection with exit 5 and are not represented as passes. Separate reachability **54 passed**. No #885 exception or unresolved failure. Black, flake8 and mypy each remain not applicable: no changed Python target. Existing npm audit/browser-data notices and Vite chunk-size warnings are out of scope.

`git fetch origin main` and `git merge origin/main` reported **Already up to date** at `160134540517f6b74aacd1d1e1f3f584454eef86`. Fix commits preserve all previous commit IDs. No `git stash` command, rebase, history rewrite, force push or PR merge. Commit hooks ran normally; their temporary pre-commit patch handling restored unstaged evidence. No paid call, gateway/app lane, owner-service or secret-store action, product Python/config/migration edit or owner-database write. No new UI text, label, legend, tooltip, control or runtime tunable. The authorized Playwright tooling dependency is the only added dependency. No migration/fleet application or gateway restart owed; coordinator builds the client after landing and runs the whole-tree PostgreSQL gate at the final commit. PR #1099 remains open. Open coordinator questions: **none**.

Codex, GPT-6.


## After the Fourth Independent Review and the Panel — Stop Report, 2026-10-05

The product-first work is committed locally, with stable map fill/ring/hit nodes,
the separate global label mapping, the restored global memory halo, and 9px
sidebar geometry. The literal equality requirement for the selected Veil label
conflicts with the mandatory exact Veil anchor: Chromium paints 815 changed
device pixels against 8ccd3008 in an otherwise identical label clip. Gilded and
Vector selected-label comparisons are identical; all six isolated halo
comparisons are identical. Real corner-pointer sequences pass in all three
themes, and focused product/motion tests pass 18/18 with a green UI type-check.

[Complete stop report, exact commands/tails, unfinished gates and coordinator
question](after-review-r4/stop-report.md), [painted pixel and pointer
receipt](after-review-r4/product-proof.json), [replay
script](after-review-r4/product-probe.mjs). This diagnostic is not the completed
production-shell/candidate/media oracle. The prior state-surface receipt is
stale after the product edits; no Amendment-4 maxima, exceptions, regeneration,
full proof pass, merge-main, PR update or push is claimed. Earlier sections stay
historical. The common escape hatch applies until the coordinator resolves the
selected-label equality/anchor conflict.

Codex, GPT-6.


## After the Fourth Independent Review and the Panel — Resumed

The coordinator clarification resolves the historical `afbb2756` stop. The
selected Veil label's 815-pixel difference is explicitly recorded as the
mandatory anchor correction to `#b83d7a`; Gilded/Vector selected-label captures
remain identical, and the retained halo-only comparisons remain 6/6 identical.
The old report and capture bytes are preserved.

A new **measured false premise** blocks the frozen oracle rule: removing the
most frequent pixel from each solid fill's own clip removes the foreground,
then selects the background. Real NexusLayout / real TopBar / production Vite
CSS at device scale 4 give the same second-ranked `[8,11,18]` for normal and
over memory, reporting ΔE 0 for visibly different pigments. The checked-in
replay reproduced the three diagnostic clips exactly with zero page errors or
network requests. These are diagnostic captures, not acceptance regeneration.

[Resumed stop-report, exact replay/test commands and verbatim tails](after-review-r4/histogram-stop-report.md).
Focused retained-product tests pass **18/18**. No replacement oracle, new
per-group maxima/exceptions, acceptance regeneration, full proof gate, PR-body
update, main integration or push is claimed. `afbb2756` remains in ancestry;
the old acceptance receipt is still stale. No product source/config/schema
change, paid call, gateway, owner-database write or other-worktree write.

Coordinator question: specify the browser-painted foreground-identification
rule when foreground is the most frequent color. The Veil anchor clarification
is settled.

Codex, GPT-6.


## After the Fourth Independent Review and the Panel — Paint Suppression

The fourth clarification's exact paint-only control and fixed 30% mask-mode
floor are implemented on top of `2f828bd3`; visibility and layout remain.
A fresh unfiltered regeneration fails after **2,317 renders / 55.086s** on the
Vector unarmed delete candidate at width 639 (96/728 mask pixels in its mode).
A separate real verified-key probe and three repeated capture pairs per theme
fail at 18.36% in Veil/Gilded and 12.63% in Vector because bloom enlarges the
mask. Tagging its glow-bearing parent produces the same result. A diagnostic
that disables that glow in both captures passes; it is never acceptance data.

[Complete new stop-report](after-review-r4/paint-control-stop-report.md),
[replay and raw capture readbacks](after-review-r4/paint-control/diagnostic.json),
[independent PNG verification](after-review-r4/paint-control/independent-png-check.json),
and [exact commands and verbatim tails](after-review-r4/paint-control/commands.md)
retain the evidence. The checked acceptance receipt is unchanged and stale.
Focused UI: 15 product/motion tests pass, shade suite fails stale receipt.
UI check passes. No approved per-group maxima/exceptions, regenerated
swatches/tables, executed plants, full UI/offline/reachability gate, PR update,
main integration or push is claimed. Earlier reachable-inventory work and
selected-label/halo proof remain accepted historical evidence. The coordinator
must resolve the fixed floor for both measured failures before acceptance.

Codex, GPT-6.


## After the Fourth Independent Review and the Panel: Fifth Clarification

Resumed from `013ba941`; implemented the four-property transparent control and
the absolute 64-device-pixel mode floor with recorded count/fraction. The sixth
[stop-report](after-review-r4/absolute-floor-stop-report.md) retains repeated
production captures: a reachable Vector delete glyph at width 639 sits under
the existing sibling tooltip shadow, producing a 44/727 mode. Disabling only
that tooltip shadow in both causal diagnostic captures restores 293/727.
Neither timing changes nor a substitute floor were accepted. The receipt is
unchanged and stale; no complete capture, group-search acceptance, refreshed
tables/swatches, plants, complete final gates, PR update or push is claimed.
[Exact commands and tails](after-review-r4/absolute-floor/commands.md) distinguish
failed attempts, causal diagnostics and the current check/focused outcomes.
The prior selected-label/halo evidence remains historical with the mandatory
Veil anchor correction labeled; it was not broadened this run.

Codex, GPT-6.


## After the Fourth Independent Review and the Panel: Sixth Clarification, Mask Mean

The linear-sRGB full-mask mean and 16-device-pixel floor are implemented from
8052f547. The full selected-palette capture completes: 64,008 renders across
all 18 conditions, 1,312.694 seconds summed across four bounded shards, zero
network/page errors; module-graph hash fffe47582568f6e74f43ea8a5cc77f8d28b982b250e054f1a72786b60df851d6.
The 3,726 pair comparisons, token tables and 144 mean swatches are regenerated,
but clearly uncertified: delayed tooltip opening makes sixteen same-value
shipping/candidate delete witnesses disagree. Veil delete actual minimum
13.404111071186673 exceeds the candidate maximum 12.665473691002235, so the
unchanged acceptance gate correctly fails. The direct tooltip-visible replay
makes shipping and candidate means repeat exactly, without fixed sleeps or
changing any paint; that settling change is diagnostic, pending scope ruling.

The [stop-report](after-review-r4/mask-mean-stop-report.md) contains every group
maximum/choice/shortfall, exact failure, unreachable list and causal PNG proof.
Fresh native pointer, label-anchor and six pixel-identical halo comparisons
pass. Focused UI has 1 failed/23 passed; full UI 1 failed/501 passed; check/build
pass. Owner-audit 80 passed/0 targets, complete offline suites 4,795 passed/
1,380 skipped, reachability 54 passed. The executed unplanted plants control
fails the same acceptance check; no named plant is applied or counted. PR
body update, final main merge, push and PR merge are not claimed.
[Commands and verbatim tails](after-review-r4/mask-mean/commands.md) retain all
failures and retries. No paid call, gateway lane or protected database write.

Codex, GPT-6.


## After the Fourth Independent Review and the Panel

**Completed R4, all eight clarifications.** This section supersedes the earlier
R4 stop reports and uncertified numeric evidence; their artifacts remain as
historical diagnostics. The final settled 18-condition regeneration was
preserved and assembled once for the shipped receipt. Resume checkpointed
regeneration, per-group acceptance, plants and final evidence separately.

The MapTab pointer target and fill/ring paths retain their DOM identities as
geometry changes. Real native corner hover/click/leave sequences pass in all
three themes. Labels use the pre-PR global LABEL_COLOR mapping; memory halos
use the unchanged global --glow-soft. The sidebar marker is 9px with
viewBox="-4.5 -4.5 9 9", 2.5px fill radius and 4px ring radius/1px stroke.
The real-timer delete regression checks armed at delete_arm_ms−100 and
disarmed by delete_arm_ms+500. No UI text, legend, tooltip, control or tunable
was added. The preceding shadcn investigation and glyph decisions stand.

The painted pixel is the measurement: linear-sRGB mean over exact
painted/control difference pixels, with a minimum mask of 16 device pixels.
Only fill, stroke, background-color and color become transparent on the tagged
subtree in the control; shadows, filters, layout, siblings and media remain.
There is no compositing/cascade model and no modal-color or fraction floor.
The receipt records mask size, full mean, top-eight exact histogram buckets,
interaction readbacks and settle criteria. Hover/Tab-triggered tooltips await
their final open state; leaving/closing awaits closure. Finite document
animations/transitions finish, including portalled/overlapping siblings;
infinite animations pause at declared start/trough phases. All **3,780 exact
same-value witnesses** pass.

Default measurement: **1200×900, dark, reduced motion, device scale 4,
file://, HTTP(S) aborted**, Chromium **153.0.8010.12**, Playwright **1.63.0**.
All 18 declared media/motion conditions are covered. The completed full
regeneration reports **64,008 renders / 1,436.204s** summed across bounded
shards, zero requests/errors. Regenerate with
`npm --prefix ui run resolve-state-surfaces` in the four recorded condition
batches, then `-- --assemble`; [exact commands/tails](after-review-r4/settled/commands.md)
and [shard/receipt manifest](after-review-r4/settled/capture-manifest.json)
make that single final regeneration reviewable without rerunning it.
Freshness fingerprint: **5fe7c407848242b61e8ce45313ab3d4cd61fb8c84319ea058dd6ffa0f6596901**.
It covers all **2,095 esbuild metafile inputs**, including ThemeContext.tsx,
recursive CSS imports, the full Tailwind client-source scan, scripts/helpers,
configs, package/lockfiles, emulation and browser versions. Vitest recomputes
the module graph/hash without a browser. Global freeze compares entire
normalized declarations against 8ccd3008, with only seven exact #b83d7a Veil
anchors exempt. Consumer closure excludes canvas labels and the memory meter box-shadow; the verified-key and canvas-pin drop-shadow halos read state tokens by design under A2.

Amendment 4 searches each group independently. Groups with a ≥15 assignment
ship one with the fewest changed tokens; other groups ship their own maximum.
The final certified results are:

| Theme | Group | Joint Maximum | Shipped Minimum | Below-15 Comparisons |
| --- | --- | ---: | ---: | ---: |
| Veil | memory | 48.26216860311984 | 28.716026547237604 | 0 |
| Veil | delete | 12.665473691002235 | 12.665473691002235 | 72 |
| Veil | map | 6.263229138922101 | 6.263229138922101 | 134 |
| Veil | key | 15.790725684474648 | 15.085778917790371 | 0 |
| Gilded | memory | 43.18401598713267 | 33.22061397257012 | 0 |
| Gilded | delete | 10.364598322897914 | 10.364598322897914 | 72 |
| Gilded | map | 8.550393827837024 | 8.550393827837024 | 468 |
| Gilded | key | 12.171588571637937 | 12.171588571637937 | 36 |
| Vector | memory | 41.776944390354544 | 39.04211998102758 | 0 |
| Vector | delete | 20.21055516867386 | 15.09491501231194 | 0 |
| Vector | map | 6.63707389972062 | 6.63707389972062 | 232 |
| Vector | key | 9.033064002163252 | 9.033064002163252 | 90 |

Exceptions: **Veil delete/map; Gilded delete/map/key; Vector map/key**.
Their 206 / 576 / 322 below-15 comparisons retain distinct static signatures.
All reachable groups ship ≥15 in every context. [Certified tables/CSV](amendment-2/pair-measurements.md),
[exact groups](after-review-r4/settled/group-results.json),
[state assignments](amendment-2/state-tokens.md), and
[ordinary/deutan mean swatches](amendment-2/swatches.png) replace the old
numbers. Swatches were visually inspected: 36 states × four before/after
ordinary/deutan columns, readable labels and no clipping. All twelve group
maxima differ from f648a18a; assignments change in **7 Veil, 9 Gilded, 8 Vector**
state tokens. [Exact before/after token and old-maximum record](after-review-r4/settled/palette-delta.json).

The [unreachable-context list](after-review-r4/settled/unreachable-contexts.md)
excludes sidebar hovered glyphs (six sidebar contexts), optional-absent in
required rows (three), required-missing in optional rows (three), and the
absent/missing pair with no shared requiredness context. Canvas hovered remains
in sea/land fill/ring contexts. These are not shortfalls or substituted paints.
The accepted [sidebar action failure](after-review-r4/sidebar-hover-context-failure.json)
and [required/optional production-row capture](after-review-r4/control-backdrop/key-reachability.json)
establish why; 70 state samples, 69 comparisons and 13 base pairs remain per
theme/condition.

All **nine plants** are negative at the Amendment-8 **default condition only**
and restored byte-identically. [Checked-in adapter](after-review-r4/settled/plants-default.mjs),
[protocol, named failures and verbatim tails](after-review-r4/settled/plants.md),
[summary](after-review-r4/settled/plants-summary.json). All nine stale receipts
reject. Eight successful 3,556-render partial regenerations fail the fresh
production-painted assertions; the overpainting-shadow probe rejects a named
empty foreground mask after 1,318 renders and remains incomplete. Fresh
default diagnostics run three production assertions, never certify the partial
receipt or optimize a reduced domain. The qualified dark media-root retry and
its initial ineffective green attempt are explicitly documented. The canonical
UI protocol's generic full-regeneration path is not the Amendment-8 execution;
the QA adapter supplies the ordered default scope without changing the shipped
input fingerprint. Earlier R3 index.css/revision prose is superseded by the
actual executed paths and browser version in these records.

[Fresh label/halo/native-pointer proof](after-review-r4/settled/product-final/product-proof.json)
and capture pairs compare pinned 8ccd3008 global paint on current geometry.
Gilded/Vector current, hovered and selected labels are pixel-identical.
Veil current/hovered label fill remains rgb(214,92,173); their broad clips have
19/3 anchor-linked backdrop/antialias differences, and restoring only the seven
anchors makes each clip exactly match the full-baseline overlay. The selected
Veil label paints **rgb(184,61,122) = #b83d7a**. The accepted separately labeled
[815-pixel anchor-correction capture pair](after-review-r4/product-proof.json)
is retained; the fresh wider-spacing clip differs by 797 pixels and also
matches baseline exactly when only anchors are restored. No non-anchor label
change is permitted. Rest labels culled by production zoom rules paint nothing
in this native action context. All six halo-only comparisons are pixel-identical
with fill held fixed and computed shadows unchanged. Native pointer sequences
at (2,1.6) CSS px from center pass hover → selected → rest with stable nodes.
Fresh monochrome map captures were inspected; the four state silhouettes stay
distinct, and the sidebar states remain legible.

Final gates: focused UI **25 passed**; full UI **503 passed / 37 files**;
TypeScript/design-sync and production build pass. Owner-target guard under
NEXUS_RUN_POSTGRES=1 and tests.dbname_audit: **80 passed, zero DB targets**,
secret-store guard active (printed ReplicationConnection audit limitation is
retained). Both complete offline suites: **4,795 passed / 1,380 skipped / zero
failures**, [411/411 default pytest files](after-review-r4/settled/offline-coverage.json),
including the two live modules skipped at collection. Separate reachability:
**54 passed**. [Exact commands and every verbatim tail](after-review-r4/settled/commands.md).
No #885 exception or unresolved failure. Static Python product checks remain
inapplicable: no Python product target changed. Existing browser-data,
third-party eval/PostCSS and Vite chunk-size notices are retained, not cleaned up.

Owner decisions remain **Disposition: Build (disp_777=build)** and
**Secondary panes at narrow width: A bottom rail (q_777_panes=rail)**.
This glyph/deutan work is independent of #767; the narrow ledger waits for #767.
No paid call, gateway lane, protected DB write, product Python/config/migration
change, other-worktree write, stash, rebase, history rewrite or PR merge.
Coordinator owns the whole-tree PostgreSQL gate and PR merge; no migration or
gateway restart is owed. Rebuild the client after landing. Open coordinator
questions: **none**.

Codex, GPT-6.

## After the Stopping-Rule Reviews

2026-10-06, round-5 measurement checkpoint `3ffb7842` on `721ebe12`.
The complete second stopping-rule panel was read before editing. The
90%-difference core, identical-pigment calibration, 18-vector/27-render
media inventory, independent phase-pair scoring, canvas-hovered sidebar
contexts and extended control are checkpointed. `npm --prefix ui run check`
passed. The named regeneration stopped after 74 Veil default calibration
samples: `map/canvas-sea/ring` rest/hovered measured
**22.92610822908579 deutan ΔE**, exceeding the required **1.0**. The full
Veil calibration maximum is **23.707049774790395**. The threshold and
tolerance remain fixed. The [stop report](after-review-r5/stop-report.md)
contains the exact samples, diagnosis, two painted PNGs, controls and tails.
There is no new accepted receipt, searched assignment or proof-gate claim.

### Residuals

- Identical pigment does not imply identical painted core color across the
  inherited ring inventory: rest is sampled at its opaque fill, outlines
  paint at opacity 0.6, and sidebar states have different row backdrops.
  Calibration requires a coordinator ruling before regeneration can continue.
- The per-group deutan max-min criterion has no glyph-against-backdrop floor.
  The accepted `721ebe12` Vector current and Veil selected map tokens remain
  at 30% lightness; no round-5 search was reached. A legibility floor is a
  future owner criterion, not implemented by this order.
- Every `client/src` source file remains a freshness input because Tailwind
  scans the entire tree; any client edit requires regeneration. Font loading
  and font hash coverage remain pending item 11.
- All previously declared scope exclusions remain. Later protocol/record
  corrections, the Amendment-5 evidence/PR sentence and remaining gates were
  not reached after the required calibration stop.

### Coordinator's Frozen Whole-Tree Gate at 721ebe12

Provided by the coordinator, 2026-10-06, dedicated frozen worktree,
`NEXUS_RUN_POSTGRES=1 -p tests.dbname_audit`; this is not a gate run on the
round-5 checkpoint:

```text
6116 passed, 59 skipped, 35 warnings in 2431.35s (0:40:31)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
GATE-1099 EXIT=0
```

Codex, GPT-6.


### Continuation After Clarifications 1 and 2

The earlier calibration stop is superseded by the like-part, effective-opacity
and control-core-backdrop rule, including Clarification 2's mandatory
translucent optional key pair. Checkpoint `02018234` implements that narrow
classification. The named full command passes all three default calibrations
(222 samples) but stops after 477 total renders / 80.661704500s at
`w1-639/reduce/Vector/shipped/delete/ready/rest/unarmed`: the foreground mask
is empty. The required lowest-band midpoint is 320px; production `.lm-quants`
is a 0px-wide overflow clip. Real Tab focus and blur leave it clipped. Painted
and control PNGs are byte-identical. See the [complete continuation stop,
calibration, PNGs and verbatim tail](after-review-r5/clarification-2/stop-report.md).
The incomplete probe never replaced the accepted receipt; no new searched
palette or acceptance-gate claim is made.

The viewport-domain/unpainted-context ruling is pending. Font/provider/protocol
changes and final gates remain pending in the ordered sequence. The Residuals
and coordinator's frozen whole-tree gate above remain recorded; the opaque versus
translucent calibration conflict is now resolved, while this new nonpainting
width representative blocks full regeneration. No mask-floor or representative
change, product layout edit, comparison removal, PR update, push or merge has
been performed.

Codex, GPT-6.


## After the Stopping-Rule Reviews

2026-10-06. Round 5 resumes from `8a528239` under Clarifications 1–3.
The [Clarification 3 stop report](after-review-r5/clarification-3/stop-report.md)
records the remaining specification contradiction: nearest-edge selection
requires 1281px for the 1281–1535 band, while the coordinator's explicit list
requires 1535px. The 18 feature vectors and 27 condition renders are confirmed
by the emitted CSS and native Chromium prelude readbacks. All 222 calibration
samples passed before the deliberate stop; the interrupted command records
26,896 renders, 530.131s and `acceptanceComplete=false`. Shipping shades and
the acceptance receipt remain byte-identical to `721ebe12`.

### Residuals

The objective still has no glyph-against-backdrop floor. The search has not
been rerun after the new measurement, so no new 30%-lightness outcome is
claimed. The full `client/src` freshness scan remains required by Tailwind's
content scan. The later fixture/font, protocol, record corrections and proof
stages remain pending. All previously excluded contract scope remains excluded.

### Coordinator's Frozen Whole-Tree Gate at 721ebe12

The coordinator supplied this pre-change result, dated 2026-10-06, from a
dedicated frozen worktree under `NEXUS_RUN_POSTGRES=1 -p tests.dbname_audit`.
It is not a gate result for this resumed checkpoint:

```text
6116 passed, 59 skipped, 35 warnings in 2431.35s (0:40:31)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
GATE-1099 EXIT=0
```

Codex, GPT-6.


## After the Stopping-Rule Reviews

Round 5 replaces the halo-biased whole-mask mean with the mean of the 90%-difference core, retaining the foreground mask and its size floors. Identical-pigment calibration compares like parts: opaque pairs regardless of backdrop (≤1.0), translucent pairs only over matching control-core backdrops (≤2.5; backdrop agreement ≤1.0). Skipped pairs and mandatory coverage are recorded. Optional key rows are mandatory translucent pairs.

Conditions are the distinct media-prelude truth sets from the Cartesian product of width bands and motion values. The nearest-edge rule chooses widths 639, 760, 767, 1023, 1100, 1200, 1280, 1281 and 1536: 18 vectors and 27 renders including both motion phases. Clarification 3's example of 1535 contradicted its nearest-edge rule; Clarification 4 resolved it to 1281 before regeneration resumed. Motion comparisons take the minimum across independent phase pairs. Hovered sidebar glyphs are captured with the pointer on their canvas pin in rest/selected-current rows; only the row-hover combination is excluded.

Amendment 5 intentionally deviates from base hit handling: outline rings retain `pointerEvents: "none"` so they cannot steal a neighbouring pin's disc click; the disc, label and sidebar row remain targets.

The fixture mounts the real FontProvider and TooltipProvider, SettingsPane wrappers, and the tab corresponding to the content. Production fonts are fulfilled from `client/public` on disk, with no network; the fonts join the freshness hash. The injected control rule suppresses every required paint channel on the tagged subtree and its pseudo-elements. The declaration-root assertion applies to both closure and global freeze; the palette tie-break prefers fewest changed tokens, then largest group minimum, then enumeration order.

### Residuals

The objective has no glyph-against-backdrop floor. Any final 30%-lightness marker is an owner decision under this order; a legibility floor remains a future criterion. The entire `client/src` tree remains a freshness input because Tailwind scans all client sources; any client edit requires regeneration. Existing Round-4 contract exclusions continue to apply.

The coordinator's whole-tree gate at `721ebe12` was run on 2026-10-06 in a dedicated frozen worktree with `NEXUS_RUN_POSTGRES=1 -p tests.dbname_audit`. This is historical baseline evidence, not a claim that the amended tree passed that whole-tree gate:

```text
6116 passed, 59 skipped, 35 warnings in 2431.35s (0:40:31)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
GATE-1099 EXIT=0
```

Codex, GPT-6.


## After the Stopping-Rule Reviews

2026-10-06. This completed Round-5 record supersedes the earlier Round-5 stop reports above. The implementation and palette accepted at `d64e0c44`, frontend gates at `2f586440`, backdrop plant at `9bf1a656`, and calibration-coverage handling at `f4061784` stand. The full panel report at `/Users/pythagor/nexus/temp/orders_2026_09_30/panel-1099-721ebe12.md` was read in full before the resumed work. No additional palette or product behavior was changed during this resume.

The foreground mask is every changed device pixel; its core consists of mask pixels at least 90% of the maximum Euclidean linear-sRGB painted/control difference. The painted color is the linear mean of that core. Mask and core sizes and histogram buckets remain recorded. The accepted Round-4 Clarification 6 removed the former mode/fraction floors; its 16-device-pixel mask minimum remains. Calibration compares like parts and effective opacity: opaque pairs regardless of backdrop at ≤1.0 deutan ΔE; translucent pairs only with control-core backdrops within 1.0, at ≤2.5. All skipped pairs and mandatory opaque/translucent coverage remain in `proof.calibration`. The acceptance objective keeps all reachable pairs over their production backdrops.

The emitted CSS produces nine width bands × two motion values = 18 truth vectors and 27 condition renders. Representatives are 639, 760, 767, 1023, 1100, 1200, 1280, 1281 and 1536px under the nearest-default-edge rule. Clarification 3's transcribed 1535 conflicted with that rule; Clarification 4 settled 1281 before the completed regeneration. Motion-enabled pairs score the minimum over start/start, start/trough, trough/start and trough/trough. Canvas hover drives the hovered diamond in unhovered sidebar rest/selected-current rows; only hovered glyph × row hover stays excluded.

The real FontProvider, TooltipProvider and SettingsPane wrappers mount with the matching tab. Production public fonts load from disk through Playwright routes under file://; external HTTP(S) is aborted. The control suppresses all required paint channels, including background-image and pseudo-elements. Root declarations are asserted in both consumer closure and global freeze. Search ties prefer fewest changed tokens, then largest group minimum, then enumeration order.

Amendment 5 intentionally deviates from base hit handling: outline rings retain `pointerEvents: "none"` so they cannot steal a neighbouring pin's disc click; the disc, label and sidebar row remain targets.

The verified-key drop-shadow (`nexus-layout.css`) and canvas-pin glow (`MapPane.tsx`) read state tokens by design under A2; only the memory meter's box-shadow keeps a global token. The historical key-overpainting-shadow record is corrected to name the recorded-table check and freshness as its robust guards, not the 16-pixel floor; the optional-row empty-mask event was a rounding coincidence. In this Round-5 protocol run, the planted shadow is rejected earlier by identical-pigment calibration: Vector required-missing/present at rest has opaque ΔE 1.1084665796847142 > 1.0. The two painted PNGs and controls are preserved in the final plants archive; no fresh-table result is claimed for that interrupted plant capture. The deleted hand-ordered `styles.css` no longer appears in the changed-file index; the control is the rule injected by `resolve-state-surfaces.mjs`.

### Final Measurement and Search

The post-protocol full regeneration completed with 101,742 renders and all 27 conditions in 2082.646s, within its derived 4123-second bound. Its fingerprint is `58840ffef265ffd34ab449b5c03db066158fe248ed1cf2dc63e73948b998f77e`. Only the protocol-input hash changed after `f4061784`. The renewed capture has settled delete-tooltip overlay/readback variation and condition ordering relative to the historical accepted receipt, so its tables and exception ordering were regenerated. The calibration maxima, every search assignment, and every group maximum/shipped minimum are identical; the accepted shipped tokens stand. Vector/delete now enumerates 153 feasible assignments versus 152 in the earlier capture. The [36-token old → new table](after-review-r5/final/token-changes.md) reports every token against `721ebe12`, including unchanged values; shades are judged under Machado deutan severity 1, D65 Lab and CIEDE2000. Veil's exact `#b83d7a` anchor and every theme's hue families remain.

| Theme | Group | Search maximum | Shipped minimum | Feasible assignments | Changed tokens vs original search reference (8ccd3008) |
| --- | --- | --- | --- | --- | --- |
| Veil | memory | 48.282053 | 28.723129 | 270 | 0 |
| Veil | delete | 14.631358 | 14.631358 | 0 | 2 |
| Veil | map | 5.994260 | 5.994260 | 0 | 3 |
| Veil | key | 18.445797 | 17.266564 | 1930 | 2 |
| Gilded | memory | 43.175673 | 33.211691 | 150 | 1 |
| Gilded | delete | 12.156104 | 12.156104 | 0 | 2 |
| Gilded | map | 7.497799 | 7.497799 | 0 | 4 |
| Gilded | key | 16.256194 | 16.150626 | 22 | 3 |
| Vector | memory | 41.815623 | 39.072759 | 36 | 1 |
| Vector | delete | 23.288018 | 15.764553 | 153 | 0 |
| Vector | map | 5.900185 | 5.900185 | 0 | 3 |
| Vector | key | 11.468146 | 11.468146 | 0 | 3 |

The complete 6,561 pair measurements (2,187 per theme) are in the Amendment-2 CSV/joint JSON and current swatches. Below-15 comparisons are explicitly enumerated: Veil 230, Gilded 766, Vector 1,187. The acceptance objective retains real translucent backgrounds and all independent phase pairs; the calibration does not exclude objective pairs.

### Completion Proof

All 11 plants have a stale rejection, a fresh diagnostic or named measurement/calibration rejection, and a passing pre-hash/HEAD restoration proof. The shipping receipt was refreshed only after the final restore proof was committed. The gradient plant regenerates successfully and the element-scoped redeclaration fails the root assertion. [Plants](after-review-r5/final/plants.md) and their individual command logs preserve the results.

The final frontend gates pass: 26 focused tests, 504 full-suite tests, TypeScript/design-sync check and production build (both exit 0). The guarded owner-target proof passes all 80 tests with `NEXUS_RUN_POSTGRES=1 -p tests.dbname_audit`, reports no connection targets or owner targets, and preserves the audit limitation for `psycopg2.extensions.ReplicationConnection`. The two offline suites pass: core 2,930 passed / 559 skipped; API/Orrery 1,865 passed / 1,369 skipped. Separate reachability passes all 54 tests. Exact command tails and measured wall times are in [commands](after-review-r5/final/commands.md); [offline coverage](after-review-r5/final/offline-coverage.json) proves all 412 default test files are covered once across 15 partitions. Secret-store denial is active for every Python gate. No owner database, paid provider, secret write, config or migration change is part of this resume. Python formatting/type checks are not applicable: no Python product or test source changed.

### Residuals

The per-group objective has no glyph-against-backdrop floor. The shipped 30%-lightness values are Veil map-selected and key-present; Gilded map-selected, key-present and mem-over; Vector key-absent and mem-over. In particular, both Veil and Gilded selected canvas pins remain at 30% lightness. These are recorded owner decisions under this order; a legibility floor is a future criterion. The token table retains their exact HSL values. No hue family was dropped to improve the deuteranopia score.

The freshness hash covers every `client/src` source because Tailwind's content scan makes every client file a CSS input; any client edit requires regeneration. Production font files are additional inputs. All scope exclusions and known accessibility/device limitations recorded in the Round-4 clarifications remain outside this order. The full PostgreSQL whole-tree gate for the amended branch remains the coordinator's responsibility; the baseline below does not certify the amended tree. Artifact indexes track the current corrected records; frozen logs and pre-plant content hashes are preserved.

### Coordinator's Frozen Whole-Tree Gate at 721ebe12

Supplied by the coordinator on 2026-10-06 from a dedicated frozen worktree under `NEXUS_RUN_POSTGRES=1 -p tests.dbname_audit`. This is historical baseline evidence:

```text
6116 passed, 59 skipped, 35 warnings in 2431.35s (0:40:31)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
GATE-1099 EXIT=0
```

Codex, GPT-6.

### Sixth Review

Astra's sole P2 is fixed: split media lists only at depth-zero commas, exclude print/forced-colors alternatives individually with parent-list/reason receipts, and treat each kept alternative as its own band/feature/satisfied-set prelude. Five unit regressions pass, including the 640–759px band represented by 759, print-only lists and forced-colors beside width. The first full regeneration retained 27 conditions and unchanged calibration maxima, palettes and shipped minima, but 114 delete focus/tooltip samples varied at 760/767px; six shipped samples switched recorded open/closed state. Vector/delete's search maximum changed 23.288 → 23.243 and feasible assignments 153 → 152. The historical table above belongs to `198e4e03`; exact equality is no longer the acceptance proof.

Clarification 2 supersedes the open-tooltip expectation after the [Clarification 1 stop](after-review-r5/final/sixth-review/settled-stop/stop-report.md). The production Radix tooltip trigger is the exceeds row: row focus opens and blur closes as Tab moves to its nested trash button, so open-after-Tab is a component race. In the accepted `198e4e03` receipt, only 7/81 unarmed and 16/81 armed focus samples had an open tooltip; unarmed hover was open 81/81 and armed hover was closed 81/81. The measured focus-visible state now dismisses the tooltip for both unarmed and armed states: after real Tab, press Escape once if present, retain focus-visible on the trash button and expanded family, and compare DOM signatures, form values and dialog markup before/after. Hover expectations remain enforced. The open-tooltip focus variant is unmeasured; across the 114 varying samples compared at `61fb421c`, its painted-core effect was at most 0.0097 Euclidean in linear sRGB (well under 1 deutan ΔE). The coordinator owns the product issue; the component is unchanged.

The completed regeneration at `89cc64a4` captures all 27 conditions and 101,742 samples in 1986.519s within the 4123-second bound. Every tooltip readback matches its context expectation before both captures; all 2,760 dismissed-focus sample signatures match, and every sample records `settleWaitMs`. The measurement-input fingerprint is `7c7cda7c5a1124025888de538122b3efb555de17e1a2dd30ea48cb84fc3ab7f9`. Tables, CSV, swatches and exception manifests were regenerated from this actual receipt; equality with `198e4e03` is not the proof. Calibration maxima are unchanged. Palettes and shipped minima stand; current group search results are in the table above. The initial implementation attempt stopped at 16 calibration samples on a missing `createHash` import and wrote no acceptance receipt; its log is preserved, the import was fixed, and only one complete regeneration was performed. [Renewed receipt proof and calibration](after-review-r5/final/sixth-review/dismissed-focus/receipt-proof.json) preserve the exact results. The diff remains inside `ui/` and `docs/`, so the coordinator's whole-tree Python gate on `198e4e03` remains applicable; no new whole-tree result is claimed.


The renewed closed-tooltip receipt returns Vector/delete maximum 23.288018 with 156 feasible assignments (153 at `198e4e03`), while every shipped minimum and every other group maximum/count remains unchanged. The actual below-15 manifest now contains Veil 229, Gilded 766 and Vector 1,187 comparisons. The export step wrote the new joint records and correctly rejected the old Veil exception manifest; the manifest and tables were then refreshed from the receipt. This bootstrap rejection is archived separately from the subsequent acceptance gates.


The Sixth Review proof is complete: 31 focused tests, 509 full UI tests, TypeScript/design-sync check and production build pass. Five media regressions also pass separately. The exact mixed-list plant changes all nine optional-key rest means at 759×900/dark/reduce and turns the fresh recorded-table shade assertion red; restoration hashes agree with the pre-plant snapshot, live tree, scratch and HEAD, and all 11 restored shade assertions pass. Separate reachability passes all 54 tests with the secret-store guard active and `nexus-api` denied. The new plant is recorded [alongside the eleven](after-review-r5/final/plants.md); [command tails](after-review-r5/final/sixth-review/dismissed-focus/commands.md) retain the results. Scope remains `ui/` and `docs/`.

Codex, GPT-6.
