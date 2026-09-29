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
template's own `applied_at` (copied, never re-applied), and the only other
stamps are the migrations the template has not seen. Those two assertions are
the proof. The follow-up `migrate_database(clone) == (0, 0)` is an idempotence
check only: initialization already raises on any unapplied migration, so a
second pass must return `(0, 0)`.

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

`test_template_clone_first_runner_pass_applies_nothing` makes the first
runner pass itself observable, independent of fleet lag. It builds a `tmp_path`
tree that holds only the migration files whose versions `NEXUS_template` has
stamped, then runs `initialize_slot_database(<disposable>, force=True,
migrations_dir=tree)` on a database made directly (not through the fixture).
The clone's stamps equal the template's stamps, with identical `applied_at`:
the first pass applied nothing. With the filter disabled (the full tree), the
same test fails because the clone gains stamps 128-132 with fresh `applied_at`:

```
E             Left contains 5 more items:
E             {'128': datetime.datetime(2026, 9, 29, 17, 1, 16, 479802, tzinfo=datetime.timezone.utc),
E              '129': datetime.datetime(2026, 9, 29, 17, 1, 16, 482769, tzinfo=datetime.timezone.utc),
```

## Proof 2: A Failing Migration Is Unapplied and Initialization Raises

`test_failing_migration_is_unapplied_and_initialization_raises` copies the real
tree to `tmp_path`, adds `999_fail_loudly.sql` (`SELECT 1/0;` after a header),
and runs the real runner on a real template clone:
`migrate_database(clone, migrations_dir=tree) == (0, 1)`, no `999` stamp. Then
`initialize_slot_database(clone, force=True, migrations_dir=tree)` raises
`RuntimeError: Migrations failed on <db>: 5 applied, 1 unapplied. ...`, still
no `999` stamp, and `memory_idf_corpora` is empty (the raise precedes the
fresh-slot IDF corpora and the "ready" log line). The fresh-story
`global_variables` row is written before the migrations run, because a pending
migration may expect it; the raise does not undo that row.

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

Rerun after the review fixes (one new test,
`test_template_clone_first_runner_pass_applies_nothing`):

```
FAILED tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle
1 failed, 47 passed, 5 warnings in 36.71s
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

Fleet status (read-only), captured after all work including the review fixes.
The `grep` removes only the `[x]` (applied) lines; every header and every `[ ]`
line is verbatim. The template and `save_02..05` each show 128-132 pending;
`save_01` is locked, so the runner does not list its stamps.

```
$ PYTHONPATH=$PWD $PY scripts/migrate.py --status | grep -v '\[x\]'
Found 129 managed migrations in /Users/pythagor/nexus/.claude/worktrees/810-setup-fails-loud/migrations

NEXUS_template:
  [ ] 128_character_identity_rulings
  [ ] 129_wizard_confirmation
  [ ] 130_retire_psychology_endpoint_comments
  [ ] 131_regeneration_lineage
  [ ] 132_genesis_weird_level

save_01: [LOCKED]
  (locked - use --write-locked-slot to apply migrations)
save_02:
  [ ] 128_character_identity_rulings
  [ ] 129_wizard_confirmation
  [ ] 130_retire_psychology_endpoint_comments
  [ ] 131_regeneration_lineage
  [ ] 132_genesis_weird_level

save_03:
  [ ] 128_character_identity_rulings
  [ ] 129_wizard_confirmation
  [ ] 130_retire_psychology_endpoint_comments
  [ ] 131_regeneration_lineage
  [ ] 132_genesis_weird_level

save_04:
  [ ] 128_character_identity_rulings
  [ ] 129_wizard_confirmation
  [ ] 130_retire_psychology_endpoint_comments
  [ ] 131_regeneration_lineage
  [ ] 132_genesis_weird_level

save_05:
  [ ] 128_character_identity_rulings
  [ ] 129_wizard_confirmation
  [ ] 130_retire_psychology_endpoint_comments
  [ ] 131_regeneration_lineage
  [ ] 132_genesis_weird_level
```

Per-database stamps (read-only `SELECT`), `save_01` included. Every
`max(applied_at)` is 2026-09-24 20:28-20:29 -04, before this branch's first
commit (`0d315d72`, 2026-09-29 11:52 -05), so no database in the fleet was
written by this work:

```
$ for db in NEXUS_template save_01 save_02 save_03 save_04 save_05; do printf "%s: " $db; \
    psql -X -At -d $db -c "SELECT count(*), max(version), max(applied_at) FROM schema_migrations"; done
