> Historical: the coordinator's second clarification resolves the histogram rule below with a visibility-hidden control capture. The subsequent interaction blocker is recorded in [interaction-stop-report.md](interaction-stop-report.md).

# Resumed Round-Four Stop Report: Histogram Rule Removes the Foreground

Date: 2026-10-05. Source head: `afbb27568aeb4a19c13103720b9c7134b48393d1`.
Branch: `claude/777-glyph-first-states`; PR #1099 remains open.
**STOP: the prescribed dominant-foreground algorithm selects the backdrop on
real solid state surfaces.** No palette or acceptance receipt is regenerated.

## The Accepted Clarification Is Resolved

The selected Veil label retains the prescribed global `--brass` mapping and
paints `rgb(184, 61, 122)` (`#b83d7a`). The existing before/after capture pair's
815 changed device pixels are now explicitly labeled **mandatory Veil anchor
correction** in `product-proof.json`. No old pigment is authorized. The pinned
Gilded and Vector selected-label comparisons remain zero changed pixels; the
existing halo-only comparisons remain 6/6 pixel-identical with computed shadows
unchanged. Those are retained prior-run comparisons, not newly broadened proof
of every label state. The old stop-report is marked historical and resolved.

## A Separate False Premise, Measured

Round-four section 1 defines foreground as “the most frequent pixel value in
the clip after removing the most frequent value (the backdrop)” and requires
a clip of the surface's bounding box. In an actual solid fill's own box the
most frequent value is the foreground. Removing it gives the wrong color:

| Real Surface | Clip, Device Pixels | Actual Pigment Mode / Count | Next Mode / Count, Selected by the Literal Rule |
| --- | --- | --- | --- |
| Veil normal `.mem-fill` | 164 × 12 | `[184,61,122]` / 1782 | `[8,11,18]` / 166 |
| Veil over `.mem-fill.over` | 352 × 12 | `[230,115,77]` / 3822 | `[8,11,18]` / 382 |
| Rest canvas `.map-state-fill` | 24 × 24 | `[230,115,77]` / 404 | `[21,17,22]` / 92 |

The literal algorithm reports the identical backdrop `[8,11,18]` for normal
and over memory, hence deutan CIEDE2000 **0**, despite the magenta and coral
interiors actually painted. The map disc's top mode is also its coral pigment;
the second-ranked mode is the surrounding pixel color. The actual clips and
full-shell screenshot were visually inspected. There is no compositing model
in this diagnostic; the RGB/count modes come directly from decoded PNG bytes.
Computed colors are included only as diagnostic labels, not as measurements.

`histogram-proof.json` holds the exact boxes and top eight histogram modes;
`normal-memory-fill.png`, `over-memory-fill.png`, `rest-map-fill.png` and
`real-shell.png` are the inspected captures. The checked-in replay and fixture
are `histogram-probe.mjs` and `histogram-fixture.tsx`. A second run with that
checked-in replay reproduced all three boxes, counts and RGB modes exactly.

The replay mounts the **actual NexusLayout**, ThemeProvider and
DeveloperModeProvider. Its real TopBar reads seeded local-model status. The
actual MapPane is mounted by a React portal into the actual `.nexus-content`;
the slot-null shell notice remains, so this is a focused diagnostic, **not**
the completed acceptance fixture. The shell's active slot is null, keeping
narrative recovery and WebSockets disabled. The shell's URL update is adapted
only to keep the `file://` transport on the same file. No production module or
CSS is altered by the probe. It uses the actual production Vite config/build
and emitted bundle CSS, with no fixture stylesheet overrides. The status data
changes through React Query; no delete, verify or persistent write is invoked.

Conditions: 1200×900, dark, reduced motion, **deviceScaleFactor 4**, file://,
HTTP(S) aborted, Chromium **153.0.8010.12**, zero page errors, zero network
requests. The replay awaits browser animation completion after two animation
frames, with no fixed sleep. Its output is exclusively in the prescribed
scratch subtree. Its first build invocation needed Vite's cwd set to the
worktree's `ui` directory for Tailwind; that failed diagnostic attempt is not
counted as evidence. The checked-in replay includes the correction.

## Disposition and Work Remaining

The common order's escape hatch says: “if honest attempts cannot satisfy a
rule or a gate, STOP and write a stop-report (what you tried, exact errors,
your diagnosis).” Treating the second-ranked backdrop as the foreground would
ship a false proof and tune shades against backgrounds. Changing the prescribed
algorithm or clip without a ruling would improvise beyond the frozen order.
An asynchronous clarification was requested; no answer had arrived when this
report was written. No default selection is treated as authorization.

The suggested correction is an explicitly authorized **browser-painted
backdrop control** or another specified foreground-identification rule; no
hand-written cascade or compositing chain should return. This report does not
implement that suggestion.

