# Migration Lint Table Forms Verification

## Scope

Work order 819-S2, branch `claude/819-lint-table-forms`, cut from `origin/main`
at `41783c1d` (still the tip at push time). Decision 819-Q2 on #819 is applied as written:
parity for `CREATE FOREIGN TABLE`, while `IMPORT FOREIGN SCHEMA` and `SELECT ... INTO` fail as
unsupported. Only `scripts/check_migration_comments.py`, its offline tests,
`docs/database.md`, and this file change. There is no migration, no fleet application, no gateway, and no paid
call. The only database created by hand was the disposable `qa640_819s2`, which
was dropped after the fact check. No test writes to `save_NN` or `NEXUS_template`
(the dbname audit below reports `owner targets: none`).

## PostgreSQL Fact Check: How a Foreign Table Takes a Comment

PostgreSQL 17.11 (Postgres.app), on the disposable `qa640_819s2` database:

```
CREATE FOREIGN DATA WRAPPER qa_fdw;
CREATE FOREIGN DATA WRAPPER
CREATE SERVER qa_srv FOREIGN DATA WRAPPER qa_fdw;
CREATE SERVER
CREATE FOREIGN TABLE ft (id int) SERVER qa_srv;
CREATE FOREIGN TABLE
COMMENT ON TABLE ft IS 'x';
ERROR:  "ft" is not a table
COMMENT ON FOREIGN TABLE ft IS 'x';
COMMENT
SELECT obj_description('ft'::regclass, 'pg_class');
 obj_description
-----------------
 x
(1 row)
```

`dropdb qa640_819s2` followed; a later listing found no `qa640_819s2` database.
So `COMMENT ON TABLE` cannot document a foreign table. The lint therefore
gives a foreign table the obligation kind `foreign table`, which only
`COMMENT ON FOREIGN TABLE` satisfies.

## Probe: Before and After

`130_probe.sql`, kept in the session scratchpad and never committed:

```
CREATE FOREIGN TABLE remote_moods (id int, mood text) SERVER s;
IMPORT FOREIGN SCHEMA remote FROM SERVER s INTO public;
SELECT id, mood INTO mood_snapshot FROM scene_moods;
```

Before (`origin/main` at `41783c1d`), `scripts/check_migration_comments.py --migrations-dir <probe>`:

```
OK: every object created after migration 129 has a comment.
exit 0
```

After (this branch):

```
Found 6 schema documentation finding(s):
  <probe>/130_probe.sql:1: column public.remote_moods.id has no COMMENT ON COLUMN
  <probe>/130_probe.sql:1: column public.remote_moods.mood has no COMMENT ON COLUMN
  <probe>/130_probe.sql:1: foreign table public.remote_moods has no COMMENT ON FOREIGN TABLE
  <probe>/130_probe.sql:2: IMPORT FOREIGN SCHEMA creates foreign tables it does not name; their columns cannot be verified
  <probe>/130_probe.sql:3: SELECT INTO public.mood_snapshot declares no column list; its columns cannot be verified
  <probe>/130_probe.sql:3: table public.mood_snapshot has no COMMENT ON TABLE

New tables, columns, enums, functions, procedures, and views need a non-blank COMMENT ON in the same migration (docs/database.md).
exit 1
```

## History Is Unchanged

`check_migrations(REPO_ROOT / "migrations", watermark=0)`, rendered one finding
per line, was saved before any edit (`hist_before.txt`) and again after the
change (`hist_after.txt`):

```
$ cmp hist_before.txt hist_after.txt; echo "cmp exit $?"
cmp exit 0
     405 hist_before.txt
     405 hist_after.txt
```

