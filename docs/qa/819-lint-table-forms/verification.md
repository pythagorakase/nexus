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

## After the Third Review

The second independent pass found one P1 and three P2 in the round-2 `EXPLAIN`
handling and recursive wrapper reading at `cad24cfb`. Commit `8012b084` applies
the coordinator's decision: the lint stops parsing `EXPLAIN` options. This
change opened no database.

- **No recursion (P1).** `_query_tokens` called itself once per `EXPLAIN`
  prefix and once per parenthesized `WITH` main statement, so
  `"EXPLAIN ANALYZE " * 1100 + "("` and 1,100 nested `WITH a AS (SELECT 1) (`
  wrappers raised `RecursionError`. It is now one bounded pass: at most one
  `EXPLAIN` prefix, one rebase through leading parentheses, one `WITH` list
  (with its `SEARCH`/`CYCLE` clauses), and, when the main statement opens with
  `(`, one more rebase and `WITH` list; a further parenthesized main statement
  yields nothing. A statement whose brackets do not balance (PostgreSQL
  rejects it) is read by its depth-0 tokens, which is how `cb5c500c` read every
  statement, so the malformed cases below match `cb5c500c` exactly.
- **`EXPLAIN` is reported, never parsed (P2 x3).** `_explain_runs` and
  `_explained` are deleted. `_after_explain` strips `EXPLAIN` and either one
  parenthesized option list or the grammar's `ANALYZE`/`ANALYSE` and `VERBOSE`
  keywords, without reading them; the rest is checked like any other
  statement. The keywords are stripped as well as the option list so that
  `EXPLAIN ANALYZE (SELECT 1 INTO t)` stays reported. A `SELECT INTO` behind
  any `EXPLAIN` now gets the normal `SELECT INTO ... declares no column list`
  finding, although a plain `EXPLAIN` creates nothing: the lint does not model
  which `EXPLAIN` forms execute, and no migration should `EXPLAIN`. The module
  docstring and `docs/database.md` say so.
  `EXPLAIN (SELECT 1 INTO t)` is read as an option list and passes
  (unchanged; PostgreSQL reads it as a parenthesized statement, see "After the
  Fourth Review").

`test_select_into_is_found_past_search_cycle_and_explain_analyze` is renamed
`test_select_into_is_found_past_search_cycle_and_explain`. Its plain
`EXPLAIN`, `EXPLAIN VERBOSE`, and `EXPLAIN (ANALYZE false, VERBOSE)` cases are
now positives, and `EXPLAIN ("analyze") SELECT 1 INTO quoted_option;`,
`EXPLAIN (ANALYZE true, ANALYZE false) SELECT 1 INTO repeated_option;`, and
`EXPLAIN (ANALYZE "false") SELECT 1 INTO quoted_value;` are added; each
reports exactly one finding at its `INTO` line (lines 17-22). The SEARCH/CYCLE,
parenthesized-main, and real-`DELETE` cases are unchanged. New test
`test_select_into_reading_is_bounded` runs the 1,100-prefix `EXPLAIN ANALYZE`
chain ending in `(`, a 1,100-deep parenthesis nest around
`SELECT 1 INTO deep`, a bare `(`, an empty statement, and 1,100 nested `WITH`
wrappers, and asserts the full list: only the nest's `SELECT INTO public.deep`
finding.

Both tests fail on `cad24cfb` (a scratch copy of
`git show cad24cfb:scripts/check_migration_comments.py` beside the new test
file, `-k "bounded or search_cycle_and_explain"`):

```
E       AssertionError: assert ['130_clauses...erified', ...] == ['130_clauses...erified', ...]
test_lint_copy.py:1113: AssertionError
E       RecursionError: maximum recursion depth exceeded in comparison
scripts/check_migration_comments.py:704: RecursionError
FAILED test_lint_copy.py::test_select_into_is_found_past_search_cycle_and_explain
FAILED test_lint_copy.py::test_select_into_reading_is_bounded - RecursionErro...
2 failed, 37 deselected in 4.14s
```

Each case alone, through `check_migrations`, against scratch copies of
`cb5c500c` and `cad24cfb` and against `8012b084` (each file also holds
`COMMENT ON TABLE t`; findings counted, `RecursionError` caught by the probe):

| Case | `cb5c500c` | `cad24cfb` | `8012b084` |
| --- | --- | --- | --- |
| `"EXPLAIN ANALYZE " * 1100 + "("` | 0 | RecursionError | 0 |
| 1,100-deep `(...(SELECT 1 INTO deep)...)` | 0 | 2 | 2 |
| `(` | 0 | 0 | 0 |
| empty statement | 0 | 0 | 0 |
| 1,100 nested `WITH a AS (SELECT 1) (` | 0 | RecursionError | 0 |
| `EXPLAIN ("analyze") SELECT 1 INTO t` | 1 | 0 | 1 |
| `EXPLAIN (ANALYZE true, ANALYZE false) SELECT 1 INTO t` | 1 | 1 | 1 |
| `EXPLAIN (ANALYZE "false") SELECT 1 INTO t` | 1 | 1 | 1 |
| `EXPLAIN SELECT 1 INTO t` | 1 | 0 | 1 |
| `EXPLAIN VERBOSE SELECT 1 INTO t` | 1 | 0 | 1 |
| `EXPLAIN (ANALYZE false) SELECT 1 INTO t` | 1 | 0 | 1 |
| `EXPLAIN ANALYZE (SELECT 1 INTO t)` | 0 | 1 | 1 |
| `EXPLAIN (SELECT 1 INTO t)` | 0 | 0 | 0 |
| `(SELECT 1 INTO t` (unbalanced) | 0 | 1 | 0 |

The quoted option name (`EXPLAIN ("analyze")`) was silent on `cad24cfb`. The
nest's two findings are its `SELECT INTO public.deep` finding and a missing
`COMMENT ON TABLE` for `deep` (the probe documents only `t`); the test documents
`deep` and expects one.

On `8012b084`, with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT`
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
39 passed, 5 warnings in 0.84s
$ real tree
OK: every object created after migration 129 has a comment.
exit=0
$ cmp hist_before.txt hist_after.txt
exit=0
     405
     405
$ reachability
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.92s
```

`hist_before.txt` was taken at `cad24cfb` before these edits and is
byte-identical to the round-2 snapshot (and so to the one taken before the
original change).

## After the Fourth Review

One P3, a wording defect: `_after_explain` reads any `(` right after `EXPLAIN`
as an option list, so `EXPLAIN (SELECT 1 INTO t);` is stripped to nothing and
passes, but the module docstring, the `_after_explain` docstring, and
`docs/database.md` said that every `EXPLAIN` of a `SELECT ... INTO` is
reported, and the test docstring said PostgreSQL's grammar reads the form as an
option list. PostgreSQL reads it as a parenthesized statement: the reviewer's
`psql -d postgres -Atc "EXPLAIN (SELECT 1 INTO t)"` returned
`Result  (cost=0.00..0.01 rows=1 width=4)`, and `EXPLAIN ((SELECT 1 INTO t))`
behaves the same way. No table escapes the lint: without `ANALYZE` an
`EXPLAIN` does not execute its statement, and both executing spellings are
reported.

The code is unchanged. The fix is wording only:

- Module docstring: `EXPLAIN (` is always read as an option list, so an
  `EXPLAIN` whose statement opens with a parenthesis passes; it cannot execute,
  because no `ANALYZE` precedes the statement.
- `_after_explain` docstring: the grammar claim is removed; it says PostgreSQL
  also accepts a parenthesized statement after `EXPLAIN`, that the lint reads
  it as an option list and passes it, and why that is safe.
- `docs/database.md`: the same exception, in the "fails" list.
- `test_select_into_is_found_past_search_cycle_and_explain` docstring: the
  true reason replaces "as PostgreSQL's grammar reads it". Its assertions are
  unchanged.
- The "After the Third Review" text above now says the same.

The code is identical to `af03db94` apart from docstrings: the two files'
ASTs, with every module, class, and function docstring blanked, compare equal.

A probe (`130_explain_paren.sql`, each table documented with
`COMMENT ON TABLE`) gives the same findings on a scratch copy of `af03db94` and
on the new head:

```
EXPLAIN (SELECT 1 INTO plain_paren);                 -- passes
EXPLAIN ((SELECT 1 INTO double_paren));              -- passes
EXPLAIN ANALYZE (SELECT 1 INTO analyzed_paren);      -- reported
EXPLAIN (ANALYZE) (SELECT 1 INTO option_then_paren); -- reported

Found 2 schema documentation finding(s):
  130_explain_paren.sql:3: SELECT INTO public.analyzed_paren declares no column list; its columns cannot be verified
  130_explain_paren.sql:4: SELECT INTO public.option_then_paren declares no column list; its columns cannot be verified
```

With `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT` unset:

```
$ cmp hist_before.txt hist_after.txt
exit=0
     405
     405
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
39 passed, 5 warnings in 0.99s
$ real tree
OK: every object created after migration 129 has a comment.
exit=0
$ reachability
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.12s
```

`hist_before.txt` was rendered from a scratch copy of `af03db94` against the
worktree's `migrations/`, with paths relative to the worktree root.

## After the Fifth Review

The fix order for this round names this section "After the Fourth Review";
that heading already holds the P3 wording round, so this one is the fifth.
The third independent pass found three P2 in the `SELECT INTO` rule at
`77933da5`, each a legal PostgreSQL 17 form that created a table and passed.
Commit `f7701d0d` applies the coordinator's three decisions. This change opened
no database; the earlier `EXPLAIN` and `PREPARE` decisions are unchanged.

- **Nested set operations (P2).** `_query_tokens` rebased through a
  parenthesized main statement at most once more, so
  `WITH a AS (SELECT 1) (WITH b AS (SELECT 2) (SELECT 1 INTO escaped) UNION ALL SELECT 2) UNION ALL SELECT 3;`
  passed. It is now a `while` loop over an explicit counter: while the tokens
  open with `WITH`, skip that list (with its `SEARCH`/`CYCLE` clauses); a main
  statement that opens with `(` is read again past its leading parentheses;
  any other main statement ends the loop. After 64 `WITH` lists
  (`_WITH_NESTING_LIMIT`) it returns `None`, and `_select_into` reports
  `cannot parse SQL: a statement nests more than 64 WITH lists` at the
  statement's first non-blank character. No function calls itself.
- **`into` as an identifier (P2).** `_is_into_clause`: a base-depth `INTO` is
  the clause unless the token before it is `AS` (an output alias) or the
  character before it, past whitespace, is `.` (a qualified attribute). A `.`
  that ends an all-digit run is a numeric literal (`SELECT 1. INTO t`), not a
  qualifier, so that `INTO` stays the clause. The rule takes the first
  base-depth `INTO` after the verb that passes.
- **A target named `temp` (P2).** `_select_into_target` replaces the
  `_SELECT_INTO_TARGET` regex. `GLOBAL`/`LOCAL`, then
  `TEMP`/`TEMPORARY`/`UNLOGGED`, are modifiers only when `_names_target`
  finds a name next: a quoted identifier, a placeholder (`%s`, `%(n)s`, or the
  `{}` an interpolated value renders as), a word not in `_RESERVED_WORDS`, or
  `TABLE` followed by one of those. Otherwise the word is the target's name.
  `TABLE` is reserved, so `INTO TABLE temp` names `temp`. `_RESERVED_WORDS` is
  PostgreSQL 17's reserved key-word list; it equals the 78 `RESERVED_KEYWORD`
  entries of the installed
  `/Applications/Postgres.app/Contents/Versions/latest/include/postgresql/server/parser/kwlist.h`
  (`diff` exit 0).

Tests: `test_select_into_reading_is_bounded` now expects the 1,100-deep
`WITH a AS (SELECT 1) (` wrapper to report `cannot parse SQL` (it passed
before, which the decision forbids), and adds the nested set operation
(reports `escaped`), a 64-deep `(WITH x AS (SELECT 1) ` nest (reports
`at_limit`), and a 70-deep one (reports `cannot parse SQL`). New
`test_into_after_a_dot_or_as_is_a_name` holds the order's three statements
plus a spaced `src . into AS into INTO spaced` and `SELECT 1. INTO numbered`.
New `test_select_into_target_named_temp` holds `INTO temp`, `INTO temporary`,
`INTO TABLE temp`, `INTO unlogged;` and `(SELECT 1 INTO temp);` (each
reported), and `INTO TEMP t`, `INTO LOCAL TEMP t`, `(SELECT 1 INTO TEMP t)`,
`INTO TEMP TABLE t WHERE true`, `INTO GLOBAL TEMPORARY "t"`, and a Python
f-string `INTO TEMP {name}` (each silent). Every test asserts the full
findings list.

The three tests fail on `77933da5` (a scratch copy of
`git show 77933da5:scripts/check_migration_comments.py` beside the new test
file, `-k "bounded or into_after_a_dot or target_named_temp"`):

```
E       AssertionError: assert ['130_bounded... be verified'] == ['130_bounded...4 WITH lists']
test_lint_copy.py:1171: AssertionError
E       AssertionError: assert ['130_into_na... be verified'] == ['130_into_na... be verified']
test_lint_copy.py:1203: AssertionError
E       AssertionError: assert ['130_temp_na... be verified'] == ['130_temp_na... be verified']
test_lint_copy.py:1248: AssertionError
FAILED test_lint_copy.py::test_select_into_reading_is_bounded - AssertionErro...
FAILED test_lint_copy.py::test_into_after_a_dot_or_as_is_a_name - AssertionEr...
FAILED test_lint_copy.py::test_select_into_target_named_temp - AssertionError...
3 failed, 38 deselected in 0.08s
```

Each of the order's statements alone, through `check_migrations` (no
`COMMENT ON` in the file, so a reported table also has its missing-comment
finding):

