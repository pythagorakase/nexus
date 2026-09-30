# Verification for #810: Migration 138 Adopts Three Unowned Indexes and One Column

Branch `claude/810-adopt-unowned-indexes`, cut from `origin/main` at c8dd8c85.
Every command ran from the worktree root with the shared interpreter
`/Users/pythagor/nexus/.venv/bin/python` (`$PY`) and `PYTHONPATH=$PWD`, with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT` unset. No `save_NN`
database or `NEXUS_template` was written; the six databases below were only
read, and every write in the tests went to a disposable `qa640_810_*` clone.

## Live Catalog on the Six Fleet Databases (Read-Only, 2026-09-30)

```
for db in NEXUS_template save_01 save_02 save_03 save_04 save_05; do
  psql -X -At -d $db \
    -c "select indexname||' | '||indexdef from pg_indexes where schemaname='public' and indexname in ('narrative_chunks_text_idx','idx_chunk_metadata_scene','idx_chunk_metadata_season_episode_scene') order by indexname" \
    -c "select 'col: '||format_type(a.atttypid,a.atttypmod)||' | '||coalesce(col_description(a.attrelid,a.attnum),'<null>') from pg_attribute a where a.attrelid='public.chunk_metadata'::regclass and a.attname='scene'" \
    -c "select 'max stamp: '||max(version) from schema_migrations"
done
```

Each of the six databases printed exactly these five lines (the output repeats
them once per database with a `== <db>` header):

```
idx_chunk_metadata_scene | CREATE INDEX idx_chunk_metadata_scene ON public.chunk_metadata USING btree (scene)
idx_chunk_metadata_season_episode_scene | CREATE INDEX idx_chunk_metadata_season_episode_scene ON public.chunk_metadata USING btree (season, episode, scene)
narrative_chunks_text_idx | CREATE INDEX narrative_chunks_text_idx ON public.narrative_chunks USING gin (to_tsvector('english'::regconfig, raw_text))
col: integer | Scene number within the episode
max stamp: 136
```

Three views read `chunk_metadata.scene` on `NEXUS_template` (`narrative_view`,
`chunk_character_references_view`, `chunk_places_view`; `pg_depend` through
`pg_rewrite`). The recreate test drops the column with `CASCADE` on its clone
and does not compare those views.

## Ownership Proofs (`git grep`)

No migration adds `chunk_metadata.scene`; only the two legacy scripts do.
Migration 001 names the column only in its prose list of the manual schema,
and migration 078 lists it among the columns it requires, without creating it
(`migrations/078_retrograde_summary_storage.py:159-165`).

```
$ git grep -n -i -E "add column( if not exists)? +scene( |;|$)" c8dd8c85 -- migrations scripts
c8dd8c85:scripts/extract_scene_numbers.py:163:                    ALTER TABLE chunk_metadata ADD COLUMN scene int4;
c8dd8c85:scripts/update_scene_numbers.py:76:                    ALTER TABLE chunk_metadata ADD COLUMN scene int4;

$ git grep -n -i "add column.*scene" c8dd8c85 -- migrations
c8dd8c85:migrations/094_scene_weather_override.sql:6:    ADD COLUMN scene_weather text NULL;

$ git grep -n -w "scene" c8dd8c85 -- migrations/001_baseline.sql
c8dd8c85:migrations/001_baseline.sql:12:--   - chunk_metadata: Chunk metadata (season, episode, scene)
```

The three index names had no migration owner:

```
$ git grep -n -E "narrative_chunks_text_idx|idx_chunk_metadata_scene|idx_chunk_metadata_season_episode_scene" c8dd8c85
c8dd8c85:nexus/agents/memnon/utils/db_access.py:478:                CREATE INDEX IF NOT EXISTS narrative_chunks_text_idx 
c8dd8c85:scripts/extract_scene_numbers.py:171:                    CREATE INDEX IF NOT EXISTS idx_chunk_metadata_scene 
c8dd8c85:scripts/extract_scene_numbers.py:174:                    CREATE INDEX IF NOT EXISTS idx_chunk_metadata_season_episode_scene 
c8dd8c85:scripts/update_scene_numbers.py:84:                    CREATE INDEX IF NOT EXISTS idx_chunk_metadata_scene 
c8dd8c85:scripts/update_scene_numbers.py:87:                    CREATE INDEX IF NOT EXISTS idx_chunk_metadata_season_episode_scene 
```

`MEMNON._initialize_database_connection` and `MEMNON._setup_hybrid_search`
had no caller. At the base, every hit is either a definition, the one call
from inside the dead `MEMNON._initialize_database_connection` (memnon.py:573),
or the separate `DatabaseManager` methods in `db_schema.py`. `MEMNON` builds
its database access through `DatabaseManager` instead.

```
$ git grep -n -E "_initialize_database_connection|_setup_hybrid_search" c8dd8c85 -- nexus scripts tests ir_eval
c8dd8c85:nexus/agents/memnon/memnon.py:540:    def _initialize_database_connection(self) -> sa.engine.Engine:
c8dd8c85:nexus/agents/memnon/memnon.py:573:                    self._setup_hybrid_search(engine)
c8dd8c85:nexus/agents/memnon/memnon.py:587:    def _setup_hybrid_search(self, engine):
c8dd8c85:nexus/agents/memnon/utils/db_schema.py:107:        self.engine = self._initialize_database_connection()
c8dd8c85:nexus/agents/memnon/utils/db_schema.py:112:    def _initialize_database_connection(self) -> sa.engine.Engine:
c8dd8c85:nexus/agents/memnon/utils/db_schema.py:152:                    self._setup_hybrid_search(engine)
c8dd8c85:nexus/agents/memnon/utils/db_schema.py:166:    def _setup_hybrid_search(self, engine):

