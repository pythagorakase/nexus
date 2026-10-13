# Home Theme Menu: Show a Rejected Theme Save (#961)

Work order 961-HOME with coordinator amendments 1 and 2 (2026-10-09) and the resume amendment (2026-10-13). Branch `claude/961-home-theme-save-error`, cut from `claude/wave-b-integration` at `7eb9a10c`. The code head is `4d8ea147`. No Python change, no migration, and no paid call.

## Resumed on 2026-10-13

The second builder stopped at the usage limit on 2026-10-09 at 03:23, after the five code commits and before this evidence directory was committed. On resume, `git status --short` showed only `?? docs/qa/961-home-theme-save-error/`, and `claude/wave-b-integration` was still at `7eb9a10c` (`git merge claude/wave-b-integration`: `Already up to date.`). The draft's claims were checked against the round-2 logs in `scratchpad/961-HOME-r2/` and against the current tree. They hold, and they are kept below. Every proof command was then run again on the code head (`scratchpad/961-HOME-r3/`), and the rendered check on lane 8025 was repeated. The fresh tails replace the 2026-10-09 tails below; the two rendered-check screenshots are the 2026-10-13 captures.

| Commit | What it holds | Order item |
| --- | --- | --- |
| `7727ccef` | First-round red tests against the bare menu | Item 4 (the red run before the product change) |
| `8451c2cb` | The menu change as first ordered: controlled `open`, the alert below the themes, clear on unmount | Items 1 and 2, as first ordered |
| `1ab1b773` | Tests rewritten to render `SplashPage` with the real provider and query client; new `WizardShell.theme.test.tsx` | Item 4 with ruling (b); Part B tests (ruling d) |
| `9521d2b9` | One `SplashThemeMenu` hoisted into `SplashPage`; `ThemeSaveRejected` and `useOpenOnThemeSaveError`; open on mount, no clear on unmount; wizard menu opens on a rejection | Items 1-3 with rulings (a) and (c); Part B (ruling d) |
| `4d8ea147` | The wizard's alert rendered beside `ThemeMenu`, which is unchanged, instead of through a new prop | Part B (ruling d); keeps `npm --prefix ui run check` green |
| this commit | This evidence directory and `pr-body.md` | Item 5 and the proof section |

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
- `ui/client/src/pages/SplashPage.tsx` renders exactly one `<SplashThemeMenu />`, outside the variant swap (ruling a). `VeilSplash.tsx`, `GildedSplash.tsx` and `VectorSplash.tsx` no longer render it. The wrapper keeps `position: absolute; top: 28px; left: 28px; z-index: 50`.
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

The same command with `8451c2cb`'s `shared.tsx` (the menu change as first ordered, not hoisted, clearing on unmount) and the base `SplashPage.tsx` and variants. This shows that the remount defeats the unhoisted design:

```
   × ... shows an online HTTP rejection inside the open menu and keeps Veil checked 1094ms
     → Unable to find an element by: [data-testid="splash-theme-save-error"]
   (the same seven tests fail, each with the same message)
 Test Files  1 failed (1)
      Tests  7 failed | 1 passed (8)
```

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

## Proof on the Code Head (`4d8ea147`, Rerun 2026-10-13)

Every command ran from the worktree root, after `git merge claude/wave-b-integration` (`Already up to date.`). `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus;print(nexus.__file__)'` printed `/Users/pythagor/nexus/.claude/worktrees/961-home-theme-save-error/nexus/__init__.py`. Logs are in `scratchpad/961-HOME-r3/`.

`nice -n 15 npm --prefix ui test -- SplashThemeMenu SettingsPane shell-accessibility` (exit 0):

```
 ✓ src/shell-accessibility.test.ts (11 tests) 67ms
 ✓ src/components/nexus/SettingsPane.test.tsx (20 tests) 656ms
 ✓ src/pages/splash/SplashThemeMenu.test.tsx (8 tests) 516ms
 Test Files  3 passed (3)
      Tests  39 passed (39)
   Start at  10:24:44
   Duration  1.57s (transform 182ms, setup 185ms, collect 591ms, tests 1.24s, environment 1.05s, prepare 508ms)
```

`nice -n 15 npm --prefix ui test -- SplashThemeMenu SettingsPane shell-accessibility WizardShell ContinuePage` (Part B and the two files whose stubs changed; exit 0):

```
 ✓ src/shell-accessibility.test.ts (11 tests) 61ms
 ✓ src/components/nexus/SettingsPane.test.tsx (20 tests) 700ms
 ✓ src/pages/splash/SplashThemeMenu.test.tsx (8 tests) 598ms
 ✓ src/pages/ContinuePage.test.tsx (8 tests) 834ms
 ✓ src/components/NewStoryWizard/WizardShell.theme.test.tsx (6 tests) 452ms
 ✓ src/components/NewStoryWizard/WizardShell.test.tsx (24 tests) 1162ms
 ✓ src/pages/ContinuePage.resume.test.tsx (4 tests) 3552ms
 Test Files  7 passed (7)
      Tests  81 passed (81)
   Start at  10:24:50
   Duration  4.54s (transform 686ms, setup 286ms, collect 2.63s, tests 7.36s, environment 1.72s, prepare 362ms)
```

The stderr of that run carries `Function components cannot be given refs` warnings from `InteractiveWizard` → `ResizablePanelGroup`, in `WizardShell.test.tsx` and `ContinuePage.resume.test.tsx`. This change does not touch those components.

