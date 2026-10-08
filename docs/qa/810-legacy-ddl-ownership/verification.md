# Legacy Script DDL Ownership Verification

Refs #810. Order: `810-S3.md`, including Decisions 810-Q3, Q4 and Q9.

## Resumed State and Scope

Claude's saved implementation was clean at `9b90bc88`. On 2026-10-08, Codex
reviewed it against the full order and the recorded issue decisions, merged
`origin/main` (`afd034f360e625f8bc4ffa8a717dda28422b19c7`) without conflicts as
`b83dd1036fd9884d01ee4be3962002a8728e46ec`, and ran the proof below. No source
correction was needed. The evidence commit after that merge changes this
verification document and its logs only. The pre-edit and planted-index controls
were temporary, and every script was restored byte-for-byte before the final run.

This is focused branch proof. The coordinator explicitly owns the serial full
integration gate, including the broader offline consumers. That gate and the
independent review remain prerequisites to opening the PR. No PR was opened and
nothing was merged to main during this resume.

## Source Audit

The pre-edit citations below are from `origin/main` at `afd034f3`; current
citations refer to `b83dd103`. The full static inventory, including every
path, line, scope and statement, is in
[scan-main.txt](resume-2026-10-08/scan-main.txt) and
[scan-branch.txt](resume-2026-10-08/scan-branch.txt).

| Area | Before | Current Behavior |
| --- | --- | --- |
| Scene metadata | `scripts/update_scene_numbers.py:60-104` and `scripts/extract_scene_numbers.py:147-191` added the scene column and two indexes owned by migration 138. | `require_scene_column` at lines 60 and 147 respectively checks the public column and raises the exact migration-138 message. Both main paths call the check. |
| Assets flag | `scripts/new_story_setup.py:69-89` created a nine-column assets table. Migration 007 owns it; all six fleet copies have 54 columns. | `require_assets_tables` at line 69 only reads `to_regclass`; `--create-assets` remains available with check-only help and its call at line 571. The four extension-creation statements remain at lines 256, 261, 488 and 493. |
| Importer | `scripts/import_narratives.py:247-271` installed vector, dropped four tables and called `Base.metadata.create_all`. | `_require_importer_schema` at line 229 checks vector, both baseline tables, then the obsolete undimensioned table. The constructor calls it at line 288. ORM declarations remain. No current reader of the two old schema-creation settings remains. |
| ANN helpers | `scripts/create_vector_index.py:170-210` dropped/created indexes; `scripts/regenerate_embeddings.py:751-774` created indexes. | Both `create_vector_indexes` methods (lines 90 and 715) query existing public HNSW/IVFFlat indexes. Missing indexes raise the exact 2560d-gate/#812 message; the existing missing-table, empty-model and dimension-limit behavior stays. CLI flag names remain, with check-only help and status text. |
| Regenerator setup | `scripts/regenerate_embeddings.py:354` installed vector; line 446 dropped a dimensional table under the unused `force_recreate` switch. | The extension check at line 355 refuses a missing extension. `_ensure_dimension_table_exists` at line 434 has no force-recreate parameter or DROP; `ensure_embedding_table` remains the lazy owner at line 451. |
| Old vector migration | `scripts/vector_migration.py:60,197,230` altered the undimensioned table, created its index and printed a DROP hint. | `require_dimensions_column` at line 44 checks public metadata and raises the exact legacy-table explanation. No index creation or DROP hint remains. |
| Season extractor | `scripts/extract_season_episode.py:143-162` called `initialize_database`, which created `ChunkMetadata.__table__` at line 161. | Lines 143-165 preserve the check call and inspection, then raise the exact baseline-schema message. No ORM schema creation remains. |
| Provider rewrite | `scripts/migrate_provider_names.py:28-35,99-115` altered and replaced `apex_audition.provider_enum`. | `migrate` at line 22 reads existing enum labels and refuses missing values before the retained Steps 2-3 data rewrite/verification. No fleet database has that schema. |
| Data backup | `scripts/update_raw_text.py:110-139` copies narrative chunks before rewriting data. | Unchanged by decision; line 128 is explicitly allowlisted. |
| Documentation | `docs/database.md:86-89` described the legacy DDL as future work. | Lines 86-103 describe the checks and scanner. Other main documentation is preserved. `docs/vector_embeddings.md` remains untouched and historical. |

