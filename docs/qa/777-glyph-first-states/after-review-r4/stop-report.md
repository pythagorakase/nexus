# After the Fourth Independent Review and the Panel — Stop Report

Date: 2026-10-05. Started at `f648a18a2468ddb785a62380e54090ab391166d5` on
`claude/777-glyph-first-states`, PR #1099. **STOP: the literal selected-label
pixel-equality requirement conflicts with the retained exact Veil anchor.**
The common working rules require a stop-report when a hard rule cannot be
satisfied. This is partial product work, not completed round-four acceptance.

## Conflicting Requirements and Browser Evidence

Amendment 4 in `1099-fix-r4.md` §3 requires a separate `LABEL_COLOR` map to the
pre-PR **global tokens**, with appearance unchanged; the final requested proof
requires the label pixel-identical to `8ccd3008`. The baseline selected label
uses `var(--brass)` (`git show 8ccd3008:ui/client/src/components/nexus/MapPane.tsx`).
Amendment 3 and round-four §1 require Veil's `--brass` to resolve to exactly
`#b83d7a`. The pinned baseline declares `--brass: hsl(320 55% 48%)`, which
Chromium serializes as `rgb(190, 55, 145)`. These cannot be equal.

The restored mapping was actually rendered with the production Vite build's
CSS, real MapPane, and seeded query data. At 1200×900, dark, reduced motion,
device scale 4, file:// and HTTP(S) aborted, Chromium 153.0.8010.12 paints the
selected Veil label `rgb(184, 61, 122)`. Overlaying the pinned baseline global
declarations in the identical DOM produces `rgb(190, 55, 145)`: **815 changed
pixels in the 136×52 device-pixel clip**. The same comparisons give zero
changed pixels in Gilded and Vector. Before/after PNGs and the unrounded,
per-comparison receipt are checked in beside this report. The Veil pair was
visually inspected. No compositing model is used to compare those pixels.

The halo does not have this conflict: `--glow-soft` contains the original
literal two tones. Restoring that declaration gives identical computed shadows
and **6/6 pixel-identical halo-only comparisons** (three themes, normal/over).
Those comparisons keep the glyph fill fixed while changing only the halo
mapping, so they make no claim that the tuned meter fill matches the old fill.

A literal old-pixel label would require a local override/literal or a different
mapping; none is authorized by the retained global freeze and the prescribed
`LABEL_COLOR` mapping. Removing the mandatory anchor would violate the owner's
settled color model. Neither workaround was shipped. An asynchronous question
was sent while independent product fixes continued; no answer was received.

## Completed Product Work

- Stable `<path>` fill and ring nodes replace element-type swaps. The ring is
  mounted and hidden at rest, so it also retains identity. A stable transparent
  circular hit path keeps the original canvas click area; visible paths do not
  take pointer events. Each outer map group remains keyed by place id.
- Place-name text now reads the separate old global `LABEL_COLOR` mapping;
  glyphs and leaders retain the state mapping.
- The memory fill's `box-shadow: var(--glow-soft)` is restored; only the fill
  background and warning use the state pigments.
- Sidebar glyphs use 9px boxes / `-4.5 -4.5 9 9`, a 2.5px fill, 4px ring and 1px
  stroke. Existing row centering/padding is retained; spec §§3.1/3.2 agree.
- Component regressions verify stable nodes through rest/hovered/selected/rest,
  sidebar geometry, and both inverse-zoom/coordinate/leader checks. The native
  delete timer is still armed at window−100 and disarmed by window+500.

The real Chromium mouse probe enters the original circular target at a corner
(offset 2px,1.6px), clicks, moves out, then selects another place through its
row: **3/3 themes hovered→selected→rest with the same fill/ring/hit nodes**.
The component tests are complementary jsdom event/identity proofs; no claim is
made that jsdom performs hit testing. The diagnostic uses the prior fixture
with only scratch seed coordinates tightened to keep every pin visible. It is
**not** the required production-NexusLayout acceptance oracle. Its build uses
the real Vite config and writes to the prescribed scratch folder. The replay
script and dependency-free PNG decoder are checked in as diagnostic evidence.
No gateway/app server, database, Keychain or provider is involved.

