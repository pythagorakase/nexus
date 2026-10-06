# Painted Core-Mean Oracle

Round 5 keeps the foreground mask: every device pixel differing between the
painted and paint-suppressed control captures. The core contains mask pixels
whose Euclidean difference in linear sRGB is at least **90% of the maximum
mask difference**. The painted color is the core's mean in linear sRGB. The
maximum pixel always belongs to the core. The receipt records `coreSize`,
`maskSize`, the retained linear triple, and the top eight mask RGB/count buckets.
The **16 device pixel** mask floor remains; there is no mode floor.

The injected control covers the tagged subtree and its `::before`/`::after`.
It sets fill, stroke, background-color, color, border-color, outline-color,
text-decoration-color, column-rule-color, caret-color, stop-color, flood-color
and lighting-color to transparent, and background-image to none, all with
`!important`. Layout, visibility, shadows and filters keep their declarations.

Every regeneration first renders the full default inventory for each theme
with all tokens in a surface group set to its shipped present/rest pigment.
`proof.calibration` records samples and per-context pair maxima. Every identical
pigment comparison must be **≤1.0 deutan ΔE**. A failure stops regeneration with
the numbers and the two painted PNGs; the threshold and tolerance are fixed.

The fixture mounts real NexusLayout, KeysSection, ModelSection and MapPane
with seeded local data and the production Vite build's emitted CSS in shipped
order. No DOM/cascade/compositing model determines a color. The convention is
file://, HTTP(S) aborted, device scale 4, 1200×900 default, dark scheme and
reduced motion, plus every CSS-derived emulatable media condition. Range
breakpoints partition width/height into distinct integer viewport bands,
including singleton bands for coincident inclusive bounds. Finite bands use
an integer midpoint; the default 1200×900 remains its band's representative,
and an unbounded upper band uses its first integer. Discrete feature values
are crossed with those bands; compound/nested preludes are conjunctions and
comma lists are alternatives. One vector per distinct satisfied-prelude set
is retained, and every included prelude must be satisfied. Print and forced
colors are recorded as excluded environments, never rendered. Unsupported
features and container preludes fail by name. The shipped CSS has **9 width
bands × 2 motion values = 18 vectors**, expanded into **27 condition renders**
by motion start/trough phases. IDs name band and motion, for example
`w1101-1279/reduce` and `w1101-1279/motion/{start,trough}`. Pair scoring takes
the minimum over all four independent phase pairs within each motion band. Mouse hover
and keyboard Tab produce the recorded contexts. Delayed tooltips triggered by hover/Tab are awaited in their final open state;
click/leave contexts await closure. Every capture records these settle criteria
and pseudo-class readbacks. All finite document animations/transitions finish,
including overlapping siblings and portalled tooltips, before both captures; infinite animations pause at declared start/trough phases.

The inventory holds reachable states only. Hovered glyphs in sidebar row-hover contexts, absent
keys in required rows, missing keys in optional rows, and the absent/missing
pair without a shared context are excluded and documented in the evidence.

Freshness hashes every esbuild metafile input, recursive CSS imports, tooling,
configs, lockfile, browser versions and the full Tailwind client-source scan.
Vitest recomputes it in a clean Node process without launching a browser.

Run from the worktree root, using bounded condition batches:

```sh
STATE_SURFACES_SCRATCH=<order-scratch>/capture/batch-1 \
STATE_SURFACES_CONDITION=<comma-separated-condition-ids> \
STATE_SURFACES_OUTPUT=<order-scratch>/capture/shards/batch-1.json \
npm --prefix ui run resolve-state-surfaces
# Repeat for all remaining conditions, then assemble the complete inventory:
STATE_SURFACES_SCRATCH=<order-scratch>/capture \
npm --prefix ui run resolve-state-surfaces -- --assemble
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
```

The named command runs without environment variables, using
`scratchpad/777-S2/after-review-r5/capture`. Its bound is derived from the
condition count: 589 seconds per four-condition batch; filtered commands keep
a 589-second bound. Filtered/probe runs require a
scratch output and cannot replace the acceptance receipt. Assembly requires
complete unique conditions, all themes and identical current fingerprints.
Failed captures retain named diagnostic PNGs and acceptanceComplete=false.
The per-group exhaustive search accepts 15 when reachable, otherwise the
group's maximum; ties prefer the fewest changed tokens. Tables, swatches and
exception manifests must be refreshed alongside a changed accepted palette.

The checked-in plants protocol runs in bounded stages; see `plants.mjs`.
It first requires a passing unplanted control, then records stale rejection,
full regeneration (or a named measurement failure), fresh rejection and
restoration for each named plant. Scratch copies alone are mutated.

Codex, GPT-6.