`tests/test_schema_ownership.py:54-112` has exactly fourteen reasoned allowlist
keys. The scanner at lines 115-242 covers string constants including f-string
parts, ignores actual docstrings, tracks dotted lexical scopes, and recognizes
both ORM schema-call forms. Its documented limit remains runtime-built verbs or
object kinds; it does not scan SQL or shell files. On main it finds 50 sites,
31 unowned. On the restored branch it finds 19 sites, zero unowned. Every
allowlist entry still matches a site. The deleted line-230 vector DROP hint was
also a static finding because the scanner deliberately covers all non-docstring
strings, including printed instructions.

The exception baseline removes exactly eight obsolete entries: two from
`create_vector_index.create_vector_indexes`, one from each scene helper, one
from `NarrativeImporter.__init__`, two from
`EmbeddingRegenerator.create_vector_indexes`, and one from
`vector_migration.create_index`. No reachability baseline was changed.
[Exact baseline delta](resume-2026-10-08/baseline-delta.diff).

## Read-Only Fleet Survey

The survey used `nexus.database.connection_kwargs` with an explicit empty
password (no secret-store lookup) and
`options='-c default_transaction_read_only=on'` from connection startup. It
asserted `SHOW transaction_read_only = on` for each database. Only catalog
SELECTs ran; no edited legacy script ran against an owner database.
[All six results](resume-2026-10-08/fleet-survey.txt).

```sql
SHOW transaction_read_only;
SELECT to_regnamespace('apex_audition')::text,
       to_regclass('public.chunk_embeddings')::text,
       to_regclass('public.chunk_embeddings_small')::text;
SELECT count(*) FROM information_schema.columns
 WHERE table_schema = 'assets' AND table_name = 'new_story_creator';
SELECT tablename, indexname, indexdef FROM pg_indexes
 WHERE schemaname = 'public'
   AND tablename IN ('chunk_embeddings_1024d', 'chunk_embeddings_1536d')
   AND indexdef ~ 'USING (hnsw|ivfflat)'
 ORDER BY tablename, indexname;
```

`NEXUS_template` and `save_01` through `save_05` all have no `apex_audition`
schema, no undimensioned embedding table or small companion, and exactly 54
columns in `assets.new_story_creator`. Only saves 01 and 02 have the legacy
1024d/1536d HNSW indexes. Both indexes use `vector_cosine_ops`,
`ef_construction=64`, `m=16`; this observed definition is retained verbatim in
the survey output. This order does not alter those indexes.

## Commands and Results

Every run used `/Users/pythagor/nexus/.venv/bin/python` as `$PY`,
`PYTHONPATH=$PWD` pointing exactly at
`/Users/pythagor/nexus/.claude/worktrees/810-legacy-ddl-ownership`, and `nice -n 15`.
The import preflight printed that worktree's `nexus/__init__.py`.
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT`, and `NEXUS_RUN_LIVE_LLM`
were unset. PostgreSQL runs used `NEXUS_RUN_POSTGRES=1` and
`-p tests.dbname_audit`. Sessions ran serially; one-minute load was below 24
before each (5.39 for the ordered proof, recorded in each red transcript,
5.77 for the final restored run). No paid calls, owner writes, service changes,
model downloads or model-cache changes were requested.

### Ordered PostgreSQL Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q \
  -p tests.dbname_audit \
  tests/test_schema_ownership.py tests/test_new_story_setup.py \
  tests/test_postgres_tools.py tests/test_unowned_index_adoption_pg.py \
  tests/test_regenerate_embeddings_truncate_pg.py \
  tests/test_memnon_script_model_loaders.py tests/test_memnon/test_ann_gate.py \
  tests/test_orrery/test_card_identity.py tests/test_connection_lifecycle.py \
  tests/test_owner_target_guard.py
```

[Full ordered log](resume-2026-10-08/focused.txt), exit 0:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
155 passed, 3 skipped, 2 warnings in 110.77s (0:01:50)
```

The three skips are the opt-in `requires_corpus` cases: the ANN operator probe
and the sync/async owner-corpus card-exposure probes. `NEXUS_RUN_CORPUS` was not
enabled. All new ownership PostgreSQL cases ran. The model-loader test file is
unchanged and passed. The audit's `save_04` names are on two fixture-owned,
registered disposable clusters (ports 56440/56442), not the owner server.
Legacy-script child probes receive only the disposable URL from the fixture
and have Hugging Face/Transformers offline flags set; their parent fixture
connections are present in the audit.

### Negative Controls and Restored Proof

The original pre-edit transcript was not present in the saved worktree. The
pre-edit proof was therefore **replayed on 2026-10-08**, using the branch's new
test file and temporarily replacing all nine edited scripts with their exact
`origin/main` bytes. This is not claimed as Claude's historical red run.

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q \
  -p tests.dbname_audit tests/test_schema_ownership.py
```

