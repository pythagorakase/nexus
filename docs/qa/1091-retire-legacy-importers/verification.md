# Verification: Retire the Legacy Chunk Importers and MEMNON File Ingest (1091-S1, 1119-S2)

Issues #1091 and #1119. Branch `claude/1091-retire-legacy-importers`, cut from
`origin/main` at `c7ae2988`. `origin/main` did not move between the two
commits (`git merge origin/main` reported `Already up to date.`), so the merge
base, and the stamp of item 13, is `c7ae2988d07b443f627a04d3a4eed1816b1cd438`.
No migration, no paid call, no gateway lane, no write to any `save_NN`,
`NEXUS_template` or `ref_codex_bakeoff_2026_07`.

## Cited Lines (at `c7ae2988`)

- `nexus/agents/memnon/utils/content_processor.py:338-341` INSERTs
  `chunk_metadata (chunk_id, season, episode, scene, perspective, location,
  time_code, world_layer, keywords, characters)`; `:295-302` UPDATEs
  `perspective`, `location`, `time_code`, `keywords`.
- `content_processor.py:326-331` inserts `narrative_chunks (raw_text)`
  directly, a derived column.
- `content_processor.py:211-226`: each chunk's exception is logged and the
  count returned; `:86-98`: each file's exception is logged. Baseline entries
  `ContentProcessor.process_all_narrative_files` and
  `ContentProcessor.process_chunked_file`.
- `content_processor.py:393-397`: `if embedding is None: ... continue`.
- `nexus/agents/memnon/memnon.py:286-295` (construction), `:871-910`
  (`process_all_narrative_files`), `:946-957` (`process_files` branch of
  `step()`; handler at `:955-957`), `:1020-1030` (`process files` branch of
  `_parse_command`), `:1725-1765` (three delegating wrappers).

## Read-Only Column Query

```
$ PGOPTIONS='-c default_transaction_read_only=on' psql -d NEXUS_template -Atc "SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='public' AND table_name='chunk_metadata'"
id,chunk_id,season,episode,scene,world_layer,time_delta,generation_date,slug,world_time,generation_model,scene_weather
```

The same query, read-only, returns the identical list on `save_01`, `save_02`
and `save_05`. `NEXUS_template` is at stamp 151 (`SELECT max(version) FROM
schema_migrations`), and `narrative_chunks` there has `id` of type `bigint`
and no `sequence` column.

## New Guard: Red on Unchanged Code

`PYTHONPATH=$PWD $PY -m pytest -vv tests/test_memnon_db_access.py::test_memnon_file_ingest_is_absent`
before any deletion:

```
E       AssertionError: assert ['nexus/agents/memnon/utils/content_processor.py exists', 'nexus/agents/memnon/memnon.py:871', 'nexus/agents/memnon/memnon.py:1725', 'nexus/agents/memnon/memnon.py:1738', 'nexus/agents/memnon/memnon.py:1752', 'nexus/agents/memnon/memnon.py:288', 'nexus/agents/memnon/memnon.py:290', 'nexus/agents/memnon/memnon.py:290', 'nexus/agents/memnon/memnon.py:1736', 'nexus/agents/memnon/memnon.py:1750', 'nexus/agents/memnon/memnon.py:1763', 'nexus/agents/memnon/memnon.py:888', 'nexus/agents/memnon/memnon.py:1736', 'nexus/agents/memnon/memnon.py:1750', 'nexus/agents/memnon/memnon.py:1763', 'nexus/agents/memnon/memnon.py:888', 'nexus/agents/memnon/memnon.py:953', 'nexus/agents/memnon/utils/content_processor.py:20', 'nexus/agents/memnon/utils/content_processor.py:51', 'nexus/agents/memnon/utils/content_processor.py:105', 'nexus/agents/memnon/utils/content_processor.py:228', 'nexus/agents/memnon/utils/content_processor.py:377', 'nexus/agents/memnon/utils/content_processor.py:87', 'nexus/agents/memnon/utils/content_processor.py:214', 'nexus/agents/memnon/utils/content_processor.py:362', 'nexus/agents/memnon/utils/content_processor.py:320', 'scripts/import_narratives.py:326', 'scripts/import_narratives.py:413', 'scripts/import_narratives.py:702', 'scripts/import_narratives.py:391', 'memnon.py:1020'] == []
FAILED tests/test_memnon_db_access.py::test_memnon_file_ingest_is_absent
======================== 1 failed, 5 warnings in 1.41s =========================
```