PL/pgSQL `SELECT ... INTO` in the DO bodies of migrations 022, 077, 100, 109,
110, 134, and 138 stays silent because the DO-body scanner runs with
`plpgsql=True` (forcing the flag off makes `SELECT INTO` findings appear in
exactly those seven files). The `SELECT ... INTO` in the function bodies of
migrations 114 and 133 is masked as a literal.
`test_every_historical_migration_parses` now asserts that no historical finding
names `SELECT INTO`, `IMPORT FOREIGN SCHEMA`, or `foreign table` (the last
compared case-insensitively, so a `CREATE FOREIGN TABLE` label is caught too).

## The New Tests Fail Without the Change

Each mirror is a copy of `scripts/check_migration_comments.py` and this branch's
test file in the scratchpad, run with
`-k "foreign or import or select_into"`:

| Script under test | Result |
| --- | --- |
| `origin/main` | all 4 new tests fail |
| this branch, with the `plpgsql` early return removed | `test_select_into_fails_like_ctas` fails |
| this branch, without the two new `_PY_SQL_HINT` alternatives | `test_import_foreign_schema_fails_as_unsupported` and `test_select_into_fails_like_ctas` fail |
| this branch, without `FOREIGN` in `_CREATE_MODIFIERS` | `test_run_time_foreign_kind_fails` fails |

## Gates

All commands run from the worktree root with the shared interpreter, with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT` unset.

`python -m pytest -q tests/test_migration_comment_lint.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
36 passed, 5 warnings in 0.75s
```

`python scripts/check_migration_comments.py` (the real tree):

```
OK: every object created after migration 129 has a comment.
exit 0
```

`NEXUS_RUN_POSTGRES=1 python -m pytest -q -p tests.dbname_audit tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
110 passed in 13.86s
```

`python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2629 passed, 419 skipped, 8 warnings in 419.25s (0:06:59)
```

`python -m pytest -q tests/test_api tests/test_orrery`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1816 passed, 742 skipped, 7 warnings in 38.98s
```

`python -m pytest -q tests/test_reachability.py`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.70s
```

Black (`2 files would be left unchanged`), flake8 (exit 0), and mypy
(`Success: no issues found in 2 source files`) on
`scripts/check_migration_comments.py` and `tests/test_migration_comment_lint.py`.

## Review Fixes

Commit `9182a195` applies the review findings: the docstring and
`docs/database.md` list `IMPORT FOREIGN SCHEMA` and `SELECT ... INTO` as
separate failing forms and say that an `EXECUTE` command in a DO body is still
checked; `test_select_into_fails_like_ctas` asserts the unresolvable finding for
`EXECUTE 'SELECT 1 AS id INTO ' || v_name || ' FROM scene_moods'` at its line
(changing the `SELECT INTO` label in `_select_into` makes it fail); and the
historical guard's comment and match were corrected as described above. On
`9182a195`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT` unset:

```
$ python -m pytest -q tests/test_migration_comment_lint.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
36 passed, 5 warnings in 0.72s
$ python scripts/check_migration_comments.py; echo "exit $?"
OK: every object created after migration 129 has a comment.
exit 0
$ cmp hist_fix_before.txt hist_fix_after.txt; echo "cmp exit $?"
cmp exit 0
     405 hist_fix_before.txt
     405 hist_fix_after.txt
```

`hist_fix_before.txt` was saved at `90076e4a` before the fixes and is also
byte-identical to the original `hist_before.txt`. Black
(`2 files would be left unchanged`), flake8 (exit 0), and mypy
(`Success: no issues found in 2 source files`) pass on both changed Python
files. The wider gate tails above predate these fixes; the fixes change only a
docstring, prose, and one test file, so only the lint's own tests were rerun.

## Not Covered

`ALTER FOREIGN TABLE ... ADD COLUMN` stays unchecked, because `_ALTER_TABLE`
matches only `ALTER TABLE` and decision 819-Q2 covers only `CREATE FOREIGN TABLE`.
The script docstring and `docs/database.md` say so, and the point is recorded on
#819 as a follow-up. `CREATE FOREIGN DATA WRAPPER`, `CREATE SERVER`, and
`CREATE USER MAPPING` create no table and stay unchecked.
