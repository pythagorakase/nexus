# Verification: De-Own the Corpus Clones and Guard the Tree (#885 B2-9b)

The review-round-two tails below ran at `2ce4aba5`, the code head after the second review round; the earlier tails, kept under their own heading, ran at `212ea7f9`. Each run started from a clean tree (`git status --porcelain` empty) and `HEAD` did not move during it; the only later commit is this docs-only file. Every PostgreSQL run loaded `-p tests.dbname_audit` and ran with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset, on the shared interpreter `/Users/pythagor/nexus/.venv/bin/python` (`$PY`) with `nexus` imported from this worktree. No paid provider was called. Each fenced tail lists whole lines selected from its run log with `grep -E "^(FAILED|ERROR)|^SKIPPED|secret-store guard|^dbname audit|[0-9]+ passed|[0-9]+ failed"` (the proof below also keeps its `^Lane ` line); no line is edited or shortened. Round-two logs sit in the session scratchpad under `885-B2-9b-fix2/`; the earlier ones under `885-B2-9b-fix/`.

## Review Round Two at `2ce4aba5`

### `proof_session_truth.py` Once on Lane 8018

Rerun at the code head, because the round-one rewrite of `tests/dbname_audit.py` (the plugin that prints the audit lines) postdates the first-round run. Lane 8018 had no listener before the run and none after it.

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s -p tests.dbname_audit tests/proofs/proof_session_truth.py
Lane 8018; evidence directory /private/var/folders/r5/zvbnrwp55r7dctnkr9s3b3780000gn/T/pytest-of-pythagor/pytest-1805/test_disconnected_session_brow0/775-session-truth
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_775_browser_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed, 4 warnings in 53.45s
```

### Primary Proof Set

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_scheduler_recovery_pg.py tests/test_api/test_session_truth_pg.py tests/test_api/test_reader_asset_endpoints.py tests/test_api/test_wizard_chat_validation.py tests/test_api/test_return_recap_pg.py tests/test_owner_target_guard.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 31 targets: postgres, qa640_775_errors_* x2, qa640_775_left_*, qa640_775_right_*, qa640_775_status_*, qa640_800_kill_*, qa640_800_renew_* x4, qa640_offline_gate_* x7, qa640_reader_assets_*, qa640_reader_reads_*, qa832_recap_* x10, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
146 passed, 7 warnings in 89.83s (0:01:29)
```

The count rises from 143 to 146 with the guard's three new spelling cases.

### The Files This Round Changed

