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
- `SplashPage` renders exactly one `SplashThemeMenu`, outside the variant swap, and the three variants no longer render it. The trigger's box is `x 28, y 28, 36x36` in every theme, both before and after the change.
- `SplashThemeMenu` now controls its own open state and shows `data-testid="splash-theme-save-error"` below the themes. It no longer clears the error on unmount; the Settings THEME card still clears it on mount.
- `WizardShell` (Part B) controls its menu's open state and opens on a rejection. It renders `data-testid="wizard-theme-save-error"` after `<ThemeMenu />`. `ThemeMenu.tsx` is unchanged, because the design-sync preview renders it with no props.
- Tests:
  - `SplashThemeMenu.test.tsx` now renders `SplashPage` with the real `ThemeProvider` and query client. It covers an HTTP 500, a network `TypeError`, a second rejection, a retry after each kind of failure, a held rejection on a later Home visit with Settings staying clean, a rejection that completes while the player is away, and the success path.
  - The new `WizardShell.theme.test.tsx` mirrors these tests for the wizard.
  - The `useTheme` stubs in `WizardShell.test.tsx` and `ContinuePage.resume.test.tsx` now return `saveError: null`.
- Evidence is in `docs/qa/961-home-theme-save-error/verification.md`, with screenshots.

## Tests

The red runs came before the product change. Each one-test pass is the success path, which already holds on the base.
- `SplashThemeMenu` against the base splash files: `Tests  7 failed | 1 passed (8)`.
- `SplashThemeMenu` against the first-round, unhoisted menu (`8451c2cb`): the same 7 tests fail, each with `Unable to find an element by: [data-testid="splash-theme-save-error"]`.
- `WizardShell.theme` against the base wizard: `Tests  5 failed | 1 passed (6)`.

Green runs on the code head (`4d8ea147`), rerun on 2026-10-13 after the resume (`git merge claude/wave-b-integration`: `Already up to date.`):

```
$ nice -n 15 npm --prefix ui test -- SplashThemeMenu SettingsPane shell-accessibility
 ✓ src/shell-accessibility.test.ts (11 tests) 67ms
 ✓ src/components/nexus/SettingsPane.test.tsx (20 tests) 656ms
 ✓ src/pages/splash/SplashThemeMenu.test.tsx (8 tests) 516ms
 Test Files  3 passed (3)
      Tests  39 passed (39)
   Start at  10:24:44

$ nice -n 15 npm --prefix ui test -- SplashThemeMenu SettingsPane shell-accessibility WizardShell ContinuePage
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

$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 42 passed (43)
      Tests  646 passed (646)
   Start at  10:24:55
```

In the full suite, the only failure is the `state-shades.test.ts` staleness, which is expected on the wave-B integration base. The coordinator regenerates state surfaces once on the final UI union.

```
$ nice -n 15 npm --prefix ui run check        # exit 0
> tsc && npm run check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

$ nice -n 15 npm --prefix ui run build        # exit 0
✓ 2818 modules transformed.
../dist/public/assets/index--wbtCQTL.js                         1,775.64 kB │ gzip: 529.87 kB
✓ built in 2.71s

$ /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref claude/wave-b-integration
OK: exception disposition coverage and shrink-only baseline verified.

$ PYTHONPATH=$PWD nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
66 passed, 5 warnings in 8.00s
```

No Python change and no migration, so mypy, flake8 and PostgreSQL tests have nothing to run; no changed path is a `sources:` entry of a canonical document.

## Rendered Check (Lane 8025, Private `runtime.state_dir`, Production Bundle)

Run on 2026-10-09 (round 2: placement and a first rejected-pick run) and again on 2026-10-13 (round 3: the rejected-pick run, the screenshots in the evidence, and a menu timeline). Both rounds served the same bundle, `index--wbtCQTL.js`.


- Placement: before and after the change, the Home menu trigger is the single trigger at `x 28, y 28, 36x36` in Veil, Gilded and Vector, and it is the topmost element at its center. Gilded's 1200x900 captures are identical pixel for pixel. Veil and Vector differ only in their animated background strands. The screenshot pairs are in the evidence file.
- Failure: with the private state directory set to `chmod 0555`, two Gilded picks returned `PATCH /api/preferences 500` (gateway: `PermissionError: [Errno 13] Permission denied`). The item select closes the menu, and it opens again with the alert about 30 ms later, when the 500 arrives (round-3 `data-state` timeline). After each pick, the open menu showed `role="alert"` `WRITE REJECTED` / `500: Internal Server Error`, Veil stayed checked, and the preferences file hash did not change.
- Recovery: after `chmod 0755`, the same pick returned 200, the menu closed, the alert was gone, and Gilded survived a reload.
- Cleanup: the gateway ran as a direct uvicorn process with `NEXUS_TEST_PROVIDER_ONLY=1` and `NEXUS_KEYRING_DISABLE=1`, so the mock provider on 5102 never started. The process was stopped afterwards, 8025 was free again, and `nexus down` with the same environment printed `nothing running`. No owner path and no port 8002, 8012 or 5102 was touched.

## Deferred

- The alert text from the real gateway is `500: Internal Server Error`. Mapping the route's error detail (here a `PermissionError`) into the response is server-side work for a later slice (amendment 2e).
- Residual from ruling (c): if a pick is followed within the same second by leaving Home, the rejection appears on the next Home visit, or in the wizard menu, not in Settings.
- For the coordinator to decide: a held rejection clears only after a successful save or a Settings visit. After the player has seen and closed the alert, the menu opens on it again at every later Home or wizard mount. Clearing on an explicit dismissal (Escape or an outside click; not on an item select, since Radix runs `onClick` before closing and a reset there would detach the new save) would end the repeat. That clearing was not ordered, so it is not built.
- The design-sync previews of `VeilSplash`, `GildedSplash` and `VectorSplash` render those variants alone, so after the hoist they no longer show the corner menu. The `SplashPage` and `SplashThemeMenu` previews still show it. Whether to re-sync is for the owner or the coordinator.
- The wizard menu was verified by unit tests only. Opening `/new-story` in a browser reads the slot list from the save databases, and the rendered check was assigned to Home.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01FsLmRyABWHoUEXsidSRfMC
