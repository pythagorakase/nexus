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

Read from `qa640_778s1a_04` after migration with `obj_description` (function,
trigger, constraint, view) and `col_description` (columns). A script parsed
each `COMMENT ON ... IS '...'` literal from
`migrations/140_world_clock_primary_layer.sql`, undoubled `''`, and compared it
with the live text:

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

The same script confirmed that each comment text in the work order (items
2.1-2.8) and the Two Clocks section of `docs/database.md` appear verbatim.
Catalog state on the clone:

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

Without migration 140 on disk (file moved aside, clone built at 138), six of
the seven contract tests fail; `test_seed_committed_chunk_bootstrap_elapses_no_time`
passes there because it checks the fixture default, which only the
migration's bootstrap rule makes necessary:

```text
FAILED tests/test_world_clock_contract_pg.py::test_world_clock_identity_and_face
FAILED tests/test_world_clock_contract_pg.py::test_world_layer_edit_restamps_clock
FAILED tests/test_world_clock_contract_pg.py::test_negative_time_delta_rejected
FAILED tests/test_world_clock_contract_pg.py::test_bootstrap_delta_must_be_zero
FAILED tests/test_world_clock_contract_pg.py::test_refresh_writes_only_changed_rows
FAILED tests/test_world_clock_contract_pg.py::test_migration_140_refuses_bad_clocks
6 failed, 1 passed in 8.77s
```

## Tails

All PostgreSQL runs used `NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p
tests.dbname_audit ...` with `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL` and
`NEXUS_SLOT` unset.

### Named Proof Set (Final Head `c5c593c6`)

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

Top-level `tests/*.py` (`tests --ignore=` every subdirectory):

```text
FAILED tests/test_dbname_audit.py::test_owner_session_starts_no_owner_backend
FAILED tests/test_idf_dictionary_pg.py::test_source_lock_precedes_world_time_refresh
2 failed, 2168 passed, 40 skipped, 10 warnings in 783.40s (0:13:03)
```

The 40 skips are live-LLM, live-E2E, secret-store, and local cross-encoder
opt-ins. `test_source_lock_precedes_world_time_refresh` is the bootstrap
case fixed above; the file rerun after the fix:

```text
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

`tests/test_orrery`, in three alphabetical parts of 45, 45 and 44 files:

```text
553 passed, 29 skipped, 2 warnings in 111.47s (0:01:51)
FAILED tests/test_orrery/test_migrate.py::test_migration_sequence_has_only_known_gaps   (139 missing; expected at that base)
1 failed, 421 passed, 4 skipped, 2 warnings in 106.88s (0:01:46)
667 passed, 9 skipped in 71.86s (0:01:11)
```

Each part printed `secret-store guard: active; nexus-api: denied` and
`dbname audit: owner targets: none`.

### Offline Suites (Final Head)

`$PY -m pytest -q tests/test_api tests/test_orrery`:

```text
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1820 passed, 743 skipped, 7 warnings in 35.53s
```

`$PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`:

```text
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
54 passed, 5 warnings in 9.52s
```

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
