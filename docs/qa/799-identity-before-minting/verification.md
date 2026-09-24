# Identity Before Minting Verification

Work order 799, branch `claude/799-identity-before-minting`.

## Import Provenance

Run from this worktree, using the shared interpreter:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/799-identity-before-minting/nexus/__init__.py
```

## Implemented Contract

- `nexus/presence/identity.py:62`: one resolver returns resolved, ambiguous, or novel using the roster's `IdentityIndex`. Exact canonical names and unique stored aliases bind existing IDs. Case-folded collisions, shared name forms, fuzzy matches, conflicting kinds, and explicit location conflicts require review. Descriptor, role, and location evidence can narrow review candidates but cannot promote ambiguity to an automatic binding.
- `nexus/api/presence_reconciliation.py`: pre-hydration declarations use that resolver; post-insert reconciliation resolves alias declarations to their canonical IDs.
- `nexus/agents/lore/logon_utility.py`: validation runs before the provider repair delegate. `CharacterIdentityAmbiguity` inherits the terminal wire-contract exception and the existing attempt ledger retains the rejection, candidates, and review choices.
- `nexus/api/commit_handler_sync.py` and `commit_handler.py`: acceptance rechecks identity before inserting the narrative chunk. Synchronous maturation and asynchronous declaration conversion also resolve under the transaction's identity advisory lock before inserting a character.
- `nexus/agents/orrery/retrograde_persistence.py`: seeding plans use the same resolver and an alias-aware catalog; insertion rechecks under the lock. A concurrent existing binding is never classified as an inserted stub, including for death/deactivation eligibility.
- Wizard protagonist creation and trait character stubs resolve before insertion. Declaration maturation refreshes generated aliases and treats identity ambiguity as a terminal worker failure.
- Generated aliases are deterministic first-name, surname, and authored-title forms. Generation considers every character's proposed forms and canonical names plus existing aliases. Shared forms are withheld, and generated aliases made ambiguous by a later character are removed. Authored aliases are retained.

## PostgreSQL and Provider Proofs

The real acceptance proofs are in `tests/test_presence_roster_pg.py`; the wizard HTTP staging/acceptance proofs are in `tests/test_wizard_opening_presence_pg.py`. The tests verify exact canonical reuse, unique alias reuse, novel minting, repeated declarations, canonical reference IDs, and a shared surname rejected before any staging row exists.

`tests/test_orrery/test_character_identity_pg.py` exercises real Retrograde seeding, asynchronous declaration conversion, surname rejection, alias provenance and revocation, stale-plan reuse, and a place/character collision. Its terminal-rejection test uses the real OpenAI SDK against a local TEST HTTP server, PostgreSQL catalog reads, the actual provider validator and attempt ledger, and `nexus usage --run <session> --json`. With three provider repairs allowed, ambiguity makes exactly one HTTP request and produces one persisted rejection. No paid inference is used.

The full Retrograde wizard transition in `test_persistence_identity_binds_database_alias_without_packet_alias` now succeeds using the existing protagonist alias, with no alias-named duplicate. The fixture applies migration 123 only to its disposable clone.

## Save 04 Census

Source `save_04` was copied using `pg_dump --format=custom` and restored into disposable `qa640_identity799_third_census_0f520c565a81`. The repository fixture applied migration 123 only to that clone and dropped it after the census. The source was never changed or disconnected.

[census.json](census.json) records **23 characters, zero resolved to an earlier character ID, and zero ambiguous matches**. This is a conservative name/alias census, not a claim that all semantic duplicates have been identified. The scan compares each character against earlier IDs and their stored aliases; it does not invent aliases for historical rows.

The census connection sets `readonly=True` before these queries:

```sql
SELECT id, name, entity_id, summary FROM characters ORDER BY id;
SELECT character_id, alias FROM character_aliases;
```

The reusable command is:

```sh
PYTHONPATH=$PWD $PY scripts/character_identity_census.py <qa640_clone>
```

The exact clone/census invocation was:

```python
from tests.pg_fixtures import disposable_slot_database
from scripts.character_identity_census import census
with disposable_slot_database(
    'qa640_identity799_third_census', source_db='save_04', include_data=True
) as dbname:
    result = census(dbname)
