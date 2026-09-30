# Legacy Vector Dimension Inventory (#812, Order 812-S1)

**Snapshot taken 2026-09-30, 12:40:03-12:40:09 America/New_York (11:40 CDT), on the owner's PostgreSQL 17.11 server (Postgres.app, localhost:5432).** This is a point-in-time snapshot of read-only SQL. It changes nothing, and any later embedding job, slot reset, or clone makes it stale. Every session ran with `PGOPTIONS='-c default_transaction_read_only=on'` (plus `-c statement_timeout=90000`), and the first statement of every session is `SHOW default_transaction_read_only`, which returned `on` in all of them. No database was written.

The issue's verifier amendment asks for this inventory "before dropping" legacy dimensions. This change drops nothing; it removes two unread constants (`LEGACY_EMBEDDING_DIMENSIONS`, `DIMENSION_TABLES`) and records what exists.

## Databases on the Server

```
$ psql -Atc "SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY 1"
NEXUS
NEXUS_template
mock
nexus_test_correspondence_370c240cc28f
orrery_rehearsal_01
orrery_rehearsal_02
orrery_rehearsal_05
postgres
pythagor
qa640_offline_gate_04fe3b0fe387
qa832_recap_f271e0643367
ref_codex_bakeoff_2026_07
save_01
save_01_backup_009
save_02
save_02_pre203_20260516_122902
save_03
save_04
save_05
```

Inventoried (14): `save_01` to `save_05`, `NEXUS_template`, the deprecated `NEXUS`, the reference corpus `ref_codex_bakeoff_2026_07`, and every other owner database that holds embedding tables (`save_01_backup_009`, `save_02_pre203_20260516_122902`, `orrery_rehearsal_01`, `orrery_rehearsal_02`, `orrery_rehearsal_05`, `mock`).

Skipped:

- `postgres`, `pythagor`: maintenance databases; the discovery pass below found no embedding tables in them.
- `qa640_offline_gate_04fe3b0fe387`, `qa832_recap_f271e0643367`, `nexus_test_correspondence_370c240cc28f`: disposable databases owned by test runs that other builders run on this machine right now. They are not owner data, and an open connection from this inventory would make their fixtures' `DROP DATABASE` fail, so they were not opened.

## Discovery Pass

The table patterns are those in `nexus/agents/memnon/utils/embedding_tables.py` (`EMBEDDING_TABLE_PATTERN`, `RETROGRADE_SUMMARY_EMBEDDING_TABLE_PATTERN`, `CHARACTER_EXPERIENCE_EMBEDDING_TABLE_PATTERN`), searched in every schema.

```
$ for db in NEXUS NEXUS_template mock orrery_rehearsal_01 orrery_rehearsal_02 orrery_rehearsal_05 postgres pythagor ref_codex_bakeoff_2026_07 save_01 save_01_backup_009 save_02 save_02_pre203_20260516_122902 save_03 save_04 save_05; do echo "== $db"; PGOPTIONS='-c default_transaction_read_only=on' psql -X -d "$db" -Atc "SHOW default_transaction_read_only" -c "SELECT n.nspname||'.'||c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind IN ('r','p') AND c.relname ~ '^(chunk_embeddings|retrograde_summary_embeddings|character_experience_embeddings)_[0-9]+d\$' ORDER BY 1"; done
== NEXUS
on
public.chunk_embeddings_0384d
public.chunk_embeddings_1024d
public.chunk_embeddings_1536d
public.chunk_embeddings_2560d
public.chunk_embeddings_4096d
== NEXUS_template
on
== mock
on
public.chunk_embeddings_0384d
public.chunk_embeddings_1024d
public.chunk_embeddings_1536d
== orrery_rehearsal_01
on
public.chunk_embeddings_1024d
public.chunk_embeddings_1536d
== orrery_rehearsal_02
on
public.chunk_embeddings_1024d
public.chunk_embeddings_1536d
== orrery_rehearsal_05
on
public.chunk_embeddings_2560d
== postgres
on
== pythagor
on
== ref_codex_bakeoff_2026_07
on
public.chunk_embeddings_2560d
public.retrograde_summary_embeddings_2560d
== save_01
on
public.chunk_embeddings_1024d
public.chunk_embeddings_1536d
public.chunk_embeddings_2560d
public.retrograde_summary_embeddings_1024d
public.retrograde_summary_embeddings_1536d
public.retrograde_summary_embeddings_2560d
== save_01_backup_009
on
public.chunk_embeddings_0384d
public.chunk_embeddings_1024d
public.chunk_embeddings_1536d
== save_02
on
public.chunk_embeddings_1024d
public.chunk_embeddings_1536d
public.chunk_embeddings_2560d
public.retrograde_summary_embeddings_1024d
public.retrograde_summary_embeddings_1536d
public.retrograde_summary_embeddings_2560d
== save_02_pre203_20260516_122902
on
public.chunk_embeddings_1024d
public.chunk_embeddings_1536d
public.chunk_embeddings_2560d
public.chunk_embeddings_4096d
== save_03
on
public.chunk_embeddings_2560d
public.retrograde_summary_embeddings_2560d
== save_04
on
public.chunk_embeddings_2560d
public.retrograde_summary_embeddings_2560d
== save_05
on
```

No database holds a `character_experience_embeddings_NNNNd` table (the table is created lazily on first write). `NEXUS_template` and `save_05` hold no embedding table at all (confirmed again by the zero count in their transcripts).

## Summary

Rows, sizes, and models come from the transcripts below. "Differ" counts chunks whose two vectors in one family are not exactly equal (their `vector::text` values differ).

