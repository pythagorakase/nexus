# Slot Setup Fails Loudly: Verification

## Scope

Work order 810/823 (hardening slice), branch `claude/810-setup-fails-loud`, cut
from `origin/main` at `9a67e864`. No migration, no gateway lane, no paid calls.
Every hand-created database uses the `qa640_` prefix and was dropped afterward;
`NEXUS_template`, `save_01`, and `save_02` were only read (`pg_dump`, `SELECT`).
No migration was applied to the template or any save.

## Before This Change

- `scripts/new_story_setup.py:41-46` imported the runner in `try/except
  ImportError` (`HAS_MIGRATE`); `:268-280` logged a warning on a failed or
  missing runner, then ran `_initialize_empty_idf_corpora` and logged
  "Database ... ready".
- `scripts/migrate.py:397-399` caught `psycopg2.Error` on connect and returned
  `(0, 0)`, which every caller read as "nothing pending". `db_exists`
  (`:153-164`) and `is_db_locked` (`:123-150`) also swallowed connection errors
  (returning "does not exist" and "unlocked").
- `clone_slot_with_data` (`scripts/new_story_setup.py:377-450`) called bare
  `dropdb`/`createdb`/`pg_dump`/`psql`, ran `dropdb` with `check=False`, and
  restored with `psql target -f dump` without `ON_ERROR_STOP`.

## Proof 1: Template Clone Replays No Migration

`tests/test_new_story_setup.py::test_template_clone_replays_no_migration` builds
a clone of `NEXUS_template` through `tests.pg_fixtures.disposable_slot_database`
(which calls `initialize_slot_database`). Every template stamp arrives with the
template's own `applied_at` (copied, never re-applied); the only other stamps
are the migrations the template has not seen; a follow-up
`migrate_database(clone)` returns `(0, 0)`.

The fleet template currently lags `main` by 128-132 (land-time migrations), so
initialization applies exactly those five and nothing earlier:

```
INFO     nexus.migrate:migrate.py:406 Migrating qa640_810_clone_927a2709a9bf...
INFO     nexus.migrate:migrate.py:362   Applied: 128_character_identity_rulings
INFO     nexus.migrate:migrate.py:362   Applied: 129_wizard_confirmation
INFO     nexus.migrate:migrate.py:362   Applied: 130_retire_psychology_endpoint_comments
INFO     nexus.migrate:migrate.py:362   Applied: 131_regeneration_lineage
INFO     nexus.migrate:migrate.py:362   Applied: 132_genesis_weird_level
INFO     nexus.new_story_setup:new_story_setup.py:282 Applied 5 migrations to qa640_810_clone_927a2709a9bf
INFO     nexus.new_story_setup:new_story_setup.py:286 Database qa640_810_clone_927a2709a9bf ready
INFO     nexus.migrate:migrate.py:406 Migrating qa640_810_clone_927a2709a9bf...
INFO     nexus.migrate:migrate.py:445   No pending migrations
```

## Proof 2: A Failing Migration Is Unapplied and Initialization Raises

`test_failing_migration_is_unapplied_and_initialization_raises` copies the real
tree to `tmp_path`, adds `999_fail_loudly.sql` (`SELECT 1/0;` after a header),
and runs the real runner on a real template clone:
`migrate_database(clone, migrations_dir=tree) == (0, 1)`, no `999` stamp. Then
`initialize_slot_database(clone, force=True, migrations_dir=tree)` raises
`RuntimeError: Migrations failed on <db>: 5 applied, 1 unapplied. ...`, still
no `999` stamp, and `memory_idf_corpora` is empty (the raise precedes the
fresh-story seeding and the "ready" log line).

```
INFO     nexus.migrate:migrate.py:406 Migrating qa640_810_fail_f5af830c5fec...
ERROR    nexus.migrate:migrate.py:368   FAILED: 999_fail_loudly - division by zero
INFO     nexus.new_story_setup:new_story_setup.py:272 Running migrations on qa640_810_fail_f5af830c5fec...
INFO     nexus.migrate:migrate.py:406 Migrating qa640_810_fail_f5af830c5fec...
INFO     nexus.migrate:migrate.py:362   Applied: 128_character_identity_rulings
...
INFO     nexus.migrate:migrate.py:362   Applied: 132_genesis_weird_level
ERROR    nexus.migrate:migrate.py:368   FAILED: 999_fail_loudly - division by zero
```

## Proof 3: Plain-Dump Restore Stops at the First Error

`test_restore_plain_dump_stops_at_first_error`: `_restore_plain_dump` on an
empty disposable database with a dump whose second statement inserts into a
missing table raises `subprocess.CalledProcessError`; the third statement's
table never exists. A valid two-statement dump succeeds and leaves both effects
(`restore_ok` holds `7`).

`test_clone_with_data_restores_template_into_disposable_target` runs the whole
`clone_slot_with_data(5, source_db="NEXUS_template", force=True,
target_db=<disposable>)` under `ON_ERROR_STOP`; the clone carries the template's
exact stamps and `new_story = true`.

Real-slot evidence (ad hoc, read-only sources, disposable targets dropped): the
stricter restore still clones the owner's populated slots cleanly.

