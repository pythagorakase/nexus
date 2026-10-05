# Painted Mask-Mean Oracle

The sixth clarification defines the painted color as the **mean of all
foreground-mask pixel colors in linear sRGB**. Each surface is captured twice
under identical conditions. A unique attribute tags its subtree; the control
sets only **fill, stroke, background-color and color** to transparent with
`!important`. Layout, visibility, shadows and filters retain their declarations
in both captures. A drop-shadow can still change with its source alpha.

Foreground is the exact painted/control device-pixel difference. Every channel
is linearized before averaging. The receipt keeps the linear triple for
Machado deutan simulation and D65 CIELAB, the mask size, and its top eight exact
RGB/count buckets for audit. The only mask-size failure is fewer than **16
device pixels**, including an empty mask, named by context. There is no mode or
fraction floor. Swatches encode the retained mean only for display.

The fixture mounts real NexusLayout, KeysSection, ModelSection and MapPane
with seeded local data and the production Vite build's emitted CSS in shipped
order. No DOM/cascade/compositing model determines a color. The convention is
file://, HTTP(S) aborted, device scale 4, 1200×900 default, dark scheme and
reduced motion, plus every CSS-derived emulatable media condition. Mouse hover
and keyboard Tab produce the recorded contexts. Finite animations/transitions
finish before capture; infinite animations pause at declared start/trough phases.

The inventory holds reachable states only. Sidebar hovered glyphs, absent
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

Each capture command has a 589-second bound. Filtered/probe runs require a
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
