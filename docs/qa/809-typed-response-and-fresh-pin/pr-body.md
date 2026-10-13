Refs #809. Slices 809-S3b and 809-S7a. 809-S6, 809-S7b and the owner question 809-Q1 stay open.

## Goal

- **809-S3b (Decisions 809-Q4, 809-Q5).** Type the `GET /api/settings` response with a Pydantic model and keep every non-alias field it serves. Keep the next-story model preference, and delete only the dead client plumbing.
- **809-S7a (Decision 809-Q2).** A fresh or reset slot stores no model pin (NULL). The `TEST` placeholder `global.model.default_slot_model` is retired.

## What Was Wrong

- `get_settings` (`nexus/api/settings_endpoints.py:118-119` on the base) was typed `Dict[str, Any]`, and no Pydantic model declared the response.
- The client `SettingsPayload` declared four fields that no client module reads: `apex.provider`, `wizard`, `lore.token_budget.system_prompt_tokens` and `memnon`. Its header named an Express proxy that no longer exists.
- `useSettings.ts` projected `wizard_model` into `payload.wizard` (`:36-39`), copied it into the preferences cache (`:54`) and invalidated key status on it (`:64-67`). No client caller sends `wizard_model`. The server keeps the preference (`preferences_endpoints.py:33`, `story_model.py:184-185`).
- `ModelConfig.default_slot_model` defaulted to `"TEST"` (`settings_models.py:346`), and the roster supplied it (`nexus.toml:48`). `ensure_global_variables` (`nexus/maintenance/new_story_setup.py:117`) wrote it into every new or reset slot. `start_setup` (`new_story_flow.py:148-152`) treated that value as "no pin" when there was no wizard cache, and `resolve_setup_model` repeated the rule for tests only.
- The QA kit wrote the key (`scripts/qa_shift/qa_shift.py:790`).
- The column already means "no pin" when NULL. Its comment on `NEXUS_template` says: `NULL leaves model resolution to defaults.` A read-only check shows that `save_01` and `save_02` hold NULL, `save_03`, `save_04` and the reference corpus hold `gpt-5.6-terra`, and `save_05` holds `gpt-6-astra`. No slot stores TEST.

## What Changed

Part A (809-S3b):
- `nexus/api/settings_endpoints.py`: three new models, `ModelOption`, `SettingsMeta` and `SettingsPayload`, each with `extra="forbid"`. `SettingsPayload` has one `Dict[str, Any]` field for each `Settings` section except `secrets`: the sections `Settings` requires are required here, and the rest are optional. It also carries `settings_meta`. `_build_settings_meta` returns `SettingsMeta`. `_build_payload` validates today's dict. The route declares `response_model=SettingsPayload, response_model_exclude_unset=True`, so a section that is missing from the file stays out of the JSON instead of appearing as `null`. An unknown top-level section raises. HEAD is unchanged.
- `ui/client/src/types/settings.ts`: the four unread fields and `SettingsPatch.wizard_model` are removed, the header is replaced, and `Preferences.wizard_model` is kept.
- `ui/client/src/hooks/useSettings.ts`: the `wizard` projection, the `wizard_model` cache copy and the key-status invalidation are deleted.
- `ui/client/src/components/nexus/SettingsPane.test.tsx`: fixtures follow the type change. The projection test asserts that no `wizard` key is present.

Part B (809-S7a):
- `nexus/config/settings_models.py`: the `default_slot_model` field, its selection path and its registry-check tuple are removed. The known-ID check covers `default_model` only, with the same message. A config that still names the key fails with `extra_forbidden`, and a roster `uses` that names it fails with `Unknown model use`.
- `nexus.toml`: the TEST entry's `uses` is removed (the entry stays), and the header comment now says that a new or reset slot stores no model pin.
- `nexus/maintenance/new_story_setup.py` (where 811-S3a moved the implementation): `_get_default_slot_model` is deleted. `ensure_global_variables` inserts `(TRUE, TRUE, NULL)` and logs `(no model pin)`. `scripts/new_story_setup.py` no longer re-exports the deleted function.
- `nexus/api/new_story_flow.py`: `resolve_setup_model` and the placeholder block in `start_setup` are deleted, so any non-NULL slot model is a pin. The `read_cache_raw` import is removed and the docstring is updated.
- `scripts/qa_shift/qa_shift.py`: the key write is removed. The loop that follows it already pins `wizard.default_model`.
- `docs/settings_scopes.md`: one sentence is added: "A new or reset slot stores NULL in `model`: no pin."
- `docs/decisions/0021-killed-c063.md`: `verified_commit` is moved to `f073b371`, because its declared source `qa_shift.py` changed.

