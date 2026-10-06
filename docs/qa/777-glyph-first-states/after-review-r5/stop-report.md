# STOP-REPORT: Round-5 Identical-Pigment Calibration

2026-10-06. Measurement checkpoint: `3ffb7842`, based on `721ebe12`.
The complete panel report `panel-1099-721ebe12.md` and the standing orders,
amendments and all eight round-4 clarifications were read before editing.

The round-5 item 2 stop condition fired. The named command
`npm --prefix ui run resolve-state-surfaces` exited 1 after rendering the
full Veil default calibration inventory: **74 samples**, **28.514232625s**.
The derived media inventory contains **18 truth vectors / 27 condition
renders**. No candidate render or acceptance condition render was performed;
Gilded and Vector calibration were not reached. The shipping receipt was
not replaced. `proof.acceptanceComplete` is false in the archived
[incomplete probe](incomplete-probe.json).

## Calibration Failure

All four map tokens were set to the shipped map-rest pigment,
`hsl(15 75% 60%)`. Threshold **0.9**, tolerance **1.0**, mask minimum **16**;
none was adjusted. Default: 1200×900, dark, reduced motion, device scale 4,
file:// with HTTP(S) aborted. There were zero page errors and network requests.
The fixture remains the accepted round-4 fixture; the later provider/font
fidelity stage was not reached.

The first failing context is `map/canvas-sea/ring`, rest versus hovered:
**22.92610822908579 deutan CIEDE2000**. These are the exact PNGs the
resolver named; both were visually inspected:

- [Rest painted PNG](veil-canvas-sea-ring-rest-painted.png)
- [Hovered painted PNG](veil-canvas-sea-ring-hovered-painted.png)
- [Rest control PNG](veil-canvas-sea-ring-rest-control.png)
- [Hovered control PNG](veil-canvas-sea-ring-hovered-control.png)

| State | Mask Pixels | Core Pixels | Core Mean in Linear sRGB | Display RGB |
| --- | ---: | ---: | --- | --- |
| Rest | 576 | 423 | 0.7888038603082501, 0.1708470795507751, 0.07400065153320673 | 230, 115, 77 |
| Hovered | 896 | 638 | 0.27654365255656027, 0.06958884968543248, 0.03618139999709093 | 143, 75, 53 |

The full Veil calibration maximum is **23.707049774790395**,
`map/sidebar/rest/ring`, rest versus current. Even restricting that context
to actual rings does not meet 1.0: current/selected is **1.8987673152388203**
and selected/hovered is **1.8409652448644422**.

The other measured groups do pass calibration: memory maximum
0.0002655887508743018; delete maximum 0.012334576619474699; key maximum
0.03958693576307006; map fill maximum 0.07468917510215183. This confirms
that the core excludes the verified-key halo and fill-shape coverage in
these Veil samples, while the ring context has a separate premise problem.

## Diagnosis and Required Ruling

The inherited ring inventory measures the rest state's fill because rest has
no ring (`resolve-state-surfaces.mjs:321`, `:333`). The production outline
opacity is 0.6 (`MapPane.tsx:122`), while the fill is opaque. A core mean of
the painted pixels retains that compositing difference. The exact PNGs show
the bright rest disc and the darker hovered outline, both using one pigment.

The sidebar also paints ring states over different row backdrops: the selected
row has `.on` styling while the current/hovered rows do not. Thus ignoring the
rest-as-fill comparison alone does not satisfy the stipulated calibration.
These are production opacity/backdrop differences, not halo contamination.

A coordinator ruling is needed on how identical-pigment calibration should
handle the actual ring opacity and state-dependent row backdrops while the
measurement remains the painted core mean. No opacity, backdrop, geometry,
threshold, tolerance, pair or context was changed to pass calibration.

## Completed Checkpoint and Deferred Work

- `png.mjs`: 90%-difference core mean with `coreSize`, unchanged foreground
  mask/histogram and mask minimum.
- `resolve-state-surfaces.mjs`: full default identical-pigment calibration
  before candidates; stop with exact pair/PNG witnesses; extended paint-only
  control; real canvas-hover sidebar captures and pin-hover readback.
- `media.mjs`: range-band/discrete-feature Cartesian product, deduplicated
  satisfied-prelude sets, exclusions for print/forced colors and unsupported
  prelude rejection. The shipped preludes produce 18 vectors / 27 renders.
- `state-shades.test.ts`: calibration receipt assertion, core audit checks,
  corrected reachable sidebar states and independent start/trough pair scores.
- README and unreachable-context record: corrected measurement and reachability
  rules. Their statements describe the checkpoint implementation, not a newly
  accepted receipt.

The named regeneration stopped at its required calibration gate. The full
condition capture, focused acceptance suite, per-group search, shipped shade
changes, items 7–14, plants, offline/owner-target/reachability proofs, PR-body
update, merge from main and push remain pending. The gradient/redeclaration
plants were not run. No new acceptance result is claimed.

## Commands and Verbatim Tails

`node --check ui/scripts/resolve-state-surfaces.mjs` and
`node --check ui/scripts/state-surfaces/media.mjs`: exit 0, no output.

`git diff --check`: exit 0, no output.

`npm --prefix ui run check`: exit 0:

```text
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync

> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
```

`npm --prefix ui run resolve-state-surfaces`: exit 1:

```text
Resolving w1101-1279/reduce/Veil…
Completed w1101-1279/reduce/Veil; renders=74; wall=28.510s
Incomplete painted probe: renders=74; wall=28.514s; acceptanceComplete=false
```

The full verbatim exception, with both original PNG paths, is in
[regeneration.log](regeneration.log). The original 148 calibration/control
PNGs remain in `scratchpad/777-S2/after-review-r5/capture/calibration/`;
the archived probe contains all 74 samples and all context maxima.
The four witness PNGs, raw probe and command logs are sealed by
[artifact-hashes.json](artifact-hashes.json).

Codex, GPT-6.
