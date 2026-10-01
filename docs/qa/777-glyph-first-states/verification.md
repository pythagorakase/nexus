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
