# 809-S3b and 809-S7a Verification: Typed Settings Response, Fresh Slots Store No Pin

Order: `temp/orders_2026_10_07/809-S3b.md` (with both coordinator amendments). Issue #809 (Decisions 809-Q2, 809-Q4, 809-Q5). Branch `claude/809-typed-response-and-fresh-pin`, cut from `claude/wave-b-integration` at `7eb9a10c`; merge base with `origin/main` is `f073b371`. No migration, no paid call, no gateway lane, no write to any `save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07`.

## Resumed on 2026-10-13

The first builder stopped at the usage limit on 2026-10-09 03:16. `git log --stat claude/wave-b-integration..HEAD` and `git status --short` at resume:

| Commit | Content | Order items |
| --- | --- | --- |
| `e0a7ad22` | Failing tests first: `test_settings_endpoints.py` (pinned keys, typed OpenAPI response, absent optional section, unknown section, full-section loop, picker via `.settings_meta`), `test_retired_default_slot_model_is_rejected`, `test_fresh_slot_stores_no_model_pin`, `test_start_setup_keeps_every_non_null_slot_pin`, the NULL-pin guard in `test_wizard_records_player_model_in_slot`, `test_qa_shift.py` edits, the `SettingsPane.test.tsx` fixture and projection edits | Tests section; items 6 and the `test_qa_shift.py` part of 13 |
| `93b9abd4` | Implementation: response models and builders and route (1-3), client type (4), hook (5), setting retirement (7), `nexus.toml` (8), setup script in `nexus/maintenance/new_story_setup.py` plus the wrapper re-export in `scripts/new_story_setup.py` (9), `new_story_flow.py` (10), QA kit (11), `docs/settings_scopes.md` (12), stale consumers (13: `test_settings_models.py`, `test_settings_parity.py`, deleted `test_new_story_setup_config.py`, `settings_helpers.py`, `test_supervisor_live.py`, `test_wizard_model_resolution.py`, the two live-test comments), and the `docs/decisions/0021-killed-c063.md` freshness stamp (its declared source `scripts/qa_shift/qa_shift.py` changed) | 1-13, part of 15 |
| uncommitted | `tests/test_api/test_wizard_model_resolution.py`: `doc = tomlkit.parse(...)` became `doc: Any = tomlkit.parse(...)` so mypy accepts the indexed assignments in the new test | finished and committed as `074cb47b` |

Work done on resume: committed the edit (`074cb47b`); the red, green and mutation runs; item 14 (`80c4321a`); the static, lint and UI checks; this file and `pr-body.md`. Every item was re-read against the order; no deviation was found in the resumed commits.

Item 3 of the 2026-10-09 amendment: the setup-script implementation now lives in `nexus/maintenance/new_story_setup.py` (811-S3a); `scripts/new_story_setup.py` is a thin wrapper whose re-export of `_get_default_slot_model` was removed with the function.

## Cited Lines, Verified on `claude/wave-b-integration` (7eb9a10c)

The order's line numbers came from `364fef4b`; these are the base locations.

- `nexus/api/settings_endpoints.py:56` `_build_settings_meta(...) -> Dict[str, Any]`; `:94` `_build_payload(...) -> Dict[str, Any]`; `:118-119` `@router.get("")` / `async def get_settings() -> Dict[str, Any]`. No Pydantic model declared the response.
- `ui/client/src/types/settings.ts:3` names the retired Express proxy; `:56` `apex.provider`; `:58` `wizard`; `:62` `lore.token_budget.system_prompt_tokens`; `:65` `memnon`; `:94` `SettingsPatch.wizard_model`; `:88` `Preferences.wizard_model` (kept).
- `ui/client/src/hooks/useSettings.ts:36-39` the `wizard` projection; `:54` the `wizard_model` cache copy; `:64-67` the `wizard_model` key-status invalidation. `SECRETS_QUERY_KEY` stays imported: `useStorySettingsMutation` (`:90` on the base, `:79` on the branch) still uses it.
- `nexus/api/preferences_endpoints.py:33` accepts `wizard_model`; `nexus/config/story_model.py:184-185` reads it for the wizard seat (unchanged, Decision 809-Q5).
- `nexus/config/settings_models.py:35` `MODEL_SELECTION_PATHS` entry; `:346` the field (default `"TEST"`); `:373` the known-ID loop; `:4514` the registry-check tuple.
- `nexus.toml:14` "TEST supplies the default for new/reset save slots."; `:48` the TEST entry's `uses = ["global.model.default_slot_model"]`.
- `nexus/maintenance/new_story_setup.py:107-114` `_get_default_slot_model`; `:117-119` `ensure_global_variables` reads it; called at `:362` (initialization) and `:658` (post-clone cleanup).
- `nexus/api/new_story_flow.py:30` `read_cache_raw` import; `:97` `resolve_setup_model`; `:148-152` the placeholder block in `start_setup`.
- `scripts/qa_shift/qa_shift.py:790` `model["default_slot_model"] = config.target_model`.
- `tests/pg_fixtures.py:236` `story_pin: str | None = "TEST"` (unchanged; out of scope).

## Read-Only Fleet Listing

`PGOPTIONS='-c default_transaction_read_only=on' psql -X -d <db> -Atc "SELECT coalesce(model,'<NULL>') FROM global_variables"`, 2026-10-13:

```
NEXUS_template: (rows: 0)
save_01: <NULL> (rows: 1)
save_02: <NULL> (rows: 1)
save_03: gpt-5.6-terra (rows: 1)
save_04: gpt-5.6-terra (rows: 1)
save_05: gpt-6-astra (rows: 1)
ref_codex_bakeoff_2026_07: gpt-5.6-terra (rows: 1)
```

Column comment on `NEXUS_template`: `Per-story Skald model pin read through StorySettings; NULL leaves model resolution to defaults.` No slot stores TEST; no existing pin is touched.

## No Remaining Reader

`git grep -n -E 'default_slot_model|resolve_setup_model|_get_default_slot_model' -- . ':!docs/qa'` at `80c4321a`:

```
tests/config/test_settings_models.py:472:def test_retired_default_slot_model_is_rejected():
tests/config/test_settings_models.py:475:    raw["global"]["model"]["default_slot_model"] = "TEST"
tests/config/test_settings_models.py:482:    test_entry["uses"] = ["global.model.default_slot_model"]
tests/config/test_settings_models.py:484:        ValidationError, match="Unknown model use 'global.model.default_slot_model'"
tests/test_qa_shift.py:304:    assert "default_slot_model" not in model
```

Only the two tests that assert the retirement remain.

## Item 14: Tests That Initialize a Slot Directly

Every test file that calls `initialize_slot_database`, `ensure_global_variables` or `_post_clone_cleanup`, or drives slot creation through the setup module, ran under PostgreSQL:

- Failed and fixed: `tests/test_orrery/test_character_experiences_pg.py::test_real_commit_forms_verified_seeds_and_boundary_batch` (`assert 'gpt-6-astra' != 'gpt-6-astra'`: the job's story-follow model now equals `apex.model` under the NULL pin). `_disposable_database` now pins TEST right after initialization with `write_story_settings(cur, StorySettings(skald_model="TEST", gaia_model=None))`, as `pin_clone` does (`80c4321a`). The file then passed 28/28.
- Passed unchanged: `tests/test_orrery/test_recall_disclosure_pg.py`, `tests/test_orrery/test_acquisition_scan_pg.py`, `tests/test_orrery/test_experience_enqueue_gin_pg.py`, `tests/test_player_identity_consumers_pg.py`, `tests/test_record_revelation_cli_pg.py`, `tests/test_commit_choice_presence_pg.py`, `tests/test_wizard_opening_presence_pg.py`, `tests/test_orrery/test_geo_reference_pg.py`, `tests/test_story_identity_pg.py`, `tests/test_new_story_setup.py`, `tests/test_postgres_tools.py`, `tests/test_connection_lifecycle.py`, `tests/test_rebuild_memory_idf_pg.py`, `tests/test_schema_documentation_pg.py`, `tests/test_slot_operations_pg.py`, `tests/test_slot_operations_journal.py`, `tests/test_database_contract.py`, `tests/test_slot_routed_entrypoints.py`, `tests/test_scheduler_helpers_routing.py`, `tests/test_schema_ownership.py`, `tests/test_new_story_cli.py`, `tests/test_api/test_conversations.py`, `tests/test_api/test_wizard_messages_migration_pg.py`, `tests/test_api/test_wizard_model_switch.py`, `tests/test_live_gate_clones_pg.py`.
- Not run (live, paid): `tests/test_golden_path_live.py`, `tests/test_orrery/test_retrograde_wizard_live.py`, `tests/test_issue_601_wizard_live.py` (comment edits only in the first two).

The whole-tree PostgreSQL gate (`tests --ignore=...`, `tests/test_api`, `tests/test_orrery`) was not run: the common rules' machine-load gate (added 2026-10-07) forbids it and replaces it with the focused set plus `test_card_identity.py` and `test_connection_lifecycle.py`; the list above extends that set to every direct slot initializer. The coordinator runs the whole-tree gate at landing.

## Red Run (Tests at `e0a7ad22`, Product Code Unchanged)

Run from a `git archive e0a7ad22` export under the session scratchpad (`809-S3b-resume/red`), import path proven to that tree.

Offline:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api/test_settings_endpoints.py tests/config/test_settings_models.py::test_retired_default_slot_model_is_rejected "tests/test_qa_shift.py::test_begin_creates_archive_and_pins_every_remote_model" tests/test_qa_shift.py::test_every_tracked_model_route_is_pinned
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
=========================== short test summary info ============================
FAILED tests/test_api/test_settings_endpoints.py::test_get_serves_no_legacy_alias_blocks
FAILED tests/test_api/test_settings_endpoints.py::test_get_top_level_keys_are_pinned
FAILED tests/test_api/test_settings_endpoints.py::test_get_declares_the_typed_response
FAILED tests/test_api/test_settings_endpoints.py::test_unknown_section_fails_loudly
FAILED tests/test_api/test_settings_endpoints.py::test_picker_lists_every_visible_model
FAILED tests/config/test_settings_models.py::test_retired_default_slot_model_is_rejected
FAILED tests/test_qa_shift.py::test_begin_creates_archive_and_pins_every_remote_model
7 failed, 8 passed, 5 warnings in 1.17s
```

Failure reasons, in order: `'dict' object has no attribute 'model_dump'`; `ImportError: cannot import name 'SettingsPayload'`; `KeyError: '$ref'`; `DID NOT RAISE ValidationError`; `'dict' object has no attribute 'settings_meta'`; `DID NOT RAISE ValidationError`; `assert 'default_slot_model' not in {... 'default_slot_model': 'gpt-5.6-terra' ...}`.

Passing on the base, as the order expects or as noted: `test_absent_optional_section_is_omitted` (guard); `test_every_tracked_model_route_is_pinned` (an edited existing test, not a new one: on the base the kit's `default_slot_model` key is legal, so `load_settings(path)` loads; its teeth exist only once the key is retired, and the kit-writes-the-key regression fails `test_begin_creates_archive_and_pins_every_remote_model` above). The other passes are the unchanged HEAD and read-only tests.

PostgreSQL:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_new_story_setup.py::test_fresh_slot_stores_no_model_pin tests/test_api/test_wizard_model_resolution.py::test_start_setup_keeps_every_non_null_slot_pin tests/test_api/test_slot_settings.py::test_wizard_records_player_model_in_slot
E               AssertionError: assert ('TEST', True) == (None, True)
E       AssertionError: assert 'TEST-B' == 'TEST'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 5 targets: postgres, qa640_809_fresh_pin_*, qa640_810_template_*, qa640_offline_gate_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_new_story_setup.py::test_fresh_slot_stores_no_model_pin - A...
FAILED tests/test_api/test_wizard_model_resolution.py::test_start_setup_keeps_every_non_null_slot_pin
2 failed, 1 passed, 5 warnings in 11.37s
```

`test_wizard_records_player_model_in_slot` (the NULL-pin guard) passes on the base, as the order expects.

UI (base `useSettings.ts` restored into the worktree for one run, then `git checkout` back):

```
$ (cd ui && nice -n 15 npx vitest run client/src/components/nexus/SettingsPane.test.tsx -t "projects player preferences")
   × SettingsPane model IDs > projects player preferences without changing story defaults 4ms
AssertionError: expected { ui: { theme: 'vector', …(1) }, …(3) } to not have property "wizard"
    509|     expect(patched).not.toHaveProperty("wizard");
      Tests  1 failed | 19 skipped (20)
```

## Green Run

Load gate: each PostgreSQL run waited in `until [ "$(sysctl -n vm.loadavg | awk '{print int($2)}')" -lt 24 ]; do sleep 30; done`. The one-minute load read 25.11 before the focused run, 31.81 before the experiences rerun, 26.24 before the extended set and 38.70 before the wizard set; each wait ended within about three minutes.

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py tests/test_api/test_wizard_model_resolution.py tests/test_api/test_slot_settings.py tests/test_qa_shift.py tests/test_runtime/test_supervisor_live.py tests/test_postgres_tools.py tests/test_owner_target_guard.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 45 targets: nexus_m10_fresh_test_55811, nexus_m10_template_test_55811, postgres, qa640_759_measure_*, qa640_778s4a_tests_* x6, qa640_778s6a_family_* x9, qa640_809_fresh_pin_*, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_816_lifecycle_test_provider, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_885_ren_replay_* x4, qa640_offline_gate_* x8, qa885_supervisor_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:63176 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:63180 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:63176 (psycopg2), save_04@local:63180 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
221 passed, 2 skipped, 13 warnings in 204.34s (0:03:24)
```

The two skips are `tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False]` and `[True]`, the only `requires_corpus` tests in the set (`NEXUS_RUN_CORPUS` unset).

Item 14 runs. Each block shows the full command and the full summary tail (the pytest warnings section above the guard line is omitted):

Before the fix in `80c4321a`. The failure is `tests/test_orrery/test_character_experiences_pg.py::test_real_commit_forms_verified_seeds_and_boundary_batch` (`tests/test_orrery/test_character_experiences_pg.py:3493: AssertionError: assert 'gpt-6-astra' != 'gpt-6-astra'`):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_orrery/test_character_experiences_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_orrery/test_acquisition_scan_pg.py tests/test_orrery/test_experience_enqueue_gin_pg.py tests/test_player_identity_consumers_pg.py tests/test_record_revelation_cli_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 42 targets: postgres, qa640_wizard_drain_* x3, qa_identity_surface_16223b3a6f, qa_identity_surface_39bf18b908, qa_identity_surface_55f27b8080, qa_identity_surface_9806948139, qa_identity_surface_c4069a35eb, qa_identity_surface_d2e5457d27, qa_identity_surface_fa6c88726e, qa_player_identity_e8130b2712, qa_wt664_*, qa_wt720_*, qa_wt723_*, qa_wt724_experience_* x26, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 failed, 82 passed, 2 warnings in 98.45s (0:01:38)
```

