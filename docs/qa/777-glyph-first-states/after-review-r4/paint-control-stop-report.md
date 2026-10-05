> Historical: the fifth clarification resolves the own-shadow and fraction-floor blocker below. The subsequent sibling-tooltip/absolute-floor blocker is recorded in [absolute-floor-stop-report.md](absolute-floor-stop-report.md).

# After the Fourth Independent Review and the Panel: Paint-Control Floor STOP-REPORT

Date: 2026-10-05. Resumed local head: `2f828bd3`. Branch:
`claude/777-glyph-first-states`; PR #1099 remains open. That head and all
accepted reachable-inventory, batch and diagnostic work remain in ancestry.

**STOP: the fourth clarification's 30% mode floor rejects real reachable
surfaces under its prescribed paint-suppression control.** This is independent
of the resolved visibility/backdrop issue. No relaxed floor or alternative
mask was used for acceptance. The exact unfiltered regeneration also failed.

## Implemented Control and Provenance

`ui/scripts/resolve-state-surfaces.mjs` tags the sampled surface with a unique
data attribute and injects one rule for it and all descendants:

```css
fill: transparent !important;
stroke: transparent !important;
background-color: transparent !important;
color: transparent !important;
box-shadow: none !important;
filter: none !important;
text-shadow: none !important;
```

The control retains visibility, layout, siblings, ancestors and media conditions.
`png.mjs` measures the exact device-pixel difference and rejects an empty mask
or a mode below `.30`, naming the context and top-eight colors. The receipt
records `.30`; the shade test now asserts that exact floor instead of accepting
any receipt-specified fraction. No Python product, palette, geometry, theme,
halo, label, config, migration or database change accompanies this control.

Import proof, run from this worktree:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/nexus/__init__.py
```

The real NexusLayout and production settings sections render with the Vite
production build's emitted CSS. Chromium 153.0.8010.12, Playwright 1.63.0,
revision 1243, device scale 4, 1200×900, dark, reduced motion, file://, HTTP(S)
aborted. All native actions and captures run locally; no gateway or provider.

## Repeated Verified-Key Failure

The filtered baseline/shipped probe first failed at
`default/Vector/shipped/key/required/rest/verified/hsl(185 100% 70%)`:
**291 / 2304 = 0.12630208333333334**, below 0.30. The surface is a 12×12 CSS-pixel
Lucide SVG, captured as 48×48 device pixels. Its primary mode is the actual cyan
glyph interior `[102,242,255]`; the problem is the required fraction, not
selection of a background mode. The second interior mode `[97,230,242]` has 132
pixels under the real Vector scanline overlay. Many glow shades fill the rest
of the mask. The original failure JSON and painted/control PNGs are retained.

The checked-in [diagnostic replay](paint-control/diagnostic.mjs) loads that
probe's production-built fixture and repeats the exact painted/control capture
three times per theme, with no candidate token overrides. It verifies the
applied transparent/none properties on the SVG and descendants, visible layout,
unchanged boxes/display/opacity/row pseudos, DPR 4, zero running
animations, no page errors and no HTTP(S) requests. All three alternating
capture pairs in each theme have identical PNG hashes.

| Theme | Mask Pixels | Mode Pixels | Mode Fraction | Prescribed Result |
| --- | ---: | ---: | ---: | --- |
| Veil | 2304 | 423 | 0.18359375 | Below 0.30, three identical rejections |
| Gilded | 2304 | 423 | 0.18359375 | Below 0.30, three identical rejections |
| Vector | 2304 | 291 | 0.12630208333333334 | Below 0.30, three identical rejections |

Three causal checks isolate the effect:

- An unused diagnostic property changes **zero pixels** in every theme.
- Tagging the `.key-status` parent instead, suppressing its own filter too,
  gives the **same mask and mode** over the identical SVG clip. This rules out
  failure merely from leaving the ancestor filter active in the original control.
- Disabling the existing `.key-status.verified` drop-shadow in **both** captures
  solely for a causal diagnostic yields 423/723 = 0.5822959889349931 in Veil and
  Gilded, and 283/726 = 0.38980716253443526 in Vector. These pass the floor.
  This diagnostic modification is never written to production or used for
  acceptance. Production's filter is `drop-shadow(0 0 5px
  var(--state-key-verified))` at `nexus-layout.css:2160`.

[Complete readbacks, histograms, rules and PNG hashes](paint-control/diagnostic.json)
retain every comparison. Representative prescribed captures are
[Vector painted](paint-control/vector-prescribed-1-painted.png) /
[Vector control](paint-control/vector-prescribed-1-control.png); all repeat and
causal captures are beside them. The first failure pair was visually inspected:
the painted check-circle has visible bloom, while the control is background.
An independent Pillow RGBA byte comparison reproduced **18/18 masks and every
top-eight RGB/count histogram**, including empty neutral controls
([independent check](paint-control/independent-png-check.json)). No package was
installed. The diagnostic command exits zero because its assertions prove the
expected rejections and causal checks; that exit is **not acceptance**.

## Unfiltered Regeneration Failure

`STATE_SURFACES_SCRATCH=<order-scratch>/paint-control/full-attempt npm --prefix ui
run resolve-state-surfaces` attempts the full inventory, without theme, group,
condition or probe filtering. The script stops after **2317 renders** and
**55.086 seconds** of capture/build wall time, with acceptanceComplete=false:

```text
Painted capture progress: renders=2041; wall=48.277s
Incomplete painted probe: renders=2317; wall=55.086s; acceptanceComplete=false
Error: Measurement failure width-639/Vector/candidate/delete/ready-exceeds/row-hover/unarmed/hsl(185 40% 40%): weak foreground mask; mode=0.131868 < 0.3; top8=[{"rgb":[21,47,49],"count":96},{"rgb":[21,46,48],"count":46},{"rgb":[23,51,53],"count":44},{"rgb":[23,52,54],"count":44},{"rgb":[22,49,51],"count":37},{"rgb":[22,48,50],"count":36},{"rgb":[22,50,52],"count":36},{"rgb":[21,48,49],"count":24}]
```

The 11×11 CSS-pixel Trash2 clip has **728 mask pixels**, with 96 in the mode.
The real row-hover matches; SVG hover and focus-visible do not. Its named
[failure receipt](paint-control/full-attempt-measurement-failure.json) and
[painted](paint-control/full-attempt-measurement-failure-painted.png) /
[control](paint-control/full-attempt-measurement-failure-control.png) captures
are retained. This failure occurs before the full capture can reach the
verified-key failure; changing only treatment of verified-key glow would not
resolve the complete inventory's floor.

The earlier baseline/shipped probe stopped after **105 renders / 12.302s** on
the verified key. Neither run is a completed regeneration or acceptance
receipt. Failed/incomplete captures remain in the prescribed scratch tree.
The checked `state-surfaces.resolved.json` is byte-identical to the resumed
head's stale receipt; no provisional colors or search output replaced it.

## Gates and Retained Proof

[Exact commands and verbatim tails](paint-control/commands.md), with
[argv/cwd/exit/timing records](paint-control/commands.json), record each bounded
foreground invocation. Every command has completed; no process remains running.

```text
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 2 passed (3)
      Tests  15 passed (15)
   Start at  14:38:30
   Duration  1.12s (transform 228ms, setup 85ms, collect 383ms, tests 464ms, environment 512ms, prepare 120ms)