Stale consumers (item 13):
- `tests/config/test_settings_models.py`: the two `default_slot_model` tests are replaced by `test_retired_default_slot_model_is_rejected`, and two key lines are dropped.
- `tests/config/test_settings_parity.py`: the ownership entry is removed.
- `tests/test_new_story_setup_config.py`: deleted.
- `tests/settings_helpers.py`: the docstring clause is removed.
- `tests/test_runtime/test_supervisor_live.py`: the assignment and its import are removed.
- `tests/test_api/test_wizard_model_resolution.py`: the `resolve_setup_model` tests are removed.
- `tests/test_qa_shift.py`: updated.
- `tests/test_golden_path_live.py` and `tests/test_orrery/test_retrograde_wizard_live.py`: comment text only. Neither live test was run.

Item 14: of every test file that initializes a slot directly, exactly one test relied on the placeholder: `tests/test_orrery/test_character_experiences_pg.py::test_real_commit_forms_verified_seeds_and_boundary_batch`. It failed with `assert 'gpt-6-astra' != 'gpt-6-astra'`. Its `_disposable_database` helper now pins TEST right after initialization, as `pin_clone` does. `tests/pg_fixtures.py` is unchanged, and no placeholder returns to product code.

New tests:
- `test_get_top_level_keys_are_pinned`
- `test_get_declares_the_typed_response`
- `test_absent_optional_section_is_omitted` (guard; the mutation run below shows it can fail)
- `test_unknown_section_fails_loudly`
- `test_fresh_slot_stores_no_model_pin`
- `test_start_setup_keeps_every_non_null_slot_pin`
- `test_retired_default_slot_model_is_rejected`
- The full-section loop in `test_get_serves_no_legacy_alias_blocks`
- The NULL-pin guard in `test_wizard_records_player_model_in_slot`
- The `test_qa_shift.py` assertions, including a `load_settings` of the generated QA config

## Test Commands and Tails

The full red, green, item 14, mutation, static and UI record is in `docs/qa/809-typed-response-and-fresh-pin/verification.md`. Excerpts:

Red, with the tests at `e0a7ad22` and the product code unchanged:
```
FAILED tests/test_api/test_settings_endpoints.py::test_get_serves_no_legacy_alias_blocks
FAILED tests/test_api/test_settings_endpoints.py::test_get_top_level_keys_are_pinned
FAILED tests/test_api/test_settings_endpoints.py::test_get_declares_the_typed_response
FAILED tests/test_api/test_settings_endpoints.py::test_unknown_section_fails_loudly
FAILED tests/test_api/test_settings_endpoints.py::test_picker_lists_every_visible_model
FAILED tests/config/test_settings_models.py::test_retired_default_slot_model_is_rejected
FAILED tests/test_qa_shift.py::test_begin_creates_archive_and_pins_every_remote_model
7 failed, 8 passed, 5 warnings in 1.17s

E               AssertionError: assert ('TEST', True) == (None, True)
E       AssertionError: assert 'TEST-B' == 'TEST'
dbname audit: owner targets: none
FAILED tests/test_new_story_setup.py::test_fresh_slot_stores_no_model_pin - A...
FAILED tests/test_api/test_wizard_model_resolution.py::test_start_setup_keeps_every_non_null_slot_pin
2 failed, 1 passed, 5 warnings in 11.37s

   × SettingsPane model IDs > projects player preferences without changing story defaults 4ms
AssertionError: expected { ui: { theme: 'vector', …(1) }, …(3) } to not have property "wizard"
```

