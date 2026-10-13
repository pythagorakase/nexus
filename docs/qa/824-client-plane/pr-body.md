## Goal

Refs #824. Two slices under one proof: 824-S1 makes the IRIS client aware of the plane that serves it (Decisions 824-Q3, 824-Q4 client half, 824-Q7), and 824-S5 retires the no-op `slot/select` route (Decision 824-Q8). On the player plane the client now sends no operator request and renders no operator-backed control. Theme and fonts come from the player route `GET /api/preferences`. The projections still enforce the planes; the client's plane only shapes the interface.

Base: `claude/wave-b-integration` at `7eb9a10c` (merge base with `origin/main`: `f073b371`). No migration. No paid call. No listener or tunnel change.

## What Is Wrong Today (Lines on the Base)

- `/health` returns `{"status": "healthy", "service": "narrative_api"}` (`nexus/api/narrative.py:823-826`), so the client cannot learn its plane.
- The connectivity probe sends `HEAD /api/settings` (`ui/client/src/hooks/useNarrativeEngine.ts:404`, every `CONNECTIVITY_POLL_MS` `:38`), an operator route (`nexus/api/route_capabilities.py:152`): on the player plane it answers 404 and the client shows OFFLINE.
- `ThemeProvider` (`ThemeContext.tsx:41-43`) and `FontProvider` (`FontContext.tsx:61-65`) read `useSettingsQuery` (`useSettings.ts:10-11`), which needs the operator `GET /api/settings` (`route_capabilities.py:153`), although `GET /api/preferences` is a player route (`:155`). On the player plane a saved theme and saved fonts are never applied.
- Operator requests fire on any plane: the memory meter (`TopBar.tsx:198-200`, rendered at `:300`), NexusLayout's `/api/settings` (`NexusLayout.tsx:69`), the backstage gate (`DeveloperModeContext.tsx:22-25`), the settings pane's story settings and secrets (`SettingsPane.tsx:774`, `:465`).
- Operator-backed controls render on any plane: MODEL, API KEYS, CONTEXT LENGTH (`SettingsPane.tsx:869-875`), portrait upload and set-main (`CharactersPane.tsx:68-80`, `:169`; registry `route_capabilities.py:220-224`), CLEAR (`SlotSelector.tsx:87`, `:254`; `setup/reset` `route_capabilities.py:186`), and the OVERWRITE dialog for an occupied slot (`SlotSelector.tsx:118`, `:344`).
- `POST /api/story/new/slot/select` (`setup_endpoints.py:218-229`) calls `activate_slot` (`new_story_flow.py:1033`), whose two callees are no-ops (`save_slots.py:236-247`, `:287-310`). Its only client was `LocationPhase.tsx:49-52`, which no app module mounts.

## What Changed

### 824-S1: Client Plane Awareness

- `route_capabilities.py`: `set_serving_plane(app, plane)` and `serving_plane(app)`, which raises `RouteCapabilityError` when an app declares no plane (no default). `_build_projection` declares each projection's plane. `narrative.py` declares the unprojected gateway `operator` after `require_classified(app)`, and `health_check(request)` returns `"plane": serving_plane(request.app)`, so one shared route reports each projection's own plane.
- `ui/client/src/hooks/usePlane.ts` (new): `Plane`, `HealthPayload`, `HEALTH_QUERY_KEY`, `usePlane()`. An unknown plane counts as not operator.
- `useNarrativeEngine.ts`: the probe reads `GET /health`, caches the payload under `HEALTH_QUERY_KEY` when `res.ok`, and sets reachability from `res.ok` as before; a failed probe keeps the cached plane. `ui/vite.config.ts` proxies `/health`. The `HEAD /api/settings` handler stays; only its docstring changes.
- `useSettings.ts`: `usePreferencesQuery()`; `useSettingsQuery` fetches the operator defaults only on the operator plane and keeps the merge. Theme and Font providers read `usePreferencesQuery()`.
- Player plane withholds: the memory meter (`TopBar.tsx`), NexusLayout's `/api/settings` read, the backstage gate query (`gateOpen` stays false), the settings pane's model, API keys, context length and advanced sections (the pane renders theme, typography and app icon from `SettingsConsole settings={null}`), portrait upload (`CharactersPane.tsx`, upload region only), CLEAR (`SlotSelector.tsx`). An occupied slot on the player plane opens no overwrite dialog and starts nothing, and its card drops the pointer cursor and hover brightening; RESUME and empty slots behave as before.
- `useLocalModels.ts` and `narrative-api.ts` need no change: after these edits their operator calls run only from operator-plane components.
- Harness stubs: `ui/.design-sync/ds-provider.tsx` answers `/health` (operator plane) and `/api/preferences`; `ui/.design-sync/NOTES.md` names both; `ui/scripts/state-surfaces/fixture.tsx` answers `GET /health`, seeds `['/health']` and a full `['/api/preferences']`.
- `docs/runtime.md`: the planes paragraph states what `/health` reports and what the player-plane client withholds; the dev-server proxy list names `/health`.