| Statement | `77933da5` | `f7701d0d` |
| --- | --- | --- |
| `WITH a AS (SELECT 1) (WITH b AS (SELECT 2) (SELECT 1 INTO escaped) UNION ALL SELECT 2) UNION ALL SELECT 3;` | passes | `SELECT INTO public.escaped`, no comment |
| 70-deep `(WITH x AS (SELECT 1) ... SELECT 1 INTO t ...)` | passes | `cannot parse SQL: a statement nests more than 64 WITH lists` |
| `SELECT src.into temp INTO escaped FROM (VALUES (1)) AS src("into");` | passes | `SELECT INTO public.escaped`, no comment |
| `SELECT src.into FROM (VALUES (1)) AS src("into");` | `SELECT INTO public.from`, no comment | passes |
| `SELECT 1 AS into;` | `SELECT INTO names '<nothing>'` | passes |
| `SELECT 1 INTO temp FROM (VALUES (1)) AS v(n);` | passes | `SELECT INTO public.temp`, no comment |
| `SELECT 1 INTO temporary FROM (VALUES (1)) AS v(n);` | passes | `SELECT INTO public.temporary`, no comment |
| `SELECT 1 INTO TABLE temp FROM (VALUES (1)) AS v(n);` | `SELECT INTO public.temp`, no comment | the same |
| `SELECT 1 INTO TEMP t;` | passes | passes |
| `SELECT 1 INTO LOCAL TEMP t;` | passes | passes |
| `(SELECT 1 INTO TEMP t);` | passes | passes |

