# Remaining Rolled-Back Owner Writers Leave the Owner Slots: Verification

Work order 885-B2-5. Issue #885 (comments "Slice B2 Mapped: Nine Ordered Slices", slice B2-5, and "B2-1 Landed (PR #1034)", which added `test_stage2a_epistemics_live.py`). Base: `origin/main` at `3e8e692e`. Test-only: no migration, no gateway lane, no paid calls (every clone is TEST-pinned). Every PostgreSQL run below had `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset.

## What Was Wrong (on `3e8e692e`)

| Module | Owner target | Failure or write |
| --- | --- | --- |
| `tests/test_trait_compiler_integration.py` | `TEST_DBNAME = "save_05"` (:48), `connect(TEST_DBNAME)` in all five tests | All five fail on the empty slot: `_insert_protagonist` fires the need-state trigger (`need-clock anchor unavailable`). Rolled-back writes to `characters`, `entities`, `places`, `factions`, `entity_pair_tags`, `entity_tags`, `character_need_states` advance `save_05` sequences. `_install_valence_shadow` (:60-128) shadowed `character_relationships` in `pg_temp`, so the real valence and provenance triggers never ran. |
| `tests/test_orrery/test_stage2a_status_live.py` (live_llm) | `LIVE_SLOT = 5` (:39); `get_slot_db_url(slot=LIVE_SLOT)` (:47); `enumerate_seed_eligible_vocabulary(slot_dbname(LIVE_SLOT))` (:113-115); `resolve_enqueued_seat(..., slot=5)` via `enqueue_declared_entity_maturations` | All five fail under `NEXUS_RUN_LIVE_LLM=1` on the empty slot (need clock, `_active_faction` `.one()`, `int(None)` from `max(id)`). |
| `tests/test_orrery/test_stage2a_epistemics_live.py` | `LIVE_DATABASE = "NEXUS_template"` (:26) | Three tests insert chunks, entities, and world events into the template and roll back, advancing the template's `narrative_chunks`, `entities`, and `world_events` sequences on every run. |
| `tests/test_lore/test_retrieval_coverage_live.py` | `LIVE_SLOT = 5` (:18), `get_slot_db_url(slot=LIVE_SLOT)` (:42) | Re-runs migration 075's DDL in the owner slot (:52) and asserts `len(rows) == 2` (:145) against a writer that moved in #903 to `record_rendered_coverage` (`nexus/memory/manager.py:1136`), so it fails on every slot; on `save_05` it fails first on the need clock. |
| `tests/test_lore/test_intertitle_live.py` | `LIVE_SLOT = 2` (:20), engines at :24 and :52 (never disposed) | Reads the owner's anchor chunk and player; the prologue test inserts into `narrative_chunks` and rolls back (the sequence advances). The location assertion was conditional (:38). |
| `tests/test_faction_table_audit.py` | `TEST_DBNAME = "save_02"` (:32), `get_connection` (:295-304), `cli.run_faction_audit(Namespace(slot=2))`, `psycopg2.connect(get_slot_db_url(dbname=TEST_DBNAME))` (:967) | Audits the owner's factions; asserts `dbname == "save_02"` (:634); skips the write test when no faction exists (:985); the legacy-category assertions (:441-459) pass vacuously without a deprecated-category faction tag. The write test advances `tags_id_seq` and `entity_tags_id_seq`. |
| `tests/test_orrery/test_adjudication_history.py` | `WRITE_SLOT = 2`, `HISTORY_SLOTS = (2, 5)` (:40-45) | The commit test rolls back `orrery_resolutions`, `orrery_adjudication_log`, `orrery_scene_pressures`, `orrery_prompt_exposures`, and `world_events` writes on `save_02` (sequences advance). The oracle reads both owner slots (vacuous on both: neither holds a ruling). `test_history_is_non_vacuous_on_audited_slots` (:324-338) asserts the owner slots hold Skald rulings and fails today. |

Per-module file:line detail is in `temp/orders_2026_09_29/b2_map.json` in the coordinator's tree. The base modules were not re-run here: each would advance the owner sequences this slice exists to protect.

## What Changed

### Shared Helpers (`tests/pg_fixtures.py`)

