# Verification: One Routing Contract for Every Test (#885 B2-9a)

Head `d47f4f92` on `claude/885-routing-contract`, rebased onto `origin/main` `ac2a585a` (B2-8, #1042). Every PostgreSQL run below loaded `-p tests.dbname_audit`, ran with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset, and used the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`) with `nexus` imported from this worktree. No paid provider was called; every provider consumer ran on TEST.

## Lanes Each Module Used

| Module | Lane |
| --- | --- |
| `tests/test_cli_inspect_pg.py` | 8018 (`gateway_lane` default; was a hard-set 8017, shared with `test_db_pool_pg`) |
| `tests/test_api/test_narrative_jobs_pg.py` | 8018 (`gateway_lane` default; was a hard-set 8016) |
| `tests/test_api/test_scheduler_corpus_pg.py` | 8018 (`gateway_lane` default) |
| `tests/test_api/test_seat_policy_jobs_pg.py` | 8019 (kept) |
| `tests/test_live_gate_clones_pg.py` | 8019 (kept) |
| `tests/test_api/test_attempt_manifest_pg.py` | 0 (OS-assigned, through `gateway_lane`) |
| `tests/test_scheduler_helpers_routing.py` | 0 (`gateway_lane` refusal case; refuses before binding) |
| `tests/test_api/test_acceptance_staging_pg.py` | 0 (its supervisor-refusal listener) |
| `tests/proofs/proof_session_truth.py` | 8018 (default; was 8014) |
| every other module in the proof set | no gateway |

## The Order's PostgreSQL Proof Set

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_pg_disposable_target.py tests/test_live_gate_clones_pg.py tests/test_slot_routed_entrypoints.py tests/test_new_story_cache.py tests/test_api/test_session_truth_pg.py tests/test_api/test_seat_policy_jobs_pg.py tests/test_cli_inspect_pg.py tests/test_api/test_narrative_jobs_pg.py tests/test_api/test_scheduler_corpus_pg.py tests/test_api/test_attempt_manifest_pg.py tests/test_orrery/test_narration_job_fencing_pg.py tests/test_api/test_acceptance_staging_pg.py tests/test_orrery/test_claim_accounts_live.py tests/test_orrery/test_claim_consumption_live.py tests/test_scheduler_helpers_routing.py
```

The order's list plus the new `tests/test_scheduler_helpers_routing.py`. No failure and no skip; `test_new_story_cache.py::test_weird_level_round_trips_and_only_a_new_wizard_clears_it` passes (it failed on every `main` head the issue names).

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 67 targets: postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_775_errors_* x2, qa640_775_left_*, qa640_775_right_*, qa640_775_status_*, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_operator_*, qa640_800_turn_*, qa640_800b_inspect_*, qa640_814_seats_*, qa640_815_inspect_*, qa640_acceptance_* x22, qa640_claim_accounts_*, qa640_claim_consumption_*, qa640_offline_gate_* x10, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*, qa676_* x7, qa838_genesis_weird_*, qa838_weird_level_*, qa885_entrypoints_*, qa885_transaction_writer_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
166 passed, 9 warnings in 166.21s (0:02:46)
```

## `tests/proofs/proof_session_truth.py` Once on Lane 8018

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s -p tests.dbname_audit tests/proofs/proof_session_truth.py
```

```
Lane 8018; evidence directory <pytest tmp_path>/775-session-truth
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_775_browser_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed, 9 warnings in 92.00s (0:01:31)
```

## `tests/test_api` on PostgreSQL

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api
```

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 199 targets: nexus_test_continue_* x10, nexus_test_correspondence_* x2, nexus_test_issue_613_*, nexus_test_retry_* x17, postgres, qa640_764_jobs_*, qa640_764_manifest_*, qa6 ... (list shortened here)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
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
FAILED tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
FAILED tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs
19 failed, 846 passed, 4 skipped, 9 warnings in 405.06s (0:06:45)
```

Audit owner-target report (each attempt was refused at connect time, before libpq opened a connection):

```
dbname audit: FAILED: owner targets: save_02 (psycopg2) from tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_adjacent, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunk_404, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunks_by_season_episode, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_episodes_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_latest_chunk_shape, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_outline_and_chunk_by_id, tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_seasons_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_characters_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_current_place, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_factions_live_schema, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_places_shape, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_relationships_and_psychology, tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_zones_shape; save_05 (psycopg2) from tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision
```

The four skips are the live_llm or paid-authorization gates in `test_conversations.py`, `test_secrets_endpoints.py` and `test_narrative_summary_paid_pg.py` (`Requires explicit two-call summary authorization`).

### Every Remaining Failure by Class

| Class | Tests | Owner |
| --- | --- | --- |
| Reads owner `save_02` outright; the audit refuses it | `test_reader_asset_endpoints.py`: the 14 `TestNarrativeReads`/`TestWorldReads` tests | slice B2-9b |
| Reads owner `save_05` outright; the audit refuses it | `test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision` | slice B2-9b |
| `save_04` include_data clone assuming owner content (`character_experience_jobs` id 3 queued) | `test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]`, `test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience` (`Scheduler did not reach the expected durable state`) | slice B2-9b |
| `save_04` clone expects a pending migration that the fleet already carries (`assert (0 == 0 and 0 >= 1)` on `applied >= 1`) | `test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs` | unmapped; pre-existing |
| Test double lags the production signature (`gated_real_commit() got an unexpected keyword argument 'bind_session_id'`) | `test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit` | unmapped; pre-existing |

The last four fail the same way on a plain `git archive` export of `origin/main` `ac2a585a`:

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p tests.dbname_audit <the four test ids>
____ test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit _____
_ test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs] _
__________ test_scheduler_gateway_sigkill_resumes_inflight_experience __________
___________ test_seat_policy_migration_backfills_save04_active_jobs ____________
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
4 failed, 3 passed, 7 warnings in 45.49s
```

(The run reports 3 passed because the preempted-lease test is parametrized; only its `[False-character_experience_jobs]` case fails.)

## Offline Suites

```
$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2515 passed, 387 skipped, 8 warnings in 342.27s (0:05:42)

$PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 737 skipped, 7 warnings in 28.78s

$PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.10s
```

## Static Checks on the Changed Files

- Black: `14 files would be left unchanged.`
- flake8: no new finding. The changed files carry 64 findings against 66 in their `origin/main` versions (all E501 and pytest-fixture F401/F811 already on `main`); the branch removes an E402 in `tests/scheduler_helpers.py` and an E501 in `tests/test_api/test_acceptance_staging_pg.py`.
- mypy (`--explicit-package-bases`): 7 errors, all pre-existing: missing `requests` stubs (4 files) and tomlkit indexing at `tests/test_api/test_acceptance_staging_pg.py:642-644`, code this branch does not change.
