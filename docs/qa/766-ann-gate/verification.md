# ANN Gate Verification

## Outcome

The coordinator's second-issue amendments resolve both first-issue blockers.
The alias query now selects columns present in the live schema. Exact search
remains the default (`ann.enabled = false`); no save/template index, migration,
paid call, embedding inference, or gateway service was used. All manually
created databases use the `qa640_766_*` prefix and are dropped by the operator
or test fixture.

## Alias Schema Repair

The first issue reproduced this pre-existing error against the unchanged
`2b9266b5` baseline in a read-only `save_01` connection (retained in
`baseline-alias-error.txt`):

```text
UndefinedColumn: column m.characters does not exist
LINE 17:                m.characters, m.place, m.atmosphere, m.time_d...
                        ^
```

Read-only live schema inspection also confirms `place` and `atmosphere` are
absent from `chunk_metadata`. Both generated query branches now omit these
three obsolete projections while retaining `time_delta` and the other current
metadata. Existing optional response fields remain `None`; this change does
not invent denormalized character/place metadata or alter ranking.

The disabled-SQL rule now means byte-identical to this repaired baseline.
An AST extraction of `create_hybrid_alias_search_sql` from
`git show 2b9266b5:nexus/agents/memnon/utils/alias_search.py` compared both
branches (`[]` and `['asset']`) with the current disabled builder after replacing
only `m.characters, m.place, m.atmosphere, m.time_delta` with `m.time_delta`.
SQL strings and parameter dictionaries matched exactly:

```text
Both disabled alias branches are byte-identical to the repaired 2b9266b5 baseline; parameters unchanged.
```

## Runtime Proof

`tests/test_memnon/test_ann_gate.py` restores a read-only-source `save_01` dump
into a disposable clone. It uses the first stored vector and a real lexeme
(`asset`) from that chunk's text, so both alias branches must return candidates
and rank that chunk first. It compares exact and controlled-HNSW top-1 for
vector search, multi-model hybrid search, Retrograde summaries, and both alias
branches. The cursor records and executes real SQL and EXPLAIN plans; no rows
or database responses are mocked.

With ANN enabled, each nearest-neighbor query is index-eligible: session-local
`enable_seqscan = off`, `enable_sort = off`, and `jit = off` controls allow
EXPLAIN to demonstrate the candidate HNSW index. The test also executes the
query under those controls before comparing results. Disabled nearest-neighbor
queries retain full-precision SQL and sequential scans even with the candidate
index present. Runtime statements contain no index creation or sequential-scan
override; `hnsw.ef_search` is configured only for the enabled path.

The other production `<=>` site, Orrery experience scoring, evaluates supplied
experience IDs rather than retrieving nearest neighbors. Its real clone test
verifies the configured cast and a self-similarity score of 1 in both modes.
An ID-bound primary-key B-tree scan is valid for that path; no HNSW eligibility
claim is made for it.

### Planner Behavior at This Scale

Natural planning chooses a sequential scan at 1,425 rows. Controlled ANN timings
measure index eligibility and candidate performance, not natural runtime index
selection. Production leaves planner settings untouched. Natural index adoption
is deferred to a larger measured scale where the latency and recall gate passes;
the precise natural planner crossover has not been established by this run.
The operator preserves both natural and controlled plans in its evidence JSON.

The issue's verifier specifies keys, not numeric defaults. Starting thresholds
are 10,000 documents, exact p95 over 50 ms, mean recall@10 at least 0.98, and
ANN p95 below exact p95. `ef_search = 100` and 100 deterministic stored-vector
probes define the benchmark. Rationales live beside the settings in `nexus.toml`;
`ANNConfig` validates them. Row count alone can never produce `PROMOTE`.

## Measured Scale

Command (after the test suites completed):

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/ann_gate.py --slot 1 > /tmp/766-second-operator.log 2>&1
```

Verbatim printed table and output:

```text
| Rows | Probes | Exact p95 ms | ANN p95 ms | Recall@10 | Build ms | Index bytes | Verdict |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 1425 | 100 | 5.481 | 2.061 | 1.0000 | 2481.066 | 11681792 | KEEP_EXACT |
Evidence: /Users/pythagor/nexus/.claude/worktrees/766-ann-gate/docs/qa/766-ann-gate/save_01.json
```

Evidence: `save_01.json` contains all per-query exact/ANN top-10 sets, latencies,
recall, sample checksum, machine/software versions, natural and controlled
plans, build time, index size, source slot, and clone cleanup confirmation.
Both scale and exact-latency thresholds fail, so the verdict remains
`KEEP_EXACT`. These measurements refresh the first issue's evidence.


## Verification Commands and Tails

All commands run from this worktree. Interpreter provenance was checked before
using any test result:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/766-ann-gate/nexus/__init__.py
```