- `seed_adjudication_ledger(dbname, *, actor_entity_id, ticks) -> AdjudicationLedgerSeed(tick_chunk_ids, resolutions, adjudication_log_ids, streaks, scene_pressure_ids, prompt_exposure_ids)`. It refuses owner databases first, then commits one `commit_orrery_tick_sync` per tick with adjudications, then `promote_pending_resolutions_sync(limit=2)` and `drain_narration_outbox_sync` (deterministic descriptors; no provider call). Modeled on `tests/test_orrery/test_live_cycle.py:98-160`. The committed ledger: on the first tick a salient `hide` (promoted, narration `succeeded`) and a below-threshold `stroll` (skipped, narration `none`), with thresholds read from `[orrery.promote]`; on the second tick an `eat` ratified after a deferral and a `sleep` committed by a replace with a delta (both pending); a `drink` deferred then voided; a `work` deferred on every tick (open); one scene pressure per tick and the prompt exposures each tick renders under `[orrery.prompt]`. `ticks` must be two or more ascending chunk ids, the actor must be a character, and the save must hold no pending resolution. Every row is read back and asserted; `resolutions` maps each id to `(promotion_status, narration_status)` and `streaks` maps each proposal id to `(outcome, length)`.
- `seed_legacy_faction_tag(dbname, *, faction_entity_id, category="legitimacy_status", tag) -> int`. The one seed allowed to plant a deprecated-category tag (its docstring says so). It accepts only migration 043's legacy faction categories (`LEGACY_TAG_CATEGORIES`), registers `(category, 'faction')` as deprecated if absent, inserts the `tags` row if the tag is new (an existing tag must already sit in `category`), bestows it on the faction entity, and asserts one deprecated registry row, one live tag row, and one `entity_tags_current` row.
- Both join `SEED_CALLS` in `tests/test_pg_disposable_target.py`, which proves they refuse every owner database before connecting. Their own PostgreSQL tests: `tests/test_pg_adjudication_ledger_seed.py` (the committed rows, the history payload built from them, and the refusals for fewer than two ticks, descending ticks, and a save with pending resolutions) and `tests/test_pg_legacy_faction_tag_seed.py` (a template tag and a new tag, a registry row re-created as deprecated, and refusals for a live category, a non-faction entity, and a tag from another category).

### Conversions

