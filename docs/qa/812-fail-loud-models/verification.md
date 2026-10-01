# 812-S2 Verification: The Reranker and the Embedder Fail Loudly

Work order 812-S2 for issue #812 (812-Q1: fail the turn; 812-Q8: every error
propagates through every layer). Base commit: `41783c1d`. No migration, no
paid call, no gateway lane; every PostgreSQL test ran on disposable clones
(`dbname audit: owner targets: none`).

## Item 14: Remaining `except Exception` Handlers

Command, run at `6e415bdd` (the final product commit):

```
git grep -n "except Exception" -- nexus/agents/memnon/utils/cross_encoder.py \
  nexus/agents/memnon/utils/embedding_manager.py nexus/agents/memnon/utils/search.py \
  nexus/agents/memnon/memnon.py nexus/agents/memnon/utils/db_access.py \
  nexus/agents/memnon/utils/continuous_temporal_search.py \
  nexus/agents/lore/utils/turn_cycle.py nexus/agents/lore/lore.py nexus/memory/incremental.py
```

46 hits. None sits on the path from `query_memory`, `rerank_results` or
`generate_embedding` to a turn and swallows the error. (The 47th hit,
`_get_chunk_by_id` at `memnon.py:1553`, was deleted at `6e415bdd`; see
Second Review Fixes.)

| Hit | Function | Why it is not a swallow on the turn's retrieval path |
|---|---|---|
| `cross_encoder.py:185` | `CrossEncoderReranker.__init__` | Re-raises a load failure as `RuntimeError` naming the folder and the `hf download` remedy, chained `from exc`. |
| `cross_encoder.py:570` | `Qwen3LMReranker.__init__` | Same chained re-raise for the Qwen3 reranker. |
| `embedding_manager.py:153` | `load_local_model` | Re-raises a load failure as `RuntimeError` with the restore command, chained. |
| `embedding_manager.py:273` | `generate_embedding` | The new encode re-raise: `RuntimeError("Embedding model '<key>' failed to encode: ...")` from the model error. |
| `embedding_manager.py:314` | `generate_embeddings_batch` | The same chained re-raise for a batch. |
| `search.py:556` | `SearchManager.query_text_search` | Called only by `MEMNON._query_text_search`, which has no caller; `query_memory` runs only the `hybrid_search` and `vector_search` strategies. |
| `search.py:742` | `SearchManager.query_structured_data` | No caller under `nexus/`. |
| `memnon.py:431`, `memnon.py:441` | `get_schema_summary` | No caller under `nexus/`; reads table comments, no model. |
| `memnon.py:507`, `memnon.py:528` | `execute_readonly_sql` | No caller under `nexus/`; no model. |
| `memnon.py:967` | `_query_structured_data` | No caller under `nexus/`. |
| `memnon.py:1015` | `process_all_narrative_files` | Import path, reached only from the legacy `step` command handler. |
| `memnon.py:1070`, `memnon.py:1106` | `step` | Legacy command handlers (order: Out of Scope). |
| `memnon.py:1240`, `memnon.py:1297` | `_get_status` | Status report for the legacy `step` command; no retrieval. |
| `memnon.py:1356` | `_test_hybrid_search` | Legacy diagnostic (order: Out of Scope). |
| `memnon.py:1419` | `get_chunk_by_id` | Fetches one chunk by id with SQL, no model. Its turn caller is the warm-analysis handler `turn_cycle.py:376` (Out of Scope); `retrieve_context` turns its `None` into a raised `ValueError`. |
| `memnon.py:1489` | `get_recent_chunks` | Logs and re-raises as `RuntimeError("FATAL: Failed to retrieve recent chunks ...")`. |
| `db_access.py:200` | `check_vector_extension` | Schema setup (`db_schema.py`), not retrieval. |
| `db_access.py:355` | `execute_vector_search` | No caller under `nexus/` (order: Out of Scope). |
| `db_access.py:467`, `493`, `540`, `559`, `566`, `576` | `setup_database_indexes` | Index setup (`db_schema.py`), not retrieval (order: expected survivor). |
| `continuous_temporal_search.py:277` | `get_total_chunks` | Reads `MAX(id)` on the time-aware path, no model data (order: Out of Scope). |
| `continuous_temporal_search.py:432` | `execute_time_aware_search` | No caller under `nexus/` (order: Out of Scope). |
| `turn_cycle.py:376`, `turn_cycle.py:406` | `perform_warm_analysis` | Warm-slice handlers, named 380 and 410 in the order (Out of Scope). |
| `turn_cycle.py:519`, `567`, `584`, `601` | `query_entity_states` | Entity-state handlers, named 523, 571, 588, 605 (Out of Scope). |
| `turn_cycle.py:1537`, `turn_cycle.py:1604` | `call_apex_ai` | Storyteller-call handlers, named 1548 and 1615 (Out of Scope). |
| `turn_cycle.py:1699` | `integrate_response` | Named 1710 (Out of Scope); wraps a log line, no retrieval. |
| `lore.py:183` | `_load_settings` | Re-raises as `RuntimeError("Cannot initialize LORE without valid configuration ...")`, chained. |
| `lore.py:264` | `_initialize_memnon` | Re-raises as `RuntimeError("FATAL: MEMNON initialization failed: ...")`, chained; this carries the new reranker load failure. |
| `lore.py:285` | `_initialize_logon` | Re-raises as `RuntimeError("Failed to initialize LOGON")`, chained. |
| `lore.py:422` | `process_turn` | The turn's own boundary: it records `"<phase>: <error>"` in `turn_context.error_log` and returns an error string; the narrative gateway's `_describe_lore_failure` (`nexus/api/narrative_generation.py:65-85`) turns that into an HTTP 500 and a failed session, so the turn fails. |
| `lore.py:478` | `retrieve_context` | Logs and re-raises (`raise`). |
| `lore.py:877` | `main` | The module's command-line entry point. |
| `incremental.py:190` | `expand_warm_slice` | Warm-slice handler, named 202 in the order (Out of Scope). |

