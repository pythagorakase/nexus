# Guarded Dead-Strata Retirement: 813-S1

Implementation and clone proof for migration 143. Decisions 813-Q1, Q2 and Q6
bind exactly as recorded in issue #813 and the frozen order. No fleet write,
paid call, gateway, client bundle change, historical migration edit, placeholder
migration or KNOWN_GAPS edit was made. The coordinator owns fleet application.

## Frozen Source and Clone Identities

All commands ran in `/Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata`.
The shared interpreter imported `nexus/__init__.py` from that worktree, both
before proof and before static checks. Initial base: `2e70e9cb`.
Scratch files and pytest temporary files were confined to:
`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/`.

Only `pg_dump` read each owner source. Source environment came from
`tests.pg_fixtures.subprocess_env()`, with
`PGOPTIONS += ' -c default_transaction_read_only=on'`. Full data, custom format:

```text
pg_dump --format=custom --verbose --file <scratch>/<source>.dump --dbname <source>
pg_restore --exit-on-error --no-owner --no-acl --dbname <allocated-clone> <scratch>/<source>.dump
```

The database allocation, connection contract and teardown came from
`tests.pg_fixtures.disposable_database` and `connect`. Sources and targets are
separate; these original frozen clones were dropped by their context managers.
Original archive TOCs (`pg_restore --list`, no connection) confirm `pythagor`
owns every target table, sequence, enum and the shared function on every source.
Restore normalizes clone owners; sequence-to-id ownership edges are preserved.

| Read-Only Source | Disposable Frozen Clone | items Rows | ai_notebook Rows |
| --- | --- | --- | --- |
| `NEXUS_template` | `qa640_813_manifest_8d7acc3b209f` | 0 | 0 |
| `save_01` | `qa640_813_manifest_8275f4bd9273` | 0 | 0 |
| `save_02` | `qa640_813_manifest_89dc5d952adf` | 0 | 0 |
| `save_03` | `qa640_813_manifest_265393eeddde` | 0 | 0 |
| `save_04` | `qa640_813_manifest_f0701f833fb0` | 0 | 0 |
| `save_05` | `qa640_813_manifest_34c17dea5371` | 0 | 0 |

Slot 2 supplies schema and emptiness evidence only; no chronology claim uses it.
Target definitions, enum labels, sequence ownership, constraints, indexes,
columns/defaults/comments and normalized dependency identities agree across all
six frozen sources. The initial incoming closure had 52 catalog addresses;
explicitly listing all 16 table columns adds 14 leaf addresses, giving 66.
There are 62 actual dependency edges (14 additional inventory rows have no
outgoing edge). Both enum-typed columns are notebook.agent and notebook.level;
the other seven enum types have no typed columns. Table row types/arrays, enum
arrays, TOAST tables/indexes, the four RI FK triggers and trg_items_set_updated
are explicitly included. TOAST identifiers and RI trigger OID suffixes normalize;
application object identities stay fully qualified.

All six deferred function definitions/signatures agree. The sole other function
disagreement is whitespace in `public.refresh_world_time_from_chunk_trigger()`
on save_01/save_02 versus template/save_03..05. No source repair was attempted.
Per-clone preservation snapshots retain each source's exact surviving definition.
All 34 non-extension application function/procedure definitions on each frozen
clone were inventoried; none contained EXECUTE. The exact six deferred definitions
and original comments are in `tests/fixtures/813_pre143_manifest.json` under
`deferred_functions`; they remain outside this drop under #812 / 813-Q1.

## Catalog Manifest and Preflight SQL

`tests/fixtures/813_pre143_schema.sql` was extracted from the frozen dump's
schema blocks, including original comments and OWNED BY, before fleet landing.
It recreates only the drop slice and restores only the original shared-function
comment, never its body. `813_pre143_manifest.json` freezes labels, columns,
constraints/indexes, sequences, internal trigger definitions, shared body/comment,
all closure addresses/edges and the deferred definitions. No hand-written
approximation or post-landing source supplies those definitions.

The clone queries were:

```sql
SELECT current_database(), version();
SELECT (SELECT count(*) FROM public.items),
       (SELECT count(*) FROM public.ai_notebook);
SELECT pg_get_serial_sequence('public.items', 'id'),
       pg_get_serial_sequence('public.ai_notebook', 'id');
```

The complete closure query, also used by the guarded fixture loader, is:

```sql
WITH RECURSIVE roots(classid,objid,objsubid) AS (
 SELECT 'pg_class'::regclass::oid,c.oid,0 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('items','ai_notebook')
 UNION SELECT 'pg_class'::regclass::oid,a.attrelid,a.attnum FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('items','ai_notebook') AND a.attnum>0 AND NOT a.attisdropped
 UNION SELECT 'pg_type'::regclass::oid,t.oid,0 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' AND t.typname IN ('agent_type','log_level_type','emotional_valence','entity_type','item_type','relationship_type','threat_domain_type','threat_lifecycle_type','trait')
), closure AS ( SELECT * FROM roots UNION SELECT d.classid,d.objid,d.objsubid FROM pg_depend d JOIN closure c ON d.refclassid=c.classid AND d.refobjid=c.objid AND (c.objsubid=0 OR d.refobjsubid=c.objsubid))
SELECT c.classid::regclass::text,pg_describe_object(c.classid,c.objid,c.objsubid),d.deptype,pg_describe_object(d.refclassid,d.refobjid,d.refobjsubid) FROM closure c LEFT JOIN pg_depend d ON d.classid=c.classid AND d.objid=c.objid AND d.objsubid=c.objsubid ORDER BY 1,2,3,4
```

Migration 143 resolves each target by namespace/OID and locks both tables before
counting either. It validates empty tables, sequence identity/id ownership,
frozen columns/defaults/constraints and internal FK trigger definitions, and
every reached address and outgoing dependency edge before any DROP. It allows
no arbitrary automatic/internal dependent. Target tables/types use RESTRICT;
owned sequences disappear through ownership and are asserted absent afterward.
The shared function body and surviving character/place triggers stay unchanged;
only its exact prescribed comment changes. Transaction-local helper functions
carry comments, are explicitly removed, and introduce no persistent object/debt.

The body guard tokenizes SQL/PLpgSQL comments, literals and quoted identifiers;
resolves types/relations under proconfig/caller search_path; proves NEW/OLD or
query-column types from actual relations; and folds constant EXECUTE concatenation
and format calls before checking their SQL. It rejects unresolved parameters,
runtime path/role changes (including computed setting names), foreign SECURITY
DEFINER context, unsupported languages, Unicode-escape identifiers and unsupported
references. Diagnostic strings and actual varchar relationship columns are
preserved. The migration header documents supported forms and refusal rules.

## Guard Outcomes and Preservation

The new module has 82 real PostgreSQL cases. Six-source success cases rehearse
raw full-data pre-143 restores through the full runner, separately from fixture
reconstruction, comparing all surviving schema/data, other stamps, exact comment
and second-pass `(0, 0)`. Fresh later post-143 sources work without archived dumps:
the guarded loader accepts only complete matching pre/post states, calls
require_disposable_target before connecting, checks current_database against its
allocated qa640_813_* name before writing, and reconstructs + removes only the
143 stamp atomically. Four partial/drifted state probes prove refusal/rollback.

All other required cases repeat after establishing real post-143 schema/stamp
on a fresh clone and reconstructing it. Refusal cases use apply_migration, assert
False and the named offender/target in real runner logs, hash the entire catalog
and data before/after, and assert absence of the stamp. Probes cover both nonempty
tables; view, FK, external default, domain, array column, argument/result and
extra trigger; missing/wrong-kind table and detached/reassigned sequence;
SQL/PLpgSQL/procedure and SQL-standard bodies, quoted cast, CAST AS, declarations,
%TYPE/%ROWTYPE, constant concatenation/format, unresolved parameters, catalog and
sequence lookups, Unicode identifiers and runtime search-path mutation.

Positive probes preserve varchar column names (qualified/aliased/bare/%TYPE),
diagnostic messages, constant safe dynamic SQL and an unrelated assets.item_type
under the function's configured path. A real relationship write derives 2/5.5
and retains its +2 literal; an invalid literal still raises the original message.
A real SQL hybrid_search caller and all six deferred definitions survive.
The real normalized wizard cache-to-transition path persists protagonist and
location on the migrated routed TEST clone. No database/mock or provider mock
replaces these paths. All clone story pins are TEST before preceding migrations.

Preservation dumps include owners and ACLs. Only public target table/sequence
blocks, the nine public enum blocks, the public shared-function comment and the
143 stamp are excluded; all other migration stamps are compared separately,
including raw rehearsal and reconstruction. The TEST pin is established before
snapshots. Database-private temporary schemas are not persistent dump objects.

## Validation Commands and Verbatim Tails

