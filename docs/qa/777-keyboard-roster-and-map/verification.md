# 777-KBD Verification: Keyboard Roster Access and Map Dialog Focus Return

Refs #777 (nightly-QA comment of 2026-10-09 04:50 UTC). Branch `claude/777-keyboard-roster-and-map`, cut from `claude/wave-b-integration` at `7eb9a10c`. No Python, migration, prompt or `nexus.toml` change; no gateway lane; no paid call; no database touched.

## Commits

| Commit | Content |
| --- | --- |
| `9ec29087` | Failing tests (roster keyboard, map focus return) and the red tail |
| `16b4909c` | Product change (`CharactersPane.tsx`, `MapPane.tsx`, `MapPlaceDialog.tsx`, `nexus-layout.css`) |
| later | This evidence directory and `pr-body.md` |

## shadcn Check (Required Before UI Code)

The harness that ran this order exposes no subagent tool, so the check ran in this session (WebFetch of ui.shadcn.com/docs/components, /toggle-group and /radio-group, plus the vendored sources in `ui/client/src/components/ui/`). shadcn lists no listbox component. The candidates:

- **Radio Group** (`radio-group.tsx`): renders `<button role="radio">` items with a Radix indicator (`Circle` glyph) and `grid gap-2` root; Radix radio groups move the selection with the arrow keys (selection follows focus), which the order rules out.
- **Toggle Group** (`toggle-group.tsx`): renders Radix `<button>` items with the toggle variant classes; single mode lets a press deselect the item, and the markup is buttons, not the roster's `<li>` rows.
- **Command** (`command.tsx`, cmdk): keeps DOM focus on a search input and moves an `aria-activedescendant` highlight; it renders its own wrapper, input and item markup and classes.

Each one changes the roster's rendered markup or styles (the decision rule forbids that), so the roster gains listbox semantics in place (item A).

## Focus Indicator Finding

The rail buttons and the map place buttons have no explicit `:focus-visible` rule: Chromium paints its UA ring (`outline: auto 1px rgb(0, 95, 204)` in the readback below). The explicit keyboard ring the shell does define is shadcn's `--ring` token (`Button`: `focus-visible:ring-1 focus-visible:ring-ring`; the dialog's Close button: `focus:ring-2 focus:ring-ring`, which reads back as `rgb(184, 61, 122) 0 0 0 4px` under Veil). The roster rows reuse that token: `.charspane-list li:focus-visible { outline: none; box-shadow: 0 0 0 1px hsl(var(--ring)); }`. No new color; under Veil it resolves to the anchor `#b83d7a` (`rgb(184, 61, 122)`). The ring draws outside the row border, so the selected row's brass border stays readable under it. The row's `.on` class is unchanged.

## Red Run (Tests at `9ec29087`, Product at `7eb9a10c`)

`nice -n 15 npm --prefix ui test -- CharactersPane MapPane` (full output: `red-ui.txt`):

```
   × CharactersPane roster keyboard access > gives the roster one tab stop, on the selected row, and Shift+Tab leaves it
   × CharactersPane roster keyboard access > starts the tab stop on the first row when nothing has been picked
   × CharactersPane roster keyboard access > moves focus with the arrows, Home and End without changing the selection
   × CharactersPane roster keyboard access > selects the focused row with Enter and with Space
   × CharactersPane roster keyboard access > exposes each row as an option named for its character in a named listbox
   × CharactersPane roster keyboard access > still selects on a mouse click and moves the tab stop to the clicked row
   × MapPane place dialog focus return > returns focus to the place button after Escape
   × MapPane place dialog focus return > returns focus to the place button after the Close button
   × MapPane place dialog focus return > focuses the map pane root when the opener left the document
 Test Files  2 failed (2)
      Tests  9 failed | 17 passed (26)
```

Failure reasons: Tab from the preceding button went past the roster (`expected <button …> to be <li class="on" …>`); no `listbox` named Characters; Enter left the dossier on Alex; after Escape or Close, `document.activeElement` was `<body>` (the QA defect, reproduced in jsdom).

## Green Runs (at `16b4909c`)

`nice -n 15 npm --prefix ui test -- CharactersPane MapPane shell-accessibility NexusLayout` (`green-focused.txt`):

```
 ✓ src/shell-accessibility.test.ts (11 tests) 68ms
 ✓ src/components/nexus/NexusLayout.test.tsx (5 tests) 146ms
 ✓ src/components/nexus/CharactersPane.test.tsx (18 tests) 184ms
 ✓ src/components/nexus/NexusLayout.announcer.test.tsx (3 tests) 268ms
 ✓ src/components/nexus/MapPane.test.tsx (8 tests) 355ms

 Test Files  5 passed (5)
      Tests  45 passed (45)
```

