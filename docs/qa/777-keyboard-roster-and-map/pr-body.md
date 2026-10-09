## Goal

Refs #777. This PR fixes the two keyboard defects in the nightly-QA comment of 2026-10-09 04:50 UTC:

1. Tab skips every row of the **Characters** roster, so a keyboard-only player cannot select a character.
2. Closing the **Map** place dialog (Escape or **Close**) drops focus on `document.body`.

## What Is Wrong Today

- `ui/client/src/components/nexus/CharactersPane.tsx:133-152` (on `f073b371`): each roster row is an `<li onClick>` with no `tabIndex`, role or key handler. The accessibility tree shows the rows as generic containers, and from the **Characters** rail button, Tab goes Settings → Upload portrait.
- `ui/client/src/components/nexus/MapPane.tsx:499-500` (`selectPlace`) opens a controlled dialog. `MapPlaceDialog.tsx:89-94` renders a Radix `Dialog` with no `DialogTrigger` and no `onCloseAutoFocus`. Radix's modal content calls `preventDefault()` on close and focuses `triggerRef.current`, which is null, so focus falls to `BODY`.

## What Changed

**Roster (`CharactersPane.tsx`, `nexus-layout.css`).** The `<ul>` becomes `role="listbox"` with `aria-label="Characters"`. Each `<li>` becomes `role="option"` with:

- a stable `useId`-based `id`;
- `aria-selected`;
- `aria-label` set to the character's name;
- a roving `tabIndex`: one row is `0`, starting at the selected row (the first row when nothing is picked), and every other row is `-1`.

ArrowUp/ArrowDown (clamped) and Home/End move focus without changing the selection. Enter and Space select the focused row; Space calls `preventDefault` so the pane does not scroll. A click still selects and moves the roving stop. The `data-testid`, glyph/portrait markup, `char-name` and the `.on` class are unchanged, and no visible label is added.

A `:focus-visible` rule reuses the shell's shadcn focus-ring token (`box-shadow: 0 0 0 1px hsl(var(--ring))`, the `ring-1 ring-ring` that `Button` uses). Under Veil it resolves to the anchor `#b83d7a`; no new color is added.

**Map (`MapPane.tsx`, `MapPlaceDialog.tsx`).** `selectPlace` takes a third `opener` argument:

- The place row buttons pass `event.currentTarget`.
- Canvas pins (SVG groups, not focusable controls) pass `null`.

The pane root gets `tabIndex={-1}` and `mapRootRef`. `MapPlaceDialog` accepts `onCloseAutoFocus` and passes it to `DialogContent`. MapPane's handler calls `preventDefault()`, then focuses the opener if it is still connected and the pane root otherwise, and clears the ref. Escape and **Close** still close the dialog, and the dialog still focuses **Close** on open.

**shadcn check.** shadcn has no listbox. Radio Group moves the selection with the arrows, Toggle Group renders buttons with toggle styles, and Command keeps focus in a search input with its own markup. Each would change the roster's rendered markup or styles, so the listbox semantics are added in place. Details are in `docs/qa/777-keyboard-roster-and-map/verification.md`.

## Tests

`CharactersPane.test.tsx` gains six user-event tests:

- Tab lands on exactly one row, the selected one, and Shift+Tab leaves the list.
- The first row holds the stop when nothing is picked.
- Arrows, Home and End move focus without selecting.
- Enter and Space select, and Space's default is prevented.
- Rows are options named for their characters inside a listbox named Characters.
- A mouse click still selects.

`MapPane.test.tsx` gains three:

- Escape returns focus to the place button.
- **Close**, then a second keyboard pass, returns focus to the place button.
- When a refetch moves the open place into a collapsed zone (its row leaves the document), Escape focuses the pane root, not `BODY`.

Red run before the product change (tests at `9ec29087`, product at `7eb9a10c`), `nice -n 15 npm --prefix ui test -- CharactersPane MapPane`:

```
 Test Files  2 failed (2)
      Tests  9 failed | 17 passed (26)
```

(The failures: Tab went past the roster; no `listbox` named Characters; `document.activeElement` was `<body>` after Escape or Close.)