```

## Review Amendments for PR #929

- **Symmetric title normalization:** `nexus/presence/normalization.py:22` applies the configured case, diacritic, and title normalization to both declared names and catalog names/aliases. Title-only equivalence remains ambiguous; it cannot authorize a binding. PostgreSQL tests cover both `Lady Ada` against `Ada` and the reverse, plus a stored `Ada` alias, through reconciliation before hydration and staging.
- **Location evidence:** character catalog reads join the `characters.current_location` place ID to its name (`nexus/presence/identity.py:194`; `nexus/api/presence_reconciliation.py:153`). The frontier comes from `continuation_setting` in the provider validator and both commit paths. `NewEntityDeclaration.scene_location` carries optional independent declaration evidence. Both locations reach the resolver; neither silently overrides the other. A different-location exact name rejects before staging; frontier evidence narrows a shared-surname candidate set without resolving it.
- **Growing batch catalog:** `nexus/presence/identity.py:153` validates against a private copy of the catalog and adds each novel declaration under a provisional negative ID. No database rows are written by validation. `Silas Wren` followed by `Silas Wrenn` fails before staging. The caller's canonical index is preserved, and read-only `asyncpg.Record` evidence is not deep-copied.
- **Terminal failure class:** `nexus/agents/orrery/retrograde_maturation.py:1585` persists `result_manifest.failure_class`, retains the required manifest schema version, and refuses requeue for `CharacterIdentityAmbiguity` even with attempts remaining. A real leased PostgreSQL job proves durable state `failed`, class `CharacterIdentityAmbiguity`, and a cleared lease nonce. Contrary to the amendment's premise, neither this branch nor fetched `origin/main` has a maturation `failure_class` column; the existing structured result manifest holds the class without an additional migration.
- **Alias provenance:** generation/revocation now uses the value `generated`; migration 123's column comment names `authored` and `generated`. Existing authored aliases remain intact.

The TEST HTTP proof now covers surname, title, location, and intra-batch ambiguity. Each case allows three repairs but makes one request and records one rejection, also read through `nexus usage --json`. Exact-name, unique-alias, and novel/idempotent mint proofs run through both real synchronous and asynchronous acceptance connections. New proofs use disposable databases; no paid inference or gateway service is used.

Fix commit `85f2fb7f` was followed by `git fetch origin` and a clean merge of `origin/main` in `c74eec9c`. The gates below run after that merge. The source import was rechecked and still resolves inside this worktree.

## Third-Round Review Amendments

Fix commit `121c356b` addresses the two remaining Codex findings. `git fetch origin && git merge origin/main` reported `Already up to date.` against `12510525654c50ef4afeb1ff4efa4cee924176e8`. The import provenance was rechecked before the final gates.

- **Truthful trait audit:** `nexus/api/trait_compiler.py:1726` resolves named character targets before planning or creating stubs, including dry runs. Exact names, aliases, and normalized names all report an existing canonical identity in `reused_entities`; only actual insertions (or planned novel dry-run insertions) enter `created_entities`. Repeated references to one identity are counted once. The result model, counters, persisted character/wizard audit, and CLI expose both collections (`nexus/api/trait_compiler_schemas.py:429`, `nexus/cli.py:251`). Ambiguity is terminal instead of a prose-only remainder.
- **One normalization implementation:** `nexus/presence/normalization.py:8` owns case folding, optional NFKD diacritic removal, whitespace, and title normalization. Minting calls these functions; `IdentityIndex.matching_keys` calls them for persistent sync/async references and Retrograde pair-hint endpoints (`nexus/presence/roster.py:309`, `nexus/agents/orrery/retrograde_maturation.py:380`). Catalog SQL reads original names and aliases; matching happens in the shared index, eliminating the separate SQL `lower(...)` identity policy. ID lookups remain direct SQL queries. No normalized column, extra migration, or database-specific Unicode policy was introduced. The prose detector retains its separate case-insensitive text search index, while identity resolution uses original labels so case-sensitive settings are not lost.
- **Real consumer proofs:** `tests/test_orrery/test_identity_consumers_pg.py:43` exercises the real compiler and persisted audit for exact, alias, normalized, and novel targets, with dry-run/apply parity and idempotent repetition. It checks the actual CLI audit renderer. `:125` loads temporary TOML through the production settings scope and tests `case_folding=false`, `strip_diacritics=true`, and `strip_titles=false` through mint checks, catalog resolution, synchronous/asynchronous persistent references, and pair hints. `:200` checks loud alias/name collision rejection. All nine PostgreSQL cases ran against disposable databases, including rejection of absent or whitespace-only references when the catalog contains a title-only name.
- **Census refreshed:** the current save_04 clone still contains 23 characters, zero matches to earlier identities, and zero ambiguous matches. The clone was dropped after the read-only census.

The broader full PostgreSQL gate exposed an older acceptance fixture without a setting: `Chunk 1 requires exactly one continuation setting; found 0: (none)`. Commit `b52ef431` adds the station setting to that fixture (`tests/test_api/test_acceptance_staging_pg.py:461`). The full acceptance file passes all 18 tests; runtime location validation remains strict. The interrupted exploratory gate and independent reproduction are recorded in the history.

Commit `db255876` repairs two more full-gate fixtures: the slot-lock test now loads the production generation-session migrations and a real session; the lifecycle fixture applies migration 123 only to its private databases when absent. Both pass (`2 passed, 7 warnings in 67.92s (0:01:07)`), including the actual CLI/gateway/TEST wizard lifecycle. Fixture names and database prefixes are unchanged. The source template and fleet are not migrated.

A second fetch brought in `725d4203` (PR #930). Merge commit `a516210a` preserves both identity and prompt-registry reachability. The only conflict was the baseline's descriptive reason. Both hooks passed, and the gates below were rerun after this final merge.

The first completed full PostgreSQL run identified eight further fixture failures, all repaired in `3e35daa7`: the affected Retrograde tests now use migrated disposable copies of save_02; clock and staging clones receive migration 123; staging anchors carry explicit settings; and the knowledge-surfacing test uses the real OrreryTickProposal. The affected modules pass 90 tests. No fleet migration was used, and no existing fixture was renamed. A final fetch/merge confirmed `origin/main` was still fully merged. The additional missing-reference regression passes through PostgreSQL and preserves fail-fast behavior for None, empty, and whitespace-only names.

The diagnostic run history, including repaired failures, is in [validation-history.md](validation-history.md). Existing TEST-provider proofs still invoke the actual `nexus usage --run <session> --json` CLI; no paid-provider flag or gateway environment was enabled.

## Final Gates

All final gates ran on source commit `3e35daa7`, after merging `origin/main` at `725d4203` in `a516210a` and confirming the final fetch was already merged. The import still resolves inside the assigned worktree. `PY=/Users/pythagor/nexus/.venv/bin/python`; `NEXUS_RUN_LIVE_LLM`, `NEXUS_800_PAID_PROOF`, `NEXUS_GATEWAY_PORT`, and `NEXUS_API_URL` were unset at launch. Repository fixtures own temporary services and their teardown.

Logs are `/tmp/nexus-799-final-{offline,pg,full-pg,reachability,black}.log`.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2708 passed, 892 skipped, 9 warnings in 113.67s (0:01:53)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_presence_roster_pg.py tests/test_wizard_opening_presence_pg.py tests/test_orrery -k 'identity or alias or declar or mint or seed'
```

