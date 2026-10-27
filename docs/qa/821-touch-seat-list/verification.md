# 821-S2 Verification: Seat List Reachable on Touch Devices

Refs #821. Order: `temp/orders_2026_10_26/821-S2.md` (Decisions 821-Q1, 821-D2, 821-D3 on the issue). Branch `claude/821-touch-seat-list`.

Commits, in order:

- `99f7f6b9` tests only (red); branch then at `e058005f` plus this commit.
- `90727f93` product change (green).
- `90ccacfc` merge of `origin/main` at `d295eef0`.
- `e719f79d` re-stamps `0054-responsive-shell.md` and `0067-seat-lists-in-a-popover.md` to the merge base `d295eef0928706cda3a9f7c5a8b4dc103929e1ed`.
- `240bbe72` the phone-width fixture and proof script. The final UI tails, the browser proof and the Python suites below ran on `e719f79d`/`240bbe72` (`240bbe72` adds only the two files under this directory).
- `3ffa0f32` review fix: the popover test also asserts that a hover opens nothing. Its tail is under Green; it changes only `SettingsPane.test.tsx`, so the other tails stand.
- `de0ac056` records the hover check and the state-shades coverage gap (this file only).
- The second review fix (the commit that adds this line): `seat-proof.mjs` reads the dialog's accessible name from Playwright's accessibility engine. The phone-width proof was rerun on `de0ac056` plus that one-file change; see Phone-Width Check.

## The shadcn Check

The order says to dispatch a subagent for this check. The harness running this order has no subagent-spawn tool, so the implementer made the check directly (WebFetch, 2026-10-26). This is a deviation from the order step as written; the review fixer's harness has no subagent-spawn tool either, so the coordinator either acknowledges it at landing or reruns the check through a subagent and appends the result here.

- ui.shadcn.com/docs/components/popover: "Displays rich content in a portal, triggered by a button." Parts `Popover`, `PopoverTrigger`, `PopoverContent`; installed with `shadcn@latest add popover`. The page offers Radix UI, Base UI and React Aria variants; the vendored copy is the Radix one.
- radix-ui.com Popover: the trigger "toggles the popover"; Space and Enter open and close it; Esc "Closes the popover and moves focus to `Popover.Trigger`."
- ui.shadcn.com Tooltip: "A popup that displays information related to an element when the element receives keyboard focus or the mouse hovers over it." Radix source (`ui/node_modules/@radix-ui/react-tooltip/dist/index.mjs:185`): `onPointerMove` returns early `if (event.pointerType === "touch")`, so a tap never opens it.
- ui.shadcn.com Hover Card: "For sighted users to preview content available behind a link." Radix Hover Card: "intended for sighted users only, the content will be inaccessible to keyboard users"; Radix source (`ui/node_modules/@radix-ui/react-hover-card/dist/index.mjs:231`) drops touch pointer events (`event.pointerType === "touch" ? void 0 : eventHandler()`).

Finding: Popover is the ready-made component that opens on a tap, a click, Enter or Space. It is already vendored at `ui/client/src/components/ui/popover.tsx` (Radix `@radix-ui/react-popover`, `PopoverContent` in a portal) and is used unchanged.

## Cited Lines (Main at c7ae2988; Re-Located Unchanged at d295eef0)

Every cited line in `SettingsPane.tsx`, `SettingsPane.test.tsx` and `nexus-layout.css` (and `secrets_endpoints.py:228`) holds the same text on `origin/main` at `d295eef0`, the main this branch merged: no commit in `c7ae2988..d295eef0` touches those files (`git diff --quiet c7ae2988 d295eef0 -- <file>` exits 0 for each), and the lines were also confirmed on the branch before editing.

- `ui/client/src/components/nexus/SettingsPane.tsx:570`: `<span className="key-provider-name" title={requiredByTitle(row)}>`; the seat list lived only in a native `title`.
- `SettingsPane.tsx:442-444`: comment "The provider name's hover title lists the needing seats"; `:448-456` `SEAT_LABELS`; `:458-467` `requiredByTitle` (unchanged on the branch).
- `nexus/api/secrets_endpoints.py:228`: `required=bool(requirements)`.
- `SettingsPane.test.tsx:245`, `:252`, `:257`, `:682-683`: the title assertions replaced here.
- `nexus-layout.css:2147-2158` `.lm-tip.lm-tip` (portaled tooltip tokens), `:2182-2189` `.key-provider-name`, `:929-932` the `--ring` focus precedent.
- `ui/client/src/state-shades.test.ts:695` pins ``className={`key-status ${status}`}``; that line is untouched (now `SettingsPane.tsx:596`). The pin did not run on this branch: see the note on the stale receipt under Green.
- `ui/scripts/state-surfaces/fixture.tsx:62-64` seeds every key row with `required_by: []`, so the state-surface fixture's rows keep the plain `<span>`.

