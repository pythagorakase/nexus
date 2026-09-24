# PostgreSQL Gate Repair Verification

## Review Fixes for PR #922

Merged `origin/main` as `5fe4f7c4` and addressed the third coordinator amendment on the same branch. The source tested by the final gates is `6b1f1f0f`.

- **MEMNON configuration:** construction calls `nexus.config.loader.load_settings()` inside the owner's scope. All former `MEMNON_SETTINGS` and `GLOBAL_SETTINGS` readers now use instance dictionaries, including both evaluation entry points. Overrides validate through `MEMNONSettings`; module imports no longer load config or install logging handlers. The real two-LORE regression checks distinct debug, retrieval, and embedding settings on one disposable database (`tests/test_lore/test_runtime_config.py:169`; implementation `nexus/agents/memnon/memnon.py:207`).
- **Historical map:** `/api/current-place` returns every setting of the latest committed chunk with settings in referenced place-ID order (`nexus/api/reader_endpoints.py:565`). The map centers on the first, marks all, and uses the existing readout for all names (`ui/client/src/components/nexus/MapPane.tsx:210`). A disposable HTTP/SQL regression also excludes later uncommitted drafts (`tests/test_presence_roster_pg.py:543`).
- **Recall:** the anchor SQL carries the whole ordered setting list; scoring uses documented any-of semantics (`nexus/agents/orrery/knowledge_surfacing.py:474`). The disposable test checks a match for each setting and no match for a third place (`tests/test_presence_roster_pg.py:574`).
- **Experience metadata without migration:** formation includes the complete setting list in its fingerprint. The existing `anchor_chunk_id` links each durable experience to all canonical setting references; `_load_experience_sources` recovers ordered IDs/names for rendering and name validation (`nexus/agents/orrery/experiences.py:1410`). The scalar `location_id` remains an explicit event location or an unambiguous singleton setting, and is null for an unspecified location on a multi-setting scene. Acquisitions retain their delivered-account entitlement boundary. Disposable regressions reread the experience through a fresh connection with and without an explicit event location (`tests/test_presence_roster_pg.py:645`). This follows the work order's no-migration constraint; no duplicate list column was added.
- **Reachability:** kept exactly the two declarations already landed in #920 (`config/reachability.toml:38` and `:41`). The standalone checker reports no violations; the file now matches `origin/main`.

The built map was inspected against read-only `save_02` on lane 8019, with no scheduler and browser API requests restricted to GET. Both setting pins were marked, the center matched the first place, and there were no page errors. [Map evidence](review-map-settings.png). The owned gateway was interrupted, the same-environment `nexus down` returned `nothing running`, and `lsof` found no listener on 8019. `tests/scheduler_helpers.py:113` still selects 8018.

## Scope and Coordinator Rulings

Resumed from the first stop report after the coordinator supplied the historical-setting contract and #915's third commit. The starting worktree already contained cherry-picks `bbae037a` and `ca83ef22`; `6eb285b0` was cherry-picked as `a2ce73fe`. This work supersedes #915. No migration, fleet reset, or paid-provider opt-in is part of this repair. The reader UI location label is updated to honor the historical-settings ruling.

The supplied baseline at `39b06734` contains 181 distinct failing IDs:

```text
142 failed, 3223 passed, 49 skipped, 11 warnings, 39 errors in 634.07s (0:10:34)
```

The worktree's base also includes #919 (`1c5ce99a`). Its two new operator entry points needed reachability registration; these were not in the supplied baseline log.