`nice -n 15 npm --prefix ui test` (`ui-full.txt`): every file passes except `src/state-shades.test.ts`, which fails to load with `Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces`. That failure is expected on this base (coordinator amendment 4; this branch also edits `nexus-layout.css`, inside the input closure). Resolve was not run.

```
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
 Test Files  1 failed | 40 passed (41)
      Tests  641 passed (641)
```

`nice -n 15 npm --prefix ui run check` (`ui-check.txt`): `tsc` and `tsc -p .design-sync/tsconfig.previews.json` exit 0 with no diagnostics.

`nice -n 15 npm --prefix ui run build` (`ui-build.txt`): exit 0.

```
../dist/public/assets/index-DntCEJHP.css                          202.76 kB │ gzip:  37.21 kB
../dist/public/assets/index-cdTliB28.js                         1,775.74 kB │ gzip: 529.87 kB
✓ built in 2.76s
```

Repository gates (no Python changed): `PYTHONPATH=$PWD $PY -m pytest -q tests/test_doc_front_matter.py` printed `66 passed, 5 warnings in 8.21s` with `secret-store guard: active; nexus-api: denied; disposable keychain: denied`. No canonical document declares a changed path in its `sources:`. `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref claude/wave-b-integration` printed `OK: exception disposition coverage and shrink-only baseline verified.`

## Rendered-Browser Verification (Item 9, at `16b4909c`)

`KBD_SCRATCH=<scratch>/777-KBD/browser nice -n 15 node docs/qa/777-keyboard-roster-and-map/keyboard-proof.mjs`. The script is modeled on `docs/qa/777-shell-ui-bundle/mobile-proof.mjs` and `ui/scripts/state-surfaces/tooltip-focus-trace.mjs`. Headless Chromium runs at 1200x900, dark, reduced motion, on a `file://` origin. Every `http(s)` request is aborted and WebSockets are routed to nothing. The page uses the production CSS that `npm --prefix ui run build` emitted (`index-DntCEJHP.css`) and the real `NexusLayout` shell. Data comes from `keyboard-fixture.tsx`, a copy of `ui/scripts/state-surfaces/fixture.tsx` with a seven-member cast and the QA run's zone and place names; `fixture.tsx` is unchanged. The bundled fixture and its HTML are written to scratch, not here.

```
roster (first load + reload) and map focus return passed: 33 readbacks, 0 page errors, 0 HTTP requests
```

Each step's `document.activeElement` readback (tag, role, accessible name, `aria-selected`, `tabindex`, `:focus-visible`, the dossier heading, dialog presence, focus styling) is in `keyboard-readback.json` and `keyboard-readback-table.txt`. The roster steps:

- Characters rail button, then Tab: Settings.
- Tab: option "Ivo Sato" (selected, tabindex 0, focus-visible, ring `rgb(184, 61, 122) 0px 0px 0px 1px`).
- Shift+Tab: Settings. Tab: Ivo Sato.
- ArrowDown: "Pela" gets focus; the dossier still shows Ivo Sato and Pela's `aria-selected` stays false.
- Enter: the dossier shows Pela.
- ArrowDown, then Space: the dossier shows Mara Quill, and the list's scrollTop does not change.
- End: Juno Halloran. Home: Ivo Sato.
- Tab: Upload portrait. Shift+Tab: Ivo Sato, which holds the roving stop.
- A mouse click on Rhea Lind selects her.

The whole sequence ran on first load and again after `page.reload()`, with identical readbacks.

The map steps: Enter on the zone header expands Accord Station Garden Rings; focus goes to Ring Three Public Kitchen. Each pass presses Enter, and the Close button gets focus in the open dialog. The passes then close the dialog three ways: Escape, Enter on Close, and a mouse click on Close. After every close, `document.activeElement` is `BUTTON` "Ring Three Public Kitchen" with `:focus-visible` true; it is never `BODY`.

Screenshots (1200x900): `roster-keyboard-focus.png`, after ArrowDown, shows Ivo Sato selected and Pela with the keyboard ring. `map-focus-return.png`, after Escape, shows focus back on the place button with its ring. The roster's accessibility snapshot is in `roster-accessibility.txt` (`listbox "Characters"`, seven `option`s named for their characters, `[selected]` on Ivo Sato).

## Probe Outside the Ordered Tests

A throwaway vitest probe (not committed) covered a refetch that drops the open place. That makes `MapPlaceDialog` return `null`, so the dialog unmounts while open. Radix still fires `onCloseAutoFocus`, and focus landed on the `map-pane` root (`SCRATCH-ACTIVE DIV map-pane`), not on the body.

## Machine Load

`uptime` before the work read `load averages: 8.97 5.47 4.13` (below 24). Every test, build and Chromium command ran under `nice -n 15`, one at a time. No PostgreSQL test ran (none is named by this order and no Python changed).