An initial diagnostic used widely separated old fixture coordinates and missed
the clipped target; that run failed waiting for the dialog. Tightening only
scratch seed coordinates fixed the diagnostic visibility. A separate first
launch failed because Vite's CJS entry has no ESM named `build`; the replay
uses the project's CJS export. Neither failed attempt is counted as evidence.

## Work Not Completed

The replacement production shell/sections oracle, candidate renders, media
inventory, module-graph hash, per-group exhaustive search, acceptance tests,
plants script, regenerated tables/swatches and PR body update remain undone.
The committed `state-surfaces.resolved.json` still describes `f648a18a` and is
**stale after these product edits**. The old closure also needs Amendment 4's
explicit halo exemption and non-state label enumeration. No full state-shades
or client acceptance pass is claimed. No regeneration count/wall time or
Amendment-4 group maxima/exceptions exist for this partial run. Previous
round-three numbers cannot stand in for them.

The prescribed final owner-target, offline split, reachability and full UI/build
gates were not run after the ordered stop. The diagnostic's production CSS
build is not represented as the final `npm --prefix ui run build` gate. Python
Black, flake8 and mypy are not applicable: no Python targets changed.
No paid call, gateway lane, product Python, nexus.toml, migration or owner DB
write occurred. No main checkout/other worktree was modified; no stash, rebase,
amend, force push or PR merge. Useful product changes and this stop evidence
are committed locally. **No push**: the full proof gates are not satisfied.
No merge of origin/main is claimed; that remains required before a later push.

## Exact Commands and Verbatim Tails

Import provenance:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/nexus/__init__.py
```

Bootstrap (the npm advisory is left unchanged):

```text
npm --prefix ui ci
added 959 packages, and audited 960 packages in 5s

34 vulnerabilities (2 low, 8 moderate, 23 high, 1 critical)
```

```text
npm --prefix ui test -- StateGlyphs MapPane shell-accessibility

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ src/shell-accessibility.test.ts (9 tests) 54ms
 ✓ src/components/nexus/MapPane.test.tsx (3 tests) 129ms
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 424ms

 Test Files  3 passed (3)
      Tests  18 passed (18)
   Start at  12:57:15
   Duration  1.46s (transform 226ms, setup 173ms, collect 684ms, tests 608ms, environment 887ms, prepare 112ms)

```

```text
npm --prefix ui run check

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

```

```text
STATE_SURFACES_SCRATCH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4 node docs/qa/777-glyph-first-states/after-review-r4/product-probe.mjs
veil selected label: rgb(190, 55, 145) -> rgb(184, 61, 122); changed device pixels=815
gilded selected label: rgb(209, 158, 31) -> rgb(209, 158, 31); changed device pixels=0
vector selected label: rgb(0, 234, 255) -> rgb(0, 234, 255); changed device pixels=0
Halo-only comparisons: 6/6 pixel-identical; computed shadows unchanged
Real pointer sequences: 3/3 hovered -> selected -> rest; stable fill/ring/hit node identity
Chromium 153.0.8010.12; deviceScaleFactor=4; page errors=0
```

Earlier focused commands also passed: `npm --prefix ui test -- StateGlyphs
MapPane` initially 8/8 and after the node-identity test 9/9. The final 18-test
run above includes both files and shell-accessibility. `git diff --check`
returns no output and exit 0.

## Coordinator Question

Does Amendment 4 retain Amendment 3's sole anchor exemption for the **selected
Veil label**, so equality is required for all other label pixels, or does it
explicitly authorize a frozen old pigment for this label while keeping the
brand anchor? The halo needs no exemption. The choice must resolve the exact
mapping/freeze rules before the literal requested equality can be certified.
No owner color-model decision is reopened.

Codex, GPT-6.
