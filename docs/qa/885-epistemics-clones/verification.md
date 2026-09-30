# #885 Slice B2-2: Tick-Commit and Epistemics Writers Leave the Owner Slots

Work order 885-B2-2 (issue #885, plan comment "Slice B2 Mapped: Nine Ordered Slices"). Base `origin/main` at `813c23d9`. Test-only; no migration; no paid call (every clone is TEST-pinned by `disposable_slot_database`); no gateway lane.

## What Changed

Every module now builds one module-scoped `disposable_slot_database("qa885_<module>")`, seeds the need-clock anchor first (`seed_protagonist` with a `base_timestamp`, or `seed_story_clock` before any `seed_character`), then the rows its tests name, and connects through `tests.pg_fixtures` (`connect`, `asyncpg_kwargs`, `sqlalchemy_url`). Per-test connections still roll back. Seeding runs in synchronous fixtures only.

| File | Before (base `813c23d9`) | After |
| --- | --- | --- |
| `tests/test_orrery/test_epistemics.py` | `save_02_conn` opened `get_slot_db_url(slot=2)` (:71); async test `asyncpg_kwargs("save_02")` (:648); two `create_engine(get_slot_db_url(slot=2))` (:753, :838); CLI test `--slot 2` reported `save_02`; anchor and cast were `max(id)` and the first N characters of the owner's story | `epistemics_clone` (`qa885_epistemics`): `seed_protagonist` (base 2100-01-01), three `seed_character`, `seed_faction`, `seed_story_clock` last (head chunk at 2100-01-01T12:00Z). `epistemics_conn` rolls back per test. `_anchor_and_characters` asserts the anchor is the seeded clock and the cast names are the seeded four; the async and SQLAlchemy tests assert the anchor and entity ids equal the seeded rows; the faction test asserts the seeded faction name; the CLI test routes slot 2 to the clone with `route_slot_to_disposable` and asserts the handler reports the clone's `dbname`. The unused `slot=2` arguments to `commit_orrery_tick_*` are dropped (the body never reads `slot`: `nexus/agents/orrery/events.py:706`, `:995`) |
| `tests/test_orrery/test_claim_propagation_live.py` | `LIVE_SLOT = 5` (:48); `live_conn` on `get_slot_db_url(slot=5)` (:86); salience test `create_engine(get_slot_db_url(slot=LIVE_SLOT))` (:473); async test `asyncpg_kwargs(slot_dbname(LIVE_SLOT))` (:1181); three migration-083 `pytest.skip` guards (:105, :495, :1200); the async test's raw `INSERT INTO public.character_relationships` (:1250) had no `nexus.write_producer`, so migration 115's trigger raised on any slot | `propagation_clone` (`qa885_claim_propagation`): `seed_story_clock` first, then the async conduit pair through `seed_character` x2 and `seed_relationship` (attributed `manual`). The three skips are assertions (`_assert_migration_083`). The async test uses the seeded pair and asserts the conduit reaches the valence shadow (`associate`, `+3|trusting`, valence 3/5.5). The slot-free helpers moved to `claim_accounts_test_support.py`; `live_llm` marker unchanged |
| `tests/test_orrery/test_reveal_live.py` | `live_conn` on `get_slot_db_url(slot=5)` (:88), `pytest.skip` on unmigrated slot (:112); async test `asyncpg_kwargs(slot_dbname(5))` (:335); `_insert_private_incident` unpacked `None` on the empty `save_05` (no places, :183-184); helpers imported from the live_llm module | `reveal_clone` (`qa885_reveal`): `seed_zone`, `seed_place`, `seed_protagonist` standing there, `seed_story_clock`. The readiness skip is an assertion; `_insert_private_incident` takes the fixture's seeded `place_id` (no more lowest-id place lookup) and asserts it is `Reveal Square`; the async test asserts its clock row is the seeded clock chunk, time, and protagonist, and that the protagonist stands on the seeded place. Helpers now come from `claim_accounts_test_support.py` |
| `tests/test_orrery/test_distortion_live.py` | async test `asyncpg_kwargs(f"save_{LIVE_SLOT:02d}")` (:600); `LIVE_SLOT` and helpers imported from the live_llm module (:30-40) | async test takes `distortion_async_db` (`qa885_distortion`, `seed_protagonist`); the sync `live_conn` clone is unchanged; imports come from `claim_accounts_test_support.py`; unused `psycopg2` and `get_slot_db_url` imports removed |
| `tests/test_orrery/test_knowledge_surfacing_live.py` | `LIVE_SLOT = 5` (:37); `create_engine(get_slot_db_url(slot=LIVE_SLOT))` (:229) | `knowledge_clone` (`qa885_knowledge_surfacing`, `seed_story_clock` at 2073-08-01); `knowledge_db` asserts the head clock is the seeded clock instead of falling back to a literal |
| `tests/test_orrery/test_tag_provenance.py` | `connect(f"save_{WRITE_SLOT:02d}")` (:47), `create_engine(get_slot_db_url(slot=WRITE_SLOT))` (:259); actor and target were `save_02`'s two lowest entities; test 2 guarded its stamp checks with `if counters["applied"]:` | `provenance_clone` (`qa885_tag_provenance`): `seed_story_clock`, then actor and target `seed_character`. `_anchor_and_actors` asserts the seeded chunk and entity ids; test 1 asserts the anchor clock is the seeded time; test 2 asserts `applied == 1` and the stamp equals the seeded clock unconditionally |
| `tests/test_orrery/test_signal_events.py` | `connect(f"save_{WRITE_SLOT:02d}")` (:109), `asyncpg_kwargs(f"save_{WRITE_SLOT:02d}")` (:212) | `signal_clone` (`qa885_signal_events`): `seed_story_clock`, then avenger and target `seed_character`; both live tests assert the anchor and bound entities are the seeded rows. The three unit tests are unchanged |
| `tests/test_orrery/test_claim_awareness_replay_live.py` | `connect("NEXUS_template")` (:35) wrote `narrative_chunks`, `chunk_metadata`, `entities`, `state_checkpoints` and shadow claims to the template, rolled back | `replay_clone` (`qa885_claim_awareness_replay`, `seed_story_clock`); `replay_conn` rolls back per test |
| `tests/test_orrery/claim_accounts_test_support.py` | temp-schema claim shadows only | also holds the slot-free helpers moved from `test_claim_propagation_live.py`: `_install_valence_shadow`, `_settings`, `_insert_chunk`, `_insert_character`, `_insert_faction`, `_insert_pair_tag`, `_insert_relationship`, `_insert_claim`, `_chain`, `_canonical_rows`, `EPISTEMICS`, `_SCENE_NUMBERS`. Its docstring says the claim shadows keep `claims`, `claim_awareness` and `backstory_secrets` writes in `pg_temp`, and that `_insert_relationship` writes an attributed `public.character_relationships` row (rolled back with the caller) plus a `pg_temp` twin |
| `tests/test_orrery/test_claim_consumption_live.py`, `tests/test_orrery/test_claim_accounts_live.py` | imported the moved helpers from the `live_llm` module `test_claim_propagation_live.py` | import them from `claim_accounts_test_support.py`; no `requires_postgres` module imports from a `live_llm` module |

No replay chunk in this slice fabricated ids by `max(id)+1`: every fixture chunk already used `INSERT ... RETURNING id`. The remaining `max(id)` reads are anchor reads, now asserted equal to the seeded clock chunk. `_insert_faction` keeps `COALESCE(max(id), 0) + 1`, the production allocation for `factions` (no sequence).

## Audit Grep

```
$ for f in test_epistemics test_claim_propagation_live test_reveal_live test_distortion_live \
    test_knowledge_surfacing_live test_tag_provenance test_signal_events \
    test_claim_awareness_replay_live claim_accounts_test_support; do
    grep -n "save_0\|NEXUS_template\|get_slot_db_url(slot=\|slot_dbname([1-5])\|LIVE_SLOT" tests/test_orrery/$f.py
  done
(no output)
```

The epistemics CLI tests still pass `--slot 2`: the handler test routes that slot to the clone; `test_record_revelation_cli_requires_knower_flag_without_legacy_alias` only parses argv (offline label).

## Sequence Proof

Read-only (`PGOPTIONS='-c default_transaction_read_only=on'`), immediately before and after each slice run:

```sql
SELECT sequencename, last_value FROM pg_sequences
WHERE schemaname = 'public' ORDER BY sequencename;
SELECT 'narrative_chunks', count(*) FROM narrative_chunks
UNION ALL SELECT 'entities', count(*) FROM entities
UNION ALL SELECT 'world_events', count(*) FROM world_events
UNION ALL SELECT 'entity_tags', count(*) FROM entity_tags;
```

A poller recorded every backend on `save_02`, `save_05` and `NEXUS_template` every 0.2 s while pytest ran. Every backend carrying the pytest PID in its `application_name` (`nexus:<role>:<pid>`) was `nexus:subprocess:<pid>` on `NEXUS_template` running `pg_dump -s` catalog reads under `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, which is how `disposable_slot_database` clones the template. No backend from the run touched `save_02` or `save_05`.

| Run | Command | Before vs after |
| --- | --- | --- |
| `pg3` (pytest PID 52005) | `NEXUS_RUN_POSTGRES=1` on the eight modules | identical |
| `pg4` (rerun at `23c16622`, pytest PID 5313) | adds `NEXUS_RUN_LIVE_LLM=1 NEXUS_TEST_PROVIDER_ONLY=1` | identical; listings below |

Between runs the owner sequences did move: other builders' gates and this session's full `tests/test_orrery` run exercise still-unconverted modules (later B2 slices), so a before/after window that spans them is not a proof of this slice. Two examples: `save_05` `characters_id_seq` moved 2466 to 2471 while no run of mine was active, and `NEXUS_template` `narrative_chunks_id_seq` moved 1398 to 1401 across this session's full-tier run (see Open Items).

The `pg3` listings read `sequencename, last_value`; the `pg4` listings use the order's exact query, which adds `schemaname`.

Before `pg3`:

```
### save_02
ai_notebook_id_seq | 
backstory_secrets_id_seq | 
character_experience_jobs_id_seq | 
character_experiences_id_seq | 
character_identity_rulings_id_seq | 
character_project_states_id_seq | 3384
character_relationships_id_seq | 7
character_routine_anchors_id_seq | 
characters_id_seq | 101
chunk_metadata_id_seq | 8582
claim_awareness_id_seq | 1044
claims_id_seq | 475
correspondence_compaction_jobs_id_seq | 
entities_id_seq | 561
entity_pair_tags_id_seq | 3475
entity_tags_id_seq | 1137
generation_session_phases_id_seq | 
interaction_authorizations_id_seq | 
interaction_events_id_seq | 
interaction_participants_id_seq | 
items_id_seq | 
layers_id_seq | 1
narrative_chunks_id_seq | 2620
narrative_embedding_jobs_id_seq | 
narrative_summary_jobs_id_seq | 
offscreen_narrations_id_seq | 
orrery_adjudication_log_id_seq | 537
orrery_maturation_jobs_id_seq | 504
orrery_narration_jobs_id_seq | 
orrery_prompt_exposures_id_seq | 3146
orrery_recall_trace_id_seq | 
orrery_resolutions_id_seq | 7175
orrery_route_graph_edges_id_seq | 
orrery_route_graph_nodes_id_seq | 
orrery_scene_pressures_id_seq | 537
orrery_travel_edges_id_seq | 
pair_tags_id_seq | 29
places_id_seq | 4
relationship_versions_id_seq | 100056
retrieval_coverage_log_id_seq | 52
retrograde_summaries_id_seq | 1435
state_checkpoints_id_seq | 2944
state_delta_log_id_seq | 33
storyteller_correspondence_letters_id_seq | 
tag_clearance_log_id_seq | 1054
tags_id_seq | 556
world_events_id_seq | 8110
zones_id_seq | 1
--- counts
narrative_chunks | 1425
entities | 121
world_events | 0
entity_tags | 0
### save_05
ai_notebook_id_seq | 
backstory_secrets_id_seq | 
character_experience_jobs_id_seq | 
character_experiences_id_seq | 
character_identity_rulings_id_seq | 
character_project_states_id_seq | 
character_relationships_id_seq | 
character_routine_anchors_id_seq | 
characters_id_seq | 2476
chunk_metadata_id_seq | 2234
claim_awareness_id_seq | 
claims_id_seq | 
correspondence_compaction_jobs_id_seq | 
entities_id_seq | 5484
entity_pair_tags_id_seq | 780
entity_tags_id_seq | 41
generation_session_phases_id_seq | 
interaction_authorizations_id_seq | 
interaction_events_id_seq | 
interaction_participants_id_seq | 
items_id_seq | 
layers_id_seq | 
narrative_chunks_id_seq | 2340
narrative_embedding_jobs_id_seq | 
narrative_summary_jobs_id_seq | 
offscreen_narrations_id_seq | 
orrery_adjudication_log_id_seq | 
orrery_maturation_jobs_id_seq | 
orrery_narration_jobs_id_seq | 
orrery_prompt_exposures_id_seq | 
orrery_recall_trace_id_seq | 2056
orrery_resolutions_id_seq | 
orrery_route_graph_edges_id_seq | 
orrery_route_graph_nodes_id_seq | 
orrery_scene_pressures_id_seq | 
orrery_travel_edges_id_seq | 
pair_tags_id_seq | 387
places_id_seq | 
relationship_versions_id_seq | 12
retrieval_coverage_log_id_seq | 
retrograde_summaries_id_seq | 
state_checkpoints_id_seq | 244
state_delta_log_id_seq | 
storyteller_correspondence_letters_id_seq | 
tag_clearance_log_id_seq | 156
tags_id_seq | 20092
world_events_id_seq | 3146
zones_id_seq | 
--- counts
narrative_chunks | 0
entities | 0
world_events | 0
entity_tags | 0
### NEXUS_template
ai_notebook_id_seq | 
backstory_secrets_id_seq | 
character_experience_jobs_id_seq | 
character_experiences_id_seq | 
character_identity_rulings_id_seq | 
character_project_states_id_seq | 2
character_relationships_id_seq | 
character_routine_anchors_id_seq | 
characters_id_seq | 
chunk_metadata_id_seq | 1359
claim_awareness_id_seq | 672
claims_id_seq | 319
correspondence_compaction_jobs_id_seq | 
entities_id_seq | 2484
entity_pair_tags_id_seq | 
entity_tags_id_seq | 
generation_session_phases_id_seq | 
interaction_authorizations_id_seq | 
interaction_events_id_seq | 
interaction_participants_id_seq | 
items_id_seq | 
layers_id_seq | 
narrative_chunks_id_seq | 1401
narrative_embedding_jobs_id_seq | 
narrative_summary_jobs_id_seq | 
offscreen_narrations_id_seq | 
orrery_adjudication_log_id_seq | 
orrery_maturation_jobs_id_seq | 
orrery_narration_jobs_id_seq | 
orrery_prompt_exposures_id_seq | 
orrery_recall_trace_id_seq | 
orrery_resolutions_id_seq | 
orrery_route_graph_edges_id_seq | 
orrery_route_graph_nodes_id_seq | 
orrery_scene_pressures_id_seq | 
orrery_travel_edges_id_seq | 
pair_tags_id_seq | 29
places_id_seq | 
relationship_versions_id_seq | 
retrieval_coverage_log_id_seq | 
retrograde_summaries_id_seq | 
state_checkpoints_id_seq | 714
state_delta_log_id_seq | 
storyteller_correspondence_letters_id_seq | 
tag_clearance_log_id_seq | 
tags_id_seq | 532
world_events_id_seq | 1003
zones_id_seq | 
--- counts
narrative_chunks | 0
entities | 0
world_events | 0
entity_tags | 0
```

After `pg3` (identical to the listing above; `diff` exit 0):

```
### save_02
ai_notebook_id_seq | 
backstory_secrets_id_seq | 
character_experience_jobs_id_seq | 
character_experiences_id_seq | 
character_identity_rulings_id_seq | 
character_project_states_id_seq | 3384
character_relationships_id_seq | 7
character_routine_anchors_id_seq | 
characters_id_seq | 101
chunk_metadata_id_seq | 8582
claim_awareness_id_seq | 1044
claims_id_seq | 475
correspondence_compaction_jobs_id_seq | 
entities_id_seq | 561
entity_pair_tags_id_seq | 3475
entity_tags_id_seq | 1137
generation_session_phases_id_seq | 
interaction_authorizations_id_seq | 
interaction_events_id_seq | 
interaction_participants_id_seq | 
items_id_seq | 
layers_id_seq | 1
narrative_chunks_id_seq | 2620
narrative_embedding_jobs_id_seq | 
narrative_summary_jobs_id_seq | 
offscreen_narrations_id_seq | 
orrery_adjudication_log_id_seq | 537
orrery_maturation_jobs_id_seq | 504
orrery_narration_jobs_id_seq | 
orrery_prompt_exposures_id_seq | 3146
orrery_recall_trace_id_seq | 
orrery_resolutions_id_seq | 7175
orrery_route_graph_edges_id_seq | 
orrery_route_graph_nodes_id_seq | 
orrery_scene_pressures_id_seq | 537
orrery_travel_edges_id_seq | 
pair_tags_id_seq | 29
places_id_seq | 4
relationship_versions_id_seq | 100056
retrieval_coverage_log_id_seq | 52
retrograde_summaries_id_seq | 1435
state_checkpoints_id_seq | 2944
state_delta_log_id_seq | 33
storyteller_correspondence_letters_id_seq | 
tag_clearance_log_id_seq | 1054
tags_id_seq | 556
world_events_id_seq | 8110
zones_id_seq | 1
--- counts
narrative_chunks | 1425
entities | 121
world_events | 0
entity_tags | 0
### save_05
ai_notebook_id_seq | 
backstory_secrets_id_seq | 
character_experience_jobs_id_seq | 
character_experiences_id_seq | 
character_identity_rulings_id_seq | 
character_project_states_id_seq | 
character_relationships_id_seq | 
character_routine_anchors_id_seq | 
characters_id_seq | 2476
chunk_metadata_id_seq | 2234
claim_awareness_id_seq | 
claims_id_seq | 
correspondence_compaction_jobs_id_seq | 
entities_id_seq | 5484
entity_pair_tags_id_seq | 780
entity_tags_id_seq | 41
generation_session_phases_id_seq | 
interaction_authorizations_id_seq | 
interaction_events_id_seq | 
interaction_participants_id_seq | 
items_id_seq | 
layers_id_seq | 
narrative_chunks_id_seq | 2340
narrative_embedding_jobs_id_seq | 
narrative_summary_jobs_id_seq | 
offscreen_narrations_id_seq | 
orrery_adjudication_log_id_seq | 
orrery_maturation_jobs_id_seq | 
orrery_narration_jobs_id_seq | 
orrery_prompt_exposures_id_seq | 
orrery_recall_trace_id_seq | 2056
orrery_resolutions_id_seq | 
orrery_route_graph_edges_id_seq | 
orrery_route_graph_nodes_id_seq | 
orrery_scene_pressures_id_seq | 
orrery_travel_edges_id_seq | 
pair_tags_id_seq | 387
places_id_seq | 
relationship_versions_id_seq | 12
retrieval_coverage_log_id_seq | 
retrograde_summaries_id_seq | 
state_checkpoints_id_seq | 244
state_delta_log_id_seq | 
storyteller_correspondence_letters_id_seq | 
tag_clearance_log_id_seq | 156
tags_id_seq | 20092
world_events_id_seq | 3146
zones_id_seq | 
--- counts
narrative_chunks | 0
entities | 0
world_events | 0
entity_tags | 0
### NEXUS_template
ai_notebook_id_seq | 
backstory_secrets_id_seq | 
character_experience_jobs_id_seq | 
character_experiences_id_seq | 
character_identity_rulings_id_seq | 
character_project_states_id_seq | 2
character_relationships_id_seq | 
character_routine_anchors_id_seq | 
characters_id_seq | 
chunk_metadata_id_seq | 1359
claim_awareness_id_seq | 672
claims_id_seq | 319
correspondence_compaction_jobs_id_seq | 
entities_id_seq | 2484
entity_pair_tags_id_seq | 
entity_tags_id_seq | 
generation_session_phases_id_seq | 
interaction_authorizations_id_seq | 
interaction_events_id_seq | 
interaction_participants_id_seq | 
items_id_seq | 
layers_id_seq | 
narrative_chunks_id_seq | 1401
narrative_embedding_jobs_id_seq | 
narrative_summary_jobs_id_seq | 
offscreen_narrations_id_seq | 
orrery_adjudication_log_id_seq | 
orrery_maturation_jobs_id_seq | 
orrery_narration_jobs_id_seq | 
orrery_prompt_exposures_id_seq | 
orrery_recall_trace_id_seq | 
orrery_resolutions_id_seq | 
orrery_route_graph_edges_id_seq | 
orrery_route_graph_nodes_id_seq | 
orrery_scene_pressures_id_seq | 
orrery_travel_edges_id_seq | 
pair_tags_id_seq | 29
places_id_seq | 
relationship_versions_id_seq | 
retrieval_coverage_log_id_seq | 
retrograde_summaries_id_seq | 
state_checkpoints_id_seq | 714
state_delta_log_id_seq | 
storyteller_correspondence_letters_id_seq | 
tag_clearance_log_id_seq | 
tags_id_seq | 532
world_events_id_seq | 1003
zones_id_seq | 
--- counts
narrative_chunks | 0
entities | 0
world_events | 0
entity_tags | 0
```

The first `pg4` run (PID 54465) kept no listing, so the live-opted command was rerun at `23c16622` inside its own read-only window. The rerun is the only run that executes the 19 `test_claim_propagation_live.py` tests, which `pg3` skips by their `live_llm` marker. The window script first waits until no other `python -m pytest` process is running (it waited 305 s for other builders' gates), then snapshots, runs pytest, and snapshots again. An earlier ad-hoc attempt at 03:20:49Z, taken while another builder's `tests/test_orrery` gate (PID 85538) was running, saw `save_02` `world_events_id_seq`, `orrery_resolutions_id_seq` and `orrery_prompt_exposures_id_seq` advance; a window that overlaps another gate proves nothing about this slice, so that attempt is not used.

```
$ NEXUS_RUN_POSTGRES=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_TEST_PROVIDER_ONLY=1 python -m pytest -q <the eight modules>
....................................................................     [100%]
secret-store guard: active; nexus-api: read-only (live LLM); disposable keychain: denied
68 passed, 5 warnings in 18.25s
```

Window 2026-09-30T03:26:50Z to 03:27:09Z. The 0.2 s `pg_stat_activity` poller logged four samples with a backend on an owner database. All four were `nexus:subprocess:5313` on `NEXUS_template` running `pg_dump -s` catalog reads (`pg_depend`, `pg_constraint`, `pg_attrdef`), which is the clone step of `disposable_slot_database`. No backend touched `save_02` or `save_05`.

```
$ diff before_pg4.txt after_pg4.txt; echo "diff exit $?"
diff exit 0
```

Before `pg4`:

```
### save_02
public | ai_notebook_id_seq | 
public | backstory_secrets_id_seq | 
public | character_experience_jobs_id_seq | 
public | character_experiences_id_seq | 
public | character_identity_rulings_id_seq | 
public | character_project_states_id_seq | 3404
public | character_relationships_id_seq | 7
public | character_routine_anchors_id_seq | 
public | characters_id_seq | 101
public | chunk_metadata_id_seq | 8617
public | claim_awareness_id_seq | 1044
public | claims_id_seq | 475
public | correspondence_compaction_jobs_id_seq | 
public | entities_id_seq | 561
public | entity_pair_tags_id_seq | 3495
public | entity_tags_id_seq | 1143
public | generation_session_phases_id_seq | 
public | interaction_authorizations_id_seq | 
public | interaction_events_id_seq | 
public | interaction_participants_id_seq | 
public | items_id_seq | 
public | layers_id_seq | 1
public | narrative_chunks_id_seq | 2621
public | narrative_embedding_jobs_id_seq | 
public | narrative_summary_jobs_id_seq | 
public | offscreen_narrations_id_seq | 
public | orrery_adjudication_log_id_seq | 543
public | orrery_maturation_jobs_id_seq | 504
public | orrery_narration_jobs_id_seq | 
public | orrery_prompt_exposures_id_seq | 3167
public | orrery_recall_trace_id_seq | 
public | orrery_resolutions_id_seq | 7232
public | orrery_route_graph_edges_id_seq | 
public | orrery_route_graph_nodes_id_seq | 
public | orrery_scene_pressures_id_seq | 543
public | orrery_travel_edges_id_seq | 
public | pair_tags_id_seq | 29
public | places_id_seq | 4
public | relationship_versions_id_seq | 100093
public | retrieval_coverage_log_id_seq | 52
public | retrograde_summaries_id_seq | 1435
public | state_checkpoints_id_seq | 2957
public | state_delta_log_id_seq | 33
public | storyteller_correspondence_letters_id_seq | 
public | tag_clearance_log_id_seq | 1059
public | tags_id_seq | 556
public | world_events_id_seq | 8128
public | zones_id_seq | 1
--- counts
narrative_chunks | 1425
entities | 121
world_events | 0
entity_tags | 0
### save_05
public | ai_notebook_id_seq | 
public | backstory_secrets_id_seq | 
public | character_experience_jobs_id_seq | 
public | character_experiences_id_seq | 
public | character_identity_rulings_id_seq | 
public | character_project_states_id_seq | 
public | character_relationships_id_seq | 
public | character_routine_anchors_id_seq | 
public | characters_id_seq | 2488
public | chunk_metadata_id_seq | 2272
public | claim_awareness_id_seq | 
public | claims_id_seq | 
public | correspondence_compaction_jobs_id_seq | 
public | entities_id_seq | 5502
public | entity_pair_tags_id_seq | 780
public | entity_tags_id_seq | 41
public | generation_session_phases_id_seq | 
public | interaction_authorizations_id_seq | 
public | interaction_events_id_seq | 
public | interaction_participants_id_seq | 
public | items_id_seq | 
public | layers_id_seq | 
public | narrative_chunks_id_seq | 2378
public | narrative_embedding_jobs_id_seq | 
public | narrative_summary_jobs_id_seq | 
public | offscreen_narrations_id_seq | 
public | orrery_adjudication_log_id_seq | 
public | orrery_maturation_jobs_id_seq | 
public | orrery_narration_jobs_id_seq | 
public | orrery_prompt_exposures_id_seq | 
public | orrery_recall_trace_id_seq | 2088
public | orrery_resolutions_id_seq | 
public | orrery_route_graph_edges_id_seq | 
public | orrery_route_graph_nodes_id_seq | 
public | orrery_scene_pressures_id_seq | 
public | orrery_travel_edges_id_seq | 
public | pair_tags_id_seq | 387
public | places_id_seq | 
public | relationship_versions_id_seq | 12
public | retrieval_coverage_log_id_seq | 
public | retrograde_summaries_id_seq | 
public | state_checkpoints_id_seq | 246
public | state_delta_log_id_seq | 
public | storyteller_correspondence_letters_id_seq | 
public | tag_clearance_log_id_seq | 156
public | tags_id_seq | 20092
public | world_events_id_seq | 3194
public | zones_id_seq | 
--- counts
narrative_chunks | 0
entities | 0
world_events | 0
entity_tags | 0
### NEXUS_template
public | ai_notebook_id_seq | 
public | backstory_secrets_id_seq | 
public | character_experience_jobs_id_seq | 
public | character_experiences_id_seq | 
public | character_identity_rulings_id_seq | 
public | character_project_states_id_seq | 2
public | character_relationships_id_seq | 
public | character_routine_anchors_id_seq | 
public | characters_id_seq | 
public | chunk_metadata_id_seq | 1369
public | claim_awareness_id_seq | 672
public | claims_id_seq | 319
public | correspondence_compaction_jobs_id_seq | 
public | entities_id_seq | 2505
public | entity_pair_tags_id_seq | 
public | entity_tags_id_seq | 
public | generation_session_phases_id_seq | 
public | interaction_authorizations_id_seq | 
public | interaction_events_id_seq | 
public | interaction_participants_id_seq | 
public | items_id_seq | 
public | layers_id_seq | 
public | narrative_chunks_id_seq | 1411
public | narrative_embedding_jobs_id_seq | 
public | narrative_summary_jobs_id_seq | 
public | offscreen_narrations_id_seq | 
public | orrery_adjudication_log_id_seq | 
public | orrery_maturation_jobs_id_seq | 
public | orrery_narration_jobs_id_seq | 
public | orrery_prompt_exposures_id_seq | 
public | orrery_recall_trace_id_seq | 
public | orrery_resolutions_id_seq | 
public | orrery_route_graph_edges_id_seq | 
public | orrery_route_graph_nodes_id_seq | 
public | orrery_scene_pressures_id_seq | 
public | orrery_travel_edges_id_seq | 
public | pair_tags_id_seq | 29
public | places_id_seq | 
public | relationship_versions_id_seq | 
public | retrieval_coverage_log_id_seq | 
public | retrograde_summaries_id_seq | 
public | state_checkpoints_id_seq | 718
public | state_delta_log_id_seq | 
public | storyteller_correspondence_letters_id_seq | 
public | tag_clearance_log_id_seq | 
public | tags_id_seq | 532
public | world_events_id_seq | 1011
public | zones_id_seq | 
--- counts
narrative_chunks | 0
entities | 0
world_events | 0
entity_tags | 0
```

After `pg4` (identical to the listing above; `diff` exit 0):

```
### save_02
public | ai_notebook_id_seq | 
public | backstory_secrets_id_seq | 
public | character_experience_jobs_id_seq | 
public | character_experiences_id_seq | 
public | character_identity_rulings_id_seq | 
public | character_project_states_id_seq | 3404
public | character_relationships_id_seq | 7
public | character_routine_anchors_id_seq | 
public | characters_id_seq | 101
public | chunk_metadata_id_seq | 8617
public | claim_awareness_id_seq | 1044
public | claims_id_seq | 475
public | correspondence_compaction_jobs_id_seq | 
public | entities_id_seq | 561
public | entity_pair_tags_id_seq | 3495
public | entity_tags_id_seq | 1143
public | generation_session_phases_id_seq | 
public | interaction_authorizations_id_seq | 
public | interaction_events_id_seq | 
public | interaction_participants_id_seq | 
public | items_id_seq | 
public | layers_id_seq | 1
public | narrative_chunks_id_seq | 2621
public | narrative_embedding_jobs_id_seq | 
public | narrative_summary_jobs_id_seq | 
public | offscreen_narrations_id_seq | 
public | orrery_adjudication_log_id_seq | 543
public | orrery_maturation_jobs_id_seq | 504
public | orrery_narration_jobs_id_seq | 
public | orrery_prompt_exposures_id_seq | 3167
public | orrery_recall_trace_id_seq | 
public | orrery_resolutions_id_seq | 7232
public | orrery_route_graph_edges_id_seq | 
public | orrery_route_graph_nodes_id_seq | 
public | orrery_scene_pressures_id_seq | 543
public | orrery_travel_edges_id_seq | 
public | pair_tags_id_seq | 29
public | places_id_seq | 4
public | relationship_versions_id_seq | 100093
public | retrieval_coverage_log_id_seq | 52
public | retrograde_summaries_id_seq | 1435
public | state_checkpoints_id_seq | 2957
public | state_delta_log_id_seq | 33
public | storyteller_correspondence_letters_id_seq | 
public | tag_clearance_log_id_seq | 1059
public | tags_id_seq | 556
public | world_events_id_seq | 8128
public | zones_id_seq | 1
--- counts
narrative_chunks | 1425
entities | 121
world_events | 0
entity_tags | 0
### save_05
public | ai_notebook_id_seq | 
public | backstory_secrets_id_seq | 
public | character_experience_jobs_id_seq | 
public | character_experiences_id_seq | 
public | character_identity_rulings_id_seq | 
public | character_project_states_id_seq | 
public | character_relationships_id_seq | 
public | character_routine_anchors_id_seq | 
public | characters_id_seq | 2488
public | chunk_metadata_id_seq | 2272
public | claim_awareness_id_seq | 
public | claims_id_seq | 
public | correspondence_compaction_jobs_id_seq | 
public | entities_id_seq | 5502
public | entity_pair_tags_id_seq | 780
public | entity_tags_id_seq | 41
public | generation_session_phases_id_seq | 
public | interaction_authorizations_id_seq | 
public | interaction_events_id_seq | 
public | interaction_participants_id_seq | 
public | items_id_seq | 
public | layers_id_seq | 
public | narrative_chunks_id_seq | 2378
public | narrative_embedding_jobs_id_seq | 
public | narrative_summary_jobs_id_seq | 
public | offscreen_narrations_id_seq | 
public | orrery_adjudication_log_id_seq | 
public | orrery_maturation_jobs_id_seq | 
public | orrery_narration_jobs_id_seq | 
public | orrery_prompt_exposures_id_seq | 
public | orrery_recall_trace_id_seq | 2088
public | orrery_resolutions_id_seq | 
public | orrery_route_graph_edges_id_seq | 
public | orrery_route_graph_nodes_id_seq | 
public | orrery_scene_pressures_id_seq | 
public | orrery_travel_edges_id_seq | 
public | pair_tags_id_seq | 387
public | places_id_seq | 
public | relationship_versions_id_seq | 12
public | retrieval_coverage_log_id_seq | 
public | retrograde_summaries_id_seq | 
public | state_checkpoints_id_seq | 246
public | state_delta_log_id_seq | 
public | storyteller_correspondence_letters_id_seq | 
public | tag_clearance_log_id_seq | 156
public | tags_id_seq | 20092
public | world_events_id_seq | 3194
public | zones_id_seq | 
--- counts
narrative_chunks | 0
entities | 0
world_events | 0
entity_tags | 0
### NEXUS_template
public | ai_notebook_id_seq | 
public | backstory_secrets_id_seq | 
public | character_experience_jobs_id_seq | 
public | character_experiences_id_seq | 
public | character_identity_rulings_id_seq | 
public | character_project_states_id_seq | 2
public | character_relationships_id_seq | 
public | character_routine_anchors_id_seq | 
public | characters_id_seq | 
public | chunk_metadata_id_seq | 1369
public | claim_awareness_id_seq | 672
public | claims_id_seq | 319
public | correspondence_compaction_jobs_id_seq | 
public | entities_id_seq | 2505
public | entity_pair_tags_id_seq | 
public | entity_tags_id_seq | 
public | generation_session_phases_id_seq | 
public | interaction_authorizations_id_seq | 
public | interaction_events_id_seq | 
public | interaction_participants_id_seq | 
public | items_id_seq | 
public | layers_id_seq | 
public | narrative_chunks_id_seq | 1411
public | narrative_embedding_jobs_id_seq | 
public | narrative_summary_jobs_id_seq | 
public | offscreen_narrations_id_seq | 
public | orrery_adjudication_log_id_seq | 
public | orrery_maturation_jobs_id_seq | 
public | orrery_narration_jobs_id_seq | 
public | orrery_prompt_exposures_id_seq | 
public | orrery_recall_trace_id_seq | 
public | orrery_resolutions_id_seq | 
public | orrery_route_graph_edges_id_seq | 
public | orrery_route_graph_nodes_id_seq | 
public | orrery_scene_pressures_id_seq | 
public | orrery_travel_edges_id_seq | 
public | pair_tags_id_seq | 29
public | places_id_seq | 
public | relationship_versions_id_seq | 
public | retrieval_coverage_log_id_seq | 
public | retrograde_summaries_id_seq | 
public | state_checkpoints_id_seq | 718
public | state_delta_log_id_seq | 
public | storyteller_correspondence_letters_id_seq | 
public | tag_clearance_log_id_seq | 
public | tags_id_seq | 532
public | world_events_id_seq | 1011
public | zones_id_seq | 
--- counts
narrative_chunks | 0
entities | 0
world_events | 0
entity_tags | 0
```

## Gates

Slice modules, PostgreSQL gate, gateway variables unset:

```
$ NEXUS_RUN_POSTGRES=1 python -m pytest -q tests/test_orrery/test_epistemics.py \
    tests/test_orrery/test_claim_propagation_live.py tests/test_orrery/test_reveal_live.py \
    tests/test_orrery/test_distortion_live.py tests/test_orrery/test_knowledge_surfacing_live.py \
    tests/test_orrery/test_tag_provenance.py tests/test_orrery/test_signal_events.py \
    tests/test_orrery/test_claim_awareness_replay_live.py
.................sssssssssssssssssss................................     [100%]
secret-store guard: active; nexus-api: denied; disposable keychain: denied
49 passed, 19 skipped, 5 warnings in 19.05s
```

The 19 skips are `test_claim_propagation_live.py`, whose `live_llm` marker stays. With the opt-in:

```
$ NEXUS_RUN_POSTGRES=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_TEST_PROVIDER_ONLY=1 python -m pytest -q <same eight modules>
....................................................................     [100%]
secret-store guard: active; nexus-api: read-only (live LLM); disposable keychain: denied
68 passed, 5 warnings in 20.40s
```

Rerun at `23c16622` (the `pg4` window above): `68 passed, 5 warnings in 18.25s`. The plain run at the same commit: `49 passed, 19 skipped, 5 warnings in 16.97s`.

`tests/secret_store_guard.py:691` prints `read-only (live LLM)` whenever `NEXUS_RUN_LIVE_LLM=1`, so this run cannot print `denied`; `docs/agent_workflow.md` requires the flag unset for the `denied` line. No test in these modules calls a provider.

Full Orrery PostgreSQL tier on the final code (`NEXUS_RUN_POSTGRES=1 python -m pytest -q -rfE tests/test_orrery`, gateway variables unset):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
3 failed, 1613 passed, 39 skipped, 7 warnings, 9 errors in 273.98s (0:04:33)
```

All twelve fall into the #885 empty-owner-slot class that the issue's 2026-09-29 comments already list for later slices, and none is in this slice's files: `test_adjudication_history` (B2-5, marked "cannot be made honest"), `test_evidence` and `test_tag_library` (B2-7), `test_faction_project_contexts_live` x8 and `test_polymorphic_patron_live` (B2-4). The `test_reveal_live` x9 entry on that list no longer fails. No new failure.

Offline gates:

```
$ python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2441 passed, 355 skipped, 8 warnings in 361.61s (0:06:01)
$ python -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1807 passed, 726 skipped, 7 warnings in 31.30s
$ python -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.68s
```

After the review fixes (`23c16622`), `NEXUS_RUN_POSTGRES=1 python -m pytest -q tests/test_orrery/test_reveal_live.py tests/test_orrery/test_claim_consumption_live.py tests/test_orrery/test_claim_accounts_live.py` gives `24 passed, 5 warnings in 5.95s` (`secret-store guard: active; nexus-api: denied; disposable keychain: denied`). Black and flake8 are clean on the five files that commit touched. `mypy --explicit-package-bases` on them reports two `union-attr` errors, `test_claim_accounts_live.py:117` and `test_claim_consumption_live.py:71` (`connection.connection.cursor()`); the same command on the base versions of those two files reports the same two errors (`:117`, `:73`), so they predate this slice, and only the import lines of those files changed.

Changed files (first round): `black --check` reports 9 files unchanged; `flake8` is clean; `mypy --explicit-package-bases` reports `Success: no issues found in 9 source files`. On the base, the same mypy command reported nine errors in these files: `None`-unpack and `driver_connection` union errors, the `RetrogradeExpansionParticipant.role` literal, and an untyped `asyncpg` import. All nine are fixed here.

## #885 Ids Retired

From the canonical named list (2026-09-24 comment): `tests/test_orrery/test_reveal_live.py` x9, now green in the plain PostgreSQL gate, and `tests/test_orrery/test_claim_propagation_live.py` x19, green whenever its `live_llm` marker admits it. The #964 disposition also routed `test_epistemics` x12, `test_tag_provenance` x4 and `test_signal_events` x2 here because they depended on `save_02`'s content; they now depend on seeded rows only.

## Open Items

- `tests/test_orrery/test_stage2a_epistemics_live.py:26` sets `LIVE_DATABASE = "NEXUS_template"` and writes chunks, entities and world events to the template in rolled-back transactions under plain `requires_postgres`. The B2 map does not list it. The window containing this session's full-tier run advanced `NEXUS_template` `narrative_chunks_id_seq` 1398 to 1401, `world_events_id_seq` 1000 to 1003 and `entities_id_seq` 2475 to 2484, which matches its three tests. It needs the same conversion in a later slice.
- The `live_llm` markers on `test_claim_propagation_live.py` stay, per the order. It makes no inference call.
