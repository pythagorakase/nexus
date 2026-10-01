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

## After the Independent Review

The independent review of `cb5c500c` found three legal PostgreSQL 17 forms
that create a persistent table and passed silently. Commit `c710a927` closes
them as the fix order decides:

- **The hint is unanchored.** `_PY_SQL_HINT`'s alternative is now
  `\bSELECT\b[\s\S]*?\bINTO\b`, so a literal whose `SELECT ... INTO` follows a
  leading comment (`"-- snapshot\nSELECT 1 INTO t;"`) or another statement
  (`"BEGIN; SELECT 1 INTO t2; COMMIT;"`) is lexed. A `WITH ... SELECT ... INTO`
  literal contains both words and still matches.
- **Leading parentheses.** `_base_depth_tokens` reads the statement at its base
  depth, the depth after its leading `(` characters (whitespace and comments
  between them included), and stops at the first token shallower than the
  base. `(SELECT 1 INTO t);` and `(SELECT 1 INTO t) UNION ALL SELECT 2;` now
  report `t`; nothing after the closing `)` is read.
- **CTE names.** `_after_with_list` skips a `WITH` list before the verb search:
  after each group that closes back to the base depth, `,` continues to the
  next CTE, `AS` continues after a CTE column list, and any other token starts
  the main statement. `WITH delete AS (...) SELECT ... INTO snapshot` and
  `WITH RECURSIVE update (n) AS (...) SELECT ... INTO snapshot2` now report.
- One depth tracker: `_depth_tokens` yields words, quoted identifiers,
  brackets and commas with their depth, and replaces `_top_level_words`, whose
  only caller was this rule.

New test `test_select_into_is_found_past_comments_parentheses_and_cte_names`
asserts the full findings list: the six positives above at their `INTO` lines,
and silence for `WITH delete AS (SELECT 1 AS id) DELETE FROM t WHERE id IN
(SELECT id FROM delete);`, `SELECT 1 FROM (SELECT 2) AS sub;`, and a DO body
holding the shapes of `migrations/109_extend_expiry_default_durations.sql:41-49`
and `migrations/077_recruit_ally_projects.sql:24-25`.

On `cb5c500c` (a scratch copy of `git show cb5c500c:scripts/check_migration_comments.py`)
the new test fails with no finding at all:

```
AssertionError: assert [] == ['130_hidden.... be verified']
Right contains 6 more items, first extra item: '130_hidden.sql:2: SELECT INTO public.t declares no column list; its columns cannot be verified'
1 failed, 36 deselected
```

Each hunk is needed: with only that hunk reverted in a scratch copy, the test
fails on exactly its two cases (`-k "select_into or foreign or import"`):

```
===== hint reverted (anchored alternative)
Right contains 2 more items, first extra item: '131_hidden.py:2: SELECT INTO public.t declares no column list; its columns cannot be verified'
1 failed, 4 passed, 32 deselected in 0.05s
===== leading parentheses reverted (_LEADING_PARENS = r"\s*")
At index 0 diff: '130_hidden.sql:7: SELECT INTO public.snapshot ...' != '130_hidden.sql:2: SELECT INTO public.t ...'
1 failed, 4 passed, 32 deselected in 0.05s
===== WITH-list skip reverted
At index 2 diff: '131_hidden.py:2: SELECT INTO public.t ...' != '130_hidden.sql:7: SELECT INTO public.snapshot ...'
1 failed, 4 passed, 32 deselected in 0.05s
```

A scratch probe also reports `((SELECT 1 INTO t))` after a block comment, a
quoted CTE name `"delete"`, `MATERIALIZED` and `NOT MATERIALIZED` CTEs, and a
recursive CTE with a `SEARCH DEPTH FIRST` clause, and stays silent for
`WITH ... INSERT INTO`, `WITH ... UPDATE`, `(SELECT 1) UNION SELECT 2`, and
`(SELECT 1 INTO TEMP t)`.

On `c710a927`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT`
unset:

```
$ python -m pytest -q tests/test_migration_comment_lint.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
37 passed, 5 warnings in 0.76s
$ python scripts/check_migration_comments.py; echo "exit $?"
OK: every object created after migration 129 has a comment.
exit 0
$ cmp hist_before.txt hist_after.txt; echo "cmp exit $?"
cmp exit 0
     405 hist_before.txt
     405 hist_after.txt