Import verification:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/test-fallout-repair/nexus/__init__.py
```

Read-only current SQL confirms the #885 precondition:

```sql
SELECT (SELECT count(*) FROM narrative_chunks), (SELECT count(*) FROM characters);
```

```text
save_05: (0, 0)
```

## Repairs

- Historical rosters preserve all setting places, ordered by referenced place ID. Reader JSON returns the whole list; roster text and both reader UI location headers render every name. A continuation baseline requires exactly one setting and reports the chunk ID and every conflicting name/ID. The disposable regression inserts references in reverse place-ID order to prove stable ordering.
- LORE's explicit configuration path now scopes nested component initialization via a context variable. Database setup honors the owner's path without changing process environment or suppressing a missing-config error.
- Scheduler tests patch wakeup, unpack the two-value approval result, assert queued compaction before draining, and finish the generation lease before the scheduler pass. The lifecycle test observes the gateway scheduler's durable outcome rather than racing a second worker.
- Asyncpg fixtures use the connection-contract adapter. Provider stubs declare real-provider attributes. The knowledge-only harness explicitly disables the storyteller seat.
- Disposable corpus continuation refreshes only clone fingerprints. Gateway helpers retain lane 8018; the corpus status probe uses that same lane. Other gateway fixtures bind ephemeral ports.
- Fixture-authored relationship changes declare the manual producer. This includes masked overlaps in class-a communication, composition, faction-context, reconstruction, and replay tests; their empty-story dependency is unchanged.
- Queue summaries assert pending and stale-rejected states; the schema enum measurement tracks the current registry. Summary persistence uses a disposable clone instead of the default save. Roster-dependent miniature schemas include the columns read by the canonical query.

## Current-Behavior Evidence

- `nexus/presence/roster.py:230` enforces the continuation-only setting contract; `:262` renders every historical setting. `tests/test_presence_roster_pg.py:482` proves stable place-ID ordering and the two-setting rejection in a disposable database.
- `tests/test_api/test_reader_asset_endpoints.py:132` compares the live save_02 endpoint with the complete ordered SQL setting list.
- `nexus/config/loader.py:46` defines the lexical config scope; `nexus/agents/lore/lore.py:157` and `:359` apply it to eager and lazy component initialization. The existing explicit-path and changed-cwd integration tests pass.
- `ui/client/src/components/nexus/NarrativePane.tsx:218` builds all setting names, used by both location headers at `:440` and `:494`.

Live read-only roster output:

```text
1374 [(313, 'Le Chuchotement'), (319, 'Streets of New Orleans')]
PRESENT: Alex, Emilia, Pete, Alina, Nyati · SETTING: Le Chuchotement, Streets of New Orleans
1425 [(2, 'The Land Rig'), (311, 'Le Chat Noir')]
PRESENT: Alex, Emilia, Pete, Alina, Nyati, Sullivan · SETTING: The Land Rig, Le Chat Noir
ValueError: Chunk 1425 requires exactly one continuation setting; found 2: The Land Rig (id=2), Le Chat Noir (id=311)
```

The built reader was opened on lane 8019 with `NEXUS_SLOT` unset (no scheduler) and `PGOPTIONS='-c default_transaction_read_only=on'`. Browser API requests were additionally restricted to GET. The observed title was `THE LAND RIG, LE CHAT NOIR`, with no pane errors. [Rendered header](reader-settings.png).

The owned Uvicorn process was interrupted, then `nexus down` ran with the same lane, private runtime config, and read-only environment:

```text
nothing running
```

A final `lsof -nP -iTCP:8019 -sTCP:LISTEN` returned no listener. The scheduler test helper remains on 8018.

## Validation

[Initial repair commands](commands.md) and [review-fix commands with verbatim tails](review-commands.md) preserve diagnostics and the final evidence.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/review-full-pg.log 2>&1
```

```text
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways
95 failed, 3298 passed, 49 skipped, 11 warnings, 32 errors in 762.47s (0:12:42)
```

The gate remainder is exactly the original 127 class-(a) IDs: 95 failures and 32 setup errors. There are zero unexpected IDs and zero missing expected IDs. The complete list remains below under **#885 Remainder**; [machine-readable comparison](review-gate-comparison.json). All 54 original class-(b)–(g) IDs and the review regressions pass.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider > temp/gate/review-offline-final.log 2>&1
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2655 passed, 819 skipped, 9 warnings in 91.59s (0:01:31)
```

```sh
npm --prefix ui run check && npm --prefix ui test
```

```text
 Test Files  22 passed (22)
      Tests  238 passed (238)
   Start at  13:59:35
   Duration  1.95s (transform 1.17s, setup 989ms, collect 4.78s, tests 2.61s, environment 7.93s, prepare 1.26s)