| Database | Table | Rows | Total size (bytes) | Models: rows (created_at range) |
|---|---|---:|---:|---|
| save_01 | chunk_embeddings_1024d | 5,700 | 59,588,608 | `bge-large` 1,425 and `e5-large` 1,425 (2025-04-21); `BAAI/bge-large-en` 1,425 and `intfloat/e5-large-v2` 1,425 (2025-08-12) |
| save_01 | chunk_embeddings_1536d | 2,850 | 38,772,736 | `inf-retriever-v1-1.5b` 1,425 (2025-04-21); `infly/inf-retriever-v1-1.5b` 1,425 (2025-08-12) |
| save_01 | chunk_embeddings_2560d | 1,425 | 18,038,784 | `Octen-Embedding-4B` 1,425 (2026-05-16) |
| save_01 | retrograde_summary_embeddings_1024d / _1536d / _2560d | 0 / 0 / 0 | 24,576 each | none |
| save_02 | chunk_embeddings_1024d | 5,700 | 59,531,264 | same four models and timestamps as save_01 |
| save_02 | chunk_embeddings_1536d | 2,850 | 38,756,352 | same two models and timestamps as save_01 |
| save_02 | chunk_embeddings_2560d | 1,425 | 18,038,784 | `Octen-Embedding-4B` 1,425 (2026-05-16) |
| save_02 | retrograde_summary_embeddings_1024d / _1536d / _2560d | 0 / 0 / 0 | 24,576 each | none |
| save_03 | chunk_embeddings_2560d | 38 | 548,864 | `Octen-Embedding-4B` 38 (2026-07-30 to 2026-08-09) |
| save_03 | retrograde_summary_embeddings_2560d | 18 | 319,488 | `Octen-Embedding-4B` 18 (2026-07-30 to 2026-08-06) |
| save_04 | chunk_embeddings_2560d | 44 | 622,592 | `Octen-Embedding-4B` 44 (2026-07-30 to 2026-08-21) |
| save_04 | retrograde_summary_embeddings_2560d | 15 | 278,528 | `Octen-Embedding-4B` 15 (2026-07-30 to 2026-08-21) |
| save_05 | (none) | | | |
| NEXUS_template | (none) | | | |
| NEXUS | chunk_embeddings_0384d | 0 | 24,576 | none (embedding column is `character varying`) |
| NEXUS | chunk_embeddings_1024d | 7,125 | 79,986,688 | the four save_01 models (same timestamps) plus `Octen-Embedding-0.6B` 1,425 (2026-05-11) |
| NEXUS | chunk_embeddings_1536d | 2,850 | 39,124,992 | same two models and timestamps as save_01 |
| NEXUS | chunk_embeddings_2560d | 1,425 | 18,104,320 | `Octen-Embedding-4B` 1,425 (2026-05-11) |
| NEXUS | chunk_embeddings_4096d | 1,425 | 24,764,416 | `Octen-Embedding-8B` 1,425 (2026-05-11) |
| ref_codex_bakeoff_2026_07 | chunk_embeddings_2560d | 109 | 1,474,560 | `Octen-Embedding-4B` 109 (2026-07-14 to 2026-07-15) |
| ref_codex_bakeoff_2026_07 | retrograde_summary_embeddings_2560d | 34 | 499,712 | `Octen-Embedding-4B` 34 (2026-07-14 to 2026-07-15) |
| save_01_backup_009 | chunk_embeddings_0384d | 0 | 24,576 | none |
| save_01_backup_009 | chunk_embeddings_1024d | 5,700 | 59,736,064 | same four models and timestamps as save_01 |
| save_01_backup_009 | chunk_embeddings_1536d | 2,850 | 38,854,656 | same two models and timestamps as save_01 |
| save_02_pre203_20260516_122902 | chunk_embeddings_1024d | 5,700 | 59,736,064 | same four models and timestamps as save_01 |
| save_02_pre203_20260516_122902 | chunk_embeddings_1536d | 2,850 | 38,854,656 | same two models and timestamps as save_01 |
| save_02_pre203_20260516_122902 | chunk_embeddings_2560d / _4096d | 0 / 0 | 32,768 each | none |
| orrery_rehearsal_01 | chunk_embeddings_1024d | 5,700 | 59,564,032 | same four models and timestamps as save_01 |
| orrery_rehearsal_01 | chunk_embeddings_1536d | 2,850 | 38,756,352 | same two models and timestamps as save_01 |
| orrery_rehearsal_02 | chunk_embeddings_1024d | 5,700 | 59,531,264 | same four models and timestamps as save_01 |
| orrery_rehearsal_02 | chunk_embeddings_1536d | 2,850 | 38,756,352 | same two models and timestamps as save_01 |
| orrery_rehearsal_05 | chunk_embeddings_2560d | 1 | 98,304 | `Octen-Embedding-4B` 1 (2026-05-15) |
| mock | chunk_embeddings_0384d / _1024d / _1536d | 0 / 0 / 0 | 24,576 / 57,344 / 57,344 | none |

### Two Generations of the Same Model

The `(chunk_id, model)` primary key allows one row per exact model string, so each "second generation" is stored under a second name for the same model: the `[memnon.models]` entry key (`bge-large`, `e5-large`, `inf-retriever-v1-1.5b`, written 2025-04-21) and that entry's `remote_path` (`BAAI/bge-large-en`, `intfloat/e5-large-v2`, `infly/inf-retriever-v1-1.5b`, written 2025-08-12). The inventory groups rows by registry family (entry key and `remote_path`, from `nexus.toml` lines 900-960). The result is identical in every database that holds the legacy tables (`save_01`, `save_02`, `NEXUS`, `save_01_backup_009`, `save_02_pre203_20260516_122902`, `orrery_rehearsal_01`, `orrery_rehearsal_02`):