NEXUS_template: 124|127|2026-09-24 20:28:59.167323-04
save_01: 124|127|2026-09-24 20:29:00.021847-04
save_02: 124|127|2026-09-24 20:28:59.285609-04
save_03: 124|127|2026-09-24 20:28:59.357078-04
save_04: 124|127|2026-09-24 20:28:59.428947-04
save_05: 124|127|2026-09-24 20:28:59.499842-04
```

Reachability, Black, flake8, mypy on changed files:

```
$ $PY -m pytest -q tests/test_reachability.py
38 passed in 10.21s
$ $PY -m black --check scripts/migrate.py scripts/new_story_setup.py tests/pg_fixtures.py tests/test_new_story_setup.py
All done! ✨ 🍰 ✨
4 files would be left unchanged.
$ $PY -m flake8 scripts/migrate.py scripts/new_story_setup.py tests/pg_fixtures.py tests/test_new_story_setup.py
scripts/migrate.py:185:89: E501 line too long (94 > 88 characters)
scripts/migrate.py:206:89: E501 line too long (99 > 88 characters)
scripts/migrate.py:210:89: E501 line too long (92 > 88 characters)
scripts/new_story_setup.py:7:89: E501 line too long (101 > 88 characters)
scripts/new_story_setup.py:50:89: E501 line too long (90 > 88 characters)
scripts/new_story_setup.py:63:89: E501 line too long (91 > 88 characters)
scripts/new_story_setup.py:112:89: E501 line too long (101 > 88 characters)
scripts/new_story_setup.py:203:89: E501 line too long (96 > 88 characters)
scripts/new_story_setup.py:303:89: E501 line too long (90 > 88 characters)
scripts/new_story_setup.py:512:89: E501 line too long (116 > 88 characters)
$ $PY -m mypy --explicit-package-bases scripts/migrate.py scripts/new_story_setup.py tests/pg_fixtures.py tests/test_new_story_setup.py
tests/test_new_story_setup.py:178: error: Value of type "Item | Container" is not indexable  [index]
tests/test_new_story_setup.py:178: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
tests/test_new_story_setup.py:203: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
tests/test_new_story_setup.py:205: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
Found 4 errors in 1 file (checked 4 source files)
```

The same tools on the `origin/main` versions of the four files, for comparison.
Each file was written with `git show origin/main:<path>` into a scratch copy
`<origin/main>/` (the repository's `.flake8` copied beside it for flake8; mypy
run from the worktree root so `nexus` resolves as it does above). Every E501
above has an identical line on `origin/main`, shifted only by the lines this
branch added or removed; the two F401s are the imports this branch removed.
The four mypy errors are the same four, in `test_fresh_database_is_baseline_stamped`
(`origin/main` lines 165/190/192 are branch lines 178/203/205):

```
$ (cd <origin/main> && $PY -m flake8 scripts/migrate.py scripts/new_story_setup.py tests/pg_fixtures.py tests/test_new_story_setup.py)
scripts/migrate.py:24:1: F401 'os' imported but unused
scripts/migrate.py:29:1: F401 'typing.Optional' imported but unused
scripts/migrate.py:185:89: E501 line too long (94 > 88 characters)
scripts/migrate.py:205:89: E501 line too long (99 > 88 characters)
scripts/migrate.py:209:89: E501 line too long (92 > 88 characters)
scripts/new_story_setup.py:7:89: E501 line too long (101 > 88 characters)
scripts/new_story_setup.py:56:89: E501 line too long (90 > 88 characters)
scripts/new_story_setup.py:69:89: E501 line too long (91 > 88 characters)
scripts/new_story_setup.py:118:89: E501 line too long (101 > 88 characters)
scripts/new_story_setup.py:199:89: E501 line too long (96 > 88 characters)
scripts/new_story_setup.py:298:89: E501 line too long (90 > 88 characters)
scripts/new_story_setup.py:478:89: E501 line too long (116 > 88 characters)
$ $PY -m mypy --explicit-package-bases <origin/main>/scripts/migrate.py <origin/main>/scripts/new_story_setup.py <origin/main>/tests/pg_fixtures.py <origin/main>/tests/test_new_story_setup.py
<origin/main>/tests/test_new_story_setup.py:165: error: Value of type "Item | Container" is not indexable  [index]
<origin/main>/tests/test_new_story_setup.py:165: error: Unsupported target for indexed assignment ("Any | Item | Container")  [index]
<origin/main>/tests/test_new_story_setup.py:190: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
<origin/main>/tests/test_new_story_setup.py:192: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
Found 4 errors in 1 file (checked 4 source files)
```
