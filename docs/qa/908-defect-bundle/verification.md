# Work Order 908 Verification

## PR #916 Review Fixes

The following results supersede the earlier continuation proof below.

- **P1 / defect 6:** `scripts/stamp_lore_pass_baseline.py:115` adds
  `--refresh-fingerprint --slot N` or `--refresh-fingerprint --dbname qa640_*`.
  It validates the existing tail baseline, uses the target's story projection,
  locks the row, and changes only the payload's `config_fingerprint` with
  `jsonb_set` (`:163`). It prints old/new hashes and refuses missing baselines.
  `docs/settings_scopes.md` documents the explicit compatibility procedure;
  the coordinator refreshes affected saves at landing, with turns stopped.
- **P2 / defect 1:** `alias_search.py:21` loads names and populated aliases from
  PostgreSQL and attaches second-person pronouns to the canonical player.
  `memnon.py:714` propagates loader errors. No `ALIAS_LOOKUP` constant or cast
  fallback remains. Legacy examples under `nexus/` now use generic roles;
  the alias-search documentation describes the real database path.
- **P3 / defect 6:** `CLAUDE.md:212` now describes all matched known entities,
  the separate raw-retrieval decision, and downstream chunk deduplication.
- **Defect 5:** Typed render limits and signed relationship valence remain
  covered by the required PostgreSQL gate; #903 block budgeting is unchanged.
- **Defect 4:** `git fetch origin && git merge origin/main` reported
  `Already up to date.` Main is still `20e2c07b54cabbfb1981b0eee328dc03e2617804`.
  `git show origin/main:nexus/agents/lore/utils/turn_cycle.py | rg -n -i
  'events|threats|does not exist'` returned no matches (exit 1).
- **Defects 2 and 3:** Still deferred to #914 and #913. No migration/index was
  added; migration 119 is unallocated by this branch. No `prompts/*.md` edit.

### Clone Continuation Evidence

The first successful clone proof used save_04's actual stored fingerprint,
without restamping it to manufacture the mismatch. The production
`LORE.process_turn` path failed on the unchanged fingerprint check, then
completed after running the refresh CLI. LOGON was disabled; no paid inference
was called. This is continuation/context-assembly proof, not generated-prose QA.

```text
Before refresh: Error processing turn: Pass-2 baseline config fingerprint is incompatible for parent chunk 49: stored=434647cf417a9365a6e3af0e762d317915099deea8ea38cd4abb891ecbf36eca, current=a3b2eb7891eda6732d1190e69eaff3add40d591637e52f8669d9bbe797d78ad7
Refreshed qa640_908_fingerprint_63b2b47abc44 tail chunk 49 Pass-2 fingerprint: 434647cf417a9365a6e3af0e762d317915099deea8ea38cd4abb891ecbf36eca -> a3b2eb7891eda6732d1190e69eaff3add40d591637e52f8669d9bbe797d78ad7
Only the tail config_fingerprint changed; all other baseline content and incubator rows are identical.
After refresh: LOGON disabled; baseline_available=True
Story pin projection, repeat refresh, and missing-baseline refusal passed.
```

The durable regression reconstructs the historical `[memory]` shape only in
its disposable clone so it remains useful after fleet refresh. It also verifies
the story-window projection, repeat refresh, and refusal when the baseline is
missing. The alias regression uses real PostgreSQL through MEMNON's loader,
changes the cast, and renames the alias table to prove database errors propagate.
All disposable databases were cleaned up by their fixtures. No save was written.

The cast scan `rg -n -i '\b(alex|emilia|pete|alina|nyati|peter)\b' nexus`
returned no matches. `rg -n 'ALIAS_LOOKUP' nexus` also returned no matches.
`rg -n 'divergence_threshold|divergence_confidence' nexus tests nexus.toml CLAUDE.md`
finds only the intentional historical-key seed in
`tests/test_lore/test_baseline_fingerprint_refresh_pg.py:47`.

### Review Validation

All commands run in this worktree with no gateway environment overrides.
Import verification again printed this worktree's `nexus/__init__.py`.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > .qa908/review-offline.log 2>&1
```

```text
2647 passed, 806 skipped, 9 warnings in 94.60s (0:01:34)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon_db_access.py tests/test_lore -k 'query or pattern or divergence or render or relationship' > .qa908/review-postgres.log 2>&1
```

```text
42 passed, 246 deselected, 9 warnings in 70.85s (0:01:10)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_lore/test_baseline_fingerprint_refresh_pg.py tests/test_lore/test_query_patterns_pg.py > .qa908/review-focused-final.log 2>&1
```

```text
6 passed, 9 warnings in 32.46s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only origin/main -- '*.py') > .qa908/review-black-final.log 2>&1
```

```text
All done! ✨ 🍰 ✨
22 files would be left unchanged.
```

The required PostgreSQL selection includes both new regression tests and had
no skips. The offline suite intentionally skips database/live-provider tests.
No #885 exemption was needed. `git diff --check` passed. Commit hooks passed.

### Diagnostic Runs Before the Final Gates

The first new clone test needed the same disposable-name allowlist setup used
by the existing PostgreSQL fixtures. It failed before continuation with:
`Invalid database name: 'qa640_908_fingerprint_5af77c642b84'. Must be one of:
save_01, save_02, save_03, save_04, save_05`. The fix changes only the test's
allowlist; real LORE, MEMNON, and PostgreSQL remain in use.

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_lore/test_baseline_fingerprint_refresh_pg.py tests/test_lore/test_query_patterns_pg.py > .qa908/review-focused.log 2>&1
```

