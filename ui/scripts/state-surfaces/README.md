# Painted Control-Capture Oracle (Round-Four Work in Progress)

The control-capture replacement is blocked by a production interaction mismatch.
See [the interaction stop-report](../../../docs/qa/777-glyph-first-states/after-review-r4/interaction-stop-report.md).
The checked acceptance receipt remains stale. No tables, swatches, group maxima
or exceptions have been regenerated or approved from this partial work.

The draft bundles the real NexusLayout and production settings sections. Vite
emits the production CSS in its normal order; the reversed fixture stylesheet
has been removed. Browser captures use file://, aborted HTTP(S), device scale 4,
1200×900 default, dark scheme and reduced motion. Media preludes are inventoried
with additional emulation variants; compound-condition coverage remains to be
validated. Hover uses the actual mouse; focus-visible uses keyboard Tab.
Finite browser animations/transitions are awaited. Infinite animations are
paused at declared phases. Candidates are rendered, never composited by hand.

Each bounding-box sample has a painted PNG and a visibility:hidden control.
The mask contains changed device pixels; its RGB mode, mask size and top eight
colors are recorded. The trial mode floor is 8%: a 40% trial rejected a real
verified key whose own shadow enlarged the mask (interior mode 423/2304).
The 8% floor has not yet been validated across the complete inventory.
Empty or weak masks throw named measurement failures.

Freshness hashes path-delimited file bytes from the esbuild metafile, recursive
CSS imports, tooling, Chromium/Playwright configuration and Tailwind's complete
client source scan. Vitest computes the fingerprint in a clean Node process,
then refuses stale or incomplete receipts before using samples. The per-group
search and nine-plant protocol are draft implementations awaiting a complete
unplanted control receipt. Plants have not been run; their command splitting,
acceptance-failure classification and complete media coverage remain unfinished.

Run full regeneration only after the coordinator settles the inventory:

```sh
STATE_SURFACES_SCRATCH=<order-scratch>/capture npm --prefix ui run resolve-state-surfaces
npm --prefix ui test -- state-shades StateGlyphs shell-accessibility
```

Filtered probes require an explicit STATE_SURFACES_OUTPUT scratch path and
cannot overwrite ui/client/src/state-surfaces.resolved.json. A partial success
is marked acceptanceComplete=false; a failure writes incomplete-probe.json in
scratch and names its context. No partial probe satisfies the acceptance gates.

Codex, GPT-6.