## Red Run Against `main`

The new and rewritten tests, copied into an export of `41783c1d`
(`git archive 41783c1d`) and run there with `PYTHONPATH` at that export:

```
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -p no:cacheprovider -p tests.dbname_audit -rfs --tb=line \
  tests/test_memnon_model_failures_pg.py tests/test_memnon_embedding_cache.py \
  tests/test_memnon_cross_encoder.py tests/test_memnon_cross_encoder_artifact.py
```

```
tests/test_memnon_model_failures_pg.py:145: AssertionError: assert [] == [('/private/v...coder', None)]
tests/test_memnon_model_failures_pg.py:163: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_model_failures_pg.py:187: AttributeError: 'MEMNON' object has no attribute 'reranker'
tests/test_memnon_model_failures_pg.py:201: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_model_failures_pg.py:213: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_model_failures_pg.py:230: Failed: DID NOT RAISE <class 'psycopg2.errors.UndefinedColumn'>
tests/test_memnon_model_failures_pg.py:230: Failed: DID NOT RAISE <class 'psycopg2.errors.UndefinedColumn'>
tests/test_memnon_model_failures_pg.py:320: Failed: DID NOT RAISE <class 'RuntimeError'>   (x5, one per layer)
tests/test_memnon_embedding_cache.py:299: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_embedding_cache.py:314: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_embedding_cache.py:326: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_embedding_cache.py:341: Failed: DID NOT RAISE <class 'ValueError'>
tests/test_memnon_embedding_cache.py:350: Failed: DID NOT RAISE <class 'ValueError'>
tests/test_memnon_cross_encoder.py:309: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_cross_encoder.py:337: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_cross_encoder_artifact.py:309: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_cross_encoder_artifact.py:334: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_cross_encoder_artifact.py:334: Failed: DID NOT RAISE <class 'RuntimeError'>
tests/test_memnon_cross_encoder_artifact.py:351: Failed: DID NOT RAISE <class 'RuntimeError'>
...
dbname audit: owner targets: none
23 failed, 30 passed, 3 warnings in 35.67s
```

