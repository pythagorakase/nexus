# 778-S1a Verification: Primary-Only World Clock, Layer Refresh, Delta CHECK, and the Two-Clock Comments

Issue #778, work order 778-S1a, branch `claude/778-world-clock-primary-layer`.
Final head is rebased on `origin/main` at `56c884e7` (migration 139 is on
`main`, so `test_migration_sequence_has_only_known_gaps` passes at the final
head). No `save_NN` or `NEXUS_template` was written; every write went to a
disposable `qa640_*`/`qa885_*`/`qa762_*` clone. No paid call, no gateway lane.

## Fleet Survey (Read-Only, 2026-10-01)

Columns: database, rows, negative deltas, non-primary rows with a non-zero
delta, NULL `world_layer` rows, bootstrap row (`chunk_id layer delta`), rows
whose stored `world_time` differs from a primary-only recompute.

```text
save_01 | 1425 | 0 | 0 | 0 | 1 extradiegetic 00:00:00 | 0
save_02 | 1425 | 0 | 0 | 0 | 1 extradiegetic 00:00:00 | 0
save_03 | 40 | 0 | 0 | 0 | 1 retrograde 00:00:00 | 0
save_04 | 46 | 0 | 0 | 0 | 1 retrograde 00:00:00 | 0
save_05 | 0 | 0 | 0 | 0 | none | 0
ref_codex_bakeoff_2026_07 | 111 | 0 | 0 | 0 | 1 retrograde 00:00:00 | 0
NEXUS_template | 0 | 0 | 0 | 0 | none | 0
```

The recompute was:

```sql
SELECT count(*) FROM (
  SELECT cm.world_time,
         (SELECT COALESCE(base_timestamp, now()) FROM global_variables WHERE id)
         + COALESCE(SUM(COALESCE(cm.time_delta, interval '0'))
                      FILTER (WHERE cm.world_layer = 'primary')
                      OVER (ORDER BY cm.chunk_id), interval '0') AS w
  FROM chunk_metadata cm) s
WHERE s.world_time IS DISTINCT FROM s.w;
```

`pg_get_functiondef('refresh_world_time_from_chunk()')` and the trigger
definition on `NEXUS_template` before this change matched
`migrations/023_orrery_schema.py:721-746,756-761` (all-layer sum, `AFTER
INSERT OR UPDATE OF time_delta`); `chunk_metadata` carried one CHECK,
`chunk_metadata_scene_weather_check`.

## Zero-Change Proof (Head `c5c593c6`)

```text
=== save_02 -> qa640_778s1a_02 (head c5c593c6)
$ createdb -T template0 qa640_778s1a_02
$ pg_dump --format=custom --dbname save_02 --file save_02.dump
$ pg_restore --exit-on-error --no-owner --no-acl --dbname qa640_778s1a_02 save_02.dump
before rows:     1425
$ PYTHONPATH=$PWD $PY scripts/migrate.py --dbname qa640_778s1a_02
INFO   Applied: 140_world_clock_primary_layer
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_778s1a_02: 137 migration stamps; level 140
after rows:     1425
$ cmp before after
cmp: identical (exit 0)
$ dropdb qa640_778s1a_02
=== save_03 -> qa640_778s1a_03 (head c5c593c6)
$ createdb -T template0 qa640_778s1a_03
$ pg_dump --format=custom --dbname save_03 --file save_03.dump
$ pg_restore --exit-on-error --no-owner --no-acl --dbname qa640_778s1a_03 save_03.dump
before rows:       40
$ PYTHONPATH=$PWD $PY scripts/migrate.py --dbname qa640_778s1a_03
INFO   Applied: 140_world_clock_primary_layer
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_778s1a_03: 137 migration stamps; level 140
after rows:       40
$ cmp before after
cmp: identical (exit 0)
$ dropdb qa640_778s1a_03
=== save_04 -> qa640_778s1a_04 (head c5c593c6)
$ createdb -T template0 qa640_778s1a_04
$ pg_dump --format=custom --dbname save_04 --file save_04.dump
$ pg_restore --exit-on-error --no-owner --no-acl --dbname qa640_778s1a_04 save_04.dump
before rows:       46
$ PYTHONPATH=$PWD $PY scripts/migrate.py --dbname qa640_778s1a_04
INFO   Applied: 140_world_clock_primary_layer
INFO Summary: 1 applied, 0 skipped/failed
INFO qa640_778s1a_04: 137 migration stamps; level 140
after rows:       46
$ cmp before after
cmp: identical (exit 0)
$ dropdb qa640_778s1a_04
```