## What Changed

- `SettingsPane.tsx:565` `const seats = requiredByTitle(row);`; `:573-595` a needed row's name is a `PopoverTrigger` (`key-provider-name key-seats-trigger`, id and test id `key-seats-trigger-<provider>`) with a `PopoverContent` (`key-seats`, bottom/start, `collisionPadding={16}`, `aria-labelledby` the trigger) holding only the joined seat names; other rows keep `<span className="key-provider-name">` with no `title`. Import at `:12`. Comment at `:443-447`.
- `nexus-layout.css:2148-2149` `.lm-tip.lm-tip,\n.key-seats.key-seats {`; `:2160` width override; `:2192-2194` the trigger reset and its `--ring` focus outline. No new token, no hue change.

## Red (Tests Only, Before the Product Change)

`nice -n 15 npm --prefix ui test -- SettingsPane shell-accessibility` with the test edits on `e058005f` (committed unchanged as `99f7f6b9`):

```
 FAIL  src/components/nexus/SettingsPane.test.tsx > SettingsPane API keys > sorts needed keys first, warns while one is missing, and dims the rest
TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "anthropic"
 FAIL  src/components/nexus/SettingsPane.test.tsx > SettingsPane API keys > lists the needing seats in a popover on a tap, a click or Enter, only for needed keys
TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "anthropic"
 FAIL  src/components/nexus/SettingsPane.test.tsx > SettingsPane model IDs > re-derives the slot's required keys when the Skald pin changes
TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "openrouter"

 Test Files  1 failed | 1 passed (2)
      Tests  3 failed | 30 passed (33)
```

## Green

Same command on `90727f93`: `Test Files  2 passed (2)`, `Tests  33 passed (33)`. Again on `240bbe72`:

```
 ✓ src/shell-accessibility.test.ts (11 tests) 53ms
 ✓ src/components/nexus/SettingsPane.test.tsx (22 tests) 800ms

 Test Files  2 passed (2)
      Tests  33 passed (33)
```

Again on `3ffa0f32`, with the hover assertion (before the touch press the test hovers the `anthropic` trigger, expects no `dialog` and `aria-expanded="false"`, then unhovers):

```
 ✓ src/shell-accessibility.test.ts (11 tests) 52ms
 ✓ src/components/nexus/SettingsPane.test.tsx (22 tests) 793ms

 Test Files  2 passed (2)
      Tests  33 passed (33)
```

Mutation check for that assertion: with `onPointerEnter={(e) => e.currentTarget.click()}` added to the trigger in a scratch edit (reverted with `git checkout`, never committed), `npm --prefix ui test -- SettingsPane` fails the popover test with `AssertionError: expected <div data-side="bottom" …(9)></div> to be null` (`Tests  2 failed | 20 passed (22)`; the Skald-pin test also fails because its click toggles the hover-opened popover closed).

Full `nice -n 15 npm --prefix ui test` on `240bbe72`:

```
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).

 Test Files  1 failed | 43 passed (44)
      Tests  673 passed (673)
```

Expected by Decision 821-D3: the receipt is not regenerated on this branch. The same failure also occurs on `origin/main` at `d295eef0` without this change: with `SettingsPane.tsx` and `nexus-layout.css` checked out from `origin/main`, `npm --prefix ui test -- state-shades` reports the same "Stale browser-resolved state surfaces" error (`d295eef0` changed `LocalModelRows.tsx`, which is in the input closure). The files were then restored from `HEAD`.

This is not a receipt-only failure. The stale-receipt check throws at module load (`state-shades.test.ts:183`), so the whole file aborts before any `it` runs (`Tests  673 passed` counts no state-shades test). On this branch none of its tests ran, including the `key-status` pin (`:695`) and the source checks over the changed `nexus-layout.css`: `state_surfaces_read_only_state_tokens` (`:620`) and `global_tokens_are_unchanged_from_baseline_including_compound_and_alpha_values` (`:592`). No executed check proves that the new `.key-seats` and `.key-seats-trigger` color and outline declarations stay out of the state-surface closure. By reading the code they should pass: the new rules declare no custom properties and none of their selectors names a surface class. Landing note: after `resolve-state-surfaces` runs on the UI union, the coordinator confirms that these three tests pass.