Fuzz (`fuzz.py` in the scratch subdirectory): random statements of 1 to 40
tokens drawn from the earlier rounds' words (verbs, `WITH`, `RECURSIVE`,
`MATERIALIZED`, set operations, `INTO` and its modifiers, `EXPLAIN` and its
options, `PREPARE`, `EXECUTE`, `SEARCH`/`CYCLE` words, `DO`, `CREATE`,
`FOREIGN`, `IMPORT`, `COMMENT ON`, brackets, commas, `;`, literals, dollar
quotes, comments, placeholders) plus `.`, `AS`, `temp`, `temporary`,
`"into"`, `FROM`, `VALUES`, `1.`, and `src.into`; each a quarter as a `.sql`
statement, a DO body, an `EXECUTE` command, and a Python `execute` literal,
scanned with `_scan_sql` and resolved:

```
$ fuzz.py scripts/check_migration_comments.py 40000 4
statements=40000 forms={'sql': 10000, 'do body': 10000, 'execute': 10000, 'python': 10000} seconds=4.7
exceptions=0 {}
$ fuzz.py scripts/check_migration_comments.py 200000 819
statements=200000 forms={'sql': 50000, 'do body': 50000, 'execute': 50000, 'python': 50000} seconds=22.0
exceptions=0 {}
```