```text
=========================== short test summary info ============================
FAILED tests/test_orrery/test_claim_propagation_live.py::test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
3 failed, 191 passed, 2 skipped, 1412 deselected, 9 warnings in 114.61s (0:01:54)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q
```

```text
95 failed, 3424 passed, 49 skipped, 11 warnings, 32 errors in 1067.16s (0:17:47)
```

```sh
PYTHONPATH=$PWD $PY scripts/check_reachability.py
```

```text
    "migration": 173,
    "test": 236
  },
  "test_only": 34,
  "existing_unreachable": 75,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```

```sh
git diff origin/main --name-only -- '*.py' | xargs /Users/pythagor/nexus/.venv/bin/python -m black --check
```

```text
All done! ✨ 🍰 ✨
35 files would be left unchanged.
```

The requested PostgreSQL selection has only its three exempt #885 failures: the replay participant-awareness test and both declaration-status-hint tests. Every new PostgreSQL identity proof ran. The full PostgreSQL run has **127 failing/error test instances, all matching #885's documented tests or the work order's whole-file Orrery endpoint exemption**. No nonexempt failures remain. Parameterized variants are matched against their documented test function. Offline opt-in skips do not substitute for the separate PostgreSQL runs.

<details><summary>Full PostgreSQL Exemption Audit</summary>

