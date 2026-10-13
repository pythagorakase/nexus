# Home Theme Menu: Show a Rejected Theme Save (#961)

Work order 961-HOME with coordinator amendments 1 and 2 (2026-10-09) and the resume amendment (2026-10-13). Branch `claude/961-home-theme-save-error`, cut from `claude/wave-b-integration` at `7eb9a10c`. The code head is `a8d45cce` (review fixes of 2026-10-13; see "Review Fixes"). No Python change, no migration, and no paid call.

## Resumed on 2026-10-13

The second builder stopped at the usage limit on 2026-10-09 at 03:23, after the five code commits and before this evidence directory was committed. On resume, `git status --short` showed only `?? docs/qa/961-home-theme-save-error/`, and `claude/wave-b-integration` was still at `7eb9a10c` (`git merge claude/wave-b-integration`: `Already up to date.`). The draft's claims were checked against the round-2 logs in `scratchpad/961-HOME-r2/` and against the current tree. They hold, and they are kept below. Every proof command was then run again on the code head (`scratchpad/961-HOME-r3/`), and the rendered check on lane 8025 was repeated. The fresh tails replace the 2026-10-09 tails below; the two rendered-check screenshots are the 2026-10-13 captures.

| Commit | What it holds | Order item |
| --- | --- | --- |
| `7727ccef` | First-round red tests against the bare menu | Item 4 (the red run before the product change) |
| `8451c2cb` | The menu change as first ordered: controlled `open`, the alert below the themes, clear on unmount | Items 1 and 2, as first ordered |
| `1ab1b773` | Tests rewritten to render `SplashPage` with the real provider and query client; new `WizardShell.theme.test.tsx` | Item 4 with ruling (b); Part B tests (ruling d) |
| `9521d2b9` | One `SplashThemeMenu` hoisted into `SplashPage`; `ThemeSaveRejected` and `useOpenOnThemeSaveError`; open on mount, no clear on unmount; wizard menu opens on a rejection | Items 1-3 with rulings (a) and (c); Part B (ruling d) |
| `4d8ea147` | The wizard's alert rendered beside `ThemeMenu`, which is unchanged, instead of through a new prop | Part B (ruling d); keeps `npm --prefix ui run check` green |
| `a2ce08e9` | This evidence directory and `pr-body.md` | Item 5 and the proof section |
| `a8d45cce` | Review fixes: the Home menu first in the tab order again; the second-rejection test holds its second answer | Item 3 (no other visible change); item 4 |
| this commit | The evidence and `pr-body.md` updated for the review fixes | The proof section |

Part B needed no structural change (see "What Changed"), so nothing from it is deferred.

## The Problem on the Base

