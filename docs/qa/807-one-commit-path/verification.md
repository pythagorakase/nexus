# Verification: One Commit Path (#807, Slice A)

Branch `claude/807-one-commit-path`, cut from `origin/main` at `9a67e864`.
Slice A retires the async commit twin `nexus/api/commit_handler.py` and fixes
`find_latest_playable_chunk_id`. No migration; slice B (migration 133) follows
separately.

## No Importer Remains

```
$ grep -rn "commit_handler\b" nexus/ scripts/ tests/ ir_eval/ | grep -v commit_handler_sync
$ echo $?
1
```

Empty output. Two test modules not named in the work order also reached the
twin, through `tests/test_presence_roster_pg.py::commit_wire(commit_async=True)`
rather than an import: `tests/test_character_name_reveals_pg.py` and
`tests/test_name_reveal_tag_validation_pg.py`. They are ported too (table
below). `tests/test_reachability.py` stays green with no baseline change: the
twin was never production-reachable and had no baseline entry.

## Classification of Async-Twin Tests

Every test that imported `nexus.api.commit_handler`, or reached it through a
`commit_async=True` helper, is listed. Class (a) means the sync path has the
same behavior; no test fell in class (b): no test exercised an async-only
helper (`fetch_incubator_data`, `insert_narrative_chunk`, `clear_incubator`)
on its own, so nothing is listed under "Deleted with the async twin".

| Test on `origin/main` | Class | Result | Sync target |
| --- | --- | --- | --- |
| `tests/test_commit_handler.py::test_async_faction_state_updates_do_not_write_legacy_activity` | (a) | Covered by existing twin `test_commit_handler_sync.py::test_sync_faction_state_updates_do_not_write_legacy_activity` (same assertion) | `apply_state_updates_sync` |
| `tests/test_commit_handler.py::test_async_chunk_metadata_insert_carries_generation_model` | (a) | Ported as new `test_commit_handler_sync.py::test_sync_chunk_metadata_insert_carries_generation_model` | `insert_chunk_metadata_sync` |
| `tests/test_commit_handler.py::test_async_commit_links_same_turn_character_declaration` | (a) | Existing twin `test_sync_commit_links_same_turn_character_declaration`; added the async test's missing assertion that the metadata insert precedes declaration processing | `commit_incubator_to_database_sync` |
| `tests/test_commit_handler.py::test_async_commit_measures_seeded_bleed_offer_uptake[True,False]` | (a) | Existing twin `test_sync_commit_measures_seeded_bleed_offer_uptake` (same assertions plus uptake log record) | `commit_incubator_to_database_sync`, `record_bleed_uptake_sync` |
| `tests/test_commit_handler.py::test_async_reconciled_mentions_flow_through_adapter_and_commit` | (a) | Existing twin `test_sync_reconciled_mentions_flow_through_adapter_and_commit` (identical assertions) | `commit_incubator_to_database_sync` |
| `tests/test_commit_handler.py::test_async_commit_resolves_all_name_addressed_state_updates` | (a) | Existing twin `test_sync_commit_resolves_all_name_addressed_state_updates`; now records `apply_tag_bestowal` (the sync role of `apply_tag_bestowal_async`) instead of stubbing `_apply_state_tags`, and asserts the faction entity id and accepting world time as the async test did | `commit_incubator_to_database_sync`, `_apply_state_tags` |
| `tests/test_commit_handler.py::test_async_commit_aborts_on_unresolvable_state_update_name` | (a) | Existing twin `test_sync_commit_aborts_on_unresolvable_state_update_name` (same assertions plus rollback) | `commit_incubator_to_database_sync` |
| `tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[*-True]` | (a) | `commit_async` parameter removed; the `[*]` sync cases carry every assertion | `commit_incubator_to_database_sync` |
| `tests/test_name_reveal_staged_bindings_pg.py::test_new_unique_alias_state_update_binds_before_draft_validation[True]` | (a) | `commit_async` parameter removed; sync case retained | `commit_incubator_to_database_sync` |
| `tests/test_bootstrap_episode_pg.py::test_opening_and_real_transitions_schedule_only_populated_predecessors[async]` | (a) | `acceptance` parameter removed; sync case retained | `commit_incubator_to_database_sync` |
| `tests/test_commit_choice_presence_pg.py::test_async_commit_reconciles_enacted_choice_roster_mentions[free-text,structured]` | (a) | Existing twin `test_sync_commit_reconciles_enacted_choice_roster_mentions` (also covers the alias case) | `commit_incubator_to_database_sync` |
| `tests/test_commit_choice_presence_pg.py::test_async_commit_preserves_hydrated_authored_exit` | (a) | Existing twin `test_sync_commit_preserves_hydrated_authored_exit` | `commit_incubator_to_database_sync` |
| `tests/test_commit_choice_presence_pg.py::test_async_commit_reconciles_scene_reset_drop_named_in_enacted_choice` | (a) | Existing twin `test_sync_commit_reconciles_scene_reset_drop_named_in_enacted_choice` | `commit_incubator_to_database_sync` |
| `tests/test_commit_choice_presence_pg.py::test_async_commit_reconciles_authored_exit_named_in_enacted_choice` | (a) | Existing twin `test_sync_commit_reconciles_authored_exit_named_in_enacted_choice` | `commit_incubator_to_database_sync` |
| `tests/test_commit_choice_presence_pg.py::test_async_commit_ignores_character_named_only_in_unselected_option` | (a) | Existing twin `test_sync_commit_ignores_character_named_only_in_unselected_option` | `commit_incubator_to_database_sync` |
| `tests/test_commit_choice_presence_pg.py::test_async_commit_suppresses_only_contained_shorter_name[longest-match,shorter-name-only]` | (a) | Existing twin `test_sync_commit_suppresses_only_contained_shorter_name` | `commit_incubator_to_database_sync` |
| `tests/test_presence_roster_pg.py::test_identity_declaration_binds_or_mints_once[True-*]` | (a) | `commit_async` parameter and `commit_wire`'s async branch removed; sync cases retained | `commit_incubator_to_database_sync` |
| `tests/test_character_name_reveals_pg.py::test_accepted_reveal_preserves_id_history_and_one_presence_row[True]` (not named in the order; reached the twin through `commit_wire`) | (a) | `commit_async` parameter removed; sync case retained | `commit_incubator_to_database_sync` |
| `tests/test_character_name_reveals_pg.py::test_reveal_and_alias_rollback_with_acceptance_failure[True]` (same) | (a) | `commit_async` parameter removed; its `log_state_delta_async` stub served only the async path and is gone; the `log_state_delta_sync` failure stub remains | `commit_incubator_to_database_sync` |
| `tests/test_name_reveal_tag_validation_pg.py::test_reveal_registry_validation_and_acceptance_keep_active_tag_unchanged[True-*]` (same) | (a) | `commit_async` parameter removed; sync cases retained | `commit_incubator_to_database_sync` |
| `tests/test_orrery/test_weather_live.py::test_async_commit_stack_persists_scene_weather` | (a) | Existing twin `test_sync_commit_stack_persists_scene_weather` | `insert_chunk_metadata_sync` |
| `tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[async-*]` | (a) | `writer` parameter removed; sync cases retained | `apply_state_updates_sync` |
| `tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation[async]` | (a) | `acceptance` parameter removed; the real HTTP approve route (sync commit) remains, and the assertions the async case had made conditional (accepted outcome, compaction job, `--chunk` inspection) are now unconditional | `commit_incubator_to_database_sync` via `/api/narrative/approve` |
| `tests/test_api/test_orrery_config_reuse_pg.py::test_async_commit_loads_application_config_once` | (a) | Existing twin `test_sync_commit_loads_application_config_once` (identical assertions; wraps `commit_orrery_tick_sync` and `_orrery_checkpoint_interval` on `commit_handler_sync`) | `commit_incubator_to_database_sync` |
| `tests/test_lore/test_pass2_baseline_pg.py::test_async_regeneration_replace_and_acceptance_failure_roll_back` | (a) | No sync twin covered the replaced draft; ported as new `test_regeneration_replace_and_acceptance_failure_roll_back`, failing `insert_chunk_metadata_sync` on `commit_handler_sync` | `commit_incubator_to_database_sync` |

