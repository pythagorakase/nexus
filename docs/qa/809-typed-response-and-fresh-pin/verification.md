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
- `ui/client/src/hooks/useSettings.ts:36-39` the `wizard` projection; `:54` the `wizard_model` cache copy; `:64-67` the `wizard_model` key-status invalidation. `SECRETS_QUERY_KEY` stays imported: `:90` (`useSlotSettingsMutation`) still uses it.
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

Item 14 runs (same environment and plugin):

```
$ ... -rs -p tests.dbname_audit tests/test_orrery/test_character_experiences_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_orrery/test_acquisition_scan_pg.py tests/test_orrery/test_experience_enqueue_gin_pg.py tests/test_player_identity_consumers_pg.py tests/test_record_revelation_cli_pg.py
dbname audit: owner targets: none
1 failed, 82 passed, 2 warnings in 98.45s (0:01:38)
(before the fix: test_real_commit_forms_verified_seeds_and_boundary_batch, assert 'gpt-6-astra' != 'gpt-6-astra')

$ ... -rs -p tests.dbname_audit tests/test_orrery/test_character_experiences_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 30 targets: postgres, qa640_wizard_drain_* x3, qa_wt724_experience_* x26
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
28 passed, 2 warnings in 71.04s (0:01:11)

$ ... -rs -p tests.dbname_audit tests/test_commit_choice_presence_pg.py tests/test_orrery/test_geo_reference_pg.py tests/test_story_identity_pg.py tests/test_wizard_opening_presence_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
47 passed, 4 warnings in 224.63s (0:03:44)

$ ... -rs -p tests.dbname_audit tests/test_rebuild_memory_idf_pg.py tests/test_schema_documentation_pg.py tests/test_slot_operations_pg.py tests/test_slot_operations_journal.py tests/test_database_contract.py tests/test_script_wrappers.py tests/test_slot_routed_entrypoints.py tests/test_scheduler_helpers_routing.py tests/test_schema_ownership.py tests/test_new_story_cli.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner names admitted on registered clusters: none
dbname audit: owner targets: none
1 failed, 198 passed, 2 warnings in 233.81s (0:03:53)
(the failure is tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module, pre-existing; see below)

$ ... -rs -p tests.dbname_audit tests/test_api/test_conversations.py tests/test_api/test_wizard_messages_migration_pg.py tests/test_api/test_wizard_model_switch.py tests/test_live_gate_clones_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
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
FAILED tests/test_lore/test_assembled_prompt_fingerprint.py::test_assembled_writer_and_gaia_requests_are_unchanged
FAILED tests/test_lore/test_two_pass_pipeline.py::test_gaia_prompt_is_concise_and_self_contained
FAILED tests/test_script_wrappers.py::test_no_tracked_file_binds_a_wrapper_module
FAILED tests/test_skald_wire.py::test_wire_schema_size_and_description_budget
FAILED tests/test_wizard_agent.py::test_transition_rejects_missing_diegetic_timestamp
5 failed, 3189 passed, 672 skipped, 8 warnings in 648.91s (0:10:48)

$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
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

All sixteen offline failures above, and the `test_script_wrappers` failure in the PostgreSQL extended set, fail identically on a `git archive claude/wave-b-integration` export (`809-S3b-resume/base`), none in a file this branch changes:

- `test_assembled_writer_and_gaia_requests_are_unchanged`: Gaia fingerprint `e0f4920a...` != recorded `cac3d730...`.
- `test_gaia_prompt_is_concise_and_self_contained`: `assert 732 < 700` words.
- `test_no_tracked_file_binds_a_wrapper_module`: `tests/test_orrery/test_place_point_required_pg.py:11` and `tests/test_runtime/test_init_plan_pg.py:23` bind a wrapper module.
- `test_wire_schema_size_and_description_budget`, `test_transition_rejects_missing_diegetic_timestamp`, the two `test_wizard_confirmation` cases, `test_epistemics_rejects_event_type_without_birth_role_policy` (`claim_event_types contains event types emitted by background branches: ['ate']`) and the eight `test_worker.py` cases.

The base export also failed `test_orrery_settings_load_queue_and_resolution_defaults`, an artifact of that export (`git show HEAD:nexus.toml` in an uncommitted scratch repository); it passes on the branch.

## Mutation Run of `test_absent_optional_section_is_omitted`

`response_model_exclude_unset=True` removed from the route, the guard run, then `git checkout -- nexus/api/settings_endpoints.py`:

```
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api/test_settings_endpoints.py::test_absent_optional_section_is_omitted
>       assert "api" not in payload
E       AssertionError: assert 'api' not in {'apex': {'anthropic_storyteller_transport': 'prompted', 'gaia': {'max_output_tokens': 25000, 'reasoning_effort': 'med....}, 'default_model': 'gpt-5.6-terra', 'default_model_policy': 'fixed', 'tokenizer_probe_timeout_seconds': 120.0}}, ...}
tests/test_api/test_settings_endpoints.py:121: AssertionError
FAILED tests/test_api/test_settings_endpoints.py::test_absent_optional_section_is_omitted
1 failed, 5 warnings in 0.29s
```

A probe under the mutant printed `True None` (`api` served as `null`); after the restore it printed `False '<absent>'`. `git status --short` was clean after the restore.

## Static Checks

`black --check` on the eighteen changed Python files: `18 files would be left unchanged.`

flake8 (branch versus the same files on `claude/wave-b-integration`): branch 22, base 24. Every branch diagnostic is on an untouched line and present on the base (shifted line numbers); the base's two extra are `nexus/maintenance/new_story_setup.py:125` (the deleted INSERT line) and `tests/test_api/test_wizard_model_resolution.py:12` (`typing.Any` unused, now used).

`mypy --explicit-package-bases` per file, branch versus base: `new_story_flow.py` 1/1, `settings_endpoints.py` 0/0, `settings_models.py` 7/7, `nexus/maintenance/new_story_setup.py` 0/0, `scripts/new_story_setup.py` 0/0, `qa_shift.py` 0/0, `test_settings_models.py` 1/1, `test_settings_parity.py` 0/0, `settings_helpers.py` 0/0, `test_settings_endpoints.py` 0/0, `test_slot_settings.py` 2/2, `test_wizard_model_resolution.py` 0/0, `test_golden_path_live.py` 13/13, `test_new_story_setup.py` 4/4, `test_character_experiences_pg.py` 15/15, `test_retrograde_wizard_live.py` 0/0, `test_qa_shift.py` 2/2, `test_supervisor_live.py` 0/0. No new diagnostics.

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