After `80c4321a`, the failing file alone:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_orrery/test_character_experiences_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 30 targets: postgres, qa640_wizard_drain_* x3, qa_wt724_experience_* x26
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
28 passed, 2 warnings in 71.04s (0:01:11)
```

The five other candidate files, rerun at `310229ea` (55 passed; with the 28 above this accounts for all 83 tests of the first run):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_orrery/test_recall_disclosure_pg.py tests/test_orrery/test_acquisition_scan_pg.py tests/test_orrery/test_experience_enqueue_gin_pg.py tests/test_player_identity_consumers_pg.py tests/test_record_revelation_cli_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 13 targets: postgres, qa_identity_surface_0dba6cc079, qa_identity_surface_5dbcc26608, qa_identity_surface_63a90947b3, qa_identity_surface_783070e7a1, qa_identity_surface_d43a82373a, qa_identity_surface_e7e740b3fd, qa_identity_surface_f191cbef03, qa_player_identity_e67b51087f, qa_wt664_*, qa_wt720_*, qa_wt723_*, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
55 passed, 2 warnings in 33.34s
```

Consumers of the slot setup and new-story paths:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_commit_choice_presence_pg.py tests/test_orrery/test_geo_reference_pg.py tests/test_story_identity_pg.py tests/test_wizard_opening_presence_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 59 targets: postgres, qa640_822_backfill_a_*, qa640_822_backfill_b_*, qa640_822_backfill_t_*, qa640_822_clone_*, qa640_822_clone_bare_*, qa640_822_clone_invalid_*, qa640_822_clone_pre146_*, qa640_822_clone_src_*, qa640_822_constraints_*, qa640_822_detach_*, qa640_822_detach_bare_*, qa640_822_detach_src_*, qa640_822_doctor_s_*, qa640_822_doctor_t_*, qa640_822_init_*, qa640_822_migration_*, qa640_822_preflight_a_* x9, qa640_822_preflight_b_* x9, qa640_822_preflight_parent_* x9, qa640_822_reset_*, qa640_822_reset_src_*, qa640_822_transition_*, qa640_840_commit_*, qa640_840_empty_*, qa640_840_fresh_* x2, qa640_840_geo_*, qa655_wizard_139736c488, qa655_wizard_46d714a71c, qa655_wizard_90275767fc, qa655_wizard_b51cabedcf, qa655_wizard_cbea057c43, qa655_wizard_ff03f7c728, qa_wt715_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
47 passed, 4 warnings in 224.63s (0:03:44)
```

Slot operations and wrapper checks; the one failure is `tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module`, present on the base (see below):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_rebuild_memory_idf_pg.py tests/test_schema_documentation_pg.py tests/test_slot_operations_pg.py tests/test_slot_operations_journal.py tests/test_database_contract.py tests/test_script_wrappers.py tests/test_slot_routed_entrypoints.py tests/test_scheduler_helpers_routing.py tests/test_schema_ownership.py tests/test_new_story_cli.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 81 targets: postgres, qa640_1013_absent_*, qa640_1013_idf_* x7, qa640_810s3_ann_* x2, qa640_810s3_ann_high_* x2, qa640_810s3_ann_precheck_* x12, qa640_810s3_assets_*, qa640_810s3_importer_*, qa640_810s3_provider_*, qa640_810s3_regen_*, qa640_810s3_scene_* x2, qa640_810s3_season_*, qa640_823s1_dest_* x14, qa640_823s1_dest_02bebdc7226d_staging_*, qa640_823s1_dest_16ed7c99a20d_staging_*, qa640_823s1_dest_1ad65c9872c9_staging_*, qa640_823s1_dest_341d8277fe09_staging_*, qa640_823s1_dest_882aa781954d_staging_*, qa640_823s1_dest_917e067b2fc8_staging_*, qa640_823s1_dest_9c054b8d3a28_staging_*, qa640_823s1_dest_a172845f4aaf_staging_*, qa640_823s1_dest_b16d07f6c432_staging_*, qa640_823s1_dest_b951aa4367f6_staging_*, qa640_823s1_dest_eb79289d3752_staging_*, qa640_823s1_dest_f6967673c76e_staging_*, qa640_823s1_src_* x14, qa640_823s1_tpl_*, qa640_connection_contract, qa640_docs_refresh_*, qa640_lane_close_*, qa640_raw_url_contract, qa640_schema_docs_* x3, qa885_entrypoints_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:52642 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[1] at local:52675 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[0] at local:52690 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard; two_clusters[1] at local:52693 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard
dbname audit: owner names admitted on registered clusters: none
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 failed, 198 passed, 2 warnings in 233.81s (0:03:53)
```

Wizard and live-gate consumers:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_api/test_conversations.py tests/test_api/test_wizard_messages_migration_pg.py tests/test_api/test_wizard_model_switch.py tests/test_live_gate_clones_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 25 targets: postgres, qa640_776_hosted_*, qa640_776_uuid_*, qa640_offline_gate_* x16, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
23 passed, 7 warnings in 65.24s (0:01:05)
```

Offline:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py tests/config tests/test_api/test_settings_endpoints.py tests/test_api/test_route_capabilities.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
300 passed, 1 skipped, 7 warnings in 30.62s

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
5 failed, 3189 passed, 672 skipped, 8 warnings in 648.91s (0:10:48)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts
FAILED tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
11 failed, 1895 passed, 1518 skipped, 7 warnings in 47.94s
```

### Failures Present on the Base

All sixteen offline failures above (the `test_script_wrappers` failure among them; it also failed in the PostgreSQL extended set) fail identically on the base. The base run below was repeated on 2026-10-13 during the review fixes, on a fresh export of `claude/wave-b-integration` at `7eb9a10c`, committed into a scratch repository so that `git ls-files` and `git show HEAD:` behave as in a checkout. The import check printed the export's own `nexus/__init__.py`. None of these tests is in a file this branch changes.