```text
tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts
tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable
tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_hover_payload
tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_recent_events_respect_anchor
tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner
tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures
tests/test_api/test_orrery_dev_endpoints.py::test_what_if_validation_rejections
tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]
tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle
tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling
tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
tests/test_orrery/test_claim_accounts_live.py::test_scope_promotion_updates_every_sibling_and_hydrates_cleanly
tests/test_orrery/test_claim_accounts_live.py::test_old_divergent_sibling_scopes_raise_during_hydration
tests/test_orrery/test_claim_accounts_live.py::test_latent_sibling_secret_stays_private_until_its_own_gate_fires
tests/test_orrery/test_claim_accounts_live.py::test_sync_variant_rejects_cross_incident_lineage_parent
tests/test_orrery/test_claim_accounts_live.py::test_sibling_accounts_hydrate_predicates_and_propagate_independently
tests/test_orrery/test_claim_consumption_live.py::test_hydration_excludes_irrelevant_history_and_empty_universe_issues_no_sql
tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_common_claims_are_bounded_to_their_about_entities
tests/test_orrery/test_claim_consumption_live.py::test_recent_claim_scope_survives_inactive_endpoints
tests/test_orrery/test_claim_consumption_live.py::test_live_predicates_cover_participant_told_common_false_and_faction
tests/test_orrery/test_claim_consumption_live.py::test_historical_anchor_excludes_future_claim_and_awareness
tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity
tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_renders_two_hop_provenance_and_ledger_depth
tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_joins_distorted_delivery_to_real_depth
tests/test_orrery/test_claim_propagation_live.py::test_single_hop_ledgers_scheduled_time_provenance_and_policy
tests/test_orrery/test_claim_propagation_live.py::test_propagation_event_does_not_change_salience_or_hydration_feed
tests/test_orrery/test_claim_propagation_live.py::test_large_skip_drains_chained_hops_at_staggered_times
tests/test_orrery/test_claim_propagation_live.py::test_not_yet_mature_edge_waits
tests/test_orrery/test_claim_propagation_live.py::test_fan_out_cap_uses_latency_then_listener_id
tests/test_orrery/test_claim_propagation_live.py::test_depth_cap_is_recovered_across_separate_drains
tests/test_orrery/test_claim_propagation_live.py::test_age_horizon_and_nonbounded_scopes_do_not_propagate
tests/test_orrery/test_claim_propagation_live.py::test_late_drain_lands_hop_scheduled_inside_age_horizon
tests/test_orrery/test_claim_propagation_live.py::test_null_awareness_is_possession_terminal
tests/test_orrery/test_claim_propagation_live.py::test_null_birth_world_time_excludes_claim_from_propagation
tests/test_orrery/test_claim_propagation_live.py::test_non_primary_commit_skips_propagation_drain
tests/test_orrery/test_claim_propagation_live.py::test_cellular_clandestine_channel_uses_multiplied_latency
tests/test_orrery/test_claim_propagation_live.py::test_idempotent_redrain_and_disabled_config_are_noops
tests/test_orrery/test_claim_propagation_live.py::test_resolution_free_commit_still_drains
tests/test_orrery/test_claim_propagation_live.py::test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary
tests/test_orrery/test_claim_propagation_live.py::test_replay_reconstructs_propagated_awareness_from_event
tests/test_orrery/test_claim_propagation_live.py::test_checkpoint_verify_reports_unledgered_awareness_drift
tests/test_orrery/test_claim_propagation_live.py::test_old_checkpoint_without_awareness_section_is_skipped
tests/test_orrery/test_claim_propagation_live.py::test_async_drain_matches_sync_single_hop
tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db
tests/test_orrery/test_orbit_distance_live.py::test_hydrate_orbit_distance_from_active_relationship_graph
tests/test_orrery/test_reconstruction.py::test_checkpoint_captures_every_section_and_is_idempotent
tests/test_orrery/test_reconstruction.py::test_skald_state_updates_are_ledgered
tests/test_orrery/test_reconstruction.py::test_relationship_triggers_version_updates_and_deletes
tests/test_orrery/test_reconstruction.py::test_unattributed_relationship_write_versions_with_null_chunk
tests/test_orrery/test_replay.py::test_scalar_replay_round_trip_and_within_chunk_ordering
tests/test_orrery/test_replay.py::test_tag_bestowal_and_clearance_replay_at_exact_chunks
tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder
tests/test_orrery/test_replay.py::test_relationship_unwind_restores_updates_deletes_and_drops_inserts
tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier
tests/test_orrery/test_replay.py::test_window_born_character_fulfillment_preserves_applicability_marker
tests/test_orrery/test_replay.py::test_tag_applicability_before_fulfillment_preserves_marker
tests/test_orrery/test_replay.py::test_verify_catches_unledgered_scalar_drift
tests/test_orrery/test_replay.py::test_verify_catches_unledgered_entity_deactivation
tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift
tests/test_orrery/test_replay.py::test_verify_skips_legacy_checkpoint_without_entity_activity
tests/test_orrery/test_replay.py::test_reconstruction_refuses_pre_instrumentation_chunks
tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored
tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape
tests/test_orrery/test_replay.py::test_travel_replay_start_advance_arrive
tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible
tests/test_orrery/test_replay.py::test_post_fix_null_world_time_uses_primary_clock_exactly
tests/test_orrery/test_replay.py::test_verify_catches_unlogged_tag_clear
tests/test_orrery/test_replay.py::test_project_transition_window_replays_with_zero_checkpoint_drift
tests/test_orrery/test_replay.py::test_project_complete_hands_off_and_real_travel_applier_relocates
tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning
tests/test_orrery/test_replay.py::test_project_replay_rejects_ledger_without_applied_projection
tests/test_orrery/test_replay.py::test_relationship_multi_version_unwind_order
tests/test_orrery/test_replay.py::test_pair_tag_bestowal_and_clearance_replay
tests/test_orrery/test_reveal_live.py::test_authoring_rejects_non_private_and_unregistered_gate
tests/test_orrery/test_reveal_live.py::test_authoring_grants_unpossessed_holder_and_reveal_completes
tests/test_orrery/test_reveal_live.py::test_async_authoring_grants_unpossessed_holder
tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop
tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate
tests/test_orrery/test_reveal_live.py::test_unregistered_gate_in_latent_row_raises_loudly
tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[retrograde-settings0]
tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[primary-settings1]
tests/test_orrery/test_reveal_live.py::test_authored_and_revealed_secrets_replay_between_checkpoints
tests/test_orrery/test_stage2a_status_live.py::test_retrograde_institutional_standing_persists_status_edge
tests/test_orrery/test_stage2a_status_live.py::test_retrograde_status_skips_existing_live_standing_with_dry_run_parity
tests/test_orrery/test_stage2a_status_live.py::test_wizard_time_retrograde_status_keeps_source_chunk_null
tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate
tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
tests/test_trait_compiler_integration.py::test_dunlow_shared_faction_is_permutation_invariant_on_save_05
tests/test_trait_compiler_integration.py::test_shared_character_relationship_is_permutation_invariant_on_save_05
tests/test_trait_compiler_integration.py::test_full_trait_selection_compiles_on_save_05
tests/test_trait_compiler_integration.py::test_dependents_apply_and_dry_run_audit_on_save_05
tests/test_trait_compiler_integration.py::test_forbidden_relationship_traits_have_dry_run_apply_parity_on_save_05
tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_portrait_upload_set_main_delete
tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_invalid_type_rejected
tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_delete_handles_legacy_leading_slash_paths
tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404
tests/test_orrery/test_communication_graph_live.py::test_conflicted_live_pair_licenses_only_each_tellers_own_direction
tests/test_orrery/test_communication_graph_live.py::test_lone_row_is_sparse_and_handler_override_beats_neutral
tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum
tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge
tests/test_orrery/test_communication_graph_live.py::test_culture_profiles_multiply_and_record_provenance
tests/test_orrery/test_communication_graph_live.py::test_assembly_is_deterministic_and_unknown_configured_channel_is_loud
tests/test_orrery/test_communication_graph_live.py::test_unknown_dyad_override_key_is_loud
tests/test_orrery/test_communication_graph_live.py::test_production_explain_and_entity_audit_share_one_edge_list
tests/test_orrery/test_composition_sources_live.py::test_live_hostile_pair_is_symmetric_isolated_and_fires_redemption
tests/test_orrery/test_composition_sources_live.py::test_live_roster_source_respects_reach_roster_liveness_and_opt_in
tests/test_orrery/test_composition_sources_live.py::test_live_widened_sources_keep_resolver_and_audit_in_parity
tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_writes_mutual_contact_and_feeds_next_tick
tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[relationship]
tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[contact]
tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[hostile]
tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[different_place]
tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered
tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition
tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction
tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction
tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched
tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly
tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic
tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings
tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance
tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly
tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways
```

</details>

The diagnostic and interrupted runs are retained in [validation-history.md](validation-history.md); they are not counted as passing gates.

## Land-Time Handoff

Migration `123_character_alias_provenance.sql` adds the documented `character_aliases.provenance` column, defaulting existing rows to `authored`. Runtime tuning is typed under `[character_identity]` in `nexus.toml`. The coordinator must apply migration 123 at land time; no fleet or template migration was performed.

The census does not merge or modify existing identities. This v1 rejects ambiguous declarations and records the review requirement; an interactive adjudication surface and applying explicit `same_as` / `create_new` / `distinct_from` rulings remain follow-on work. No persistent gateway or worker service was started. The full repository suite owns any temporary gateway and worker fixtures, including their cleanup.


## Coordinator Questions

No blocking implementation questions. Migration 123 remains a coordinator land-time action. The maturation failure class is stored in the existing versioned JSON result manifest because the live repository has no dedicated class column; a later uniform jobs-status projection can expose that field if desired. No PR merge, fleet migration, persistent gateway start, or paid inference was performed.

Codex, running gpt-6-astra.