[Full replayed red log](resume-2026-10-08/red-pre-edit-replayed.txt), exit 1:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
10 failed, 11 passed in 16.78s
```

The tree test reports all 31 legacy sites. All nine PostgreSQL test instances
also fail against the old scripts. Restoring the branch and planting the
ordered `CREATE INDEX` inside `require_scene_column` yields the second control:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q \
  -p tests.dbname_audit \
  tests/test_schema_ownership.py::test_tree_has_no_unowned_ddl
```

[Plant diff](resume-2026-10-08/planted-index.diff),
[full failing log](resume-2026-10-08/red-planted-index.txt), exit 1:

```text
E         scripts/update_scene_numbers.py:72 require_scene_column CREATE INDEX
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
1 failed in 1.40s
```

The control harness initially searched for a nonexistent source anchor twice;
it stopped before writing any plant. After correcting the anchor from the actual
source, the control above ran successfully. Both temporary source rewrites use
`finally` restoration, and the scripts' final bytes match the committed branch.

After restoration:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -rs \
  -p tests.dbname_audit tests/test_schema_ownership.py \
  tests/test_doc_front_matter.py tests/test_reachability.py
```

[Full final log](resume-2026-10-08/restored-final.txt), exit 0:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
117 passed in 37.96s
```

### Static Checks

The exact ten changed Python paths are in
[changed-python.txt](resume-2026-10-08/changed-python.txt). Each command below
ran on those paths. The same flake8/mypy commands ran on the nine pre-existing
paths from an `origin/main` snapshot containing all 852 tracked Python/config
files, so imported-module context matches main. Line numbers were normalized
for diagnostic comparison; no new diagnostics or messages appeared.

```sh
nice -n 15 $PY -m black --check <changed Python paths>
nice -n 15 $PY -m flake8 <changed Python paths>
nice -n 15 $PY -m mypy --explicit-package-bases <changed Python paths>
nice -n 15 $PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main
git diff --check
```

- Black: all ten files unchanged; exit 0 ([log](resume-2026-10-08/black.txt)).
- flake8: 100 branch diagnostics versus 126 main diagnostics; no new messages.
  [Branch](resume-2026-10-08/flake8.txt),
  [main](resume-2026-10-08/flake8-main.txt),
  [delta](resume-2026-10-08/flake8-delta.txt).
- mypy: 39 errors in five existing files on both branch and main; identical
  normalized diagnostics. The new scanner/test file adds none.
  [Branch](resume-2026-10-08/mypy.txt),
  [main](resume-2026-10-08/mypy-main.txt),
  [delta](resume-2026-10-08/mypy-delta.txt).
- Exception disposition check: `OK: exception disposition coverage and
  shrink-only baseline verified.`
  [Log](resume-2026-10-08/exception-check.txt). Whitespace check also passed.

## Landing and Deferred Work

No migration, fleet application, `nexus.toml` change or UI rebuild. A gateway
restart is owed when the owner's services run again because
`nexus/api/new_story_flow.py` imports `scripts/new_story_setup.py`; no service was
restarted here. The coordinator must integrate this branch's overlapping regions
with 812-S4a and run the full gate before opening the PR. This branch does not
merge 812's registry/schema-copy work. Its committed source proof remains
`b83dd103`; subsequent commits only package evidence.

Deferred: 810-S4a genesis generator/artifact; PostgreSQL rebuild-and-drift CI;
`[memnon.database] create_tables` and `drop_existing` (`nexus.toml:907-908`,
`nexus/config/settings_models.py:3221-3222`), now read by no code; command
retirement under #811; the importer's metadata mismatch/fate under #1091;
#812's legacy dimensional tables/indexes; hand SQL and shell scripts, `ir_eval/`,
and all other regions excluded by the frozen order. The data backup and the
existing lazy dimensional-table owner remain by explicit decision.

Codex — GPT-6
