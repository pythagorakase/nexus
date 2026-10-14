Refs #961

## Goal

PR #962 gave the Settings THEME card an accessible WRITE REJECTED alert for a failed theme save. The Home theme menu (and the wizard's theme menu) still hid the rejection. On `f073b371`, the nightly QA recheck of 2026-10-09 picked Gilded twice from the Home menu with the private runtime directory read-only. Both picks got HTTP 500, and the menu went back to Veil with no visible or accessible feedback. This PR shows the rejection in the menu where the pick happened.

## What Was Wrong

- `ui/client/src/pages/splash/shared.tsx:77-110` (base): `SplashThemeMenu` read only `theme`, `setTheme` and `glowClass` from `useTheme()`, and nothing of the save state.
- `ui/client/src/pages/SplashPage.tsx:12-17` renders a different splash component per theme. `VeilSplash`, `GildedSplash` and `VectorSplash` each rendered their own `SplashThemeMenu`. A pick swaps the variant before the save completes, and a rejected save swaps it back. The menu was therefore remounted twice, and any alert inside it was lost.
- `ThemeMenu.tsx`, rendered by `WizardShell`, read no save state either.

## What Changed

- New `ui/client/src/components/ThemeSaveRejected.tsx`:
  - `ThemeSaveRejected` renders the Settings card's `alert danger` element (`role="alert"`, `WRITE REJECTED` and the message). It maps `--danger` to `--destructive`, because `nexus-layout.css` scopes `--danger` to the Settings pane. This adds no new color.
  - `useOpenOnThemeSaveError` opens a menu when a save is rejected, and also when the menu mounts while a rejection is still held.