The full list has 31 findings, beginning with
`nexus/agents/memnon/utils/content_processor.py exists` and including
`nexus/agents/memnon/memnon.py:288` (the import) and `memnon.py:1020` (the
`process files` string constant).

## 1091-S1 Gate Red Runs

After items 1-4 and the removal of the `ContentProcessor` import from
`tests/test_embedding_table_ownership_pg.py`, before item 5:

```
$ $PY -S scripts/check_exception_dispositions.py
nexus/agents/memnon/memnon.py:1: stale exception disposition baseline entry: nexus/agents/memnon/memnon.py|MEMNON.step|2a54afdd83bae0151b09ce4ac6a54b3b05f9ee467821a136bae01411d166e31a|1
nexus/agents/memnon/utils/content_processor.py:1: stale exception disposition baseline entry: nexus/agents/memnon/utils/content_processor.py|ContentProcessor.process_all_narrative_files|0ee9149abcfeff1eee5a302b06cb72f6271e315d460bc3b45f6d3a10df9cd513|1
nexus/agents/memnon/utils/content_processor.py:1: stale exception disposition baseline entry: nexus/agents/memnon/utils/content_processor.py|ContentProcessor.process_chunked_file|4b235d34507881a202238d6d737e423180c087c4e808d28712f8dac30cb3b034|1
scripts/import_narratives.py:1: stale exception disposition baseline entry: scripts/import_narratives.py|<module>|31f932a3dfc720fe6b4856f6a41530b76d99685313db2d5af54df22968c06457|1
scripts/import_narratives.py:1: stale exception disposition baseline entry: scripts/import_narratives.py|<module>|4a73365399727cd33460405b69a10a20f10fe761360f8391110b23135c745a45|1
scripts/import_narratives.py:1: stale exception disposition baseline entry: scripts/import_narratives.py|<module>|bc16a264337aeff2635fc1fde956a58aa7b4a433e53b52b8772394e36ad69515|1
scripts/import_narratives.py:1: stale exception disposition baseline entry: scripts/import_narratives.py|<module>|f69ea4153a2aa9bd14ae2b196b423c976954a3eaacd5943fc9bd3ee336290a84|1
scripts/import_narratives.py:1: stale exception disposition baseline entry: scripts/import_narratives.py|NarrativeImporter.process_chunked_file|311a4109dd97ee86996d06ef0a9a6ff3cf4ee44b4f0f751e58ccacfa64a4f16f|1
scripts/import_narratives.py:1: stale exception disposition baseline entry: scripts/import_narratives.py|NarrativeImporter.store_narrative_chunk|e629d8420750b684ed03b755d6d06bf3d46af9a4133b768b94d1b91a7d0b1bb2|1
scripts/import_narratives.py:1: stale exception disposition baseline entry: scripts/import_narratives.py|main|55e7ce774b7cf4c7300b8cffd43f923bb38d906f6204c139be19a8c0bcb80a1b|1
exit 1
```