## Playable-Boundary Lookup

`find_latest_playable_chunk_id` (`nexus/agents/orrery/retrograde_persistence.py`)
no longer filters `nc.state::text = 'finalized'`. Read-only evidence from the
fleet (`SELECT state::text, count(*) ... GROUP BY 1`):

| Database | `state` counts | Old lookup | New lookup |
| --- | --- | --- | --- |
| `save_02` | `draft` 1425 | `NULL` | 1425 |
| `save_03` | `draft` 39, `finalized` 1 (the prologue) | `NULL` | 100 |
| `save_04` | `draft` 45, `finalized` 1 (the prologue) | `NULL` | 49 |

Writers of `narrative_chunks` rows (`git grep -n "INSERT INTO narrative_chunks" -- nexus/ scripts/`):

```
nexus/agents/memnon/utils/content_processor.py:328   MEMNON import-era content processor
nexus/agents/orrery/retrograde_persistence.py:2516   Retrograde prologue insert (writes 'finalized')
nexus/api/commit_handler_sync.py:512                 the accept path (column default 'draft')
scripts/benchmark_experience_enqueue_fence.py:66,71  benchmark on a disposable clone
scripts/qa_shift/card_identity_probe.py:323          QA probe on a disposable clone
scripts/simple_update.py:911                         import-era raw-text tooling
scripts/update_raw_text.py:703                       import-era raw-text tooling
```

Only the accept path and the prologue insert are on the play path.
`nexus/api/commit_handler.py:245` was the third play-path hit before this
branch deleted the file.

New PostgreSQL-gated test
`tests/test_orrery/test_retrograde_persistence.py::test_latest_playable_chunk_is_the_last_accepted_chunk_not_the_prologue`
inserts the prologue through `_insert_prologue_chunk`, asserts the lookup is
`None`, then accepts two chunks through the real `commit_incubator_to_database_sync`
and asserts the lookup returns the later one while both keep `state = 'draft'`.
Against the unfixed query it fails with `assert None == 3`.

## Gates

Environment: `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset;
`PYTHONPATH=$PWD`; `$PY=/Users/pythagor/nexus/.venv/bin/python`; import proof
`nexus.__file__` = `.claude/worktrees/807-one-commit-path/nexus/__init__.py`.

### Changed-File Tests (PostgreSQL, Verbose)

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -v tests/test_orrery/test_playable_narrative_boundary.py::test_parent_claim_embeds_only_older_unembedded_playable_chunks tests/test_orrery/test_retrograde_persistence.py::test_latest_playable_chunk_is_the_last_accepted_chunk_not_the_prologue tests/test_lore/test_pass2_baseline_pg.py::test_regeneration_replace_and_acceptance_failure_roll_back tests/test_commit_handler_sync.py tests/test_name_reveal_staged_bindings_pg.py tests/test_bootstrap_episode_pg.py tests/test_commit_choice_presence_pg.py tests/test_presence_roster_pg.py tests/test_character_name_reveals_pg.py tests/test_name_reveal_tag_validation_pg.py tests/test_orrery/test_weather_live.py tests/test_api/test_orrery_config_reuse_pg.py
tests/test_orrery/test_playable_narrative_boundary.py::test_parent_claim_embeds_only_older_unembedded_playable_chunks PASSED
tests/test_orrery/test_retrograde_persistence.py::test_latest_playable_chunk_is_the_last_accepted_chunk_not_the_prologue PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_regeneration_replace_and_acceptance_failure_roll_back PASSED
...
======================== 69 passed in 78.43s (0:01:18) =========================
```

Full verbose list:

```
tests/test_orrery/test_playable_narrative_boundary.py::test_parent_claim_embeds_only_older_unembedded_playable_chunks PASSED
tests/test_orrery/test_retrograde_persistence.py::test_latest_playable_chunk_is_the_last_accepted_chunk_not_the_prologue PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_regeneration_replace_and_acceptance_failure_roll_back PASSED
tests/test_commit_handler_sync.py::test_sync_unresolved_character_reference_raises PASSED
tests/test_commit_handler_sync.py::test_sync_commit_links_same_turn_character_declaration PASSED
tests/test_commit_handler_sync.py::test_sync_commit_measures_seeded_bleed_offer_uptake[True] PASSED
tests/test_commit_handler_sync.py::test_sync_commit_measures_seeded_bleed_offer_uptake[False] PASSED
tests/test_commit_handler_sync.py::test_sync_commit_does_not_stamp_offer_from_regenerated_away_draft PASSED
tests/test_commit_handler_sync.py::test_sync_commit_matches_actor_name_on_word_boundaries[Anna waits by the gate.-0] PASSED
tests/test_commit_handler_sync.py::test_sync_commit_matches_actor_name_on_word_boundaries[Ann's coat is wet.-1] PASSED
tests/test_commit_handler_sync.py::test_sync_reconciled_mentions_flow_through_adapter_and_commit PASSED
tests/test_commit_handler_sync.py::test_sync_commit_resolves_all_name_addressed_state_updates PASSED
tests/test_commit_handler_sync.py::test_sync_commit_aborts_on_unresolvable_state_update_name PASSED
tests/test_commit_handler_sync.py::test_post_commit_compaction_failure_preserves_success_and_retries PASSED
tests/test_commit_handler_sync.py::test_bootstrap_commit_seeds_setting_for_next_presence_baseline PASSED
tests/test_commit_handler_sync.py::test_sync_faction_state_updates_do_not_write_legacy_activity PASSED
tests/test_commit_handler_sync.py::test_sync_chunk_metadata_insert_carries_generation_model PASSED
tests/test_commit_handler_sync.py::test_sync_location_state_updates_map_conditions_to_status_column PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[reference] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[departure] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[state] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[relationship1] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[relationship2] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_new_unique_alias_state_update_binds_before_draft_validation PASSED
tests/test_bootstrap_episode_pg.py::test_opening_and_real_transitions_schedule_only_populated_predecessors PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_reconciles_enacted_choice_roster_mentions[free-text] PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_reconciles_enacted_choice_roster_mentions[structured] PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_reconciles_enacted_choice_roster_mentions[alias] PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_preserves_present_precedence_for_choice_mention PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_preserves_hydrated_authored_exit PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_reconciles_scene_reset_drop_named_in_enacted_choice PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_reconciles_authored_exit_named_in_enacted_choice PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_ignores_character_named_only_in_unselected_option PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_suppresses_only_contained_shorter_name[longest-match] PASSED
tests/test_commit_choice_presence_pg.py::test_sync_commit_suppresses_only_contained_shorter_name[shorter-name-only] PASSED
tests/test_presence_roster_pg.py::test_roster_real_commit_promotion_audience_and_writer_seat PASSED
tests/test_presence_roster_pg.py::test_roster_real_commit_carry_forward_and_reset PASSED
tests/test_presence_roster_pg.py::test_roster_real_alias_resolution_and_ambiguity PASSED
tests/test_presence_roster_pg.py::test_roster_ambiguous_crossing_rejected_before_hydration[False] PASSED
tests/test_presence_roster_pg.py::test_roster_ambiguous_crossing_rejected_before_hydration[True] PASSED
tests/test_presence_roster_pg.py::test_roster_same_turn_departure_survives_commit_reconciliation PASSED
tests/test_presence_roster_pg.py::test_roster_operator_provenance_includes_historical_presence PASSED
tests/test_presence_roster_pg.py::test_historical_settings_are_ordered_but_frontier_is_rejected PASSED
tests/test_presence_roster_pg.py::test_current_place_returns_all_committed_settings PASSED
tests/test_presence_roster_pg.py::test_recall_scores_any_historical_setting PASSED
tests/test_presence_roster_pg.py::test_experience_metadata_retains_all_historical_settings[False] PASSED
tests/test_presence_roster_pg.py::test_experience_metadata_retains_all_historical_settings[True] PASSED
tests/test_presence_roster_pg.py::test_identity_declaration_binds_or_mints_once[Remote Friend] PASSED
tests/test_presence_roster_pg.py::test_identity_declaration_binds_or_mints_once[Fox] PASSED
tests/test_presence_roster_pg.py::test_identity_declaration_binds_or_mints_once[Juniper Moss] PASSED
tests/test_presence_roster_pg.py::test_identity_shared_surname_blocks_before_staging PASSED
tests/test_presence_roster_pg.py::test_identity_title_collision_blocks_reconciliation_and_hydration[Ada-Lady Ada] PASSED
tests/test_presence_roster_pg.py::test_identity_title_collision_blocks_reconciliation_and_hydration[Lady Ada-Ada] PASSED
tests/test_presence_roster_pg.py::test_identity_title_collision_blocks_reconciliation_and_hydration[Ada Lovelace-Lady Ada] PASSED
tests/test_presence_roster_pg.py::test_identity_location_conflict_blocks_before_staging[None] PASSED
tests/test_presence_roster_pg.py::test_identity_location_conflict_blocks_before_staging[Garden] PASSED
tests/test_presence_roster_pg.py::test_identity_frontier_location_narrows_without_resolving PASSED
tests/test_presence_roster_pg.py::test_identity_batch_fuzzy_collision_blocks_before_staging PASSED
tests/test_character_name_reveals_pg.py::test_accepted_reveal_preserves_id_history_and_one_presence_row PASSED
tests/test_character_name_reveals_pg.py::test_reveal_and_alias_rollback_with_acceptance_failure PASSED
tests/test_character_name_reveals_pg.py::test_async_name_delta_has_identical_json_with_either_codec[False] PASSED
tests/test_character_name_reveals_pg.py::test_async_name_delta_has_identical_json_with_either_codec[True] PASSED
tests/test_name_reveal_tag_validation_pg.py::test_reveal_registry_validation_and_acceptance_keep_active_tag_unchanged[False] PASSED
tests/test_name_reveal_tag_validation_pg.py::test_reveal_registry_validation_and_acceptance_keep_active_tag_unchanged[True] PASSED
tests/test_orrery/test_weather_live.py::test_binding_weather_uses_location_transit_origin_and_unknown PASSED
tests/test_orrery/test_weather_live.py::test_warm_arm_fires_from_local_weather PASSED
tests/test_orrery/test_weather_live.py::test_live_anchor_override_and_disabled_mode PASSED
tests/test_orrery/test_weather_live.py::test_sync_commit_stack_persists_scene_weather PASSED
tests/test_api/test_orrery_config_reuse_pg.py::test_sync_commit_loads_application_config_once PASSED
```

