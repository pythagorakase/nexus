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


## After the Second Independent Review

### STOP-REPORT: Catalog Re-Creation Conflicts With the Mandatory Migration Lint

Round-two fix order `1098-astra-fix-r2.md`, frozen parent/current HEAD
`fc7d298ecfd2b38f702a3139dff61ecf38ba973a`. **No fix commit was created and no
push was made:** the real `check-migration-comments` commit hook refused the
ordered post-drop `EXECUTE f.definition`. The pending migration, tests and this
report are staged in the assigned worktree. No history rewrite, stash, merge or
new PR occurred. PR #1098 is updated to identify the pending patch and blocker.

The new checker diagnostic is not a stale fingerprint, allowlist, exemption
entry or pinned baseline. `scripts/check_migration_comments.py:1246-1279` explicitly
rejects EXECUTE whose command is built at runtime, and has no exemption entry to
update. The fix order requires re-creating every surviving public routine from
`pg_get_functiondef(oid)`. A literal DML prefix or hiding this DDL would evade the
check; an exception would change its rule. Neither was applied. The common
protocol's stop-report escape hatch applies. The coordinator must resolve this
rule conflict before the patch can be committed/pushed; the checker and its
repository test remain intact.

### Pending Implementation and Preservation Proof

1. Catalog input types now include regclass, regtype, regproc, regprocedure,
   regoper, regoperator, regconfig, regdictionary, regnamespace, regrole and
   regcollation. Typed literals, function-style casts, CAST AS, :: and to_reg*
   are classified. Literal operands resolve through catalog input functions;
   closure references and unresolved literals refuse. Nonliteral operands
   refuse as unresolved, without evaluation. The existing regtypeoid spelling
   remains in the previous CAST/:: compatibility path.
2. Ordinary/doubled-quote, E/backslash, U&/optional UESCAPE, B, X, N,
   dollar/tagged and newline-concatenated literals are single string tokens.
   Unknown prefixes and invalid/unclosed literals refuse. Only validated literal
   grammar is decoded by PostgreSQL. The Unicode enum literal cannot borrow the
   unrelated varchar column's exemption. Invalid B/X enum and nonexistent
   to_reg* function forms are planted with check_function_bodies=off deliberately
   to demonstrate fail-closed scanner behavior, not valid SQL execution.
3. SELECT, WHERE, HAVING, ON, GROUP BY, ORDER BY, RETURNING, function arguments
   and UPDATE SET positions require catalog proof on named relations/aliases.
   Type contexts do not borrow column proof. The WHERE and HAVING/ORDER BY
   consumers are executed after a real relationship write; the deriving trigger
   and its diagnostic are preserved. Unrelated %TYPE still passes.
4. The scanner is the first line; after the restrictive drops and before comment
   writes/stamping, the second line re-creates every public function/procedure
   from pg_get_functiondef with check_function_bodies=on and its effective path.
   Public is the namespace of every explicit drop target. A named re-creation
   failure rolls back the entire migration. A scratch plant removes only the
   scanner invocation: SQL target queries and PLpgSQL target declarations still
   refuse, both before and after post-143 reconstruction.

The header states the residual risk plainly: neither defense completely covers
PLpgSQL expression-level references. SQL parse/analyze and PLpgSQL declaration
validation are not a claim of complete PLpgSQL expression validation.

Real catalog comparisons include routine OIDs, definitions, ownership, ACLs,
proconfig and comments (excluding only the ordered shared-trigger comment).
An explicit REVOKE/GRANT on the varchar WHERE consumer is preserved. Full-data
schema/data/trigger/stamp snapshots retain all other objects and rows. The
manifest, fixture, deferred six helper definitions, schema debt baseline,
product files, migration runner and ratchets are unchanged by this round.

### Before-Fix Evidence

The scratch `old_scanner.py` pytest plugin points only this module's MIGRATION at
an immutable `git show` copy; production/worktree SQL is never temporarily
reverted. `round2.sql` is fc7d298e's migration; `round1.sql` is 12146522's migration
plus only a seven-second statement_timeout to safely bound its missing-lock-
timeout probe. All plants run through the real apply_migration runner on
allocated clones, which are dropped even when an assertion fails.

- Round-one scanner: all 25 selected array, typed-literal, catalog CAST/computed,
  lexical-form and lock regressions fail. The lock failure is statement timeout,
  not the required lock timeout. The catalog-regtype case is included in the
  additional catalog run.
- Round-two parent: 65 failures/16 passes reproduce the new catalog forms,
  Unicode/N/B/X/unknown-prefix escapes, required column pass case, and absence
  of the independent second line. Existing guarded CAST/:: forms remain green.
- Additional round-one catalog matrix: 65 failures/2 passes. The two already-
  guarded to_regclass/to_regtype computed lookups were already refused by that
  parent; they are retained coverage, not claimed as new escapes. Every added
  failing refusal form has a red tail in these runs. No guard was artificially
  disabled to turn those two existing refusals red.

### Gate Results, Scope and Cleanup

- Migration module: **272 passed**, split into 143 direct/independent/fixture
  cases and 129 complete-post-143 reconstruction cases.
- Remaining ordered PostgreSQL files: **262 passed**, only the expected
  `test_migration_sequence_has_only_known_gaps` failure naming reserved 141/142.
  The full ordered proof therefore has 534 passes and that one named failure.
- Separate fresh fleet rerun: **six passed**, one source each from NEXUS_template
  and save_01..05, restored into qa640_813_case_* via read-only custom pg_dump
  and clone-only pg_restore. The original manifest's frozen source identities
  remain above. The fresh audit records six unique disposable allocations;
  each loader verifies its allocated current_database identity before writes.
  This rerun exercises raw pre-143 full-runner rehearsal, then reconstruction,
  compares preservation and checks a second runner pass applies nothing.
  Slot 2 remains schema/emptiness and preservation evidence, never time evidence.
- Audited offline root: 1932 passed/410 skipped, with the new mandatory migration-
  lint failure. Audited remaining core directories: 906 passed/70 skipped,
  with the existing four-entry wizard exception-baseline failure at
  `tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline`.
  It is unrelated to this order and is reported, not repaired.
- Audited offline API/Orrery: 1830 passed/1024 skipped, with only the same reserved-
  number failure. Offline skips are not counted as PostgreSQL proof.
- Reachability: 54 passed. Black and sanctioned explicit-package-bases mypy pass.
  Final flake8 has only the same 17 pre-existing diagnostics as origin/main
  `8ccd3008a48bdf8115232667399868e2bdf66f93`; paths/line shifts normalized and
  multisets compared. Two added long strings were wrapped with an asserted
  identical Python AST. No executable Python changed after the database proofs.
- Migration-comment command and real commit hook both fail at migration line
  1092: EXECUTE f.definition is runtime-built, unverifiable DDL. Other hooks pass.
  No hook bypass or linter weakening was used. The stop report records this
  required rule conflict, rather than treating it as an unrelated exemption.
- A read-only admin query on postgres confirms **no qa640_813_case_* database
  remains**. No paid call, owner/template write, or service start occurred.

Each completed audited pytest gate below has the active secret-store guard and
owner targets: none. The existing C ReplicationConnection audit limitation is
printed verbatim, as in prior runs. The first combined offline attempt was
interrupted to split by directory; a short first root attempt was interrupted
because its audit flag was missing. Neither partial, unaudited run is a gate.

### Exact Commands and Verbatim Tails

All commands execute from this worktree. The scratch run.py gives each child a
540-second duration bound and 120-second silence bound, sets PYTHONPATH to the
worktree plus the plugin directory, and TMPDIR to this order's after-review-r2
scratch. Every process was awaited; no command started by this fixer remains running. No rebase was
performed because the user requires fix commits only and forbids history rewrite.