The listing compared was `SELECT chunk_id, world_layer, time_delta, world_time
FROM chunk_metadata ORDER BY chunk_id`. The same proof also passed at the
pre-rebase head (`cfe930ba` on `9fff6a75`), where the clones went from 138 to
140 with only 140 pending; the row counts and `cmp` results were identical.

## Comments on a Migrated Clone

Rerun at head `a4f64d1c` on `qa640_778s1a_cmt`: `createdb -T template0`,
`pg_restore --exit-on-error --no-owner --no-acl` of a custom-format
`pg_dump` of `save_04` (read-only), then `PYTHONPATH=$PWD $PY
scripts/migrate.py --dbname qa640_778s1a_cmt` (`Applied:
140_world_clock_primary_layer`; `137 migration stamps; level 140`), then
`dropdb`. The listing query, run with `psql -X -A -t -F ' | '`:

```sql
SELECT 'FUNCTION public.refresh_world_time_from_chunk()' AS object,
       obj_description('public.refresh_world_time_from_chunk()'::regprocedure, 'pg_proc') AS comment
UNION ALL
SELECT 'FUNCTION public.refresh_world_time_from_chunk_trigger()',
       obj_description('public.refresh_world_time_from_chunk_trigger()'::regprocedure, 'pg_proc')
UNION ALL
SELECT 'TRIGGER trg_chunk_metadata_refresh_world_time ON public.chunk_metadata',
       obj_description(t.oid, 'pg_trigger')
  FROM pg_trigger t
 WHERE t.tgrelid = 'public.chunk_metadata'::regclass
   AND t.tgname = 'trg_chunk_metadata_refresh_world_time'
UNION ALL
SELECT 'CONSTRAINT chunk_metadata_time_delta_nonnegative ON public.chunk_metadata',
       obj_description(c.oid, 'pg_constraint')
  FROM pg_constraint c
 WHERE c.conrelid = 'public.chunk_metadata'::regclass
   AND c.conname = 'chunk_metadata_time_delta_nonnegative'
UNION ALL
SELECT 'COLUMN public.chunk_metadata.time_delta',
       col_description('public.chunk_metadata'::regclass,
                       (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.chunk_metadata'::regclass AND attname = 'time_delta'))
UNION ALL
SELECT 'COLUMN public.chunk_metadata.world_time',
       col_description('public.chunk_metadata'::regclass,
                       (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.chunk_metadata'::regclass AND attname = 'world_time'))
UNION ALL
SELECT 'VIEW public.narrative_view',
       obj_description('public.narrative_view'::regclass, 'pg_class')
UNION ALL
SELECT 'COLUMN public.narrative_view.world_time',
       col_description('public.narrative_view'::regclass,
                       (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.narrative_view'::regclass AND attname = 'world_time'))
UNION ALL
SELECT 'COLUMN public.orrery_resolutions.tick_chunk_id',
       col_description('public.orrery_resolutions'::regclass,
                       (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.orrery_resolutions'::regclass AND attname = 'tick_chunk_id'))
UNION ALL
SELECT 'COLUMN public.world_events.tick_chunk_id',
       col_description('public.world_events'::regclass,
                       (SELECT attnum FROM pg_attribute WHERE attrelid = 'public.world_events'::regclass AND attname = 'tick_chunk_id'));
```