### Offline Gate

```
$ $PY -m pytest -q
FAILED tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants
1 failed, 4032 passed, 1021 skipped in 317.15s (0:05:17)
```

The one failure is pre-existing and outside this branch: it asserts that
`prompts/storyteller_gaia.md` contains "rather than invent"; neither the prompt
nor the test changes here, and the same test fails on a `git archive` of
`origin/main` (`1 failed in 0.67s`).

### PostgreSQL Gate

Run as `NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfE <batch>` per directory, the
root-level files in three batches of 33 (`live_seed_schema_test.py` and
`live_set_designer_test.py` included in the third). The same batches were then
run on a `git archive` of `origin/main` at `9a67e864` on the same machine.

| Batch | This branch | `origin/main` |
| --- | --- | --- |
| `api` | 26 failed, 833 passed, 4 skipped, 4 errors in 479.19s (0:07:59) | 27 failed, 834 passed, 4 skipped, 4 errors in 457.12s (0:07:37) |
| `orrery` | 173 failed, 1388 passed, 39 skipped, 28 errors in 258.68s (0:04:18) | 174 failed, 1390 passed, 39 skipped, 28 errors in 240.34s (0:04:00) |
| `lore` | 4 failed, 444 passed, 1 skipped, 4 errors in 113.37s (0:01:53) | 4 failed, 444 passed, 1 skipped, 4 errors in 111.59s (0:01:51) |
| `root_rootbatch_aa` | 2 failed, 471 passed, 11 skipped, 14 errors in 270.49s (0:04:30) | 2 failed, 489 passed, 10 skipped, 14 errors in 276.81s (0:04:36) |
| `root_rootbatch_ab` | 1 failed, 542 passed, 10 skipped, 27 errors in 69.76s (0:01:09) | 1 failed, 548 passed, 11 skipped, 27 errors in 84.48s (0:01:24) |
| `root_rootbatch_ac` | 6 failed, 616 passed, 19 skipped in 125.96s (0:02:05) | 6 failed, 621 passed, 19 skipped in 142.69s (0:02:22) |
| `tests/test_memnon` | 51 passed in 30.11s | not rerun (green on branch) |
| other directories | 234 passed in 74.00s (0:01:14) | not rerun (green on branch) |

The PostgreSQL gate is **not green**, and it is not green on `origin/main`
either. After normalizing the removed `sync`/`async` parameters, the branch
fails 285 test ids and `origin/main` 283. The difference is five branch-only
and three origin-only ids; rerun in isolation, all eight give identical
results on both trees (the five branch-only ids pass on both), so they are
order- or load-dependent, with another agent's PostgreSQL gate running on the
same server at the same time.

Failure causes on this branch (first `E` line per failure section):

| Count | Cause |
| --- | --- |
| 133 | `IDF analyzer mismatch for corpus narrative: rebuild required`. The server is now PostgreSQL 17.11 (`server_version_num` 170011), but `memory_idf_corpora.analyzer_version` in `save_02`, `save_03`, `save_04` and `NEXUS_template` reads `pg_catalog.english/v1/170010`. Every data clone of a save inherits the old stamp, and any narrative insert on it raises. Schema-only clones are unaffected because `new_story_setup._initialize_empty_idf_corpora` restamps them. The live saves hit the same trigger on their next accepted turn. |
| 16 | #885: slot 5 is an empty story (`save_05 is expected to ...`, `the slot has no narrative chunks`, and the `*_on_save_05` trait-compiler tests failing on `need-clock anchor unavailable`) |
| 17 | `need-clock anchor unavailable: no canonical world time or base_timestamp` in tests outside the slot-5 set |
| 6 | Live saves missing unapplied migrations (`relation "character_identity_rulings" does not exist`, `column ... setting_confirmed does not exist`) |
| 43 | Other pre-existing failures (for example `connection cannot be re-entered recursively` in `test_narrative_retry_pg.py`, `gated_real_commit() got an unexpected keyword argument 'bind_session_id'` in `test_narrative_post_commit.py`, empty AUDIT_SLOTS in `test_orrery_dev_endpoints.py`); all also fail on `origin/main` |

The only failing tests in files this branch changes are
`tests/test_api/test_attempt_manifest_pg.py` (both tests, on `save_04` data
clones) and `tests/test_orrery/test_relationship_provenance_pg.py` (every
case, on a `save_03` data clone, including the untouched
`test_canceling_producers_retain_versions_and_crossings`). All fail during
setup or acceptance on the IDF analyzer mismatch, and the same ids fail
identically on `origin/main`; `tests/test_orrery/test_drift_live.py`,
which this branch does not touch, fails the same way on the same fixture.

<details><summary>All 289 failing test ids on this branch</summary>