#### red-round1

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/round1.sql /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k '(refuses_hidden and (sql-array or sql-quoted-array or sql-row-array or sql-typed-literal or sql-catalog-cast or sql-catalog-parentheses or sql-catalog-computed or sql-literal)) or refuses_conflicting_lock'
```

```text
        archives: dict[str, Path], tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A real competing transaction hits the five-second bound and rolls back."""
        with _clone(archives, tmp_path) as dbname:
            _load_fixture(dbname)
>           _lock_refusal(dbname, caplog)

tests/test_orrery/test_migration_dead_strata_pg.py:722: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

dbname = 'qa640_813_case_0e74765e2290'
caplog = <_pytest.logging.LogCaptureFixture object at 0x10d3d8990>

    def _lock_refusal(dbname: str, caplog: pytest.LogCaptureFixture) -> None:
        before, stamps = _snapshot(dbname, surviving=False), _stamps(dbname)
        with closing(connect(dbname)) as blocker, blocker.cursor() as cur:
            cur.execute("LOCK TABLE public.items IN ACCESS SHARE MODE")
            caplog.clear()
            assert not _apply(dbname)
>           assert "lock timeout" in caplog.text, caplog.text
E           AssertionError: ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - canceling statement due to statement timeout
E             CONTEXT:  SQL statement "LOCK TABLE public.items IN ACCESS EXCLUSIVE MODE"
E             PL/pgSQL function inline_code_block line 449 at EXECUTE
E             
E             
E           assert 'lock timeout' in 'ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - canceling statement due to statement ti...tement "LOCK TABLE public.items IN ACCESS EXCLUSIVE MODE"\nPL/pgSQL function inline_code_block line 449 at EXECUTE\n\n'
E            +  where 'ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - canceling statement due to statement ti...tement "LOCK TABLE public.items IN ACCESS EXCLUSIVE MODE"\nPL/pgSQL function inline_code_block line 449 at EXECUTE\n\n' = <_pytest.logging.LogCaptureFixture object at 0x10d3d8990>.text

tests/test_orrery/test_migration_dead_strata_pg.py:709: AssertionError
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - canceling statement due to statement timeout
CONTEXT:  SQL statement "LOCK TABLE public.items IN ACCESS EXCLUSIVE MODE"
PL/pgSQL function inline_code_block line 449 at EXECUTE
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 26 targets: postgres, qa640_813_case_* x25
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-array-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-quoted-array-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-row-array-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-typed-literal]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-cast-parentheses]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-parentheses]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-format]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-concat]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-column]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-parameter]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-computed-parentheses]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-ordinary]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-escaped]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode-escape]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-national]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-binary]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-hex]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-dollar]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-tagged]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-adjacent]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unknown]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_conflicting_lock_atomically
25 failed, 245 deselected in 54.79s
EXIT STATUS: 1
```

#### red-round2

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/round2.sql /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k '(refuses_hidden and (sql-catalog-reg or computed-lookup or sql-literal)) or accepts_live_relationship or recreation_refuses'
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 82 targets: postgres, qa640_813_case_* x81
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode-escape]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-national]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-binary]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-hex]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unknown]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_live_relationship_column_names
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[SELECT count(*) FROM public.items]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[DECLARE v public.item_type; BEGIN RETURN; END]
65 failed, 16 passed, 189 deselected in 122.34s (0:02:02)
EXIT STATUS: 1
```

#### red-catalog-round1

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/round1.sql /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k 'refuses_hidden and (sql-catalog-reg or computed-lookup)'
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 68 targets: postgres, qa640_813_case_* x67
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regtype-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regproc-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regprocedure-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoper-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-lookup]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-typed]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-call]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-cast]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-suffix]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-lookup]
65 failed, 2 passed, 205 deselected in 105.04s (0:01:45)
EXIT STATUS: 1
```

#### pg-regressions

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k 'not regressions_work_from_post143_clone'
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-call] PASSED [ 60%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-cast] PASSED [ 60%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-suffix] PASSED [ 61%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regoperator-computed-lookup] PASSED [ 62%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-typed] PASSED [ 62%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-call] PASSED [ 63%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-call] PASSED [ 64%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-cast] PASSED [ 65%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-suffix] PASSED [ 65%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regconfig-computed-lookup] PASSED [ 66%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-typed] PASSED [ 67%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-call] PASSED [ 67%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-call] PASSED [ 68%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-cast] PASSED [ 69%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-suffix] PASSED [ 69%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regdictionary-computed-lookup] PASSED [ 70%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-typed] PASSED [ 71%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-call] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-call] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-cast] PASSED [ 73%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-suffix] PASSED [ 74%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regnamespace-computed-lookup] PASSED [ 74%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-typed] PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-call] PASSED [ 76%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-call] PASSED [ 76%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-cast] PASSED [ 77%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-suffix] PASSED [ 78%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-lookup] PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-typed] PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-call] PASSED [ 80%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-call] PASSED [ 81%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-cast] PASSED [ 81%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-suffix] PASSED [ 82%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-lookup] PASSED [ 83%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-ordinary] PASSED [ 83%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-escaped] PASSED [ 84%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode] PASSED [ 85%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode-escape] PASSED [ 86%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-national] PASSED [ 86%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-binary] PASSED [ 87%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-hex] PASSED [ 88%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-dollar] PASSED [ 88%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-tagged] PASSED [ 89%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-adjacent] PASSED [ 90%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unknown] PASSED [ 90%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_conflicting_lock_atomically PASSED [ 91%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_live_relationship_column_names PASSED [ 92%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_surviving_catalog_casts PASSED [ 93%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_preserves_deferred_function_consumers PASSED [ 93%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_new_story_transition_after_migration_143 PASSED [ 94%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[SELECT count(*) FROM public.items-False] PASSED [ 95%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[SELECT count(*) FROM public.items-True] PASSED [ 95%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[DECLARE v public.item_type; BEGIN RETURN; END-False] PASSED [ 96%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[DECLARE v public.item_type; BEGIN RETURN; END-True] PASSED [ 97%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_pre143_fixture_refuses_partial_or_drifted_clone[partial-pre] PASSED [ 97%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_pre143_fixture_refuses_partial_or_drifted_clone[drifted-pre] PASSED [ 98%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_pre143_fixture_refuses_partial_or_drifted_clone[partial-post] PASSED [ 99%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_pre143_fixture_refuses_partial_or_drifted_clone[drifted-post] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 144 targets: postgres, qa640_813_case_* x143
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=============== 143 passed, 129 deselected in 290.32s (0:04:50) ================
EXIT STATUS: 0
```

#### pg-reconstruction

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k regressions_work_from_post143_clone
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-typed] PASSED [ 55%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-call] PASSED [ 56%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-computed-call] PASSED [ 57%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-computed-cast] PASSED [ 58%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-computed-suffix] PASSED [ 58%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-computed-lookup] PASSED [ 59%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-typed] PASSED [ 60%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-call] PASSED [ 61%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-computed-call] PASSED [ 62%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-computed-cast] PASSED [ 62%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-computed-suffix] PASSED [ 63%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-computed-lookup] PASSED [ 64%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-typed] PASSED [ 65%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-call] PASSED [ 65%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-computed-call] PASSED [ 66%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-computed-cast] PASSED [ 67%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-computed-suffix] PASSED [ 68%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-computed-lookup] PASSED [ 68%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-typed] PASSED [ 69%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-call] PASSED [ 70%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-computed-call] PASSED [ 71%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-computed-cast] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-computed-suffix] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-computed-lookup] PASSED [ 73%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-typed] PASSED [ 74%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-call] PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-computed-call] PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-computed-cast] PASSED [ 76%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-computed-suffix] PASSED [ 77%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-computed-lookup] PASSED [ 78%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-typed] PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-call] PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-computed-call] PASSED [ 80%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-computed-cast] PASSED [ 81%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-computed-suffix] PASSED [ 82%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-computed-lookup] PASSED [ 82%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-typed] PASSED [ 83%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-call] PASSED [ 84%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-computed-call] PASSED [ 85%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-computed-cast] PASSED [ 86%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-computed-suffix] PASSED [ 86%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-computed-lookup] PASSED [ 87%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-ordinary] PASSED [ 88%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-escaped] PASSED [ 89%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-unicode] PASSED [ 89%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-unicode-escape] PASSED [ 90%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-national] PASSED [ 91%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-binary] PASSED [ 92%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-hex] PASSED [ 93%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-dollar] PASSED [ 93%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-tagged] PASSED [ 94%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-adjacent] PASSED [ 95%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-unknown] PASSED [ 96%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[lock] PASSED [ 96%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[relationship] PASSED [ 97%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[catalog] PASSED [ 98%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[deferred] PASSED [ 99%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[transition] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 130 targets: postgres, qa640_813_case_* x129
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=============== 129 passed, 143 deselected in 315.41s (0:05:15) ================
EXIT STATUS: 0
```

#### pg-ordered-files

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_schema_documentation_pg.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_orrery/test_retrograde_constraints_pg.py tests/test_pg_disposable_target.py tests/test_owner_target_guard.py
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
...................................................F.................... [ 27%]
........................................................................ [ 54%]
........................................................................ [ 82%]
...............................................                          [100%]
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
E         '141'
E         '142'
E         Use -v to get more diff

tests/test_orrery/test_migrate.py:266: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 26 targets: nexus_m10_fresh_test_16340, nexus_m10_template_test_16340, postgres, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_issue601_* x4, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa885_transaction_writer_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 262 passed in 39.20s
EXIT STATUS: 1
```

#### fleet-clones

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k drops_only_manifest_on_each_fleet_clone
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 272 items / 266 deselected / 6 selected

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
================= 6 passed, 266 deselected in 81.06s (0:01:21) =================
EXIT STATUS: 0
```

#### offline-root-audited

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util --ignore=tests/proofs
```

```text
.............sss....................................................ssss [ 39%]
ss.................ss................................................... [ 43%]
........................................................................ [ 46%]
........ss..ss................................ssssssssssss.............. [ 49%]
............................................ssssssssssssssssssssssssssss [ 52%]
ssssssssssssssssssssss.................................................. [ 55%]
..............................sssssssssssssssss......................... [ 58%]
................................s.ssssss................................ [ 61%]
........................................................................ [ 64%]
....s.....ssssssssssssssssss........s...ss.....................s........ [ 67%]
..................sssssssssssssssssssssss......................sss...... [ 70%]
.............s..................................................ssssss.. [ 73%]
......................................................ssssssssssssssss.s [ 76%]
s...........................sssss....................................... [ 79%]
...................ssssssssssssssssssssssssssssssssss................... [ 83%]
........................................................................ [ 86%]
.................ss..................................................... [ 89%]
......................................s..s.............................s [ 92%]
sss.................sssss...................................sssss....... [ 95%]
............sss.................ssss.................................... [ 98%]
..........sssssssssssssssssssssssssss                                    [100%]
=================================== FAILURES ===================================
_______________________ test_repository_migrations_pass ________________________

    def test_repository_migrations_pass() -> None:
        """The real tree passes, and the command-line gate agrees."""
>       assert check_migrations(REPO_ROOT / "migrations") == []
E       assert [Finding(path...be verified")] == []
E         
E         Left contains one more item: Finding(path=PosixPath('/Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata/migrations/143_drop_dead_schema_s...), line=1092, message="EXECUTE 'f.definition' runs a command built at run time; its schema changes cannot be verified")
E         Use -v to get more diff

tests/test_migration_comment_lint.py:1268: AssertionError
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_migration_comment_lint.py::test_repository_migrations_pass
1 failed, 1932 passed, 410 skipped, 8 warnings in 355.09s (0:05:55)
EXIT STATUS: 1
```

#### offline-directories

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util tests/config tests/proofs
```

```text
E         Left contains 4 more items, first extra item: 'nexus/api/wizard_chat.py:1168: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.wizard_events|2e26b6145d23378bbe531f8663edbfc55460043d18da997bc263bca43ef00e4b|1'
E         Use -v to get more diff

tests/test_scripts/test_check_exception_dispositions.py:636: AssertionError
----------------------------- Captured stderr call -----------------------------
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline
1 failed, 906 passed, 70 skipped, 7 warnings in 76.16s (0:01:16)
EXIT STATUS: 1
```

#### offline-api-orrery

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_api tests/test_orrery
```

```text
ssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss [ 60%]
ssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss [ 63%]
ssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss [ 65%]
ssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss [ 68%]
sssssssssssssssssssssssssss....................s........................ [ 70%]
sssssssssssssssssssssssssss..s.........sss...........ssss............... [ 73%]
.........sss.....ssssssssssssssssssssss......sssss..s................... [ 75%]
ssssssssssssssssssssssssssssssssssssss.................................. [ 78%]
........................................................................ [ 80%]
..ssssssss.............................................................. [ 83%]
.......................s.................sssss...s...................... [ 85%]
............................sssssssssssssssssssssssss................... [ 88%]
.....................................sssssssssssss.s......s............. [ 90%]
......s....ssssssssss.......ss...............ssss....................... [ 93%]
...............ss....sssssssssss........................................ [ 95%]
.......................................sssssssssss...................... [ 98%]
..sssssssssssssss.............sssss..........s.                          [100%]
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
E         '141'
E         '142'
E         Use -v to get more diff

tests/test_orrery/test_migrate.py:266: AssertionError
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1830 passed, 1024 skipped, 7 warnings in 31.84s
EXIT STATUS: 1
```

#### reachability

```sh
env -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit tests/test_reachability.py
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
......................................................                   [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
54 passed in 9.69s
EXIT STATUS: 0
```

#### black-final

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
EXIT STATUS: 0
```

#### flake-final

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

#### flake-main

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/agents/logon/apex_enums.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py:689:89: E501 line too long (91 > 88 characters)
EXIT STATUS: 1
```

#### mypy-branch

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/mypy-branch nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
EXIT STATUS: 0
```

#### mypy-main

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/mypy-main /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/origin-main/nexus/agents/logon/apex_enums.py
```

```text
Success: no issues found in 3 source files
EXIT STATUS: 0
```

#### comments

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
Found 1 schema documentation finding(s):
  migrations/143_drop_dead_schema_strata.sql:1092: EXECUTE 'f.definition' runs a command built at run time; its schema changes cannot be verified

New tables, columns, enums, functions, procedures, and views need a non-blank COMMENT ON in the same migration (docs/database.md).
EXIT STATUS: 1
```

#### commit-attempt

```sh
git commit --file /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/commit-message.txt
```

```text
Regenerate Orrery package catalog............................................Passed
Validate NEXUS config and model-ID drift.....................................Passed
Require COMMENT ON for new migration objects.................................Failed
- hook id: check-migration-comments
- exit code: 1

Found 1 schema documentation finding(s):
  migrations/143_drop_dead_schema_strata.sql:1092: EXECUTE 'f.definition' runs a command built at run time; its schema changes cannot be verified

New tables, columns, enums, functions, procedures, and views need a non-blank COMMENT ON in the same migration (docs/database.md).

Require dispositions for swallowing exception handlers.......................Passed
EXIT STATUS: 1
```

#### cleanup

```sh
/Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/cleanup.py
```

```text
admin identity: ('postgres', 'on')
remaining qa640_813_case clones: []
EXIT STATUS: 0
```


### Development Probes and Interrupted Runs (Not Gates)

The first smoke run found the unrelated %TYPE column had been classified as a
declaration; that was corrected, and the full 272-case proof passes it. Two
subsequent smoke collections caught malformed Python string wrapping, corrected
before the passing smoke/full proofs. The initial flake8 output found two added
long strings, corrected with unchanged AST. These tails and the interrupted
commands are retained below for completeness, never counted as passing gates.


#### smoke

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k 'accepts_live_relationship or accepts_surviving_catalog or recreation_refuses or (refuses_hidden and (sql-literal-unicode or sql-catalog-regclass-call or sql-catalog-regclass-computed-call))'
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 270 items / 262 deselected / 8 selected

tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-call] PASSED [ 12%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regclass-computed-call] PASSED [ 25%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode] PASSED [ 37%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode-escape] PASSED [ 50%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_live_relationship_column_names FAILED [ 62%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_surviving_catalog_casts PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[SELECT count(*) FROM public.items] PASSED [ 87%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[DECLARE v public.item_type; BEGIN RETURN; END] PASSED [100%]

=================================== FAILURES ===================================
__________ test_migration_143_accepts_live_relationship_column_names ___________

archives = {'NEXUS_template': PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scrat...4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/pytest-of-pythagor/pytest-2/813-archives0/save_03.dump'), ...}
tmp_path = PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/pytest-of-pythagor/pytest-2/test_migration_143_accepts_liv0')

    def test_migration_143_accepts_live_relationship_column_names(
        archives: dict[str, Path], tmp_path: Path
    ) -> None:
        """Keep varchar fields, diagnostic strings, and the real deriving trigger."""
        with _clone(archives, tmp_path) as dbname:
            _load_fixture(dbname)
            _column_consumers(dbname)
            before = _snapshot(dbname, surviving=True)
>           assert _apply(dbname)
E           AssertionError: assert False
E            +  where False = _apply('qa640_813_case_83488890a78d')

tests/test_orrery/test_migration_dead_strata_pg.py:935: AssertionError
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_percent() refuses: target public.emotional_valence: unsupported or unresolved body identifier character_relationships.emotional_valence
CONTEXT:  PL/pgSQL function inline_code_block line 627 at RAISE
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 9 targets: postgres, qa640_813_case_* x8
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_live_relationship_column_names
================= 1 failed, 7 passed, 262 deselected in 25.87s =================
EXIT STATUS: 1
```

#### smoke2

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k 'accepts_live_relationship or accepts_surviving_catalog or recreation_refuses'
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 0 items / 1 error

==================================== ERRORS ====================================
_____ ERROR collecting tests/test_orrery/test_migration_dead_strata_pg.py ______
../../../.venv/lib/python3.11/site-packages/_pytest/python.py:493: in importtestmodule
    mod = import_path(
../../../.venv/lib/python3.11/site-packages/_pytest/pathlib.py:587: in import_path
    importlib.import_module(module_name)
../../../../.pyenv/versions/3.11.12/lib/python3.11/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
<frozen importlib._bootstrap>:1204: in _gcd_import
    ???
<frozen importlib._bootstrap>:1176: in _find_and_load
    ???
<frozen importlib._bootstrap>:1147: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:690: in _load_unlocked
    ???
../../../.venv/lib/python3.11/site-packages/_pytest/assertion/rewrite.py:176: in exec_module
    source_stat, co = _rewrite_test(fn, self.config)
../../../.venv/lib/python3.11/site-packages/_pytest/assertion/rewrite.py:356: in _rewrite_test
    tree = ast.parse(source, filename=strfn)
../../../../.pyenv/versions/3.11.12/lib/python3.11/ast.py:50: in parse
    return compile(source, filename, mode, flags,
E     File "/Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata/tests/test_orrery/test_migration_dead_strata_pg.py", line 769
E       "COMMENT ON FUNCTION public.probe813_shadow() IS '813 effective search path'; "REVOKE ALL ON FUNCTION public.probe813_where() FROM PUBLIC; "
E                                                                                                                                                  ^
E   SyntaxError: unterminated string literal (detected at line 769)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
ERROR tests/test_orrery/test_migration_dead_strata_pg.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.13s ===============================
EXIT STATUS: 2
```

#### smoke3

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k 'accepts_live_relationship or accepts_surviving_catalog or recreation_refuses'
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 0 items / 1 error

==================================== ERRORS ====================================
_____ ERROR collecting tests/test_orrery/test_migration_dead_strata_pg.py ______
../../../.venv/lib/python3.11/site-packages/_pytest/python.py:493: in importtestmodule
    mod = import_path(
../../../.venv/lib/python3.11/site-packages/_pytest/pathlib.py:587: in import_path
    importlib.import_module(module_name)
../../../../.pyenv/versions/3.11.12/lib/python3.11/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
<frozen importlib._bootstrap>:1204: in _gcd_import
    ???
<frozen importlib._bootstrap>:1176: in _find_and_load
    ???
<frozen importlib._bootstrap>:1147: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:690: in _load_unlocked
    ???
../../../.venv/lib/python3.11/site-packages/_pytest/assertion/rewrite.py:176: in exec_module
    source_stat, co = _rewrite_test(fn, self.config)
../../../.venv/lib/python3.11/site-packages/_pytest/assertion/rewrite.py:356: in _rewrite_test
    tree = ast.parse(source, filename=strfn)
../../../../.pyenv/versions/3.11.12/lib/python3.11/ast.py:50: in parse
    return compile(source, filename, mode, flags,
E     File "/Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata/tests/test_orrery/test_migration_dead_strata_pg.py", line 771
E       "GRANT EXECUTE ON FUNCTION public.probe813_where() TO CURRENT_USER"",
E                                                                          ^
E   SyntaxError: unterminated string literal (detected at line 771)
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
ERROR tests/test_orrery/test_migration_dead_strata_pg.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.13s ===============================
EXIT STATUS: 2
```

#### smoke4

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit tests/test_orrery/test_migration_dead_strata_pg.py -k 'accepts_live_relationship or accepts_surviving_catalog or recreation_refuses'
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 270 items / 266 deselected / 4 selected

tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_live_relationship_column_names PASSED [ 25%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_surviving_catalog_casts PASSED [ 50%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[SELECT count(*) FROM public.items] PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_recreation_refuses_without_scanner[DECLARE v public.item_type; BEGIN RETURN; END] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 5 targets: postgres, qa640_813_case_* x4
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
====================== 4 passed, 266 deselected in 20.35s ======================
EXIT STATUS: 0
```

#### offline-core

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
```

```text
........................................................................ [  2%]
.........................................................s.............. [  4%]
........................sssssss...ssss.................................. [  6%]
........................................................................ [  8%]
........................................................................ [ 10%]
........................................................................ [ 13%]
................
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/selectors.py:415: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
436 passed, 14 skipped, 7 warnings in 175.24s (0:02:55)
EXIT STATUS: 2
```

#### offline-root

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util
```

```text
........s......................................sssssss...ssss........... [  3%]
........................................................................ [  6%]
.
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/pythagor/.pyenv/versions/3.11.12/lib/python3.11/threading.py:327: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
133 passed, 14 skipped, 7 warnings in 16.04s
EXIT STATUS: 2
```

#### flake-branch

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
tests/test_orrery/test_migration_dead_strata_pg.py:833:89: E501 line too long (97 > 88 characters)
tests/test_orrery/test_migration_dead_strata_pg.py:870:89: E501 line too long (92 > 88 characters)
EXIT STATUS: 1
```

#### black

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
EXIT STATUS: 0
```

### Final Handoff

The existing PR body was patched, not its branch/history. A fresh read verifies
that the body exactly matches the expected JSON payload, its original footer is
intact, and both local and PR HEAD remain fc7d298ecfd2b38f702a3139dff61ecf38ba973a.

```sh
gh api -X PATCH repos/pythagorakase/nexus/pulls/1098 --input /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r2/pr-patch.json --jq '{url:.html_url,head:.head.sha}'
```

```text
{"head":"fc7d298ecfd2b38f702a3139dff61ecf38ba973a","url":"https://github.com/pythagorakase/nexus/pull/1098"}
EXIT STATUS: 0
```

`git diff --cached --check` reports trailing whitespace only inside the captured
failure-tail blocks. It is retained because the order requires verbatim tails;
source Python/SQL has no whitespace finding. This optional whitespace check is
not being used to waive the mandatory migration-comment rejection.

The staged patch is backed up at after-review-r2/pending-r2.patch. No commit was
created, and no push was attempted after the failed commit hook. No command started by this fixer is
running. The code is ready for coordinator review, but the mandatory checker
contract must be resolved before this patch can become the PR head.

Authored by Codex, running GPT-6.

## Coordinator Resolution: Language Validators Replace Re-Creation

Date 2026-10-01. The stop-report's conflict is accepted as a rule conflict and
resolved by changing the mechanism, not the checker: `check_migration_comments.py`
is right to refuse run-time-built DDL it cannot inspect, and the ordered
`EXECUTE pg_get_functiondef(oid)` re-creation was such DDL. The second line of
defense now calls PostgreSQL's SQL-callable language validators,
`pg_catalog.fmgr_sql_validator(oid)` and `pg_catalog.plpgsql_validator(oid)`,
under `SET LOCAL check_function_bodies = on` and each routine's effective
`search_path`. These are the functions `CREATE FUNCTION` itself invokes: a SQL
body is parsed and analyzed against the live (post-drop) catalog, a PLpgSQL body
is compiled with its declared types resolved, and nothing is created, replaced
or altered, so OIDs, ownership, ACLs and comments are untouched by construction.
The validator dispatches on `pg_language.lanname` (PostgreSQL refuses a validator
called for the wrong language), and the routine selection now mirrors the
scanner's: every non-system schema, excluding extension members
(`pg_depend.deptype = 'e'`). The residual-risk statement in the header is
unchanged: PLpgSQL expression-level references are late-bound and no body check
covers them.

The test exercising the second line is renamed from
`test_migration_143_recreation_refuses_without_scanner` to
`test_migration_143_validation_refuses_without_scanner`; its assertions are
unchanged (the scanner invocation is removed from a scratch copy; the SQL target
query and the PLpgSQL target declaration must still refuse with `post-drop` and
`probe813` in the runner log; snapshots, routine catalog and stamps unchanged).
Earlier tails in this document carry the old name.

### Mechanism Probe (Disposable Database, Fresh Session)

A `qa640_coord_probe_*` database was created, given a table `t`, an enum `mood`,
an old-style SQL function reading `t`, a PLpgSQL function declaring a `mood`
variable, two late-bound PLpgSQL functions, and a clean SQL function; `t` and
`mood` were dropped (RESTRICT succeeds: string bodies record no dependency).
From a second session (no cached PLpgSQL compilation), the validators and the
previous CREATE OR REPLACE path gave identical verdicts:

```text
--- fresh session validators:
SET
ERROR:  relation "t" does not exist
LINE 1: SELECT count(*)::int FROM t
QUERY:  SELECT count(*)::int FROM t
ERROR:  type "mood" does not exist
LINE 1:  DECLARE m mood; BEGIN m := 'a'; END
 f_plpgsql_ref | (passes: late-bound table reference)
 f_plpgsql_cast | (passes: late-bound expression cast)
 f_ok | (passes)
--- same fresh-session check through CREATE OR REPLACE for comparison:
NOTICE:  f_sql REFUSED: relation "t" does not exist
NOTICE:  f_plpgsql_type REFUSED: type "mood" does not exist
NOTICE:  f_plpgsql_ref re-created ok
NOTICE:  f_plpgsql_cast re-created ok
NOTICE:  f_ok re-created ok
```

Same-session note: a validator run right after `CREATE FUNCTION` in the same
session reuses the cached PLpgSQL compilation and does not refuse; the migration
runs in its own session, where no such cache exists, and the test below proves
the refusal through the real runner.

### Migration-Comment Lint

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
LINT EXIT=0
```

### Second Line and Fleet Clones

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k "validation_refuses_without_scanner or drops_only_manifest_on_each_fleet_clone"
```

```text
..........                                                               [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 11 targets: postgres, qa640_813_case_* x10
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
10 passed, 262 deselected in 86.93s (0:01:26)
```

### Full Module, Runner and Schema-Documentation Suites

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_owner_target_guard.py
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 284 targets: postgres, qa640_813_case_* x272, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 461 passed in 616.26s (0:10:16)
```

The single failure is the allowed sequencing failure: `assert {'013', '119', '141', '142'} == frozenset({'013', '119'})`; migrations 141 and 142 land with batch B before this PR. All 272 dead-strata cases pass under the validator second line.


## After the Third Independent Review

### STOP-REPORT: Main Integration and Exception-Baseline Gate

Frozen parent remains `b1ec9488fc1ba9cf7fe997bb3f5634911a23ad61`.
All three accepted findings and the header change are implemented. No fix commit,
rebase or push has occurred. The mandatory main-comparison exception-disposition
lint fails; it is not bypassed. The latest observed shared `origin/main` is
`581aad0f301a65a0cee81b65222c6cbaa999a6f5` (initial fetch was
`8ccd3008a48bdf8115232667399868e2bdf66f93`). Other builders advanced the shared
remote-tracking ref during this run. Main now removed thirteen baseline entries
that this unreconciled branch still contains: four wizard entries and nine
MEMNON entries. The failed offline test is exactly
`tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline`.
Neither those source files nor the exception baseline was changed here. This is
not a fingerprint made stale by this order's lexer/validator changes. No baseline
entry, checker, test, exemption, historical migration, manifest or fixture was
weakened or changed to pass the check.

The user requires both keeping b1ec9488 without history rewrite/fix commits only
and rebasing onto newest main before push. The histories diverge. A rebase
replaces b1ec9488's branch-ancestry hash; preserving it requires an integration
merge. An asynchronous clarification of that conflict remains unanswered.
The stop-report escape hatch in the common rules applies; no rebase or merge
is invented as authority to discard the other explicit requirement. Mandatory
standalone lint against HEAD passes, but that does not waive the red comparison
against main. API/Orrery offline and reachability were not rerun after this stop;
no final integrated-head proof is claimed. The coordinator must resolve the
integration instruction, then integrate current main (including its baseline),
rerun the remaining gates and refreshed proof, commit and push. No merge here.

### Implementation and Preservation Evidence

- `--` comments now terminate at either CR or LF. An audit of every `\n` use in
  the migration found only the line-comment loop and continuation check; both
  now use `[\n\r]`.
- Literal continuation implements PostgreSQL's line-comment whitespace grammar,
  with a required CR/LF and further whitespace or newline-terminated line
  comments; block comments are excluded. The first segment's escape semantics
  continue to apply. Chained comments, CRLF, bare CR and E-string continuations
  are covered by executed real PLpgSQL routines.
- Every proconfig entry is split at its first `=`, saved with current_setting,
  applied transaction-locally with set_config, and restored after the language
  validator. Applying an obsolete SET target refuses with the routine named.
  The exception block rolls configuration changes back on refusal. No routine
  replacement DDL is introduced.
- The DateStyle test sets only its allocated clone database default to ISO, MDY,
  creates a healthy routine with ISO, DMY, a search path and an `a=b` custom GUC,
  then executes the real runner on a fresh connection. DateStyle, search_path
  and the custom maintenance GUC are compared on that SAME connection afterward.
  A later SQL routine requiring MDY proves no per-routine leak. Before/after
  catalog comparisons cover OIDs, definitions, owner, ACL, proconfig and comments.
- Four primary refusal cases execute before migration and return PostgreSQL's
  target OIDs: CR-hidden items/item_type and comment-continued items/item_type.
  Surviving public.ems and public.em_type prevent suffix lookup from refusing
  accidentally. All refusal snapshots preserve the entire catalog/data and stamps.
- A block-comment pass body uses `'public.it' /* ... */ || 'ems'` as text data
  under length(), returning 12. Its scanner tokens are two separate strings
  and an explicit concatenation operator, with no catalog cast or target use.
  The bare adjacent shape `SELECT 'public.it' /* ... */ 'ems'` raises PostgreSQL
  SyntaxError; it cannot be a healthy naked adjacent-literal PLpgSQL expression.
  This direct SQL assertion documents why block comments must not concatenate
  tokens. The valid body survives migration unchanged.
- All 26 new cases run both on the frozen pre-143 shape and after real retirement
  plus reconstruction. The module totals 298 passes in two bounded splits:
  169 direct/fixture/independent/new cases and 129 reconstruction cases. Six
  read-only fresh full-data source dumps rehearse through the real full runner,
  including preservation and repeat-run checks; every clone is qa640_813_case_*.
  Other ordered proof files retain their repository-owned disposable prefixes,
  as required by the common fixture rules. No driver reaches an owner database.
- Remaining ordered proof files: 189 passes and only the allowed sequence
  failure naming 141 and 142. The tested frozen branch lacks those files. Latest observed main now contains
  141_genesis_run_ledger.sql and 142_world_event_occurrence_time.sql, so the
  sequence failure must disappear after integration and refreshed proof. Offline root: 1933 passes; core directories: 906 passes and the
  exception-baseline failure described above. Offline skips are not PG proof.
- Black passes. Mypy --explicit-package-bases passes on four branch files and
  three git-show main copies; the module is new on main. Flake8's seventeen
  diagnostics match the initial fetched main copies exactly modulo prefixes
  and line shifts; none occurs in the new module or a changed/added line.
  Six added long strings were wrapped with asserted identical Python AST.
  One mypy narrowing diagnostic was fixed by an explicit non-None assertion;
  the subsequent static run is green. No untouched diagnostic was fixed.
- Migration-comment lint passes. Standalone exception lint against HEAD passes;
  main comparison fails, so there is no claim of a fully green head.
- Read-only admin identity is postgres with transaction_read_only=on, PostgreSQL
  17.11 (Postgres.app). No qa640_813_case_* database remains. No paid calls,
  service starts, owner/template writes, other worktree writes or stash occurred.
  Every test command completed before handoff.

### PostgreSQL Source Evidence and Transcription Difference

Sources directly inspected during this run:

1. [REL_17_STABLE scan.l](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/parser/scan.l#L189):
   lines 205-226 define space, newline, non_newline, line comment,
   special_whitespace, whitespace_with_newline and quotecontinue. Lines 547-566
   preserve the string state across continuation. Thus CR and LF terminate
   comments, line comments participate in continuation, block comments do not,
   and continuation retains the first segment's decoding mode. The live OID
   assertions and red destructive verdicts independently demonstrate these rules.
2. The order transcribes pre-newline horizontal whitespace as `[ \t\f]`.
   The linked actual REL_17_STABLE source instead uses non_newline_space
   `[ \t\f\v]`; current master agrees. The fix includes vertical tab in
   accordance with the order's governing rule that PostgreSQL's reading wins.
   A real vertical-tab continuation test returns the items OID before migration
   and refuses with catalogs unchanged afterward. The old migration applies
   destructively. This is a documented source correction, not a guard exception.
3. [REL_17_STABLE pg_proc.c](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/catalog/pg_proc.c#L635):
   lines 635-668 apply proconfig through ProcessGUCArray before the language
   validator and restore GUC state afterward with check_function_bodies on.
   Lines 795-810 and 855-905 show raw parsing but no analysis for polymorphic
   input types. Lines 169-180 require polymorphic input for polymorphic return types;
   the requested header states the limitation for argument or return types.
   Ordinary string SQL bodies are analyzed; the retained independent SQL query
   and PLpgSQL declaration probes still refuse when the scanner alone is removed.

The header residual-risk text is now:

```text
Residual risk: polymorphic SQL bodies (any polymorphic argument or return type)
receive only a syntax check from fmgr_sql_validator, shared by re-creation.
Other SQL bodies are parsed/analyzed; PLpgSQL syntax/declared types are validated.
Neither defense completely covers late-bound PLpgSQL expression-level references.
The SET-clause environment is applied as CREATE FUNCTION applies it.
```

### Exact Commands and Verbatim Tails

All commands run from the assigned worktree with the shared interpreter.
Import proof resolved nexus/__init__.py inside this worktree. Scratch files,
plugins, pytest temporaries and logs are under after-review-r3 only. The scratch
run.py records exact child argv, sets PYTHONPATH to this worktree plus that plugin
directory and TMPDIR to after-review-r3, with duration 540s and silence 120s
bounds. Commands were sequential except independent static checks. OLD_MIGRATION
plants use only the git-show b1ec9488 SQL copy via old_scanner.py; production SQL
was never temporarily reverted. The red-complete run proves eight destructive
lexer verdicts, the safe-continuation false refusal, DateStyle false refusal and
missed obsolete SET reference (11 failures); CR-survivor and block-separated text
already pass (2 passes). Earlier red-round3 includes a malformed block probe,
corrected to the valid explicit concatenation described above, never claimed
as a product failure. Early Black syntax/long-string and mypy diagnostics were
corrected before the recorded passing static gates.

#### red-round3

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/b1ec9488.sql /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p old_scanner -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k 'round3 and False'
```

```text
                cur.execute("SELECT set_config('probe813.note','maintenance',false)")
                conn.commit()
>               assert migrate.apply_migration(
                    conn, "143", "drop_dead_schema_strata", MIGRATION
                )
E               AssertionError: assert False
E                +  where False = <function apply_migration at 0x10ed3e0c0>(<connection object at 0x10f272f80; dsn: 'dbname=qa640_813_case_76cbafd58a61 host='' port=5432 user=pythagor connect_timeout=5 options='-c TimeZone=UTC' application_name=nexus:sync:11469', closed: 0>, '143', 'drop_dead_schema_strata', PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/b1ec9488.sql'))
E                +    where <function apply_migration at 0x10ed3e0c0> = migrate.apply_migration

tests/test_orrery/test_migration_dead_strata_pg.py:1262: AssertionError
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: post-drop function/procedure public.probe813_date() validation refuses: date/time field value out of range: "31/12/2026"
CONTEXT:  PL/pgSQL function inline_code_block line 23 at RAISE
___________ test_migration_143_round3_invalid_setting_refuses[False] ___________

archives = {'NEXUS_template': PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scrat...4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/pytest-of-pythagor/pytest-0/813-archives0/save_03.dump'), ...}
tmp_path = PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/pytest-of-pythagor/pytest-0/test_migration_143_round3_inva0')
caplog = <_pytest.logging.LogCaptureFixture object at 0x10f14e750>, post = False

    @pytest.mark.parametrize("post", (False, True))
    def test_migration_143_round3_invalid_setting_refuses(
        archives: dict[str, Path],
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        post: bool,
    ) -> None:
        """A vanished text-search SET target refuses with its routine named."""
        with _clone(archives, tmp_path) as dbname:
            _round3_prepare(dbname, post)
            _sql(
                dbname,
                "CREATE TEXT SEARCH CONFIGURATION public.probe813_config (COPY=pg_catalog.english); "
                "COMMENT ON TEXT SEARCH CONFIGURATION public.probe813_config IS '813 SET dependency'; "
                "CREATE FUNCTION public.probe813_setting() RETURNS integer LANGUAGE sql "
                "SET default_text_search_config='public.probe813_config' AS $$SELECT 1$$; "
                "COMMENT ON FUNCTION public.probe813_setting() IS '813 vanished SET target'; "
                "DROP TEXT SEARCH CONFIGURATION public.probe813_config RESTRICT",
            )
            before, functions, stamps = (
                _snapshot(dbname, surviving=False),
                _function_catalog(dbname),
                _stamps(dbname),
            )
            caplog.clear()
>           assert not _apply(dbname), caplog.text
E           AssertionError: 
E           assert not True
E            +  where True = _apply('qa640_813_case_04ce292b4da6')

tests/test_orrery/test_migration_dead_strata_pg.py:1300: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: postgres, qa640_813_case_* x9
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-item-type-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-item-type-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-survivor-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[block-separated-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_validator_settings[False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_invalid_setting_refuses[False]
================= 8 failed, 1 passed, 281 deselected in 26.76s =================
EXIT STATUS: 1
```

#### red-final

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/b1ec9488.sql /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p old_scanner -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k 'round3 and False'
```

```text
                assert settings[0] == "ISO, MDY"
                cur.execute("SELECT set_config('probe813.note','maintenance',false)")
                conn.commit()
>               assert migrate.apply_migration(
                    conn, "143", "drop_dead_schema_strata", MIGRATION
                )
E               AssertionError: assert False
E                +  where False = <function apply_migration at 0x109fc1f80>(<connection object at 0x109fc7610; dsn: 'dbname=qa640_813_case_a87eeb2675b4 host='' port=5432 user=pythagor connect_timeout=5 options='-c TimeZone=UTC' application_name=nexus:sync:11958', closed: 0>, '143', 'drop_dead_schema_strata', PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/b1ec9488.sql'))
E                +    where <function apply_migration at 0x109fc1f80> = migrate.apply_migration

tests/test_orrery/test_migration_dead_strata_pg.py:1264: AssertionError
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: post-drop function/procedure public.probe813_date() validation refuses: date/time field value out of range: "31/12/2026"
CONTEXT:  PL/pgSQL function inline_code_block line 23 at RAISE
___________ test_migration_143_round3_invalid_setting_refuses[False] ___________

archives = {'NEXUS_template': PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scrat...4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/pytest-of-pythagor/pytest-1/813-archives0/save_03.dump'), ...}
tmp_path = PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/pytest-of-pythagor/pytest-1/test_migration_143_round3_inva0')
caplog = <_pytest.logging.LogCaptureFixture object at 0x10a4cab50>, post = False

    @pytest.mark.parametrize("post", (False, True))
    def test_migration_143_round3_invalid_setting_refuses(
        archives: dict[str, Path],
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        post: bool,
    ) -> None:
        """A vanished text-search SET target refuses with its routine named."""
        with _clone(archives, tmp_path) as dbname:
            _round3_prepare(dbname, post)
            _sql(
                dbname,
                "CREATE TEXT SEARCH CONFIGURATION public.probe813_config (COPY=pg_catalog.english); "
                "COMMENT ON TEXT SEARCH CONFIGURATION public.probe813_config IS '813 SET dependency'; "
                "CREATE FUNCTION public.probe813_setting() RETURNS integer LANGUAGE sql "
                "SET default_text_search_config='public.probe813_config' AS $$SELECT 1$$; "
                "COMMENT ON FUNCTION public.probe813_setting() IS '813 vanished SET target'; "
                "DROP TEXT SEARCH CONFIGURATION public.probe813_config RESTRICT",
            )
            before, functions, stamps = (
                _snapshot(dbname, surviving=False),
                _function_catalog(dbname),
                _stamps(dbname),
            )
            caplog.clear()
>           assert not _apply(dbname), caplog.text
E           AssertionError: 
E           assert not True
E            +  where True = _apply('qa640_813_case_713eb64f89be')

tests/test_orrery/test_migration_dead_strata_pg.py:1302: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 10 targets: postgres, qa640_813_case_* x9
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-item-type-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-item-type-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-survivor-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_validator_settings[False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_invalid_setting_refuses[False]
================= 7 failed, 2 passed, 281 deselected in 29.17s =================
EXIT STATUS: 1
```

#### green-round3

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k round3
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 290 items / 272 deselected / 18 selected

tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-items-False] PASSED [  5%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-items-True] PASSED [ 11%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-item-type-False] PASSED [ 16%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-item-type-True] PASSED [ 22%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-items-False] PASSED [ 27%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-items-True] PASSED [ 33%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-item-type-False] PASSED [ 38%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-item-type-True] PASSED [ 44%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-survivor-False] PASSED [ 50%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-survivor-True] PASSED [ 55%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-survivor-False] PASSED [ 61%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-survivor-True] PASSED [ 66%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[block-separated-False] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[block-separated-True] PASSED [ 77%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_validator_settings[False] PASSED [ 83%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_validator_settings[True] PASSED [ 88%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_invalid_setting_refuses[False] PASSED [ 94%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_invalid_setting_refuses[True] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 19 targets: postgres, qa640_813_case_* x18
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
===================== 18 passed, 272 deselected in 51.18s ======================
EXIT STATUS: 0
```

#### red-complete

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/b1ec9488.sql /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p old_scanner -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k 'round3 and False'
```

```text
                    conn, "143", "drop_dead_schema_strata", MIGRATION
                )
E               AssertionError: assert False
E                +  where False = <function apply_migration at 0x10c719f80>(<connection object at 0x10c8c1a80; dsn: 'dbname=qa640_813_case_a0877dcfe74f host='' port=5432 user=pythagor connect_timeout=5 options='-c TimeZone=UTC' application_name=nexus:sync:14469', closed: 0>, '143', 'drop_dead_schema_strata', PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/b1ec9488.sql'))
E                +    where <function apply_migration at 0x10c719f80> = migrate.apply_migration

tests/test_orrery/test_migration_dead_strata_pg.py:1280: AssertionError
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: post-drop function/procedure public.probe813_date() validation refuses: date/time field value out of range: "31/12/2026"
CONTEXT:  PL/pgSQL function inline_code_block line 23 at RAISE
___________ test_migration_143_round3_invalid_setting_refuses[False] ___________

archives = {'NEXUS_template': PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scrat...4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/pytest-of-pythagor/pytest-3/813-archives0/save_03.dump'), ...}
tmp_path = PosixPath('/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/pytest-of-pythagor/pytest-3/test_migration_143_round3_inva0')
caplog = <_pytest.logging.LogCaptureFixture object at 0x10cd88ed0>, post = False

    @pytest.mark.parametrize("post", (False, True))
    def test_migration_143_round3_invalid_setting_refuses(
        archives: dict[str, Path],
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        post: bool,
    ) -> None:
        """A vanished text-search SET target refuses with its routine named."""
        with _clone(archives, tmp_path) as dbname:
            _round3_prepare(dbname, post)
            _sql(
                dbname,
                "CREATE TEXT SEARCH CONFIGURATION public.probe813_config (COPY=pg_catalog.english); "
                "COMMENT ON TEXT SEARCH CONFIGURATION public.probe813_config IS '813 SET dependency'; "
                "CREATE FUNCTION public.probe813_setting() RETURNS integer LANGUAGE sql "
                "SET default_text_search_config='public.probe813_config' AS $$SELECT 1$$; "
                "COMMENT ON FUNCTION public.probe813_setting() IS '813 vanished SET target'; "
                "DROP TEXT SEARCH CONFIGURATION public.probe813_config RESTRICT",
            )
            before, functions, stamps = (
                _snapshot(dbname, surviving=False),
                _function_catalog(dbname),
                _stamps(dbname),
            )
            caplog.clear()
>           assert not _apply(dbname), caplog.text
E           AssertionError: 
E           assert not True
E            +  where True = _apply('qa640_813_case_b3d6e08ff528')

tests/test_orrery/test_migration_dead_strata_pg.py:1318: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_813_case_* x13
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-cr-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-chain-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-vtab-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-escape-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-item-type-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-items-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-item-type-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-survivor-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_validator_settings[False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_invalid_setting_refuses[False]
================ 11 failed, 2 passed, 285 deselected in 33.29s =================
EXIT STATUS: 1
```

#### pg-direct

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k 'not regressions_work_from_post143_clone'
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-suffix] PASSED [ 66%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regrole-computed-lookup] PASSED [ 66%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-typed] PASSED [ 67%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-call] PASSED [ 68%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-call] PASSED [ 68%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-cast] PASSED [ 69%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-suffix] PASSED [ 69%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-catalog-regcollation-computed-lookup] PASSED [ 70%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-ordinary] PASSED [ 71%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-escaped] PASSED [ 71%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unicode-escape] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-national] PASSED [ 73%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-binary] PASSED [ 73%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-hex] PASSED [ 74%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-dollar] PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-tagged] PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-adjacent] PASSED [ 76%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_hidden_body_reference[sql-literal-unknown] PASSED [ 76%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_refuses_conflicting_lock_atomically PASSED [ 77%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_live_relationship_column_names PASSED [ 78%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_accepts_surviving_catalog_casts PASSED [ 78%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_preserves_deferred_function_consumers PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_new_story_transition_after_migration_143 PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_validation_refuses_without_scanner[SELECT count(*) FROM public.items-False] PASSED [ 80%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_validation_refuses_without_scanner[SELECT count(*) FROM public.items-True] PASSED [ 81%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_validation_refuses_without_scanner[DECLARE v public.item_type; BEGIN RETURN; END-False] PASSED [ 81%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_validation_refuses_without_scanner[DECLARE v public.item_type; BEGIN RETURN; END-True] PASSED [ 82%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_pre143_fixture_refuses_partial_or_drifted_clone[partial-pre] PASSED [ 82%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_pre143_fixture_refuses_partial_or_drifted_clone[drifted-pre] PASSED [ 83%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_pre143_fixture_refuses_partial_or_drifted_clone[partial-post] PASSED [ 84%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_pre143_fixture_refuses_partial_or_drifted_clone[drifted-post] PASSED [ 84%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-cr-items-False] PASSED [ 85%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-cr-items-True] PASSED [ 85%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-chain-items-False] PASSED [ 86%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-chain-items-True] PASSED [ 86%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-vtab-items-False] PASSED [ 87%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-vtab-items-True] PASSED [ 88%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-escape-items-False] PASSED [ 88%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-escape-items-True] PASSED [ 89%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-items-False] PASSED [ 89%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-items-True] PASSED [ 90%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-item-type-False] PASSED [ 91%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-item-type-True] PASSED [ 91%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-items-False] PASSED [ 92%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-items-True] PASSED [ 92%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-item-type-False] PASSED [ 93%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-item-type-True] PASSED [ 94%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-survivor-False] PASSED [ 94%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[cr-survivor-True] PASSED [ 95%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-survivor-False] PASSED [ 95%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[continued-survivor-True] PASSED [ 96%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[block-separated-False] PASSED [ 97%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_literal_grammar[block-separated-True] PASSED [ 97%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_validator_settings[False] PASSED [ 98%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_validator_settings[True] PASSED [ 98%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_invalid_setting_refuses[False] PASSED [ 99%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round3_invalid_setting_refuses[True] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 170 targets: postgres, qa640_813_case_* x169
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=============== 169 passed, 129 deselected in 345.39s (0:05:45) ================
EXIT STATUS: 0
```

#### pg-reconstruction

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k regressions_work_from_post143_clone
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-typed] PASSED [ 55%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-call] PASSED [ 56%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-computed-call] PASSED [ 57%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-computed-cast] PASSED [ 58%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-computed-suffix] PASSED [ 58%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoper-computed-lookup] PASSED [ 59%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-typed] PASSED [ 60%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-call] PASSED [ 61%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-computed-call] PASSED [ 62%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-computed-cast] PASSED [ 62%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-computed-suffix] PASSED [ 63%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regoperator-computed-lookup] PASSED [ 64%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-typed] PASSED [ 65%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-call] PASSED [ 65%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-computed-call] PASSED [ 66%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-computed-cast] PASSED [ 67%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-computed-suffix] PASSED [ 68%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regconfig-computed-lookup] PASSED [ 68%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-typed] PASSED [ 69%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-call] PASSED [ 70%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-computed-call] PASSED [ 71%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-computed-cast] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-computed-suffix] PASSED [ 72%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regdictionary-computed-lookup] PASSED [ 73%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-typed] PASSED [ 74%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-call] PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-computed-call] PASSED [ 75%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-computed-cast] PASSED [ 76%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-computed-suffix] PASSED [ 77%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regnamespace-computed-lookup] PASSED [ 78%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-typed] PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-call] PASSED [ 79%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-computed-call] PASSED [ 80%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-computed-cast] PASSED [ 81%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-computed-suffix] PASSED [ 82%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regrole-computed-lookup] PASSED [ 82%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-typed] PASSED [ 83%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-call] PASSED [ 84%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-computed-call] PASSED [ 85%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-computed-cast] PASSED [ 86%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-computed-suffix] PASSED [ 86%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-catalog-regcollation-computed-lookup] PASSED [ 87%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-ordinary] PASSED [ 88%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-escaped] PASSED [ 89%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-unicode] PASSED [ 89%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-unicode-escape] PASSED [ 90%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-national] PASSED [ 91%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-binary] PASSED [ 92%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-hex] PASSED [ 93%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-dollar] PASSED [ 93%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-tagged] PASSED [ 94%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-adjacent] PASSED [ 95%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[hidden:sql-literal-unknown] PASSED [ 96%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[lock] PASSED [ 96%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[relationship] PASSED [ 97%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[catalog] PASSED [ 98%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[deferred] PASSED [ 99%]
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[transition] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 130 targets: postgres, qa640_813_case_* x129
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=============== 129 passed, 169 deselected in 315.43s (0:05:15) ================
EXIT STATUS: 0
```

#### pg-ordered

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_owner_target_guard.py
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
..................F..................................................... [ 37%]
........................................................................ [ 75%]
..............................................                           [100%]
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
dbname audit: 12 targets: postgres, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 189 passed in 18.64s
EXIT STATUS: 1
```

#### comments

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
EXIT STATUS: 0
```

#### exceptions

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py
```

```text
OK: exception disposition coverage and shrink-only baseline verified.
EXIT STATUS: 0
```

#### black

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
EXIT STATUS: 0
```

#### flake-branch

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
tests/test_orrery/test_migration_dead_strata_pg.py:1121:89: E501 line too long (97 > 88 characters)
tests/test_orrery/test_migration_dead_strata_pg.py:1264:89: E501 line too long (94 > 88 characters)
tests/test_orrery/test_migration_dead_strata_pg.py:1269:89: E501 line too long (91 > 88 characters)
tests/test_orrery/test_migration_dead_strata_pg.py:1305:89: E501 line too long (97 > 88 characters)
tests/test_orrery/test_migration_dead_strata_pg.py:1306:89: E501 line too long (99 > 88 characters)
tests/test_orrery/test_migration_dead_strata_pg.py:1309:89: E501 line too long (90 > 88 characters)
EXIT STATUS: 1
```

#### flake-final

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

#### flake-main

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/agents/logon/apex_enums.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py:689:89: E501 line too long (91 > 88 characters)
EXIT STATUS: 1
```

#### mypy-branch

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/mypy-branch nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py:1233: error: Unsupported operand types for in ("str | None" and "str")  [operator]
Found 1 error in 1 file (checked 4 source files)
EXIT STATUS: 1
```

#### mypy-main

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/mypy-main /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/origin-main/nexus/agents/logon/apex_enums.py
```

```text
Success: no issues found in 3 source files
EXIT STATUS: 0
```

#### mypy-final

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/mypy-branch nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
EXIT STATUS: 0
```

#### offline-root

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util --ignore=tests/proofs
```

```text
........s......................................sssssss...ssss........... [  3%]
........................................................................ [  6%]
........................................................................ [  9%]
........................................................................ [ 12%]
................................................................s....... [ 15%]
..........................................................ssssssssss.... [ 18%]
...............s....s........................s......................ss.. [ 21%]
..............s..ss..................s.................................. [ 24%]
.................ssssssss........ssssssssssssssss.....s....s..........ss [ 27%]
..ssssssssssssssssssssssssssssssss..........ssssssssssssssssssssssssss.. [ 30%]
....s....ss.............................s........ss.............ssssssss [ 33%]
ssssssss............................................................ss.. [ 36%]
.............sss....................................................ssss [ 39%]
ss.................ss................................................... [ 43%]
........................................................................ [ 46%]
........ss..ss................................ssssssssssss.............. [ 49%]
............................................ssssssssssssssssssssssssssss [ 52%]
ssssssssssssssssssssss.................................................. [ 55%]
..............................sssssssssssssssss......................... [ 58%]
................................s.ssssss................................ [ 61%]
........................................................................ [ 64%]
....s.....ssssssssssssssssss........s...ss.....................s........ [ 67%]
..................sssssssssssssssssssssss......................sss...... [ 70%]
.............s..................................................ssssss.. [ 73%]
......................................................ssssssssssssssss.s [ 76%]
s...........................sssss....................................... [ 79%]
...................ssssssssssssssssssssssssssssssssss................... [ 83%]
........................................................................ [ 86%]
.................ss..................................................... [ 89%]
......................................s..s.............................s [ 92%]
sss.................sssss...................................sssss....... [ 95%]
............sss.................ssss.................................... [ 98%]
..........sssssssssssssssssssssssssss                                    [100%]
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

tests/test_memnon_cross_encoder_artifact.py::test_qwen3_loads_its_local_folder_and_scores
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/tokenization_utils_base.py:2718: UserWarning: `max_length` is ignored when `padding`=`True` and there is no truncation strategy. To pad to max length, use `padding='max_length'`.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1933 passed, 410 skipped, 8 warnings in 370.16s (0:06:10)
EXIT STATUS: 0
```

#### offline-directories

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util tests/config tests/proofs
```

```text
E         Left contains 13 more items, first extra item: 'nexus/agents/memnon/utils/content_processor.py:436: baseline growth forbidden: nexus/agents/memnon/utils/content_processor.py|ContentProcessor._generate_chunk_embeddings|31f7919238de69c3543c28a5f4d3cd41891ee39576b41f1c7a3995ef3f15bd7c|1'
E         Use -v to get more diff

tests/test_scripts/test_check_exception_dispositions.py:636: AssertionError
----------------------------- Captured stderr call -----------------------------
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
To disable this warning, you can either:
	- Avoid using `tokenizers` before the fork if possible
	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
=============================== warnings summary ===============================
<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.

<frozen abc>:106
<frozen abc>:106
  <frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.

../../../.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201
  /Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
    _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline
1 failed, 906 passed, 70 skipped, 7 warnings in 80.88s (0:01:20)
EXIT STATUS: 1
```

#### exceptions-main

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

```text
nexus/agents/memnon/utils/content_processor.py:436: baseline growth forbidden: nexus/agents/memnon/utils/content_processor.py|ContentProcessor._generate_chunk_embeddings|31f7919238de69c3543c28a5f4d3cd41891ee39576b41f1c7a3995ef3f15bd7c|1
nexus/agents/memnon/utils/db_access.py:200: baseline growth forbidden: nexus/agents/memnon/utils/db_access.py|check_vector_extension|f40e90a1a69e734e892bdb1e18105828c1ad1daab08ee68d12708d68ea1c690d|1
nexus/agents/memnon/utils/db_access.py:467: baseline growth forbidden: nexus/agents/memnon/utils/db_access.py|setup_database_indexes|6b53a987b88e0246e5a5eacc97fb056ca97ee8a11515646ad1739d8aff80b97e|1
nexus/agents/memnon/utils/db_access.py:493: baseline growth forbidden: nexus/agents/memnon/utils/db_access.py|setup_database_indexes|189003dbed1940b3d1b2a58593ac3723f8b855f86e2b765e74cf551e5438aabd|1
nexus/agents/memnon/utils/db_access.py:540: baseline growth forbidden: nexus/agents/memnon/utils/db_access.py|setup_database_indexes|2bb427024de559e1ae86584eb5f578ae011aea3698e4dba7be021cd51681568e|1
nexus/agents/memnon/utils/db_access.py:559: baseline growth forbidden: nexus/agents/memnon/utils/db_access.py|setup_database_indexes|8eeb5b357c45b106dbc295a5b7f93670b0ca7b9a76dd750a09c920efd37721ee|1
nexus/agents/memnon/utils/db_access.py:566: baseline growth forbidden: nexus/agents/memnon/utils/db_access.py|setup_database_indexes|e332f0cb4568ce6249f95968cd12acac6068e9b6f1f82925832df010bdb6d61b|1
nexus/agents/memnon/utils/db_access.py:576: baseline growth forbidden: nexus/agents/memnon/utils/db_access.py|setup_database_indexes|5335445c524ecdc3e2087e1cbfb22bfbd2ade6020fd38bcf7cfa082bf0863247|1
nexus/agents/memnon/utils/db_schema.py:183: baseline growth forbidden: nexus/agents/memnon/utils/db_schema.py|DatabaseManager._setup_hybrid_search|315aba118220cefb097d0462c142438cae259783338e5cccfe6dee34203d9c77|1
nexus/api/wizard_chat.py:1168: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.wizard_events|2e26b6145d23378bbe531f8663edbfc55460043d18da997bc263bca43ef00e4b|1
nexus/api/wizard_chat.py:1210: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_stream_endpoint.wizard_events|326cd8cce1c1e55ab05eb3c7bc20df030ab107da8b427799b8070ce405d49952|1
nexus/api/wizard_chat.py:772: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_endpoint|fb0fba2b5d218b71a960a846f0e49c24022812e642d4b532e743048bb69734d8|1
nexus/api/wizard_chat.py:815: baseline growth forbidden: nexus/api/wizard_chat.py|new_story_chat_endpoint|730a0ad62f7e700aedc6d1c8b16ab2f8cab571a9ca7336c33066c121bbe32550|1
EXIT STATUS: 1
```

#### cleanup

```sh
/Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r3/cleanup.py
```

```text
admin identity: ('postgres', 'on', 'PostgreSQL 17.11 (Postgres.app) on aarch64-apple-darwin23.6.0, compiled by Apple clang version 15.0.0 (clang-1500.3.9.4), 64-bit')
remaining qa640_813_case clones: []
EXIT STATUS: 0
```

### Open Coordinator Questions and Landing Notes

Resolve the conflicting requirements: may an ordinary rebase replace the hashes
of prior commits (preserving all their changes), or must b1ec9488 remain an ancestor
with main integrated by a merge? The latest main baseline must win without any
lint bypass. The thirteen-entry divergence now exceeds the original four-entry
wizard difference. All previous landing notes remain: integrate 141/142 before
143, fresh full-data pre-143 rehearsal, coordinator-only fleet application,
gateway restart by name, fresh post-143 regression proof and final whole-tree
PostgreSQL gate. Six vector helpers remain deferred to #812. No new owner ruling.

Authored by Codex, running GPT-6.

### Final Stop Handoff

The PR body was updated through gh api -X PATCH with the ordered JSON input.
A fresh GET confirms exact equality with the payload, the original footer byte
for byte, and local/PR HEAD b1ec9488fc1ba9cf7fe997bb3f5634911a23ad61. All three
files are staged, with the staged patch backed up in after-review-r3. No fix
commit or push was attempted after the main-comparison exception lint failed.
No command started by this fixer remains running. The implementation is
reviewable locally; main integration and final gates remain outstanding.

Authored by Codex, running GPT-6.


## After the Fourth Independent Review

Fix order `1098-astra-fix-r4.md`, frozen parent `5483d9965f98e508d33ffc3f5de0d86cb6dc9ed5`.
Integrated newest observed main `160134540517f6b74aacd1d1e1f3f584454eef86` by merge `66520398d4eab9efde85452429658f23e0e674fc` before proof.
The frozen head remains an ancestor. No rebase, history rewrite, stash, lint
bypass, fleet write, paid call, service start or other-worktree edit occurred.
Main's generated baselines were adopted by the merge; no round-four baseline
entry was added, removed or exempted. The prior stop-report requirements are
resolved by the current explicit merge authorization and main integration.

### Ordered Changes and Real-Runner Evidence

- The raw routine source is checked before tokenization. Case-insensitive `U&'`,
  `U&"` and `UESCAPE` anywhere, including comments and data strings, refuse with
  `unicode-escape literal or identifier; edit the routine`, wrapped with the
  qualified routine identity. All Unicode-specific lexer branches are removed.
  Ordinary/E/B/X/N/dollar/tagged literals and CR/LF/comment continuation retain
  their existing behavior. Unicode escapes inside an E-string remain supported.
- Each validator runs in its own BEGIN/EXCEPTION subtransaction. All proconfig
  entries are applied locally, the language validator runs, then fixed SQLSTATE
  D1430/message `dead143 validation complete` forces native abort/unwind. Only
  that sentinel is accepted as success; all other errors refuse with the routine
  named. Manual JSON restoration is removed. No routine DDL executes.
- One commented, transaction-local `pg_temp.dead143_setting(text)` helper splits
  name before the first equals sign and preserves the entire remaining value.
  Both scanner search_path and validator settings use it; it is dropped before
  stamping, alongside the other temporary helpers.
- Sixteen new real-routine cases run on qa640_813_case_* clones, both on the
  frozen pre-143 shape and after actual retirement plus reconstruction. The two
  comment-separated Unicode shapes execute before migration and return items'
  actual OID. A surviving public.z prevents suffix resolution from accidentally
  rejecting the old scanner. Unicode text solely in a comment/string and a
  Unicode identifier also refuse by the new deliberate raw-text rule. An E-string
  with \u007a resolves public.z before and after migration and passes unchanged.
- The healthy SQL function with SET log_min_messages=notice followed by SET
  session_authorization to a newly allocated NOLOGIN/NOSUPERUSER probe role
  creates and executes successfully with default public EXECUTE, then migrates.
  On the SAME maintenance connection, session_authorization, role,
  log_min_messages, search_path and the full pg_settings inventory equal the
  original values afterward. Routine OID/definition/owner/ACL/proconfig/comment
  and surviving schema/data are unchanged. Every temporary role is dropped in
  finally before its clone is dropped. The schema a=b/search_path case also
  creates, executes and migrates unchanged, with all session settings restored.
- Existing vanished-text-search-config SET tests still refuse naming the routine
  and target. Catalog/data/comment/stamp snapshots remain unchanged on refusal.
  Prior CR/continuation/DateStyle tests and independent validator tests all pass.
- OLD_MIGRATION is a byte-identical git-show copy of frozen 5483d996, selected
  solely by the scratch old_scanner.py plugin; production SQL was never reverted.
  The final red run has seven failures/one pass: four Unicode literal/comment/data
  cases apply destructively with targets (None, None); the Unicode identifier
  already refuses but lacks the new required message; both healthy SET cases
  falsely refuse. E-string Unicode already passes. No prior assertion was weakened.
- Complete ordered PostgreSQL proof: 185 direct/fleet/fixture cases + 129 complete
  post-143 reconstruction cases + 190 runner/documentation/owner-guard cases =
  504 passed, zero failures/skips. All six fresh read-only full-data dumps pass
  the full-runner rehearsal/preservation/repeat-run checks. Other named proof
  files retain their repository-owned disposable fixture prefixes per the common
  rules. Migrations 141/142 are present; the sequence test now passes.
- All offline splits pass: 1972 root, 958 other-directory, 1865 API/Orrery passes;
  skips are offline gates only, not PostgreSQL proof. Reachability: 54 passes.
  Black and explicit-package-bases mypy pass; flake8 has exactly the same 17
  untouched diagnostics as main (normalized path/message multisets compared).
  Migration-comment and main-comparison exception-disposition lints both pass.
- Read-only postgres admin check confirms PostgreSQL 17.11, zero remaining
  qa640_813_case_* databases and zero probe roles. No driver opened an owner DB.
  Test-provider-only and secret-store guards stayed active in every pytest run;
  every audited pytest summary reports owner targets: none. Paid usage: zero.

### PostgreSQL Grammar and Backend Evidence

Primary source bytes downloaded directly from the immutable REL_17_11 tag,
matching the live server, are preserved under after-review-r4/postgres-17.11-source.
Line numbers below refer to those exact files (web extraction line numbering
can differ). SHA256 fingerprints follow, allowing exact reproduction.

1. [parser.c](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/parser/parser.c#L253),
   base_yylex lines 253-313, consumes UIDENT/USCONST, UESCAPE and its SCONST
   argument at token level; its preceding comment at lines 91-107 explains the
   comment-separated lookahead. The scanner's whitespace-only suffix was not
   this grammar. Both real routines return the items OID before migration;
   the frozen scanner destructively applies, whereas the fixed guard refuses.
2. [scan.l](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/parser/scan.l#L223),
   lines 223-244 define newline/comment/quote continuation; lines 280-281 and
   656-713 define E-string Unicode escapes. This round retains that existing
   lexer grammar; the E-string pass test verifies PostgreSQL decodes \u007a
   into the surviving relation name.
3. [pg_proc.c](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/catalog/pg_proc.c#L677),
   lines 677-712 apply proconfig with ProcessGUCArray/GUC_ACTION_SAVE before
   the language validator, then call AtEOXact_GUC to unwind its GUC nesting level.
4. [guc.c](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/utils/misc/guc.c#L6370),
   ParseLongOption lines 6370-6398 uses the first '=' and copies the complete
   remainder. TransformGUCArray/ProcessGUCArray lines 6406-6488 use that split.
   The helper shares this delimiter/value behavior; canonical proconfig names
   are used as stored (ParseLongOption additionally normalizes '-' in names).
5. [guc_funcs.c](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/utils/misc/guc_funcs.c#L332),
   lines 332-374 show set_config checks current superuser status and uses LOCAL
   for its true third argument. A manual re-assignment after dropping privilege
   can therefore fail; the red log specifically names log_min_messages permission.
6. [xact.c](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/access/transam/xact.c#L5301)
   calls AtEOXact_GUC(false, s->gucNestLevel) in AbortSubTransaction.
   [guc.c](https://github.com/postgres/postgres/blob/REL_17_11/src/backend/utils/misc/guc.c#L2264),
   lines 2264-2308 and 2376-2510, restores stacked prior values/assign hooks on
   abort, without fresh set_config permission checks. This is the native unwind
   the sentinel invokes. The order's AtEOSubXact_GUC name is a transcription
   difference: PostgreSQL 17.11 calls the shared AtEOXact_GUC routine instead.

The header states LOCAL versus SAVE explicitly. Native restoration follows the
same backend stack machinery; this is not a claim that every SET acceptance
rule is identical. GUC_NO_RESET rejects SAVE specifically (guc.c:3656-3674), as
noted in the fourth review. The order explicitly prescribes set_config(...,true);
no extra unrequested GUC inventory/refusal policy was introduced in this round.
Polymorphic SQL remains syntax-only and PLpgSQL expression-level references
remain late-bound, as already documented.

- `access/transam/xact.c`: `0b5feef266271e810f6a716169761ad2fc28e27d1b319c721e6a933f1cfd5649`
- `catalog/pg_proc.c`: `f139301977df98e235e821311a3a4967cbbb87cb608972e1fcecd445822441b8`
- `parser/parser.c`: `210a5341eb2b71300732125b05f58bee100ad782f52c147fcc5e9509676cd5ad`
- `parser/scan.l`: `11729c526c464dab20e0b6a500cfc432243c8fab04e5c2afa45ea5101c924f39`
- `utils/misc/guc.c`: `c1a70e1fd8bc5b52c284f23c2e324d23a202d0212abea13f76ac31f5cbf8ce34`
- `utils/misc/guc_funcs.c`: `27d7e32592ddf4ac6b6a278b07d3288ab0bd6d352138cba57525177592ebab90`

### Commands and Verbatim Tails

Every command runs from the assigned worktree with the shared interpreter.
The import proof prints this worktree's nexus/__init__.py. Scratch run.py sets
PYTHONPATH to this worktree plus after-review-r4, TMPDIR to after-review-r4,
and bounds each child to 540 seconds/120 seconds of silence. Long suites run
sequentially and finish before the next command; independent static commands
run together. Each command/tail below is copied from its recorded JSON. Final
string wraps have identical Python ASTs; no executable test changed after proof.

#### red-round4-final

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/old143.sql /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k 'round4 and not True'
```

```text
E                    +    where <function apply_migration at 0x10e3a3ec0> = migrate.apply_migration

tests/test_orrery/test_migration_dead_strata_pg.py:1462: AssertionError
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_scope() refuses: invalid value for parameter "search_path": ""a"
CONTEXT:  PL/pgSQL function inline_code_block line 627 at RAISE
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 9 targets: postgres, qa640_813_case_* x8
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-gap-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-argument-gap-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-comment-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-string-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-identifier-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[session-authorization-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[search-path-False]
7 failed, 1 passed, 306 deselected in 25.51s
EXIT STATUS: 1
```

#### green-round4-complete

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k 'round4 or round3_invalid_setting'
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[search-path-True] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 19 targets: postgres, qa640_813_case_* x18
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
===================== 18 passed, 296 deselected in 49.51s ======================
EXIT STATUS: 0
```

#### pg-direct

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k 'not regressions_work_from_post143_clone'
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[search-path-True] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 186 targets: postgres, qa640_813_case_* x185
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=============== 185 passed, 129 deselected in 371.31s (0:06:11) ================
EXIT STATUS: 0
```

#### pg-reconstruction

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k regressions_work_from_post143_clone
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_regressions_work_from_post143_clone[transition] PASSED [100%]

secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 130 targets: postgres, qa640_813_case_* x129
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=============== 129 passed, 185 deselected in 313.73s (0:05:13) ================
EXIT STATUS: 0
```

#### pg-ordered

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py tests/test_owner_target_guard.py
```

```text
........................................................................ [ 75%]
..............................................                           [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 12 targets: postgres, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
190 passed in 18.65s
EXIT STATUS: 0
```

#### offline-root

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery --ignore=tests/config --ignore=tests/test_config --ignore=tests/test_ir_eval_v2 --ignore=tests/test_lore --ignore=tests/test_memnon --ignore=tests/test_runtime --ignore=tests/test_scripts --ignore=tests/test_util --ignore=tests/proofs
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1972 passed, 478 skipped, 8 warnings in 361.83s (0:06:01)
EXIT STATUS: 0
```

#### offline-directories

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_config tests/test_ir_eval_v2 tests/test_lore tests/test_memnon tests/test_runtime tests/test_scripts tests/test_util tests/config tests/proofs
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
958 passed, 81 skipped, 7 warnings in 126.25s (0:02:06)
EXIT STATUS: 0
```

#### offline-api-orrery

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_api tests/test_orrery
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1865 passed, 1135 skipped, 7 warnings in 43.44s
EXIT STATUS: 0
```

#### reachability

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_reachability.py
```

```text
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
......................................................                   [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 0 targets: none
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
54 passed in 10.21s
EXIT STATUS: 0
```

#### black-gate

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
All done! ✨ 🍰 ✨
4 files would be left unchanged.
EXIT STATUS: 0
```

#### flake-gate

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

#### flake-main

```sh
/Users/pythagor/nexus/.venv/bin/python -m flake8 /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/agents/logon/apex_enums.py
```

```text
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/agents/logon/apex_schema.py:305:89: E501 line too long (92 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.List' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:12:1: F401 'typing.Tuple' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.datetime' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:13:1: F401 'datetime.timezone' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:15:1: F401 'nexus.api.new_story_schemas.SpecificLocation' imported but unused
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:107:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:211:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:265:89: E501 line too long (94 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:315:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:318:89: E501 line too long (102 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:545:89: E501 line too long (118 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:552:89: E501 line too long (100 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:562:89: E501 line too long (93 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:563:89: E501 line too long (90 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:566:89: E501 line too long (91 > 88 characters)
/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py:689:89: E501 line too long (91 > 88 characters)
EXIT STATUS: 1
```

#### mypy-gate

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/mypy-branch nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
EXIT STATUS: 0
```

#### mypy-main

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/mypy-main /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/api/new_story_db_mapper.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/agents/logon/apex_schema.py /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/origin-main/nexus/agents/logon/apex_enums.py
```

```text
Success: no issues found in 3 source files
EXIT STATUS: 0
```

#### comments-final

```sh
/Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text
OK: every object created after migration 129 has a comment.
EXIT STATUS: 0
```

#### exceptions-final

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

```text
OK: exception disposition coverage and shrink-only baseline verified.
EXIT STATUS: 0
```

#### cleanup

```sh
/Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/cleanup.py
```

```text
admin identity: ('postgres', 'on', 'PostgreSQL 17.11 (Postgres.app) on aarch64-apple-darwin23.6.0, compiled by Apple clang version 15.0.0 (clang-1500.3.9.4), 64-bit')
remaining qa640_813_case clones: []
remaining qa640_813_case roles: []
EXIT STATUS: 0
```

### Before-Fix Destructive and False-Refusal Excerpts

```text
OLD DESTRUCTIVE VERDICT: unicode-gap applied; targets: (None, None)
OLD DESTRUCTIVE VERDICT: unicode-argument-gap applied; targets: (None, None)
OLD DESTRUCTIVE VERDICT: unicode-comment applied; targets: (None, None)
OLD DESTRUCTIVE VERDICT: unicode-string applied; targets: (None, None)
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_unicode() refuses: unsupported Unicode-escape quoted identifier
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: post-drop function/procedure public.probe813_scope() validation refuses: permission denied to set parameter "log_min_messages"
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_scope() refuses: invalid value for parameter "search_path": ""a"
```

### Development Diagnostics Corrected

The first two green-focused attempts migrate the healthy routines successfully
but the full pg_settings list gains twelve pgvector GUCs, then five PLpgSQL GUCs
from lazy library loading. The final harness explicitly loads both libraries
before taking its settings inventory; equality now passes without filtering any
setting. The first cleanup attempt passed an unsupported options keyword to
connect and never connected; it was corrected to SET TRANSACTION READ ONLY.
Three added long strings and quoting normalization were fixed, with AST equality
asserted; intermediate static failures are not final passing gates. Raw logs and
all earlier records remain under the ordered scratch directory.

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/old143.sql /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k 'round4 and not True'
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 9 targets: postgres, qa640_813_case_* x8
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-gap-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-argument-gap-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-comment-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-string-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_unicode_forms[unicode-identifier-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[session-authorization-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[search-path-False]
7 failed, 1 passed, 306 deselected in 25.87s
EXIT STATUS: 1
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k 'round4 or round3_invalid_setting'
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 19 targets: postgres, qa640_813_case_* x18
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[session-authorization-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[session-authorization-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[search-path-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[search-path-True]
================ 4 failed, 14 passed, 296 deselected in 50.04s =================
EXIT STATUS: 1
```

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -v -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k 'round4 or round3_invalid_setting'
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 19 targets: postgres, qa640_813_case_* x18
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[session-authorization-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[session-authorization-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[search-path-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round4_validator_scope[search-path-True]
================ 4 failed, 14 passed, 296 deselected in 48.84s =================
EXIT STATUS: 1
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
tests/test_orrery/test_migration_dead_strata_pg.py:1336:89: E501 line too long (93 > 88 characters)
tests/test_orrery/test_migration_dead_strata_pg.py:1433:89: E501 line too long (89 > 88 characters)
tests/test_orrery/test_migration_dead_strata_pg.py:1446:89: E501 line too long (94 > 88 characters)
EXIT STATUS: 1
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/mypy-branch nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
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
tests/test_orrery/test_migration_dead_strata_pg.py:1435:89: E501 line too long (89 > 88 characters)
EXIT STATUS: 1
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/mypy-branch nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
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
tests/test_orrery/test_migration_dead_strata_pg.py:1436:89: E501 line too long (89 > 88 characters)
EXIT STATUS: 1
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m mypy --explicit-package-bases --cache-dir /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/mypy-branch nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
Success: no issues found in 4 source files
EXIT STATUS: 0
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check nexus/api/new_story_db_mapper.py nexus/agents/logon/apex_schema.py nexus/agents/logon/apex_enums.py tests/test_orrery/test_migration_dead_strata_pg.py
```

```text
would reformat tests/test_orrery/test_migration_dead_strata_pg.py

Oh no! 💥 💔 💥
1 file would be reformatted, 3 files would be left unchanged.
EXIT STATUS: 1
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
/Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/cleanup.py
```

```text
Traceback (most recent call last):
  File "/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/813-S1/after-review-r4/cleanup.py", line 3, in <module>
    with closing(connect("postgres", options="-c default_transaction_read_only=on")) as conn, conn.cursor() as cur:
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: connect() got an unexpected keyword argument 'options'
EXIT STATUS: 1
```

### Open Coordinator Question and Landing Notes

Do you want a separate ordered policy for the remaining LOCAL/SAVE acceptance
mismatch on GUC_NO_RESET settings? It was noted in review but this order explicitly
requires LOCAL calls and native subtransaction unwind; the header now names the
boundary rather than claiming full equivalence. No requested fix is deferred.

All landing notes remain: preceding 141/142 are integrated; fresh raw full-data
pre-143 rehearsal without reconstruction or stamp removal; coordinator-only fleet
application including template and locked slot 1; gateway restart by name; fresh
post-143 regression proof; final whole-tree PostgreSQL gate. Six vector helpers
remain deferred to #812, and no owner ruling is added or reopened. Do not merge.

Authored by Codex, running GPT-6.

## After the Fifth Independent Review (Coordinator Fix)

Date 2026-10-01. The fifth pass (Astra, frozen at `e04d966d`) found one P2 and
nothing else: a routine declared with `SET check_function_bodies = off` carries
that setting in `proconfig`; applying it inside the validation subtransaction
overrides the transaction-level `on`, and both language validators honor the
switch, so the second line would record success without checking the body.
`CREATE FUNCTION` behaves the same way; this guard is now stricter: after a
routine's own SET clauses are applied and before its validator runs,
`check_function_bodies` is re-asserted `on` (`set_config(..., true)`, inside the
same subtransaction, so the native unwind restores it with everything else).
The header states this as the one place the guard is stricter than
`CREATE FUNCTION`.

Regression `test_migration_143_round5_routine_cannot_disable_validation`
(`case` × `post`): a SQL routine created under `check_function_bodies = off`
with `SET check_function_bodies = off` and either a broken body
(`SELECT missing_column FROM public.characters`) or `SELECT 1`. The broken body
refuses naming the routine with `post-drop` and `missing_column` in the runner
log, stamps and catalogs unchanged; the healthy body applies with the routine,
its `proconfig` and comment preserved and the maintenance session's
`check_function_bodies` still `on` afterwards.

### Red Against the Previous Migration (`e04d966d`)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=$S/old143.sql PYTHONPATH=$PWD:$S /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k "round5"
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round5_routine_cannot_disable_validation[broken-body-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round5_routine_cannot_disable_validation[broken-body-True]
2 failed, 2 passed, 314 deselected in 21.49s
```

(`$S` is this order's `after-review-r5` scratch directory holding `old143.sql`
from `git show e04d966d:migrations/143_drop_dead_schema_strata.sql` and the
round-4 `old_scanner` swap plugin.)

### Green With the Fix

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k "round5 or round4_validator_scope or drops_only_manifest_on_each_fleet_clone"
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
14 passed, 304 deselected in 95.14s (0:01:35)
```

`scripts/check_migration_comments.py`: OK. Black and flake8 on the test module:
clean. The full module and the whole-tree gate run at the final head below.

## After the Sixth Independent Review (Coordinator Fix)

Date 2026-10-01. The sixth pass (Astra, frozen at `23bf8aa9`) found one P2:
the `check_function_bodies` re-assertion is an unqualified `set_config` call,
so a routine whose declared path names `pg_catalog` after another schema
(`SET search_path = public, pg_catalog`) resolves that call through a
surviving `public.set_config(text,text,boolean)` instead of the builtin. The
finding generalizes: every unqualified builtin function or operator the
scanner's `pg_temp` helpers call while a routine's effective path is in force,
and every unqualified builtin the migration itself calls under the maintenance
session's path, resolves the same way. The fix is one rule at three points,
not a qualification of the lexer:

- `pg_temp.dead143_path_first()` returns the first non-temporary schema of
  `pg_catalog.current_schemas(true)` (the effective order, implicit
  `pg_catalog` included; no path string is parsed). Every call inside it is
  schema-qualified, including the operator, because it runs under the path it
  judges.
- Session: a `DO` block immediately after `SET LOCAL lock_timeout` refuses the
  migration when that schema is not `pg_catalog`, naming the path
  (`...; migration refused`).
- Scanner: after a routine's effective path is applied and before anything
  else resolves under it (the `dead143_body` arguments included), the same
  test refuses the routine (`...; unresolved context`).
- Validator: every `proconfig` entry is parsed under the session path first,
  then applied with `pg_catalog.set_config`; the same test refuses the routine
  before `check_function_bodies` is re-asserted.
- The migration's own GUC calls (`current_setting`, `set_config`, `unnest`,
  `array_append`, `array_length`) are `pg_catalog.`-qualified.

Sol drafted the regression (`test_migration_143_round6_search_path`, seven
cases × `post`) before its run was aborted by the provider's content
classifier; the coordinator completed the migration change. Cases: a surviving
`public.set_config(text,text,boolean)` whose body is
`SELECT pg_catalog.set_config('check_function_bodies','off',true)`, plus a
routine with `SET search_path = public, pg_catalog` and either the round-5
broken body or `SELECT 1` (both refuse on the path, naming the routine, the
path and `unresolved context`); a database default
`ALTER DATABASE ... SET search_path = public, pg_catalog` (the session check
refuses before any scan, `migration refused`, no routine named);
`SET search_path = pg_catalog, public` with the broken body (refuses on the
body: `post-drop`, `missing_column`) and with `SELECT 1` (applies);
`SET search_path = public` (implicit `pg_catalog` first; applies); the round-4
`SET search_path = "a=b", public` (applies). Every case asserts the session's
`search_path` is unchanged afterwards and the catalog, snapshot and stamps are
preserved.

### Red Against the Previous Migration (`23bf8aa9`)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=$S/old143.sql PYTHONPATH=$PWD:$S /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k "round6"
```

```text
OLD DESTRUCTIVE VERDICT: shadow-broken targets: (None, None)
OLD DESTRUCTIVE VERDICT: shadow-broken targets: (None, None)
OLD DESTRUCTIVE VERDICT: shadow-healthy targets: (None, None)
OLD DESTRUCTIVE VERDICT: shadow-healthy targets: (None, None)
OLD DESTRUCTIVE VERDICT: session-path targets: (None, None)
OLD DESTRUCTIVE VERDICT: session-path targets: (None, None)
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[shadow-broken-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[shadow-broken-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[shadow-healthy-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[shadow-healthy-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[session-path-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[session-path-True]
6 failed, 8 passed, 318 deselected in 41.00s
```

Correction recorded during round 8: the red run above is explicitly against
`23bf8aa9`, not `bbabe984`. The old `OLD DESTRUCTIVE VERDICT` labels establish
only that the targets disappeared, not that a routine broke. Two already-broken
`shadow-broken` cases applied without validation; four healthy `shadow-healthy`
and `session-path` cases applied. The eight remaining cases had their intended
outcome. The old output is retained verbatim as a historical artifact; its
"destructive" labels must not be treated as demonstrated post-drop failures.
Round-8 item 14 names `bbabe984`, which already refuses those explicit public-first
paths. That revision attribution requires coordinator correction before this
frozen order can be completed.

### Green With the Fix

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k "round6 or round5 or round4 or drops_only_manifest_on_each_fleet_clone or validation_refuses_without_scanner"
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
44 passed, 288 deselected in 154.82s (0:02:34)
```

`scripts/check_migration_comments.py`: OK. Black and flake8 on the test
module: clean. The full module, the runner and schema-documentation suites and
the whole-tree gate run at this head below.

## After the Seventh Independent Review (Coordinator Fix)

Date 2026-10-01. The seventh pass (Astra, frozen at `bbabe984`) found two P2
that together retire the path-precedence rule introduced in round 6:

- PostgreSQL function resolution ranks every candidate signature across the
  whole search path, so "pg_catalog first" does not make an unqualified
  builtin call deterministic: a surviving `public.jsonb_build_array(jsonb)`
  outranks the catalog's variadic overload for a single `jsonb` argument even
  under `search_path = pg_catalog, public`, the lexer's token array becomes
  empty, and a routine holding `EXECUTE 'SELECT 1 FROM public.items'` is never
  scanned (the red run below shows the drop proceeding).
- `IS DISTINCT FROM` resolves an `=` operator, so the round-6 path check was
  itself subject to the path it judged.

Only two things make a builtin call deterministic: schema qualification, or a
search path containing `pg_catalog` alone. The migration now runs under the
second for its entire body and uses the first wherever a routine's path must be
in force:

- `SET LOCAL search_path = pg_catalog` is the migration's first statement;
  `SET LOCAL search_path TO DEFAULT` is its last, handing the session's startup
  path back for the runner's own stamp statement.
- Every `pg_temp` helper pins `SET search_path = pg_catalog`.
- The scanner never switches the session to a routine's path. The routine's
  effective path (its declared `search_path`, else the session's startup path
  from `pg_settings.reset_val`) is passed to `dead143_body` as `routine_path`,
  and every name lookup that depends on it (`to_regclass`, `to_regtype`, the
  catalog-literal cast) goes through `pg_temp.dead143_resolve(statement,
  routine_path)`: a pinned helper that applies the routine's path, executes
  one statement prebuilt by its caller under `pg_catalog` with every function
  and type qualified, and returns to `pg_catalog` (on error too). So an
  unqualified name in a routine body resolves exactly as PostgreSQL resolves
  it for that routine, and nothing else resolves under that path.
- The validator sub-block applies the session's startup path, then the
  routine's own SET clauses, re-asserts `check_function_bodies`, and calls the
  validator chosen *before* the sub-block (a boolean, no `CASE … WHEN` operator
  lookup inside); every statement under the routine's environment is
  `pg_catalog`-qualified. The base path matters: a fleet routine with no
  declared path (`public.orrery_active_character_tag_names`, which names
  `entity_tags` unqualified) is validated under the session's startup path,
  as `CREATE FUNCTION` validated it, not under `pg_catalog` alone.
- The round-6 helper `dead143_path_first`, the session/scanner/validator path
  checks and the `search_path places a schema before pg_catalog` refusals are
  removed: declared paths are no longer refused, because the guard no longer
  depends on them.

`test_migration_143_round6_search_path` is rewritten for the design (eight
cases × `post`): the `public.set_config` stand-in under `public, pg_catalog`
with a broken body refuses on the body (`post-drop`, `missing_column`) and
with a healthy body applies; a database default `public, pg_catalog` applies;
the new `overload-broken` case (the reviewer's `public.jsonb_build_array(jsonb)`
plus a PL/pgSQL routine holding `EXECUTE 'SELECT 1 FROM public.items'` under
`pg_catalog, public`) refuses on the folded dynamic reference naming the
routine and `public.items`; `pg_catalog, public`, `public` and `"a=b", public`
keep their outcomes; every case asserts the session path is unchanged
afterwards and no `search_path places a schema` message appears.

### Red Against the Previous Migration (`bbabe984`)

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=$S/old143.sql PYTHONPATH=$PWD:$S /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k "round6"
```

```text
OLD DESTRUCTIVE VERDICT: overload-broken targets: (None, None)
OLD DESTRUCTIVE VERDICT: overload-broken targets: (None, None)
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[shadow-broken-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[shadow-broken-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[shadow-healthy-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[shadow-healthy-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[session-path-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[session-path-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[overload-broken-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round6_search_path[overload-broken-True]
8 failed, 8 passed, 318 deselected in 45.91s
```

Under `bbabe984` the overload case applied destructively (the drop targets are
gone; the reference was never seen); the stand-in and session-path cases were
refused on their paths rather than decided on their bodies.

### Green With the Fix

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p tests.dbname_audit -p no:cacheprovider tests/test_orrery/test_migration_dead_strata_pg.py -k "round6 or round5 or round4 or round3 or drops_only_manifest_on_each_fleet_clone or validation_refuses_without_scanner"
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
72 passed, 262 deselected in 218.70s (0:03:38)
```

Two intermediate failures during this fix are recorded because each is a
contract: with the session pinned to `pg_catalog` and no base path applied,
every fleet clone refused on `public.orrery_active_character_tag_names`
(`relation "entity_tags" does not exist`), which is why the validator applies
the session's startup path first; and without the closing
`SET LOCAL search_path TO DEFAULT`, the runner's stamp failed with
`relation "schema_migrations" does not exist`. `scripts/check_migration_comments.py`:
OK (an `EXECUTE` of a prebuilt validator call was replaced by a precomputed
boolean dispatch because the lint refuses run-time `EXECUTE` in top-level
blocks regardless of statement kind). The full module and the whole-tree gate
run at this head below.


### Coordinator-Reported Round-7 Gate Tails at `ebcfbe15`

The round-8 order supplies these completed coordinator runs dated 2026-10-05.
These are coordinator-reported tails, not runs repeated by this implementer:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
524 passed in 746.20s (0:12:26)
6450 passed, 59 skipped, 35 warnings in 3226.36s (0:53:46)
GATE-1098 EXIT=0
```

## After the Eighth Independent Review and the Panel

### Stop Report: Item 14 Attributes the Historical Run to the Wrong Revision

This round is **incomplete and not pushed**. The working rules explicitly require
"If the order's premise turns out to be false, write a stop-report instead of
improvising." Item 14 requires a claim that `bbabe984` applied the two broken and
four healthy path cases. The evidence's actual old run is headed `23bf8aa9`.
Reading `bbabe984:migrations/143_drop_dead_schema_strata.sql` proves that its
scanner already refuses an effective path preceding pg_catalog:

```sh
git show bbabe984:migrations/143_drop_dead_schema_strata.sql | sed -n '1083,1105p'
```

```text
            SELECT (pg_temp.dead143_setting(setting))[2] INTO effective_path FROM unnest(f.proconfig) setting WHERE setting LIKE 'search_path=%';
            PERFORM pg_catalog.set_config('search_path',coalesce(effective_path,saved_path),true);
            IF pg_temp.dead143_path_first() IS DISTINCT FROM 'pg_catalog' THEN
                RAISE EXCEPTION 'search_path places a schema before pg_catalog (%): builtin resolution is not deterministic; unresolved context',pg_catalog.current_setting('search_path');
            END IF;
```

Coordinator question: should item 14 name `23bf8aa9`, and describe the two
already-broken routines as applied without validation rather than newly broken
by the drops? The checkpoint does not invent the requested `bbabe984` verdict.

### Implemented Checkpoint and Limits

- Scanner uses complete parsed proconfig, PostgreSQL-parsed effective string
  settings, spaceless typed-literal tokens, all decoded literal target lookups,
  strict noncatalog fold-candidate checks, mutation forms, parenthesis-scoped
  JSON RETURNING, catalog index identities, and normal-OID/window selection.
- Resolver initially relied on normal function exit, as item 3 describes. The
  real declared-role test showed that a helper's SET search_path saves that GUC
  alone; other locally applied GUCs leaked and drops failed with "must be owner
  of table items". The checkpoint uses the protocol's native success-sentinel
  subtransaction pattern for the resolver too (D1431), without manual restore.
  The six focused role/lock/cache tests then passed. No routine is executed by
  the migration, and no runtime DDL was added.
- The lock policy remains a single top-level SET LOCAL value ('5s'), captured as
  a CONSTANT before routine SETs in the helper and validator; both reassert it.
  Both reassert exit_on_error=off; validators reassert check_function_bodies=on.
- Runner closes the tracking/bootstrap connection and uses a fresh maintenance
  connection per pending migration, preserving the locked-slot override.
- Ordinary archives dump NEXUS_template only. The separate fleet fixture requires
  NEXUS_RUN_CORPUS=1 and a selected requires_corpus marker. It logs every dump;
  marked six-source corpus rehearsal passed. No fleet routine was refused by
  the new literal rule and no exemption was introduced. The default template
  has an extension-owned public.|| candidate, so the literal EXECUTE controls
  explicitly declare search_path=pg_catalog; separate public-path tests require
  unresolved-context refusals. The accepted column-control routine likewise
  declares that safe path for its constant format call.
- Every migration refusal assertion now identifies scanner/validator/catalog/
  manifest/lock provenance. Historical verdict helpers execute routines after
  an old apply and require missing-relation/type errors for destructive labels;
  healthy and already-broken routines get distinct labels.
- All work remained in this worktree. The immutable SQL and old runner, recreated
  OLD_MIGRATION collection plugin, log runner and logs are in after-review-r8.
  The runner sets worktree PYTHONPATH, scratch TMPDIR, and (after the first red
  run) NEXUS_DBNAME_AUDIT=1, bounded at 540 seconds and 120 seconds silence.
  The first red run lacked the dbname audit; its immediately repeated audited
  run is the authoritative red cohort.
- The two mandatory lints passed. The full ordered PG proof, offline splits,
  no-new-diagnostics flake8/mypy comparison, final Black check, head-wide green
  rerun, PR-body update and push are **not completed**. Earlier focused green
  runs are not a green gate for the checkpoint. In particular, the final USAGE
  filtering and additional window/system-schema validator cases have red proof
  but no final green run. No paid calls, owner writes or service starts occurred.

### Exact Executed Commands and Verbatim Tails

All commands ran from the ordered worktree. `PY` below denotes the shared
`/Users/pythagor/nexus/.venv/bin/python`; `S` denotes the full after-review-r8
scratch path. These variables abbreviate the absolute paths in the executed
commands. Each entry also preserves its exact pytest/script argv. Log files
remain under S and are not repository artifacts.

**red-r8**

```sh
NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=$S/ebcfbe15.sql OLD_RUNNER=$S/old_runner.py $PY $S/run.py red-r8 /Users/pythagor/nexus/.venv/bin/python -m pytest -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k round8 -vs --tb=short
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-on-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-on-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-quote-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-quote-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[national-off-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[national-off-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[typed-date-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[typed-date-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[ordinary-data-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[ordinary-data-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[escaped-data-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[escaped-data-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[dollar-data-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[dollar-data-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[national-data-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[national-data-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[relation-size-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[relation-size-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[regclass-variable-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[regclass-variable-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[regtype-variable-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[regtype-variable-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-pkey-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-pkey-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-name-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-name-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-notebook-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-notebook-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-schema-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-schema-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-local-schema-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-local-schema-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-session-schema-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-session-schema-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[session-auth-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[session-auth-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-settings-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-settings-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-qualified-settings-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-qualified-settings-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[json-returning-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[json-returning-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-target-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-target-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[system-schema-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[system-schema-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-format-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-format-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-operator-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-operator-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-format-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-format-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-operator-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-operator-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[role-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[role-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[session_authorization-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[session_authorization-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_validator_lock_timeout
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_runner_recompiles
==== 64 failed, 16 passed, 334 deselected, 6 warnings in 150.36s (0:02:30) =====
EXIT STATUS: 1
```

**red-r8-audited**

```sh
NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=$S/ebcfbe15.sql OLD_RUNNER=$S/old_runner.py $PY $S/run.py red-r8-audited /Users/pythagor/nexus/.venv/bin/python -m pytest -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k round8 -vs --tb=short
```

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 83 targets: postgres, qa640_813_case_* x82
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-quote-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-quote-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[national-off-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[national-off-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[typed-date-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[typed-date-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[ordinary-data-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[ordinary-data-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[escaped-data-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[escaped-data-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[dollar-data-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[dollar-data-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[national-data-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[national-data-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[relation-size-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[relation-size-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[regclass-variable-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[regclass-variable-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[regtype-variable-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[regtype-variable-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-pkey-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-pkey-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-name-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-name-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-notebook-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[index-notebook-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-schema-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-schema-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-local-schema-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-local-schema-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-session-schema-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-session-schema-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[session-auth-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[session-auth-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-settings-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-settings-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-qualified-settings-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-qualified-settings-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[json-returning-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[json-returning-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-target-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-target-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[system-schema-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[system-schema-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-healthy-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-healthy-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-format-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-format-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-operator-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-operator-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-format-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-format-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-operator-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-operator-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[role-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[role-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[session_authorization-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[session_authorization-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_validator_lock_timeout
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_runner_recompiles
===== 64 failed, 18 passed, 334 deselected, 1 warning in 154.30s (0:02:34) =====
EXIT STATUS: 1
```

**green-r8-initial**

```sh
NEXUS_RUN_POSTGRES=1 $PY $S/run.py green-r8-initial /Users/pythagor/nexus/.venv/bin/python -m pytest tests/test_orrery/test_migration_dead_strata_pg.py -k round8 -vs --tb=short -x
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 416 items / 334 deselected / 82 selected

tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-False] 813 source dump: NEXUS_template
PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-on-False] FAILED

=================================== FAILURES ===================================
_______________ test_migration_143_round8_contract[scs-on-False] _______________
tests/test_orrery/test_migration_dead_strata_pg.py:1741: in test_migration_143_round8_contract
    assert applied is (defense is None), caplog.text
E   AssertionError: ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_r8() refuses: unresolved constant EXECUTE context: noncatalog format/concat/|| candidate
E     CONTEXT:  PL/pgSQL function inline_code_block line 637 at RAISE
E     
E     
E   assert False is (None is None)
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_r8() refuses: unresolved constant EXECUTE context: noncatalog format/concat/|| candidate
CONTEXT:  PL/pgSQL function inline_code_block line 637 at RAISE
dbname audit: 4 targets: postgres, qa640_813_case_* x3
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-on-False]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
================= 1 failed, 2 passed, 334 deselected in 6.26s ==================
EXIT STATUS: 1
```

**green-r8-second**

```sh
NEXUS_RUN_POSTGRES=1 $PY $S/run.py green-r8-second /Users/pythagor/nexus/.venv/bin/python -m pytest tests/test_orrery/test_migration_dead_strata_pg.py -k round8 -vs --tb=short -x
```

```text
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-schema-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-local-schema-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-local-schema-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-session-schema-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[set-session-schema-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[session-auth-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[session-auth-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-settings-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-settings-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-qualified-settings-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[update-qualified-settings-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[select-into-config-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[select-into-config-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[perform-config-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[perform-config-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[json-returning-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[json-returning-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[dml-returning-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[dml-returning-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-target-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-target-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-healthy-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-healthy-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[system-schema-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[system-schema-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-healthy-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-healthy-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[exit-on-error-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[runtime-data-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[runtime-data-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-format-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-format-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-concat-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-concat-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-operator-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[public,pg_catalog-operator-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-format-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-format-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-concat-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-concat-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-operator-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_fold_candidates[pg_catalog,public-operator-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[role-False] FAILED

=================================== FAILURES ===================================
____________ test_migration_143_round8_role_resolution[role-False] _____________
tests/test_orrery/test_migration_dead_strata_pg.py:1796: in test_migration_143_round8_role_resolution
    assert _apply(dbname), caplog.text
E   AssertionError: ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - must be owner of table items
E     
E     
E   assert False
E    +  where False = _apply('qa640_813_case_ba4349cfa925')
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - must be owner of table items
dbname audit: 78 targets: postgres, qa640_813_case_* x77
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[role-False]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
=========== 1 failed, 76 passed, 334 deselected in 166.37s (0:02:46) ===========
EXIT STATUS: 1
```

**green-r8-env**

```sh
NEXUS_RUN_POSTGRES=1 $PY $S/run.py green-r8-env /Users/pythagor/nexus/.venv/bin/python -m pytest tests/test_orrery/test_migration_dead_strata_pg.py -k 'round8_role or round8_validator or round8_runner' -vs --tb=short
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 416 items / 410 deselected / 6 selected

tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[role-False] 813 source dump: NEXUS_template
PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[role-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[session_authorization-False] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[session_authorization-True] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_validator_lock_timeout PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_runner_recompiles PASSED

dbname audit: 7 targets: postgres, qa640_813_case_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
secret-store guard: active; nexus-api: denied; disposable keychain: denied
====================== 6 passed, 410 deselected in 16.85s ======================
EXIT STATUS: 0
```

**fleet**

```sh
NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 $PY $S/run.py fleet /Users/pythagor/nexus/.venv/bin/python -m pytest tests/test_orrery/test_migration_dead_strata_pg.py -k each_fleet -vs --tb=short
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 416 items / 410 deselected / 6 selected

tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[NEXUS_template] 813 source dump: NEXUS_template
813 source dump: save_01
813 source dump: save_02
813 source dump: save_03
813 source dump: save_04
813 source dump: save_05
PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_01] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_02] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_03] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_04] PASSED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_drops_only_manifest_on_each_fleet_clone[save_05] PASSED

dbname audit: 7 targets: postgres, qa640_813_case_* x6
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
secret-store guard: active; nexus-api: denied; disposable keychain: denied
================= 6 passed, 410 deselected in 82.30s (0:01:22) =================
EXIT STATUS: 0
```

**red-r8-final-additions**

```sh
NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=$S/ebcfbe15.sql $PY $S/run.py red-r8-final-additions /Users/pythagor/nexus/.venv/bin/python -m pytest -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k 'round8 and (scs or role or window-broken or system-schema-broken)' -vs --tb=short
```

```text
    assert _apply(dbname) is usage, caplog.text
E   AssertionError: ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_role() refuses: target items: hidden body identifier reference
E     CONTEXT:  PL/pgSQL function inline_code_block line 628 at RAISE
E     
E     
E   assert False is True
E    +  where False = _apply('qa640_813_case_a9993d690a29')
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_role() refuses: target items: hidden body identifier reference
CONTEXT:  PL/pgSQL function inline_code_block line 628 at RAISE
__________ test_migration_143_round8_role_resolution[True-role-True] ___________
tests/test_orrery/test_migration_dead_strata_pg.py:1936: in test_migration_143_round8_role_resolution
    assert _apply(dbname) is usage, caplog.text
E   AssertionError: ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_role() refuses: target items: hidden body identifier reference
E     CONTEXT:  PL/pgSQL function inline_code_block line 628 at RAISE
E     
E     
E   assert False is True
E    +  where False = _apply('qa640_813_case_9407769f3ab4')
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_role() refuses: target items: hidden body identifier reference
CONTEXT:  PL/pgSQL function inline_code_block line 628 at RAISE
_ test_migration_143_round8_role_resolution[True-session_authorization-False] __
tests/test_orrery/test_migration_dead_strata_pg.py:1936: in test_migration_143_round8_role_resolution
    assert _apply(dbname) is usage, caplog.text
E   AssertionError: ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_role() refuses: target items: hidden body identifier reference
E     CONTEXT:  PL/pgSQL function inline_code_block line 628 at RAISE
E     
E     
E   assert False is True
E    +  where False = _apply('qa640_813_case_e322105ed5b5')
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_role() refuses: target items: hidden body identifier reference
CONTEXT:  PL/pgSQL function inline_code_block line 628 at RAISE
__ test_migration_143_round8_role_resolution[True-session_authorization-True] __
tests/test_orrery/test_migration_dead_strata_pg.py:1936: in test_migration_143_round8_role_resolution
    assert _apply(dbname) is usage, caplog.text
E   AssertionError: ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_role() refuses: target items: hidden body identifier reference
E     CONTEXT:  PL/pgSQL function inline_code_block line 628 at RAISE
E     
E     
E   assert False is True
E    +  where False = _apply('qa640_813_case_dcb60f5258d8')
------------------------------ Captured log call -------------------------------
ERROR    nexus.migrate:migrate.py:364   FAILED: 143_drop_dead_schema_strata - target public.items/public.ai_notebook/nine enums: function/procedure public.probe813_role() refuses: target items: hidden body identifier reference
CONTEXT:  PL/pgSQL function inline_code_block line 628 at RAISE
dbname audit: 19 targets: postgres, qa640_813_case_* x18
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-quote-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[scs-off-quote-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-broken-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[window-broken-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[system-schema-broken-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_contract[system-schema-broken-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[True-role-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[True-role-True]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[True-session_authorization-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[True-session_authorization-True]
================ 12 failed, 6 passed, 406 deselected in 31.96s =================
EXIT STATUS: 1
```

**red-r8-usage**

```sh
NEXUS_RUN_POSTGRES=1 OLD_MIGRATION=$S/ebcfbe15.sql $PY $S/run.py red-r8-usage /Users/pythagor/nexus/.venv/bin/python -m pytest -p old_scanner tests/test_orrery/test_migration_dead_strata_pg.py -k 'round8_role and False-role' -vs --tb=short
```

```text
<frozen abc>:106: DeprecationWarning: You should use `Logger` instead. Deprecated since version 1.39.0 and will be removed in a future release.
<frozen abc>:106: DeprecationWarning: You should use `LoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/opentelemetry/_events/__init__.py:201: DeprecationWarning: You should use `ProxyLoggerProvider` instead. Deprecated since version 1.39.0 and will be removed in a future release.
  _PROXY_EVENT_LOGGER_PROVIDER = ProxyEventLoggerProvider()
============================= test session starts ==============================
platform darwin -- Python 3.11.12, pytest-8.3.5, pluggy-1.5.0 -- /Users/pythagor/nexus/.venv/bin/python
cachedir: .pytest_cache
secret-store guard: active; nexus-api: denied; disposable keychain: denied
rootdir: /Users/pythagor/nexus/.claude/worktrees/813-drop-dead-strata
configfile: pytest.ini
plugins: asyncio-1.2.0, anyio-4.9.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 424 items / 422 deselected / 2 selected

tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[False-role-False] 813 source dump: NEXUS_template
OLD DESTRUCTIVE VERDICT role call failed: relation "items" does not exist
FAILED
tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[False-role-True] OLD DESTRUCTIVE VERDICT role call failed: relation "items" does not exist
FAILED

=================================== FAILURES ===================================
_________ test_migration_143_round8_role_resolution[False-role-False] __________
tests/test_orrery/test_migration_dead_strata_pg.py:1946: in test_migration_143_round8_role_resolution
    assert applied is usage, caplog.text
E   AssertionError: 
E   assert True is False
__________ test_migration_143_round8_role_resolution[False-role-True] __________
tests/test_orrery/test_migration_dead_strata_pg.py:1946: in test_migration_143_round8_role_resolution
    assert applied is usage, caplog.text
E   AssertionError: 
E   assert True is False
dbname audit: 3 targets: postgres, qa640_813_case_* x2
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[False-role-False]
FAILED tests/test_orrery/test_migration_dead_strata_pg.py::test_migration_143_round8_role_resolution[False-role-True]
====================== 2 failed, 422 deselected in 3.79s =======================
EXIT STATUS: 1
```

**migration-comment-lint**

```sh
PYTHONPATH=$PWD $PY $S/run.py migration-comment-lint /Users/pythagor/nexus/.venv/bin/python scripts/check_migration_comments.py
```

```text

OK: every object created after migration 129 has a comment.
EXIT STATUS: 0
```

**exception-lint**

```sh
PYTHONPATH=$PWD $PY $S/run.py exception-lint /Users/pythagor/nexus/.venv/bin/python -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
```

```text

OK: exception disposition coverage and shrink-only baseline verified.
EXIT STATUS: 0
```

### Git State and Handoff

`git fetch origin main` resolved main to
`160134540517f6b74aacd1d1e1f3f584454eef86`. `git merge origin/main` returned
`Already up to date.`; this main revision was already in the frozen head's
ancestry. No rebase, rewrite, stash or main-checkout edit occurred. The current
changes are checkpointed locally because useful work must not remain unstaged
at handoff. They are not ready for push or merge; the frozen-order discrepancy
and the incomplete proof gates above remain explicit.
