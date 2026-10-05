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