The logs of that run show each swallow at work, for example:
`Error generating embedding with model 'Octen-Embedding-4B': The size of tensor
a (42) must match the size of tensor b (32)` followed by `Failed to generate
embeddings for any active model.`; `Error scoring batch: The size of tensor a
(44) must match ...; falling back to per-passage scoring`; and `Error in
multi-model hybrid search: column "missing_column" does not exist`. The one
red test without a "fails today" line in the order is
`test_disabled_reranking_loads_nothing`, which fails on `main` only because
`MEMNON.reranker` is new. `test_blank_raw_input_runs_no_query` passes on
`main` (the swallow hid the blank query there) and pins the new guard.

## Proof Tails (at `6d66762a`)

These tails ran at `6d66762a`, before the review fixes. The same commands at
the final product commit are under Proof Tails (at `6e415bdd`).

PostgreSQL proof, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT`
unset:

```
NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_memnon_model_failures_pg.py tests/test_memnon_embedding_cache.py tests/test_memnon_runtime_config.py tests/test_presence_boost_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_lore/test_window_coverage_pg.py tests/test_lore/test_scene_order_render.py tests/test_lore/test_runtime_config.py tests/test_lore/test_pass2_baseline_pg.py tests/test_lore/test_baseline_fingerprint_refresh_pg.py tests/test_lore/test_logon_lazy_init.py tests/test_lore/test_pass2_chunk1369.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 44 targets: nexus_test_pass2_* x7, postgres, qa640_908_fingerprint_*, qa640_historical_coverage_* x3, qa640_memnon_config_*, qa640_scene_clock_*, qa640_scene_null_clock_*, qa640_scene_parent_*, qa640_settings_stamp_*, qa640_window_coverage_*, qa683_presence_* x2, qa885_transaction_writer_*, qa_lazy_logon_*, qa_model_cache_* x2, qa_model_failures_* x13, qa_pass2_corpus_*, qa_runtime_config_* x5, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
243 passed, 22 warnings in 142.09s (0:02:22)
```

No skips. These files build a real LORE or MEMNON with the production
folders, so they also load the production reranker at construction.

Focused offline proof:

```
$PY -m pytest -q tests/test_memnon_cross_encoder.py tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder_dependencies.py tests/test_api/test_import_side_effects.py tests/test_lore/test_turn_cycle.py tests/test_lore/test_memory_manager.py tests/test_lore/test_lore_retrieve_context.py tests/test_memnon tests/test_doc_front_matter.py

secret-store guard: active; nexus-api: denied; disposable keychain: denied
176 passed, 4 skipped, 8 warnings in 19.78s
```

The four skips: `test_memnon_cross_encoder_dependencies.py:28` (its model path
is relative to the checkout, and a worktree has no `models/` folder) and three
PostgreSQL tests in `tests/test_memnon/test_ann_gate.py`. Because removing the
outer `try` in `execute_multi_model_hybrid_search` re-indents code around
triple-quoted SQL, the SQL literals were kept byte-identical; the ANN gate's
frozen SQL fingerprint passes, and its PostgreSQL tests were run as well:

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p no:cacheprovider -p tests.dbname_audit tests/test_memnon/test_ann_gate.py

dbname audit: owner targets: none
SKIPPED [1] tests/test_memnon/test_ann_gate.py:115: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
15 passed, 1 skipped in 6.69s
```

Offline suites:

```
$PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2633 passed, 432 skipped, 8 warnings in 410.08s (0:06:50)

$PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1816 passed, 742 skipped, 7 warnings in 38.43s

$PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.45s
```

The skips in the offline suites are the PostgreSQL tests, which need
`NEXUS_RUN_POSTGRES=1`.

Static checks on the changed Python files: Black reports all 14 files
unchanged. flake8 reports no new finding against the base files (the count of
pre-existing E501 lines falls in `db_access.py` and `search.py`). mypy
(`--ignore-missing-imports --follow-imports=silent --explicit-package-bases`)
reports no new error in the nine product files against the base and four fewer
(65 to 61): the four `dict[str, list[float] | None]` argument errors that the
`None` embeddings caused. The new PostgreSQL test file is clean.

