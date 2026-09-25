# ANN Gate Verification

## Outcome

The third-issue ruling removes the runtime ANN switch entirely. Production
vector, hybrid, alias, Retrograde, and Orrery experience searches use the
repaired exact-search baseline. The five remaining ANN settings configure
only the measurement operator. No save/template index, migration, paid call,
embedding inference, or gateway service is part of this change.

## Alias Schema Repair and Error Propagation

The first issue reproduced this pre-existing error against the unchanged
`2b9266b5` baseline using a read-only `save_01` connection; the original output
is retained in `baseline-alias-error.txt`:

```text
UndefinedColumn: column m.characters does not exist
LINE 17:                m.characters, m.place, m.atmosphere, m.time_d...
                        ^
```

Both alias SQL branches omit the retired `characters`, `place`, and `atmosphere`
metadata projections and retain `time_delta`. No ranking or SQL changes beyond
that approved repair remain. The broad catches around both main hybrid and
direct-text execution are removed: database errors now propagate.

The real PostgreSQL alias test samples a stored vector and a lexeme from its
chunk, executes both alias branches, and requires candidates with that chunk
ranked first. It then transactionally renames `chunk_metadata.time_delta` on
the clone and asserts `ProgrammingError: column m.time_delta does not exist`.
A separate transactional rename of `narrative_chunks.raw_text` verifies the
direct-text branch also raises. Both deliberate faults are rolled back.

## Exact Runtime Baseline

`git diff 2b9266b5 -- nexus/agents/memnon/utils/db_access.py
nexus/agents/orrery/knowledge_surfacing.py` is empty. The alias diff against
that baseline contains only the approved metadata repair and catch removal.
`tests/test_memnon/fixtures/ann_repaired_sql.json` freezes SQL AST fingerprints
from `2b9266b5` with just the approved alias projection replacement. The tests
compare literal SQL whitespace and interpolations across all three production
search files, independently of Python control-flow indentation. They also
reject candidate-index construction, halfvec casts, and ANN session settings
in those runtime files. No `ann.enabled` or runtime ANN helper remains.

## Natural Planning and the Measurement Gate

The operator dumps `save_01` with `default_transaction_read_only=on`, restores
it into a unique `qa640_766_*` database, and always drops that clone. Query
vectors come from existing stored embeddings. All measurements run in one
process on one machine. Each query gets one warm-up and one timed execution;
p95 uses nearest rank over client execute-and-fetch time. Self-matches count
in top-10 recall. The sample is deterministic MD5 order, with a recorded hash.

Exact ground truth runs before candidate construction, with index and bitmap
scans disabled. Those two settings are restored to session defaults before
candidate measurement. The natural candidate path sets only
`SET LOCAL hnsw.ef_search`; it does not disable sequential scans or sorts.
Every sampled natural EXPLAIN plan must contain the candidate's actual
`Index Name` before the verdict can be `PROMOTE`. A sequential plan returns
`KEEP_EXACT` with reason `planner_prefers_sequential_scan`, even if latency,
recall, and scale thresholds would otherwise permit promotion.

The controlled HNSW pass runs afterward with session-local `enable_seqscan =
off`, `enable_sort = off`, and `jit = off`. Its latency, recall, plans, and
per-query top-10 sets are labeled informational and never enter the verdict.
The real operator test checks natural sequential planning at clone scale,
controlled index eligibility, all four measurements, recall, and KEEP_EXACT
with the planner reason. A separate real clone test builds, inspects, and
drops the candidate through its explicit helper.

The starting thresholds remain 10,000 documents, exact p95 over 50 ms, mean
recall@10 at least 0.98, and natural candidate p95 below exact p95. `ef_search =
100` and 100 probes define the benchmark. Comments in `nexus.toml` explain these
conservative choices; the issue's verifier specified keys, not numbers. Row
count alone cannot promote. `ANNConfig` rejects the removed `enabled` field.

## Measured Scale

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/ann_gate.py --slot 1 > /tmp/766-third-operator.log 2>&1
```

Verbatim output:

```text
| Path | Rows | Probes | p95 ms | Recall@10 | Build ms | Index bytes |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| Exact | 1425 | 100 | 5.606 | 1.0000 | — | — |
| Candidate (Natural Plan) | 1425 | 100 | 7.537 | 1.0000 | 2498.447 | 11681792 |
| Controlled HNSW (Informational Only) | 1425 | 100 | 2.221 | 1.0000 | — | — |
KEEP_EXACT: planner_prefers_sequential_scan
Evidence: /Users/pythagor/nexus/.claude/worktrees/766-ann-gate/docs/qa/766-ann-gate/save_01.json
```

`save_01.json` records the refreshed natural and controlled plans for every
probe, three latency measurements per probe, top-10 sets, recall, index build
time and size, machine/software versions, source slot, and clone cleanup.
All 100 natural candidate plans select sequential scans. The natural candidate
p95 is slower than exact; scale and exact latency are also below their gate
thresholds. Controlled HNSW is faster at recall 1.0, but cannot change the verdict.


## Verification Commands and Tails

All commands ran from this worktree. Interpreter provenance was checked first:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/766-ann-gate/nexus/__init__.py
```

