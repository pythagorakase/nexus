# Integrated Final Gates

Base: `581aad0f301a65a0cee81b65222c6cbaa999a6f5` (newest origin/main at integration). Tested branch: `8ace1995`, with the subsequent coverage assertion in state-shades.test.ts exercised by the focused/full UI gates. All commands run from the designated worktree. Long Python gates use the 589-second timeout wrapper. All 133 root files are included in six batches; remaining directories and API/Orrery are complete.

## integrated-focused

```text
STATE_SHADES_EVIDENCE_DIR=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2 npm --prefix ui test -- shell-accessibility state-shades StateGlyphs TopBar LocalModelRows MapPane SettingsPane
 ✓ src/state-shades.test.ts (4 tests) 6085ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 6047ms

 Test Files  7 passed (7)
      Tests  76 passed (76)
   Start at  06:43:13
   Duration  6.69s (transform 416ms, setup 282ms, collect 1.33s, tests 7.33s, environment 1.92s, prepare 276ms)

```

## integrated-ui-all

```text
npm --prefix ui test
 ✓ src/state-shades.test.ts (4 tests) 6723ms
   ✓ 777-S2 state shades > reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures 6685ms

 Test Files  37 passed (37)
      Tests  496 passed (496)
   Start at  06:53:36
   Duration  7.64s (transform 2.15s, setup 2.08s, collect 10.71s, tests 22.33s, environment 13.55s, prepare 1.80s)

```

## integrated-check

```text
npm --prefix ui run check

> nexus-ui@1.0.0 check
> tsc && npm run check:design-sync


> nexus-ui@1.0.0 check:design-sync
> tsc -p .design-sync/tsconfig.previews.json

```

## integrated-build

```text
npm --prefix ui run build
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 2.60s

PWA v1.0.3
mode      generateSW
precache  22 entries (2312.61 KiB)
files generated
  ../dist/public/sw.js
  ../dist/public/workbox-40c80ae4.js
```

## integrated-owner-guard

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_owner_target_guard.py
........................................................................ [ 90%]
........                                                                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
80 passed in 2.79s
```

## integrated-small

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/config tests/test_config tests/test_ir_eval_v2 tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util
secret-store guard: active; nexus-api: denied; disposable keychain: denied
502 passed, 25 skipped, 7 warnings in 63.63s (0:01:03)
```

## integrated-lore

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore
secret-store guard: active; nexus-api: denied; disposable keychain: denied
414 passed, 55 skipped, 5 warnings in 20.50s
```

## integrated-api-orrery

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1852 passed, 821 skipped, 7 warnings in 34.48s
```

## integrated-root-1

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_backfill_review_packet.py tests/test_bootstrap_episode_pg.py tests/test_character_identity.py tests/test_character_name_reveals.py tests/test_character_name_reveals_pg.py tests/test_character_relationship_id_types_pg.py tests/test_character_tag_manifest.py tests/test_chunk_lifecycle_columns_migration_pg.py tests/test_cli.py tests/test_cli_choice_http.py tests/test_cli_contract.py tests/test_cli_generation_http.py tests/test_cli_inspect_pg.py tests/test_cli_model_selection.py tests/test_cli_session_wait.py tests/test_cli_wizard_confirmation.py tests/test_clock_face.py tests/test_commit_choice_presence_pg.py tests/test_commit_chronology.py tests/test_commit_handler_sync.py tests/test_connection_lifecycle.py tests/test_correspondence.py tests/test_correspondence_live.py tests/test_database_contract.py tests/test_db_converters.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
490 passed, 28 skipped, 5 warnings in 252.70s (0:04:12)
```

## integrated-root-2

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_dbname_audit.py tests/test_doc_front_matter.py tests/test_embedding_artifacts.py tests/test_embedding_table_ownership_pg.py tests/test_entity_reference_parity_pg.py tests/test_entity_tag_manifest_apply.py tests/test_enum_column_comment_labels_pg.py tests/test_faction_table_audit.py tests/test_gis_scripts_live.py tests/test_golden_path_live.py tests/test_idf_dictionary_pg.py tests/test_inherited_slot_isolation_pg.py tests/test_intention_revision_weight.py tests/test_interaction_boundary.py tests/test_interactions_pg.py tests/test_issue_601_wizard_live.py tests/test_jobs_cli_pg.py tests/test_live_gate_clones_pg.py tests/test_local_skald_live.py tests/test_logon_mock_integration.py tests/test_lore_adapter_metadata.py tests/test_measure_place_coordinate_costs.py tests/test_measure_place_coordinate_costs_pg.py tests/test_measure_place_scale_grammar.py tests/test_measure_place_scale_grammar_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
120 passed, 145 skipped, 5 warnings in 13.49s
```