Green, focused PostgreSQL proof:
```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py tests/test_api/test_wizard_model_resolution.py tests/test_api/test_slot_settings.py tests/test_qa_shift.py tests/test_runtime/test_supervisor_live.py tests/test_postgres_tools.py tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner server: local:5432
dbname audit: owner names admitted on registered clusters: save_04@local:63176 (psycopg2), save_04@local:63180 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
221 passed, 2 skipped, 13 warnings in 204.34s (0:03:24)
```
The 2 skips are the `requires_corpus` card-exposure tests (`NEXUS_RUN_CORPUS` unset).

Item 14 PostgreSQL runs, covering every file that initializes a slot directly:
- `test_character_experiences_pg.py` after the pin: `28 passed`.
- The other candidate files and the remaining direct initializers: `82 passed` (with the one failure fixed above), `47 passed`, `23 passed`, and `198 passed` with one failure that is also on the base.
- Every run printed `dbname audit: owner targets: none` and `secret-store guard: active; nexus-api: denied`.

Offline:
```
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py tests/config tests/test_api/test_settings_endpoints.py tests/test_api/test_route_capabilities.py
300 passed, 1 skipped, 7 warnings in 30.62s
$ PYTHONPATH=$PWD $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
5 failed, 3189 passed, 672 skipped, 8 warnings in 648.91s (0:10:48)
$ PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery
11 failed, 1895 passed, 1518 skipped, 7 warnings in 47.94s
```
All 16 offline failures, and the `test_script_wrappers` failure, also fail on a `claude/wave-b-integration` export, and none of them is in a file this branch changes. The verification file lists their ids and reasons. They include:
- `test_assembled_writer_and_gaia_requests_are_unchanged` and `test_gaia_prompt_is_concise_and_self_contained`
- `test_no_tracked_file_binds_a_wrapper_module`: from `test_place_point_required_pg.py:11` and `test_init_plan_pg.py:23`
- `test_wire_schema_size_and_description_budget`
- `test_transition_rejects_missing_diegetic_timestamp`
- Two `test_wizard_confirmation` cases
- `test_epistemics_rejects_event_type_without_birth_role_policy`
- Eight `test_worker.py` cases

Mutation run, with `response_model_exclude_unset=True` removed and then restored:
```
E       AssertionError: assert 'api' not in {'apex': {'anthropic_storyteller_transport': 'prompted', ...}, ...}
FAILED tests/test_api/test_settings_endpoints.py::test_absent_optional_section_is_omitted
1 failed, 5 warnings in 0.29s
```

Static checks:
- Black: 18 files unchanged.
- flake8: 22 on the branch against 24 on the base, with none on a changed line.
- mypy `--explicit-package-bases`: the per-file counts are equal on the branch and on the base for all 18 files.
- `check_exception_dispositions.py --baseline-base-ref origin/main`: `OK`.

UI:
- `npm --prefix ui ci`, `run check` and `run build` exited 0.
- `npm --prefix ui test`: `Test Files 1 failed | 40 passed (41)`, `Tests 632 passed (632)`. The one failure is `state-shades.test.ts`, "Stale browser-resolved state surfaces", which is expected on this base. `resolve-state-surfaces` was not run, by coordinator instruction.

## Deferred

- The whole-tree PostgreSQL gate was not run, because of the machine-load rule. The focused set plus every direct slot initializer stands in for it, and the coordinator runs the whole tree at landing.
- The state-surface receipt is regenerated once by the coordinator on the final UI union.
- Out of scope by name: 809-S6, 809-S7b (the TEST registry entry stays), 809-Q1, 809-Q7 to 809-Q10, a UI control for the next-story model, and `tests/pg_fixtures.py`.

## Landing Notes

- There is no migration and nothing is applied to the fleet. Existing slot pins are not touched.
- Product code and `nexus.toml` change, so the gateway needs a restart when the services run again.
- The client changes, so the UI bundle is rebuilt at landing.
- The next QA-kit run generates its config without `default_slot_model`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01FsLmRyABWHoUEXsidSRfMC