```

`hist_before.txt` is the snapshot taken before the original change; the
historical run at `cb5c500c` was also byte-identical to it before these edits.
Black (`2 files left unchanged`), flake8 (exit 0), and mypy
(`Success: no issues found in 2 source files`) pass on both changed Python
files. Prose that reads "select ... into" inside a non-executed Python string
now reaches the scanner by design, as the coordinator accepted.

## After the Second Review

Two verifiers then proved four more gaps in the `SELECT ... INTO` rule at
`043d664e`, each checked in PostgreSQL 17.11 in a rolled-back transaction.
Commit `76e4a8fe` closes them; this change itself opened no database.

- **A parenthesized main statement after a WITH list.**
  `WITH a AS (SELECT 1) (SELECT 1 INTO t);` and the same with
  `UNION ALL SELECT 2` passed, because the group was read at the outer base
  depth. `_query_tokens` now reads a main statement that opens with `(` as a
  query of its own, with its own leading parentheses and WITH list.
- **SEARCH and CYCLE clauses.** `_after_with_list` read the token after a
  recursive CTE's group as the main statement, so `CYCLE n SET update USING
  path`, `SEARCH DEPTH FIRST BY n SET ord, delete AS (...)`, and
  `SEARCH BREADTH FIRST BY delete SET ord` silenced the rule.
  `_after_search_cycle` skips `SEARCH {BREADTH | DEPTH} FIRST BY col [, ...]
  SET name` and `CYCLE ... USING name` (USING is reserved) before the `,` /
  `AS` / main-statement decision.
- **EXPLAIN ANALYZE.** It executes its statement, but `EXPLAIN ANALYZE (SELECT
  1 INTO t);` and `EXPLAIN (ANALYZE) WITH delete AS (...) SELECT id INTO t
  FROM delete;` passed. `_explained` reads through `EXPLAIN ANALYZE [VERBOSE]`
  (or `ANALYSE`) and through an option list that holds `ANALYZE` with no
  false, off, or 0 value.
- **Plans that create nothing.** Plain `EXPLAIN`, `EXPLAIN VERBOSE`, and
  `EXPLAIN (ANALYZE false, ...)` only plan the statement and now pass.
  `PREPARE p AS SELECT 1 INTO t;` stays reported, as a documented false
  positive (module docstring, `_select_into` docstring, `docs/database.md`):
  it creates nothing by itself, but a later `EXECUTE p` runs it, so exempting
  it would let that pair through.

`test_select_into_fails_like_ctas` gains the two parenthesized-main cases
(lines 48 and 51 of its fixture). New test
`test_select_into_is_found_past_search_cycle_and_explain_analyze` asserts the
full findings list: the three SEARCH/CYCLE cases, four EXPLAIN ANALYZE cases
(plain, parenthesized, CTE-led behind `(ANALYZE)`, and `ANALYZE VERBOSE` with a
CTE and a parenthesized main statement), and `PREPARE`; and silence for
`EXPLAIN`, `EXPLAIN VERBOSE`, `EXPLAIN (ANALYZE false, VERBOSE)`,
`EXPLAIN (SELECT 1 INTO ...)`, and a real `DELETE` after `SEARCH` and `CYCLE`
clauses whose names are `delete` and `update`.

On `043d664e` (a scratch copy of `git show 043d664e:scripts/check_migration_comments.py`)
both tests fail. Their findings there:

```
test_select_into_fails_like_ctas FAIL; findings:
    130_snapshots.sql:2: SELECT INTO public.mood_snapshot declares no column list; its columns cannot be verified
    130_snapshots.sql:6: SELECT INTO public.recent_moods declares no column list; its columns cannot be verified
    130_snapshots.sql:9: SELECT INTO public.mood_ids declares no column list; its columns cannot be verified
    130_snapshots.sql:43: SELECT INTO names '{}', which is not a literal identifier; name the object literally so its COMMENT can be verified
    131_snapshots.py:3: SELECT INTO public.py_snapshot declares no column list; its columns cannot be verified
    131_snapshots.py:9: SELECT INTO public.py_recent declares no column list; its columns cannot be verified
test_select_into_is_found_past_search_cycle_and_explain_analyze FAIL; findings:
    130_clauses.sql:11: SELECT INTO public.explained declares no column list; its columns cannot be verified
    130_clauses.sql:16: SELECT INTO public.prepared declares no column list; its columns cannot be verified
    130_clauses.sql:17: SELECT INTO public.planned declares no column list; its columns cannot be verified
    130_clauses.sql:17: table public.planned has no COMMENT ON TABLE
    130_clauses.sql:18: SELECT INTO public.planned_verbose declares no column list; its columns cannot be verified
    130_clauses.sql:18: table public.planned_verbose has no COMMENT ON TABLE
    130_clauses.sql:19: SELECT INTO public.planned_off declares no column list; its columns cannot be verified
    130_clauses.sql:19: table public.planned_off has no COMMENT ON TABLE
```

Each fix is needed: with only that fix removed in a scratch copy
(`-k select_into`):

```
== mutant with_paren (no re-read of a parenthesized main statement)
FAILED test_lint_copy.py::test_select_into_fails_like_ctas - AssertionError: ...
FAILED test_lint_copy.py::test_select_into_is_found_past_search_cycle_and_explain_analyze
2 failed, 1 passed, 35 deselected in 0.06s
== mutant search_cycle (no SEARCH/CYCLE skip)
FAILED test_lint_copy.py::test_select_into_is_found_past_search_cycle_and_explain_analyze
1 failed, 2 passed, 35 deselected in 0.05s
== mutant explain (no EXPLAIN handling)
FAILED test_lint_copy.py::test_select_into_is_found_past_search_cycle_and_explain_analyze
1 failed, 2 passed, 35 deselected in 0.05s
```

The verifiers' eleven scratch cases (x01-x11), rerun against both scripts
(count of `SELECT INTO` findings, old then new): x01 0→1, x02 0→1, x03 1→1,
x04 0→1, x05 0→1, x06 0→1, x07 1→1, x08 0→1, x09 0→1, x10 1→0, x11 1→1
(PREPARE, kept). Extra cases: `EXPLAIN (ANALYZE false, VERBOSE)` 1→0,
`EXPLAIN ANALYZE VERBOSE WITH ... (SELECT 1 INTO t)` 0→1,
`EXPLAIN (SELECT 1 INTO t)` 0→0, a real `DELETE` after SEARCH and CYCLE 0→0.

On `76e4a8fe`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT`
unset:

```
$ black --check
All done! ✨ 🍰 ✨
2 files would be left unchanged.
exit=0
$ flake8
exit=0
$ mypy
Success: no issues found in 2 source files
$ pytest lint
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 0.88s
$ real tree
OK: every object created after migration 129 has a comment.
exit=0
$ cmp hist_before.txt hist_after.txt
exit=0
     405
     405
$ reachability
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.61s
```

`hist_before.txt` was taken at `043d664e` before these edits and is
byte-identical to the snapshot taken before the original change.