`PY=/Users/pythagor/nexus/.venv/bin/python`; `PYTHONPATH=$PWD` and TMPDIR point
at this worktree and order scratch respectively. Foreground pytest commands ran
under scratch `run.py` with subprocess timeout 540 seconds, printed exit statuses,
and completed before the next gate. Expected numbering failure:
`tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps`
names missing 141 and 142. KNOWN_GAPS remains {'013', '119'}; no placeholders.
The coordinator integrates 141/142 before landing 143 and reruns the proof.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_orrery/test_retrograde_constraints_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
dbname audit: 104 targets: nexus_m10_fresh_test_15257, nexus_m10_template_test_15257, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_813_case_* x78, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_issue601_* x4, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 340 passed in 243.74s (0:04:03)
EXIT STATUS: 1
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py tests/test_schema_documentation_pg.py
```

```text
...........................................                              [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 87 targets: postgres, qa640_813_case_* x82, qa640_docs_refresh_*, qa640_schema_docs_* x3
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
115 passed in 217.64s (0:03:37)
EXIT STATUS: 0
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2735 passed, 480 skipped, 8 warnings in 453.72s (0:07:33)
EXIT STATUS: 0
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1828 passed, 822 skipped, 7 warnings in 38.52s
EXIT STATUS: 1
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.25s
EXIT STATUS: 0
```

```sh
PYTHONPATH=$PWD "$PY" scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
EXIT STATUS: 0
```

```sh
"$PY" -m black --check nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
EXIT STATUS: 0
```

```sh
"$PY" -m mypy --explicit-package-bases nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
EXIT STATUS: 0
```

```sh
"$PY" -m mypy --explicit-package-bases /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_enums.py
```

```text
Success: no issues found in 3 source files
EXIT STATUS: 0
```

## Pre-Existing Diagnostics

Sanctioned mypy invocation uses --explicit-package-bases; branch: success in four
files, origin/main versions: success in three files. Each uses an isolated scratch
MYPY_CACHE_DIR; MYPYPATH on baseline puts the scratch origin-main tree before the
worktree. Flake8 runs on the same branch files, then on git-show origin/main
versions of the three pre-existing files. Every final branch diagnostic equals
main's message/path modulo line shifts: 17 pre-existing diagnostics on untouched
lines, no new-file diagnostic and no added/changed-line diagnostic. None fixed.
Exact branch and baseline outputs follow (each exit 1):

```sh
"$PY" -m flake8 nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
nexus/api/new_story_db_mapper.py:687:89: E501 line too long (91 > 88 characters)

```

```sh
"$PY" -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_enums.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:689:89: E501 line too long (91 > 88 characters)
EXIT STATUS: 1

```

## Development Failures Corrected

Initial -x run: missing template global_variables row while applying the TEST
pin (1 failed in 15.41s). Clone preparation now inserts that row before pinning.
The next -x run reached 54 passes before a relationship probe lacked required
dynamic/recent_events/history values; the probe now supplies all required fields.
A temporary string-wrapping error in the test was fixed before final proof.
The stricter dependency-edge pass initially omitted the explicit ::text cast on
pg_depend.deptype (PostgreSQL internal "char"), causing `operator is not unique:
text || "char"`. The cast was fixed; every later relevant run passed except the
named numbering gap. Temporary E501/Black formatting diagnostics on new test
lines were fixed; the final diagnostics above are solely untouched main debt.
The earlier unguarded-body smoke runner applied 143 successfully, and the later
strict-edge smoke printed `RESULT True`, both against disposable template clones.

Earlier complete proof tails, superseded by the final runs above:

```text
development:
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed, 54 passed in 157.17s (0:02:37)
EXIT STATUS: 1
```

```text
development-live:
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed, 54 deselected in 16.96s
EXIT STATUS: 1
```

```text
development-live2:
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed, 56 deselected, 1 warning in 19.29s
EXIT STATUS: 1
```

```text
development-live3:
dbname audit: owner targets: none
6 passed, 56 deselected in 25.92s
EXIT STATUS: 0
```

```text
proof:
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 332 passed in 228.30s (0:03:48)
EXIT STATUS: 1
```

```text
proof-final:
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction
71 failed, 221 passed, 41 errors in 124.99s (0:02:04)
EXIT STATUS: 1
```

```text
proof-final2:
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 332 passed in 238.52s (0:03:58)
EXIT STATUS: 1
```

```text
proof-release:
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 336 passed in 249.18s (0:04:09)
EXIT STATUS: 1
```

## Rebased Final Proof

Rebased cleanly onto `origin/main` at
`56b7854a1f6b62ccddb0417e0dda8446620ddcbd`. Product and tests at
`b0cd365d582ba8381b251b0b84808ebfe6095a7c`; the follow-up commit records
only this refreshed evidence. Import verification again resolved to this
worktree. All foreground commands completed; the required proof and both
offline splits were rerun. Commit hooks passed. No new diagnostic appeared.

These final tails supersede the earlier development-stage counts above.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_orrery/test_retrograde_constraints_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
tests/test_orrery/test_migrate.py:266: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 108 targets: nexus_m10_fresh_test_57702, nexus_m10_template_test_57702, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_813_case_* x82, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_issue601_* x4, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 344 passed in 254.63s (0:04:14)
EXIT STATUS: 1
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2840 passed, 480 skipped, 8 warnings in 465.61s (0:07:45)
EXIT STATUS: 0
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1830 passed, 834 skipped, 7 warnings in 34.22s
EXIT STATUS: 1
```

Static checks were refreshed against the same origin/main. The main
versions of the three pre-existing changed Python files were copied using
`git show origin/main:<path>` into the order scratch, never a checkout edit.
The 17 flake8 messages agree exactly modulo line shifts and path prefix;
all are on untouched lines. The new test module has no diagnostic.
Mypy uses the sanctioned `--explicit-package-bases` invocation.

```sh
/Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.21s
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
nexus/api/new_story_db_mapper.py:687:89: E501 line too long (91 > 88 characters)
EXIT STATUS: 1
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_enums.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py:689:89: E501 line too long (91 > 88 characters)
EXIT STATUS: 1
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/origin-main/nexus/agents/logon/apex_enums.py
```

```text
Success: no issues found in 3 source files
EXIT STATUS: 0
```

## Landing and Open Questions

No owner decision is added or reopened. The six functions wait for #812; 813-Q3
labels and Q5's separate MEMNON SQL slice remain unchanged. Legacy NEXUS, mocks,
backups and rehearsals are outside the template-plus-five-slot runner fleet.

The coordinator integrates 140/141/142 first, restores fresh full-data pre-143
sources into TEST clones, reruns the full runner rehearsal without reconstruction
or stamp removal, and records identical preservation/comment/repeat assertions.
After pulling product code, restart the owner gateway by name (`nexus restart
gateway`) before/with fleet application. Only the coordinator runs --all,
--slot 1 --write-locked-slot, and --template, confirms stamps/absence/comment on
all six sources, and reruns this regression file against fresh post-143 dumps
and the final whole-tree PostgreSQL gate. No UI rebuild is owed. No merge here.

Open questions for the coordinator: none; sequencing and landing work remain.

Authored by Codex, running GPT-6.


## After the Independent Review

Fix order `1098-astra-fix.md`, against frozen parent `121465222bb227e667095a4ef6994277729ab2a0`.
All four findings are applied without changing the drop manifest, reconstruction
fixture, shared function body, surviving triggers, six deferred helpers, or
schema-documentation debt. No paid provider call or owner database write occurred.

1. Candidate names now come from the complete catalog type closure, including
   each enum, table row type and actual generated array `pg_type.typname`. The
   lexer resolves quoted/unquoted and schema-qualified spellings with fresh OIDs.
   The array probes refuse with both `probe813` and the actual type identity.
2. A candidate immediately followed by a string is a typed literal. Column proof
   is restricted to qualified occurrences or a SELECT column-list position whose
   relation and unrelated actual column type resolve through the catalog.
   `emotional_valence '+2|friendly'` refuses; a bare SELECT of the live varchar
   column and the real valence trigger/diagnostic/write still pass.
3. Catalog casts are inspected from CAST/AS or `::`, including enclosing
   parentheses and `pg_catalog` qualification. Literal regclass/regtype/regproc/
   regprocedure/regtypeoid expressions resolve through the catalog; closure
   references and unresolved literals refuse. Concatenations, parameters,
   function calls and column expressions refuse as unresolved rather than being
   evaluated. Surviving characters/places and set_updated_at catalog casts pass
   and return the same OIDs after retirement.
4. `SET LOCAL lock_timeout = '5s';` is the first SQL statement. The header records
   ACCESS EXCLUSIVE locks on dropped relations/types and a five-second maximum
   wait for each acquisition, with transaction rollback on timeout. A real
   competing ACCESS SHARE transaction causes lock timeout and leaves all schema,
   rows, comments and stamps unchanged, before and after reconstruction.

The module now has 114 real PostgreSQL cases (82 before this review), including
all new refusal/pass cases repeated from complete post-143 clones. The 34-case
verbose subset below names the review probes, pass cases and reconstruction
counterparts. The separate six-source rerun takes new read-only full-data dumps
of `NEXUS_template`, `save_01`, `save_02`, `save_03`, `save_04` and `save_05`,
restores each through `disposable_database("qa640_813_case")`, pins TEST, exercises
raw pre-143 runner rehearsal plus reconstruction, compares schema/data/comments
and other stamps, and verifies that the second full-runner pass applies nothing.
All allocations are dropped by their fixture context; no archived dump is used.
Slot 2 remains schema/emptiness evidence only, never time evidence.

### Gate Results and Coordinator Follow-up

The complete ordered PostgreSQL proof: 376 passed, with only the expected
`test_migration_sequence_has_only_known_gaps` failure naming reserved 141 and 142.
The focused review subset: 34 passed; the separate fresh fleet rerun: all six
passed. Every pytest command below has the secret-store guard active and the
owner-target audit reports none. Offline skips are not counted as PostgreSQL proof.

Offline root and API suites and reachability passed. Offline Orrery has only the
same expected sequence failure. The remaining core directories have one unrelated
failure: `tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline`.
It reports four `wizard_chat.py` baseline growth entries against origin/main
`8ccd3008a48bdf8115232667399868e2bdf66f93` (the newer shared ref observed during
this run); the HEAD comparison is clean. Neither wizard_chat.py nor its baseline
changed under this fix order. The common protocol requires reporting, not fixing,
unrelated failures. No ordered change here made this baseline stale.

Black and migration comments pass. Sanctioned mypy uses
`--explicit-package-bases` and passes on both branch and main copies. The 17
flake8 diagnostics match exactly modulo file prefixes and line shifts, are on
untouched pre-existing lines, and are reproduced below. Main copies were read
using `git show 8ccd3008a48bdf8115232667399868e2bdf66f93:<path>` into this order's
scratch directory, never into another checkout.

No rebase was performed: this fix order and the user's instructions require
fix commits only and explicitly prohibit history rewrite, overriding the generic
common-workflow rebase instruction. Integrating preceding migrations and resolving
unrelated main/branch baseline divergence remain coordinator tasks. No merge or
new PR was made. All four fixes and their proof were applied; no fix was deferred.

### Exact Commands and Verbatim Tails

Every command ran from the assigned worktree. Long commands were executed
sequentially through the existing scratch `run.py` with a 540-second subprocess
timeout, and were awaited to completion. `PYTHONPATH=$PWD` and `TMPDIR` were set
to this worktree and this order's `after-review/` scratch, respectively. Mypy
uses separate caches in that same scratch. No shared venv install occurred.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k 'hidden_body_reference or accepts_live_relationship or accepts_surviving_catalog'
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 34 targets: postgres, qa640_813_case_* x33
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
33 passed, 75 deselected in 64.59s (0:01:04)
EXIT STATUS: 0
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_orrery/test_retrograde_constraints_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
=================================== FAILURES ===================================
_________________ test_migration_sequence_has_only_known_gaps __________________

    def test_migration_sequence_has_only_known_gaps() -> None:
        """A new hole or a reused historical hole in the numbering fails."""
    
        versions = _on_disk_versions()
        head = max(int(version) for version in versions)
        missing = {f"{number:03d}" for number in range(1, head + 1)} - set(versions)
    
        assert min(versions) == "001"
>       assert missing == KNOWN_GAPS
E       AssertionError: assert {'013', '119', '141', '142'} == frozenset({'013', '119'})
E         
E         Extra items in the left set:
E         '142'
E         '141'
E         Use -v to get more diff

tests/test_orrery/test_migrate.py:266: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 140 targets: nexus_m10_fresh_test_21595, nexus_m10_template_test_21595, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_813_case_* x114, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_issue601_* x4, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 376 passed in 317.98s (0:05:17)
EXIT STATUS: 1
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k drops_only_manifest_on_each_fleet_clone
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[NEXUS_template] PASSED [ 16%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_01] PASSED [ 33%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_02] PASSED [ 50%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_03] PASSED [ 66%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_04] PASSED [ 83%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_05] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 7 targets: postgres, qa640_813_case_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
================= 6 passed, 108 deselected in 79.08s (0:01:19) =================
EXIT STATUS: 0
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util --ignore=tests/config --ignore=tests/proofs
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1933 passed, 410 skipped, 8 warnings in 359.24s (0:05:59)
EXIT STATUS: 0
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util tests/config tests/proofs
```

```text
=================================== FAILURES ===================================
_______________ test_repository_tree_matches_committed_baseline ________________

    def test_repository_tree_matches_committed_baseline() -> None:
        root = CHECKER.parents[1]
        assert lint.check_tree(root, root / lint.BASELINE_PATH, "HEAD") == []
>       assert lint.check_tree(root, root / lint.BASELINE_PATH, "origin/main") == []
E       AssertionError: assert ['nexus/api/w...21bbe32550|1'] == []
E         
E         Left contains 4 more items, first extra item: 'nexus/api/wizard_chat.py:1168: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.wizard_events|2e26b6145d23378bbe531f8663edbfc55460043d18da997bc263bca43ef00e4b|1'
E         Use -v to get more diff

tests/test_scripts/test_check_exception_dispositions.py:636: AssertionError

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline
1 failed, 906 passed, 70 skipped, 7 warnings in 74.96s (0:01:14)
EXIT STATUS: 1
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_api
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
641 passed, 240 skipped, 7 warnings in 22.15s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
EXIT STATUS: 0
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_orrery
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1189 passed, 626 skipped, 2 warnings in 9.03s
EXIT STATUS: 1
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_reachability.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
54 passed in 9.15s
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
nexus/api/new_story_db_mapper.py:687:89: E501 line too long (91 > 88 characters)
EXIT STATUS: 1
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/agents/logon/apex_enums.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py:689:89: E501 line too long (91 > 88 characters)
EXIT STATUS: 1
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review/origin-main/nexus/agents/logon/apex_enums.py
```

```text
Success: no issues found in 3 source files
EXIT STATUS: 0
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k 'sql-array or sql-quoted-array or sql-row-array or sql-typed-literal or catalog or relationship or lock'
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-array-cast] PASSED [  2%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-quoted-array-cast] PASSED [  5%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-row-array-cast] PASSED [  8%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-typed-literal] PASSED [ 11%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-cast] PASSED [ 14%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-cast-parentheses] PASSED [ 17%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-parentheses] PASSED [ 20%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype] PASSED [ 23%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-format] PASSED [ 26%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-concat] PASSED [ 29%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-column] PASSED [ 32%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-parameter] PASSED [ 35%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-suffix] PASSED [ 38%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-parentheses] PASSED [ 41%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_conflicting_lock_atomically PASSED [ 44%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-array-cast] PASSED [ 47%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-quoted-array-cast] PASSED [ 50%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-row-array-cast] PASSED [ 52%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-typed-literal] PASSED [ 55%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-cast] PASSED [ 58%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-cast-parentheses] PASSED [ 61%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-parentheses] PASSED [ 64%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regtype] PASSED [ 67%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-computed-format] PASSED [ 70%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-computed-concat] PASSED [ 73%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-computed-column] PASSED [ 76%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-computed-parameter] PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-computed-suffix] PASSED [ 82%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-computed-parentheses] PASSED [ 85%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[lock] PASSED [ 88%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[relationship] PASSED [ 91%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[catalog] PASSED [ 94%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_live_relationship_column_names PASSED [ 97%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_surviving_catalog_casts PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 35 targets: postgres, qa640_813_case_* x34
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
================= 34 passed, 80 deselected in 88.81s (0:01:28) =================
EXIT STATUS: 0
```

Unrelated baseline diagnostic inventory (read-only):

```text
BASELINE REF: 8ccd3008a48bdf8115232667399868e2bdf66f93
nexus/api/wizard_chat.py:1168: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.wizard_events|2e26b6145d23378bbe531f8663edbfc55460043d18da997bc263bca43ef00e4b|1
nexus/api/wizard_chat.py:1210: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.wizard_events|326cd8cce1c1e55ab05eb3c7bc20df030ab107da8b427799b8070ce405d49952|1
nexus/api/wizard_chat.py:772: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_endpoint|fb0fba2b5d218b71a960a846f0e49c24022812e642d4b532e743048bb69734d8|1
nexus/api/wizard_chat.py:815: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_endpoint|730a0ad62f7e700aedc6d1c8b16ab2f8cab571a9ca7336c33066c121bbe32550|1
HEAD diagnostics: []
```