### 824-S5: Retire the No-Op slot/select

- Deleted `select_slot_endpoint`, `SelectSlotRequest`, `activate_slot`, the `all_slots` import in `new_story_flow.py`, the registry entry, and the `activate_slot` entry in `config/exception_disposition_baseline.json` (the baseline only shrinks).
- `LocationPhase.tsx`: the fetch and `useMutation` are gone; ENTER SIMULATION calls `onNext(locationData)`. `LocationPhaseProps` is unchanged, so the design-sync card, `nexus-ui.ts` and `previews/LocationPhase.tsx` are byte-identical.
- `docs/runtime.md`: `slot/select` leaves the Operator row.

### Tests

- Python (`tests/test_api/test_route_capabilities.py`, real dispatch through `TestClient`): `test_health_reports_the_serving_plane` (player, operator and unprojected, both static branches), `test_serving_plane_requires_a_declaration`, `test_retired_slot_select_is_not_served`; `slot/select` removed from `OPERATOR_REQUESTS` and from `tests/test_api/test_slot_mutation_guard.py`.
- Vitest: `PreferenceProviders.test.tsx` (applies saved theme and fonts from preferences alone), and player-plane cases in `SettingsPane.test.tsx`, `TopBar.test.tsx`, `CharactersPane.test.tsx`, `SlotSelector.test.tsx`, `NexusLayout.test.tsx`, `useNarrativeEngine.recovery.test.tsx`. Suites that render operator controls seed the operator plane. The live-engine stubs in `NexusLayout.announcer.test.tsx` and `NarrativePane.regenerate.test.tsx` answer `GET /health` with a JSON body (they answered the retired `HEAD /api/settings` probe), and every suite that mounts `ThemeProvider` seeds `/api/preferences` in the `Preferences` shape, the key `ThemeProvider` reads (the retired `/api/settings` theme seeds are gone; an `/api/settings` seed stays only where an operator surface reads it: StateGlyphs' MemoryMeter knobs and NexusLayout's backstage knobs in the announcer suite). The `/health` plane test builds both projections before its first request, so a plane kept in one shared place fails it.

## Proof

The full record, with every tail, both red runs and the three browser transcripts, is in `docs/qa/824-client-plane/verification.md`.

Red runs (product hunks reverted with `git checkout claude/wave-b-integration -- <files>`, restored with `git checkout HEAD -- <files>`):

```
tests/test_api/test_route_capabilities.py::test_health_reports_the_serving_plane
E         Right contains 1 more item:
E         {'plane': 'player'}
2 failed, 7 warnings in 0.75s

client/src/contexts/PreferenceProviders.test.tsx
 FAIL  src/contexts/PreferenceProviders.test.tsx > preference providers > applies saved theme and fonts from preferences alone
Error: expect(element).toHaveClass("theme-gilded")

Expected the element to have class:
  theme-gilded
Received:
  dark
 Test Files  1 failed (1)
      Tests  1 failed (1)
```