```
$ B=<scratch>/809-S3b-resume/base-7eb9a10c
$ git archive 7eb9a10c | tar -x -C $B && git -C $B init -q && git -C $B add -A \
    && git -C $B -c user.name=scratch -c user.email=scratch@localhost commit -q --no-verify -m "export of claude/wave-b-integration 7eb9a10c"
$ cd $B && PYTHONPATH=$PWD $PY -c 'import nexus;print(nexus.__file__)'
<scratch>/809-S3b-resume/base-7eb9a10c/nexus/__init__.py
$ cd $B && env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider \
  tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged \
  tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained \
  tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module \
  tests/test_skald_wire.py::test_wire_schema_size_and_description_budget \
  tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp \
  "tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]" \
  "tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]" \
  tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy \
  tests/test_orrery/test_config.py::test_orrery_settings_load_queue_and_resolution_defaults \
  tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job \
  tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows \
  tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief \
  tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds \
  tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration \
  tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures \
  tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts \
  tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[setting_confirmed]
FAILED tests/test_api/test_wizard_confirmation.py::test_final_transition_cannot_bypass_artifact_acceptance[character_confirmed]
FAILED tests/test_orrery/test_config.py::test_epistemics_rejects_event_type_without_birth_role_policy
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_queues_narration_job
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_skips_low_signal_rows
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_state_signal_without_brief
FAILED tests/test_orrery/test_worker.py::test_promote_pending_resolutions_uses_configured_thresholds
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_persists_offscreen_narration
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_requeues_transient_failures
FAILED tests/test_orrery/test_worker.py::test_drain_narration_outbox_marks_terminal_after_max_attempts
FAILED tests/test_orrery/test_worker.py::test_clear_semantic_tags_is_conservative_noop_without_local_inference
16 failed, 1 passed, 5 warnings in 2.87s
```

The one test that passes is `test_orrery_settings_load_queue_and_resolution_defaults`, included as a control. The first base export (an uncommitted scratch repository) failed it because `git show HEAD:nexus.toml` had no commit to read. It passes on the committed export and on the branch.

Failure reasons from the same base log:

- `test_assembled_writer_and_gaia_requests_are_unchanged`: Gaia fingerprint `e0f4920a...` != recorded `cac3d730...`.
- `test_gaia_prompt_is_concise_and_self_contained`: `assert 732 < 700` words.
- `test_no_tracked_file_binds_a_wrapper_module`: `tests/test_orrery/test_place_point_required_pg.py:11` and `tests/test_runtime/test_init_plan_pg.py:23` bind a wrapper module.
- `test_wire_schema_size_and_description_budget`: the description of `NewEntityDeclaration.coordinates` is over its length budget (`assert {'NewEntityDe...other kinds.'} == {}`).
- `test_transition_rejects_missing_diegetic_timestamp` and the two `test_wizard_confirmation` cases: `Unit test attempted psycopg2.connect; mark it requires_postgres`.
- `test_epistemics_rejects_event_type_without_birth_role_policy`: `claim_event_types contains event types emitted by background branches: ['ate']`, which does not match the expected regex.
- The eight `test_worker.py` cases: `orrery.projects.milestone_magnitude must be >= orrery.promote.magnitude_threshold`.

## Mutation Run of `test_absent_optional_section_is_omitted`

