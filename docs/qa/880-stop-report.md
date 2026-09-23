# Work Order 880 Stop Report

No PR was opened. This is an incomplete implementation, not a review-ready result.

## Stop Condition

The full wizard-to-continuation proof is blocked by the no-hosted-provider rule and the existing local wizard conversation route. A real local model server was started successfully; its health endpoint returned `{"status":"ok"}`. Constructing `ConversationsClient` with the configured local model, without creating a thread or making a hosted call, returned:

```text
Configured local model: nousresearch/hermes-4-70b
Conversation store mode: openai
Conversation API base URL: https://api.openai.com/v1/
```

`nexus/api/conversations.py:70` handles Anthropic file storage, but the local provider falls through to the hosted OpenAI client at lines 80-82. `create_thread()` calls that client's Conversations API at line 96. Fixing local wizard storage is outside this frozen connection work order. No hosted provider call was made. The local model process started for this investigation was terminated.

## Current Snapshot Limitations

The final targeted check has two failures introduced by the last, unvalidated URL-query preservation edit:

```text
{'options': '-c TimeZone=UTC'} != {'options': '-c TimeZone=UTC -c TimeZone=UTC'}
{'connect_timeout': 5} != {'connect_timeout': '5'}
```

These come from `nexus/database.py:64` appending TimeZone and `nexus/database.py:115` copying URL query strings back over typed parameters. They remain unresolved because implementation stopped at the external proof blocker. The clean offline run below predates that final edit and is not evidence that the stopped snapshot passes.

The two-cluster test exercises actual pooled, SQLAlchemy, and asyncpg connections, UTC sessions, and pre-DDL mismatch rejection. It inspects the non-target cluster's catalog, pg_stat_activity, and connection/statement log. It does **not** prove wizard creation, bootstrap, a real continuation, retrieval, or background-job execution. No gateway was started. No UI files, fleet migrations, template writes, or paid inference were used. The test-created clusters were stopped and removed, including the directory left by the initial failed cluster startup.

## Commands and Verbatim Tails

