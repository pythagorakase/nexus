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