Raw output (`object | comment`):

```text
FUNCTION public.refresh_world_time_from_chunk() | Recomputes chunk_metadata.world_time for every chunk as global_variables.base_timestamp (now() if absent) plus the running sum, in chunk_id order, of the time_delta of primary-layer chunks (NULL counts as zero), so a chunk of any other layer, or with a NULL world_layer, carries the mainline clock at its position. Raises when the bootstrap chunk (the lowest chunk_id) has a time_delta other than zero or NULL, because base_timestamp is the clock at its end. Writes only rows whose world_time changes; a world_time written by the inserter is overwritten.
FUNCTION public.refresh_world_time_from_chunk_trigger() | Statement trigger function for trg_chunk_metadata_refresh_world_time (AFTER INSERT OR UPDATE OF time_delta, world_layer on chunk_metadata): calls refresh_world_time_from_chunk(); commit_handler_sync reads the resulting trigger-authored world_time after insertion.
TRIGGER trg_chunk_metadata_refresh_world_time ON public.chunk_metadata | Restamps chunk_metadata.world_time through refresh_world_time_from_chunk() after every INSERT statement and every UPDATE statement with time_delta or world_layer in its SET list, even one that inserts or changes no row. A DELETE or TRUNCATE does not fire it.
CONSTRAINT chunk_metadata_time_delta_nonnegative ON public.chunk_metadata | Story time never runs backward within a chunk: time_delta is NULL or at least zero.
COLUMN public.chunk_metadata.time_delta | Story time elapsing during this chunk, NULL or at least zero. Only a primary-layer delta advances the mainline clock, and world_time is that clock at the chunk's end; a delta on any other layer leaves the mainline clock unchanged. The bootstrap chunk (lowest chunk_id) carries zero or NULL, because base_timestamp is the clock at its end.
COLUMN public.chunk_metadata.world_time | The canonical story clock is chunk_metadata.world_time: for a primary-layer chunk, the mainline clock at the end of the chunk; for a chunk of any other layer, the mainline clock at its position. Only primary-layer time_delta advances it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.
VIEW public.narrative_view | The canonical story clock is chunk_metadata.world_time: for a primary-layer chunk, the mainline clock at the end of the chunk; for a chunk of any other layer, the mainline clock at its position. Only primary-layer time_delta advances it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.
COLUMN public.narrative_view.world_time | The canonical story clock is chunk_metadata.world_time: for a primary-layer chunk, the mainline clock at the end of the chunk; for a chunk of any other layer, the mainline clock at its position. Only primary-layer time_delta advances it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.
COLUMN public.orrery_resolutions.tick_chunk_id | Tick chunk under which the resolution was applied. Ticks are the turn clock, which serves ordering, replay, exposure fairness, habituation, and narration cadence; the story time at this tick is chunk_metadata.world_time of this chunk.
COLUMN public.world_events.tick_chunk_id | Tick chunk attributed to the event by its writer. Ticks are the turn clock, which serves ordering, replay, exposure fairness, habituation, and narration cadence; the event's story time is world_events.world_time, and a NULL world_time inherits chunk_metadata.world_time of this chunk.
```

The comparison script, `scratchpad/778-S1a/fix/compare_comments.py`, drops
the `--` header lines of `migrations/140_world_clock_primary_layer.sql`,
parses each `COMMENT ON <target> IS '<literal>';` statement, undoubles `''`,
requires the same ten targets as the listing, and compares the UTF-8 bytes of
each literal with the listed text. Its output:

```text
MATCH FUNCTION public.refresh_world_time_from_chunk()
MATCH FUNCTION public.refresh_world_time_from_chunk_trigger()
MATCH TRIGGER trg_chunk_metadata_refresh_world_time ON public.chunk_metadata
MATCH CONSTRAINT chunk_metadata_time_delta_nonnegative ON public.chunk_metadata
MATCH COLUMN public.chunk_metadata.time_delta
MATCH COLUMN public.chunk_metadata.world_time
MATCH VIEW public.narrative_view
MATCH COLUMN public.narrative_view.world_time
MATCH COLUMN public.orrery_resolutions.tick_chunk_id
MATCH COLUMN public.world_events.tick_chunk_id
```