`response_model_exclude_unset=True` removed from the route, the guard run, then `git checkout -- nexus/api/settings_endpoints.py`:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api/test_settings_endpoints.py::test_absent_optional_section_is_omitted
>       assert "api" not in payload
E       AssertionError: assert 'api' not in {'apex': {'anthropic_storyteller_transport': 'prompted', 'gaia': {'max_output_tokens': 25000, 'reasoning_effort': 'med....}, 'default_model': 'gpt-5.6-terra', 'default_model_policy': 'fixed', 'tokenizer_probe_timeout_seconds': 120.0}}, ...}
tests/test_api/test_settings_endpoints.py:121: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_api/test_settings_endpoints.py::test_absent_optional_section_is_omitted
1 failed, 5 warnings in 0.29s
```

A probe under the mutant printed `True None` (`api` served as `null`); after the restore it printed `False '<absent>'`. `git status --short` was clean after the restore.

## Static Checks

Run on 2026-10-13 during the review fixes. The branch side ran in the worktree at `b2ccf1b7`, whose Python files are identical to `813add4a`. The base side ran on the committed `7eb9a10c` export described under "Failures Present on the Base". `FILES` is the eighteen Python files that the branch changes and keeps (`git diff --name-only --diff-filter=d claude/wave-b-integration...HEAD -- '*.py'`); the deleted `tests/test_new_story_setup_config.py` is not checked:

```
nexus/api/new_story_flow.py
nexus/api/settings_endpoints.py
nexus/config/settings_models.py
nexus/maintenance/new_story_setup.py
scripts/new_story_setup.py
scripts/qa_shift/qa_shift.py
tests/config/test_settings_models.py
tests/config/test_settings_parity.py
tests/settings_helpers.py
tests/test_api/test_settings_endpoints.py
tests/test_api/test_slot_settings.py
tests/test_api/test_wizard_model_resolution.py
tests/test_golden_path_live.py
tests/test_new_story_setup.py
tests/test_orrery/test_character_experiences_pg.py
tests/test_orrery/test_retrograde_wizard_live.py
tests/test_qa_shift.py
tests/test_runtime/test_supervisor_live.py
```

Black:

```
$ nice -n 15 $PY -m black --check $FILES
All done! ✨ 🍰 ✨
18 files would be left unchanged.
```

### flake8

```
$ cd <worktree> && nice -n 15 $PY -m flake8 $FILES        # branch, exit 1
nexus/api/new_story_flow.py:14:1: F401 'pathlib.Path' imported but unused
nexus/api/new_story_flow.py:991:89: E501 line too long (100 > 88 characters)
nexus/api/new_story_flow.py:997:89: E501 line too long (90 > 88 characters)
nexus/api/new_story_flow.py:1019:89: E501 line too long (94 > 88 characters)
nexus/config/settings_models.py:86:89: E501 line too long (89 > 88 characters)
nexus/config/settings_models.py:133:89: E501 line too long (90 > 88 characters)
nexus/config/settings_models.py:148:89: E501 line too long (101 > 88 characters)
nexus/config/settings_models.py:156:89: E501 line too long (91 > 88 characters)
nexus/config/settings_models.py:2518:89: E501 line too long (93 > 88 characters)
nexus/config/settings_models.py:4563:89: E501 line too long (131 > 88 characters)
nexus/maintenance/new_story_setup.py:7:89: E501 line too long (101 > 88 characters)
nexus/maintenance/new_story_setup.py:66:89: E501 line too long (90 > 88 characters)
nexus/maintenance/new_story_setup.py:81:89: E501 line too long (91 > 88 characters)
nexus/maintenance/new_story_setup.py:241:89: E501 line too long (96 > 88 characters)
nexus/maintenance/new_story_setup.py:383:89: E501 line too long (90 > 88 characters)
nexus/maintenance/new_story_setup.py:806:89: E501 line too long (116 > 88 characters)
scripts/new_story_setup.py:7:89: E501 line too long (101 > 88 characters)
tests/test_api/test_slot_settings.py:43:89: E501 line too long (90 > 88 characters)
tests/test_api/test_slot_settings.py:227:89: E501 line too long (91 > 88 characters)
tests/test_api/test_wizard_model_resolution.py:12:1: F401 'types.SimpleNamespace' imported but unused
tests/test_orrery/test_character_experiences_pg.py:3572:89: E501 line too long (91 > 88 characters)
tests/test_orrery/test_character_experiences_pg.py:3578:89: E501 line too long (107 > 88 characters)

$ cd <scratch>/809-S3b-resume/base-7eb9a10c && nice -n 15 $PY -m flake8 $FILES        # base, exit 1
nexus/api/new_story_flow.py:14:1: F401 'pathlib.Path' imported but unused
nexus/api/new_story_flow.py:1015:89: E501 line too long (100 > 88 characters)
nexus/api/new_story_flow.py:1021:89: E501 line too long (90 > 88 characters)
nexus/api/new_story_flow.py:1043:89: E501 line too long (94 > 88 characters)
nexus/config/settings_models.py:87:89: E501 line too long (89 > 88 characters)
nexus/config/settings_models.py:134:89: E501 line too long (90 > 88 characters)
nexus/config/settings_models.py:149:89: E501 line too long (101 > 88 characters)
nexus/config/settings_models.py:157:89: E501 line too long (91 > 88 characters)
nexus/config/settings_models.py:2524:89: E501 line too long (93 > 88 characters)
nexus/config/settings_models.py:4570:89: E501 line too long (131 > 88 characters)
nexus/maintenance/new_story_setup.py:7:89: E501 line too long (101 > 88 characters)
nexus/maintenance/new_story_setup.py:66:89: E501 line too long (90 > 88 characters)
nexus/maintenance/new_story_setup.py:81:89: E501 line too long (91 > 88 characters)
nexus/maintenance/new_story_setup.py:125:89: E501 line too long (101 > 88 characters)
nexus/maintenance/new_story_setup.py:253:89: E501 line too long (96 > 88 characters)
nexus/maintenance/new_story_setup.py:395:89: E501 line too long (90 > 88 characters)
nexus/maintenance/new_story_setup.py:818:89: E501 line too long (116 > 88 characters)
scripts/new_story_setup.py:7:89: E501 line too long (101 > 88 characters)
tests/test_api/test_slot_settings.py:43:89: E501 line too long (90 > 88 characters)
tests/test_api/test_slot_settings.py:224:89: E501 line too long (91 > 88 characters)
tests/test_api/test_wizard_model_resolution.py:11:1: F401 'types.SimpleNamespace' imported but unused
tests/test_api/test_wizard_model_resolution.py:12:1: F401 'typing.Any' imported but unused
tests/test_orrery/test_character_experiences_pg.py:3567:89: E501 line too long (91 > 88 characters)
tests/test_orrery/test_character_experiences_pg.py:3573:89: E501 line too long (107 > 88 characters)
```

Branch 22, base 24. The base's two extra diagnostics are on lines this branch deleted or now uses: `nexus/maintenance/new_story_setup.py:125` E501 (the old INSERT line that passed the default slot model) and `tests/test_api/test_wizard_model_resolution.py:12` F401 (`typing.Any` was unused; `test_start_setup_keeps_every_non_null_slot_pin` now uses it at line 105).

### mypy

One run per file, so each file's own diagnostics stay separate:

```
$ for f in $FILES; do PYTHONPATH=$PWD nice -n 15 $PY -m mypy --explicit-package-bases "$f"; done
```

Branch output (worktree):

```
== nexus/api/new_story_flow.py
nexus/api/new_story_flow.py:1037: error: Incompatible return value type (got "dict[int, str]", expected "dict[str, str]")  [return-value]
Found 1 error in 1 file (checked 1 source file)
== nexus/api/settings_endpoints.py
Success: no issues found in 1 source file
== nexus/config/settings_models.py
nexus/config/settings_models.py:137: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:137: note: Right operand is of type "int | None"
nexus/config/settings_models.py:138: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:138: error: Unsupported operand types for < ("int" and "None")  [operator]
nexus/config/settings_models.py:138: error: Unsupported left operand type for > ("None")  [operator]
nexus/config/settings_models.py:138: note: Both left and right operands are unions
nexus/config/settings_models.py:145: error: Unsupported operand types for + ("int" and "None")  [operator]
nexus/config/settings_models.py:145: note: Right operand is of type "int | None"
nexus/config/settings_models.py:145: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4561: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4561: note: Right operand is of type "int | None"
Found 7 errors in 1 file (checked 1 source file)
== nexus/maintenance/new_story_setup.py
Success: no issues found in 1 source file
== scripts/new_story_setup.py
Success: no issues found in 1 source file
== scripts/qa_shift/qa_shift.py
Success: no issues found in 1 source file
== tests/config/test_settings_models.py
tests/config/test_settings_models.py:873: error: Item "None" of "RuntimeSettings | None" has no attribute "cli"  [union-attr]
Found 1 error in 1 file (checked 1 source file)
== tests/config/test_settings_parity.py
Success: no issues found in 1 source file
== tests/settings_helpers.py
Success: no issues found in 1 source file
== tests/test_api/test_settings_endpoints.py
Success: no issues found in 1 source file
== tests/test_api/test_slot_settings.py
tests/test_api/test_slot_settings.py:53: error: Incompatible types in assignment (expression has type "dict[str, str] | dict[str, int]", variable has type "dict[str, object]")  [assignment]
tests/test_api/test_slot_settings.py:194: error: Unsupported target for indexed assignment ("Item | Container")  [index]
Found 2 errors in 1 file (checked 1 source file)
== tests/test_api/test_wizard_model_resolution.py
Success: no issues found in 1 source file
== tests/test_golden_path_live.py
tests/test_golden_path_live.py:71: error: Library stubs not installed for "requests"  [import-untyped]
tests/test_golden_path_live.py:71: note: Hint: "python3 -m pip install types-requests"
tests/test_golden_path_live.py:71: note: (or run "mypy --install-types" to install all missing stub packages)
tests/test_golden_path_live.py:71: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
tests/test_golden_path_live.py:256: error: Item "None" of "WizardCache | None" has no attribute "thread_id"  [union-attr]
tests/test_golden_path_live.py:256: error: Argument "thread_id" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]
tests/test_golden_path_live.py:258: error: Item "None" of "WizardCache | None" has no attribute "artifact_token"  [union-attr]
tests/test_golden_path_live.py:258: error: Argument "artifact_token" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]
tests/test_golden_path_live.py:483: error: Value of type "Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:483: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
tests/test_golden_path_live.py:484: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:485: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:486: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:488: error: Value of type "Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:488: error: Value of type "Any | Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:488: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
Found 13 errors in 1 file (checked 1 source file)
== tests/test_new_story_setup.py
tests/test_new_story_setup.py:207: error: Value of type "Item | Container" is not indexable  [index]
tests/test_new_story_setup.py:207: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
tests/test_new_story_setup.py:232: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_new_story_setup.py:234: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
Found 4 errors in 1 file (checked 1 source file)
== tests/test_orrery/test_character_experiences_pg.py
tests/test_orrery/test_character_experiences_pg.py:1596: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1597: error: "LogRecord" has no attribute "world_event_type"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1598: error: "LogRecord" has no attribute "world_event_tick_chunk_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1599: error: "LogRecord" has no attribute "world_event_actor_entity_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1600: error: "LogRecord" has no attribute "world_event_target_entity_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1601: error: "LogRecord" has no attribute "world_event_resolution_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1602: error: "LogRecord" has no attribute "world_event_source"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1603: error: "LogRecord" has no attribute "world_event_world_layer"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1604: error: "LogRecord" has no attribute "quarantine_reason_code"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2729: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2730: error: "LogRecord" has no attribute "replacement_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2829: error: "LogRecord" has no attribute "supersession_rejection_reason"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2836: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2837: error: "LogRecord" has no attribute "replacement_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2838: error: "LogRecord" has no attribute "supersession_rejection_detail"  [attr-defined]
Found 15 errors in 1 file (checked 1 source file)
== tests/test_orrery/test_retrograde_wizard_live.py
Success: no issues found in 1 source file
== tests/test_qa_shift.py
tests/test_qa_shift.py:192: error: "Collection[Collection[str]]" has no attribute "get"  [attr-defined]
tests/test_qa_shift.py:1088: error: No overload variant of "int" matches argument type "object"  [call-overload]
tests/test_qa_shift.py:1088: note: Possible overload variants:
tests/test_qa_shift.py:1088: note:     def int(str | Buffer | SupportsInt | SupportsIndex | SupportsTrunc = ..., /) -> int
tests/test_qa_shift.py:1088: note:     def int(str | bytes | bytearray, /, base: SupportsIndex) -> int
Found 2 errors in 1 file (checked 1 source file)
== tests/test_runtime/test_supervisor_live.py
tests/test_runtime/test_supervisor_live.py:657: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
Success: no issues found in 1 source file
```

Base output (`7eb9a10c` export):

```
== nexus/api/new_story_flow.py
nexus/api/new_story_flow.py:1061: error: Incompatible return value type (got "dict[int, str]", expected "dict[str, str]")  [return-value]
Found 1 error in 1 file (checked 1 source file)
== nexus/api/settings_endpoints.py
Success: no issues found in 1 source file
== nexus/config/settings_models.py
nexus/config/settings_models.py:138: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:138: note: Right operand is of type "int | None"
nexus/config/settings_models.py:139: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:139: error: Unsupported operand types for < ("int" and "None")  [operator]
nexus/config/settings_models.py:139: error: Unsupported left operand type for > ("None")  [operator]
nexus/config/settings_models.py:139: note: Both left and right operands are unions
nexus/config/settings_models.py:146: error: Unsupported operand types for + ("int" and "None")  [operator]
nexus/config/settings_models.py:146: note: Right operand is of type "int | None"
nexus/config/settings_models.py:146: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4568: error: Unsupported operand types for > ("int" and "None")  [operator]
nexus/config/settings_models.py:4568: note: Right operand is of type "int | None"
Found 7 errors in 1 file (checked 1 source file)
== nexus/maintenance/new_story_setup.py
Success: no issues found in 1 source file
== scripts/new_story_setup.py
Success: no issues found in 1 source file
== scripts/qa_shift/qa_shift.py
Success: no issues found in 1 source file
== tests/config/test_settings_models.py
tests/config/test_settings_models.py:875: error: Item "None" of "RuntimeSettings | None" has no attribute "cli"  [union-attr]
Found 1 error in 1 file (checked 1 source file)
== tests/config/test_settings_parity.py
Success: no issues found in 1 source file
== tests/settings_helpers.py
Success: no issues found in 1 source file
== tests/test_api/test_settings_endpoints.py
Success: no issues found in 1 source file
== tests/test_api/test_slot_settings.py
tests/test_api/test_slot_settings.py:53: error: Incompatible types in assignment (expression has type "dict[str, str] | dict[str, int]", variable has type "dict[str, object]")  [assignment]
tests/test_api/test_slot_settings.py:194: error: Unsupported target for indexed assignment ("Item | Container")  [index]
Found 2 errors in 1 file (checked 1 source file)
== tests/test_api/test_wizard_model_resolution.py
Success: no issues found in 1 source file
== tests/test_golden_path_live.py
tests/test_golden_path_live.py:71: error: Library stubs not installed for "requests"  [import-untyped]
tests/test_golden_path_live.py:71: note: Hint: "python3 -m pip install types-requests"
tests/test_golden_path_live.py:71: note: (or run "mypy --install-types" to install all missing stub packages)
tests/test_golden_path_live.py:71: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
tests/test_golden_path_live.py:256: error: Item "None" of "WizardCache | None" has no attribute "thread_id"  [union-attr]
tests/test_golden_path_live.py:256: error: Argument "thread_id" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]
tests/test_golden_path_live.py:258: error: Item "None" of "WizardCache | None" has no attribute "artifact_token"  [union-attr]
tests/test_golden_path_live.py:258: error: Argument "artifact_token" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]
tests/test_golden_path_live.py:483: error: Value of type "Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:483: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
tests/test_golden_path_live.py:484: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:485: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:486: error: Unsupported target for indexed assignment ("Item | Container")  [index]
tests/test_golden_path_live.py:488: error: Value of type "Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:488: error: Value of type "Any | Item | Container" is not indexable  [index]
tests/test_golden_path_live.py:488: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
Found 13 errors in 1 file (checked 1 source file)
== tests/test_new_story_setup.py
tests/test_new_story_setup.py:207: error: Value of type "Item | Container" is not indexable  [index]
tests/test_new_story_setup.py:207: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
tests/test_new_story_setup.py:232: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_new_story_setup.py:234: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
Found 4 errors in 1 file (checked 1 source file)
== tests/test_orrery/test_character_experiences_pg.py
tests/test_orrery/test_character_experiences_pg.py:1591: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1592: error: "LogRecord" has no attribute "world_event_type"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1593: error: "LogRecord" has no attribute "world_event_tick_chunk_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1594: error: "LogRecord" has no attribute "world_event_actor_entity_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1595: error: "LogRecord" has no attribute "world_event_target_entity_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1596: error: "LogRecord" has no attribute "world_event_resolution_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1597: error: "LogRecord" has no attribute "world_event_source"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1598: error: "LogRecord" has no attribute "world_event_world_layer"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:1599: error: "LogRecord" has no attribute "quarantine_reason_code"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2724: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2725: error: "LogRecord" has no attribute "replacement_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2824: error: "LogRecord" has no attribute "supersession_rejection_reason"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2831: error: "LogRecord" has no attribute "world_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2832: error: "LogRecord" has no attribute "replacement_event_id"  [attr-defined]
tests/test_orrery/test_character_experiences_pg.py:2833: error: "LogRecord" has no attribute "supersession_rejection_detail"  [attr-defined]
Found 15 errors in 1 file (checked 1 source file)
== tests/test_orrery/test_retrograde_wizard_live.py
Success: no issues found in 1 source file
== tests/test_qa_shift.py
tests/test_qa_shift.py:192: error: "Collection[Collection[str]]" has no attribute "get"  [attr-defined]
tests/test_qa_shift.py:1089: error: No overload variant of "int" matches argument type "object"  [call-overload]
tests/test_qa_shift.py:1089: note: Possible overload variants:
tests/test_qa_shift.py:1089: note:     def int(str | Buffer | SupportsInt | SupportsIndex | SupportsTrunc = ..., /) -> int
tests/test_qa_shift.py:1089: note:     def int(str | bytes | bytearray, /, base: SupportsIndex) -> int
Found 2 errors in 1 file (checked 1 source file)
== tests/test_runtime/test_supervisor_live.py
tests/test_runtime/test_supervisor_live.py:660: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
Success: no issues found in 1 source file
```

Branch 45 errors, base 45 errors, with the same message in the same file each time. The only note-only output is the `annotation-unchecked` note in `tests/test_runtime/test_supervisor_live.py` (branch line 657, base line 660), which is on both sides.

### Pre-existing Diagnostics

Each branch diagnostic below was matched to a base diagnostic with the same file and message. Its branch line was checked against the added lines of `git diff -U0 claude/wave-b-integration...HEAD -- <file>`. No diagnostic is on a changed or added line. Line shifts come from the branch's deletions and insertions above the diagnostic.

flake8 (22):

- branch `nexus/api/new_story_flow.py:14` F401 'pathlib.Path' imported but unused; base `nexus/api/new_story_flow.py:14`
- branch `nexus/api/new_story_flow.py:991` E501 line too long (100 > 88 characters); base `nexus/api/new_story_flow.py:1015`
- branch `nexus/api/new_story_flow.py:997` E501 line too long (90 > 88 characters); base `nexus/api/new_story_flow.py:1021`
- branch `nexus/api/new_story_flow.py:1019` E501 line too long (94 > 88 characters); base `nexus/api/new_story_flow.py:1043`
- branch `nexus/config/settings_models.py:86` E501 line too long (89 > 88 characters); base `nexus/config/settings_models.py:87`
- branch `nexus/config/settings_models.py:133` E501 line too long (90 > 88 characters); base `nexus/config/settings_models.py:134`
- branch `nexus/config/settings_models.py:148` E501 line too long (101 > 88 characters); base `nexus/config/settings_models.py:149`
- branch `nexus/config/settings_models.py:156` E501 line too long (91 > 88 characters); base `nexus/config/settings_models.py:157`
- branch `nexus/config/settings_models.py:2518` E501 line too long (93 > 88 characters); base `nexus/config/settings_models.py:2524`
- branch `nexus/config/settings_models.py:4563` E501 line too long (131 > 88 characters); base `nexus/config/settings_models.py:4570`
- branch `nexus/maintenance/new_story_setup.py:7` E501 line too long (101 > 88 characters); base `nexus/maintenance/new_story_setup.py:7`
- branch `nexus/maintenance/new_story_setup.py:66` E501 line too long (90 > 88 characters); base `nexus/maintenance/new_story_setup.py:66`
- branch `nexus/maintenance/new_story_setup.py:81` E501 line too long (91 > 88 characters); base `nexus/maintenance/new_story_setup.py:81`
- branch `nexus/maintenance/new_story_setup.py:241` E501 line too long (96 > 88 characters); base `nexus/maintenance/new_story_setup.py:253`
- branch `nexus/maintenance/new_story_setup.py:383` E501 line too long (90 > 88 characters); base `nexus/maintenance/new_story_setup.py:395`
- branch `nexus/maintenance/new_story_setup.py:806` E501 line too long (116 > 88 characters); base `nexus/maintenance/new_story_setup.py:818`
- branch `scripts/new_story_setup.py:7` E501 line too long (101 > 88 characters); base `scripts/new_story_setup.py:7`
- branch `tests/test_api/test_slot_settings.py:43` E501 line too long (90 > 88 characters); base `tests/test_api/test_slot_settings.py:43`
- branch `tests/test_api/test_slot_settings.py:227` E501 line too long (91 > 88 characters); base `tests/test_api/test_slot_settings.py:224`
- branch `tests/test_api/test_wizard_model_resolution.py:12` F401 'types.SimpleNamespace' imported but unused; base `tests/test_api/test_wizard_model_resolution.py:11`
- branch `tests/test_orrery/test_character_experiences_pg.py:3572` E501 line too long (91 > 88 characters); base `tests/test_orrery/test_character_experiences_pg.py:3567`
- branch `tests/test_orrery/test_character_experiences_pg.py:3578` E501 line too long (107 > 88 characters); base `tests/test_orrery/test_character_experiences_pg.py:3573`

mypy (45):

- branch `nexus/api/new_story_flow.py:1037` Incompatible return value type (got "dict[int, str]", expected "dict[str, str]")  [return-value]; base `nexus/api/new_story_flow.py:1061`
- branch `nexus/config/settings_models.py:137` Unsupported operand types for > ("int" and "None")  [operator]; base `nexus/config/settings_models.py:138`
- branch `nexus/config/settings_models.py:138` Unsupported operand types for > ("int" and "None")  [operator]; base `nexus/config/settings_models.py:139`
- branch `nexus/config/settings_models.py:138` Unsupported operand types for < ("int" and "None")  [operator]; base `nexus/config/settings_models.py:139`
- branch `nexus/config/settings_models.py:138` Unsupported left operand type for > ("None")  [operator]; base `nexus/config/settings_models.py:139`
- branch `nexus/config/settings_models.py:145` Unsupported operand types for + ("int" and "None")  [operator]; base `nexus/config/settings_models.py:146`
- branch `nexus/config/settings_models.py:145` Unsupported operand types for > ("int" and "None")  [operator]; base `nexus/config/settings_models.py:146`
- branch `nexus/config/settings_models.py:4561` Unsupported operand types for > ("int" and "None")  [operator]; base `nexus/config/settings_models.py:4568`
- branch `tests/config/test_settings_models.py:873` Item "None" of "RuntimeSettings | None" has no attribute "cli"  [union-attr]; base `tests/config/test_settings_models.py:875`
- branch `tests/test_api/test_slot_settings.py:53` Incompatible types in assignment (expression has type "dict[str, str] | dict[str, int]", variable has type "dict[str, object]")  [assignment]; base `tests/test_api/test_slot_settings.py:53`
- branch `tests/test_api/test_slot_settings.py:194` Unsupported target for indexed assignment ("Item | Container")  [index]; base `tests/test_api/test_slot_settings.py:194`
- branch `tests/test_golden_path_live.py:71` Library stubs not installed for "requests"  [import-untyped]; base `tests/test_golden_path_live.py:71`
- branch `tests/test_golden_path_live.py:256` Item "None" of "WizardCache | None" has no attribute "thread_id"  [union-attr]; base `tests/test_golden_path_live.py:256`
- branch `tests/test_golden_path_live.py:256` Argument "thread_id" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]; base `tests/test_golden_path_live.py:256`
- branch `tests/test_golden_path_live.py:258` Item "None" of "WizardCache | None" has no attribute "artifact_token"  [union-attr]; base `tests/test_golden_path_live.py:258`
- branch `tests/test_golden_path_live.py:258` Argument "artifact_token" to "confirm_artifact" has incompatible type "str | Any | None"; expected "str"  [arg-type]; base `tests/test_golden_path_live.py:258`
- branch `tests/test_golden_path_live.py:483` Value of type "Item | Container" is not indexable  [index]; base `tests/test_golden_path_live.py:483`
- branch `tests/test_golden_path_live.py:483` Unsupported target for indexed assignment ("Any | Item | Container")  [index]; base `tests/test_golden_path_live.py:483`
- branch `tests/test_golden_path_live.py:484` Unsupported target for indexed assignment ("Item | Container")  [index]; base `tests/test_golden_path_live.py:484`
- branch `tests/test_golden_path_live.py:485` Unsupported target for indexed assignment ("Item | Container")  [index]; base `tests/test_golden_path_live.py:485`
- branch `tests/test_golden_path_live.py:486` Unsupported target for indexed assignment ("Item | Container")  [index]; base `tests/test_golden_path_live.py:486`
- branch `tests/test_golden_path_live.py:488` Value of type "Item | Container" is not indexable  [index]; base `tests/test_golden_path_live.py:488`
- branch `tests/test_golden_path_live.py:488` Value of type "Any | Item | Container" is not indexable  [index]; base `tests/test_golden_path_live.py:488`
- branch `tests/test_golden_path_live.py:488` Unsupported target for indexed assignment ("Any | Item | Container")  [index]; base `tests/test_golden_path_live.py:488`
- branch `tests/test_new_story_setup.py:207` Value of type "Item | Container" is not indexable  [index]; base `tests/test_new_story_setup.py:207`
- branch `tests/test_new_story_setup.py:207` Unsupported target for indexed assignment ("Any | Item | Container")  [index]; base `tests/test_new_story_setup.py:207`
- branch `tests/test_new_story_setup.py:232` Value of type "tuple[Any, ...] | None" is not indexable  [index]; base `tests/test_new_story_setup.py:232`
- branch `tests/test_new_story_setup.py:234` Value of type "tuple[Any, ...] | None" is not indexable  [index]; base `tests/test_new_story_setup.py:234`
- branch `tests/test_orrery/test_character_experiences_pg.py:1596` "LogRecord" has no attribute "world_event_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1591`
- branch `tests/test_orrery/test_character_experiences_pg.py:1597` "LogRecord" has no attribute "world_event_type"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1592`
- branch `tests/test_orrery/test_character_experiences_pg.py:1598` "LogRecord" has no attribute "world_event_tick_chunk_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1593`
- branch `tests/test_orrery/test_character_experiences_pg.py:1599` "LogRecord" has no attribute "world_event_actor_entity_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1594`
- branch `tests/test_orrery/test_character_experiences_pg.py:1600` "LogRecord" has no attribute "world_event_target_entity_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1595`
- branch `tests/test_orrery/test_character_experiences_pg.py:1601` "LogRecord" has no attribute "world_event_resolution_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1596`
- branch `tests/test_orrery/test_character_experiences_pg.py:1602` "LogRecord" has no attribute "world_event_source"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1597`
- branch `tests/test_orrery/test_character_experiences_pg.py:1603` "LogRecord" has no attribute "world_event_world_layer"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1598`
- branch `tests/test_orrery/test_character_experiences_pg.py:1604` "LogRecord" has no attribute "quarantine_reason_code"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:1599`
- branch `tests/test_orrery/test_character_experiences_pg.py:2729` "LogRecord" has no attribute "world_event_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:2724`
- branch `tests/test_orrery/test_character_experiences_pg.py:2730` "LogRecord" has no attribute "replacement_event_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:2725`
- branch `tests/test_orrery/test_character_experiences_pg.py:2829` "LogRecord" has no attribute "supersession_rejection_reason"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:2824`
- branch `tests/test_orrery/test_character_experiences_pg.py:2836` "LogRecord" has no attribute "world_event_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:2831`
- branch `tests/test_orrery/test_character_experiences_pg.py:2837` "LogRecord" has no attribute "replacement_event_id"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:2832`
- branch `tests/test_orrery/test_character_experiences_pg.py:2838` "LogRecord" has no attribute "supersession_rejection_detail"  [attr-defined]; base `tests/test_orrery/test_character_experiences_pg.py:2833`
- branch `tests/test_qa_shift.py:192` "Collection[Collection[str]]" has no attribute "get"  [attr-defined]; base `tests/test_qa_shift.py:192`
- branch `tests/test_qa_shift.py:1088` No overload variant of "int" matches argument type "object"  [call-overload]; base `tests/test_qa_shift.py:1089`

No new diagnostics. The matcher script is `<scratch>/809-S3b-resume/fix_map.py`.

Exception dispositions:

```
$ PYTHONPATH=$PWD $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
$ PYTHONPATH=$PWD $PY -S scripts/check_exception_dispositions.py --baseline-base-ref claude/wave-b-integration
OK: exception disposition coverage and shrink-only baseline verified.
```

## UI

```
$ nice -n 15 npm --prefix ui ci          # exit 0
$ nice -n 15 npm --prefix ui run check   # exit 0
$ nice -n 15 npm --prefix ui test
 FAIL  src/state-shades.test.ts [ src/state-shades.test.ts ]
