# Schema-Documentation Ratchet Extension Verification

## Scope

Work order 819-B, branch `claude/819-ratchet-enums-functions-views`, cut from
`origin/main` at 6b9c3e17. This slice adds no migration and writes no comment on a
legacy object. No gateway was started and no paid provider was called. Hand-built
databases use `qa640_*`; the test suite's fixtures keep their own disposable names.
Nothing was written to `NEXUS_template` or any save; counts below come from a
read-only session on `NEXUS_template` (migration head 134).

`tests/test_schema_documentation_pg.py` now inventories five object kinds in
`public` and `assets`, each excluding extension members through `pg_depend`
(`deptype = 'e'`) with the classid of its own catalog:

| Kind | Catalog Predicate | Key | Comment Source |
| --- | --- | --- | --- |
| Table | `pg_class.relkind IN ('r','p','f')` | `table:<schema>.<name>` | `obj_description(oid, 'pg_class')` |
| Column | `pg_attribute` of any inventoried table | `column:<schema>.<table>.<name>` | `col_description` |
| Enum | `pg_type.typtype = 'e'` | `enum:<schema>.<name>` | `obj_description(oid, 'pg_type')` |
| Function | `pg_proc.prokind IN ('f','w','p')` | `function:<schema>.<name>(<pg_get_function_identity_arguments>)` | `obj_description(oid, 'pg_proc')` |
| View | `pg_class.relkind IN ('v','m')` | `view:<schema>.<name>` | `obj_description(oid, 'pg_class')` |

Trigger functions are ordinary `pg_proc` rows and are covered. Procedures key as
PostgreSQL prints their identity arguments (for example
`function:assets.schema_docs_probe(IN n integer)`, exercised by the
`new-procedure` test case). Aggregates (`prokind = 'a'`) stay outside the gate.

Views and materialized views are documented at the view level only; their
columns are not inventoried. `scripts/check_migration_comments.py` requires
`COMMENT ON VIEW` and `COMMENT ON MATERIALIZED VIEW` for a new view but cannot
require column comments, because view DDL declares no column list, so a ratchet
that required them would fail a migration the lint had passed. This follows a
coordinator amendment: the first push inventoried view columns as `column:` keys
and baselined 115 of them.

## Counts

Read-only inventory of `NEXUS_template`, produced by the test module's own
`_inventory` and `_baseline` (the coverage assertion passes on the same data):

| Kind | Inventoried | Documented | Baselined |
| --- | ---: | ---: | ---: |
| table | 85 | 85 | 0 |
| column | 867 | 853 | 14 |
| enum | 41 | 0 | 41 |
| function | 34 | 13 | 21 |
| view | 16 | 11 | 5 |
| total | 1043 | 962 | 81 |

The enum, function, and view totals match the slice-A inventory in
`docs/qa/819-schema-docs/verification.md` (41/41, 34/21, 16/5 undocumented):
migrations 128–134 added comments with every object they created or replaced.
The 14 table-column entries are unchanged from slice A, and so is the column
inventory: its 867 keys and comments equal those of slice A's query (6b9c3e17) on
the same read-only session.

## Baseline Reasons

`config/schema_docs_baseline.json` grows from 14 to 81 entries. Every reason was
checked against the catalog or `git grep` at this base:

