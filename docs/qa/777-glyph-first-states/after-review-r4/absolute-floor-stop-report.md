# After the Fourth Independent Review and the Panel: Absolute-Floor STOP-REPORT

Date: 2026-10-05. Resumed head: `013ba941d32eb8238e680d5c9b70f189926c3e76`.
Implementation commit: `448faad9`. Branch: `claude/777-glyph-first-states`.
PR #1099 remains open. This is the sixth stop-report, after the fifth
clarification; that clarification resolves the previous shadow/fraction blocker.

**STOP: a reachable, settled tooltip shadow splits a delete glyph's foreground
mode into 44 device pixels, below the mandated absolute floor of 64.** The
failure is reproduced with the exact new control, without changing geometry,
product opacity, any shadow/filter declaration or the mask rule. The floor is
not lowered, and the hovered context is not silently removed.

## Implemented Clarification

The control tags the surface and its descendants and suppresses only `fill`,
`stroke`, `background-color` and `color` with transparent `!important` paint.
Box shadows, filters and text shadows keep their original declarations.
`png.mjs` rejects empty masks or modes below 64 device pixels and records
`modeCount`, `modeFraction`, `maskSize` and the top eight RGB/count modes.
The shade test requires `proof.minimumModePixels === 64`, checks the mode
count against the histogram and floor, and retains the fraction as an audit.
The accepted real fixture, reachable inventory, batching, geometry, pointer,
label, halo and timer implementation remain intact. No state shade is changed.
The plants runner is split into bounded stages, but is not executed as proof.

Import provenance, from this worktree:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/nexus/__init__.py
```

## Exact Failure and Causal Isolation

The first six-condition full-candidate batch stops at:

```text
width-639/Vector/candidate/delete/ready-exceeds/row-hover/unarmed/hsl(185 40% 70%)
mode=44 device pixels < 64; fraction=0.060523
```

The mask has **727 pixels**, with three tied top RGB modes of **44 pixels**:
`[47,67,68]`, `[52,74,75]`, `[53,75,76]`. Deterministic RGB-order tie-breaking
chooses the first; no tied mode reaches 64. The clip is 11×11 CSS pixels,
44×44 device pixels, at `{x:522.03125,y:395}`. The first batch has **2346 renders /
56.323 seconds**, acceptanceComplete=false. A separate Vector/delete/width-639
capture reproduces the same histogram at **178 renders / 53.293 seconds**.
These counts are incomplete attempts, not a completed regeneration tail.

Chromium 153.0.8010.12, Playwright 1.63.0/revision 1243; DPR 4, dark, reduced
motion, file://, HTTP(S) aborted. The production NexusLayout and ModelSection
render with Vite's production CSS. Row :hover=true; glyph :hover=false;
focus-visible=false; aria-pressed=false. Computed SVG/child paint is
`rgb(148, 204, 209)`. There are **zero running animations** and zero network or
page errors. An instrumented sequence and another sequence with two additional
animation frames both retain the same failure. Three repeated capture pairs
on the failed page remain byte-identical. Extra frames are a rejected timing
hypothesis, not an accepted implementation change.

A quick direct candidate capture initially passed with a 293-pixel mode. That
was investigated, not treated as acceptance. The production tooltip had not
yet opened. Waiting for the actual tooltip by locator, re-establishing the
real row hover after scrolling, and awaiting animations reproduces the
44-pixel failure directly, three times. No fixed sleep is used.

The tooltip is the existing `.lm-tip`, text “needs 96 gb · 32 gb memory”,
`data-state=delayed-open`, box `{x:378.75,y:351.5,width:209.265625,height:30}`.
Its computed shadow is `rgba(0, 0, 0, 0.5) 0px 8px 24px 0px`. The tooltip box
ends at y=381.5; the shadow crosses the glyph at y=395. The shadow remains
painted in both prescribed captures, but spatially attenuates the glyph's RGB
into many shades, so a correct foreground no longer has a large exact-RGB mode.
This is a sibling overlay, not the surface's own glow joining the mask.

| Diagnostic | Mask | Mode | Fraction | Repetitions |
| --- | ---: | ---: | ---: | ---: |
| Production tooltip and prescribed control | 727 | 44 | 0.06052269601100413 | 3 identical pairs |
| Same tooltip, its shadow disabled in both captures, diagnostic only | 727 | 293 | 0.4030261348005502 | 3 identical pairs |
| Direct candidate before the tooltip opens | 727 | 293 | 0.4030261348005502 | 3 identical pairs |

Only the causal diagnostic injects `.lm-tip { box-shadow:none!important }`;
it is never written to product CSS or used for acceptance. Restoring the
unmodified shadow reproduces the rejection. Thus this is a real reachable
context, not an animation race, PNG decoder error or unavailable glyph.

[Tooltip proof and computed readbacks](absolute-floor/tooltip-proof.json),
[shadow-only causal proof](absolute-floor/shadow-causality.json),
[before-tooltip proof](absolute-floor/before-tooltip-proof.json),
[full shell](absolute-floor/tooltip-full-shell.png), and three prescribed
painted/control PNG pairs are retained. The full shell and the failing glyph
were visually inspected. Independent Pillow decoding matches **9/9** masks
and every top-eight RGB/count histogram
([independent check](absolute-floor/independent-png-check.json)).
[Replay](absolute-floor/tooltip-diagnostic.mjs) loads the exact production-built
fixture created by the isolated command; its `DIAGNOSTIC_NO_TIP_SHADOW=1`
mode is explicitly diagnostic. All paths/hashes are retained in
[capture inputs](absolute-floor/capture-inputs.json) and
[artifact hashes](absolute-floor/artifact-hashes.json).

## Gates and Unfinished Proof

[Every bounded command and verbatim tail](absolute-floor/commands.md), with
[argv/cwd/exit/wall-time records](absolute-floor/commands.json), includes the
failed attempts and diagnostics. Every command completed; no process remains.
The initial direct diagnostic intentionally exposed a mismatch rather than
assuming rejection. One tooltip probe timed out after scrolling dismissed it;
the corrected real-action sequence is recorded separately. Neither is a gate.

```text
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 2 passed (3)
      Tests  15 passed (15)
   Start at  14:55:55
   Duration  1.16s (transform 239ms, setup 95ms, collect 391ms, tests 478ms, environment 548ms, prepare 88ms)