At the earlier head `c5c593c6`, on `qa640_778s1a_04`, a comparison also
confirmed that each comment text in the work order (items 2.1-2.8) and the
Two Clocks section of `docs/database.md` appear verbatim. Catalog state on
that clone:

```text
CREATE TRIGGER trg_chunk_metadata_refresh_world_time AFTER INSERT OR UPDATE OF time_delta, world_layer ON public.chunk_metadata FOR EACH STATEMENT EXECUTE FUNCTION refresh_world_time_from_chunk_trigger()|O
CHECK ((time_delta >= '00:00:00'::interval))
```

## Item 6: Parentless Openings in Production

No production path commits a non-zero opening delta, so the bootstrap rule
does not fail any production commit today.

- A parentless opening is the incubator with `parent_chunk_id = 0`
  (`nexus/api/narrative.py:991-992`). Its only writer is
  `generate_bootstrap_narrative` (`nexus/api/narrative_generation.py:261-278`),
  which builds `metadata_updates.chronology` itself with
  `time_delta_minutes: 0` (`nexus/api/narrative_generation.py:844-860`); it
  does not take the storyteller's chronology.
- `commit_handler_sync` passes that chronology through `chronology_for_commit`
  (`nexus/api/db_converters.py:74-85`), which keeps the elapsed time and only
  forces `episode_transition = "continue"`, then inserts it through
  `insert_chunk_metadata_sync` (`nexus/api/commit_handler_sync.py:578-590`). A
  save with no Retrograde prologue chunk therefore gets a zero-delta primary
  bootstrap chunk.
- The Retrograde prologue chunk is inserted with `interval '0 seconds'`
  (`nexus/agents/orrery/retrograde_persistence.py:2572-2585`).
- No code path rewrites an incubator's `metadata_updates` after generation:
  the two `UPDATE incubator` sites set choice fields
  (`nexus/api/narrative.py:369-380`) or replace the whole draft from a fresh
  generation (`nexus/api/narrative_generation.py:588-600`).

If a future change lets the storyteller's chronology reach a parentless
opening on a save without a prologue, a non-zero delta will now fail at
commit with `Bootstrap chunk ... must be zero`.

## Changed Tests

Contract-breaking seeds (item 5): each set `base_timestamp` through
`seed_protagonist` and then seeded the first chunk later with
`seed_story_clock`, giving that chunk a non-zero delta. Each now passes the
first story-clock instant as `base_timestamp`.

| File | Old gap | Did an assertion depend on the gap? |
| --- | --- | --- |
| `tests/test_runtime/test_supervisor_live.py` (`supervisor_clone`) | 1 hour | No; no assertion reads the clock. |
| `tests/test_slot_routed_entrypoints.py` (`entrypoint_clone`) | 1 hour | No; no assertion reads the clock. |
| `tests/test_orrery/test_tag_library.py` (namespace-skew test) | 1 day | No; tag expiry compares against the head clock, which is unchanged. |
| `tests/test_orrery/test_epistemics.py` (`STORY_CLOCK`, was `BASE_TIMESTAMP + 12h`) | 12 hours | No; assertions compare with `STORY_CLOCK` (`:152`, `:1259`), unchanged. `BASE_TIMESTAMP` and the `timedelta` import are removed. |
| `tests/test_orrery/test_reveal_live.py` (`STORY_CLOCK`, was `BASE_TIMESTAMP + 6h`) | 6 hours | No; assertions compare with `STORY_CLOCK` (`:490`), unchanged. `BASE_TIMESTAMP` is removed. |
| `tests/test_orrery/checkpointed_story_support.py` (`HEAD_WORLD_TIME`, was `BASE_TIMESTAMP + 24h`) | 24 hours | No; every dependent (`test_replay.py`, `test_reconstruction.py`, `test_build_venture_replay.py`, `test_recruit_ally_replay.py`, `test_pursue_romance_replay.py`, `test_tag_library.py`, `tests/test_pg_disposable_target.py`) passes unchanged. `BASE_TIMESTAMP` is removed and the docstring now says `base_timestamp` is the head clock. |