```
save_02: narrative_chunks=1425 schema_migrations=(124, '127')
qa640_810_evidence_a29e0b7e: narrative_chunks=1425 schema_migrations=(124, '127')
dropped qa640_810_evidence_a29e0b7e
save_01: narrative_chunks=1425 schema_migrations=(124, '127')
qa640_810_evidence_a2853712: narrative_chunks=1425 schema_migrations=(124, '127')
dropped qa640_810_evidence_a2853712
```

## Proof 4: Connection Errors Propagate

`test_migrate_database_propagates_connection_errors`:
`migrate_database("qa640_does_not_exist_<hex>")` still returns `(0, 0)` through
the `db_exists` branch. On an existing disposable database set to
`ALLOW_CONNECTIONS false`, `migrate_database` raises `psycopg2.Error`
(`ALLOW_CONNECTIONS true` is restored before the drop).

## Mutation Check

With the old behavior temporarily restored (the connect `try/except` returning
`(0, 0)`, and the new `RuntimeError` disabled), both new failure proofs fail,
then the files were restored byte for byte:

```
E           Failed: DID NOT RAISE <class 'RuntimeError'>
E                   Failed: DID NOT RAISE <class 'psycopg2.Error'>
ERROR    nexus.migrate:migrate.py:414 Cannot connect to qa640_810_noconn_ddfa753beeb8: connection to server on socket "/tmp/.s.PGSQL.5432" failed: FATAL:  database "qa640_810_noconn_ddfa753beeb8" is not currently accepting connections
2 failed, 5 deselected in 3.16s
```

## `scripts/migrate_slots.sql` Disposition

Deleted. `git grep -n migrate_slots origin/main` returns nothing (exit 1). It
was added in `bdebff46` (2025-11-23), three days before the migration runner
(`aebc6294`, #118). Relative to `migrations/003_add_layer_zone_drafts.sql` it
had no header or `COMMENT ON` lines and one extra column: it added
`layer_draft`, `zone_draft`, **and** `initial_location` (all `JSONB`, `IF NOT
EXISTS`) to `assets.new_story_creator`, where 003 adds only `layer_draft` and
`zone_draft`. `initial_location` is created and commented by
`migrations/007_normalize_new_story_creator.sql:138,176`, so nothing is lost.

## Gates

All commands ran from the worktree root with `NEXUS_GATEWAY_PORT` and
`NEXUS_API_URL` unset.

PostgreSQL gate for the touched modules:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_new_story_setup.py tests/test_postgres_tools.py tests/test_database_contract.py tests/test_connection_lifecycle.py tests/test_schema_documentation_pg.py
FAILED tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
1 failed, 46 passed in 32.38s
```

The one failure is pre-existing and outside this change: the lifecycle fixture
restores the fleet template's schema, hand-applies only migration 123, and then
the CLI hits `column nsc.setting_confirmed does not exist` (migration 129, which
the fleet template has not received). It fails identically with
`scripts/migrate.py`, `scripts/new_story_setup.py`, and `tests/pg_fixtures.py`
temporarily reset to `origin/main` (`1 failed in 8.71s`).

Offline gate:

```
$ $PY -m pytest -q
FAILED tests/test_skald_wire.py::test_state_authoring_documents_share_core_invariants
1 failed, 4039 passed, 1053 skipped in 314.62s (0:05:14)
```

The one failure is pre-existing and outside this change: `prompts/storyteller_gaia.md`
no longer contains the phrase "rather than invent" that the test pins. This
branch touches no prompt or that test.

Fleet status (read-only) after all work, unchanged from before it: the template
and `save_02..05` show the same five land-time migrations pending (128-132)
that they showed before this branch ran anything; `save_01` is locked.

```
$ PYTHONPATH=$PWD $PY scripts/migrate.py --status | grep -v '\[x\]'
NEXUS_template:
  [ ] 128_character_identity_rulings
  [ ] 129_wizard_confirmation
  [ ] 130_retire_psychology_endpoint_comments
  [ ] 131_regeneration_lineage
  [ ] 132_genesis_weird_level
save_01: [LOCKED]
save_02 .. save_05: the same five pending
```

Reachability, Black, flake8, mypy on changed files:

```
$ $PY -m pytest -q tests/test_reachability.py
38 passed in 10.21s
$ $PY -m black --check scripts/migrate.py scripts/new_story_setup.py tests/pg_fixtures.py tests/test_new_story_setup.py
4 files would be left unchanged.
$ $PY -m flake8 scripts/migrate.py scripts/new_story_setup.py tests/pg_fixtures.py tests/test_new_story_setup.py
(10 E501 findings, all on lines this branch did not write; origin/main has the same
lines plus two F401s this branch removed)
$ $PY -m mypy --explicit-package-bases scripts/migrate.py scripts/new_story_setup.py tests/pg_fixtures.py tests/test_new_story_setup.py
Found 4 errors in 1 file (checked 4 source files)
(all 4 in pre-existing lines of test_fresh_database_is_baseline_stamped; origin/main's
file reports the same 4)
```
