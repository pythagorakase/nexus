# Database Connections

`nexus.database` owns target and session resolution. Use `get_connection()` for
API transactions and `create_slot_engine()` for SQLAlchemy. All engine checkout
pings are enabled. `[api.database]` defines minimum/maximum pool connections,
`preflight_idle_seconds` (zero pings every checkout), and `application_name_prefix`.
SQLAlchemy starts connections lazily; its retained pool size is the minimum and
its overflow allowance is maximum minus minimum.

Backend labels are `<prefix>:<role>:<suffix>`: the roles are `sync` (including API
pools and direct psycopg2 clients), `asyncpg`, `sqlalchemy`, and `subprocess`.
The suffix is `NEXUS_GATEWAY_PORT` when set, otherwise the process ID. For example,
lane 8017 pooled sessions are `nexus:sync:8017`. Existing explicit libpq session
options remain supported; termination probes must verify the actual backend label.

Pooled checkout rejects closed or non-idle sessions and pings sufficiently idle
sessions before yielding. One replacement is allowed, with an INFO reason; a
second failure escapes. Transaction connection errors and failed rollbacks discard
the session. Ordinary SQL errors roll back and preserve reusable connections.

## Ambiguous Commits Must Not Be Replayed

A connection-level error from commit does not establish whether PostgreSQL
committed the transaction. `AmbiguousCommit` names the database and original
error, closes the failed connection, and is terminal. Never replay the mutation,
try another fallback strategy, or requeue a job in response. Direct transaction
owners can use `commit_transaction()` or `transaction()` to preserve this contract.
Generic retries cover provider rate limits/timeouts only. Where a caller cannot
identify the commit phase, even a raw (or wrapped) database connection error is
terminal. Heartbeats may recover only when their commit-aware context proves
commit was not attempted. Otherwise the scheduler stops dispatch and reports
`failed`; operators must
reconcile durable state before restarting it. This policy does not infer success
or failure, and does not create an automatic recovery migration.

Slot replacement calls `dispose_database(dbname)` before destructive work and
before returning, invalidating local pools and registered engines. SQLAlchemy
engine references remain registered after disposal so repeated resets invalidate
their replacement pools too. Replacement must quiesce work using that database;
disposal does not coordinate transactions in other processes.

## Migration Ownership

`scripts/migrate.py` is the only migration runner: it discovers, applies, and
stamps migrations in each database's `schema_migrations` table, and
`scripts/new_story_setup.py` calls it for fresh slots. Do not apply migration SQL
with `psql` or ad hoc scripts; an unstamped change is invisible to the runner.
Slot initialization and data cloning in `scripts/new_story_setup.py` raise on
any migration or restore error and never log success, but the partial target
database remains: initialization can leave committed migrations, seed rows, and
the `global_variables` row without IDF initialization, and a failed clone can
keep the source's `new_story = false`, which lists the slot as active.
`start_setup` reuses an existing database without checking its migrations, so
recreate the target with `--force` after fixing the cause; durable quarantine
and staged replacement belong to #823. The runner itself propagates connection
errors instead of reporting nothing pending, and `migrate.py --all` stops at the
first database that raises, logging the databases it processed and the ones it
did not reach.
Discovery fails loudly when an entry in `migrations/` is not an
`NNN_name.sql` or `NNN_name.py` file (bytecode caches and `.DS_Store` excepted),
when two files share a version, or when a Python migration's version is missing
from `PYTHON_MIGRATION_ALLOWLIST`. New migrations are SQL and take the next free
number. Python is reserved for mechanics a single transaction cannot express,
such as `CREATE INDEX CONCURRENTLY`; allowlist such a version with a comment
giving the reason. Offline tests in `tests/test_orrery/test_migrate.py` pin the
allowlist to the Python files on disk, keep versions unique and increasing, and
fail on any numbering gap beyond the historical `KNOWN_GAPS` (013 and 119).

Migration 138 owns the column `chunk_metadata.scene` and three indexes that no
earlier migration created: `narrative_chunks_text_idx`,
`idx_chunk_metadata_scene`, and `idx_chunk_metadata_season_episode_scene`. It
refuses, by name, a same-named index with another definition and a `scene`
column of another type. Constructing the MEMNON `DatabaseManager` creates no
schema object and refuses a missing vector extension, owned by migration 022.
Migration 138 owns the fixed indexes and scene column. Migration 022 documents
lazy dimension-table ownership by `ensure_embedding_table`,
`ensure_retrograde_summary_embedding_table`, and
`ensure_character_experience_embedding_table` for narrative chunks, Retrograde
summaries, and actor-owned character experiences. These helpers validate the
catalog contract before modifying existing objects, write full table, column,
primary-key index and model-index comments, and fail loudly on incompatibility
or database errors. Transactions belong to their callers. ANN creation remains
behind the explicit 2560d candidate gate; #812 owns legacy 1024d/1536d tables
and L2 HNSW indexes on `save_01`/`save_02`. The legacy scripts
`scripts/extract_scene_numbers.py`, `scripts/update_scene_numbers.py`, and
`scripts/import_narratives.py` still carry their own DDL; moving those into
migrations is later work on #810.