| Family | Table | Chunks | Chunks with more than one row | Chunks whose vectors differ | Cosine distance between generations (min / avg / max) |
|---|---|---:|---:|---:|---|
| bge-large | chunk_embeddings_1024d | 1,425 | 1,425 | 225 | 0.000000 / 0.000385 / 0.027360 |
| e5-large | chunk_embeddings_1024d | 1,425 | 1,425 | 225 | 0.000000 / 0.000620 / 0.049550 |
| inf-retriever-v1-1.5b | chunk_embeddings_1536d | 1,425 | 1,425 | 345 | 0.000000 / 0.000307 / 0.038963 |

Every Octen family (`Octen-Embedding-0.6B`, `-4B`, `-8B`) has one row per chunk: 0 chunks with more than one row, 0 that differ. No retrograde summary table holds a legacy-dimension row.

## Which Model and Dimension Production Reads Today

Production reads **`Octen-Embedding-4B` at 2560 dimensions** from `chunk_embeddings_2560d` (narrative chunks) and `retrograde_summary_embeddings_2560d` (Retrograde summaries), filtered by `model = 'Octen-Embedding-4B'`. No production path reads the 0384d, 1024d, 1536d, or 4096d tables; the inactive registry entries are only selectable as offline ir_eval candidates (`nexus.toml:884-890`).

- Settings key: `[memnon.models."Octen-Embedding-4B"]` at `nexus.toml:935-940`: `is_active = true`, `dimensions = 2560`, `weight = 1.0`. Every other entry is `is_active = false` with `weight = 0.0`.
- Exactly one active embedder is enforced at load: `nexus/config/settings_models.py:4398-4411`.
- Only the active entry is loaded: `nexus/agents/memnon/utils/embedding_manager.py:194-207` (`_initialize_models` skips `is_active = false`).
- MEMNON builds its query embeddings from the loaded models only: `nexus/agents/memnon/memnon.py:683-689`, then calls `execute_multi_model_hybrid_search` at `nexus/agents/memnon/memnon.py:782-785` (the temporal path, `nexus/agents/memnon/utils/continuous_temporal_search.py:514,544,611`, calls the same function).
- The reader picks the table from the query vector's length and filters by model: `nexus/agents/memnon/utils/db_access.py:1074` (`table_name = resolve_dimension_table(dimensions)`, so 2560 gives `chunk_embeddings_2560d`) and `nexus/agents/memnon/utils/db_access.py:1099` (`ce.model = %s`). Retrograde summaries use `retrograde_summary_table_name_for_dimensions` at `nexus/agents/memnon/utils/db_access.py:992` with `rse.model = %s` at line 1012.
- The writer embeds with the active models only: `nexus/jobs/embeddings.py:76` (`active_embedding_models`, defined at `nexus/agents/memnon/utils/source_embeddings.py:101-116`), into `table_name_for_dimensions(dimensions)`.

## The Deleted Constants Had No Reader

```
$ git grep -n -E "LEGACY_EMBEDDING_DIMENSIONS|DIMENSION_TABLES" origin/main
origin/main:nexus/agents/memnon/utils/embedding_tables.py:25:LEGACY_EMBEDDING_DIMENSIONS = (1024, 1536, 2560, 4096)
origin/main:nexus/agents/memnon/utils/embedding_tables.py:26:DIMENSION_TABLES: List[str] = [
origin/main:nexus/agents/memnon/utils/embedding_tables.py:27:    f"chunk_embeddings_{dimensions:04d}d" for dimensions in LEGACY_EMBEDDING_DIMENSIONS

$ git grep -n -E "LEGACY_EMBEDDING_DIMENSIONS|DIMENSION_TABLES"      # this branch
tests/test_ir_eval_v2/test_embedding_tables.py:52:    assert not hasattr(embedding_tables, "LEGACY_EMBEDDING_DIMENSIONS")
tests/test_ir_eval_v2/test_embedding_tables.py:53:    assert not hasattr(embedding_tables, "DIMENSION_TABLES")
```

A filesystem `grep -rn` over the worktree (tracked and untracked, `.git` and `node_modules` excluded) returns the same two test lines. The only hits on `origin/main` are the definitions themselves; `ir_eval/`, `scripts/`, `docs/`, and `tests/` hold none.

## How the Inventory Was Run

A generator read each database's table shapes in a read-only session (first statement `SHOW default_transaction_read_only`, which returned `on` for all 14), then wrote one SQL file per database. Each file was run with:

```
PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=90000' \
  psql -X -v ON_ERROR_STOP=1 -a -d "$db" -f "inventory_$db.sql"
```

`-a` echoes every statement before its output, so each transcript carries its own SQL. All 14 runs exited 0. The full transcripts are in [`transcripts/`](transcripts/), one file per database. The `save_01` transcript follows in full as the representative; the others run the same queries against their own tables.

<details><summary>save_01 transcript (SQL and output)</summary>

