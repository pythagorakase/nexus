# Regeneration of the Browser-Resolved State Surfaces for the 2026-10-26 UI Union

Order UI-UNION-REGEN (1102-S2, 821-S3). Branch `claude/ui-union-regen-2026-10-26`, cut from
`origin/main` at `925f2591`. Protocol: `ui/scripts/state-surfaces/README.md`. Precedent: PR #1150
(`a01c162f`), the wave-B union regeneration.

## Premise

The receipt's freshness fingerprint hashes every client source. Three landed PRs of the
2026-10-26 wave changed client sources and each deferred the regeneration to this union run:

| PR | Slice | Client sources in the hashed closure |
| --- | --- | --- |
| #1170 | 1102-S1, Decision 1102-D7 | `LocalModelRows.tsx`, `LocalModelRows.test.tsx`, `scripts/state-surfaces/tooltip-focus-trace.mjs` |
| #1171 | 821-S2, Decision 821-D3 | `SettingsPane.tsx`, `SettingsPane.test.tsx`, `nexus-layout.css`, the Radix Popover modules |
| #1176 | 824-S4 | `InteractiveWizard.tsx` and its two test files |

`ui/vite.config.ts` also changed in the hashed closure (PR #1169, the two-listener re-point).

On `925f2591`, before any capture, `nice -n 15 npm --prefix ui test -- state-shades` failed as
stale:

```
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 ❯ src/state-shades.test.ts:183:9
 Test Files  1 failed | 1 passed (2)
      Tests  95 passed (95)
```

## Condition List

`npm --prefix ui ci` ran in this worktree (959 packages; no symlinked `node_modules`). The
condition ids come from `mediaConditions()` in `ui/scripts/state-surfaces/media.mjs`, applied to
the production Vite build's emitted CSS, which is how `resolve-state-surfaces.mjs` derives them;
`STATE_SURFACES_CONDITION` takes a comma-separated list of these ids. The run found 33 conditions
and 0 unsupported preludes: 27 fine-pointer renders over nine width bands, and six coarse-pointer
renders for the two bands through 760px.

```
w1101-1279/pointer=fine/reduce            (the 1200×900 default)
w1-639/pointer=fine/{reduce,motion/start,motion/trough}
w1-639/pointer=coarse/{reduce,motion/start,motion/trough}
w640-760/pointer=fine/{reduce,motion/start,motion/trough}
w640-760/pointer=coarse/{reduce,motion/start,motion/trough}
w761-767/pointer=fine/{reduce,motion/start,motion/trough}
w768-1023/pointer=fine/{reduce,motion/start,motion/trough}
w1024-1100/pointer=fine/{reduce,motion/start,motion/trough}
w1101-1279/pointer=fine/{motion/start,motion/trough}
w1280/pointer=fine/{reduce,motion/start,motion/trough}
w1281-1535/pointer=fine/{reduce,motion/start,motion/trough}
w1536+/pointer=fine/{reduce,motion/start,motion/trough}
```

## Capture Batches

There were nine serial batches of at most four conditions. Each ran as
`nice -n 15 npm --prefix ui run resolve-state-surfaces` with its own
`STATE_SURFACES_SCRATCH=<scratch>/UI-UNION-REGEN/capture/batch-N`, `STATE_SURFACES_CONDITION` and
`STATE_SURFACES_OUTPUT=<scratch>/UI-UNION-REGEN/capture/shards/batch-N.json`. A background
driver started the batches one after another and stopped on the first failure. Every batch is
bounded at 589 seconds, and none came close to that bound.

| Batch | Conditions | Renders | Wall (s) | Requests | Page errors | Calibration |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `w1101-1279/fine/reduce`; `w1-639/fine/` reduce, start, trough | 15,262 | 393.104 | 0 | 0 | 3/3 passed |
| 2 | `w1-639/coarse/` reduce, start, trough; `w640-760/fine/reduce` | 15,262 | 388.268 | 0 | 0 | 3/3 passed |
| 3 | `w640-760/fine/` start, trough; `w640-760/coarse/` reduce, start | 15,262 | 378.405 | 0 | 0 | 3/3 passed |
| 4 | `w640-760/coarse/trough`; `w761-767/fine/` reduce, start, trough | 15,262 | 378.577 | 0 | 0 | 3/3 passed |
| 5 | `w768-1023/fine/` reduce, start, trough; `w1024-1100/fine/reduce` | 15,262 | 385.005 | 0 | 0 | 3/3 passed |
| 6 | `w1024-1100/fine/` start, trough; `w1101-1279/fine/` start, trough | 15,262 | 393.914 | 0 | 0 | 3/3 passed |
| 7 | `w1280/fine/` reduce, start, trough; `w1281-1535/fine/reduce` | 15,262 | 389.506 | 0 | 0 | 3/3 passed |
| 8 | `w1281-1535/fine/` start, trough; `w1536+/fine/` reduce, start | 15,262 | 392.015 | 0 | 0 | 3/3 passed |
| 9 | `w1536+/fine/trough` | 3,982 | 373.357 | 0 | 0 | 3/3 passed |

Every batch's tail has the same form, with the condition count varying (4, or 1 for batch 9):

```
Resolved painted state surfaces: renders=15262; wall=393.104s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-1.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6
```

Calibration renders the full default inventory for each theme before any capture. It passed in
all nine batches, and the three per-theme calibration lines were byte-identical across all nine:

```
Calibration Veil: {"memory":{"opaqueMaximum":0.00026414815709771805,"translucentMaximum":0,"skippedPairs":0},"delete":{"opaqueMaximum":0.006002891112468775,"translucentMaximum":0.012334576619474699,"skippedPairs":0},"key":{"opaqueMaximum":0.030457571214044847,"translucentMaximum":0.013459005795140349,"skippedPairs":0},"map":{"opaqueMaximum":0.07468917510215183,"translucentMaximum":0.4165404892186375,"skippedPairs":20}}; passed
Calibration Gilded: {"memory":{"opaqueMaximum":0.0002619007277823465,"translucentMaximum":0,"skippedPairs":0},"delete":{"opaqueMaximum":0.008785869899490675,"translucentMaximum":0.0079023496576129,"skippedPairs":0},"key":{"opaqueMaximum":0.04713082389726427,"translucentMaximum":0.02240636952243324,"skippedPairs":0},"map":{"opaqueMaximum":0.06845821399370854,"translucentMaximum":0.350355580029468,"skippedPairs":19}}; passed
Calibration Vector: {"memory":{"opaqueMaximum":0.0003181767847390889,"translucentMaximum":0,"skippedPairs":0},"delete":{"opaqueMaximum":0.029118582412838427,"translucentMaximum":0.02152663851962112,"skippedPairs":0},"key":{"opaqueMaximum":0.011120218162869937,"translucentMaximum":0.003968024121739456,"skippedPairs":0},"map":{"opaqueMaximum":0.08088889823513667,"translucentMaximum":0.500656347153232,"skippedPairs":19}}; passed
```

## Assembly

`STATE_SURFACES_SCRATCH=<scratch>/UI-UNION-REGEN/capture nice -n 15 npm --prefix ui run resolve-state-surfaces -- --assemble`:

```
Resolved painted state surfaces: renders=126078; wall=3472.152s (sum of bounded capture shards); Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 33 media conditions; file://; network aborted; requests=0; errors=0
Wrote <worktree>/ui/client/src/state-surfaces.resolved.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6
```

The assembled receipt records `acceptanceComplete: true`, 9 shards, 126,078 renders, 0 network
requests and 0 page errors. It is committed through the existing LFS rule in `.gitattributes`
(new object `6973376496…`, 206,639,077 bytes; previously `2e73d14392…`, 206,605,800 bytes), and
no samples were dropped.

## What Changed in the Receipt

The old receipt (smudged from `925f2591`) was compared structurally with the new one:

- **Inputs.** The fingerprint moved from `c7df4f2c…` to `eb1ab6e7…`, and the module graph from
  2,099 to 2,108 inputs. The changed files are the client sources listed under Premise, plus
  `vite.config.ts`. The added files are the eight Radix Popover-family modules that #1171 brought
  into the bundle.
- **Media.** The 33 condition variants are identical. The only change is
  `declarationGuards.declarationsScanned`, which moved from 4,745 to 4,757 because the emitted CSS
  gained 12 declarations.
- **Painted fields.** No differences. `meanLinear`, `controlMeanLinear`, `maskSize` and `coreSize`
  are identical in every sample of every condition and theme.
- **Interaction metadata.** For the exceeds-RAM delete focus-visible contexts, the action text
  changed from "tooltip already dismissed" to "keyboard Escape dismisses tooltip", and
  `escapePressed` changed from false to true in 1,972 samples. The DOM signatures of those
  contexts also changed (6,732 samples). Both changes are expected after #1102: keyboard focus
  inside the row now holds the tooltip open, so the oracle presses Escape before it measures, as
  the README states.
- **Layout boxes.** In 102 samples the `box.y` value moved by -35 or +36 px. All of them are in
  `delete/ready-exceeds/rest` and its candidates, in the `w761-767` and `w1281-1535` bands. They
  are scroll offsets of the measured row. The painted means of those samples did not change.
- **Settle times.** `settleWaitMs` timing values differ in 370,972 samples. These values are
  timings and are expected to vary from run to run.

## Inventory Counts per Theme

| Theme | Shipped samples | Before samples | Candidate samples | Measured joint rows | Exceptions (< 15 ΔE) | Changed tokens |
| --- | --- | --- | --- | --- | --- | --- |
| Veil | 2,442 | 2,442 | 38,907 | 2,673 | 275 | 7 |
| Gilded | 2,442 | 2,442 | 40,293 | 2,673 | 792 | 10 |
| Vector | 2,442 | 2,442 | 30,228 | 2,673 | 1,266 | 7 |

The sample counts match the previous receipt exactly.

## Joint Tables, Exceptions and State Tokens

`state-shades` ran with `STATE_SHADES_EVIDENCE_DIR` pointed at the scratch directory, which makes
the test emit fresh `veil-`, `gilded-` and `vector-joint.json` tables.
`theme-exceptions.json` was rebuilt from the emitted measurements, keeping the shortfalls below
15 ΔE in measurement order. All four regenerated files are **byte-identical** to the committed
files under `docs/qa/777-glyph-first-states/amendment-2/` (checked with `cmp`). The refresh
therefore produces no diff. The exhaustive search proposes no palette change: the shipped
assignment remains each group's optimum or clears 15 where 15 is reachable. As a result,
`state-tokens.md` is unchanged, and so are the theme tokens and the Veil anchor `#b83d7a`.

## Tests

`nice -n 15 npm --prefix ui test -- state-shades StateGlyphs shell-accessibility` (tail also in
`acceptance-tail.txt`):

```
 ✓ media-state-shades.test.ts (95 tests) 16ms
 ✓ src/shell-accessibility.test.ts (11 tests) 55ms
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 401ms
 ✓ src/state-shades.test.ts (11 tests) 56258ms
 Test Files  4 passed (4)
      Tests  123 passed (123)
```

`nice -n 15 npm --prefix ui test` (the full UI suite):

```
 Test Files  44 passed (44)
      Tests  688 passed (688)
   Duration  58.99s (transform 2.33s, setup 2.16s, collect 12.40s, tests 76.76s, environment 12.72s, prepare 2.20s)
```

`nice -n 15 npm --prefix ui run check` exited with 0 (`tsc && tsc -p .design-sync/tsconfig.previews.json`).
`nice -n 15 npm --prefix ui run build` exited with 0 (`vite build` and the PWA `generateSW`, with 22
precache entries).

## Document Freshness

Two decision records declare sources that this union covers. Record 0066
(`docs/decisions/0066-the-keyboard-held-tooltip.md`) declares `ui/client/src/state-shades.test.ts`
and `LocalModelRows.tsx`. Record 0067 (`docs/decisions/0067-seat-lists-in-a-popover.md`) declares
`ui/client/src/state-surfaces.resolved.json` and `SettingsPane.tsx`. Both records were checked
against the current sources. `LocalModelRows.tsx:99-103` computes
`open = radixOpen || (keyboardFocusWithin && !escapeDismissed)`. `SettingsPane.tsx:574-591` opens
the seat list in a shadcn `Popover`, with `requiredByTitle` as the content source. Both records
are re-stamped at the merge base with `origin/main`, `925f259182be535614882157c6b5d082e0cfaacc`.
`PYTHONPATH=$PWD $PY -m pytest -q tests/test_doc_front_matter.py` passes; its tail is in the PR body.

No Python file, product source, theme token, fixture or capture script changed. `plants.mjs` was
not run.
