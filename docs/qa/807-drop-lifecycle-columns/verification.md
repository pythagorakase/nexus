# Verification: Retire the Chunk Lifecycle Columns (#807, Slice B)

Branch `claude/807-drop-lifecycle-columns`, cut from `origin/main` at
`588fc543` (slice A, PR #1012). Migration 134 drops `narrative_chunks.state`,
`finalized_at`, and `regeneration_count`. Migration 133 was already on main
(the IDF rebuild, PR #1014); no open PR or remote branch carries a `134_` file.

## Evidence the Columns Carry No Lifecycle

Read-only SQL on 2026-09-29, before any change:

| Database | `state` counts | `finalized_at` set | `regeneration_count <> 0` | View or matview dependents |
| --- | --- | --- | --- | --- |
| `NEXUS_template` | none (empty) | 0 | 0 | 0 |
| `save_01` | `draft` 1,425 | 0 | 0 | 0 |
| `save_02` | `draft` 1,425 | 0 | 0 | 0 |
| `save_03` | `draft` 39, `finalized` 1 (id 1, the prologue marker) | 1 | 0 | 0 |
| `save_04` | `draft` 45, `finalized` 1 (id 1, the prologue marker) | 1 | 0 | 0 |
| `save_05` | none (empty) | 0 | 0 | 0 |

The dependents column uses the same `pg_depend` / `pg_rewrite` / `pg_class` /
`pg_attribute` join as the migration's guard. No function body on the
template mentions `finalized`, `regeneration_count`, or `state` next to
`narrative_chunks` (`pg_proc.prosrc` search), and `pg_views` has no match.

The only `'finalized'` writer was the Retrograde prologue insert
(`nexus/agents/orrery/retrograde_persistence.py:2547-2549` at `588fc543`).
The only other writer was `scripts/qa_shift/card_identity_probe.py:323`,
which wrote `'accepted'`.

## Code Changes

- `migrations/134_drop_chunk_lifecycle_columns.sql`: a `DO` block raises
  and names each view or materialized view that depends on the columns; then
  one `ALTER TABLE ... DROP COLUMN` for the three columns.
- Writers: `_insert_prologue_chunk` and the card-identity QA probe no longer
  name the columns.
- Tests that inserted the columns stop doing so:
  `test_presence_boost_pg.py`, `test_orrery/test_retrograde_retrieval_pg.py`,
  `test_orrery/test_acquisition_scan_pg.py`, `test_orrery/test_card_identity.py`,
  `test_api/test_orrery_config_reuse_pg.py`, `test_api/test_narrative_retry_pg.py`,
  `test_api/test_narrative_continue_validation.py`.
- `test_orrery/test_retrograde_persistence.py`: the prologue test asserts
  `playable_narrative_predicate` (prologue false, accepted rows true) and that
  the three columns are absent, instead of `state` values.
- `test_orrery/test_retrograde_summary_migration_pg.py`: migration 078 is
  historical and ran while the columns existed; it still requires `state`
  for its legacy copy and recreates it on an empty table. The fixture reads
  the clone's own `schema_migrations` stamp and takes one of two explicit
  branches (definitions from migrations 018 and 021). A clone that stamped
  134 gets a strict `ADD COLUMN` for the three columns. A clone that did not
  must already carry exactly `character varying(20)` / `'draft'`,
  `timestamp with time zone` / no default, and `integer` / `0`, or the
  fixture raises. The legacy seeds and every 078 guard test then run against
  the schema 078 met; each test rewinds 078's own artifacts with
  `_drop_migration_targets`.
- New `tests/test_chunk_lifecycle_columns_migration_pg.py`: on a disposable
  template clone, restores the columns, unstamps 134, adds a hand-made view
  and materialized view, and runs the real `migrate.migrate_database`. The
  run fails with both names in the error and leaves the columns; after the
  views are dropped, the runner applies 134 and stamps it.
- Docs: `docs/orrery_retrograde_spec.md` states that the prologue is
  identified by its `authorial_directives` marker, not a state column;
  `nexus/docs/idf_dictionary.md` no longer mentions `state = 'finalized'`.

Remaining grep hits for the column names are historical migrations (018, 021,
078), `docs/qa/807-*` evidence, the 078 test fixture above, the new migration
and test, the absence assertion in
`tests/test_orrery/test_retrograde_persistence.py:1325`, and the historical
`docs/qa/909-long-absence-probe/live/*` captures, which are frozen evidence
and stay unchanged.

## Migration on a Template Clone

```
$ createdb -T NEXUS_template qa640_807_tpl134
$ PYTHONPATH=$PWD $PY scripts/migrate.py --dbname qa640_807_tpl134
INFO Migrating qa640_807_tpl134...
INFO   Applied: 134_drop_chunk_lifecycle_columns
INFO
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_807_tpl134: 131 migration stamps; level 134

$ psql -d qa640_807_tpl134 -c '\d narrative_chunks'
                                             Table "public.narrative_chunks"
         Column         |           Type           | Collation | Nullable |                   Default
------------------------+--------------------------+-----------+----------+----------------------------------------------
 id                     | bigint                   |           | not null | nextval('narrative_chunks_id_seq'::regclass)
 raw_text               | text                     |           | not null |
 created_at             | timestamp with time zone |           |          | now()
 embedding_generated_at | timestamp with time zone |           |          |
 storyteller_text       | text                     |           |          |
 choice_object          | jsonb                    |           |          |
 choice_text            | text                     |           |          |
 authorial_directives   | jsonb                    |           | not null | '[]'::jsonb
 orrery_proposal        | jsonb                    |           |          |
```

Data clones through `tests/pg_fixtures.disposable_slot_database(include_data=True)`
(pg_dump of the slot, restore, runner):

```
save_02 -> clone: level=134 rows 1425->1425 columns=['id', 'raw_text', 'created_at', 'embedding_generated_at', 'storyteller_text', 'choice_object', 'choice_text', 'authorial_directives', 'orrery_proposal']
save_04 -> clone: level=134 rows 46->46 columns=['id', 'raw_text', 'created_at', 'embedding_generated_at', 'storyteller_text', 'choice_object', 'choice_text', 'authorial_directives', 'orrery_proposal']
```

## Fleet Untouched

Filtered to the database headers and pending lines (the unfiltered output is
669 lines, mostly `[x]` stamps):

```
$ PYTHONPATH=$PWD $PY scripts/migrate.py --status 2>&1 | grep -E '^[A-Za-z]|LOCKED|\[ \]'
Found 131 managed migrations in <worktree>/migrations
NEXUS_template:
  [ ] 134_drop_chunk_lifecycle_columns
save_01: [LOCKED]
save_02:
  [ ] 134_drop_chunk_lifecycle_columns
save_03:
  [ ] 134_drop_chunk_lifecycle_columns
save_04:
  [ ] 134_drop_chunk_lifecycle_columns
save_05:
  [ ] 134_drop_chunk_lifecycle_columns
```

`--status` prints only `[LOCKED]` for `save_01`, so its level and columns
come from read-only SQL. Every fleet database is at level 133 and still has
all three columns:

```
$ for db in NEXUS_template save_01 save_02 save_03 save_04 save_05; do
    echo "== $db"
    psql -d $db -Atc "select max(version::int) from schema_migrations"
    psql -d $db -Atc "select column_name, data_type, column_default
      from information_schema.columns where table_schema='public'
      and table_name='narrative_chunks'
      and column_name in ('state','finalized_at','regeneration_count')
      order by column_name"
  done
== NEXUS_template
133
finalized_at|timestamp with time zone|
regeneration_count|integer|0
state|character varying|'draft'::character varying
== save_01
133
finalized_at|timestamp with time zone|
regeneration_count|integer|0
state|character varying|'draft'::character varying
== save_02
133
finalized_at|timestamp with time zone|
regeneration_count|integer|0
state|character varying|'draft'::character varying
== save_03
133
finalized_at|timestamp with time zone|
regeneration_count|integer|0
state|character varying|'draft'::character varying
== save_04
133
finalized_at|timestamp with time zone|
regeneration_count|integer|0
state|character varying|'draft'::character varying
== save_05
133
finalized_at|timestamp with time zone|
regeneration_count|integer|0
state|character varying|'draft'::character varying
```

The coordinator applies 134 at land time, `save_01` through
`--write-locked-slot`.

## Gates

PostgreSQL proof set (the order's list), `NEXUS_GATEWAY_PORT` and
`NEXUS_API_URL` unset, against the live (pre-134) template:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_presence_boost_pg.py tests/test_orrery/test_retrograde_retrieval_pg.py tests/test_orrery/test_acquisition_scan_pg.py tests/test_orrery/test_retrograde_summary_migration_pg.py tests/test_orrery/test_retrograde_persistence.py tests/test_schema_documentation_pg.py -p no:warnings
........................................................                 [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
56 passed in 17.32s
```

Post-land simulation: `"NEXUS_template"` replaced by the migrated
`qa640_807_tpl134` across `tests/` (uncommitted, reverted with
`git checkout -- tests` afterward), so fixtures that clone the template
directly see the post-134 schema:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings <proof set> tests/test_chunk_lifecycle_columns_migration_pg.py tests/test_api/test_narrative_continue_validation.py tests/test_api/test_narrative_retry_pg.py tests/test_api/test_orrery_config_reuse_pg.py tests/test_orrery/test_card_identity.py
FAILED tests/test_api/test_narrative_retry_pg.py::test_staging_failure_resumes_as_recovery_and_retries_once
FAILED tests/test_api/test_narrative_retry_pg.py::test_dead_worker_is_advertised_exactly_as_retry_accepts_it
FAILED tests/test_api/test_narrative_retry_pg.py::test_restart_reopens_the_menu_when_no_retry_can_resume
3 failed, 115 passed in 66.09s (0:01:06)
```

The three `test_narrative_retry_pg.py` failures are pre-existing: the same
three fail identically on an export of `588fc543` (`git archive`, run with its
own `PYTHONPATH`), with
`psycopg2.ProgrammingError: the connection cannot be re-entered recursively`
at `nexus/api/choice_recovery.py:68`. They do not touch the dropped columns.

The 078 fixture's two branches, after the review fix (commit `1effefba`).
Unstamped branch, against the live pre-134 template:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings tests/test_orrery/test_retrograde_summary_migration_pg.py
13 passed in 3.34s
```

Stamped branch: `createdb -T NEXUS_template qa640_807b_tpl134`, the runner
applied 134 (`level 134`), and the file's template name was swapped to that
clone (uncommitted, reverted with `git checkout`):

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:warnings tests/test_orrery/test_retrograde_summary_migration_pg.py
13 passed in 3.55s
```

Drift check: on an unstamped template clone with
`regeneration_count` default set to `1`, the helper raises:

```
AssertionError: Template clone has not stamped migration 134 but its lifecycle columns differ from the pre-134 definitions: expected {'state': ('character varying(20)', "'draft'::character varying"), 'finalized_at': ('timestamp with time zone', None), 'regeneration_count': ('integer', '0')}, found {'finalized_at': ('timestamp with time zone', None), 'regeneration_count': ('integer', '1'), 'state': ('character varying(20)', "'draft'::character varying")}
```

Both `qa640_807b_*` clones were dropped afterward.

Offline gate:

```
$ $PY -m pytest -q -p no:warnings
secret-store guard: active; nexus-api: denied; disposable keychain: denied
4101 passed, 1044 skipped in 285.02s (0:04:45)
```

Reachability, formatting, lint, types:

```
$ $PY -m pytest -q -p no:warnings tests/test_reachability.py
38 passed in 8.45s
$ $PY -m black --check <changed .py files>
12 files would be left unchanged.
```

flake8 and mypy (`--explicit-package-bases --ignore-missing-imports
--follow-imports=silent`) on the changed `.py` files report the same findings
as on `588fc543` (line numbers stripped, diffed): no new finding; two
pre-existing E501 lines got shorter but remain over 88.