## IDF Rebuild After a PostgreSQL Update

Migration 114 keys each IDF corpus row (`memory_idf_corpora.analyzer_version`)
on `pg_catalog.english/v1/<server_version_num>`, the exact server version, and
`sync_memory_idf_document` and `IDFStateError` reject a mismatch. The key stays
exact because a patch release can change lexing. Postgres.app installs patch
releases by itself, so after any update every existing slot and
`NEXUS_template` refuse narrative and summary writes (`IDF analyzer mismatch
for corpus narrative: expected ..., found ...`) until their corpora are rebuilt.
`nexus doctor` reports it first: `template.idf_analyzer_current` and
`slots.idf_analyzer_current` compare each corpus key with the live server,
fail unless exactly the `narrative` and `retrograde_summary` rows exist, and
name the command. Fresh slots are unaffected; `scripts/new_story_setup.py`
seeds them with the live key.

`scripts/rebuild_memory_idf.py` is the rebuild. It takes the migration runner's
targets (`--slot N`, `--template`, `--all`, `--dbname qa640_*|ref_*`), skips a
database that does not exist, and skips a locked slot unless
`--write-locked-slot` is given (the override lasts one maintenance session).
Like `migrate.py --dbname`, an explicit `--dbname` that does not exist raises,
and one that is read-only without `--write-locked-slot` is refused (exit 2).
For each database, one transaction locks `narrative_chunks`, `chunk_metadata`
and `retrograde_summaries`, locks the corpus rows, seeds a missing `narrative`
or `retrograde_summary` row at the live key as migration 114 does (the report
marks it `seeded`), clears `memory_idf_lexemes` and `memory_idf_documents`,
stamps the live key, advances each corpus epoch, and recomputes every chunk and
summary through the trigger's own `sync_memory_idf_document`. It commits only
if each corpus keeps its document count (a seeded corpus starts at 0 and must
reach the documents the trigger admits) and carries the live key; otherwise it
rolls back, reports the database as `failed`, and exits non-zero. A database
without `memory_idf_corpora` is refused, naming the migration runner. A
connection lost during COMMIT is `commit_unknown` (exit non-zero), never a
rollback: the outcome is unknown, `--dry-run` shows the current keys and
counts, and re-running the rebuild is safe because it recomputes the
projection idempotently. It is the one mutation a replay after
`AmbiguousCommit` is allowed for; narrative commits are never replayed
(above). The report gives each corpus's key
and document count before and after, and the number of lexemes whose row
differs from the pre-rebuild state (added, dropped, or given a new frequency;
each counts once), which is a diagnostic, not a failure. `--dry-run` reads
keys and counts in a read-only session and changes nothing (a locked slot is
skipped without `--write-locked-slot`, as in the runner); `--json` prints the
report as JSON.

After a PostgreSQL update:

```bash
python scripts/rebuild_memory_idf.py --all --dry-run
python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot --dry-run
python scripts/rebuild_memory_idf.py --all
python scripts/rebuild_memory_idf.py --slot 1 --write-locked-slot
```

## Two Clocks

PostgreSQL comments define both clocks; read them with `\d+ chunk_metadata`, `\df+ refresh_world_time_from_chunk*` and `\dd trg_chunk_metadata_refresh_world_time`. The story clock is `chunk_metadata.world_time`, recomputed by `refresh_world_time_from_chunk()` from `global_variables.base_timestamp` and primary-layer `time_delta` after every insert and every `time_delta` or `world_layer` update; event occurrence time is `world_events.world_time`. Diegetic state belongs on the story clock. The tick clock is the accepted chunk in each `tick_chunk_id` column; it serves ordering, replay, exposure fairness, habituation, and narration cadence.

## Schema Documentation

