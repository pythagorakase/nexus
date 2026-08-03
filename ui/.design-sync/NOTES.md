# NEXUS Iris — design-sync notes

Repo-specific gotchas for `/design-sync`. Read this before any re-sync.

## Architecture: app, not a component library

`nexus-ui` is a **Vite PWA application**, not a publishable component library — its
`dist/` is an app/server build, and `node_modules/nexus-ui` doesn't exist. The
converter expects an installed library with a `dist/` + `.d.ts` tree, so we route
around it:

1. **`cfg.buildCmd` = `node .design-sync/build.mjs`** which: (a) runs
   `gen-entry.mjs` to regenerate `.cache/lib-entry.tsx` (`export *` of all 102
   component modules + the default re-exports + `DesignThemeRoot`) and
   `.cache/componentSrcMap.json`; (b) runs a **Vite library build**
   (`vite.lib.config.mts`) → clean ESM `.cache/lib-dist/index.js` + extracted
   `style.css` (React externalized); (c) runs the dedicated declaration-only
   `tsconfig.lib.json` → a real `.cache/lib-dist/**/*.d.ts` tree plus a curated
   top-level `index.d.ts`; (d) rewrites the brand `@font-face` `/fonts/` urls so
   the converter can copy the TTFs.
2. **Converter is run with a phantom `--entry`:**
   `node .ds-sync/package-build.mjs --config .design-sync/config.json --node-modules ./node_modules --entry ./.design-sync/.cache/lib-dist/index.js --out ./ds-bundle`
   The `--entry` points at the Vite dist (real → bundles the clean, pre-resolved
   JS, no app-isms). Vite absorbs the `@/` barrels, CSS side-effects, and font
   assets that esbuild (the converter's bundler) chokes on.
3. **Discovery is curated by `componentSrcMap`** (97 entries). This is a deliberate
   full enumeration (the skill's usual "sparse only" rule doesn't apply):
   `build.mjs` generates the declaration `index.d.ts` from this exact surface so
   the hundreds of runtime compound exports do not become standalone cards.
   `gen-entry.mjs` regenerates `componentSrcMap.json`; **on a component add/remove,
   re-merge it into `config.json`** (it's static there). The `general` group = the
   shadcn `ui/` primitives (the converter treats `ui` as a generic container →
   `general`).

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

## FIXED (#657): real `.d.ts` prop contracts

The lib build now emits **129 declaration files** under `.cache/lib-dist/`, and
`package.json#types` points the converter at the curated top-level declaration barrel.
The converter resolves real props for **97/97** configured components instead of falling
back to `interface <Name>Props { [key: string]: unknown }` for all of them.

Two details are load-bearing:
- The converter's package-wide glob ignores hidden directories. The top-level
  `index.d.ts` makes `lib-dist/` the declaration root; emitting only the nested tsc
  output would still report `[DTS] parsed 0 .d.ts files`.
- The runtime entry intentionally exports hundreds of compound pieces. The declaration
  barrel exports only the 97 committed `componentSrcMap` roots so declaration discovery
  does not turn every `DialogTrigger`/`TableRow`-style subpart into a new card.

Thirteen root components genuinely accept no props. Their `cfg.dtsPropsFor` entries use
`[key: string]: never` so the generated contracts say exactly that instead of falling
back to the permissive unknown stub. The one remaining literal
`[key: string]: unknown` in the emitted tree belongs to `NarrativeProgress.data`, an
open-ended server payload — it is not a component prop contract.

## Known render warns

**As of 2026-07-30 the final driver run emits ZERO warn lines** — no `[GRID_OVERFLOW]`,
no `[RENDER_*]`, no `[FONT_*]`, no `[DOCS_*]`. Treat any warn on a future run as new:
look at it, then fix it or record it here.

## Known cosmetic issues (polish before final upload)

- The shadcn primitives land in group `general` (the converter treats `ui` as a generic
  container). Acceptable, but a tidier grouping (e.g. "Components") would improve the
  pane. Regroup via docsMap category stubs if desired.
- Each card cell reserves a tall viewport (content top, empty below). Cosmetic.

## Re-sync risks (watch-list)

- `componentSrcMap` in `config.json` is static; a component add/remove requires
  re-merging `.cache/componentSrcMap.json` (run `build.mjs` then re-merge).
- The phantom-`--entry` technique depends on `resolveDistEntry(soft)` returning
  null for a nonexistent path — verify if the converter is upgraded.
- `build.mjs`'s font-url rewrite (`/fonts/` → `../../../client/public/fonts/`) is
  path-depth-specific to `.cache/lib-dist/`.
- Playwright lives in `.ds-sync/node_modules` (1.61.0, which pins chromium rev 1228).
  The browser cache on macOS is **`~/Library/Caches/ms-playwright`** — not
  `~/.cache/ms-playwright`, which is the Linux path this file used to name.
- **`pages/dev-orrery/` is excluded from the bundle** (`gen-entry.mjs` `find` filter).
  It's the internal `/dev/orrery` audit dashboard (#430, a separate "design-package
  port"), not IRIS's customer design system — its viz deps must not bloat the synced
  bundle. A genuinely new IRIS component rides the bundle uncarded until deliberately
  added to `config.json`'s `componentSrcMap` with an authored preview — `Intertitle`
  (#456) and `LocalModelRows` (#465 Phase 1b) were both carded on 2026-07-30, so the
  standing deferral list is currently empty. Never blind-merge
  `.cache/componentSrcMap.json`: discovery drifts (it still renames the `Form` card's
  primary export to `FormItem` — keep the committed `Form` pin, drop `FormItem`).
- **The cached anchor is always one generation stale.** `.design-sync/.cache/remote-sync.json`
  is fetched at the START of a run, and that run then uploads a NEW `_ds_sync.json`. So
  the file left on disk describes the run *before* last. Re-fetch it from the project, or
  `cp ds-bundle/_ds_sync.json .design-sync/.cache/remote-sync.json` after confirming that
  file's `auxSha`/`bundleSha12` match the live project's.

## Running the sync from a git worktree

The owner often has backend work in the main checkout, so this sync is normally run
from a `git worktree` to keep the durable-set edits (`config.json`, `ds-provider.tsx`,
`previews/*.tsx`) out of their `git status`. Everything the sync needs that is
gitignored must be re-provisioned there:

- **`ui/node_modules` — hardlink-copy it, NEVER symlink it.** `cp -Rl ../../../ui/node_modules
  ./node_modules` (~14 s, near-zero disk, shared inodes). esbuild inlines each resolved
  module's path as a comment inside `_preview/<Name>.js`, and a symlinked `node_modules`
  resolves to its realpath — emitting `../../../../ui/node_modules/lucide-react/…`
  instead of `node_modules/lucide-react/…`. That silently churns `renderHashes` for
  every component whose preview imports a **bundled** dep (lucide-react, recharts,
  cmdk): 10 components, phantom `changed` entries, a spurious `[SPOT_CHECK]` canary, and
  an upload set of 12 instead of 2. Previews importing only the externalized `nexus-ui`
  (Button, Badge, Card, Input, Dialog) are unaffected, which is the tell-tale signature.
  Uploaded bytes must not depend on which directory the sync ran from.
- `.ds-sync/`: `cp -r` the scripts from the skill dir, copy `package.json` +
  `package-lock.json`, then symlinking `.ds-sync/node_modules` at the main checkout IS
  safe — converter deps never reach the emitted artifacts.
- `.design-sync/.cache/remote-sync.json` (the anchor) and, optionally,
  `.design-sync/.cache/review/` to carry grade state. Neither is in git.
- `.design-sync/previews/` needs nothing — it is tracked, so it arrives with the worktree.

## Card layout: `cfg.overrides` cardMode (triaged 2026-07-30)

Validate's `[GRID_OVERFLOW]` check flags stories that crop or escape their cell in the
product's grid view. 65 of 97 components were flagged and had been shipping untriaged
since the first sync (`config.json` had no `overrides` key at all). All 65 now carry an
override: **51 `{"cardMode":"column"}"`** (wide — keeps every story, one per full-width
row) and **14 `{"cardMode":"single", "primaryStory": …}`** for the portal/fixed-position
overlays, where a single open overlay is the honest card anyway. Primary picks favour the
open state showing real content over a trivial one (`Select`→`ModelPicker` not `Closed`,
`WaitScreen`→`Generating`, `AlertDialog`→`WipeSlot`, `HoverCard`→`CharacterCard`).

- **These overrides do NOT invalidate grades.** `configSlicesFor` deliberately strips
  `cardMode`/`primaryStory` from the graded component slice ("they arrange the default
  card view, not any solo-captured story"), so a layout flip carries grades forward. It
  does change each `.html`, so the 65 land in `upload.components` and trigger a
  `render_churn` `[SPOT_CHECK]` canary — that canary is expected, not a defect.
- Review sheets capture each story **solo** (`?story=`), so they show every export
  regardless of `cardMode`. To eyeball the actual card arrangement use `.review.html`.
- Judge grid overflow from `.render-check.json`'s `gridOverflow` field, never from a
  contact sheet — the sheet tiles full-card screenshots at fixed width, so it clips
  cards (e.g. `Intertitle`) that the product's grid presents fine.

## Data-bound cards share ONE query cache

A card renders all of its cells in a single page load against the one `queryClient`
singleton, so every cell necessarily sees the same payload — **per-cell mock scenarios
are impossible**. Vary cells by real props and by driving real interactions; put the
state diversity into one rich stub scenario instead.

- **`LocalModelRows`** (`/api/local-models/status` + `/download` in `ds-provider.tsx`).
  The stub is required, not a nicety: the component does
  `if (statusQuery.error && !status) throw statusQuery.error`, so an unmocked status
  endpoint throws and blanks every pane mounting it — `SettingsPane` embeds it since
  #482. The single scenario is tuned so one render shows the maximum number of row
  states (`system_ram_gb: 48` puts two 70B quants over the memory ceiling; one quant
  serving, one on disk, one downloadable, one mid-download). Catalog mirrors
  `nexus.toml [local_models]` so the cards name the real Hermes families.
- Its accordion `open` map is internal `useState` with no prop to seed it, and the
  families do not exist in the DOM until the query resolves. The `Quantizations` cell
  therefore polls briefly and clicks the component's own chevron, selecting on
  `[aria-expanded="false"]` so it is idempotent and never toggles an open family shut.
  Same principle as the ContextMenu preview: drive the real trigger, never hand-write
  the open state.
- It renders bare `<li>`s — wrap in `<ul className="model-list">` inside a
  **`.nexus-shell` ancestor**, as `SettingsPane` does. Checking that the `.lm-*` rules
  are unscoped is NOT sufficient: the component also emits `.caption`, `.btn-soft`, and
  `.btn-primary`, and nexus-layout.css defines all three ONLY under `.nexus-shell`, so a
  bare `<ul>` renders the quant labels and the EJECT / APPLY buttons as browser defaults
  (caught in Codex review of PR #656). Override the shell's `100vh` and its `52px 1fr`
  row grid locally. **When auditing a preview's wrapper, grep every class the component
  emits — not just its own namespace.** `Intertitle` was checked the same way and is
  genuinely clean (only unscoped `.intertitle*` rules).

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