- `ui/client/src/pages/splash/shared.tsx:77-110` (base): `SplashThemeMenu` read only `theme`, `setTheme` and `glowClass` from `useTheme()`. It did not read the save state.
- `ui/client/src/pages/SplashPage.tsx:12-17` (base) renders a different splash component for each theme. `VeilSplash.tsx:161`, `GildedSplash.tsx:181` and `VectorSplash.tsx:355` each rendered their own `<SplashThemeMenu />`. `ThemeContext.setTheme` applies the pick before the save, so the variant swaps. A rejected save rolls the cache back and the variant swaps back again. A rejected pick therefore remounted the menu twice, and the ordered alert was lost on each remount. The builder's STOP report of 03:16 found this, and coordinator amendment 2 ruled on it.
- `ui/client/src/components/ThemeMenu.tsx` (the wizard's shared theme items, rendered by `WizardShell.tsx:246`) also read no save state.

## What Changed

- `ui/client/src/components/ThemeSaveRejected.tsx` (new):
  - `ThemeSaveRejected({ testId })` renders the Settings card's alert. It is one `role="alert"` element with the classes `alert danger`, the title `WRITE REJECTED` and the message. It renders nothing while `saveError` is null.
  - `nexus-layout.css` defines `--danger` only inside `.settings-pane-v2` (lines 1326-1327), and the menu portal sits outside that pane. The element therefore sets `--danger: hsl(var(--destructive))`, which is the same mapping the pane uses. This adds no new color or hue. The rendered border and title read `rgb(210, 45, 45)`, which is `--destructive` `0 65% 50%`.
  - `useOpenOnThemeSaveError(setOpen)` opens a menu when `saveError` changes from null to a message. It also opens a menu that mounts while a rejection is still held (ruling c).
- `ui/client/src/pages/SplashPage.tsx` renders exactly one `<SplashThemeMenu />`, outside the variant swap (ruling a). `VeilSplash.tsx`, `GildedSplash.tsx` and `VectorSplash.tsx` no longer render it. The wrapper keeps `position: absolute; top: 28px; left: 28px; z-index: 50`. The menu is rendered before the variant, so its trigger stays the first focusable element on Home, as it was when each variant rendered it first (`VeilSplash.tsx:160-161` on the base). The paint order does not change: the highest `zIndex` inside a variant is 10 (`VectorSplash.tsx:378`), below the wrapper's 50.
- `ui/client/src/pages/splash/shared.tsx`: `SplashThemeMenu` now controls its own `open` state with `useState` and keeps the same user-driven open and close behavior. It calls `useOpenOnThemeSaveError(setOpen)` and renders `<ThemeSaveRejected testId="splash-theme-save-error" />` below the theme items. It no longer clears the error on unmount (ruling c).
- `ui/client/src/components/NewStoryWizard/WizardShell.tsx` (Part B, ruling d): the hamburger `DropdownMenu` is controlled with `menuOpen`. It calls `useOpenOnThemeSaveError(setMenuOpen)` and renders `<ThemeSaveRejected testId="wizard-theme-save-error" />` right after `<ThemeMenu />`. `ThemeMenu.tsx` itself is unchanged: a required prop on it failed `npm --prefix ui run check`, because `.design-sync/previews/ThemeMenu.tsx` renders `<ThemeMenu />` bare. The wizard did not need a structural change and does not remount on a theme change: `NewStoryPage` renders `<NewStoryWizard />` without a theme key.
- Test stubs: `WizardShell.test.tsx` and `ContinuePage.resume.test.tsx` stub `useTheme` module-wide. Their stub changed from `({})` to `({ saveError: null })` because `WizardShell` now reads `saveError`.
- Tests:
  - `ui/client/src/pages/splash/SplashThemeMenu.test.tsx` renders `SplashPage` with the real `ThemeProvider` and query client (ruling b), so the variant swap and remount are part of each test. jsdom has no canvas, so the file gives the Veil spiral a 2D context that accepts every call. This is an environment shim like the `ResizeObserver` one in `tests/setup.ts`. The file has no bare-menu case, because every bare-menu assertion is covered through `SplashPage`.
  - `ui/client/src/components/NewStoryWizard/WizardShell.theme.test.tsx` (new) holds the mirrored wizard tests. It renders `NewStoryWizard` with the real provider and query client, and spies `fetch` for the slot list and `PATCH /api/preferences` only.

## Behavior and the Residuals

- If a pick from the Home menu is rejected, the menu closes on select and then opens again with the alert below the themes. The checkmark stays on the saved theme. A new pick starts a new save, and the alert clears when the shared mutation resets. A successful pick closes the menu as before and shows no alert.
- The rejection is held in the theme context until a later save succeeds or the Settings THEME card mounts (that card still clears on mount). A Home menu or wizard menu that mounts while a rejection is held opens and shows it.
- Residual from ruling (c): suppose the player picks a theme on Home and leaves Home within the same second, before the answer arrives. The rejection then appears on the next Home visit (or in the wizard menu), not in Settings, because the Settings card clears on mount.
- Residual, for the coordinator to decide: nothing clears a held rejection except a successful save or a Settings visit. Suppose the player sees the alert on Home, closes the menu, and opens the wizard or returns to Home. The menu then opens again on the same rejection. This follows rulings (c) and (d) as written. Clearing on an explicit dismissal (Escape or an outside click, not an item select, because Radix runs the item's `onClick` before it closes the menu) would end the repeat. That clearing was not ordered, so it is not built.

## Red Runs Before the Product Change

The first round's red run of the bare-menu tests (`7727ccef` against the base) is in `scratchpad/961-HOME/red.log`. The round-2 tests drive `SplashPage` and `WizardShell` and were each run red against the product files they cover:

`nice -n 15 npm --prefix ui test -- SplashThemeMenu` with the base splash files (`claude/wave-b-integration` versions of `SplashPage.tsx`, `shared.tsx` and the three variants):

```
   × Home theme menu save failures (#961) > shows an online HTTP rejection inside the open menu and keeps Veil checked 1090ms
   × Home theme menu save failures (#961) > shows a network failure inside the open menu 1028ms
   × Home theme menu save failures (#961) > shows a second rejection after a new pick cleared the first 1027ms
   × Home theme menu save failures (#961) > a successful retry after an HTTP 500 clears the alert, closes the menu and checks Gilded 1024ms
   × Home theme menu save failures (#961) > a successful retry after a network failure clears the alert, closes the menu and checks Gilded 1024ms
   × Home theme menu save failures (#961) > shows a held rejection when Home mounts again, and Settings shows none 1025ms
   × Home theme menu save failures (#961) > shows on return a rejection that completed while the player was elsewhere 1045ms
 Test Files  1 failed (1)
      Tests  7 failed | 1 passed (8)
```

The same command with `8451c2cb`'s `shared.tsx` (the menu change as first ordered, not hoisted, clearing on unmount) and the base `SplashPage.tsx` and variants (`scratchpad/961-HOME-r2/red-unhoisted.log`). Six tests fail because the remount loses the alert. The seventh fails on the context probe instead:

```
   × ... shows an online HTTP rejection inside the open menu and keeps Veil checked 1094ms
     → Unable to find an element by: [data-testid="splash-theme-save-error"]
   × ... shows a network failure inside the open menu 1030ms
     → Unable to find an element by: [data-testid="splash-theme-save-error"]
   × ... shows a second rejection after a new pick cleared the first 1027ms
     → Unable to find an element by: [data-testid="splash-theme-save-error"]
   × ... a successful retry after an HTTP 500 clears the alert, closes the menu and checks Gilded 1026ms
     → Unable to find an element by: [data-testid="splash-theme-save-error"]
   × ... a successful retry after a network failure clears the alert, closes the menu and checks Gilded 1026ms
     → Unable to find an element by: [data-testid="splash-theme-save-error"]
   × ... shows a held rejection when Home mounts again, and Settings shows none 1026ms
     → Unable to find an element by: [data-testid="splash-theme-save-error"]
   × ... shows on return a rejection that completed while the player was elsewhere 1035ms
     → expect(element).toHaveTextContent()
Expected element to have text content:
  Failed to fetch
Received:
  none
 Test Files  1 failed (1)
      Tests  7 failed | 1 passed (8)
```

The seventh failure comes from `8451c2cb`'s `clearSaveError` on unmount, which ruling (c) removed. `clearSaveError` is the mutation's `reset` (`ThemeContext.tsx:95`). Leaving Home while the save is still pending unmounts the menu, and the reset detaches the context from the pending mutation. The rejection that arrives later therefore never reaches `saveError`, and the probe reads `none`.

(This run predates the two tests that `a8d45cce` added or changed; see "Review Fixes".)

`nice -n 15 npm --prefix ui test -- WizardShell.theme` with the base `WizardShell.tsx` and `ThemeMenu.tsx`:

```
   × wizard theme menu save failures (#961) > shows an online HTTP rejection inside the open menu and keeps Veil checked 1108ms
     → Unable to find an element by: [data-testid="wizard-theme-save-error"]
   × wizard theme menu save failures (#961) > shows a network failure inside the open menu 1032ms
   × ... a successful retry after an HTTP 500 clears the alert, closes the menu and checks Gilded 1031ms
   × ... a successful retry after a network failure clears the alert, closes the menu and checks Gilded 1028ms
   × ... opens on mount with a rejection that completed before the wizard opened 1008ms
 Test Files  1 failed (1)
      Tests  5 failed | 1 passed (6)
```

In each red run, the one passing test is the success path, which the base already satisfies.

## Review Fixes (`a8d45cce`, 2026-10-13)

Four review findings were applied. Logs and scripts are in `scratchpad/961-HOME-r3/fix/`.

- Tab order. After the hoist, `SplashPage` rendered the menu after the variant, so the trigger moved from the first to the last focusable element on Home (behind Continue, Load and Settings). `SplashPage` now renders it before the variant. The new test `keeps the theme menu trigger first in the tab order on Home` tabs once from the page (`@testing-library/user-event`) and expects the trigger to have focus. Red run with `4d8ea147`'s `SplashPage.tsx` (`red-taborder.log`):

  ```
     × Home theme menu save failures (#961) > keeps the theme menu trigger first in the tab order on Home 16ms
       → expect(element).toHaveFocus()
  Received element with focus:
    <button class="" style="position: relative; width: 280px; ... border: 2px solid var(--brass); ...">   (the Veil Continue button)
   Test Files  1 failed (1)
        Tests  1 failed | 8 passed (9)
  ```

  The rendered check below repeats this in Chromium for all three themes (`firstTabIsTrigger`).
- The second-rejection test. Its assertion that the alert was gone after the second pick passed on the menu closing alone, because closing unmounts `DropdownMenuContent` whatever `saveError` holds. The test now holds the second `PATCH` answer, waits until the context probe reads `none` while that save is pending, then answers with the 500 and expects the alert inside the reopened menu. Red run with a temporary `ThemeContext.tsx` change that keeps the previous error while a new save is pending (`red-sticky-error.patch`, reverted; `red-sticky-error.log`):

  ```
     × Home theme menu save failures (#961) > shows a second rejection after a new pick cleared the first 1063ms
       → expect(element).toHaveTextContent()
  Expected element to have text content:
    none
  Received:
    500: PermissionError: [Errno 13] Permission denied
   Test Files  1 failed (1)
        Tests  1 failed | 8 passed (9)
  ```

  Under the same temporary change, the previous version of the test also fails (`old-test-sticky-error.log`), but later and for a different reason: `Unable to find an element by: [data-testid="splash-theme-save-error"]` at the old file's line 165, because a held error never changes from null to a message, so the menu does not open again. Its "cleared" assertion (line 163) passed.
- The red-run report for `8451c2cb` above now lists each failure; one of the seven differs.
- The placement claims below now cite a recorded pixel comparison.

## Proof on the Code Head (`a8d45cce`, 2026-10-13)

Every command ran from the worktree root, after `git merge claude/wave-b-integration` (`Already up to date.`; the integration branch is still at `7eb9a10c`). `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus;print(nexus.__file__)'` printed `/Users/pythagor/nexus/.claude/worktrees/961-home-theme-save-error/nexus/__init__.py`. Logs are in `scratchpad/961-HOME-r3/fix/`.

`nice -n 15 npm --prefix ui test -- SplashThemeMenu SettingsPane shell-accessibility` (exit 0):

```
 ✓ src/shell-accessibility.test.ts (11 tests) 54ms
 ✓ src/components/nexus/SettingsPane.test.tsx (20 tests) 693ms
 ✓ src/pages/splash/SplashThemeMenu.test.tsx (9 tests) 605ms
 Test Files  3 passed (3)
      Tests  40 passed (40)
   Start at  10:38:39
   Duration  1.33s (transform 164ms, setup 107ms, collect 510ms, tests 1.35s, environment 612ms, prepare 111ms)
```

`nice -n 15 npm --prefix ui test -- SplashThemeMenu SettingsPane shell-accessibility WizardShell ContinuePage` (Part B and the two files whose stubs changed; exit 0):

```
 ✓ src/shell-accessibility.test.ts (11 tests) 57ms
 ✓ src/components/nexus/SettingsPane.test.tsx (20 tests) 713ms
 ✓ src/pages/splash/SplashThemeMenu.test.tsx (9 tests) 630ms
 ✓ src/pages/ContinuePage.test.tsx (8 tests) 832ms
 ✓ src/components/NewStoryWizard/WizardShell.theme.test.tsx (6 tests) 476ms
 ✓ src/components/NewStoryWizard/WizardShell.test.tsx (24 tests) 1217ms
 ✓ src/pages/ContinuePage.resume.test.tsx (4 tests) 3559ms
 Test Files  7 passed (7)
      Tests  82 passed (82)
   Start at  10:38:41
   Duration  4.53s (transform 755ms, setup 284ms, collect 2.49s, tests 7.48s, environment 1.96s, prepare 503ms)
```

The stderr of that run carries `Function components cannot be given refs` warnings from `InteractiveWizard` → `ResizablePanelGroup`, in `WizardShell.test.tsx` and `ContinuePage.resume.test.tsx`. This change does not touch those components.

`nice -n 15 npm --prefix ui test` (the full suite; exit 1). Every file passes except `state-shades.test.ts`, whose "Stale browser-resolved state surfaces" failure is expected on this base (amendment 1, item 4):

```
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 42 passed (43)
      Tests  647 passed (647)
   Start at  10:38:46
   Duration  7.79s (transform 2.86s, setup 2.52s, collect 15.29s, tests 22.59s, environment 17.84s, prepare 2.41s)
```

`nice -n 15 npm --prefix ui run check` (exit 0):

```
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
```

`nice -n 15 npm --prefix ui run build` (exit 0). The bundle is `index-Bjad2Pld.js`. On `4d8ea147` it was `index--wbtCQTL.js`, the bundle that rounds 2 and 3 of the rendered check served:

```
✓ 2818 modules transformed.
../dist/public/assets/index-Bjad2Pld.js                         1,775.64 kB │ gzip: 529.87 kB
✓ built in 3.01s
```

Repository gates:

```
$ /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref claude/wave-b-integration
OK: exception disposition coverage and shrink-only baseline verified.
$ PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 8.27s
```

No changed path is in the `sources:` list of a `status: canonical` document, so no `verified_commit` moves. There is no Python change, so mypy and flake8 have no changed files to check. No PostgreSQL test applies.

## Rendered Verification (Lane 8025)

Every round ran the gateway the same way, from this worktree, with `NEXUS_HOME=scratchpad/961-HOME-r<n>/home` (round 4: `scratchpad/961-HOME-r3/fix/home`). That directory holds a copy of `nexus.toml` whose only change is `[runtime].state_dir` pointing to a private `state` directory beside it. The environment also had `NEXUS_GATEWAY_PORT=8025`, `NEXUS_API_URL=http://127.0.0.1:8025`, `NEXUS_TEST_PROVIDER_ONLY=1` and `NEXUS_KEYRING_DISABLE=1`, with `NEXUS_SLOT` unset. The process was `python -m uvicorn nexus.api.narrative:app --host 127.0.0.1 --port 8025`, not `nexus up`, because `nexus up` would also start the TEST provider's mock service on 5102, which must stay stopped. Driving was headless Chromium (Playwright from `ui/node_modules`) at 1200x900.

- Round 2 (2026-10-09, PID 12001): the placement captures below and a first rejected-pick run. API calls: `GET /api/settings` (8), `GET /api/preferences` (8), `PATCH /api/preferences` (11, including the placement theme saves), `GET /api/dev/backstage/health` (8).
- Round 3 (2026-10-13, PID 53673): the rejected-pick run below and a menu timeline. `lsof -nP -iTCP:8025 -sTCP:LISTEN` found no listener before the start. A seed `PATCH /api/preferences {"theme":"veil"}` answered 200 and wrote the private `preferences.toml`. API calls: `GET /api/settings` (3), `GET /api/preferences` (5), `PATCH /api/preferences` (6: the seed, three rejected picks, the retry, the timeline reset), `GET /api/dev/backstage/health` (3, all 404). After the run, PID 53673 was stopped, 8025 was free again, and `nexus down` with the same environment printed `nothing running`; 8002 and 5102 had no listener.
- Round 4 (2026-10-13, PID 89498, `scratchpad/961-HOME-r3/fix/home`, bundle `index-Bjad2Pld.js` from `a8d45cce`): the placement and tab-order check below. `lsof` found no listener on 8025 before the start. API calls: `GET /api/settings` (3), `GET /api/preferences` (5), `PATCH /api/preferences` (4: one theme save per capture, then Veil restored), `GET /api/dev/backstage/health` (3). After the run, PID 89498 was stopped, 8025 was free again, `nexus down` with the same environment printed `nothing running`, and 8002 and 5102 had no listener.

None of these routes reads a slot database. No owner path and no port 8002, 8012 or 5102 was touched in any round.

### Placement Before and After the Hoist

The base bundle (`index-C5o0njTX.js`, built from the `claude/wave-b-integration` splash and wizard files) and `4d8ea147`'s bundle (`index--wbtCQTL.js`) were each served in turn in round 2, and `a8d45cce`'s bundle (`index-Bjad2Pld.js`) in round 4. Each theme was saved through `PATCH /api/preferences` and Home was loaded. Round 4's driver (`scratchpad/961-HOME-r3/fix/placement.cjs`, round 2's driver plus one `Tab` press after the screenshot) also records whether the first `Tab` focuses the trigger:

```
before veil   {"htmlClass":"dark","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,"wrapper":"position: absolute; top: 28px; left: 28px; z-index: 50;"}
before gilded {"htmlClass":"dark theme-gilded","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...}
before vector {"htmlClass":"dark theme-vector","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...}
after veil    {"htmlClass":"dark","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,"wrapper":"position: absolute; top: 28px; left: 28px; z-index: 50;"}
after gilded  {"htmlClass":"dark theme-gilded","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...}
after vector  {"htmlClass":"dark theme-vector","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...}
after2 veil   {"htmlClass":"dark","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,"wrapper":"position: absolute; top: 28px; left: 28px; z-index: 50;","firstTabIsTrigger":true}
after2 gilded {"htmlClass":"dark theme-gilded","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...,"firstTabIsTrigger":true}
after2 vector {"htmlClass":"dark theme-vector","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...,"firstTabIsTrigger":true}
```

The trigger's DOM box, its wrapper and its place on top are therefore the same before the hoist, after it, and after the tab-order fix.

Pixel comparison of the original 1200x900 PNG captures (the JPEGs below are compressed copies). The script is `scratchpad/961-HOME-r3/fix/compare_placement.py`. It uses Pillow's `ImageChops.difference`, and for the full frame and for the trigger box (x 28, y 28, 36x36) it reports the count of differing pixels, their bounding box, and the peak luma of the difference image. Output (`compare_placement.log`):

```
$ python -I compare_placement.py ../../961-HOME-r2/shots ../../961-HOME-r2/shots after
veil    frame   differing px  68407  bbox (0, 0, 1200, 900)  peak luma of difference 190
veil    trigger differing px     86  bbox (16, 0, 26, 36)  peak luma of difference 15
gilded  frame   differing px      0  bbox None  peak luma of difference 0
gilded  trigger differing px      0  bbox None  peak luma of difference 0
vector  frame   differing px  51858  bbox (2, 0, 1200, 899)  peak luma of difference 187
vector  trigger differing px    200  bbox (8, 0, 19, 20)  peak luma of difference 36
$ python -I compare_placement.py ../../961-HOME-r2/shots shots after2
veil    frame   differing px  63252  bbox (0, 0, 1200, 900)  peak luma of difference 190
veil    trigger differing px     77  bbox (16, 0, 26, 36)  peak luma of difference 10
gilded  frame   differing px      0  bbox None  peak luma of difference 0
gilded  trigger differing px      0  bbox None  peak luma of difference 0
vector  frame   differing px  50344  bbox (0, 0, 1200, 900)  peak luma of difference 187
vector  trigger differing px    200  bbox (8, 0, 19, 20)  peak luma of difference 36
```

- Gilded, whose Home has no animation, is identical pixel for pixel in all three captures, including the trigger.
- Veil and Vector differ across the whole frame, because the spiral canvas and the Vector grid animate and each capture catches a different frame. Inside the trigger box, 77 to 86 (Veil) and 200 (Vector) of the 1296 pixels differ. The button is the `ghost` variant and has no background of its own, and its glyph is drawn in the primary color at 70% alpha (`text-primary/70`). So pixels in the box take on the animated background behind them. These differences do not show that the trigger itself moved or changed; the identical DOM box above shows that it did not.

| Theme | Before | After |
| --- | --- | --- |
| Veil | ![](before-home-veil.jpg) | ![](after-home-veil.jpg) |
| Gilded | ![](before-home-gilded.jpg) | ![](after-home-gilded.jpg) |
| Vector | ![](before-home-vector.jpg) | ![](after-home-vector.jpg) |

### Rejected Picks, Retry and Reload (Round 3)

This run used `4d8ea147`'s production bundle, with Veil saved. Only the private state directory was made read-only (`chmod 0555`). Driver: `scratchpad/961-HOME-r3/scripts/render.cjs` (round 2's driver, unchanged). Excerpt of its log (`scratchpad/961-HOME-r3/render.log`; the `outerHTML` field is cut):

