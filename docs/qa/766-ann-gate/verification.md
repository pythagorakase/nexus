# ANN Gate Stop Report

## Status

STOP: work order 766's unchanged-disabled-SQL requirement conflicts with its
real alias-search proof on the current save schema. Partial implementation is
committed for coordinator review; it is not qualified for promotion or a PR.
No save/template index, migration, paid call, embedding inference, or gateway
service was used. All manually created databases were `qa640_766_*` clones and
were dropped. Runtime defaults remain `ann.enabled = false`.

## Blocking Evidence

The PostgreSQL runtime test reached the existing alias query and failed with:

```text
UndefinedColumn: column m.characters does not exist
LINE 17:                m.characters, m.place, m.atmosphere, m.time_d...
                        ^
```

The original builder from `2b9266b57e420b939112891d3a9201cca58086b8` was extracted with Python AST from
`git show HEAD:nexus/agents/memnon/utils/alias_search.py` and its SQL was
submitted to `EXPLAIN` against `save_01` with
`options='-c default_transaction_read_only=on'`. It produced the same error.
See `baseline-alias-error.txt`. The query is at
`nexus/agents/memnon/utils/alias_search.py:172` and in the no-alias branch at
line 210. The test subsequently reports `InFailedSqlTransaction` because the
old disabled path catches the first error and leaves the transaction aborted.
This is not one of issue 885's slot-5 exemptions.

Repairing the retired-column references would change the disabled SQL, which
the frozen order explicitly requires to remain byte-identical. Adding fake
columns to a test clone would not prove compatibility with the production schema.

## Measured Scale

Command (worktree root):

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/ann_gate.py --slot 1 > /tmp/766-ann-operator.log 2>&1
```

Verbatim printed table:

| Rows | Probes | Exact p95 ms | ANN p95 ms | Recall@10 | Build ms | Index bytes | Verdict |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 1425 | 100 | 5.603 | 2.072 | 1.0000 | 2386.835 | 11681792 | KEEP_EXACT |

Evidence JSON: `save_01.json`. It includes every query's exact/ANN top-10,
latencies and recall, deterministic sample checksum, software/machine versions,
index size/build time, source slot, and clone cleanup confirmation.

The issue's verifier names settings but supplies no numeric defaults. The
implemented starting gates are 10,000 documents, exact p95 over 50 ms, mean
recall@10 at least 0.98, and ANN p95 below exact p95. `ef_search = 100` and
100 stored-vector probes supply the benchmark parameters. These values and
rationales are declared in `nexus.toml`, validated by `ANNConfig`.
The current scale fails both the document and exact-latency thresholds.

### Planner Limitation

Initial runs rejected their evidence because PostgreSQL chose a sequential
scan, then a model B-tree scan plus sort when sequential scans were discouraged.
The successful candidate measurement explicitly disables sequential scans and
sorts and disables JIT within the measurement transaction. Both the natural
ANN-expression plan and the controlled HNSW plan are retained in JSON. The
natural plan still chooses a sequential scan at this scale. Runtime only sets
`hnsw.ef_search`; it retains normal cost-based planning. Thus the measured ANN
p95 is a controlled index comparison, not proof of a natural runtime index scan.

The runtime test captures real PostgreSQL statements/plans using a cursor
subclass, with no fabricated rows. Its enabled plan checks also use explicit
planner controls to prove index eligibility. Those enabled checks were not
reached because the disabled alias query failed first. This distinction must
be resolved by the coordinator before accepting the requested runtime proof.

The expression-index and ascending distance-order requirements follow the
[pgvector documentation](https://github.com/pgvector/pgvector#half-precision-indexing).

## Verification Commands and Tails

The interpreter provenance check printed this worktree's `nexus/__init__.py`:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/766-ann-gate/nexus/__init__.py
```

The offline suite was started before the new test module was written, so this
is a passing existing-suite run, not a completed final-snapshot offline gate:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > /tmp/766-offline.log 2>&1
```

```text
2804 passed, 935 skipped, 9 warnings in 127.16s (0:02:07)
```

The focused real-PostgreSQL test ran; its operator check passed and its runtime
check hit the baseline blocker:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon/test_ann_gate.py > /tmp/766-ann-tests.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_memnon/test_ann_gate.py::test_ann_runtime_searches_and_plans
1 failed, 9 passed, 5 warnings in 21.51s
```

Black formatting and its final check:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black nexus/config/settings_models.py nexus/agents/memnon/utils/embedding_tables.py nexus/agents/memnon/utils/db_access.py nexus/agents/memnon/utils/alias_search.py nexus/agents/orrery/knowledge_surfacing.py scripts/qa_shift/ann_gate.py
```

```text
All done! ✨ 🍰 ✨
4 files reformatted, 2 files left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black tests/test_memnon/test_ann_gate.py scripts/qa_shift/ann_gate.py
```

```text
All done! ✨ 🍰 ✨
2 files reformatted.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/config/settings_models.py nexus/agents/memnon/utils/embedding_tables.py nexus/agents/memnon/utils/db_access.py nexus/agents/memnon/utils/alias_search.py nexus/agents/orrery/knowledge_surfacing.py scripts/qa_shift/ann_gate.py tests/test_memnon/test_ann_gate.py > /tmp/766-black.log 2>&1
```

```text
All done! ✨ 🍰 ✨
7 files would be left unchanged.
```

Static reachability command:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/check_reachability.py --report /tmp/766-reachability.json
```

```text
  "newly_unreachable": [],
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

Its production closure contains all three modules with runtime `<=>` sites:
`alias_search.py`, `db_access.py`, and `orrery/knowledge_surfacing.py`.
The latter scores a supplied list of experience IDs rather than searching
nearest neighbors; its enabled halfvec cast is implemented but unverified.

Cleanup query:

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'qa640_766_%';
```

```text
 datname
---------
(0 rows)
```

## Deferred Proof and Coordinator Questions

- Authorize a separate alias-schema repair, or explicitly allow the disabled
  SQL to change within this order? The required alias top-1 proof cannot pass
  against the real schema while preserving the current query.
- Accept planner-controlled index-eligibility proof at this scale, or require
  runtime planner policy changes to guarantee HNSW use when enabled?
- After resolving those decisions, complete the remaining enabled search-site
  checks, experience-scoring coverage, final-snapshot offline run, the specified
  PostgreSQL `tests/test_memnon tests/test_api -k 'ann or vector or embedding or search'`
  gate, standalone reachability/prompt-lint tests, and config validation.
- No push, PR, review wait, or merge was performed because proof gates did not pass.
