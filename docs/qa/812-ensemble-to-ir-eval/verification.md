# 812-S4b Verification: Move the Ensemble Weighting Into ir_eval

Branch `claude/812-ensemble-to-ir-eval`, cut from `origin/main` at
`c7ae2988d07b443f627a04d3a4eed1816b1cd438` (still the newest `origin/main`
when this file was written; the merge base of every re-stamp). No migration,
no paid call, no gateway lane, no write to any `save_NN`, `NEXUS_template`
or `ref_codex_bakeoff_2026_07`. Every PostgreSQL run used
`-p tests.dbname_audit` with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` unset, under `nice -n 15`, with the one-minute load below 24.

## Cited Lines (Checked at c7ae2988)

| Claim | Location at c7ae2988 |
| --- | --- |
| `EmbeddingModelConfig.weight` is required | `nexus/config/settings_models.py:3255` |
| `weight = 1.0` on the one runtime entry | `nexus.toml:955` (entry `:950-955`) |
| Single-embedder validator | `nexus/config/settings_models.py:4568-4590` |
| MEMNON builds `model_weights` | `nexus/agents/memnon/memnon.py:244-248`, `:267` |
| Duplicated ensemble paths in MEMNON | `memnon.py:446-604` (`perform_hybrid_search`), `:606-681` (`_query_vector_search`) |
| Debug command and status weight | `memnon.py:1213`, `:1174-1178` |
| SearchManager gathers by `model_weights` | `nexus/agents/memnon/utils/search.py:148-175`, `:282-305` (reads at `:155`, `:289`) |
| Scorer skips a zero-weight model | `nexus/agents/memnon/utils/db_access.py:816` |
| ir_eval round-trips its weights through config | `ir_eval/engine/run_executor.py:129-130`, `:152-157`, `:171` |
| ir_eval calls the runtime search | `run_executor.py:368-380` |
| Executor omits `db_url` (PR #916 omission) | `run_executor.py:202` (`QueryAnalyzer(settings=memnon_settings)`); `39b06734` changed `query_analysis.py` and `search.py` only |
| Presence-boost script reads `weight` | `scripts/measure_presence_boost.py:287-290`, `:298` |
| Unloadable candidate | `nexus.toml:1292-1297`; `/Users/pythagor/nexus/models/bge_small_finetuned_20250320_153654` does not exist (`ls`: No such file or directory) |
| Clone path dumps two schemas | `nexus/maintenance/new_story_setup.py:576-585` (`-n public -n assets`); fresh initialization `:288-299` adds `-n ir_eval` |

## Fleet ir_eval Counts (Read-Only, 2026-10-26)

Each query ran with `PGOPTIONS='-c default_transaction_read_only=on'`:

```sql
SELECT count(*) FROM information_schema.tables WHERE table_schema = 'ir_eval';
SELECT string_agg(version::text, ',' ORDER BY version)
FROM schema_migrations WHERE version::text IN ('015', '016', '017');
```

| Database | `ir_eval` tables | Stamps |
| --- | --- | --- |
| NEXUS_template | 7 | 015,016,017 |
| save_01 | 7 | 015,016,017 |
| save_02 | 0 | 015,016,017 |
| save_03 | 0 | 015,016,017 |
| save_04 | 0 | 015,016,017 |
| save_05 | 0 | 015,016,017 |

## Red on Unchanged c7ae2988 (the Executor Was Broken)

The three parity tests on `c7ae2988` with no product change:

```
>       query_analyzer = QueryAnalyzer(settings=memnon_settings)
E       TypeError: QueryAnalyzer.__init__() missing 1 required positional argument: 'db_url'