```
$ PYTHONPATH=$PWD $PY scripts/check_reachability.py
{
  "maintained": 404,
  "reachable_by_kind": {
    "production": 224,
    "operator": 263,
    "migration": 200,
    "test": 301
  },
  "test_only": 44,
  "existing_unreachable": 60,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [
    "scripts/import_narratives.py"
  ],
  "baseline_remove_deleted_production_paths": [
    "nexus/agents/memnon/utils/content_processor.py"
  ],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "unclassified_paths": [],
  "classified_paths_not_in_repository": [
    "scripts/import_narratives.py"
  ],
  "class_graph_mismatches": [],
  "classification_counts": {
    "dead": 33,
    "documented": 8,
    "openrouter-shim": 1,
    "operator": 46,
    "pending-ruling:811-Q1": 3,
    "pending-ruling:811-Q3": 78,
    "pending-ruling:811-Q4": 2,
    "pending-ruling:811-Q5": 38,
    "runtime": 3,
    "test-only": 25
  },
  "route_reachability": "not_proven"
}
exit 1
```

## 1091-S1 Reachability Baseline Diff

```diff
diff --git a/config/reachability_baseline.json b/config/reachability_baseline.json
index 6788bc9c..14bae7a8 100644
--- a/config/reachability_baseline.json
+++ b/config/reachability_baseline.json
@@ -1,6 +1,6 @@
 {
   "schema_version": 1,
-  "reason": "Wave B (2026-10-09): 823-S1 slot operation journal and staging; 840-S2 required place points; 803-S1 readiness import and desktop checks; 811-S3a maintenance module moves; 777 shell UI-config route",
+  "reason": "#1091 S1: retire MEMNON file ingest (content_processor.py) and scripts/import_narratives.py",
   "unreachable": [
     "ir_eval/db.py",
     "ir_eval/evaluate_query_classifier.py",
@@ -39,7 +39,6 @@
     "scripts/fix_episode_ranges.py",
     "scripts/freestyle_api_query.py",
     "scripts/generate_octen_embeddings.py",
-    "scripts/import_narratives.py",
     "scripts/import_setting.py",
     "scripts/map_builder_legacy.py",
     "scripts/migrate_chunk_character_references.py",
@@ -89,7 +88,6 @@
     "nexus/agents/memnon/memnon.py",
     "nexus/agents/memnon/utils/alias_search.py",
     "nexus/agents/memnon/utils/artifact_manifest.py",
-    "nexus/agents/memnon/utils/content_processor.py",
     "nexus/agents/memnon/utils/continuous_temporal_search.py",
     "nexus/agents/memnon/utils/cross_encoder.py",
     "nexus/agents/memnon/utils/db_access.py",
```

## 1119-S2 Red Run

After item 8a (six scripts deleted, prompts still present):

```
$ $PY -m pytest -q tests/test_prompt_lint.py tests/test_schema_ownership.py::test_every_allowlist_entry_matches_a_site
E       AssertionError: assert {'AMBIENT_SCE...PRIVACY', ...} == {'AMBIENT_SCE...PRIVACY', ...}
E         
E         Extra items in the right set:
E         'OPERATORS_ESTIMATE_TIME_DELTA_SYSTEM'
E         'OPERATORS_MAP_BUILDER'
E         'OPERATORS_MAP_BUILDER_SCHEMA'
E         'OPERATORS_ESTIMATE_TIME_DELTA_USER'
E         'OPERATORS_MAP_BUILDER_JSON_REMINDER'
E         'OPERATORS_PROCESS_CHARACTERS'
E         Use -v to get more diff
E       FileNotFoundError: [Errno 2] No such file or directory: '/Users/pythagor/nexus/.claude/worktrees/1091-1119/scripts/estimate_time_delta.py'
E       AssertionError: Allowlist entries with no matching site: [('scripts/simple_update.py', 'resequence_all_chunks', 'CREATE TABLE'), ('scripts/simple_update.py', 'resequence_all_chunks', 'DROP TABLE'), ('scripts/update_raw_text.py', 'Ch
E       assert not [('scripts/simple_update.py', 'resequence_all_chunks', 'CREATE TABLE'), ('scripts/simple_update.py', 'resequence_all_chunks', 'DROP TABLE'), ('scripts/update_raw_text.py', 'ChunkUpdater.create_backup_table', 'CREATE TABLE
FAILED tests/test_prompt_lint.py::test_every_prompt_has_a_reader_outside_tests
FAILED tests/test_prompt_lint.py::test_allowlist_is_exact_and_has_no_stale_entries
FAILED tests/test_schema_ownership.py::test_every_allowlist_entry_matches_a_site
3 failed, 20 passed, 5 warnings in 12.49s
```

