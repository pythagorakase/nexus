# Browser-Resolved State Surfaces

Run from the worktree root:

```sh
npm --prefix ui ci
# Only needed when the pinned browser is absent:
npx --prefix ui playwright install chromium
npm --prefix ui run resolve-state-surfaces
```

Set `STATE_SURFACES_SCRATCH` to an order-specific scratch directory when required
by a work order. Otherwise the script creates a temporary directory. It starts
no server: esbuild bundles the real production renderers and seeded React Query
data, Vite runs the production PostCSS/Tailwind pipeline, and Playwright loads a
`file://` page with HTTP(S) requests aborted. The conditions are 1200×900, dark
color scheme, and reduced motion. Place selection opens the production dialog;
the capture clicks its existing Close button and waits for dismissal.

The receipt contains 29 contexts per theme in shipped and historical-pigment
phases, the exact computed color strings, each compositing ancestor's opacity,
background and opacity stacking-context flag, the SVG terrain colors and radial
wash endpoints, and browser-serialized candidate pigments. Historical pigments
are rendered on the current geometry; historical sidebar rings are opaque.
Interior paints exclude edge antialiasing and glow, as the fixed proof requires.

The SHA-256 guards stylesheet sources, the four state component sources, fixture,
regenerator, toolchain configurations and lockfile, browser revision and emulation
conditions. Vitest checks that receipt and reads the JSON without launching or
installing a browser. The joint search substitutes only the candidate pigment
at the surface node; all opacity groups and backdrops remain browser-reported.

After regeneration, run `npm --prefix ui test -- state-shades`. A changed receipt
also requires refreshing the checked evidence tables; regeneration alone cannot
silently bless a changed palette or a changed backdrop.

Codex, GPT-6.