```
2026-10-13T15:25:57.198Z home loaded; html class: "dark" prefs sha256: 163b1afa7d2747c8e08b247a5f0eb1903c7920311cbdc1ebeb2e38ff0211e386
2026-10-13T15:25:57.288Z menu items: Gilded | Vector | Veil ✓
2026-10-13T15:25:57.569Z state dir mode now 555
2026-10-13T15:25:57.604Z attempt 1: menu open before pick: true
2026-10-13T15:25:57.655Z response: PATCH /api/preferences 500
2026-10-13T15:26:02.606Z pick Gilded: menu closed after the pick: false
2026-10-13T15:26:02.607Z failure 1: PATCH status 500
2026-10-13T15:26:02.610Z failure 1: alert {"role":"alert","testid":"splash-theme-save-error","className":"alert danger mt-1 max-w-[280px] break-words","text":"WRITE REJECTED500: Internal Server Error","insideMenu":true,"borderLeftColor":"rgb(210, 45, 45)","titleColor":"rgb(210, 45, 45)","destructive":"0 65% 50%",...}
2026-10-13T15:26:02.612Z failure 1: menu items: Gilded | Vector | Veil ✓ html class: "dark"
2026-10-13T15:26:02.612Z failure 1: prefs sha256 unchanged: true
2026-10-13T15:26:02.613Z attempt 2: menu open before pick: true
2026-10-13T15:26:02.672Z response: PATCH /api/preferences 500
2026-10-13T15:26:07.614Z pick Gilded: menu closed after the pick: false
2026-10-13T15:26:07.615Z failure 2: PATCH status 500
2026-10-13T15:26:07.617Z failure 2: alert {"role":"alert","testid":"splash-theme-save-error",...,"text":"WRITE REJECTED500: Internal Server Error","insideMenu":true,...}
2026-10-13T15:26:07.618Z failure 2: menu items: Gilded | Vector | Veil ✓ html class: "dark"
2026-10-13T15:26:07.618Z failure 2: prefs sha256 unchanged: true
2026-10-13T15:26:07.651Z state dir mode now 755
2026-10-13T15:26:07.705Z response: PATCH /api/preferences 200
2026-10-13T15:26:07.930Z pick Gilded: menu closed after the pick: true
2026-10-13T15:26:07.934Z retry: PATCH status 200 alert count: 0 menu visible: false html class: "dark theme-gilded"
2026-10-13T15:26:07.934Z retry: preferences theme line: theme = "gilded"
2026-10-13T15:26:08.600Z after reload: html class: "dark theme-gilded" menu items: Gilded ✓ | Vector | Veil alert count: 0
```

