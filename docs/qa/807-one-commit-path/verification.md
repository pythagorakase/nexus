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

## Retrograde Re-Apply After Play

Review finding: once `find_latest_playable_chunk_id` returns a real boundary,
`nexus retrograde-apply-expansion` passes the latest played chunk as
`recorded_at_chunk_id`. `plan_retrograde_summaries` used that caller value both
as the default for new rows and as the value an existing row had to match, so
re-applying an expansion whose summaries were recorded at the prologue raised
`Retrograde world event N already has divergent summary fields:
recorded_at_chunk_id` in dry-run and in execute.

Fix (`nexus/agents/orrery/retrograde_persistence.py`, `plan_retrograde_summaries`):
a boundary is compared with an existing row only when the event source itself
carries one (the persisted-event loader and explicit sources still do). The
caller's boundary is only the default for new inserts, and an existing row
reports the boundary it was recorded at.

New PostgreSQL test
`tests/test_orrery/test_retrograde_persistence.py::test_reapplying_expansion_after_play_keeps_existing_summary_boundary`
applies a one-event expansion on a disposable template clone (summary recorded
at the prologue), accepts one turn through `commit_incubator_to_database_sync`,
asserts the lookup now returns that chunk, then re-applies the same expansion
with `recorded_at_chunk_id=find_latest_playable_chunk_id(cur)` in dry-run and
execute. Both report `events_already_present == 1`,
`summaries_already_present == 1`, status `already_present`, the original
summary id and the prologue boundary, and the table still holds one row.
Against the previous planner it fails:

```
E                   ValueError: Retrograde world event 1 already has divergent summary fields: recorded_at_chunk_id
1 failed, 25 deselected, 5 warnings in 2.06s
```

## Gates

Environment: `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset;
`PYTHONPATH=$PWD`; `$PY=/Users/pythagor/nexus/.venv/bin/python`; import proof
`nexus.__file__` = `.claude/worktrees/807-one-commit-path/nexus/__init__.py`.
Every gate below ran at `a966bc1e` (the code is unchanged after it) and every
run's terminal summary carries `secret-store guard: active; nexus-api: denied`.

### Fleet State During These Runs

The first gate on this branch hit `IDF analyzer mismatch for corpus narrative:
rebuild required` on every data clone of `save_02`..`save_04` and
`NEXUS_template` (stamp `pg_catalog.english/v1/170010`, server 170011). The
coordinator has since restamped them. Read-only check before the runs below:

```
NEXUS_template: narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011
save_02: retrograde_summary=pg_catalog.english/v1/170011, narrative=pg_catalog.english/v1/170011
save_03: narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011
save_04: narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011
save_05: narrative=pg_catalog.english/v1/170011, retrograde_summary=pg_catalog.english/v1/170011
save_01: retrograde_summary=pg_catalog.english/v1/170010, narrative=pg_catalog.english/v1/170010   (golden master, not restamped)
server_version_num: 170011
```

Both the branch gate and the `origin/main` gate below ran after the restamp.

### Ported Tests on the Real Fixtures

The two ported files that never passed on the stale fleet
(`tests/test_api/test_attempt_manifest_pg.py`, `save_04` data clones, and
`tests/test_orrery/test_relationship_provenance_pg.py`, a `save_03` data clone)
now pass unmodified on their own fixtures:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -v tests/test_api/test_attempt_manifest_pg.py tests/test_orrery/test_relationship_provenance_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
tests/test_api/test_attempt_manifest_pg.py::test_manifest_reference_privacy_retention_and_readonly PASSED
tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation PASSED
tests/test_api/test_attempt_manifest_pg.py::test_child_job_enqueue_correlation_and_transaction_reset PASSED
tests/test_api/test_attempt_manifest_pg.py::test_inspect_turn_pre_session_chunk_and_duplicate_sessions PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_analyst_sqlalchemy_helper_stamps_insert_and_replacement PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[primary] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[flashback] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[atemporal] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_canceling_producers_retain_versions_and_crossings[sync] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_canceling_producers_retain_versions_and_crossings[async] PASSED
secret-store guard: active; nexus-api: denied; disposable keychain: denied
============================= 10 passed in 34.16s ==============================
```