Other changes:

- `tests/test_lore/test_character_dossier_tags_pg.py`: the bootstrap row is
  `(chunk_id, world_layer, time_delta) VALUES (1, 'primary', interval '0')`
  (was `(1, interval '1 hour')` with a NULL layer). Its assertions read
  `max(world_time)` and pass unchanged.
- `tests/test_idf_dictionary_pg.py::test_source_lock_precedes_world_time_refresh`
  (further gate failure): the test bumped `time_delta` on the first chunk of
  the save, which is now the refused bootstrap case
  (`RaiseException: Bootstrap chunk 1 has time_delta 00:00:01`). A zero-delta
  bootstrap chunk is seeded first, so the edited clock source is a later
  primary chunk; its +1 second still moves the next chunk's clock, so the
  refresh still rewrites the row the waiter holds and the lock-order case is
  still exercised.
- `tests/pg_fixtures.py`: `seed_committed_chunk(time_delta=None)` (zero for
  the first chunk of a save, one minute otherwise), primary-only head-clock
  sums in `_require_need_clock_anchor` and `seed_story_clock`, the
  `seed_story_clock` bootstrap assertion, and the docstring and message prose.
- `tests/test_world_clock_contract_pg.py`: the pin becomes `(0, 7, 7, 7)`;
  new tests `test_world_layer_edit_restamps_clock`,
  `test_negative_time_delta_rejected`, `test_bootstrap_delta_must_be_zero`,
  `test_refresh_writes_only_changed_rows`,
  `test_seed_committed_chunk_bootstrap_elapses_no_time`, and
  `test_migration_140_refuses_bad_clocks`.

Without migration 140 on disk (file moved aside, clone built at 139), six of
the seven contract tests fail; `test_seed_committed_chunk_bootstrap_elapses_no_time`
passes there because it checks the fixture default, which only the
migration's bootstrap rule makes necessary. Rerun at head `2f30518a` with
`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and `NEXUS_SLOT` unset:
`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit
tests/test_world_clock_contract_pg.py`, the migration file restored right
after (`git status` clean). Log: `778-S1a/fix2/without_140.log` in the session
scratchpad. Raw tail:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 8 targets: postgres, qa640_clock_* x7
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
FAILED tests/test_world_clock_contract_pg.py::test_world_clock_identity_and_face
FAILED tests/test_world_clock_contract_pg.py::test_world_layer_edit_restamps_clock
FAILED tests/test_world_clock_contract_pg.py::test_negative_time_delta_rejected
FAILED tests/test_world_clock_contract_pg.py::test_bootstrap_delta_must_be_zero
FAILED tests/test_world_clock_contract_pg.py::test_refresh_writes_only_changed_rows
FAILED tests/test_world_clock_contract_pg.py::test_migration_140_refuses_bad_clocks
6 failed, 1 passed in 8.63s
```

## Tails