## Review Fixes (Tails at `cb34f9d0`)

Fixes made after review: `LORE._process_single_directive` drops a query that
sanitizes to nothing, so a directive of `???` sends no `""` to `query_memory`;
`test_sql_layer_propagates_a_query_error` asserts the raised error has no
`__context__`; the artifact tests' fixture (now `isolated_model_caches`)
isolates both caches and covers `test_score_pair_raises_for_an_over_long_pair`.
The `lore.py` fix replaced one line with one line, so it changed no item-14
hit.

The FakeMemnon test below was removed at `6e415bdd` and replaced by
`test_blank_directive_runs_no_query` on a real LORE (see Second Review
Fixes). Its red check, kept as the record of this round: the then-new
`test_retrieve_context_skips_a_directive_that_sanitizes_to_nothing` against
the previous `lore.py` (`6d66762a`):

```
E       AssertionError: assert [''] == []
FAILED tests/test_lore/test_lore_retrieve_context.py::test_retrieve_context_skips_a_directive_that_sanitizes_to_nothing
1 failed, 3 passed, 5 warnings in 0.41s
```

Mutation check: a catch-and-retry wrapper appended to
`continuous_temporal_search.py` (on any error, call
`db_access.execute_multi_model_hybrid_search` with the same arguments), then
reverted:

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit "tests/test_memnon_model_failures_pg.py::test_sql_layer_propagates_a_query_error"

E       assert UndefinedColumn('column "missing_column" does not exist\nLINE 20:                      AND cm.season = missing_column\n ...') is None
dbname audit: owner targets: none
1 failed, 1 passed in 5.57s
```

The `time_aware` parameter fails and the `hybrid` parameter passes.

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_memnon_model_failures_pg.py

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa_model_failures_* x13
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
13 passed, 9 warnings in 26.16s

$PY -m pytest -q tests/test_memnon_cross_encoder.py tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder_dependencies.py tests/test_api/test_import_side_effects.py tests/test_lore/test_turn_cycle.py tests/test_lore/test_memory_manager.py tests/test_lore/test_lore_retrieve_context.py tests/test_memnon tests/test_doc_front_matter.py

secret-store guard: active; nexus-api: denied; disposable keychain: denied
177 passed, 4 skipped, 8 warnings in 19.72s
```

The four skips are the same four named above. Black reports the four changed
Python files unchanged; flake8 reports nothing new; mypy reports no new error
in the changed files.

## Second Review Fixes (at `6e415bdd`)

- `MEMNON._get_chunk_by_id` has no `try`/`except` (812-Q8: every error
  propagates through every layer). It was reachable from a turn: Pass 2 sends
  the stripped player input to `query_memory` unchanged (`incremental.py:136`,
  `145`), and `query_memory` routes a query that starts with `chunk_id:` and an
  integer to `_get_chunk_by_id` (`memnon.py:1596-1599`). The not-found branch
  stays: no row is a data state, not a failure. The item-14 grep falls from 47
  to 46 hits; the open question on this handler is closed.
- New `test_chunk_id_lookup_propagates_a_query_error` (PostgreSQL, on the
  clone): `query_memory("chunk_id:<seeded id>")` returns the seeded chunk and
  an unknown id returns no results; after
  `ALTER TABLE chunk_metadata RENAME COLUMN world_layer TO world_layer_gone`
  on the disposable clone, the same query raises
  `sqlalchemy.exc.ProgrammingError` whose `orig` is
  `psycopg2.errors.UndefinedColumn`.
- The FakeMemnon test `test_retrieve_context_skips_a_directive_that_sanitizes_to_nothing`
  is deleted; `tests/test_lore/test_lore_retrieve_context.py` is back to its
  base content (`git diff 41783c1d -- tests/test_lore/test_lore_retrieve_context.py`
  is empty). New `test_blank_directive_runs_no_query(lore_on_clone)` runs
  `asyncio.run(lore_on_clone.retrieve_context(["???"], chunk_id=None))` on a
  real LORE on the clone and asserts the directive's `search_progress` is
  empty.

