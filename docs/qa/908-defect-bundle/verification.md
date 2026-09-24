# Work Order 908 Stop Report

## Blocking Finding

Defect 2 cannot be implemented as specified on the installed pgvector 0.8.0.
The source table stores `vector(2560)`; HNSW rejects vectors above 2,000
dimensions. The attempted index used the same `vector_cosine_ops`,
`ef_construction = 64`, and `m = 16` as save_01's existing 1024d index.
The work order requires stopping when an honest attempt cannot satisfy a gate.

No runtime code, configuration, prompts, or migration files were changed.
Migration 119 remains unallocated by this branch. No pytest or Black gates were
run or claimed passed; no PR was opened. Defects 1, 5, and 6 remain unimplemented;
defect 3 remains deferred to #913.

## Environment and Read-Only Evidence

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

## Clone and Index Attempt

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

## Cleanup and Coordinator Question

The disposable `qa640_908_hnsw` database and `.qa908/save_01.dump` were removed
after recording the failure. No save database was written, no service was
started, and no provider was called.

Should defect 2 be deferred, or should a revised work order authorize a different
index representation/operator class and the matching retrieval changes?
A half-precision expression index would not satisfy this order's requirement
to use the 1024d index's operator class.