All PostgreSQL runs used `NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p
tests.dbname_audit ...` with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` unset.

### Named Proof Set (Head `c5c593c6`)

This run predates `a4f64d1c`, which changes comments only and is covered by
the rerun under Review Fixes (Head `a4f64d1c`); the whole set reran at
`2f30518a` under Review Fixes (Head `2f30518a`).

Files: `tests/test_world_clock_contract_pg.py tests/test_orrery/test_migrate.py
tests/test_schema_documentation_pg.py tests/test_new_story_setup.py
tests/test_pg_accepted_turn_factory.py tests/test_pg_disposable_target.py
tests/test_owner_target_guard.py tests/test_runtime/test_supervisor_live.py
tests/test_slot_routed_entrypoints.py tests/test_orrery/test_tag_library.py
tests/test_orrery/test_epistemics.py tests/test_orrery/test_reveal_live.py
tests/test_lore/test_character_dossier_tags_pg.py tests/test_orrery/test_replay.py
tests/test_orrery/test_reconstruction.py tests/test_orrery/test_build_venture_replay.py
tests/test_orrery/test_recruit_ally_replay.py tests/test_orrery/test_pursue_romance_replay.py
tests/test_idf_dictionary_pg.py tests/test_character_relationship_id_types_pg.py
tests/test_new_story_setup_config.py tests/test_migration_comment_lint.py`

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 86 targets: ... qa640_clock_* x7, ...
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
466 passed, 7 warnings in 203.83s (0:03:23)
```

`PYTHONPATH=$PWD $PY scripts/check_migration_comments.py`:

```text
OK: every object created after migration 129 has a comment.
```

### Whole PostgreSQL Gate (Pre-Rebase Head on `9fff6a75`)

The gate was split by directory to stay under the ten-minute command limit.
At that base 139 was not on `main`, so its gap failure was expected.