- **Enums (41).** 34 name the table and view columns they type (catalog join on
  `pg_attribute.atttypid` over the enum and its array type). Seven
  (`emotional_valence`, `entity_type`, `item_type`, `relationship_type`,
  `threat_domain_type`, `threat_lifecycle_type`, `trait`) type no column in the
  template and no SQL under `nexus/`, `scripts/`, or `migrations/` casts to them;
  they are marked as decision-ledger (#817) questions.
- **Functions (21).** Twelve trigger functions name their trigger and table
  (from `pg_trigger.tgfoid`) and state what the body does. Three helpers name
  their single caller (`orrery_sync_character_need_states` calls
  `orrery_active_character_tag_names` and `orrery_need_applies_to_tags`;
  `refresh_world_time_from_chunk_trigger` calls `refresh_world_time_from_chunk`).
  Six have no caller in `nexus/`, `scripts/`, or another NEXUS function: the three
  `hybrid_search` overloads (MEMNON's `execute_hybrid_search` in
  `nexus/agents/memnon/utils/db_access.py:401` delegates to
  `execute_multi_model_hybrid_search`, which builds its own SQL at
  `nexus/agents/memnon/utils/db_access.py:581`),
  `migrate_embeddings()` (it names `chunk_embeddings` and
  `chunk_embeddings_small`; `to_regclass` finds neither in the template), and the
  two `pad_vector_*` helpers.
- **Views (5).** Each reason names the Python files under `nexus/` and
  `scripts/` that mention the view (`git grep -lw`).

No reason is a comment in disguise: purposes are stated only where a trigger
binding, a single caller, or the function body itself shows them
(`migrate_embeddings` and the two `pad_vector_*` helpers are described from their
bodies). Entries with reader/writer evidence defer the comment to the backfill
slice. The seven unused enums defer to the decision ledger (#817), and the six
uncalled functions state that no caller exists (the three `hybrid_search`
overloads add that no evidence establishes their contract).

The amendment deleted the 115 view-column entries of the first push and nothing
else (115 deletions, no additions). Read-only on `NEXUS_template`, every deleted
key resolves to a column of a relation with `relkind = 'v'`, and together they are
exactly the template's undocumented view columns outside extensions (118 such
columns, 3 documented). The 14 remaining `column:` entries resolve to
`relkind = 'r'` and equal slice A's entries, keys and reasons alike.

## Ratchet Proof

The suite exercises each failure mode with real catalog DDL on the module's
`qa640_schema_docs_*` clone, rolled back after each case:

- New undocumented object: `new-enum`, `new-trigger-function`, `new-overload`
  (a second `schema_docs_refresh_probe` signature gets its own key),
  `new-procedure`, `new-view`, `new-materialized-view`, plus the slice-A table
  and column cases.
- Comment removed or blanked: `blank-enum-comment` (a whitespace-only
  `COMMENT ON TYPE ... IS '   '`; PostgreSQL stores it, unlike `''`, which it
  treats as removing the comment), `removed-function-comment`
  (`public.clear_incubator()`), `removed-view-comment` (`public.narrative_view`).
- Baseline entry now documented or removed, per kind: `test_baseline_retirement`
  over table, column, enum, function, and view, each documented and each dropped.
- Baseline key naming no object: `test_baseline_rejects_nonexistent_keys` for
  table, column, enum, function, and view keys.
- View level only: `test_views_are_documented_at_view_level` creates an
  uncommented view and materialized view; the ratchet reports exactly their two
  `view:` keys, passes once `COMMENT ON VIEW` and `COMMENT ON MATERIALIZED VIEW`
  exist while their columns stay uncommented, and rejects a baseline `column:`
  key that names a view column. With the column query's `relkind` filter removed
  by hand, the module fixture fails listing exactly the 115 deleted view-column
  keys as undocumented objects absent from the baseline.
- Extension exclusion: the coverage test asserts that the PostGIS views
  `geometry_columns` and `geography_columns` and the functions
  `postgis_full_version()` and `vector_dims(vector)` are absent from the
  inventory, and that `pg_depend` really records them as extension members.

Hand-built red/green run (`disposable_slot_database("qa640_ratchet_manual")`, then
an undocumented enum, PL/pgSQL trigger function, and view committed by hand, the
view's one column left uncommented; then `COMMENT ON TYPE`, `COMMENT ON FUNCTION`,
and `COMMENT ON VIEW`), rerun after the view-column amendment. The exact driver,
kept outside the repository and run from the worktree root as
`NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY <scratchpad>/ratchet_manual.py`:

```python
from contextlib import closing

from tests.pg_fixtures import connect, disposable_slot_database
from tests.test_schema_documentation_pg import _assert_coverage, _baseline, _inventory

UNDOCUMENTED_DDL = """
CREATE TYPE public.manual_probe_mood AS ENUM ('calm', 'tense');
CREATE FUNCTION public.manual_probe_touch() RETURNS trigger LANGUAGE plpgsql AS
$$BEGIN NEW.updated_at := now(); RETURN NEW; END$$;
CREATE VIEW public.manual_probe_view AS
SELECT 'calm'::public.manual_probe_mood AS mood;
"""
COMMENT_DDL = """
COMMENT ON TYPE public.manual_probe_mood IS 'Manual probe enum';
COMMENT ON FUNCTION public.manual_probe_touch() IS 'Manual probe trigger function';
COMMENT ON VIEW public.manual_probe_view IS 'Manual probe view';
"""


def check(dbname: str, label: str) -> None:
    with closing(connect(dbname)) as conn:
        conn.set_session(readonly=True)
        try:
            _assert_coverage(_inventory(conn), _baseline())
        except AssertionError as error:
            print(f"[{label}] RED:\n{error}")
        else:
            print(f"[{label}] GREEN")


def execute(dbname: str, sql: str) -> None:
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(sql)


with disposable_slot_database("qa640_ratchet_manual") as dbname:
    print(f"clone: {dbname}")
    check(dbname, "fresh clone")
    execute(dbname, UNDOCUMENTED_DDL)
    with closing(connect(dbname)) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT l.lanname, pg_get_function_result(p.oid) FROM pg_proc p "
                "JOIN pg_language l ON l.oid = p.prolang "
                "WHERE p.oid = 'public.manual_probe_touch()'::regprocedure"
            )
            print(f"manual_probe_touch language/result: {cur.fetchone()}")
            cur.execute(
                "SELECT col_description('public.manual_probe_view'::regclass, 1)"
            )
            print(f"manual_probe_view.mood comment: {cur.fetchone()}")
    check(dbname, "after undocumented enum/function/view")
    execute(dbname, COMMENT_DDL)
    check(dbname, "after COMMENT ON TYPE/FUNCTION/VIEW")
```

Tail of its output (the fixture's restore log precedes it):

```text
clone: qa640_ratchet_manual_01c8d06fd94e
[fresh clone] GREEN
manual_probe_touch language/result: ('plpgsql', 'trigger')
manual_probe_view.mood comment: (None,)
[after undocumented enum/function/view] RED:
Undocumented objects absent from baseline: ['enum:public.manual_probe_mood', 'function:public.manual_probe_touch()', 'view:public.manual_probe_view']
Retire documented or removed baseline entries: []
[after COMMENT ON TYPE/FUNCTION/VIEW] GREEN
```

The fixture dropped the clone on exit.

Function keys spell argument types through `format_type`, which adds a schema
only for types off the session `search_path`. `_inventory` therefore pins
`search_path` to `public` for its transaction
(`set_config('search_path', 'public', true)`), the path the baseline was rendered
under. A read-only probe of `NEXUS_template` with the session path set to
`assets` (`options='-c search_path=assets'`) showed the effect: the raw query and
the pinned inventory differed in 10 keys, two spellings each of five functions
(the two `vector`-typed `hybrid_search` overloads, `orrery_need_applies_to_tags`,
and the two `pad_vector_*` helpers, spelled `public.vector` /
`public.character_need_type` instead of the baseline's unqualified names). The
third overload, `hybrid_search(..., query_embedding bytea, ...)`, has no argument
type in `public` and kept its key. The pinned inventory matched the baseline with
zero untracked and zero retired entries, and the session path read `assets` again
after the rollback.

## Refresh Survival

The module fixture commits documented probes to its clone: enum
`public.schema_docs_refresh_probe`, function
`public.schema_docs_refresh_probe(integer)`, and view
`public.schema_docs_refresh_probe_v`. Every legacy enum
is still debt, so a probe is the only way to prove an enum comment survives.
`test_schema_only_refresh_preserves_comments` (real `pg_dump -s` into a
`qa640_schema_docs_*` database) and `test_story_setup_and_runner_preserve_comments`
(`scripts/new_story_setup.py` schema copy, seed copy, and migration runner via
`disposable_slot_database(source_db=...)`) both assert full inventory equality with
the source and the three exact probe comments on the target.

## Commands

All from the worktree root with `PY=/Users/pythagor/nexus/.venv/bin/python`.
Import proof printed
`/Users/pythagor/nexus/.claude/worktrees/819-ratchet-extension/nexus/__init__.py`.

PostgreSQL gate (`NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset):

```bash
NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_schema_documentation_pg.py tests/test_new_story_setup.py
```

```text
41 passed, 5 warnings in 14.05s (rerun after the view-column amendment)
```

Reachability, style, and types:

```bash
$PY -m pytest -q tests/test_reachability.py
$PY -m black --check tests/test_schema_documentation_pg.py scripts/check_migration_comments.py
$PY -m flake8 tests/test_schema_documentation_pg.py scripts/check_migration_comments.py
$PY -m mypy tests/test_schema_documentation_pg.py scripts/check_migration_comments.py
```

```text
38 passed in 8.75s
2 files would be left unchanged.
(flake8: no output)
Success: no issues found in 2 source files
```

Offline suite, run on a551c20b plus the second review fixes (the skips are the
PostgreSQL-gated tests). It was not rerun for the view-column amendment, which
changes only the PostgreSQL-gated module (skipped offline), the baseline that only
that module reads, and docs:

```bash
$PY -m pytest -q
```

```text
4119 passed, 1070 skipped, 8 warnings in 293.69s (0:04:53)
```

## Astra Review Fixes

Astra's independent review of eb156a9f found two gaps between the offline lint and
the ratchet and two errors in this file. This pass fixes those four and nothing
else.

- **Procedures (P2).** `scripts/check_migration_comments.py` now handles
  `CREATE [OR REPLACE] PROCEDURE` the way it handles functions and accepts
  `COMMENT ON PROCEDURE` or `COMMENT ON ROUTINE` as its documentation; a Python
  migration string that creates a procedure is scanned like one that creates a
  function. The review's `CREATE PROCEDURE public.review_p() LANGUAGE sql AS
  'SELECT 1';` without a comment now reports `procedure public.review_p() has no
  COMMENT ON PROCEDURE`; before, it passed while the ratchet rejected
  `function:public.review_p()`.
- **Overloads (P2).** Routine comments now match by argument types instead of
  argument count. The `CREATE` and `COMMENT` lists both drop parameter names,
  modes, and `DEFAULT` clauses, fold unquoted words to lower case, and collapse
  whitespace; type aliases, type modifiers, and array spellings are canonicalized
  as well (Type Alias Table, below). A comment without an
  argument list documents the one overload of its kind that the migration
  creates; with two or more, it is reported as ambiguous and documents none. The
  review's `review_f(integer)` and `review_f(text)`, with only the integer
  overload commented, now report `function public.review_f(text) has no COMMENT
  ON FUNCTION`.
- **`search_path` paragraph (P3).** Corrected above. A rerun of the read-only
  probe on `NEXUS_template` listed the same 10 differing keys (five functions, two
  spellings each) and left the `bytea` `hybrid_search` key unchanged.
- **Commit attribution (P3).** Rewritten below.

The lint follows how PostgreSQL 17 (Postgres.app 17.11) resolves routine comments,
probed on disposable `qa640_procprobe_*` databases, dropped afterwards:

| Comment | Routines | PostgreSQL 17 |
| --- | --- | --- |
| `COMMENT ON FUNCTION f_out(int)` | function `f_out(IN a int, OUT b int)` | documents it |
| `COMMENT ON FUNCTION f_out(int, int)` | same | `function f_out(integer, integer) does not exist` |
| `COMMENT ON FUNCTION f_out(IN int, OUT int)` | same | documents it |
| `COMMENT ON PROCEDURE p_out(int)` | procedure `p_out(IN a int, OUT b int)` | documents it |
| `COMMENT ON PROCEDURE p_out(int, int)` | same | documents it |
| `COMMENT ON PROCEDURE p_out(OUT text)` | procedure `p_out(IN a int, OUT b text)` | `procedure p_out() does not exist` |
| `COMMENT ON FUNCTION review_p()` | procedure `review_p()` | `review_p() is not a function` |
| `COMMENT ON FUNCTION review_f` | functions `review_f(integer)`, `review_f(text)` | `function name "review_f" is not unique` |
| `COMMENT ON FUNCTION mixed` | function `mixed(int)`, procedure `mixed(text)` | documents the function |
| `COMMENT ON ROUTINE mixed` | same | `routine name "mixed" is not unique` |
| `COMMENT ON PROCEDURE q(int, int)` | procedures `q(a int, b int)`, `q(IN a int, OUT b int)` | `procedure name "q" is not unique` |

New lint tests: `test_missing_object_comment_fails[procedure]` (finding);
`test_procedure_comments_follow_postgresql_lookup` (input-list, full-list, and
bare `ROUTINE` comments document their procedures; a `COMMENT ON FUNCTION` on a
procedure and an uncommented procedure in a Python DDL constant are findings);
`test_each_function_overload_needs_its_own_comment` (finding names
`public.review_f(text)`); `test_function_signatures_ignore_names_modes_defaults_and_case`
(both overloads commented in other spellings, clean); and
`test_bare_function_name_must_name_one_overload` (the ambiguous comment and both
overloads are findings; a bare name with one overload still documents it). They
replace `test_function_comments_match_argument_count`. Each test's SQL was also
applied to a disposable `qa640_linttests_*` database: the documented routines
received their comments, and the bare `review_f` comment and
`COMMENT ON FUNCTION purge()` failed as the tests state. Against the pre-fix lint
(`git show HEAD:scripts/check_migration_comments.py` beside the new test module
in a scratch directory), the procedure, overload, bare-name, and procedure-lookup
tests fail because that lint reports nothing for them, and the `function` case
differs only in message format. Over every migration (watermark 0) the lint
returns the same 405 findings before and after; only function signatures print
differently (`public.orrery_active_character_tag_names(bigint)` for
`public.orrery_active_character_tag_names (1 argument)`).

Tails at e16f6d28, from the worktree root with
`PY=/Users/pythagor/nexus/.venv/bin/python`; the import proof printed
`/Users/pythagor/nexus/.claude/worktrees/819-ratchet-extension/nexus/__init__.py`,
and `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` were unset:

```text
$ $PY -m pytest -q tests/test_migration_comment_lint.py tests/test_reachability.py
.....................................................................    [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
69 passed in 8.02s

$ PYTHONPATH=$PWD $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.

$ $PY -S scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_schema_documentation_pg.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
33 passed, 5 warnings in 4.76s

$ $PY -m black --check scripts/check_migration_comments.py tests/test_migration_comment_lint.py
All done! ✨ 🍰 ✨
2 files would be left unchanged.

$ $PY -m flake8 scripts/check_migration_comments.py tests/test_migration_comment_lint.py
(no output)

$ $PY -m mypy scripts/check_migration_comments.py tests/test_migration_comment_lint.py
Success: no issues found in 2 source files
```

### Type Alias Table

The coordinator accepted the three additions that follow PostgreSQL (ambiguous
procedure argument lists, `COMMENT ON FUNCTION` not documenting a procedure, and
both `docs/database.md` corrections) and asked for one more change. Signature
normalization now canonicalizes the type spellings PostgreSQL treats as one type,
through `_TYPE_ALIASES` in the lint:

| Spelling | Reads As |
| --- | --- |
| `int`, `int4`, `serial` | `integer` |
| `int8`, `bigserial` | `bigint` |
| `int2` | `smallint` |
| `bool` | `boolean` |
| `varchar` | `character varying` |
| `char` | `character` |
| `float`, `float8` | `double precision` |
| `float4` | `real` |
| `decimal` | `numeric` |
| `varbit` | `bit varying` |
| `timestamptz` | `timestamp with time zone` |
| `timestamp` | `timestamp without time zone` |
| `timetz` | `time with time zone` |
| `time` | `time without time zone` |

Type modifiers, interval fields, and array bounds drop, and every array spelling
(`integer ARRAY`, `integer[3]`, `int4[][]`) reads `integer[]`. `float(p)` is
resolved rather than stripped, because its precision picks the type: `real` for p
up to 24, `double precision` above. Only unquoted words map, so the single-byte
type `"char"` stays distinct from `char`.

PostgreSQL 17 on a disposable `qa640_aliasprobe_*` database (dropped) printed the
canonical name for every entry: `pg_get_function_identity_arguments` of
`al(timestamptz, timestamp(3), time, timetz, varbit(3), char(5), decimal(5,2),
bool, int8, int2, float4, float8, varchar(20), int)` reads `timestamp with time
zone, timestamp without time zone, time without time zone, time with time zone,
bit varying, character, numeric, boolean, bigint, smallint, real, double
precision, character varying, integer`, and a `COMMENT ON FUNCTION` naming those
types applied. `integer ARRAY[3]`, `int4[][]`, and `text ARRAY` read `integer[]`,
`integer[]`, and `text[]`; `interval day to second(3)` and `interval(2)` read
`interval`. `float(24)` reads `real` while `float(25)` and `float` read `double
precision`, so `COMMENT ON FUNCTION fl(float)` fails for `fl(float(24))`
(`function fl(double precision) does not exist`), and `COMMENT ON FUNCTION
qc(char)` fails for `qc("char")` (`function qc(character) does not exist`).
PostgreSQL rejects `serial` and `bigserial` as argument types (`type serial does
not exist`), so a migration that uses one fails when applied, whatever the lint
reports.

`test_function_type_aliases_typmods_and_arrays_match` covers the requested cases,
one migration each: `f(a int)` with `COMMENT ON FUNCTION f(integer)` is clean;
`f(a varchar(20))` with `COMMENT ON FUNCTION f(character varying)` is clean;
array and alias spellings (`integer ARRAY[3]`, `int4[][]`, `timestamptz`, and
`float(24)`, commented as `int[]`, `integer[]`, `timestamp with time zone`, and
`real`) are clean; and `f(a text)` with `COMMENT ON FUNCTION f(integer)` is still
a finding. Its SQL on a disposable `qa640_aliastest_*` database (dropped): the
three clean migrations applied, and the last failed with `function f(integer)
does not exist`. Against e16f6d28's lint the test fails, reporting the `int`,
`varchar(20)`, and array migrations as undocumented. Over every migration
(watermark 0) the lint still returns the same 405 findings, and the read-only
inventory of `NEXUS_template` still gives the counts above.

Tails at the alias-table commit, run the same way:

```text
$ $PY -m pytest -q tests/test_migration_comment_lint.py tests/test_reachability.py
......................................................................   [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
70 passed in 8.20s

$ PYTHONPATH=$PWD $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.

$ $PY -S scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.

$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_schema_documentation_pg.py
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
33 passed, 5 warnings in 5.01s

$ $PY -m black --check scripts/check_migration_comments.py tests/test_migration_comment_lint.py
All done! ✨ 🍰 ✨
2 files would be left unchanged.

$ $PY -m flake8 scripts/check_migration_comments.py tests/test_migration_comment_lint.py
(no output)

$ $PY -m mypy scripts/check_migration_comments.py tests/test_migration_comment_lint.py
Success: no issues found in 2 source files
```

## Commit Attribution

Under the amended common rule, the Opus 5.5 commits on this branch carry their own
`Co-Authored-By: Claude Opus 5.5` line.

## Remaining on #819

1. A backfill migration that comments enums, functions, and views whose
   semantics a reader or writer site establishes, citing that evidence as
   migration 127 does, and retiring the matching baseline entries.
2. The 14 table-column entries and every object without such evidence (including
   the seven unused enums and the six uncalled functions) go to the decision
   ledger (#817).