`test_new_story_setup` (the template stand-in now lags migration 135, and the clone test asserts the lag set is exactly `{'135'}` and that the clone carries 135's comments again), `test_readiness_pg` (one routed stand-in is locked and stale, and the `--write-locked-slot` remediation is asserted unconditionally), `test_ann_gate` (the index build/drop and alias tests run on the seeded `qa640_766_schema_*` clone under the plain gate), `test_lore/test_infrastructure` (now holds the corpus fixtures), and `test_wizard_live` (the live tests skip; its script-path `setup_db_mocks()` resolves slots 1 and 5 to `qa640_fake_wizard_slot_1` and `qa640_fake_wizard_slot_5` through `route_slots_to_disposable`).

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_new_story_setup.py tests/test_runtime/test_readiness_pg.py tests/test_memnon/test_ann_gate.py tests/test_lore/test_infrastructure.py tests/test_wizard_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 22 targets: nexus_m10_fresh_test_75352, nexus_m10_template_test_75352, postgres, qa640_1013_readiness_* x2, qa640_766_schema_*, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa_lore_infra_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [1] tests/test_memnon/test_ann_gate.py:115: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_lore/test_infrastructure.py:219: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [8] tests/test_wizard_live.py:244: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [5] tests/test_wizard_live.py:294: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_wizard_live.py:433: Set NEXUS_ISSUE_600_LIVE=1 to run the live seed-repair proof.
33 passed, 16 skipped, 5 warnings in 28.64s
```

### Every `@requires_corpus` Case Under Its Opt-In

Eleven ran: `test_card_identity` x6, `test_projects`, `test_recruit_ally_projects`, `test_lore/test_infrastructure`, `test_pass2_chunk1369`, and `test_ann_gate::test_ann_operator_measures_and_verdict`. The two ANN tests that measure nothing corpus-specific left the opt-in for the plain gate (13 to 11).

```
NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 $PY -m pytest -q -rs -p tests.dbname_audit -m requires_corpus tests
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_766_*, qa640_781_cards_* x6, qa885_projects_corpus_*, qa885_recruit_ally_corpus_*, qa_lore_corpus_*, qa_pass2_corpus_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [1] tests/live_seed_schema_test.py:24: Set NEXUS_RUN_LIVE_LLM=1 to run live seed schema tests.
SKIPPED [1] tests/live_set_designer_test.py:36: Set NEXUS_RUN_LIVE_LLM=1 to run live set designer tests.
SKIPPED [1] tests/test_api/test_narrative_summary_paid_pg.py: Requires explicit two-call summary authorization
11 passed, 3 skipped, 5482 deselected, 9 warnings in 111.75s (0:01:51)
```

### Offline Guard

```
$PY -m pytest -q tests/test_owner_target_guard.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
39 passed, 5 warnings in 2.49s
```

On this branch the guard finds 7 uses over the tree, all admitted by its exemption table (0 unexempted); the `test_lore/conftest.py` exemption is gone because the `save_01` data clone now lives in the `requires_corpus` module `test_lore/test_infrastructure.py`.

### The Guard over `origin/main`

The current guard (`2ce4aba5`), run over `git archive origin/main tests` (`95028625`) with its allowlist and exemptions applied. It reports 19 unexempted findings; the first round's 17 came from the first-round guard, before the clone/dump rule and before the lore conftest exemption was removed.

```
tests/proofs/proof_session_truth.py:89: include_data-without-requires_corpus: disposable_slot_database( "qa640_775_browser", source_db="save_04", include_data=True )
tests/test_api/test_narrative_summary_paid_pg.py:69: include_data-without-requires_corpus: disposable_slot_database( "qa640_800b_paid", source_db="save_04", include_data=True )
tests/test_api/test_reader_asset_endpoints.py:138: connection-owner-literal: get_connection(f"save_{READ_SLOT:02d}")
tests/test_api/test_scheduler_recovery_pg.py:295: include_data-without-requires_corpus: disposable_slot_database( "qa640_800_renew", source_db="save_04", include_data=True )
tests/test_api/test_scheduler_recovery_pg.py:443: include_data-without-requires_corpus: disposable_slot_database( "qa640_800_kill", source_db="save_04", include_data=True )
tests/test_api/test_seat_policy_backfill_pg.py:24: subprocess-owner-literal: subprocess.run( [ "pg_dump", "--format=custom", "--file", str(archive), "--dbname", "save_04", ], check=True, capture_output=True, text=True, env=subprocess_env(), )
tests/test_api/test_session_truth_pg.py:153: include_data-without-requires_corpus: disposable_slot_database( "qa640_775_errors", source_db="save_04", include_data=True )
tests/test_api/test_summary_budget_usage.py:120: include_data-without-requires_corpus: disposable_slot_database( "qa640_937_budget", source_db="save_04", include_data=True )
tests/test_lore/conftest.py:116: include_data-without-requires_corpus: disposable_slot_database( "qa_lore_corpus", source_db="save_01", include_data=True )
tests/test_lore/test_baseline_fingerprint_refresh_pg.py:30: include_data-without-requires_corpus: disposable_slot_database( "qa640_908_fingerprint", source_db="save_04", include_data=True )
tests/test_lore/test_pass2_chunk1369.py:38: include_data-without-requires_corpus: disposable_slot_database( "qa_pass2_corpus", source_db="save_01", include_data=True )
tests/test_lore/test_scene_order_render.py:387: include_data-without-requires_corpus: disposable_slot_database( "qa640_scene_parent", source_db="save_04", include_data=True )
tests/test_lore/test_seat_blocks.py:397: include_data-without-requires_corpus: disposable_slot_database( "qa640_742_seat_test", source_db="save_04", include_data=True )
tests/test_memnon/test_ann_gate.py:81: clone-or-dump-literal-slot-without-requires_corpus: slot_clone(1)
tests/test_orrery/test_card_identity.py:93: include_data-without-requires_corpus: disposable_slot_database( "qa640_781_cards", source_db="save_04", include_data=True )
tests/test_orrery/test_drift_live.py:37: include_data-without-requires_corpus: disposable_slot_database( "qa640_drift", source_db="save_03", include_data=True )
tests/test_orrery/test_retrograde_maturation.py:731: include_data-without-requires_corpus: disposable_slot_database( "qa640_maturation799", source_db="save_02", include_data=True )
tests/test_orrery/test_retrograde_projects_live.py:70: include_data-without-requires_corpus: disposable_slot_database( "qa640_projects799", source_db="save_02", include_data=True )
tests/test_prose_metrics_pg.py:22: include_data-without-requires_corpus: disposable_slot_database( "qa640_prose_metrics", source_db="save_04", include_data=True )
19 unexempted findings on origin/main
  clone-or-dump-literal-slot-without-requires_corpus: 1
  connection-owner-literal: 1
  include_data-without-requires_corpus: 16
  subprocess-owner-literal: 1
```

### Lint and Types

Black: clean on every changed file. flake8: per-file finding counts equal the previous head's (`tests/test_lore/test_infrastructure.py` 5, all W291 inside a SQL string; `tests/test_memnon/test_ann_gate.py` 4, all E501 in the alias test's SQL; both counts are the same at `3971a5e9`; the other changed files have none). mypy: `tests/test_owner_target_guard.py`, `tests/test_runtime/test_readiness_pg.py`, `tests/test_memnon/test_ann_gate.py` and both lore files check clean; `tests/test_new_story_setup.py` (4) and `tests/test_wizard_live.py` (6) report errors only on lines this round did not touch.

### Not Rerun at `2ce4aba5`

The whole-tree PostgreSQL gate and the two offline directory gates below ran at `212ea7f9` and were not rerun for this round. The round's changes are test-only and confined to seven files (the five named above, `tests/test_owner_target_guard.py`, and `tests/test_lore/conftest.py`, which lost the two corpus fixtures), each covered by a tail in this section; the two ANN tests now also run under the plain gate (they passed in the tail above).

## Earlier Tails at `212ea7f9`

### Primary Proof Set

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_scheduler_recovery_pg.py tests/test_api/test_session_truth_pg.py tests/test_api/test_reader_asset_endpoints.py tests/test_api/test_wizard_chat_validation.py tests/test_api/test_return_recap_pg.py tests/test_owner_target_guard.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 31 targets: postgres, qa640_775_errors_* x2, qa640_775_left_*, qa640_775_right_*, qa640_775_status_*, qa640_800_kill_*, qa640_800_renew_* x4, qa640_offline_gate_* x7, qa640_reader_assets_*, qa640_reader_reads_*, qa832_recap_* x10, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
143 passed, 7 warnings in 90.55s (0:01:30)
```

### Every `@requires_corpus` Case Under Its Opt-In

The paid summary proof self-skips without `NEXUS_800B_PAID_PROOF=1`; the two live-LLM scripts skip without `NEXUS_RUN_LIVE_LLM=1`. The 13 that ran are `test_card_identity` (6), `test_projects` (1), `test_recruit_ally_projects` (1), `test_lore/test_infrastructure` (1, through `lore_corpus_database`), `test_pass2_chunk1369` (1), and `test_memnon/test_ann_gate` (3, newly marked in this round).

```
NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 $PY -m pytest -q -rs -p tests.dbname_audit -m requires_corpus tests
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_766_*, qa640_781_cards_* x6, qa885_projects_corpus_*, qa885_recruit_ally_corpus_*, qa_lore_corpus_*, qa_pass2_corpus_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
SKIPPED [1] tests/live_seed_schema_test.py:24: Set NEXUS_RUN_LIVE_LLM=1 to run live seed schema tests.
SKIPPED [1] tests/live_set_designer_test.py:36: Set NEXUS_RUN_LIVE_LLM=1 to run live set designer tests.
SKIPPED [1] tests/test_api/test_narrative_summary_paid_pg.py: Requires explicit two-call summary authorization
13 passed, 3 skipped, 5477 deselected, 9 warnings in 117.77s (0:01:57)
```

### Whole-Tree PostgreSQL Gate

A superset of `tests/test_api tests/test_orrery tests/test_lore`. No failure in any class. The registration line lists every cluster a private-cluster fixture registered; the admitted line lists every owner-named database opened on one, and none was opened on the owner's server.

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 635 targets: mock, nexus_m10_fresh_test_8861, nexus_m10_template_test_8861, nexus_test_813_*, nexus_test_continue_* x10, nexus_test_correspondence_* x2, nexus_test_i685_* x3, nexus_test_interactions_* x14, nexus_test_issue_613_*, nexus_test_pass2_* x7, nexus_test_retry_* x17, postgres, qa638_*, qa640_* x18, qa640_1013_absent_*, qa640_1013_idf_* x7, qa640_1013_readiness_* x2, qa640_742_seat_test_*, qa640_764_jobs_*, qa640_764_manifest_*, qa640_764_turn_*, qa640_775_errors_* x2, qa640_775_left_*, qa640_775_right_*, qa640_775_status_*, qa640_800_call_gate_*, qa640_800_corpus_*, qa640_800_kill_*, qa640_800_operator_*, qa640_800_renew_* x4, qa640_800_turn_*, qa640_800b_inspect_*, qa640_804_* x12, qa640_807_boundary_*, qa640_807_latest_playable_*, qa640_807_lifecycle_drop_*, qa640_807_lifecycle_template_*, qa640_807_lifecycle_trigger_*, qa640_807_maturation_boundary_*, qa640_807_reapply_*, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_811_full_clear_only_*, qa640_811_gaia_scene_*, qa640_811_scene_clear_only_*, qa640_811_scene_kind_*, qa640_811_scene_pin_*, qa640_811_seed_policy_*, qa640_811_tag_library_*, qa640_811_tags_audit_* x5, qa640_811_tags_audit_nocol_*, qa640_814_backfill_*, qa640_814_benchmark_*, qa640_814_seats_*, qa640_815_inspect_*, qa640_816_factory_*, qa640_816_free_text_*, qa640_816_pending_*, qa640_816_preconditions_*, qa640_816_staging_failure_*, qa640_818_estimate_*, qa640_818_pin_* x2, qa640_908_aliases_*, qa640_908_cast_*, qa640_908_fingerprint_*, qa640_910_dossier_* x7, qa640_937_budget_* x2, qa640_938_usage_* x2, qa640_acceptance_* x44, qa640_bleed_acceptance_*, qa640_bleed_proximity_* x4, qa640_claim_accounts_*, qa640_claim_consumption_*, qa640_clock_*, qa640_communication_graph_*, qa640_compaction_retry_*, qa640_connection_contract, qa640_docs_refresh_*, qa640_drift_* x2, qa640_ecology_*, qa640_geo_resolver_*, qa640_grieving_migration_*, qa640_historical_coverage_* x3, qa640_issue601_* x4, qa640_lane_close_*, qa640_maturation799_*, qa640_memnon_config_*, qa640_mig077_*, qa640_mig084_*, qa640_mig085_*, qa640_mig086_*, qa640_mig087_*, qa640_mig088_*, qa640_mig090_*, qa640_mig091_*, qa640_mig092_*, qa640_mig095_*, qa640_mig096_*, qa640_need_absence_* x7, qa640_offline_gate_* x60, qa640_orbit_distance_*, qa640_pair_tag_predicates_*, qa640_pair_tag_substrate_*, qa640_presence_audit_*, qa640_projects799_*, qa640_prose_metrics_*, qa640_provenance_* x3, qa640_raw_url_contract, qa640_reader_assets_*, qa640_reader_reads_*, qa640_reconstruction_*, qa640_regen_truncate_* x2, qa640_replay_*, qa640_retrieval_* x2, qa640_retro078_* x13, qa640_roster798_* x56, qa640_scene_clock_*, qa640_scene_null_clock_*, qa640_scene_parent_*, qa640_schema_docs_* x3, qa640_settings_stamp_*, qa640_status_bestow_*, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*, qa640_vocab_migration_* x6, qa640_weather_migration_*, qa640_window_coverage_*, qa640_wizard_drain_* x3, qa640_worker_*, qa649_*, qa653_* x2, qa654_*, qa655_*, qa655_wizard_04d12a4e7c, qa655_wizard_13cf06b9c2, qa655_wizard_168d1869d6, qa655_wizard_4f8c185e25, qa655_wizard_6fa71c75d3, qa655_wizard_de3636cca1, qa665_*, qa672_*, qa676_* x7, qa679_*, qa683_presence_* x2, qa735_gis_scripts_* x3, qa735_gis_stubs_* x5, qa735_mood_*, qa735_pair_tags_* x10, qa735_slot_model_*, qa735_weather_*, qa762_corpus_copy_*, qa762_fresh_*, qa762_idf_* x19, qa762_other_*, qa804_fixture_target, qa832_recap_* x10, qa838_genesis_weird_*, qa838_weird_level_*, qa885_adjudication_history_*, qa885_anchor_pair_seeds_*, qa885_build_venture_*, qa885_build_venture_async_*, qa885_build_venture_replay_*, qa885_character_manifest_*, qa885_character_pair_* x2, qa885_claim_awareness_replay_*, qa885_court_patron_* x2, qa885_court_patron_async_*, qa885_distortion_*, qa885_entrypoints_*, qa885_epistemics_*, qa885_evidence_*, qa885_faction_audit_*, qa885_faction_contexts_*, qa885_intertitle_*, qa885_knowledge_surfacing_*, qa885_ledger_seed_* x3, qa885_legacy_tag_* x4, qa885_orrery_dev_*, qa885_patron_circle_*, qa885_place_manifest_*, qa885_presence_baseline_*, qa885_project_promotion_*, qa885_pursue_romance_*, qa885_pursue_romance_async_*, qa885_pursue_romance_replay_*, qa885_recruit_ally_projects_*, qa885_recruit_ally_replay_*, qa885_retrieval_coverage_*, qa885_retrograde_vocab_*, qa885_reveal_*, qa885_seek_redemption_* x2, qa885_seek_redemption_async_*, qa885_signal_events_*, qa885_stage2a_epistemics_*, qa885_supervisor_*, qa885_tag_library_* x2, qa885_tag_provenance_*, qa885_trait_compiler_*, qa885_transaction_writer_*, qa946_character_* x3, qa947_episode_*, qa950_place_* x2, qa951_identity_* x4, qa951_overwrite_*, qa_identity_surface_4040352605, qa_identity_surface_667124c784, qa_identity_surface_7cdb3c4a59, qa_identity_surface_8df30b5a0e, qa_identity_surface_9be8db3e93, qa_identity_surface_e6ff82223b, qa_identity_surface_f323248082, qa_lazy_logon_*, qa_lore_infra_*, qa_model_cache_* x2, qa_player_identity_fabfb6ef9e, qa_runtime_config_* x5, qa_wt625_*, qa_wt625_empty_*, qa_wt664_*, qa_wt715_*, qa_wt720_*, qa_wt723_*, qa_wt724_experience_* x26, qa_wt724_recall_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*, test_event_sources_*, test_slot_guard_8068551637e34344b084418c48b1b3da
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:63596 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:63597 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[0] at local:63946 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[1] at local:63947 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[0] at local:63954 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard; two_clusters[1] at local:63957 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard
dbname audit: owner names admitted on registered clusters: save_04@local:63596 (psycopg2), save_04@local:63597 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
5399 passed, 94 skipped, 10 warnings in 1504.02s (0:25:04)
```

### Offline Gates

```
$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2561 passed, 389 skipped, 8 warnings in 363.05s (0:06:03)
$PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 737 skipped, 7 warnings in 30.32s
$PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 9.13s
```

### Negative Controls

- Identity check: with `if identity == _owner_identity():` changed to `if identity == -1:`, `tests/test_dbname_audit.py::test_owner_names_are_admitted_only_on_a_registered_disposable_cluster` fails, its nested session reporting `Failed: DID NOT RAISE <class 'tests.dbname_audit.OwnerEndpointRegistrationRefused'>` (the owner's server registered under a spelling the endpoint check was told to miss).
- Clone rule: `scan_source` over `05eefab7`'s `tests/test_memnon/test_ann_gate.py` returns `tests/test_memnon/test_ann_gate.py:81: clone-or-dump-literal-slot-without-requires_corpus: slot_clone(1)`.
- Exemptions: `test_an_exemption_admits_only_its_own_use` shows a new `psycopg2.connect(dbname="save_02")` in `test_memnon_db_access.py`, and a third copy of its exempted `database_url("save_04")`, are findings.

### Lint and Types

Black: clean on every changed file. flake8: per-file finding counts equal `05eefab7`'s (`tests/dbname_audit.py`, `tests/test_owner_target_guard.py`, `tests/test_dbname_audit.py` and `tests/test_pg_target_contract.py` at zero), and the `test_scheduler_corpus_pg` docstring line is now within 88 columns (12 findings to 11). mypy: per-file error counts equal `05eefab7`'s; `tests/dbname_audit.py` and `tests/test_owner_target_guard.py` check clean.