```

```sh
npm --prefix ui run build > temp/gate/review-ui-build.log 2>&1
```

```text
PWA v1.0.3
mode      generateSW
precache  22 entries (2273.84 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only --diff-filter=ACM origin/main -- '*.py') > temp/gate/review-black-final.log 2>&1
```

```text
All done! ✨ 🍰 ✨
49 files would be left unchanged.
```

All 49 Python files changed from `origin/main` are Black-clean. The initial repair recorded 90 unrelated whole-repository formatting failures; that pre-existing formatting debt remains outside this repair. The normal commit hooks passed.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -S scripts/check_reachability.py --report temp/gate/review-reachability-final.json > temp/gate/review-reachability-final.log 2>&1
```

```text
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```

No migration, paid-provider call, or runtime-default change was introduced by the review fixes. The merge brought in the already-landed character-tag defaults from `origin/main`; `nexus.toml` and `config/reachability.toml` have no PR diff against it. No coordinator question remains: post the complete remainder to #885 at landing. This PR still supersedes #915 and remains unmerged.

## Classification

Each table row names one exact ID, its original outcome, exactly one primary class, and the observed cause or explicitly stated diagnostic inference. Class a rows retain the empty-save cause. Masked independent defects are repaired as described above.

- a: #885 empty slot 5 / explicitly exempted corpus-dependent audit.
- b: scheduler fallout (#902).
- c: seat-window fallout (#903).
- d: render-limits or divergence fallout (#916).
- e: connection-contract fallout (#897/#904).
- f: roster or need-tick fallout (#900/#905).
- g: other, with the cause named in the row.

| Class | IDs |
| --- | ---: |
| a | 127 |
| b | 10 |
| c | 3 |
| d | 1 |
| e | 9 |
| f | 4 |
| g | 27 |
| Total | 181 |

| Exact Test ID | Original Outcome | Class | Cause |
| --- | --- | --- | --- |
| `tests/test_api/test_correspondence_pg.py::test_accept_reject_hysteresis_and_digest_undo` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_api/test_narrative_continue_validation.py::test_pending_choice_rolls_back_when_auto_approval_validation_fails` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_hover_payload` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_recent_events_respect_anchor` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_validation_rejections` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling` | FAILED | a | Empty save_05 or combined slot-2/slot-5 corpus assertion; coordinator #885 exemption. |
| `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape` | FAILED | f | Historical multi-setting reads rejected by the old roster guard; repaired under the coordinator ruling. |
| `tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render` | FAILED | d | Cloned save_04 pass-2 baseline fingerprint is incompatible after divergence configuration changed. |
| `tests/test_api/test_scheduler_pg.py::test_scheduler_gateway_restart_recovers_leased_job` | FAILED | g | Lane 8018 was already occupied by PID 16798 in the supplied log; keep the mandated helper lane unchanged. |
| `tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_recovers_terminated_heartbeat_backend` | FAILED | g | Lane 8018 was already occupied by PID 16798 in the supplied log; keep the mandated helper lane unchanged. |
| `tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle` | FAILED | b | Legacy synchronous-worker counts race scheduler consumption; assert durable narration for the exact seeded tick. |
| `tests/test_jobs_cli_pg.py::test_jobs_cli_reports_counts_and_non_terminal_rows` | FAILED | b | Expected counts omit pending and stale_rejected queue states exposed by scheduler status. |
| `tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore` | FAILED | c | Route provider stub lacks usage_provider_name; logged payload-assembly error prevents completion. |
| `tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_lore/test_runtime_config.py::test_explicit_lore_settings_path_beats_runtime_environment` | FAILED | e | MEMNON connection setup reloads config via missing runtime path or relative nexus.toml, losing LORE config precedence. |
| `tests/test_lore/test_runtime_config.py::test_lore_without_runtime_environment_falls_back_to_repo_root` | FAILED | e | MEMNON connection setup reloads config via missing runtime path or relative nexus.toml, losing LORE config precedence. |
| `tests/test_memnon_embedding_cache.py::test_memnon_close_disposes_engine` | FAILED | e | Fixture URL uses localhost while runtime contract uses the Unix socket (empty host). |
| `tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots` | FAILED | a | Combined slot-2/slot-5 non-vacuity assertion; coordinator #885 exemption. |
| `tests/test_orrery/test_build_venture_async.py::test_async_build_venture_start_and_completion_match_sync` | FAILED | e | Asyncpg receives a libpq/socket URL instead of asyncpg connection kwargs; repaired with the common adapter. |
| `tests/test_orrery/test_claim_accounts_live.py::test_scope_promotion_updates_every_sibling_and_hydrates_cleanly` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_accounts_live.py::test_old_divergent_sibling_scopes_raise_during_hydration` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_accounts_live.py::test_latent_sibling_secret_stays_private_until_its_own_gate_fires` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_accounts_live.py::test_sync_variant_rejects_cross_incident_lineage_parent` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_accounts_live.py::test_sibling_accounts_hydrate_predicates_and_propagate_independently` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_accounts_live.py::test_async_variant_primitive_uses_real_postgres` | FAILED | e | Asyncpg receives a libpq/socket URL instead of asyncpg connection kwargs; repaired with the common adapter. |
| `tests/test_orrery/test_claim_consumption_live.py::test_hydration_excludes_irrelevant_history_and_empty_universe_issues_no_sql` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_common_claims_are_bounded_to_their_about_entities` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_consumption_live.py::test_recent_claim_scope_survives_inactive_endpoints` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_consumption_live.py::test_live_predicates_cover_participant_told_common_false_and_faction` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_consumption_live.py::test_historical_anchor_excludes_future_claim_and_awareness` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_renders_two_hop_provenance_and_ledger_depth` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_joins_distorted_delivery_to_real_depth` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_single_hop_ledgers_scheduled_time_provenance_and_policy` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_propagation_event_does_not_change_salience_or_hydration_feed` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_large_skip_drains_chained_hops_at_staggered_times` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_not_yet_mature_edge_waits` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_fan_out_cap_uses_latency_then_listener_id` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_depth_cap_is_recovered_across_separate_drains` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_age_horizon_and_nonbounded_scopes_do_not_propagate` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_late_drain_lands_hop_scheduled_inside_age_horizon` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_null_awareness_is_possession_terminal` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_null_birth_world_time_excludes_claim_from_propagation` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_non_primary_commit_skips_propagation_drain` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_cellular_clandestine_channel_uses_multiplied_latency` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_idempotent_redrain_and_disabled_config_are_noops` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_resolution_free_commit_still_drains` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_replay_reconstructs_propagated_awareness_from_event` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_checkpoint_verify_reports_unledgered_awareness_drift` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_old_checkpoint_without_awareness_section_is_skipped` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_claim_propagation_live.py::test_async_drain_matches_sync_single_hop` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_court_patron_async.py::test_async_court_patron_three_write_completion` | FAILED | e | Asyncpg receives a libpq/socket URL instead of asyncpg connection kwargs; repaired with the common adapter. |
| `tests/test_orrery/test_distortion_live.py::test_async_variant_mint_persists_validated_depth` | FAILED | e | Asyncpg receives a libpq/socket URL instead of asyncpg connection kwargs; repaired with the common adapter. |
| `tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end` | FAILED | a | Empty save_05: AssertionError: save_05 is expected to bind off-screen actors |
| `tests/test_orrery/test_gaia_registry_schema_pg.py::test_gaia_registry_strict_schema_stays_within_measured_budget_and_limits` | FAILED | g | Measured registry enum count is 625; pinned expectation is 626 (budget bounds pass). |
| `tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True]` | FAILED | c | Live LORE harness lacks logon required by per-seat payload budget assembly. |
| `tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[False]` | FAILED | c | Live LORE harness lacks logon required by per-seat payload budget assembly. |
| `tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_mood_live.py::test_expired_unswept_tag_does_not_source_actor_binding` | FAILED | f | Temporary schema lacks characters.name required by the new roster query. |
| `tests/test_orrery/test_orbit_distance_live.py::test_hydrate_orbit_distance_from_active_relationship_graph` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_projects.py::test_slot2_coverage_distribution_and_project_gate_payload` | FAILED | f | Historical multi-setting reads rejected by the old roster guard; repaired under the coordinator ruling. |
| `tests/test_orrery/test_pursue_romance_async.py::test_async_pursue_romance_start_and_completion` | FAILED | e | Asyncpg receives a libpq/socket URL instead of asyncpg connection kwargs; repaired with the common adapter. |
| `tests/test_orrery/test_reconstruction.py::test_checkpoint_captures_every_section_and_is_idempotent` | FAILED | a | Empty save_05: AssertionError: save_05 must carry active tags Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_reconstruction.py::test_skald_state_updates_are_ledgered` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_reconstruction.py::test_relationship_triggers_version_updates_and_deletes` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_reconstruction.py::test_unattributed_relationship_write_versions_with_null_chunk` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_recruit_ally_projects.py::test_live_stage_ladder_completion_and_applied_ledger` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_recruit_ally_projects.py::test_slot2_recruitment_routes_persisted_target_without_routine_drift` | FAILED | f | Historical multi-setting reads rejected by the old roster guard; repaired under the coordinator ruling. |
| `tests/test_orrery/test_recruit_ally_replay.py::test_recruit_ally_lifecycle_replays_between_checkpoints_without_drift` | FAILED | g | Original log deadlocked during a shared save_02 relationship insertion; no recurrence in the completed full rerun. |
| `tests/test_orrery/test_replay.py::test_scalar_replay_round_trip_and_within_chunk_ordering` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_tag_bestowal_and_clearance_replay_at_exact_chunks` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_relationship_unwind_restores_updates_deletes_and_drops_inserts` | FAILED | a | Empty save_05: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_window_born_character_fulfillment_preserves_applicability_marker` | FAILED | a | Empty save_05: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_tag_applicability_before_fulfillment_preserves_marker` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_verify_catches_unledgered_scalar_drift` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_verify_catches_unledgered_entity_deactivation` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift` | FAILED | a | Empty save_05: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_verify_skips_legacy_checkpoint_without_entity_activity` | FAILED | a | Empty save_05: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_reconstruction_refuses_pre_instrumentation_chunks` | FAILED | a | Empty save_05: AssertionError: save_05 must carry a genesis checkpoint Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_travel_replay_start_advance_arrive` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_post_fix_null_world_time_uses_primary_clock_exactly` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_verify_catches_unlogged_tag_clear` | FAILED | a | Empty save_05: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_project_transition_window_replays_with_zero_checkpoint_drift` | FAILED | a | Empty save_05: AssertionError: replay project tests need one located uncommitted actor Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_project_complete_hands_off_and_real_travel_applier_relocates` | FAILED | a | Empty save_05: AssertionError: replay project tests need one located uncommitted actor Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning` | FAILED | a | Empty save_05: AssertionError: replay project tests need one located uncommitted actor Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_project_replay_rejects_ledger_without_applied_projection` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_relationship_multi_version_unwind_order` | FAILED | a | Empty save_05: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_replay.py::test_pair_tag_bestowal_and_clearance_replay` | FAILED | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_reveal_live.py::test_authoring_rejects_non_private_and_unregistered_gate` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_authoring_grants_unpossessed_holder_and_reveal_completes` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_async_authoring_grants_unpossessed_holder` | FAILED | a | Empty save_05: Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. |
| `tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_unregistered_gate_in_latent_row_raises_loudly` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[retrograde-settings0]` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[primary-settings1]` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_authored_and_revealed_secrets_replay_between_checkpoints` | FAILED | a | Empty save_05: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_seek_redemption_async.py::test_async_seek_redemption_three_write_completion` | FAILED | e | Asyncpg receives a libpq/socket URL instead of asyncpg connection kwargs; repaired with the common adapter. |
| `tests/test_orrery/test_stage2a_status_live.py::test_retrograde_institutional_standing_persists_status_edge` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_stage2a_status_live.py::test_retrograde_status_skips_existing_live_standing_with_dry_run_parity` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_stage2a_status_live.py::test_wizard_time_retrograde_status_keeps_source_chunk_null` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate` | FAILED | a | Empty save_05: required actor/place/history lookup raises NoResultFound. |
| `tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction` | FAILED | a | Empty save_05: TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType' |
| `tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size` | FAILED | a | Empty save_05: AssertionError: save_05 must contain current entity tags |
| `tests/test_player_identity_consumers_pg.py::test_ambient_resolver_excludes_established_protagonist` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_ambient_resolver_rejects_save_without_protagonist` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_context_building_features_established_protagonist` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_context_building_rejects_save_without_protagonist` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_turn_cycle_intertitle_uses_canonical_identity_for_both_states` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_logon_context_reader_uses_canonical_identity_for_both_states` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_memnon_alias_reader_uses_canonical_pov_and_never_falls_back` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_resolver_local_weather_uses_canonical_identity_for_both_states` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_sync_gis_reader_uses_canonical_identity_for_both_states` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_retrograde_protagonist_reader_uses_canonical_identity_for_both_states` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_memory_manager_metadata_uses_canonical_identity_for_both_states` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_player_identity_consumers_pg.py::test_bootstrap_identity_and_location_use_canonical_player_for_both_states` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_runtime/test_supervisor_live.py::test_local_profile_full_lifecycle` | FAILED | g | Fixed-port lifecycle returned a dead gateway PID in the original log; the ephemeral-port fixture passes. |
| `tests/test_summary_triggers.py::test_generation_failure_marker_round_trips_and_can_be_replaced_live` | FAILED | g | Summary round-trip uses the default database instead of a disposable writable fixture; INSERT and cleanup DELETE fail read-only. |
| `tests/test_trait_compiler_integration.py::test_dunlow_shared_faction_is_permutation_invariant_on_save_05` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_trait_compiler_integration.py::test_shared_character_relationship_is_permutation_invariant_on_save_05` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_trait_compiler_integration.py::test_full_trait_selection_compiles_on_save_05` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_trait_compiler_integration.py::test_dependents_apply_and_dry_run_audit_on_save_05` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_trait_compiler_integration.py::test_forbidden_relationship_traits_have_dry_run_apply_parity_on_save_05` | FAILED | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_wizard_opening_presence_pg.py::test_wizard_opening_stage_and_accept_reconcile_known_character` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_declared_character_named_without_presence_commits_present_row` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_declared_character_already_listed_present_has_one_present_row` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_declared_name_collision_raises_and_rolls_back[alias-owner]` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_declared_name_collision_raises_and_rolls_back[canonical-name]` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_ordinary_turn_carries_promoted_presence_before_commit` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_portrait_upload_set_main_delete` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_invalid_type_rejected` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_delete_handles_legacy_leading_slash_paths` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). |
| `tests/test_orrery/test_communication_graph_live.py::test_conflicted_live_pair_licenses_only_each_tellers_own_direction` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_communication_graph_live.py::test_lone_row_is_sparse_and_handler_override_beats_neutral` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_communication_graph_live.py::test_culture_profiles_multiply_and_record_provenance` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_communication_graph_live.py::test_assembly_is_deterministic_and_unknown_configured_channel_is_loud` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_communication_graph_live.py::test_unknown_dyad_override_key_is_loud` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_communication_graph_live.py::test_production_explain_and_entity_audit_share_one_edge_list` | ERROR | a | Empty save_05: need-clock anchor unavailable (no story clock). Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_composition_sources_live.py::test_live_hostile_pair_is_symmetric_isolated_and_fires_redemption` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_composition_sources_live.py::test_live_roster_source_respects_reach_roster_liveness_and_opt_in` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_composition_sources_live.py::test_live_widened_sources_keep_resolver_and_audit_in_parity` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_writes_mutual_contact_and_feeds_next_tick` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[relationship]` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[contact]` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[hostile]` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[different_place]` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_court_patron_projects.py::test_completion_applies_inbound_outbound_and_patron_relationship` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_court_patron_projects.py::test_completion_preserves_existing_relationship_valence` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_court_patron_replay.py::test_court_patron_completion_replays_without_drift` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. Masked producer-attribution defect repaired. |
| `tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle` | ERROR | a | Empty save_05: required actor/place/history lookup raises NoResultFound. |
| `tests/test_orrery/test_pursue_romance_projects.py::test_sync_applier_fresh_romance_and_overwrite_preserve_first_provenance` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_seek_redemption_projects.py::test_fresh_completion_inserts_reconciliation_and_absent_grudge_is_noop` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_seek_redemption_projects.py::test_existing_negative_relationship_is_repaired_and_originals_survive_rewrite` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_seek_redemption_replay.py::test_seek_redemption_completion_replays_without_drift` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance` | ERROR | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly` | ERROR | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways` | ERROR | a | Empty save_05: TypeError: cannot unpack non-iterable NoneType object |

## #885 Remainder

Exactly the final gate's failure/error ID set; coordinator landing follow-up.

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

Agent: Codex (GPT-6 Astra).