No acceptance regeneration tail/render count/wall time exists. The three
successful diagnostic clips are not represented as a full regeneration.
Amendment-4 per-group maxima, shipped assignments and exceptions are **not
available**. The oracle replacement, candidate/media inventory, module-graph
hash, group-search changes, plants, regenerated tables/swatches, full UI gates,
owner-target proof, offline suites and reachability remain unfinished. The
existing acceptance receipt remains stale after `afbb2756`'s product fixes.
The full acceptance gates were not run or claimed after this ordered stop.
Python static checks are not applicable: no Python target changed.

Useful evidence is committed locally. `afbb2756` remains in ancestry. No fetch,
merge of origin/main, PR body update or push is claimed; these require the
unfinished proof gates before release. No stash, rebase, amend, force push or
PR merge. No paid call, gateway/app server, owner service, secret-store access,
product Python, nexus.toml, migration, database write, main-checkout write or
other-worktree modification occurred.

## Exact Commands and Verbatim Tails

Import provenance:

```text
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/777-glyph-first-states/nexus/__init__.py
```

Bootstrap:

```text
npm --prefix ui ci
added 959 packages, and audited 960 packages in 7s

34 vulnerabilities (2 low, 8 moderate, 23 high, 1 critical)
```

Retained product regressions:

```text
npm --prefix ui test -- StateGlyphs MapPane shell-accessibility

[baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
 ✓ src/shell-accessibility.test.ts (9 tests) 71ms
 ✓ src/components/nexus/MapPane.test.tsx (3 tests) 125ms
 ✓ src/components/nexus/StateGlyphs.test.tsx (6 tests) 414ms

 Test Files  3 passed (3)
      Tests  18 passed (18)
   Start at  13:04:36
   Duration  1.51s (transform 299ms, setup 152ms, collect 705ms, tests 610ms, environment 1.16s, prepare 102ms)

```

Diagnostic production build and browser replay (exit 0):

```text
STATE_SURFACES_SCRATCH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/after-review-r4/histogram-proof node docs/qa/777-glyph-first-states/after-review-r4/histogram-probe.mjs
{"name":"normal-memory-fill","selector":".mem-fill","computed":"rgb(184, 61, 122)","box":{"x":934.28125,"y":25.25,"width":41,"height":3},"width":164,"height":12,"histogram":[{"rgb":[184,61,122],"count":1782},{"rgb":[8,11,18],"count":166},{"rgb":[55,33,58],"count":6},{"rgb":[53,32,58],"count":3},{"rgb":[54,32,58],"count":2},{"rgb":[34,16,33],"count":1},{"rgb":[39,18,38],"count":1},{"rgb":[82,32,64],"count":1}],"literalSelected":{"rgb":[8,11,18],"count":166}}
{"name":"over-memory-fill","selector":".mem-fill.over","computed":"rgb(230, 115, 77)","box":{"x":913.484375,"y":26.75,"width":88,"height":3},"width":352,"height":12,"histogram":[{"rgb":[230,115,77],"count":3822},{"rgb":[8,11,18],"count":382},{"rgb":[92,48,41],"count":2},{"rgb":[162,82,59],"count":2},{"rgb":[171,86,61],"count":2},{"rgb":[172,86,61],"count":2},{"rgb":[208,104,71],"count":2},{"rgb":[211,105,72],"count":2}],"literalSelected":{"rgb":[8,11,18],"count":382}}
{"name":"rest-map-fill","selector":"[data-testid=\"map-pin-2\"] .map-state-fill","computed":"rgb(230, 115, 77)","box":{"x":776,"y":643.75,"width":6,"height":6},"width":24,"height":24,"histogram":[{"rgb":[230,115,77],"count":404},{"rgb":[21,17,22],"count":92},{"rgb":[220,109,74],"count":6},{"rgb":[172,88,61],"count":3},{"rgb":[221,110,74],"count":3},{"rgb":[41,25,27],"count":2},{"rgb":[45,28,28],"count":2},{"rgb":[53,32,30],"count":2}],"literalSelected":{"rgb":[21,17,22],"count":92}}
Real NexusLayout=1; Chromium 153.0.8010.12; deviceScaleFactor=4; page errors=0; network requests=0
```

Syntax and whitespace checks:

```text
node --check docs/qa/777-glyph-first-states/after-review-r4/histogram-probe.mjs
[no output, exit 0]
git diff --check
[no output, exit 0]
```

## Coordinator Question

What browser-painted rule should identify the foreground when the foreground
is the most frequent pixel in its own bounding box? May the oracle use a
separate painted backdrop control before selecting foreground modes? The
literal second-ranked-color rule has now been disproved on actual production
memory fills. The already-resolved Veil label/halo clarification is not reopened.

Codex, GPT-6.
