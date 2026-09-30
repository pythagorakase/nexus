# #885 Slice B2-4: Checkpoint-Replay and Resolver-Composition Fixtures Leave the Owner Slots

Branch `claude/885-composition-clones`, rebased onto `origin/main` at `3e8e692e` (B2-2, #1035, on top of B2-3, #1036). Test-only; no migration; no paid call (TEST provider only; every clone is TEST-pinned); no gateway lane. `$PY` is `/Users/pythagor/nexus/.venv/bin/python`, run from the worktree root, whose `nexus` import resolves inside the worktree.

## What Was Wrong

Line numbers are at `ae2e29bc`, where this slice was cut; neither B2-3 nor B2-2 touched these seven files.

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
| `test_recruit_ally_replay` | module clone `qa885_recruit_ally_replay` from `seed_checkpointed_story`; binds `actor=protagonist`, `target=rival`, the free pair (asserted unrelated in the fixture, and again in the test body before the reconstruction check); chunk ids from the sequence (`INSERT ... RETURNING id`); `_next_world_time` requires the seeded head clock instead of falling back to 2026. |
| `test_pursue_romance_replay` | module clone `qa885_pursue_romance_replay`, same free pair and sequence-assigned ids; the shadow schema (`event_types`, `character_project_states`, migration 085) stays. `test_court_patron_replay` and `test_seek_redemption_replay` import `_fabricate_chunk` and `_next_world_time` from it, so both are rerun in every gate below (the rerun B2-3's evidence defers to this slice). |

## The Two Corpus-Statistics Tests

`test_recruit_ally_projects::test_corpus_recruitment_routes_persisted_target_without_routine_drift` (was `test_slot2_...`) and `test_projects::test_corpus_coverage_distribution_and_project_gate_payload` (was `test_slot2_...`) assert emergent resolver statistics of the played slot 2 story (35 playable anchors, surveil winners, routine-share shifts, advance winners). Each is now `@pytest.mark.requires_corpus` on a module-scoped `disposable_slot_database(..., source_db="save_02", include_data=True)` fixture that fails unless `NEXUS_RUN_CORPUS=1` (the `tests/test_lore/conftest.py` pattern). **The clone is a read of `save_02`** through `pg_dump`; nothing is written to the source. The engine comes from `sqlalchemy_url(dbname)`, the migration-074 re-run is dropped, every assertion is kept, and the off-screen recruit-target skip is now an assertion (it passes on the clone).

## Sequence Proof

Read-only snapshots (`BEGIN READ ONLY ... ROLLBACK`, script `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/snap.sh`) of `save_02` and `save_05`, taken directly before and after the fixer's rerun of the three slice runs below (PostgreSQL, live opt-in, corpus opt-in) with the review fixes applied. The corpus run's two `pg_dump` reads of `save_02` fall inside the window. `diff /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/before.txt /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/after.txt`: **identical**. `ps` before the window showed no other pytest process. The bodies below are those two files, verbatim.

Earlier pairs: the builder's pair at the pre-fix head (04:27:58Z to 04:29:14Z) and a pair before the rebase onto B2-2 (03:54:49Z to 03:56:01Z) were also identical. A pair at 04:10:43Z to 04:11:59Z differed: `save_02` `character_project_states_id_seq` and `orrery_resolutions_id_seq`, and seven `save_05` sequences, moved while another session's `pytest tests/test_orrery` (which still includes unconverted modules) was running. That pair is discarded, not explained away. Between the builder's 04:29:14Z snapshot and the fixer's 2026-09-30T04:45:10Z snapshot, seven sequences moved outside both windows (`save_02` `character_project_states`, `chunk_metadata`, `entity_pair_tags`, `orrery_resolutions`, `relationship_versions`, `state_checkpoints`; `save_05` `entities`) while other builders' sessions were running. Neither window moved.

### Before (2026-09-30T04:45:10Z)

#### save_02

```
BEGIN
 schemaname |               sequencename                | last_value 
------------+-------------------------------------------+------------
 public     | ai_notebook_id_seq                        |           
 public     | backstory_secrets_id_seq                  |           
 public     | character_experience_jobs_id_seq          |           
 public     | character_experiences_id_seq              |           
 public     | character_identity_rulings_id_seq         |           
 public     | character_project_states_id_seq           |       3454
 public     | character_relationships_id_seq            |          7
 public     | character_routine_anchors_id_seq          |           
 public     | characters_id_seq                         |        101
 public     | chunk_metadata_id_seq                     |       8682
 public     | claim_awareness_id_seq                    |       1044
 public     | claims_id_seq                             |        475
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |        561
 public     | entity_pair_tags_id_seq                   |       3528
 public     | entity_tags_id_seq                        |       1157
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |          1
 public     | narrative_chunks_id_seq                   |       2624
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |        561
 public     | orrery_maturation_jobs_id_seq             |        504
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |       3230
 public     | orrery_recall_trace_id_seq                |           
 public     | orrery_resolutions_id_seq                 |       7370
 public     | orrery_route_graph_edges_id_seq           |           
 public     | orrery_route_graph_nodes_id_seq           |           
 public     | orrery_scene_pressures_id_seq             |        561
 public     | orrery_travel_edges_id_seq                |           
 public     | pair_tags_id_seq                          |         29
 public     | places_id_seq                             |          4
 public     | relationship_versions_id_seq              |     100142
 public     | retrieval_coverage_log_id_seq             |         52
 public     | retrograde_summaries_id_seq               |       1435
 public     | state_checkpoints_id_seq                  |       2982
 public     | state_delta_log_id_seq                    |         33
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |       1070
 public     | tags_id_seq                               |        556
 public     | world_events_id_seq                       |       8182
 public     | zones_id_seq                              |          1
(48 rows)

            tbl            | count 
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

ROLLBACK
```

#### save_05

```
BEGIN
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
 public     | characters_id_seq                         |       2524
 public     | chunk_metadata_id_seq                     |       2386
 public     | claim_awareness_id_seq                    |           
 public     | claims_id_seq                             |           
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |       5553
 public     | entity_pair_tags_id_seq                   |        780
 public     | entity_tags_id_seq                        |         41
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |           
 public     | narrative_chunks_id_seq                   |       2492
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |           
 public     | orrery_maturation_jobs_id_seq             |           
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |           
 public     | orrery_recall_trace_id_seq                |       2184
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
 public     | state_checkpoints_id_seq                  |        252
 public     | state_delta_log_id_seq                    |           
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |        156
 public     | tags_id_seq                               |      20092
 public     | world_events_id_seq                       |       3338
 public     | zones_id_seq                              |           
(48 rows)

            tbl            | count 
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

ROLLBACK
```

### After (2026-09-30T04:46:40Z)

#### save_02

```
BEGIN
 schemaname |               sequencename                | last_value 
------------+-------------------------------------------+------------
 public     | ai_notebook_id_seq                        |           
 public     | backstory_secrets_id_seq                  |           
 public     | character_experience_jobs_id_seq          |           
 public     | character_experiences_id_seq              |           
 public     | character_identity_rulings_id_seq         |           
 public     | character_project_states_id_seq           |       3454
 public     | character_relationships_id_seq            |          7
 public     | character_routine_anchors_id_seq          |           
 public     | characters_id_seq                         |        101
 public     | chunk_metadata_id_seq                     |       8682
 public     | claim_awareness_id_seq                    |       1044
 public     | claims_id_seq                             |        475
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |        561
 public     | entity_pair_tags_id_seq                   |       3528
 public     | entity_tags_id_seq                        |       1157
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |          1
 public     | narrative_chunks_id_seq                   |       2624
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |        561
 public     | orrery_maturation_jobs_id_seq             |        504
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |       3230
 public     | orrery_recall_trace_id_seq                |           
 public     | orrery_resolutions_id_seq                 |       7370
 public     | orrery_route_graph_edges_id_seq           |           
 public     | orrery_route_graph_nodes_id_seq           |           
 public     | orrery_scene_pressures_id_seq             |        561
 public     | orrery_travel_edges_id_seq                |           
 public     | pair_tags_id_seq                          |         29
 public     | places_id_seq                             |          4
 public     | relationship_versions_id_seq              |     100142
 public     | retrieval_coverage_log_id_seq             |         52
 public     | retrograde_summaries_id_seq               |       1435
 public     | state_checkpoints_id_seq                  |       2982
 public     | state_delta_log_id_seq                    |         33
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |       1070
 public     | tags_id_seq                               |        556
 public     | world_events_id_seq                       |       8182
 public     | zones_id_seq                              |          1
(48 rows)

            tbl            | count 
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

ROLLBACK
```

#### save_05

```
BEGIN
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
 public     | characters_id_seq                         |       2524
 public     | chunk_metadata_id_seq                     |       2386
 public     | claim_awareness_id_seq                    |           
 public     | claims_id_seq                             |           
 public     | correspondence_compaction_jobs_id_seq     |           
 public     | entities_id_seq                           |       5553
 public     | entity_pair_tags_id_seq                   |        780
 public     | entity_tags_id_seq                        |         41
 public     | generation_session_phases_id_seq          |           
 public     | interaction_authorizations_id_seq         |           
 public     | interaction_events_id_seq                 |           
 public     | interaction_participants_id_seq           |           
 public     | items_id_seq                              |           
 public     | layers_id_seq                             |           
 public     | narrative_chunks_id_seq                   |       2492
 public     | narrative_embedding_jobs_id_seq           |           
 public     | narrative_summary_jobs_id_seq             |           
 public     | offscreen_narrations_id_seq               |           
 public     | orrery_adjudication_log_id_seq            |           
 public     | orrery_maturation_jobs_id_seq             |           
 public     | orrery_narration_jobs_id_seq              |           
 public     | orrery_prompt_exposures_id_seq            |           
 public     | orrery_recall_trace_id_seq                |       2184
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
 public     | state_checkpoints_id_seq                  |        252
 public     | state_delta_log_id_seq                    |           
 public     | storyteller_correspondence_letters_id_seq |           
 public     | tag_clearance_log_id_seq                  |        156
 public     | tags_id_seq                               |      20092
 public     | world_events_id_seq                       |       3338
 public     | zones_id_seq                              |           
(48 rows)

            tbl            | count 
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

ROLLBACK
```

## Slice Gates

Gateway variables unset (`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL`). Each run loads the scratch `dbname_audit` plugin, not committed, at `/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/dbname_audit.py`, through `PYTHONPATH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4`. The plugin wraps `psycopg2.connect` and `asyncpg.connect`, resolves each target's `dbname` (keyword or DSN through `parse_dsn`), and prints every name reached plus any matching `save_0` or `NEXUS_template`. SQLAlchemy engines connect through `psycopg2.connect`, so they are covered; `pg_dump` is a subprocess and is not. Each tail is the complete, unfiltered output file named above it.

### PostgreSQL

`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/slice_pg.txt`:

```
$ NEXUS_RUN_POSTGRES=1 PYTHONPATH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4 $PY -m pytest -q -rs -p dbname_audit \
    tests/test_orrery/test_faction_project_contexts_live.py tests/test_orrery/test_polymorphic_patron_live.py \
    tests/test_orrery/test_composition_sources_live.py tests/test_orrery/test_recruit_ally_projects.py \
    tests/test_orrery/test_projects.py tests/test_orrery/test_recruit_ally_replay.py \
    tests/test_orrery/test_pursue_romance_replay.py tests/test_orrery/test_court_patron_replay.py \
    tests/test_orrery/test_seek_redemption_replay.py tests/test_pg_disposable_target.py \
    tests/test_pg_anchor_pair_tag_seeds.py
.........ssssssss.......................s............s.................. [ 72%]
...........................                                              [100%]
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

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname-audit: postgres, qa885_anchor_pair_seeds_2a09d4a0be4e, qa885_court_patron_b9e4a9413f43, qa885_faction_contexts_5e96f3ec40a3, qa885_patron_circle_897acd67d1e4, qa885_project_promotion_e41f836388f2, qa885_pursue_romance_replay_46df2f7f372f, qa885_recruit_ally_projects_3eef0e961976, qa885_recruit_ally_replay_d1accf7d47e4, qa885_seek_redemption_13d36d16ff09, qa885_transaction_writer_4532cc7e9763
dbname-audit owner targets: []
=========================== short test summary info ============================
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [4] tests/test_orrery/test_composition_sources_live.py:546: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_orrery/test_recruit_ally_projects.py:808: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_orrery/test_projects.py:609: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
89 passed, 10 skipped, 5 warnings in 15.74s
```

### PostgreSQL with the Live Opt-In

`test_composition_sources_live` runs only under `NEXUS_RUN_LIVE_LLM=1`; it makes no inference call and its clone is TEST-pinned. Under that flag the guard's summary reads `nexus-api: read-only (live LLM)` instead of `denied`: `describe()` picks that word from `LIVE_LLM_OPT_IN` (`tests/secret_store_guard.py:691`), and `docs/agent_workflow.md:24-25` notes that `nexus-api: denied` requires `NEXUS_RUN_LIVE_LLM` to be unset. This run adds the live-opt-in coverage only. The gate that carries `secret-store guard: active; nexus-api: denied` is the plain PostgreSQL run above, over the same eleven modules.

`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/slice_live.txt`:

```
$ NEXUS_RUN_POSTGRES=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_TEST_PROVIDER_ONLY=1 PYTHONPATH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4 \
    $PY -m pytest -q -rs -p dbname_audit <the same eleven modules>
........................................s............s.................. [ 72%]
...........................                                              [100%]
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

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: read-only (live LLM); disposable keychain: denied
dbname-audit: postgres, qa885_anchor_pair_seeds_13b64909a280, qa885_composition_sources_cdf0fd8d3cc8, qa885_court_patron_8a8740e1ab9d, qa885_faction_contexts_3dc3891c9623, qa885_patron_circle_51e847d5e533, qa885_project_promotion_9d30d4789c3e, qa885_pursue_romance_replay_02494d19317d, qa885_recruit_ally_projects_a91c67d0187c, qa885_recruit_ally_replay_e58d1b52dd1e, qa885_seek_redemption_00ae91b23c39, qa885_transaction_writer_fe5c602b2c63
dbname-audit owner targets: []
=========================== short test summary info ============================
SKIPPED [1] tests/test_orrery/test_recruit_ally_projects.py:808: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
SKIPPED [1] tests/test_orrery/test_projects.py:609: Set NEXUS_RUN_CORPUS=1 to run owner-corpus probes on disposable clones.
97 passed, 2 skipped, 5 warnings in 17.62s
```

### The Two `@requires_corpus` Tests Under Their Opt-In

`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/slice_corpus.txt`:

```
$ NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 PYTHONPATH=/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4 $PY -m pytest -q -rs -p dbname_audit \
    "tests/test_orrery/test_recruit_ally_projects.py::test_corpus_recruitment_routes_persisted_target_without_routine_drift" \
    "tests/test_orrery/test_projects.py::test_corpus_coverage_distribution_and_project_gate_payload"
..                                                                       [100%]
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

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname-audit: postgres, qa885_projects_corpus_e6e2cde72349, qa885_recruit_ally_corpus_3437a7609e0d
dbname-audit owner targets: []
2 passed, 5 warnings in 47.19s
```

## Full Orrery PostgreSQL Run

Rerun by the fixer on the fix head after the snapshot window, in two halves for the shell time limit. This run includes unconverted modules of later slices, which still roll back writes on the owner slots. Each tail runs from the `FAILURES` header to the end of the raw file, unfiltered; the progress lines above it hold only dots and `s`/`F` marks.

`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/orrery_ao.txt`:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfE tests/test_orrery/test_[a-o]*.py
=================================== FAILURES ===================================
_________________ test_history_is_non_vacuous_on_audited_slots _________________

    def test_history_is_non_vacuous_on_audited_slots() -> None:
        """Both slots must still carry adjudication data or the suite is hollow."""
    
        total_rows = 0
        for slot in HISTORY_SLOTS:
            engine = create_engine(get_slot_db_url(slot=slot))
            try:
                with Session(engine) as session:
                    total_rows += adjudication_history(session)["totals"]["log_rows"]
            finally:
                engine.dispose()
>       assert total_rows > 0, (
            "no audited slot has adjudication-log rows — the history assertions "
            "are vacuous; repoint HISTORY_SLOTS at a slot with Skald rulings"
        )
E       AssertionError: no audited slot has adjudication-log rows — the history assertions are vacuous; repoint HISTORY_SLOTS at a slot with Skald rulings
E       assert 0 > 0

tests/test_orrery/test_adjudication_history.py:335: AssertionError
_____________ test_slot_backed_explain_carries_evidence_end_to_end _____________

    @pytest.mark.requires_postgres
    def test_slot_backed_explain_carries_evidence_end_to_end() -> None:
        """Evidence must survive the full audit payload path on a real slot."""
    
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
    
        from nexus.agents.orrery.audit import explain_dry_run
        from nexus.api.slot_utils import get_slot_db_url
        from nexus.config import load_settings_as_dict
    
        orrery = load_settings_as_dict()["orrery"]
        engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
        try:
            with Session(engine) as session:
                report = explain_dry_run(
                    session,
                    BUILTIN_TEMPLATES,
                    anchor_chunk_id=None,
                    window_chunks=int(orrery["binding"]["window_chunks"]),
                    sunhelm_settings=orrery.get("sunhelm"),
                )
        finally:
            engine.dispose()
    
        payload = json.loads(json.dumps(report.to_dict()))
>       assert payload["actors"], "save_05 is expected to bind off-screen actors"
E       AssertionError: save_05 is expected to bind off-screen actors
E       assert []

tests/test_orrery/test_evidence.py:454: AssertionError
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
=========================== short test summary info ============================
FAILED tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
2 failed, 805 passed, 29 skipped, 7 warnings in 165.76s (0:02:45)
```

`/private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/885-B2-4/orrery_pz.txt`:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rfE tests/test_orrery/test_[p-z]*.py
=================================== FAILURES ===================================
____________ test_contextual_library_save_05_completeness_and_size _____________

    @pytest.mark.skipif(
        os.environ.get("NEXUS_RUN_POSTGRES") != "1",
        reason="Set NEXUS_RUN_POSTGRES=1 for the read-only save_05 size proof.",
    )
    def test_contextual_library_save_05_completeness_and_size() -> None:
        """Live registry stays complete while a realistic slice is at most half-size."""
    
        conn = tag_library._connect("save_05")
        try:
            conn.set_session(readonly=True, autocommit=True)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT etc.entity_kind::text AS entity_kind,
                                    CASE etc.entity_kind::text
                                        WHEN 'character' THEN characters.id
                                        WHEN 'place' THEN places.id
                                        WHEN 'faction' THEN factions.id
                                    END AS row_id
                    FROM entity_tags_current AS etc
                    LEFT JOIN characters
                      ON etc.entity_kind::text = 'character'
                     AND characters.entity_id = etc.entity_id
                    LEFT JOIN places
                      ON etc.entity_kind::text = 'place'
                     AND places.entity_id = etc.entity_id
                    LEFT JOIN factions
                      ON etc.entity_kind::text = 'faction'
                     AND factions.entity_id = etc.entity_id
                    ORDER BY entity_kind, row_id
                    LIMIT 5
                    """
                )
                entity_refs = [
                    tag_library.EntityRowReference(
                        kind=cast(tag_library.EntityKind, str(row["entity_kind"])),
                        row_id=int(row["row_id"]),
                    )
                    for row in cur.fetchall()
                ]
                cur.execute(
                    """
                    SELECT chunk_id
                    FROM chunk_metadata
                    WHERE world_time IS NOT NULL
                    ORDER BY world_time DESC, chunk_id DESC
                    LIMIT 1
                    """
                )
                anchor_row = cur.fetchone()
        finally:
            conn.close()
>       assert entity_refs, "save_05 must contain current entity tags"
E       AssertionError: save_05 must contain current entity tags
E       assert []

tests/test_orrery/test_tag_library.py:869: AssertionError
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
=========================== short test summary info ============================
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
1 failed, 824 passed, 12 skipped, 7 warnings in 127.29s (0:02:07)
```

| Failure | Count | Cause in this run | Class |
| --- | ---: | --- | --- |
| `test_adjudication_history::test_history_is_non_vacuous_on_audited_slots` | 1 | `HISTORY_SLOTS = (2, 5)` (:41); `save_02` and `save_05` each hold 0 `orrery_adjudication_log` rows (read-only count) | later slice B2-5 (cannot be made honest as written); pre-existing on main |
| `test_evidence::test_slot_backed_explain_carries_evidence_end_to_end` | 1 | `LIVE_SLOT = 5` (:111); `save_05` holds 0 characters, so `explain_dry_run` binds no actors | later slice B2-7; pre-existing on main |
| `test_tag_library::test_contextual_library_save_05_completeness_and_size` | 1 | reads `save_05`, which holds 0 `entity_tags_current` rows | later slice B2-7; pre-existing on main |

No failure is new. Against B2-3's recorded run (`docs/qa/885-project-applier-clones/verification.md`), the eight `test_faction_project_contexts_live` errors and the `test_polymorphic_patron_live` error are gone (this slice), the nine `test_reveal_live` failures are gone (B2-2), and the second half has two more skips: the two `@requires_corpus` tests, which now run only under `NEXUS_RUN_CORPUS=1`.

## Offline Gates

Run on the rebased head, before the review fixes. The fixes change only PostgreSQL-gated assertions in three test files, so the fixer reran those files offline (the last two lines of pytest output shown) and rechecked the ten changed files:

```
$ $PY -m pytest -q tests/test_orrery/test_recruit_ally_replay.py tests/test_orrery/test_pursue_romance_replay.py tests/test_orrery/test_composition_sources_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
10 skipped, 5 warnings in 0.26s
$ $PY -m black --check <ten files>
10 files would be left unchanged.
$ $PY -m flake8 <ten files>
flake8 exit 0
```

The builder's runs on the rebased head:

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2465 passed, 377 skipped, 8 warnings in 352.47s (0:05:52)

$ $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 736 skipped, 7 warnings in 30.78s

$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.66s
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

## #885 IDs Retired

- `tests/test_orrery/test_faction_project_contexts_live.py`: all eight ids (setup `NoResultFound` on `save_05`).
- `tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle` (setup `NoResultFound`; behind it, the migration 115 producer failure on any slot).
- `tests/test_orrery/test_composition_sources_live.py` (live_llm): eight ids, which error on `save_05` under the live opt-in.
- Owner-slot readers moved to clones: the four fixture-backed `test_recruit_ally_projects` tests, `test_projects::test_resolution_insert_skips_routine_promotion_but_queues_milestone`, `test_recruit_ally_replay`, `test_pursue_romance_replay`; the two coverage tests now read a `save_02` data clone under `requires_corpus`.

## Deferred

- The `live_llm` marker on `test_composition_sources_live` stays (order note 9); the module makes no inference call, and whether it should go is the owner's decision.
- The 081 and 096 re-runs inside the per-test transactions stay. They are idempotent on a head-migrated clone; 081's keeps the comment assertion pinned to its text.
