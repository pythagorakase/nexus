# 811-S1 Verification: Classify Every Script and ir_eval Path

Work order 811-S1 (issue #811), branch `claude/811-classify-paths`, cut from `origin/main` at `41783c1d`. No database is read or written; no migration; no gateway; no paid call.

## Premises Checked at 41783c1d

- `git ls-files scripts ir_eval | wc -l` = 223; `scripts/` 158 (78 `.py`), `ir_eval/` 65 (38 `.py`). No untracked, non-ignored files under either directory.
- `python -S scripts/check_reachability.py --report <scratch>/report.json`: of the 116 scoped `.py` files, 7 production-reachable (`scripts/__init__.py`, `api_anthropic.py`, `api_openai.py`, `database_targets.py`, `migrate.py`, `new_story_setup.py`, `summarize_narrative.py`), 19 operator- or migration-reachable only, 33 test-reachable only, 57 reached by no root.
- The six in-scope migration-reachable paths (`scripts/__init__.py`, `api_anthropic.py`, `api_openai.py`, `database_targets.py`, `migrate.py`, `summarize_narrative.py`) are all production-reachable, so no `operator` reason uses kind `migration`.
- `[[operators]]` holds 24 entries, 20 under `scripts/`.

## Counts

The first draft came from a scratch generator applying the order's rules 1-9 in order (first match wins, `fnmatch` patterns); only the TOML is committed. Every count matches item 4 of the order.

| Class | Count |
| --- | ---: |
| `pending-ruling:811-Q3` | 78 |
| `pending-ruling:811-Q5` | 38 |
| `dead` | 33 |
| `operator` | 30 |
| `test-only` | 25 |
| `documented` | 8 |
| `runtime` | 5 |
| `pending-ruling:811-Q1` | 3 |
| `pending-ruling:811-Q4` | 2 |
| `openrouter-shim` | 1 |
| **Total** | **223** |

## Graph Classes

A `dead` class is a finding for review, not a deletion decision.

### dead (33)

| Path | Reason |
| --- | --- |
| `ir_eval/evaluate_query_classifier.py` | No root reaches it; no tracked document names it. |
| `ir_eval/improve_query_classifier.py` | No root reaches it; no tracked document names it. |
| `ir_eval/improved_analyzer_implementation.py` | No root reaches it; no tracked document names it. |
| `scripts/assemble_context.py` | No root reaches it; no tracked document names it. |
| `scripts/chunk_transcripts.py` | No root reaches it; no tracked document names it. |
| `scripts/create_vector_index.py` | No root reaches it; no tracked document names it. |
| `scripts/creative_character_expansion.py` | No root reaches it; no tracked document names it. |
| `scripts/edi` | Wraps a client outside the repository (scripts/edi:5); no tracked file runs it. |
| `scripts/estimate_time_delta.py` | No root reaches it; no tracked document names it. |
| `scripts/extract_season_episode.py` | No root reaches it; no tracked document names it. |
| `scripts/fix_chunks.py` | No root reaches it; no tracked document names it. |
| `scripts/fix_episode_ranges.py` | No root reaches it; no tracked document names it. |
| `scripts/freestyle_api_query.py` | No root reaches it; no tracked document names it. |
| `scripts/import_setting.py` | No root reaches it; no tracked document names it. |
| `scripts/map_builder_legacy.py` | No root reaches it; no tracked document names it. |
| `scripts/migrate_chunk_character_references.py` | No root reaches it; no tracked document names it. |
| `scripts/migrate_provider_names.py` | No root reaches it; no tracked document names it. |
| `scripts/pr_review.py` | No root reaches it; no tracked document names it. |
| `scripts/process_characters.py` | No root reaches it; no tracked document names it. |
| `scripts/process_factions.py` | No root reaches it; no tracked document names it. |
| `scripts/query_narratives.py` | No root reaches it; no tracked document names it. |
| `scripts/query_narratives_simple.py` | No root reaches it; no tracked document names it. |
| `scripts/query_narratives_vector.py` | No root reaches it; no tracked document names it. |
| `scripts/register_production_conditions.sh` | Runs scripts/run_apex_audition_batch.py (:15), which does not exist. |
| `scripts/remove_storyteller_contamination.py` | No root reaches it; no tracked document names it. |
| `scripts/simple_update.py` | No root reaches it; no tracked document names it. |
| `scripts/test_narrative_api.py` | No root reaches it; no tracked document names it. |
| `scripts/test_setup_flow.py` | No root reaches it; no tracked document names it. |
| `scripts/token_count` | Runs scripts/token_counter.py (scripts/token_count:8), which no root reaches. |
| `scripts/token_counter.py` | No root reaches it; no tracked document names it. |
| `scripts/trim_oversized_contexts.py` | No root reaches it; no tracked document names it. |
| `scripts/update_raw_text.py` | No root reaches it; no tracked document names it. |
| `scripts/vector_migration.py` | No root reaches it; no tracked document names it. |

### documented (8)

| Path | Reason |
| --- | --- |
| `scripts/checkpoint_state.py` | No root reaches it; named by migrations/065_reconstructability.sql:137 |
| `scripts/extract_scene_numbers.py` | No root reaches it; named by docs/database.md:77 |
| `scripts/faction_relationship_analyst.py` | No root reaches it; named by migrations/135_schema_docs_backfill.sql:39 |
| `scripts/generate_octen_embeddings.py` | No root reaches it; named by ir_eval/README.md:52 |
| `scripts/import_narratives.py` | No root reaches it; named by docs/database.md:78 |
| `scripts/sync_secrets.py` | No root reaches it; named by .claude/agents/scribe.md:62 |
| `scripts/update_scene_numbers.py` | No root reaches it; named by docs/database.md:78 |
| `scripts/validate_embeddings.py` | No root reaches it; named by docs/vector_embeddings.md:208 |

### test-only (25)

| Path | Reason |
| --- | --- |
| `ir_eval/README.md` | Documents the V2 runner ir_eval/runner.py, which only tests reach. |
| `ir_eval/__init__.py` | test root tests/config/test_story_model.py:<module> |
| `ir_eval/engine/__init__.py` | test root tests/config/test_story_model.py:<module> |
| `ir_eval/engine/comparison.py` | test root tests/config/test_story_model.py:<module> |
| `ir_eval/engine/judge.py` | test root tests/config/test_story_model.py:<module> |
| `ir_eval/engine/metrics.py` | test root tests/test_ir_eval_v2/test_metrics.py:<module> |
| `ir_eval/engine/run_executor.py` | test root tests/test_database_contract.py:<module> |
| `ir_eval/engine/storage.py` | test root tests/test_database_contract.py:<module> |
| `ir_eval/golden_queries_backup.json` | V2 seed file named by ir_eval/README.md:20. |
| `ir_eval/models/__init__.py` | test root tests/test_database_contract.py:<module> |
| `ir_eval/models/schemas.py` | test root tests/test_ir_eval_v2/test_metrics.py:<module> |
| `ir_eval/runner.py` | test root tests/test_database_contract.py:<module> |
| `scripts/benchmark_experience_enqueue_fence.py` | test root tests/test_api/test_benchmark_seat_jobs_pg.py:<module> |
| `scripts/entity_reference_parity.py` | test root tests/test_entity_reference_parity_pg.py:<module> |
| `scripts/gis_backfill.py` | test root tests/test_gis_scripts_live.py:<module> |
| `scripts/gis_hygiene.py` | test root tests/test_gis_scripts_live.py:<module> |
| `scripts/import_orrery_route_graph.py` | test root tests/test_orrery/test_routing.py:<module> |
| `scripts/install_pgvector.sh` | Read by tests/test_database_contract.py:228; no root runs it. |
| `scripts/measure_presence_boost.py` | test root tests/test_presence_boost.py:<module> |
| `scripts/new_story_cli.py` | test root tests/test_new_story_cli.py:<module> |
| `scripts/regenerate_embeddings.py` | test root tests/test_regenerate_embeddings_truncate_pg.py:<module> |
| `scripts/register_drift_study.py` | test root tests/test_register_drift_study.py:<module> |
| `scripts/report_retrieval_coverage.py` | test root tests/test_lore/test_retrieval_coverage.py:<module> |
| `scripts/retrieval_query_bakeoff.py` | test root tests/test_lore/test_retrieval_query_bakeoff.py:<module> |
| `scripts/utils/embedding_utils.py` | test root tests/test_regenerate_embeddings_truncate_pg.py:<module> |

### runtime (5)

| Path | Reason |
| --- | --- |
| `scripts/__init__.py` | production root nexus/cli.py:main |
| `scripts/database_targets.py` | production root nexus/api/narrative.py:app |
| `scripts/migrate.py` | production root nexus/api/narrative.py:app |
| `scripts/new_story_setup.py` | production root nexus/api/narrative.py:app |
| `scripts/summarize_narrative.py` | production root nexus/api/narrative.py:app |

### operator (30)

| Path | Reason |
| --- | --- |
| `scripts/character_identity_census.py` | operator root scripts/character_identity_census.py:main |
| `scripts/check_migration_comments.py` | operator root scripts/check_migration_comments.py:main |
| `scripts/check_model_drift.py` | operator root scripts/check_model_drift.py:main |
| `scripts/check_reachability.py` | operator root scripts/check_reachability.py:main |
| `scripts/generate_app_icons.py` | operator root scripts/generate_app_icons.py:main |
| `scripts/orrery_sample.py` | operator root scripts/orrery_sample.py:main |
| `scripts/qa_shift/README.md` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/__init__.py` | operator root scripts/qa_shift/ann_gate.py:main |
| `scripts/qa_shift/ann_gate.py` | operator root scripts/qa_shift/ann_gate.py:main |
| `scripts/qa_shift/baselines/2026-09-23/ref_codex_bakeoff_2026_07.codex_bakeoff.json` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/baselines/2026-09-23/save_01.human_play.json` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/baselines/2026-09-23/save_04.codex_qa.json` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/card_identity_probe.py` | operator root scripts/qa_shift/card_identity_probe.py:main |
| `scripts/qa_shift/historical_passage_limit.py` | operator root scripts/qa_shift/historical_passage_limit.py:main |
| `scripts/qa_shift/long_absence_probe.py` | operator root scripts/qa_shift/long_absence_probe.py:main |
| `scripts/qa_shift/long_absence_turn.py` | operator root scripts/qa_shift/long_absence_turn.py:main |
| `scripts/qa_shift/mission_prompt.md` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/mission_report_template.md` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/probe_ledger_template.md` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/prose_metrics.py` | operator root scripts/qa_shift/prose_metrics.py:main |
| `scripts/qa_shift/qa_shift.py` | operator root scripts/qa_shift/qa_shift.py:main |
| `scripts/qa_shift/qa_shift.toml` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/reference_corpora.toml` | Asset of the scripts/qa_shift operator kit. |
| `scripts/qa_shift/world_clock.py` | operator root scripts/qa_shift/world_clock.py:main |
| `scripts/rebuild_memory_idf.py` | operator root scripts/rebuild_memory_idf.py:main |
| `scripts/replay_state.py` | operator root scripts/replay_state.py:main |
| `scripts/scratchpad_audit/README.md` | Audit kit for commissioned correspondence audits (scripts/scratchpad_audit/README.md:3-4); no code. |
| `scripts/scratchpad_audit/rubric.md` | Audit kit for commissioned correspondence audits (scripts/scratchpad_audit/README.md:3-4); no code. |
| `scripts/stamp_lore_pass_baseline.py` | operator root scripts/stamp_lore_pass_baseline.py:main |
| `scripts/validate_config_commit.py` | operator root scripts/validate_config_commit.py:main |

## Held Paths and Their Graph Class

Held classes skip the graph check. For each held Python path, the graph class the checker would expect and the first kind whose `--explain` chain reaches it (kinds tried in the order production, operator, migration, test):

| Path | Held Class | Graph Class | Evidence |
| --- | --- | --- | --- |
| `ir_eval/db.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/import_golden_queries.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/import_golden_queries.py --kind test`: root `tests/test_database_contract.py:<module>` |
| `ir_eval/ir_eval.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/ir_eval.py --kind test`: root `tests/test_config/test_ir_eval_golden_overrides.py:<module>` |
| `ir_eval/ir_eval_debug.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/ir_eval_sqlite.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/migrate_sqlite_to_postgres.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/pg_db.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/pg_db.py --kind test`: root `tests/test_database_contract.py:<module>` |
| `ir_eval/scripts/__init__.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/scripts/__init__.py --kind test`: root `tests/test_config/test_ir_eval_golden_overrides.py:<module>` |
| `ir_eval/scripts/auto_judge.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/scripts/auto_judge.py --kind test`: root `tests/test_config/test_ir_eval_golden_overrides.py:<module>` |
| `ir_eval/scripts/calculate_metrics.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/scripts/check_judgments.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/scripts/comparison.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/scripts/display.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/scripts/golden_queries_module.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/scripts/golden_queries_module.py --kind test`: root `tests/test_config/test_ir_eval_golden_overrides.py:<module>` |
| `ir_eval/scripts/ir_metrics.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/scripts/ir_metrics.py --kind test`: root `tests/test_config/test_ir_eval_golden_overrides.py:<module>` |
| `ir_eval/scripts/judge_results.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/scripts/judgments.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/scripts/pg_qrels.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/scripts/pg_qrels.py --kind test`: root `tests/test_config/test_ir_eval_golden_overrides.py:<module>` |
| `ir_eval/scripts/qrels.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/scripts/query_runner.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/scripts/settings_compare.py` | `pending-ruling:811-Q5` | `test-only` | `--explain ir_eval/scripts/settings_compare.py --kind test`: root `tests/test_config/test_ir_eval_golden_overrides.py:<module>` |
| `ir_eval/scripts/utils.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/test_comparison.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/test_db.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `ir_eval/test_pg_connection.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `scripts/api_anthropic.py` | `pending-ruling:811-Q4` | `runtime` | `--explain scripts/api_anthropic.py --kind production`: root `nexus/api/narrative.py:app` |
| `scripts/api_openai.py` | `pending-ruling:811-Q4` | `runtime` | `--explain scripts/api_openai.py --kind production`: root `nexus/api/narrative.py:app` |
| `scripts/api_openrouter.py` | `openrouter-shim` | `test-only` | `--explain scripts/api_openrouter.py --kind test`: root `tests/test_api/test_provider_guard_consumers.py:<module>` |
| `scripts/apply_slot2_semantic_tags.py` | `pending-ruling:811-Q1` | `test-only` | `--explain scripts/apply_slot2_semantic_tags.py --kind test`: root `tests/test_orrery/test_slot2_tag_backfill.py:<module>` |
| `scripts/backfill_routine_anchors.py` | `pending-ruling:811-Q1` | `documented|dead` | no root reaches it |
| `scripts/run_golden_queries.py` | `pending-ruling:811-Q5` | `documented|dead` | no root reaches it |
| `scripts/seed_slot2_routine_anchors.py` | `pending-ruling:811-Q1` | `documented|dead` | no root reaches it |

- `pending-ruling:811-Q3` non-Python (78): `ir_eval/ir_eval.db`, `ir_eval/ir_eval.db.bak`, `ir_eval/query_classifier_comparison.png`, `ir_eval/query_classifier_confusion_matrix.png`, `ir_eval/query_classifier_evaluation.json`, `ir_eval/query_classifier_improvement.json`, `ir_eval/results/detailed_comparison.json`, `ir_eval/results/ir_eval_results_character_control_20250422_211943.json`, `ir_eval/results/ir_eval_results_character_experiment_20250422_211951.json`, `ir_eval/results/ir_eval_results_control_20250422_210451.json`, `ir_eval/results/ir_eval_results_experiment_20250422_210500.json`, `ir_eval/results/ir_eval_results_relationship_control_20250422_211646.json`, `ir_eval/results/ir_eval_results_relationship_experiment_20250422_211654.json`, `ir_eval/results/merged_comparison_results.json`, `scripts/ALEX_1.md`, `scripts/ALEX_2.md`, `scripts/ALEX_3_1.md`, `scripts/ALEX_3_2.md`, `scripts/ALEX_4.md`, `scripts/ALEX_5.md`, `scripts/METADATA_README.md`, `scripts/README_embedding.md`, `scripts/add_layer_zone_to_new_story_creator.sql`, `scripts/all_episodes.json`, `scripts/all_seasons.json`, `scripts/character_context_1.json`, `scripts/character_context_26.json`, `scripts/chunk_stats.json`, `scripts/context_abyss.json`, `scripts/context_alex.json`, `scripts/context_alex_emilia.json`, `scripts/context_alex_pete.json`, `scripts/context_alina.json`, `scripts/context_badlands.json`, `scripts/context_bridge.json`, `scripts/context_dynacorp.json`, `scripts/context_elliot_tran.json`, `scripts/context_emilia.json`, `scripts/context_halcyon.json`, `scripts/context_nomads.json`, `scripts/context_nyati.json`, `scripts/context_pete.json`, `scripts/context_rustborn.json`, `scripts/context_sable_rats.json`, `scripts/context_victor.json`, `scripts/context_vox_team.json`, `scripts/create_incubator_table.sql`, `scripts/creative_character_expansion.json`, `scripts/creative_character_expansion_id_002.json`, `scripts/creative_character_expansion_id_004.json`, `scripts/creative_character_expansion_id_005.json`, `scripts/creative_character_expansion_id_023A.json`, `scripts/creative_character_expansion_id_023B.json`, `scripts/creative_character_expansion_id_023C.json`, `scripts/creative_character_expansion_id_023D.json`, `scripts/creative_character_expansion_id_023E.json`, `scripts/custom_query.json`, `scripts/faction_faction_extra_data_schema.json`, `scripts/factions.sql`, `scripts/generate_psychology.py.bak`, `scripts/map_builder.md`, `scripts/map_builder.py.new`, `scripts/map_illustrator.md`, `scripts/map_illustrator_progress.md`, `scripts/memnon_config.json`, `scripts/missing_infly_inf-retriever-v1-1.5b_1746404715.txt`, `scripts/place002_silo.json`, `scripts/populate_character_summaries_schema.json`, `scripts/resequence_chunks.sql`, `scripts/summaries_parsed.json`, `scripts/test_context.json`, `scripts/test_context2.json`, `scripts/test_context3.json`, `scripts/test_context_updated.json`, `scripts/test_fixed_chunks.json`, `scripts/test_fixed_context.json`, `scripts/test_output.txt`, `scripts/verify_pgvector_max_dim.sql`
- `pending-ruling:811-Q5` non-Python (12): `ir_eval/DB_ISSUES.md`, `ir_eval/FILES_FOR_REVIEW.md`, `ir_eval/README_PG_MIGRATION.md`, `ir_eval/REVIEW_NOTES.md`, `ir_eval/TUI_design_document.md`, `ir_eval/auto_judge.md`, `ir_eval/golden_queries.json`, `ir_eval/golden_queries.json.bak`, `ir_eval/pg_schema.sql`, `ir_eval/qrels.json`, `ir_eval/scripts/README.md`, `scripts/README_golden_queries.md`

## Red Run

A scratch plant (reverted before commit; the restored file was byte-identical, checked with `cmp`) classed `scripts/migrate.py` as `operator` and removed the entry for `scripts/edi`. `python -S scripts/check_reachability.py` exited 1; the classification block of its summary:

```text
exit=1
{
  "unclassified_paths": [
    "scripts/edi"
  ],
  "classified_paths_not_in_repository": [],
  "class_graph_mismatches": [
    {
      "path": "scripts/migrate.py",
      "class": "operator",
      "expected": "runtime"
    }
  ],
  "classification_counts": {
    "dead": 32,
    "documented": 8,
    "openrouter-shim": 1,
    "operator": 31,
    "pending-ruling:811-Q1": 3,
    "pending-ruling:811-Q3": 78,
    "pending-ruling:811-Q4": 2,
    "pending-ruling:811-Q5": 38,
    "runtime": 4,
    "test-only": 25
  }
}
```

## Green Run

`python -S scripts/check_reachability.py` (exit 0):

```json
{
  "maintained": 377,
  "reachable_by_kind": {
    "production": 215,
    "operator": 227,
    "migration": 196,
    "test": 272
  },
  "test_only": 42,
  "existing_unreachable": 61,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "unclassified_paths": [],
  "classified_paths_not_in_repository": [],
  "class_graph_mismatches": [],
  "classification_counts": {
    "dead": 33,
    "documented": 8,
    "openrouter-shim": 1,
    "operator": 30,
    "pending-ruling:811-Q1": 3,
    "pending-ruling:811-Q3": 78,
    "pending-ruling:811-Q4": 2,
    "pending-ruling:811-Q5": 38,
    "runtime": 5,
    "test-only": 25
  },
  "route_reachability": "not_proven"
}
```

## Test Tails

`python -m pytest -q tests/test_reachability.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
52 passed, 5 warnings in 10.57s
```

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 python -m pytest -q -p tests.dbname_audit tests/test_reachability.py tests/test_owner_target_guard.py` (with `NEXUS_SLOT` also unset):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
132 passed in 13.25s
```

Offline `python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2639 passed, 419 skipped, 8 warnings in 435.94s (0:07:15)
```

Offline `python -m pytest -q tests/test_api tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1816 passed, 742 skipped, 7 warnings in 41.02s
```

Black (unchanged), flake8 (clean) and mypy on `scripts/check_reachability.py` and `tests/test_reachability.py`: mypy reports four errors in `scripts/check_reachability.py` (three `"AST" has no attribute "lineno"` in `ImportVisitor.record`, one `None` assignment in the tombstone `toml_key` branch). All four are present unchanged on `origin/main` (same lines before this change's eight-line docstring); none is in the code this change adds. The test file is clean.

## Mutation Checks

Two scratch edits to `_expected_graph_class` (each restored from a copy afterwards) confirm the graph tests bind the rule:

- Dropping the migration kind (`or path in reachable["migration"]`): `pytest -k "graph_classes or ratchet"` gave `2 failed, 12 passed` (the two base-fixture cases where only the migration loader reaches `scripts/migrate.py`).
- Moving the production branch below the test branch: `pytest -k graph_classes` gave `8 failed, 2 passed`.

## Review Fixes at 1f298eb1

The tails above ran before the review round. Commit `1f298eb1` changes only `tests/test_reachability.py`, `docs/reachability.md`, and a comment in `config/reachability.toml`. The checker and the classification entries do not change, so the counts, the red run and the green run above still hold. These tails ran on `1f298eb1`:

`python -m pytest -q tests/test_reachability.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
52 passed, 5 warnings in 11.07s
```

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 python -m pytest -q -p tests.dbname_audit tests/test_reachability.py tests/test_owner_target_guard.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
132 passed in 12.68s
```

`python -S scripts/check_reachability.py` exits 0 with three empty lists and the counts in the table above. Black leaves both Python files unchanged, flake8 is clean, and mypy reports the same four pre-existing errors in `scripts/check_reachability.py` and none in the test file.

The graph fixture now gives `scripts/shared.py` a production and an operator root (`scripts/tool.py` imports it) and gives `scripts/tool_helper.py` an operator and a test root (`tests/test_example.py` imports it). The decision test now finds the first 811-S1 rule (1-8, in order) for each entry and asserts that the paths falling to rule 5 are exactly the `pending-ruling:811-Q5` set (38) and the paths falling to rule 8 are exactly the `pending-ruling:811-Q3` set (78). Three more scratch mutations, each restored from a copy afterwards:

- Testing the test kind before the operator kind in `_expected_graph_class`: `pytest -k graph_classes_follow` gave `8 failed, 2 passed`.
- Testing the operator kind before production: `pytest -k graph_classes_follow` gave `8 failed, 2 passed`.
- Reclassing `ir_eval/qrels.json` from `pending-ruling:811-Q5` to `dead` in the TOML: `pytest -k "811_decisions or ratchet"` gave `1 failed, 4 passed` (the decision test fails; the ratchet alone still passes, because a non-Python path has no graph check).

## Second Review Fixes at 16e17270

Commit `16e17270` changes only `tests/test_reachability.py`. The checker and the classification entries do not change, so the counts, the red run and the green run above still hold.

- The graph test gains two `base-tested` cases on the base fixture, where `tests/test_example.py` also imports `scripts.migrate`. Migration and test roots reach the loader, and no production or operator root does. Classed `test-only`, it gives one mismatch with expected `operator`; classed `operator`, it gives none.
- The duplicate-entry case is now `[paths[0], paths[1], dict(paths[0]), paths[2]]`: a duplicate that also breaks the sort order. It must raise `more than one`.

These tails ran on `16e17270`:

`python -m pytest -q tests/test_reachability.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.25s
```

`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 python -m pytest -q -p tests.dbname_audit tests/test_reachability.py tests/test_owner_target_guard.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
134 passed in 12.60s
```

`python -S scripts/check_reachability.py` exits 0. Black leaves the test file unchanged, flake8 is clean, and mypy reports no error in the test file.

Two scratch mutations to `scripts/check_reachability.py`, each run on the tree of `16e17270` and reverted with `git checkout -- scripts/check_reachability.py`:

- Testing the test kind before the migration kind in `_expected_graph_class` (operator, then test, then migration): `pytest tests/test_reachability.py` gave `2 failed, 52 passed`, both `base-tested` cases.
- Running the sorted check before the duplicate check: `pytest tests/test_reachability.py` gave `1 failed, 53 passed` (`test_classification_requires_one_entry_per_scoped_path`).