Error: Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).
 Test Files  1 failed | 40 passed (41)
      Tests  632 passed (632)
$ nice -n 15 npm --prefix ui run build   # exit 0; build output not committed
```

The stale state-surface receipt is expected on this base (amendment item 4); `resolve-state-surfaces` was not run. The coordinator regenerates once on the final UI union. No element was added and no rendered output changed.

## Document Freshness

`git diff --name-only claude/wave-b-integration...HEAD` against every `status: canonical` document's `sources:`: `nexus.toml` (AGENTS.md, `docs/turn_flow_sequence.md`, decisions 0009, 0010, 0024, 0034), `nexus/maintenance/new_story_setup.py` (decision 0040) and `scripts/qa_shift/qa_shift.py` (decision 0021). Each carries `verified_commit: "f073b3711a3bd0273943c9defad85913452fd00b"`, the merge base with `origin/main`. None of them names `default_slot_model`, TEST as a slot default, or `resolve_setup_model`. Decision 0021 was moved from `d70a1991` in `93b9abd4`. `tests/test_doc_front_matter.py` passed in the focused offline run.

## Integration Branch

`git merge claude/wave-b-integration` before push: `Already up to date.` (the integration branch is still `7eb9a10c`).

## Review Fixes (2026-10-13)

Three confirmed P3 review findings, applied after `813add4a`:

1. `scripts/qa_shift/README.md` still said that the generated QA config "sets the slot default to the same model". Item 11 removed that write, and item 7 removed the key. Commit `b2ccf1b7` changes the sentence to the reviewer's text: "That config pins both the default and Gaia OpenAI roles, and the wizard default, to the configured target model. It never edits `nexus.toml`." The README is not one of the consumers that item 13 lists. The coordinator passed this edit as a confirmed finding, so it lands in this branch and the PR body lists it. The README has no front matter, and no test reads it.
2. "Failures Present on the Base" now has the exact base-export command, its FAILED lines and its summary tail.
3. "Static Checks" now has the exact Black, flake8 and mypy commands and both full outputs, plus "Pre-existing Diagnostics", which gives the base location of each branch diagnostic. The earlier count of 43 mypy diagnostics was wrong: the per-file counts added up to 45 on each side.

Tests covering the README fix (the QA kit it documents), at `b2ccf1b7`:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_qa_shift.py tests/test_doc_front_matter.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
131 passed, 16 skipped, 5 warnings in 12.47s

$ uptime    # load averages: 23.68 15.29 15.36 (under 24)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit tests/test_qa_shift.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 17 targets: postgres, qa640_759_measure_*, qa640_778s4a_tests_* x6, qa640_778s6a_family_* x9
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
81 passed, 6 warnings in 45.23s
```

No Python file changed in these fixes. Black on the eighteen changed Python files: `18 files would be left unchanged.` `git merge claude/wave-b-integration`: `Already up to date.` (still `7eb9a10c`).
