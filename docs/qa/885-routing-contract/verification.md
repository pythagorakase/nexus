# Verification: One Routing Contract for Every Test (#885 B2-9a)

Fix pass on top of `2c25d59a` on `claude/885-routing-contract` (base `origin/main` `ac2a585a`, B2-8, #1042). Every PostgreSQL run below loaded `-p tests.dbname_audit`, ran with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset, and used the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`) with `nexus` imported from this worktree. No paid provider was called; every provider consumer ran on TEST. Logs sit in the session scratchpad under `885-B2-9a-fix/`. Each fenced tail lists whole lines selected from its run log with `grep` (the guard line, every `dbname audit` line, skip reasons, failures and the summary; for the recovery runs also the traceback locations and errors); no line is edited or shortened.

## Item 7's Grep

```
grep -rn "slot_endpoints.slot_dbname\|VALID_DBNAMES" tests/ | cut -d: -f1 | sort | uniq -c
   3 tests/pg_fixtures.py
   1 tests/scheduler_helpers.py
   7 tests/test_pg_disposable_target.py
   1 tests/test_scheduler_helpers_routing.py
   2 tests/test_slot_routed_entrypoints.py
```

Only the shared helpers and their tests remain. The 30 modules that widened `VALID_DBNAMES` by hand now call `route_slot_to_disposable` (or `route_slots_to_disposable`); module-scoped fixtures route under their own `pytest.MonkeyPatch` (synthesis note 5). Each routes the slot its code under test resolves (for example slot 1 in `test_orrery_tag_validation_pg`, 2 in `test_retrograde_projects_live`, 3 in `test_retrograde_constraints_pg` and `test_need_clock_anchor_pg`, 4 in the reader and scheduler tests), else slot 5. The hand-written `slot_dbname` lambdas those fixtures carried (`test_reader_*_provenance_pg`, `test_return_recap_pg`, `test_reader_draft_identity_pg`, `test_slot_mutation_guard`, `test_pass2_baseline_pg`, `test_mock_wizard_responses`, and `test_slot_settings`'s `slot_endpoints` patch) are gone. `test_slot_mutation_guard` routes every slot to its one clone, because slot selection resolves every slot's name. `test_connection_lifecycle` alone uses the new `admit_disposable_database`: its slot databases live on a private cluster it starts, so `save_04` there must keep resolving; the helper refuses owner names and routes nothing.

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
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_pg_disposable_target.py tests/test_live_gate_clones_pg.py tests/test_slot_routed_entrypoints.py tests/test_new_story_cache.py tests/test_api/test_session_truth_pg.py tests/test_api/test_seat_policy_jobs_pg.py tests/test_cli_inspect_pg.py tests/test_api/test_narrative_jobs_pg.py tests/test_api/test_scheduler_corpus_pg.py tests/test_api/test_attempt_manifest_pg.py tests/test_orrery/test_narration_job_fencing_pg.py tests/test_api/test_acceptance_staging_pg.py tests/test_orrery/test_claim_accounts_live.py tests/test_orrery/test_claim_consumption_live.py tests/test_scheduler_helpers_routing.py
```

The order's list plus `tests/test_scheduler_helpers_routing.py`. No failure and no skip; `test_new_story_cache.py::test_weird_level_round_trips_and_only_a_new_wizard_clears_it` passes (it failed on every `main` head the issue names).

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 68 targets: postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_775_errors_* x2, qa640_775_left_*, qa640_775_right_*, qa640_775_status_*, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_operator_*, qa640_800_turn_*, qa640_800b_inspect_*, qa640_814_seats_*, qa640_815_inspect_*, qa640_acceptance_* x22, qa640_claim_accounts_*, qa640_claim_consumption_*, qa640_lane_close_*, qa640_offline_gate_* x10, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*, qa676_* x7, qa838_genesis_weird_*, qa838_weird_level_*, qa885_entrypoints_*, qa885_transaction_writer_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
174 passed, 9 warnings in 169.47s (0:02:49)
```

Outside the audit: `test_session_truth_pg.py:154` clones owner `save_04` with `include_data` through `pg_dump`, a subprocess read the audit does not record. It belongs to slice B2-9b.

## `tests/proofs/proof_session_truth.py` Once on Lane 8018

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s -p tests.dbname_audit tests/proofs/proof_session_truth.py
```

```
Lane 8018; evidence directory /private/var/folders/r5/zvbnrwp55r7dctnkr9s3b3780000gn/T/pytest-of-pythagor/pytest-1656/test_disconnected_session_brow0/775-session-truth
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_775_browser_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed, 9 warnings in 91.51s (0:01:31)
```

Outside the audit: `proof_session_truth.py:90` clones owner `save_04` with `include_data` through `pg_dump`, a subprocess read the audit does not record. It belongs to slice B2-9b.

## The Converted Modules on PostgreSQL

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_scheduler_helpers_routing.py tests/test_pg_disposable_target.py tests/test_api/test_slot_settings.py tests/test_api/test_correspondence_pg.py tests/test_api/test_db_pool_pg.py tests/test_api/test_mock_wizard_responses.py tests/test_api/test_reader_character_provenance_pg.py tests/test_api/test_reader_draft_identity_pg.py tests/test_api/test_reader_place_provenance_pg.py tests/test_api/test_return_recap_pg.py tests/test_api/test_slot_mutation_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 45 targets: nexus_test_correspondence_* x2, nexus_test_issue_613_*, postgres, qa640_804_* x12, qa640_lane_close_*, qa640_offline_gate_* x6, qa832_recap_* x10, qa885_transaction_writer_*, qa946_character_* x3, qa950_place_* x2, qa951_identity_* x4, qa951_overwrite_*, test_slot_guard_a3ec34dd209b48af86e37c2a11e08249
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
224 passed, 7 warnings in 45.09s
```

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_lore/test_baseline_fingerprint_refresh_pg.py tests/test_lore/test_logon_lazy_init.py tests/test_lore/test_pass2_chunk1369.py tests/test_lore/test_pass2_baseline_pg.py tests/test_lore/test_seat_blocks.py tests/test_lore/test_runtime_config.py tests/test_memnon_embedding_cache.py tests/test_correspondence_live.py tests/test_bootstrap_episode_pg.py tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_commit_handler_sync.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 51 targets: nexus_test_pass2_* x7, postgres, qa640_742_seat_test_*, qa640_908_fingerprint_*, qa640_compaction_retry_*, qa640_roster798_* x23, qa640_settings_stamp_*, qa655_wizard_29db8033f8, qa655_wizard_5401249a91, qa655_wizard_7f9f117dc6, qa655_wizard_b390e32db1, qa655_wizard_bf69a11816, qa655_wizard_c0fb22ab19, qa947_episode_*, qa_lazy_logon_*, qa_model_cache_* x2, qa_pass2_corpus_*, qa_runtime_config_* x5
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
110 passed, 1 skipped, 9 warnings in 142.60s (0:02:22)
```

The skip is `tests/test_correspondence_live.py` (`Set NEXUS_CONSPIRACY_E2E=1 for the live correspondence gate.`), a live gate this pass did not open. Outside the audit: `pg_dump` reads of owner `save_04` (`test_seat_blocks.py:398`, `test_baseline_fingerprint_refresh_pg.py:31`) and `save_01` (`test_pass2_chunk1369.py:39`) for `include_data` clones.

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_orrery/test_retrograde_constraints_pg.py tests/test_orrery/test_retrograde_projects_live.py tests/test_orrery/test_need_clock_anchor_pg.py tests/test_orrery/test_event_sources_pg.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_tag_library.py tests/test_orrery/test_gaia_registry_schema_pg.py tests/test_orrery_tag_validation_pg.py tests/test_database_contract.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 40 targets: postgres, qa638_*, qa640_* x18, qa640_807_latest_playable_*, qa640_807_maturation_boundary_*, qa640_807_reapply_*, qa640_811_full_clear_only_*, qa640_811_gaia_scene_*, qa640_811_scene_clear_only_*, qa640_811_scene_kind_*, qa640_811_scene_pin_*, qa640_811_tag_library_*, qa640_connection_contract, qa640_issue601_* x4, qa640_projects799_*, qa640_raw_url_contract, qa649_*, qa885_tag_library_* x2, test_event_sources_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [1] tests/test_orrery/test_gaia_registry_schema_pg.py:347: Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.
152 passed, 1 skipped, 5 warnings in 71.30s (0:01:11)
```

Outside the audit: the `pg_dump` read of owner `save_02` (`test_retrograde_projects_live.py:71`) for its `include_data` clone.

`tests/test_connection_lifecycle.py` passes without the audit (`1 passed, 5 warnings in 25.35s`). Under the audit it errors the same way on this branch and on a `git archive` export of `2c25d59a`, because the audit refuses any database named `save_04`, including the one on the test's private cluster:

```
dbname audit: FAILED: owner targets: save_04 (psycopg2) from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
ERROR tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
```

## `tests/test_api` on PostgreSQL

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 198 targets: nexus_test_continue_* x10, nexus_test_correspondence_* x2, nexus_test_issue_613_*, nexus_test_retry_* x17, postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_775_errors_* x2, qa640_775_left_*, qa640_775_right_*, qa640_775_status_*, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_kill_*, qa640_800_renew_* x4, qa640_800_turn_*, qa640_800b_inspect_*, qa640_804_* x12, qa640_814_backfill_*, qa640_814_benchmark_*, qa640_814_seats_*, qa640_937_budget_* x2, qa640_938_usage_* x2, qa640_acceptance_* x44, qa640_offline_gate_* x60, qa640_reader_assets_*, qa654_*, qa832_recap_* x10, qa885_orrery_dev_*, qa946_character_* x3, qa950_place_* x2, qa951_identity_* x4, qa951_overwrite_*, qa_wt625_*, qa_wt625_empty_*, save_02, test_slot_guard_81e4b777bf47414a91fd1efd98d4d03b
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: FAILED: owner targets: save_02 (psycopg2) from tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_adjacent, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunk_404, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunks_by_season_episode, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_episodes_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_latest_chunk_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_outline_and_chunk_by_id, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_seasons_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_characters_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_current_place, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_factions_live_schema, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_places_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_relationships_and_psychology, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_zones_shape
FAILED tests/test_api/test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_seasons_shape
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_episodes_shape
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_latest_chunk_shape
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_outline_and_chunk_by_id
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunk_404
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_adjacent
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunks_by_season_episode
FAILED tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_characters_shape
FAILED tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_places_shape
FAILED tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_zones_shape
FAILED tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_factions_live_schema
FAILED tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_current_place
FAILED tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_relationships_and_psychology
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
FAILED tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs
18 failed, 847 passed, 4 skipped, 9 warnings in 408.64s (0:06:48)
```

Each owner target in that report was refused at connect time, before libpq opened a connection. The four skips are the live_llm or paid-authorization gates in `test_conversations.py`, `test_secrets_endpoints.py` and `test_narrative_summary_paid_pg.py` (`Requires explicit two-call summary authorization`).

### Owner Reads This Branch Retired

- `test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision`: read owner `save_05` through a resolver the fixture's hand patch missed; `recap_slot` now routes slot 5 through the shared sweep, and the test passes on its clone.
- `test_wizard_chat_validation.py::test_repeated_trait_confirmation_reports_wildcard_state` and `::test_trait_choice_outside_character_reports_current_state`: their `POST /api/story/new/chat` read owner `save_04` through `wizard_chat`'s import-bound `slot_dbname`; `offline_gate_db` now sweeps that binding, so both reach the clone.

### Every Remaining Failure by Class

| Class | Tests | Owner |
| --- | --- | --- |
| Reads owner `save_02` outright; the audit refuses it | `test_reader_asset_endpoints.py`: the 14 `TestNarrativeReads`/`TestWorldReads` tests | slice B2-9b |
| `save_04` include_data clone whose job 3 carries a persisted paid model (`gpt-5.6-terra`) that the TEST guard refuses, so the render never reaches the TEST provider | `test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]`, `test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience` | slice B2-9b |
| `save_04` clone expects a pending migration that the fleet already carries (`assert (0 == 0 and 0 >= 1)` on `applied >= 1`) | `test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs` | unmapped; pre-existing |
| Test double lags the production signature (`gated_real_commit() got an unexpected keyword argument 'bind_session_id'`) | `test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit` | unmapped; pre-existing |

### The Two Recovery Failures, Branch and `main`

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit --tb=short --basetemp=<scratch> "tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]" tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
```

This branch (working tree of this fix pass):

```
_ test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs] _
tests/test_api/test_scheduler_recovery_pg.py:392: in test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt
    wait_until(finished)
tests/test_api/test_scheduler_pg.py:41: in wait_until
    raise AssertionError("Scheduler did not reach the expected durable state")
E   AssertionError: Scheduler did not reach the expected durable state
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
__________ test_scheduler_gateway_sigkill_resumes_inflight_experience __________
tests/test_api/test_scheduler_recovery_pg.py:533: in test_scheduler_gateway_sigkill_resumes_inflight_experience
    wait_until(
tests/test_api/test_scheduler_pg.py:41: in wait_until
    raise AssertionError("Scheduler did not reach the expected durable state")
E   AssertionError: Scheduler did not reach the expected durable state
nexus down (8018): nothing running
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_800_kill_*, qa640_800_renew_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
2 failed, 5 warnings in 27.31s
```

A `git archive` export of `origin/main` `ac2a585a` (`PYTHONPATH` set to the export):

```
_ test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs] _
tests/test_api/test_scheduler_recovery_pg.py:392: in test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt
    wait_until(finished)
tests/test_api/test_scheduler_pg.py:41: in wait_until
    raise AssertionError("Scheduler did not reach the expected durable state")
E   AssertionError: Scheduler did not reach the expected durable state
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
__________ test_scheduler_gateway_sigkill_resumes_inflight_experience __________
tests/test_api/test_scheduler_recovery_pg.py:531: in test_scheduler_gateway_sigkill_resumes_inflight_experience
    wait_until(
tests/test_api/test_scheduler_pg.py:41: in wait_until
    raise AssertionError("Scheduler did not reach the expected durable state")
E   AssertionError: Scheduler did not reach the expected durable state
nexus down (8018): nothing running
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa640_800_kill_*, qa640_800_renew_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
2 failed, 7 warnings in 28.03s
```

Both fail at the same wait: the sigkill test's `wait_until` for `Experience render received; response delay=4` in `mock_openai.log` (branch line 533, `main` line 531; the branch adds two lines above it), and the preempted-lease test's `wait_until(finished)` at line 392. The cause on both is job 3's persisted `gpt-5.6-terra`, refused by the TEST guard. On the branch the closing `nexus down` child now runs through `tests.slot_routed_cli` (`nexus down (8018): nothing running`).

The rewritten recovery child runner starts and serves before that failure. Lines 1-9 of the branch child's `gateway-first.log`, then lines 26-27 (the end of its render traceback):

```
INFO:     Started server process [38974]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on socket ('127.0.0.1', 8018) (Press CTRL+C to quit)
INFO:     127.0.0.1:57113 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:57114 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:57116 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:57117 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:57118 - "GET /health HTTP/1.1" 200 OK
    raise ProviderForbiddenInTests(
nexus.config.provider_guard.ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1
```

The child's failed render touched the clone, not the owner: after the run, owner `save_04` still holds job 3 untouched (read-only query):

```
psql -X -d save_04 -c "SELECT id, state, attempts, updated_at FROM character_experience_jobs WHERE id = 3"
 id | state  | attempts |          updated_at
----+--------+----------+-------------------------------
  3 | queued |        0 | 2026-08-21 00:51:41.719029-04
```

On `main`, the same child logs its pool target (lines 2-6 of its `gateway-first.log`):

```
INFO:     Started server process [41599]
INFO:     Waiting for application startup.
INFO Created connection pool for database: qa640_800_kill_c37aa1603cfa
INFO:     Application startup complete.
INFO:     Uvicorn running on socket ('127.0.0.1', 8018) (Press CTRL+C to quit)
```

## Offline Suites

```
$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2522 passed, 388 skipped, 8 warnings in 340.64s (0:05:40)

$PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 737 skipped, 7 warnings in 28.58s

$PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.06s
```

## Static Checks on the Changed Files

- Black: `36 files would be left unchanged.`
- flake8: no new finding. The 36 changed files carry 80 findings, the same count as their versions at `2c25d59a` (E501 and pytest-fixture F401/F811 already present).
- mypy (`--explicit-package-bases`): no error that the files' `2c25d59a` versions lack. `tests/scheduler_helpers.py`, `tests/pg_fixtures.py`, `tests/test_scheduler_helpers_routing.py` and `tests/test_pg_disposable_target.py` check clean.