`check_exception_dispositions.py` then reported 109 stale entries: 21
`scripts/estimate_time_delta.py`, 1 `scripts/extract_season_episode.py`, 40
`scripts/map_builder_legacy.py`, 31 `scripts/process_characters.py`, 7
`scripts/simple_update.py`, 9 `scripts/update_raw_text.py`. All 119 baseline
entries (10 + 109) were deleted by exact key; none was added.

## 1119-S2 Reachability Baseline Diff

```diff
diff --git a/config/reachability_baseline.json b/config/reachability_baseline.json
index 14bae7a8..fc17a5ad 100644
--- a/config/reachability_baseline.json
+++ b/config/reachability_baseline.json
@@ -1,6 +1,6 @@
 {
   "schema_version": 1,
-  "reason": "#1091 S1: retire MEMNON file ingest (content_processor.py) and scripts/import_narratives.py",
+  "reason": "#1119 S2: retire six legacy chunk_metadata writers",
   "unreachable": [
     "ir_eval/db.py",
     "ir_eval/evaluate_query_classifier.py",
@@ -31,20 +31,16 @@
     "scripts/chunk_transcripts.py",
     "scripts/create_vector_index.py",
     "scripts/creative_character_expansion.py",
-    "scripts/estimate_time_delta.py",
     "scripts/extract_scene_numbers.py",
-    "scripts/extract_season_episode.py",
     "scripts/faction_relationship_analyst.py",
     "scripts/fix_chunks.py",
     "scripts/fix_episode_ranges.py",
     "scripts/freestyle_api_query.py",
     "scripts/generate_octen_embeddings.py",
     "scripts/import_setting.py",
-    "scripts/map_builder_legacy.py",
     "scripts/migrate_chunk_character_references.py",
     "scripts/migrate_provider_names.py",
     "scripts/pr_review.py",
-    "scripts/process_characters.py",
     "scripts/process_factions.py",
     "scripts/query_narratives.py",
     "scripts/query_narratives_simple.py",
@@ -52,13 +48,11 @@
     "scripts/remove_storyteller_contamination.py",
     "scripts/run_golden_queries.py",
     "scripts/seed_slot2_routine_anchors.py",
-    "scripts/simple_update.py",
     "scripts/sync_secrets.py",
     "scripts/test_narrative_api.py",
     "scripts/test_setup_flow.py",
     "scripts/token_counter.py",
     "scripts/trim_oversized_contexts.py",
-    "scripts/update_raw_text.py",
     "scripts/update_scene_numbers.py",
     "scripts/validate_embeddings.py",
     "scripts/vector_migration.py"
```

## Green Gates

```
$ PYTHONPATH=$PWD $PY scripts/check_reachability.py; echo $?
(JSON summary with every list empty)
0
$ $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
OK: exception disposition coverage and shrink-only baseline verified.
```

## Grep