## integrated-root-3

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon_cross_encoder.py tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder_dependencies.py tests/test_memnon_db_access.py tests/test_memnon_embedding_cache.py tests/test_memnon_embedding_contract.py tests/test_memnon_model_failures_pg.py tests/test_memnon_runtime_config.py tests/test_memnon_script_model_loaders.py tests/test_migration_comment_lint.py tests/test_mock_openai.py tests/test_model_artifact_lock_committed.py tests/test_model_drift.py tests/test_model_registry_live.py tests/test_name_reveal_staged_bindings.py tests/test_name_reveal_staged_bindings_pg.py tests/test_name_reveal_tag_validation.py tests/test_name_reveal_tag_validation_pg.py tests/test_native_structured_output.py tests/test_new_story_cache.py tests/test_new_story_cli.py tests/test_new_story_integration.py tests/test_new_story_schemas.py tests/test_new_story_setup.py tests/test_new_story_setup_config.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
360 passed, 53 skipped, 8 warnings in 29.97s
```

## integrated-root-4

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_openai_registry_capabilities.py tests/test_orrery_tag_validation.py tests/test_orrery_tag_validation_pg.py tests/test_owner_target_guard.py tests/test_pg_accepted_turn_factory.py tests/test_pg_adjudication_ledger_seed.py tests/test_pg_anchor_pair_tag_seeds.py tests/test_pg_character_pair_seed.py tests/test_pg_disposable_target.py tests/test_pg_legacy_faction_tag_seed.py tests/test_pg_target_contract.py tests/test_place_tag_manifest.py tests/test_player_identity_consumers_pg.py tests/test_postgres_tools.py tests/test_presence_audit.py tests/test_presence_boost.py tests/test_presence_boost_pg.py tests/test_presence_reconciliation.py tests/test_presence_roster.py tests/test_presence_roster_pg.py tests/test_prompt_lint.py tests/test_prompt_tag_vocabulary_pg.py tests/test_prose_metrics.py tests/test_prose_metrics_pg.py tests/test_qa_shift.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
472 passed, 140 skipped, 7 warnings in 32.32s
```

## integrated-root-5

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py tests/test_rebuild_memory_idf_pg.py tests/test_record_revelation_cli_pg.py tests/test_reentry_wire_ledger.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_register_drift_study.py tests/test_retrograde_summary_retrieval.py tests/test_routine_delta_grammar_probe_pg.py tests/test_runtime_home.py tests/test_scheduler_helpers_basetemp.py tests/test_scheduler_helpers_routing.py tests/test_schema_documentation_pg.py tests/test_secret_manager.py tests/test_secret_store_guard.py tests/test_secret_store_integration.py tests/test_skald_wire.py tests/test_slot_routed_entrypoints.py tests/test_slot_utils.py tests/test_summary_triggers.py tests/test_tags_audit_pg.py tests/test_trait_compiler.py tests/test_trait_compiler_integration.py tests/test_trait_input_derivation.py tests/test_trait_menu_docs.py tests/test_travel_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
442 passed, 76 skipped, 7 warnings in 41.05s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

## integrated-root-6

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_travel_reachability_pg.py tests/test_turn_observation.py tests/test_unowned_index_adoption_pg.py tests/test_usage_recorder.py tests/test_wizard_agent.py tests/test_wizard_live.py tests/test_wizard_opening_presence_pg.py tests/test_world_clock_contract_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
87 passed, 34 skipped, 7 warnings in 5.77s
```

## integrated-reachability

```text
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.48s
```

## integrated-emitted-css

```text
node /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/inspect-css.cjs
Emitted index-DgHx-njr.css: (prefers-reduced-motion: reduce) [class*=animate-]{animation:none!important}
```

## integrated-browser

```text
node /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/777-S2/capture.cjs
Browser fixture: 45 SVGs; 12 pulse elements all animation:none; API requests: 0; page errors: 0; CSS index-DgHx-njr.css
```

## Restored-Exclusion Red Plant (Reverted)

```text
npm --prefix ui test -- shell-accessibility
    236|     expect(rule.selectors.map(normalize)).toEqual([GUARD]);

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/2]⎯

 FAIL  src/shell-accessibility.test.ts > reduced motion (app-wide animate-* guard) > map_pin_pulses_match_the_app_wide_reduced_motion_guard
AssertionError: expected [ Array(1) ] to deeply equal [ '[class*="animate-"]' ]

- Expected
+ Received

  Array [
-   "[class*=\"animate-\"]",
+   "[class*=\"animate-\"]:not(.map-pin *)",
  ]

 ❯ src/shell-accessibility.test.ts:251:47
    249|       if (within(rule, isReducedMotion) && rule.selector.includes('[cl…
    250|     });
    251|     expect(guards.map(rule => rule.selector)).toEqual([GUARD]);
       |                                               ^
    252|     expect(guards[0].nodes.some(node => node.type === "decl" && node.p…
    253|     const uses: { file: string; token: string }[] = [];

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[2/2]⎯

 Test Files  1 failed (1)
      Tests  2 failed | 7 passed (9)
   Start at  06:19:05
   Duration  410ms (transform 23ms, setup 27ms, collect 23ms, tests 30ms, environment 170ms, prepare 28ms)

```
