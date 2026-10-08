# 778-S1b Verification: Loud NULL-Base Failure, Base-Edit Guard and Fixture Ordering

Issue #778, work order 778-S1b, branch `claude/778-null-base-guard`, cut from
`origin/main` at `364fef4b`. Review round 1 merged `origin/main` at
`b0da93ea` into the branch (`c3fe5d70`); `origin/main` is still `b0da93ea`.
Decisions 778-Q8 (A) and 778-Q3 (B) from the "Decisions Recorded" comment on
#778. No `save_NN`, `NEXUS_template` or `ref_codex_bakeoff_2026_07` was
written; every write went to a disposable clone (`qa640_*`, `qa676_*`,
`qa762_*`, `qa_wt724_*`, `nexus_test_*`). No paid call, no gateway lane.

Every tail in this file names the commit it ran on and the state of the
working tree. "Clean" means that the log printed `uncommitted: 0 files` (or
`uncommitted before plant: 0 files`), counted with `git status --short`.
Where a log records neither, the file says so and gives the commit that was
`HEAD` when the log was written (from the log's modification time and the
commit times).

## Resumed on 2026-10-07

The coordinator stopped the first builder at 12:50 CDT for machine load. The
resumed builder found one commit and seven modified files.

| Commit or file | Order items | State found | Left unfinished |
| --- | --- | --- | --- |
| `36cc28ea` (migration 144, `docs/database.md`) | 1, 2, 3 | Complete; re-read against the order (comments byte-equal to the order, statement order, lock and rerun paragraphs). | Nothing. |
| `tests/pg_fixtures.py` (uncommitted) | 4 | `DEFAULT_BASE_TIMESTAMP`, `set_story_base`, `seed_story_base`, `seed_protagonist`/`seed_story_clock` rewrites, prose fixes. | Committed as `1b5473d9`. |
| `tests/test_pg_disposable_target.py` (uncommitted) | 4 | `seed_story_base` registered in `SEED_CALLS`. | Committed as `1b5473d9`. |
| `tests/test_interactions_pg.py`, `tests/test_orrery/test_retrograde_retrieval_pg.py`, `tests/test_lore/conftest.py` (uncommitted) | 5 | Known fixes applied. | Committed as `1b5473d9`. |
| `tests/test_connection_lifecycle.py` (uncommitted) | 5 | `set_story_base(cur, timestamp)` added at `:102`. | Discarded: the gate failed it (see below). |
| `tests/test_world_clock_contract_pg.py` (uncommitted) | Tests | Five new tests written. | Docstring reflowed to 88 columns; committed as `5c5b4615`. |
| (nothing) | 5, 6 (rest of the gate) | Not started. | Done in `58cef582`. |
| (nothing) | 7, 8, evidence, proofs | Not started. | Done in this file and the AGENTS.md commit. |

## Review Rounds

Astra (Codex, GPT-6) reviewed `f744f30c` and returned CHANGES_REQUIRED.