ir_eval/engine/run_executor.py:202: TypeError
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 4 targets: postgres, qa640_812s4b_* x3
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_ir_eval_v2/test_ensemble_parity_pg.py::test_ir_eval_run_scores_by_its_own_weights
FAILED tests/test_ir_eval_v2/test_ensemble_parity_pg.py::test_ir_eval_production_run_matches_the_runtime_path
2 failed, 1 passed in 11.58s
```

## Before (c7ae2988 Plus the One-Line Executor Repair)

Parity file alone:

```
...                                                                      [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 4 targets: postgres, qa640_812s4b_* x3
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
3 passed in 11.81s
```

Whole proof set (the order's command):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
...
dbname audit: owner targets: none
238 passed, 2 skipped, 23 warnings in 262.70s (0:04:22)
```

## Red

`test_runtime_embedder_rejects_weight` on the unchanged settings model:

```
>       with pytest.raises(ValidationError) as raised:
E       Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>

tests/test_memnon_embedding_contract.py:212: Failed
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_memnon_embedding_contract.py::test_runtime_embedder_rejects_weight
1 failed, 5 warnings in 0.51s
```

Red plant (scratch, reverted): `_ensemble_search` passed
`{name: 1.0 / len(model_weights) for name in model_weights}` to both scorers.

```
E       assert [2, 1, 3, 4] == [4, 3, 2, 1]
E         At index 0 diff: 2 != 4
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_ir_eval_v2/test_ensemble_parity_pg.py::test_ir_eval_run_scores_by_its_own_weights
1 failed, 3 passed in 23.73s
```

The clone's chunk ids are 1-4, so `[2, 1, 3, 4]` is the equal-weight order
c2, c1, c3, c4 the order predicts.

## After

Whole proof set at the final head:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
...
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
240 passed, 2 skipped, 23 warnings in 308.40s (0:05:08)
```

The two added tests account for 238 to 240. Afterward
`psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_812s4b%'"`
returned no rows.

## Static Checks

Run on every changed Python file and on its `origin/main` version (exported
with `git archive origin/main` into a scratch tree), compared without line
numbers.

- Black: `13 files would be left unchanged`.
- flake8: 118 diagnostics on `origin/main`, 111 after; the seven removed are
  `E501` lines inside the deleted MEMNON methods. None added.
- mypy (`--explicit-package-bases`): 52 errors on `origin/main`, 48 after.
  Removed: `run_executor.py` `Missing positional argument "db_url" in call to
  "QueryAnalyzer"` (the repaired TypeError) and its `query_vector_search`
  `filters=None` arg-type error; `memnon.py`'s two implicit-Optional defaults
  of the deleted `perform_hybrid_search` and their two notes. None added.
- `python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  `OK: exception disposition coverage and shrink-only baseline verified.`
  The baseline does not change.

## Offline Suites

`nice -n 15 $PY -m pytest -q -rs tests --ignore=tests/test_api --ignore=tests/test_orrery`
(before the model-path count update):

```
FAILED tests/test_config/test_ir_eval_golden_overrides.py::test_golden_query_overrides_merge_without_field_errors
FAILED tests/test_runtime_home.py::test_shipped_model_paths_are_unchanged_by_anchoring
2 failed, 3195 passed, 682 skipped, 8 warnings in 655.80s (0:10:55)
```

Both pass on an `origin/main` export (`2 passed, 7 warnings in 4.07s`), so
this branch causes both.

- `test_shipped_model_paths_are_unchanged_by_anchoring` pins the number of
  configured model paths; deleting `bge-small-custom` makes it 13. Updated
  14 to 13; `tests/test_runtime_home.py` then passes (`53 passed`).
- `test_golden_query_overrides_merge_without_field_errors` failed because the
  ir_eval V1 `ir_eval/golden_queries.json` `settings.models` block carried a
  `weight` on its four ensemble-era embedders, and the merged V1 settings
  then failed with `extra_forbidden` at `memnon.models.<name>.weight`:

  ```
  E           AssertionError: assert [(('memnon', ...a_forbidden')] == []
  E             Left contains 4 more items, first extra item: (('memnon', 'models', 'bge-large', 'weight'), 'extra_forbidden')
  tests/test_config/test_ir_eval_golden_overrides.py:105: AssertionError
  ```

  Fixed in `d16b1f21` (review round 2): the four `weight` keys are deleted
  from that block (data only; the V1 readers take `weight` through `.get()`
  defaults at `ir_eval/ir_eval.py:1890` and `:1940`). The test is unchanged.
  This is a recorded exception to the 812-Q12 out-of-scope line for
  `ir_eval/golden_queries*.json`; `ir_eval/golden_queries_backup.json` is
  not read by the test and is not edited.

`nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery`:

```
1910 passed, 1532 skipped, 7 warnings in 48.93s
```

## Review Round 2 (Head `92a932d8`, After Merging `origin/main` at `9a0714d7`)

- `d16b1f21`: the golden-overrides fix above, and
  `test_committed_runtime_holds_one_embedder` now pins the production
  entry's keys on the committed `[memnon.models."Octen-Embedding-4B"]` table
  (`_raw()`), keeping the `model_dump()` schema assertion beside it.
- `92a932d8`: merge of `origin/main` at `9a0714d7`; the six `verified_commit`
  conflicts (`AGENTS.md`, `docs/turn_flow_sequence.md`, decisions 0009,
  0010, 0024, 0034) resolve to the new merge base `9a0714d7`. None of those
  documents describes the ensemble weight. #1162 had not landed, so no
  0056-0083 record needed a re-stamp.

Tails (the commit each ran on is named after the block):

```
$ nice -n 15 $PY -m pytest -q tests/test_config/test_ir_eval_golden_overrides.py tests/test_ir_eval_v2/test_candidate_registry.py
12 passed, 5 warnings in 5.28s

$ nice -n 15 $PY -m pytest -q tests/test_doc_front_matter.py tests/test_config/test_ir_eval_golden_overrides.py tests/test_ir_eval_v2/test_candidate_registry.py tests/test_memnon_embedding_contract.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
87 passed, 5 warnings in 19.35s

$ nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3244 passed, 701 skipped, 8 warnings in 670.89s (0:11:10)

$ nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1547 skipped, 7 warnings in 49.67s

$ $PY scripts/validate_config_commit.py    # exit 0, no output
```

The first command ran on `d16b1f21` before the merge; the rest on
`92a932d8`. Black and flake8 on `tests/test_ir_eval_v2/test_candidate_registry.py`:
`1 file left unchanged`, no flake8 output.