```
tests/test_api/test_attempt_manifest_pg.py::test_child_job_enqueue_correlation_and_transaction_reset
tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation
tests/test_api/test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
tests/test_api/test_narrative_retry_pg.py::test_dead_worker_is_advertised_exactly_as_retry_accepts_it
tests/test_api/test_narrative_retry_pg.py::test_restart_reopens_the_menu_when_no_retry_can_resume
tests/test_api/test_narrative_retry_pg.py::test_staging_failure_resumes_as_recovery_and_retries_once
tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling
tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle
tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]
tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_hover_payload
tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_recent_events_respect_anchor
tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable
tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts
tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures
tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner
tests/test_api/test_orrery_dev_endpoints.py::test_what_if_validation_rejections
tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404
tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_delete_handles_legacy_leading_slash_paths
tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_invalid_type_rejected
tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_portrait_upload_set_main_delete
tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_characters_shape
tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_relationships_and_psychology
tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision
tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render
tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_rechecks_generation_after_leasing_before_provider
tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-correspondence_compaction_jobs]
tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[True-correspondence_compaction_jobs]
tests/test_api/test_seat_policy_jobs_pg.py::test_accept_repin_and_scheduler_use_literal_seat_models
tests/test_interactions_pg.py::test_adversarial_public_api_flow_stops_and_replays_exactly
tests/test_interactions_pg.py::test_command_retries_return_recorded_outcome_without_new_event
tests/test_interactions_pg.py::test_concurrent_proposals_share_one_database_enforced_outcome
tests/test_interactions_pg.py::test_concurrent_recoverers_execute_cleanup_under_one_exclusive_claim
tests/test_interactions_pg.py::test_constructor_only_capability_and_executor_vocabulary
tests/test_interactions_pg.py::test_cooperative_public_api_flow_replay_equals_live_state
tests/test_interactions_pg.py::test_explicit_lease_and_cleanup_completion_make_recovery_idempotent
tests/test_interactions_pg.py::test_grant_expiry_uses_wall_clock_after_transaction_lock_stall
tests/test_interactions_pg.py::test_independent_grants_and_fail_closed_states
tests/test_interactions_pg.py::test_locked_authoritative_head_rejects_stale_start_and_unavailable_identity
tests/test_interactions_pg.py::test_malformed_stored_authorization_and_policy_deny_typed
tests/test_interactions_pg.py::test_material_term_drift_requires_fresh_authorization
tests/test_interactions_pg.py::test_membership_changes_bump_revision_void_grants_and_replay_history
tests/test_interactions_pg.py::test_migration_comments_columns_and_events_are_append_only
tests/test_jobs_cli_pg.py::test_jobs_cli_reports_counts_and_non_terminal_rows
tests/test_jobs_cli_pg.py::test_jobs_cli_reports_experiences_stamped_without_vectors
tests/test_lore/test_baseline_fingerprint_refresh_pg.py::test_divergence_fingerprint_refresh_preserves_save4_continuation
tests/test_lore/test_intertitle_live.py::test_anchor_fallback_skips_retrograde_prologue
tests/test_lore/test_pass2_chunk1369.py::test_pass2_handles_karaoke_divergence
tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_omit_empty_section
tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_render_real_outcomes_across_sparse_chunk_ids
tests/test_lore/test_recent_orrery_rulings_pg.py::test_recent_rulings_respect_configured_cap
tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
tests/test_lore/test_scene_order_render.py::test_recent_warm_window_ends_at_historical_parent
tests/test_new_story_cache.py::test_weird_level_round_trips_and_only_a_new_wizard_clears_it
tests/test_orrery_tag_validation_pg.py::test_active_character_identity_only_reassert_arm_is_removed
tests/test_orrery_tag_validation_pg.py::test_active_character_update_with_activity_survives_registry_coercion
tests/test_orrery_tag_validation_pg.py::test_active_character_update_with_tags_clear_survives_registry_coercion
tests/test_orrery_tag_validation_pg.py::test_active_place_and_faction_identity_only_reassert_arms_are_removed_by_id[factions-faction-schismatic_internal_threat]
tests/test_orrery_tag_validation_pg.py::test_active_place_and_faction_identity_only_reassert_arms_are_removed_by_id[places-place-qa649_place_watch]
tests/test_orrery_tag_validation_pg.py::test_expired_semantic_row_is_relanded_without_expiry
tests/test_orrery_tag_validation_pg.py::test_expiry_at_anchor_is_inactive_and_defaulted_from_exact_anchor
tests/test_orrery_tag_validation_pg.py::test_id_name_disagreement_rejects_with_distinct_reason
tests/test_orrery_tag_validation_pg.py::test_identity_only_active_character_update_is_removed_before_registry_coercion
tests/test_orrery_tag_validation_pg.py::test_inactive_extend_expiry_rejection_text_is_unchanged
tests/test_orrery_tag_validation_pg.py::test_migration_109_seeds_only_time_cleared_defaults
tests/test_orrery_tag_validation_pg.py::test_mixed_payload_logs_active_defaulted_and_rejected_reasons
tests/test_orrery_tag_validation_pg.py::test_model_controlled_name_cannot_inject_a_reason_token
tests/test_orrery_tag_validation_pg.py::test_non_extend_expiry_tags_survive_active_normalization
tests/test_orrery_tag_validation_pg.py::test_place_resolution_preserves_supplied_identity_conflicts[False]
tests/test_orrery_tag_validation_pg.py::test_place_resolution_preserves_supplied_identity_conflicts[True]
tests/test_orrery_tag_validation_pg.py::test_removed_active_update_rebases_later_defaulted_application
tests/test_orrery_tag_validation_pg.py::test_replacement_state_delta_extend_expiry_remains_rejected
tests/test_orrery_tag_validation_pg.py::test_same_turn_declared_faction_first_application_commits
tests/test_orrery_tag_validation_pg.py::test_semantic_and_event_first_applications_land_without_expiry[dying-event]
tests/test_orrery_tag_validation_pg.py::test_semantic_and_event_first_applications_land_without_expiry[recently_protective-semantic]
tests/test_orrery_tag_validation_pg.py::test_time_default_survives_real_draft_and_commit_route
tests/test_orrery_tag_validation_pg.py::test_time_first_application_lands_with_registry_default_expiry
tests/test_orrery_tag_validation_pg.py::test_time_first_application_without_default_rejects_loudly
tests/test_orrery_tag_validation_pg.py::test_unknown_name_preserves_extend_expiry_rejection
tests/test_orrery/test_adjudication_history.py::test_commit_persists_enriched_history_then_rolls_back
tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
tests/test_orrery/test_build_venture_replay.py::test_build_venture_replays_applied_snapshots_through_completion
tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False]
tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[True]
tests/test_orrery/test_card_identity.py::test_ren_rank_commit_replay[False-False]
tests/test_orrery/test_card_identity.py::test_ren_rank_commit_replay[False-True]
tests/test_orrery/test_card_identity.py::test_ren_rank_commit_replay[True-False]
tests/test_orrery/test_card_identity.py::test_ren_rank_commit_replay[True-True]
tests/test_orrery/test_claim_accounts_live.py::test_latent_sibling_secret_stays_private_until_its_own_gate_fires
tests/test_orrery/test_claim_accounts_live.py::test_old_divergent_sibling_scopes_raise_during_hydration
tests/test_orrery/test_claim_accounts_live.py::test_scope_promotion_updates_every_sibling_and_hydrates_cleanly
tests/test_orrery/test_claim_accounts_live.py::test_sibling_accounts_hydrate_predicates_and_propagate_independently
tests/test_orrery/test_claim_accounts_live.py::test_sync_variant_rejects_cross_incident_lineage_parent
tests/test_orrery/test_claim_awareness_replay_live.py::test_verify_reports_projection_only_awareness_drift
tests/test_orrery/test_claim_awareness_replay_live.py::test_verify_skips_checkpoint_that_predates_awareness_section
tests/test_orrery/test_claim_birth_coverage_pg.py::test_detected_signal_receipt_is_separate_from_private_deed[informant_contact-encoded_message-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_detected_signal_receipt_is_separate_from_private_deed[retaliation_attempted-threat_issued-False]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_detected_signal_receipt_is_separate_from_private_deed[surveillance_performed-compliance_alert-False]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_live_claim_replay_identity_and_sibling_account
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[hunt_called_off-False]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[hunt_declared-False]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[informant_contact-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[intel_acquired-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[intel_acted_on-False]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[protective_intervention-False]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[pursue_romance_completed-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[recruit_ally_completed-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[retaliation_attempted-False]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[retaliation_executed-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[rival_consulted-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[seek_redemption_completed-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[surveillance_performed-False]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_primary_resolver_birth_roles_and_provenance[warning_delivered-True]
tests/test_orrery/test_claim_birth_coverage_pg.py::test_relationship_drift_birth_is_actor_private_and_replays
tests/test_orrery/test_claim_birth_coverage_pg.py::test_resolution_free_commit_does_not_backfill_historical_event
tests/test_orrery/test_claim_birth_coverage_pg.py::test_retrograde_private_event_mints_actor_awareness_only
tests/test_orrery/test_claim_birth_coverage_pg.py::test_retrograde_private_reprocess_backfills_no_target_awareness
tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_common_claims_are_bounded_to_their_about_entities
tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_joins_distorted_delivery_to_real_depth
tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_renders_two_hop_provenance_and_ledger_depth
tests/test_orrery/test_claim_consumption_live.py::test_historical_anchor_excludes_future_claim_and_awareness
tests/test_orrery/test_claim_consumption_live.py::test_hydration_excludes_irrelevant_history_and_empty_universe_issues_no_sql
tests/test_orrery/test_claim_consumption_live.py::test_live_predicates_cover_participant_told_common_false_and_faction
tests/test_orrery/test_claim_consumption_live.py::test_recent_claim_scope_survives_inactive_endpoints
tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity
tests/test_orrery/test_communication_graph_live.py::test_assembly_is_deterministic_and_unknown_configured_channel_is_loud
tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum
tests/test_orrery/test_communication_graph_live.py::test_conflicted_live_pair_licenses_only_each_tellers_own_direction
tests/test_orrery/test_communication_graph_live.py::test_culture_profiles_multiply_and_record_provenance
tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge
tests/test_orrery/test_communication_graph_live.py::test_lone_row_is_sparse_and_handler_override_beats_neutral
tests/test_orrery/test_communication_graph_live.py::test_production_explain_and_entity_audit_share_one_edge_list
tests/test_orrery/test_communication_graph_live.py::test_unknown_dyad_override_key_is_loud
tests/test_orrery/test_court_patron_replay.py::test_court_patron_completion_replays_without_drift
tests/test_orrery/test_drift_live.py::test_colocated_characters_without_events_produce_no_versions
tests/test_orrery/test_drift_live.py::test_commit_drift_updates_versions_projects_literal_and_mints_claim
tests/test_orrery/test_drift_live.py::test_disabled_config_does_not_drift
tests/test_orrery/test_drift_live.py::test_gaia_update_attributes_version_and_emits_milestone
tests/test_orrery/test_drift_live.py::test_long_scale_valence_uses_same_rung_as_postgres
tests/test_orrery/test_drift_live.py::test_retrograde_world_layer_does_not_drift
tests/test_orrery/test_drift_live.py::test_unattributed_or_invalid_valence_update_raises[None]
tests/test_orrery/test_drift_live.py::test_unattributed_or_invalid_valence_update_raises[unattributed_pre_115]
tests/test_orrery/test_drift_live.py::test_unattributed_or_invalid_valence_update_raises[unknown]
tests/test_orrery/test_drift_live.py::test_zero_edge_tick_still_records_drain_marker
tests/test_orrery/test_ecology_live.py::test_outbound_pair_tag_and_detection_gate_live
tests/test_orrery/test_epistemics.py::test_async_live_applier_has_epistemics_parity
tests/test_orrery/test_epistemics.py::test_kill_switch_disables_real_retrograde_and_live_producers
tests/test_orrery/test_epistemics.py::test_live_applier_mints_and_ledgers_epistemics_ids
tests/test_orrery/test_epistemics.py::test_pydantic_epistemics_settings_coerce_and_drive_live_producer
tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction
tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction
tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered
tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly
tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched
tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings
tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic
tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition
tests/test_orrery/test_knowledge_surfacing_live.py::test_digest_cap_drops_oldest_and_reports_truncation
tests/test_orrery/test_knowledge_surfacing_live.py::test_digest_surfaces_only_possessed_safe_accounts
tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[False]
tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True]
tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db
tests/test_orrery/test_narration_job_fencing_pg.py::test_completion_clock_counts_time_blocked_on_job_lock
tests/test_orrery/test_narration_job_fencing_pg.py::test_completion_locks_world_layer_before_comparing_anchor
tests/test_orrery/test_narration_job_fencing_pg.py::test_descriptor_retirement_preserves_canon_legacy_jobs_and_bleed
tests/test_orrery/test_narration_job_fencing_pg.py::test_duplicate_enqueue_collapses_to_one_effective_job
tests/test_orrery/test_narration_job_fencing_pg.py::test_expired_lease_reclaimed_and_original_completion_fenced
tests/test_orrery/test_narration_job_fencing_pg.py::test_normal_narration_path_succeeds_once_end_to_end
tests/test_orrery/test_narration_job_fencing_pg.py::test_stale_anchor_completion_is_terminally_rejected
tests/test_orrery/test_need_clock_anchor_pg.py::test_atemporal_need_tick_and_replay_use_primary_world_clock
tests/test_orrery/test_need_clock_anchor_pg.py::test_atomic_transition_bounds_zone_with_configured_radius
tests/test_orrery/test_need_clock_anchor_pg.py::test_atomic_transition_replaces_stale_clock_before_protagonist_trigger
tests/test_orrery/test_need_clock_anchor_pg.py::test_atomic_transition_rolls_back_when_zone_boundary_write_fails
tests/test_orrery/test_need_clock_anchor_pg.py::test_legacy_atemporal_travel_start_keeps_world_times_unreproducible
tests/test_orrery/test_need_clock_anchor_pg.py::test_markerless_null_clock_mismatch_is_a_field_level_remainder
tests/test_orrery/test_need_clock_anchor_pg.py::test_migration_provenance_counts_and_rerun_are_idempotent
tests/test_orrery/test_need_clock_anchor_pg.py::test_migration_reconciles_future_poison_in_a_past_set_story
tests/test_orrery/test_need_clock_anchor_pg.py::test_migration_reconciles_poisoned_rows_and_guards_fulfillment_domain
tests/test_orrery/test_need_clock_anchor_pg.py::test_reconciled_wall_accrued_debt_is_an_absolute_remainder
tests/test_orrery/test_need_clock_anchor_pg.py::test_reconciliation_audit_survives_need_row_delete_and_reinsert
tests/test_orrery/test_need_clock_anchor_pg.py::test_replay_does_not_restamp_post_migration_fulfillment
tests/test_orrery/test_need_clock_anchor_pg.py::test_replay_mirrors_reconciliation_across_migration_100_boundary
tests/test_orrery/test_need_clock_anchor_pg.py::test_replay_reconstructs_post_migration_trigger_anchor
tests/test_orrery/test_need_clock_anchor_pg.py::test_replay_uses_marker_result_for_overlapping_post_migration_chunk
tests/test_orrery/test_orbit_distance_live.py::test_hydrate_orbit_distance_from_active_relationship_graph
tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
tests/test_orrery/test_pursue_romance_replay.py::test_pursue_romance_lifecycle_replays_between_checkpoints_without_drift
tests/test_orrery/test_reconstruction.py::test_checkpoint_captures_every_section_and_is_idempotent
tests/test_orrery/test_reconstruction.py::test_relationship_triggers_version_updates_and_deletes
tests/test_orrery/test_reconstruction.py::test_skald_state_updates_are_ledgered
tests/test_orrery/test_reconstruction.py::test_unattributed_relationship_write_versions_with_null_chunk
tests/test_orrery/test_recruit_ally_replay.py::test_recruit_ally_lifecycle_replays_between_checkpoints_without_drift
tests/test_orrery/test_relationship_provenance_pg.py::test_canceling_producers_retain_versions_and_crossings[async]
tests/test_orrery/test_relationship_provenance_pg.py::test_canceling_producers_retain_versions_and_crossings[sync]
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[atemporal]
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[flashback]
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[primary]
tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape
tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored
tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier
tests/test_orrery/test_replay.py::test_pair_tag_bestowal_and_clearance_replay
tests/test_orrery/test_replay.py::test_post_fix_null_world_time_uses_primary_clock_exactly
tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder
tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning
tests/test_orrery/test_replay.py::test_project_complete_hands_off_and_real_travel_applier_relocates
tests/test_orrery/test_replay.py::test_project_replay_rejects_ledger_without_applied_projection
tests/test_orrery/test_replay.py::test_project_transition_window_replays_with_zero_checkpoint_drift
tests/test_orrery/test_replay.py::test_reconstruction_refuses_pre_instrumentation_chunks
tests/test_orrery/test_replay.py::test_relationship_multi_version_unwind_order
tests/test_orrery/test_replay.py::test_relationship_unwind_restores_updates_deletes_and_drops_inserts
tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift
tests/test_orrery/test_replay.py::test_scalar_replay_round_trip_and_within_chunk_ordering
tests/test_orrery/test_replay.py::test_tag_applicability_before_fulfillment_preserves_marker
tests/test_orrery/test_replay.py::test_tag_bestowal_and_clearance_replay_at_exact_chunks
tests/test_orrery/test_replay.py::test_travel_replay_start_advance_arrive
tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible
tests/test_orrery/test_replay.py::test_verify_catches_unledgered_entity_deactivation
tests/test_orrery/test_replay.py::test_verify_catches_unledgered_scalar_drift
tests/test_orrery/test_replay.py::test_verify_catches_unlogged_tag_clear
tests/test_orrery/test_replay.py::test_verify_skips_legacy_checkpoint_without_entity_activity
tests/test_orrery/test_replay.py::test_window_born_character_fulfillment_preserves_applicability_marker
tests/test_orrery/test_retrograde_constraints_pg.py::test_persistence_identity_binds_database_alias_without_packet_alias
tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_compiler_gate_suppresses_all_named_target_materialization
tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_packet_and_transition_keep_event_without_adversarial_rows
tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction
tests/test_orrery/test_retrograde_embedding_pg.py::test_batch_embedding_writes_every_summary_model_pair
tests/test_orrery/test_retrograde_embedding_pg.py::test_cli_repairs_stamped_summary_when_vector_table_is_missing
tests/test_orrery/test_retrograde_embedding_pg.py::test_repaired_summary_participates_in_dedicated_vector_join
tests/test_orrery/test_retrograde_embedding_pg.py::test_stamped_without_vector_audit_follows_damage_and_repair
tests/test_orrery/test_retrograde_projects_live.py::test_between_capture_maturation_job_still_replays_under_gate
tests/test_orrery/test_retrograde_projects_live.py::test_cap_dropped_projects_do_not_claim_actor_keys
tests/test_orrery/test_retrograde_projects_live.py::test_checkpoints_without_control_key_keep_legacy_window
tests/test_orrery/test_retrograde_projects_live.py::test_delayed_maturation_write_is_gated_out_of_checkpoint_replay
tests/test_orrery/test_retrograde_projects_live.py::test_dropped_project_targets_do_not_create_entity_stubs
tests/test_orrery/test_retrograde_projects_live.py::test_maturation_disabled_config_drops_intent_loudly
tests/test_orrery/test_retrograde_projects_live.py::test_maturation_project_replays_exactly_and_hydrates_continuation
tests/test_orrery/test_retrograde_projects_live.py::test_maturation_seeds_only_target_actor_and_logs_advisory_drops
tests/test_orrery/test_retrograde_projects_live.py::test_maturation_shared_writer_validation_raises
tests/test_orrery/test_retrograde_projects_live.py::test_maturation_start_at_base_chunk_replays_without_drift
tests/test_orrery/test_retrograde_projects_live.py::test_maturation_start_at_target_chunk_is_absent_without_drift
tests/test_orrery/test_retrograde_projects_live.py::test_maturation_started_event_requires_applied_projection_in_replay
tests/test_orrery/test_retrograde_projects_live.py::test_summary_backfill_excludes_wizard_and_maturation_project_starts
tests/test_orrery/test_retrograde_projects_live.py::test_wizard_genesis_checkpoint_carries_seeded_project_through_replay
tests/test_orrery/test_retrograde_projects_live.py::test_writer_inserts_all_types_and_started_events
tests/test_orrery/test_retrograde_retrieval_pg.py::test_summary_planning_is_idempotent_on_disposable_database
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_accepts_complete_legacy_embedding_catalog
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_moves_ids_embeddings_manifests_and_rolls_back
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_reanchors_multi_hop_maturation_ancestry
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_reanchors_nested_maturation_job
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_refuses_lifecycle_repair_on_populated_slot
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_rejects_json_null_manifest_without_laundering
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_rejects_nested_job_manifest_request_mismatch
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_rejects_null_legacy_embedding_timestamp
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_rejects_stamped_summary_without_vector_coverage
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_requires_full_copy_schema_for_legacy_rows[chunk_metadata-scene]
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_requires_full_copy_schema_for_legacy_rows[narrative_chunks-choice_text]
tests/test_orrery/test_retrograde_summary_migration_pg.py::test_migration_078_rolls_back_after_late_postcondition_failure
tests/test_orrery/test_reveal_live.py::test_async_authoring_grants_unpossessed_holder
tests/test_orrery/test_reveal_live.py::test_authored_and_revealed_secrets_replay_between_checkpoints
tests/test_orrery/test_reveal_live.py::test_authoring_grants_unpossessed_holder_and_reveal_completes
tests/test_orrery/test_reveal_live.py::test_authoring_rejects_non_private_and_unregistered_gate
tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop
tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate
tests/test_orrery/test_reveal_live.py::test_unregistered_gate_in_latent_row_raises_loudly
tests/test_orrery/test_reveal_live.py::test_verify_skips_checkpoint_that_predates_backstory_section
tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[primary-settings1]
tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[retrograde-settings0]
tests/test_orrery/test_seek_redemption_replay.py::test_seek_redemption_completion_replays_without_drift
tests/test_orrery/test_signal_events.py::test_async_commit_emits_signal_rows_live
tests/test_orrery/test_signal_events.py::test_committed_signal_feeds_consumer_gates_live
tests/test_orrery/test_stage2a_epistemics_live.py::test_common_claim_can_be_revealed_without_teller_awareness_row
tests/test_orrery/test_stage2a_epistemics_live.py::test_faction_participant_mints_awareness_at_source_chunk_world_time
tests/test_orrery/test_stage2a_epistemics_live.py::test_two_hop_revelation_threads_root_and_rejects_unpossessed_teller
tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly
tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways
tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance
tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
tests/test_orrery/test_tag_provenance.py::test_chunk_keyed_bestowal_without_metadata_leaves_world_time_null
tests/test_orrery/test_tag_provenance.py::test_resolver_commit_stamps_bestowal_provenance
tests/test_presence_boost_pg.py::test_measurement_harness_uses_ephemeral_corpus
tests/test_presence_boost_pg.py::test_presence_boost_entry_point_and_summary_scope
tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants
tests/test_trait_compiler_integration.py::test_dependents_apply_and_dry_run_audit_on_save_05
tests/test_trait_compiler_integration.py::test_dunlow_shared_faction_is_permutation_invariant_on_save_05
tests/test_trait_compiler_integration.py::test_forbidden_relationship_traits_have_dry_run_apply_parity_on_save_05
tests/test_trait_compiler_integration.py::test_full_trait_selection_compiles_on_save_05
tests/test_trait_compiler_integration.py::test_shared_character_relationship_is_permutation_invariant_on_save_05
```

