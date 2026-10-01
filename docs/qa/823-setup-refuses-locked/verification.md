# Verification: Standalone Slot Setup Refuses Locked Slots (#823, Slice S0)

Work order 823-S0. No migration, no paid call, no gateway lane. Nothing in
this run wrote to any `save_NN` or `NEXUS_template`, and
`scripts/new_story_setup.py` was never run against a slot.

## What Was Wrong (Cited at `origin/main` a4c2be8d; Unchanged at f8dd073c)

The line citations hold at both commits: #1070 (f8dd073c) adds new files and
edits none of the files cited here.

- `initialize_slot_database` (`scripts/new_story_setup.py:164-286`) terminated
  the target's sessions and ran `dropdb --if-exists` when `force` was set
  (lines 192-210). It never read the lock.
- `clone_slot_with_data` (lines 397-481) ran `dropdb --if-exists` when `force`
  was set (lines 419-425). It never read the lock.
- `main` (lines 494-537) sent `--slot N --force` to `create_slot_schema_only`
  (line 537, which calls `initialize_slot_database` at line 136) or to
  `clone_slot_with_data` (line 535). No path read the lock.
- The lock is `default_transaction_read_only=on` on the database
  (`nexus/api/save_slots.py:160-201`). It blocks writes inside the database;
  `dropdb` connects to another database, so the setting does not stop it.
- `reset_setup` already refuses a locked slot before any change
  (`nexus/api/new_story_flow.py:689-693`) with
  `Slot N is locked. Unlock it first with: nexus unlock --slot N`, raised as
  `ValueError`, through `is_slot_locked` (`nexus/api/save_slots.py:123-157`),
  which uses `dbname` when one is given (line 136) and returns `False` for a
  database with no setting or no row (line 155). It then reaches
  `initialize_slot_database` through `create_slot_schema_only(..., force=True)`
  (line 702).
- `start_setup` calls `create_slot_schema_only` without `force` only when the
  connection to the slot fails (`nexus/api/new_story_flow.py:126-134`), so its
  target never exists and reads as unlocked; this change does not alter it.
- Routing contract: `route_slots_to_disposable` replaces
  `slot_utils.VALID_DBNAMES` with the clone names (`tests/pg_fixtures.py:467`),
  and `tests/test_scheduler_helpers_routing.py:84` asserts it, so the slot-name
  test is the fixed pattern `save_0([1-5])`, not `VALID_DBNAMES`.

## The Change (Branch `claude/823-setup-refuses-locked`)

- `_locked_target_message` (`scripts/new_story_setup.py:166`) returns reset's
  text for a `save_0N` name and a database text with no `nexus unlock` hint for
  any other name.
- `_refuse_locked_target` (`scripts/new_story_setup.py:184`) calls
  `is_slot_locked(..., dbname=target_db)` and raises `ValueError` with that text.
- `initialize_slot_database` calls it at line 229, after `_postgres_tools` and
  before `if force:` (line 231; session termination and `dropdb` follow,
  through line 249).
- `clone_slot_with_data` calls it at line 460, after `_postgres_tools` and
  before `dispose_database` and `dropdb` (line 465).
- No override flag. `--force` help now reads
  `Drop and recreate the target slot database if it exists; a locked slot is refused`.

## Lock State Read Before the Run (Read-Only)

```
$ PGOPTIONS='-c default_transaction_read_only=on' psql -d postgres -Atc "SELECT d.datname, s.setconfig FROM pg_db_role_setting s JOIN pg_database d ON d.oid = s.setdatabase WHERE s.setrole = 0"
save_01|{default_transaction_read_only=on}
ref_codex_bakeoff_2026_07|{default_transaction_read_only=on}
```

## Green Run (at ab67ce91, After the Rebase Onto f8dd073c)

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py tests/test_postgres_tools.py tests/test_api/test_slot_mutation_guard.py tests/test_owner_target_guard.py tests/test_scheduler_helpers_routing.py
(NEXUS_GATEWAY_PORT, NEXUS_API_URL, NEXUS_SLOT unset)
...
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 16 targets: nexus_m10_fresh_test_76344, nexus_m10_template_test_76344, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_823_locked_clone_*, qa640_823_locked_init_*, qa640_823_unlocked_clone_*, qa640_823_unlocked_init_*, qa640_lane_close_*, test_slot_guard_983e3e76a587483fbd9460483a7689c1
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
197 passed, 7 warnings in 22.41s
```

`tests/test_postgres_tools.py::test_missing_tools_abort_before_database_changes`
is in that run, unchanged, and passes: the lock read runs after
`_postgres_tools`.

After the run, no `qa640_823` database remained:

```
$ psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_823%'"
(no rows)
```

## Red Run (Both `_refuse_locked_target(target_db)` Calls Removed, Then Restored)

A scratch plant deleted the two call lines; the file was restored byte for
byte (`cmp` against the saved copy) before any commit.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_new_story_setup.py -k refuses_locked
...
>           assert _database_oid(dbname) == oid
E           AssertionError: assert 158854809 == 158854802
E            +  where 158854809 = _database_oid('qa640_823_locked_init_c51c63a0de70')

tests/test_new_story_setup.py:547: AssertionError
...
>           assert _database_oid(dbname) == oid
E           AssertionError: assert 158867288 == 158866931
E            +  where 158867288 = _database_oid('qa640_823_locked_clone_412bd9d2ae29')

tests/test_new_story_setup.py:571: AssertionError
----------------------------- Captured stdout call -----------------------------
REVOKE
------------------------------ Captured log call -------------------------------
WARNING  nexus.new_story_setup:new_story_setup.py:467 Dropped database qa640_823_locked_clone_412bd9d2ae29 if it existed
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 4 targets: postgres, qa640_810_template_*, qa640_823_locked_clone_*, qa640_823_locked_init_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_new_story_setup.py::test_initialize_refuses_locked_target
FAILED tests/test_new_story_setup.py::test_clone_refuses_locked_target - Asse...
2 failed, 11 deselected in 3.77s
```

Both refusal tests fail on the oid assertion: without the refusal, the locked
target was dropped and recreated (a new oid) even though it was read-only.

## Offline Suites

These runs predate the rebase onto f8dd073c. #1070 touches none of the files
they cover; it only adds new files (its two travel-reachability test files were
not in these runs).

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2665 passed, 425 skipped, 8 warnings in 391.85s (0:06:31)

$ $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1820 passed, 743 skipped, 7 warnings in 34.93s

$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.45s
```

The skips are the PostgreSQL-backed tests, which need `NEXUS_RUN_POSTGRES=1`.

## Lint and Types

- `black --check scripts/new_story_setup.py tests/test_new_story_setup.py`:
  2 files would be left unchanged.
- `flake8 tests/test_new_story_setup.py`: clean. `flake8
  scripts/new_story_setup.py`: seven E501 lines, all present on `origin/main`
  (the same seven at lines 7, 49, 62, 109, 200, 301, 516 there); none is new.
- `mypy scripts/new_story_setup.py tests/test_new_story_setup.py`: four errors,
  all in the existing `test_fresh_database_is_baseline_stamped` (the tomlkit
  index and two `fetchone()[0]`); the same four appear on `origin/main`'s copy
  of the file. `scripts/new_story_setup.py` has none.
