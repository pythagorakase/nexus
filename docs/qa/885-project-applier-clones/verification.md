# Project-Applier Tests Leave save_02: Verification

Work order 885-B2-3. Issue #885 (comment "Slice B2 Mapped: Nine Ordered Slices", slice B2-3). Base: `origin/main` at `ae2e29bc`. Test-only: no migration, no gateway lane, no paid calls. Every PostgreSQL run below had `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset.

## What Was Wrong

The court_patron, pursue_romance, seek_redemption, and build_venture applier tests built shadow copies of `event_types`, `orrery_resolutions`, and `character_project_states` in a per-test schema, but connected to the owner's `save_02`. Through `search_path` fall-through (`"<shadow>", public`) they read `save_02`'s first two characters by id and its latest clocked chunk, and several wrote public tables before the rollback. Sequences advanced through the rollback, and the owner protagonist's relationship row was deleted and row-locked for the length of each test.

| Module | Owner target (on `ae2e29bc`) | Public `save_02` writes before rollback |
| --- | --- | --- |
| `test_court_patron_projects.py` (+ `test_court_patron_replay.py` through `pytest_plugins`) | `psycopg2.connect(get_slot_db_url(slot=2))` at :436 | DELETE (:450-456) and INSERT (:578-586) on `character_relationships`; `relationship_versions` (migration 115 trigger); `entity_pair_tags` (`sponsors`, `obligation`); the replay adds `narrative_chunks`, `chunk_metadata`, `orrery_resolutions`, `state_checkpoints` |
| `test_court_patron_async.py` | `asyncpg_kwargs("save_02")` at :102 | DELETE on `character_relationships` (:119-126) and the patron upsert; `relationship_versions`; `entity_pair_tags` |
| `test_pursue_romance_projects.py` | `get_slot_db_url(slot=2)` at :348 | DELETE on `character_relationships` (:362-368) and upserts; `relationship_versions`; `entity_pair_tags` (`contact:intimate`, three attempts) |
| `test_pursue_romance_async.py` | `asyncpg_kwargs("save_02")` at :89 | DELETE (:106-113) and the romantic upsert; `relationship_versions`; `entity_pair_tags` |
| `test_seek_redemption_projects.py` (+ `test_seek_redemption_replay.py` through `pytest_plugins`) | `get_slot_db_url(slot=2)` at :365 | DELETE (:380) and INSERT `enemy` (:510) on `character_relationships`; `relationship_versions`; `relationship_milestone_queue`; `entity_tags` (grudge clear :387, INSERT :520); `tag_clearance_log`; the replay adds `narrative_chunks`, `chunk_metadata`, `orrery_resolutions`, `state_checkpoints` |
| `test_seek_redemption_async.py` | `asyncpg_kwargs("save_02")` at :105 | DELETE (:122) and INSERT `enemy` (:130); `relationship_versions`; `relationship_milestone_queue`; `entity_tags` (:140, :146); `tag_clearance_log` |
| `test_build_venture_projects.py` | `get_slot_db_url(slot=2)` at :272 | reads only (`characters`, `chunk_metadata` at :277-286); applier writes land in the shadow tables |
| `test_build_venture_async.py` | `asyncpg_kwargs("save_02")` at :108 | reads only (:113-124) |
| `test_build_venture_replay.py` | `get_slot_db_url(slot=2)` at :113 | its schema is empty, so migration 084 ran against public `character_project_states` (constraint DDL), `event_types`, `tag_category_registry`, `tags`; `narrative_chunks` with an explicit `max(id) + 1` id (:131-139); `chunk_metadata`; `orrery_resolutions`; `state_checkpoints` |

Per-module file:line detail is in `temp/orders_2026_09_29/b2_map.json` in the coordinator's tree.

## What Changed