Before the fleet restamp, the same ten ids also passed with an evidence-only,
uncommitted patch to `tests/pg_fixtures.py::disposable_slot_database` that
rebuilt each disposable data clone's IDF projection under the server's stamp
(the migration 114 backfill: clear `memory_idf_lexemes` and
`memory_idf_documents`, restamp `memory_idf_corpora`, re-sync every narrative
chunk and summary): `10 passed, 9 warnings in 43.43s`. The patch was reverted
and is not part of this branch.

### Changed-File Tests (PostgreSQL, Verbose)

Every test file this branch changes, run whole, plus the owner's named
`claim_parent_embedding` test:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -v tests/test_orrery/test_playable_narrative_boundary.py::test_parent_claim_embeds_only_older_unembedded_playable_chunks tests/test_api/test_attempt_manifest_pg.py tests/test_api/test_orrery_config_reuse_pg.py tests/test_bootstrap_episode_pg.py tests/test_character_name_reveals_pg.py tests/test_commit_choice_presence_pg.py tests/test_commit_handler_sync.py tests/test_lore/test_pass2_baseline_pg.py tests/test_name_reveal_staged_bindings_pg.py tests/test_name_reveal_tag_validation_pg.py tests/test_orrery/test_relationship_provenance_pg.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_weather_live.py tests/test_presence_roster_pg.py
tests/test_orrery/test_playable_narrative_boundary.py::test_parent_claim_embeds_only_older_unembedded_playable_chunks PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_regeneration_replace_and_acceptance_failure_roll_back PASSED
tests/test_orrery/test_retrograde_persistence.py::test_latest_playable_chunk_is_the_last_accepted_chunk_not_the_prologue PASSED
tests/test_orrery/test_retrograde_persistence.py::test_reapplying_expansion_after_play_keeps_existing_summary_boundary PASSED
...
======================= 111 passed in 118.25s (0:01:58) ========================
```

No skips and no failures.

<details><summary>All 111 PASSED lines</summary>

```
tests/test_orrery/test_playable_narrative_boundary.py::test_parent_claim_embeds_only_older_unembedded_playable_chunks PASSED
tests/test_api/test_attempt_manifest_pg.py::test_manifest_reference_privacy_retention_and_readonly PASSED
tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation PASSED
tests/test_api/test_attempt_manifest_pg.py::test_child_job_enqueue_correlation_and_transaction_reset PASSED
tests/test_api/test_attempt_manifest_pg.py::test_inspect_turn_pre_session_chunk_and_duplicate_sessions PASSED
tests/test_api/test_orrery_config_reuse_pg.py::test_sync_commit_loads_application_config_once PASSED
tests/test_bootstrap_episode_pg.py::test_opening_and_real_transitions_schedule_only_populated_predecessors PASSED
tests/test_character_name_reveals_pg.py::test_accepted_reveal_preserves_id_history_and_one_presence_row PASSED
tests/test_character_name_reveals_pg.py::test_reveal_and_alias_rollback_with_acceptance_failure PASSED
tests/test_character_name_reveals_pg.py::test_async_name_delta_has_identical_json_with_either_codec[False] PASSED
tests/test_character_name_reveals_pg.py::test_async_name_delta_has_identical_json_with_either_codec[True] PASSED
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
tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_component_regeneration_sparse_promotion_restore_and_cascade PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_window_change_rebases_accepted_baseline_and_semantic_change_refuses PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_acceptance_failure_rolls_back_chunk_baseline_and_incubator_delete PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_regeneration_replace_and_acceptance_failure_roll_back PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_missing_tail_error_and_admin_stamp_boundary PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_story_settings_pinned_window_survives_accepted_turn PASSED
tests/test_lore/test_pass2_baseline_pg.py::test_evaluation_database_baseline_stamp_uses_story_settings PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[reference] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[departure] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[state] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[relationship1] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_conflicting_reveal_id_is_rejected_before_any_acceptance_write[relationship2] PASSED
tests/test_name_reveal_staged_bindings_pg.py::test_new_unique_alias_state_update_binds_before_draft_validation PASSED
tests/test_name_reveal_tag_validation_pg.py::test_reveal_registry_validation_and_acceptance_keep_active_tag_unchanged[False] PASSED
tests/test_name_reveal_tag_validation_pg.py::test_reveal_registry_validation_and_acceptance_keep_active_tag_unchanged[True] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_analyst_sqlalchemy_helper_stamps_insert_and_replacement PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[primary] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[flashback] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_gaia_milestone_retains_layer_and_resolver_filter[atemporal] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_canceling_producers_retain_versions_and_crossings[sync] PASSED
tests/test_orrery/test_relationship_provenance_pg.py::test_canceling_producers_retain_versions_and_crossings[async] PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_plan_resolves_row_shaped_dry_run PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_plan_reports_unresolved_refs PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_plan_can_stage_missing_entity_stubs PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_plan_reports_missing_source_enum_values PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_plan_counts_vocabulary_blocked_events PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_plan_blocks_entity_kind_incompatible_tags PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_execute_writes_canonical_rows PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_dry_run_plans_summaries PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_summaries_can_be_disabled PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_summaries_idempotent_when_embedded PASSED
tests/test_orrery/test_retrograde_persistence.py::test_plan_summaries_from_persisted_events PASSED
tests/test_orrery/test_retrograde_persistence.py::test_plan_summaries_requires_summary_text PASSED
tests/test_orrery/test_retrograde_persistence.py::test_plan_summaries_derives_content_from_canonical_world_event PASSED
tests/test_orrery/test_retrograde_persistence.py::test_plan_summaries_rejects_incoming_canonical_payload_divergence[event_ref] PASSED
tests/test_orrery/test_retrograde_persistence.py::test_plan_summaries_rejects_incoming_canonical_payload_divergence[summary] PASSED
tests/test_orrery/test_retrograde_persistence.py::test_plan_summaries_rejects_incoming_canonical_payload_divergence[chronology] PASSED
tests/test_orrery/test_retrograde_persistence.py::test_plan_summaries_rejects_non_retrograde_world_event_source PASSED
tests/test_orrery/test_retrograde_persistence.py::test_existing_event_rerun_cannot_seed_summary_from_new_plan_content PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_execute_rejects_cross_kind_relationship_plan PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_death_of_preexisting_entity_blocks PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_execute_deactivates_staged_stub PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_death_already_inactive_is_idempotent PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_death_of_unresolved_entity_blocks_execute PASSED
tests/test_orrery/test_retrograde_persistence.py::test_persistence_death_of_staged_stub_plans_deactivation PASSED
tests/test_orrery/test_retrograde_persistence.py::test_latest_playable_chunk_is_the_last_accepted_chunk_not_the_prologue PASSED
tests/test_orrery/test_retrograde_persistence.py::test_reapplying_expansion_after_play_keeps_existing_summary_boundary PASSED
tests/test_orrery/test_weather_live.py::test_binding_weather_uses_location_transit_origin_and_unknown PASSED
tests/test_orrery/test_weather_live.py::test_warm_arm_fires_from_local_weather PASSED
tests/test_orrery/test_weather_live.py::test_live_anchor_override_and_disabled_mode PASSED
tests/test_orrery/test_weather_live.py::test_sync_commit_stack_persists_scene_weather PASSED
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
```

</details>

### Offline Gate

```
$ $PY -m pytest -q
FAILED tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants
1 failed, 4032 passed, 1022 skipped in 259.08s (0:04:19)
```

The one failure is pre-existing and outside this branch: it asserts that
`prompts/storyteller_gaia.md` contains "rather than invent"; neither the prompt
nor the test changes here, and the same test fails on `origin/main` (below).

### PostgreSQL Gate

Run as `NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings -rfE <batch>`, one
batch per test directory (`tests/test_config` and `tests/config` separately)
and the root-level test files in three batches, sequentially, first on this
branch and then on a `git archive` of `origin/main` at `9a67e864` (the merge
base; the origin root batches add the deleted `tests/test_commit_handler.py`).

| Batch | This branch (`a966bc1e`) | `origin/main` (`9a67e864`) |
| --- | --- | --- |
| `tests/test_api` | 19 failed, 840 passed, 4 skipped, 4 errors in 542.04s (0:09:02) | 20 failed, 841 passed, 4 skipped, 4 errors in 509.48s (0:08:29) |
| `tests/test_orrery` | 57 failed, 1509 passed, 39 skipped, 24 errors in 247.29s (0:04:07) | 58 failed, 1510 passed, 39 skipped, 24 errors in 253.35s (0:04:13) |
| `tests/test_lore` | 1 failed, 450 passed, 1 skipped, 1 error in 121.69s (0:02:01) | 1 failed, 450 passed, 1 skipped, 1 error in 133.03s (0:02:13) |
| `tests/test_memnon` | 51 passed in 28.64s | 51 passed in 29.01s |
| `tests/test_config` | 81 passed in 3.83s | 81 passed in 3.68s |
| `tests/config` | 102 passed in 3.99s | 102 passed in 3.54s |
| `tests/test_ir_eval_v2` | 11 passed in 2.87s | 11 passed in 2.57s |
| `tests/test_runtime` | 135 passed in 82.30s (0:01:22) | 135 passed in 67.59s (0:01:07) |
| `tests/test_util` | 7 passed in 0.28s | 7 passed in 0.27s |
| root files, batch 1 of 3 | 487 passed, 11 skipped in 260.17s (0:04:20) | 505 passed, 11 skipped in 275.57s (0:04:35) |
| root files, batch 2 of 3 | 1 failed, 569 passed, 10 skipped in 68.67s (0:01:08) | 1 failed, 577 passed, 10 skipped in 82.99s (0:01:22) |
| root files, batch 3 of 3 | 6 failed, 616 passed, 19 skipped in 116.54s (0:01:56) | 6 failed, 619 passed, 19 skipped in 125.73s (0:02:05) |

The PostgreSQL gate is **not green on either tree**, and this branch adds no
failure. The failing-id sets, with the removed `sync`/`async` parameters
normalized away (`comm` of the sorted id lists):

```
branch failing ids: 113    origin/main failing ids: 115
$ comm -23 branch_ids.txt origin_ids.txt     # fail only on this branch
(empty)
$ comm -13 branch_ids.txt origin_ids.txt     # fail only on origin/main
tests/test_api/test_preferences.py::test_preferences_round_trip_keeps_repository_clean
tests/test_orrery/test_config.py::test_orrery_settings_load_queue_and_resolution_defaults
```

The two origin-only ids are artefacts of running `origin/main` from a
`git archive` (no `.git`): they shell out to `git status --porcelain` and
`git show HEAD:nexus.toml`. Isolated reruns:

```
# branch worktree
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfE tests/test_api/test_preferences.py::test_preferences_round_trip_keeps_repository_clean tests/test_orrery/test_config.py::test_orrery_settings_load_queue_and_resolution_defaults
2 passed in 0.29s