### Offline Suite

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > /tmp/766-third-offline-final.log 2>&1
```

```text
2817 passed, 938 skipped, 9 warnings in 128.03s (0:02:08)
```

### Required PostgreSQL Selection

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon tests/test_api -k 'ann or vector or embedding or search' > /tmp/766-third-postgres-final.log 2>&1
```

```text
27 passed, 438 deselected, 9 warnings in 33.04s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Black

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/config/settings_models.py nexus/agents/memnon/utils/embedding_tables.py nexus/agents/memnon/utils/db_access.py nexus/agents/memnon/utils/alias_search.py nexus/agents/orrery/knowledge_surfacing.py scripts/qa_shift/ann_gate.py tests/test_memnon/test_ann_gate.py > /tmp/766-third-black-final.log 2>&1
```

```text
All done! ✨ 🍰 ✨
7 files would be left unchanged.
```

### Reachability and Prompt Lint

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py tests/test_prompt_lint.py > /tmp/766-third-static.log 2>&1
```

```text
60 passed, 5 warnings in 18.97s
```

### Static Reachability Report

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/check_reachability.py --report /tmp/766-third-reachability.json > /tmp/766-third-reachability.log 2>&1
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

### Configuration Validation

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py > /tmp/766-third-config.log 2>&1
```

Exit 0; no stdout or stderr.

The required PostgreSQL selection ran all 27 tests with no skips or failures;
no #885 exemption was needed. The offline skips are opt-in integration and
live-provider tests. Static reachability reports no lost production paths or
new orphan modules; HTTP route reachability is not claimed by that report.

### Development Checks

Before expanding the SQL fingerprint selector to include cosine queries with
`SELECT` followed by a newline, the focused PostgreSQL test file passed:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon/test_ann_gate.py > /tmp/766-third-focused.log 2>&1
```

```text
15 passed, 5 warnings in 24.20s
```

The first complete offline and PostgreSQL selection runs also passed:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > /tmp/766-third-offline.log 2>&1
```

```text
2817 passed, 938 skipped, 9 warnings in 129.25s (0:02:09)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon tests/test_api -k 'ann or vector or embedding or search' > /tmp/766-third-postgres.log 2>&1
```

```text
27 passed, 438 deselected, 9 warnings in 31.92s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

The final runs above include the expanded fingerprint check. Formatting used:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black nexus/config/settings_models.py nexus/agents/memnon/utils/embedding_tables.py nexus/agents/memnon/utils/db_access.py nexus/agents/memnon/utils/alias_search.py nexus/agents/orrery/knowledge_surfacing.py scripts/qa_shift/ann_gate.py tests/test_memnon/test_ann_gate.py
```

```text
All done! ✨ 🍰 ✨
3 files reformatted, 4 files left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black tests/test_memnon/test_ann_gate.py > /tmp/766-third-format.log 2>&1
```

```text
All done! ✨ 🍰 ✨
1 file reformatted.
```

### Commit Hooks

Implementation commit `f6bedea2` ran both hooks without bypass:

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
```


## Source and Cleanup Evidence

The following queries ran with `default_transaction_read_only=on` against
`save_01`. Verbatim SQL and returned rows:

```text
transaction_read_only: on
SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'chunk_metadata' AND column_name IN ('characters', 'place', 'atmosphere');
[]
SELECT count(*) AS rows FROM chunk_embeddings_2560d;
[(1425,)]
SELECT indexname FROM pg_indexes WHERE tablename = 'chunk_embeddings_2560d' AND indexdef ILIKE '%hnsw%';
[]
```

After the operator and final PostgreSQL selection completed, a read-only
connection to `postgres` returned no remaining gate clones:

```text
SELECT datname FROM pg_database WHERE datname LIKE 'qa640_766_%';
[]
```

## Deferred Work and Coordinator Questions

Promotion is a future order. It must ship iterative scans
(`hnsw.iterative_scan`), an overfetch-and-filter stage or partial indexes, and
measured filtered and hybrid recall. This benchmark's model-scoped nearest
neighbors do not establish those production-query recall guarantees. Even a
future `PROMOTE` verdict is measurement evidence, not an automatic runtime
switch or deployment. The natural planner crossover at larger scale is not
established by this small-corpus run.

No unresolved coordinator questions. No save writes, fleet/template DDL, paid
calls, or embedding inference occurred. No gateway was started. PR #944 is
updated on the same branch, without merging or waiting for review bots.

Authored by Codex (GPT-6 Astra).
