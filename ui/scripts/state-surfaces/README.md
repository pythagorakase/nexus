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
`proof.calibration` records samples, per-group opaque/translucent maxima and
every skipped pair. Map parts compare like-for-like. Effective opacity is the
product of computed opacity from the surface through the fixture root. Opaque
pairs compare regardless of backdrop at **≤1.0 deutan ΔE**; translucent pairs
compare at **≤2.5** only when their control means over their respective cores
agree within **1.0**. Skips name `part-distinct` or `backdrop-distinct`. Required
pairs guard against vacuous calibration: required key rows and canvas/sidebar fills
are opaque; optional key rows at rest are mandatory translucent pairs. A failure stops regeneration with
the numbers and the two painted PNGs; the threshold and tolerances are fixed.
Acceptance comparisons retain all reachable pairs over their real backdrops.

The fixture mounts real NexusLayout with its MapPane or SettingsPane,
including the real settings wrapper, FontProvider and TooltipProvider,
with seeded local query data and the matching active tab and the production Vite build's emitted CSS in shipped
order. No DOM/cascade/compositing model determines a color. The convention is
file://, HTTP(S) aborted, production public fonts fulfilled from disk through
Playwright routes, device scale 4, 1200×900 default, dark scheme and
reduced motion, plus every CSS-derived emulatable media condition. Range
breakpoints partition width/height into distinct integer viewport bands,
including singleton bands for coincident inclusive bounds. Each band's
representative is its edge nearest the default 1200×900 viewport; the
default's own band uses the default exactly. The shipped representatives are
639, 760, 767, 1023, 1100, 1200, 1280, 1281 and 1536px. Clarification 4
confirms 1281 for the 1281–1535 band: the nearest-edge rule governs over
Clarification 3's transcribed 1535 example. The historical
[stop report](../../../docs/qa/777-glyph-first-states/after-review-r5/clarification-3/stop-report.md)
records the discrepancy.
Discrete feature values
are crossed with those bands; compound/nested preludes are conjunctions and
comma lists are alternatives. One vector per distinct satisfied-prelude set
is retained, and every included prelude must be satisfied. Sixth Review:
every media list is split at depth-zero commas (parentheses may nest); each
kept alternative is its own prelude for bands, features and satisfied sets.
The evaluator's measured environment is screen, `forced-colors: none`.
Its allowlist is colon-form width/height in unsigned integer px (including min-/max- prefixes),
`prefers-reduced-motion` (reduce/no-preference), `prefers-color-scheme`
(dark/light), hover/any-hover (hover/none), pointer/any-pointer
(fine/coarse/none), and forced-colors (active/none). Media types screen/all
or no type are true; print is false; only is a no-op. Bare not print is true,
bare not screen/not all are false. Forced-colors none and bare
`not (forced-colors: active)` are true; active and bare
`not (forced-colors: none)` are false. Always-true terms are stripped and
recorded in `media.stripped`; false alternatives are individually recorded
with parent list and reason in `media.excluded`. Children under excluded
parents are skipped and named in that exclusion. Each kept nested alternative
is the conjunction of its kept parent and child. Unknown terms refuse before
exclusion; refused parents are not traversed. Negation combined with any other
term, any `or`, Level-4 range syntax, unknown types/feature values, every
feature outside this allowlist, and container preludes fail naming the prelude.
A mixed list retains its kept alternatives. Eighth Review normalizes each prelude by
stripping `/* … */` comments, lowercasing, collapsing whitespace and removing
space around `(`, `)`, `:` and `,` before grammar evaluation. Numeric values
must be safe unsigned integers in `px`; fractions, signs, exponents and other
units refuse by prelude. Every term must match completely; any residue refuses.
At-rule dispatch lowercases every name: `media` is evaluated; `container` and
`import` refuse by name. Only `supports`, `layer`, `font-face`, `keyframes`,
`property`, `scope`, `page`, `starting-style`, `charset`, `namespace`,
`font-feature-values`, `counter-style` and `view-transition` are ignored as
non-media wrappers; nested media is still evaluated. All other at-rule names,
and any name or prelude containing a backslash, refuse by name. CSS escapes
are never decoded. This audit also checks at-rules inside excluded parents;
media conditions under those parents retain Round 7's skipped-child rule.
Everything outside the modelled grammar refuses; no unknown at-rule is silently
ignored.
The shipped CSS has **9 width
bands × 2 motion values = 18 vectors**, expanded into **27 condition renders**
by motion start/trough phases. IDs name band and motion, for example
`w1101-1279/reduce` and `w1101-1279/motion/{start,trough}`. Pair scoring takes
the minimum over all four independent phase pairs within each motion band. Mouse hover
and keyboard Tab produce the recorded contexts. Hover tooltips await their expected final state; click/leave contexts await
closure. Exceeds-RAM delete focus-visible contexts measure the trash button
with the tooltip dismissed for both unarmed and armed states: after Tab, press
Escape once if a tooltip is present. A DOM signature (excluding only the
trigger's tooltip state/description), form values and dialog markup must agree
before/after, with focus-visible on the button and the family still expanded. Every capture records these settle criteria
and pseudo-class readbacks. All finite document animations/transitions finish,
including overlapping siblings and portalled tooltips, before both captures; infinite animations pause at declared start/trough phases.
Sixth Review Clarification 1 enforces tooltip settledness before each painted
and control capture: poll until presence and open-state readback match the
context expectation, within the existing 30-second Playwright settle bound
(capped by the command bound). Every sample records `settleWaitMs` and both
capture readbacks. Exceeds-RAM delete focus contexts expect a closed tooltip;
unarmed hover expects open and armed hover expects closed. The expectation
is independent of the observed state. A timeout writes the
named context/condition PNGs and readback and stops regeneration. It cannot
enter an acceptance receipt or redefine the expected state at a narrow width.

The inventory holds reachable states only. Hovered glyphs in sidebar row-hover contexts, absent
keys in required rows, missing keys in optional rows, and the absent/missing
pair without a shared context are excluded and documented in the evidence.
The focus-visible-with-tooltip-open delete variant is unmeasured: Radix row
focus/blur makes it nondeterministic as Tab moves to the nested trash button.
Across the 114 varying samples in the two regenerations compared at `61fb421c`,
its painted-core effect was at most 0.0097 Euclidean in linear sRGB (well under
1 deutan ΔE). The coordinator owns the component issue; this oracle change
leaves the production component intact.

Freshness hashes every esbuild metafile input, recursive CSS imports, tooling,
configs, lockfile, browser versions, production font files and the full
Tailwind client-source scan. Any client source edit therefore requires
regeneration; that conservative scope remains a process residual.
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
group's maximum; ties prefer the fewest changed tokens, then the largest
group minimum, then enumeration order. Tables, swatches and
exception manifests must be refreshed alongside a changed accepted palette.

The checked-in `plants.mjs` runs one bounded stage per command. It first
requires the complete unplanted state-shades suite to pass and records content
hashes before planting, checking those hashes against `git show HEAD:<path>`
(the content OID for the LFS receipt). It records stale rejection, regeneration
at the default 1200×900/dark/reduce condition only, fresh rejection, and
restoration against the saved hashes and current HEAD. Restoration checks read
the live worktree and scratch copy before any restoration write. Scratch copies
alone are mutated; node_modules `dist` directories are retained.

```sh
STATE_SURFACES_SCRATCH="$PWD/scratchpad/777-S2/after-review-r5/plants" \
node ui/scripts/state-surfaces/plants.mjs --stage control
# For each plant name in plants.mjs, repeat with --plant NAME:
# --stage stale, --stage capture, --stage fresh, --stage restore
```

Fresh diagnostics keep partial receipts `acceptanceComplete=false` and test
core means, same-value witnesses, interaction semantics, recorded tables,
root declarations and consumer closure at default only. They omit full-media
certification and do not run a reduced-domain joint search. A media plant may
add feature names to the default ID; the diagnostic records and normalizes that
ID solely for comparisons with the same physical shipping default. The protocol
uses the html-qualified dark media override that wins the production cascade.
The Sixth Review mixed-print/width plant uses Astra's exact 640–759px rule;
its capture is the new 759×900/dark/reduce representative, compared with the
prior 760px band receipt. The 1200px default lies outside the planted rule.
The Seventh Review nested `not print` plant uses Astra's exact nested rule
at the same approved 759×900 representative. The Eighth Review uppercase
`@MEDIA` plant uses Astra's exact rule at that representative too. These viewport exceptions keep
partial receipts uncertified.
Gradient paint must regenerate successfully; element-scoped state declarations
must fail. The gradient and redeclaration regressions are included.

The complete JSON receipt exceeds GitHub's ordinary blob limit; it is tracked
through the repository's existing LFS workflow without dropping samples.

Codex, GPT-6.