`nice -n 15 npm --prefix ui run check`: exit 0 (`tsc && npm run check:design-sync`, no output). `nice -n 15 npm --prefix ui run build`: exit 0, `✓ built in 2.62s` (the pre-existing chunk-size warning only).

## Phone-Width Check

`SEAT_SCRATCH=<scratch>/821-S2/seat-build nice -n 15 node docs/qa/821-touch-seat-list/seat-proof.mjs` first on `240bbe72`, after the build. Rerun after the second review fix on `de0ac056` plus the `seat-proof.mjs` change (a fresh `nice -n 15 npm --prefix ui run build`, same `index-CBz8DeaZ.css`), with the same output; `seat-popover-390.png` came out byte-identical:

```
390x844 touch: seat popover opened on a tap (Skald · Summaries), stayed inside the viewport, closed on an outside tap; optional row has no trigger; 0 page errors, 0 HTTP requests
```

`seat-fixture.tsx` is `docs/qa/777-keyboard-roster-and-map/keyboard-fixture.tsx` with the ordered `keyRows` seeding. One more change was needed: the 777 copy predates #1147 (client plane awareness), so without a `/health` answer the shell stayed at "[ RECEIVING ]" and rendered no Settings sections. The copy now carries the three plane lines #1147 added to `ui/scripts/state-surfaces/fixture.tsx` (the operator `/health` answer and its `['/health']` seed, the full `['/api/preferences']` seed) and drops the retired `HEAD /api/settings` answer. Bundle and HTML stay in the scratch directory.

Readback (`seat-readback.json`, production CSS `index-CBz8DeaZ.css`):

| Reading | Value |
|---|---|
| Viewport | 390x844, `(max-width: 760px) and (pointer: coarse)` matches |
| Dialogs before the tap | 0 |
| `required-missing` trigger before the tap | x 300, width 90, right 390 (inside 0..390); `BUTTON`, `aria-expanded="false"`, no `title` |
| `#set-keys` text | no seat name |
| Dialog text after `locator.tap()` | `Skald · Summaries` |
| Dialog accessible name (computed by Playwright's accessibility engine) | `getByRole('dialog', { name: 'required-missing', exact: true })` count 1; `ariaSnapshot()` `- dialog "required-missing": Skald · Summaries`; not inside `#set-keys` |
| Dialog box | x 239, right 374.05 (inside 0..390), width 135.05, max-width 358px |
| `document.documentElement.scrollWidth` | 390 before and after |
| Trigger after the tap | `aria-expanded="true"` |
| Outside tap at (195, 407) | a non-interactive `UL`; dialog detached; trigger `aria-expanded="false"` |
| `optional-absent` row | 0 triggers, 0 buttons named `optional-absent`, name is a `SPAN` with no `title` |
| HTTP requests / page errors | 0 / 0 |

The in-page fixture transport recorded only `GET`s answered in the page (`/api/secrets/status?slot=4`, `/api/slot/4/state`, `/api/narrative/active?slot=4`, `/health`); none left the browser.

Screenshot: `seat-popover-390.png`. The settings card column is clipped at 390px, as on `main` (777 evidence `docs/qa/777-shell-ui-bundle/narrow-settings.png`); the order keeps that layout out of scope, and the popover itself sits inside the viewport.

## Python

No Python file changed, so Black, flake8 and `mypy --explicit-package-bases` have no changed files to check.

`NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_secret_requirements.py tests/test_api/test_secrets_endpoints.py`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset (load 11.02 before the run):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 3 targets: postgres, qa640_offline_gate_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
24 passed, 2 skipped, 7 warnings in 7.01s
```

The two skips are `test_secrets_endpoints.py:384` and `:395`: "Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests." (no paid call is ordered).

`nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3285 passed, 702 skipped, 8 warnings in 639.61s (0:10:39)
```

`nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1547 skipped, 7 warnings in 46.45s
```

`$PY -m pytest -q tests/test_doc_front_matter.py tests/test_reachability.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
149 passed, 5 warnings in 15.36s
```

`$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`: `OK: exception disposition coverage and shrink-only baseline verified.`

## Document Freshness

`git diff --name-only origin/main...HEAD` against the `sources:` of every `status: canonical` file: `nexus-layout.css` is a source of `docs/decisions/0054-responsive-shell.md`, and `SettingsPane.tsx` is a source of `docs/decisions/0067-seat-lists-in-a-popover.md`. No other match. 0054: the change adds the API keys trigger and popover styles and a shared tooltip selector; the responsive-shell ruling is unchanged. 0067: the branch implements its ruling. Both `verified_commit` values are now `d295eef0928706cda3a9f7c5a8b4dc103929e1ed`, the merge base; no other text changed.