$ git grep -n -E "_initialize_database_connection|_setup_hybrid_search" -- nexus scripts tests ir_eval    # this branch
nexus/agents/memnon/utils/db_schema.py:107:        self.engine = self._initialize_database_connection()
nexus/agents/memnon/utils/db_schema.py:112:    def _initialize_database_connection(self) -> sa.engine.Engine:
nexus/agents/memnon/utils/db_schema.py:149:                    self._setup_hybrid_search(engine)
nexus/agents/memnon/utils/db_schema.py:163:    def _setup_hybrid_search(self, engine):
```

The four imports that only the dead methods used (`create_slot_engine`,
`verify_database_url`, `check_vector_extension`, `setup_database_indexes`) were
removed from `memnon.py`; no module or test reads them through
`nexus.agents.memnon.memnon` (`git grep -n -E "memnon\.memnon\.(create_slot_engine|verify_database_url|check_vector_extension|setup_database_indexes)"`
and a search for their quoted names under `tests nexus scripts ir_eval` both
print nothing).

Nothing links to the deleted document:

```
$ git grep -n "memnon_hybrid_search" c8dd8c85
(no output)
```

After the change, no `create_all` call remains under `nexus/`; the two that
remain are out of scope (`scripts/import_narratives.py`, and a `.bak` file):

```
$ git grep -n "create_all" -- nexus scripts
scripts/generate_psychology.py.bak:135:    metadata.create_all(engine)
scripts/import_narratives.py:268:            Base.metadata.create_all(self.engine)
```

## Scratch Plant: `create_all` Restored

With `Base.metadata.create_all(engine)` put back into
`DatabaseManager._initialize_database_connection` (then reverted; `git diff`
afterward shows only the deletion):

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_unowned_index_adoption_pg.py -k "creates_no_table or no_create_all_call"
E                   AssertionError: assert ('characters',) == (None,)
E       AssertionError: assert ['nexus/agent...chema.py:128'] == []
E         Left contains one more item: 'nexus/agents/memnon/utils/db_schema.py:128'
FAILED tests/test_unowned_index_adoption_pg.py::test_database_manager_construction_creates_no_table
FAILED tests/test_unowned_index_adoption_pg.py::test_no_create_all_call_under_nexus
2 failed, 3 deselected in 2.62s
```

## Migration Comment Lint

```
$ $PY scripts/check_migration_comments.py
OK: every object created after migration 129 has a comment.
```

Plant: a copy of `migrations/` whose 138 lacks the `COMMENT ON COLUMN` line.

```
$ $PY scripts/check_migration_comments.py --migrations-dir <scratch copy>
Found 1 schema documentation finding(s):
  <scratch copy>/138_adopt_unowned_fleet_indexes.sql:40: column public.chunk_metadata.scene has no COMMENT ON COLUMN
```

## PostgreSQL Proof Files

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_database_contract.py tests/test_orrery/test_migrate.py tests/test_new_story_setup.py tests/test_schema_documentation_pg.py tests/test_memnon_db_access.py tests/test_unowned_index_adoption_pg.py
E       AssertionError: assert {'013', '119', '137'} == frozenset({'013', '119'})
E         
E         Extra items in the left set:
E         '137'
E         Use -v to get more diff

tests/test_orrery/test_migrate.py:266: AssertionError
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 27 targets: nexus_m10_fresh_test_28758, nexus_m10_template_test_28758, postgres, qa640_810_adopt_drift_*, qa640_810_adopt_noop_*, qa640_810_adopt_recreate_*, qa640_810_clone_*, qa640_810_dataclone_*, qa640_810_fail_*, qa640_810_firstpass_*, qa640_810_no_create_all_*, qa640_810_noconn_*, qa640_810_restore_*, qa640_810_template_*, qa640_connection_contract, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_raw_url_contract, qa640_schema_docs_* x3, qa640_vocab_migration_* x6
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:62068 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[1] at local:62069 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[0] at local:62076 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard; two_clusters[1] at local:62079 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard
dbname audit: owner names admitted on registered clusters: none
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 150 passed in 42.26s
```

The one failure is expected: migration 137 belongs to the parallel #819 order
and is not on this branch, so the sequence test sees 137 as a gap. It is not
added to `KNOWN_GAPS`; the coordinator merges `main` after 137 lands and reruns
the test.

## Offline Suites

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2609 passed, 410 skipped, 8 warnings in 404.25s (0:06:44)
```

```
$ $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps
1 failed, 1810 passed, 742 skipped, 7 warnings in 38.94s
```

The one failure is the same expected 137 gap.

```
$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed, 5 warnings in 9.78s
```

## Formatting, Lint, and Types on the Changed Python Files

- `black --check` on `nexus/agents/memnon/memnon.py`,
  `nexus/agents/memnon/utils/db_schema.py`, and
  `tests/test_unowned_index_adoption_pg.py`: `3 files would be left unchanged.`
- `flake8`: the new test file is clean. The finding sets of `memnon.py` and
  `db_schema.py` against their c8dd8c85 versions differ only by two `E501`
  lines removed from `memnon.py` (in the deleted methods); every remaining
  finding (unused imports, long lines) predates this change.
- `mypy` on the same three files: no error in the new test file. The errors
  it reports sit in untouched code of `memnon.py` and in the `db_schema.py`
  model classes (`Base` as a declarative base), which this change does not
  edit.