PostgreSQL comments are the schema reference (`\d+` in psql or
`MEMNON.get_schema_summary`); add a non-empty `COMMENT ON` with each new table,
table column, enum, function, and view. The PostgreSQL-gated
`tests/test_schema_documentation_pg.py` ratchet checks five object kinds that
NEXUS owns in `public` and `assets`: tables (`table:<schema>.<name>`), table
columns (`column:<schema>.<table>.<name>`), enums (`enum:<schema>.<name>`),
functions and procedures, trigger functions included
(`function:<schema>.<name>(<identity arguments>)`, so each overload has its own
key), and views and materialized views (`view:<schema>.<name>`). A view is
documented at the view level: its `COMMENT ON VIEW` (or `MATERIALIZED VIEW`) is
required, comments on its columns are not, because view DDL declares no column
list for the offline lint below to check. Extension members (PostGIS, pgvector)
are excluded through `pg_depend` (`deptype = 'e'`) in each object's own catalog,
not by name. Legacy debt is listed by that key and a
one-line reason in `config/schema_docs_baseline.json`. To retire an entry,
establish its contract from reader/writer code, cite that evidence in the comment
migration, add the comment, and remove the baseline entry in the same change; a
dropped object's entry is removed with the drop. The ratchet fails on a new
undocumented object of any kind, on a baseline entry whose object is now
documented, and on a baseline key that names no object, so the list only shrinks.
Run with `NEXUS_RUN_POSTGRES=1`; the test migrates disposable template clones and
proves that schema-only dumps and the actual new-story setup preserve table,
column, enum, function, and view comments.

New migrations are also checked offline, before any database exists.
`scripts/check_migration_comments.py` (pre-commit hook `check-migration-comments`
and the `migration-comment-check.yml` CI workflow) requires every table, foreign
table (documented with `COMMENT ON FOREIGN TABLE`), column, enum, function,
procedure, view, and materialized view that a migration numbered
above its watermark (129) creates or replaces, including DDL in DO blocks, `EXECUTE`
commands, and Python migration strings, to have a non-blank `COMMENT ON` in the
same file. `CREATE OR REPLACE` counts as a change, so the migration restates the
comment even though PostgreSQL would keep the old one. Unqualified names mean
`public`, or the schema a `CREATE SCHEMA` statement creates for its own elements.
Functions and procedures match by name and argument types, as PostgreSQL resolves
a routine comment: parameter names, modes, `DEFAULT` clauses, type modifiers, and
array bounds are ignored, `OUT` arguments may be omitted (a function comment omits
them unless it marks them `OUT`), unquoted words fold to lower case, and built-in
type aliases read as one type, so `int` matches `integer` and `varchar(20)` matches
`character varying`. A comment without an argument list names the one overload of
its kind that the migration creates; a comment that matches several overloads
documents none. What cannot be read statically fails rather
than passes: verbs, object kinds, names, and `ALTER TABLE` actions built at
run time (f-strings, `+` or `||` with a non-literal operand, `{}` and `%I`
placeholders), an `EXECUTE` of a variable or of anything not starting with literal
text, columns a statement does not list (`AS` without a column list,
`PARTITION OF`, `INHERITS`, or `LIKE` unless its options, applied left to right,
include `COMMENTS`), `IMPORT FOREIGN SCHEMA`, and `SELECT ... INTO` outside a DO
body (an `into` after `.` or `AS` is a column or alias name, and `TEMP`,
`TEMPORARY`, `UNLOGGED`, `GLOBAL`, or `LOCAL` after `INTO` is the target's name
unless a name follows it, so `SELECT 1 INTO temp FROM ...` is reported; more
than 64 nested `WITH` lists are reported as SQL the lint cannot parse; as a
PL/pgSQL statement in a DO body it assigns a variable; an `EXECUTE`
command is still checked; `EXPLAIN` of it, with or without `ANALYZE`, is
reported although a plain `EXPLAIN` creates nothing, because the lint does not
model which `EXPLAIN` forms execute and no migration should `EXPLAIN`, except
that `EXPLAIN (` is always read as an option list, so an `EXPLAIN` whose
statement opens with a parenthesis passes, since without `ANALYZE` it cannot
execute; and
`PREPARE` of it is reported because a later `EXECUTE` runs it). Not covered: domains, composite types,
triggers, indexes, sequences, `ALTER FOREIGN TABLE ... ADD COLUMN`, DDL inside a
function body, even when the migration calls
that function, and SQL a Python migration does not spell as a string literal in
its own file (an imported constant such as `from nexus.x import DDL;
cur.execute(DDL)`, names joined only at run time such as `cur.execute(A + B)`, a
file it reads, or a bytes literal). Legacy enums, functions, and views are
enforced by the PostgreSQL ratchet above through their entries in
`config/schema_docs_baseline.json`.