### Offline Suite

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > /tmp/766-second-offline.log 2>&1
```

```text
2812 passed, 937 skipped, 9 warnings in 133.35s (0:02:13)
```

### Required PostgreSQL Selection

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon tests/test_api -k 'ann or vector or embedding or search' > /tmp/766-second-postgres.log 2>&1
```

```text
21 passed, 438 deselected, 9 warnings in 29.38s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Black

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/config/settings_models.py nexus/agents/memnon/utils/embedding_tables.py nexus/agents/memnon/utils/db_access.py nexus/agents/memnon/utils/alias_search.py nexus/agents/orrery/knowledge_surfacing.py scripts/qa_shift/ann_gate.py tests/test_memnon/test_ann_gate.py > /tmp/766-second-black.log 2>&1
```

```text
All done! ✨ 🍰 ✨
7 files would be left unchanged.
```

### Reachability and Prompt Lint

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py tests/test_prompt_lint.py > /tmp/766-second-static.log 2>&1
```

```text
60 passed, 5 warnings in 20.84s
```

### Static Reachability Report

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/check_reachability.py --report /tmp/766-second-reachability.json > /tmp/766-second-reachability.log 2>&1
```

```text
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

The offline skips are opt-in integration/live-provider tests. The required
PostgreSQL selection actually ran all 21 selected tests, including both ANN
clone tests, with no skips or failures. No #885 exemption was needed.

The production reachability closure contains all runtime cosine sites:
`alias_search.py`, `db_access.py`, and `orrery/knowledge_surfacing.py`.

### Configuration Validation

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py > /tmp/766-second-config.log 2>&1
```

Exit 0; no stdout or stderr.

### Development Checks

The first focused run passed after the alias repair:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon/test_ann_gate.py > /tmp/766-second-ann-tests.log 2>&1
```

```text
10 passed, 5 warnings in 23.07s
```

Formatting:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black nexus/agents/memnon/utils/alias_search.py tests/test_memnon/test_ann_gate.py
```

```text
All done! ✨ 🍰 ✨
2 files left unchanged.
```

Adding experience-scoring coverage revealed an over-broad test assertion: the
ID-bound scorer legitimately used its primary-key B-tree, rather than a sequential
scan. This development run failed before that assertion was scoped to actual
nearest-neighbor queries:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon/test_ann_gate.py > /tmp/766-second-ann-tests-final.log 2>&1
```

```text
FAILED tests/test_memnon/test_ann_gate.py::test_ann_runtime_searches_and_plans
1 failed, 9 passed, 5 warnings in 22.56s
```

The final required PostgreSQL selection above includes and passes the corrected
test, as well as the operator test. No product fallback or planner change was
introduced to accommodate this assertion.

### Commit Hooks

Commit `4c579e94` ran both hooks without bypass:

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
```


## Read-Only Source and Cleanup Evidence

SQL executed against `save_01` with `SET default_transaction_read_only=on`:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'chunk_metadata'
  AND column_name IN ('characters', 'place', 'atmosphere');
-- (0 rows)
SELECT count(*) AS rows FROM chunk_embeddings_2560d;
-- 1425
SELECT indexname FROM pg_indexes
WHERE tablename = 'chunk_embeddings_2560d' AND indexdef ILIKE '%hnsw%';
-- (0 rows)
```

After the operator and tests completed:

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'qa640_766_%';
```

```text
 datname
---------
(0 rows)
```


## Deferred Work and Coordinator Questions

No unresolved coordinator questions. Promotion, fleet/template DDL, and a larger
corpus experiment remain deferred: today's gate keeps exact search. No paid
provider or embedding inference was used. No gateway was started, so no lane
cleanup was needed. The PR is for review only; do not merge from this session.

Authored by Codex (GPT-6 Astra).
