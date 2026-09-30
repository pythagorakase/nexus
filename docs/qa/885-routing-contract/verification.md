# Verification: One Routing Contract for Every Test (#885 B2-9a)

Every tail below was produced at `f65459e5` (the code head of `claude/885-routing-contract`; base `origin/main` `ac2a585a`, B2-8, #1042) with a clean tree: `git status --porcelain` was empty before the first run and after the last, and `HEAD` did not move. The only later commit is this docs-only file. Every PostgreSQL run loaded `-p tests.dbname_audit`, ran with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset, and used the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`) with `nexus` imported from this worktree. No paid provider was called; every provider consumer ran on TEST. Logs sit in the session scratchpad under `885-B2-9a-fix2/`. Each fenced tail lists whole lines selected from its run log with `grep` (the guard line, every `dbname audit` line, skip reasons, failures and the summary; for the recovery runs also the traceback locations and errors); no line is edited or shortened.

## Item 7's Grep

```
grep -rn "slot_endpoints.slot_dbname\|VALID_DBNAMES" tests/ | cut -d: -f1 | sort | uniq -c
   3 tests/pg_fixtures.py
   1 tests/scheduler_helpers.py
  13 tests/test_pg_disposable_target.py
   1 tests/test_scheduler_helpers_routing.py
   2 tests/test_slot_routed_entrypoints.py
```

Only the shared helpers and their tests remain. The 30 modules that widened `VALID_DBNAMES` by hand now call `route_slot_to_disposable` (or `route_slots_to_disposable`); module-scoped fixtures route under their own `pytest.MonkeyPatch` (synthesis note 5). Each routes the slot its code under test resolves (for example slot 1 in `test_orrery_tag_validation_pg`, 2 in `test_retrograde_projects_live`, 3 in `test_retrograde_constraints_pg` and `test_need_clock_anchor_pg`, 4 in the reader and scheduler tests), else slot 5. The hand-written `slot_dbname` lambdas those fixtures carried (`test_reader_*_provenance_pg`, `test_return_recap_pg`, `test_reader_draft_identity_pg`, `test_slot_mutation_guard`, `test_pass2_baseline_pg`, `test_mock_wizard_responses`, and `test_slot_settings`'s `slot_endpoints` patch) are gone. `test_slot_mutation_guard` routes every slot to its one clone, because slot selection resolves every slot's name. `test_connection_lifecycle` alone uses the new `admit_disposable_database`: its slot databases live on a private cluster it starts, so `save_04` there must keep resolving; the helper refuses owner names and routes nothing.

This pass also removed four hand resolvers the grep does not spell: `test_secret_requirements`'s `slot_client` loop over `(secrets_endpoints, slot_endpoints)`, whose lambda answered every slot after `offline_gate_db` had routed slot 4; and the resolvers in `test_record_revelation_cli_pg` (slot 4), `test_tags_audit_pg` (slot 3, keeping its `all_slots` narrowing) and `test_player_identity_consumers_pg` (slot 1), which raised `AssertionError` or answered every slot. All four now route through `route_slot_to_disposable`, so an unrouted slot raises `RuntimeError` from `_routed_slot_dbname`.

Hand slot resolvers that remain outside this slice (a wider grep for `setattr(..., "slot_dbname" | "require_slot_dbname" | "resolve_dbname", ...)`; flagged to the coordinator for B2-9b): `test_api/test_narrative_continue_validation.py:708,1551,1559`, `test_api/test_wizard_confirmation_pg.py:226,306,307,363`, `test_api/test_wizard_weird_level.py:455`, `test_orrery/test_retrograde_embedding_pg.py:97-98`, `test_orrery/test_worker.py:435`, `test_orrery/test_retrograde_maturation.py:498,636`, `test_presence_roster_pg.py:560`, and the offline or live-only `test_wizard_agent.py:258,277,300,440,542`, `test_wizard_live.py:232,522`, `live_seed_schema_test.py:115`.

## The Private-Config Guard

`require_private_runtime_config` (`tests/scheduler_helpers.py`) now defines private positively. The resolved `[runtime].state_dir` must lie under the pytest temporary root (`PYTEST_DEBUG_TEMPROOT`, else `tempfile.gettempdir()`, as pytest roots `tmp_path`), and it must not equal the default `state_dir` anchored at any tree `git worktree list` prints, the owner's main checkout included. Before, it only had to differ from this checkout's, so from a builder's worktree a config naming the main checkout's `.nexus/runtime` by absolute path passed. `test_private_runtime_config_is_required` adds that case (the main checkout's absolute `state_dir`, refused as "keeps the state_dir of checkout") and a path outside the temporary root (refused as "outside the pytest temporary root"). It passes in the proof set and in the first converted-module batch below.

## Lanes Each Module Used

| Module | Lane |
| --- | --- |
| `tests/test_cli_inspect_pg.py` | 8018 (`gateway_lane` default; was a hard-set 8017, shared with `test_db_pool_pg`) |
| `tests/test_api/test_narrative_jobs_pg.py` | 8018 (`gateway_lane` default; was a hard-set 8016) |
| `tests/test_api/test_scheduler_corpus_pg.py` | 8018 (`gateway_lane` default) |
| `tests/test_api/test_scheduler_recovery_pg.py` | 8018 (its own listener) |
| `tests/test_api/test_seat_policy_jobs_pg.py` | 8019 (kept) |
| `tests/test_live_gate_clones_pg.py` | 8019 (kept) |
| `tests/test_api/test_attempt_manifest_pg.py` | 0 (OS-assigned, through `gateway_lane`) |
| `tests/test_scheduler_helpers_routing.py` | 0 (`gateway_lane` start refusal binds nothing; the close refusal serves a lane on port 0) |
| `tests/test_api/test_acceptance_staging_pg.py` | 0 (its supervisor-refusal listener) |
| `tests/proofs/proof_session_truth.py` | 8018 (default; was 8014) |
| every other module in the proof set | no gateway |

## The Order's PostgreSQL Proof Set

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_pg_disposable_target.py tests/test_live_gate_clones_pg.py tests/test_slot_routed_entrypoints.py tests/test_new_story_cache.py tests/test_api/test_session_truth_pg.py tests/test_api/test_seat_policy_jobs_pg.py tests/test_cli_inspect_pg.py tests/test_api/test_narrative_jobs_pg.py tests/test_api/test_scheduler_corpus_pg.py tests/test_api/test_attempt_manifest_pg.py tests/test_orrery/test_narration_job_fencing_pg.py tests/test_api/test_acceptance_staging_pg.py tests/test_orrery/test_claim_accounts_live.py tests/test_orrery/test_claim_consumption_live.py tests/test_scheduler_helpers_routing.py
```

The order's list plus `tests/test_scheduler_helpers_routing.py`. No failure and no skip; `test_new_story_cache.py::test_weird_level_round_trips_and_only_a_new_wizard_clears_it` passes (it failed on every `main` head the issue names).

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 68 targets: postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_775_errors_* x2, qa640_775_left_*, qa640_775_right_*, qa640_775_status_*, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_operator_*, qa640_800_turn_*, qa640_800b_inspect_*, qa640_814_seats_*, qa640_815_inspect_*, qa640_acceptance_* x22, qa640_claim_accounts_*, qa640_claim_consumption_*, qa640_lane_close_*, qa640_offline_gate_* x10, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*, qa676_* x7, qa838_genesis_weird_*, qa838_weird_level_*, qa885_entrypoints_*, qa885_transaction_writer_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
174 passed, 9 warnings in 173.90s (0:02:53)
```

Outside the audit: `test_session_truth_pg.py:154` clones owner `save_04` with `include_data` through `pg_dump`, a subprocess read the audit does not record. It belongs to slice B2-9b.

## `tests/proofs/proof_session_truth.py` Once on Lane 8018

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s -p tests.dbname_audit tests/proofs/proof_session_truth.py
```

```
Lane 8018; evidence directory /private/var/folders/r5/zvbnrwp55r7dctnkr9s3b3780000gn/T/pytest-of-pythagor/pytest-1663/test_disconnected_session_brow0/775-session-truth
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_775_browser_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed, 9 warnings in 91.87s (0:01:31)
```

Outside the audit: `proof_session_truth.py:90` clones owner `save_04` with `include_data` through `pg_dump`, a subprocess read the audit does not record. It belongs to slice B2-9b.

## The Converted Modules on PostgreSQL

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_scheduler_helpers_routing.py tests/test_pg_disposable_target.py tests/test_api/test_slot_settings.py tests/test_api/test_correspondence_pg.py tests/test_api/test_db_pool_pg.py tests/test_api/test_mock_wizard_responses.py tests/test_api/test_reader_character_provenance_pg.py tests/test_api/test_reader_draft_identity_pg.py tests/test_api/test_reader_place_provenance_pg.py tests/test_api/test_return_recap_pg.py tests/test_api/test_slot_mutation_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 45 targets: nexus_test_correspondence_* x2, nexus_test_issue_613_*, postgres, qa640_804_* x12, qa640_lane_close_*, qa640_offline_gate_* x6, qa832_recap_* x10, qa885_transaction_writer_*, qa946_character_* x3, qa950_place_* x2, qa951_identity_* x4, qa951_overwrite_*, test_slot_guard_462e9851a8e641d495344352853120ab
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
224 passed, 7 warnings in 45.73s
```

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_lore/test_baseline_fingerprint_refresh_pg.py tests/test_lore/test_logon_lazy_init.py tests/test_lore/test_pass2_chunk1369.py tests/test_lore/test_pass2_baseline_pg.py tests/test_lore/test_seat_blocks.py tests/test_lore/test_runtime_config.py tests/test_memnon_embedding_cache.py tests/test_correspondence_live.py tests/test_bootstrap_episode_pg.py tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_commit_handler_sync.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 51 targets: nexus_test_pass2_* x7, postgres, qa640_742_seat_test_*, qa640_908_fingerprint_*, qa640_compaction_retry_*, qa640_roster798_* x23, qa640_settings_stamp_*, qa655_wizard_23fecb9ccd, qa655_wizard_779202c51f, qa655_wizard_7aa478334a, qa655_wizard_99ef342e97, qa655_wizard_eebd174696, qa655_wizard_f4c4b917e3, qa947_episode_*, qa_lazy_logon_*, qa_model_cache_* x2, qa_pass2_corpus_*, qa_runtime_config_* x5
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [1] tests/test_correspondence_live.py: Set NEXUS_CONSPIRACY_E2E=1 for the live correspondence gate.
110 passed, 1 skipped, 9 warnings in 143.32s (0:02:23)
```

The skip is a live gate this pass did not open. Outside the audit: `pg_dump` reads of owner `save_04` (`test_seat_blocks.py:398`, `test_baseline_fingerprint_refresh_pg.py:31`) and `save_01` (`test_pass2_chunk1369.py:39`) for `include_data` clones.

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_orrery/test_retrograde_constraints_pg.py tests/test_orrery/test_retrograde_projects_live.py tests/test_orrery/test_need_clock_anchor_pg.py tests/test_orrery/test_event_sources_pg.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_tag_library.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_orrery_tag_validation_pg.py tests/test_database_contract.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 40 targets: postgres, qa638_*, qa640_* x18, qa640_807_latest_playable_*, qa640_807_maturation_boundary_*, qa640_807_reapply_*, qa640_811_full_clear_only_*, qa640_811_gaia_scene_*, qa640_811_scene_clear_only_*, qa640_811_scene_kind_*, qa640_811_scene_pin_*, qa640_811_tag_library_*, qa640_connection_contract, qa640_issue601_* x4, qa640_projects799_*, qa640_raw_url_contract, qa649_*, qa885_tag_library_* x2, test_event_sources_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [1] tests/test_orrery/test_gaia_registry_schema_pg.py:347: Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.
152 passed, 1 skipped, 5 warnings in 70.92s (0:01:10)
```

Outside the audit: the `pg_dump` read of owner `save_02` (`test_retrograde_projects_live.py:71`) for its `include_data` clone.

The four modules whose hand resolvers this pass removed:

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_api/test_secret_requirements.py tests/test_record_revelation_cli_pg.py tests/test_tags_audit_pg.py tests/test_player_identity_consumers_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 18 targets: postgres, qa640_811_tags_audit_* x5, qa640_811_tags_audit_nocol_*, qa640_offline_gate_* x2, qa_identity_surface_23afcf7cb3, qa_identity_surface_403d90f2f5, qa_identity_surface_58f14b3194, qa_identity_surface_64a7065e20, qa_identity_surface_6924920515, qa_identity_surface_726e846c81, qa_identity_surface_be525a6028, qa_player_identity_197d6478df, qa_wt664_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
39 passed, 7 warnings in 20.38s
```

`tests/test_connection_lifecycle.py` at the same SHA (with only this file modified in the tree) passes without the audit and errors under it, as it did at `2c25d59a`, because the audit refuses any database named `save_04`, including the one on the test's private cluster:

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed, 5 warnings in 25.34s

NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, save_04
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: FAILED: owner targets: save_04 (psycopg2) from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
ERROR tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
5 warnings, 1 error in 2.33s
```

## `tests/test_api` on PostgreSQL

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_api
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 198 targets: nexus_test_continue_* x10, nexus_test_correspondence_* x2, nexus_test_issue_613_*, nexus_test_retry_* x17, postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_775_errors_* x2, qa640_775_left_*, qa640_775_right_*, qa640_775_status_*, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_kill_*, qa640_800_renew_* x4, qa640_800_turn_*, qa640_800b_inspect_*, qa640_804_* x12, qa640_814_backfill_*, qa640_814_benchmark_*, qa640_814_seats_*, qa640_937_budget_* x2, qa640_938_usage_* x2, qa640_acceptance_* x44, qa640_offline_gate_* x60, qa640_reader_assets_*, qa654_*, qa832_recap_* x10, qa885_orrery_dev_*, qa946_character_* x3, qa950_place_* x2, qa951_identity_* x4, qa951_overwrite_*, qa_wt625_*, qa_wt625_empty_*, save_02, test_slot_guard_69b606779a064a72b55b8a989168fc82
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: FAILED: owner targets: save_02 (psycopg2) from tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_adjacent, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunk_404, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunks_by_season_episode, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_episodes_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_latest_chunk_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_outline_and_chunk_by_id, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_seasons_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_characters_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_current_place, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_factions_live_schema, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_places_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_relationships_and_psychology, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_zones_shape
SKIPPED [1] tests/test_api/test_conversations.py:377: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_api/test_narrative_summary_paid_pg.py: Requires explicit two-call summary authorization
SKIPPED [1] tests/test_api/test_secrets_endpoints.py:268: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_api/test_secrets_endpoints.py:279: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
18 failed, 847 passed, 4 skipped, 9 warnings in 408.56s (0:06:48)
```

The 18 failing tests, by their traceback headers in the same log:

```
____ test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit _____
____________________ TestNarrativeReads.test_seasons_shape _____________________
____________________ TestNarrativeReads.test_episodes_shape ____________________
__________________ TestNarrativeReads.test_latest_chunk_shape __________________
_______________ TestNarrativeReads.test_outline_and_chunk_by_id ________________
______________________ TestNarrativeReads.test_chunk_404 _______________________
_______________________ TestNarrativeReads.test_adjacent _______________________
____________________ TestNarrativeReads.test_context_shape _____________________
_______________ TestNarrativeReads.test_chunks_by_season_episode _______________
_____________________ TestWorldReads.test_characters_shape _____________________
_______________________ TestWorldReads.test_places_shape _______________________
_______________________ TestWorldReads.test_zones_shape ________________________
___________________ TestWorldReads.test_factions_live_schema ___________________
______________________ TestWorldReads.test_current_place _______________________
_______________ TestWorldReads.test_relationships_and_psychology _______________
_ test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs] _
__________ test_scheduler_gateway_sigkill_resumes_inflight_experience __________
___________ test_seat_policy_migration_backfills_save04_active_jobs ____________
```

Each owner target in that report was refused at connect time, before libpq opened a connection. The four skips are the live_llm or paid-authorization gates.

### Owner Reads This Branch Retired

- `test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision`: read owner `save_05` through a resolver the fixture's hand patch missed; `recap_slot` now routes slot 5 through the shared sweep, and the test passes on its clone.
- `test_wizard_chat_validation.py::test_repeated_trait_confirmation_reports_wildcard_state` and `::test_trait_choice_outside_character_reports_current_state`: their `POST /api/story/new/chat` read owner `save_04` through `wizard_chat`'s import-bound `slot_dbname`; `offline_gate_db` now sweeps that binding, so both reach the clone.

### Every Remaining Failure by Class

| Class | Tests | Owner |
| --- | --- | --- |
| Reads owner `save_02` outright; the audit refuses it | `test_reader_asset_endpoints.py`: the 14 `TestNarrativeReads`/`TestWorldReads` tests | slice B2-9b |
| `save_04` include_data clone whose job 3 carries a persisted paid model (`gpt-5.6-terra`) that the TEST guard refuses, so the render never reaches the TEST provider | `test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]`, `test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience` | slice B2-9b |
| `save_04` corpus clone (a full `pg_dump` of owner `save_04`, `test_seat_policy_backfill_pg.py:22-36`) that expects migration 126 still pending; the fleet already carries it (`assert (0 == 0 and 0 >= 1)` on `applied >= 1`) | `test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs` | flagged to the coordinator for B2-9b (a `save_04` corpus-clone case); fails identically on `main` |
| Test double lags the production signature (`gated_real_commit() got an unexpected keyword argument 'bind_session_id'`) | `test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit` | unmapped; fails identically on `main` |

The four non-reader failures on a `git archive` export of `origin/main` `ac2a585a`, run from the export with `PYTHONPATH` set to it (`nexus` imported from the export):

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit --tb=short --basetemp=<scratch> "tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]" tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs tests/test_api/test_narrative_post_commit.py
```

```
_ test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs] _
tests/test_api/test_scheduler_recovery_pg.py:392: in test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt
tests/test_api/test_scheduler_pg.py:41: in wait_until
E   AssertionError: Scheduler did not reach the expected durable state
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
__________ test_scheduler_gateway_sigkill_resumes_inflight_experience __________
tests/test_api/test_scheduler_recovery_pg.py:531: in test_scheduler_gateway_sigkill_resumes_inflight_experience
tests/test_api/test_scheduler_pg.py:41: in wait_until
E   AssertionError: Scheduler did not reach the expected durable state
nexus down (8018): nothing running
___________ test_seat_policy_migration_backfills_save04_active_jobs ____________
tests/test_api/test_seat_policy_backfill_pg.py:89: in test_seat_policy_migration_backfills_save04_active_jobs
E   assert (0 == 0 and 0 >= 1)
____ test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit _____
tests/test_api/test_narrative_post_commit.py:404: in test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
E   assert False
tests/test_api/test_narrative_post_commit.py:428: in test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
E   AssertionError: []
E   assert False
ERROR Failed to commit narrative: test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit.<locals>.gated_real_commit() got an unexpected keyword argument 'bind_session_id'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_800_kill_*, qa640_800_renew_*, qa640_814_backfill_*, qa640_offline_gate_* x2
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
FAILED tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs
FAILED tests/test_api/test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
4 failed, 4 passed, 7 warnings in 34.96s
```

The four passes are the other tests in `test_narrative_post_commit.py`.

Outside the audit, the `pg_dump` reads of owner `save_04` in this module set: `test_seat_policy_backfill_pg.py:22-36` (a full custom-format dump restored into `qa640_814_backfill_*`) and `test_scheduler_recovery_pg.py:296` and `:444` (`disposable_slot_database(..., source_db="save_04", include_data=True)`).

### The Two Recovery Failures on This Branch

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit --tb=short --basetemp=<scratch> "tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]" tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
```

```
_ test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs] _
tests/test_api/test_scheduler_recovery_pg.py:392: in test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt
tests/test_api/test_scheduler_pg.py:41: in wait_until
E   AssertionError: Scheduler did not reach the expected durable state
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
__________ test_scheduler_gateway_sigkill_resumes_inflight_experience __________
tests/test_api/test_scheduler_recovery_pg.py:533: in test_scheduler_gateway_sigkill_resumes_inflight_experience
tests/test_api/test_scheduler_pg.py:41: in wait_until
E   AssertionError: Scheduler did not reach the expected durable state
nexus down (8018): nothing running
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_800_kill_*, qa640_800_renew_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
2 failed, 5 warnings in 27.59s
```

Both fail at the same waits as on `main` above: the sigkill test's `wait_until` for `Experience render received; response delay=4` in `mock_openai.log` (branch line 533, `main` line 531; the branch adds two lines above it), and the preempted-lease test's `wait_until(finished)` at line 392. The cause on both is job 3's persisted `gpt-5.6-terra`, refused by the TEST guard.

The `nexus down (8018): nothing running` line prints the same text on both sides, so the text alone does not show routing. What does: at `f65459e5` the closing call is

```
tests/test_api/test_scheduler_recovery_pg.py:610-611
                down = subprocess.run(
                    [sys.executable, "-m", "tests.slot_routed_cli", "down"],
```

(`main` runs `[sys.executable, "-m", "nexus.cli", "down"]` at its line 609), and the test asserts `down.returncode == 0` before it prints that line. `tests.slot_routed_cli` refuses to start without the route; the same entry point with `NEXUS_ROUTED_SLOT=4`, `NEXUS_ROUTED_SLOT_DATABASE` unset and a scratch runtime config exits 1 before `nexus.cli` loads:

```
env -u NEXUS_ROUTED_SLOT_DATABASE NEXUS_ROUTED_SLOT=4 NEXUS_RUNTIME_CONFIG=<scratch>/probe/runtime.toml PYTHONPATH=$PWD $PY -m tests.slot_routed_cli down
    raise RuntimeError(
RuntimeError: A routed entry point needs NEXUS_ROUTED_SLOT_DATABASE: it serves only a disposable clone and never an owner slot
exit 1
```

So the printed line shows the routed child ran with its route.

The rewritten recovery child runner starts and serves before that failure. Lines 1-9 of the branch child's `gateway-first.log`, then lines 27-28 (the end of its render traceback):

```
INFO:     Started server process [30239]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on socket ('127.0.0.1', 8018) (Press CTRL+C to quit)
INFO:     127.0.0.1:61803 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:61804 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:61806 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:61807 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:61808 - "GET /health HTTP/1.1" 200 OK
    raise ProviderForbiddenInTests(
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
```

The child's failed render touched the clone, not the owner: after the runs, owner `save_04` still holds job 3 untouched (read-only query):

```
psql -X -d save_04 -c "SELECT id, state, attempts, updated_at FROM character_experience_jobs WHERE id = 3"
 id | state  | attempts |          updated_at
----+--------+----------+-------------------------------
  3 | queued |        0 | 2026-08-21 00:51:41.719029-04
```

## Offline Suites

```
$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2522 passed, 388 skipped, 8 warnings in 342.32s (0:05:42)

$PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 737 skipped, 7 warnings in 28.75s

$PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.04s
```

## Static Checks on the Changed Files

The file set is `git diff --name-only origin/main...HEAD -- '*.py'` at `f65459e5`: 49 files (48 modified, 1 added, `tests/test_scheduler_helpers_routing.py`). The baseline is each file's `origin/main` `ac2a585a` version from a `git archive` export, checked from the export's root with the same interpreter and the export's own `.flake8`.

- Black: `49 files would be left unchanged.`
- flake8: 118 findings on the branch against 120 on `main`'s versions of the 48 existing files; the added file has none. Grouped by file and code, no group grows: the two fewer are one `E402` in `tests/scheduler_helpers.py` and one `E501` in `tests/test_api/test_acceptance_staging_pg.py`. The rest are pre-existing `E501` and pytest-fixture `F401`/`F811`.
- mypy (`--explicit-package-bases`, errors reported in the changed files only): 154 on the branch and 154 on `main`'s versions, identical when grouped by file and error code; the added file has none.

## Review Round (Astra)

Astra's P2 (`tests/scheduler_helpers.py:96`): the private-runtime guard took `PYTEST_DEBUG_TEMPROOT`, else `tempfile.gettempdir()`, as the only place a private `state_dir` could lie, so a run with `--basetemp` elsewhere refused the config `private_runtime_config(tmp_path, ...)` wrote, and the gateway tests failed before startup.

The fix: a session-scoped autouse fixture in `tests/conftest.py` (`_register_private_runtime_root`) records `tmp_path_factory.getbasetemp()` through `scheduler_helpers.register_pytest_basetemp`. The guard admits a `state_dir` under that registered base or under `tempfile.gettempdir()`, and nowhere else; outside a pytest session nothing is registered and only the system temp directory counts. `PYTEST_DEBUG_TEMPROOT` no longer counts on its own, because pytest's base temp already lies under it when it is set. The refusals of an unset variable, the checkout's `nexus.toml`, and every `git worktree list` tree's default `state_dir` run before this check, unchanged. This supersedes the temporary-root sentence in "The Private-Config Guard" above.

The new `tests/test_scheduler_helpers_basetemp.py` runs `tests/test_scheduler_helpers_routing.py` in a child pytest with `TMPDIR` set to one directory and `--basetemp` set to a sibling, so every child `tmp_path` lies outside the child's `tempfile.gettempdir()`. It requires `test_private_runtime_config_is_required` (the private config admitted; the main checkout's `state_dir` and a directory under `$HOME` refused) and both gateway-lane tests (the close-time one serves a lane, so it is required when `NEXUS_RUN_POSTGRES=1`) to pass, and checks the child's `tmp_path` directories were made under the base temp.

The review's failure, reproduced at `c92173e6` before the fix (`$S` is this fixer's scratch directory under `/private/tmp/claude-501/...`, outside `tempfile.gettempdir()`, which is `/var/folders/r5/.../T`):

```text
$ $PY -m pytest -q tests/test_scheduler_helpers_routing.py::test_private_runtime_config_is_required --basetemp=$S/repro-basetemp
E           RuntimeError: NEXUS_RUNTIME_CONFIG='/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-9a-fix/repro-basetemp/test_private_runtime_config_is0/runtime.toml' puts state_dir at '/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-9a-fix/repro-basetemp/test_private_runtime_config_is0/runtime', outside the pytest temporary root '/private/var/folders/r5/zvbnrwp55r7dctnkr9s3b3780000gn/T'; point it into the test's tmp_path
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_scheduler_helpers_routing.py::test_private_runtime_config_is_required
1 failed, 7 warnings in 2.41s

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_scheduler_helpers_basetemp.py
E         FAILED tests/test_scheduler_helpers_routing.py::test_private_runtime_config_is_required
E         FAILED tests/test_scheduler_helpers_routing.py::test_gateway_lane_refuses_to_close_without_a_private_config
E         =================== 2 failed, 12 passed, 7 warnings in 4.72s ===================
FAILED tests/test_scheduler_helpers_basetemp.py::test_routing_contract_passes_under_a_basetemp_outside_the_system_temp
1 failed in 5.10s
```

After the fix:

```text
$ $PY -m pytest -q tests/test_scheduler_helpers_routing.py::test_private_runtime_config_is_required --basetemp=$S/repro-basetemp
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed, 7 warnings in 2.36s

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_scheduler_helpers_basetemp.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed, 5 warnings in 6.10s
```

The gateway-lane modules and the new test, with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset:

```text
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_scheduler_helpers_routing.py tests/test_cli_inspect_pg.py tests/test_api/test_narrative_jobs_pg.py tests/test_api/test_scheduler_corpus_pg.py tests/test_scheduler_helpers_basetemp.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 19 targets: postgres, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_turn_*, qa640_815_inspect_*, qa640_acceptance_* x3, qa640_lane_close_*, qa640_offline_gate_* x10
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
32 passed, 9 warnings in 76.26s (0:01:16)
```

Static checks on the three changed files (`tests/scheduler_helpers.py`, `tests/conftest.py`, `tests/test_scheduler_helpers_basetemp.py`):

```text
All done! ✨ 🍰 ✨
3 files would be left unchanged.
black=0
flake8=0
Success: no issues found in 3 source files
```