```

```text
npm --prefix ui run check
> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync

> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
```

Generator, PNG helper and plants script syntax checks and `git diff --check`
return no output and exit zero. npm ci completed; the existing npm advisories
remain out of scope. Production Vite builds completed inside each capture,
with the existing eval/browser-data notices. No separate final UI build, full
UI suite, owner-target guard, offline suites or reachability gate was run after
this new measurement failure. No partial/prior run is a current complete gate.
Black/flake8/mypy are not applicable; no Python target changed.

The checked acceptance receipt is byte-identical to `013ba941` and remains
stale. No full regeneration, accepted per-group maxima/assignments/exceptions,
refreshed Amendment-2 tables/swatches or executed plant proof exists from this
run. The plants protocol requires a passing unplanted control, which cannot
be obtained while the receipt is stale and regeneration fails.

Accepted unreachable inventory remains: hovered sidebar glyph; absent key in
a required row; missing key in an optional row; absent/missing pair without a
shared reachable context. See the accepted
[readbacks and capture links](control-backdrop-stop-report.md#reachable-inventory-implemented).
The tooltip-visible hovered row is reachable and is not added to that list.

Label/halo proof remains **historical**, not newly broadened: the retained
[product proof](product-proof.json) shows selected Gilded/Vector labels with
zero changed pixels; selected Veil has the labeled mandatory 815-pixel anchor
correction and paints `[184,61,122]`; all six isolated halo comparisons are
identical. Relevant product sources and state shades are unchanged this run.
No new proof for every reachable label state is claimed.

`git fetch origin main` and `git merge origin/main` reported **Already up to
date** before the captures. All prior commits remain in ancestry. Useful work
and this evidence are committed locally. No PR-body update, final release
merge/push, PR merge, rewrite, rebase, amend, force push or stash is claimed.
No paid call, gateway/app/service lane, owner service, database write, secret
store, Python product/config/migration edit, main-checkout edit or other
worktree edit occurred.

## Coordinator Question and Stop Rule

The [common order](/Users/pythagor/nexus/temp/orders_2026_09_30/_common_codex.md)
requires: “if honest attempts cannot satisfy a rule or a gate, STOP and write a
stop-report (what you tried, exact errors, your diagnosis).” The fifth
clarification requires an absolute floor of 64 for every candidate and context;
the inventory clarification requires reachable production contexts. These
settled, repeated captures cannot satisfy both with the unchanged pixel mask.

**How should the absolute mode floor apply when a reachable glyph is painted
under an unchanged sibling tooltip shadow and its largest exact-RGB mode is
44 device pixels?** A rule for the surface's own shadow alone does not address
this sibling overlay. No lowered floor, histogram binning, shadow removal,
context exclusion or product repaint is authorized here. The complete capture,
search, tables, swatches, plants and acceptance gates still require completion
after that measurement ruling.

Codex, GPT-6.