Green at `16b4909c`, `nice -n 15 npm --prefix ui test -- CharactersPane MapPane shell-accessibility NexusLayout`:

```
 ✓ src/shell-accessibility.test.ts (11 tests) 68ms
 ✓ src/components/nexus/NexusLayout.test.tsx (5 tests) 146ms
 ✓ src/components/nexus/CharactersPane.test.tsx (18 tests) 184ms
 ✓ src/components/nexus/NexusLayout.announcer.test.tsx (3 tests) 268ms
 ✓ src/components/nexus/MapPane.test.tsx (8 tests) 355ms

 Test Files  5 passed (5)
      Tests  45 passed (45)
```

`nice -n 15 npm --prefix ui test` (full):

```
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
 Test Files  1 failed | 40 passed (41)
      Tests  641 passed (641)
```

The one failing file is `state-shades.test.ts`, with `Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces`. It is expected on this base (wave-B integration; this branch also edits `nexus-layout.css`, inside the input closure). The coordinator regenerates once on the final UI union.

`nice -n 15 npm --prefix ui run check`: exit 0, no diagnostics (`tsc`, then `tsc -p .design-sync/tsconfig.previews.json`).

`nice -n 15 npm --prefix ui run build`:

```
../dist/public/assets/index-DntCEJHP.css                          202.76 kB │ gzip:  37.21 kB
../dist/public/assets/index-cdTliB28.js                         1,775.74 kB │ gzip: 529.87 kB
✓ built in 2.76s
```

`PYTHONPATH=$PWD $PY -m pytest -q tests/test_doc_front_matter.py`: `66 passed, 5 warnings in 8.21s`, and the guard line reads `secret-store guard: active; nexus-api: denied; disposable keychain: denied`. `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref claude/wave-b-integration`: `OK: exception disposition coverage and shrink-only baseline verified.`

## Rendered-Browser Verification

`KBD_SCRATCH=<scratch> nice -n 15 node docs/qa/777-keyboard-roster-and-map/keyboard-proof.mjs` uses headless Chromium at 1200x900 on `file://`, with HTTP aborted, the production CSS from the build above, and the real `NexusLayout` with seeded query data. The fixture is a copy of the state-surface fixture with a seven-member cast; `fixture.tsx` itself is unchanged.

```
roster (first load + reload) and map focus return passed: 33 readbacks, 0 page errors, 0 HTTP requests
```

- **Roster** (first load, then again after a full reload): Characters → Tab → Settings → Tab → option "Ivo Sato" (selected, focus-visible, ring `rgb(184, 61, 122) 0px 0px 0px 1px`) → Shift+Tab → Settings. ArrowDown focuses "Pela" while the dossier stays on Ivo Sato; Enter selects Pela. ArrowDown then Space selects Mara Quill without scrolling the list. End/Home reach the last and first rows; Tab → Upload portrait; a mouse click still selects.
- **Map**: Enter on Ring Three Public Kitchen opens the dialog with Close focused. Escape, Enter on Close, and a mouse click on Close each return focus to the place button (`BUTTON`, "Ring Three Public Kitchen", focus-visible); it is never `BODY`.

Readbacks and screenshots: `docs/qa/777-keyboard-roster-and-map/keyboard-readback.json`, `keyboard-readback-table.txt`, `roster-accessibility.txt`, `roster-keyboard-focus.png`, `map-focus-return.png`.

## Deferred and Notes for Review

- The rail buttons and the map place buttons still rely on Chromium's UA focus ring (blue `auto` outline); only shadcn components use the `--ring` token. This PR aligns the roster with the token and leaves the rail and map rows alone. Unifying the shell's keyboard ring is a separate decision.
- A canvas pin opens the dialog with no focusable opener, so closing it focuses the map pane root. That root (`tabIndex={-1}`) shows Chromium's UA ring when focused after keyboard use.
- `state-shades.test.ts` needs the coordinator's single `resolve-state-surfaces` run on the final UI union; this branch did not run it.
- No Python, migration, prompt, `nexus.toml` or database change, and no PostgreSQL run (the order names none).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01FsLmRyABWHoUEXsidSRfMC