All Python commands ran from this worktree. `$PY` was `/Users/pythagor/nexus/.venv/bin/python`.

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```
```text
/Users/pythagor/nexus/.claude/worktrees/880-connection-contract/nexus/__init__.py
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus_880_offline.log 2>&1
```
```text
FAILED tests/test_api/test_runtime_status.py::test_database_status_uses_api_connection_path
FAILED tests/test_memnon_db_access.py::test_setup_database_indexes_skips_ann_indexes_for_high_dimensions
FAILED tests/test_memnon_db_access.py::test_setup_database_indexes_fails_on_unparseable_embedding_table
FAILED tests/test_reachability.py::test_repository_reachability_ratchet - Ass...
FAILED tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app
5 failed, 2571 passed, 756 skipped, 11 warnings in 88.58s (0:01:28)
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q > /tmp/nexus_880_offline_final.log 2>&1
```
```text
2583 passed, 757 skipped, 11 warnings in 89.89s (0:01:29)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api tests/test_lore tests/test_memnon_db_access.py tests/test_runtime -k 'connection or url or pool or override or status' > /tmp/nexus_880_postgres.log 2>&1
```
```text
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures
1 failed, 45 passed, 614 deselected, 11 warnings in 26.11s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The only selection failure is the coordinator-exempt #885 test. No exemptions were added to the suite.

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_database_contract.py > /tmp/nexus_880_contract.log 2>&1
```

Initial attempt:
```text
ERROR tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard
7 passed, 1 error in 0.88s
```

The cluster log identified a Unix-domain socket path longer than macOS's 103-byte limit. The fixture then used `/tmp` for the socket directory; rerunning the same command produced:
```text
........                                                                 [100%]
8 passed in 1.67s
```

Final stopped-snapshot check:
```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_database_contract.py > /tmp/nexus_880_contract_stop.log 2>&1
```
```text
FAILED tests/test_database_contract.py::test_connection_environment_and_url_escaping
FAILED tests/test_database_contract.py::test_connection_config_and_explicit_override
2 failed, 6 passed in 1.67s
```

```sh
$PY -m compileall -q nexus scripts
git diff --check
```
Both exited 0 with no output after formatting. Changed Python ranges were formatted using Black 25.1.0; new modules were formatted in full. Complete retained test logs are under `temp/qa880_stop/` (local, ignored).

## Files Changed

- `config/reachability_baseline.json` — Register the new production connection module.
- `docs/qa/880-stop-report.md` — Record the stop condition, partial changes, evidence, and incomplete gates.
- `nexus.toml` — Add PostgreSQL identity and TimeZone settings; clear the legacy MEMNON URL.
- `nexus/agents/lore/logon_utility.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/agents/lore/lore.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/agents/memnon/memnon.py` — Route connections through the contract and reject foreign schema targets.
- `nexus/agents/memnon/test_idf_dictionary.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/agents/memnon/utils/continuous_temporal_search.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/agents/memnon/utils/db_access.py` — Route connections through the contract and reject foreign schema targets.
- `nexus/agents/memnon/utils/db_schema.py` — Route connections through the contract and reject foreign schema targets.
- `nexus/agents/memnon/utils/idf_dictionary.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/agents/memnon/utils/temporal_search.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/agents/orrery/retrograde_maturation.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/agents/orrery/tag_library.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/agents/orrery/worker.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/backstage_endpoints.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/db_pool.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/mock_openai.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/narrative.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/new_story_flow.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/orrery_dev_endpoints.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/presence_reconciliation.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/runtime_status.py` — Report credential-free pooled and URL client targets.
- `nexus/api/save_slots.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/slot_utils.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/api/summary_triggers.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `nexus/cli.py` — Report credential-free pooled and URL client targets.
- `nexus/config/settings_models.py` — Validate server fields and IANA session time zones.
- `nexus/database.py` — Add target, URL, asyncpg, subprocess, and session-policy adapters; URL normalization remains incomplete.
- `nexus/memory/correspondence.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/api_anthropic.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/api_openai.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/api_openrouter.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/apply_migration_to_slots.sh` — Delegate PostgreSQL CLI environment resolution to the shared module.
- `scripts/apply_slot2_semantic_tags.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/assemble_context.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/backfill_routine_anchors.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/benchmark_experience_enqueue_fence.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/character_chunk_ranker.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/character_episode_ranker.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/checkpoint_state.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/create_vector_index.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/creative_character_expansion.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/estimate_time_delta.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/extract_scene_numbers.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/extract_season_episode.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/faction_former.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/faction_relationship_analyst.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/fix_chunks.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/fix_episode_ranges.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/freestyle_api_query.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/generate_character_summaries_experimental.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/generate_psychology copy.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/generate_psychology.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/gis_backfill.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/gis_hygiene.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/import_narratives.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/import_orrery_route_graph.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/import_setting.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/map_builder.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/map_builder_fail.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/map_builder_legacy.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/map_illustrator.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/measure_presence_boost.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/memnon_config.json` — Remove the legacy hardcoded database URL.
- `scripts/migrate.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/migrate_chunk_character_references.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/migrate_provider_names.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/new_story_setup.py` — Route Python and PostgreSQL CLI connections through the contract.
- `scripts/orrery_sample.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/process_characters.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/process_factions.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/propagate_schema.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/qa_shift/prose_metrics.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/query_narratives_simple.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/query_narratives_vector.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/regenerate_embeddings.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/register_drift_study.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/relationship_analyst.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/replay_state.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/report_retrieval_coverage.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/retrieval_query_bakeoff.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/run_golden_queries.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/seed_slot2_routine_anchors.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/simple_update.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/stamp_lore_pass_baseline.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/summarize_narrative.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/test_narrative_simple.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/test_narrative_turn.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/trim_oversized_contexts.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/update_raw_text.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/update_scene_numbers.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/validate_embeddings.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `scripts/vector_migration.py` — Replace independent connection/URL construction or credential-bearing diagnostics with the shared contract.
- `tests/test_api/test_runtime_status.py` — Update existing expectations for the shared contract and status payload.
- `tests/test_database_contract.py` — Add precedence, escaping, guard, timezone, and two-disposable-cluster tests.
- `tests/test_memnon_db_access.py` — Update existing expectations for the shared contract and status payload.

## Questions for the Coordinator

1. Should a separate order repair local-provider wizard conversation storage, or may this proof use the repository's deterministic TEST provider at the model boundary while keeping every database path real?
2. After that decision, resume the two URL-normalization fixes, re-run the full gates on one frozen snapshot, complete the gameplay/CLI proof, and review the broad script migration before authorizing PR publication.

Codex — GPT-6 Astra.