Round 2's run (`scratchpad/961-HOME-r2/render.log`, 2026-10-09T08:26) logged the same lines, with the same prefs hash, the same alert text and colors, and the same retry and reload results.

Two log lines need explaining:
- After each rejected pick the driver logged `menu closed after the pick: false`. The round-3 timeline (`scratchpad/961-HOME-r3/scripts/timeline.cjs`, a `MutationObserver` on the menu's `data-state`, the trigger's `aria-expanded` and the alert) shows what happens instead. The item select does close the menu. The 500 arrives about 25 ms later, and the menu opens again with the alert 7 ms after that. The closing menu stays in the page for its exit animation, so it never became hidden for the driver to see:

  ```
  {"ms":0,"why":"start","menus":["open"],"alert":false,"trigger":"true"}
  {"ms":1,"why":"click Gilded"}
  {"ms":257,"why":"mutation","menus":["closed"],"alert":false,"trigger":"false"}
  {"ms":280,"why":"PATCH answered 500"}
  {"ms":281,"why":"mutation","menus":["closed"],"alert":true,"trigger":"false"}
  {"ms":288,"why":"mutation","menus":["open"],"alert":true,"trigger":"true"}
  ```

  (The 256 ms before the close is Playwright's own click handling.)
- The console's `404` lines are `GET /api/dev/backstage/health` (the developer gate is off).

Gateway log for the same window (`scratchpad/961-HOME-r3/gateway.log`, in order; the third 500 is the timeline run):

```
INFO:     127.0.0.1:61885 - "PATCH /api/preferences HTTP/1.1" 200 OK
INFO:     127.0.0.1:61890 - "PATCH /api/preferences HTTP/1.1" 500 Internal Server Error
PermissionError: [Errno 13] Permission denied: '.../scratchpad/961-HOME-r3/home/state/tmpgu50tcbe'
INFO:     127.0.0.1:61892 - "PATCH /api/preferences HTTP/1.1" 500 Internal Server Error
PermissionError: [Errno 13] Permission denied: '.../scratchpad/961-HOME-r3/home/state/tmpoexfxi3f'
INFO:     127.0.0.1:61911 - "PATCH /api/preferences HTTP/1.1" 200 OK
INFO:     127.0.0.1:61915 - "PATCH /api/preferences HTTP/1.1" 200 OK
INFO:     127.0.0.1:61918 - "PATCH /api/preferences HTTP/1.1" 500 Internal Server Error
PermissionError: [Errno 13] Permission denied: '.../scratchpad/961-HOME-r3/home/state/tmpvtmcp0pb'
```

The alert DOM after the second rejection:

```html
<div class="alert danger mt-1 max-w-[280px] break-words" role="alert" data-testid="splash-theme-save-error" style="--danger: hsl(var(--destructive));"><svg ... class="lucide lucide-triangle-alert">...</svg><div class="min-w-0"><div class="alert-title">WRITE REJECTED</div><div class="alert-body">500: Internal Server Error</div></div></div>
```

![Home menu after the second rejected Gilded pick](home-menu-write-rejected.jpg)

![Home after the retry and a reload: Gilded saved, no alert](home-after-retry-and-reload.jpg)

The wizard menu was not driven in the browser. Opening `/new-story` reads the slot list from the save databases, and the order assigns the rendered check to Home only. The wizard menu is covered by `WizardShell.theme.test.tsx`.

## Machine Load

Round 2: the one-minute load was 6.6 to 19.3. Round 3: it was 8.1 at the start and 26.8 at the end, when another builder's work overlapped the offline `tests/test_doc_front_matter.py` run. Review fixes: it was 14.6 to 28.7. No PostgreSQL run took place in any round, so the load wait did not apply. Every test, build and Chromium command ran under `nice -n 15`.