# origin/main archive, as run in the gate
E               subprocess.CalledProcessError: Command '['git', 'status', '--porcelain']' returned non-zero exit status 128.
E               subprocess.CalledProcessError: Command '['git', 'show', 'HEAD:nexus.toml']' returned non-zero exit status 128.
2 failed in 0.33s

# origin/main archive after `git init && git add -A && git commit` in the scratch copy
2 passed in 0.29s
```

Cause of every failing or erroring id on this branch (first `E` line of each
id's failure section, grouped; the same 113 ids fail on `origin/main` with the
same first line):

| Tag | Failed | Errors | Cause |
| --- | --- | --- | --- |
| `SLOT5` | 57 | 16 | #885: test hardwires slot 5, an empty story |
| `CLOCK` | 15 | 8 | #885: slot-5 live test raises need-clock anchor unavailable (no base_timestamp on the empty story) |
| `DUPCOL` | 0 | 4 | retrograde_constraints: fixture re-applies migration 123 to a template that has it |
| `RETRY` | 3 | 0 | narrative_retry_pg: psycopg2.ProgrammingError, connection re-entered recursively |
| `SCHED` | 3 | 0 | save_04 data clone carries experience jobs pinned to gpt-5.6-terra; the test provider guard fails them, so the scheduler never reaches the expected state |
| `KNOWLEDGE` | 2 | 0 | knowledge_surfacing_live: the test's stub LORE settings lack lore.render_limits, so RenderLimits validation fails |
| `PROMPT` | 1 | 0 | skald_wire: prompts/storyteller_gaia.md lacks 'rather than invent' |
| `IDF` | 0 | 1 | IDF analyzer mismatch: the fixture clones save_01, which still carries the 170010 stamp (read-only golden master) |
| `SEATBACKFILL` | 1 | 0 | seat_policy_backfill: migrate_database applies 0 migrations to the save_04 clone (assert applied >= 1) |
| `DBNAME` | 1 | 0 | new_story_cache: slot validation rejects the disposable qa838_ database name |
| `POSTCOMMIT` | 1 | 0 | narrative_post_commit: the test's gated_real_commit stub rejects the bind_session_id kwarg |

Totals: 84 failed and 29 errored ids (113), matching the batch summaries
(19 + 57 + 1 + 1 + 6 failed; 4 + 24 + 1 errors). Every id in the per-batch
tails below carries its cause tag. None of these test files is changed by this
branch. `SLOT5` and `CLOCK` (96 ids) are #885 exemptions: tests that hardwire
slot 5, an empty story; the `CLOCK` ones are slot-5 live tests whose
need-clock trigger finds no `base_timestamp`. `IDF` is the one fixture that
clones `save_01` (`tests/test_lore/test_pass2_chunk1369.py`), the golden master
the coordinator did not restamp. The remaining 16 ids (`DUPCOL`, `RETRY`,
`SCHED`, `KNOWLEDGE`, `POSTCOMMIT`, `DBNAME`, `SEATBACKFILL`, `PROMPT`) are
pre-existing failures outside this branch, left for the coordinator's triage.

<details><summary>Per-batch <code>-rfE</code> short-summary tails on this branch, with cause tags</summary>

#### `api`

```
ERROR tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404  [SLOT5]
ERROR tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_delete_handles_legacy_leading_slash_paths  [SLOT5]
ERROR tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_invalid_type_rejected  [SLOT5]
ERROR tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_portrait_upload_set_main_delete  [SLOT5]
FAILED tests/test_api/test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit  [POSTCOMMIT]
FAILED tests/test_api/test_narrative_retry_pg.py::test_dead_worker_is_advertised_exactly_as_retry_accepts_it  [RETRY]
FAILED tests/test_api/test_narrative_retry_pg.py::test_restart_reopens_the_menu_when_no_retry_can_resume  [RETRY]
FAILED tests/test_api/test_narrative_retry_pg.py::test_staging_failure_resumes_as_recovery_and_retries_once  [RETRY]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_hover_payload  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_recent_events_respect_anchor  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner  [SLOT5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_validation_rejections  [SLOT5]
FAILED tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision  [SLOT5]
FAILED tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_rechecks_generation_after_leasing_before_provider  [SCHED]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience  [SCHED]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]  [SCHED]
FAILED tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs  [SEATBACKFILL]
```

#### `orrery`

```
ERROR tests/test_orrery/test_communication_graph_live.py::test_assembly_is_deterministic_and_unknown_configured_channel_is_loud  [CLOCK]
ERROR tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum  [CLOCK]
ERROR tests/test_orrery/test_communication_graph_live.py::test_conflicted_live_pair_licenses_only_each_tellers_own_direction  [CLOCK]
ERROR tests/test_orrery/test_communication_graph_live.py::test_culture_profiles_multiply_and_record_provenance  [CLOCK]
ERROR tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge  [CLOCK]
ERROR tests/test_orrery/test_communication_graph_live.py::test_lone_row_is_sparse_and_handler_override_beats_neutral  [CLOCK]
ERROR tests/test_orrery/test_communication_graph_live.py::test_production_explain_and_entity_audit_share_one_edge_list  [CLOCK]
ERROR tests/test_orrery/test_communication_graph_live.py::test_unknown_dyad_override_key_is_loud  [CLOCK]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction  [SLOT5]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction  [SLOT5]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered  [SLOT5]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly  [SLOT5]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched  [SLOT5]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings  [SLOT5]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic  [SLOT5]
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition  [SLOT5]
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle  [SLOT5]
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_persistence_identity_binds_database_alias_without_packet_alias  [DUPCOL]
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_compiler_gate_suppresses_all_named_target_materialization  [DUPCOL]
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_packet_and_transition_keep_event_without_adversarial_rows  [DUPCOL]
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction  [DUPCOL]
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly  [SLOT5]
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways  [SLOT5]
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance  [SLOT5]
FAILED tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots  [SLOT5]
FAILED tests/test_orrery/test_claim_accounts_live.py::test_latent_sibling_secret_stays_private_until_its_own_gate_fires  [CLOCK]
FAILED tests/test_orrery/test_claim_accounts_live.py::test_old_divergent_sibling_scopes_raise_during_hydration  [CLOCK]
FAILED tests/test_orrery/test_claim_accounts_live.py::test_scope_promotion_updates_every_sibling_and_hydrates_cleanly  [CLOCK]
FAILED tests/test_orrery/test_claim_accounts_live.py::test_sibling_accounts_hydrate_predicates_and_propagate_independently  [CLOCK]
FAILED tests/test_orrery/test_claim_accounts_live.py::test_sync_variant_rejects_cross_incident_lineage_parent  [CLOCK]
FAILED tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_common_claims_are_bounded_to_their_about_entities  [CLOCK]
FAILED tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_joins_distorted_delivery_to_real_depth  [CLOCK]
FAILED tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_renders_two_hop_provenance_and_ledger_depth  [CLOCK]
FAILED tests/test_orrery/test_claim_consumption_live.py::test_historical_anchor_excludes_future_claim_and_awareness  [CLOCK]
FAILED tests/test_orrery/test_claim_consumption_live.py::test_hydration_excludes_irrelevant_history_and_empty_universe_issues_no_sql  [CLOCK]
FAILED tests/test_orrery/test_claim_consumption_live.py::test_live_predicates_cover_participant_told_common_false_and_faction  [CLOCK]
FAILED tests/test_orrery/test_claim_consumption_live.py::test_recent_claim_scope_survives_inactive_endpoints  [CLOCK]
FAILED tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity  [CLOCK]
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end  [SLOT5]
FAILED tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[False]  [KNOWLEDGE]
FAILED tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True]  [KNOWLEDGE]
FAILED tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db  [SLOT5]
FAILED tests/test_orrery/test_orbit_distance_live.py::test_hydrate_orbit_distance_from_active_relationship_graph  [CLOCK]
FAILED tests/test_orrery/test_reconstruction.py::test_checkpoint_captures_every_section_and_is_idempotent  [SLOT5]
FAILED tests/test_orrery/test_reconstruction.py::test_relationship_triggers_version_updates_and_deletes  [SLOT5]
FAILED tests/test_orrery/test_reconstruction.py::test_skald_state_updates_are_ledgered  [SLOT5]
FAILED tests/test_orrery/test_reconstruction.py::test_unattributed_relationship_write_versions_with_null_chunk  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_pair_tag_bestowal_and_clearance_replay  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_post_fix_null_world_time_uses_primary_clock_exactly  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_project_complete_hands_off_and_real_travel_applier_relocates  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_project_replay_rejects_ledger_without_applied_projection  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_project_transition_window_replays_with_zero_checkpoint_drift  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_reconstruction_refuses_pre_instrumentation_chunks  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_relationship_multi_version_unwind_order  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_relationship_unwind_restores_updates_deletes_and_drops_inserts  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_scalar_replay_round_trip_and_within_chunk_ordering  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_tag_applicability_before_fulfillment_preserves_marker  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_tag_bestowal_and_clearance_replay_at_exact_chunks  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_travel_replay_start_advance_arrive  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_verify_catches_unledgered_entity_deactivation  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_verify_catches_unledgered_scalar_drift  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_verify_catches_unlogged_tag_clear  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_verify_skips_legacy_checkpoint_without_entity_activity  [SLOT5]
FAILED tests/test_orrery/test_replay.py::test_window_born_character_fulfillment_preserves_applicability_marker  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_async_authoring_grants_unpossessed_holder  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_authored_and_revealed_secrets_replay_between_checkpoints  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_authoring_grants_unpossessed_holder_and_reveal_completes  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_authoring_rejects_non_private_and_unregistered_gate  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_unregistered_gate_in_latent_row_raises_loudly  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[primary-settings1]  [SLOT5]
FAILED tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[retrograde-settings0]  [SLOT5]
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size  [SLOT5]
```

#### `lore`

```
ERROR tests/test_lore/test_pass2_chunk1369.py::test_pass2_handles_karaoke_divergence  [IDF]
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection  [CLOCK]
```

#### `memnon`

```
```

#### `test_config`

```
```

#### `config`

```
```

#### `ir_eval_v2`

```
```

#### `runtime`

```
```

#### `util`

```
```

#### `root_rootbatch_aa`

```
```

#### `root_rootbatch_ab`

```
FAILED tests/test_new_story_cache.py::test_weird_level_round_trips_and_only_a_new_wizard_clears_it  [DBNAME]
```

#### `root_rootbatch_ac`

```
FAILED tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants  [PROMPT]
FAILED tests/test_trait_compiler_integration.py::test_dependents_apply_and_dry_run_audit_on_save_05  [SLOT5]
FAILED tests/test_trait_compiler_integration.py::test_dunlow_shared_faction_is_permutation_invariant_on_save_05  [SLOT5]
FAILED tests/test_trait_compiler_integration.py::test_forbidden_relationship_traits_have_dry_run_apply_parity_on_save_05  [SLOT5]
FAILED tests/test_trait_compiler_integration.py::test_full_trait_selection_compiles_on_save_05  [SLOT5]
FAILED tests/test_trait_compiler_integration.py::test_shared_character_relationship_is_permutation_invariant_on_save_05  [SLOT5]
```

</details>

The pre-restamp branch gate (for the record, superseded by the tables above):
`api` 25 failed / 4 errors, `orrery` 170 / 28, `lore` 4 / 4, root batches 2 / 14,
1 / 0, 6 / 0; 156 of those 258 ids failed on the IDF analyzer mismatch.

### Reachability, Black, Flake8, Mypy

Rerun at `a966bc1e` over all 15 changed `.py` files (the 14 of the first round
plus `nexus/api/commit_handler_sync.py`, whose docstring changed):

```
$ $PY -m pytest -q tests/test_reachability.py
38 passed in 7.83s