Red check: the two new tests, with `nexus/agents/memnon/memnon.py` from
`dfa9fa8f` (the handler present) and `nexus/agents/lore/lore.py` from
`6d66762a` (no blank-query filter) copied over the tree, then restored:

```
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfs -p no:cacheprovider -p tests.dbname_audit --tb=line -p no:logging tests/test_memnon_model_failures_pg.py::test_chunk_id_lookup_propagates_a_query_error tests/test_memnon_model_failures_pg.py::test_blank_directive_runs_no_query

tests/test_memnon_model_failures_pg.py:276: Failed: DID NOT RAISE <class 'sqlalchemy.exc.ProgrammingError'>
nexus/agents/memnon/utils/embedding_manager.py:267: ValueError: Embedding model 'Octen-Embedding-4B' was given empty or non-string text: ''
dbname audit: owner targets: none
FAILED tests/test_memnon_model_failures_pg.py::test_chunk_id_lookup_propagates_a_query_error
FAILED tests/test_memnon_model_failures_pg.py::test_blank_directive_runs_no_query
2 failed, 1 warning in 7.46s
```

Static checks: Black reports the three changed Python files unchanged; flake8
reports nothing on the test file and 66 findings on `memnon.py`, the same 66 as
at `dfa9fa8f`; mypy reports 33 errors in `memnon.py`, the same 33 as at
`dfa9fa8f`, and none in the test file.

## Proof Tails (at `6e415bdd`)

Every tail below ran at `6e415bdd`, the final product commit, with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset.

The order's PostgreSQL proof list:

```
NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_memnon_model_failures_pg.py tests/test_memnon_embedding_cache.py tests/test_memnon_runtime_config.py tests/test_presence_boost_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_lore/test_window_coverage_pg.py tests/test_lore/test_scene_order_render.py tests/test_lore/test_runtime_config.py tests/test_lore/test_pass2_baseline_pg.py tests/test_lore/test_baseline_fingerprint_refresh_pg.py tests/test_lore/test_logon_lazy_init.py tests/test_lore/test_pass2_chunk1369.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 46 targets: nexus_test_pass2_* x7, postgres, qa640_908_fingerprint_*, qa640_historical_coverage_* x3, qa640_memnon_config_*, qa640_scene_clock_*, qa640_scene_null_clock_*, qa640_scene_parent_*, qa640_settings_stamp_*, qa640_window_coverage_*, qa683_presence_* x2, qa885_transaction_writer_*, qa_lazy_logon_*, qa_model_cache_* x2, qa_model_failures_* x15, qa_pass2_corpus_*, qa_runtime_config_* x5, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
245 passed, 23 warnings in 158.98s (0:02:38)
```

No skips (the log has no `SKIPPED` line). 245 = the 243 above plus the two new
tests.

Focused offline proof:

```
$PY -m pytest -q tests/test_memnon_cross_encoder.py tests/test_memnon_cross_encoder_artifact.py tests/test_memnon_cross_encoder_dependencies.py tests/test_api/test_import_side_effects.py tests/test_lore/test_turn_cycle.py tests/test_lore/test_memory_manager.py tests/test_lore/test_lore_retrieve_context.py tests/test_memnon tests/test_doc_front_matter.py

secret-store guard: active; nexus-api: denied; disposable keychain: denied
176 passed, 4 skipped, 8 warnings in 20.33s
```

176 = the 177 at `cb34f9d0` less the deleted FakeMemnon test. The four skips
are the same four named above.

Offline suites and reachability:

```
$PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2633 passed, 434 skipped, 8 warnings in 437.11s (0:07:17)

$PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1816 passed, 742 skipped, 7 warnings in 39.29s

$PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.45s
```

The two more skips than at `6d66762a` are the two new PostgreSQL tests, which
need `NEXUS_RUN_POSTGRES=1` and pass in the PostgreSQL proof above.