```
$ git grep -nE "ContentProcessor|content_processor|store_narrative_chunk|import_narratives|process_all_narrative_files|process_chunked_file|simple_update|update_raw_text|extract_season_episode|estimate_time_delta|map_builder_legacy|process_characters|OPERATORS_(ESTIMATE_TIME_DELTA|MAP_BUILDER|PROCESS_CHARACTERS)" -- ':!docs/qa' ':!docs/decisions' ':!temp'
scripts/METADATA_README.md:33:First, run the `extract_season_episode.py` script to extract season and episode information from narrative chunks. This doesn't require API calls and can be done quickly:
scripts/METADATA_README.md:37:python scripts/extract_season_episode.py --all
scripts/METADATA_README.md:40:python scripts/extract_season_episode.py --missing
scripts/METADATA_README.md:43:python scripts/extract_season_episode.py --range 1 100
scripts/METADATA_README.md:71:### extract_season_episode.py
scripts/map_builder.md:8:This script will analyze one chunk at a time, record relationships to known locations, and help identify new locations. It will use an interactive workflow very similar to that found in `map_builder_legacy.py`, with exceptions as detailed below.
scripts/map_builder.md:125:- This is a rewrite of an existing script (`map_builder_legacy.py`), focus on reliability
tests/test_memnon_db_access.py:34:    "ContentProcessor",
tests/test_memnon_db_access.py:35:    "content_processor",
tests/test_memnon_db_access.py:36:    "process_all_narrative_files",
tests/test_memnon_db_access.py:37:    "process_chunked_file",
tests/test_memnon_db_access.py:38:    "store_narrative_chunk",
tests/test_memnon_db_access.py:47:    if (root / "nexus/agents/memnon/utils/content_processor.py").exists():
tests/test_memnon_db_access.py:48:        found.append("nexus/agents/memnon/utils/content_processor.py exists")
```

The grep was taken before this evidence file existed; `docs/qa` is excluded
from it in any case.

## Offline Suites

```
$ nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3195 passed, 675 skipped, 8 warnings in 624.95s (0:10:24)
$ nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1532 skipped, 7 warnings in 46.36s
```

These two runs include `tests/test_reachability.py`,
`tests/test_doc_front_matter.py`, `tests/config/test_settings_parity.py`,
`tests/test_prompt_lint.py`, `tests/test_memnon_db_access.py` and
`tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline`.

## PostgreSQL Proof Set

Load average before the run: 4.72 (no wait). `NEXUS_GATEWAY_PORT`,
`NEXUS_API_URL` and `NEXUS_SLOT` unset.

```
$ NEXUS_RUN_POSTGRES=1 nice -n 15 $PY -m pytest -q -p tests.dbname_audit tests/test_embedding_table_ownership_pg.py tests/test_schema_ownership.py tests/test_player_identity_consumers_pg.py tests/test_lore/test_query_patterns_pg.py tests/test_memnon_model_failures_pg.py tests/test_lore/test_window_coverage_pg.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: owner targets: none
137 passed, 4 skipped, 19 warnings in 305.52s (0:05:05)
```

The four skips are the `requires_corpus` tests
(`test_configured_k_bounds_the_deep_query_pool[3]`, `[15]` and
`test_card_exposure_rank_joint_and_backstage_parity[False]`, `[True]`), which
run only under `NEXUS_RUN_CORPUS=1`.

## Static Checks

Black: `10 files would be left unchanged.` flake8 and
`mypy --explicit-package-bases` ran on the ten changed Python files on the
branch and on their `origin/main` versions (a `git archive origin/main`
export). Compared by file and message: flake8 149 on the branch against 152 on
main, 0 new (3 removed: E501 lines inside deleted code); mypy 64 errors
against 65, 0 new (1 removed: the implicit-Optional default of the deleted
`process_all_narrative_files`). The remaining diagnostics are pre-existing on
untouched lines.

## Document Freshness

`AGENTS.md` (sources `memnon.py`, `lore.py`, `registry.py`) and
`docs/turn_flow_sequence.md` (sources `memnon.py`, `lore.py`) were re-read
against the changes. Neither names the file ingest, `ContentProcessor`, the
`process files` command or the six operator prompts; their MEMNON and LORE
passages (retrieval through `query_memory`, a fresh LORE closed per turn)
stay accurate. Both `verified_commit` values move from `a01c162f` to
`c7ae2988d07b443f627a04d3a4eed1816b1cd438`. No other canonical document
declares a changed file.