- `SplashPage` renders exactly one `SplashThemeMenu`, outside the variant swap and before it, and the three variants no longer render it. The trigger's box is `x 28, y 28, 36x36` in every theme, both before and after the change, and it is still the first stop in the tab order. Its `z-index: 50` is above every variant layer (the highest is 10), so the paint order is unchanged.
- `SplashThemeMenu` now controls its own open state and shows `data-testid="splash-theme-save-error"` below the themes. It no longer clears the error on unmount; the Settings THEME card still clears it on mount. The comment above that clear now names the Home and wizard menus, which show and hold their own rejection.
- `WizardShell` (Part B) controls its menu's open state and opens on a rejection. It renders `data-testid="wizard-theme-save-error"` after `<ThemeMenu />`. `ThemeMenu.tsx` is unchanged, because the design-sync preview renders it with no props.
- Tests:
  - `SplashThemeMenu.test.tsx` now renders `SplashPage` with the real `ThemeProvider` and query client. It covers an HTTP 500, a network `TypeError`, a second rejection (the second answer is held so the test sees the cleared rejection while that save is pending), a retry after each kind of failure, a held rejection on a later Home visit with Settings staying clean, a rejection that completes while the player is away, the success path, and the trigger as the first tab stop on Home.
  - The new `WizardShell.theme.test.tsx` covers the wizard menu: an HTTP 500, a network `TypeError`, a second rejection (the second answer held, as on Home), a retry after each kind of failure, a rejection that completed before the wizard opened, and the success path. It has no counterpart for the Home held-rejection-on-remount test with Settings staying clean (its open-on-mount test covers the same hook path) or for the tab-order test (the wizard's trigger did not move).
  - The `useTheme` stubs in `WizardShell.test.tsx` and `ContinuePage.resume.test.tsx` now return `saveError: null`.
- Evidence is in `docs/qa/961-home-theme-save-error/verification.md`, with screenshots.

## Tests

The red runs came before the product change. Each one-test pass is the success path, which already holds on the base.
- `SplashThemeMenu` against the base splash files: `Tests  7 failed | 1 passed (8)`.
- `SplashThemeMenu` against the first-round, unhoisted menu (`8451c2cb`): 7 tests fail. Six fail with `Unable to find an element by: [data-testid="splash-theme-save-error"]`, because the remount loses the alert. The seventh, `shows on return a rejection that completed while the player was elsewhere`, fails on the context probe (expected `Failed to fetch`, received `none`). That failure comes from `8451c2cb`'s `clearSaveError` on unmount, which ruling (c) removed: `clearSaveError` is the mutation's `reset`, so leaving Home during the pending save detached the context from it.
- `WizardShell.theme` against the base wizard: `Tests  5 failed | 1 passed (6)`.
- Second review round (`7b66932f`): the wizard second-rejection test fails under the same temporary sticky-error change (expected `none`, received `500: PermissionError: ...`; `Tests  1 failed | 6 passed (7)`), and passes after the revert.
- Review fixes (`a8d45cce`): the new tab-order test against `4d8ea147`'s `SplashPage.tsx` fails (the Veil Continue button gets the first focus). The reworked second-rejection test fails under a temporary `ThemeContext.tsx` change that keeps the previous error while a new save is pending (expected `none`, received `500: PermissionError: ...`).

Green runs on the code head (`7b66932f`), on 2026-10-13 (`git merge claude/wave-b-integration`: `Already up to date.`):

```
$ nice -n 15 npm --prefix ui test -- SplashThemeMenu SettingsPane shell-accessibility
 ✓ src/shell-accessibility.test.ts (11 tests) 53ms
 ✓ src/pages/splash/SplashThemeMenu.test.tsx (9 tests) 562ms
 ✓ src/components/nexus/SettingsPane.test.tsx (20 tests) 672ms
 Test Files  3 passed (3)
      Tests  40 passed (40)
   Start at  10:51:34

$ nice -n 15 npm --prefix ui test -- SplashThemeMenu SettingsPane shell-accessibility WizardShell ContinuePage
 ✓ src/shell-accessibility.test.ts (11 tests) 57ms
 ✓ src/components/nexus/SettingsPane.test.tsx (20 tests) 685ms
 ✓ src/pages/splash/SplashThemeMenu.test.tsx (9 tests) 607ms
 ✓ src/pages/ContinuePage.test.tsx (8 tests) 830ms
 ✓ src/components/NewStoryWizard/WizardShell.theme.test.tsx (7 tests) 529ms
 ✓ src/components/NewStoryWizard/WizardShell.test.tsx (24 tests) 1134ms
 ✓ src/pages/ContinuePage.resume.test.tsx (4 tests) 3525ms
 Test Files  7 passed (7)
      Tests  83 passed (83)
   Start at  10:51:35

$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 42 passed (43)
      Tests  648 passed (648)
   Start at  10:51:40
```

In the full suite, the only failure is the `state-shades.test.ts` staleness, which is expected on the wave-B integration base. The coordinator regenerates state surfaces once on the final UI union.

```
$ nice -n 15 npm --prefix ui run check        # exit 0
> tsc && npm run check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

$ nice -n 15 npm --prefix ui run build        # exit 0
✓ 2818 modules transformed.
../dist/public/assets/index-Bjad2Pld.js                         1,775.64 kB │ gzip: 529.87 kB
✓ built in 2.77s

$ /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref claude/wave-b-integration
OK: exception disposition coverage and shrink-only baseline verified.

$ PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 7.63s
```

No Python change and no migration, so mypy, flake8 and PostgreSQL tests have nothing to run; no changed path is a `sources:` entry of a canonical document.

## Rendered Check (Lane 8025, Private `runtime.state_dir`, Production Bundle)

Rounds 2 (2026-10-09: placement and a first rejected-pick run) and 3 (2026-10-13: a second rejected-pick run and a menu timeline) served `4d8ea147`'s bundle, `index--wbtCQTL.js`. Rounds 4 and 5 (2026-10-13) served the code head's bundle, `index-Bjad2Pld.js` (`a8d45cce` and `7b66932f` build the same bundle; the only later product-file change is a comment). Round 4 repeated the placement check with a first-`Tab` probe, and round 5 repeated the rejected-pick, retry and reload run. The committed rejection screenshots and the "After" placement column are the code head's captures; the "Before" column is the base bundle, `index-C5o0njTX.js`.

- Placement: before the change, after it, and after the tab-order fix, the Home menu trigger is the single trigger at `x 28, y 28, 36x36` in Veil, Gilded and Vector, with the same wrapper style, and it is the topmost element at its center. In round 4 the first `Tab` focuses it in all three themes. A recorded pixel comparison (Pillow `ImageChops.difference`; script and output in the evidence) finds Gilded, which does not animate, identical pixel for pixel. Veil and Vector differ across the whole frame because their backgrounds animate. Inside the trigger box, 77-86 (Veil) and 200 (Vector) of 1296 pixels differ. The button has no background of its own and its glyph is drawn at 70% alpha, so the animated background shows through it; the identical DOM box shows the trigger did not move. The screenshot pairs are in the evidence file.
- Failure (round 5, code head bundle; rounds 2 and 3 logged the same): with the private state directory set to `chmod 0555`, two Gilded picks returned `PATCH /api/preferences 500` (gateway: `PermissionError: [Errno 13] Permission denied`). The item select closes the menu, and it opens again with the alert about 30 ms later, when the 500 arrives (round-3 `data-state` timeline, on `4d8ea147`'s bundle; `a8d45cce` changed only where `SplashPage` renders the menu). After each pick, the open menu showed `role="alert"` `WRITE REJECTED` / `500: Internal Server Error`, Veil stayed checked, and the preferences file hash did not change.
- Recovery: after `chmod 0755`, the same pick returned 200, the menu closed, the alert was gone, and Gilded survived a reload.
- Gateway (round 5): `PATCH /api/preferences` answered 200 (the Veil seed), 500, 500 (each with `PermissionError: [Errno 13] Permission denied: '.../scratchpad/961-HOME-r3/fix2/home/state/tmp...'`), then 200 (the retry).
- Cleanup: the gateway ran as a direct uvicorn process with `NEXUS_TEST_PROVIDER_ONLY=1` and `NEXUS_KEYRING_DISABLE=1` and `NEXUS_SLOT` unset, so the mock provider on 5102 never started. After each round the process was stopped, 8025 was free again, and `nexus down` with the same environment printed `nothing running`. No owner path and no port 8002, 8012 or 5102 was touched.

## Deferred

- The alert text from the real gateway is `500: Internal Server Error`. Mapping the route's error detail (here a `PermissionError`) into the response is server-side work for a later slice (amendment 2e).
- Residual from ruling (c): if a pick is followed within the same second by leaving Home, the rejection appears on the next Home visit, or in the wizard menu, not in Settings.
- For the coordinator to decide: a held rejection clears only after a new pick (while its save is pending), a successful save, or the Settings THEME card mounting, so a Settings visit clears only failures from before the visit. After the player has seen and closed the alert, the menu opens on it again at every later Home or wizard mount. Clearing on an explicit dismissal (Escape or an outside click; not on an item select, since Radix runs `onClick` before closing and a reset there would detach the new save) would end the repeat. That clearing was not ordered, so it is not built.
- For the coordinator to decide: a theme save rejected inside Settings opens the Home or wizard menu on the next visit there. The THEME card shows the rejection but clears only when it mounts, so the rejection is still held after the player leaves Settings, and the next Home or wizard mount opens its menu on a failure the player has already seen. Having `ThemeSection` also clear on unmount (`useEffect(() => { clearSaveError(); return clearSaveError; }, [clearSaveError])`) would close this case. The trade-off: `clearSaveError` is the mutation's `reset`, which detaches a save that is still pending, so a Settings pick followed by leaving Settings within the same second would then show its rejection nowhere. Not ordered, so not built.
- The design-sync previews of `VeilSplash`, `GildedSplash` and `VectorSplash` render those variants alone, so after the hoist they no longer show the corner menu. The `SplashPage` and `SplashThemeMenu` previews still show it. Whether to re-sync is for the owner or the coordinator.
- The wizard menu was verified by unit tests only. Opening `/new-story` in a browser reads the slot list from the save databases, and the rendered check was assigned to Home.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01FsLmRyABWHoUEXsidSRfMC