In 20,000 of the `.sql` statements, 187 reached a `SELECT INTO` finding, so
the fuzz exercises the new rules.

With `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT` unset:

```
$ cmp hist_before.txt hist_after.txt
exit=0
     405
     405
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
41 passed, 5 warnings in 1.06s
$ real tree
OK: every object created after migration 129 has a comment.
exit=0
$ reachability
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 11.06s
```

`hist_before.txt` was rendered at `77933da5` before these edits.

## After the Sixth Review

Two verifiers found one more P2 at `88255096`: `_is_into_clause` decided
whether a `.` before `INTO` ends a numeric literal with `str.isdigit()` on the
run before the dot. PostgreSQL 16 and later accept `_` digit separators in
decimal literals, so in `SELECT 1_000. INTO t;` the run is `1_000`,
`isdigit()` is false, the dot was read as a qualifier, the `INTO` was skipped
as an attribute name, and the statement passed. The verifiers showed on the
local PostgreSQL 17.11 that `SELECT 1_000. INTO TEMP ...` runs its `INTO`
clause and returns 1000; `0x1F.`, `0o17.`, `0b101.` and `1e5.` are syntax
errors there, so only the separated form was affected. This change opened no
database.

Commit `f0f190cd`: the run must fully match PostgreSQL's decinteger,
`_DECINTEGER = re.compile(r"[0-9](?:_?[0-9])*")` (ASCII digits, single `_`
between digits). `test_into_after_a_dot_or_as_is_a_name` adds
`SELECT 1_000. INTO separated;` (with its `COMMENT ON TABLE`) and expects its
`SELECT INTO public.separated declares no column list` finding at line 6.