PostgreSQL (`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset):

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_api/test_route_capabilities.py tests/test_api/test_slot_mutation_guard.py tests/test_api/test_cors.py tests/test_api/test_wizard_resume.py tests/test_api/test_slot_settings.py tests/test_new_story_setup.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
156 passed, 2 skipped, 7 warnings in 129.21s (0:02:09)
```

The two skips are the `requires_corpus` case of `test_card_identity.py`.

The `/health` plane test builds both projections before its first request. With a pytest plugin that keeps the plane in one module global, it fails on the player case (`{'plane': 'operator'} != {'plane': 'player'}`, `2 failed`), where the earlier request-per-build structure passed (`2 passed`). After that change, `tests/test_api/test_route_capabilities.py` under PostgreSQL: `37 passed`, `dbname audit: owner targets: none`.

Offline (`tests --ignore=tests/test_api --ignore=tests/test_orrery` in three sequential pieces, because one run passes the ten-minute command limit under this machine's load). The pieces: `tests/config tests/fixtures tests/proofs tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util`; `$(ls tests/test_*.py | head -78)`; and `$(ls tests/test_*.py | tail -66) tests/live_seed_schema_test.py tests/live_set_designer_test.py`. The two `*_test.py` modules are collected by pytest's default `python_files`; the first second-half run missed them, so the second half was re-run with them (both skip at module level offline). Together the pieces cover the same files as the order's command. Both file lists are in `verification.md`.

```
subdirectories:          2 failed, 1043 passed, 89 skipped in 161.26s
top-level, first half:   1088 passed, 299 skipped in 404.98s
top-level, second half:  3 failed, 1061 passed, 283 skipped in 97.87s   (re-run with the two *_test.py modules)
tests/test_api:          2 failed, 544 passed, 330 skipped in 34.47s
tests/test_orrery:       9 failed, 1349 passed, 1187 skipped in 14.07s
tests/test_reachability.py tests/test_doc_front_matter.py: 120 passed in 19.57s
```

All 16 failures are in files this branch does not change, and each fails the same way on `claude/wave-b-integration` (checked from a `git archive` export of the base): `test_assembled_prompt_fingerprint` (Gaia digest), `test_two_pass_pipeline::test_gaia_prompt_is_concise_and_self_contained` (732 words), `test_skald_wire::test_wire_schema_size_and_description_budget` (`NewEntityDeclaration.coordinates`), `test_wizard_agent::test_transition_rejects_missing_diegetic_timestamp` and two `test_wizard_confirmation` cases (unmarked `psycopg2.connect`), eight `test_orrery/test_worker.py` cases (`milestone_magnitude` validation) and `test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy`, and `test_script_wrappers::test_no_tracked_file_binds_a_wrapper_module` (flags `tests/test_orrery/test_place_point_required_pg.py:11` and one other base file). Reported for triage, not fixed.

UI:

```
$ npm --prefix ui run check          # tsc && tsc -p .design-sync/tsconfig.previews.json: exit 0
$ npm --prefix ui test
 Test Files  1 failed | 41 passed (42)
      Tests  639 passed (639)
$ npm --prefix ui run build          # exit 0
$ (cd ui && node .design-sync/build.mjs)
[build] dist/index.js + style.css + declarations ready (brand font urls rewritten)
$ git diff --name-only claude/wave-b-integration...HEAD -- ui/.design-sync
ui/.design-sync/NOTES.md
ui/.design-sync/ds-provider.tsx
```

The one failing Vitest file is `src/state-shades.test.ts` ("Stale browser-resolved state surfaces"), expected on this base; the coordinator regenerates the state surfaces once on the final UI union.

Browser proof (scratch uvicorn, one projection per process, built `ui/dist`, Playwright with a fresh context; server env `PYTHONPATH`, `NEXUS_RUNTIME_CONFIG=<scratch nexus.toml with an absolute state_dir>`, `NEXUS_KEYRING_DISABLE=1`, plus `NEXUS_TEST_PROVIDER_ONLY=1` and read-only `PGOPTIONS` for safety):

```
RED, cut point 7eb9a10c, player on 8023
patch_preferences_200: false
html_has_theme_gilded: false
preferences_toml_theme_gilded: false
no_operator_request: false          # GET/HEAD /api/settings, /api/local-models/status, /api/dev/backstage/health
api_and_health_below_400: false     # each of those answered 404
RESULT: FAIL

GREEN, final tree, player on 8023
patch_preferences_200: true
html_has_theme_gilded: true
preferences_toml_theme_gilded: true
no_operator_request: true
api_and_health_below_400: true
RESULT: PASS

GREEN, final tree, operator on 8024
set_keys_renders: true
get_api_settings_requested: true
get_local_models_status_requested: true
RESULT: PASS
```

Static checks on the changed Python files: Black clean; flake8 and `mypy --explicit-package-bases` show no new diagnostic against the base versions (each removes the diagnostics that lived in the deleted `activate_slot` and its imports). `scripts/check_exception_dispositions.py --baseline-base-ref origin/main`: `OK: exception disposition coverage and shrink-only baseline verified.`

Document freshness: `narrative.py` and `useNarrativeEngine.ts` are declared sources of `AGENTS.md` and `docs/turn_flow_sequence.md`. Both documents were re-read and stay true (`turn_flow_sequence.md:62-63`: OFFLINE reflects gateway reachability alone). Three canonical decision records also declare changed files: `docs/decisions/0008-the-story-clock-in-chrome.md` (`TopBar.tsx`), `docs/decisions/0051-time-lens.md` and `docs/decisions/0054-responsive-shell.md` (`NexusLayout.tsx`); all three were re-read and stay true (the branch touches neither the story clock, the time lens nor the bottom rail). All five already carry `verified_commit` `f073b371`, the merge base with `origin/main`, so no stamp moves; `tests/test_doc_front_matter.py` passes.

## Deferred and Out of Scope

- The server half of Decision 824-Q4 (a player `setup/start` limited to empty slots, without overwrite or repin), listener binding, the launcher, the second listener's lane, the tunnel move, desktop routing, per-plane CORS and the remote CLI profile (824-Q5, Q6, Q9), and the owner questions 824-Q1 and 824-Q2.
- No operator route moves to the player plane (Decision 824-Q3); the registry changes only by the deleted `slot/select` entry.
- State-surface regeneration: owed once on the final UI union (coordinator).

## Landing Notes

- No migration; no fleet application.
- A gateway restart is owed when the services run again (`narrative.py`, `route_capabilities.py`, `settings_endpoints.py`, `setup_endpoints.py`, `new_story_flow.py`, `narrative_schemas.py` change).
- A UI rebuild (`npm --prefix ui run build`) is owed, together with the gateway restart or after it, never while an older gateway runs: an old gateway's `/health` has no `plane`, so the new bundle would hide every operator control and keep the settings pane on RECEIVING.
- Design-sync: no card should change; a re-upload is the coordinator's call.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01FsLmRyABWHoUEXsidSRfMC