```
-- First statement of the session: the session is read-only.
SHOW default_transaction_read_only;
 default_transaction_read_only 
-------------------------------
 on
(1 row)

SELECT current_database() AS database, now() AS snapshot_at;
 database |         snapshot_at          
----------+------------------------------
 save_01  | 2026-09-30 12:40:03.25094-04
(1 row)

-- Tables, row counts and total relation size.
SELECT t.table_name, t.row_count,
       pg_total_relation_size(('public.' || t.table_name)::regclass) AS total_bytes,
       pg_size_pretty(pg_total_relation_size(('public.' || t.table_name)::regclass)) AS total_size
FROM (
    SELECT 'chunk_embeddings_1024d' AS table_name, (SELECT count(*) FROM public.chunk_embeddings_1024d) AS row_count
    UNION ALL SELECT 'chunk_embeddings_1536d' AS table_name, (SELECT count(*) FROM public.chunk_embeddings_1536d) AS row_count
    UNION ALL SELECT 'chunk_embeddings_2560d' AS table_name, (SELECT count(*) FROM public.chunk_embeddings_2560d) AS row_count
    UNION ALL SELECT 'retrograde_summary_embeddings_1024d' AS table_name, (SELECT count(*) FROM public.retrograde_summary_embeddings_1024d) AS row_count
    UNION ALL SELECT 'retrograde_summary_embeddings_1536d' AS table_name, (SELECT count(*) FROM public.retrograde_summary_embeddings_1536d) AS row_count
    UNION ALL SELECT 'retrograde_summary_embeddings_2560d' AS table_name, (SELECT count(*) FROM public.retrograde_summary_embeddings_2560d) AS row_count
) t
ORDER BY 1;
             table_name              | row_count | total_bytes | total_size 
-------------------------------------+-----------+-------------+------------
 chunk_embeddings_1024d              |      5700 |    59588608 | 57 MB
 chunk_embeddings_1536d              |      2850 |    38772736 | 37 MB
 chunk_embeddings_2560d              |      1425 |    18038784 | 17 MB
 retrograde_summary_embeddings_1024d |         0 |       24576 | 24 kB
 retrograde_summary_embeddings_1536d |         0 |       24576 | 24 kB
 retrograde_summary_embeddings_2560d |         0 |       24576 | 24 kB
(6 rows)

-- Rows per model in chunk_embeddings_1024d (embedding type vector(1024)).
SELECT model, count(*) AS rows, count(DISTINCT chunk_id) AS distinct_chunk_ids, min(created_at) AS earliest_created_at, max(created_at) AS latest_created_at
FROM public.chunk_embeddings_1024d GROUP BY model ORDER BY model;
        model         | rows | distinct_chunk_ids |      earliest_created_at      |       latest_created_at       
----------------------+------+--------------------+-------------------------------+-------------------------------
 BAAI/bge-large-en    | 1425 |               1425 | 2025-08-12 12:36:24.770362-04 | 2025-08-12 12:37:36.2834-04
 bge-large            | 1425 |               1425 | 2025-04-21 18:34:13.492018-04 | 2025-04-21 18:35:34.411871-04
 e5-large             | 1425 |               1425 | 2025-04-21 18:17:01.062454-04 | 2025-04-21 18:18:00.832686-04
 intfloat/e5-large-v2 | 1425 |               1425 | 2025-08-12 12:37:52.621872-04 | 2025-08-12 12:38:57.820514-04
(4 rows)

-- Two generations in chunk_embeddings_1024d: rows grouped by registry family (entry key and remote_path are one model).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.chunk_id AS item_id, e.model,
           coalesce(r.family, e.model) AS family,
           e.embedding::text AS vec
    FROM public.chunk_embeddings_1024d e LEFT JOIN registry r ON r.alias = e.model
),
per_item AS (
    SELECT family, item_id, count(*) AS n,
           count(DISTINCT vec) AS distinct_vectors
    FROM tagged GROUP BY family, item_id
)
SELECT p.family,
       (SELECT string_agg(DISTINCT t2.model, ', ') FROM tagged t2
        WHERE t2.family = p.family) AS model_names,
       count(*) AS chunk_ids,
       count(*) FILTER (WHERE n > 1) AS chunk_ids_with_multiple_rows,
       count(*) FILTER (WHERE distinct_vectors > 1) AS chunk_ids_whose_vectors_differ
FROM per_item p GROUP BY p.family ORDER BY p.family;
  family   |          model_names           | chunk_ids | chunk_ids_with_multiple_rows | chunk_ids_whose_vectors_differ 
-----------+--------------------------------+-----------+------------------------------+--------------------------------
 bge-large | BAAI/bge-large-en, bge-large   |      1425 |                         1425 |                            225
 e5-large  | e5-large, intfloat/e5-large-v2 |      1425 |                         1425 |                            225
(2 rows)

-- Cosine distance between the two generations in chunk_embeddings_1024d (pairs only; no rows means one generation).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.chunk_id AS item_id, e.model, e.embedding,
           coalesce(r.family, e.model) AS family
    FROM public.chunk_embeddings_1024d e LEFT JOIN registry r ON r.alias = e.model
)
SELECT a.family, a.model AS model_a, b.model AS model_b,
       count(*) AS pairs,
       round(min(a.embedding <=> b.embedding)::numeric, 6) AS min_cosine_distance,
       round(avg(a.embedding <=> b.embedding)::numeric, 6) AS avg_cosine_distance,
       round(max(a.embedding <=> b.embedding)::numeric, 6) AS max_cosine_distance
FROM tagged a JOIN tagged b
  ON a.item_id = b.item_id AND a.family = b.family AND a.model < b.model
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
  family   |      model_a      |       model_b        | pairs | min_cosine_distance | avg_cosine_distance | max_cosine_distance 
-----------+-------------------+----------------------+-------+---------------------+---------------------+---------------------
 bge-large | BAAI/bge-large-en | bge-large            |  1425 |            0.000000 |            0.000385 |            0.027360
 e5-large  | e5-large          | intfloat/e5-large-v2 |  1425 |            0.000000 |            0.000620 |            0.049550
(2 rows)

-- Rows per model in chunk_embeddings_1536d (embedding type vector(1536)).
SELECT model, count(*) AS rows, count(DISTINCT chunk_id) AS distinct_chunk_ids, min(created_at) AS earliest_created_at, max(created_at) AS latest_created_at
FROM public.chunk_embeddings_1536d GROUP BY model ORDER BY model;
            model            | rows | distinct_chunk_ids |      earliest_created_at      |       latest_created_at       
-----------------------------+------+--------------------+-------------------------------+-------------------------------
 inf-retriever-v1-1.5b       | 1425 |               1425 | 2025-04-21 18:18:33.628161-04 | 2025-04-21 18:27:14.907842-04
 infly/inf-retriever-v1-1.5b | 1425 |               1425 | 2025-08-12 12:39:11.132277-04 | 2025-08-12 12:47:47.514297-04
(2 rows)

-- Two generations in chunk_embeddings_1536d: rows grouped by registry family (entry key and remote_path are one model).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.chunk_id AS item_id, e.model,
           coalesce(r.family, e.model) AS family,
           e.embedding::text AS vec
    FROM public.chunk_embeddings_1536d e LEFT JOIN registry r ON r.alias = e.model
),
per_item AS (
    SELECT family, item_id, count(*) AS n,
           count(DISTINCT vec) AS distinct_vectors
    FROM tagged GROUP BY family, item_id
)
SELECT p.family,
       (SELECT string_agg(DISTINCT t2.model, ', ') FROM tagged t2
        WHERE t2.family = p.family) AS model_names,
       count(*) AS chunk_ids,
       count(*) FILTER (WHERE n > 1) AS chunk_ids_with_multiple_rows,
       count(*) FILTER (WHERE distinct_vectors > 1) AS chunk_ids_whose_vectors_differ
FROM per_item p GROUP BY p.family ORDER BY p.family;
        family         |                    model_names                     | chunk_ids | chunk_ids_with_multiple_rows | chunk_ids_whose_vectors_differ 
-----------------------+----------------------------------------------------+-----------+------------------------------+--------------------------------
 inf-retriever-v1-1.5b | inf-retriever-v1-1.5b, infly/inf-retriever-v1-1.5b |      1425 |                         1425 |                            345
(1 row)

-- Cosine distance between the two generations in chunk_embeddings_1536d (pairs only; no rows means one generation).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.chunk_id AS item_id, e.model, e.embedding,
           coalesce(r.family, e.model) AS family
    FROM public.chunk_embeddings_1536d e LEFT JOIN registry r ON r.alias = e.model
)
SELECT a.family, a.model AS model_a, b.model AS model_b,
       count(*) AS pairs,
       round(min(a.embedding <=> b.embedding)::numeric, 6) AS min_cosine_distance,
       round(avg(a.embedding <=> b.embedding)::numeric, 6) AS avg_cosine_distance,
       round(max(a.embedding <=> b.embedding)::numeric, 6) AS max_cosine_distance
FROM tagged a JOIN tagged b
  ON a.item_id = b.item_id AND a.family = b.family AND a.model < b.model
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
        family         |        model_a        |           model_b           | pairs | min_cosine_distance | avg_cosine_distance | max_cosine_distance 
-----------------------+-----------------------+-----------------------------+-------+---------------------+---------------------+---------------------
 inf-retriever-v1-1.5b | inf-retriever-v1-1.5b | infly/inf-retriever-v1-1.5b |  1425 |            0.000000 |            0.000307 |            0.038963
(1 row)

-- Rows per model in chunk_embeddings_2560d (embedding type vector(2560)).
SELECT model, count(*) AS rows, count(DISTINCT chunk_id) AS distinct_chunk_ids, min(created_at) AS earliest_created_at, max(created_at) AS latest_created_at
FROM public.chunk_embeddings_2560d GROUP BY model ORDER BY model;
       model        | rows | distinct_chunk_ids |      earliest_created_at      |       latest_created_at       
--------------------+------+--------------------+-------------------------------+-------------------------------
 Octen-Embedding-4B | 1425 |               1425 | 2026-05-16 18:06:03.794974-04 | 2026-05-16 18:24:45.282331-04
(1 row)

-- Two generations in chunk_embeddings_2560d: rows grouped by registry family (entry key and remote_path are one model).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.chunk_id AS item_id, e.model,
           coalesce(r.family, e.model) AS family,
           e.embedding::text AS vec
    FROM public.chunk_embeddings_2560d e LEFT JOIN registry r ON r.alias = e.model
),
per_item AS (
    SELECT family, item_id, count(*) AS n,
           count(DISTINCT vec) AS distinct_vectors
    FROM tagged GROUP BY family, item_id
)
SELECT p.family,
       (SELECT string_agg(DISTINCT t2.model, ', ') FROM tagged t2
        WHERE t2.family = p.family) AS model_names,
       count(*) AS chunk_ids,
       count(*) FILTER (WHERE n > 1) AS chunk_ids_with_multiple_rows,
       count(*) FILTER (WHERE distinct_vectors > 1) AS chunk_ids_whose_vectors_differ
FROM per_item p GROUP BY p.family ORDER BY p.family;
       family       |    model_names     | chunk_ids | chunk_ids_with_multiple_rows | chunk_ids_whose_vectors_differ 
--------------------+--------------------+-----------+------------------------------+--------------------------------
 Octen-Embedding-4B | Octen-Embedding-4B |      1425 |                            0 |                              0
(1 row)

-- Cosine distance between the two generations in chunk_embeddings_2560d (pairs only; no rows means one generation).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.chunk_id AS item_id, e.model, e.embedding,
           coalesce(r.family, e.model) AS family
    FROM public.chunk_embeddings_2560d e LEFT JOIN registry r ON r.alias = e.model
)
SELECT a.family, a.model AS model_a, b.model AS model_b,
       count(*) AS pairs,
       round(min(a.embedding <=> b.embedding)::numeric, 6) AS min_cosine_distance,
       round(avg(a.embedding <=> b.embedding)::numeric, 6) AS avg_cosine_distance,
       round(max(a.embedding <=> b.embedding)::numeric, 6) AS max_cosine_distance
FROM tagged a JOIN tagged b
  ON a.item_id = b.item_id AND a.family = b.family AND a.model < b.model
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
 family | model_a | model_b | pairs | min_cosine_distance | avg_cosine_distance | max_cosine_distance 
--------+---------+---------+-------+---------------------+---------------------+---------------------
(0 rows)

-- Rows per model in retrograde_summary_embeddings_1024d (embedding type vector(1024)).
SELECT model, count(*) AS rows, count(DISTINCT summary_id) AS distinct_summary_ids, min(created_at) AS earliest_created_at, max(created_at) AS latest_created_at
FROM public.retrograde_summary_embeddings_1024d GROUP BY model ORDER BY model;
 model | rows | distinct_summary_ids | earliest_created_at | latest_created_at 
-------+------+----------------------+---------------------+-------------------
(0 rows)

-- Two generations in retrograde_summary_embeddings_1024d: rows grouped by registry family (entry key and remote_path are one model).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.summary_id AS item_id, e.model,
           coalesce(r.family, e.model) AS family,
           e.embedding::text AS vec
    FROM public.retrograde_summary_embeddings_1024d e LEFT JOIN registry r ON r.alias = e.model
),
per_item AS (
    SELECT family, item_id, count(*) AS n,
           count(DISTINCT vec) AS distinct_vectors
    FROM tagged GROUP BY family, item_id
)
SELECT p.family,
       (SELECT string_agg(DISTINCT t2.model, ', ') FROM tagged t2
        WHERE t2.family = p.family) AS model_names,
       count(*) AS summary_ids,
       count(*) FILTER (WHERE n > 1) AS summary_ids_with_multiple_rows,
       count(*) FILTER (WHERE distinct_vectors > 1) AS summary_ids_whose_vectors_differ
FROM per_item p GROUP BY p.family ORDER BY p.family;
 family | model_names | summary_ids | summary_ids_with_multiple_rows | summary_ids_whose_vectors_differ 
--------+-------------+-------------+--------------------------------+----------------------------------
(0 rows)

-- Cosine distance between the two generations in retrograde_summary_embeddings_1024d (pairs only; no rows means one generation).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.summary_id AS item_id, e.model, e.embedding,
           coalesce(r.family, e.model) AS family
    FROM public.retrograde_summary_embeddings_1024d e LEFT JOIN registry r ON r.alias = e.model
)
SELECT a.family, a.model AS model_a, b.model AS model_b,
       count(*) AS pairs,
       round(min(a.embedding <=> b.embedding)::numeric, 6) AS min_cosine_distance,
       round(avg(a.embedding <=> b.embedding)::numeric, 6) AS avg_cosine_distance,
       round(max(a.embedding <=> b.embedding)::numeric, 6) AS max_cosine_distance
FROM tagged a JOIN tagged b
  ON a.item_id = b.item_id AND a.family = b.family AND a.model < b.model
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
 family | model_a | model_b | pairs | min_cosine_distance | avg_cosine_distance | max_cosine_distance 
--------+---------+---------+-------+---------------------+---------------------+---------------------
(0 rows)

-- Rows per model in retrograde_summary_embeddings_1536d (embedding type vector(1536)).
SELECT model, count(*) AS rows, count(DISTINCT summary_id) AS distinct_summary_ids, min(created_at) AS earliest_created_at, max(created_at) AS latest_created_at
FROM public.retrograde_summary_embeddings_1536d GROUP BY model ORDER BY model;
 model | rows | distinct_summary_ids | earliest_created_at | latest_created_at 
-------+------+----------------------+---------------------+-------------------
(0 rows)

-- Two generations in retrograde_summary_embeddings_1536d: rows grouped by registry family (entry key and remote_path are one model).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.summary_id AS item_id, e.model,
           coalesce(r.family, e.model) AS family,
           e.embedding::text AS vec
    FROM public.retrograde_summary_embeddings_1536d e LEFT JOIN registry r ON r.alias = e.model
),
per_item AS (
    SELECT family, item_id, count(*) AS n,
           count(DISTINCT vec) AS distinct_vectors
    FROM tagged GROUP BY family, item_id
)
SELECT p.family,
       (SELECT string_agg(DISTINCT t2.model, ', ') FROM tagged t2
        WHERE t2.family = p.family) AS model_names,
       count(*) AS summary_ids,
       count(*) FILTER (WHERE n > 1) AS summary_ids_with_multiple_rows,
       count(*) FILTER (WHERE distinct_vectors > 1) AS summary_ids_whose_vectors_differ
FROM per_item p GROUP BY p.family ORDER BY p.family;
 family | model_names | summary_ids | summary_ids_with_multiple_rows | summary_ids_whose_vectors_differ 
--------+-------------+-------------+--------------------------------+----------------------------------
(0 rows)

-- Cosine distance between the two generations in retrograde_summary_embeddings_1536d (pairs only; no rows means one generation).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.summary_id AS item_id, e.model, e.embedding,
           coalesce(r.family, e.model) AS family
    FROM public.retrograde_summary_embeddings_1536d e LEFT JOIN registry r ON r.alias = e.model
)
SELECT a.family, a.model AS model_a, b.model AS model_b,
       count(*) AS pairs,
       round(min(a.embedding <=> b.embedding)::numeric, 6) AS min_cosine_distance,
       round(avg(a.embedding <=> b.embedding)::numeric, 6) AS avg_cosine_distance,
       round(max(a.embedding <=> b.embedding)::numeric, 6) AS max_cosine_distance
FROM tagged a JOIN tagged b
  ON a.item_id = b.item_id AND a.family = b.family AND a.model < b.model
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
 family | model_a | model_b | pairs | min_cosine_distance | avg_cosine_distance | max_cosine_distance 
--------+---------+---------+-------+---------------------+---------------------+---------------------
(0 rows)

-- Rows per model in retrograde_summary_embeddings_2560d (embedding type vector(2560)).
SELECT model, count(*) AS rows, count(DISTINCT summary_id) AS distinct_summary_ids, min(created_at) AS earliest_created_at, max(created_at) AS latest_created_at
FROM public.retrograde_summary_embeddings_2560d GROUP BY model ORDER BY model;
 model | rows | distinct_summary_ids | earliest_created_at | latest_created_at 
-------+------+----------------------+---------------------+-------------------
(0 rows)

-- Two generations in retrograde_summary_embeddings_2560d: rows grouped by registry family (entry key and remote_path are one model).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.summary_id AS item_id, e.model,
           coalesce(r.family, e.model) AS family,
           e.embedding::text AS vec
    FROM public.retrograde_summary_embeddings_2560d e LEFT JOIN registry r ON r.alias = e.model
),
per_item AS (
    SELECT family, item_id, count(*) AS n,
           count(DISTINCT vec) AS distinct_vectors
    FROM tagged GROUP BY family, item_id
)
SELECT p.family,
       (SELECT string_agg(DISTINCT t2.model, ', ') FROM tagged t2
        WHERE t2.family = p.family) AS model_names,
       count(*) AS summary_ids,
       count(*) FILTER (WHERE n > 1) AS summary_ids_with_multiple_rows,
       count(*) FILTER (WHERE distinct_vectors > 1) AS summary_ids_whose_vectors_differ
FROM per_item p GROUP BY p.family ORDER BY p.family;
 family | model_names | summary_ids | summary_ids_with_multiple_rows | summary_ids_whose_vectors_differ 
--------+-------------+-------------+--------------------------------+----------------------------------
(0 rows)

-- Cosine distance between the two generations in retrograde_summary_embeddings_2560d (pairs only; no rows means one generation).
WITH registry(alias, family) AS (VALUES
        ('bge-large', 'bge-large'), ('BAAI/bge-large-en', 'bge-large'), ('e5-large', 'e5-large'), ('intfloat/e5-large-v2', 'e5-large'), ('bge-small-custom', 'bge-small-custom'), ('inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('infly/inf-retriever-v1-1.5b', 'inf-retriever-v1-1.5b'), ('Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen/Octen-Embedding-0.6B', 'Octen-Embedding-0.6B'), ('Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen/Octen-Embedding-4B', 'Octen-Embedding-4B'), ('Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen/Octen-Embedding-4B-INT8', 'Octen-Embedding-4B-INT8'), ('Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen/Octen-Embedding-8B', 'Octen-Embedding-8B'), ('Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8'), ('Octen/Octen-Embedding-8B-INT8', 'Octen-Embedding-8B-INT8')
),
tagged AS (
    SELECT e.summary_id AS item_id, e.model, e.embedding,
           coalesce(r.family, e.model) AS family
    FROM public.retrograde_summary_embeddings_2560d e LEFT JOIN registry r ON r.alias = e.model
)
SELECT a.family, a.model AS model_a, b.model AS model_b,
       count(*) AS pairs,
       round(min(a.embedding <=> b.embedding)::numeric, 6) AS min_cosine_distance,
       round(avg(a.embedding <=> b.embedding)::numeric, 6) AS avg_cosine_distance,
       round(max(a.embedding <=> b.embedding)::numeric, 6) AS max_cosine_distance
FROM tagged a JOIN tagged b
  ON a.item_id = b.item_id AND a.family = b.family AND a.model < b.model
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
 family | model_a | model_b | pairs | min_cosine_distance | avg_cosine_distance | max_cosine_distance 
--------+---------+---------+-------+---------------------+---------------------+---------------------
(0 rows)

```