```text
FAILED tests/test_lore/test_baseline_fingerprint_refresh_pg.py::test_divergence_fingerprint_refresh_preserves_save4_continuation
1 failed, 5 passed, 5 warnings in 3.34s
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_lore/test_baseline_fingerprint_refresh_pg.py > .qa908/review-fingerprint.log 2>&1
```

```text
1 passed, 9 warnings in 29.23s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only origin/main -- '*.py') > .qa908/review-black.log 2>&1
```

```text
would reformat nexus/agents/memnon/utils/temporal_search_example.py

Oh no! 💥 💔 💥
1 file would be reformatted, 21 files would be left unchanged.
```

Black's initial check caught the longer generic query in
`temporal_search_example.py`; formatting that file produced the clean gate above.

### Coordinator Action

Run the documented fingerprint refresh for affected saves after deployment,
with turns stopped. No open design questions. Do not merge this PR from this
work order.


## Amended Scope

The coordinator deferred defect 2 to #914 after the initial stop below.
Migration 119 remains unallocated. Defect 3 remains deferred to #913.
This continuation implements defects 1, 5, and 6 and confirms defect 4.

## Remaining Defect Outcomes

- **1 — Fixed.** `query_analysis.py:36-55` requires an explicit database URL,
  reads `characters.name` and populated `character_aliases.alias`, and escapes
  each name for classification and extraction. SearchManager, MEMNON, and turn
  accounting share that analyzer. `test_query_patterns_pg.py` seeds a disposable
  cast and exercises aliases, regex punctuation, boundaries, changed/empty casts,
  and missing databases through the real PostgreSQL connection path.
- **4 — Confirmed absent.** After `git fetch origin main`, `origin/main` remains
  `20e2c07b54cabbfb1981b0eee328dc03e2617804`; the exact `git show ... | rg ...`
  command preserved below still returns no matches (exit 1).
- **5 — Fixed.** `nexus.toml:228-232` sets four per-block caps (default five),
  validated by `settings_models.py:953-961`. `logon_utility.py:2549-2555` renders
  signed `valence_current`; its event, threat, and Bleed loops use their own caps.
  Real renderer tests cover independent limits below/above five and negative,
  zero, and positive valence. The #903 budget machinery and `prompts/*.md` are
  unchanged.
- **6 — Fixed.** Removed the threshold from TOML, its Pydantic field, manager
  reads and diagnostics, and the fabricated confidence from detector results,
  context state, and memory summaries. `entity_detector.py:271-275` retains the
  boolean detection and explicit gaps; `divergence.py:13-25` serializes that
  contract. Updated the CLAUDE.md paragraph and affected tests. `rg -n
  'divergence_threshold|divergence_confidence' nexus tests nexus.toml CLAUDE.md`
  returns no matches (exit 1).

No schema migration, UI change, gateway process, or paid provider call was
needed. The existing PostgreSQL fixtures own and clean up their disposable
clones; no save was written. No #885 exception was needed by the passing gates.

## Continuation Proof