The test fails on `88255096` (a scratch `git archive` of that commit with the
new test file copied in, `-k into_after_a_dot`):

```
E       AssertionError: assert ['130_into_na... be verified'] == ['130_into_na... be verified']
E         
E         Right contains one more item: '130_into_names.sql:6: SELECT INTO public.separated declares no column list; its columns cannot be verified'
E         Use -v to get more diff
FAILED tests/test_migration_comment_lint.py::test_into_after_a_dot_or_as_is_a_name
1 failed, 40 deselected, 5 warnings in 0.30s
```

The verifiers' probe, a scratch `999_x.sql` holding `SELECT 1_000. INTO t;`,
through `--migrations-dir`:

| Statement | `88255096` | `f0f190cd` |
| --- | --- | --- |
| `SELECT 1_000. INTO t;` | `OK`, exit 0 | `SELECT INTO public.t declares no column list` and `table public.t has no COMMENT ON TABLE`, exit 1 |
| `SELECT 1_000_000. INTO b;` | not run | reported |
| `SELECT 1_000.5 INTO d;` | not run | reported |
| `SELECT x1_000.into FROM (VALUES (1)) AS x1_000("into");` | not run | passes (a qualifier) |
| `SELECT _1.into FROM (VALUES (1)) AS _1("into");` | not run | passes (a qualifier) |

Fuzz (`r5/fuzz.py`, the fifth round's script with `1_000.`, `1_000` and
`x1_0.` added to its tokens):

```
$ fuzz.py scripts/check_migration_comments.py 40000 5
statements=40000 forms={'sql': 10000, 'do body': 10000, 'execute': 10000, 'python': 10000} seconds=4.3
exceptions=0 {}
```

With `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT` unset:

```
$ cmp hist_before.txt hist_after.txt
exit=0
     405
     405
$ black --check
All done! ✨ 🍰 ✨
2 files would be left unchanged.
$ flake8
exit=0
$ mypy
Success: no issues found in 2 source files
$ pytest lint
secret-store guard: active; nexus-api: denied; disposable keychain: denied
41 passed, 5 warnings in 1.11s
$ real tree
OK: every object created after migration 129 has a comment.
exit 0
$ reachability
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 10.51s
```

`hist_before.txt` was rendered at `88255096` before these edits.