```

```text
npm --prefix ui run check
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync

> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
```

Node syntax checks on the generator, PNG helper and diagnostic, and
`git diff --check`, return no output and exit zero. No changed Python target
requires Black/flake8/mypy. Full UI/build, owner-target guard, both complete
offline suites and separate reachability were **not rerun after this stop**;
no current pass is claimed for them. No #885 exception is invoked.

The accepted [unreachable inventory and capture links](control-backdrop-stop-report.md#reachable-inventory-implemented)
remain intact: no hovered sidebar glyph, no optional-absent in a required row,
no required-missing in an optional row, and no absent/missing pair without a
shared reachable context. The accepted real-action readbacks and captures are
retained; no substitute context was measured.

The accepted [product proof](product-proof.json) remains historical evidence:
selected Gilded/Vector labels have zero changed pixels, selected Veil has the
815-pixel mandatory anchor correction to `[184,61,122]`, and all six isolated
halo comparisons are identical. The relevant product sources were unchanged
in this run. This is not new proof for every reachable label state.

**No approved Amendment-4 group maxima, assignments, exceptions, regenerated
tables or swatches exist from this run.** Plants were not executed: their
protocol requires an unplanted passing control, which this run cannot produce.
No PR-body update, merge-main, push or PR merge is claimed. All previous commit
IDs remain; no rewrite, rebase, amend, force push or stash occurred. No paid
call, gateway/app lane, owner service, save/template/reference write, secret
store, main-checkout or other-worktree mutation occurred.

## Coordinator Question and Stop Rule

The common order's escape hatch requires: “if honest attempts cannot satisfy a
rule or a gate, STOP and write a stop-report (what you tried, exact errors, your
diagnosis).” Its Codex-specific notes require a stop for a false premise. The
fourth clarification requires one 30% floor for every surface and candidate;
these production captures fail it repeatedly. Lowering the floor, suppressing
product glow in both captures, narrowing the clip or excluding mask pixels
would each change the frozen measurement rule and is not authorized.

What measurement rule should apply to both (1) the verified key whose required
mask includes bloom across the full clip and (2) the translucent/scanline delete
candidate whose mode is only 96/728? A ruling limited to the verified-key
ancestor filter does not resolve the second failure. An asynchronous ruling
request was sent; no answer had arrived when this report was written.

Codex, GPT-6.
