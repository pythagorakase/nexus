# #885 Slice B2-4: Checkpoint-Replay and Resolver-Composition Fixtures Leave the Owner Slots

Branch `claude/885-composition-clones`, rebased onto `origin/main` at `0b21163d` (B2-3, #1036). Test-only; no migration; no paid call (TEST provider only; every clone is TEST-pinned); no gateway lane. `$PY` is `/Users/pythagor/nexus/.venv/bin/python`, run from the worktree root, whose `nexus` import resolves inside the worktree.

## What Was Wrong

Line numbers are at `ae2e29bc`, where this slice was cut; B2-3 did not touch these seven files.

| Module | Owner access | Owner content it took | State on main |
| --- | --- | --- | --- |
| `test_faction_project_contexts_live` | `create_engine(get_slot_db_url(slot=LIVE_SLOT))` (:154), `LIVE_SLOT = 5` | first place (:168 `scalar_one`), `max(id)` chunk (:172), first two factions or `pytest.skip` (:190) | all 8 ids ERROR in setup on the empty `save_05` (`NoResultFound`) |
| `test_polymorphic_patron_live` | `create_engine(get_slot_db_url(slot=5))` (:44) | first place (:73), latest clocked chunk; raw `character_relationships` INSERT (:109) with no `nexus.write_producer` | ERROR in setup on `save_05`; the INSERT raises `Missing or invalid nexus.write_producer` on any slot (`migrations/115_relationship_write_provenance.sql:61-65`) |
| `test_composition_sources_live` (live_llm) | `LIVE_SLOT = 5` (:46) | first place (:147), empty place or skip (:456), two places or skip (:585), `max(id)` tick chunk | every test ERRORs in setup under `NEXUS_RUN_LIVE_LLM=1` |
| `test_recruit_ally_projects` | `psycopg2.connect(get_slot_db_url(slot=2))` (:302), `create_engine(get_slot_db_url(slot=2))` (:782) | three lowest characters or skip (:314), `max(id)` chunk, first place; the coverage test asserts `save_02`'s played statistics and skipped without an off-screen target (:868) | passes only because `save_02` is populated |
| `test_projects` | `psycopg2.connect(get_slot_db_url(slot=2))` (:530), `create_engine(get_slot_db_url(slot=2))` (:583) | `max(id)` chunk and lowest character; coverage test asserts `save_02`'s played statistics and re-runs migration 074 (:589), rewriting head comments to V1 text | passes only because `save_02` is populated |
| `test_recruit_ally_replay` | `psycopg2.connect(get_slot_db_url(slot=2))` (:43) | two lowest characters or skip (:53); fabricated chunk ids `max(id) + 1` (:95) | passes only because `save_02` is populated |
| `test_pursue_romance_replay` | `psycopg2.connect(get_slot_db_url(slot=2))` (:45) | two lowest characters or skip (:121); fabricated chunk ids `max(id) + 1` (:163) | passes only because `save_02` is populated |

Every write rolled back, but the owner sequences advanced (`b2_map.json` lists them per module).

## Shared Helpers

Both live in `tests/pg_fixtures.py`, call `require_disposable_target` before connecting, commit one row, and join `SEED_CALLS` in `tests/test_pg_disposable_target.py` (which proves the owner refusal before any connection).

- `seed_routine_anchor(dbname, *, character_entity_id, place_id, anchor_type="home", mobility_policy="fixed_place", source="test", schedule=None) -> int`: one committed `character_routine_anchors` row, returning its ID. The table's unique key `(character_entity_id, anchor_type)` and its check constraints (a `fixed_place` anchor needs `place_id`) decide validity; the helper does not second-guess them.
- `seed_pair_tag(dbname, *, subject_entity_id, object_entity_id, tag, source_kind="template", template_id=None, source_chunk_id=None) -> int`: one active `entity_pair_tags` row whose `pair_tag_id` is resolved from `pair_tags.tag` with `NOT deprecated`, asserting exactly one row (the `seed_entity_tag` pattern), so an unknown or deprecated tag fails by name.

`tests/test_pg_anchor_pair_tag_seeds.py` (PostgreSQL) reads each row back on a fresh connection and proves the failures: a duplicate anchor raises `UniqueViolation`, a placeless fixed anchor raises `CheckViolation`, and an unknown tag and the template's deprecated `contact` tag each fail the assertion and commit nothing.

## Per-Module Before and After

| Module | After |
| --- | --- |
| `test_faction_project_contexts_live` | module clone `qa885_faction_contexts`: zone, place, `seed_protagonist` (canonical player for the anchored resolver's weather read), `seed_story_clock`, two `seed_faction`, four `seed_character`, two `seed_routine_anchor`, two `seed_pair_tag('obligation')`, three `seed_relationship`. Per-test transaction, rollback, and the 081 re-run stay. The factions skip is an assertion that the clone holds exactly the two seeded active factions. |
| `test_polymorphic_patron_live` | module clone `qa885_patron_circle`: zone, place, protagonist, story clock (one world time, so need debt is zero), actor at home, member, `seed_faction`, `seed_relationship` (fixes the migration 115 producer bug), `seed_routine_anchor`, `seed_pair_tag('status:senior')`. The in-test `status:<level>` insert asserts its row. Per-test transaction, rollback, and the 096 re-run stay. |
| `test_composition_sources_live` | module clone `qa885_composition_sources`: zone, two places, story clock, six characters, five `seed_faction`, one anchor, three relationships, six pair tags. Both place skips are assertions; the in-test pair-tag insert asserts its row (`RETURNING id`); the acquaintance commit uses the seeded tick chunk instead of `max(id)`. The `live_llm` marker is unchanged. |
| `test_recruit_ally_projects` | module clone `qa885_recruit_ally_projects`: zone, place, `seed_character_pair` (B2-3's helper; head chunk a day before the pinned `NOW`) plus a third `seed_character`; bindings come from the returned ids; the three-character skip and the owner cleanup are gone. The coverage test is `@requires_corpus` (see below). |
| `test_projects` | module clone `qa885_project_promotion`: story clock and one character for the promotion probe. The coverage test is `@requires_corpus` (see below). |
| `test_recruit_ally_replay` | module clone `qa885_recruit_ally_replay` from `seed_checkpointed_story`; binds `actor=protagonist`, `target=rival`, the free pair (asserted unrelated in the fixture); chunk ids from the sequence (`INSERT ... RETURNING id`); `_next_world_time` requires the seeded head clock instead of falling back to 2026. |
| `test_pursue_romance_replay` | module clone `qa885_pursue_romance_replay`, same free pair and sequence-assigned ids; the shadow schema (`event_types`, `character_project_states`, migration 085) stays. `test_court_patron_replay` and `test_seek_redemption_replay` import `_fabricate_chunk` and `_next_world_time` from it, so both are rerun in every gate below (the rerun B2-3's evidence defers to this slice). |

## The Two Corpus-Statistics Tests

`test_recruit_ally_projects::test_corpus_recruitment_routes_persisted_target_without_routine_drift` (was `test_slot2_...`) and `test_projects::test_corpus_coverage_distribution_and_project_gate_payload` (was `test_slot2_...`) assert emergent resolver statistics of the played slot 2 story (35 playable anchors, surveil winners, routine-share shifts, advance winners). Each is now `@pytest.mark.requires_corpus` on a module-scoped `disposable_slot_database(..., source_db="save_02", include_data=True)` fixture that fails unless `NEXUS_RUN_CORPUS=1` (the `tests/test_lore/conftest.py` pattern). **The clone is a read of `save_02`** through `pg_dump`; nothing is written to the source. The engine comes from `sqlalchemy_url(dbname)`, the migration-074 re-run is dropped, every assertion is kept, and the off-screen recruit-target skip is now an assertion (it passes on the clone).

## Sequence Proof

Read-only snapshots (`BEGIN READ ONLY`) of `save_02` and `save_05`, taken directly before and after the three slice runs below (PostgreSQL, live opt-in, corpus opt-in). The corpus run's two `pg_dump` reads of `save_02` fall inside the window. `diff` of the two bodies: **identical**.

### Before (2026-09-30T03:54:49Z)

#### save_02

```
 schemaname |               sequencename                | last_value 
------------+-------------------------------------------+------------
 public     | ai_notebook_id_seq                        |           
 public     | backstory_secrets_id_seq                  |           
 public     | character_experience_jobs_id_seq          |           
 public     | character_experiences_id_seq              |           
 public     | character_identity_rulings_id_seq         |           
 public     | character_project_states_id_seq           |       3414
 public     | character_relationships_id_seq            |          7
 public     | character_routine_anchors_id_seq          |           
 public     | characters_id_seq                         |        101
 public     | chunk_metadata_id_seq                     |       8642
 public     | claim_awareness_id_seq                    |       1044
 public     | claims_id_seq                             |        475
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |        561
 public     | entity_pair_tags_id_seq                   |       3510
 public     | entity_tags_id_seq                        |       1145
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |          1
 public     | narrative_chunks_id_seq                   |       2621
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |        546
 public     | orrery_maturation_jobs_id_seq             |        504
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |       3174
 public     | orrery_recall_trace_id_seq                |           
 public     | orrery_resolutions_id_seq                 |       7261
 public     | orrery_route_graph_edges_id_seq           |           
 public     | orrery_route_graph_nodes_id_seq           |           
 public     | orrery_scene_pressures_id_seq             |        546
 public     | orrery_travel_edges_id_seq                |           
 public     | pair_tags_id_seq                          |         29
 public     | places_id_seq                             |          4
 public     | relationship_versions_id_seq              |     100126
 public     | retrieval_coverage_log_id_seq             |         52
 public     | retrograde_summaries_id_seq               |       1435
 public     | state_checkpoints_id_seq                  |       2966
 public     | state_delta_log_id_seq                    |         33
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |       1061
 public     | tags_id_seq                               |        556
 public     | world_events_id_seq                       |       8128
 public     | zones_id_seq                              |          1
(48 rows)

        table_name         | count 
---------------------------+-------
 entities                  |   121
 characters                |    35
 places                    |    77
 factions                  |     9
 character_relationships   |    84
 entity_pair_tags          |     0
 character_routine_anchors |     0
 orrery_resolutions        |     0
(8 rows)

```

#### save_05

```
 schemaname |               sequencename                | last_value 
------------+-------------------------------------------+------------
 public     | ai_notebook_id_seq                        |           
 public     | backstory_secrets_id_seq                  |           
 public     | character_experience_jobs_id_seq          |           
 public     | character_experiences_id_seq              |           
 public     | character_identity_rulings_id_seq         |           
 public     | character_project_states_id_seq           |           
 public     | character_relationships_id_seq            |           
 public     | character_routine_anchors_id_seq          |           
 public     | characters_id_seq                         |       2488
 public     | chunk_metadata_id_seq                     |       2272
 public     | claim_awareness_id_seq                    |           
 public     | claims_id_seq                             |           
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |       5505
 public     | entity_pair_tags_id_seq                   |        780
 public     | entity_tags_id_seq                        |         41
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |           
 public     | narrative_chunks_id_seq                   |       2378
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |           
 public     | orrery_maturation_jobs_id_seq             |           
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |           
 public     | orrery_recall_trace_id_seq                |       2088
 public     | orrery_resolutions_id_seq                 |           
 public     | orrery_route_graph_edges_id_seq           |           
 public     | orrery_route_graph_nodes_id_seq           |           
 public     | orrery_scene_pressures_id_seq             |           
 public     | orrery_travel_edges_id_seq                |           
 public     | pair_tags_id_seq                          |        387
 public     | places_id_seq                             |           
 public     | relationship_versions_id_seq              |         12
 public     | retrieval_coverage_log_id_seq             |           
 public     | retrograde_summaries_id_seq               |           
 public     | state_checkpoints_id_seq                  |        246
 public     | state_delta_log_id_seq                    |           
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |        156
 public     | tags_id_seq                               |      20092
 public     | world_events_id_seq                       |       3194
 public     | zones_id_seq                              |           
(48 rows)

        table_name         | count 
---------------------------+-------
 entities                  |     0
 characters                |     0
 places                    |     0
 factions                  |     0
 character_relationships   |     0
 entity_pair_tags          |     0
 character_routine_anchors |     0
 orrery_resolutions        |     0
(8 rows)

```

### After (2026-09-30T03:56:01Z)

#### save_02

```
 schemaname |               sequencename                | last_value 
------------+-------------------------------------------+------------
 public     | ai_notebook_id_seq                        |           
 public     | backstory_secrets_id_seq                  |           
 public     | character_experience_jobs_id_seq          |           
 public     | character_experiences_id_seq              |           
 public     | character_identity_rulings_id_seq         |           
 public     | character_project_states_id_seq           |       3414
 public     | character_relationships_id_seq            |          7
 public     | character_routine_anchors_id_seq          |           
 public     | characters_id_seq                         |        101
 public     | chunk_metadata_id_seq                     |       8642
 public     | claim_awareness_id_seq                    |       1044
 public     | claims_id_seq                             |        475
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |        561
 public     | entity_pair_tags_id_seq                   |       3510
 public     | entity_tags_id_seq                        |       1145
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |          1
 public     | narrative_chunks_id_seq                   |       2621
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |        546
 public     | orrery_maturation_jobs_id_seq             |        504
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |       3174
 public     | orrery_recall_trace_id_seq                |           
 public     | orrery_resolutions_id_seq                 |       7261
 public     | orrery_route_graph_edges_id_seq           |           
 public     | orrery_route_graph_nodes_id_seq           |           
 public     | orrery_scene_pressures_id_seq             |        546
 public     | orrery_travel_edges_id_seq                |           
 public     | pair_tags_id_seq                          |         29
 public     | places_id_seq                             |          4
 public     | relationship_versions_id_seq              |     100126
 public     | retrieval_coverage_log_id_seq             |         52
 public     | retrograde_summaries_id_seq               |       1435
 public     | state_checkpoints_id_seq                  |       2966
 public     | state_delta_log_id_seq                    |         33
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |       1061
 public     | tags_id_seq                               |        556
 public     | world_events_id_seq                       |       8128
 public     | zones_id_seq                              |          1
(48 rows)

        table_name         | count 
---------------------------+-------
 entities                  |   121
 characters                |    35
 places                    |    77
 factions                  |     9
 character_relationships   |    84
 entity_pair_tags          |     0
 character_routine_anchors |     0
 orrery_resolutions        |     0
(8 rows)

```

#### save_05

```
 schemaname |               sequencename                | last_value 
------------+-------------------------------------------+------------
 public     | ai_notebook_id_seq                        |           
 public     | backstory_secrets_id_seq                  |           
 public     | character_experience_jobs_id_seq          |           
 public     | character_experiences_id_seq              |           
 public     | character_identity_rulings_id_seq         |           
 public     | character_project_states_id_seq           |           
 public     | character_relationships_id_seq            |           
 public     | character_routine_anchors_id_seq          |           
 public     | characters_id_seq                         |       2488
 public     | chunk_metadata_id_seq                     |       2272
 public     | claim_awareness_id_seq                    |           
 public     | claims_id_seq                             |           
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |       5505
 public     | entity_pair_tags_id_seq                   |        780
 public     | entity_tags_id_seq                        |         41
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |           
 public     | narrative_chunks_id_seq                   |       2378
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |           
 public     | orrery_maturation_jobs_id_seq             |           
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |           
 public     | orrery_recall_trace_id_seq                |       2088
 public     | orrery_resolutions_id_seq                 |           
 public     | orrery_route_graph_edges_id_seq           |           
 public     | orrery_route_graph_nodes_id_seq           |           
 public     | orrery_scene_pressures_id_seq             |           
 public     | orrery_travel_edges_id_seq                |           
 public     | pair_tags_id_seq                          |        387
 public     | places_id_seq                             |           
 public     | relationship_versions_id_seq              |         12
 public     | retrieval_coverage_log_id_seq             |           
 public     | retrograde_summaries_id_seq               |           
 public     | state_checkpoints_id_seq                  |        246
 public     | state_delta_log_id_seq                    |           
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |        156
 public     | tags_id_seq                               |      20092
 public     | world_events_id_seq                       |       3194
 public     | zones_id_seq                              |           
(48 rows)

        table_name         | count 
---------------------------+-------
 entities                  |     0
 characters                |     0
 places                    |     0
 factions                  |     0
 character_relationships   |     0
 entity_pair_tags          |     0
 character_routine_anchors |     0
 orrery_resolutions        |     0
(8 rows)

```

## Slice Gates

Gateway variables unset (`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL`). Each run loads a scratch `dbname_audit` plugin (not committed) that wraps `psycopg2.connect` and `asyncpg.connect`, resolves each target's `dbname` (keyword or DSN through `parse_dsn`), and prints every name reached plus any matching `save_0` or `NEXUS_template`. SQLAlchemy engines connect through `psycopg2.connect`, so they are covered; `pg_dump` is a subprocess and is not. Deprecation-warning lines are filtered from the tails.

### PostgreSQL

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=<scratch> $PY -m pytest -q -rs -p dbname_audit \
    tests/test_orrery/test_faction_project_contexts_live.py tests/test_orrery/test_polymorphic_patron_live.py \
    tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_recruit_ally_projects.py \
    tests/test_orrery/test_projects.py tests/test_orrery/test_recruit_ally_replay.py \
    tests/test_orrery/test_pursue_romance_replay.py tests/test_orrery/test_court_patron_replay.py \
    tests/test_orrery/test_seek_redemption_replay.py tests/test_pg_disposable_target.py \
    tests/test_pg_anchor_pair_tag_seeds.py
.........ssssssss.......................s............s.................. [ 74%]
.........................                                                [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname-audit: postgres, qa885_anchor_pair_seeds_7da18a50ebbd, qa885_court_patron_2a8ed529420e, qa885_faction_contexts_4bf6d8d9d6af, qa885_patron_circle_0c15da808d69, qa885_project_promotion_5429ebdbcb9b, qa885_pursue_romance_replay_3d99be331da1, qa885_recruit_ally_projects_5d6de41bb8c8, qa885_recruit_ally_replay_9d3051b37c1d, qa885_seek_redemption_c358761358c4
dbname-audit owner targets: []
=========================== short test summary info ============================
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py:546: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_recruit_ally_projects.py:808: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_orrery/test_projects.py:609: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
87 passed, 10 skipped, 5 warnings in 12.79s
```

### PostgreSQL With the Live Opt-In

`test_composition_sources_live` runs only under `NEXUS_RUN_LIVE_LLM=1`; it makes no inference call and its clone is TEST-pinned. Under that flag the guard reports `nexus-api: read-only (live LLM)` instead of `denied`, which is the guard's documented live mode, not a weaker gate.

```
$ NEXUS_RUN_POSTGRES=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_TEST_PROVIDER_ONLY=1 PYTHONPATH=<scratch> \
    $PY -m pytest -q -rs -p dbname_audit <the same eleven modules>
........................................s............s.................. [ 74%]
.........................                                                [100%]
secret-store guard: active; nexus-api: read-only (live LLM); disposable keychain: denied
dbname-audit: postgres, qa885_anchor_pair_seeds_6ca3a9e29359, qa885_composition_sources_34f550b7cd2f, qa885_court_patron_ef0d9d50bc9a, qa885_faction_contexts_764aa3378d84, qa885_patron_circle_1835deeccf4c, qa885_project_promotion_fa662e612231, qa885_pursue_romance_replay_575c2d4cbeb3, qa885_recruit_ally_projects_af830b3031e4, qa885_recruit_ally_replay_1a7f3bd6cec1, qa885_seek_redemption_3d23380d60af
dbname-audit owner targets: []
=========================== short test summary info ============================
SKIPPED [1] tests/test_orrery/test_recruit_ally_projects.py:808: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_orrery/test_projects.py:609: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
95 passed, 2 skipped, 5 warnings in 14.67s
```

### The Two `@requires_corpus` Tests Under Their Opt-In

```
$ NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 PYTHONPATH=<scratch> $PY -m pytest -q -rs -p dbname_audit \
    "tests/test_orrery/test_recruit_ally_projects.py::test_corpus_recruitment_routes_persisted_target_without_routine_drift" \
    "tests/test_orrery/test_projects.py::test_corpus_coverage_distribution_and_project_gate_payload"
..                                                                       [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname-audit: postgres, qa885_projects_corpus_dd2a05e66b7e, qa885_recruit_ally_corpus_0d6b3b3079cc
dbname-audit owner targets: []
2 passed, 5 warnings in 43.33s
```

## Full Orrery PostgreSQL Run

Run after the snapshot window, in two halves for the shell time limit. This run includes unconverted modules of later slices, which still roll back writes on the owner slots.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfE tests/test_orrery/test_[a-o]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
2 failed, 805 passed, 29 skipped, 7 warnings in 154.42s (0:02:34)

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
10 failed, 815 passed, 12 skipped, 7 warnings in 117.21s (0:01:57)
```

| Failure | Count | Class |
| --- | ---: | --- |
| `test_reveal_live` | 9 | later slice B2-2 (empty `save_05`); pre-existing on main |
| `test_adjudication_history::test_history_is_non_vacuous_on_audited_slots` | 1 | later slice B2-5 (cannot be made honest as written); pre-existing on main |
| `test_evidence::test_slot_backed_explain_carries_evidence_end_to_end` | 1 | later slice B2-7; pre-existing on main |
| `test_tag_library::test_contextual_library_save_05_completeness_and_size` | 1 | later slice B2-7; pre-existing on main |

No failure is new. Against B2-3's recorded run (`docs/qa/885-project-applier-clones/verification.md`), the eight `test_faction_project_contexts_live` errors and the `test_polymorphic_patron_live` error are gone, and the second half has two more skips: the two `@requires_corpus` tests, which now run only under `NEXUS_RUN_CORPUS=1`.

## Offline Gates

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2465 passed, 375 skipped, 8 warnings in 355.00s (0:05:55)

$ $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 736 skipped, 7 warnings in 31.33s

$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.64s
```

Black, flake8, and mypy on the ten changed files:

```
$ $PY -m black --check <ten files>
10 files would be left unchanged.
$ $PY -m flake8 <ten files>
flake8 exit 0
```

mypy (`--explicit-package-bases --follow-imports=silent`; `tests/` has no `__init__.py`) reports 26 errors on the branch and 31 on the same nine pre-existing files at `origin/main`. The diff (line numbers stripped) removes five pre-existing `tuple | None is not indexable` errors from the rewritten fixtures and adds none:

```
1c1
< Found 31 errors in 5 files (checked 9 source files)
---
> Found 26 errors in 3 files (checked 10 source files)
28,32d27
< tests/test_orrery/test_projects.py: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
< tests/test_orrery/test_projects.py: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
< tests/test_orrery/test_projects.py: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
< tests/test_orrery/test_recruit_ally_projects.py: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
< tests/test_orrery/test_recruit_ally_projects.py: error: Value of type "tuple[Any, ...] | None" is not indexable  [index]
```

## Audit Grep

```
$ for f in <the seven modules>; do grep -n "save_0\|NEXUS_template\|get_slot_db_url(slot=\|slot_dbname([1-5])\|LIVE_SLOT" $f; done
== tests/test_orrery/test_faction_project_contexts_live.py
== tests/test_orrery/test_polymorphic_patron_live.py
== tests/test_orrery/test_composition_sources_live.py
== tests/test_orrery/test_recruit_ally_projects.py
362:        "qa885_recruit_ally_corpus", source_db="save_02", include_data=True
== tests/test_orrery/test_projects.py
561:        "qa885_projects_corpus", source_db="save_02", include_data=True
== tests/test_orrery/test_recruit_ally_replay.py
== tests/test_orrery/test_pursue_romance_replay.py
== pytest.skip / slot2 / _on_save_05
(none)
```

The only hits are the two `@requires_corpus` clones' `source_db="save_02"` argument.

## #885 Ids Retired

- `tests/test_orrery/test_faction_project_contexts_live.py`: all eight ids (setup `NoResultFound` on `save_05`).
- `tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle` (setup `NoResultFound`; behind it, the migration 115 producer failure on any slot).
- `tests/test_orrery/test_composition_sources_live.py` (live_llm): eight ids, which error on `save_05` under the live opt-in.
- Owner-slot readers moved to clones: the four fixture-backed `test_recruit_ally_projects` tests, `test_projects::test_resolution_insert_skips_routine_promotion_but_queues_milestone`, `test_recruit_ally_replay`, `test_pursue_romance_replay`; the two coverage tests now read a `save_02` data clone under `requires_corpus`.

## Deferred

- The `live_llm` marker on `test_composition_sources_live` stays (order note 9); the module makes no inference call, and whether it should go is the owner's decision.
- The 081 and 096 re-runs inside the per-test transactions stay. They are idempotent on a head-migrated clone; 081's keeps the comment assertion pinned to its text.
