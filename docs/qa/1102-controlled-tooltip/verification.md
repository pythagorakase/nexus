# 1102-S1 Verification: The Keyboard-Held Exceeds-RAM Tooltip

Order: `temp/orders_2026_10_26/1102-S1.md` with the coordinator amendment of
2026-10-26 (test (d) moves the pointer the Chromium way). Branch
`claude/1102-tooltip-focus`, cut from `c7ae2988`, merged with `origin/main` at
`e058005f`. Scratch output lives under the session scratchpad in `1102-S1-r2/`.

## Cited Lines (at `c7ae2988`)

- `ui/client/src/components/nexus/LocalModelRows.tsx:476-483`: the exceeds
  branch wrapped the quant row in an uncontrolled `<Tooltip>` with the row as
  `<TooltipTrigger asChild>`. The row (`:356-388`, `role="radio"`,
  `tabIndex={0}`) contains the trash button (`:412-448`).
- `LocalModelRows.tsx:370-376`: the row's `onBlur` calls `preventDefault` when
  `relatedTarget` stays inside the row, which skips Radix's blur close
  (`ui/node_modules/@radix-ui/react-tooltip/dist/index.mjs:205`). It covers a
  focus move inside the row only.
- Radix Tooltip 1.2.8 (`ui/node_modules/@radix-ui/react-tooltip/package.json:3`):
  the content's capture-phase `window` scroll listener calls `onClose` when the
  scroll target contains the trigger (`dist/index.mjs:311-319`); it closes on
  the `TOOLTIP_OPEN` broadcast (`:307-310`); the trigger opens on focus unless
  a pointer is down (`:202-204`) and closes on pointerdown when open
  (`:195-198`).
- Natural Tab scrolls `.set-scroller` from 523px to 527px and the row closed:
  `docs/qa/777-shell-ui-bundle/verification.md:199-220`, `trace-initial.txt`
  (0/50 row open). This branch's red plant reproduces the same 523 -> 527
  scroll and 0/50.
- `ui/scripts/state-surfaces/tooltip-focus-trace.mjs:86-117`, `:119`, `:123`:
  the stationary-viewport precondition, which made the trace read 50/50/50
  with or without the fix.
- `ui/scripts/state-surfaces/README.md:130-141`: natural Tab auto-scroll still
  dismissed the tooltip.
- Receipt at `c7ae2988`: 1,978 `tooltip already dismissed` and 1,394
  `keyboard Escape dismisses tooltip` strings in
  `ui/client/src/state-surfaces.resolved.json` (recounted on this branch:
  `1978 / 1394`; the receipt is not regenerated here, Decision 1102-D7).

## Commits

- `2fcd01d6` tests (a)-(e); `6a5716b4` product (`ExceedsRamTooltip`);
  `f418788c` test (d) per the amendment; `63eb4353` trace and README;
  merge of `origin/main` (`e058005f`); `25c666de` re-stamp of decision 0066
  to the merge base; `1d43db54` rewrap of the README passage (whitespace
  only, `git diff --word-diff` shows no word change).

## Red: Tests on the `c7ae2988` Product File

Tests as committed at `f418788c` (amended (d)); `LocalModelRows.tsx` replaced
by `git show c7ae2988:...`, then restored (SHA-256 before and after:
`9b2b24bfe9e3889c3c7c930bf6ddf856cf060b190288da2053c4455b88adb291`).

```
$ nice -n 15 npm --prefix ui test -- LocalModelRows
   × exceeds-RAM tooltip > stays open through an ancestor scroll while keyboard focus is in the row 54ms
   × exceeds-RAM tooltip > Escape dismisses it until focus leaves the row 47ms
   ✓ exceeds-RAM tooltip > a pointer click on the trash does not hold it open 723ms
   × exceeds-RAM tooltip > the hold re-engages on keyboard focus after an earlier pointer click 55ms
 Test Files  1 failed (1)
      Tests  3 failed | 22 passed (25)
```

(a) fails at `LocalModelRows.test.tsx:470` (no tooltip after the scrolls);
(b) fails at `:491`, the Shift+Tab back onto the row, where Radix reopens on
focus; (e) fails at `:556`. (c) and (d) pass, as ordered.

## Green: After the Product Change (`f418788c`)

```
$ nice -n 15 npm --prefix ui test -- LocalModelRows
 ✓ src/components/nexus/LocalModelRows.test.tsx (25 tests) 1049ms
   ✓ exceeds-RAM tooltip > a pointer click on the trash does not hold it open 724ms
 Test Files  1 passed (1)
      Tests  25 passed (25)
```

## Plants

Each plant was applied to `LocalModelRows.tsx`, run, and restored from a copy
of the fixed file. Every before and after hash is
`9b2b24bfe9e3889c3c7c930bf6ddf856cf060b190288da2053c4455b88adb291`.

- P1, `pointerDownRef.current = false` removed from `onBlur`:
  ```
     × exceeds-RAM tooltip > the hold re-engages on keyboard focus after an earlier pointer click 86ms
        Tests  1 failed | 24 passed (25)
  ```
- P2, `if (!pointerDownRef.current)` dropped in `onFocus`:
  ```
     × exceeds-RAM tooltip > a pointer click on the trash does not hold it open 734ms
        Tests  1 failed | 24 passed (25)
  ```
