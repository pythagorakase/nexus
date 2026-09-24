# PostgreSQL Gate Triage: Stop Report

## Status

Stopped under the frozen work order's rule for a production defect requiring a design decision. The canonical roster reader rejects historical multi-setting chunks in the populated `save_02` corpus. No PR was opened and nothing was pushed: the proof gates have not passed. No production code, save data, migrations, or service listeners were changed by this run.

The supplied baseline log is `temp/gate/full-pg-gate-main.log`, recorded at `39b06734`:

```text
142 failed, 3223 passed, 49 skipped, 11 warnings, 39 errors in 634.07s (0:10:34)
```

This worktree actually started at `1c5ce99a` (the subsequent #919 landing). Import-path verification succeeded:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/test-fallout-repair/nexus/__init__.py
```

## Completed Work

Fetched `origin/claude/fix-post-commit-patch` and checked `gh pr view 915 --json commits,headRefName,headRefOid`. Both sources contain **two**, not three, commits; remote head is `30603bc8b5db2c8fab095cb9b13d19ae84def465`. The missing enqueue-then-drain compaction commit's SHA was requested from the coordinator.

- `db08794a` was cherry-picked as `bbae037a`: continue-validation patches `wake_scheduler`.
- `30603bc8` was cherry-picked as `ca83ef22`: correspondence and wizard-opening fixtures patch `wake_scheduler`.
- Both commit messages end with `Agent: Codex (GPT-6 Astra)`. Installed hooks ran on the amended commits; catalog regeneration passed and config validation reported no staged files to check.
- All 181 distinct FAILED/ERROR IDs from the supplied log have one primary class in the table below. These are log-based triage assignments, **not** proof of an acceptable final remainder. The repairs and overlap audit stopped at the production finding.

## Production Finding: Historical Settings

Read-only SQL on `save_02`:

```sql
SELECT r.chunk_id, r.place_id, p.name, r.reference_type::text
FROM place_chunk_references r
JOIN places p ON p.id = r.place_id
WHERE r.chunk_id IN (1374, 1425)
  AND r.reference_type::text = 'setting'
ORDER BY r.chunk_id, r.place_id;
```

| Chunk | Place ID | Place | Reference Type |
| --- | --- | --- | --- |
| 1374 | 313 | Le Chuchotement | setting |
| 1374 | 319 | Streets of New Orleans | setting |
| 1425 | 2 | The Land Rig | setting |
| 1425 | 311 | Le Chat Noir | setting |

A `conn.set_session(readonly=True)` connection and the production `read_roster(conn, chunk)` reproduced both errors:

```text
save_02 chunk 1374: ValueError: Chunk 1374 has multiple setting places
save_02 chunk 1425: ValueError: Chunk 1425 has multiple setting places
```

The guard is at `nexus/presence/roster.py:224-226`; the write-side singleton rule is at `nexus/presence/roster.py:378-379`. `nexus/api/reader_endpoints.py:270` calls the shared reader to serve context; `nexus/agents/orrery/resolver.py:1291` calls it for historical actor binding windows. `nexus/agents/lore/logon_utility.py:228-234` converts settings to a single `PlaceRef` by taking the first entry. Merely deleting the reader guard would therefore silently select a setting in a continuation consumer. Selecting a canonical setting, preserving all historical settings while enforcing singleton continuation, or migrating historical data changes the contract and needs Claude's design decision. Rewriting the context/coverage tests to avoid these chunks would conceal a production failure.

Affected original IDs (also included in class f below):

- `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape`
- `tests/test_orrery/test_projects.py::test_slot2_coverage_distribution_and_project_gate_payload`
- `tests/test_orrery/test_recruit_ally_projects.py::test_slot2_recruitment_routes_persisted_target_without_routine_drift`

## Verification Performed

Exact pytest invocation (the only pytest run in this execution):

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape > temp/gate/roster-reproduction.log 2>&1
```

Tail, verbatim:

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape
1 failed, 5 warnings in 0.26s
```

Black verification of the three cherry-picked Python files (not a repository-wide Black gate):

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check tests/test_api/test_correspondence_pg.py tests/test_api/test_narrative_continue_validation.py tests/test_wizard_opening_presence_pg.py
```

```text
All done! ✨ 🍰 ✨
3 files would be left unchanged.
```

Read-only `save_05` SQL also succeeded (the Postgres.app permission hazard did not occur):

```sql
SELECT (SELECT count(*) FROM narrative_chunks), (SELECT count(*) FROM characters);
```

```text
(0, 0)
```

## Deferred Work and Coordinator Questions

1. What is the intended historical multi-setting read/continuation contract? Supply that ruling before repair resumes.
2. Where is #915's third compaction commit? Only two are currently published.
3. Reconcile the 127 class-a IDs below with #885's named list. The adjudication-history test audits both slots 2 and 5, so slot-5 emptiness alone does not establish that all of its data debt is covered by #885. The owner explicitly exempted the whole dev-endpoint module; its multi-slot assertions are identified accordingly.
4. Finish repairs for classes b-g, and inspect class-a tests for masked b-g defects. In particular, the six class-e async URL failures can expose slot-data failures after connection repair; do not reclassify them as a without first fixing the connection contract. Relationship provenance errors are g even where tests also depend on save data.
5. Rerun the required full PostgreSQL gate and offline suite, then Black and the normal commit hooks. No claim of a green gate or a class-a-only remainder is made here. No gateway was started on 8019 or any other lane, so there is no owned service to stop.
6. Preserve scheduler helper lane 8018. Two supplied failures show an existing listener there; no ownership or live-state conclusion about that PID was established in this run.

## Classification

Each table row names one exact ID, its original outcome, exactly one primary class, and the observed cause or explicitly stated diagnostic inference. Class a rows are the exact inventory for coordinator reconciliation; they have not been fixed.

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
| `tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. Log: AssertionError: no audited slot produces resolutions — winner parity is vacuous; repoint AUDIT_SLOTS at a slot with Orrery activity |
| `tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. Log: AssertionError: save_05 is expected to bind off-screen actors |
| `tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_hover_payload` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_recent_events_respect_anchor` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. |
| `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. Log: AssertionError: no audited slot yields an actor-only winner gated on NOT(has_inbound_pair_tag(hunting)) — the what-if kill test is vacuous; repoint AUDIT_SLOTS at a slot with routine/concealment winners |
| `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. Log: AssertionError: sleep debt 500 flipped no off-screen actor's sleep template on any audited slot — the stack-side what-if assertion is vacuous; repoint AUDIT_SLOTS |
| `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_validation_rejections` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. Log: IndexError: list index out of range |
| `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. Log: AssertionError: {"detail":"No anchors to analyze: the slot has no narrative chunks"} |
| `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. Log: AssertionError: {"detail":"No anchors to analyze: the slot has no narrative chunks"} |
| `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling` | FAILED | a | Owner-exempt #885 dev endpoint assertion: audited slot data/actors/anchors absent; some assertions also cover slot 2. |
| `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape` | FAILED | f | Production roster reader rejects persisted multi-setting chunks in populated save_02; STOP finding. |
| `tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render` | FAILED | d | Cloned save_04 pass-2 baseline fingerprint is incompatible after divergence configuration changed. |
| `tests/test_api/test_scheduler_pg.py::test_scheduler_gateway_restart_recovers_leased_job` | FAILED | g | Lane 8018 was already occupied by PID 16798 in the supplied log; keep the mandated helper lane unchanged. |
| `tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_recovers_terminated_heartbeat_backend` | FAILED | g | Lane 8018 was already occupied by PID 16798 in the supplied log; keep the mandated helper lane unchanged. |
| `tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle` | FAILED | b | Worker reports promoted=0 after seeding work; scheduler consumption is the suspected race, not independently proved. |
| `tests/test_jobs_cli_pg.py::test_jobs_cli_reports_counts_and_non_terminal_rows` | FAILED | b | Expected counts omit pending and stale_rejected queue states exposed by scheduler status. |
| `tests/test_lore/test_pass2_baseline_pg.py::test_real_continuation_route_restores_pass2_baseline_in_fresh_lore` | FAILED | c | Route provider stub lacks usage_provider_name; logged payload-assembly error prevents completion. |
| `tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_lore/test_runtime_config.py::test_explicit_lore_settings_path_beats_runtime_environment` | FAILED | e | MEMNON connection setup reloads config via missing runtime path or relative nexus.toml, losing LORE config precedence. |
| `tests/test_lore/test_runtime_config.py::test_lore_without_runtime_environment_falls_back_to_repo_root` | FAILED | e | MEMNON connection setup reloads config via missing runtime path or relative nexus.toml, losing LORE config precedence. |
| `tests/test_memnon_embedding_cache.py::test_memnon_close_disposes_engine` | FAILED | e | Fixture URL uses localhost while runtime contract uses the Unix socket (empty host). |
| `tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots` | FAILED | a | Audits slots 2 and 5; neither has adjudication rows in the log, including empty slot 5. Coordinator must reconcile the multi-slot assertion with #885. Log: AssertionError: no audited slot has adjudication-log rows — the history assertions are vacuous; repoint HISTORY_SLOTS at a slot with Skald rulings |
| `tests/test_orrery/test_build_venture_async.py::test_async_build_venture_start_and_completion_match_sync` | FAILED | e | asyncpg receives the SQLAlchemy/socket URL instead of connection kwargs; slot-5 data may be a second blocker. |
| `tests/test_orrery/test_claim_accounts_live.py::test_scope_promotion_updates_every_sibling_and_hydrates_cleanly` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_accounts_live.py::test_old_divergent_sibling_scopes_raise_during_hydration` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_accounts_live.py::test_latent_sibling_secret_stays_private_until_its_own_gate_fires` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_accounts_live.py::test_sync_variant_rejects_cross_incident_lineage_parent` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_accounts_live.py::test_sibling_accounts_hydrate_predicates_and_propagate_independently` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_accounts_live.py::test_async_variant_primitive_uses_real_postgres` | FAILED | e | asyncpg receives the SQLAlchemy/socket URL instead of connection kwargs; slot-5 data may be a second blocker. |
| `tests/test_orrery/test_claim_consumption_live.py::test_hydration_excludes_irrelevant_history_and_empty_universe_issues_no_sql` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_common_claims_are_bounded_to_their_about_entities` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_consumption_live.py::test_recent_claim_scope_survives_inactive_endpoints` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_consumption_live.py::test_live_predicates_cover_participant_told_common_false_and_faction` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_consumption_live.py::test_historical_anchor_excludes_future_claim_and_awareness` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_renders_two_hop_provenance_and_ledger_depth` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_joins_distorted_delivery_to_real_depth` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_single_hop_ledgers_scheduled_time_provenance_and_policy` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_propagation_event_does_not_change_salience_or_hydration_feed` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_large_skip_drains_chained_hops_at_staggered_times` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_not_yet_mature_edge_waits` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_fan_out_cap_uses_latency_then_listener_id` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_depth_cap_is_recovered_across_separate_drains` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_age_horizon_and_nonbounded_scopes_do_not_propagate` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_late_drain_lands_hop_scheduled_inside_age_horizon` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_null_awareness_is_possession_terminal` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_null_birth_world_time_excludes_claim_from_propagation` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_non_primary_commit_skips_propagation_drain` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_cellular_clandestine_channel_uses_multiplied_latency` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_idempotent_redrain_and_disabled_config_are_noops` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_resolution_free_commit_still_drains` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_replay_reconstructs_propagated_awareness_from_event` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_checkpoint_verify_reports_unledgered_awareness_drift` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_old_checkpoint_without_awareness_section_is_skipped` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_claim_propagation_live.py::test_async_drain_matches_sync_single_hop` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: asyncpg.exceptions.RaiseError: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_court_patron_async.py::test_async_court_patron_three_write_completion` | FAILED | e | asyncpg receives the SQLAlchemy/socket URL instead of connection kwargs; slot-5 data may be a second blocker. |
| `tests/test_orrery/test_distortion_live.py::test_async_variant_mint_persists_validated_depth` | FAILED | e | asyncpg receives the SQLAlchemy/socket URL instead of connection kwargs; slot-5 data may be a second blocker. |
| `tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: AssertionError: save_05 is expected to bind off-screen actors |
| `tests/test_orrery/test_gaia_registry_schema_pg.py::test_gaia_registry_strict_schema_stays_within_measured_budget_and_limits` | FAILED | g | Measured registry enum count is 625; pinned expectation is 626 (budget bounds pass). |
| `tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True]` | FAILED | c | Live LORE harness lacks logon required by per-seat payload budget assembly. |
| `tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[False]` | FAILED | c | Live LORE harness lacks logon required by per-seat payload budget assembly. |
| `tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_mood_live.py::test_expired_unswept_tag_does_not_source_actor_binding` | FAILED | f | Temporary schema lacks characters.name required by the new roster query. |
| `tests/test_orrery/test_orbit_distance_live.py::test_hydrate_orbit_distance_from_active_relationship_graph` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_projects.py::test_slot2_coverage_distribution_and_project_gate_payload` | FAILED | f | Production roster reader rejects persisted multi-setting chunks in populated save_02; STOP finding. |
| `tests/test_orrery/test_pursue_romance_async.py::test_async_pursue_romance_start_and_completion` | FAILED | e | asyncpg receives the SQLAlchemy/socket URL instead of connection kwargs; slot-5 data may be a second blocker. |
| `tests/test_orrery/test_reconstruction.py::test_checkpoint_captures_every_section_and_is_idempotent` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: AssertionError: save_05 must carry active tags |
| `tests/test_orrery/test_reconstruction.py::test_skald_state_updates_are_ledgered` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_reconstruction.py::test_relationship_triggers_version_updates_and_deletes` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_reconstruction.py::test_unattributed_relationship_write_versions_with_null_chunk` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_recruit_ally_projects.py::test_live_stage_ladder_completion_and_applied_ledger` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_recruit_ally_projects.py::test_slot2_recruitment_routes_persisted_target_without_routine_drift` | FAILED | f | Production roster reader rejects persisted multi-setting chunks in populated save_02; STOP finding. |
| `tests/test_orrery/test_recruit_ally_replay.py::test_recruit_ally_lifecycle_replays_between_checkpoints_without_drift` | FAILED | g | Relationship insertion deadlocks against another transaction in shared save_02; owner of competing transaction needs investigation. |
| `tests/test_orrery/test_replay.py::test_scalar_replay_round_trip_and_within_chunk_ordering` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_tag_bestowal_and_clearance_replay_at_exact_chunks` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_relationship_unwind_restores_updates_deletes_and_drops_inserts` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint |
| `tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_window_born_character_fulfillment_preserves_applicability_marker` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint |
| `tests/test_orrery/test_replay.py::test_tag_applicability_before_fulfillment_preserves_marker` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_verify_catches_unledgered_scalar_drift` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_verify_catches_unledgered_entity_deactivation` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint |
| `tests/test_orrery/test_replay.py::test_verify_skips_legacy_checkpoint_without_entity_activity` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint |
| `tests/test_orrery/test_replay.py::test_reconstruction_refuses_pre_instrumentation_chunks` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: AssertionError: save_05 must carry a genesis checkpoint |
| `tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_travel_replay_start_advance_arrive` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_post_fix_null_world_time_uses_primary_clock_exactly` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_verify_catches_unlogged_tag_clear` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint |
| `tests/test_orrery/test_replay.py::test_project_transition_window_replays_with_zero_checkpoint_drift` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: AssertionError: replay project tests need one located uncommitted actor |
| `tests/test_orrery/test_replay.py::test_project_complete_hands_off_and_real_travel_applier_relocates` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: AssertionError: replay project tests need one located uncommitted actor |
| `tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: AssertionError: replay project tests need one located uncommitted actor |
| `tests/test_orrery/test_replay.py::test_project_replay_rejects_ledger_without_applied_projection` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_replay.py::test_relationship_multi_version_unwind_order` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint |
| `tests/test_orrery/test_replay.py::test_pair_tag_bestowal_and_clearance_replay` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction` | FAILED | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_reveal_live.py::test_authoring_rejects_non_private_and_unregistered_gate` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_authoring_grants_unpossessed_holder_and_reveal_completes` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_async_authoring_grants_unpossessed_holder` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. |
| `tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_unregistered_gate_in_latent_row_raises_loudly` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[retrograde-settings0]` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[primary-settings1]` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_reveal_live.py::test_authored_and_revealed_secrets_replay_between_checkpoints` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: 'NoneType' object is not subscriptable |
| `tests/test_orrery/test_seek_redemption_async.py::test_async_seek_redemption_three_write_completion` | FAILED | e | asyncpg receives the SQLAlchemy/socket URL instead of connection kwargs; slot-5 data may be a second blocker. |
| `tests/test_orrery/test_stage2a_status_live.py::test_retrograde_institutional_standing_persists_status_edge` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_stage2a_status_live.py::test_retrograde_status_skips_existing_live_standing_with_dry_run_parity` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_stage2a_status_live.py::test_wizard_time_retrograde_status_keeps_source_chunk_null` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType' |
| `tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size` | FAILED | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: AssertionError: save_05 must contain current entity tags |
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
| `tests/test_runtime/test_supervisor_live.py::test_local_profile_full_lifecycle` | FAILED | g | Supervisor up returns a gateway PID that is no longer alive; subprocess logs and port isolation need investigation. |
| `tests/test_summary_triggers.py::test_generation_failure_marker_round_trips_and_can_be_replaced_live` | FAILED | g | Summary round-trip uses the default database instead of a disposable writable fixture; INSERT and cleanup DELETE fail read-only. |
| `tests/test_trait_compiler_integration.py::test_dunlow_shared_faction_is_permutation_invariant_on_save_05` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_trait_compiler_integration.py::test_shared_character_relationship_is_permutation_invariant_on_save_05` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_trait_compiler_integration.py::test_full_trait_selection_compiles_on_save_05` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_trait_compiler_integration.py::test_dependents_apply_and_dry_run_audit_on_save_05` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_trait_compiler_integration.py::test_forbidden_relationship_traits_have_dry_run_apply_parity_on_save_05` | FAILED | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_wizard_opening_presence_pg.py::test_wizard_opening_stage_and_accept_reconcile_known_character` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_declared_character_named_without_presence_commits_present_row` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_declared_character_already_listed_present_has_one_present_row` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_declared_name_collision_raises_and_rolls_back[alias-owner]` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_declared_name_collision_raises_and_rolls_back[canonical-name]` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_wizard_opening_presence_pg.py::test_ordinary_turn_carries_promoted_presence_before_commit` | FAILED | b | Patches a removed post-commit drain; #915 changes the patch to wake_scheduler. |
| `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_portrait_upload_set_main_delete` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_invalid_type_rejected` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_delete_handles_legacy_leading_slash_paths` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_communication_graph_live.py::test_conflicted_live_pair_licenses_only_each_tellers_own_direction` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_communication_graph_live.py::test_lone_row_is_sparse_and_handler_override_beats_neutral` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_communication_graph_live.py::test_culture_profiles_multiply_and_record_provenance` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_communication_graph_live.py::test_assembly_is_deterministic_and_unknown_configured_channel_is_loud` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_communication_graph_live.py::test_unknown_dyad_override_key_is_loud` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_communication_graph_live.py::test_production_explain_and_entity_audit_share_one_edge_list` | ERROR | a | Slot-5 fixture cannot seed needs: no canonical world time or base_timestamp in empty story. Log: psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp |
| `tests/test_orrery/test_composition_sources_live.py::test_live_hostile_pair_is_symmetric_isolated_and_fires_redemption` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_composition_sources_live.py::test_live_roster_source_respects_reach_roster_liveness_and_opt_in` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_composition_sources_live.py::test_live_widened_sources_keep_resolver_and_audit_in_parity` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_writes_mutual_contact_and_feeds_next_tick` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[relationship]` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[contact]` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[hostile]` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_composition_sources_live.py::test_live_acquaintance_rebuffs_prior_ties_and_separation[different_place]` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_court_patron_projects.py::test_completion_applies_inbound_outbound_and_patron_relationship` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_court_patron_projects.py::test_completion_preserves_existing_relationship_valence` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_court_patron_replay.py::test_court_patron_completion_replays_without_drift` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: sqlalchemy.exc.NoResultFound: No row was found when one was required |
| `tests/test_orrery/test_pursue_romance_projects.py::test_sync_applier_fresh_romance_and_overwrite_preserve_first_provenance` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_seek_redemption_projects.py::test_fresh_completion_inserts_reconciliation_and_absent_grudge_is_noop` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_seek_redemption_projects.py::test_existing_negative_relationship_is_repaired_and_originals_survive_rewrite` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_seek_redemption_replay.py::test_seek_redemption_completion_replays_without_drift` | ERROR | g | Relationship fixture writes omit mandatory nexus.write_producer provenance. |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways` | ERROR | a | Empty slot-5 story lacks a required actor, place, checkpoint, tag or chunk head; see exact exception below. Log: TypeError: cannot unpack non-iterable NoneType object |

Codex (GPT-6 Astra).