`tests/test_lore tests/test_runtime tests/test_config tests/config tests/test_ir_eval_v2 tests/test_memnon tests/test_util`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
866 passed, 3 skipped, 9 warnings in 212.91s (0:03:32)
```

Top-level `tests/*.py` (`tests --ignore=` every subdirectory). The two
failures, by their failure-section headers in the raw log, were
`tests/test_dbname_audit.py::test_owner_session_starts_no_owner_backend` and
`tests/test_idf_dictionary_pg.py::test_source_lock_precedes_world_time_refresh`.
Raw tail (`pg_toplevel.log`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: <N> targets: ... (target list elided here; full line in the raw log)
dbname audit: owner server: local:5432
dbname audit: registered disposable clusters: two_clusters[0] at local:57345 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[1] at local:57351 from tests/test_connection_lifecycle.py::test_connection_two_clusters_story_lifecycle; two_clusters[0] at local:57817 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[1] at local:57823 from tests/test_database_contract.py::test_connection_raw_url_and_asyncpg_session_policy; two_clusters[0] at local:57842 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard; two_clusters[1] at local:57847 from tests/test_database_contract.py::test_connection_two_clusters_pool_url_async_timezone_and_guard
dbname audit: owner names admitted on registered clusters: save_04@local:57345 (psycopg2), save_04@local:57351 (psycopg2)
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [1] tests/live_seed_schema_test.py:24: Set NEXUS_RUN_LIVE_LLM=1 to run live seed schema tests.
SKIPPED [1] tests/live_set_designer_test.py:38: Set NEXUS_RUN_LIVE_LLM=1 to run live set designer tests.
SKIPPED [1] tests/test_correspondence_live.py: Set NEXUS_CONSPIRACY_E2E=1 for the live correspondence gate.
SKIPPED [8] tests/test_golden_path_live.py: Set NEXUS_GOLDEN_PATH_E2E=1 to run the expensive golden-path gate.
SKIPPED [1] tests/test_issue_601_wizard_live.py:125: Set NEXUS_ISSUE_601_LIVE=1 to run the live trait-confirmation proof.
SKIPPED [1] tests/test_local_skald_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_memnon_cross_encoder_dependencies.py:28: Local DeBERTa cross-encoder model is not available
SKIPPED [3] tests/test_model_registry_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [2] tests/test_new_story_integration.py:21: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [2] tests/test_new_story_schemas.py:756: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [2] tests/test_new_story_schemas.py:775: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [2] tests/test_secret_store_integration.py: Set NEXUS_RUN_SECRET_STORE=1 to run disposable platform secret-store integration tests.
SKIPPED [1] tests/test_skald_wire.py:2110: Set NEXUS_639_PRESENCE_E2E=1 for the live writer presence gate.
SKIPPED [8] tests/test_wizard_live.py:244: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [5] tests/test_wizard_live.py:294: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_wizard_live.py:433: Set NEXUS_ISSUE_600_LIVE=1 to run the live seed-repair proof.
2 failed, 2168 passed, 40 skipped, 10 warnings in 783.40s (0:13:03)
```

The 40 skips are live-LLM, live-E2E, secret-store, and local cross-encoder
opt-ins. `test_source_lock_precedes_world_time_refresh` is the bootstrap
case fixed above; the file rerun after the fix (`idf.log`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: <N> targets: ... (target list elided here; full line in the raw log)
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
19 passed in 27.37s
```

`test_owner_session_starts_no_owner_backend` failed because the
`NEXUS_template` session counter moved in every bracket (other builders on
this machine clone the template concurrently). The file rerun once:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
24 passed in 7.71s
```

`tests/test_api`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: owner targets: none
874 passed, 4 skipped, 9 warnings in 455.17s (0:07:35)
```

`tests/test_orrery`, in three alphabetical parts of 45, 45 and 44 files.
Part one (`pg_orrery_aa.log`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: <N> targets: ... (target list elided here; full line in the raw log)
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [2] tests/test_orrery/test_card_identity.py:121: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [18] tests/test_orrery/test_claim_propagation_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_claim_propagation_live.py:1075: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py:546: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
553 passed, 29 skipped, 2 warnings in 111.47s (0:01:51)
```

Part two (`pg_orrery_ab.log`). Its one failure was
`tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps`
(`AssertionError: assert {'013', '119', '139'} == frozenset({'013', '119'})`:
139 missing, expected at that base):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: <N> targets: ... (target list elided here; full line in the raw log)
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [1] tests/test_orrery/test_gaia_registry_schema_pg.py:347: Set NEXUS_638_ENUM_E2E=1 for the live Gaia enum-schema gate.
SKIPPED [1] tests/test_orrery/test_live_cycle.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_projects.py:609: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_orrery/test_recruit_ally_projects.py:808: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
1 failed, 421 passed, 4 skipped, 2 warnings in 106.88s (0:01:46)
```

Part three (`pg_orrery_ac.log`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: <N> targets: ... (target list elided here; full line in the raw log)
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [1] tests/test_orrery/test_retrograde_live.py:29: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_retrograde_maturation_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_retrograde_retrieval_live.py: NEXUS_RETROGRADE_RETRIEVAL_TEST_DB_URL is not configured
SKIPPED [1] tests/test_orrery/test_retrograde_wizard_live.py: Set NEXUS_RETROGRADE_WIZARD_E2E=1 to run the live cold-start proof.
SKIPPED [5] tests/test_orrery/test_stage2a_status_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
667 passed, 9 skipped in 71.86s (0:01:11)
```

### Offline Suites (Head `c5c593c6`)

The two suite runs below ran at `c5c593c6`. The `tests/test_reachability.py`
tail was logged seconds before the rebase that produced `c5c593c6`; the rerun
at `2f30518a` under Review Fixes (Head `2f30518a`) replaces it as evidence.

`$PY -m pytest -q tests/test_api tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1820 passed, 743 skipped, 7 warnings in 35.53s
```

`$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_cli_generation_http.py::test_cli_prints_each_genesis_stage_once_while_transition_runs[seed-confirm]
1 failed, 2666 passed, 434 skipped, 8 warnings in 391.49s (0:06:31)
```

That test asserts `scenario.snapshot_reads == 1` against an in-process fake
HTTP server and read 2 (a polling race); it touches no database and no file
this branch changes, and it passed in both earlier offline runs. The file
rerun once:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 94.18s (0:01:34)
```

`$PY -m pytest -q tests/test_reachability.py`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 9.52s
```

### Review Fixes (Head `a4f64d1c`)

`a4f64d1c` changes comments only: the lock paragraph of
`migrations/140_world_clock_primary_layer.sql` (DROP TRIGGER takes ACCESS
EXCLUSIVE, CREATE TRIGGER takes SHARE ROW EXCLUSIVE) and the lock-order
comment in `tests/test_idf_dictionary_pg.py::test_source_lock_precedes_world_time_refresh`.
The raw logs above are in the session scratchpad under `778-S1a/`; the
rerun log is `778-S1a/fix/fix_pg.log`. Covering PostgreSQL rerun:
`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit
tests/test_idf_dictionary_pg.py tests/test_world_clock_contract_pg.py
tests/test_orrery/test_migrate.py tests/test_schema_documentation_pg.py
tests/test_migration_comment_lint.py` (139 is on `main` at this base, so
`test_migration_sequence_has_only_known_gaps` passes):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 41 targets: postgres, qa640_clock_* x7, qa640_docs_refresh_*, qa640_grieving_migration_*, qa640_schema_docs_* x3, qa640_vocab_migration_* x6, qa762_corpus_copy_*, qa762_fresh_*, qa762_idf_* x19, qa762_other_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
177 passed in 48.95s
```

`PYTHONPATH=$PWD $PY scripts/check_migration_comments.py`: `OK: every object
created after migration 129 has a comment.` `black --check
tests/test_idf_dictionary_pg.py`: `1 file would be left unchanged.`
`flake8 tests/test_idf_dictionary_pg.py`: 7 findings, the same 7 E501 as
`main`.

### Review Fixes (Head `2f30518a`)

`2f30518a` rewraps two docstrings in `tests/pg_fixtures.py`
(`_require_need_clock_anchor` and `seed_story_clock`); the words are
unchanged. Logs are under `778-S1a/fix2/` in the session scratchpad. The
named proof set reran in full (same files and command as the Head
`c5c593c6` run above; `named.log`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 86 targets: ... qa640_clock_* x7, ...
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
466 passed, 7 warnings in 190.84s (0:03:10)
```

`$PY -m pytest -q tests/test_api tests/test_orrery` (`offline_b.log`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1820 passed, 743 skipped, 7 warnings in 31.64s
```

`$PY -m pytest -q tests/test_reachability.py` (`reach.log`):

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
54 passed, 5 warnings in 10.10s
```

`PYTHONPATH=$PWD $PY scripts/check_migration_comments.py`: `OK: every object
created after migration 129 has a comment.` `black --check
tests/pg_fixtures.py`: `1 file would be left unchanged.` `flake8
tests/pg_fixtures.py`: no output.

### Black, flake8, mypy (Changed Python Files)

`black --check` over the ten changed files: `10 files would be left
unchanged.` `flake8`, findings per file on `main` and on this branch (all
E501; no other code):

```text
tests/pg_fixtures.py                              main 0  branch 0
tests/test_idf_dictionary_pg.py                   main 7  branch 7
tests/test_lore/test_character_dossier_tags_pg.py main 15 branch 14
tests/test_orrery/checkpointed_story_support.py   main 0  branch 0
tests/test_orrery/test_epistemics.py              main 0  branch 0
tests/test_orrery/test_reveal_live.py             main 0  branch 0
tests/test_orrery/test_tag_library.py             main 0  branch 0
tests/test_runtime/test_supervisor_live.py        main 0  branch 0
tests/test_slot_routed_entrypoints.py             main 0  branch 0
tests/test_world_clock_contract_pg.py             main 2  branch 2
```

`mypy --explicit-package-bases` over the same files reports 11 errors, all
present on `main`: nine in `tests/test_idf_dictionary_pg.py` (Optional
arithmetic and indexing; the `main` copy alone reports the same nine), the
`seat` literal at `tests/test_lore/test_character_dossier_tags_pg.py:330`, and
the `intertitle["world_time"]` index on an optional dict in
`tests/test_world_clock_contract_pg.py` (the pre-existing identity test).