</details>

### Reachability, Black, Flake8, Mypy

```
$ $PY -m pytest -q tests/test_reachability.py
38 passed in 9.85s

$ $PY -m black --check <14 changed .py files>
All done! ✨ 🍰 ✨
14 files would be left unchanged.

$ $PY -m flake8 <file>   (finding count, origin/main copy vs branch)
nexus/agents/orrery/retrograde_persistence.py origin/main=0 branch=0
tests/test_api/test_attempt_manifest_pg.py origin/main=20 branch=20
tests/test_api/test_orrery_config_reuse_pg.py origin/main=0 branch=0
tests/test_bootstrap_episode_pg.py origin/main=0 branch=0
tests/test_character_name_reveals_pg.py origin/main=0 branch=0
tests/test_commit_choice_presence_pg.py origin/main=0 branch=0
tests/test_commit_handler_sync.py origin/main=7 branch=7
tests/test_lore/test_pass2_baseline_pg.py origin/main=2 branch=2
tests/test_name_reveal_staged_bindings_pg.py origin/main=0 branch=0
tests/test_name_reveal_tag_validation_pg.py origin/main=0 branch=0
tests/test_orrery/test_relationship_provenance_pg.py origin/main=9 branch=9
tests/test_orrery/test_retrograde_persistence.py origin/main=1 branch=1
tests/test_orrery/test_weather_live.py origin/main=0 branch=0
tests/test_presence_roster_pg.py origin/main=19 branch=19

$ $PY -m mypy --explicit-package-bases --ignore-missing-imports <14 modified .py files>
branch errors in the changed files: 30; origin/main errors in the same files: 30; diff: 0 lines
```

No new Black, flake8 or mypy finding: every remaining finding exists at the
same count in the `origin/main` copy of the same file. The new test in
`tests/test_orrery/test_retrograde_persistence.py` has no mypy finding. Plain
`mypy <test file>` stops with "Source file found twice under different module
names", so the comparison uses `--explicit-package-bases`.