`nice -n 15 npm --prefix ui test` (the full suite; exit 1). Every file passes except `state-shades.test.ts`, whose "Stale browser-resolved state surfaces" failure is expected on this base (amendment 1, item 4):

```
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 42 passed (43)
      Tests  646 passed (646)
   Start at  10:24:55
   Duration  9.15s (transform 3.42s, setup 3.05s, collect 15.63s, tests 24.20s, environment 18.09s, prepare 2.83s)
```

`nice -n 15 npm --prefix ui run check` (exit 0):

```
> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json
```

`nice -n 15 npm --prefix ui run build` (exit 0). The bundle hash is the same as round 2's, so the rendered checks of both rounds ran the same code:

```
✓ 2818 modules transformed.
../dist/public/assets/index--wbtCQTL.js                         1,775.64 kB │ gzip: 529.87 kB
✓ built in 2.71s
```

Repository gates:

```
$ /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref claude/wave-b-integration
OK: exception disposition coverage and shrink-only baseline verified.
$ PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 8.00s
```

No changed path is in the `sources:` list of a `status: canonical` document, so no `verified_commit` moves. There is no Python change, so mypy and flake8 have no changed files to check. No PostgreSQL test applies.

## Rendered Verification (Lane 8025)

Both rounds ran the gateway the same way, from this worktree, with `NEXUS_HOME=scratchpad/961-HOME-r<n>/home`. That directory holds a copy of `nexus.toml` whose only change is `[runtime].state_dir` pointing to a private `scratchpad/961-HOME-r<n>/home/state`. The environment also had `NEXUS_GATEWAY_PORT=8025`, `NEXUS_API_URL=http://127.0.0.1:8025`, `NEXUS_TEST_PROVIDER_ONLY=1` and `NEXUS_KEYRING_DISABLE=1`, with `NEXUS_SLOT` unset. The process was `python -m uvicorn nexus.api.narrative:app --host 127.0.0.1 --port 8025`, not `nexus up`, because `nexus up` would also start the TEST provider's mock service on 5102, which must stay stopped. Driving was headless Chromium (Playwright from `ui/node_modules`) at 1200x900.

- Round 2 (2026-10-09, PID 12001): the placement captures below and a first rejected-pick run. API calls: `GET /api/settings` (8), `GET /api/preferences` (8), `PATCH /api/preferences` (11, including the placement theme saves), `GET /api/dev/backstage/health` (8).
- Round 3 (2026-10-13, PID 53673): the rejected-pick run below and a menu timeline. `lsof -nP -iTCP:8025 -sTCP:LISTEN` found no listener before the start. A seed `PATCH /api/preferences {"theme":"veil"}` answered 200 and wrote the private `preferences.toml`. API calls: `GET /api/settings` (3), `GET /api/preferences` (5), `PATCH /api/preferences` (6: the seed, three rejected picks, the retry, the timeline reset), `GET /api/dev/backstage/health` (3, all 404). After the run, PID 53673 was stopped, 8025 was free again, and `nexus down` with the same environment printed `nothing running`; 8002 and 5102 had no listener.

None of these routes reads a slot database. No owner path and no port 8002, 8012 or 5102 was touched in either round.

### Placement Before and After the Hoist

The base bundle (`index-C5o0njTX.js`, built from the `claude/wave-b-integration` splash and wizard files) and this branch's bundle (`index--wbtCQTL.js`) were each served in turn. Each theme was saved through `PATCH /api/preferences` and Home was loaded:

```
before veil   {"htmlClass":"dark","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,"wrapper":"position: absolute; top: 28px; left: 28px; z-index: 50;"}
before gilded {"htmlClass":"dark theme-gilded","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...}
before vector {"htmlClass":"dark theme-vector","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...}
after veil    {"htmlClass":"dark","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,"wrapper":"position: absolute; top: 28px; left: 28px; z-index: 50;"}
after gilded  {"htmlClass":"dark theme-gilded","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...}
after vector  {"htmlClass":"dark theme-vector","triggers":1,"box":{"x":28,"y":28,"width":36,"height":36},"topmostIsTrigger":true,...}
```

The pixel comparison of the PNG captures:
- Gilded: the two captures are identical (no differing pixel).
- Veil and Vector: the captures differ only where the animated spiral strands and the Vector grid's scan beam happened to be at capture time. The trigger's box and its rendered glyph are the same in both captures.

| Theme | Before | After |
| --- | --- | --- |
| Veil | ![](before-home-veil.jpg) | ![](after-home-veil.jpg) |
| Gilded | ![](before-home-gilded.jpg) | ![](after-home-gilded.jpg) |
| Vector | ![](before-home-vector.jpg) | ![](after-home-vector.jpg) |

### Rejected Picks, Retry and Reload (Round 3)

This run used this branch's production bundle, with Veil saved. Only the private state directory was made read-only (`chmod 0555`). Driver: `scratchpad/961-HOME-r3/scripts/render.cjs` (round 2's driver, unchanged). Excerpt of its log (`scratchpad/961-HOME-r3/render.log`; the `outerHTML` field is cut):

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

Round 2: the one-minute load was 6.6 to 19.3. Round 3: it was 8.1 at the start and 26.8 at the end, when another builder's work overlapped the offline `tests/test_doc_front_matter.py` run. No PostgreSQL run took place in either round, so the load wait did not apply. Every test, build and Chromium command ran under `nice -n 15`.
