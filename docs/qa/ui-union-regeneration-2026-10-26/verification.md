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

The tail of each batch log (the `Resolved`, `Emulation` and `Wrote` lines, with the scratch
path shortened to `<scratch>`):

```
==> batch-1.log <==
Resolved painted state surfaces: renders=15262; wall=393.104s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-1.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6

==> batch-2.log <==
Resolved painted state surfaces: renders=15262; wall=388.268s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-2.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6

==> batch-3.log <==
Resolved painted state surfaces: renders=15262; wall=378.405s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-3.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6

==> batch-4.log <==
Resolved painted state surfaces: renders=15262; wall=378.577s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-4.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6

==> batch-5.log <==
Resolved painted state surfaces: renders=15262; wall=385.005s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-5.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6

==> batch-6.log <==
Resolved painted state surfaces: renders=15262; wall=393.914s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-6.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6

==> batch-7.log <==
Resolved painted state surfaces: renders=15262; wall=389.506s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-7.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6

==> batch-8.log <==
Resolved painted state surfaces: renders=15262; wall=392.015s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 4 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-8.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6

==> batch-9.log <==
Resolved painted state surfaces: renders=3982; wall=373.357s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote <scratch>/UI-UNION-REGEN/capture/shards/batch-9.json; module graph=2108 inputs; SHA-256 eb1ab6e708fde3ddbf829a314d505b098cc73fda514fdcddea3ad296b654e5a6
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
  `escapePressed` changed from false to true, in 1,972 samples (one field each). The DOM
  signatures in the same `delete/ready-exceeds/focus-visible` context also changed: 6,732
  `signature` fields in 3,366 samples, and no signature outside that context. Both changes are
  expected after #1102: keyboard focus inside the row now holds the tooltip open, so the oracle
  presses Escape before it measures, as the README states.
- **Layout boxes.** In 102 samples (34 per band) the `box.y` value moved. Each group of 34 is the
  two shipped samples, the two before samples and 30 candidate samples of one context:

  | Samples | Condition | Theme | Context | `box.y` move |
  | --- | --- | --- | --- | --- |
  | 34 | `w761-767/pointer=fine/motion/trough` | Gilded | `delete/ready-exceeds/rest` | -35 px |
  | 34 | `w1281-1535/pointer=fine/motion/trough` | Veil | `delete/ready-exceeds/rest` | -35 px |
  | 34 | `w1101-1279/pointer=fine/motion/start` | Gilded | `delete/ready/button-hover` | +36 px |

  These are scroll or row offsets of the measured row. No painted field moved: `meanLinear`,
  `controlMeanLinear`, `maskSize` and `coreSize` are unchanged in all 102 samples, as in every
  other sample.
- **Settle times.** `settleWaitMs` timing values differ in 370,972 fields across 124,078 of the
  receipt's 124,080 samples. These values are timings and are expected to vary from run to run.

The per-sample counts and the box breakdown come from a structural diff that walks every sample
(a dict that carries `meanLinear`) and lists every moved `box.y` with no cap. The old receipt is
the LFS object `2e73d14392…` smudged from `925f2591`; the new one is `6973376496…`:

```
nice -n 15 $PY -I <scratch>/UI-UNION-REGEN/tools/sample-diff.py \
  <scratch>/UI-UNION-REGEN/old-receipt.json ui/client/src/state-surfaces.resolved.json
```

```
samples in receipt: 124080
changed leaf key: distinct samples / changed fields
  settleWaitMs: 124078 samples / 370972 fields
  signature: 3366 samples / 6732 fields
  escapePressed: 1972 samples / 1972 fields
  action: 1972 samples / 1972 fields
  y: 102 samples / 102 fields
box.y moves grouped by condition, theme, context and delta:
   34  w1101-1279/pointer=fine/motion/start | Gilded | delete/ready/button-hover | +36 px
   34  w1281-1535/pointer=fine/motion/trough | Veil | delete/ready-exceeds/rest | -35 px
   34  w761-767/pointer=fine/motion/trough | Gilded | delete/ready-exceeds/rest | -35 px
```

A companion pass over the same two files (`signature-contexts.py`) groups the changed samples by
context:

```
escapePressed	delete/ready-exceeds/focus-visible	1972
signature	delete/ready-exceeds/focus-visible	3366
```

<details>
<summary>All 102 moved <code>box.y</code> samples (condition | theme | sample path | move)</summary>

```
w1101-1279/pointer=fine/motion/start | Gilded | before/delete/ready/button-hover/armed | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | before/delete/ready/button-hover/unarmed | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 100% 50%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 100% 55%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 100% 60%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 100% 65%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 80% 50%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 80% 55%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 80% 60%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 80% 65%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 90% 50%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 90% 55%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 90% 60%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-armed/hsl(0 90% 65%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 30%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 40%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 50%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 52%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 60%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 70%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 30%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 40%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 50%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 52%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 60%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 70%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 30%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 40%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 50%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 52%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 60%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 70%)/delete/ready/button-hover | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | shipped/delete/ready/button-hover/armed | +36 px
w1101-1279/pointer=fine/motion/start | Gilded | shipped/delete/ready/button-hover/unarmed | +36 px
w1281-1535/pointer=fine/motion/trough | Veil | before/delete/ready-exceeds/rest/armed | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | before/delete/ready-exceeds/rest/unarmed | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 100% 50%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 100% 55%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 100% 60%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 100% 65%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 80% 50%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 80% 55%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 80% 60%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 80% 65%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 90% 50%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 90% 55%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 90% 60%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-armed/hsl(0 90% 65%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 30% 30%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 30% 40%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 30% 50%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 30% 60%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 30% 65%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 30% 70%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 40% 30%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 40% 40%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 40% 50%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 40% 60%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 40% 65%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 40% 70%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 50% 30%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 50% 40%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 50% 50%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 50% 60%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 50% 65%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | candidates/--state-delete-unarmed/hsl(42 50% 70%)/delete/ready-exceeds/rest | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | shipped/delete/ready-exceeds/rest/armed | -35 px
w1281-1535/pointer=fine/motion/trough | Veil | shipped/delete/ready-exceeds/rest/unarmed | -35 px
w761-767/pointer=fine/motion/trough | Gilded | before/delete/ready-exceeds/rest/armed | -35 px
w761-767/pointer=fine/motion/trough | Gilded | before/delete/ready-exceeds/rest/unarmed | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 100% 50%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 100% 55%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 100% 60%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 100% 65%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 80% 50%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 80% 55%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 80% 60%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 80% 65%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 90% 50%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 90% 55%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 90% 60%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-armed/hsl(0 90% 65%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 30%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 40%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 50%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 52%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 60%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 40% 70%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 30%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 40%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 50%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 52%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 60%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 50% 70%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 30%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 40%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 50%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 52%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 60%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | candidates/--state-delete-unarmed/hsl(43 60% 70%)/delete/ready-exceeds/rest | -35 px
w761-767/pointer=fine/motion/trough | Gilded | shipped/delete/ready-exceeds/rest/armed | -35 px
w761-767/pointer=fine/motion/trough | Gilded | shipped/delete/ready-exceeds/rest/unarmed | -35 px
```

</details>

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
The two checks below also ran before the first push, with the same results. The tails here are from
the rerun on the tree of the review-fix commit that adds them (parent `0148024b`), with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
89 passed, 5 warnings in 5.51s
```

`nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:

```
OK: exception disposition coverage and shrink-only baseline verified.
```

No Python file, product source, theme token, fixture or capture script changed. `plants.mjs` was
not run.