- P3, `setKeyboardFocusWithin(false)` removed from `onBlur`:
  ```
     × exceeds-RAM tooltip > stays open as focus moves from the row to its trash button 50ms
     × exceeds-RAM tooltip > closes when keyboard focus leaves the row after a held scroll 32ms
        Tests  2 failed | 23 passed (25)
  ```

## Focus Trace

Green, on `63eb4353`'s trace with the fixed product file (1200x900; no
height change was needed):

```
$ STATE_SURFACES_SCRATCH=<scratchpad>/1102-S1-r2/trace-green nice -n 15 node ui/scripts/state-surfaces/tooltip-focus-trace.mjs
Tooltip focus trace: 50/50 row open; 50/50 trash open; 50/50 outside closed
EXIT 0
```

Reading (`tooltip-focus-trace-green.json`, copied beside this file): counts
`{"rowOpen":50,"trashOpen":50,"outsideClosed":50}`, 50 runs, 0 page errors, 0
requests. Every run: 23 Tabs, `scrollBeforeRowTab` 523, row 527
(`instant-open`), trash 527 (`instant-open`), outside 1123 (`closed`).

Red plant: `LocalModelRows.tsx` replaced by
`git show origin/main:ui/client/src/components/nexus/LocalModelRows.tsx`,
hash before and after restore
`9b2b24bfe9e3889c3c7c930bf6ddf856cf060b190288da2053c4455b88adb291`.

```
Tooltip focus trace: 0/50 row open; 50/50 trash open; 50/50 outside closed
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
+ actual - expected

  {
    outsideClosed: 50,
+   rowOpen: 0,
-   rowOpen: 50,
    trashOpen: 50
  }

    at file:///Users/pythagor/nexus/.claude/worktrees/1102-S1/ui/scripts/state-surfaces/tooltip-focus-trace.mjs:119:8 {
EXIT 1
```

Reading (`tooltip-focus-trace-red.json`): 50 runs, each past the scroll
assertion (523 -> 527), row `closed` with no tooltip in all 50, trash
`instant-open`, outside `closed`; 0 page errors, 0 requests. The failure is
the final `assert.deepEqual(counts, ...)` only.

## Oracle Probe (Scratch Only, Not a Regeneration)

```
$ STATE_SURFACES_SCRATCH=<scratchpad>/1102-S1-r2/probe STATE_SURFACES_CONDITION=default STATE_SURFACES_THEME=Veil STATE_SURFACES_GROUP=delete STATE_SURFACES_PROBE=1 STATE_SURFACES_OUTPUT=<scratchpad>/1102-S1-r2/probe/delete.json nice -n 15 npm --prefix ui run resolve-state-surfaces
Resolved painted state surfaces: renders=254; wall=130.538s; Chromium 153.0.8010.12; Playwright 1.63.0
Emulation: 1200×900 default; deviceScaleFactor=4; dark; reduced motion; 1 media conditions; file://; network aborted; requests=0; errors=0
Wrote .../1102-S1-r2/probe/delete.json; module graph=2099 inputs; SHA-256 cf6b6dd765295a85c8ed8d86723bf582b1fa7827587b7173bc90af27b3d824c8
EXIT 0
```

In `delete.json`: `tooltip already dismissed` 0, `keyboard Escape dismisses
tooltip` 10. No `Measurement failure` line in the log.

## Full UI Suite, Check, Build (after the merge, `25c666de`)

```
$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 43 passed (44)
      Tests  672 passed (672)
```

The `state-shades.test.ts` failure is expected under Decision 1102-D7: the
receipt is regenerated by the coordinator on the wave's UI union.

```
$ nice -n 15 npm --prefix ui run check
> tsc && npm run check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
CHECK EXIT 0
$ nice -n 15 npm --prefix ui run build
PWA v1.0.3
mode      generateSW
precache  22 entries (2325.71 KiB)
BUILD EXIT 0
```

No diagnostics from `check`, so there are no new or pre-existing ones.

## Python Gates

The offline suites ran on `25c666de`, every run below with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` and `NEXUS_RUN_POSTGRES`
unset. No Python file changed:

```
$ git diff --name-only origin/main...HEAD -- '*.py'
(no output)
$ PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
/Users/pythagor/nexus/.claude/worktrees/1102-S1/nexus/__init__.py
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3285 passed, 702 skipped, 8 warnings in 649.88s (0:10:49)
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1547 skipped, 7 warnings in 45.85s
```

Rerun on `1d43db54` (the README rewrap) with full logs kept under the
scratchpad's `1102-S1-r2/` (`reachability.log`, `front-matter.log`,
`dispositions.log`):

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
60 passed, 5 warnings in 8.66s
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
89 passed, 5 warnings in 6.78s
$ PYTHONPATH=$PWD $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
EXIT 0
```

The skips are the PostgreSQL-backed tests (`NEXUS_RUN_POSTGRES` unset). No
PostgreSQL proof set applies: there is no Python, SQL, migration or
`nexus.toml` change. Black, flake8 and mypy have no file to check.

Decision 0066 (`docs/decisions/0066-the-keyboard-held-tooltip.md`) declares
`LocalModelRows.tsx` as a source. Its body quotes Decisions 1102-D1 to D7,
which match the change as built; `verified_commit` moved from `c7ae2988` to
the merge base `e058005f`.