- `tests/pg_fixtures.py`: `seed_character_pair(dbname, *, world_time, actor_name, target_name) -> CharacterPairSeed(actor_entity_id, target_entity_id, actor_character_id, target_character_id, chunk_id, world_time)`. It calls `require_disposable_target` first, then `seed_story_clock` (the need-clock anchor), then `seed_character` twice, reads the rows back, and asserts two active character entities and one chunk clocked at `world_time`. A second call on the same save takes the next scene of season 1, episode 1, so the chunk slug stays unique; `seed_story_clock` still refuses a clock earlier than the head.
- `tests/test_pg_character_pair_seed.py` (new): two PostgreSQL tests on clones. They check the anchor, the chunk clock, the character and entity rows, the need rows, the absence of relationships, a distinct second pair, and the backward-clock refusal. `tests/test_pg_disposable_target.py`: `seed_character_pair` joins `SEED_CALLS`, so its owner-database refusal is proven before any connection.
- Each of the nine modules: a module-scoped `disposable_slot_database("qa885_<module>")` fixture seeds the pair through `seed_character_pair` and yields the IDs. Synchronous tests connect with `tests.pg_fixtures.connect(dbname)`. Async tests connect with `tests.pg_fixtures.asyncpg_kwargs(dbname)` and take the synchronous fixture, so seeding never runs inside the event loop. The shadow schemas and each test's rollback are unchanged. The fixture names (`live_patron_db`, `live_romance_db`, `live_redemption_db`, `live_venture_db`, `replay_db`) and their dict keys are unchanged. The owner-cleanup `DELETE`/grudge-clear statements are gone, because a fresh clone has nothing to clean.
- Pre-existing relationships: the court_patron `mentor` row and the seek_redemption `enemy` rows are now committed through `seed_relationship` on a second seeded pair (`live_mentored_patron_db`, `live_estranged_redemption_db`, and the async module's clone). The first pair stays relationship-free, whatever order the tests run in.
- `test_build_venture_replay.py`: `_chunk` takes its id from the sequence (`INSERT ... RETURNING id`) and keeps its `chunk_metadata` insert. `base_time` is still `max(world_time)`, and it is asserted equal to the seeded clock. It does not use `seed_checkpointed_story`.

## Audit Grep

```
$ for f in tests/test_orrery/test_{court_patron_projects,court_patron_replay,court_patron_async,pursue_romance_projects,pursue_romance_async,seek_redemption_projects,seek_redemption_replay,seek_redemption_async,build_venture_projects,build_venture_async,build_venture_replay}.py; do grep -n "save_0\|NEXUS_template\|get_slot_db_url(slot=\|slot_dbname([1-5])\|LIVE_SLOT" $f; done; echo audit-done
audit-done
```

No test id or message in these files named `slot2` or `save_02`, so nothing was renamed.

## Sequence Proof on save_02 (Read-Only)

`snap.sql`, run with `psql -X -d save_02` inside `BEGIN READ ONLY`:

```sql
SELECT schemaname, sequencename, last_value FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename;
SELECT 'character_relationships' AS t, count(*) FROM character_relationships
UNION ALL SELECT 'relationship_versions', count(*) FROM relationship_versions
UNION ALL SELECT 'entity_pair_tags', count(*) FROM entity_pair_tags
UNION ALL SELECT 'entity_tags', count(*) FROM entity_tags
UNION ALL SELECT 'tag_clearance_log', count(*) FROM tag_clearance_log
UNION ALL SELECT 'relationship_milestone_queue', count(*) FROM relationship_milestone_queue;
```

Taken at `2026-09-30T03:18:53Z` (before) and `2026-09-30T03:19:11Z` (after), around the slice gate below. `diff` of the two bodies prints nothing: identical.

```
 schemaname |               sequencename                | last_value 
------------+-------------------------------------------+------------
 public     | ai_notebook_id_seq                        |           
 public     | backstory_secrets_id_seq                  |           
 public     | character_experience_jobs_id_seq          |           
 public     | character_experiences_id_seq              |           
 public     | character_identity_rulings_id_seq         |           
 public     | character_project_states_id_seq           |       3394
 public     | character_relationships_id_seq            |          7
 public     | character_routine_anchors_id_seq          |           
 public     | characters_id_seq                         |        101
 public     | chunk_metadata_id_seq                     |       8607
 public     | claim_awareness_id_seq                    |       1044
 public     | claims_id_seq                             |        475
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |        561
 public     | entity_pair_tags_id_seq                   |       3490
 public     | entity_tags_id_seq                        |       1139
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |          1
 public     | narrative_chunks_id_seq                   |       2620
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |        540
 public     | orrery_maturation_jobs_id_seq             |        504
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |       3153
 public     | orrery_recall_trace_id_seq                |           
 public     | orrery_resolutions_id_seq                 |       7204
 public     | orrery_route_graph_edges_id_seq           |           
 public     | orrery_route_graph_nodes_id_seq           |           
 public     | orrery_scene_pressures_id_seq             |        540
 public     | orrery_travel_edges_id_seq                |           
 public     | pair_tags_id_seq                          |         29
 public     | places_id_seq                             |          4
 public     | relationship_versions_id_seq              |     100089
 public     | retrieval_coverage_log_id_seq             |         52
 public     | retrograde_summaries_id_seq               |       1435
 public     | state_checkpoints_id_seq                  |       2953
 public     | state_delta_log_id_seq                    |         33
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |       1056
 public     | tags_id_seq                               |        556
 public     | world_events_id_seq                       |       8110
 public     | zones_id_seq                              |          1
(48 rows)

              t               | count 
------------------------------+-------
 character_relationships      |    84
 relationship_versions        |    84
 entity_pair_tags             |     0
 entity_tags                  |     0
 tag_clearance_log            |     0
 relationship_milestone_queue |     0
(6 rows)

```

Other sessions' concurrent runs of unconverted modules still write `save_02`. A snapshot taken at 03:04Z, before this branch ran any PostgreSQL test, read `relationship_versions_id_seq` 100056 and `entity_pair_tags_id_seq` 3475; by 03:18Z they read 100089 and 3490. In that window this branch ran only its converted modules, which the audited gate below shows open no owner database. A before/after pair is therefore evidence only for a window that no other session wrote in, as this one was. For proof that does not depend on concurrency, the slice gate also ran with a pytest plugin that wraps `psycopg2.connect` and `asyncpg.connect` and records every database name the process opens (`dbname-audit` lines below). It opened `postgres` (the clone admin connection) and `qa885_*` clones only; no owner database. Clone creation also runs `pg_dump -s` against `NEXUS_template` in a subprocess, which is read-only.

## Slice Gate

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=<scratch> $PY -m pytest -q -p dbname_audit \
    tests/test_orrery/test_court_patron_projects.py tests/test_orrery/test_court_patron_replay.py \
    tests/test_orrery/test_court_patron_async.py tests/test_orrery/test_pursue_romance_projects.py \
    tests/test_orrery/test_pursue_romance_async.py tests/test_orrery/test_seek_redemption_projects.py \
    tests/test_orrery/test_seek_redemption_replay.py tests/test_orrery/test_seek_redemption_async.py \
    tests/test_orrery/test_build_venture_projects.py tests/test_orrery/test_build_venture_async.py \
    tests/test_orrery/test_build_venture_replay.py tests/test_pg_disposable_target.py \
    tests/test_pg_character_pair_seed.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname-audit: postgres, qa885_build_venture_2f10d388db03, qa885_build_venture_async_452deaa4e9da, qa885_build_venture_replay_37185028cbb7, qa885_character_pair_5bee3dec709b, qa885_character_pair_ec765b98ec11, qa885_court_patron_062ca319223d, qa885_court_patron_async_3c4d4f5fa0b7, qa885_court_patron_daf9915bd905, qa885_pursue_romance_24df10f133ff, qa885_pursue_romance_async_acf4ac46279b, qa885_seek_redemption_4a406d4d5d87, qa885_seek_redemption_async_f68f74847dd8, qa885_seek_redemption_cdf8c82af736
dbname-audit owner targets: []
112 passed, 5 warnings in 17.35s
```

The `dbname_audit` plugin (scratch file, not committed):

```python
"""Record every PostgreSQL database this pytest process connects to."""

from __future__ import annotations

import functools

SEEN: set[str] = set()


def _record(kwargs: dict, args: tuple) -> None:
    name = kwargs.get("dbname") or kwargs.get("database")
    if name is None and args:
        name = f"dsn:{args[0]}"
    SEEN.add(str(name))


def pytest_configure(config):  # noqa: D103
    import asyncpg
    import psycopg2

    original_pg = psycopg2.connect

    @functools.wraps(original_pg)
    def pg_connect(*args, **kwargs):
        _record(kwargs, args)
        return original_pg(*args, **kwargs)

    psycopg2.connect = pg_connect

    original_async = asyncpg.connect

    @functools.wraps(original_async)
    async def async_connect(*args, **kwargs):
        _record(kwargs, args)
        return await original_async(*args, **kwargs)

    asyncpg.connect = async_connect


def pytest_terminal_summary(terminalreporter):  # noqa: D103
    names = sorted(SEEN)
    terminalreporter.write_line("dbname-audit: " + ", ".join(names))
    owners = [n for n in names if n.startswith("save_") or n == "NEXUS_template"]
    terminalreporter.write_line(f"dbname-audit owner targets: {owners}")
```

## Orrery PostgreSQL Tier

Split in two for the ten-minute shell limit.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfE tests/test_orrery/test_[a-o]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings
2 failed, 796 passed, 29 skipped, 7 warnings, 8 errors in 163.11s (0:02:43)

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfE tests/test_orrery/test_[p-z]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_reveal_live.py::test_authoring_rejects_non_private_and_unregistered_gate
FAILED tests/test_orrery/test_reveal_live.py::test_authoring_grants_unpossessed_holder_and_reveal_completes
FAILED tests/test_orrery/test_reveal_live.py::test_async_authoring_grants_unpossessed_holder
FAILED tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop
FAILED tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate
FAILED tests/test_orrery/test_reveal_live.py::test_unregistered_gate_in_latent_row_raises_loudly
FAILED tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[retrograde-settings0]
FAILED tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[primary-settings1]
FAILED tests/test_orrery/test_reveal_live.py::test_authored_and_revealed_secrets_replay_between_checkpoints
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
10 failed, 811 passed, 10 skipped, 7 warnings, 1 error in 125.56s (0:02:05)
```

Every remaining failure is an owner-content assumption on the empty `save_05` (or the audited-slot probe), which #885 already lists as the Orrery tier's remaining set after PR #1019. Each belongs to a later B2 slice. None is new, and none is in this slice's files.

| Failure | Count | Cause | Slice |
| --- | ---: | --- | --- |
| `test_reveal_live` | 9 | `TypeError: 'NoneType' object is not subscriptable` or `assert None is not None` on the empty `save_05` | B2-2 |
| `test_faction_project_contexts_live` | 8 | setup `sqlalchemy.exc.NoResultFound` on the empty `save_05` | B2-4 |
| `test_polymorphic_patron_live` | 1 | setup `sqlalchemy.exc.NoResultFound` on the empty `save_05` | B2-4 |
| `test_adjudication_history::test_history_is_non_vacuous_on_audited_slots` | 1 | no audited slot has adjudication-log rows | B2-5 (cannot be made honest as written) |
| `test_evidence::test_slot_backed_explain_carries_evidence_end_to_end` | 1 | `save_05 is expected to bind off-screen actors` | B2-7 |
| `test_tag_library::test_contextual_library_save_05_completeness_and_size` | 1 | `save_05 must contain current entity tags` | B2-7 |

## Offline Gates

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2442 passed, 357 skipped, 8 warnings in 351.58s (0:05:51)

$ $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1807 passed, 729 skipped, 7 warnings in 31.78s

$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.55s
```

Black and flake8 are clean on every changed file. `mypy --explicit-package-bases` on the changed files reports only errors on lines this branch does not touch (the pure `WorldState(**dict)` calls in `test_seek_redemption_projects.py`, `_apply`'s `object` argument in `test_build_venture_replay.py`, and the missing `asyncpg` stubs); `git blame` puts each on a commit already on `main`.

## #885 Ids Retired (15)

- `tests/test_orrery/test_court_patron_projects.py::test_completion_applies_inbound_outbound_and_patron_relationship`
- `tests/test_orrery/test_court_patron_projects.py::test_completion_preserves_existing_relationship_valence`
- `tests/test_orrery/test_court_patron_replay.py::test_court_patron_completion_replays_without_drift`
- `tests/test_orrery/test_court_patron_async.py::test_async_court_patron_three_write_completion`
- `tests/test_orrery/test_pursue_romance_projects.py::test_sync_applier_fresh_romance_and_overwrite_preserve_first_provenance`
- `tests/test_orrery/test_pursue_romance_async.py::test_async_pursue_romance_start_and_completion`
- `tests/test_orrery/test_seek_redemption_projects.py::test_fresh_completion_inserts_reconciliation_and_absent_grudge_is_noop`
- `tests/test_orrery/test_seek_redemption_projects.py::test_existing_negative_relationship_is_repaired_and_originals_survive_rewrite`
- `tests/test_orrery/test_seek_redemption_replay.py::test_seek_redemption_completion_replays_without_drift`
- `tests/test_orrery/test_seek_redemption_async.py::test_async_seek_redemption_three_write_completion`
- `tests/test_orrery/test_build_venture_projects.py::test_live_applier_runs_start_progress_milestones_and_completion`
- `tests/test_orrery/test_build_venture_projects.py::test_live_stall_abandon_and_budget_interaction`
- `tests/test_orrery/test_build_venture_projects.py::test_live_start_rejects_every_target_column`
- `tests/test_orrery/test_build_venture_async.py::test_async_build_venture_start_and_completion_match_sync`
- `tests/test_orrery/test_build_venture_replay.py::test_build_venture_replays_applied_snapshots_through_completion`

## Deferred

- `_fabricate_chunk` in `tests/test_orrery/test_pursue_romance_replay.py` (B2-4 scope) still assigns `max(id) + 1`. The two coupled replay modules here import it and pass on the clone, because `seed_character_pair` guarantees a chunk. The sequence-assigned rewrite belongs to B2-4 with the file.