| Commit | Round | Change |
| --- | --- | --- |
| `c3fe5d70` | 1 | Merge of `origin/main` (`b0da93ea`). |
| `9343e8b8` | 1 | `AGENTS.md` `verified_commit` moves to the new merge base `b0da93ea`. |
| `7e32be25` | 1 | `test_null_base_rejects_later_writes` also makes the flashback primary under the planted NULL base (an UPDATE of `world_layer` only) and asserts `Story clock has no base` and unchanged clocks, layers and row count (Astra P2 #2). |
| the commit that adds this row | 2 | This file and the PR body only: item 8 corrected (Astra P2 #1); every tail attributed to its commit, and the tails that could not be attributed rerun at `7e32be25` (Astra P3). |

Round 2 changes no code, migration or test, so each rerun at `7e32be25`
below also holds for the round-2 head. Round 2 ran every PostgreSQL session
after a bounded wait for a one-minute load below 24 (the plant A run waited
11 minutes); the scripts are in `scratchpad/1114-astra-fix-2/`.

## What Is Wrong at `364fef4b` (Checked)

- `migrations/140_world_clock_primary_layer.sql:106-111` stamps from
  `COALESCE((SELECT base_timestamp ...), now())`; its comment documents the
  fallback (`:147-148`) and 140 keeps it by name (`:62-64`). On
  `NEXUS_template`, `pg_get_functiondef('public.refresh_world_time_from_chunk()')`
  still carries `COALESCE(` ... `now()` (read-only, lines 22-24 of the
  definition).
- `global_variables` has no user trigger on `NEXUS_template` or any slot (read-only
  `pg_trigger ... NOT tgisinternal` = 0 on all six databases, below).
- `migrations/118_world_clock_identity.sql:23-24`: the base comment says nothing
  about when it may change.
- Production order: `nexus/api/new_story_db_mapper.py:609-619` sets the base in
  the transition before the character rows and before the Retrograde hook
  (`:680`), which writes the prologue metadata at
  `nexus/agents/orrery/retrograde_persistence.py:2575`.
- Test harness at `origin/main`: `tests/pg_fixtures.py:637-643` sets the base
  under existing chunks and re-stamps them; `:806-810` writes the base by its
  own SQL.

## Fleet Survey (Read-Only, 2026-10-07)

`PGOPTIONS='-c default_transaction_read_only=on'`; columns: chunks, base set,
migration level, user triggers on `global_variables`. Read during the resumed
session (time not recorded):

```text
NEXUS_template 0||143|0
save_01 1425|t|143|0
save_02 1425|t|143|0
save_03 40|t|143|0
save_04 46|t|143|0
save_05 0|f|143|0
```

Read again at 23:22 CDT in round 2 (read-only SQL; no branch code is
involved):

```text
NEXUS_template 0||143|0
save_01 1425|true|143|0
save_02 1425|true|143|0
save_03 40|true|143|0
save_04 46|true|143|0
save_05 0|false|143|0
```

`NEXUS_template` has no `global_variables` row; `save_05` has a NULL base. No
database holds chunks under a NULL base, so 144's final refresh raises nowhere.

## Comments From a Migrated Clone

At `7e32be25`, clean, 15:24 CDT (round 1, `1114-astra-fix/template-proof.sh`):
`createdb -T NEXUS_template qa640_778s1b_template`, then
`PYTHONPATH=$PWD $PY scripts/migrate.py --dbname qa640_778s1b_template`
(`Applied: 144_world_clock_base_contract`, `level 144`), then
`obj_description` and `col_description` into `comments.txt`:

```text
FUNCTION refresh_world_time_from_chunk(): Recomputes chunk_metadata.world_time for every chunk as global_variables.base_timestamp plus the running sum, in chunk_id order, of the time_delta of primary-layer chunks (NULL counts as zero), so a chunk of any other layer, or with a NULL world_layer, carries the mainline clock at its position. Raises when chunk_metadata holds a row and base_timestamp is NULL or its row is missing; there is no wall-clock fallback. Raises when the bootstrap chunk (the lowest chunk_id) has a time_delta other than zero or NULL, because base_timestamp is the clock at its end. Writes only rows whose world_time changes; a world_time written by the inserter is overwritten.
FUNCTION refuse_base_timestamp_change(): Row trigger function for trg_global_variables_base_timestamp_fixed: raises when an UPDATE changes global_variables.base_timestamp while chunk_metadata holds any row, because refresh_world_time_from_chunk() would re-date chunk metadata while stored event times keep the old clock.
TRIGGER trg_global_variables_base_timestamp_fixed: Fixes base_timestamp at genesis: BEFORE UPDATE, for each row whose base_timestamp IS DISTINCT FROM its old value (NULL included), it calls refuse_base_timestamp_change(), which raises once chunk_metadata holds a row. An update that keeps the same value passes; a DELETE or INSERT of the row does not fire it.
COLUMN global_variables.base_timestamp: Story clock at the end of the bootstrap chunk, stored as timestamptz whose UTC face is the story clock face. It is set before the first chunk: while it is NULL, an INSERT into chunk_metadata, or an UPDATE of its time_delta or world_layer, raises when chunk_metadata then holds a row; once chunk_metadata holds a row, it cannot change.
```

`cmp` against the listing this file carried before (made at 14:11 with
`HEAD` at `58cef582`; tree not recorded): identical. A script
(`scratchpad/1114-astra-fix-2/cmp_comments.py`, run at `7e32be25`, clean)
compared each line with the migration's `COMMENT ON` literals (with `''`
unescaped): `4 4 [True, True, True, True]`. The earlier run also compared
them with the order's item 2 text: equal. `$PY scripts/check_migration_comments.py`
at `7e32be25`, clean (round 2): `OK: every object created after migration
129 has a comment.`

## Template-Clone Proof

On the same clone, at `7e32be25`, clean. The log (`template-proof.log`,
round 1) without the three import-time deprecation warnings and the progress
line; the script runs under `set -x`:

```text
uptime: 15:24  up  2:04, 5 users, load averages: 23.84 23.12 22.12
commit: 7e32be25; uncommitted: 0 files
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/template-proof.sh:6> createdb -T NEXUS_template qa640_778s1b_template
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/template-proof.sh:7> PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/778-null-base-guard nice -n 15 /Users/pythagor/nexus/.venv/bin/python scripts/migrate.py --dbname qa640_778s1b_template
INFO Migrating qa640_778s1b_template...
INFO   Applied: 144_world_clock_base_contract
INFO 
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_778s1b_template: 141 migration stamps; level 144
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/template-proof.sh:8> psql -At -d qa640_778s1b_template -c 'SELECT '\''FUNCTION refresh_world_time_from_chunk(): '\'' || obj_description('\''public.refresh_world_time_from_chunk()'\''::regprocedure, '\''pg_proc'\'') UNION ALL SELECT '\''FUNCTION refuse_base_timestamp_change(): '\'' || obj_description('\''public.refuse_base_timestamp_change()'\''::regprocedure, '\''pg_proc'\'') UNION ALL SELECT '\''TRIGGER trg_global_variables_base_timestamp_fixed: '\'' || obj_description(t.oid, '\''pg_trigger'\'') FROM pg_trigger t WHERE t.tgname = '\''trg_global_variables_base_timestamp_fixed'\'' UNION ALL SELECT '\''COLUMN global_variables.base_timestamp: '\'' || col_description('\''public.global_variables'\''::regclass, (SELECT attnum FROM pg_attribute WHERE attrelid = '\''public.global_variables'\''::regclass AND attname = '\''base_timestamp'\''))'
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/template-proof.sh:9> env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT 'NEXUS_TEST_TEMPLATE_DB=qa640_778s1b_template' 'NEXUS_RUN_POSTGRES=1' 'PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/778-null-base-guard' nice -n 15 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_need_clock_anchor_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 19 targets: postgres, qa640_* x18
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
18 passed in 10.34s
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/template-proof.sh:10> dropdb qa640_778s1b_template
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/template-proof.sh:11> set +x
```

This replaces the 14:11 run (`HEAD` at `58cef582`, tree not recorded;
`18 passed in 12.57s`).

## Zero-Change Proof

For N in 02, 03, 04: `createdb -T template0 qa640_778s1b_N`;
`pg_dump --format=custom save_N`; `pg_restore --exit-on-error --no-owner
--no-acl`; `SELECT chunk_id, world_layer, time_delta, world_time FROM
chunk_metadata ORDER BY chunk_id` before and after
`PYTHONPATH=$PWD $PY scripts/migrate.py --dbname qa640_778s1b_N`; `cmp`; drop.
The transcripts below ran at `7e32be25`, clean, at 15:25 CDT (round 1,
`1114-astra-fix/zero-change.sh`, under `set -x`; `cmp` printed nothing, so
`echo IDENTICAL` ran). They replace the 14:12 runs (`HEAD` at `58cef582`,
tree not recorded; the same row counts and `IDENTICAL` for all three).
`migrations/` and `scripts/migrate.py` do not differ between `58cef582` and
`7e32be25`.

`zero-change-02.log`:

```text
uptime: 15:25  up  2:04, 5 users, load averages: 21.22 22.55 21.94
commit: 7e32be25; uncommitted: 0 files
== save_02 -> qa640_778s1b_02
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:9> createdb -T template0 qa640_778s1b_02
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:10> nice -n 15 pg_dump '--format=custom' -f /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_02.dump save_02
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:11> nice -n 15 pg_restore --exit-on-error --no-owner --no-acl -d qa640_778s1b_02 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_02.dump
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:12> psql -At -d qa640_778s1b_02 -c 'SELECT chunk_id, world_layer, time_delta, world_time FROM chunk_metadata ORDER BY chunk_id'
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:13> PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/778-null-base-guard nice -n 15 /Users/pythagor/nexus/.venv/bin/python scripts/migrate.py --dbname qa640_778s1b_02
INFO Migrating qa640_778s1b_02...
INFO   Applied: 144_world_clock_base_contract
INFO 
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_778s1b_02: 141 migration stamps; level 144
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:14> psql -At -d qa640_778s1b_02 -c 'SELECT chunk_id, world_layer, time_delta, world_time FROM chunk_metadata ORDER BY chunk_id'
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:15> wc -l
    1425
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:16> cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zc_02_before.txt /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zc_02_after.txt
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:16> echo IDENTICAL
IDENTICAL
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:17> psql -At -d qa640_778s1b_02 -c 'SELECT max(version) FROM schema_migrations'
144
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:18> dropdb qa640_778s1b_02
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:19> rm -f /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_02.dump
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:20> set +x
```

`zero-change-03.log`:

```text
uptime: 15:25  up  2:05, 5 users, load averages: 18.91 21.91 21.72
commit: 7e32be25; uncommitted: 0 files
== save_03 -> qa640_778s1b_03
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:9> createdb -T template0 qa640_778s1b_03
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:10> nice -n 15 pg_dump '--format=custom' -f /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_03.dump save_03
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:11> nice -n 15 pg_restore --exit-on-error --no-owner --no-acl -d qa640_778s1b_03 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_03.dump
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:12> psql -At -d qa640_778s1b_03 -c 'SELECT chunk_id, world_layer, time_delta, world_time FROM chunk_metadata ORDER BY chunk_id'
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:13> PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/778-null-base-guard nice -n 15 /Users/pythagor/nexus/.venv/bin/python scripts/migrate.py --dbname qa640_778s1b_03
INFO Migrating qa640_778s1b_03...
INFO   Applied: 144_world_clock_base_contract
INFO 
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_778s1b_03: 141 migration stamps; level 144
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:14> psql -At -d qa640_778s1b_03 -c 'SELECT chunk_id, world_layer, time_delta, world_time FROM chunk_metadata ORDER BY chunk_id'
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:15> wc -l
      40
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:16> cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zc_03_before.txt /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zc_03_after.txt
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:16> echo IDENTICAL
IDENTICAL
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:17> psql -At -d qa640_778s1b_03 -c 'SELECT max(version) FROM schema_migrations'
144
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:18> dropdb qa640_778s1b_03
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:19> rm -f /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_03.dump
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:20> set +x
```

`zero-change-04.log`:

```text
uptime: 15:25  up  2:05, 5 users, load averages: 18.91 21.91 21.72
commit: 7e32be25; uncommitted: 0 files
== save_04 -> qa640_778s1b_04
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:9> createdb -T template0 qa640_778s1b_04
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:10> nice -n 15 pg_dump '--format=custom' -f /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_04.dump save_04
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:11> nice -n 15 pg_restore --exit-on-error --no-owner --no-acl -d qa640_778s1b_04 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_04.dump
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:12> psql -At -d qa640_778s1b_04 -c 'SELECT chunk_id, world_layer, time_delta, world_time FROM chunk_metadata ORDER BY chunk_id'
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:13> PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/778-null-base-guard nice -n 15 /Users/pythagor/nexus/.venv/bin/python scripts/migrate.py --dbname qa640_778s1b_04
INFO Migrating qa640_778s1b_04...
INFO   Applied: 144_world_clock_base_contract
INFO 
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_778s1b_04: 141 migration stamps; level 144
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:14> psql -At -d qa640_778s1b_04 -c 'SELECT chunk_id, world_layer, time_delta, world_time FROM chunk_metadata ORDER BY chunk_id'
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:15> wc -l
      46
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:16> cmp /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zc_04_before.txt /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zc_04_after.txt
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:16> echo IDENTICAL
IDENTICAL
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:17> psql -At -d qa640_778s1b_04 -c 'SELECT max(version) FROM schema_migrations'
144
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:18> dropdb qa640_778s1b_04
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:19> rm -f /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/save_04.dump
+/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/1114-astra-fix/zero-change.sh:20> set +x
```

No `qa640_778s1b_*` database remains (`psql -Atl`).

## Red Run

Three scratch copies of 144 (`144.plantA.sql`, `144.plantB.sql`,
`144.plantC.sql`, copied unchanged from `778-S1b-resume/` to
`1114-astra-fix-2/`). For each, `red3.sh` waited until the one-minute load
was below 24, recorded `uptime`, the commit and `git status --short`, copied
the plant over `migrations/144_world_clock_base_contract.sql`, ran the five
new tests with the command shown, and restored the file with `git checkout`;
the last line counts uncommitted files afterwards. All three ran in round 2
at `7e32be25` with a clean tree (the plant aside), under `-rfEp` so the short
summary names every failure, error and pass. Each block is the log's first
three lines, then the log from the `secret-store guard` line to the end,
verbatim (`COLUMNS=200` sets the separator width and cuts long messages with
`...`). `7 deselected` is the other seven tests of the file.

These runs replace the runs at 14:45 (`HEAD` at `00dba586`; the logs
recorded the plant but not the tree) and at 13:38. All three rounds gave the
same counts.

Plant A (140's function body, guard kept):

```text
uptime: 23:36  up 10:16, 5 users, load averages: 22.95 32.20 31.75
commit: 7e32be25; uncommitted before plant: 0 files
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT COLUMNS=200 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rfEp -p tests.dbname_audit tests/test_world_clock_contract_pg.py -k 'test_null_base_rejects_first_chunk or test_null_base_rejects_later_writes or test_base_timestamp_fixed_once_chunks_exist or test_base_timestamp_free_before_chunks or test_migration_144_refuses_null_base_and_reruns'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_clock_* x5
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
======================================================================================= short test summary info ========================================================================================
FAILED tests/test_world_clock_contract_pg.py::test_null_base_rejects_first_chunk - Failed: DID NOT RAISE <class 'psycopg2.errors.RaiseException'>
FAILED tests/test_world_clock_contract_pg.py::test_null_base_rejects_later_writes - Failed: DID NOT RAISE <class 'psycopg2.errors.RaiseException'>
FAILED tests/test_world_clock_contract_pg.py::test_migration_144_refuses_null_base_and_reruns - assert (1, 0) == (0, 1)
PASSED tests/test_world_clock_contract_pg.py::test_base_timestamp_fixed_once_chunks_exist
PASSED tests/test_world_clock_contract_pg.py::test_base_timestamp_free_before_chunks
3 failed, 2 passed, 7 deselected in 9.77s
exit=1; plant reverted: 0 uncommitted files
```

Plant B (no `CREATE TRIGGER` and no `COMMENT ON TRIGGER`):

```text
uptime: 23:37  up 10:17, 5 users, load averages: 21.96 30.76 31.25
commit: 7e32be25; uncommitted before plant: 0 files
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT COLUMNS=200 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rfEp -p tests.dbname_audit tests/test_world_clock_contract_pg.py -k 'test_null_base_rejects_first_chunk or test_null_base_rejects_later_writes or test_base_timestamp_fixed_once_chunks_exist or test_base_timestamp_free_before_chunks or test_migration_144_refuses_null_base_and_reruns'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_clock_* x5
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
======================================================================================= short test summary info ========================================================================================
FAILED tests/test_world_clock_contract_pg.py::test_null_base_rejects_later_writes - psycopg2.errors.UndefinedObject: trigger "trg_global_variables_base_timestamp_fixed" for table "global_variables"...
FAILED tests/test_world_clock_contract_pg.py::test_base_timestamp_fixed_once_chunks_exist - Failed: DID NOT RAISE <class 'psycopg2.errors.RaiseException'>
FAILED tests/test_world_clock_contract_pg.py::test_migration_144_refuses_null_base_and_reruns - psycopg2.errors.UndefinedObject: trigger "trg_global_variables_base_timestamp_fixed" for table "globa...
PASSED tests/test_world_clock_contract_pg.py::test_null_base_rejects_first_chunk
PASSED tests/test_world_clock_contract_pg.py::test_base_timestamp_free_before_chunks
3 failed, 2 passed, 7 deselected in 10.91s
exit=1; plant reverted: 0 uncommitted files
```

Plant C (`refuse_base_timestamp_change()` always raises):

```text
uptime: 23:37  up 10:17, 5 users, load averages: 20.59 30.03 30.98
commit: 7e32be25; uncommitted before plant: 0 files
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT COLUMNS=200 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rfEp -p tests.dbname_audit tests/test_world_clock_contract_pg.py -k 'test_null_base_rejects_first_chunk or test_null_base_rejects_later_writes or test_base_timestamp_fixed_once_chunks_exist or test_base_timestamp_free_before_chunks or test_migration_144_refuses_null_base_and_reruns'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 6 targets: postgres, qa640_clock_* x5
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
======================================================================================= short test summary info ========================================================================================
FAILED tests/test_world_clock_contract_pg.py::test_base_timestamp_free_before_chunks - psycopg2.errors.RaiseException: global_variables.base_timestamp is fixed once chunk_metadata holds a row: refu...
FAILED tests/test_world_clock_contract_pg.py::test_migration_144_refuses_null_base_and_reruns - psycopg2.errors.RaiseException: global_variables.base_timestamp is fixed once chunk_metadata holds a ...
ERROR tests/test_world_clock_contract_pg.py::test_null_base_rejects_later_writes - psycopg2.errors.RaiseException: global_variables.base_timestamp is fixed once chunk_metadata holds a row: refusing...
ERROR tests/test_world_clock_contract_pg.py::test_base_timestamp_fixed_once_chunks_exist - psycopg2.errors.RaiseException: global_variables.base_timestamp is fixed once chunk_metadata holds a row: ...
PASSED tests/test_world_clock_contract_pg.py::test_null_base_rejects_first_chunk
2 failed, 1 passed, 7 deselected, 2 errors in 9.47s
exit=1; plant reverted: 0 uncommitted files
```

Under Plant B, tests 2 and 5 fail on the missing trigger in `_set_guard`,
which runs in the test body (not in a fixture), so pytest reports FAILED
rather than a setup ERROR; test 3 fails on its own assertion. Under Plant C,
tests 2 and 3 error in the `clock_db` fixture's `seed_protagonist`, and tests 4
and 5 fail in their own base seed.

Test 4 (`test_base_timestamp_free_before_chunks`) passes under Plants A and B
(the `PASSED` lines above).

Plant D (`144.plantD.sql`, added in round 1 for the layer-only arm of
`7e32be25`): the migration ends by recreating
`trg_chunk_metadata_refresh_world_time` as `AFTER INSERT OR UPDATE OF
time_delta`, so an UPDATE of `world_layer` alone no longer runs the refresh.
`test_null_base_rejects_later_writes` must then fail at its new arm, after
its INSERT and `time_delta` arms pass. The traceback in the log points at
`tests/test_world_clock_contract_pg.py:430`, the `pytest.raises` of that
arm. Rerun in round 2 at `7e32be25`, clean (round 1 ran it on `9343e8b8`
with the test edit of `7e32be25` uncommitted):

```text
uptime: 23:17  up  9:57, 5 users, load averages: 21.57 25.45 22.37
commit: 7e32be25; uncommitted before plant: 0 files
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT COLUMNS=200 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rfEp -p tests.dbname_audit tests/test_world_clock_contract_pg.py -k test_null_base_rejects_later_writes
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: postgres, qa640_clock_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
======================================================================================= short test summary info ========================================================================================
FAILED tests/test_world_clock_contract_pg.py::test_null_base_rejects_later_writes - Failed: DID NOT RAISE <class 'psycopg2.errors.RaiseException'>
1 failed, 11 deselected in 2.35s
exit=1; plant reverted: 0 uncommitted files
```

## Item 8: Production Writers

Corrected in review round 2. The first answer said that every
chunk-metadata writer writes into a story that already has a base. That is
false: three writers can import into an empty slot without the wizard and
without reading the base. The writers below were found with
`grep -rnE "INSERT INTO (public\.)?chunk_metadata|UPDATE (public\.)?chunk_metadata|insert_chunk_metadata_sync|ChunkMetadata\(" --include='*.py' nexus scripts`
and read at `7e32be25`. Review round 3 widened the search to table names
held in a constant and interpolated by an f-string:
`grep -rnE "(INSERT INTO|UPDATE) +(public\.)?(chunk_metadata|\{CHUNK_METADATA_TABLE\})|insert_chunk_metadata_sync|ChunkMetadata\(" --include='*.py' nexus scripts`,
plus `grep -rnE "(INSERT INTO|UPDATE) +\{" --include='*.py' nexus scripts`
for any other interpolated target. The first adds
`scripts/map_builder_legacy.py:1358,1373` and
`scripts/process_characters.py:858,875` (listed under Other Writers). Every
other interpolated target the second finds is an embedding, asset, job,
place or character table, not `chunk_metadata`. Round 3 read these at
`bbf46429`; it changes only this file and the PR body, and the production
files it cites are identical at `7e32be25`.

What fires: `trg_chunk_metadata_refresh_world_time` runs
`refresh_world_time_from_chunk()` once per statement after an INSERT, or
after an UPDATE whose SET list names `time_delta` or `world_layer`
(`migrations/140_world_clock_primary_layer.sql:140-143`). Under 144 the
function raises `Story clock has no base` when `chunk_metadata` then holds a
row and the base is NULL or its row is missing, so the statement and its
transaction fail.

### Base Writer

`global_variables.base_timestamp` has one production writer:
`nexus/api/new_story_db_mapper.py:612-619`, inside the wizard-to-narrative
transition, before the character rows and before the Retrograde hook
(`:680`) writes the prologue metadata
(`nexus/agents/orrery/retrograde_persistence.py:2575`). That base write has
no chunk-empty precondition: `perform_transition` deletes the entity tables
(`:572-585`) but never `chunk_metadata` or `narrative_chunks`, so it writes
the base before any chunk only because the caller gives it a fresh slot or
one cleared by `reset_setup` (`nexus/api/new_story_flow.py:704-740`, which
recreates the slot from `NEXUS_template`). `start_setup` reuses an existing
database without clearing chunks, and `scripts/new_story_setup.py --mode
clone` leaves a data-bearing slot that `_post_clone_cleanup`
(`scripts/new_story_setup.py:528-532`) marks `new_story = TRUE`. A
transition over a slot that holds chunks now raises `global_variables.base_timestamp
is fixed once chunk_metadata holds a row` in that `UPDATE` instead of
silently re-basing the stored chunks. So the answer is no only on the
condition that the caller resets the slot first, which the transition does
not check. The guard is unchanged; this is reported only. The other
`base_timestamp` writes in `nexus/` (`nexus/api/new_story_cache.py:1190`,
`:1753`) target `assets.new_story_creator`, the wizard cache, not
`global_variables`. `scripts/qa_shift/` only reads the base
(`scripts/qa_shift/world_clock.py:30`).

### Chunk-Metadata Writers That Raise Loudly

- `nexus/api/commit_handler_sync.py:124,134` (`insert_chunk_metadata_sync`,
  called at `:578` in the turn commit). `commit_incubator_to_database_sync`
  rolls back and re-raises (`:887-890`). Its callers roll back and re-raise
  the error as HTTP 500 `Failed to commit narrative: Story clock has no base
  ...` (`nexus/api/narrative.py:763-769`, `:1415-1417`), so the turn fails
  loudly. It runs only after the transition has set the base.
- `nexus/agents/orrery/retrograde_persistence.py:2575`
  (`_ensure_prologue_metadata`), inside the transition's transaction after
  the base write. `perform_transition` re-raises
  (`nexus/api/new_story_db_mapper.py:684-690`).

### Chunk-Metadata Writers That Swallow the Failure

Each of these can reach an empty slot whose base is NULL, because none runs
the wizard or reads the base. The writer probe below ran the first three.

- `scripts/simple_update.py`: `create_chunk` inserts the `narrative_chunks`
  row and the metadata row (`:933`) in one transaction. The raise is caught
  at `:941-943`, logged, and `None` is returned. `process_file` counts an
  error, and `main` prints `Chunks created: 0` and `Errors: N` and returns 0
  (`:1187`), so the exit status is 0. `--fix-metadata`
  (`ensure_all_chunks_have_metadata`, insert at `:415`) catches at
  `:443-445` and returns False (read, not probed).
- `scripts/update_raw_text.py`: `create_new_chunk` (insert at `:733`)
  catches at `:758-760` and returns `None`. `process_files` counts that as
  `chunks_not_found` (`:822-825`), not as an error, then calls
  `session.commit()` (`:829`), which commits nothing and logs `Committed
  changes`. `main` prints the summary and the exit status is 0.
- MEMNON `ContentProcessor.process_chunked_file`
  (`nexus/agents/memnon/utils/content_processor.py:105`; reached through
  `MEMNON.process_chunked_file`, `nexus/agents/memnon/memnon.py:1740`, and
  through `process_all_narrative_files`, `:890`, which the `process_files`
  command calls at `:955`). `store_narrative_chunk` re-raises (`:370-375`),
  and `process_chunked_file` catches each chunk's exception at `:222-226`,
  logs it, and returns the number of chunks stored. Its INSERT (`:337-341`)
  and its UPDATE (`:295-302`) name columns that `chunk_metadata` does not
  have (`perspective`, `location`, `time_code`, `keywords`, `characters`;
  read-only `information_schema.columns` on `NEXUS_template` lists `id,
  chunk_id, season, episode, scene, world_layer, time_delta,
  generation_date, slug, world_time, generation_model, scene_weather`). The
  statement therefore fails with `UndefinedColumn` before the trigger runs,
  with or without a base, and the method returns 0. Migration 144 does not
  change this outcome today. If the column list matched the schema, 144's
  raise would be swallowed by the same handler.
- `scripts/estimate_time_delta.py:1275` (UPDATE of `time_delta`) and
  `:1286` (INSERT), in `update_chunk_metadata`: the inner handler rolls back
  and re-raises (`:1314-1318`); the outer handler catches at `:1325-1327`
  and returns False, and both callers (`:1425`, `:1539`) ignore the result.
  It writes metadata only for existing `narrative_chunks` rows, so it
  reaches a slot without a base only where such rows exist. Read, not
  probed (its estimates call a paid model).

### Other Writers (Read, Not Probed)

- `scripts/import_narratives.py` (`:552`, `:568`) and
  `scripts/extract_season_episode.py` (`:287`): their ORM models declare
  UUID ids, `narrative_chunks.sequence` and `chunk_metadata` columns
  (`setting`, `narrative_vector`, `location`, `atmosphere` and others) that
  the current schema does not have, so they cannot write chunk metadata on
  the current schema, whatever the base.
- `scripts/update_scene_numbers.py:138`, `scripts/extract_scene_numbers.py:132`,
  `scripts/fix_chunks.py:81` and the resequencing UPDATEs in
  `scripts/simple_update.py:712,723` set only `scene`, `season` and
  `episode`, or `id`, so the refresh trigger does not fire.
- `scripts/map_builder_legacy.py:1358` (UPDATE) and `:1373` (INSERT), and
  `scripts/process_characters.py:858` (UPDATE) and `:875` (INSERT), each in
  its `update_chunk_metadata` (`scripts/map_builder_legacy.py:1331`,
  `scripts/process_characters.py:788`): they write the columns `place` and
  `characters`, which `chunk_metadata` does not have (the read-only column
  listing above), so each statement fails with `UndefinedColumn` before the
  trigger runs, whatever the base. Each inner handler rolls back and
  returns False (`scripts/map_builder_legacy.py:1386-1391`,
  `scripts/process_characters.py:890-895`).
- `scripts/qa_shift/card_identity_probe.py:334` copies an anchor's metadata
  inside a `save_04` data clone (`:304-306`), whose base is set.

The guard is not softened, and round 2 changes no production code. The PR
body lists the swallowing handlers under "Deferred and Out of Scope" for a
follow-up issue.

### Writer Probe (Round 2)

`probe.sh` and `memnon_probe.py` in `scratchpad/1114-astra-fix-2/`, at
`7e32be25` with a clean tree. One disposable database,
`qa640_1114_probe`: `createdb -T NEXUS_template`, `scripts/migrate.py
--dbname` (144 applied), then `INSERT INTO global_variables (id) VALUES
(true)`, the shape of `save_05` (row present, base NULL, no chunks). Phase 1
runs each writer on a file with two scene breaks (`PROBE_S01E01.md`). Phase
2 sets the base while no chunk exists and runs the writers again
(`simple_update.py` on `PROBE_S01E02.md`, so that it creates chunks instead
of updating them). `memnon_probe.py` builds the real `DatabaseManager` and
`ContentProcessor` (embedding manager `None`; no embedding is reached) and
calls `process_chunked_file`. The output is filtered by `grep` to errors and
summaries (the filters are in `probe.sh`):

```text
head: 7e32be255e0db344abd05012cb48e7384fd58ffb; uncommitted: 0 files
uptime: 23:11  up  9:50, 5 users, load averages: 22.20 27.02 21.19
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_1114_probe: 141 migration stamps; level 144
INSERT 0 1
== phase 1: global_variables row present, base_timestamp NULL (the save_05 shape)
narrative_chunks=0 chunk_metadata=0 base=NULL
-- scripts/simple_update.py
2026-10-07 23:11:10,156 - nexus.simple_update - ERROR - Error creating chunk for S01E01_001: (psycopg2.errors.RaiseException) Story clock has no base: global_variables.base_timestamp is NULL or its row is missing while chunk_metadata holds chunk 1448; set base_timestamp before the first chunk
2026-10-07 23:11:10,159 - nexus.simple_update - ERROR - Error creating chunk for S01E01_002: (psycopg2.errors.RaiseException) Story clock has no base: global_variables.base_timestamp is NULL or its row is missing while chunk_metadata holds chunk 1449; set base_timestamp before the first chunk
Chunks created: 0
Errors: 2
exit=0
narrative_chunks=0 chunk_metadata=0 base=NULL
-- scripts/update_raw_text.py --no-backup
2026-10-07 23:11:10,825 - nexus.update_raw_text - ERROR - Error creating new chunk for S01E01_001: (psycopg2.errors.RaiseException) Story clock has no base: global_variables.base_timestamp is NULL or its row is missing while chunk_metadata holds chunk 1; set base_timestamp before the first chunk
2026-10-07 23:11:10,826 - nexus.update_raw_text - INFO - Committed changes for chunk S01E01_001
2026-10-07 23:11:10,828 - nexus.update_raw_text - ERROR - Error creating new chunk for S01E01_002: (psycopg2.errors.RaiseException) Story clock has no base: global_variables.base_timestamp is NULL or its row is missing while chunk_metadata holds chunk 1; set base_timestamp before the first chunk
2026-10-07 23:11:10,828 - nexus.update_raw_text - INFO - Committed changes for chunk S01E01_002
Chunks created: 0
Chunks not found: 2
Errors: 0
exit=0
narrative_chunks=0 chunk_metadata=0 base=NULL
-- MEMNON ContentProcessor.process_chunked_file
Error storing narrative chunk: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
psycopg2.errors.UndefinedColumn: column "perspective" of relation "chunk_metadata" does not exist
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
Error processing chunk: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
Error storing narrative chunk: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
psycopg2.errors.UndefinedColumn: column "perspective" of relation "chunk_metadata" does not exist
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
Error processing chunk: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
process_chunked_file returned 0
exit=0
narrative_chunks=0 chunk_metadata=0 base=NULL
UPDATE 1
== phase 2: base_timestamp set before any chunk
narrative_chunks=0 chunk_metadata=0 base=2099-12-31 19:00:00-05
-- MEMNON ContentProcessor.process_chunked_file
Error storing narrative chunk: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
psycopg2.errors.UndefinedColumn: column "perspective" of relation "chunk_metadata" does not exist
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
Error processing chunk: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
Error storing narrative chunk: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
psycopg2.errors.UndefinedColumn: column "perspective" of relation "chunk_metadata" does not exist
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
Error processing chunk: (psycopg2.errors.UndefinedColumn) column "perspective" of relation "chunk_metadata" does not exist
process_chunked_file returned 0
exit=0
narrative_chunks=0 chunk_metadata=0 base=2099-12-31 19:00:00-05
-- scripts/update_raw_text.py --no-backup
Chunks created: 2
Chunks not found: 0
Errors: 0
exit=0
narrative_chunks=2 chunk_metadata=2 base=2099-12-31 19:00:00-05
-- scripts/simple_update.py
Chunks created: 2
Errors: 0
exit=0
narrative_chunks=4 chunk_metadata=4 base=2099-12-31 19:00:00-05
1|2099-12-31 19:00:00-05
2|2099-12-31 19:00:00-05
3|2099-12-31 19:00:00-05
1454|2099-12-31 19:00:00-05
dropped: 0 remaining
```

A first attempt ran the same phases; its `memnon_probe.py` used a
`localhost` URL, which `DatabaseManager` refused (`PostgreSQL target
mismatch`; the runtime connects through the socket), and its database was
dropped by the script. A debugging run of `memnon_probe.py` on
`qa640_1114_memnon` (same setup, NULL base) showed the full `UndefinedColumn`
traceback; that database was dropped too. No `qa640_1114_*` database
remains (`psql -Atl`).

## Changed Tests and the Failure That Forced Each

Every failure below carried `Story clock has no base: global_variables.base_timestamp
is NULL or its row is missing while chunk_metadata holds chunk N`. None carried
`is fixed once chunk_metadata holds a row` except the discarded lifecycle edit.

| File | Fix | Failing tests before the fix |
| --- | --- | --- |
| `tests/test_interactions_pg.py` | `set_story_base(cur, DEFAULT_BASE_TIMESTAMP)` on the raw template clone | Known fix (item 5); cannot fail red before landing (raw 143-template clone). |
| `tests/test_orrery/test_retrograde_retrieval_pg.py` | `set_story_base` on `disposable_cursor` before the prologue chunk | Known fix (item 5); cannot fail red before landing (raw 143-template clone). |
| `tests/test_lore/conftest.py` | `seed_story_base` in `lore_infra_database` | Known fix (item 5). |
| `tests/test_idf_dictionary_pg.py` | `seed_story_base` in `idf_slot`, `qa762_other`, `qa762_fresh` | 17 tests (`test_slot_and_corpus_isolation` ... `test_data_clone_migrates_without_unlocking_source`). |
| `tests/test_orrery/test_narration_job_fencing_pg.py` | `set_story_base` in `_disposable_narration_db` (a `qa676_` raw template clone) | 7 tests (`test_duplicate_enqueue_collapses_to_one_effective_job` ... `test_descriptor_retirement_preserves_canon_legacy_jobs_and_bleed`). |
| `tests/test_orrery/test_recall_disclosure_pg.py` | `set_story_base` in module fixture `recall_database` | 21 tests. |
| `tests/test_orrery/test_bleed_proximity_live.py` | `seed_story_base` in `bleed_proximity_db` | 4 setup errors. |
| `tests/test_memnon/test_ann_gate.py` | `seed_story_base` in `ann_schema_clone` | 2 setup errors. |
| `tests/test_regenerate_embeddings_truncate_pg.py` | `seed_story_base` in `seeded_slot` | 2 setup errors. |
| `tests/test_api/test_narrative_jobs_pg.py` | `seed_story_base(offline_gate_db)` in the test (shared fixture left base-free) | `test_embedding_job_names_the_embedder_restore_command[missing]`, `[incomplete]`. |
| `tests/test_jobs_cli_pg.py` | `set_story_base` on the inserting cursor in the test | `test_jobs_cli_reports_counts_and_non_terminal_rows`. |
| `tests/test_lore/test_pass2_baseline_pg.py` | `seed_story_base` in the test | `test_evaluation_database_baseline_stamp_uses_story_settings`. |
| `tests/test_lore/test_scene_order_render.py` | `seed_story_base` in both tests | `test_recalled_render_clocks_come_from_narrative_view`, `test_assembly_hydrates_only_selected_recalled_entries_with_null_clocks`. |
| `tests/test_embedding_table_ownership_pg.py` | `seed_story_base` in `seed_source` before a chunk (an identical re-seed passes the guard) | 16 tests (every `chunk_id` parameter, plus `test_embedding_job_source_path_propagates_ensure_failure` and `test_content_processor_embedding_method_propagates_ensure_failure`). |
| `tests/test_api/test_scheduler_pg.py` | `seed_story_base` in `seed_experiences` (on `offline_gate_db`) | `test_scheduler_embeds_rendered_experiences_and_skips_the_rest`. |
| `tests/test_api/test_narrative_retry_pg.py` | `seed_story_base` in `recovery_db` before `_reset_to_committed_parent` | 17 setup errors. |

`tests/test_connection_lifecycle.py` is not changed. The order's known fix for
`:101` (`set_story_base(cur, timestamp)` first) is wrong for this test: by
then the wizard has bootstrapped `save_04` on the disposable cluster, so the
base is already set (1347-06-11 03:21) and chunks exist. The added call
failed the test with
`RaiseException: global_variables.base_timestamp is fixed once chunk_metadata holds a row: refusing to change it from 1347-06-11 03:21:00+00 to 2196-07-06 23:00:00+00`.
Without the call the chunk insert has a base and the test passes as on `main`
(`1 passed in 27.69s`).

`tests/test_world_clock_contract_pg.py` gains the five new tests; round 1
(`7e32be25`) added the layer-only arm to `test_null_base_rejects_later_writes`.
`tests/test_pg_disposable_target.py` registers `seed_story_base`.

## Which PostgreSQL Files Ran

The Machine load rule forbids the whole PostgreSQL gate. Instead of the
three-piece split, these focused sets ran, one session at a time, under
`nice -n 15`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:

1. The order's proof set plus every changed test file (final runs A and B
   below; rerun in round 2 at `7e32be25`, clean, with
   `tests/test_api/test_place_reference_validation_pg.py` added to B).
2. Every test file the order's static list names, every file that writes
   `chunk_metadata` directly (40 more files found by
   `grep -E "INSERT INTO chunk_metadata|insert_chunk_metadata_sync\(|seed_committed_chunk\("`),
   every test module importing a helper from one of those files (15 files),
   and every not-yet-run file with a raw `base_timestamp` write (5 files).
   After the fixes, all of these passed. These survey runs are not rerun at
   the head: final runs A and B rerun every changed file, and the
   coordinator's whole-tree gate at landing covers the other surveyed files.

The coordinator's whole-tree gate at landing covers the remaining PostgreSQL
files, which write chunks only through `seed_protagonist`,
`seed_played_story`, `seed_story_clock`, the accepted-turn factory or the
wizard transition (each sets the base first).

Load: in the resumed session every run before the last two started at a
one-minute load between 5.7 and 10.5; the first final run A started at
33.72 (I did not read `uptime` before launching it), and before the first
final run B the wait found 14.65. Round 2: each PostgreSQL session ran after
the bounded wait; the load each one started at is its first line.

## Review Fixes (Commit `00dba586`)

The `seed_protagonist` docstring now gives migration 144's guard as the reason
it refuses to move a set base, in place of the pre-144 desynchronization
sentence. Black left `tests/pg_fixtures.py` unchanged.

Its rerun in this file (`74 passed`, 15:08 with `HEAD` at `517544f8`; the
log records neither commit nor tree) is replaced by this round-2 session at
`7e32be25`, clean, which also holds the documentation tests:

```text
uptime: 23:13  up  9:53, 5 users, load averages: 13.23 21.38 19.93
commit: 7e32be25; uncommitted: 0 files
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rfEs -p tests.dbname_audit tests/test_world_clock_contract_pg.py tests/test_pg_disposable_target.py tests/test_doc_front_matter.py tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_clock_* x12, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
170 passed in 41.21s
exit=0
```

## Tails

Final run A (the order's proof set, the known fixes and `tests/test_lore`),
round 2, `7e32be25`, clean; the log's first three lines, then from the
`secret-store guard` line to the end, verbatim:

```text
uptime: 23:38  up 10:18, 5 users, load averages: 19.03 28.77 30.49
commit: 7e32be25; uncommitted: 0 files
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_world_clock_contract_pg.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_orrery/test_need_clock_anchor_pg.py tests/test_qa_shift.py tests/test_new_story_setup.py tests/test_pg_accepted_turn_factory.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py tests/test_interactions_pg.py tests/test_orrery/test_retrograde_retrieval_pg.py tests/test_lore
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 145 targets: mock, nexus_m10_fresh_test_90041, nexus_m10_template_test_90041, nexus_test_813_*, nexus_test_i685_* x3, nexus_test_interactions_* x14, nexus_test_pass2_* x7, postgres, qa640_* x18, qa640_742_seat_test_*, qa640_756s1_distinct_*, qa640_756s1_generation_* x2, qa640_759_measure_*, qa640_778s4a_tests_* x6, qa640_778s6a_family_* x9, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_816_factory_*, qa640_816_free_text_*, qa640_816_pending_*, qa640_816_preconditions_*, qa640_816_staging_failure_*, qa640_818_estimate_*, qa640_818_pin_* x2, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_885_remembered_*, qa640_885_remembered_opening_*, qa640_885_ren_replay_* x4, qa640_908_aliases_*, qa640_908_cast_*, qa640_908_fingerprint_*, qa640_910_dossier_* x7, qa640_clock_* x12, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_historical_coverage_* x3, qa640_retrieval_* x2, qa640_scene_clock_*, qa640_scene_null_clock_*, qa640_scene_parent_*, qa640_schema_docs_* x3, qa640_settings_stamp_*, qa640_vocab_migration_* x6, qa640_window_coverage_*, qa885_intertitle_*, qa885_retrieval_coverage_*, qa885_transaction_writer_*, qa_lazy_logon_*, qa_lore_infra_*, qa_runtime_config_* x5
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:60279 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:60282 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:60279 (psycopg2), save_04@local:60282 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:122: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_lore/test_infrastructure.py:219: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_lore/test_pass2_chunk1369.py: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [2] tests/test_lore/test_window_coverage_pg.py:488: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
873 passed, 6 skipped, 15 warnings in 286.28s (0:04:46)
exit=0
uncommitted after: 0 files
```

`test_migration_sequence_has_only_known_gaps` passed (every number below 144
is on `main`).

Final run B (the other changed test files and
`tests/test_api/test_place_reference_validation_pg.py`), round 2,
`7e32be25`, clean:

```text
uptime: 23:44  up 10:24, 5 users, load averages: 22.93 27.05 28.92
commit: 7e32be25; uncommitted: 0 files
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_api/test_narrative_jobs_pg.py tests/test_api/test_narrative_retry_pg.py tests/test_api/test_scheduler_pg.py tests/test_embedding_table_ownership_pg.py tests/test_idf_dictionary_pg.py tests/test_jobs_cli_pg.py tests/test_memnon/test_ann_gate.py tests/test_orrery/test_bleed_proximity_live.py tests/test_orrery/test_narration_job_fencing_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_api/test_place_reference_validation_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 133 targets: nexus_test_retry_* x17, postgres, qa640_766_schema_*, qa640_800_operator_*, qa640_810s2_contract_* x52, qa640_acceptance_* x6, qa640_bleed_proximity_* x4, qa640_offline_gate_* x17, qa640_regen_truncate_* x2, qa653_* x2, qa676_* x7, qa762_corpus_copy_*, qa762_fresh_*, qa762_idf_* x19, qa762_other_*, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [1] tests/test_memnon/test_ann_gate.py:120: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
163 passed, 1 skipped, 7 warnings in 291.57s (0:04:51)
exit=0
uncommitted after: 0 files
```

These replace final runs A (`873 passed, 6 skipped`) and B (`160 passed, 1
skipped`) of 14:27 and 14:32, which ran with `HEAD` at `58cef582` before the
merge of `b0da93ea`; their logs record neither commit nor tree, and the next
commit (`1760cbfd`, 14:34) changed only `AGENTS.md` and this file. B now has
3 more tests, those of the added file.

Survey runs (same environment), in order. They ran between 13:42 and 14:09
CDT with `HEAD` at `36cc28ea` and the uncommitted working tree that became
`1b5473d9`..`58cef582` (`proof1` also held the `tests/test_connection_lifecycle.py`
edit that was later discarded); the logs record neither commit nor tree.
They show the failures that forced each fix and the passes after it. The
logs in `scratchpad/778-S1b-resume/` hold the output but not the commands.
The file lists below are reconstructed from the order's static list and the
saved grep lists (`done.txt`, `risky1.txt`, `risky2.txt`). Each list was
checked on `517544f8` with `pytest -q --collect-only`: it collects exactly
the number of tests its log reports (passed + failed + skipped + errors).
The flags are those of runs A and B; the short summaries in the logs match
`-rfEs`. Each tail is verbatim from the log, from the `secret-store guard`
line through the count line.

proof1: the order's proof set and the known fixes, with the `tests/test_connection_lifecycle.py` edit present.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_world_clock_contract_pg.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py tests/test_orrery/test_need_clock_anchor_pg.py tests/test_qa_shift.py tests/test_new_story_setup.py tests/test_pg_accepted_turn_factory.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py tests/test_interactions_pg.py tests/test_orrery/test_retrograde_retrieval_pg.py tests/test_lore/test_infrastructure.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 101 targets: mock, nexus_m10_fresh_test_17029, nexus_m10_template_test_17029, nexus_test_interactions_* x14, postgres, qa640_* x18, qa640_759_measure_*, qa640_778s4a_tests_* x6, qa640_778s6a_family_* x9, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_816_factory_*, qa640_816_free_text_*, qa640_816_pending_*, qa640_816_preconditions_*, qa640_816_staging_failure_*, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_885_remembered_*, qa640_885_remembered_opening_*, qa640_885_ren_replay_* x4, qa640_clock_* x12, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_retrieval_* x2, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*, qa_lore_infra_*
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:50944 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:50971 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:50944 (psycopg2), save_04@local:50971 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
1 failed, 412 passed, 3 skipped, 13 warnings in 142.59s (0:02:22)
```

proof1b: `tests/test_connection_lifecycle.py` with that edit discarded.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_connection_lifecycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 2 targets: mock, postgres
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:52096 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:52097 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
dbname audit: owner names admitted on registered clusters: save_04@local:52096 (psycopg2), save_04@local:52097 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1 passed in 27.69s
```

proof2: the order's static list and `tests/test_lore`, before the fixes; every failure and error is `Story clock has no base`.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_memnon/test_ann_gate.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_api/test_narrative_jobs_pg.py tests/test_jobs_cli_pg.py tests/test_orrery/test_bleed_proximity_live.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_idf_dictionary_pg.py tests/test_orrery/test_narration_job_fencing_pg.py tests/test_orrery/test_claim_accounts_live.py tests/test_orrery/test_boundary_enumeration_pg.py tests/test_orrery/test_reveal_live.py tests/test_lore
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 101 targets: nexus_test_813_*, nexus_test_i685_* x3, nexus_test_pass2_* x7, postgres, qa640_742_seat_test_*, qa640_756s1_distinct_*, qa640_756s1_generation_* x2, qa640_766_schema_*, qa640_780_boundaries_*, qa640_780_storm_*, qa640_800_operator_*, qa640_818_estimate_*, qa640_818_pin_* x2, qa640_908_aliases_*, qa640_908_cast_*, qa640_908_fingerprint_*, qa640_910_dossier_* x7, qa640_acceptance_* x3, qa640_bleed_proximity_* x4, qa640_claim_accounts_*, qa640_historical_coverage_* x3, qa640_offline_gate_* x10, qa640_regen_truncate_* x2, qa640_scene_clock_*, qa640_scene_null_clock_*, qa640_scene_parent_*, qa640_settings_stamp_*, qa640_window_coverage_*, qa653_* x2, qa676_* x7, qa762_idf_* x19, qa762_other_*, qa885_intertitle_*, qa885_retrieval_coverage_*, qa885_reveal_*, qa_lazy_logon_*, qa_lore_infra_*, qa_runtime_config_* x5, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_narrative_jobs_pg.py::test_embedding_job_names_the_embedder_restore_command[missing]
FAILED tests/test_api/test_narrative_jobs_pg.py::test_embedding_job_names_the_embedder_restore_command[incomplete]
FAILED tests/test_jobs_cli_pg.py::test_jobs_cli_reports_counts_and_non_terminal_rows
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_cognition_trace_endpoint_rejects_invalid_identifiers
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_cognition_trace_deep_reads_reject_post_validation_mutations
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_cognition_trace_endpoint_keeps_canonical_truth_guarded
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_distorted_account_never_leaks_canonical_event_adjacency
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_cognition_trace_rolls_awareness_and_secret_status_back_to_anchor
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_ownership_and_anchor_validity_are_hard_boundaries
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_experience_recall_index_preserves_all_eligibility_boundaries
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_experience_recall_large_shape_uses_eligibility_index
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_critical_current_scene_account_bypasses_ranking
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_world_clock_decay_lowers_rank_without_mutating_possession
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_claim_rank_is_invariant_to_unpossessed_sibling_secret
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_turn_inputs_change_experience_ranking_via_shared_query_embedding
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_disclosure_suppression_is_logged_and_not_surfaced
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_role_obligation_suppresses_unauthorized_audience
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_trust_and_shared_status_can_disclose_private_claim
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_per_character_cap_preserves_shared_budget_for_other_actors
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_trace_retention_prunes_oldest_rows_per_character
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_empty_candidate_set_executes_no_trace_statements
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_batched_trace_rows_match_across_database_surfaces
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_same_turn_batched_trace_rerun_updates_without_duplicates
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_trace_round_trips_are_bounded_by_configured_batch_size
FAILED tests/test_idf_dictionary_pg.py::test_slot_and_corpus_isolation - psyc...
FAILED tests/test_idf_dictionary_pg.py::test_edits_deletes_rollback_and_membership
FAILED tests/test_idf_dictionary_pg.py::test_reader_snapshot_and_next_commit
FAILED tests/test_idf_dictionary_pg.py::test_postgres_lexemes_and_query_quoting
FAILED tests/test_idf_dictionary_pg.py::test_mismatched_state_fails_through_production_search
FAILED tests/test_idf_dictionary_pg.py::test_truncation_clears_counts - psyco...
FAILED tests/test_idf_dictionary_pg.py::test_summary_counts_and_production_search
FAILED tests/test_idf_dictionary_pg.py::test_concurrent_writers_preserve_document_frequencies
FAILED tests/test_idf_dictionary_pg.py::test_query_reads_stay_bounded_when_unrelated_vocabulary_grows[narrative]
FAILED tests/test_idf_dictionary_pg.py::test_query_reads_stay_bounded_when_unrelated_vocabulary_grows[retrograde_summary]
FAILED tests/test_idf_dictionary_pg.py::test_fresh_slot_from_migrated_source_has_empty_own_state
FAILED tests/test_idf_dictionary_pg.py::test_shared_reader_scores_its_own_snapshot[query]
FAILED tests/test_idf_dictionary_pg.py::test_shared_reader_scores_its_own_snapshot[batch]
FAILED tests/test_idf_dictionary_pg.py::test_shared_reader_scores_its_own_snapshot[single]
FAILED tests/test_idf_dictionary_pg.py::test_shared_reader_scores_its_own_snapshot[high_terms]
FAILED tests/test_idf_dictionary_pg.py::test_source_lock_precedes_world_time_refresh
FAILED tests/test_idf_dictionary_pg.py::test_data_clone_migrates_without_unlocking_source
FAILED tests/test_orrery/test_narration_job_fencing_pg.py::test_duplicate_enqueue_collapses_to_one_effective_job
FAILED tests/test_orrery/test_narration_job_fencing_pg.py::test_expired_lease_reclaimed_and_original_completion_fenced
FAILED tests/test_orrery/test_narration_job_fencing_pg.py::test_stale_anchor_completion_is_terminally_rejected
FAILED tests/test_orrery/test_narration_job_fencing_pg.py::test_completion_locks_world_layer_before_comparing_anchor
FAILED tests/test_orrery/test_narration_job_fencing_pg.py::test_completion_clock_counts_time_blocked_on_job_lock
FAILED tests/test_orrery/test_narration_job_fencing_pg.py::test_normal_narration_path_succeeds_once_end_to_end
FAILED tests/test_orrery/test_narration_job_fencing_pg.py::test_descriptor_retirement_preserves_canon_legacy_jobs_and_bleed
FAILED tests/test_lore/test_pass2_baseline_pg.py::test_evaluation_database_baseline_stamp_uses_story_settings
FAILED tests/test_lore/test_scene_order_render.py::test_recalled_render_clocks_come_from_narrative_view
FAILED tests/test_lore/test_scene_order_render.py::test_assembly_hydrates_only_selected_recalled_entries_with_null_clocks
ERROR tests/test_memnon/test_ann_gate.py::test_ann_candidate_index_build_drop
ERROR tests/test_memnon/test_ann_gate.py::test_ann_alias_candidates_and_database_errors
ERROR tests/test_regenerate_embeddings_truncate_pg.py::test_truncate_table_keeps_rows_when_the_model_artifact_is_missing
ERROR tests/test_regenerate_embeddings_truncate_pg.py::test_chunk_keeps_its_row_when_the_model_artifact_is_missing
ERROR tests/test_orrery/test_bleed_proximity_live.py::test_live_boundary_reservation_and_configured_starvation
ERROR tests/test_orrery/test_bleed_proximity_live.py::test_live_faction_reference_is_not_a_physical_anchor
ERROR tests/test_orrery/test_bleed_proximity_live.py::test_live_backfill_and_determinism
ERROR tests/test_orrery/test_bleed_proximity_live.py::test_live_phase_state_reports_distance_class_counts
SKIPPED [1] tests/test_memnon/test_ann_gate.py:115: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_lore/test_infrastructure.py:219: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_lore/test_pass2_chunk1369.py: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [2] tests/test_lore/test_window_coverage_pg.py:488: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
51 failed, 513 passed, 5 skipped, 9 warnings, 8 errors in 205.84s (0:03:25)
```

proof2b: the ten failing files, after the fixes.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_api/test_narrative_jobs_pg.py tests/test_jobs_cli_pg.py tests/test_orrery/test_recall_disclosure_pg.py tests/test_idf_dictionary_pg.py tests/test_orrery/test_narration_job_fencing_pg.py tests/test_lore/test_pass2_baseline_pg.py tests/test_lore/test_scene_order_render.py tests/test_memnon/test_ann_gate.py tests/test_regenerate_embeddings_truncate_pg.py tests/test_orrery/test_bleed_proximity_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 65 targets: nexus_test_pass2_* x7, postgres, qa640_766_schema_*, qa640_800_operator_*, qa640_acceptance_* x3, qa640_bleed_proximity_* x4, qa640_offline_gate_* x10, qa640_regen_truncate_* x2, qa640_scene_clock_*, qa640_scene_null_clock_*, qa640_scene_parent_*, qa640_settings_stamp_*, qa653_* x2, qa676_* x7, qa762_corpus_copy_*, qa762_fresh_*, qa762_idf_* x19, qa762_other_*, qa_wt724_recall_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [1] tests/test_memnon/test_ann_gate.py:120: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
101 passed, 1 skipped, 9 warnings in 125.13s (0:02:05)
```

proof3a: 20 direct `chunk_metadata` writers (`risky1.txt`); the 16 failures are `Story clock has no base`.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_api/test_acceptance_staging_pg.py tests/test_api/test_backstage_endpoints_pg.py tests/test_api/test_correspondence_pg.py tests/test_api/test_frontier_clock_pg.py tests/test_api/test_narrative_continue_validation.py tests/test_api/test_orrery_config_reuse_pg.py tests/test_api/test_reader_feed_pg.py tests/test_api/test_return_recap_pg.py tests/test_api/test_seat_policy_backfill_pg.py tests/test_commit_choice_presence_pg.py tests/test_commit_handler_sync.py tests/test_embedding_table_ownership_pg.py tests/test_measure_place_coordinate_costs_pg.py tests/test_memnon_model_failures_pg.py tests/test_orrery_tag_validation_pg.py tests/test_orrery/test_acquisition_scan_pg.py tests/test_orrery/test_build_venture_replay.py tests/test_orrery/test_character_experiences_pg.py tests/test_orrery/test_claim_awareness_replay_live.py tests/test_orrery/test_claim_birth_coverage_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 154 targets: nexus_test_continue_* x10, nexus_test_correspondence_* x2, postgres, qa640_767s1_feed_* x3, qa640_778s6a_backstage_*, qa640_778s6a_empty_*, qa640_810s2_contract_* x52, qa640_814_backfill_*, qa640_840_cost_*, qa640_acceptance_* x19, qa640_compaction_retry_*, qa640_offline_gate_*, qa640_wizard_drain_* x3, qa649_*, qa654_*, qa679_*, qa832_recap_* x10, qa885_build_venture_replay_*, qa885_claim_awareness_replay_*, qa_model_failures_* x15, qa_wt715_*, qa_wt723_*, qa_wt724_experience_* x26
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[sqlalchemy-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[tuple-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_creates_commented_corpus_contract[dict-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_is_idempotent_and_never_builds_ann[chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[dimension-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[source_type-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[nullable_model-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[primary-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[fk_target-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[fk_delete-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[timestamp-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[view-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_refuses_malformed_objects_before_writing[index-chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_ensure_and_upsert_roll_back_with_the_caller[chunk_id]
FAILED tests/test_embedding_table_ownership_pg.py::test_embedding_job_source_path_propagates_ensure_failure
FAILED tests/test_embedding_table_ownership_pg.py::test_content_processor_embedding_method_propagates_ensure_failure
16 failed, 265 passed, 17 warnings in 279.54s (0:04:39)
```

proof3a2: `tests/test_embedding_table_ownership_pg.py`, after its fix.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_embedding_table_ownership_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 53 targets: postgres, qa640_810s2_contract_* x52
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
52 passed in 77.89s (0:01:17)
```

proof3b: 20 more direct `chunk_metadata` writers (`risky2.txt`).

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_orrery/test_claim_propagation_live.py tests/test_orrery/test_drift_live.py tests/test_orrery/test_experience_enqueue_gin_pg.py tests/test_orrery/test_generation_model_provenance_live.py tests/test_orrery/test_knowledge_surfacing_live.py tests/test_orrery/test_mood_live.py tests/test_orrery/test_need_absence_pg.py tests/test_orrery/test_pursue_romance_replay.py tests/test_orrery/test_recruit_ally_replay.py tests/test_orrery/test_replay.py tests/test_orrery/test_retrograde_projects_live.py tests/test_orrery/test_retrograde_summary_migration_pg.py tests/test_orrery/test_stage2a_epistemics_live.py tests/test_orrery/test_weather_live.py tests/test_orrery/test_weather_migration_pg.py tests/test_orrery/test_world_event_time_pg.py tests/test_player_identity_consumers_pg.py tests/test_presence_boost_pg.py tests/test_rebuild_memory_idf_pg.py tests/test_runtime/test_readiness_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 86 targets: postgres, qa640_1013_absent_*, qa640_1013_idf_* x7, qa640_1013_readiness_* x2, qa640_778s2a_time_* x14, qa640_778s6a_played_*, qa640_778s6a_replay_* x7, qa640_drift_*, qa640_need_absence_* x7, qa640_projects799_*, qa640_provenance_* x3, qa640_replay_*, qa640_retro078_* x13, qa640_weather_migration_*, qa683_presence_* x2, qa735_mood_*, qa735_weather_*, qa885_claim_propagation_*, qa885_knowledge_surfacing_*, qa885_pursue_romance_replay_*, qa885_recruit_ally_replay_*, qa885_stage2a_epistemics_*, qa_identity_surface_04d22ac099, qa_identity_surface_198c15305d, qa_identity_surface_4057466219, qa_identity_surface_692117310f, qa_identity_surface_6a3d525a8e, qa_identity_surface_a127d15dee, qa_identity_surface_f2589c1815, qa_player_identity_6a61d9fd1a, qa_wt720_*, readiness803_*, readiness803_slot1_*, readiness803_slot2_*, readiness803_slot3_*, readiness803_slot4_*, readiness803_slot5_*, readiness803_template_*, readiness803ro_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
180 passed, 2 warnings in 135.65s (0:02:15)
```

proof4: 14 modules that import helpers from the files above.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_api/test_narrative_retry_pg.py tests/test_api/test_reentry_wire_pg.py tests/test_api/test_scheduler_pg.py tests/test_api/test_scheduler_recovery_pg.py tests/test_bootstrap_episode_pg.py tests/test_memnon/test_source_embeddings.py tests/test_name_reveal_staged_bindings_pg.py tests/test_orrery/test_court_patron_replay.py tests/test_orrery/test_experiences.py tests/test_orrery/test_relationship_provenance_pg.py tests/test_orrery/test_retrograde_persistence.py tests/test_orrery/test_seek_redemption_replay.py tests/test_presence_roster_pg.py tests/test_retrograde_summary_retrieval.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 97 targets: nexus_test_retry_* x17, postgres, qa640_800_kill_*, qa640_800_renew_* x4, qa640_807_latest_playable_*, qa640_807_maturation_boundary_*, qa640_807_reapply_*, qa640_810s2_experience_ids_*, qa640_810s2_source_* x5, qa640_810s2_summary384_*, qa640_acceptance_* x19, qa640_drift_*, qa640_offline_gate_* x12, qa640_roster798_* x29, qa885_court_patron_*, qa885_seek_redemption_*, qa947_episode_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_pg.py::test_scheduler_embeds_rendered_experiences_and_skips_the_rest
ERROR tests/test_api/test_narrative_retry_pg.py::test_concurrent_retry_has_one_owner_and_never_recommits_action
ERROR tests/test_api/test_narrative_retry_pg.py::test_retry_rejects_changed_durable_state_before_session_creation[pending]
ERROR tests/test_api/test_narrative_retry_pg.py::test_retry_rejects_changed_durable_state_before_session_creation[newer_attempt]
ERROR tests/test_api/test_narrative_retry_pg.py::test_retry_rejects_changed_durable_state_before_session_creation[newer_chunk]
ERROR tests/test_api/test_narrative_retry_pg.py::test_retry_rejects_changed_durable_state_before_session_creation[missing_action]
ERROR tests/test_api/test_narrative_retry_pg.py::test_retry_rejects_changed_durable_state_before_session_creation[discarded]
ERROR tests/test_api/test_narrative_retry_pg.py::test_retry_rejects_changed_durable_state_before_session_creation[missing_parent]
ERROR tests/test_api/test_narrative_retry_pg.py::test_staging_failure_resumes_as_recovery_and_retries_once
ERROR tests/test_api/test_narrative_retry_pg.py::test_dead_worker_is_advertised_exactly_as_retry_accepts_it
ERROR tests/test_api/test_narrative_retry_pg.py::test_restart_reopens_the_menu_when_no_retry_can_resume
ERROR tests/test_api/test_narrative_retry_pg.py::test_retry_bootstrap_without_a_playable_parent
ERROR tests/test_api/test_narrative_retry_pg.py::test_failure_between_acceptance_and_bind_stays_retryable
ERROR tests/test_api/test_narrative_retry_pg.py::test_explicit_frontier_chunk_bind_failure_stays_retryable
ERROR tests/test_api/test_narrative_retry_pg.py::test_pending_approval_failure_after_commit_stays_retryable
ERROR tests/test_api/test_narrative_retry_pg.py::test_abandon_before_worker_commit_still_binds_the_approved_action
ERROR tests/test_api/test_narrative_retry_pg.py::test_cancelled_route_leaves_a_retryable_failure_after_the_worker_commits
ERROR tests/test_api/test_narrative_retry_pg.py::test_worker_binding_and_cancelled_abandon_overlap_without_deadlock
2 failed, 153 passed, 7 warnings, 17 errors in 302.98s (0:05:02)
```

proof4b: the three failing files, after the fixes.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_api/test_scheduler_recovery_pg.py tests/test_api/test_scheduler_pg.py tests/test_api/test_narrative_retry_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: nexus_test_retry_* x17, postgres, qa640_800_kill_*, qa640_800_renew_* x4, qa640_offline_gate_* x12
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
34 passed, 7 warnings in 122.78s (0:02:02)
```

proof5: 5 not-yet-run files with raw `base_timestamp` writes.

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_api/test_reader_draft_identity_pg.py tests/test_gis_scripts_live.py tests/test_orrery/test_gis_stub_paths_live.py tests/test_orrery/test_pair_tag_writer.py tests/test_wizard_opening_presence_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 30 targets: postgres, qa655_wizard_1a13b523ed, qa655_wizard_22bc968275, qa655_wizard_76ba6bd743, qa655_wizard_a653517aea, qa655_wizard_d8953f4c28, qa655_wizard_f2abe60da3, qa735_gis_scripts_* x3, qa735_gis_stubs_* x5, qa735_pair_tags_* x10, qa951_identity_* x4, qa951_overwrite_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
28 passed, 9 warnings in 70.82s (0:01:10)
```

The import scan found a fifteenth importer that proof4 did not run,
`tests/test_api/test_place_reference_validation_pg.py` (3 tests; proof4
collected 172 = the other 14 files). It ran at 15:08 with `HEAD` at
`517544f8` (the log records neither commit nor tree; the next commit,
`f744f30c`, changed only this file), after `uptime` read 12.75:

```text
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p tests.dbname_audit -rfEs tests/test_api/test_place_reference_validation_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_acceptance_* x3
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
3 passed, 7 warnings in 4.77s
```

In proof4,
`tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]`
failed on a timing bound (`assert (2492.553798708 - 2491.374662458) < 1`)
at a one-minute load near 10, with no clock or base error; the same file
passed whole in proof4b (`34 passed`). It is reported, not fixed.

Offline suites, all at `7e32be25`, clean. Round 1 split the first suite in
two by the first letter of each top-level `tests/test_*` entry (the
ten-minute limit); piece a keeps `tests/config`, `tests/fixtures` and
`tests/proofs`, which piece b ignores. At `7e32be25`, `--collect-only` gives
1,501 tests for piece a and 2,029 for piece b, 3,530 together, the count of
the whole `tests --ignore=tests/test_api --ignore=tests/test_orrery` set.
Each run reports two more results than its `--collect-only` count; I did not
find why (no subtests or nested pytest runs in `tests/`).

Piece a (round 1, `offline-a.log`):

```text
uptime: 15:25  up  2:05, 5 users, load averages: 17.48 21.40 21.54
commit: 7e32be25; uncommitted: 0 files
$ PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore-glob='tests/test_[m-z]*'
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1276 passed, 227 skipped, 5 warnings in 376.28s (0:06:16)
exit=0
```

Piece b (round 1, `offline-b.log`):

```text
uptime: 15:32  up  2:12, 5 users, load averages: 32.16 25.47 23.13
commit: 7e32be25; uncommitted: 0 files
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore-glob='tests/test_[a-l]*' --ignore=tests/config --ignore=tests/fixtures --ignore=tests/proofs
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1689 passed, 342 skipped, 8 warnings in 277.81s (0:04:37)
exit=0
```

`tests/test_api tests/test_orrery` (round 2; the round-1 run of this piece
stopped at 2 % and is not used):

```text
uptime: 23:18  up  9:57, 5 users, load averages: 20.78 25.11 22.31
commit: 7e32be25; uncommitted: 0 files
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_POSTGRES PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1848 passed, 1369 skipped, 7 warnings in 48.83s
exit=0
```

`tests/test_doc_front_matter.py` and `tests/test_reachability.py` ran in the
round-2 session above (`170 passed`). The offline tails this file carried
before (`2944 passed, 564 skipped`; `1865 passed, 1369 skipped`; `96
passed`) ran with `HEAD` at `58cef582` before the merge of `b0da93ea`, with
the tree not recorded, and are replaced.

Static checks on the changed Python files, round 2, `7e32be25`, clean
(`r4.sh`; the `origin/main` versions are linted in a copy under the
scratch directory). The log's first 14 lines and its last 5, verbatim; the
41 lines between list the branch's mypy messages against the failed
`origin/main` half and are omitted:

```text
uptime: 23:20  up 10 hrs, 5 users, load averages: 41.45 30.54 24.83
commit: 7e32be25; uncommitted: 0 files; origin/main: b0da93ea; merge base: b0da93ea
changed Python files: 19
== black --check
19 files would be left unchanged.
pre-existing on origin/main: 19
== flake8 branch: 53 diagnostics
== flake8 origin/main: 53 diagnostics
flake8 set difference (branch minus main, line numbers dropped):
tests/test_api/test_scheduler_pg.py: F811 redefinition of unused 'mock_openai_server' from line 378
== mypy branch
Found 39 errors in 8 files (checked 19 source files)
== mypy origin/main
mypy: error: Cannot find config file '/Users/pythagor/nexus/.claude/worktrees/778-null-base-guard/mypy.ini'
== exception dispositions
OK: exception disposition coverage and shrink-only baseline verified.
== migration comments
OK: every object created after migration 129 has a comment.
uncommitted after: 0 files
```

The flake8 difference is one diagnostic whose message names a line that
moved: `F811 redefinition of unused 'mock_openai_server' from line 378` on
the branch is `from line 377` on `origin/main`, shifted by the added import
line. `r4.sh` called mypy on the `origin/main` versions with a config file
that does not exist, so that half ran again on a `git archive` of
`origin/main` (`nexus`, `tests`, `scripts`, `pyproject.toml`) under the
scratch directory:

```text
origin/main tree: b0da93ea exported by git archive
Found 39 errors in 8 files (checked 19 source files)
branch minus main:
main minus branch:
```

The mypy messages, with line numbers dropped, are the same set on both. No
new diagnostic. `$PY -S scripts/check_exception_dispositions.py
--baseline-base-ref origin/main`: `OK: exception disposition coverage and
shrink-only baseline verified.`

Pre-existing diagnostics: the 53 flake8 and 39 mypy diagnostics above are all
on lines this branch does not change.

## Document Freshness

`tests/pg_fixtures.py` and `tests/test_lore/conftest.py` are `AGENTS.md`
sources. `AGENTS.md` names them only as the fixture modules to reuse
(`:53`), which stays true. `verified_commit` moved from `41783c1d` to the
merge base `364fef4b` in `1760cbfd`, then to the new merge base `b0da93ea`
in `9343e8b8`. `tests/test_doc_front_matter.py` passes at `7e32be25` (the
`170 passed` session above). No `docs/turn_flow_sequence.md` source changed.

## Landing Notes

Migration 144. Apply when no turn is in flight: `python scripts/migrate.py --all`,
then `python scripts/migrate.py --slot 1 --write-locked-slot`, then
`nexus doctor`. With the template at 144, rerun every raw-template-clone file
the order lists (`tests/test_interactions_pg.py`,
`tests/test_orrery/test_retrograde_retrieval_pg.py`,
`tests/test_orrery/test_need_clock_anchor_pg.py`,
`tests/test_presence_boost_pg.py`, `tests/test_orrery_tag_validation_pg.py`,
`tests/test_lore/test_recent_orrery_rulings_pg.py`,
`tests/test_api/test_mock_wizard_responses.py`,
`tests/test_correspondence_live.py`, `tests/test_presence_reconciliation.py`,
`tests/test_orrery/test_gaia_registry_schema_pg.py`) with
`NEXUS_RUN_POSTGRES=1 ... -p tests.dbname_audit`. Migration, tests and docs
only: no gateway restart, no UI rebuild.