</details>

<details><summary>Generator (reads table shapes read-only, writes one SQL file per database)</summary>

```python
"""Generate one read-only inventory SQL file per database (#812, order 812-S1).

Table shapes are read through a read-only psql session; the generated SQL is
then run with ``psql -X -a`` so the verification file carries every statement
next to its output.
"""

import os
import subprocess
import sys

OUT = os.path.dirname(os.path.abspath(__file__))
DBS = sys.argv[1:]
PATTERN = (
    "^(chunk_embeddings|retrograde_summary_embeddings|"
    "character_experience_embeddings)_[0-9]+d$"
)
ID_COLUMN = {
    "chunk_embeddings": "chunk_id",
    "retrograde_summary_embeddings": "summary_id",
    "character_experience_embeddings": "experience_id",
}
# Aliases from the [memnon.models] registry in nexus.toml: each entry's key
# and its remote_path name the same model family.
REGISTRY = [
    ("bge-large", "BAAI/bge-large-en"),
    ("e5-large", "intfloat/e5-large-v2"),
    ("bge-small-custom", None),
    ("inf-retriever-v1-1.5b", "infly/inf-retriever-v1-1.5b"),
    ("Octen-Embedding-0.6B", "Octen/Octen-Embedding-0.6B"),
    ("Octen-Embedding-4B", "Octen/Octen-Embedding-4B"),
    ("Octen-Embedding-4B-INT8", "Octen/Octen-Embedding-4B-INT8"),
    ("Octen-Embedding-8B", "Octen/Octen-Embedding-8B"),
    ("Octen-Embedding-8B-INT8", "Octen/Octen-Embedding-8B-INT8"),
]


def registry_values() -> str:
    rows = []
    for key, remote in REGISTRY:
        rows.append(f"('{key}', '{key}')")
        if remote:
            rows.append(f"('{remote}', '{key}')")
    return ", ".join(rows)


def shapes(db: str) -> list[tuple[str, bool, str]]:
    env = dict(os.environ, PGOPTIONS="-c default_transaction_read_only=on")
    sql = f"""
    SELECT c.relname,
           EXISTS (SELECT 1 FROM pg_attribute a
                   WHERE a.attrelid = c.oid AND a.attname = 'created_at'
                     AND NOT a.attisdropped),
           format_type(e.atttypid, e.atttypmod)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    JOIN pg_attribute e ON e.attrelid = c.oid AND e.attname = 'embedding'
    WHERE c.relkind IN ('r', 'p') AND c.relname ~ '{PATTERN}'
    ORDER BY 1
    """
    out = subprocess.run(
        [
            "psql",
            "-X",
            "-d",
            db,
            "-AtF",
            "|",
            "-c",
            "SHOW default_transaction_read_only",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout
    lines = out.splitlines()
    if lines[0] != "on":
        raise RuntimeError(f"{db}: shape session is not read-only: {lines[0]!r}")
    print(f"{db}: shape session default_transaction_read_only = {lines[0]}")
    result = []
    for line in lines[1:]:
        name, has_created, etype = line.split("|")
        result.append((name, has_created == "t", etype))
    return result


def build(db: str) -> str:
    tables = shapes(db)
    parts = [
        "-- First statement of the session: the session is read-only.",
        "SHOW default_transaction_read_only;",
        "SELECT current_database() AS database, now() AS snapshot_at;",
    ]
    if not tables:
        parts.append(
            "SELECT count(*) AS embedding_tables FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE c.relkind IN ('r','p') AND c.relname ~ '{PATTERN}';"
        )
        return "\n".join(parts) + "\n"
    unions = "\n    UNION ALL ".join(
        f"SELECT '{t}' AS table_name, (SELECT count(*) FROM public.{t}) AS row_count"
        for t, _, _ in tables
    )
    parts.append(
        "-- Tables, row counts and total relation size.\n"
        "SELECT t.table_name, t.row_count,\n"
        "       pg_total_relation_size(('public.' || t.table_name)::regclass)"
        " AS total_bytes,\n"
        "       pg_size_pretty(pg_total_relation_size(('public.' ||"
        " t.table_name)::regclass)) AS total_size\n"
        f"FROM (\n    {unions}\n) t\nORDER BY 1;"
    )
    for t, has_created, etype in tables:
        prefix = t.rsplit("_", 1)[0]
        idcol = ID_COLUMN[prefix]
        created = (
            "min(created_at) AS earliest_created_at, "
            "max(created_at) AS latest_created_at"
            if has_created
            else "NULL AS earliest_created_at, NULL AS latest_created_at"
        )
        parts.append(
            f"-- Rows per model in {t} (embedding type {etype}).\n"
            f"SELECT model, count(*) AS rows, count(DISTINCT {idcol}) AS "
            f"distinct_{idcol}s, {created}\n"
            f"FROM public.{t} GROUP BY model ORDER BY model;"
        )
        parts.append(
            f"-- Two generations in {t}: rows grouped by registry family "
            "(entry key and remote_path are one model).\n"
            "WITH registry(alias, family) AS (VALUES\n        "
            f"{registry_values()}\n),\n"
            "tagged AS (\n"
            f"    SELECT e.{idcol} AS item_id, e.model,\n"
            "           coalesce(r.family, e.model) AS family,\n"
            "           e.embedding::text AS vec\n"
            f"    FROM public.{t} e LEFT JOIN registry r ON r.alias = e.model\n"
            "),\n"
            "per_item AS (\n"
            "    SELECT family, item_id, count(*) AS n,\n"
            "           count(DISTINCT vec) AS distinct_vectors\n"
            "    FROM tagged GROUP BY family, item_id\n"
            ")\n"
            "SELECT p.family,\n"
            "       (SELECT string_agg(DISTINCT t2.model, ', ') FROM tagged t2\n"
            "        WHERE t2.family = p.family) AS model_names,\n"
            f"       count(*) AS {idcol}s,\n"
            f"       count(*) FILTER (WHERE n > 1) AS {idcol}s_with_multiple_rows,\n"
            "       count(*) FILTER (WHERE distinct_vectors > 1)"
            f" AS {idcol}s_whose_vectors_differ\n"
            "FROM per_item p GROUP BY p.family ORDER BY p.family;"
        )
        if etype.startswith("vector("):
            parts.append(
                f"-- Cosine distance between the two generations in {t}"
                " (pairs only; no rows means one generation).\n"
                "WITH registry(alias, family) AS (VALUES\n        "
                f"{registry_values()}\n),\n"
                "tagged AS (\n"
                f"    SELECT e.{idcol} AS item_id, e.model, e.embedding,\n"
                "           coalesce(r.family, e.model) AS family\n"
                f"    FROM public.{t} e LEFT JOIN registry r ON r.alias = e.model\n"
                ")\n"
                "SELECT a.family, a.model AS model_a, b.model AS model_b,\n"
                "       count(*) AS pairs,\n"
                "       round(min(a.embedding <=> b.embedding)::numeric, 6)"
                " AS min_cosine_distance,\n"
                "       round(avg(a.embedding <=> b.embedding)::numeric, 6)"
                " AS avg_cosine_distance,\n"
                "       round(max(a.embedding <=> b.embedding)::numeric, 6)"
                " AS max_cosine_distance\n"
                "FROM tagged a JOIN tagged b\n"
                "  ON a.item_id = b.item_id AND a.family = b.family"
                " AND a.model < b.model\n"
                "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;"
            )
    return "\n\n".join(parts) + "\n"


for db in DBS:
    with open(os.path.join(OUT, f"inventory_{db}.sql"), "w") as handle:
        handle.write(build(db))
    print(db, "ok")
```

</details>
