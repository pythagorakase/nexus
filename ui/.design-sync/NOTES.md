# NEXUS Iris — design-sync notes

Repo-specific gotchas for `/design-sync`. Read this before any re-sync.

## Architecture: app, not a component library

`nexus-ui` is a **Vite PWA application**, not a publishable component library — its
`dist/` is an app/server build, and `node_modules/nexus-ui` doesn't exist. The
converter expects an installed library with a `dist/` + `.d.ts` tree, so we route
around it:

1. **`cfg.buildCmd` = `node .design-sync/build.mjs`** which: (a) runs
   `gen-entry.mjs` to regenerate `.cache/lib-entry.tsx` (`export *` of all 95
   component modules + the default re-exports + `DesignThemeRoot`) and
   `.cache/componentSrcMap.json`; (b) runs a **Vite library build**
   (`vite.lib.config.mts`) → clean ESM `.cache/lib-dist/index.js` + extracted
   `style.css` (React externalized); (c) rewrites the brand `@font-face`
   `/fonts/` urls so the converter can copy the TTFs.
2. **Converter is run with a phantom `--entry`:**
   `node .ds-sync/package-build.mjs --config .design-sync/config.json --node-modules ./node_modules --entry ./.design-sync/.cache/lib-dist/index.js --out ./ds-bundle`
   The `--entry` points at the Vite dist (real → bundles the clean, pre-resolved
   JS, no app-isms). Vite absorbs the `@/` barrels, CSS side-effects, and font
   assets that esbuild (the converter's bundler) chokes on.
3. **Discovery is via `componentSrcMap`** (95 entries) because there's no `.d.ts`
   tree. This is a deliberate full enumeration (the skill's usual "sparse only"
   rule doesn't apply — discovery depends on it). `gen-entry.mjs` regenerates
   `componentSrcMap.json`; **on a component add/remove, re-merge it into
   `config.json`** (it's static there). The `general` group = the shadcn `ui/`
   primitives (the converter treats `ui` as a generic container → `general`).

## Provider / theme

- `cfg.provider = DesignThemeRoot` (in `.design-sync/ds-provider.tsx`, exported
  through the Vite entry). It mounts `QueryClientProvider` (retries off — the
  headless `/api/settings` fetch fails and falls back to Veil keeper defaults) →
  `ThemeProvider` → `FontProvider` → a `.dark` div. So every card renders in the
  **Veil** theme with brand fonts, and components that call
  `useTheme`/`useFonts`/`useSettings` mount instead of throwing.
- **Per-preview theme override:** a preview can show a non-Veil theme by setting
  `window.localStorage?.setItem("nexus-theme", "gilded"|"vector"|"veil")` at the
  module top level (runs at import, before `ThemeProvider` seeds from it). Used
  for `deco/*` (Gilded — `DecoFrame` gates its corners on `isGilded`) and the
  splash compositions. Veil frames stay Veil.

## Preview authoring recipe (proven)

- `.design-sync/previews/<Name>.tsx`, import from `"nexus-ui"`, each named export
  = one graded cell, 2-5 cells. Never wrap in a provider (cfg.provider does it).
  Inline styles for layout glue only; component keeps its own classes. Realistic
  NEXUS story-engine content; Chicago Title Case labels.
- **Overlays** (Dialog/Popover/DropdownMenu/Tooltip/Sheet/Drawer/HoverCard/
  ContextMenu/Select/Command/Menubar/NavigationMenu/AlertDialog): render OPEN.
  - **Dialog**: `open modal={false}` — otherwise the `bg-black/80` overlay blacks
    out the cell.
  - **Tooltip**: wrap in `TooltipProvider`, `open` on `Tooltip`, pad the trigger
    (~48px) + `side` so the portalled bubble lands in the captured cell.
- Static states via `defaultChecked` / `defaultValue` / `defaultOpen` (no React
  state needed); `defaultChecked disabled` is a useful distinct state.
- Full-bleed overlay components (`veil/*` frames) need a sized relative parent
  (e.g. 560×360) to frame.
- Review sheet renders each cell as a populated top band + an empty band below —
  the empty band is sheet layout, NOT a missing render.

## Known cosmetic issues (polish before final upload)

- 51 shadcn primitives land in group `general` (the converter skips `ui` as a
  generic container). Acceptable, but a tidier grouping (e.g. "Components") would
  improve the pane. Regroup via docsMap category stubs if desired.
- Each card cell reserves a tall viewport (content top, empty below). Cosmetic.

## Re-sync risks (watch-list)

- `componentSrcMap` in `config.json` is static; a component add/remove requires
  re-merging `.cache/componentSrcMap.json` (run `build.mjs` then re-merge).
- The phantom-`--entry` technique depends on `resolveDistEntry(soft)` returning
  null for a nonexistent path — verify if the converter is upgraded.
- `build.mjs`'s font-url rewrite (`/fonts/` → `../../../client/public/fonts/`) is
  path-depth-specific to `.cache/lib-dist/`.
- Playwright/Chromium installed under `.ds-sync/node_modules` + `~/.cache/ms-playwright`.
- **`pages/dev-orrery/` is excluded from the bundle** (`gen-entry.mjs` `find` filter).
  It's the internal `/dev/orrery` audit dashboard (#430, a separate "design-package
  port"), not IRIS's customer design system — its viz deps must not bloat the synced
  bundle. If a genuinely new IRIS component appears (e.g. `Intertitle`, #456), it rides
  the bundle uncarded until deliberately added to `config.json`'s `componentSrcMap` with
  an authored preview. Never blind-merge `.cache/componentSrcMap.json`: discovery drifts
  (it renamed the `Form` card's primary export to `FormItem`).

## Component-type recipes (folded from wave-2 authoring)

Overlays — render OPEN so the card shows content; pad portalled content 140-220px so
it lands in the ~900×700 capture cell:
- Dialog / Sheet / Popover / Drawer / AlertDialog: `open modal={false}` (a modal overlay blacks out the cell).
- HoverCard / Select: `open` (Select also `position="item-aligned"`).
- Tooltip: `TooltipProvider` + `open` + padded trigger + `side`.
- Menubar / NavigationMenu: `value` on the Root (and Item) = the open-menu id.
- DropdownMenu: `open`.
- ContextMenu: can't be forced via `open` (position derives from the pointer event) — ref the trigger and dispatch a synthetic `contextmenu` MouseEvent (clientX/Y from its rect) in a mount `useEffect`.
- Toast / Toaster: Radix `Toast.Root` returns null without a `ToastViewport`; mount one with inline `position:static` + column flex so toasts flow inside the cell.

Compounds / context:
- Form: `const form = useForm()` inside the cell (`react-hook-form` is bundled; only react/react-dom/nexus-ui are externalized). Errors via `form.setError` in a `useEffect`.
- Sidebar: `collapsible="none"` inside its `SidebarProvider` for an always-visible inline variant.
- ChartContainer: recharts + theme `--color-*` vars work.

Layout primitives (ScrollArea, ResizablePanelGroup, Collapsible, AspectRatio): need explicit width/height + `border:1px solid hsl(var(--border))`; style inline via `hsl(var(--token))`.

Full-screen compositions (splash/*, ErrorBoundary fallback): size the wrapper to ~the capture viewport (~900×690 / 760×620, overflow:hidden) — internals use vh/vw that resolve against the viewport, not the wrapper.

Screenshot groups: `ai/*` → `ai`; shadcn primitives + loose → `general`; deco/veil/splash → own dirs.

## Data-bound rescues (fetch stub) — no floor cards remain

All 95 components ship as authored cards. The data-bound panes render populated via
the GET-only `DesignThemeRoot` fetch stub (`ds-provider.tsx`):

- **CharactersPane** — mocks `/api/characters` (cast roster) + `/api/characters/<id>/images`
  (→ `[]`). The images route MUST match the `<id>` segment; a stub that only matches
  `/api/characters/images` falls through to the cast mock and crashes on
  `portraitSrc(undefined)` — that was the original blank-card cause.
- **SettingsPane** — mocks `/api/settings` with a full payload (model roles, slider
  bounds, keeper fonts). The theme it returns ECHOES the preview's own
  `localStorage["nexus-theme"]`, NOT a hardcoded `"veil"` — otherwise the Theme/Font
  providers adopt the mock's theme and override every deco/splash card. Per-component
  capture isolation keeps this from bleeding across cards. Its preview wrapper keeps
  the `nexus-shell` class (overriding 100vh + the 52px TopBar grid row) so the
  RESET/COMMIT footer buttons get their shell-scoped `.btn-soft`/`.btn-primary`
  styling — a bare flex wrapper renders them as default browser buttons (Codex review).
- SlotSelector via `/api/story/new/slots`; SeedPhase / LocationPhase card their
  on-brand generating states.

## ds-provider QueryClient

`DesignThemeRoot` uses the app's `queryClient` (`lib/queryClient.ts`) so the
exported provider carries the default `queryFn` (`getQueryFn`) — components that
rely on it (e.g. `useSettingsQuery`) resolve / fall back cleanly instead of
erroring "Missing queryFn".

## More layout gotchas (wave-3 nexus)

- `.nexus-shell` hardcodes `height:100vh` + a `52px 1fr` row grid — wrapping a
  non-TopBar pane as its only child clips it; use a plain sized flex container.
- `.rail-right` is `display:none` below 1100px; the 900px capture viewport needs a
  scoped `<style>` override (RightLedger preview does this). Data-bound panes
  populate best via direct props (NarrativePane `engine`, MapPane `worldOutline`).