- `test_trait_compiler_integration`: module-scoped `disposable_slot_database("qa885_trait_compiler")` seeded with `seed_zone`, `seed_place`, and `seed_protagonist(current_location=…)`; `connect(dbname)`; the `psycopg2.Error` skips are gone. `_install_valence_shadow` is dropped after proving on the clone that every count and remainder holds against the real triggers (the compiler sets its own producer, `nexus/api/trait_compiler.py:1931`): all five tests pass without it, and two tests now assert, through `_assert_real_relationship_triggers`, that each edge sits in `public.character_relationships` with `valence_current` derived by the real valence-boundary trigger and exactly one `trait_compiler` insert row in `relationship_versions` (migration 115). With the shadow installed that assertion fails, because the rows land in `pg_temp`. Test ids `*_on_save_05` became `*_on_seeded_clone`.
- `test_stage2a_status_live`: module-scoped clone routed with `route_slot_to_disposable(mp.setattr, slot=5, …)` inside `pytest.MonkeyPatch.context()`; seeded with `seed_protagonist` (clock at 2073-08-01), `seed_faction`, and `seed_story_clock`. `_insert_subject` stays inside the rolled-back transaction. The vocabulary reader takes the clone name; `slot=ROUTED_SLOT` still reaches the seat resolver through the route. The live_llm marker is unchanged.
- `test_stage2a_epistemics_live`: the same routed module clone with a player and a faction; `LIVE_DATABASE = "NEXUS_template"` is gone. No head chunk is seeded: each test inserts the story's first chunk (`S01E01_001`) itself, and a seeded head chunk takes that slug. The clock is `base_timestamp`, so the first test now asserts the source chunk is stamped exactly `WORLD_TIME` (on the template it was stamped wall-clock time).
- `test_retrieval_coverage_live`: rewritten in place to the post-#903 contract. After each `handle_user_input` it asserts no row exists yet, then calls `record_rendered_coverage` with the rendered chunks (warm slice plus that turn's retrieved passages) and their rendered tokens, as `turn_cycle.py:1310-1313` does. Every base assertion survives: exactly two rows, the hit/gap row's detected entities, kept chunk ids, coverage and gap entities, and the empty-detection row. It also asserts `kept_tokens` equals the rendered tokens. The migration-075 exec is gone (the clone is at head). The clone is routed under slot 5 (the report label) and seeded with a player and two committed chunks: the warm slice's chunk 1 and the head chunk the covered reference lands on (with one chunk the covered chunk was the warm slice's chunk 1 and deduplicated away). The probe characters stay in-transaction inserts. The clone is module-scoped, routed inside `pytest.MonkeyPatch.context()` like the Stage 2a and adjudication modules; the test's own writes roll back in its transaction.
- `test_intertitle_live`: module clone with a zoned place, a located protagonist, and a chunk clocked at `WORLD_TIME`; `sqlalchemy_url` engines, disposed. The location assertion is unconditional, and the intertitle's clock and place name, and the prologue test's anchor, are pinned to the seeded rows.
- `test_faction_table_audit`: module clone with `seed_faction` plus two `seed_legacy_faction_tag` rows (`legitimacy_status: gray_legal`, `operational_secrecy: cellular_clandestine`); each PostgreSQL test routes slot 2 with `monkeypatch` and closes the clone's pool afterward. `TEST_DBNAME` is gone; the audit asserts the seeded categories and tags exactly (so the legacy-mapping assertions bite); the CLI asserts `dbname == <clone>`; the "no faction" and "could not seed tag" skips are assertions; the write test uses `tests.pg_fixtures.connect`. Fake-cursor manifests carried `save_02`/`save_05` as labels only; they now use `fixture_manifest_db`.
- `test_adjudication_history`: one module clone routed under slot 2, with a located player, an explicit actor, a ledger over three ticks, and a fourth chunk the commit test anchors on (no `ORDER BY entity_id LIMIT 1`, no `max(id)`). The oracle drops `HISTORY_SLOTS` and reads the seeded ledger. `test_history_is_non_vacuous_on_audited_slots` is replaced by `test_seeded_ledger_covers_every_outcome_the_history_renders`: its meaning (the owner's slots hold Skald rulings) is not a test of this code, and neither slot holds one. The replacement checks that the ledger the oracle reads has every streak outcome, every promotion status, a succeeded narration, a replace with delta, pressures, and both exposure kinds.

## Audit Grep

```
$ for f in tests/test_trait_compiler_integration.py tests/test_orrery/test_stage2a_status_live.py tests/test_orrery/test_stage2a_epistemics_live.py tests/test_lore/test_retrieval_coverage_live.py tests/test_lore/test_intertitle_live.py tests/test_faction_table_audit.py tests/test_orrery/test_adjudication_history.py; do grep -n "save_0\|NEXUS_template\|get_slot_db_url(slot=\|slot_dbname([1-5])\|LIVE_SLOT\|LIVE_DATABASE" $f; done; echo audit-done
audit-done
```

## Connection Audit

B2-6 has not landed on `origin/main`, so every PostgreSQL run used its `dbname_audit` plugin (copied unchanged from the `claude/885-migration-test-clones` branch, `tests/dbname_audit.py` at `df8c3dde`) from this order's scratchpad subdirectory, loaded with `PYTHONPATH=<scratchpad>/885-B2-5:$PWD ... -p dbname_audit`. It records every psycopg2 and asyncpg target and fails the session on any `save_NN` or `NEXUS_template` target. Child processes (`pg_dump` and `psql` in clone creation) are not audited.

Slice gate, PostgreSQL:

```
dbname audit: 13 targets: postgres, qa885_adjudication_history_*, qa885_faction_audit_*, qa885_intertitle_*, qa885_ledger_seed_* x3, qa885_legacy_tag_* x2, qa885_retrieval_coverage_*, qa885_stage2a_epistemics_*, qa885_trait_compiler_*, qa885_transaction_writer_*
dbname audit: owner targets: none
```

Slice gate, PostgreSQL plus live flag (adds `qa885_stage2a_status_*`):

```
dbname audit: 14 targets: postgres, qa885_adjudication_history_*, qa885_faction_audit_*, qa885_intertitle_*, qa885_ledger_seed_* x3, qa885_legacy_tag_* x2, qa885_retrieval_coverage_*, qa885_stage2a_epistemics_*, qa885_stage2a_status_*, qa885_trait_compiler_*, qa885_transaction_writer_*
dbname audit: owner targets: none
```

## Sequence Proof (Read-Only)

`snapshot.sh` runs, for each of `save_02`, `save_05`, and `NEXUS_template`, inside `BEGIN READ ONLY`:

```sql
SELECT schemaname, sequencename, last_value FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename;
SELECT 'narrative_chunks', count(*) FROM narrative_chunks
UNION ALL SELECT 'entities', count(*) FROM entities
UNION ALL SELECT 'characters', count(*) FROM characters
UNION ALL SELECT 'factions', count(*) FROM factions
UNION ALL SELECT 'world_events', count(*) FROM world_events
UNION ALL SELECT 'orrery_resolutions', count(*) FROM orrery_resolutions
UNION ALL SELECT 'orrery_adjudication_log', count(*) FROM orrery_adjudication_log;
```

Taken directly before the slice's PostgreSQL gate (2026-09-30T04:25:42Z) and directly after its live-flag gate (2026-09-30T04:26:16Z); `diff` of the two outputs is empty. `NULL` is a sequence never called.

### save_02

| Row count | Before | After |
| --- | ---: | ---: |
| `narrative_chunks` | 1425 | 1425 |
| `entities` | 121 | 121 |
| `characters` | 35 | 35 |
| `factions` | 9 | 9 |
| `world_events` | 0 | 0 |
| `orrery_resolutions` | 0 | 0 |
| `orrery_adjudication_log` | 0 | 0 |

| Sequence (`public`) | Before `last_value` | After `last_value` |
| --- | ---: | ---: |
| `ai_notebook_id_seq` | NULL | NULL |
| `backstory_secrets_id_seq` | NULL | NULL |
| `character_experience_jobs_id_seq` | NULL | NULL |
| `character_experiences_id_seq` | NULL | NULL |
| `character_identity_rulings_id_seq` | NULL | NULL |
| `character_project_states_id_seq` | 3444 | 3444 |
| `character_relationships_id_seq` | 7 | 7 |
| `character_routine_anchors_id_seq` | NULL | NULL |
| `characters_id_seq` | 101 | 101 |
| `chunk_metadata_id_seq` | 8672 | 8672 |
| `claim_awareness_id_seq` | 1044 | 1044 |
| `claims_id_seq` | 475 | 475 |
| `correspondence_compaction_jobs_id_seq` | NULL | NULL |
| `entities_id_seq` | 561 | 561 |
| `entity_pair_tags_id_seq` | 3525 | 3525 |
| `entity_tags_id_seq` | 1157 | 1157 |
| `generation_session_phases_id_seq` | NULL | NULL |
| `interaction_authorizations_id_seq` | NULL | NULL |
| `interaction_events_id_seq` | NULL | NULL |
| `interaction_participants_id_seq` | NULL | NULL |
| `items_id_seq` | NULL | NULL |
| `layers_id_seq` | 1 | 1 |
| `narrative_chunks_id_seq` | 2624 | 2624 |
| `narrative_embedding_jobs_id_seq` | NULL | NULL |
| `narrative_summary_jobs_id_seq` | NULL | NULL |
| `offscreen_narrations_id_seq` | NULL | NULL |
| `orrery_adjudication_log_id_seq` | 561 | 561 |
| `orrery_maturation_jobs_id_seq` | 504 | 504 |
| `orrery_narration_jobs_id_seq` | NULL | NULL |
| `orrery_prompt_exposures_id_seq` | 3230 | 3230 |
| `orrery_recall_trace_id_seq` | NULL | NULL |
| `orrery_resolutions_id_seq` | 7353 | 7353 |
| `orrery_route_graph_edges_id_seq` | NULL | NULL |
| `orrery_route_graph_nodes_id_seq` | NULL | NULL |
| `orrery_scene_pressures_id_seq` | 561 | 561 |
| `orrery_travel_edges_id_seq` | NULL | NULL |
| `pair_tags_id_seq` | 29 | 29 |
| `places_id_seq` | 4 | 4 |
| `relationship_versions_id_seq` | 100138 | 100138 |
| `retrieval_coverage_log_id_seq` | 52 | 52 |
| `retrograde_summaries_id_seq` | 1435 | 1435 |
| `state_checkpoints_id_seq` | 2978 | 2978 |
| `state_delta_log_id_seq` | 33 | 33 |
| `storyteller_correspondence_letters_id_seq` | NULL | NULL |
| `tag_clearance_log_id_seq` | 1070 | 1070 |
| `tags_id_seq` | 556 | 556 |
| `world_events_id_seq` | 8182 | 8182 |
| `zones_id_seq` | 1 | 1 |

### save_05

| Row count | Before | After |
| --- | ---: | ---: |
| `narrative_chunks` | 0 | 0 |
| `entities` | 0 | 0 |
| `characters` | 0 | 0 |
| `factions` | 0 | 0 |
| `world_events` | 0 | 0 |
| `orrery_resolutions` | 0 | 0 |
| `orrery_adjudication_log` | 0 | 0 |

| Sequence (`public`) | Before `last_value` | After `last_value` |
| --- | ---: | ---: |
| `ai_notebook_id_seq` | NULL | NULL |
| `backstory_secrets_id_seq` | NULL | NULL |
| `character_experience_jobs_id_seq` | NULL | NULL |
| `character_experiences_id_seq` | NULL | NULL |
| `character_identity_rulings_id_seq` | NULL | NULL |
| `character_project_states_id_seq` | NULL | NULL |
| `character_relationships_id_seq` | NULL | NULL |
| `character_routine_anchors_id_seq` | NULL | NULL |
| `characters_id_seq` | 2524 | 2524 |
| `chunk_metadata_id_seq` | 2386 | 2386 |
| `claim_awareness_id_seq` | NULL | NULL |
| `claims_id_seq` | NULL | NULL |
| `correspondence_compaction_jobs_id_seq` | NULL | NULL |
| `entities_id_seq` | 5550 | 5550 |
| `entity_pair_tags_id_seq` | 780 | 780 |
| `entity_tags_id_seq` | 41 | 41 |
| `generation_session_phases_id_seq` | NULL | NULL |
| `interaction_authorizations_id_seq` | NULL | NULL |
| `interaction_events_id_seq` | NULL | NULL |
| `interaction_participants_id_seq` | NULL | NULL |
| `items_id_seq` | NULL | NULL |
| `layers_id_seq` | NULL | NULL |
| `narrative_chunks_id_seq` | 2492 | 2492 |
| `narrative_embedding_jobs_id_seq` | NULL | NULL |
| `narrative_summary_jobs_id_seq` | NULL | NULL |
| `offscreen_narrations_id_seq` | NULL | NULL |
| `orrery_adjudication_log_id_seq` | NULL | NULL |
| `orrery_maturation_jobs_id_seq` | NULL | NULL |
| `orrery_narration_jobs_id_seq` | NULL | NULL |
| `orrery_prompt_exposures_id_seq` | NULL | NULL |
| `orrery_recall_trace_id_seq` | 2184 | 2184 |
| `orrery_resolutions_id_seq` | NULL | NULL |
| `orrery_route_graph_edges_id_seq` | NULL | NULL |
| `orrery_route_graph_nodes_id_seq` | NULL | NULL |
| `orrery_scene_pressures_id_seq` | NULL | NULL |
| `orrery_travel_edges_id_seq` | NULL | NULL |
| `pair_tags_id_seq` | 387 | 387 |
| `places_id_seq` | NULL | NULL |
| `relationship_versions_id_seq` | 12 | 12 |
| `retrieval_coverage_log_id_seq` | NULL | NULL |
| `retrograde_summaries_id_seq` | NULL | NULL |
| `state_checkpoints_id_seq` | 252 | 252 |
| `state_delta_log_id_seq` | NULL | NULL |
| `storyteller_correspondence_letters_id_seq` | NULL | NULL |
| `tag_clearance_log_id_seq` | 156 | 156 |
| `tags_id_seq` | 20092 | 20092 |
| `world_events_id_seq` | 3338 | 3338 |
| `zones_id_seq` | NULL | NULL |

### NEXUS_template

| Row count | Before | After |
| --- | ---: | ---: |
| `narrative_chunks` | 0 | 0 |
| `entities` | 0 | 0 |
| `characters` | 0 | 0 |
| `factions` | 0 | 0 |
| `world_events` | 0 | 0 |
| `orrery_resolutions` | 0 | 0 |
| `orrery_adjudication_log` | 0 | 0 |

| Sequence (`public`) | Before `last_value` | After `last_value` |
| --- | ---: | ---: |
| `ai_notebook_id_seq` | NULL | NULL |
| `backstory_secrets_id_seq` | NULL | NULL |
| `character_experience_jobs_id_seq` | NULL | NULL |
| `character_experiences_id_seq` | NULL | NULL |
| `character_identity_rulings_id_seq` | NULL | NULL |
| `character_project_states_id_seq` | 2 | 2 |
| `character_relationships_id_seq` | NULL | NULL |
| `character_routine_anchors_id_seq` | NULL | NULL |
| `characters_id_seq` | NULL | NULL |
| `chunk_metadata_id_seq` | 1399 | 1399 |
| `claim_awareness_id_seq` | 672 | 672 |
| `claims_id_seq` | 319 | 319 |
| `correspondence_compaction_jobs_id_seq` | NULL | NULL |
| `entities_id_seq` | 2568 | 2568 |
| `entity_pair_tags_id_seq` | NULL | NULL |
| `entity_tags_id_seq` | NULL | NULL |
| `generation_session_phases_id_seq` | NULL | NULL |
| `interaction_authorizations_id_seq` | NULL | NULL |
| `interaction_events_id_seq` | NULL | NULL |
| `interaction_participants_id_seq` | NULL | NULL |
| `items_id_seq` | NULL | NULL |
| `layers_id_seq` | NULL | NULL |
| `narrative_chunks_id_seq` | 1441 | 1441 |
| `narrative_embedding_jobs_id_seq` | NULL | NULL |
| `narrative_summary_jobs_id_seq` | NULL | NULL |
| `offscreen_narrations_id_seq` | NULL | NULL |
| `orrery_adjudication_log_id_seq` | NULL | NULL |
| `orrery_maturation_jobs_id_seq` | NULL | NULL |
| `orrery_narration_jobs_id_seq` | NULL | NULL |
| `orrery_prompt_exposures_id_seq` | NULL | NULL |
| `orrery_recall_trace_id_seq` | NULL | NULL |
| `orrery_resolutions_id_seq` | NULL | NULL |
| `orrery_route_graph_edges_id_seq` | NULL | NULL |
| `orrery_route_graph_nodes_id_seq` | NULL | NULL |
| `orrery_scene_pressures_id_seq` | NULL | NULL |
| `orrery_travel_edges_id_seq` | NULL | NULL |
| `pair_tags_id_seq` | 29 | 29 |
| `places_id_seq` | NULL | NULL |
| `relationship_versions_id_seq` | NULL | NULL |
| `retrieval_coverage_log_id_seq` | NULL | NULL |
| `retrograde_summaries_id_seq` | NULL | NULL |
| `state_checkpoints_id_seq` | 730 | 730 |
| `state_delta_log_id_seq` | NULL | NULL |
| `storyteller_correspondence_letters_id_seq` | NULL | NULL |
| `tag_clearance_log_id_seq` | NULL | NULL |
| `tags_id_seq` | 532 | 532 |
| `world_events_id_seq` | 1035 | 1035 |
| `zones_id_seq` | NULL | NULL |

## Gates

Slice gate (`gate.sh pg`): the seven modules, `tests/test_pg_disposable_target.py`, and the two helper tests.

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL PYTHONPATH=<scratchpad>/885-B2-5:$PWD NEXUS_RUN_POSTGRES=1 \
    /Users/pythagor/nexus/.venv/bin/python -m pytest -q -p dbname_audit tests/test_trait_compiler_integration.py \
    tests/test_orrery/test_stage2a_status_live.py tests/test_orrery/test_stage2a_epistemics_live.py \
    tests/test_lore/test_retrieval_coverage_live.py tests/test_lore/test_intertitle_live.py tests/test_faction_table_audit.py \
    tests/test_orrery/test_adjudication_history.py tests/test_pg_disposable_target.py \
    tests/test_pg_adjudication_ledger_seed.py tests/test_pg_legacy_faction_tag_seed.py -rs
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 13 targets: postgres, qa885_adjudication_history_*, qa885_faction_audit_*, qa885_intertitle_*, qa885_ledger_seed_* x3, qa885_legacy_tag_* x2, qa885_retrieval_coverage_*, qa885_stage2a_epistemics_*, qa885_trait_compiler_*, qa885_transaction_writer_*
dbname audit: owner targets: none
SKIPPED [5] tests/test_orrery/test_stage2a_status_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
76 passed, 5 skipped, 5 warnings in 15.54s
```

The five skips are `test_stage2a_status_live`, gated by its unchanged live_llm marker. The same files with `NEXUS_RUN_LIVE_LLM=1 NEXUS_TEST_PROVIDER_ONLY=1` added (`gate.sh live`); `read-only (live LLM)` is the guard's correct output under the live flag:

```
secret-store guard: active; nexus-api: read-only (live LLM); disposable keychain: denied
dbname audit: 14 targets: postgres, qa885_adjudication_history_*, qa885_faction_audit_*, qa885_intertitle_*, qa885_ledger_seed_* x3, qa885_legacy_tag_* x2, qa885_retrieval_coverage_*, qa885_stage2a_epistemics_*, qa885_stage2a_status_*, qa885_trait_compiler_*, qa885_transaction_writer_*
dbname audit: owner targets: none
81 passed, 5 warnings in 16.89s
```

Directory gates, `NEXUS_RUN_POSTGRES=1 ... -p dbname_audit` (each tail is verbatim from the guard line down; the three `tests/test_orrery` sessions end with the audit's `dbname audit: FAILED: owner targets: ...` line, which the table below classifies):

```
$ ... pytest -q -p dbname_audit tests/test_lore
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 44 targets: nexus_test_813_*, nexus_test_i685_* x3, nexus_test_pass2_* x7, postgres, qa640_742_seat_test_*, qa640_818_estimate_*, qa640_818_pin_* x2, qa640_908_aliases_*, qa640_908_cast_*, qa640_908_fingerprint_*, qa640_910_dossier_* x7, qa640_historical_coverage_* x3, qa640_scene_clock_*, qa640_scene_null_clock_*, qa640_scene_parent_*, qa640_settings_stamp_*, qa640_window_coverage_*, qa885_intertitle_*, qa885_retrieval_coverage_*, qa_lazy_logon_*, qa_lore_infra_*, qa_pass2_corpus_*, qa_runtime_config_* x5
dbname audit: owner targets: none
455 passed, 1 skipped, 9 warnings in 124.34s (0:02:04)
$ ... pytest -q -p dbname_audit <tests/test_orrery/test_*.py, files 1-45>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 75 targets: postgres, qa640_781_cards_* x6, qa640_bleed_acceptance_*, qa640_bleed_proximity_* x4, qa640_claim_accounts_*, qa640_claim_consumption_*, qa640_communication_graph_*, qa640_drift_*, qa640_ecology_*, qa640_roster798_* x14, qa640_wizard_drain_* x3, qa679_*, qa885_adjudication_history_*, qa885_build_venture_*, qa885_build_venture_async_*, qa885_build_venture_replay_*, qa885_claim_awareness_replay_*, qa885_court_patron_* x2, qa885_court_patron_async_*, qa885_distortion_*, qa885_epistemics_*, qa_wt723_*, qa_wt724_experience_* x26, save_02, save_05, test_event_sources_*
dbname audit: FAILED: owner targets: save_02 (psycopg2) from tests/test_orrery/test_backstory_secrets_migration_pg.py::test_migration_091_enforces_checks_uniqueness_and_foreign_keys, tests/test_orrery/test_backstory_secrets_migration_pg.py::test_migration_091_installs_secret_contract_and_comments, tests/test_orrery/test_backstory_secrets_migration_pg.py::test_migration_091_seeds_both_revelation_events, tests/test_orrery/test_build_venture_migration_pg.py::test_migration_084_widens_projects_and_registers_vocabulary, tests/test_orrery/test_claim_accounts_migration_pg.py::test_migration_090_mints_canonical_idempotently_and_variants_loudly, tests/test_orrery/test_claim_accounts_migration_pg.py::test_migration_090_rejects_self_ancestor, tests/test_orrery/test_claim_accounts_migration_pg.py::test_migration_090_swaps_index_and_preserves_existing_rows, tests/test_orrery/test_court_patron_migration_pg.py::test_migration_086_widens_constraints_and_seeds_events, tests/test_orrery/test_distortion_migration_pg.py::test_migration_092_adds_nullable_positive_documented_depth, tests/test_orrery/test_distortion_migration_pg.py::test_migration_092_rejects_canonical_account_with_depth, tests/test_orrery/test_distortion_migration_pg.py::test_variant_mint_rejects_invalid_distortion_depth_before_sql[-1], tests/test_orrery/test_distortion_migration_pg.py::test_variant_mint_rejects_invalid_distortion_depth_before_sql[0], tests/test_orrery/test_distortion_migration_pg.py::test_variant_mint_rejects_invalid_distortion_depth_before_sql[1.5], tests/test_orrery/test_distortion_migration_pg.py::test_variant_mint_rejects_invalid_distortion_depth_before_sql[True]; save_05 (psycopg2) from tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
1 failed, 549 passed, 27 skipped, 7 warnings in 96.74s (0:01:36)
$ ... pytest -q -p dbname_audit <tests/test_orrery/test_*.py, files 46-90>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 86 targets: postgres, qa638_*, qa640_* x18, qa640_800_operator_*, qa640_807_boundary_*, qa640_811_gaia_scene_*, qa640_drift_*, qa640_grieving_migration_*, qa640_need_absence_* x7, qa640_orbit_distance_*, qa640_pair_tag_predicates_*, qa640_pair_tag_substrate_*, qa640_provenance_* x3, qa640_reconstruction_*, qa640_replay_*, qa640_roster798_* x9, qa640_vocab_migration_* x6, qa672_*, qa676_* x7, qa735_gis_stubs_* x5, qa735_mood_*, qa735_pair_tags_* x10, qa885_knowledge_surfacing_*, qa885_pursue_romance_*, qa885_pursue_romance_async_*, qa_wt720_*, qa_wt724_recall_*, save_02, save_05
dbname audit: FAILED: owner targets: save_02 (psycopg2) from tests/test_orrery/test_projects.py::test_resolution_insert_skips_routine_promotion_but_queues_milestone, tests/test_orrery/test_projects.py::test_slot2_coverage_distribution_and_project_gate_payload, tests/test_orrery/test_pursue_romance_migration_pg.py::test_migration_085_widens_constraints_and_seeds_events, tests/test_orrery/test_pursue_romance_replay.py::test_pursue_romance_lifecycle_replays_between_checkpoints_without_drift, tests/test_orrery/test_recruit_ally_migration_pg.py::test_migration_077_preserves_progress_and_replaces_completed_target_guard, tests/test_orrery/test_recruit_ally_projects.py::test_live_neglect_applies_recruitment_setback, tests/test_orrery/test_recruit_ally_projects.py::test_live_schema_target_discipline_and_one_project_budget, tests/test_orrery/test_recruit_ally_projects.py::test_live_stage_ladder_completion_and_applied_ledger, tests/test_orrery/test_recruit_ally_projects.py::test_live_start_persists_bound_character_target, tests/test_orrery/test_recruit_ally_projects.py::test_slot2_recruitment_routes_persisted_target_without_routine_drift, tests/test_orrery/test_recruit_ally_replay.py::test_recruit_ally_lifecycle_replays_between_checkpoints_without_drift; save_05 (psycopg2) from tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction, tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction, tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered, tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly, tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched, tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings, tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic, tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition, tests/test_orrery/test_geo_resolver_live.py::test_covering_zone_wins_over_nearer_noncovering_zone, tests/test_orrery/test_geo_resolver_live.py::test_nearest_boundary_wins_outside_all_zones, tests/test_orrery/test_geo_resolver_live.py::test_no_bounded_zone_raises, tests/test_orrery/test_geo_resolver_live.py::test_story_active_zone_and_corruption_raise, tests/test_orrery/test_geo_resolver_live.py::test_zone_id_breaks_equal_distance_tie, tests/test_orrery/test_mood_migration_pg.py::test_mood_vocabulary_contract, tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle, tests/test_orrery/test_polymorphic_patron_migration_pg.py::test_polymorphic_patron_constraints_accept_xor_and_reject_other_shapes
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic
ERROR tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
433 passed, 2 skipped, 7 warnings, 9 errors in 106.14s (0:01:46)
$ ... pytest -q -p dbname_audit <tests/test_orrery/test_*.py, files 91-133>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 45 targets: postgres, qa640_807_latest_playable_*, qa640_807_maturation_boundary_*, qa640_807_reapply_*, qa640_811_full_clear_only_*, qa640_811_scene_clear_only_*, qa640_811_scene_kind_*, qa640_811_scene_pin_*, qa640_811_seed_policy_*, qa640_811_tag_library_*, qa640_issue601_* x4, qa640_maturation799_*, qa640_projects799_*, qa640_retrieval_* x2, qa640_retro078_* x13, qa640_status_bestow_*, qa640_weather_migration_*, qa640_worker_*, qa665_*, qa735_weather_*, qa885_reveal_*, qa885_seek_redemption_* x2, qa885_seek_redemption_async_*, qa885_signal_events_*, qa885_stage2a_epistemics_*, qa885_tag_provenance_*, save_02, save_05
dbname audit: FAILED: owner targets: save_02 (psycopg2) from tests/test_orrery/test_retrograde_vocabulary.py::test_seed_eligible_vocabulary_can_include_live_tag_registry, tests/test_orrery/test_seek_redemption_migration_pg.py::test_migration_087_widens_constraints_and_seeds_events, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_authored_literal_update_rederives_float, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_backfills_and_canonicalizes_existing_rows, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_check_rejects_open_interval_endpoints[endpoint0], tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_check_rejects_open_interval_endpoints[endpoint1], tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_float_update_reprojects_literal, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_float_wins_when_both_representations_change, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_insert_without_float_derives_canonical_state, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_preserves_trust_hydration_for_canonical_rows, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_round_trip_preserves_all_eleven_rungs, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_same_literal_reassertion_preserves_intra_rung_float, tests/test_orrery/test_valence_float_migration_pg.py::test_migration_088_unparseable_literal_raises, tests/test_orrery/test_valence_float_migration_pg.py::test_trait_compiler_reports_trigger_canonicalized_valence; save_05 (psycopg2) from tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size, tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_kosi_uses_character_entity_id
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
1 failed, 640 passed, 10 skipped, 5 warnings in 89.93s (0:01:29)
```

### Remaining Failures and Owner Targets in the Directory Gates

`tests/test_lore` is clean, with no owner target. In `tests/test_orrery`, every failure, and every owner target the audit reported, is in a module this branch does not touch. All are listed on #885 for a later B2 slice and were already present on `main`. None is new.

| Node or module | Audit target | Class |
| --- | --- | --- |
| `test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end` (FAILED) | `save_05` | B2-7 (read-only owner content), pre-existing on main |
| `test_tag_library.py::test_contextual_library_save_05_completeness_and_size` (FAILED); `test_contextual_library_save_05_kosi_uses_character_entity_id` (SKIPPED, vacuous: its `pytest.skip` at `test_tag_library.py:919` fires because the empty `save_05` has no character whose `characters.id` differs from `characters.entity_id`) | `save_05` | B2-7, which converts both; pre-existing on main |
| `test_faction_project_contexts_live.py` x8 (ERROR) | `save_05` | B2-4, pre-existing on main |
| `test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle` (ERROR) | `save_05` | B2-4, pre-existing on main |
| `test_projects.py`, `test_recruit_ally_projects.py`, `test_recruit_ally_replay.py`, `test_pursue_romance_replay.py` (pass) | `save_02` | B2-4 |
| `test_backstory_secrets_migration_pg.py`, `test_build_venture_migration_pg.py`, `test_claim_accounts_migration_pg.py`, `test_court_patron_migration_pg.py`, `test_distortion_migration_pg.py`, `test_pursue_romance_migration_pg.py`, `test_recruit_ally_migration_pg.py`, `test_seek_redemption_migration_pg.py`, `test_valence_float_migration_pg.py` (pass) | `save_02` | B2-6 (in review, not on `origin/main`) |
| `test_geo_resolver_live.py`, `test_mood_migration_pg.py`, `test_polymorphic_patron_migration_pg.py` (pass) | `save_05` | B2-6 |
| `test_retrograde_vocabulary.py::test_seed_eligible_vocabulary_can_include_live_tag_registry` (pass) | `save_02` | Not in the B2 map: a read-only `enumerate_seed_eligible_vocabulary(dbname="save_02")` (:59); raised for the coordinator |

The directory gates run modules other slices still own, so no owner snapshot was taken around them. The sequence proof above covers this slice's runs.

## Offline Gates, Reachability, and Lint

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2465 passed, 376 skipped, 8 warnings in 358.91s (0:05:58)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_POSTGRES /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery -p no:cacheprovider
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 735 skipped, 7 warnings in 32.16s
$ /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.49s
$ lint.sh   # black --check, flake8, mypy -m on every file changed from origin/main
+ black --check
All done! ✨ 🍰 ✨
11 files would be left unchanged.
black exit=0
+ flake8
flake8 exit=0
Success: no issues found in 11 source files
mypy exit=0
```

## Review Fixes

After review, the retrieval-coverage clone became module-scoped. Both slice gates were rerun on the fixed branch with the same results:

```
$ gate.sh pg
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 13 targets: postgres, qa885_adjudication_history_*, qa885_faction_audit_*, qa885_intertitle_*, qa885_ledger_seed_* x3, qa885_legacy_tag_* x2, qa885_retrieval_coverage_*, qa885_stage2a_epistemics_*, qa885_trait_compiler_*, qa885_transaction_writer_*
dbname audit: owner targets: none
SKIPPED [5] tests/test_orrery/test_stage2a_status_live.py: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
76 passed, 5 skipped, 5 warnings in 16.57s
$ gate.sh live
secret-store guard: active; nexus-api: read-only (live LLM); disposable keychain: denied
dbname audit: 14 targets: postgres, qa885_adjudication_history_*, qa885_faction_audit_*, qa885_intertitle_*, qa885_ledger_seed_* x3, qa885_legacy_tag_* x2, qa885_retrieval_coverage_*, qa885_stage2a_epistemics_*, qa885_stage2a_status_*, qa885_trait_compiler_*, qa885_transaction_writer_*
dbname audit: owner targets: none
81 passed, 5 warnings in 18.17s
$ NEXUS_RUN_POSTGRES=1 pytest -q -rs "tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_kosi_uses_character_entity_id"   # read-only, confirms the table's SKIPPED row
SKIPPED [1] tests/test_orrery/test_tag_library.py:919: save_05 has no character whose characters.id differs from characters.entity_id; cannot exercise namespace translation
1 skipped, 5 warnings in 0.54s
$ black --check / flake8 / mypy -m tests.test_lore.test_retrieval_coverage_live
1 file would be left unchanged. / exit 0 / Success: no issues found in 1 source file
```