$ grep -rn "commit_handler\b" nexus/ scripts/ tests/ ir_eval/ | grep -v commit_handler_sync
$ echo $?
1

$ $PY -m black --check <15 changed .py files>
All done! ✨ 🍰 ✨
15 files would be left unchanged.

$ $PY -m flake8 <file>   (finding count, origin/main 9a67e864 copy vs branch)
nexus/agents/orrery/retrograde_persistence.py origin/main=0 branch=0
nexus/api/commit_handler_sync.py origin/main=1 branch=1
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

$ $PY -m mypy --explicit-package-bases --ignore-missing-imports <14 modified .py files>   (first round)
branch errors in the changed files: 30; origin/main errors in the same files: 30; diff: 0 lines

$ $PY -m mypy --explicit-package-bases --ignore-missing-imports nexus/agents/orrery/retrograde_persistence.py nexus/api/commit_handler_sync.py tests/test_orrery/test_retrograde_persistence.py   (this round, HEAD before vs after)
before: retrograde_persistence.py:2735 [assignment], :2900 [arg-type]
after:  retrograde_persistence.py:2745 [assignment], :2910 [arg-type]   (same two findings, shifted 10 lines)
```

No new Black, flake8 or mypy finding: every remaining finding exists at the
same count in the `origin/main` copy of the same file. The new tests in
`tests/test_orrery/test_retrograde_persistence.py` have no mypy finding. Plain
`mypy <test file>` stops with "Source file found twice under different module
names", so the comparison uses `--explicit-package-bases`.