All commands run from this worktree with the shared interpreter. No gateway
environment overrides were set. Final tail output is verbatim.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > .qa908/offline-final.log 2>&1
```

```text
2647 passed, 804 skipped, 9 warnings in 95.30s (0:01:35)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_memnon_db_access.py tests/test_lore -k 'query or pattern or divergence or render or relationship' > .qa908/postgres-final.log 2>&1
```

```text
40 passed, 246 deselected, 9 warnings in 40.40s
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_query_patterns_pg.py tests/test_lore/test_logon_prompt_formatting.py -k 'query_patterns or render_limits' > .qa908/focused-final.log 2>&1
```

```text
10 passed, 35 deselected, 5 warnings in 1.54s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only origin/main -- '*.py') > .qa908/black-final.log 2>&1
```

```text
All done! ✨ 🍰 ✨
16 files would be left unchanged.
```

The offline gate intentionally skips PostgreSQL/live-provider tests. The required
PostgreSQL selection ran without skips. Both pre-commit hooks passed on both
implementation commits; `git diff --check` passed.

An earlier offline run overlapped pre-commit's temporary unstaged-file stash.
Its 23 failures were configuration mismatches (new Pydantic code reading the
briefly restored old TOML), not accepted gate results. The final offline and
PostgreSQL gates above ran after both code commits, with no overlapping commits.

Earlier runs used the same pytest commands with `.qa908/offline.log`,
`.qa908/postgres.log`, and `.qa908/focused.log` as output paths, respectively:

```text
23 failed, 2624 passed, 804 skipped, 9 warnings in 106.88s (0:01:46)
40 passed, 246 deselected, 9 warnings in 46.57s
10 passed, 35 deselected, 5 warnings in 1.92s
```


## Coordinator Questions

None. Defect 2 belongs to #914; defect 3 belongs to #913. Migration 119 remains
free. The prior failed index experiment below is retained as historical evidence,
not claimed as a successful build.

## Initial Stop Report (Preserved)

### Blocking Finding

Defect 2 cannot be implemented as specified on the installed pgvector 0.8.0.
The source table stores `vector(2560)`; HNSW rejects vectors above 2,000
dimensions. The attempted index used the same `vector_cosine_ops`,
`ef_construction = 64`, and `m = 16` as save_01's existing 1024d index.
The work order requires stopping when an honest attempt cannot satisfy a gate.

At the initial stop, no runtime code, configuration, prompts, or migration files were changed.
Migration 119 remains unallocated by this branch. No pytest or Black gates were
run or claimed passed; no PR was opened. Defects 1, 5, and 6 remain unimplemented;
defect 3 remains deferred to #913.

### Environment and Read-Only Evidence

Branch: `claude/908-defect-bundle`; base: `20e2c07b`.
Read issue #908 using `gh issue view 908` before investigating.

Command:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

Output:

```text
/Users/pythagor/nexus/.claude/worktrees/908-defect-bundle/nexus/__init__.py
```

Read-only SQL on save_01 confirmed:

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
-- 0.8.0
SELECT count(*) AS chunks FROM narrative_chunks;
-- 1425
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename IN ('chunk_embeddings_1024d', 'chunk_embeddings_2560d');
-- 1024d: CREATE INDEX chunk_embeddings_1024d_hnsw_idx ON
-- public.chunk_embeddings_1024d USING hnsw (embedding vector_cosine_ops)
-- WITH (ef_construction='64', m='16')
-- 2560d: primary key and model btree only
SELECT format_type(atttypid, atttypmod) AS embedding_type
FROM pg_attribute
WHERE attrelid = 'chunk_embeddings_2560d'::regclass AND attname = 'embedding';
-- vector(2560)
```

The dimension limit is already documented in
`nexus/agents/memnon/utils/embedding_tables.py:19-21` and
`migrations/014_add_2560d_4096d_embeddings.sql:3-5,34-38`.
No 1024d HNSW migration was found under `migrations/`; the live index definition
provided the required operator class and parameters.

Defect 4 is confirmed absent from the locally fetched `origin/main` at
`20e2c07b`: this command returned no matches (exit 1):

```sh
git show origin/main:nexus/agents/lore/utils/turn_cycle.py | rg -n -i 'events|threats|does not exist'
```

### Clone and Index Attempt

Commands (completed successfully, with no output):

```sh
mkdir -p .qa908
pg_dump -Fc -d save_01 -f .qa908/save_01.dump
createdb qa640_908_hnsw
pg_restore --exit-on-error --no-owner -d qa640_908_hnsw .qa908/save_01.dump
```

Command:

```sh
psql -X -v ON_ERROR_STOP=1 -d qa640_908_hnsw -c "SELECT count(*) AS chunks FROM narrative_chunks; SELECT count(*) AS embeddings FROM chunk_embeddings_2560d;"
```

Output:

```text
 chunks
--------
   1425
(1 row)

 embeddings
------------
       1425
(1 row)
```

Exact index-build command:

```sh
psql -X -v ON_ERROR_STOP=1 -d qa640_908_hnsw <<'SQL'
\timing on
CREATE INDEX IF NOT EXISTS chunk_embeddings_2560d_hnsw_idx
ON public.chunk_embeddings_2560d USING hnsw (embedding vector_cosine_ops)
WITH (ef_construction = 64, m = 16);
COMMENT ON INDEX public.chunk_embeddings_2560d_hnsw_idx IS
'Accelerate cosine nearest-neighbor retrieval for 2560-dimensional narrative chunk embeddings.';
SQL
```

Verbatim output (exit 3):

```text
Timing is on.
ERROR:  column cannot have more than 2000 dimensions for hnsw index
Time: 2.103 ms
```

The 2.103 ms is time to rejection, not a successful index build time.
`ON_ERROR_STOP` prevented the index comment from executing.
Idempotence and successful build timing could not be validated.

### Cleanup and Coordinator Question

The disposable `qa640_908_hnsw` database and `.qa908/save_01.dump` were removed
after recording the failure. No save database was written, no service was
started, and no provider was called.

The initial coordinator question was whether to defer defect 2 or authorize a
different index representation/operator class and matching retrieval changes.
The amendment resolved this by deferring it to #914.
A half-precision expression index would not satisfy this order's requirement
to use the 1024d index's operator class.
