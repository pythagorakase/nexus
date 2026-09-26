# Static Disposition of the 232 Red PostgreSQL-Gate Nodes

Issue #964 records the isolated full gate on `b0645dafb646bf849a084d6a0eda77c076492bd4` (3,503 passed, 165 failed, 67 errors, 85 skipped; 232 unique red nodes) and asks for a per-node cause-to-issue disposition. This document is that disposition, produced on 2026-09-26 by reading each red test, the fixtures it uses, and the production code named by its recorded first-line signature. No PostgreSQL run was performed: the environment that produced this analysis has no `NEXUS_template`, so every row marked *runtime confirmation needed* still requires a focused run on a private cluster before its repair is declared complete. The machine-readable form is `dispositions.json` beside this file.

## Summary

| Root cause | Nodes |
|---|---:|
| `hardcoded_connection_target` | 10 |
| `keychain_access` | 2 |
| `template_or_migration_drift` | 4 |
| `ann_table_absent` | 3 |
| `mock_database_absent` | 2 |
| `environment_path_or_port` | 1 |
| `fixture_helper_defect` | 2 |
| `empty_slot_missing_clock` | 33 |
| `owner_slot_content_assumption` | 175 |
| **Total** | **232** |

| Repair route | Nodes |
|---|---:|
| `seed_disposable_clone` | 176 |
| `parametrize_slot_or_fixture` | 31 |
| `migrate_to_pg_fixtures_connection` | 11 |
| `gate_behind_corpus_flag` | 8 |
| `fix_test_environment_assumption` | 4 |
| `other` | 2 |

| Routed issue | Nodes |
|---|---:|
| #885 | 207 |
| #804 | 10 |
| #816 | 6 |
| #810 | 4 |
| #963 | 2 |
| none | 2 |
| new-issue | 1 |

Product defects suspected even with a valid fixture: 2 (both low severity; see the rows below). Nodes whose repair needs a runtime confirmation before it can be declared complete: 127.

## Reading the Groups

- `hardcoded_connection_target` (10, routed to #804): the test data was built correctly on the private cluster, but a hand-built `postgresql://pythagor@localhost:5432/...` URL or the `tests/test_lore/lore_test_settings.json` literal sent the request to the owner's server, which the guard denied. Repair: resolve the clone through `nexus.database` or `tests/pg_fixtures`.
- `keychain_access` (2, routed to #963): the tests unset `NEXUS_KEYRING_DISABLE` and drove the real `security` CLI. The #963 branch replaces this with an injected in-memory backend and a fail-closed guard.
- `template_or_migration_drift` (4, routed to #810): a fixture re-executes migrations 097 and 123 raw against an already-migrated template clone.
- `ann_table_absent` (3), `mock_database_absent` (2), `environment_path_or_port` (1), `fixture_helper_defect` (2): environment or fixture-helper assumptions with individual repairs below.
- `empty_slot_missing_clock` (33) and `owner_slot_content_assumption` (175): the tests read a named owner slot (save_02, save_04, save_05, or a data clone of one) and assume it holds a played story, a world clock, characters, chunks or Orrery rows. On the private cluster every slot was an empty template clone. Repair: seed a disposable template clone with exactly the rows each test needs through `tests/pg_fixtures.disposable_slot_database` plus `seed_protagonist` and new shared seed helpers; a small number of intentionally corpus-bound probes should instead be gated behind an explicit corpus opt-in and documented as integration exclusions.

## Shared Repairs by File

- **`tests/test_api/test_attempt_manifest_pg.py`** (4 red nodes): Every test in the file clones the owner's save_04 with include_data=True; the passing privacy test is only vacuously green on an empty clone. The failures split in two. (a) Turn-driven nodes (real_test_turn sync and async) need a production-path playable-story factory (#816). In a default template clone routed with scheduler_helpers.route_slot under test_provider_config, drive 'nexus continue --slot 4 --model TEST' then '--accept-fate' until bootstrap, as in tests/test_connection_lifecycle.py. This leaves an accepted tail whose Pass-2 baseline already carries the TEST fingerprint. (b) Row-seedable nodes (child_job_enqueue, inspect_turn) need a default clone plus seed_protagonist plus shared helpers. Promote _insert_chunk, and the chunk/NPC/slept-event/seed_character_experiences_sync half of _enqueue_render_job, from tests/test_orrery/test_character_experiences_pg.py into tests/pg_fixtures.py. Seed relationships inside SET LOCAL nexus.write_producer='manual'. Replace the hardcoded chunk 49 with a seeded id.
- **`tests/test_api/test_backstage_endpoints_pg.py`** (6 red nodes): All six red nodes share one defect. Three hand-built SQLAlchemy URLs, 'postgresql://pythagor@localhost:5432/<clone>', are monkeypatched over backstage_endpoints.get_slot_db_url: in the client fixture's disposable_url, in test_empty_slot_is_404's lambda, and in test_backstage_gate_both_arms' on-arm lambda. The clones themselves are created and seeded through the module _connect(), which honors PGHOST/PGPORT. Seeding therefore landed on the private cluster (55442), while every endpoint request dialed owner 5432. Evidence: test_incubator_view_never_exposes_staged_correspondence uses the same backstage_case through _connect and is not red, and test_bad_slot_is_structured_400 never touches the database. Repair: (1) Add one helper, _route_slot_4_to(monkeypatch, dbname), that patches slot_utils.VALID_DBNAMES and slot_utils.slot_dbname the way tests/test_api/conftest.py::offline_gate_db does, so the production get_slot_db_url -> nexus.database.database_url resolves the clone through the one connection contract. The minimal alternative is to return nexus.database.database_url(dbname). (2) Replace the module _connect with tests.pg_fixtures.connect. Replace the bespoke module fixtures disposable_db and empty_disposable_db, which call pytest.skip when the admin connection is unavailable (contradicting the NEXUS_RUN_POSTGRES fail-not-skip doctrine) and only pop db_pool._pools, with disposable_slot_database('qa_wt625') and disposable_slot_database('qa_wt625_empty'), which use db_pool.dispose_database and also dispose registered SQLAlchemy engines. The TEST story pin they add should be harmless to commit_incubator_to_database_sync, but confirm it. (3) Per #804's acceptance comment, add a fixture preflight asserting that a psycopg2 connection and a create_slot_engine(database_url(dbname)) session report the same current_database() and inet_server_port(). Cross-cutting note: pg_fixtures.connection_parameters() reads only the PG* env, while nexus.database.connection_kwargs gives [api.database] host/port precedence over the env. They agree today only because nexus.toml leaves host empty and port absent, so pg_fixtures should delegate to nexus.database. No commit after b0645daf changed this file or its code paths. commit_handler_sync did change after baseline (name reveals, bind_session_id), which is why the detailed payload assertions need a runtime confirmation after the routing fix.
- **`tests/test_api/test_orrery_dev_endpoints.py`** (10 red nodes): The module is pinned to LIVE_SLOT=5 and AUDIT_SLOTS=(5,), the owner's Orrery-native save_05. All eight red nodes are empty-slot manifestations. Three more parity nodes (resolve_parity[5], joint_beats_parity[5], coverage_head_anchor_reconciles) pass vacuously today. Add a module-scoped orrery_audit_world fixture that creates a disposable clone and routes slot 5 to it with a module-scoped pytest.MonkeyPatch on slot_utils.slot_dbname and VALID_DBNAMES, so get_slot_db_url(slot=5) and the router both hit the clone. The fixture should seed: seed_protagonist plus a zoned player location; at least 3 NPC characters with dossiers; at least 7 playable chunks with world_time spanning a multi-day gap and ending at night; chunk_character_references with NPCs referenced off-screen in the window and the player (plus one NPC) 'present' at the head; one NPC carrying the durable 'seeking_identity' tag, inserted with applied_at_world_time NULL to reproduce the legacy data-quality pathology; and one world_events row for an off-screen NPC before the head. Use tests/test_orrery/test_need_absence_pg.py as the pattern. A seeded fixture is the more honest route than a corpus flag. The non-vacuity guards were written to force a slot with activity, and CLAUDE.md does not accept skips as a passing gate. Keep an optional owner-save_05 parametrization behind an explicit corpus flag for live-corpus audits.
- **`tests/test_api/test_reader_asset_endpoints.py`** (16 red nodes): All 16 red nodes come from two hardwired owner slots: READ_SLOT=2 (save_02 'mature corpus') and WRITE_SLOT=5 (save_05). The 4 nodes that stayed green (test_status, test_chunk_404, test_factions_live_schema, test_invalid_slot_is_400) are content-independent. The assertions are wire-shape contracts, so seeding is more honest than a corpus gate. (1) Add a module-scoped `reader_slot` fixture: pytest.MonkeyPatch.context() around tests.pg_fixtures.disposable_slot_database('qa396_reader'), routing the slot through slot_utils.VALID_DBNAMES, slot_utils.slot_dbname and slot_mutations.slot_dbname (generalize tests/test_api/conftest.py offline_gate_db to take the slot, or reuse slot 4). (2) Add a `seed_reader_corpus(dbname)` helper to tests/pg_fixtures.py. It runs seed_protagonist (base_timestamp + player, needed before any characters insert because of trg_characters_need_state_init), then inserts a second character with a relationship (SET LOCAL nexus.write_producer; migration 115) and a character_psychology row, a layer, a zone, a place with geography coordinates, 1 seasons row, 1 episodes row, and 3 narrative_chunks with chunk_metadata (season 1, episode 1, scenes 1-3, time_delta, slug), plus a place_chunk_references 'setting' row and a chunk_character_references row on the last chunk. (3) Replace the hardcoded get_connection(f'save_{READ_SLOT:02d}') in test_context_shape with the fixture dbname. (4) For TestAssetRoundTrip, give temp_character a routed disposable slot with base_timestamp, and monkeypatch asset_endpoints.UPLOAD_ROOT to tmp_path. The test currently imports UPLOAD_ROOT by value and writes into the repo's ui/client/public. Caveat (#810): disposable clones are built by new_story_setup.initialize_slot_database, which only logs a warning when a pending migration fails. /api/characters now reads character_identity_rulings (migration 128, added after b0645daf), so a failed migration would surface as UndefinedTable in the test instead of a fixture error.
- **`tests/test_api/test_scheduler_corpus_pg.py`** (3 red nodes): All three nodes clone save_04 with data but need different things. drains_starved_corpus: seeded N render jobs plus one pending resolution, replacing the literal 9 (corpus-bound #800 proof; seeding is the honest gate default and an owner-corpus variant can sit behind a corpus flag). rechecks_generation: one seeded queued render job. live_turn: the playable_test_story factory plus one queued render job. Shared helpers: promote test_character_experiences_pg._enqueue_render_job (production path via world_events, seed_character_experiences_sync and enqueue_scene_experience_job_sync) and reuse test_narration_job_fencing_pg._materialize_pending_resolution. For the live turn, set NEXUS_GATEWAY_PORT=0 so gateway_lane does not bind the fixed 8018.
- **`tests/test_api/test_scheduler_recovery_pg.py`** (5 red nodes): All 5 red nodes clone save_04 for data it does not need. Use disposable_slot_database('qa640_...') with seed_protagonist and a new shared seed_experience_render_job helper, promoted from _enqueue_render_job in tests/test_orrery/test_character_experiences_pg.py. Replace every hardcoded job id=3 with the returned id. The passing nodes (offline_gate_db plus seed_narration) already show the template-clone approach works. Adjacent finding worth its own issue: SlotScheduler on a truly empty pre-protagonist slot loops in 'recovering', because drain_experience_render_jobs_sync resolves canonical_player_entity_id before selecting any job.
- **`tests/test_api/test_seat_policy_backfill_pg.py`** (1 red nodes): Single node. It needs a reproducible pre-126 database: seed active and terminal jobs on a template clone, drop the four tables' resolved_model/resolved_source columns, delete schema_migrations '126', then migrate. As written, the test is also time-bound on the owner's machine once save_04 has migrated past 126 (overlaps #810).
- **`tests/test_api/test_seat_policy_jobs_pg.py`** (1 red nodes): This single node needs the shared playable_test_story factory (#816) plus seeded prior-scene character_experiences on the tail, so the scene-boundary acceptance enqueues all four queues. Replace the hardcoded NEXUS_GATEWAY_PORT=8019 and NEXUS_API_URL with port 0 as test_attempt_manifest_pg does. Drop the save_04 corpus clone and the fingerprint refresh.
- **`tests/test_api/test_secrets_endpoints.py`** (1 red nodes): The isolated_keychain fixture is the single point of failure. It unsets NEXUS_KEYRING_DISABLE, which re-enables the owner's store, and _delete_test_account shells out to the real 'security' CLI against service nexus-api, account test-secret-455. Route to #963 (worktree claude/963-secret-store-test-isolation exists but is unchanged at 36faaf8). Replace the fixture with an explicit injected test backend through a new secret_manager adapter seam. Add a tests/conftest.py tripwire that fails any 'security' or keyring access unless a platform-store opt-in is set. Gate any real Keychain variant, including the already live_llm-gated test_openai_verify_wrong_key_returns_sanitized_failure, behind that opt-in with a throwaway keychain and a unique service. test_provider_derivation_uses_registry_accounts and test_malformed_write_body_does_not_echo_submitted_key do not touch the store.
- **`tests/test_api/test_session_truth_pg.py`** (1 red nodes): Promote _build_story_transition and NewStoryDatabaseMapper.perform_transition (tests/test_orrery/test_need_clock_anchor_pg.py with tests/fixtures/slot3_midnight_qa_wizard_cache.json) into tests/pg_fixtures.seed_transitioned_story and use it for both parametrizations. The [validation] variant currently passes only because the empty clone's setting is already NULL.
- **`tests/test_api/test_summary_budget_usage.py`** (2 red nodes): Both parametrizations share one cause: disposable_slot_database('qa640_937_budget', source_db='save_04', include_data=True) copies save_04's corpus, which was empty on the private cluster. Replace it with a template clone and seed, before the job-table cleanup block, one narrative_chunks row with chunk_metadata(season=1, episode=2, scene=1). Add seasons(1) and episodes(1,2) rows if chunk_metadata requires them. Seeding before cleanup lets any insert-triggered embedding or summary jobs be purged. A reusable tests/pg_fixtures.py seed_chunk(dbname, *, raw_text, season=None, episode=None, scene=None, world_time=None) helper would serve this file and all five Orrery files in this batch. As a separate small product follow-up, add a season-side no-chunk guard in nexus/jobs/summaries.py (or set last_error in generate_season_summary), so an empty season is not reported as 'Summary provider returned no summary'.
- **`tests/test_faction_table_audit.py`** (2 red nodes): Add one seeded-faction clone fixture (faction entities, factions rows with legacy columns, and legacy-category entity_tags) that routes slot 2 through slot_utils.slot_dbname and VALID_DBNAMES, and use it for both live audit nodes and for test_live_faction_apply_execute_inserts_and_rolls_back. That test currently pytest.skip()s when save_02 has no faction, which hides it in a gate that treats skips as failure.
- **`tests/test_lore/test_baseline_fingerprint_refresh_pg.py`** (1 red nodes): Needs a seeded, stamped story tail: seed_transitioned_story plus seed_accepted_chunks plus stamp_slot_tail(dbname=clone). Real LORE retrieval on unembedded seeded chunks needs a run. If it cannot complete, split the save_04 continuation proof behind an explicit corpus opt-in.
- **`tests/test_lore/test_chunk_operations.py`** (1 red nodes): Only one PostgreSQL node, and it depends on the LORE conftest's sample_chunks -> db_connection, which uses the literal save_01@localhost:5432 (see the test_infrastructure note). This node should not need PostgreSQL at all. calculate_chunk_tokens is a pure registry-estimator call, and the in-test guard 'if chunk and "raw_text" in chunk' means a connection-only fix would turn the red into a silent no-op on any empty slot. Decouple it: use a committed narrative excerpt, drop requires_postgres, and make the assertions unconditional.
- **`tests/test_lore/test_infrastructure.py`** (3 red nodes): tests/test_lore/conftest.py::db_connection and this file's test_postgresql_connection both build psycopg2 connections from the tests/test_lore/lore_test_settings.json 'Database' block ({name: save_01, host: localhost, port: 5432}). That settings.json-era literal ignores PG* env and nexus.database: under the private lane it hits the guard on owner 5432, and in the owner's environment it reads the live golden master. Shared repair in tests/test_lore/conftest.py: delete the 'Database' block. Replace db_connection with a module-scoped fixture yielding tests.pg_fixtures.connect() to disposable_slot_database('qa_lore_infra'), seeded with one narrative_chunks + chunk_metadata row (propose a shared seed_committed_chunk helper in tests/pg_fixtures.py next to seed_protagonist). Move sample_chunks and test_scenes (18 curated golden-master ids) behind a new explicit corpus opt-in (for example a requires_corpus marker plus NEXUS_RUN_CORPUS=1 in tests/conftest.py) that reads a disposable include_data clone of save_01, never the live slot. Blast radius: only three tests in tests/test_lore use db_connection, sample_chunks or test_scenes (this file's test_narrative_view_exists and test_test_scenes_available, and test_chunk_operations::test_calculate_chunk_tokens_narrative). The other tests in this file (tiktoken, settings structure, project structure) are marked requires_postgres at module level but need no database and passed. Side hazard, not a cause here: the session-scoped autouse ensure_nexus_slot_env in the LORE conftest sets NEXUS_SLOT=1 on first use and only pops it at session teardown, so it leaks NEXUS_SLOT=1 into every later test outside tests/test_lore. Review under #885 or #816.
- **`tests/test_lore/test_intertitle_live.py`** (2 red nodes): Both nodes hardwire LIVE_SLOT=2 through get_slot_db_url and write (rolled back) to an owner slot. Add one module fixture: template clone, seed_transitioned_story (protagonist with a current_location place carrying coordinates), and one accepted chunk with world_time, opened through tests.pg_fixtures.sqlalchemy_url.
- **`tests/test_lore/test_pass2_chunk1369.py`** (1 red nodes): This is an intentionally corpus-bound golden-master probe (chunk 1369, deep cut 743-770, named cast). Gate the module behind an explicit corpus opt-in (requires_corpus / NEXUS_RUN_CORPUS=1) and document it as an intentional integration exclusion. Add a read-only preflight on save_01 (chunk 1369 present, user_character bound) that fails with an explicit message before cloning. Do not attempt a seeded replacement; it would not test real retrieval ranking.
- **`tests/test_lore/test_retrieval_coverage_live.py`** (1 red nodes): Single node. Move from hardwired slot 5 to disposable_slot_database + seed_protagonist + one narrative chunk. Also update the stale pre-#903 contract: handle_user_input now only stages coverage, so call manager.record_rendered_coverage after each turn, as tests/test_lore/test_window_coverage_pg.py does. Keep the test: it is the only PostgreSQL proof that runs real entity detection into coverage and gap rows.
- **`tests/test_lore/test_scene_order_render.py`** (1 red nodes): Only the save_04 node is red. Seed at least 20 playable chunks with chunk_metadata in a template clone; the other PG nodes in this file already use template clones successfully.
- **`tests/test_lore/test_seat_blocks.py`** (1 red nodes): Single PG node. Use a template clone with seed_transitioned_story and one parent chunk that has exactly one 'setting' place_chunk_references row; pass its id as target_chunk_id.
- **`tests/test_memnon/test_ann_gate.py`** (3 red nodes): Split the module fixture `ann_clone` (slot_clone(1) of the owner's save_01). (a) A seeded fixture: disposable_slot_database('qa640_766_seed'), ensure_embedding_table(cur, 2560), plus a few narrative_chunks/chunk_metadata rows with 2560-dim vectors, used by test_ann_candidate_index_build_drop and test_ann_alias_candidates_and_database_errors. (b) Keep the save_01 clone only for test_ann_operator_measures_and_verdict behind an explicit corpus opt-in (a new requires_corpus marker plus NEXUS_RUN_CORPUS=1, registered in pytest.ini and tests/conftest.py), with a loud preflight that the table and at least probe_queries rows exist. The table is absent from fresh slots by design (migration 022 plus lazy creation), so this is not #810 schema drift.
- **`tests/test_mock_openai.py`** (2 red nodes): Add one fixture for both requires_postgres nodes. It yields disposable_slot_database('qa_mock_openai'), monkeypatches nexus.api.mock_openai.MOCK_DB to that name, and seeds one incubator row (parent_chunk_id 0, storyteller_text, choice_object {'presented': [two choices]}). Assert the seeded narrative is returned so the silent empty-incubator fallback cannot satisfy the test. As a follow-up under #804, move the hardcoded 'mock' database name into nexus.toml.
- **`tests/test_orrery/test_adjudication_history.py`** (2 red nodes): The module-level _connect(slot) hardcodes database=f'save_{slot:02d}' (WRITE_SLOT=2, HISTORY_SLOTS=(2, 5)), and the oracle test uses get_slot_db_url(slot=...). Add a module-scoped fixture on disposable_slot_database('adjudication_history') seeded with seed_protagonist and one chunk with chunk_metadata world_time. Use tests.pg_fixtures.connect and sqlalchemy_url instead of slot routing; get_slot_db_url would reject a disposable dbname unless it is added to VALID_DBNAMES. For the oracle, commit (do not roll back) a commit_orrery_tick_sync run with defer, replace and void rulings, and mark one resolution promoted, so the history oracle is non-vacuous by construction. The save_02/save_05 audit variant, including the non-vacuity guard, should move behind a new requires_corpus marker (for example NEXUS_RUN_CORPUS=1 in tests/conftest.py; none exists today), run on include_data clones, never live slots. Note that test_adjudication_history_matches_sql_oracle[2] and [5] currently pass vacuously on empty slots.
- **`tests/test_orrery/test_build_venture_async.py`** (1 red nodes): Replace the hardcoded asyncpg_kwargs('save_02') with a disposable clone. Recommended shared helpers for tests/pg_fixtures.py, reusable by all build_venture and court_patron files: `seed_character(dbname, name) -> (character_id, entity_id)`, for use after seed_protagonist has set base_timestamp, and `seed_timed_chunk(dbname, world_time) -> chunk_id` (INSERT narrative_chunks, INSERT chunk_metadata, then UPDATE world_time, because trg_chunk_metadata_refresh_world_time recomputes world_time on INSERT). This consolidates the dozen duplicated _insert_chunk helpers across tests/test_orrery. This test needs seed_protagonist plus one timed chunk.
- **`tests/test_orrery/test_build_venture_projects.py`** (3 red nodes): Rewrite `live_venture_db` (shared by all 3 nodes) to open pg_fixtures.connect() on disposable_slot_database('qa_build_venture'), seeded with seed_protagonist (actor), one extra character entity (other) and one timed chunk. Keep the shadow schema plus migration 084 and the rollback-on-teardown. No owner slot is touched.
- **`tests/test_orrery/test_build_venture_replay.py`** (1 red nodes): Rewrite `replay_db` on a disposable clone seeded with seed_protagonist and one narrative chunk. Change `_chunk` from max(id)+1 to sequence-assigned ids so it works on a chunk-less table and does not bypass the sequence.
- **`tests/test_orrery/test_card_identity.py`** (6 red nodes): The card_database fixture (disposable clone of save_04 with include_data=True) is shared by two corpus-bound tests that need different repairs. test_ren_rank_commit_replay replays JSON deltas from committed receipts and needs only a clock plus actors 4/6/13. Give it a seeded template clone: pinned entity ids, receipt names, base_timestamp. test_card_exposure_rank_joint_and_backstage_parity needs a real populated world to produce resolutions, scene pressures and joint beats. Gate it behind an explicit corpus opt-in, with a fixture-level fingerprint assertion that fails loudly when opted in and the source is empty. The same corpus marker would serve the other include_data=True users (test_drift_live, test_retrograde_projects_live, test_scheduler_corpus_pg, and others). Six non-PostgreSQL tests in this file stay green.
- **`tests/test_orrery/test_claim_accounts_live.py`** (5 red nodes): All five red nodes share account_connection. It connects to LIVE_SLOT=5 (imported from test_claim_propagation_live) via get_slot_db_url(slot=5) and relies on save_05 already having a story clock. Replace it with a module-scoped database fixture: 'with disposable_slot_database("qa964_claim_accounts") as dbname: seed_protagonist(dbname); yield dbname'. account_connection should then use create_engine(sqlalchemy_url(dbname)). get_slot_db_url cannot be used because require_slot_dbname rejects names outside VALID_DBNAMES. Keep the per-test connection.begin()/rollback, CREATE SCHEMA with SET LOCAL search_path, _install_account_shadow and _install_valence_shadow unchanged. Precedent: tests/test_orrery/test_distortion_live.py::live_conn already uses disposable_slot_database, seed_protagonist, install_claim_accounts_shadow_sync and the same claim_propagation_live helpers, and was green in the baseline. Also point the green test_async_variant_primitive_uses_real_postgres at asyncpg_kwargs(dbname) so the file stops touching save_05. Structurally, move the slot-free helpers (_insert_character, _insert_chunk, _insert_relationship, _install_valence_shadow, _settings, EPISTEMICS) and a shared seeded-clone fixture into a support module such as tests/test_orrery/claim_accounts_test_support.py. That stops claim_accounts, claim_consumption, distortion and the live_llm-marked test_claim_propagation_live (same slot-5 assumption; skipped in this gate) from importing LIVE_SLOT out of a test module. Nothing on main after b0645daf changes this file or its code path.
- **`tests/test_orrery/test_claim_consumption_live.py`** (8 red nodes): All eight red nodes share live_connection, which targets hardwired slot 5, and every test inserts characters before chunks. Apply the same repair as claim_accounts: a module-scoped disposable_slot_database with seed_protagonist (or a new clock-only pg_fixtures helper, seed_world_clock(dbname, base_timestamp), if a player row is unwanted), create_engine(sqlalchemy_url(dbname)), and a per-test transaction rollback with install_claim_accounts_shadow_sync and _install_valence_shadow. None of these tests needs a protagonist: hydrate_world_state, resolve_dry_run and explain_dry_run run with weather disabled and ambient None, and entity_context never calls canonical_player_*. A seeded player is still harmless to every assertion. Keep the clone module-scoped with per-test rollback so test_historical_anchor's max(narrative_chunks.id) == head_anchor stays valid.
- **`tests/test_orrery/test_communication_graph_live.py`** (8 red nodes): All eight nodes error in the communication_db setup, and the fixture has two owner-slot assumptions stacked on each other. (1) It connects to module-local LIVE_SLOT=5 and inserts characters with no story clock, which triggers the need-clock raise. (2) It then selects an existing active faction without operational_secrecy/operational_mode tags using .scalar_one(), which raises NoResultFound on any clone without factions. Repair: yield from 'with disposable_slot_database("qa964_communication") as dbname: seed_protagonist(dbname)' (module scope is fine; per-test rollback is kept), build the engine from sqlalchemy_url(dbname), and replace the corpus faction lookup with a fixture-created faction. Insert an entities row with kind 'faction' plus a factions row with id coalesce(max(id),0)+1, as test_faction_subject_status already does. That also guarantees the untagged baseline test_culture_profiles expects. The relationship inserts already hit the pg_temp shadow with the manual producer (#922). test_conflicted_live_pair should drop its Tomi/Kosi corpus read and seed an equivalent ward/captor pair (see its disposition). Otherwise it would skip on every clone and on the owner's now-empty save_05.
- **`tests/test_orrery/test_court_patron_async.py`** (1 red nodes): Replace asyncpg_kwargs('save_02') with a disposable clone seeded with two character entities (seed_protagonist plus one more) and one timed chunk. Keep write_producer='manual' and the shadow schema plus migration 086. Pair tags 'sponsors'/'obligation' come from the template seed tables.
- **`tests/test_orrery/test_court_patron_projects.py`** (2 red nodes): Rewrite `live_patron_db` (shared by both nodes here and by test_court_patron_replay.py via pytest_plugins) on a disposable clone seeded with two character entities and one timed chunk. Keep _create_schema's write_producer='manual' and the rollback-on-teardown.
- **`tests/test_orrery/test_court_patron_replay.py`** (1 red nodes): Fixed by the live_patron_db repair in test_court_patron_projects.py. Also change the borrowed test_pursue_romance_replay._fabricate_chunk from max(id)+1 to sequence-assigned ids. Run it after the repair to confirm verify_checkpoints_sync reports no drift on a sparse clone.
- **`tests/test_orrery/test_drift_live.py`** (1 red nodes): Only one of the 8 tests in this file failed. Seed a place inside test_colocated_characters_without_events_produce_no_versions instead of reading an arbitrary existing place. Switch the module fixture from source_db='save_03', include_data=True to a template clone, since every test self-seeds and the owner's save_03 corpus is unnecessary.
- **`tests/test_orrery/test_ecology_live.py`** (1 red nodes): Move the test off a hand-built save_02 connection onto disposable_slot_database with seed_protagonist (for the world clock), three characters, and one anchor chunk with world_time. The current test permanently changes characters.current_activity in the owner's save_02, because its cleanup does not restore it.
- **`tests/test_orrery/test_epistemics.py`** (12 red nodes): All 12 red nodes share one cause. The file reads owner save_02 content through three entry points: the save_02_conn fixture (get_slot_db_url(slot=2)), two SQLAlchemy tests (create_engine(get_slot_db_url(slot=2))) and one asyncpg test (hand-built kwargs, database='save_02'). The content they need is max(narrative_chunks.id) as an anchor, the first 2-4 characters with entity_id, one faction entity, and chunk_metadata.world_time. The fix is a module-scoped fixture, `epistemics_db`, built from `disposable_slot_database('qa964_epistemics')` and seeded once in this order: (1) seed_protagonist(dbname), which sets base_timestamp and user_character and so satisfies the need-clock trigger; (2) one narrative_chunks row plus a chunk_metadata row (season/episode/scene, world_layer 'primary', time_delta 0), whose world_time trg_chunk_metadata_refresh_world_time derives from base_timestamp; (3) four non-player characters, each with an active 'character' entity; (4) one factions row with an explicit id and an active 'faction' entity. The fixture yields dbname plus the ids. A function-scoped `save_02_conn` replacement then opens connect(dbname), installs install_claim_accounts_shadow_sync, and rolls back, so the existing per-test rollback isolation holds and the module clone is reused. Point the SQLAlchemy tests at sqlalchemy_url(dbname) and the asyncpg test at asyncpg_kwargs(dbname), which also retires the hand-built connection (#804). Replace `_anchor_and_characters` queries with the fixture ids. This file and more than 15 other test_orrery files carry private `_insert_chunk`/`_insert_character` copies; add `seed_accepted_chunk(cur, *, time_delta=...)`, `seed_character(cur, name)`, `seed_faction(cur, name)` and `seed_place(cur, name)` to tests/pg_fixtures.py once and reuse them.
- **`tests/test_orrery/test_evidence.py`** (1 red nodes): Only one PostgreSQL node. Replace LIVE_SLOT=5 and get_slot_db_url with a disposable clone seeded so that anchor-less compose_actor_bindings finds off-screen actors: seed_protagonist for base_timestamp, plus two or more non-player characters, each with a character_routine_anchors row (mobility_policy 'fixed_place', place_id pointing at a seeded place) or an active ephemeral entity_tags row. Confirm at runtime that the 'checked > 100' leaf threshold is met, or derive it from the number of actor-only templates times the number of seeded actors.
- **`tests/test_orrery/test_faction_project_contexts_live.py`** (8 red nodes): All 8 nodes error in faction_context_db setup. LIVE_SLOT=5 is empty on the owner's machine too (#922 class-a remainder). The line that fails is `SELECT id FROM places ... scalar_one()`; after it come int(max chunk id), character inserts that need the clock, and a `pytest.skip('save_05 needs two active faction entities')` that would hide the gap as a skip. The fix: wrap the fixture in `disposable_slot_database('qa964_faction_contexts')`. Seed in this order: seed_protagonist (clock), one place with an entity, one accepted chunk plus chunk_metadata (world_time derived from base_timestamp), and two factions with active entities. Then open the engine with sqlalchemy_url(dbname) and keep the fixture's own character, routine-anchor, obligation pair-tag and relationship inserts inside the rollback transaction. Replace the pytest.skip with the seeded factions. The fixture also re-executes migrations/081_faction_project_contexts.sql, which rewrites the target_faction_entity_id comment and trigger to their 081 versions over the template's post-096 schema. Remove that (#810 ownership) and, in the same change, update test_live_faction_rebinding_raises_loudly's expected comment to 096's text or to an 'immutable' substring check. Module scope for the clone is safe because every test rolls back.
- **`tests/test_orrery/test_knowledge_surfacing_live.py`** (2 red nodes): Both red nodes fail from harness drift after #932: _LiveLoreHarness.settings lacks lore.render_limits. Derive the harness settings from load_settings_as_dict(). Separately, the knowledge_db fixture opens a rolled-back write transaction in owner save_05 through get_slot_db_url(slot=5) and should move to disposable_slot_database (#885/#804).
- **`tests/test_orrery/test_migrate.py`** (1 red nodes): Only test_canonical_grieving_migration_executes_against_slot_db is red. It commits entities and entity_tags rows and runs migration 046's run(conn), which commits, against save_05 by name. Give it a per-test disposable_slot_database with seed_protagonist (tests.pg_fixtures.connect(dbname)) and drop the skip-on-unavailable branch and the manual cleanup. The other six *_executes_against_slot_db tests in this file also write to save_05 by name. They were not red, but they should move to the same fixture to satisfy #964's rule that owner saves are never used as test data.
- **`tests/test_orrery/test_orbit_distance_live.py`** (1 red nodes): This is a single test with an inline engine on module-local LIVE_SLOT=5. Wrap it in disposable_slot_database with seed_protagonist and build the engine from sqlalchemy_url(dbname). Also fix the masked second blocker: the four public.character_relationships inserts need relationship_producer_sqlalchemy(session, 'manual'), because migration 115's fail-closed provenance trigger will otherwise raise 'Missing or invalid nexus.write_producer' once the clock exists.
- **`tests/test_orrery/test_playable_narrative_boundary.py`** (1 red nodes): Only one node is PostgreSQL-backed. It clones the save_04 corpus only to borrow a prologue row and chunk ids 7, 8 and 9. Switch to a template clone. Seed a playable chunk, a prologue created with the production helper retrograde_persistence._insert_prologue_chunk, and a pending_review chunk, and assert on the returned ids. Gating behind a corpus flag would be less honest, since the contract is corpus-independent.
- **`tests/test_orrery/test_polymorphic_patron_live.py`** (1 red nodes): The single node's fixture targets slot 5, which is empty on the owner's machine too. It needs a place, a world clock (base_timestamp) before its character inserts, and a clocked chunk. Wrap it in disposable_slot_database, seed with seed_protagonist, one place and one accepted chunk with chunk_metadata, and use sqlalchemy_url(dbname). Drop the vestigial in-fixture execution of migration 096.
- **`tests/test_orrery/test_projects.py`** (2 red nodes): The two PostgreSQL nodes need different repairs. test_resolution_insert_skips_routine_promotion_but_queues_milestone needs only a template clone with seed_protagonist and one narrative_chunks row. test_slot2_coverage_distribution_and_project_gate_payload is a save_02 corpus-statistics probe: gate it behind a corpus flag on an include_data clone of save_02. Both use get_slot_db_url(slot=2) directly today. Also remove the in-test replay of migrations/074_plan_relocation_projects.sql. The template already carries 074, and replaying migration DDL inside a test is a template/migration drift hazard (#810-style).
- **`tests/test_orrery/test_pursue_romance_async.py`** (1 red nodes): The test connects to the literal 'save_02' through nexus.database.asyncpg_kwargs and needs two character entities and one clocked chunk from the public tables. Its pre-085 shadow schema for the project tables is self-contained. Seed a disposable clone with seed_protagonist, two characters and one chunk plus chunk_metadata, and connect with tests.pg_fixtures.asyncpg_kwargs(dbname). The _create_schema helper duplicates test_pursue_romance_projects.py; share one helper and seeding fixture between the two files.
- **`tests/test_orrery/test_pursue_romance_projects.py`** (1 red nodes): The live_romance_db fixture is hardwired to get_slot_db_url(slot=2) and needs two character entities and one clocked chunk. Use the same seeded disposable clone as the async twin; the other nodes in this file are pure and unaffected.
- **`tests/test_orrery/test_reconstruction.py`** (4 red nodes): All four red nodes share _connect(), which hardwires save_05, replays migrations/074, and creates 'CREATE TEMP TABLE backstory_secrets (id bigint) ON COMMIT DROP'. That temp table shadows the real migration-091 table through pg_temp search precedence, so checkpoints read an empty stub. This is obsolete scaffolding for pre-091 slots and should be removed along with the 074 replay. Replace the helper with a module-scoped disposable_slot_database('reconstruction') clone, seeded once with: seed_protagonist (base_timestamp, character and entity); a second character with entity; one place with entity_id; one narrative_chunks row plus chunk_metadata(world_layer='primary', world_time=base); one character_relationships row between the two characters written under nexus.agents.orrery.relationship_provenance.relationship_producer(cur, 'manual'); and one active entity_tags row on a character from the vocab tags table (base_timestamp must exist first, because need-applicability sync raises 'need-clock anchor unavailable' without a clock). Each test takes a fresh connect(dbname) and rolls back. Use the seeded ids rather than max(id) and LIMIT 1 lookups, and in the unattributed test read the version row by key or by id greater than a pre-update baseline.
- **`tests/test_orrery/test_recruit_ally_projects.py`** (5 red nodes): Four of the five nodes are setup errors in one fixture, live_project_db. It connects to get_slot_db_url(slot=2), and int(cur.fetchone()[0]) on max(id) FROM narrative_chunks raises on the empty slot. The fixture also carries a pytest.skip('save_02 needs three character entities') escape hatch that hides missing data as a skip, which the gate rules forbid. Rewrite it on disposable_slot_database('recruit_ally'). Seed: seed_protagonist plus two more characters with entities (actor, target, other); one place (for place_id); one narrative_chunks row with chunk_metadata(world_layer='primary', world_time=NOW or near it), which the project writers read through _tick_world_time_sync and without which they raise OrreryWorldClockUnavailableError. Keep SET LOCAL nexus.write_producer='manual', yield the seeded ids, remove the skip, and roll back per test. The fifth node (test_slot2_recruitment_routes_persisted_target_without_routine_drift) is a save_02 35-anchor corpus probe: gate it behind the corpus flag on an include_data clone and replace its pytest.skip with an assertion.
- **`tests/test_orrery/test_relationship_provenance_pg.py`** (1 red nodes): The drift_database fixture is imported from tests/test_orrery/test_drift_live.py and clones the owner-named save_03 with include_data=True. The fix belongs there. Switch it to a NEXUS_template clone (default source_db, include_data=False) plus seed_protagonist, and seed one place for test_drift_live's colocated test, which is in another batch. Only the analyst test is red, because it is the only test in the module that inserts characters before any chunk. The other tests pass on the empty clone only because refresh_world_time_from_chunk() falls back to wall-clock now() for chunk world_time when base_timestamp is NULL. That is a latent #640 inconsistency; consider filing it as a separate low-severity issue after confirming the template's function body.
- **`tests/test_orrery/test_replay.py`** (24 red nodes): All 24 red nodes have one cause. Module _connect() hardwires save_05 (WRITE_SLOT=5; NEXUS_REPLAY_TEST_DB may only name save_05 or qa640_*), and every test assumes the owner's populated native QA slot. In the baseline, save_05 on the private 55442 cluster was an empty template clone, so each test died at its first content read:
- _probe_character returned None (TypeError unpack).
- _project_probe_character asserted.
- _fabricate_chunk's 'max(id)+1' was NULL (NotNullViolation).
- the genesis-checkpoint probe asserted.
The tests fabricate their own post-checkpoint history inside always-rolled-back transactions (#428 pattern). They are not corpus probes, so the honest route is a seeded disposable clone, not gate_behind_corpus_flag. The test file is unchanged since b0645daf. Later replay.py/reconstruction.py/commit_handler_sync.py edits (#957: names in checkpoints, name reveals) do not touch this failure path. docs/qa/test-fallout-repair/verification.md (#922) already classed these IDs as class a (#885, empty save_05). That PR also added the SET LOCAL nexus.write_producer lines the relationship tests need.

Repair (one change for the whole file):
(1) Add a module-scoped replay_db fixture: 'with disposable_slot_database("qa640_replay") as dbname: seed_replay_corpus(dbname); yield dbname'. Every test takes replay_db, and _connect(dbname) returns pg_fixtures.connect(dbname). Delete WRITE_SLOT, the NEXUS_REPLAY_TEST_DB override and its assert. This also brings the file onto the #804 connection contract. Tests never commit (finally: rollback), so one seeded clone per module is safe.
(2) Delete _apply_migration_074 and its three call sites (_connect and two project tests). The template clone already stamps 074, and re-running a CWD-relative migration file inside tests is stale.
(3) New helper seed_replay_corpus(dbname). Put it in tests/pg_fixtures.py beside seed_protagonist, or in tests/test_orrery/replay_corpus_support.py following claim_accounts_test_support.py, so tests/test_orrery/test_reconstruction.py (identical save_05 pattern) can reuse it. Run it in ONE committed transaction, in this order:
  a. seed_protagonist(base_timestamp=B). It sets base_timestamp and user_character before the character INSERT, so trg_characters_need_state_init creates all five need rows anchored at B instead of raising 'need-clock anchor unavailable'.
  b. Two more active character entities with characters rows (3 total), for the pair-tag and relationship pair queries.
  c. Two places ('INSERT INTO places (name, type) ... fixed_location'). Set the protagonist's current_location to place 1 and give it a current_activity. No coordinates are needed; _estimate_route_sync tolerates NULL.
  d. A pre-instrumentation chunk and a head chunk (sequence ids), plus chunk_metadata for the head with time_delta NULL. trg_chunk_metadata_refresh_world_time then sets world_time = B, which makes _head_chunk, max(id)+1, _next_world_time (B+6h) and the 'primary clock' well defined. Without it, _next_world_time falls back to 2026-01-01 while seed_protagonist's default base is 2100-01-01, and need clocks would run backwards.
  e. set_commit_chunk_attribution_sync(cur, head) plus SET LOCAL nexus.write_producer='manual', then character_relationships (c1,c2) and (c1,c3) with emotional_valence '0|neutral', leaving (c2,c3) free.
  f. One durable, non-severity, non-need-immunity active entity tag via tag_writer._insert_entity_tag (source_chunk_id=head).
  g. Last: capture_state_checkpoint_sync(cur, chunk_id=head, label='genesis').
Seeding in one transaction keeps relationship and tag created_at at or before the head chunk's created_at, which matters because replay's wall-clock insert filter is strict '>'.
Optional hardening: make _fabricate_chunk assert that max(id) is not None, for a legible precondition failure. No product defect is indicated for any node.
- **`tests/test_orrery/test_retrograde_constraints_pg.py`** (4 red nodes): Fix the `disposable_dbname` fixture once for all 4 nodes. Replace the CREATE DATABASE ... TEMPLATE clone and the hand-executed migrations 097/123 with `with tests.pg_fixtures.disposable_slot_database('qa640_issue601') as dbname:`. That path uses initialize_slot_database, which copies the schema_migrations stamps and runs migrate_database, so only unapplied migrations run and no clone-locking of NEXUS_template occurs. Then run `UPDATE global_variables SET new_story = true, base_timestamp = '2026-05-14T10:48:00+00:00' WHERE id = true`, register VALID_DBNAMES, and call close_all_pools in teardown. Drop the pytest.skip on admin failure (the gate must fail loudly). If a minimal patch is wanted first, guard 123 with the information_schema check used in test_need_clock_anchor_pg.py:99-106. The durable fix is to stop hand-replaying migrations in fixtures (#810 migration ownership). Evidence: no commit after b0645daf touched this fixture; the only change on main (f5b0969b) adds confirm_artifact calls in _hydrate_fixture.
- **`tests/test_orrery/test_retrograde_maturation.py`** (4 red nodes): The module fixture maturation_corpus clones source_db='save_02' with include_data=True, so the result depends on whatever save_02 holds. All 4 PG nodes fail in _latest_chunk_id() on int(None) (`SELECT max(id) FROM narrative_chunks`). Switch to a plain template clone, disposable_slot_database('qa640_maturation799'), seed one narrative_chunks plus chunk_metadata row in the fixture, and hand its id to the tests. No assertion depends on corpus content, so seeding is more honest than gate_behind_corpus_flag. The offline tests in this file are unaffected.
- **`tests/test_orrery/test_retrograde_projects_live.py`** (19 red nodes): All 19 nodes error on the same fixture precondition: project_db asserts at least 12 characters, and the corpus is a copy of the empty private save_02 (disposable_slot_database(..., source_db='save_02', include_data=True)). No assertion depends on save_02-specific content. The file is 'live' PostgreSQL coverage with fabricated LLM contracts, so gating it behind a corpus flag would hide 19 production-writer tests. Seed a disposable clone instead (#885). The seeding helper is reusable for other files and belongs in tests/pg_fixtures.py (#816).

1. Change project_corpus to disposable_slot_database('qa640_projects799'), a template clone with no include_data, keeping VALID_DBNAMES registration.
2. Seed it through a shared helper, e.g. tests/pg_fixtures.seed_story_cast(dbname, npc_count=12, place_count=2):
   - seed_protagonist(dbname) first, which sets global_variables.base_timestamp before any character exists (the need-sync trigger otherwise raises 'need-clock anchor unavailable') and binds user_character. The create_missing_entities, maturation and resolve_dry_run paths need it.
   - 2 active place entities plus places(type 'fixed_location').
   - 12 active NPC character entities plus characters rows with distinct multi-word names and current_location set to a seeded place. Also set the protagonist's current_location.
   - One retrograde prologue chunk with authorial_directives [RETROGRADE_PROLOGUE_MARKER], mirroring a post-wizard story.
   - One accepted primary narrative chunk plus chunk_metadata whose world_time is pinned to base_timestamp, using the insert-then-UPDATE idiom from tests/test_orrery/test_need_clock_anchor_pg.py::_insert_chunk_at.
3. In project_db, exclude global_variables.user_character from the 12-character query so the actors are NPCs.
4. Make _fabricate_chunk insert without an explicit max(id)+1. That form inserts NULL on an empty table and can collide with the prologue's sequence nextval, because sequences are not rolled back.
5. Replace the stale '["retrograde_prologue"]' literal in test_wizard_genesis_checkpoint_carries_seeded_project_through_replay with json.dumps([RETROGRADE_PROLOGUE_MARKER]); the real marker is 'orrery:retrograde_prologue_anchor'.

Replay and resolver nodes (maturation replay, genesis replay, delayed-gate) need a run on the seeded clone to confirm drift-free verification.
- **`tests/test_orrery/test_reveal_live.py`** (9 red nodes): The live_conn fixture hardwires get_slot_db_url(slot=5). Chunk insertion works on an empty slot because refresh_world_time_from_chunk falls back to now() when base_timestamp is NULL, and test_verify_skips_checkpoint_that_predates_backstory_section was green. _insert_private_incident, however, selects the first existing places row, which accounts for all 8 sync TypeErrors. Fix: a module-scoped disposable_slot_database('reveal_live') clone plus seed_protagonist for a deterministic base_timestamp, connecting via tests.pg_fixtures.connect(dbname, cursor_factory=RealDictCursor). Make _insert_private_incident create its own place (entities kind='place' plus places(name, type='fixed_location', entity_id)). The async test should use tests.pg_fixtures.asyncpg_kwargs(dbname) and insert its own chunk and character entity rather than discovering 'latest clock' and 'first character'. Also consider replacing the readiness pytest.skip('slot 5 requires applied migrations 083 and 090') with a hard failure: a migrated clone always qualifies, and a skip hides gate debt. These bodies have been masked by the empty save_05 in the owner's environment too (#922 class a), so they need a run after repair.
- **`tests/test_orrery/test_seek_redemption_async.py`** (1 red nodes): The test connects to the literal 'save_02' through asyncpg_kwargs and discovers its actor and target from 'first two characters' and its chunk from 'latest world_time chunk'. Use a disposable template clone, seed two characters with entities and one clocked chunk, and pass the ids in. Keep SET LOCAL nexus.write_producer = 'manual'. It passes on the populated save_02 after #922, so a data-only repair is expected to suffice.
- **`tests/test_orrery/test_seek_redemption_projects.py`** (2 red nodes): The live_redemption_db fixture (also consumed by test_seek_redemption_replay.py via pytest_plugins) hardwires get_slot_db_url(slot=2) and unpacks the first two character entities plus the latest clocked chunk. Rebuild it on disposable_slot_database with seed_protagonist, a second seeded character, and a shared seed_chunk helper, keeping the shadow-schema build (event_types, orrery_resolutions, character_project_states plus migration 087) and the write_producer SET LOCAL. Consider moving the fixture into a shared helper module or conftest so the replay file does not import a test module as a plugin. The pure-offline evaluate() tests in this file are unaffected.
- **`tests/test_orrery/test_seek_redemption_replay.py`** (1 red nodes): This file fails only through live_redemption_db, so fix that fixture in test_seek_redemption_projects.py. Separately harden _fabricate_chunk in tests/test_orrery/test_pursue_romance_replay.py: `max(id) + 1` is NULL on an empty narrative_chunks table, so use COALESCE(max(id), 0) + 1 or the sequence. That removes the helper's hidden 'at least one chunk exists' precondition for every replay test that borrows it.
- **`tests/test_orrery/test_signal_events.py`** (2 red nodes): Both live tests hand-build connections to save_{WRITE_SLOT:02d}. The sync test reads PGHOST/PGUSER/PGPORT directly; the async test omits the port entirely. This is a secondary #804 contract violation. Replace both with a disposable template clone accessed through tests.pg_fixtures.connect / tests.pg_fixtures.asyncpg_kwargs, seed two characters with active entities and one chunk with chunk_metadata world_time, and use those ids in place of max(narrative_chunks.id) and 'first two character entities'. The offline tests are unaffected.
- **`tests/test_orrery/test_status_bestow_delta_live.py`** (3 red nodes): The status_delta_db fixture hardwires get_slot_db_url(slot=5). It already inserts its own character and faction entities, but it still needs an existing clocked chunk. Switch to a disposable template clone, seed one narrative_chunks plus chunk_metadata row (with seed_protagonist or an explicit base_timestamp so world_time is deterministic), and read world_time back from chunk_metadata for the provenance assertion. The pair_tags status:* vocabulary comes from template seed data. Suggested cross-file helper for all 7 files: add seed_chunk(cur, *, world_layer='primary', time_delta=None) -> (chunk_id, world_time), seed_character(cur, name, *, place_id=None) -> (character_id, entity_id), and seed_place(cur, name) -> (place_id, entity_id) to tests/pg_fixtures.py. That would replace the dozen-plus duplicated _insert_chunk helpers across tests/test_orrery.
- **`tests/test_orrery/test_tag_library.py`** (1 red nodes): Only the two save_05 probes touch PostgreSQL; the rest are monkeypatched unit tests.

- test_contextual_library_save_05_completeness_and_size failed on its corpus precondition.
- The sibling test_contextual_library_save_05_kosi_uses_character_entity_id calls pytest.skip when no character has id <> entity_id, so it silently skipped on the empty slot. That is hidden gate debt of the kind CLAUDE.md warns about.

Move both onto a disposable_slot_database('tag_library') module fixture registered in VALID_DBNAMES and seeded with:

- seed_protagonist;
- a place or faction entity inserted before the characters, so characters.id and entity_id skew;
- tags applied through tag_writer.apply_tag_bestowal both to a character's entity and to the unrelated entity whose id equals that character's row id, which the kosi namespace proof needs;
- one world-time chunk.

Switch the skipif decorators to requires_postgres. If the owner wants the realistic save_05 byte and token measurement, keep it as an optional corpus-flag probe; the gate should run the seeded version.
- **`tests/test_orrery/test_tag_provenance.py`** (4 red nodes): All 4 nodes fail on _anchor_and_actors ('save_02 is expected to hold at least two characters'). The module hardwires WRITE_SLOT=2: tests write rolled-back rows into the owner's save_02 through a hand-built psycopg2.connect and get_slot_db_url(slot=2), which is also #804 connection-contract debt.

Replace this with a module-scoped fixture that:

1. Opens disposable_slot_database('tag_provenance') and adds it to VALID_DBNAMES.
2. Calls seed_protagonist(dbname) for base_timestamp and user_character.
3. Inserts one additional active NPC character (entities plus characters).
4. Inserts one narrative chunk plus chunk_metadata with a pinned world_time, which becomes the max(id) anchor.

Then replace _connect() with tests.pg_fixtures.connect(dbname) and get_slot_db_url(slot=WRITE_SLOT) with sqlalchemy_url(dbname). Keep the per-test rollback discipline. Leave the slot=WRITE_SLOT argument to commit_orrery_tick_sync or drop it; the sync body ignores it. The 'off_grid' tag and 'hunting' pair tag come from the template seed vocabulary. No product defect is suspected.
- **`tests/test_place_tag_manifest.py`** (1 red nodes): Add one seeded-place clone fixture (prose that yields review_required candidates) routed as slot 2. Use it for both live CLI nodes, including the currently green manifest node, so neither reads the owner slot.
- **`tests/test_prose_metrics_pg.py`** (1 red nodes): Single node. Seed a small modern corpus on a template clone: storyteller_text, choice_object.presented, world_time, setting references, and one Retrograde prologue chunk so that total > measured. The script's refusal of an empty corpus is correct.
- **`tests/test_runtime/test_supervisor_live.py`** (1 red nodes): Not a data problem. The unmanaged-port refusal is correct, and only the optional lsof/ps listener suffix is missing in the guarded environment. Confirm by running lsof/ps timing in that environment, add -nP to the supervisor's lsof call and move its timeout into nexus.toml, and make the test probe _describe_port_occupant directly instead of shutil.which('lsof').
- **`tests/test_secret_manager.py`** (1 red nodes): The only red node calls the raw subprocess helper _delete_test_account against the real login Keychain after unsetting NEXUS_KEYRING_DISABLE. The same #963 adapter or test-backend fix applies. test_set_secret_persists_trimmed_value already shows the injection pattern (it replaces _write_macos_keychain/_write_keyring_library), but #963 asks for an explicit backend rather than monkeypatched privates. Keep the round-trip, cache-invalidation and case-folding assertions against the test backend by default, and move the real-store round trip behind an explicit platform-store opt-in with a proven-disposable target.
- **`tests/test_trait_compiler_integration.py`** (5 red nodes): All five nodes share one problem. TEST_DBNAME = 'save_05' is opened with a bare psycopg2.connect, followed by an environment-guard pytest.skip (a hidden-skip antipattern under the gate policy). Every test's first characters INSERT fires the need-state trigger, which needs a world clock. Fix: add a module-scoped fixture that yields disposable_slot_database('qa640_trait_compiler') after seed_protagonist(dbname), which sets base_timestamp and user_character. It should also call a new pg_fixtures helper (e.g. seed_player_location) that inserts layer, zone and place and sets the player's current_location, because test_full_trait_selection's domain place stub calls story_active_zone. Connect through tests.pg_fixtures.connect(dbname), keep the per-test conn.rollback() so tests can share the clone, and delete the skip guards. Follow-up worth a runtime A/B: _install_valence_shadow shadows 'pending migration 088', which is now in the template. It routes relationship writes to a temp table, so the real public.character_relationships valence and provenance triggers go unexercised. Consider removing it once the tests are green on a clone.

## Per-Node Dispositions

### `hardcoded_connection_target` (10 nodes)

#### `tests/test_api/test_backstage_endpoints_pg.py::test_backstage_gate_both_arms`

- Baseline outcome: failure; signature: `sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `migrate_to_pg_fixtures_connection` to #804; confidence 0.9; runtime confirmation needed
- Cause: The gated-off arm makes no database calls and completed: routes are removed, health and turn return 404 or 503, and exactly one catch-all is found. The gated-on arm monkeypatches get_slot_db_url with a lambda that returns the literal 'postgresql://pythagor@localhost:5432/<disposable_db>'. GET /api/dev/backstage/4/turn dials owner 5432 and the guard denies it, which matches the recorded sqlalchemy OperationalError. The test also reads Path('nexus.toml') relative to cwd, so it assumes pytest runs from the repo root. That holds for poetry run pytest and is not the cause.
- Prerequisite: backstage_case rows (any committed turn), plus a copy of nexus.toml with [orrery.dashboard].enabled toggled.
- Repair steps:
  1. Replace the on-arm lambda with the shared routing helper from file_notes.
  1. Optionally resolve nexus.toml through the repo root (Path(__file__).parents[2]/'nexus.toml') so the test does not depend on cwd.
  1. Rerun to confirm that the on arm returns 200 with 'correspondence' and that route_count stays 2.

#### `tests/test_api/test_backstage_endpoints_pg.py::test_empty_and_provisional_chunks_are_404`

- Baseline outcome: failure; signature: `sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `migrate_to_pg_fixtures_connection` to #804; confidence 0.9; runtime confirmation needed
- Cause: Both requests (chunk_id = latest+1000, which exists only in the incubator, and chunk_id = 1, the retrograde prologue) go through the client fixture's literal 'postgresql://pythagor@localhost:5432/<clone>' URL and are denied on owner 5432 before build_backstage_turn runs. backstage.py already raises BackstagePayloadError(404, 'Committed chunk N does not exist in this slot') for rows it excludes.
- Prerequisite: backstage_case rows: a pending incubator row at latest+1000 and the retrograde prologue chunk 1 with its prologue metadata.
- Repair steps:
  1. Same file-level routing fix (see file_notes).
  1. Rerun to confirm that both the provisional and the prologue chunk return 404 with 'Committed chunk' in the detail.

#### `tests/test_api/test_backstage_endpoints_pg.py::test_empty_slot_is_404`

- Baseline outcome: failure; signature: `sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `migrate_to_pg_fixtures_connection` to #804; confidence 0.92
- Cause: The test monkeypatches get_slot_db_url with an inline lambda that returns 'postgresql://pythagor@localhost:5432/<empty clone>'. empty_disposable_db was created on the private cluster through _connect('postgres') (PG env honored), but the request's SQLAlchemy engine dials owner 5432 and the guard denies it. No content assumption: the test wants a clone with zero committed chunks, and a template clone provides exactly that. On an empty slot, backstage._committed_chunks raises the clear 404 'The slot has no committed story turns'.
- Prerequisite: A schema-only template clone with no narrative_chunks rows. The NEXUS_template contract is schema, seed vocab and schema_migrations only, with no chunks.
- Repair steps:
  1. Replace the inline lambda with the shared routing helper from file_notes (database_url(empty_dbname), or patch slot_utils.slot_dbname/VALID_DBNAMES).
  1. Replace empty_disposable_db with a disposable_slot_database('qa_wt625_empty') fixture.

#### `tests/test_api/test_backstage_endpoints_pg.py::test_history_counts_field_level_relationship_writes`

- Baseline outcome: failure; signature: `sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `migrate_to_pg_fixtures_connection` to #804; confidence 0.9; runtime confirmation needed
- Cause: Same client fixture as the other backstage nodes: the first client.get('/api/dev/backstage/4/turn') goes through the monkeypatched get_slot_db_url literal 'postgresql://pythagor@localhost:5432/<clone>' and is denied on owner 5432. The seeded backstage_case clone lives on the private cluster (PGPORT honored by _connect), so the URL and the fixture disagree on which server to use.
- Prerequisite: backstage_case rows, in particular the prior relationship commit (chunk 4), whose incubator entity_updates change only dynamic and recent_events on the Victor->Celia relationship (two field-level writes).
- Repair steps:
  1. Same file-level routing fix as the other backstage nodes (see file_notes).
  1. Rerun and confirm that the prior-chunk writes are still exactly {dynamic, recent_events} and that history writes == 2 after the post-baseline commit_handler_sync changes.

#### `tests/test_api/test_backstage_endpoints_pg.py::test_payload_assembles_every_committed_stream`

- Baseline outcome: failure; signature: `sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `migrate_to_pg_fixtures_connection` to #804; confidence 0.9; runtime confirmation needed
- Cause: Module fixtures disposable_db and backstage_case create and seed the clone through the module _connect(), which honors PGHOST/PGPORT (private cluster 55442), so seeding succeeded. The sibling test_incubator_view_never_exposes_staged_correspondence uses the same backstage_case through _connect and is not red. The function-scoped client fixture then monkeypatches backstage_endpoints.get_slot_db_url with disposable_url(), which returns the hand-built literal 'postgresql://pythagor@localhost:5432/<clone>'. GET /api/dev/backstage/4/turn runs _slot_session -> create_slot_engine(url) -> url_connection_kwargs, which dials owner PostgreSQL on 5432, and the OS guard denies it: sqlalchemy OperationalError 'Operation not permitted'. The empty private slots and missing corpus play no part, because the test builds all of its own rows. No commit after b0645daf touched the test, the endpoint, backstage.py or the fixtures (checked with git log b0645daf..HEAD).
- Prerequisite: The rows backstage_case already writes: prologue chunk 1 via _insert_prologue_chunk/_ensure_prologue_metadata; committed chunks 2-3 with chunk_metadata slugs S01E01_001/002; place Rootline; characters Celia/Victor with entities and bidirectional character_relationships; global_variables.user_character and base_timestamp; chunks 4-5 committed via commit_incubator_to_database_sync; the hunting pair tag; a correspondence digest; orrery_adjudication_log, orrery_resolutions, orrery_scene_pressures, world_events and world_event_entities rows; a pending incubator row. The only missing piece is an endpoint URL that resolves to the same clone on the same server.
- Repair steps:
  1. Apply the file-level routing fix from file_notes: the client fixture resolves the clone through nexus.database.database_url(dbname), or patches slot_utils.VALID_DBNAMES and slot_utils.slot_dbname so the production get_slot_db_url resolves it.
  1. Rerun this node on the private lane. Its payload assertions (header chunk_label S01E01_004, orrery rows, history counts) were last run green only on the owner port and have never run on the private lane. commit_handler_sync changed after baseline (name reveals, bind_session_id), so confirm the payload shape at runtime.

#### `tests/test_api/test_backstage_endpoints_pg.py::test_requested_chunk_is_historically_bounded`

- Baseline outcome: failure; signature: `sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `migrate_to_pg_fixtures_connection` to #804; confidence 0.9; runtime confirmation needed
- Cause: GET /api/dev/backstage/4/turn?chunk_id=3 goes through the client fixture's hand-built localhost:5432 URL. SQLAlchemy dials owner PostgreSQL and the guard denies it. The fixture data on the private clone was created successfully.
- Prerequisite: backstage_case rows: committed chunk 3 (slug S01E01_002) with no correspondence exchanges or digest at or before it.
- Repair steps:
  1. Same file-level routing fix (see file_notes).
  1. Rerun to confirm turn_label t.2 and the empty correspondence for chunk 3.

#### `tests/test_lore/test_chunk_operations.py::TestTokenCalculation::test_calculate_chunk_tokens_narrative`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.OperationalError: connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `fix_test_environment_assumption` to #804; confidence 0.9
- Cause: The test requests sample_chunks -> db_connection from tests/test_lore/conftest.py. db_connection calls psycopg2.connect with literals from tests/test_lore/lore_test_settings.json 'Database' (name save_01, host localhost, port 5432), ignoring PGPORT and nexus.database. Setup dials owner 5432 and the guard denies it (setup error). There is also a latent content assumption: the test wants golden-master chunk 2 ('dialogue_offer', S01E01_002) raw_text from the owner's save_01. Its body is guarded by 'if chunk and "raw_text" in chunk:', so on an empty private slot a connection-only fix would make it pass while asserting nothing. calculate_chunk_tokens is a pure function (resolve_seat('skald') registry estimator over a string) and needs no database.
- Prerequisite: Only a realistic narrative text string of a few hundred tokens. A PostgreSQL row is not needed for what the function under test does.
- Repair steps:
  1. Drop @pytest.mark.requires_postgres and the sample_chunks dependency. Feed a committed multi-paragraph narrative excerpt (a module constant or tests/fixtures text file) to calculate_chunk_tokens.
  1. Make the bounds assertions (50 < tokens < 5000) unconditional. Remove the silent 'if chunk ...' guard.
  1. If coverage of reading chunk text from the database is wanted, move it behind the corpus opt-in described in the test_infrastructure file_notes and fail loudly when the chunk is missing, rather than skipping the assertion.

#### `tests/test_lore/test_infrastructure.py::TestInfrastructure::test_narrative_view_exists`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.OperationalError: connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `seed_disposable_clone` to #804; confidence 0.85
- Cause: Setup error: the db_connection fixture in tests/test_lore/conftest.py dials save_01 @ localhost:5432 from lore_test_settings.json and the guard denies it. Latent second failure: after the connection is fixed, an empty private slot or a schema-only clone still fails 'assert count > 0' on SELECT COUNT(*) FROM narrative_view. The view (migrations/118_world_clock_identity.sql) inner-joins narrative_chunks to chunk_metadata and exposes id, season, episode, scene, world_time, world_layer and raw_text, so the column checks pass on any template clone.
- Prerequisite: One narrative_chunks row (raw_text) with a matching chunk_metadata row (season, episode, scene, world_layer='primary', slug). The backstage fixture shows that direct insertion works on a template clone, and the world-time refresh trigger falls back to now() when base_timestamp is null.
- Repair steps:
  1. In the LORE conftest, yield a disposable_slot_database('qa_lore_infra') clone and connect with tests.pg_fixtures.connect.
  1. Seed one chunk and its metadata with a small helper (either add a shared seed_committed_chunk(dbname, ...) to tests/pg_fixtures.py next to seed_protagonist, or reuse retrograde_persistence._insert_prologue_chunk plus _ensure_prologue_metadata the way test_backstage_endpoints_pg does). Then assert count > 0.

#### `tests/test_lore/test_infrastructure.py::TestInfrastructure::test_postgresql_connection`

- Baseline outcome: failure; signature: `psycopg2.OperationalError: connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `migrate_to_pg_fixtures_connection` to #804; confidence 0.92
- Cause: The test body builds its own psycopg2.connect from the session 'settings' fixture (lore_test_settings.json 'Database': save_01 @ localhost:5432) and bypasses PG* env and nexus.database.connection_kwargs, so it dials owner 5432 and the guard denies it. The test then only checks current_database() == 'save_01', that narrative_chunks and chunk_metadata exist, and that any chunk_embeddings_* table name ends in 'd'. It needs no rows. In the owner's normal environment it reads the owner's live golden master directly, which #964 forbids for test data.
- Prerequisite: Any slot-shaped database cloned from NEXUS_template (narrative_chunks and chunk_metadata tables). No content.
- Repair steps:
  1. Connect with tests.pg_fixtures.connect(dbname) to a disposable_slot_database('qa_lore_infra') clone from the LORE conftest (see file_notes). Assert current_database() == that clone's name.
  1. Delete the 'Database' block from tests/test_lore/lore_test_settings.json. It is a settings.json-era literal and should not return.

#### `tests/test_lore/test_infrastructure.py::TestInfrastructure::test_test_scenes_available`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.OperationalError: connection to server at "localhost" (::1), port 5432 failed: Operation not permitted`
- Route: `gate_behind_corpus_flag` to #804; confidence 0.88
- Cause: Setup error: sample_chunks -> db_connection dials save_01 @ localhost:5432 and the guard denies it. This test is a corpus-bound probe by design. It asserts that all 18 curated golden-master scenes from lore_test_scenes.md (narrative_view ids 2, 5, 7, 10, 16, 17, 25, 35, 41, 50, 52, 60, 67, 376, 518, 537, 888, 910) exist with non-empty raw_text. With a fixed connection it would still fail on any empty private slot or template clone (0 of 18). Seeding 18 synthetic rows at those ids would only test the seeder.
- Prerequisite: The golden master save_01 corpus (1,425 chunks), including the 18 curated scene ids with raw_text and metadata. Per #885, save_01 is the only slot with a stable content contract.
- Repair steps:
  1. Add an explicit corpus opt-in: a new pytest.ini marker (for example requires_corpus), skipped in tests/conftest.py unless an env flag such as NEXUS_RUN_CORPUS=1 is set, so the default PostgreSQL gate reports it as an intentional skip, not red.
  1. Under the flag, read from a disposable_slot_database('qa_lore_corpus', source_db='save_01', include_data=True) clone, never the live slot. Keep sample_chunks and test_scenes in that corpus-only fixture.
  1. Gating is more honest than parametrizing over seeded slots here, because the test verifies the curated corpus itself. Coordinate the marker name with the other #964 batches so only one corpus flag is created.

### `keychain_access` (2 nodes)

#### `tests/test_api/test_secrets_endpoints.py::test_status_put_status_and_unknown_provider_flow`

- Baseline outcome: error; signature: `failed on setup with "PermissionError: [Errno 1] Operation not permitted: 'security'"`
- Route: `fix_test_environment_assumption` to #963; confidence 0.95
- Cause: The macOS-only isolated_keychain fixture unsets NEXUS_KEYRING_DISABLE, which explicitly re-enables the real store. Its setup then calls the module helper _delete_test_account(), which runs subprocess.run(['security', 'delete-generic-password', '-s', 'nexus-api', '-a', 'test-secret-455']) against the owner's login Keychain in the production nexus-api namespace. The OS guard blocks spawning 'security', so PermissionError [Errno 1] surfaces in fixture setup before any endpoint code runs. The test body would then write and read the same real Keychain item through PUT /api/secrets/{provider} -> set_secret -> _write_macos_keychain, and through status -> get_secret -> _read_macos_keychain. #963 records that PR #962's unguarded run did exactly that. Isolation is correctly enforced; the test design is the defect. The #963 worktree (claude/963-secret-store-test-isolation) is at main 36faaf8 with no changes, so this is not fixed yet.
- Prerequisite: An explicit, disposable secret store that provably is not the owner's login Keychain or the production 'nexus-api' service, for setup, write, read and teardown. For the default path, an injected test backend that lets set_secret/get_secret keep their real lru_cache invalidation and case-folding logic.
- Repair steps:
  1. Add a production seam per #963: a secret-store adapter (for example a [secrets] backend or keychain/service override in nexus.toml, or a set_backend() injection point) so tests can select an explicit memory or temp-file backend without monkeypatching private helpers or unsetting NEXUS_KEYRING_DISABLE.
  1. Rewrite isolated_keychain to install that test backend, and make _delete_test_account go through the same backend. Keep the endpoint assertions: absent status, PUT, masked last4, refreshed status, 404 for an unknown provider, no key echo.
  1. Add an autouse tripwire in tests/conftest.py, like _forbid_unopted_postgres_connections, that fails any subprocess 'security' call or keyring access unless a separate platform-store opt-in marker or flag is set.
  1. Put any real platform-store variant behind that opt-in, using a throwaway keychain (security create-keychain in tmp) and a unique service name, and assert the target before any operation.
  1. Make guard verification a fail-closed preflight of the full-gate launcher (#963 acceptance).

#### `tests/test_secret_manager.py::test_set_secret_round_trip_and_overwrite_clear_cached_value`

- Baseline outcome: failure; signature: `PermissionError: [Errno 1] Operation not permitted: 'security'`
- Route: `fix_test_environment_assumption` to #963; confidence 0.95
- Cause: The test is Darwin-only (skipif). It unsets NEXUS_KEYRING_DISABLE and <ACCOUNT>_API_KEY, then calls _delete_test_account() at line 42, before its try block. That helper subprocesses the real 'security delete-generic-password -s nexus-api -a test-secret-455' against the owner's login Keychain. The OS guard denies spawning 'security', so the test fails with PermissionError [Errno 1] before set_secret is reached. The intended coverage (write, lru-cached read, uppercase-account overwrite clearing the cache, read again) only runs against the real production-namespace Keychain. #963 documents that an unguarded run touched it. Unchanged since baseline, and the #963 worktree has no changes.
- Prerequisite: An explicit test secret-store backend, or a proven-disposable keychain plus a non-production service name, so set_secret and get_secret run their real code paths: strip, lowercase account, cache_clear on write.
- Repair steps:
  1. Using the #963 adapter seam (see the secrets endpoint node), run the round trip against a memory or temp-file backend by default. Assert that get_secret returns the second value after set_secret(TEST_ACCOUNT.upper(), second), which proves the lowercase account plus cache invalidation.
  1. Remove the raw subprocess _delete_test_account helper from the default path. Its teardown goes through the injected backend.
  1. Move the real Keychain round trip behind the platform-store opt-in with a throwaway keychain and a unique service, and verify the target before any delete.

### `template_or_migration_drift` (4 nodes)

#### `tests/test_orrery/test_retrograde_constraints_pg.py::test_persistence_identity_binds_database_alias_without_packet_alias`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.errors.DuplicateColumn: column "provenance" of relation "character_aliases" already exists"`
- Route: `migrate_to_pg_fixtures_connection` to #810; confidence 0.95
- Cause: The module fixture `disposable_dbname` (lines 64-126) clones the template with `CREATE DATABASE ... TEMPLATE "NEXUS_template"` and then hand-executes migrations 097 and 123 from disk (lines 85-97). Migration 097 is idempotent (`ADD COLUMN IF NOT EXISTS`), but `migrations/123_character_alias_provenance.sql` is a bare `ALTER TABLE character_aliases ADD COLUMN provenance ...`. #929 (e0d9424c) added the 123 replay while the owner's fleet template still lacked 123. The private baseline template was already stamped past 123, so the replay raised DuplicateColumn during setup before any test body ran. Sibling fixtures guard the same replay with an information_schema check (tests/test_orrery/test_need_clock_anchor_pg.py:99-106, tests/test_orrery_tag_validation_pg.py:224-231, tests/test_connection_lifecycle.py:206-220), and none of those files appear in the red inventory. docs/qa/954-wizard-revision-confirmation/verification.md:104-108 already records these exact four setup errors with this cause. This is a fixture defect: hand-replayed migrations do not consult schema_migrations stamps, so they break whenever the template's migration level changes. The fixture also calls pytest.skip when the admin connection is unavailable, which goes against the gate's fail-loud rule.
- Prerequisite: A template clone brought to head through the stamp-aware runner (schema_migrations copied, only unapplied migrations run), not a hand replay of 097/123. The global_variables row with new_story=true and base_timestamp='2026-05-14T10:48:00+00:00' must exist before any character INSERT. Also needs the checked-in tests/fixtures/slot3_midnight_qa_wizard_cache.json and the clone name in VALID_DBNAMES.
- Repair steps:
  1. Apply the shared fixture repair in file_notes (replace the hand-rolled clone with tests.pg_fixtures.disposable_slot_database).
  1. This test adds its own character_aliases row for the protagonist inside `persist`; no extra seed is needed.

#### `tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_compiler_gate_suppresses_all_named_target_materialization`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.errors.DuplicateColumn: column "provenance" of relation "character_aliases" already exists"`
- Route: `migrate_to_pg_fixtures_connection` to #810; confidence 0.95
- Cause: Same shared `disposable_dbname` fixture. It re-executes the non-idempotent `migrations/123_character_alias_provenance.sql` (`ADD COLUMN provenance`) against a template clone that already has the column, so setup errors with DuplicateColumn and the test body never runs. See the first node of this file for the provenance (#929 added the unguarded replay; sibling fixtures guard it; docs/qa/954 records the same four errors).
- Prerequisite: A head-schema template clone migrated by stamps. global_variables.base_timestamp and new_story=true set before the transition inserts characters. The slot3 wizard-cache fixture JSON.
- Repair steps:
  1. Apply the shared fixture repair in file_notes.
  1. No per-test seed is needed: the test writes its own cache and runs the full mapper transition.

#### `tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_packet_and_transition_keep_event_without_adversarial_rows`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.errors.DuplicateColumn: column "provenance" of relation "character_aliases" already exists"`
- Route: `migrate_to_pg_fixtures_connection` to #810; confidence 0.95
- Cause: Same shared `disposable_dbname` fixture: an unguarded hand replay of migration 123 on a template clone that already has character_aliases.provenance raises DuplicateColumn during setup. The packet, validation and persistence code under test is never reached.
- Prerequisite: A head-schema template clone migrated by stamps. global_variables base_timestamp and new_story=true. The slot3 wizard-cache fixture JSON. The seed-eligible vocabulary (event_types/tags/pair_tags) copied from the template seed tables.
- Repair steps:
  1. Apply the shared fixture repair in file_notes.
  1. No per-test data is needed beyond what _hydrate_fixture writes.

#### `tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.errors.DuplicateColumn: column "provenance" of relation "character_aliases" already exists"`
- Route: `migrate_to_pg_fixtures_connection` to #810; confidence 0.93
- Cause: Same shared `disposable_dbname` fixture: setup errors with DuplicateColumn from the unguarded replay of migration 123. The test body's own relationship writes already declare `SET LOCAL nexus.write_producer = 'manual'` (#922 fixed its earlier provenance failure), so the setup replay is the only blocker in the recorded trace.
- Prerequisite: A head-schema template clone migrated by stamps. base_timestamp set before the test's direct `INSERT INTO characters` (the need-state trigger requires a clock anchor). The slot3 wizard-cache fixture JSON. load_settings().orrery.projects.
- Repair steps:
  1. Apply the shared fixture repair in file_notes.
  1. Keep the fixture's base_timestamp write (now as an UPDATE of the row ensure_global_variables creates) so the test's direct character inserts find a need-clock anchor.

### `ann_table_absent` (3 nodes)

#### `tests/test_memnon/test_ann_gate.py::test_ann_alias_candidates_and_database_errors`

- Baseline outcome: failure; signature: `sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedTable) relation "chunk_embeddings_2560d" does not exist`
- Route: `seed_disposable_clone` to #885; confidence 0.88
- Cause: Shares the `ann_clone` fixture. The first statement selects `chunk_id, model, embedding::text FROM chunk_embeddings_2560d`, which raised ProgrammingError(UndefinedTable) because the empty private save_01 has no lazily created 2560d table. alias_lookup is passed explicitly, so no player identity is needed. The test only needs one embedded chunk whose raw_text yields a lowercase token of three or more letters other than 'gender'. chunk_metadata is LEFT JOINed but must exist as a table so the time_delta rename check works.
- Prerequisite: One narrative_chunks row with raw_text containing an ordinary English word, an optional chunk_metadata row, and a chunk_embeddings_2560d row for that chunk under any model string. The template's chunk_metadata.time_delta and narrative_chunks.raw_text columns (the test renames them transactionally).
- Repair steps:
  1. Use the seeded fixture from test_ann_candidate_index_build_drop: disposable_slot_database, then ensure_embedding_table(cur, 2560).
  1. Insert 2-3 narrative_chunks (raw_text, storyteller_text) with chunk_metadata, plus one 2560-dim vector per chunk (a deterministic self-match vector is enough; the test only checks that the query chunk ranks first).
  1. Keep the rename-and-rollback error-propagation checks; they need only the template schema.

#### `tests/test_memnon/test_ann_gate.py::test_ann_candidate_index_build_drop`

- Baseline outcome: failure; signature: `psycopg2.errors.UndefinedTable: relation "chunk_embeddings_2560d" does not exist`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: Shares the `ann_clone` fixture (a pg_dump/restore of save_01). The test drops and builds the candidate HNSW index on chunk_embeddings_2560d. On the empty private save_01 that table never existed (migration 022 drops empty embedding tables; creation is lazy), so the index DDL raised UndefinedTable. The test only needs the table to exist; it asserts on the index definition and its removal, not on corpus rows.
- Prerequisite: A database with a chunk_embeddings_2560d table (rows optional; HNSW builds on an empty table) and the pgvector halfvec operator class.
- Repair steps:
  1. Move this test to a seeded fixture: tests.pg_fixtures.disposable_slot_database('qa640_766_seed'), then nexus.agents.memnon.utils.embedding_tables.ensure_embedding_table(cur, 2560), the production lazy-creation path.
  1. No corpus needed. Keep the existing assertions (USING hnsw, halfvec(2560), to_regclass NULL after drop).

#### `tests/test_memnon/test_ann_gate.py::test_ann_operator_measures_and_verdict`

- Baseline outcome: failure; signature: `psycopg2.errors.UndefinedTable: relation "chunk_embeddings_2560d" does not exist`
- Route: `gate_behind_corpus_flag` to #885; confidence 0.9
- Cause: The module fixture `ann_clone` calls scripts/qa_shift/ann_gate.slot_clone(1), which pg_dumps save_01 and restores it into a qa640_766_* clone. measure_clone then ANALYZEs and queries chunk_embeddings_2560d. That table is not part of the fresh-slot schema: migration 022 drops empty chunk_embeddings_* tables, and write paths create them lazily through ensure_embedding_table. The private save_01 was an empty template clone, so the table did not exist and the query raised UndefinedTable. The absence is correct schema for an empty slot. It is not template or migration drift, so #964's tentative #810 routing does not fit. The test is a deliberately corpus-bound measurement: the module docstring says 'read-only-source save_01 clone', and it asserts verdict KEEP_EXACT with reason 'planner_prefers_sequential_scan' for the golden-master corpus (the 1,425-document history cited in nexus.toml [memnon.retrieval.ann]).
- Prerequisite: save_01 golden-master corpus with chunk_embeddings_2560d holding at least probe_queries (20) rows, and at least 10 rows per model, with matching narrative_chunks. pgvector with halfvec/HNSW support.
- Repair steps:
  1. Keep this measurement on the save_01 clone, but put it behind an explicit corpus opt-in: register a `requires_corpus` marker in pytest.ini and have tests/conftest.py skip it unless NEXUS_RUN_CORPUS=1. Document the exclusion in the gate notes.
  1. When the flag is set, preflight save_01 (read-only) and fail loudly if chunk_embeddings_2560d is missing or has fewer than probe_queries rows.
  1. Gating is more honest than seeding here. A seeded 20-vector clone would exercise the operator mechanics, but on a tiny table 'planner_prefers_sequential_scan' is trivially true and says nothing about the corpus the gate exists to measure.

### `mock_database_absent` (2 nodes)

#### `tests/test_mock_openai.py::test_mock_responses_routes_bootstrap_schema_as_final_result_tool`

- Baseline outcome: failure; signature: `psycopg2.OperationalError: connection to server at "127.0.0.1", port 55442 failed: FATAL: database "mock" does not exist`
- Route: `parametrize_slot_or_fixture` to #816; confidence 0.95
- Cause: responses_create routes StorytellerResponseBootstrap to get_cached_bootstrap_narrative, which queries the incubator table through get_mock_connection. That opens psycopg2 on `connection_kwargs(MOCK_DB)`, and MOCK_DB is hardcoded to "mock" (nexus/api/mock_openai.py:36). The owner's cluster has a hand-maintained `mock` database; the private port-55442 cluster does not, so the connect raised FATAL 'database "mock" does not exist'. The test therefore depends on owner-machine state. The only fixture that provisions `mock` is test_connection_lifecycle.py, which creates it inside its own throwaway clusters. Also note: if `mock` exists but the incubator is empty, the code returns a silent fallback ('[TEST MODE] No mock data available' with two choices) that still validates, so today the test can pass without exercising the DB-backed branch.
- Prerequisite: A database the mock server reads, with the template schema (incubator table) and one incubator row (storyteller_text plus choice_object {'presented': [2-4 choices]}), selected through an injectable name instead of the literal 'mock'.
- Repair steps:
  1. Add a fixture that yields tests.pg_fixtures.disposable_slot_database('qa_mock_openai') and monkeypatches nexus.api.mock_openai.MOCK_DB to that name (get_mock_connection reads the module global at call time).
  1. Seed one incubator row, as test_connection_lifecycle.py:271-280 does: INSERT INTO incubator (parent_chunk_id, storyteller_text, choice_object) VALUES (0, <text>, Json({'presented': [..2 choices..]})).
  1. Assert that the returned narrative equals the seeded storyteller_text, so the empty-table fallback can no longer satisfy the test.
  1. Optionally, under #804, move the hardcoded 'mock' database name into nexus.toml (for example [runtime.services.mock_openai].database), per the no-hardcoded-settings directive.

#### `tests/test_mock_openai.py::test_mock_responses_routes_bootstrap_schema_as_native_text_format`

- Baseline outcome: failure; signature: `psycopg2.OperationalError: connection to server at "127.0.0.1", port 55442 failed: FATAL: database "mock" does not exist`
- Route: `parametrize_slot_or_fixture` to #816; confidence 0.95
- Cause: Same path as the final_result_tool variant, with native text.format instead of a tool. _requested_output_properties detects the bootstrap schema, and get_cached_bootstrap_narrative calls get_mock_connection on the hardcoded database "mock", which does not exist in the private cluster (FATAL database "mock" does not exist).
- Prerequisite: An injectable mock-server database with the template schema and one seeded incubator row.
- Repair steps:
  1. Use the same shared fixture as the sibling test: a disposable clone, monkeypatched MOCK_DB, and a seeded incubator row.
  1. Assert that output_text parses to the seeded narrative and choices.

### `environment_path_or_port` (1 nodes)

#### `tests/test_runtime/test_supervisor_live.py::test_up_refuses_port_held_by_unmanaged_process`

- Baseline outcome: failure; signature: `assert 'Listener: pid=' in "Port 62061 is already in use by an unmanaged process; refusing to spawn 'gateway'. Adjust [runtime.services.gateway] ...sion, kill that pid...`
- Route: `fix_test_environment_assumption` to new-issue; confidence 0.4; product defect suspected, runtime confirmation needed
- Cause: The refusal itself works (returncode 1, 'already in use by an unmanaged process', NEXUS_GATEWAY_PORT hint present). Only the optional ' Listener: pid=...' suffix is missing. It is added only when nexus/runtime/supervisor._describe_port_occupant returns a description. That function runs 'lsof -ti tcp:<port> -sTCP:LISTEN' then 'ps -o pid=,etime=,command= -p <pid>' with a hardcoded 5 s timeout, and returns None on empty output, TimeoutExpired or OSError. The test requires the suffix whenever shutil.which('lsof') is truthy. In the same baseline run, the sigkill test's own 'lsof -nP -iTCP:<port> -sTCP:LISTEN' found the pytest process's listener, so lsof exists and can see same-user sockets. The likely causes are therefore environment-specific: lsof exceeding 5 s under full-gate load, host/service name resolution (no -n/-P) under the OS guard, or ps being denied. The owner's unguarded run presumably passes.
- Prerequisite: A host where lsof and ps can identify the listening pytest process from a grandchild subprocess within the diagnostic timeout.
- Repair steps:
  1. Confirm in the guarded environment: bind a listener in pytest, then time 'lsof -ti tcp:<port> -sTCP:LISTEN' and 'ps -o pid=,etime=,command= -p <pid>' from a subprocess.
  1. Product hardening: add -n -P to the supervisor's lsof call, as the tests' own lsof calls do, and move the 5 s diagnostic timeout into nexus.toml per the no-hardcoded-tunables directive.
  1. Test: replace the shutil.which('lsof') precondition with a direct probe, asserting _describe_port_occupant(GATEWAY_PORT) from the test process returns 'pid=<os.getpid()> ...' before calling 'up'. A host that cannot introspect then fails on a clearly labeled precondition instead of a confusing message assertion.
- Product defect detail: Low severity. The diagnostic silently degrades to no listener identity: lsof runs without -n/-P (it may attempt name resolution) and with a hardcoded 5 s timeout, so on a loaded or sandboxed host the operator loses the pid hint the error message promises. The refusal behavior is correct.

### `fixture_helper_defect` (2 nodes)

#### `tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[False]`

- Baseline outcome: failure; signature: `pydantic_core._pydantic_core.ValidationError: 4 validation errors for RenderLimits`
- Route: `other` to none; confidence 0.95
- Cause: This failure does not depend on the environment. The test's _LiveLoreHarness builds a hand-written settings dict with no 'lore' section. TurnCycleManager.assemble_context_payload calls _select_scene_payload, which runs RenderLimits.model_validate(self.lore.settings.get('lore', {}).get('render_limits', {})) (nexus/agents/lore/utils/turn_cycle.py:1151). The four required fields (relationships, events, threats, bleed_menu) are missing, giving 'ValidationError: 4 validation errors for RenderLimits'. The call was added by d30d256a (#932, 2026-09-24), after the test was last touched in e0d9424c (#929), so this is test drift and would also fail on the owner's machine. The knowledge_db fixture itself works on the empty slot 5, since its sibling digest tests passed.
- Prerequisite: Harness settings containing lore.render_limits, taken from nexus.toml and not hardcoded.
- Repair steps:
  1. Build the harness settings from load_settings_as_dict() (or at least copy lore.render_limits from load_settings().lore.render_limits.model_dump()) and then override the orrery.knowledge, experiences and bleed keys the test needs.
  1. Separately, per #885/#804, move knowledge_db off get_slot_db_url(slot=5), a rolled-back write transaction in the owner's save_05, onto disposable_slot_database.

#### `tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True]`

- Baseline outcome: failure; signature: `pydantic_core._pydantic_core.ValidationError: 4 validation errors for RenderLimits`
- Route: `other` to none; confidence 0.95; runtime confirmation needed
- Cause: Same as the [False] variant: _LiveLoreHarness.settings lacks lore.render_limits, and RenderLimits.model_validate in _select_scene_payload (added in #932) raises 4 validation errors before any knowledge digest is attached.
- Prerequisite: Harness settings containing lore.render_limits from nexus.toml.
- Repair steps:
  1. Same harness-settings fix as the [False] variant; derive the settings from load_settings_as_dict().

### `empty_slot_missing_clock` (33 nodes)

#### `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93; runtime confirmation needed
- Cause: Setup error in the module's temp_character fixture. It writes straight into hardwired WRITE_SLOT=5 (save_05), running INSERT INTO entities (kind) VALUES ('character') and then INSERT INTO characters. The characters insert fires trg_characters_need_state_init (migration 057), which calls orrery_sync_character_need_states(entity_id). As redefined in migrations/100_orrery_need_clock_anchor.sql:96-103, that function computes COALESCE(MAX(chunk_metadata.world_time), global_variables.base_timestamp) and raises 'need-clock anchor unavailable' when both are NULL. The private save_05 is an empty template clone, so it has no chunk world_time and no base_timestamp. docs/qa/test-fallout-repair/verification.md:331-334 shows the owner's save_05 is also empty, so this fails on the owner machine too. The test body never ran.
- Prerequisite: A writable slot routed to the test with global_variables.base_timestamp set before any character insert. Also one character row with an active character entity (the temp character). The upload root must be writable.
- Repair steps:
  1. Replace WRITE_SLOT=5 and temp_character with a function-scoped fixture on tests.pg_fixtures.disposable_slot_database. Route the clone by patching slot_utils.VALID_DBNAMES/slot_dbname and slot_mutations.slot_dbname (asset uploads call require_writable_slot); tests/test_api/conftest.py offline_gate_db already does this for slot 4.
  1. Call seed_protagonist(dbname) (or at least UPDATE global_variables SET base_timestamp) before inserting the temp character so the need-state trigger has an anchor.
  1. monkeypatch asset_endpoints.UPLOAD_ROOT to tmp_path, and have the test read asset_endpoints.UPLOAD_ROOT instead of its import-time UPLOAD_ROOT binding. This keeps portraits out of the repo's ui/client/public/character_portraits/<id>, where low clone character ids can collide with the owner's real portrait directories.

#### `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_delete_handles_legacy_leading_slash_paths`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93; runtime confirmation needed
- Cause: Same setup error as the other asset nodes: the temp_character insert into hardwired save_05 trips orrery_sync_character_need_states ('need-clock anchor unavailable') because the empty slot has no chunk world_time and no base_timestamp. A masked follow-on risk: the body mkdirs and writes legacy.png under the repo's real UPLOAD_ROOT (ui/client/public/character_portraits/<id>). The OS guard on protected writes may block that, and it pollutes the owner tree.
- Prerequisite: A routed disposable writable slot with global_variables.base_timestamp and one temp character. A writable, test-owned upload root.
- Repair steps:
  1. Use the shared seeded, routed asset fixture described in file_notes (disposable_slot_database + seed_protagonist + slot_utils/slot_mutations routing).
  1. Patch asset_endpoints.UPLOAD_ROOT to tmp_path and build rel_dir from the patched attribute.

#### `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_invalid_type_rejected`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: Setup error in temp_character. Inserting a character into hardwired empty save_05 fires the need-state trigger, which raises 'need-clock anchor unavailable' (no chunk_metadata.world_time and no global_variables.base_timestamp). The assertion itself (400 on image/gif) never ran, and it does not depend on slot content.
- Prerequisite: A routed disposable writable slot with base_timestamp and one temp character.
- Repair steps:
  1. Use the shared seeded, routed asset fixture (see file_notes). No change to the assertion is needed.

#### `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_portrait_upload_set_main_delete`

- Baseline outcome: error; signature: `failed on setup with "psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93; runtime confirmation needed
- Cause: Setup error in temp_character. The character insert into hardwired empty save_05 fires trg_characters_need_state_init, and orrery_sync_character_need_states raises 'need-clock anchor unavailable'. After the clock is fixed, the body writes real files under the repo's ui/client/public/character_portraits/<id> via _handle_upload. The OS guard may block that, and it risks colliding with owner portrait directories in a clone whose character ids restart low.
- Prerequisite: A routed disposable writable slot (slot_utils and slot_mutations routing, unlocked) with base_timestamp and one temp character. UPLOAD_ROOT pointed at tmp_path.
- Repair steps:
  1. Use the shared seeded, routed asset fixture (see file_notes).
  1. Patch asset_endpoints.UPLOAD_ROOT to tmp_path and compute `stored` from the patched root.

#### `tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection`

- Baseline outcome: failure; signature: `sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The test hardwires LIVE_SLOT=5 through get_slot_db_url(slot=5). Inside a rolled-back transaction it inserts an active character entity plus a characters row ('Coverage Hit Probe'). trg_characters_need_state_init calls orrery_sync_character_need_states, which raises 'need-clock anchor unavailable' because empty save_05 has no chunk_metadata.world_time and no base_timestamp. docs/qa/911-passage-limit and docs/qa/test-fallout-repair record the same failure on the owner's empty save_05. Two more defects are masked behind this one. (1) The CTE takes max(nc.id) FROM narrative_chunks; with no chunk, reference_row is empty and `.one()` raises NoResultFound. (2) The test predates #903 (20e2c07, before baseline b0645daf). #903 changed ContextMemoryManager.handle_user_input to only _stage_retrieval_coverage; rows are written by record_rendered_coverage after rendering. The test never calls record_rendered_coverage, so even with a clock and a chunk, retrieval_coverage_log gets 0 rows and `assert len(rows) == 2` fails. The second handle_user_input call would also overwrite the first staged record. tests/test_lore/test_window_coverage_pg.py is the post-#903 disposable-slot proof of the staged/render contract, but it bypasses real entity detection. This test still adds unique coverage of detection-to-coverage through handle_user_input, so repair it rather than delete it.
- Prerequisite: A disposable slot with global_variables.base_timestamp (so character inserts pass the need trigger) and at least 1 narrative_chunks row (the covered chunk). Two probe characters, with a chunk_character_references 'present' row for the covered one. The test must call manager.record_rendered_coverage(...) after each handle_user_input so rows are written.
- Repair steps:
  1. Replace get_slot_db_url(slot=LIVE_SLOT) with `with disposable_slot_database('qa640_retrieval_coverage') as dbname:` and create_engine(database_url(dbname)). Call seed_protagonist(dbname) (sets base_timestamp) and insert one narrative_chunks row before the probes. Drop the redundant re-execution of migration 075, since the clone is migrated.
  1. After each manager.handle_user_input(...), call manager.record_rendered_coverage(update.retrieved_chunks or the LiveReferenceMemnon chunk list, {chunk_id: tokens}), mirroring test_window_coverage_pg.py, so the #903 post-render contract writes one row per turn.
  1. Keep the detection, coverage and gap assertions. Pass the fixture dbname label to format_retrieval_coverage_report.

#### `tests/test_orrery/test_claim_accounts_live.py::test_latent_sibling_secret_stays_private_until_its_own_gate_fires`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93; runtime confirmation needed
- Cause: The account_connection fixture opens a rolled-back SQLAlchemy transaction on get_slot_db_url(slot=LIVE_SLOT). LIVE_SLOT=5 is imported from test_claim_propagation_live, so in the baseline this was the private, empty save_05. The fixture then installs schema-local claims tables (migrations 090-092). The first write, _mint_sibling_incident -> _insert_character (tests/test_orrery/test_claim_propagation_live.py:184), inserts an active 'character' entity plus a characters row before any chunk exists. The AFTER INSERT trigger trg_characters_need_state_init (migration 057) calls orrery_sync_character_need_states. Migration 100 (lines 96-103) anchors that function to COALESCE(MAX(chunk_metadata.world_time), global_variables.base_timestamp) and raises when both are NULL. That is always true on a template clone: new_story_setup.ensure_global_variables inserts the row with base_timestamp NULL, and there are no chunks. The test creates every row it later asserts on: two characters, three chunks, a threat_issued event, canonical and variant claims, and two holder_death backstory secrets drained over two ticks. It needs no corpus, only a story clock. #922 recorded the same class-a cause in docs/qa/test-fallout-repair/verification.md:216 and noted that the owner's save_05 is now empty too (0 chunks, 0 characters). No commit since b0645daf touches this file or the code path.
- Prerequisite: global_variables.base_timestamp is non-NULL (or at least one chunk_metadata row has world_time) before the first characters INSERT. Template seed event_types (threat_issued, claim_propagated) and world_events.world_time (migration 083) are present. No corpus rows are needed.
- Repair steps:
  1. Apply the file-level fixture repair in file_notes: a module-scoped disposable_slot_database with seed_protagonist, and account_connection building create_engine(sqlalchemy_url(dbname)) with the existing per-test begin()/rollback and schema-local 090-092 install.
  1. Verify with NEXUS_RUN_POSTGRES=1 poetry run pytest 'tests/test_orrery/test_claim_accounts_live.py::test_latent_sibling_secret_stays_private_until_its_own_gate_fires'.

#### `tests/test_orrery/test_claim_accounts_live.py::test_old_divergent_sibling_scopes_raise_during_hydration`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.92; runtime confirmation needed
- Cause: This test uses the same account_connection on hardwired slot 5 (private and empty in the baseline). Its first statement is _mint_sibling_incident -> _insert_character, which runs before _insert_chunk. The characters AFTER INSERT need-state trigger (057 -> orrery_sync_character_need_states, migration 100) finds neither a chunk world_time nor a base_timestamp and raises 'need-clock anchor unavailable'. The expected ValueError ('Sibling claims.*divergent scopes') comes later, from load_epistemics_hydration, so the recorded RaiseException is not the assertion under test. The rows are self-created: one incident, a canonical claim, and a variant claim set to private.
- Prerequisite: Story clock (global_variables.base_timestamp) before the characters INSERT, plus the migration 090-092 shape installed schema-locally by the fixture. No corpus.
- Repair steps:
  1. Apply the file-level account_connection repair (module-scoped disposable_slot_database with seed_protagonist; sqlalchemy_url engine; per-test rollback).
  1. Confirm that pytest.raises(ValueError, match='Sibling claims.*divergent scopes') now fires from load_epistemics_hydration, not from the trigger.

#### `tests/test_orrery/test_claim_accounts_live.py::test_scope_promotion_updates_every_sibling_and_hydrates_cleanly`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93; runtime confirmation needed
- Cause: The fixture uses hardwired slot 5. _mint_sibling_incident(scope='common') inserts the actor character before any chunk, so the characters need-state trigger raises because the empty clone has no chunk_metadata.world_time and no base_timestamp. promote_claim_scope and load_epistemics_hydration never run. The test otherwise seeds its own event, canonical claim, and variant claim.
- Prerequisite: global_variables.base_timestamp is set (the test's _insert_chunk then stamps deterministic world_time) and the schema-local claims shadow is installed by the fixture. No corpus.
- Repair steps:
  1. Apply the file-level account_connection repair (disposable clone plus seed_protagonist).
  1. Re-run the node. No per-test changes are expected.

#### `tests/test_orrery/test_claim_accounts_live.py::test_sibling_accounts_hydrate_predicates_and_propagate_independently`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: The fixture uses hardwired slot 5. The first write is _insert_character('account-canonical-knower'), before _insert_chunk, so the characters need-state trigger raises on the empty clone. The body later needs six self-created characters, two manual-producer relationships (_insert_relationship already wraps relationship_producer('manual')), a birth chunk, a threat_issued event, canonical and variant claims with a told awareness row, and a drain chunk 4h later for drain_claim_propagation_sync. It has no corpus dependency.
- Prerequisite: Story clock (base_timestamp) before the characters INSERT, the template pair_tags/event_types seed, and the pg_temp valence shadow installed by the fixture.
- Repair steps:
  1. Apply the file-level account_connection repair (disposable clone plus seed_protagonist; sqlalchemy_url engine).
  1. Re-run the node and confirm drained.minted_count == 2 and the per-claim ledgers.

#### `tests/test_orrery/test_claim_accounts_live.py::test_sync_variant_rejects_cross_incident_lineage_parent`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93; runtime confirmation needed
- Cause: The fixture uses hardwired slot 5. _mint_sibling_incident('lineage-source') inserts characters before any chunk, so the need-state trigger raises 'need-clock anchor unavailable' on the empty clone. The expected ValueErrors from mint_account_variant_sync ('belongs to world event', 'Lineage parent claim 999999') are never reached. The test creates two incidents itself.
- Prerequisite: global_variables.base_timestamp is set and the schema-local 090-092 claims shape is installed. No corpus.
- Repair steps:
  1. Apply the file-level account_connection repair (disposable clone plus seed_protagonist).
  1. Re-run the node and confirm both pytest.raises blocks match on the writer, not the trigger.

#### `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_common_claims_are_bounded_to_their_about_entities`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The live_connection fixture opens a rolled-back SQLAlchemy transaction on get_slot_db_url(slot=LIVE_SLOT=5) (the private, empty save_05) and installs install_claim_accounts_shadow_sync plus the valence shadow. The test's first write, _insert_character('audit-common-subject'), comes before _insert_chunk. The characters need-state trigger (migration 057 -> 100) therefore sees no chunk world_time and no base_timestamp and raises. The body later seeds four characters, one chunk, and two common-scope claims, deletes their awareness, and calls entity_context. Every asserted row is self-created. The same class-a cause is in docs/qa/test-fallout-repair/verification.md:221.
- Prerequisite: Story clock (global_variables.base_timestamp) before the characters INSERT and the template event_types seed. No protagonist is needed: entity_context and the hydration paths used here never call canonical_player_*.
- Repair steps:
  1. Apply the file-level live_connection repair (module-scoped disposable_slot_database with seed_protagonist or a clock-only seed; create_engine(sqlalchemy_url(dbname)); per-test begin()/rollback).
  1. Re-run the node.

#### `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_joins_distorted_delivery_to_real_depth`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The live_connection fixture uses hardwired slot 5. _chain(cur, 2) calls _insert_character before any chunk, so the characters need-state trigger raises on the empty clone. The body then needs a manual-producer relationship chain, a birth chunk, a canonical claim, a distortion variant (distortion_min_depth=1), a drain chunk 2h later with distortion enabled, and entity_context. All of these are self-created.
- Prerequisite: Story clock before the first characters INSERT, the claims shadow including 092 distortion_min_depth (the fixture installs it when missing), and the template seed. No corpus.
- Repair steps:
  1. Apply the file-level live_connection repair (disposable clone plus seed).
  1. Re-run and confirm drained.minted_count == 1 and knowledge[delivered]['depth'] == 1.

#### `tests/test_orrery/test_claim_consumption_live.py::test_entity_audit_renders_two_hop_provenance_and_ledger_depth`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The fixture uses hardwired slot 5. _chain(cur, 3) calls _insert_character first, so the need-state trigger raises (no chunk world_time and no base_timestamp in the empty clone). The body builds a self-contained three-character chain plus an 'about' character, a birth chunk, a claim, and a drain 12h later. It then asserts the exact entity_context row (told, dyad:associate, depth 2, acquired_at = birth + 2h). Time arithmetic is relative to the stamped world_time, so any fixed base_timestamp works.
- Prerequisite: global_variables.base_timestamp set before the first characters INSERT (world_time becomes base + time_delta) and the template seed. No corpus.
- Repair steps:
  1. Apply the file-level live_connection repair.
  1. Re-run the node. The expected summary text uses mechanical_claim_summary with the test's own participant labels, so it is corpus-independent.

#### `tests/test_orrery/test_claim_consumption_live.py::test_historical_anchor_excludes_future_claim_and_awareness`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The fixture uses hardwired slot 5. _insert_character('anchor-source') runs before any chunk, so the characters need-state trigger raises on the empty clone. The body later inserts three chunks (historical anchor, mint +2h, head +8h), asserts max(narrative_chunks.id) == head_anchor, which holds in a disposable clone, and compares hydrate_world_state, entity_context, and load_epistemics_hydration at the historical and head anchors. Everything is self-created.
- Prerequisite: Story clock (base_timestamp) before the characters INSERT. No other chunk may be inserted concurrently in the same database (true for a per-module clone with per-test rollback).
- Repair steps:
  1. Apply the file-level live_connection repair.
  1. Keep the clone module-scoped with per-test rollback so the max(id) == head_anchor assertion stays valid.

#### `tests/test_orrery/test_claim_consumption_live.py::test_hydration_excludes_irrelevant_history_and_empty_universe_issues_no_sql`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The fixture uses hardwired slot 5. _insert_character('hydrate-relevant-source') comes before _insert_chunk, so the need-state trigger raises on the empty private clone. The body then mints 33 claims on self-created characters, deactivates two of them, and checks hydrate_world_state and an SQL-free empty-universe load_epistemics_hydration. There are no corpus reads, and the hydration path needs no protagonist: weather_settings is None, so the canonical player lookup in _load_local_weather is skipped.
- Prerequisite: Story clock before the characters INSERT and the template seed. No corpus.
- Repair steps:
  1. Apply the file-level live_connection repair.
  1. Re-run the node.

#### `tests/test_orrery/test_claim_consumption_live.py::test_live_predicates_cover_participant_told_common_false_and_faction`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The fixture uses hardwired slot 5. The first write is _insert_character('consume-source'), so the need-state trigger raises (no chunk world_time and no base_timestamp). The body later needs six characters, one faction (_insert_faction creates its own with coalesce(max(id),0)+1), a manual relationship, an authority_over pair tag (template pair_tags seed, asserted rowcount == 1), two claims, and a drain 8h later with the authority_over channel. It then asserts told-tier stamps at birth + 1h for listener and faction and calls hydrate_world_state with contagion settings. All of this is self-created.
- Prerequisite: Story clock before the characters INSERT and the pair_tags seed containing a non-deprecated authority_over. No corpus.
- Repair steps:
  1. Apply the file-level live_connection repair.
  1. Re-run and confirm drained.minted_count >= 2 and the told stamps.

#### `tests/test_orrery/test_claim_consumption_live.py::test_recent_claim_scope_survives_inactive_endpoints`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The fixture uses hardwired slot 5. _insert_character('scope-inactive-source') runs before _insert_chunk, so the characters need-state trigger raises on the empty clone. The body mints one bounded claim on self-created characters, deactivates both endpoints, and checks that hydrate_world_state keeps the recent event's scope and that knows_recent_event denies a non-knower. No corpus is involved.
- Prerequisite: global_variables.base_timestamp before the characters INSERT and the template event_types seed.
- Repair steps:
  1. Apply the file-level live_connection repair.
  1. Re-run the node.

#### `tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The fixture uses hardwired slot 5. _insert_character('gate-source') runs before any chunk, so the need-state trigger raises. The body builds a three-character trusting chain, a claim, and a drain chunk 8h later, then marks the listener relevant with a surveillance_performed event (template event_types seed). It compares resolve_dry_run and explain_dry_run for a synthetic Template before and after drain_claim_propagation_sync. Both dry runs hydrate with weather disabled and ambient None, so no protagonist is required. A seed_protagonist player would be an extra active character, but the assertion inspects only the (listener, about) binding.
- Prerequisite: Story clock before the characters INSERT and the event_types seed containing threat_issued and surveillance_performed. No corpus.
- Repair steps:
  1. Apply the file-level live_connection repair.
  1. Re-run and confirm the before and after production and explain parity.

#### `tests/test_orrery/test_communication_graph_live.py::test_assembly_is_deterministic_and_unknown_configured_channel_is_loud`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is a setup ERROR in the communication_db fixture. The fixture opens a SQLAlchemy transaction on get_slot_db_url(slot=LIVE_SLOT) with a module-local LIVE_SLOT=5 (private and empty in the baseline), then inserts 19 characters. The first characters INSERT fires the need-state trigger (migration 057 -> 100), which raises 'need-clock anchor unavailable'. A second owner-content blocker is masked behind it: after the inserts, the fixture picks an existing active faction with 'SELECT f.entity_id FROM factions ... LIMIT 1' and .scalar_one(). On a clone with no factions this raises NoResultFound even once a clock exists. The test itself compares two assemblies and one raw-cursor assembly, and expects a ValueError for an unregistered channel tag, which checks the template pair_tags seed against the nexus.toml config.
- Prerequisite: Story clock (base_timestamp) before the characters INSERT; one active faction entity and factions row without operational_secrecy/operational_mode tags (the fixture should create it); template pair_tags seed including obligation, authority_over, handles, and every status:* tag; nexus.toml [orrery.contagion].
- Repair steps:
  1. Apply the file-level communication_db repair (disposable clone plus seed_protagonist, sqlalchemy_url engine, and a fixture-created faction replacing the corpus lookup).
  1. Re-run the node.

#### `tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is a setup ERROR in the shared communication_db fixture: the first characters INSERT into the empty private save_05 raises through the need-state trigger. The masked second blocker is the corpus faction lookup (scalar_one over existing factions), which fails on an empty clone. The test asserts channel directions for self-created obligation, authority_over, and handles pair tags, and status:junior/status:outcast toward that faction. It needs the faction to exist, not any particular corpus faction.
- Prerequisite: Story clock before the characters INSERT; a fixture-created active faction; template pair_tags for obligation, authority_over, handles, status:junior, and status:outcast; nexus.toml channel config (status:* min_level junior).
- Repair steps:
  1. Apply the file-level communication_db repair including the fixture-created faction.
  1. Re-run the node.

#### `tests/test_orrery/test_communication_graph_live.py::test_culture_profiles_multiply_and_record_provenance`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is a setup ERROR in communication_db: the characters INSERT into the empty slot 5 raises the need-clock anchor. The masked corpus-faction lookup would fail next. The test adds cellular_clandestine and then covert culture tags (entity_tags on the faction entity) and expects multipliers 1.0 -> 4.0 -> 8.0. The baseline requires that the chosen faction has no culture tags, which a fixture-created faction guarantees. On the owner corpus it depended on which faction the LIMIT 1 happened to pick. entity_tags inserts on a faction entity do fire the need-applicability trigger, but orrery_sync_character_need_states returns 0 for non-character entities before the anchor check.
- Prerequisite: Story clock; a fixture-created faction with no culture or operational tags; template tags seed with non-deprecated cellular_clandestine and covert; nexus.toml culture_profiles.
- Repair steps:
  1. Apply the file-level communication_db repair with a fixture-created, untagged faction.
  1. Re-run the node.

#### `tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is a setup ERROR in communication_db (need-clock raise on the first characters INSERT into the empty slot 5), and the masked corpus-faction scalar_one lookup sits behind it. The body already creates its own member faction. It needs the fixture's parent faction to exist and receive a status:senior pair tag from the member faction.
- Prerequisite: Story clock; a fixture-created parent faction; template pair_tags status:senior.
- Repair steps:
  1. Apply the file-level communication_db repair.
  1. Re-run the node.

#### `tests/test_orrery/test_communication_graph_live.py::test_lone_row_is_sparse_and_handler_override_beats_neutral`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is a setup ERROR in communication_db: the characters INSERT on the empty private save_05 raises the need-clock anchor. The masked corpus-faction lookup follows. The body uses only fixture-seeded dyads written into the pg_temp character_relationships shadow (associate trusting, handler neutral, associate neutral, associate hostile, the reciprocal captor pair, and an inactive teller) and asserts latencies from nexus.toml. It has no corpus dependency beyond the fixture.
- Prerequisite: Story clock; fixture-created faction (needed only so the fixture completes); nexus.toml dyad_tiers and dyad_overrides.
- Repair steps:
  1. Apply the file-level communication_db repair.
  1. Re-run the node.

#### `tests/test_orrery/test_communication_graph_live.py::test_production_explain_and_entity_audit_share_one_edge_list`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is a setup ERROR in communication_db: the need-clock raise on the first characters INSERT into the empty slot 5, with the masked corpus-faction lookup behind it. The body calls resolve_dry_run and explain_dry_run with anchor_chunk_id=None, world_time_override, and epistemics disabled, then entity_context. None of these need a protagonist or chunks: weather is disabled, and ambient settings are None.
- Prerequisite: Story clock (only for the fixture's characters INSERT) and a fixture-created faction.
- Repair steps:
  1. Apply the file-level communication_db repair.
  1. Re-run the node.

#### `tests/test_orrery/test_communication_graph_live.py::test_unknown_dyad_override_key_is_loud`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is a setup ERROR in communication_db (need-clock raise on the characters INSERT into the empty slot 5, then the masked corpus-faction lookup). The body only checks that a misspelled dyad_overrides key ('handeler') raises. The valid key set includes relationship types present in live data, and the fixture's own captor and handler rows keep the shipped defaults valid on an empty clone.
- Prerequisite: Story clock; fixture-created faction; the fixture's captor and handler relationship rows; nexus.toml dyad_overrides.
- Repair steps:
  1. Apply the file-level communication_db repair.
  1. Re-run the node.

#### `tests/test_orrery/test_migrate.py::test_canonical_grieving_migration_executes_against_slot_db`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The test opens psycopg2.connect(get_slot_db_url(dbname='save_05')), a slot hardcoded by name that was the private, empty save_05 in the baseline. For each legacy grief tag ('bereaved', 'grieving_recent_partner'), it commits an active 'character' entity and then an entity_tags row. The entity_tags insert fires trg_entity_tags_need_state_applicability (migration 057), which calls orrery_sync_character_need_states for that active character entity (no characters row is needed). With no chunk_metadata and a NULL base_timestamp, migration 100's anchor check raises. The template clearly carries the legacy tags, because the test passed its 'Missing legacy grief tags' skip guard. Separately, this test is an isolation hazard: it commits entities to save_05 and runs migration 046's run(conn), which commits an upsert of the 'grieving' tag, against an owner slot. Only the entities are cleaned up afterward. No commit since b0645daf touches it.
- Prerequisite: A disposable database carrying the template tags seed (legacy grief tags plus 'grieving'); global_variables.base_timestamp set before the entity_tags INSERT for an active character entity.
- Repair steps:
  1. Replace the save_05 connection with 'with disposable_slot_database("qa964_grieving") as dbname: seed_protagonist(dbname)' and connect via tests.pg_fixtures.connect(dbname). Drop the save_05 skip-on-unavailable branch (an unreachable server must fail) and the manual entity cleanup (the clone is dropped).
  1. Run migration.run(conn) against the clone, and keep the assertions unchanged.
  1. Move the sibling *_executes_against_slot_db tests in this file (character_tag_vocab, completed_tag_vocab, entity_tag_expiry_substrate, faction_tag_vocab, state_clearance_event_type, kind_qualified_contact) to the same fixture. They were not red, but they also write to save_05 by name.

#### `tests/test_orrery/test_orbit_distance_live.py::test_hydrate_orbit_distance_from_active_relationship_graph`

- Baseline outcome: failure; signature: `sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The test opens a SQLAlchemy transaction on get_slot_db_url(slot=LIVE_SLOT) with a module-local LIVE_SLOT=5 (private and empty in the baseline). It inserts six entities (no trigger), then the characters row for active entity 'a'. That fires the need-state trigger, which raises 'need-clock anchor unavailable' because the slot has no chunk_metadata and no base_timestamp. A second failure is masked behind it. _insert_relationship writes to public.character_relationships (no pg_temp shadow in this file) without setting nexus.write_producer. The fail-closed trigger fn_version_relationship_row from migration 115 will raise 'Missing or invalid nexus.write_producer' once the clock exists. #922 added producer attribution to the other class-a relationship fixtures but not this one. The graph assertions filter to fixture entities, so no corpus rows are needed.
- Prerequisite: Story clock before the first active characters INSERT; relationship writes stamped with nexus.write_producer='manual'. hydrate_world_state is called with anchor_chunk_id=None and world_time_override, so no chunks or protagonist are needed.
- Repair steps:
  1. Wrap the test in 'with disposable_slot_database("qa964_orbit") as dbname: seed_protagonist(dbname)' and build the engine with create_engine(sqlalchemy_url(dbname), future=True), keeping the rolled-back transaction. Drop LIVE_SLOT and get_slot_db_url.
  1. Call relationship_producer_sqlalchemy(session, 'manual') (nexus.agents.orrery.relationship_provenance) before the four character_relationships inserts.
  1. Re-run the node. The seeded player is an extra active entity outside the filtered fixture set and does not affect the assertions.

#### `tests/test_orrery/test_relationship_provenance_pg.py::test_analyst_sqlalchemy_helper_stamps_insert_and_replacement`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: The module imports the module-scoped drift_database fixture from test_drift_live. That fixture clones the owner-named save_03 with include_data=True. In the baseline's private cluster, save_03 was an empty template clone, so the 'corpus clone' has no chunk_metadata and a NULL base_timestamp. This test's first action commits two _insert_character rows (test_drift_live.py:92) before any chunk exists, so the characters need-state trigger raises the migration-100 anchor error. The other tests in the same module pass on the same empty clone because _seed_tick inserts two chunks before any character. refresh_world_time_from_chunk() (migration 023) stamps those chunks with COALESCE(base_timestamp, now()), so MAX(world_time) exists by the time characters are inserted. Sibling tests always roll back, so this test sees an empty chunk table in every ordering. The test body needs nothing from the corpus: it only checks relationship_producer_sqlalchemy stamping and the fail-closed rejection of unstamped writes.
- Prerequisite: global_variables.base_timestamp (or one chunk with world_time) before the characters INSERT. Migration 115's relationship_versions.producer and trigger (present in the template).
- Repair steps:
  1. Repair the shared drift_database in tests/test_orrery/test_drift_live.py: clone NEXUS_template (default source_db, include_data=False) instead of save_03, then call seed_protagonist(dbname). Do not seed base_timestamp on top of a corpus clone, because refresh_world_time_from_chunk recomputes every chunk's world_time from base_timestamp on the next chunk insert.
  1. Because drift_database is shared, also seed one place row for test_drift_live::test_colocated_characters_without_events_produce_no_versions (another batch; it fails on 'SELECT id FROM places ORDER BY id LIMIT 1' returning None).
  1. Re-run the node and confirm the versions list and the fail-closed InternalError matches.

#### `tests/test_trait_compiler_integration.py::test_dependents_apply_and_dry_run_audit_on_save_05`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: The test opens a bare psycopg2.connect(dbname='save_05'). libpq honors PGPORT, so in the baseline this reached the private, empty save_05. Its first write is _insert_protagonist (INSERT INTO characters). The AFTER INSERT trigger trg_characters_need_state_init (migration 057) calls orrery_sync_character_need_states (redefined in migration 100). That function computes COALESCE(MAX(chunk_metadata.world_time), global_variables.base_timestamp) and raises 'need-clock anchor unavailable' when both are NULL. On a template clone both are NULL: there are no chunks and base_timestamp is unset. The owner's save_05 has a played story, so the anchor existed there. The test body only creates character stubs, pair tags and a relationship, so it needs no zone. No commit since b0645daf touches the test, migration 100 or the trait compiler.
- Prerequisite: global_variables.base_timestamp set before any characters INSERT, or one chunk_metadata row with world_time. Template seed vocabulary: pair_tags 'protects' and the single-entity tags for resources:wealthy and fame:known. Nothing else is needed: no zone and no user_character.
- Repair steps:
  1. Use the module fixture described in file_notes: disposable_slot_database('qa640_trait_compiler') plus seed_protagonist(dbname), which sets base_timestamp and user_character.
  1. Connect through tests.pg_fixtures.connect(dbname) instead of psycopg2.connect(dbname=TEST_DBNAME), and delete the pytest.skip on connection error.
  1. Keep the conn.rollback() isolation so the module can share one clone.

#### `tests/test_trait_compiler_integration.py::test_dunlow_shared_faction_is_permutation_invariant_on_save_05`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Same failure as the other trait-compiler nodes. The bare psycopg2.connect(dbname='save_05') reached the empty private save_05. Inside the first permutation savepoint, _insert_protagonist runs INSERT INTO characters, which fires trg_characters_need_state_init and then orrery_sync_character_need_states. That function raises 'need-clock anchor unavailable' because chunk_metadata has no world_time and global_variables.base_timestamp is NULL. The test's 'faction must start absent' precondition holds on an empty slot. Only the missing clock breaks it. The body creates a faction stub and a character, and adds status, hostile_to and obligation pair tags. None of these needs a zone or player identity.
- Prerequisite: global_variables.base_timestamp set, plus template seed pair_tags 'status:senior', 'hostile_to' and 'obligation'. The Dunlow faction name must be absent (true on a fresh clone).
- Repair steps:
  1. Switch to the shared module clone fixture with seed_protagonist (see file_notes), connecting through tests.pg_fixtures.connect.
  1. Remove the pytest.skip environment guard.

#### `tests/test_trait_compiler_integration.py::test_forbidden_relationship_traits_have_dry_run_apply_parity_on_save_05`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.94
- Cause: This test connects directly to save_05 and calls _insert_protagonist, whose characters INSERT fires the need-state init trigger. orrery_sync_character_need_states raises 'need-clock anchor unavailable' because the empty private save_05 has no chunk world_time and no base_timestamp. After that insert the test expects zero entity or relationship writes, because every trait is constrained 'forbidden'. The protagonist insert is therefore its only clock-dependent step.
- Prerequisite: global_variables.base_timestamp set before the protagonist INSERT. No other rows are needed.
- Repair steps:
  1. Use the shared disposable clone plus seed_protagonist module fixture and tests.pg_fixtures.connect.
  1. Remove the pytest.skip guard.

#### `tests/test_trait_compiler_integration.py::test_full_trait_selection_compiles_on_save_05`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The recorded failure is the need-clock anchor raise from the protagonist characters INSERT on the empty private save_05. A second owner-slot assumption sits behind it and will surface once the clock is seeded. This test's domain trait creates a place stub through _insert_place_stub, which calls story_active_zone(cur) (nexus/agents/orrery/geo.py). story_active_zone resolves global_variables.user_character through canonical_player_character_id, then requires that character's current_location to be a place with a non-null zone. Otherwise it raises 'Cannot locate new entity: protagonist has no current zoned place'. The owner's save_05 has a located player, but seed_protagonist alone gives the player no current_location.
- Prerequisite: Two things are required. First, global_variables.base_timestamp and user_character (via seed_protagonist). Second, the fixture player must have a current_location that points to a places row whose zone references a zones row, which in turn needs a layers row. Template seed pair_tags 'claims', 'sponsors', 'mentors' and 'obligation' must also be present.
- Repair steps:
  1. Use the shared module clone with seed_protagonist.
  1. Add a pg_fixtures helper, e.g. seed_player_location(dbname), that inserts a layer, a zone, a place entity and a place with a zone, then sets characters.current_location for global_variables.user_character. tests/test_wizard_opening_presence_pg.py::_seed_post_transition_world is a precedent.
  1. Connect through tests.pg_fixtures.connect and drop the pytest.skip guard.

#### `tests/test_trait_compiler_integration.py::test_shared_character_relationship_is_permutation_invariant_on_save_05`

- Baseline outcome: failure; signature: `psycopg2.errors.RaiseException: need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: The first INSERT INTO characters (_insert_protagonist) inside the permutation savepoint fires trg_characters_need_state_init. orrery_sync_character_need_states then raises because the empty private save_05 has neither chunk world_time nor base_timestamp. The test later creates the patron character stub (another characters INSERT) and a patron relationship. Neither needs a zone or player identity.
- Prerequisite: global_variables.base_timestamp set, and the character 'Magistrate Hale [issue 602 rollback test]' absent (true on a fresh clone).
- Repair steps:
  1. Use the shared disposable clone plus seed_protagonist module fixture through tests.pg_fixtures.connect.
  1. Remove the pytest.skip guard.

### `owner_slot_content_assumption` (175 nodes)

#### `tests/test_api/test_attempt_manifest_pg.py::test_child_job_enqueue_correlation_and_transaction_reset`

- Baseline outcome: failure; signature: `TypeError: '<=' not supported between instances of 'NoneType' and 'int'`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: The test clones save_04 with data, which is empty in the private cluster, then runs 'SELECT max(id) FROM narrative_chunks'. That returns NULL, so parent=None. The test inserts its own boundary chunk and calls enqueue_scene_experience_job_sync(scene_end_chunk_id=None). Its first line, 'if not cfg.enabled or scene_end_chunk_id <= 0', raises TypeError: '<=' not supported between 'NoneType' and 'int' (nexus/agents/orrery/experiences.py:1025). Several later steps also depend on save_04 content. 'assert count > 0' needs unrendered valid character_experiences seeds anchored at or before the parent. canonical_player_entity_id needs user_character, because include_player_character is false in nexus.toml. The unpacking 'first, second, valence = cur.fetchone()' needs at least one character_relationships row. The later rung-crossing UPDATE must produce a relationship_milestone job.
- Prerequisite: Several rows are required. First, base_timestamp plus user_character (seed_protagonist). Second, one accepted parent chunk with chunk_metadata world_layer 'primary' and world_time. Third, at least one valid, unrendered character_experiences seed for a non-player NPC with a dossier (summary and background), anchored at or before the parent. Fourth, one character_relationships row between two characters, written under nexus.write_producer 'manual' because the provenance trigger is fail-closed.
- Repair steps:
  1. Use disposable_slot_database('qa640_764_jobs') without source_db/include_data, route_slot, and seed_protagonist.
  1. Promote the chunk and seed halves of tests/test_orrery/test_character_experiences_pg.py::_enqueue_render_job into a shared helper (e.g. tests/pg_fixtures.seed_experience_candidates). The helper inserts _insert_chunk plus NPC characters plus 'slept' world_events and world_event_entities, then calls seed_character_experiences_sync. Use its chunk as parent.
  1. Seed one NPC-to-NPC character_relationships row inside SET LOCAL nexus.write_producer='manual'.
  1. Drop the max(id) lookup in favor of the helper's returned chunk id.

#### `tests/test_api/test_attempt_manifest_pg.py::test_inspect_turn_pre_session_chunk_and_duplicate_sessions`

- Baseline outcome: failure; signature: `assert None == (49,)`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: The test clones save_04 with data and asserts 'SELECT id FROM narrative_chunks WHERE id=49' == (49,). Chunk 49 is a specific legacy chunk in the owner's save_04, accepted before session binding. The private save_04 is empty, so fetchone() returns None and the assertion 'None == (49,)' fails. The rest of the test only needs some chunk id with no bound session, then two duplicate accepted sessions for it. inspect_turn does not otherwise read chunk content.
- Prerequisite: One narrative_chunks row with chunk_metadata and no narrative_generation_sessions row bound to it. The id is arbitrary.
- Repair steps:
  1. Use a default template clone (no include_data) plus route_slot.
  1. Insert one chunk through the shared chunk helper (promoted _insert_chunk) and use its returned id everywhere the test hardcodes 49, including the expected CLI output string.
  1. Drop the 'UPDATE narrative_generation_sessions SET chunk_id=NULL' step, since a fresh chunk has no session.

#### `tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation[async]`

- Baseline outcome: failure; signature: `RuntimeError: qa640_764_turn_b5d575609e1b has no accepted narrative tail`
- Route: `seed_disposable_clone` to #816; confidence 0.9; runtime confirmation needed
- Cause: The test clones the owner's populated native QA slot with disposable_slot_database(source_db='save_04', include_data=True). In the private cluster save_04 is an empty template clone, so the clone has no narrative_chunks. The test then calls scripts/stamp_lore_pass_baseline.refresh_tail_fingerprint(dbname=...). That function runs 'SELECT id FROM narrative_chunks ORDER BY id DESC LIMIT 1' and raises 'qa640_764_turn_... has no accepted narrative tail'. The rest of the test drives a real TEST-provider 'nexus continue --choice 1' turn and an async commit_incubator_to_database. It then asserts skald_writer and gaia manifests, non-empty orrery_prompt_exposures for the accepted chunk, and session-correlated child jobs. So it needs a genuinely playable story, not just a few rows. No change since b0645daf.
- Prerequisite: A playable story in a disposable clone routed as slot 4. That means: global_variables with base_timestamp, user_character, and model/gaia_model TEST; a player with a zoned current_location; at least one accepted narrative chunk with chunk_metadata world_time and a lore_pass_baselines row for the tail; incubator empty; and enough Orrery state (e.g. a present character with due need debt, or an off-screen actor) for acceptance to persist at least one orrery_prompt_exposures row.
- Repair steps:
  1. Build a production-path 'playable_test_story' factory (#816's first step). In a default template clone routed with route_slot, run 'nexus continue --slot 4 --model TEST', then '--accept-fate' until the slot leaves wizard mode, as tests/test_connection_lifecycle.py does around lines 349-363. The bootstrap acceptance stamps the tail baseline under the TEST fingerprint.
  1. Replace source_db='save_04', include_data=True with that factory. refresh_tail_fingerprint and the incubator fingerprint patch then become unnecessary; keep them only if harmless.
  1. Seed a due need or an off-screen actor so the exposure assertion is non-vacuous. Verify by running.

#### `tests/test_api/test_attempt_manifest_pg.py::test_manifest_real_test_turn_and_child_job_correlation[sync]`

- Baseline outcome: failure; signature: `RuntimeError: qa640_764_turn_6f03b7607123 has no accepted narrative tail`
- Route: `seed_disposable_clone` to #816; confidence 0.9; runtime confirmation needed
- Cause: This is the same body as the async variant. It clones save_04 with include_data=True, which is empty in the private cluster. refresh_tail_fingerprint then raises 'has no accepted narrative tail' because narrative_chunks is empty. The sync branch additionally POSTs /api/narrative/approve through the gateway lane (NEXUS_GATEWAY_PORT=0, an ephemeral port, so there is no port hazard). It asserts terminal_outcome 'accepted', a correspondence_compaction job correlated to the session (floor_turns forced to 1), and inspect-turn --chunk parity. All of that needs a real accepted tail.
- Prerequisite: Same playable story as the async variant: base_timestamp, user_character with a zoned location, a tail chunk with world_time and a Pass-2 baseline, model TEST, and Orrery state that yields prompt exposures. It also needs enough correspondence history for floor_turns=1 to enqueue a correspondence_compaction job at sync acceptance.
- Repair steps:
  1. Use the shared playable_test_story factory described for the async variant (wizard bootstrap through the TEST provider in a default clone).
  1. Drop the save_04 corpus clone.
  1. Confirm at runtime that compaction enqueues with a one-chunk history plus one new turn. If not, run one extra accepted turn in the factory.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling`

- Baseline outcome: failure; signature: `assert 400 == 200`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.93
- Cause: The two over-cap requests correctly return 400. The final stride-sampling request (count 3, stride 3) against the empty private save_05 samples no chunks, so post_coverage returns 400 'No anchors to analyze'. The bare 'assert response.status_code == 200' produces 'assert 400 == 200'. The expected anchors are derived from real save_05 chunk ids.
- Prerequisite: At least one playable chunk; at least seven are needed for the stride-3 sample to cover three distinct anchors. The chunks need world_time, and the clock and player must be valid so each anchor's explain_dry_run succeeds.
- Repair steps:
  1. Use orrery_audit_world with at least seven playable chunks.
  1. The expected-list computation already reads the routed slot, so no other change is needed.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle`

- Baseline outcome: failure; signature: `AssertionError: {"detail":"No anchors to analyze: the slot has no narrative chunks"}`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.93
- Cause: The test POSTs /api/dev/orrery/coverage for slot 5 (count 1). post_coverage calls sample_anchor_ids, which returns [] on the empty private save_05, so the endpoint raises HTTPException(400, 'No anchors to analyze: the slot has no narrative chunks'). The test's 'status_code == 200, response.text' assertion prints that detail. By design the test also requires save_05 to show the NULL-world-time bestowal pathology ('oracle_nulls > 0'), which is a fact about the owner corpus.
- Prerequisite: At least one playable narrative chunk (not a retrograde prologue) with chunk_metadata world_time, plus at least one active entity_tags row (cleared_at NULL) whose applied_at_world_time is NULL. That NULL row models the legacy pathology.
- Repair steps:
  1. Run against the module's seeded orrery_audit_world clone routed as slot 5 (see file_notes).
  1. In that fixture, insert one entity_tags row with applied_at_world_time NULL on a seeded NPC. No trigger stamps that column.
  1. Replace the hard 'slot': 5 and get_slot_db_url(slot=5) with LIVE_SLOT. A seeded fixture is more honest than a corpus flag: the oracle comparison is corpus-independent, and gating would only add a gate skip.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]`

- Baseline outcome: failure; signature: `AssertionError: {"detail":"No anchors to analyze: the slot has no narrative chunks"}`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.9; runtime confirmation needed
- Cause: The test is parametrized over AUDIT_SLOTS=(5,), the owner's Orrery-native save_05. The coverage request (count 3, stride 5) samples zero playable chunks on the empty private save_05, so post_coverage returns 400 'No anchors to analyze'. The test asserts 200 with response.text as the message.
- Prerequisite: At least one playable narrative chunk with world_time in the audited slot. For meaningful stats, a seeded Orrery world with actors so that at least one template evaluates. The clock and player must be valid so explain_dry_run succeeds per anchor.
- Repair steps:
  1. Point AUDIT_SLOTS at the seeded orrery_audit_world fixture routed as slot 5 (see file_notes).
  1. Optionally add a corpus-flagged parametrization for the owner's save_05. The seeded fixture should be the gate default.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_hover_payload`

- Baseline outcome: failure; signature: `assert []`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.92
- Cause: resolve for slot 5 returns 200 with actors == [] on the empty private save_05, so 'assert groups' fails, recorded as 'assert []'. The test then indexes groups[0] and groups[1], so it implicitly needs at least two off-screen actors. With exactly one it would fail with an IndexError instead.
- Prerequisite: At least two off-screen NPC actors with names and entity rows at the head anchor. Useful extras for coverage: tags, relationships, need rows (created by trigger), knowledge claims, and a place.
- Repair steps:
  1. Use orrery_audit_world with at least two off-screen NPCs.
  1. Optionally assert len(groups) >= 2 explicitly so the implicit prerequisite is visible.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_recent_events_respect_anchor`

- Baseline outcome: failure; signature: `assert 422 == 200`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.92
- Cause: resolve for slot 5 returns 200 with anchor_chunk_id None and actors [] on the empty private save_05, so entity_ids = []. The next POST /api/dev/orrery/context/entities sends entity_ids [], which violates OrreryEntityContextRequest.entity_ids Field(min_length=1). FastAPI returns 422, recorded as 'assert 422 == 200'. For a non-vacuous event check the test also implicitly wants world_events for those actors at or before the head.
- Prerequisite: At least one off-screen NPC actor at a non-null head anchor. Ideally the seed also includes at least one world_events row for that actor with tick_chunk_id at or before the head, so the anchor filter is exercised.
- Repair steps:
  1. Use orrery_audit_world and seed at least one world_events plus world_event_entities row for an off-screen NPC at an earlier chunk.
  1. Optionally add an explicit 'assert entity_ids' so the prerequisite fails with a clear message.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable`

- Baseline outcome: failure; signature: `AssertionError: save_05 is expected to bind off-screen actors`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.92; runtime confirmation needed
- Cause: POST /api/dev/orrery/resolve for slot 5 returns 200 on the empty private save_05. _default_anchor_chunk_id returns None, and compose_actor_bindings adds no actors when anchor_chunk_id is None, because actors come only from window-chunk rosters and world_events. So payload['actors'] == [] and the non-vacuity assertion 'save_05 is expected to bind off-screen actors' fails. The test assumes save_05's played Orrery state.
- Prerequisite: A head playable chunk with world_time. At least one active NPC character entity must be referenced in the binding window (chunk_character_references with a non-'present' reference, or world_events within window_chunks) and must not be present at the anchor. Clock and player identity must also be set.
- Repair steps:
  1. Use the seeded orrery_audit_world fixture (see file_notes). It seeds at least three NPCs referenced off-screen in window chunks, plus a present player at the head chunk.
  1. Keep the assertion as the non-vacuity guard.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts`

- Baseline outcome: failure; signature: `AssertionError: no audited slot produces resolutions — winner parity is vacuous; repoint AUDIT_SLOTS at a slot with Orrery activity`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.93; runtime confirmation needed
- Cause: This is the module's non-vacuity guard. The module-scoped production_proposals fixture runs resolve_dry_run on save_05 with anchor = max playable chunk id, which is None on the empty private slot. That yields zero resolutions, and the guard fails with 'repoint AUDIT_SLOTS at a slot with Orrery activity'. This is exactly the failure the guard was written to produce when the audited slot lacks Orrery activity. It also shows that test_resolve_parity_with_production_resolver[5], test_joint_beats_parity_with_production[5] and test_coverage_head_anchor_reconciles_with_production passed vacuously in the baseline.
- Prerequisite: At the head anchor, the production resolver must produce at least one resolution and at least one scene pressure. For example: an off-screen NPC with high accrued sleep debt (long world-time gap since last evaluation) so the 'sleep' template resolves, and a player or NPC present at the head chunk with due need debt so sleep_need_pressure appears. tests/test_orrery/test_need_absence_pg.py is a working precedent.
- Repair steps:
  1. Point AUDIT_SLOTS at the seeded orrery_audit_world fixture (see file_notes). Seed chunks spanning a multi-day world-time gap so off-screen and present need debt accrue, following test_need_absence_pg's _chunk and seed_protagonist pattern.
  1. A fixture is more honest than a corpus flag here. The guard exists to force a slot with activity, and a skip would re-hide the three parity tests that currently pass vacuously.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures`

- Baseline outcome: failure; signature: `AssertionError: sleep debt 500 flipped no off-screen actor's sleep template on any audited slot — the stack-side what-if assertion is vacuous; repoint AUDIT_SLOTS`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.88; runtime confirmation needed
- Cause: On the empty private save_05 the baseline resolve has no actors and _present_actor_ids_at_anchor(anchor=None) returns none. overrides['needs'] is therefore empty, the loop hits 'continue', and flipped_stacks stays 0. The vacuity assertion 'sleep debt 500 flipped no off-screen actor's sleep template on any audited slot' fires. The test assumes save_05 has off-screen actors whose sleep template can flip and on-screen characters for the pressure diff.
- Prerequisite: At least one off-screen NPC whose baseline actor-stack winner is not 'sleep' but whose sleep template fires at debt 500 (a sleep need row exists via the need-applicability trigger, and the NPC is not constrained). Also at least one actor present at the head anchor (chunk_character_references 'present'), so that sleep_need_pressure is added in the what-if.
- Repair steps:
  1. Use orrery_audit_world. Keep one off-screen NPC with low baseline sleep debt, and mark the player or an NPC 'present' at the head chunk.
  1. Confirm at runtime that the sleep template's other gates (time of day, location) pass for the seeded NPC.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner`

- Baseline outcome: failure; signature: `AssertionError: no audited slot yields an actor-only winner gated on NOT(has_inbound_pair_tag(hunting)) — the what-if kill test is vacuous; repoint AUDIT_SLOTS at a sl...`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.88; runtime confirmation needed
- Cause: The test looks for an off-screen actor-only winner whose top-level AND gate passed through NOT(has_inbound_pair_tag('hunting')), such as 'hide' or 'uncover_past' in nexus/agents/orrery/templates.py, plus a second off-screen actor to act as hunter. On the empty private save_05 the resolve payload has no actors, so there are no candidates and the vacuity assertion fires. This is a save_05 corpus assumption.
- Prerequisite: At least two off-screen NPC actors at the head anchor. One must win a NOT-hunting-gated actor-only template, e.g. uncover_past: carries the 'seeking_identity' tag, head chunk world_time in evening or night, and no higher-priority winner. Alternatively hide: is_hidden, has_minimal_context, not constrained.
- Repair steps:
  1. In orrery_audit_world, give one off-screen NPC the 'seeking_identity' tag and set the head chunk world_time to night. Keep its need debt low so need templates do not outrank it.
  1. Confirm at runtime which template wins. Adjust the seed (for example, use hide's is_hidden inputs) if uncover_past is shadowed.

#### `tests/test_api/test_orrery_dev_endpoints.py::test_what_if_validation_rejections`

- Baseline outcome: failure; signature: `IndexError: list index out of range`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.92
- Cause: _resolve(client, LIVE_SLOT) returns 200 with actors == [] on the empty private save_05, because the anchor is None and no bindings exist. The first line after it, payload['actors'][0]['actor_entity_id'], raises IndexError: list index out of range. Later the test also requires an audited actor carrying a durable tag, via its 'carried is not None' non-vacuity assert.
- Prerequisite: At least one off-screen NPC actor at the head anchor that carries at least one durable (non-ephemeral) entity_tags row. Tag, pair-tag and event-type seed vocabulary comes from the template.
- Repair steps:
  1. Use orrery_audit_world. The NPC seeded with 'seeking_identity' (or any durable tag) satisfies both prerequisites.
  1. Optionally replace the bare [0] index with an explicit non-vacuity assert message.

#### `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_adjacent`

- Baseline outcome: failure; signature: `IndexError: list index out of range`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.95
- Cause: The test reads hardwired READ_SLOT=2, documented as 'save_02: mature corpus, read-only'. In the isolated cluster save_02 is an empty template clone, so /api/narrative/outline returns [] and outline[len(outline)//2] raises IndexError. The endpoint handles the empty slot correctly. The same tests pass against the owner's populated save_02 (docs/qa/test-fallout-repair).
- Prerequisite: At least 3 playable narrative_chunks with chunk_metadata rows in story order, so the middle chunk has both a previous and a next.
- Repair steps:
  1. Point READ_SLOT at the shared module-scoped seeded reader slot (see file_notes), which inserts at least 3 chunks with metadata (season 1, episode 1, scenes 1-3, slug, time_delta).

#### `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_chunks_by_season_episode`

- Baseline outcome: failure; signature: `IndexError: list index out of range`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.95
- Cause: Hardwired save_02 corpus assumption. The outline from the empty private save_02 is [], so outline[0] raises IndexError before the season/episode endpoint is exercised.
- Prerequisite: At least 1 playable narrative chunk with chunk_metadata (season, episode set).
- Repair steps:
  1. Use the shared seeded reader slot (see file_notes).

#### `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_context_shape`

- Baseline outcome: failure; signature: `IndexError: list index out of range`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.94
- Cause: Hardwired save_02 corpus assumption. The outline is empty, so outline[-1] raises IndexError. The test also opens get_connection(f'save_{READ_SLOT:02d}') directly to compute expected settings, which hardwires the owner slot name a second time.
- Prerequisite: At least 1 playable chunk with metadata. To keep the settings comparison non-vacuous, the last chunk needs at least 1 place_chunk_references row with reference_type='setting' and ideally 1 chunk_character_references row.
- Repair steps:
  1. Use the shared seeded reader slot. Seed a 'setting' place reference (and a present character reference) on the last chunk.
  1. Replace get_connection(f'save_{READ_SLOT:02d}') with the fixture's dbname.

#### `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_episodes_shape`

- Baseline outcome: failure; signature: `IndexError: list index out of range`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.95
- Cause: Hardwired save_02 corpus assumption. /api/narrative/seasons returns [] on the empty private save_02, so seasons[0] raises IndexError.
- Prerequisite: 1 seasons row and at least 1 episodes row for that season (chunk_span, summary).
- Repair steps:
  1. Use the shared seeded reader slot, inserting a seasons row and a matching episodes row (see tests/test_world_clock_contract_pg.py and tests/test_api/test_narrative_jobs_pg.py for existing seasons/episodes inserts).

#### `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_latest_chunk_shape`

- Baseline outcome: failure; signature: `AssertionError: assert {'detail'} == {'choiceObjec...etadata', ...}`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.96
- Cause: Hardwired save_02 corpus assumption. get_latest_chunk finds no playable chunk joined to chunk_metadata and returns 404 {'detail': 'No chunks found'}, so the key-set assertion sees {'detail'}. That is correct endpoint behavior on an empty story.
- Prerequisite: At least 1 playable narrative chunk (no Retrograde prologue marker) with a chunk_metadata row including world_time/slug.
- Repair steps:
  1. Use the shared seeded reader slot (see file_notes).

#### `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_outline_and_chunk_by_id`

- Baseline outcome: failure; signature: `assert []`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.95
- Cause: Hardwired save_02 corpus assumption. /api/narrative/outline returns [] on the empty private save_02, so `assert outline` fails ('assert []').
- Prerequisite: At least 1 playable narrative chunk with chunk_metadata.
- Repair steps:
  1. Use the shared seeded reader slot (see file_notes).

#### `tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_seasons_shape`

- Baseline outcome: failure; signature: `assert (True and [])`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.96
- Cause: Hardwired save_02 corpus assumption. /api/narrative/seasons returns [] on the empty private save_02, so `isinstance(seasons, list) and seasons` fails ('assert (True and [])').
- Prerequisite: At least 1 seasons row.
- Repair steps:
  1. Use the shared seeded reader slot (see file_notes).

#### `tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_characters_shape`

- Baseline outcome: failure; signature: `assert []`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.95
- Cause: Hardwired save_02 corpus assumption. /api/characters returns [] on the empty slot ('assert []'). Since b0645daf the query also reads character_identity_rulings (migration 128), so the clone must carry that migration. The payload key set the test expects is unchanged.
- Prerequisite: At least 1 character row (base_timestamp seeded first). Ideally one with current_location set, so the string-coercion check is exercised.
- Repair steps:
  1. Use the shared seeded reader slot. seed_protagonist, then set current_location to the seeded place.

#### `tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_current_place`

- Baseline outcome: failure; signature: `assert 404 == 200`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.95
- Cause: Hardwired save_02 corpus assumption. get_current_place finds no place_chunk_references 'setting' row joined to chunk_metadata and returns its documented 404 ('No current place recorded'), so `assert 404 == 200` fails.
- Prerequisite: At least 1 place_chunk_references row with reference_type='setting' on a chunk that has chunk_metadata. Two settings on the latest chunk would exercise the place-id ordering assertion.
- Repair steps:
  1. Use the shared seeded reader slot. Seed setting references on the last seeded chunk.

#### `tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_places_shape`

- Baseline outcome: failure; signature: `assert []`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.95
- Cause: Hardwired save_02 corpus assumption. /api/places returns [] on the empty slot ('assert []'). The test also requires at least one place with PostGIS coordinates.
- Prerequisite: A layer and a zone, plus at least 1 place whose coordinates is a geography Point (for example ST_SetSRID(ST_MakePoint(x,y,0,0),4326)::geography, as in tests/test_gis_scripts_live.py).
- Repair steps:
  1. Use the shared seeded reader slot, inserting layer, zone, and a place with coordinates (pattern from tests/test_api/test_reader_place_provenance_pg.py plus geography).

#### `tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_relationships_and_psychology`

- Baseline outcome: failure; signature: `IndexError: list index out of range`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.94
- Cause: Hardwired save_02 corpus assumption. /api/characters returns [] on the empty slot, so characters[0] raises IndexError.
- Prerequisite: At least 1 character. Inserting it needs base_timestamp first because of the need-state trigger. To make the shape checks non-vacuous, also 1 character_relationships row and 1 character_psychology row for that character.
- Repair steps:
  1. Use the shared seeded reader slot: seed_protagonist plus a second character, a relationship between them and a psychology row. Relationship writes need SET LOCAL nexus.write_producer (migration 115 trigger).

#### `tests/test_api/test_reader_asset_endpoints.py::TestWorldReads::test_zones_shape`

- Baseline outcome: failure; signature: `assert []`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.95
- Cause: Hardwired save_02 corpus assumption. /api/zones returns [] on the empty slot ('assert []').
- Prerequisite: At least 1 zones row (with a layer). A boundary is optional for the key-set check.
- Repair steps:
  1. Use the shared seeded reader slot (the zone seeded for places).

#### `tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_drains_starved_corpus`

- Baseline outcome: failure; signature: `assert 0 == 9`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is a #800 regression proof pinned to a historical snapshot of the owner's save_04: 'the nine original jobs' plus an unnarrated promoted orrery_resolution. It clones save_04 with data, which is empty in the private cluster. It selects queued character_experience_jobs and asserts len == 9, which gives 'assert 0 == 9'. The literal 9 is a corpus fact that will also rot on the owner machine once those jobs drain. The scheduler contract under test is corpus-independent: one owner pass drains the queued experience jobs to terminal states and dispatches a pending narration.
- Prerequisite: N queued, due character_experience_jobs with valid seeds (from world_events and seed_character_experiences_sync). At least one orrery_resolution with promotion_status 'pending' and no offscreen_narrations row. Also base_timestamp, user_character, and TEST routing.
- Repair steps:
  1. Replace the save_04 clone with a default clone plus seed_protagonist. Seed N render jobs through the promoted tests/test_orrery/test_character_experiences_pg.py::_enqueue_render_job helper and one pending resolution through tests/test_orrery/test_narration_job_fencing_pg.py::_materialize_pending_resolution.
  1. Assert on the seeded job ids instead of the literal 9.
  1. Optionally keep the owner-corpus variant behind an explicit corpus flag (e.g. NEXUS_RUN_CORPUS=1). Seeding is the more honest gate default, because gating alone produces a permanent skip that is still date-bound on the owner corpus.

#### `tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_live_turn_starts_before_queued_render`

- Baseline outcome: failure; signature: `RuntimeError: qa640_800_turn_4808e194c297 has no accepted narrative tail`
- Route: `seed_disposable_clone` to #816; confidence 0.88; runtime confirmation needed
- Cause: The test clones save_04 with include_data=True, which is empty in the private cluster. It then calls refresh_tail_fingerprint(dbname=...), which raises 'qa640_800_turn_... has no accepted narrative tail' because narrative_chunks is empty. The rest of the test depends on a played corpus. It drives a real TEST 'continue --choice 1' turn through the gateway. It needs queued character_experience_jobs that exist before the turn: they are pushed an hour out, then made due at acceptance so the scheduler renders after generation starts. It asserts the commit, generation, render ordering and /runtime/status. Secondary hazard: with NEXUS_GATEWAY_PORT unset (as CLAUDE.md requires), gateway_lane binds the fixed port 8018 and asserts via lsof that it is free, so it can collide with a running owner gateway.
- Prerequisite: A playable TEST story: base_timestamp, user_character with a zoned location, and a tail chunk with world_time plus a Pass-2 baseline. At least one queued character_experience_jobs row with valid seeds (NPC dossiers and slept events) must exist before the turn. model/gaia_model must be TEST.
- Repair steps:
  1. Use the shared playable_test_story factory (wizard bootstrap via TEST in a default clone; see attempt-manifest notes), then enqueue one render job with the promoted _enqueue_render_job helper.
  1. Set NEXUS_GATEWAY_PORT=0 in the test, as test_attempt_manifest_pg does, so gateway_lane binds an ephemeral port.
  1. Remove the save_04 corpus clone. The fingerprint refresh is unnecessary for a story bootstrapped under the TEST config.

#### `tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_rechecks_generation_after_leasing_before_provider`

- Baseline outcome: failure; signature: `assert False`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The test clones save_04 with data, which is empty in the private cluster. It patches experiences._render_prompt to start an interactive generation lease just after the scheduler leases an experience job, then asserts selected.wait(5). The empty clone has no queued character_experience_jobs, so the scheduler never selects a job, _render_prompt is never called, and 'assert selected.wait(5)' fails, recorded as 'assert False'. On the owner corpus, save_04's pre-existing queued jobs supplied the job.
- Prerequisite: At least one due, queued character_experience_jobs row whose seeds validate for rendering (NPCs with summary and background, slept world_events, seed_character_experiences_sync). Also base_timestamp, user_character, and TEST provider routing.
- Repair steps:
  1. Use a default clone plus route_slot plus seed_protagonist, and enqueue one job through the promoted _enqueue_render_job helper.
  1. Drop source_db='save_04', include_data=True.

#### `tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience`

- Baseline outcome: failure; signature: `AssertionError: Scheduler did not reach the expected durable state`
- Route: `seed_disposable_clone` to #885; confidence 0.8; runtime confirmation needed
- Cause: The test clones save_04 with include_data=True and hardwires experience job id=3 in four places: the available_at update, the dead-lease read, the completion poll, and the implicit completion-proof trigger expectation. The private save_04 is empty, so there is no job 3, and the child gateway's scheduler also loops in 'recovering' on PlayerIdentityNotEstablishedError. The TEST provider therefore never logs 'Experience render received; response delay=4', and wait_until(timeout=15) raises 'Scheduler did not reach the expected durable state'. The same message is also raised by the mock-server and gateway readiness waits. Those are unlikely: a crashed process would raise the process.poll() assertion carrying its log, and the lsof checks earlier in the test must have passed.
- Prerequisite: Template clone with a bound protagonist and one queued renderable non-player character_experience_jobs row (experience_ids set). Port 8018 free, with NEXUS_GATEWAY_PORT unset. lsof available. The TEST provider delayed by 4 s.
- Repair steps:
  1. Use disposable_slot_database('qa640_800_kill'), seed_protagonist, and the shared seed_experience_render_job helper; keep the scheduler_completion_proof trigger.
  1. Replace every id=3 literal and the '[(3, 1)]' assertion with the returned job id.

#### `tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]`

- Baseline outcome: failure; signature: `assert False`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: The test clones save_04 with disposable_slot_database(source_db='save_04', include_data=True). In the private cluster save_04 is an empty template clone, so the clone has no character_experience_jobs row id=3 and no bound protagonist. 'UPDATE character_experience_jobs SET available_at=clock_timestamp() WHERE id=3' silently updates 0 rows. The scheduler never leases an experience job, so the patched _track_lease never runs and selected.wait(5) returns False, giving 'assert False'. Every drain pass also raises PlayerIdentityNotEstablishedError: drain_experience_render_jobs_sync (nexus/agents/orrery/experiences.py:1822) calls canonical_player_entity_id unconditionally because nexus.toml sets include_player_character=false, and global_variables.user_character is NULL. The owner's save_04 supplies both the job and the protagonist.
- Prerequisite: global_variables.base_timestamp and user_character bound to a character with an entity row. One queued character_experience_jobs row whose experience_ids point at non-player characters with complete dossiers (at least 2 of summary/background/personality), seeded from world_events at a scene-end chunk, plus a boundary chunk and resolved_model captured at enqueue (clone pinned to TEST). The database name must start with 'qa640_' for route_slot.
- Repair steps:
  1. Replace the save_04 corpus clone with disposable_slot_database('qa640_800_renew'), a template clone, then call seed_protagonist(dbname).
  1. Move _enqueue_render_job from tests/test_orrery/test_character_experiences_pg.py into a shared helper (for example tests/pg_fixtures.seed_experience_render_job). It seeds actors, world_events and experiences through seed_character_experiences_sync and enqueues through enqueue_scene_experience_job_sync. Have it return the job id.
  1. Use the returned job id instead of the hardcoded id=3. The blanket available_at postponement becomes a harmless no-op.

#### `tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-correspondence_compaction_jobs]`

- Baseline outcome: failure; signature: `assert False`
- Route: `seed_disposable_clone` to #885; confidence 0.75; runtime confirmation needed
- Cause: This branch seeds its own chunks (_insert_chunk), letters (persist_staged_correspondence) and a compaction job (enqueue_compaction), and that setup succeeds, so the compaction job exists. The clone still has no canonical protagonist, and SlotScheduler._drain runs promotion, then narration, then the experience queue, all before compaction. drain_experience_render_jobs_sync calls canonical_player_entity_id, which raises PlayerIdentityNotEstablishedError ('user_character is NULL') on every pass. _run catches it, calls _recover (state 'recovering') and retries after error_backoff_seconds. drain_compaction is never reached, so _track_lease is never called and selected.wait(5) returns False. On the owner's save_04 a protagonist exists, so the experience drain returns (0,0) and compaction is leased.
- Prerequisite: global_variables.base_timestamp and user_character bound to a character with an entity row (seed_protagonist), set before the chunks are inserted. More than floor_turns accepted correspondence exchanges; the test already seeds ceiling_turns+1. No corpus is needed.
- Repair steps:
  1. Use disposable_slot_database('qa640_800_renew'), a template clone, and call seed_protagonist(dbname) before the compaction seeding.
  1. Keep the existing compaction seeding and drop the save_04 corpus dependency.

#### `tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[True-character_experience_jobs]`

- Baseline outcome: failure; signature: `assert False`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: Same as the [False-character_experience_jobs] node, and the lose_lease branch is never reached. The empty save_04 clone has no experience job id=3 and no user_character, so nothing is leased, selected.wait(5) returns False, and the test fails with 'assert False'.
- Prerequisite: Same as the [False] variant: a bound protagonist and one queued, renderable, non-player character_experience_jobs row.
- Repair steps:
  1. Same shared fixture as the [False] variant: template clone, seed_protagonist, shared seed_experience_render_job helper, and the returned job id in place of id=3.

#### `tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[True-correspondence_compaction_jobs]`

- Baseline outcome: failure; signature: `assert False`
- Route: `seed_disposable_clone` to #885; confidence 0.75; runtime confirmation needed
- Cause: Same as the [False-correspondence_compaction_jobs] node. With no user_character, the experience drain raises PlayerIdentityNotEstablishedError on every scheduler pass before drain_compaction runs, so the seeded compaction job is never leased and selected.wait(5) returns False.
- Prerequisite: seed_protagonist (base_timestamp plus a bound user_character with an entity) before the chunks and letters are seeded.
- Repair steps:
  1. Same as the [False] compaction variant: template clone plus seed_protagonist; no corpus.

#### `tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs`

- Baseline outcome: failure; signature: `AssertionError: Source must contain legacy queued experiences`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: The test pg_dumps save_04 directly (not through disposable_slot_database), restores it, and requires the source to still contain active (queued/leased) character_experience_jobs, then runs migration 126 on it. The private save_04 is a template clone with no jobs, so the pre-migration assertion fails with 'Source must contain legacy queued experiences'. The test is also time-bound on the owner's machine. It needs a source that predates migration 126 ('applied >= 1' and every active row == (expected, 'migration_backfill')), so it stops being valid once save_04 has been migrated past 126 and enqueues new jobs with story_pin sources.
- Prerequisite: A database at the pre-126 schema (resolved_model and resolved_source columns absent on the four JOB_SEATS tables, no schema_migrations '126' row). Queued/leased plus terminal rows in character_experience_jobs, and ideally also in orrery_maturation_jobs, correspondence_compaction_jobs and narrative_summary_jobs. global_variables model/gaia_model pins.
- Repair steps:
  1. Create a template clone and seed_protagonist. Seed active and terminal jobs for each JOB_SEATS table through the production enqueue paths (seed_experience_render_job, enqueue_compaction, and the maturation and summary enqueue paths), then mark some rows terminal.
  1. Rewind the clone to pre-126: for each JOB_SEATS table, ALTER TABLE ... DROP COLUMN resolved_model and resolved_source, then DELETE FROM schema_migrations WHERE version='126'. Migrations 127-129 do not reference these columns. Follow the _apply_migration_100 precedent in tests/test_orrery/test_need_clock_anchor_pg.py.
  1. Run migrate.migrate_database(clone) and keep the existing backfill and terminal-NULL assertions; drop the save_04 pg_dump.

#### `tests/test_api/test_seat_policy_jobs_pg.py::test_accept_repin_and_scheduler_use_literal_seat_models`

- Baseline outcome: failure; signature: `RuntimeError: qa640_814_seats_3f429a0fff7d has no accepted narrative tail`
- Route: `seed_disposable_clone` to #816; confidence 0.87; runtime confirmation needed
- Cause: The test clones save_04 with include_data=True, which is empty in the private cluster. After checking the migration 126 stamp (present via the template), it calls refresh_tail_fingerprint, which raises 'qa640_814_seats_... has no accepted narrative tail'. Beyond that, the test needs one real TEST turn whose acceptance enqueues all four queues for the session: character_experience_jobs via a scene boundary plus prior-scene seeds, orrery_maturation_jobs via the injected 'Policy Courier', correspondence_compaction_jobs via floor_turns=1, and narrative_summary_jobs via a new_season transition. It asserts 'before[table]' is non-empty for each. On a freshly bootstrapped story the experience queue is empty unless seeds exist. Secondary hazard: the test hardcodes NEXUS_GATEWAY_PORT=8019 and NEXUS_API_URL :8019 (fixed-port collision risk).
- Prerequisite: A playable TEST story (base_timestamp, user_character with a zoned location, tail chunk with world_time plus a Pass-2 baseline). Valid unrendered character_experiences seeds for NPCs anchored at or before the scene end. Correspondence history sufficient for compaction at floor_turns=1. schema_migrations stamped 126.
- Repair steps:
  1. Use the shared playable_test_story factory. Then seed prior-scene experience candidates on the tail chunk with the promoted seed helper (world_events plus seed_character_experiences_sync) so the scene-boundary acceptance enqueues an experience job.
  1. Replace the fixed 8019 port with NEXUS_GATEWAY_PORT=0 and let gateway_lane set NEXUS_API_URL.
  1. Drop the save_04 corpus clone and the fingerprint refresh.

#### `tests/test_api/test_session_truth_pg.py::test_generation_session_preserves_bootstrap_error_class[provider_timeout]`

- Baseline outcome: failure; signature: `AssertionError: {'chunk_id': None, 'created_at': datetime.datetime(2026, 9, 25, 1, 44, 55, 961354, tzinfo=datetime.timezone(datetime.t... narrative: No setting found i...`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The test clones save_04 (include_data=True) and runs generate_narrative_async with parent 0 (bootstrap), expecting the TEST writer delay (2 s) to exceed request_timeout (0.1 s) and record error_class 'ReadTimeout'. The empty clone has global_variables.setting NULL, so generate_bootstrap_narrative raises ValueError('No setting found in global_variables; transition may not have completed') at nexus/api/narrative_generation.py:671, before any provider call. The recorded error_class is ValueError. The recorded state dict ('narrative: No setting found i...') confirms this. Error-class preservation itself worked correctly.
- Prerequisite: A transitioned story: global_variables.setting JSON with story_seed, a canonical protagonist whose characters.current_location references a places row, base_timestamp, the TEST model pins the test already sets, and the TEST provider (mock_openai_server).
- Repair steps:
  1. Replace the save_04 corpus clone with disposable_slot_database('qa640_775_errors') plus a shared seed_transitioned_story(dbname) helper. The helper promotes _build_story_transition and NewStoryDatabaseMapper.perform_transition from tests/test_orrery/test_need_clock_anchor_pg.py, using tests/fixtures/slot3_midnight_qa_wizard_cache.json, into tests/pg_fixtures.py.
  1. Apply the same fixture to the [validation] variant so its 'SET setting=NULL' is the actual cause of the ValueError.

#### `tests/test_api/test_summary_budget_usage.py::test_summary_budget_fails_job_before_test_provider_call[episode]`

- Baseline outcome: failure; signature: `RuntimeError: Episode S01E02 has no chunks to summarize`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The test (tests/test_api/test_summary_budget_usage.py:120-122) builds its disposable database with disposable_slot_database(source_db="save_04", include_data=True), i.e. a pg_dump/pg_restore copy of save_04's corpus. It expects that copy to hold season 1 / episode 2 narrative that becomes "oversized" once the input budget is squeezed to 1 token. On the private cluster, save_04 is an empty template clone, so the copy has no narrative_chunks or chunk_metadata rows. schedule_summary_generation still queues the S01E02 job. In drain_summary.prepare (nexus/jobs/summaries.py:35-42), get_episode_chunk_span(1, 2) returns None and the explicit guard raises RuntimeError('Episode S01E02 has no chunks to summarize'). That happens before the generator's _token_check could raise the SummaryInputTooLong the test expects. The guard is behaving correctly. The test simply never reached the budget path.
- Prerequisite: A slot clone whose narrative_chunks holds at least one row with non-empty raw_text, joined by chunk_metadata(season=1, episode=2, scene=1). Also a seasons row id=1 and episodes rows (1,1) and (1,2) with summary NULL, if chunk_metadata has foreign keys to them (check with \d+ chunk_metadata). No world clock or characters are needed. The TEST model pin comes from disposable_slot_database's story_pin default.
- Repair steps:
  1. Replace source_db="save_04", include_data=True with a plain template clone: disposable_slot_database("qa640_937_budget").
  1. Before the existing DELETE/UPDATE cleanup block, insert one narrative_chunks row (raw_text and storyteller_text of a few sentences) plus a chunk_metadata row (season=1, episode=2, scene=1, world_layer='primary'). Add the seasons and episodes rows if the schema requires them. Seeding first lets the cleanup purge any embedding or summary jobs that insert triggers enqueue.
  1. Consider a shared tests/pg_fixtures.py helper seed_chunk(dbname, *, raw_text, season, episode, scene, world_time=None) -> int. Batch-4 files also need it.
  1. Keep SlotScheduler(4, dbname=dbname): the slot number is only a label here. Keep the input_budget=1 assertion, since any non-empty chunk exceeds it.

#### `tests/test_api/test_summary_budget_usage.py::test_summary_budget_fails_job_before_test_provider_call[season]`

- Baseline outcome: failure; signature: `RuntimeError: Summary provider returned no summary`
- Route: `seed_disposable_clone` to #885; confidence 0.85; product defect suspected, runtime confirmation needed
- Cause: Same shared cause as the [episode] node: the save_04 include_data clone is empty on the private cluster. For the season job, prepare() in nexus/jobs/summaries.py has no no-chunk guard; the explicit guard at lines 35-42 applies only to episodes. It therefore calls SummaryGenerator.generate_season_summary(1) (scripts/summarize_narrative.py:1501-1518). get_season_chunks(1) returns [], and the function logs 'No chunks found' and returns None without setting last_error. prepare() then raises RuntimeError(generator.last_error or 'Summary provider returned no summary') (summaries.py:63-66). That message is misleading, because no provider was ever called. The expected SummaryInputTooLong from _token_check is never reached.
- Prerequisite: At least one narrative_chunks row joined by chunk_metadata(season=1, any episode, scene), plus seasons row id=1 with summary NULL (the test NULLs seasons.id=1). With the input budget at 1 token, any non-empty chunk text is oversized.
- Repair steps:
  1. Use the same seeded template clone as the [episode] case (see file note). A chunk in S01E02 covers both the episode and season parametrizations.
  1. Optionally, as a separate small product fix: in drain_summary.prepare, add a season-side guard mirroring the episode guard (db.get_season_chunks(season) empty -> RuntimeError('Season S01 has no chunks to summarize')). Alternatively, have generate_season_summary set last_error when it finds no chunks, so the failure is not misreported as a provider failure.
- Product defect detail: This is secondary and did not cause the test's intended assertion to fail; with a seeded chunk the test should reach SummaryInputTooLong. The product issue is that a season summary job for a season with no chunks is reported as 'Summary provider returned no summary' (error_class RuntimeError) even though the provider was never called. Unlike the episode path, there is no explicit no-chunk guard, and drain_job retries the failure as if it were transient. Severity is low (misleading error text and wasted retries). It could be filed as a small new issue.

#### `tests/test_faction_table_audit.py::test_build_faction_table_audit_reads_slot2_legacy_tag_categories`

- Baseline outcome: failure; signature: `assert 0 >= 1`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: _slot2_faction_audit() runs build_faction_table_audit read-only against TEST_DBNAME='save_02' through get_connection. The private save_02 is an empty template clone with zero factions, so counters['factions_scanned'] is 0 and 'assert 0 >= 1' fails. The test is intentionally bound to slot 2's legacy faction data. An in-file comment says slot-2 retrofit live coverage was retired by owner order on 2026-07-17, but these live audit nodes were kept.
- Prerequisite: At least one faction entity (entities.kind='faction') with a factions row carrying legacy columns (ideology, power_level, resources and similar), plus entity_tags in LEGACY_TAG_CATEGORIES categories, which need template vocab tags for those categories or tags inserted in the clone.
- Repair steps:
  1. Add a fixture that creates a template clone, inserts one or two faction entities and factions rows with legacy column values, and attaches entity_tags in legacy categories (registering tags and categories in the clone if the template lacks them).
  1. Point the audit at the clone (get_connection(clone)) instead of 'save_02'. Seeding is more honest than a corpus flag: the audit logic is data-agnostic, and the owner retired slot-2 retrofit coverage.

#### `tests/test_faction_table_audit.py::test_cli_faction_audit_returns_live_slot2_payload`

- Baseline outcome: failure; signature: `assert 0 >= 1`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: cli.run_faction_audit(Namespace(slot=2)) resolves slot_dbname(2)='save_02' and audits it. The private save_02 has no factions, so faction_audit.counters.factions_scanned is 0 and 'assert 0 >= 1' fails. The test also asserts dbname == 'save_02', which hardwires the owner slot.
- Prerequisite: Slot 2 routed to a clone containing at least one faction entity and factions row.
- Repair steps:
  1. Reuse the seeded faction clone fixture and route slot 2 to it: monkeypatch nexus.api.slot_utils.slot_dbname (the CLI imports it at call time) and VALID_DBNAMES. This generalizes offline_gate_db or tests/scheduler_helpers.route_slot to any slot.
  1. Assert dbname == clone instead of 'save_02'.

#### `tests/test_lore/test_baseline_fingerprint_refresh_pg.py::test_divergence_fingerprint_refresh_preserves_save4_continuation`

- Baseline outcome: failure; signature: `assert 0 == 1`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The test clones save_04 with include_data=True and reads tail_id = max(narrative_chunks.id), which is None in the empty private clone. It then UPDATEs lore_pass_baselines WHERE chunk_id = tail_id, which matches nothing, so 'assert cur.rowcount == 1' fails with 'assert 0 == 1'. The rest of the test needs a playable story: a stamped Pass-2 baseline on the tail and a real LORE(enable_logon=False).process_turn that reaches 'LOGON disabled'.
- Prerequisite: Story pin (disposable TEST pin), a bound protagonist and world clock, one or more accepted narrative chunks with chunk_metadata and a setting place reference, a lore_pass_baselines row on the tail (from scripts/stamp_lore_pass_baseline.stamp_slot_tail(dbname=...)), and whatever MEMNON retrieval needs to complete a non-LOGON turn on unembedded chunks.
- Repair steps:
  1. Build a template clone with a seeded story: a shared seed_transitioned_story helper that promotes _build_story_transition from tests/test_orrery/test_need_clock_anchor_pg.py and NewStoryDatabaseMapper.perform_transition, plus a seed_accepted_chunks helper. Stamp the tail with stamp_slot_tail(dbname=clone). The 'qa640_' prefix already passes evaluation_dbname.
  1. Keep the historical-fingerprint injection, CLI refresh, story-pin projection and missing-baseline refusal as written.
  1. If real LORE retrieval cannot complete on an unembedded seeded story, split the test. Keep the refresh_tail_fingerprint and LORE fingerprint-compatibility proof on the seeded clone, and move the 'save_04 continuation' proof behind an explicit corpus opt-in.

#### `tests/test_lore/test_intertitle_live.py::test_anchor_fallback_skips_retrograde_prologue`

- Baseline outcome: failure; signature: `assert (None is not None)`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: On save_02 (hardcoded), the test inserts a synthetic Retrograde prologue chunk and expects _orrery_anchor_chunk_id to return an older playable chunk. The empty private save_02 has no playable chunk, so max(nc.id) under playable_narrative_predicate is None, and 'assert anchor is not None and anchor < inserted' fails. The test also writes to an owner slot inside a rolled-back transaction, which would fail outright on a locked (read-only) slot.
- Prerequisite: At least one playable narrative_chunks row (no RETROGRADE_PROLOGUE_MARKER in authorial_directives) older than the inserted prologue.
- Repair steps:
  1. Use a template clone with one or two seeded playable chunks (_insert_chunk-style) and insert the prologue there, so owner slots are never written.
  1. Route through sqlalchemy_url(clone).

#### `tests/test_lore/test_intertitle_live.py::test_load_intertitle_executes_against_live_slot`

- Baseline outcome: failure; signature: `assert None is not None`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: The test connects straight to LIVE_SLOT=2 through get_slot_db_url(slot=2), a hardcoded owner slot, and reads max(chunk_id) FROM chunk_metadata. The private save_02 is empty, so the anchor is None and 'assert anchor is not None' fails with 'assert None is not None'. Past that point, _load_intertitle would also need canonical_player_character_id (user_character).
- Prerequisite: Bound protagonist (base_timestamp plus user_character) whose characters.current_location references a places row with WGS84 coordinates. One narrative chunk with chunk_metadata season/episode/scene/world_layer/world_time.
- Repair steps:
  1. Use a template clone with seed_transitioned_story (which supplies setting, protagonist, and a layer/zone/place with coordinates as current_location) plus one accepted chunk with a world_time.
  1. Open the SQLAlchemy engine on tests.pg_fixtures.sqlalchemy_url(clone) instead of get_slot_db_url(slot=2).

#### `tests/test_lore/test_pass2_chunk1369.py::test_pass2_handles_karaoke_divergence`

- Baseline outcome: error; signature: `failed on setup with "nexus.agents.orrery.player_identity.PlayerIdentityNotEstablishedError: Cannot resolve canonical player identity: user_character is NULL"`
- Route: `gate_behind_corpus_flag` to #885; confidence 0.95
- Cause: The module fixture `lore_agent` builds disposable_slot_database('qa_pass2_corpus', source_db='save_01', include_data=True) and constructs LORE on it. LORE initializes MemoryManager._initialize_entity_maps (nexus/memory/manager.py:1129-1185), which calls canonical_player_character_id and deliberately re-raises RuntimeError. In the private cluster save_01 is an empty template clone, so global_variables.user_character is NULL and PlayerIdentityNotEstablishedError is raised during setup. The test is corpus-bound by design: it hardcodes golden-master chunk 1369, the deep-cut range 743-770, and characters Alex/Emilia/Pete/Nyati, and it checks real hybrid-retrieval ranking. CLAUDE.md names it as the divergence-detection integration probe. Seeding a disposable clone cannot reproduce it honestly.
- Prerequisite: The save_01 golden-master corpus: at least 1,425 chunks including 1369 and 743-770, with embeddings, user_character bound to a named character, characters and aliases, and places. Plus a working local embedding model for MEMNON queries.
- Repair steps:
  1. Mark the module with a `requires_corpus` marker enabled only by an explicit NEXUS_RUN_CORPUS=1 (registered in pytest.ini and skipped in tests/conftest.py), and document it as an intentional integration exclusion from the private gate.
  1. Before cloning, preflight the source read-only (chunk 1369 exists and user_character is not NULL) and fail with an explicit 'golden-master corpus required' message instead of a PlayerIdentityNotEstablishedError from deep in LORE init.
  1. Keep the include_data clone so the owner's save_01 is never written.

#### `tests/test_lore/test_scene_order_render.py::test_recent_warm_window_ends_at_historical_parent`

- Baseline outcome: failure; signature: `assert 0 >= (10 + 10)`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: The test clones save_04 (include_data=True) and needs at least warm_slice_initial (10) plus 10 playable chunks, so it can anchor ten scenes behind the frontier. The empty private clone yields ids=[] and 'assert 0 >= (10 + 10)' fails. The rest of the test (real MEMNON get_chunk_by_id/get_recent_chunks, DB-less window_logon rendering) only needs chunk rows.
- Prerequisite: At least 20 playable narrative_chunks, each with a chunk_metadata row (season/episode/scene; world_time optional) so narrative_view returns them. No protagonist or clock is needed because no characters are inserted.
- Repair steps:
  1. Replace the save_04 corpus clone with a template clone seeded with 20 to 25 chunks and chunk_metadata rows, using a shared seed_accepted_chunks helper or _insert_chunk from test_narration_job_fencing_pg.
  1. Keep the offsets relative to warm_slice_initial read from settings.

#### `tests/test_lore/test_seat_blocks.py::test_seat_prompt_live_tag_library_and_order`

- Baseline outcome: failure; signature: `ValueError: Non-bootstrap narrative context requires metadata.target_chunk_id`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: The test clones save_04 (include_data=True) and sets payload.metadata.target_chunk_id = max(narrative_chunks.id), which is None in the empty private clone. LogonUtility.measure_turn_requests calls _read_presence_baseline_for_context, which raises 'ValueError: Non-bootstrap narrative context requires metadata.target_chunk_id' (nexus/agents/lore/logon_utility.py:2202). With a parent present, read_presence_baseline also needs the parent's roster with exactly one 'setting' place_chunk_references row, which continuation_setting requires, plus a canonical user_character.
- Prerequisite: Bound protagonist (base_timestamp plus user_character). One accepted narrative chunk with chunk_metadata and exactly one place_chunk_references row of reference_type 'setting' to a place (optionally chunk_character_references 'present'). Live Orrery tag library vocab from the template.
- Repair steps:
  1. Use a template clone with seed_transitioned_story (protagonist plus place) and one seeded parent chunk with chunk_metadata and a single setting place reference, through a shared seed_accepted_chunks helper that writes the setting reference.
  1. Pass the seeded chunk id as target_chunk_id; keep the VALID_DBNAMES patch.

#### `tests/test_orrery/test_adjudication_history.py::test_commit_persists_enriched_history_then_rolls_back`

- Baseline outcome: failure; signature: `AssertionError:`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: The test opens a raw psycopg2 connection with the module _connect(WRITE_SLOT=2), which hardcodes database=f'save_{slot:02d}' (lines 45-51). It then uses _fetch_one to read an anchor chunk and an actor. On the empty private save_02, 'SELECT max(id) FROM narrative_chunks' returns (None,), which passes _fetch_one because the row itself is not None, so anchor_chunk_id=None. The next query, characters JOIN entities ... LIMIT 1, returns no row, and _fetch_one's 'assert row is not None, sql' fires. The assertion message is the SQL string, which starts with a newline, giving the bare 'AssertionError:' first-line signature. The commit path (commit_orrery_tick_sync) was never reached.
- Prerequisite: One character with an active entities row (kind='character'), one narrative_chunks row to act as tick anchor, and chunk_metadata world_time on it or global_variables.base_timestamp. The commit path's drains (relationship drift, backstory reveal) and any need or world-time reads resolve the clock through _tick_world_time_sync (chunk_metadata world_time, else base_timestamp) and raise OrreryWorldClockUnavailableError without one. seed_protagonist supplies base_timestamp, the character and the entity.
- Repair steps:
  1. Replace _connect(WRITE_SLOT) with tests.pg_fixtures.connect(dbname) on a fixture built from disposable_slot_database('adjudication_history').
  1. Seed it with seed_protagonist(dbname), which provides base_timestamp, a character and its entity, and use the returned entity_id as actor_entity_id instead of querying characters.
  1. Insert one narrative_chunks row plus chunk_metadata(world_layer='primary', world_time=base) and use its id as anchor_chunk_id.
  1. Keep the rollback-and-verify structure. The post-rollback 'nothing persisted' check can use a fresh connect(dbname).

#### `tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots`

- Baseline outcome: failure; signature: `AssertionError: no audited slot has adjudication-log rows — the history assertions are vacuous; repoint HISTORY_SLOTS at a slot with Skald rulings`
- Route: `gate_behind_corpus_flag` to #885; confidence 0.95
- Cause: This is an intentional corpus non-vacuity probe (lines 330-344). It sums adjudication_history(session)['totals']['log_rows'] over HISTORY_SLOTS=(2, 5), resolved through get_slot_db_url(slot=...), and asserts the sum is greater than 0. Its purpose is to prove that the sibling oracle test test_adjudication_history_matches_sql_oracle is not vacuous. On the private cluster save_02 and save_05 are empty template clones with no orrery_adjudication_log rows, so the total is 0 and the guard fires, as designed. The sibling oracle nodes are absent from the red list: on empty slots they pass vacuously, which is exactly the hollowness this guard reports.
- Prerequisite: A slot with orrery_adjudication_log rows (ideally at least one each of defer, replace and void) and orrery_resolutions rows, including some with promotion_status='promoted'. In the owner environment that means Skald rulings in save_02/save_05; in a fixture it means rulings committed through commit_orrery_tick_sync on a seeded clone.
- Repair steps:
  1. Keep the save_02/save_05 audit only as a corpus-bound probe. Add a requires_corpus marker, skipped unless something like NEXUS_RUN_CORPUS=1, to tests/conftest.py; none exists yet. Run the probe against disposable_slot_database(source_db='save_0N', include_data=True) clones, never against the live slots.
  1. For the default PostgreSQL gate, re-point the oracle test at a module-scoped seeded clone so it is non-vacuous by construction. Seed it with seed_protagonist, one chunk with chunk_metadata world_time, and commit_orrery_tick_sync committed (not rolled back) with defer, replace and void rulings, then mark one resolution promoted. Assert log_rows > 0 on that clone as a precondition inside the oracle test.
  1. Gating only the guard is not enough: once the guard is gated, the oracle test on empty slots still passes vacuously in the default gate unless it is re-pointed to the seeded clone.

#### `tests/test_orrery/test_build_venture_async.py::test_async_build_venture_start_and_completion_match_sync`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The test connects straight to the hardcoded 'save_02' via asyncpg_kwargs('save_02'). Inside a rolled-back transaction it builds a shadow schema (search_path = shadow, public) and applies migration 084. It then does `int(await conn.fetchval('SELECT entity_id FROM characters WHERE entity_id IS NOT NULL ORDER BY id LIMIT 1'))` against public.characters. On the empty private save_02 fetchval returns None, which gives TypeError int(NoneType). #922 had passed this test on the owner's populated save_02 after fixing the asyncpg adapter (docs/qa/test-fallout-repair/verification.md:213). It also needs a chunk_metadata row with non-null world_time (asserted), used by _tick_world_time_async. It borrows an owner save as its test database.
- Prerequisite: One characters row with a non-null entity_id (entity kind 'character'). One narrative_chunks row with chunk_metadata.world_time not null. global_variables.base_timestamp set before the character insert (need-state trigger). Template seeds are sufficient for tags/event_types, since the shadow schema gets 'proprietor' from migration 084.
- Repair steps:
  1. Replace asyncpg_kwargs('save_02') with a disposable clone: tests.pg_fixtures.disposable_slot_database('qa_build_venture_async') plus tests.pg_fixtures.asyncpg_kwargs(dbname).
  1. Seed with tests.pg_fixtures.seed_protagonist(dbname), which binds the clock first and then the character/entity, and use the returned entity_id as the actor.
  1. Insert one narrative_chunks row plus chunk_metadata with world_time, following the _insert_chunk_at idiom in test_need_clock_anchor_pg.py:214-235 (INSERT, then UPDATE world_time, because trg_chunk_metadata_refresh_world_time recomputes world_time on INSERT).
  1. Keep the shadow-schema-plus-084 setup unchanged; it tests the migration's constraints, not isolation.

#### `tests/test_orrery/test_build_venture_projects.py::test_live_applier_runs_start_progress_milestones_and_completion`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Fixture `live_venture_db` connects to get_slot_db_url(slot=2) (save_02), creates the shadow runtime schema plus migration 084, then runs `actor, other = (int(row[0]) for row in cur.fetchall())` on 'SELECT entity_id FROM characters ... LIMIT 2'. On the empty private save_02 fetchall() returns [], so setup raises ValueError: not enough values to unpack (expected 2, got 0). The next query (latest chunk_metadata with world_time, then fetchone unpack) would also fail on an empty slot.
- Prerequisite: Two characters rows with entity_ids. One narrative chunk whose chunk_metadata.world_time is not null. base_timestamp set before the character inserts.
- Repair steps:
  1. Apply the shared fixture repair in file_notes: a disposable clone seeded with two characters and one timed chunk.
  1. No per-test seed beyond the fixture.

#### `tests/test_orrery/test_build_venture_projects.py::test_live_stall_abandon_and_budget_interaction`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Same `live_venture_db` fixture: the empty save_02 returns zero characters, so `actor, other = ...` raises the unpack ValueError during setup. This test really does need the second character (`other`) to show the one-open-project budget is per character.
- Prerequisite: Two characters with entity_ids (actor and other), plus one chunk with world_time.
- Repair steps:
  1. Apply the shared fixture repair in file_notes; make sure the seed creates two distinct character entities.

#### `tests/test_orrery/test_build_venture_projects.py::test_live_start_rejects_every_target_column`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Same `live_venture_db` fixture: setup fails with 'not enough values to unpack (expected 2, got 0)' because the empty save_02 has no characters. The rejection assertions ('forbids all targets') are raised by _apply_project_start_sync after _tick_world_time_sync, so the body also needs the seeded chunk.
- Prerequisite: Two characters with entity_ids (the fixture's shape), plus one chunk with world_time.
- Repair steps:
  1. Apply the shared fixture repair in file_notes.

#### `tests/test_orrery/test_build_venture_replay.py::test_build_venture_replays_applied_snapshots_through_completion`

- Baseline outcome: error; signature: `failed on setup with "TypeError: 'NoneType' object is not subscriptable"`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: Fixture `replay_db` connects to save_02 (get_slot_db_url(slot=2)), builds the shadow schema plus migration 084, then runs `actor = int(cur.fetchone()[0])` on 'SELECT entity_id FROM characters ... LIMIT 1'. On the empty private save_02 fetchone() is None, giving TypeError: 'NoneType' object is not subscriptable during setup. The body has a second empty-slot hazard: `_chunk` inserts narrative_chunks with `SELECT max(id) + 1 FROM narrative_chunks`, which yields a NULL id on an empty table, so at least one pre-existing chunk is required. max(world_time) already has a hardcoded fallback.
- Prerequisite: One characters row with entity_id. At least one existing narrative_chunks row (for the max(id)+1 idiom). base_timestamp set (need-state trigger on the character insert; world_time refresh trigger). Template seed tables for capture_state_checkpoint_sync sections.
- Repair steps:
  1. Replace the save_02 connection with tests.pg_fixtures.disposable_slot_database('qa_build_venture_replay') plus pg_fixtures.connect(dbname).
  1. Seed with seed_protagonist(dbname) (actor = the returned entity_id) and one timed narrative chunk.
  1. Change `_chunk` to let the narrative_chunks id sequence assign ids (INSERT ... RETURNING id) instead of max(id)+1, so it does not depend on existing rows or bypass the sequence.

#### `tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[False]`

- Baseline outcome: failure; signature: `AssertionError: assert (())`
- Route: `gate_behind_corpus_flag` to #885; confidence 0.9
- Cause: card_database clones the save_04 corpus (include_data=True). In the isolated cluster the source is empty. The test computes anchor = SELECT max(id) FROM narrative_chunks, which is NULL, and resolve_dry_run(anchor_chunk_id=None), whose Optional anchor is by design, returns a proposal with no resolutions, scene_pressures or joint_beats. `assert proposal.resolutions and proposal.scene_pressures and proposal.joint_beats` then fails as 'assert (())'. The test's claim depends on a real populated world: ranked resolutions, at least one scene pressure and one joint beat, plus per-actor place names that survive both commit paths, exposures, Backstage and the cognition trace. It then copies the anchor's chunk_metadata for its new chunk.
- Prerequisite: A populated story corpus equivalent to save_04: accepted chunks with chunk_metadata world_time, several characters with locations, needs, tags and relationships sufficient for BUILTIN_TEMPLATES to emit resolutions, scene pressures and a mutual joint beat.
- Repair steps:
  1. Mark the test corpus-bound: add a registered `requires_corpus` marker with an explicit opt-in (e.g. NEXUS_RUN_CORPUS=1) in tests/conftest.py and pytest.ini.
  1. Have the corpus fixture assert the source fingerprint (at least 1 accepted chunk with world_time, at least 2 characters; ideally the documented 46/49/23) and fail loudly when opted in but absent, instead of yielding an empty clone that surfaces as 'assert (())'.
  1. Longer term (#816): a seeded-world factory could replace the corpus. That is honest only if it is shared production-shaped data rather than rows tuned to make each template fire.

#### `tests/test_orrery/test_card_identity.py::test_card_exposure_rank_joint_and_backstage_parity[True]`

- Baseline outcome: failure; signature: `AssertionError: assert (())`
- Route: `gate_behind_corpus_flag` to #885; confidence 0.9
- Cause: Same as [False] (the asyncpg variant is not reached). The empty save_04 corpus clone gives anchor = max(narrative_chunks.id) = NULL, and resolve_dry_run yields no resolutions, pressures or joint beats. The first assertion fails as 'assert (())' before any commit path runs.
- Prerequisite: A populated save_04-equivalent corpus (see [False]).
- Repair steps:
  1. Same corpus marker, opt-in and fingerprint assertion as [False].

#### `tests/test_orrery/test_card_identity.py::test_ren_rank_commit_replay[False-False]`

- Baseline outcome: failure; signature: `nexus.agents.orrery.events.OrreryWorldClockUnavailableError: Orrery world clock unavailable: no primary world_time or base_timestamp`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.85; runtime confirmation needed
- Cause: The card_database fixture clones source_db='save_04' with include_data=True. It is a corpus probe by design: docs/qa/781-card-identity/verification.md records the save_04 corpus as 46 chunks, max id 49, 23 characters. In the isolated cluster save_04 is an empty template clone, so the disposable copy is empty. The test inserts an accepted narrative chunk without metadata. commit_orrery_tick_sync then falls back in _tick_world_time_sync (nexus/agents/orrery/events.py:5521-5550) to COALESCE(MAX(chunk_metadata.world_time), base_timestamp), which is NULL, and raises OrreryWorldClockUnavailableError. Two more gaps are masked behind the clock: the replayed receipt binds entity ids 6 (Ren Vale), 13 (Dr. Sera Vey) and 4 (Elian Rook), which _validate_entity_ids_sync would reject, and the final characters lookup would find no row. The test only replays JSON deltas from committed receipts (docs/qa/781-card-identity/live/after-draft.json). All three Ren cards change only character.current_activity.
- Prerequisite: global_variables.base_timestamp (or 1 chunk_metadata.world_time), plus active character entities with ids 4, 6 and 13 and characters rows named Elian Rook, Ren Vale and Dr. Sera Vey. Template seed vocab for event_types (contact_made, surveillance_performed, upkeep_done, intel_reviewed).
- Repair steps:
  1. Give this test its own fixture: disposable_slot_database('qa640_781_ren') from NEXUS_template (no include_data). Set base_timestamp (e.g. the receipt's 2189-10-17T22:37Z), insert entities with explicit ids 4/6/13 and kind 'character', then characters rows with the receipt names, then setval the entities sequence past 13. Pin the ids rather than remapping bindings, because proposal_id and binding_hash depend on them.
  1. Keep the sync/async x replacement parametrization unchanged. This is more honest than a corpus gate: the real commit path runs, and the DB only needs the bound actors to exist.

#### `tests/test_orrery/test_card_identity.py::test_ren_rank_commit_replay[False-True]`

- Baseline outcome: failure; signature: `nexus.agents.orrery.events.OrreryWorldClockUnavailableError: Orrery world clock unavailable: no primary world_time or base_timestamp`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.85; runtime confirmation needed
- Cause: Same as [False-False]. This is the sync writer with Gaia's replacement adjudication. The save_04 corpus clone is empty in the isolated cluster, so commit_orrery_tick_sync raises OrreryWorldClockUnavailableError from _tick_world_time_sync (no chunk world_time, no base_timestamp). Actors 4/6/13 from the receipt are also absent.
- Prerequisite: base_timestamp and character entities 4/6/13 with receipt names. The replacement event type intel_reviewed must be in event_types (template seed).
- Repair steps:
  1. Use the seeded Ren fixture described for [False-False].

#### `tests/test_orrery/test_card_identity.py::test_ren_rank_commit_replay[True-False]`

- Baseline outcome: failure; signature: `nexus.agents.orrery.events.OrreryWorldClockUnavailableError: Orrery world clock unavailable: no primary world_time or base_timestamp`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.85; runtime confirmation needed
- Cause: Same corpus dependency, through the asyncpg writer. commit_orrery_tick_async reaches _tick_world_time_async (events.py:5553-5579), which raises OrreryWorldClockUnavailableError because the empty save_04 clone has no chunk world_time or base_timestamp. The bound actors 4/6/13 are also absent.
- Prerequisite: base_timestamp and character entities 4/6/13 with receipt names.
- Repair steps:
  1. Use the seeded Ren fixture described for [False-False]. asyncpg_kwargs(dbname) already targets the clone.

#### `tests/test_orrery/test_card_identity.py::test_ren_rank_commit_replay[True-True]`

- Baseline outcome: failure; signature: `nexus.agents.orrery.events.OrreryWorldClockUnavailableError: Orrery world clock unavailable: no primary world_time or base_timestamp`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.85; runtime confirmation needed
- Cause: This is the async writer with the replacement adjudication. The empty save_04 corpus clone makes _tick_world_time_async raise OrreryWorldClockUnavailableError, and the receipt's bound actors are absent.
- Prerequisite: base_timestamp, character entities 4/6/13 with receipt names, and event_types seed.
- Repair steps:
  1. Use the seeded Ren fixture described for [False-False].

#### `tests/test_orrery/test_communication_graph_live.py::test_conflicted_live_pair_licenses_only_each_tellers_own_direction`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.InternalError: (psycopg2.errors.RaiseException) need-clock anchor unavailable: no canonical world time or base_timestamp`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.85; runtime confirmation needed
- Cause: The recorded ERROR comes from communication_db setup: the characters INSERT raises the need-clock anchor on the empty private save_05. Underneath, this node is a frozen-corpus probe. It ignores every fixture row, reads the characters named 'Tomi' and 'Kosi' from save_05, and calls pytest.skip('save_05 does not contain the frozen Tomi/Kosi pair') when they are absent. Even after a fixture repair it would skip on any disposable clone, and also on the owner's save_05, which #922 recorded as (0 chunks, 0 characters). The assertion itself is pure config semantics from nexus.agents.orrery.communication._dyad_edges_from_rows: Tomi->Kosi is a 'ward' row with trusting valence and therefore gets the dyad tier 24h, while Kosi->Tomi is a sparse 'captor' row, so the override forward='never' applies and no edge is produced. Both are reproducible with synthetic rows.
- Prerequisite: Two active characters A and B; a character_relationships row A->B with relationship_type 'ward' and a trusting valence (e.g. '+3|trusting', the value retrograde_vocabulary uses for ward); a row B->A with type 'captor' and any valence, with no matching B->A 'ward' or A->B 'captor' row, so the captor row is sparse and takes the forward direction; nexus.toml dyad_overrides captor forward='never'. The fixture already supplies the story clock.
- Repair steps:
  1. After the file-level fixture repair, rewrite the body to seed the pair through the fixture's _insert_relationship (manual producer): A->B 'ward' '+3|trusting' and B->A 'captor' '-3|resentful'. Assert _between(graph, A, B, 'dyad') == [('ward', 24h)] and _between(graph, B, A, 'dyad') == (). Remove the pytest.skip.
  1. Seeding is the more honest route here. The assertion tests override semantics, not corpus content, and the frozen pair no longer exists in any known slot, so a corpus-gated version would skip permanently. If the owner still wants a corpus regression, add it as a separate test behind an explicit corpus flag naming the slot that actually contains Tomi and Kosi.

#### `tests/test_orrery/test_court_patron_async.py::test_async_court_patron_three_write_completion`

- Baseline outcome: failure; signature: `ValueError: not enough values to unpack (expected 2, got 0)`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The test connects to the hardcoded 'save_02' via asyncpg_kwargs('save_02'). Inside a rolled-back transaction with write_producer='manual' it builds the shadow schema plus migration 086, then unpacks `actor, target = (int(row['entity_id']) for row in entities)` from 'SELECT entity_id FROM characters ... LIMIT 2'. The empty private save_02 returns no rows, giving ValueError: not enough values to unpack (expected 2, got 0). It also needs a chunk with world_time (int(fetchval) would fail next). It writes public character_relationships and entity_pair_tags using the template's 'sponsors'/'obligation' pair tags. #922 had passed this on the owner's populated save_02.
- Prerequisite: Two characters rows with entity_ids. One chunk_metadata row with non-null world_time. Template pair_tags containing 'sponsors' and 'obligation'. base_timestamp set before the character inserts.
- Repair steps:
  1. Use tests.pg_fixtures.disposable_slot_database('qa_court_patron_async') plus pg_fixtures.asyncpg_kwargs(dbname) instead of 'save_02'.
  1. Seed seed_protagonist(dbname) plus a second character/entity (INSERT entities kind 'character', then characters with that entity_id, after base_timestamp is set) and one timed chunk.
  1. Keep the SET LOCAL nexus.write_producer='manual' and the shadow schema.

#### `tests/test_orrery/test_court_patron_projects.py::test_completion_applies_inbound_outbound_and_patron_relationship`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Fixture `live_patron_db` connects to save_02 (get_slot_db_url(slot=2)). `_create_schema` sets write_producer='manual' and builds the shadow tables plus migration 086. The fixture then unpacks `actor, target = (int(row[0]) for row in cur.fetchall())` from 'SELECT entity_id FROM characters ... LIMIT 2'. On the empty private save_02 that raises ValueError: not enough values to unpack (expected 2, got 0) during setup. It then needs a chunk with world_time (int(fetchone()[0])). #922 had fixed this file's write_producer omission (verification.md:351); what remains is the owner-slot content dependency.
- Prerequisite: Two characters with entity_ids. One chunk_metadata row with world_time. Template pair_tags 'sponsors' and 'obligation'. base_timestamp set before the character inserts.
- Repair steps:
  1. Apply the shared fixture repair in file_notes: a disposable clone seeded with two characters and one timed chunk.

#### `tests/test_orrery/test_court_patron_projects.py::test_completion_preserves_existing_relationship_valence`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Same `live_patron_db` setup failure: there are no characters in the empty private save_02, so the 2-tuple unpack raises ValueError. The body's direct INSERT INTO character_relationships relies on the write_producer='manual' that _create_schema set, which survives because relationship_producer restores the previous value.
- Prerequisite: Two characters with entity_ids and no pre-existing relationship between them. One chunk with world_time. Template pair tags.
- Repair steps:
  1. Apply the shared fixture repair in file_notes.

#### `tests/test_orrery/test_court_patron_replay.py::test_court_patron_completion_replays_without_drift`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The test imports the `live_patron_db` fixture from test_court_patron_projects via pytest_plugins, so it errors in the same setup: zero characters on the empty private save_02, giving the 2-tuple unpack ValueError. The body also borrows `_fabricate_chunk` from test_pursue_romance_replay, which inserts narrative_chunks with max(id)+1 and would yield a NULL id on a chunk-less table. It drops the shadow orrery_resolutions to use the public ledger, captures two checkpoints, and asserts verify_checkpoints_sync reports no drift for the pair.
- Prerequisite: The live_patron_db prerequisites (two characters with entities, one timed chunk, which also satisfies the max(id)+1 idiom), template pair_tags 'sponsors'/'obligation', and the public orrery_resolutions and state-checkpoint tables from the template.
- Repair steps:
  1. No separate fixture change: it is fixed by the shared live_patron_db repair in test_court_patron_projects.py.
  1. Change test_pursue_romance_replay._fabricate_chunk to use sequence-assigned ids rather than max(id)+1.

#### `tests/test_orrery/test_drift_live.py::test_colocated_characters_without_events_produce_no_versions`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The module fixture clones save_03 with include_data=True. In the private cluster save_03 was an empty template clone, so the clone has no places. _seed_tick succeeds because it creates its own chunks, characters, edge and event, which is why the file's other seven tests passed. This test then runs 'SELECT id FROM places ORDER BY id LIMIT 1' and `cur.fetchone()['id']`. That is the only subscript that can see None after the DELETE, and it raised TypeError: 'NoneType' object is not subscriptable. The test just needs any place for the two characters to share. It never needed save_03's corpus, and cloning the owner's save_03 is an unnecessary owner-save dependency.
- Prerequisite: One places row (for example type 'fixed_location') in the test transaction. Everything else is self-seeded by _seed_tick. A world clock is not required, because the chunk refresh trigger falls back to now() and the need anchor uses MAX(world_time).
- Repair steps:
  1. In the test, replace the arbitrary place lookup with an inserted place: INSERT INTO places (name, type) VALUES ('Drift Fixture Plaza', 'fixed_location') RETURNING id (the idiom in tests/test_presence_roster_pg.py:56).
  1. Switch the module fixture to a template clone (disposable_slot_database('qa640_drift') with default source_db and include_data=False), since no test in the file needs save_03 content.

#### `tests/test_orrery/test_ecology_live.py::test_outbound_pair_tag_and_detection_gate_live`

- Baseline outcome: failure; signature: `assert 0 == 2`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: The test opens a hand-built psycopg2 connection to save_02 (LIVE_SLOT=2) and selects the two lowest-entity_id characters. The empty private save_02 has none, so 'assert len(rows) == 2' fails with 'assert 0 == 2'. It later needs a third 'rival' character and an anchor chunk (int(max(id)) would raise TypeError on an empty slot). On the owner's machine it commits real Orrery writes to save_02, and its finally-block does not undo them all: commit_orrery_tick_sync runs 'UPDATE characters SET current_activity' for the actor (nexus/agents/orrery/events.py:2196), which is never restored, so the test permanently mutates owner data.
- Prerequisite: World clock (base_timestamp) set before characters are inserted, because the need-clock trigger raises 'need-clock anchor unavailable' otherwise. Three characters with entity rows, one narrative chunk with chunk_metadata world_time as the tick anchor, and the 'hunting' pair_tag from template vocab.
- Repair steps:
  1. Use disposable_slot_database plus seed_protagonist (which sets base_timestamp), insert three non-player characters with entities and one anchor chunk with a world_time, and connect with tests.pg_fixtures.connect(clone).
  1. Remove the manual cleanup, since the clone is dropped, and never write to save_02.

#### `tests/test_orrery/test_epistemics.py::test_async_live_applier_has_epistemics_parity`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The test opens its own asyncpg connection with hand-built kwargs (database='save_02', PGHOST/PGPORT read from the environment). It bypasses both the save_02_conn fixture and the tests.pg_fixtures.asyncpg_kwargs / nexus.database.asyncpg_kwargs connection contract. The connection reached the private cluster through PGPORT. `int(await conn.fetchval('SELECT max(id) FROM narrative_chunks'))` then raised int(None) because the slot is empty. After that it unpacks two character entity ids, which would raise ValueError with fewer than two, and compares awareness world time with chunk_metadata.world_time. The hard-coded database literal is a #804 connection-contract smell, but it is not what failed here.
- Prerequisite: An anchor chunk with chunk_metadata world_time, and two active character entities, in a database the test is given rather than the literal 'save_02'.
- Repair steps:
  1. Take dbname from the seeded clone fixture and connect with `asyncpg.connect(**tests.pg_fixtures.asyncpg_kwargs(dbname))`, which also removes the hand-built database='save_02' connection (#804 contract).
  1. Use the fixture's anchor and character entity ids instead of max(id) and `LIMIT 2`.

#### `tests/test_orrery/test_epistemics.py::test_kill_switch_disables_real_retrograde_and_live_producers`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The claims and awareness counts before the run succeed (0 rows in the shadow). _anchor_and_characters(cur, 2) then raises int(None) on the empty slot 2. The disabled-policy retrograde and live producer legs need an anchor and two named character entities.
- Prerequisite: An anchor chunk with chunk_metadata world_time, and two active character entities with names.
- Repair steps:
  1. Use the seeded clone fixture's anchor and character ids and names.

#### `tests/test_orrery/test_epistemics.py::test_live_applier_mints_and_ledgers_epistemics_ids`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: _anchor_and_characters(cur, 2) raises int(None) on the empty slot 2. The test then calls commit_orrery_tick_sync on the same transaction with tick_chunk_id=anchor. That call runs `UPDATE narrative_chunks SET orrery_proposal` on the anchor, inserts orrery_resolutions that reference the tick chunk, and mints claim_awareness at the anchor's world_time. It needs a real chunk row and two character entities. commit_orrery_tick_sync does not commit, so rollback isolation holds.
- Prerequisite: An anchor narrative_chunks row with chunk_metadata world_time, and two active character entities.
- Repair steps:
  1. Use the seeded clone fixture. Pass its anchor and character entity ids into the OrreryTickProposal. slot=2 in commit_orrery_tick_sync is unused and can stay or go.

#### `tests/test_orrery/test_epistemics.py::test_pydantic_epistemics_settings_coerce_and_drive_live_producer`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The pure policy coercion asserts pass. The test then calls _anchor_and_characters(cur, 2) on slot 2, which raises int(None) on an empty narrative_chunks table. The live producer leg needs the same anchor and two entities as the sync applier test.
- Prerequisite: An anchor chunk with chunk_metadata world_time, and two active character entities.
- Repair steps:
  1. Use the seeded clone fixture's anchor and character entity ids.

#### `tests/test_orrery/test_epistemics.py::test_record_revelation_cli_handler_reports_insert_and_dedupe`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: _anchor_and_characters(cur, 3) raises int(None) on the empty slot 2. The test then asserts `max(world_time) FROM chunk_metadata` is not None, because run_record_revelation resolves the grant time through current_world_time_sync, which reads the same max. It needs a clocked chunk_metadata row as well as three character entities. `--slot 2` is only parsed for reporting: the handler uses the injected connection, so a disposable dbname works. The returned 'dbname' will say save_02 even though the connection is a clone. That is harmless because the test does not assert on it.
- Prerequisite: An anchor chunk whose chunk_metadata.world_time is non-NULL (derived from global_variables.base_timestamp by trg_chunk_metadata_refresh_world_time), and three active character entities.
- Repair steps:
  1. Use the seeded clone fixture, which must set base_timestamp before inserting chunk_metadata so that world_time is deterministic, and pass its connection as `connection=`.
  1. Keep `--slot 2` for argparse, or assert only on the fields that matter.

#### `tests/test_orrery/test_epistemics.py::test_resolver_hydrates_scopes_and_awareness_in_recent_window`

- Baseline outcome: failure; signature: `assert None is not None`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: The test opens a SQLAlchemy engine on get_slot_db_url(slot=2), installs the claim shadow and reads `SELECT max(id) FROM narrative_chunks`. Its own guard `assert anchor_value is not None` fails on the empty slot. After that it unpacks two character entity ids (ValueError with fewer than two), inserts a world_event, claim and awareness row at the anchor, and hydrates the world state with window_chunks=1.
- Prerequisite: An anchor chunk (world_time optional, since load_anchor_world_time tolerates None) and two active character entities.
- Repair steps:
  1. Build the engine with create_engine(tests.pg_fixtures.sqlalchemy_url(dbname)) from the seeded clone fixture, keeping the begin/rollback wrapper.
  1. Use the fixture's anchor and character entity ids.

#### `tests/test_orrery/test_epistemics.py::test_retrograde_already_present_event_backfills_claim`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: _anchor_and_characters(cur, 2) raises int(None) because the empty slot 2 has no narrative_chunks. The idempotent backfill contract (insert with DISABLED, then backfill with EPISTEMICS) only needs an anchor and two named characters.
- Prerequisite: An anchor chunk (chunk_metadata world_time recommended) and two characters with active entities and names.
- Repair steps:
  1. Use the seeded clone fixture and its seeded character ids and names.

#### `tests/test_orrery/test_epistemics.py::test_retrograde_faction_actor_mints_faction_awareness`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: _anchor_and_characters(cur, 2) raises int(None) on the empty slot-2 narrative_chunks. Two more content assumptions are downstream. The test asserts that save_02 has a faction with an entity_id and an entity_names_v name. It also compares claim_awareness.acquired_at_world_time with chunk_metadata.world_time of the anchor. With no chunk_metadata row, `cur.fetchone()['world_time']` would itself raise TypeError on None.
- Prerequisite: An anchor chunk with a chunk_metadata row whose world_time is non-NULL. Two characters with active entities. One factions row (factions.id given explicitly, as other clone tests do) whose entity_id points at an active 'faction' entity with a name.
- Repair steps:
  1. Use the seeded clone fixture, which includes one faction and chunk_metadata derived from base_timestamp.
  1. Read the faction id, entity id and name from the fixture instead of `SELECT ... FROM factions ... LIMIT 1`, and drop the save_02 assertion message.

#### `tests/test_orrery/test_epistemics.py::test_retrograde_producer_mints_role_correct_awareness`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: Same fixture as the rest of the file: save_02_conn on slot 2, where _anchor_and_characters(cur, 4) hits int(None) on max(narrative_chunks.id) in the empty slot. The test then needs four named character entities to build a retrograde plan (actor/target/witness/beneficiary) and passes the anchor as prologue_chunk_id to _plan_event_row. The event types threat_issued and surveillance_performed come from the template's event_types seed vocab.
- Prerequisite: An anchor chunk and four characters with active entities and distinct names. The event_types seed rows for threat_issued and surveillance_performed come from the template.
- Repair steps:
  1. Use the seeded clone fixture (4 non-player characters) from file_notes.
  1. Build the _EntityRecord list from the fixture's seeded character ids and names rather than the first four characters ordered by id.

#### `tests/test_orrery/test_epistemics.py::test_revelation_scope_and_common_semantics`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: _anchor_and_characters(cur, 4) raises int(None) on slot 2's empty narrative_chunks. The test then needs four distinct character entities (source, knower, target, unpossessed) to exercise promote_claim_scope and the record_revelation told-chain. It supplies its own world_time, so it needs no chunk clock.
- Prerequisite: An anchor chunk and four active character entities.
- Repair steps:
  1. Use the seeded clone fixture's anchor and four non-player character entity ids.

#### `tests/test_orrery/test_epistemics.py::test_two_similar_actors_are_separated_only_by_awareness`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: The module fixture save_02_conn connects to get_slot_db_url(slot=2), which is the owner's populated save_02 (the private empty save_02 in the baseline run). _anchor_and_characters runs `SELECT max(id) AS id FROM narrative_chunks` and calls int() on the result. The slot has no chunks, so max() is NULL and int(None) raises TypeError before any Epistemics code runs. The test's contract (awareness gating in SURVEIL.package_gate) does not depend on corpus facts: it borrows 'any chunk' as the anchor and 'the first 3 characters with entities'. The sibling node test_retrograde_claim_mint_skips_events_without_resolved_participants passed on the same connection. That shows the connection and install_claim_accounts_shadow_sync work, so the only cause is missing content. None of the test_epistemics nodes appear in the #922 failure tables, so they were green on the owner's populated save_02.
- Prerequisite: One narrative_chunks row to use as the anchor, and three characters whose entity_id points at an active 'character' entity (names resolved through entity_names_v). global_variables.base_timestamp, or a chunk world_time, must exist before the character inserts, because trg_characters_need_state_init raises 'need-clock anchor unavailable' otherwise.
- Repair steps:
  1. Replace save_02_conn with the file-level seeded clone fixture described in file_notes (a connection to the disposable dbname, plus the claim shadow).
  1. Take the anchor and character entity ids from the fixture's returned ids instead of max(id) and `ORDER BY c.id LIMIT 3`.

#### `tests/test_orrery/test_epistemics.py::test_unclaimed_event_is_implicitly_common_with_epistemics_enabled`

- Baseline outcome: failure; signature: `assert None is not None`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Same SQLAlchemy slot-2 pattern: `assert anchor_value is not None` fails because narrative_chunks is empty. Next the test requires `len(actor_ids) == 4` from `characters WHERE entity_id IS NOT NULL LIMIT 4`, inserts one unclaimed threat_issued event at the anchor and hydrates it.
- Prerequisite: An anchor chunk and four active character entities.
- Repair steps:
  1. Use sqlalchemy_url(dbname) from the seeded clone fixture (4 non-player characters) and the fixture's ids.

#### `tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end`

- Baseline outcome: failure; signature: `AssertionError: save_05 is expected to bind off-screen actors`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: The test calls explain_dry_run on LIVE_SLOT=5 through get_slot_db_url(slot=5) with anchor_chunk_id=None (test_evidence.py:428-470). With a None anchor, compose_actor_bindings (nexus/agents/orrery/resolver.py:1286-1410) finds off-screen actors only from three sources: character entities with active ephemeral entity_tags, inbound ephemeral 'hunting' pair tags, and character_routine_anchors rows with mobility_policy not in ('none','nomadic'). The chunk-window and world_events sources require an anchor. The empty private save_05 has none of these, so payload['actors'] is [] and the test fails its first assertion, 'save_05 is expected to bind off-screen actors'. Hydration itself tolerated the empty slot.
- Prerequisite: global_variables.base_timestamp (from seed_protagonist), and at least two non-player character entities that are not present at the head chunk. Each needs a character_routine_anchors row (anchor_type 'home', mobility_policy 'fixed_place', place_id pointing at a seeded place with its entity) or an active ephemeral entity_tags row, so the actor-only stacks (24 of 46 BUILTIN_TEMPLATES) produce more than 100 gate-trace leaves. The leaf count per actor needs a runtime check.
- Repair steps:
  1. Replace get_slot_db_url(slot=LIVE_SLOT) with create_engine(tests.pg_fixtures.sqlalchemy_url(dbname)) on a disposable_slot_database('evidence_explain') clone.
  1. Seed seed_protagonist, then two or more extra characters with entities and one place (layers, zones and places, as in tests/test_orrery/test_need_absence_pg.py). Insert character_routine_anchors rows for the extra characters, or active ephemeral entity_tags drawn from the vocab tags table.
  1. Keep the evidence-integrity loop. Either keep 'checked > 100' after confirming the seeded actors reach it, or derive the threshold from the number of actor-only templates times the number of seeded actors. The property under test (evidence survives to_dict/JSON with result parity) does not depend on the corpus, so a seeded clone is the honest gate. A save_05 corpus variant, if still wanted, belongs behind the corpus flag.

#### `tests/test_orrery/test_faction_project_contexts_live.py::test_live_accepted_entry_persists_and_advances_stored_faction`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The faction_context_db fixture targets LIVE_SLOT=5, which is empty even on the owner's machine: #922 recorded save_05 as (0 chunks, 0 characters) and left this file in the #885 class-a remainder. The fixture re-applies migration 081 successfully, then runs `SELECT id FROM places ORDER BY id LIMIT 1` with .scalar_one(), which raises NoResultFound. Three more assumptions sit behind that line. `int(max(narrative_chunks.id))` would raise int(None). The character inserts need a clock for trg_characters_need_state_init ('need-clock anchor unavailable'). With fewer than two active faction entities the fixture calls pytest.skip, so the test silently skips instead of failing. This node also needs anchor chunk world_time for the project.start next_eligible computation.
- Prerequisite: global_variables.base_timestamp set, one places row, one accepted narrative chunk with chunk_metadata world_time (the anchor), and two factions rows linked to active 'faction' entities. The template's pair_tags seed must include 'obligation'. The fixture already inserts its own four characters, routine anchors, pair tags and relationships.
- Repair steps:
  1. Apply the file-level seeded clone repair in file_notes.
  1. No per-node change is needed beyond reading chunk_id and faction ids from the seeded fixture.

#### `tests/test_orrery/test_faction_project_contexts_live.py::test_live_actor_only_continuation_preserves_stored_faction`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Same fixture error: NoResultFound on `SELECT id FROM places ... scalar_one()` in the empty slot 5, with the chunk, clock and faction assumptions behind it. The body needs the bound actor to compose, through its routine anchor, into START_FACTION_PROJECT and then into actor-only ADVANCE and STALL drafts at the anchor chunk.
- Prerequisite: Same as the file: base_timestamp, a place, a clocked anchor chunk, and two active faction entities.
- Repair steps:
  1. Apply the file-level seeded clone repair.

#### `tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_enumeration_is_truthful_distinct_and_ordered`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The fixture's places lookup raises NoResultFound in the empty slot 5. The body asserts that compose_actor_faction_bindings returns exactly the two fixture factions, sorted, bound through the fixture's 'obligation' pair tags. This needs two active faction entities in the slot, which the fixture currently skips on instead of seeding.
- Prerequisite: Two active faction entities with factions rows, an anchor chunk, and a place. The seed pair_tags 'obligation' row comes from the template.
- Repair steps:
  1. Apply the file-level repair. Seed exactly two factions so the sorted equality is deterministic.

#### `tests/test_orrery/test_faction_project_contexts_live.py::test_live_faction_rebinding_raises_loudly`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: The fixture raises NoResultFound on the places lookup in the empty slot 5. There is also a latent test-side problem that seeding alone will not expose. The final assertion compares the column comment on character_project_states.target_faction_entity_id with migration 081's text. That holds only because the fixture re-executes 081 inside the transaction. The canonical schema, and so the template, carries migration 096's later comment ('Immutable faction target for faction-bound projects; COURT_PATRON sets this exactly when target_character_entity_id is NULL.'). The assertion is therefore self-fulfilling and stale. If the vestigial 081 re-application is removed, which is right now that the template is fully stamped, this assertion fails.
- Prerequisite: Same as the file (base_timestamp, a place, a clocked anchor chunk, two active faction entities), plus a comment assertion that matches the current schema.
- Repair steps:
  1. Apply the file-level seeded clone repair.
  1. When the in-fixture 081 execution is dropped, update the expected comment to migration 096's text, or assert only on the 'immutable' substring. The trigger check via psycopg2.errors.RaiseException keeps working because the trigger function comes from the template.

#### `tests/test_orrery/test_faction_project_contexts_live.py::test_live_gating_only_faction_template_leaves_binding_untouched`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The fixture raises NoResultFound on the places lookup in the empty slot 5. The body starts a faction-bound project and then runs a gating-only faction template, which needs the same anchor, clock and two-faction content.
- Prerequisite: Same as the file: base_timestamp, a place, a clocked anchor chunk, and two active faction entities.
- Repair steps:
  1. Apply the file-level seeded clone repair.

#### `tests/test_orrery/test_faction_project_contexts_live.py::test_live_production_and_explain_compose_same_faction_bindings`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: The fixture raises NoResultFound on the places lookup in the empty slot 5. The body asserts parity between resolve_dry_run and explain_dry_run, with exactly one arbitrated start and one trimmed start for the bound actor across the two factions. That needs the seeded two-faction content and composes over the whole slot. A clean clone makes it more deterministic than a populated native slot would.
- Prerequisite: Same as the file: base_timestamp, a place, a clocked anchor chunk, and exactly two active faction entities.
- Repair steps:
  1. Apply the file-level seeded clone repair.

#### `tests/test_orrery/test_faction_project_contexts_live.py::test_live_target_faction_product_is_bounded_and_deterministic`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The fixture raises NoResultFound on the places lookup in the empty slot 5. The body expects the product of the fixture's two relationship targets and two factions, and a fanout cap of 2 drafts that is identical across calls. The two factions are the only slot content it needs beyond the anchor and clock.
- Prerequisite: Same as the file: base_timestamp, a place, a clocked anchor chunk, and two active faction entities.
- Repair steps:
  1. Apply the file-level seeded clone repair.

#### `tests/test_orrery/test_faction_project_contexts_live.py::test_live_zero_edge_actor_keeps_actor_and_target_composition`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The fixture raises NoResultFound on the places lookup in the empty slot 5. The body relies on the zero-edge actor being composed through its routine anchor at the fixture place, and on one fixture relationship to target_a. Only the place, anchor chunk and clock come from the slot.
- Prerequisite: base_timestamp, a place, and a clocked anchor chunk. The fixture must still reach its own inserts, which currently happen only after the faction check passes, so two faction entities are needed as well.
- Repair steps:
  1. Apply the file-level seeded clone repair.

#### `tests/test_orrery/test_playable_narrative_boundary.py::test_legacy_accept_embeds_the_previous_playable_chunk`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.92; runtime confirmation needed
- Cause: The test already uses a disposable clone, but a corpus clone: disposable_slot_database(source_db='save_04', include_data=True). It assumes save_04 contains a Retrograde prologue row (authorial_directives containing 'orrery:retrograde_prologue_anchor') and chunk ids 7, 8 and 9. In the baseline, save_04 was an empty private template clone. `SELECT authorial_directives ... @> [marker] LIMIT 1` returned no row, and `cur.fetchone()[0]` raised TypeError: 'NoneType' object is not subscriptable. The corpus dependency is incidental. The test copies the prologue directives from any prologue row onto id 8 and rewrites the state of 7 and 9 itself. The contract (ChunkWorkflow.accept_chunk enqueues an embedding for the previous playable chunk and skips the synthetic prologue) needs only three rows. accept_chunk and enqueue_embedding are simple SQL with no other slot dependencies.
- Prerequisite: Three narrative_chunks rows in id order: a playable finalized chunk with embedding_generated_at NULL and authorial_directives '[]', a synthetic prologue whose authorial_directives equals json.dumps([RETROGRADE_PROLOGUE_MARKER]), and a pending_review chunk to accept. narrative_embedding_jobs must be empty.
- Repair steps:
  1. Switch to a template clone: disposable_slot_database('qa964_boundary') with no source_db or include_data.
  1. Insert a playable finalized chunk A with embedding_generated_at NULL. Create the prologue through the production helper nexus.agents.orrery.retrograde_persistence._insert_prologue_chunk(cur). Insert a pending_review chunk B. Capture the returned ids in place of the hard-coded 7, 8 and 9.
  1. Assert that accept_chunk(B) yields exactly one queued narrative_embedding_jobs row for A. Seeding is more honest than gate_behind_corpus_flag because nothing in the contract depends on the save_04 story.

#### `tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle`

- Baseline outcome: error; signature: `failed on setup with "sqlalchemy.exc.NoResultFound: No row was found when one was required"`
- Route: `seed_disposable_clone` to #885; confidence 0.87; runtime confirmation needed
- Cause: The patron_circle_db fixture connects to get_slot_db_url(slot=5). That slot is empty even on the owner's machine; #922 left this node in the #885 class-a remainder. The fixture re-applies migration 096 (harmless, since 096 is the latest definition of those constraints), inserts its own two character entities and one faction entity, then runs `SELECT id FROM places ORDER BY id LIMIT 1` with .scalar_one(), which raises NoResultFound. Two more failures would follow a place-only fix. `INSERT INTO characters` with entity_id fires trg_characters_need_state_init, which raises 'need-clock anchor unavailable' when there is neither a chunk world_time nor global_variables.base_timestamp. `SELECT chunk_id FROM chunk_metadata WHERE world_time IS NOT NULL ... scalar_one()` raises NoResultFound again. Everything else (characters, relationship, routine anchor, 'status:senior' pair tag) is fixture-authored.
- Prerequisite: global_variables.base_timestamp set before the character inserts, one places row, and one narrative chunk with chunk_metadata world_time (the tick chunk). The template's pair_tags seed must include the status:senior, status:respected and status:junior rows.
- Repair steps:
  1. Wrap the fixture in disposable_slot_database('qa964_polymorphic_patron').
  1. Before opening the SQLAlchemy engine on sqlalchemy_url(dbname), call seed_protagonist(dbname) for the clock, insert one place with an entity, and insert one accepted chunk plus chunk_metadata (world_time derived from base_timestamp). Return the place id and chunk id from the seeding step instead of selecting them.
  1. Drop the in-fixture execution of migrations/096_polymorphic_patron.sql, since the template is stamped with it (#810 ownership).

#### `tests/test_orrery/test_projects.py::test_resolution_insert_skips_routine_promotion_but_queues_milestone`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.95
- Cause: The test opens psycopg2.connect(get_slot_db_url(slot=2)) (test_projects.py:522-569), reads 'SELECT max(id) FROM narrative_chunks', which gives chunk_id=None on the empty slot, then reads 'SELECT entity_id FROM characters WHERE entity_id IS NOT NULL ORDER BY id LIMIT 1'. That returns no row, so cur.fetchone()[0] raises TypeError: 'NoneType' object is not subscriptable. _insert_resolution_sync was never called.
- Prerequisite: One narrative_chunks row (FK target for orrery_resolutions.tick_chunk_id) and one character with a non-null entity_id. No world clock is needed: _insert_resolution_sync is a plain INSERT ... ON CONFLICT DO NOTHING with no triggers on orrery_resolutions.
- Repair steps:
  1. Use disposable_slot_database('project_promotion') with tests.pg_fixtures.connect(dbname).
  1. Seed seed_protagonist(dbname) for the actor entity, and insert one narrative_chunks row for tick_chunk_id. Use the returned ids directly instead of the max(id) and characters lookups.
  1. Keep the rollback. The statuses assertion ({'routine': 'skipped', 'milestone': 'pending'}) is independent of the corpus.

#### `tests/test_orrery/test_projects.py::test_slot2_coverage_distribution_and_project_gate_payload`

- Baseline outcome: failure; signature: `AssertionError: save_02 must provide coverage anchors`
- Route: `gate_behind_corpus_flag` to #885; confidence 0.95
- Cause: This is a corpus-bound pilot probe (test_projects.py:572-722). On a rolled-back SQLAlchemy connection to get_slot_db_url(slot=2), it replays migrations/074_plan_relocation_projects.sql, then calls sample_anchor_ids(count=35, stride=1). sample_anchor_ids (nexus/agents/orrery/coverage.py:94-135) selects playable narrative chunks. The empty private save_02 has none, so anchors == [] and the first assertion, 'save_02 must provide coverage anchors', fails. The later assertions are corpus statistics: the pilot anchors must contain 'surveil' winners, advance_relocation_plan must displace surveillance, and routine-template winner shares must shift by less than coverage_distribution_tolerance. They depend on save_02's authored story.
- Prerequisite: A corpus with at least 35 playable chunks whose chunk_metadata world_time is set, where the coverage analysis produces 'surveil' resolution winners for an actor and embodied or anchored routine templates win often enough for the share comparison to mean something. In practice this is save_02's corpus.
- Repair steps:
  1. Mark the test with a new requires_corpus marker (none exists in tests/conftest.py yet) and run it against disposable_slot_database('project_coverage', source_db='save_02', include_data=True) rather than the live slot.
  1. Drop the in-test replay of migrations/074_plan_relocation_projects.sql. Migration 074 is already applied to the template and to migrated corpus clones, and replaying migration DDL inside a test is a latent drift hazard.
  1. Gating is more honest than seeding here. A synthetic 35-chunk story engineered so that 'surveil' wins would turn the distribution-tolerance check into a tautology about the fixture. The non-corpus parts (project_due evidence, promotability) are already covered by the pure-substrate tests in this file.

#### `tests/test_orrery/test_pursue_romance_async.py::test_async_pursue_romance_start_and_completion`

- Baseline outcome: failure; signature: `ValueError: not enough values to unpack (expected 2, got 0)`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: The test connects with asyncpg.connect(**nexus.database.asyncpg_kwargs('save_02')), a literal owner slot. The get_slot_db_url import is unused. It builds a pre-085 shadow schema for event_types, orrery_resolutions and character_project_states and runs migration 085 into it. It then reads `SELECT entity_id FROM characters WHERE entity_id IS NOT NULL ORDER BY id LIMIT 2` from the real public tables. The private save_02 has no characters, so `actor, target = (...)` raised 'not enough values to unpack (expected 2, got 0)'. The next line, `int(fetchval(chunk_id with world_time))`, would raise int(None) for the same reason. #922 fixed this test's asyncpg adapter and it then passed against the populated save_02, so content is the only remaining cause.
- Prerequisite: Two characters with active entity rows, one narrative chunk whose chunk_metadata.world_time is non-NULL, and the template pair_tags seed containing 'contact:intimate'. character_relationships between the two may be empty; the test deletes any it finds.
- Repair steps:
  1. Run the test inside disposable_slot_database('qa964_pursue_romance'). Seed with seed_protagonist (clock), two non-player characters with entities, and one accepted chunk with chunk_metadata. Connect with tests.pg_fixtures.asyncpg_kwargs(dbname).
  1. Use the seeded actor, target and chunk ids instead of the `LIMIT 2` and latest-clocked-chunk queries.
  1. Drop the unused get_slot_db_url import.

#### `tests/test_orrery/test_pursue_romance_projects.py::test_sync_applier_fresh_romance_and_overwrite_preserve_first_provenance`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: The live_romance_db fixture connects with psycopg2.connect(get_slot_db_url(slot=2)) and builds the same pre-085 shadow schema plus migration 085. It then reads the first two characters with entity_id from public.characters. The private save_02 is empty, so `actor, target = (...)` raised 'not enough values to unpack (expected 2, got 0)' during setup. The following `int(cur.fetchone()[0])` for the latest clocked chunk would raise TypeError next. #922 fixed the missing nexus.write_producer on this test's relationship writes, and it then passed on the populated save_02.
- Prerequisite: Two characters with active entity rows, one narrative chunk with chunk_metadata.world_time non-NULL, and the template pair_tags seed containing 'contact:intimate'.
- Repair steps:
  1. Have live_romance_db wrap disposable_slot_database('qa964_pursue_romance_sync'), seed it the same way as the async twin, connect(dbname), and yield the seeded ids.
  1. Consider sharing _create_schema and the seeding fixture with test_pursue_romance_async.py; the two files carry duplicate copies.

#### `tests/test_orrery/test_reconstruction.py::test_checkpoint_captures_every_section_and_is_idempotent`

- Baseline outcome: failure; signature: `AssertionError: save_05 must carry active tags`
- Route: `seed_disposable_clone` to #885; confidence 0.95; runtime confirmation needed
- Cause: The module _connect() (test_reconstruction.py:41-51) hardwires database=save_05, replays migrations/074 and creates a TEMP TABLE backstory_secrets that shadows the real table. On the empty private save_05, max(id) FROM narrative_chunks is None, and capture_state_checkpoint_sync(chunk_id=None, label='manual') succeeds: state_checkpoints.chunk_id is nullable by design for empty slots. The section-set assertion passes, but 'SELECT count(*) FROM entity_tags WHERE cleared_at IS NULL' returns 0, so 'save_05 must carry active tags' fails. The later 'characters must be captured' check would also fail on an empty slot.
- Prerequisite: One narrative_chunks row (so chunk_id is non-null and the (chunk_id, label) idempotency check is meaningful), at least one characters row with its entity, and at least one active entity_tags row on a character entity using a vocab tag from the template's tags table. Adding a character entity tag can fire need-applicability sync (orrery_sync_character_need_states), which raises 'need-clock anchor unavailable' unless chunk_metadata world_time or global_variables.base_timestamp exists. So base_timestamp is required too; seed_protagonist sets it.
- Repair steps:
  1. Apply the file-level fixture: a module-scoped disposable clone seeded once, with a per-test connection that is rolled back.
  1. Seed seed_protagonist, one chunk plus chunk_metadata world_time, and one active entity_tags row (INSERT ... SELECT entity_id, id, 'authored' FROM tags WHERE tag = <a vocab tag>).
  1. Remove the migration-074 replay and the TEMP TABLE backstory_secrets shadow from the connection helper.

#### `tests/test_orrery/test_reconstruction.py::test_relationship_triggers_version_updates_and_deletes`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: On the hardwired save_05 connection, the test sets chunk attribution from max(id) FROM narrative_chunks (None on the empty slot). It then runs 'UPDATE character_relationships ... WHERE (c1, c2) IN (SELECT ... LIMIT 1) RETURNING character1_id, character2_id'. The empty slot has no character_relationships rows, so RETURNING yields nothing and 'c1, c2 = cur.fetchone()' raises TypeError: cannot unpack non-iterable NoneType object. The versioning trigger never fired. set_commit_chunk_attribution_sync(cur, None) also stored the literal string 'None' in nexus.source_chunk_id, which would have broken the trigger's cast had any row been updated.
- Prerequisite: Two characters with entities, one character_relationships row between them inserted under relationship_producer(cur, 'manual') (as in tests/test_orrery/test_event_sources_pg.py), and one narrative_chunks row for attribution. The versioning triggers are BEFORE UPDATE OR DELETE, so the seeding INSERT writes no relationship_versions rows.
- Repair steps:
  1. Use the file-level seeded clone: seed_protagonist, a second character with entity, one relationship row written under relationship_producer, and one chunk.
  1. Use the seeded chunk id and relationship pair directly, rather than max(id) and a LIMIT 1 subselect.

#### `tests/test_orrery/test_reconstruction.py::test_skald_state_updates_are_ledgered`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: On the hardwired save_05 connection, the test reads max(id) FROM narrative_chunks (None), the state_delta_log baseline, and then 'SELECT c.id, c.entity_id FROM characters ... LIMIT 1'. The empty slot has no characters, so 'character_id, entity_id = cur.fetchone()' raises TypeError: cannot unpack non-iterable NoneType object. The places lookup that follows, 'place_id, place_entity_id = cur.fetchone()', would fail the same way. apply_state_updates_sync was never reached. It also logs state deltas only when source_chunk_id is not None, so the chunk is required too.
- Prerequisite: One narrative_chunks row (the state_delta_log.source_chunk_id target, which must be non-null or no ledger rows are written), one character with entity_id, and one places row with its entity_id (places get an entity through the entity spine). A layer and zone are optional; see test_need_absence_pg for a working pattern.
- Repair steps:
  1. Use the file-level seeded clone: seed_protagonist for the character and entity, one place row (INSERT INTO places (name, type[, zone]) ... RETURNING id, entity_id), and one chunk.
  1. Pass the seeded ids to StateUpdates instead of the LIMIT 1 lookups.

#### `tests/test_orrery/test_reconstruction.py::test_unattributed_relationship_write_versions_with_null_chunk`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: On the hardwired save_05 connection, the test runs an UPDATE on character_relationships (LIMIT 1 subselect) without chunk attribution. It then reads 'SELECT source_chunk_id FROM relationship_versions ORDER BY id DESC LIMIT 1' and asserts the first column is None. The empty slot has no relationship rows, so the UPDATE touches nothing, no version row is written, fetchone() returns None, and 'cur.fetchone()[0]' raises TypeError: 'NoneType' object is not subscriptable. (On a slot with existing version rows but no relationships, this test would instead read a stale version row. The seeded fixture should guarantee the UPDATE hits exactly one row.)
- Prerequisite: Two characters with entities and one character_relationships row between them, inserted under relationship_producer(cur, 'manual'). No chunk is needed, since the test asserts NULL attribution.
- Repair steps:
  1. Use the file-level seeded clone and its relationship pair.
  1. Assert the UPDATE rowcount == 1, and read the version row by relationship key (or by id greater than a pre-update max(id)), so the assertion cannot pass or fail on a stale row.

#### `tests/test_orrery/test_recruit_ally_projects.py::test_live_neglect_applies_recruitment_setback`

- Baseline outcome: error; signature: `failed on setup with "TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'"`
- Route: `seed_disposable_clone` to #885; confidence 0.95; runtime confirmation needed
- Cause: This is a setup error in the shared live_project_db fixture (lines 300-345). The fixture connects with psycopg2.connect(get_slot_db_url(slot=2)), and 'SELECT max(id) FROM narrative_chunks' returns (None,) on the empty private save_02. 'chunk_id = int(cur.fetchone()[0])' then raises TypeError: int() argument must be ... not 'NoneType'. The test body, which inserts a stalled-due recruit_ally project and applies the neglect setback through _insert_resolution_sync and _apply_state_delta_sync, never ran.
- Prerequisite: Three character entities (actor, target, other) with characters rows, one places row, and one narrative_chunks row with a world clock. _apply_project_stall_sync and the other project writers call _tick_world_time_sync, which needs chunk_metadata.world_time for the chunk, or else base_timestamp, and raises OrreryWorldClockUnavailableError otherwise. The transaction also needs nexus.write_producer='manual' (the fixture already sets it).
- Repair steps:
  1. Apply the file-level live_project_db rewrite (see file note).
  1. No per-test changes are needed beyond using the seeded ids the fixture yields.

#### `tests/test_orrery/test_recruit_ally_projects.py::test_live_schema_target_discipline_and_one_project_budget`

- Baseline outcome: error; signature: `failed on setup with "TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'"`
- Route: `seed_disposable_clone` to #885; confidence 0.95; runtime confirmation needed
- Cause: This is the same setup error in live_project_db: int(None) on max(id) FROM narrative_chunks in the empty private save_02. The body exercises template CHECK constraints (a recruit_ally row with target_place_id, a plan_relocation row with a character target) and the one-active-project unique index. It also needs the fixture's place_id, which the fixture looks up with another int(cur.fetchone()[0]) that would also fail on an empty slot.
- Prerequisite: Three character entities, one places row (for place_id), and one chunk. No clock is needed for the constraint checks themselves.
- Repair steps:
  1. Apply the file-level live_project_db rewrite, making sure it yields a real seeded place_id.

#### `tests/test_orrery/test_recruit_ally_projects.py::test_live_stage_ladder_completion_and_applied_ledger`

- Baseline outcome: error; signature: `failed on setup with "TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'"`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This is the same setup error in live_project_db (int(None) on max chunk id in the empty private save_02). Once seeded, the body inserts a 'friend' character_relationships row between the actor and target characters (it joins characters by entity_id). It then applies start, routine, milestone and completion drafts through _insert_resolution_sync and _apply_state_delta_sync, and asserts on the 'ally' pair tag, the relationship_type change, preserved relationship prose, and reconcile_trait_relationship_pair_tags reporting no drift.
- Prerequisite: Actor and target character entities, each with a characters row (the relationship insert joins characters.entity_id), one chunk with chunk_metadata.world_time (or base_timestamp) for _tick_world_time_sync in the project writers, the 'ally' and 'contact:social' pair_tags vocab (template seed rows), and write_producer='manual' for the relationship insert and update.
- Repair steps:
  1. Apply the file-level live_project_db rewrite.
  1. Check the source_chunk_id assertion (extra_data['orrery_recruit_ally']['source_chunk_id'] == db['chunk_id']) against the seeded chunk id.

#### `tests/test_orrery/test_recruit_ally_projects.py::test_live_start_persists_bound_character_target`

- Baseline outcome: error; signature: `failed on setup with "TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'"`
- Route: `seed_disposable_clone` to #885; confidence 0.95; runtime confirmation needed
- Cause: This is the same setup error in live_project_db (int(None) on max(id) FROM narrative_chunks in the empty private save_02). The body evaluates START_RECRUIT_ALLY in memory, applies the draft, and reads back character_project_states. That write path needs an actor and target entity, a chunk, and a world clock for _apply_project_start_sync (via _tick_world_time_sync).
- Prerequisite: Actor and target character entities, and one chunk with chunk_metadata.world_time or global_variables.base_timestamp.
- Repair steps:
  1. Apply the file-level live_project_db rewrite.

#### `tests/test_orrery/test_recruit_ally_projects.py::test_slot2_recruitment_routes_persisted_target_without_routine_drift`

- Baseline outcome: failure; signature: `AssertionError: save_02 must provide 35 coverage anchors`
- Route: `gate_behind_corpus_flag` to #885; confidence 0.95
- Cause: This is a corpus-bound 35-anchor pilot probe (lines 769-1024) on a rolled-back connection to get_slot_db_url(slot=2). sample_anchor_ids(count=35, stride=1) returns [] on the empty private save_02, so 'assert len(anchors) == 35' fails with 'save_02 must provide 35 coverage anchors'. The rest depends on corpus statistics: surveil winners with a target, an actor without an open project, an unrelated off-screen recruit target, and routine-share drift below coverage_distribution_tolerance. It also contains a pytest.skip('slot 2 needs an unrelated off-screen recruit target') escape hatch that would turn missing data into a skip.
- Prerequisite: save_02's corpus: 35 or more playable chunks with chunk_metadata world_time, coverage producing 'surveil' winners with a target for an actor who has no open project, and an unrelated active character not present at anchors[0].
- Repair steps:
  1. Mark the test requires_corpus (the marker and flag still need to be added to tests/conftest.py) and run it on disposable_slot_database('recruit_coverage', source_db='save_02', include_data=True), not on the live slot.
  1. Replace the pytest.skip escape with an assertion. Under the corpus flag, a missing recruit target means the corpus changed and should fail loudly.
  1. Gating is more honest than seeding a synthetic story: the routine-drift tolerance is a statistic about the authored corpus. The target-discipline, stage-ladder and abandonment mechanics are covered by the fixture-backed live_project_db tests and the pure-substrate tests.

#### `tests/test_orrery/test_replay.py::test_applicability_toggle_resets_need_row_to_fresh_shape`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: On the empty save_05, _head_chunk returns None and _probe_character (SELECT the first character with an entity_id) returns None, so the 4-tuple unpack raises 'cannot unpack non-iterable NoneType object'. Beyond that, the test needs a hunger need row on the probe. It also needs max(chunk_metadata.world_time) to be non-NULL, because it asserts the re-inserted fresh row's last_evaluated_at equals that 'primary clock'. The migration-100 orrery_sync_character_need_states anchors fresh rows to MAX(world_time), falling back to base_timestamp. It also needs the seed 'inorganic' tag (migration 055 vocab, present in the template).
- Prerequisite: Head chunk with chunk_metadata world_time equal to base_timestamp. A probe character with an entity row whose need rows were created by trg_characters_need_state_init after base_timestamp was set, and which does not carry 'inorganic'. The 'inorganic' tag from template vocab.
- Repair steps:
  1. Use the shared replay_db fixture. seed_protagonist must run before any chunk_metadata insert, and the head metadata row (time_delta NULL) must derive world_time = base_timestamp.
  1. Do not seed any need-immunity tag on the probe character.

#### `tests/test_orrery/test_replay.py::test_need_applicability_trigger_is_mirrored`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. The test then asserts that the probe carries need rows ('probe character must carry need rows'). It bestows 'inorganic', which fires the real migration-057 trigger that deletes sleep/hunger/thirst, and expects replay to mirror that deletion.
- Prerequisite: A head chunk. A probe character (first by id with an entity_id) with sleep/hunger/thirst/socialize/intimacy need rows, created by the character INSERT trigger with base_timestamp already set, and no immunity tag. The 'inorganic' tag seed.
- Repair steps:
  1. Use the shared replay_db fixture. seed_protagonist sets base_timestamp before inserting the character, so the INSERT trigger creates the five need rows.

#### `tests/test_orrery/test_replay.py::test_need_fulfillment_replay_matches_production_applier`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. The test needs the probe's hunger row, and a probe chunk world_time (max(world_time)+6h) later than that row's last_evaluated_at, so the production debt math matches replay. On a clone with no chunk_metadata, _next_world_time falls back to 2026-01-01T06:00 while seed_protagonist's default base_timestamp is 2100-01-01, which would run the need clock backwards. The seed must therefore include head chunk_metadata aligned to base_timestamp.
- Prerequisite: base_timestamp B. A probe character with a hunger need row anchored at B. A head chunk whose chunk_metadata world_time is B.
- Repair steps:
  1. Use the shared replay_db fixture with head chunk_metadata derived from base_timestamp, so _next_world_time returns B+6h.

#### `tests/test_orrery/test_replay.py::test_pair_tag_bestowal_and_clearance_replay`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The first query (a non-deprecated pair_tags row) succeeds, because the template carries pair_tags seed vocab. The recorded signature comes from the second fetch. The pair query (two characters a < b by entity_id, both non-NULL, not already carrying that pair tag) returns None on the empty clone, so 'subject, obj = cur.fetchone()' raises 'cannot unpack non-iterable NoneType object'. The test also needs a head chunk so the reconstruct and verify window is anchored.
- Prerequisite: At least 2 characters with active character entity rows. A head chunk. Template pair_tags seed rows (already present).
- Repair steps:
  1. Use the shared replay_db fixture, which seeds 3 characters with entities.

#### `tests/test_orrery/test_replay.py::test_post_fix_null_world_time_uses_primary_clock_exactly`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. The test then fabricates a chunk with NULL world_time and reads primary_clock = max(chunk_metadata.world_time). That would be None on a slot with no metadata, and datetime.fromisoformat or the equality check would fail. It also relies on schema_migrations version '100' having an applied_at earlier than the test's resolution (_need_clock_fix_applied_at). A template clone copies those stamps.
- Prerequisite: A probe character with a thirst need row. Head chunk_metadata with a non-NULL world_time (the primary clock). A schema_migrations '100' stamp, which the template clone provides.
- Repair steps:
  1. Use the shared replay_db fixture, which includes head chunk_metadata derived from base_timestamp.

#### `tests/test_orrery/test_replay.py::test_post_target_replace_reapplication_is_presence_remainder`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.87; runtime confirmation needed
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. Next, the test needs a tag with reapplication_policy='replace' in a tag_category_registry category registered for entity_kind 'character'. Such tags should come from template vocab, for example migration 054's state-event tags in category 'state'. It also needs a head chunk with world_time, because it drives the production _insert_entity_tag writer twice.
- Prerequisite: A probe character with an entity row. A head chunk plus chunk_metadata world_time. Template seed tags that include a character-registered 'replace' tag.
- Repair steps:
  1. Use the shared replay_db fixture.
  1. If the template lacks a character-kind 'replace' tag, raise this under #810 (template seed drift) rather than inserting ad hoc vocab.

#### `tests/test_orrery/test_replay.py::test_project_applied_ledger_survives_replay_policy_retuning`

- Baseline outcome: failure; signature: `AssertionError: replay project tests need one located uncommitted actor`
- Route: `seed_disposable_clone` to #885; confidence 0.92; runtime confirmation needed
- Cause: Module _connect() hardwires save_05 (WRITE_SLOT=5). In the baseline that was an empty template clone on the private cluster. The first content read is _project_probe_character, which selects a character that has an entity_id, a non-NULL current_location and no open character_project_states row. There are zero characters, so its own assertion fires: 'replay project tests need one located uncommitted actor'. The rest of the test fabricates its own chunks and project transitions (#428 pattern), so it is not a corpus probe. Neither the test nor the path has changed since b0645daf.
- Prerequisite: At least one narrative_chunks row (_fabricate_chunk uses max(id)+1). chunk_metadata.world_time on the head chunk equal to global_variables.base_timestamp, so _next_world_time does not fall back to 2026-01-01. One active character entity plus a characters row with current_location set to a place and no active, paused or stalled project. The [orrery.projects] policy in nexus.toml; the test monkeypatches the policy.
- Repair steps:
  1. Use the shared module-scoped replay_db fixture (disposable_slot_database + seed_replay_corpus; see file_notes).
  1. In the seed, set the protagonist's current_location to seeded place 1 with a direct UPDATE in the seed transaction.
  1. Remove the stale _apply_migration_074 call path (template already stamps 074).

#### `tests/test_orrery/test_replay.py::test_project_complete_hands_off_and_real_travel_applier_relocates`

- Baseline outcome: failure; signature: `AssertionError: replay project tests need one located uncommitted actor`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: Same save_05 hardwire. After the redundant _apply_migration_074, the first read is _project_probe_character. The empty clone has no located character, so it asserts 'replay project tests need one located uncommitted actor'. The next hidden dependency is 'SELECT id FROM places WHERE id <> origin', which would return None on a clone with fewer than 2 places. project.complete hands off to the real travel.start applier. _select_route_sync falls back to _estimate_route_sync, which accepts NULL coordinates, so no geometry or OSM graph is needed.
- Prerequisite: A located, uncommitted character with an entity row. Two places, where the target differs from the origin. At least one narrative chunk. Head chunk_metadata world_time equal to base_timestamp.
- Repair steps:
  1. Use the shared replay_db fixture. The seed provides 2 places and sets the protagonist's current_location to place 1.
  1. Drop the in-test _apply_migration_074(cur) call.

#### `tests/test_orrery/test_replay.py::test_project_replay_rejects_ledger_without_applied_projection`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. With a character present, the test fabricates its own base and raw chunks (which needs at least one existing chunk for max(id)+1) and inserts a project.start ledger row without an applied projection. It expects the replay ValueError 'missing its required applied project projection'.
- Prerequisite: One character with an entity row. At least one narrative chunk. Head chunk_metadata world_time.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_replay.py::test_project_transition_window_replays_with_zero_checkpoint_drift`

- Baseline outcome: failure; signature: `AssertionError: replay project tests need one located uncommitted actor`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: Same save_05 hardwire. _project_probe_character is the first content read and asserts on the empty clone because no located character is free of an open project. The test then needs a second place as the relocation target and fabricates the whole start/advance/crisis/stall/abandon/start/complete window itself.
- Prerequisite: A located, uncommitted character with an entity row. A second place distinct from the origin. At least one narrative chunk. Head chunk_metadata world_time, so base_time = max(world_time)+6h stays after every need clock.
- Repair steps:
  1. Use the shared replay_db fixture (2 places; protagonist located at place 1).
  1. Drop the in-test _apply_migration_074(cur) call. The test already strips character_project_states from its base checkpoint to model a pre-074 checkpoint.

#### `tests/test_orrery/test_replay.py::test_reconstruction_refuses_pre_instrumentation_chunks`

- Baseline outcome: failure; signature: `AssertionError: save_05 must carry a genesis checkpoint`
- Route: `seed_disposable_clone` to #885; confidence 0.94
- Cause: The test reads min(chunk_id) from state_checkpoints and requires a genesis checkpoint, which the owner's native save_05 carries. The empty clone has no checkpoints, so it asserts 'save_05 must carry a genesis checkpoint'. Once a checkpoint exists, the test fabricates a chunk before it if necessary. reconstruct_state_at_sync then raises from _Replayer.load_base_checkpoint ('predates the instrumentation era'), which is the behavior under test.
- Prerequisite: A state_checkpoints row with a non-NULL chunk_id. Production writes this with label='genesis' via retrograde_orchestrator. Ideally a narrative chunk precedes the genesis chunk, so the non-fabricating branch is used. If genesis sits at chunk 1 the test inserts id 0, which also works.
- Repair steps:
  1. In seed_replay_corpus, insert a pre-instrumentation chunk, then the head chunk, and finish with capture_state_checkpoint_sync(cur, chunk_id=head, label='genesis').
  1. Switch the test to the replay_db fixture and reword the assertion message to be slot-neutral.

#### `tests/test_orrery/test_replay.py::test_relationship_multi_version_unwind_order`

- Baseline outcome: failure; signature: `psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The first statement is _fabricate_chunk. Its 'INSERT INTO narrative_chunks (id, ...) SELECT max(id)+1 ... FROM narrative_chunks' yields id NULL on an empty table, raising NotNullViolation on narrative_chunks.id. The helper is fragile because it gives no clear precondition error, but the real assumption is save_05 content. Next, the test needs at least one character_relationships row, otherwise 'c1, c2, original = cur.fetchone()' fails to unpack. It does two attributed updates and checks newest-first unwind.
- Prerequisite: At least one narrative chunk. At least one character_relationships row seeded under a valid nexus.write_producer; migration 115's trigger raises without one.
- Repair steps:
  1. Use the shared replay_db fixture, which seeds relationships (c1,c2) and (c1,c3) under set_commit_chunk_attribution_sync(head) and SET LOCAL nexus.write_producer='manual'.
  1. Optionally harden _fabricate_chunk with 'assert max(id) is not None' for a legible precondition failure.

#### `tests/test_orrery/test_replay.py::test_relationship_unwind_restores_updates_deletes_and_drops_inserts`

- Baseline outcome: failure; signature: `psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The first statement is _fabricate_chunk, where max(id)+1 is NULL on the empty table, raising NotNullViolation on narrative_chunks.id. The test then unpacks exactly two relationships ('(u1,u2,..),(d1,d2,_) = cur.fetchall()' with LIMIT 2), so it needs at least 2 relationship rows. Next it selects a character pair a.id < b.id with no relationship for the post-chunk INSERT, so it needs at least 3 characters. It relies on replay's strict wall-clock filter (created_at > target created_at), so seeded relationships must be created no later than the fabricated chunks.
- Prerequisite: At least one narrative chunk. At least 3 characters. 2 character_relationships rows, for example (c1,c2) and (c1,c3), with emotional_valence like '0|neutral', written under a valid nexus.write_producer and attributed to the head chunk, leaving (c2,c3) free.
- Repair steps:
  1. Use the shared replay_db fixture. Seed the relationships in the same committed seed transaction as the head chunk, so their created_at is at or before the head chunk's created_at.

#### `tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift`

- Baseline outcome: failure; signature: `psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: _head_chunk returns None, and capture_state_checkpoint_sync(chunk_id=None) silently inserts a NULL-chunk checkpoint (the column is nullable). Then _fabricate_chunk's max(id)+1 is NULL, raising NotNullViolation on narrative_chunks.id. With a head chunk, the test needs that chunk as the FK target for world_events.tick_chunk_id, plus an event_types seed row (template). It inserts its own entity, maturation job 545001 and activity projection.
- Prerequisite: A head narrative chunk. Template event_types seed. No existing orrery_maturation_jobs id 545001, which holds on a fresh clone.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_replay.py::test_scalar_replay_round_trip_and_within_chunk_ordering`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: On the empty save_05, _head_chunk returns None and _probe_character returns None, causing the unpack TypeError. The test then needs at least one place for the Skald location and conditions write through apply_state_updates_sync. It captures a manual base checkpoint at head, fabricates one probe chunk, and asserts within-chunk ordering (Skald first, then Orrery) plus zero verify drift.
- Prerequisite: A head chunk plus chunk_metadata world_time. A probe character with an entity row. At least one place.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_replay.py::test_tag_applicability_before_fulfillment_preserves_marker`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The first statement is _probe_character, which returns None on the empty save_05 and causes the unpack TypeError. The test then fabricates base, clear and fulfill chunks (which needs at least one existing chunk). Bestowing 'inorganic' deletes the probe's hunger row, which must be absent afterwards. Clearing it re-inserts a fresh row through the trigger before a same-window fulfillment. _next_world_time needs head metadata so the fresh-row anchor precedes the fulfillment clock.
- Prerequisite: A probe character without 'inorganic'. At least one narrative chunk with chunk_metadata world_time equal to base_timestamp. The 'inorganic' seed tag.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_replay.py::test_tag_bestowal_and_clearance_replay_at_exact_chunks`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. The next hidden dependency is 'SELECT id FROM entity_tags WHERE cleared_at IS NULL ORDER BY id LIMIT 1' (the clearance victim). An empty clone has no active entity tags, so fetchone()[0] would raise 'NoneType' object is not subscriptable. The test also needs a non-deprecated canonical tag not already on the probe, which template vocab provides.
- Prerequisite: A head chunk. A probe character. At least one active entity_tags row whose authored clearance replays cleanly: a durable non-severity, non-need-immunity tag, so clearing it does not fire the applicability trigger.
- Repair steps:
  1. Use the shared replay_db fixture. seed_replay_corpus seeds one durable active entity tag via tag_writer._insert_entity_tag with source_chunk_id=head, before the genesis checkpoint.

#### `tests/test_orrery/test_replay.py::test_travel_replay_start_advance_arrive`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. The test then unpacks exactly two places ('(origin,), (destination,) = cur.fetchall()' from 'SELECT id FROM places ORDER BY id LIMIT 2'), which needs at least 2 places. It also needs head chunk_metadata so the fabricated start and arrive chunks read back stored world_times. The travel rows are written directly; replay derives the rest.
- Prerequisite: A probe character with an entity row. At least 2 places. A head chunk plus chunk_metadata world_time.
- Repair steps:
  1. Use the shared replay_db fixture, which seeds 2 places.

#### `tests/test_orrery/test_replay.py::test_unresolved_arrival_marks_location_unreproducible`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. With a probe character, the test only inserts ledger rows (travel.start with destination_anchor 'home', then a bare travel.arrive) and asserts that replay flags the unknowable columns as unreproducible. It needs a head chunk for the base checkpoint and max(id)+1.
- Prerequisite: A probe character with an entity row. A head chunk plus chunk_metadata world_time.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_replay.py::test_verify_catches_unledgered_entity_deactivation`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. Given a character entity and a head chunk, the test flips entities.is_active with no ledger row and asserts that verify reports an exact entities drift.
- Prerequisite: A probe character with an active entity. A head chunk.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_replay.py::test_verify_catches_unledgered_scalar_drift`

- Baseline outcome: failure; signature: `TypeError: cannot unpack non-iterable NoneType object`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: On the empty save_05, _probe_character returns None, causing the unpack TypeError. Given a character and a head chunk, the test writes emotional_state with no ledger row and asserts that verify catches it as a characters/emotional_state value drift.
- Prerequisite: A probe character. A head chunk.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_replay.py::test_verify_catches_unlogged_tag_clear`

- Baseline outcome: failure; signature: `psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: head is None, the capture inserts a NULL-chunk checkpoint, and _fabricate_chunk's max(id)+1 is NULL, raising NotNullViolation on narrative_chunks.id. The next hidden dependency: the 'UPDATE entity_tags ... RETURNING et.id' clears the first active non-severity tag. An empty clone has no active entity tags, so fetchone()[0] would raise 'NoneType' object is not subscriptable.
- Prerequisite: A head chunk. At least one active entity_tags row whose tag is not a sleep_deprived/hungry/thirsty/under_socialized/intimacy_starved severity tag.
- Repair steps:
  1. Use the shared replay_db fixture. The seeded durable non-severity entity tag serves both this test and the tag-bestowal victim.

#### `tests/test_orrery/test_replay.py::test_verify_skips_legacy_checkpoint_without_entity_activity`

- Baseline outcome: failure; signature: `psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: head is None, and the NULL-chunk checkpoint capture and strip succeed. Then _fabricate_chunk's max(id)+1 is NULL, raising NotNullViolation on narrative_chunks.id. With a head chunk, the test needs world_events.tick_chunk_id=head and an event_types seed row, then checks that the legacy base without an entities section is an explicit skip.
- Prerequisite: A head narrative chunk. Template event_types seed.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_replay.py::test_window_born_character_fulfillment_preserves_applicability_marker`

- Baseline outcome: failure; signature: `psycopg2.errors.NotNullViolation: null value in column "id" of relation "narrative_chunks" violates not-null constraint`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: head is None, and the capture inserts a NULL-chunk checkpoint; _next_world_time falls back to 2026-01-01+6h. Then _fabricate_chunk's max(id)+1 is NULL, raising NotNullViolation on narrative_chunks.id. Even with only the helper fixed, the NULL-chunk base checkpoint would be rejected by load_base_checkpoint ('not a valid base'). So a real head chunk is required. The test inserts its own character, and the need rows come from the INSERT trigger anchored at MAX(world_time).
- Prerequisite: A head narrative chunk, ideally with chunk_metadata world_time equal to base_timestamp.
- Repair steps:
  1. Use the shared replay_db fixture.

#### `tests/test_orrery/test_retrograde_maturation.py::test_pg_enqueue_creates_stub_and_job`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Module fixture maturation_corpus calls disposable_slot_database('qa640_maturation799', source_db='save_02', include_data=True), which pg_dumps whatever save_02 holds. In the baseline cluster save_02 was an empty template clone, so the clone has no narrative_chunks. The test body first calls _latest_chunk_id(), which runs `SELECT max(id) FROM narrative_chunks` and gets NULL, then does int(None), giving the recorded TypeError. Setup succeeded (dump, restore and migrate of the empty save_02 all worked), so this is a failure in the body, not a setup error. The test was not red in the owner's #922 triage (docs/qa/test-fallout-repair/verification.md), so it passes on the populated save_02. The only thing it takes from the corpus is one chunk id: the declared entity name is unique and the orrery_maturation_jobs.requesting_chunk_id FK (migrations/062) needs a real narrative_chunks row. Neither the test file nor the chunk-id path in retrograde_maturation.py changed after b0645daf; the later diff only adds same_as and canonical-name handling.
- Prerequisite: One narrative_chunks row (FK target for orrery_maturation_jobs.requesting_chunk_id); the singleton global_variables row (resolve_enqueued_seat reads model/gaia_model/apex_context_window FOR SHARE, and the template has it); seed vocab (tag_category_registry, tags) from the template. No world clock is needed because there are no tag hints.
- Repair steps:
  1. Change maturation_corpus to a plain template clone: disposable_slot_database('qa640_maturation799') with no source_db and no include_data.
  1. In the module fixture, insert one narrative_chunks row plus a chunk_metadata row (a shared seed_chunk helper, see file_notes). Yield or cache its id and use it in place of _latest_chunk_id(), or make _latest_chunk_id fail with a clear message when it gets NULL.
  1. Keep slot=2 as the job's slot label only; nothing in the enqueue path connects to save_02.

#### `tests/test_orrery/test_retrograde_maturation.py::test_pg_enqueue_is_idempotent_per_entity`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Same fixture and helper as test_pg_enqueue_creates_stub_and_job. The corpus clone comes from the empty private save_02, so `SELECT max(id) FROM narrative_chunks` returns NULL and _latest_chunk_id() calls int(None) before either enqueue runs. The idempotency path (ON CONFLICT (entity_id) DO NOTHING) needs only one real chunk and the template schema. The test passed in the owner's environment on populated save_02.
- Prerequisite: One narrative_chunks row for requesting_chunk_id; the global_variables singleton; template seed vocab.
- Repair steps:
  1. Apply the file-level fixture repair: template clone plus one seeded chunk whose id replaces _latest_chunk_id().

#### `tests/test_orrery/test_retrograde_maturation.py::test_pg_unregistered_pair_tag_hint_fails_loudly`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: _latest_chunk_id() hits int(None) on the chunkless clone of the empty private save_02 before enqueue_declared_entity_maturations is called. Once a chunk exists, the expected RetrogradeMaturationVocabularyError comes from collect_new_entity_declaration_vocabulary_issues: validate_pair_tag_endpoint rejects the unregistered pair tag and the 'Anyone' endpoint does not resolve. Both checks run before any chunk-dependent write, so the test depends on the corpus only for the helper call.
- Prerequisite: Any real narrative_chunks id (only the helper needs it); pair_tags seed vocabulary from the template.
- Repair steps:
  1. Apply the file-level fixture repair (template clone plus seeded chunk id).

#### `tests/test_orrery/test_retrograde_maturation.py::test_pg_unregistered_tag_hint_fails_loudly`

- Baseline outcome: failure; signature: `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: Same as the other three PG nodes in this file: _latest_chunk_id() calls int(None) because the save_02 corpus clone has no narrative_chunks. With a chunk present, validate_tag_bestowal (declaration_validation.py) reports the unregistered tag and the function raises RetrogradeMaturationVocabularyError, a ValueError subclass, before _require_accepting_world_time runs. That satisfies pytest.raises(ValueError).
- Prerequisite: Any real narrative_chunks id; tags and tag_category_registry seed vocabulary from the template.
- Repair steps:
  1. Apply the file-level fixture repair (template clone plus seeded chunk id).

#### `tests/test_orrery/test_retrograde_projects_live.py::test_between_capture_maturation_job_still_replays_under_gate`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: Every test in this file depends on the module fixture project_corpus, which calls disposable_slot_database('qa640_projects799', source_db='save_02', include_data=True), and on the per-test fixture project_db, which requires at least 12 characters with entity_id and at least 2 places. In the private cluster, save_02 is an empty template clone, so the pg_dump/restore and migration succeed but the character query returns 0 rows and `assert len(characters) >= 12` fails during setup. This matches the recorded 'assert 0 >= 12'. No production code runs. This test uses characters[1], builds a base checkpoint at a fabricated chunk whose time comes from _next_world_time (which asserts max(chunk_metadata.world_time) IS NOT NULL), inserts a succeeded orrery_maturation_jobs row and a malformed build_venture_started event, and expects replay to raise 'missing its required applied'. Nothing relevant has changed on main since b0645daf: the test is untouched, and the replay.py and reconstruction.py edits do not affect this setup assertion.
- Prerequisite: global_variables.base_timestamp; at least 12 active character entities with characters rows (characters[1] used); at least 2 places with entity rows (fixture assertion); at least one narrative_chunks row with chunk_metadata.world_time (for _next_world_time and for _fabricate_chunk's max(id)+1 to be non-NULL)
- Repair steps:
  1. Apply the file-level fixture repair: a template clone plus a seeded cast, places, prologue and clock (see file_notes).
  1. No per-test change beyond making _fabricate_chunk use the id sequence.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_cap_dropped_projects_do_not_claim_actor_keys`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: Same setup failure as the rest of the file: project_db asserts at least 12 characters in a copy of save_02, and the private save_02 is empty. The test itself calls build_retrograde_persistence_plan with dry_run=False and max_seeded_projects=1 for characters[0] and [1]. That path needs global_variables.base_timestamp for project next_eligible_at_world_time, and on an empty slot it inserts a retrograde prologue chunk plus chunk_metadata, whose world_time is derived by trigger from base_timestamp.
- Prerequisite: base_timestamp; at least 12 characters with entity rows (characters[0..1] used); at least 2 places; resolvable unique character names in the entity index
- Repair steps:
  1. Use the seeded disposable clone from file_notes.
  1. Seed base_timestamp before inserting any character, which seed_protagonist does.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_checkpoints_without_control_key_keep_legacy_window`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Setup error from project_db's `assert len(characters) >= 12` against the empty private save_02 copy. The test uses characters[2], calls _next_world_time (which needs a non-NULL max(chunk_metadata.world_time)) and _fabricate_chunk (`INSERT ... SELECT max(id)+1`, which inserts a NULL id on an empty narrative_chunks table), captures two manual checkpoints, strips the _maturation_jobs_succeeded control key, and expects legacy-window replay to raise 'missing its required applied'.
- Prerequisite: base_timestamp; at least 12 characters with entity rows (characters[2] used); at least one narrative chunk with chunk_metadata.world_time; orrery_maturation_jobs and state_checkpoints tables (template)
- Repair steps:
  1. Use the seeded disposable clone from file_notes, which includes at least one world-time chunk.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_delayed_maturation_write_is_gated_out_of_checkpoint_replay`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: Setup error from project_db's 12-character assertion on the empty save_02 copy. The body uses characters[0] and [3], fabricates chunks at _next_world_time (which needs an existing world clock), inserts a maturation job, a malformed started event and an entity_pair_tags row that uses the first pair_tags id (the pair_tags seed vocabulary comes from the template), then checks that gated replay notes and verify_checkpoints_sync report no drift and at least one skipped_unreproducible.
- Prerequisite: base_timestamp; at least 12 characters with entity rows (characters[0], [3]); at least one chunk with chunk_metadata.world_time; seeded pair_tags vocabulary (template)
- Repair steps:
  1. Use the seeded disposable clone from file_notes.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_dropped_project_targets_do_not_create_entity_stubs`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The test runs build_retrograde_persistence_plan with create_missing_entities=True, which calls _load_persisted_protagonist_identity, which calls canonical_player_character_id. That raises PlayerIdentityNotEstablishedError when global_variables.user_character is NULL, so a seeded clone also needs a bound protagonist. It also needs base_timestamp for project seeding and prologue insertion.
- Prerequisite: base_timestamp and user_character (a canonical protagonist whose name tokens are not a superset of the 'Accepted Target <nonce>' stub tokens); at least 12 NPC characters with entity rows (characters[0..1] used)
- Repair steps:
  1. Use the seeded disposable clone from file_notes. seed_protagonist binds user_character.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_maturation_disabled_config_drops_intent_loudly`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body fabricates a request chunk at _next_world_time (needs an existing world clock and a non-empty narrative_chunks for max(id)+1) and calls _persist_maturation_expansion. That always passes create_missing_entities=True, so it needs a canonical protagonist, and with project seeding disabled it expects projects_dropped_disabled == 1 plus a loud log.
- Prerequisite: base_timestamp; user_character; at least 12 characters with entity rows (characters[0]); at least one chunk with chunk_metadata.world_time
- Repair steps:
  1. Use the seeded disposable clone from file_notes, which includes the protagonist and the world-time chunk.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_maturation_project_replays_exactly_and_hydrates_continuation`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.75; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. This is the most corpus-sensitive test in the file. It fabricates base, request and advance chunks, inserts a succeeded maturation job, persists a mid-arc build_venture through _persist_maturation_expansion (needs a protagonist), then runs resolve_dry_run(ADVANCE_BUILD_VENTURE). resolve_dry_run hydrates weather through canonical_player_character_id and the protagonist's current_location, and it requires character_need_states rows (created by the orrery_sync_character_need_states trigger, which raises 'need-clock anchor unavailable' when there is neither a chunk world_time nor base_timestamp) with debt below the package floors. It then commits the tick with commit_orrery_tick_sync and expects checkpoint verification with no drift.
- Prerequisite: base_timestamp; user_character with a current_location place; at least 12 NPC characters with entity rows and need-state rows created after base_timestamp exists; at least one chunk with chunk_metadata.world_time; no character_travel_states or constraint tags on the actor
- Repair steps:
  1. Use the seeded disposable clone from file_notes. Bind the protagonist and NPCs to a seeded place through current_location.
  1. Run the node alone on the seeded clone to confirm the resolver produces the 'Make the venture legible' continuation and that there is no replay drift.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_maturation_seeds_only_target_actor_and_logs_advisory_drops`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body fabricates a request chunk with an explicit id of max(id)+1, then calls _persist_maturation_expansion. On a slot with no retrograde prologue, that call inserts a prologue through the narrative_chunks id sequence. On a fresh seeded clone where the sequence equals max(id), the prologue nextval can collide with the fabricated chunk id. That is why the repair also moves _fabricate_chunk onto the sequence and/or seeds a prologue; save_02 presumably already had a prologue, which masked this.
- Prerequisite: base_timestamp; user_character; at least 12 characters with entity rows (characters[0..1]); at least one world-time chunk; an existing retrograde prologue chunk, or a _fabricate_chunk that uses the id sequence
- Repair steps:
  1. Use the seeded disposable clone from file_notes.
  1. Make _fabricate_chunk insert without an explicit id so it draws from the sequence and cannot collide with the prologue insert.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_maturation_shared_writer_validation_raises`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body uses characters[0] and [8], fabricates a request chunk from the existing world clock, and expects three fail-fast validation errors (target shape, death_plan actor, unresolvable actor) from _persist_maturation_expansion, which uses create_missing_entities=True and therefore loads the canonical protagonist.
- Prerequisite: base_timestamp; user_character; at least 12 characters with entity rows (characters[0], [8]); at least one world-time chunk
- Repair steps:
  1. Use the seeded disposable clone from file_notes.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_maturation_start_at_base_chunk_replays_without_drift`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.8; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body fabricates a base chunk, captures a manual checkpoint, inserts a succeeded maturation job at the base chunk, persists a build_venture (needs a protagonist; may insert a prologue if none exists), fabricates a target chunk, and expects the replayed state to include the project with no checkpoint drift.
- Prerequisite: base_timestamp; user_character; at least 12 characters with entity rows (characters[0]); at least one world-time chunk; ideally a seeded retrograde prologue so no prologue lands inside the replay window
- Repair steps:
  1. Use the seeded disposable clone from file_notes, including a prologue chunk and the sequence-based _fabricate_chunk.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_maturation_start_at_target_chunk_is_absent_without_drift`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.8; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body fabricates base and target chunks with manual checkpoints, then persists a maturation project attributed to the target chunk after the target capture, and expects replay to omit it with no drift. It needs the existing world clock, a protagonist (create_missing_entities=True), and ideally an existing prologue so none is inserted at a newer id than the target.
- Prerequisite: base_timestamp; user_character; at least 12 characters with entity rows (characters[0]); at least one world-time chunk; a seeded retrograde prologue
- Repair steps:
  1. Use the seeded disposable clone from file_notes.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_maturation_started_event_requires_applied_projection_in_replay`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body needs only characters[0], the existing world clock for _next_world_time, a non-empty narrative_chunks for _fabricate_chunk, and a manual checkpoint. It inserts a started event that has no `applied` field and expects reconstruct_state_at_sync to raise 'missing its required applied'.
- Prerequisite: base_timestamp; at least 1 character with an entity row (the fixture still demands 12); at least one world-time chunk
- Repair steps:
  1. Use the seeded disposable clone from file_notes.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_seek_redemption_rejects_non_materializing_planned_enemy`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body inserts a friendly TARGET->ACTOR character_relationships row inside relationship_producer(cur, 'manual'), as migration 115 requires, then runs build_retrograde_persistence_plan with dry_run=False and create_missing_entities=True, which needs a canonical protagonist. It expects the 'TARGET->ACTOR wary-or-worse' ValueError and zero seek_redemption rows.
- Prerequisite: base_timestamp; user_character; at least 12 characters with entity rows (characters[0], [8]); template relationship vocabulary (enemy/rival/captor)
- Repair steps:
  1. Use the seeded disposable clone from file_notes.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_seek_redemption_requires_target_to_actor_negative_valence`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body runs a DELETE on character_relationships without a relationship_producer wrapper. That is safe only because the fixture already cleared those pairs, so the DELETE matches zero rows and the migration-115 row trigger never fires. It then expects a dry-run 'wary-or-worse' ValueError. The dry run does not load the protagonist.
- Prerequisite: at least 12 characters with entity rows (characters[0], [8]); template vocabulary; base_timestamp for project seeding
- Repair steps:
  1. Use the seeded disposable clone from file_notes.
  1. Optionally wrap the test's DELETE in relationship_producer(cur, 'manual') so it stays valid if the fixture's clearing changes.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_summary_backfill_excludes_wizard_and_maturation_project_starts`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body persists a wizard project for characters[0], which inserts a prologue through the id sequence if none exists, then fabricates a chunk and persists a maturation project for characters[1] with summaries_enabled=True, then checks that plan_retrograde_summaries excludes both started events. It needs base_timestamp, a protagonist (maturation path) and an existing world clock.
- Prerequisite: base_timestamp; user_character; at least 12 characters with entity rows (characters[0..1]); at least one world-time chunk
- Repair steps:
  1. Use the seeded disposable clone from file_notes.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_wizard_genesis_checkpoint_carries_seeded_project_through_replay`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.8; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body also has a latent test defect. To 'force a fresh highest-id prologue' it clears authorial_directives @> '["retrograde_prologue"]', but the production marker is RETROGRADE_PROLOGUE_MARKER = 'orrery:retrograde_prologue_anchor' (nexus/agents/orrery/retrograde_markers.py), so the UPDATE is a no-op against a real prologue. It then calls persist_retrograde_history (wizard settings from nexus.toml, create_entity_stubs, genesis checkpoint), expects a second call to raise 'already exists at prologue chunk', applies a project advance at a fabricated chunk, and expects verify_checkpoints_sync to report no drift.
- Prerequisite: base_timestamp; user_character (create_entity_stubs path); at least 12 characters with entity rows (characters[0]); at least one world-time chunk; no existing 'genesis' checkpoint
- Repair steps:
  1. Use the seeded disposable clone from file_notes.
  1. Replace the stale '["retrograde_prologue"]' literal with json.dumps([RETROGRADE_PROLOGUE_MARKER]) so the fresh-prologue premise holds when a seeded prologue exists.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_writer_dedup_cap_disabled_and_unresolvable_are_loud`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body is dry-run only: it uses characters[0..3] and [8], checks duplicate-actor, cap and disabled drops plus their logs, and expects 'unresolvable target' for 'No Such Person'. It needs only resolvable character names and base_timestamp.
- Prerequisite: at least 12 characters with entity rows and distinct resolvable names (characters[0..3], [8]); base_timestamp
- Repair steps:
  1. Use the seeded disposable clone from file_notes.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_writer_inserts_all_types_and_started_events`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. This test is why the fixture wants 12 characters and 2 places: _all_type_specs uses characters[0..5] as actors and [8..11] plus places[0] as targets for all six project types. It runs dry_run=False and asserts next_eligible_at_world_time == base_timestamp + 24h, that source_chunk_id is the prologue chunk, and that started events have source 'retrograde'.
- Prerequisite: base_timestamp (asserted non-NULL); at least 12 characters with entity rows; at least 1 place with an entity row and a resolvable name (places[0])
- Repair steps:
  1. Use the seeded disposable clone from file_notes, with 12 NPCs and 2 places.

#### `tests/test_orrery/test_retrograde_projects_live.py::test_writer_rejects_project_participants_in_death_plan`

- Baseline outcome: error; signature: `failed on setup with "assert 0 >= 12`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Setup error from the 12-character assertion on the empty save_02 copy. The body calls only _validate_project_start_dependencies, a read-only validation, with characters[0], [8] and [9], and expects death_plan participant rejections.
- Prerequisite: at least 10 characters with entity rows (the fixture demands 12)
- Repair steps:
  1. Use the seeded disposable clone from file_notes.

#### `tests/test_orrery/test_reveal_live.py::test_async_authoring_grants_unpossessed_holder`

- Baseline outcome: failure; signature: `assert None is not None`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: This test does not use live_conn. It opens asyncpg.connect(**asyncpg_kwargs(slot_dbname(5))), which goes through the connection contract but is still hardwired to slot 5. After installing the claim-accounts and backstory shadows, it looks up an existing clock and holder: the latest chunk_metadata row with non-null world_time, cross-joined with the first character entity. The empty save_05 has neither, so fetchrow returns None and `assert clock is not None` fails with the recorded 'assert None is not None'. The #922 triage recorded the same class-a failure in the owner's environment.
- Prerequisite: One narrative_chunks row with a chunk_metadata row carrying world_time, and one entities row with kind='character' (a characters row is optional for this path). A seeded base_timestamp is recommended for determinism.
- Repair steps:
  1. Connect to the shared disposable clone with asyncpg.connect(**tests.pg_fixtures.asyncpg_kwargs(dbname)), or nexus.database.asyncpg_kwargs(dbname).
  1. Better: insert the chunk (narrative_chunks plus chunk_metadata) and a character entity inside the rolled-back transaction, then read world_time back, instead of discovering 'the latest' clock and 'the first' character from slot contents.

#### `tests/test_orrery/test_reveal_live.py::test_authored_and_revealed_secrets_replay_between_checkpoints`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The live_conn fixture opens psycopg2.connect(get_slot_db_url(slot=5), cursor_factory=RealDictCursor), hardwiring slot 5. It then installs throwaway-schema copies of migrations 090/091/092 and the valence shadow. _insert_chunk works on the empty slot because refresh_world_time_from_chunk falls back to now() when base_timestamp is NULL (023_orrery_schema.py); the sibling test test_verify_skips_checkpoint_that_predates_backstory_section uses only _insert_chunk and was green in the baseline. _insert_private_incident then runs `SELECT id FROM places ORDER BY id LIMIT 1`, which returns no row on the empty save_05, so cur.fetchone()['id'] raises TypeError: 'NoneType' object is not subscriptable. The #922 triage recorded the same class-a 'Empty save_05' failure in the owner's environment, so this body has not run past the places lookup there either.
- Prerequisite: At least one places row with an entity (entities kind='place' plus places(name, type='fixed_location', entity_id)) for characters.current_location. Everything else (chunks, three characters, world_event, claim, checkpoints) the test creates itself. base_timestamp is optional (trigger falls back to now()) but should be seeded for determinism.
- Repair steps:
  1. Apply the file-level fixture repair: disposable clone, connect through tests.pg_fixtures.connect(dbname, cursor_factory=RealDictCursor), seed a place.
  1. Better: have _insert_private_incident create its own place (entities kind='place' plus a places row) instead of selecting the first existing one.

#### `tests/test_orrery/test_reveal_live.py::test_authoring_grants_unpossessed_holder_and_reveal_completes`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: Hardwired slot-5 live_conn fixture. _insert_chunk succeeds (the world_time trigger falls back to now()), then _insert_private_incident's `SELECT id FROM places ORDER BY id LIMIT 1` returns no row on the empty save_05, and cur.fetchone()['id'] raises TypeError: 'NoneType' object is not subscriptable. author_backstory_secret_sync and drain_backstory_reveals_sync are never reached.
- Prerequisite: One places row with an entity (or the helper creating its own place).
- Repair steps:
  1. Apply the file-level fixture repair (disposable clone plus a seeded or helper-created place).

#### `tests/test_orrery/test_reveal_live.py::test_authoring_rejects_non_private_and_unregistered_gate`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The first _insert_private_incident call (scope='bounded') runs `SELECT id FROM places ... LIMIT 1` on the empty slot-5 save and gets None, so cur.fetchone()['id'] raises TypeError. The ValueError contracts ('must be private', 'Unregistered reveal gate') are never reached.
- Prerequisite: One places row with an entity (or the helper creating its own place).
- Repair steps:
  1. Apply the file-level fixture repair (disposable clone plus a seeded or helper-created place).

#### `tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Same helper failure. _insert_private_incident cannot find any places row in the empty slot-5 save, so fetchone() is None and ['id'] raises TypeError. commit_orrery_tick_sync with reveal_settings is never reached.
- Prerequisite: One places row with an entity (or the helper creating its own place).
- Repair steps:
  1. Apply the file-level fixture repair (disposable clone plus a seeded or helper-created place).

#### `tests/test_orrery/test_reveal_live.py::test_same_tick_reveal_waits_until_next_tick_to_propagate`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.85; runtime confirmation needed
- Cause: Same helper failure. _insert_private_incident's first-place lookup returns None on the empty save_05, raising TypeError: 'NoneType' object is not subscriptable. The contagion, distortion and reveal ordering assertions never run.
- Prerequisite: One places row with an entity. The test also creates an outsider character and a public character_relationships row via _insert_relationship (relationship_producer 'manual'), plus the pg_temp valence shadow; both are handled inside the test.
- Repair steps:
  1. Apply the file-level fixture repair (disposable clone plus a seeded or helper-created place).

#### `tests/test_orrery/test_reveal_live.py::test_unregistered_gate_in_latent_row_raises_loudly`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: _insert_private_incident fails on the empty slot-5 places table with a TypeError subscripting None. The RuntimeError('Unregistered reveal gate') contract in drain_backstory_reveals_sync is never reached.
- Prerequisite: One places row with an entity (or the helper creating its own place).
- Repair steps:
  1. Apply the file-level fixture repair (disposable clone plus a seeded or helper-created place).

#### `tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[primary-settings1]`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: Same _insert_private_incident failure: there is no places row in the empty save_05, so fetchone() is None and ['id'] raises TypeError. The disabled-config latent assertion never runs.
- Prerequisite: One places row with an entity (or the helper creating its own place).
- Repair steps:
  1. Apply the file-level fixture repair (disposable clone plus a seeded or helper-created place).

#### `tests/test_orrery/test_reveal_live.py::test_world_layer_and_disabled_config_leave_secret_latent[retrograde-settings0]`

- Baseline outcome: failure; signature: `TypeError: 'NoneType' object is not subscriptable`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: Same _insert_private_incident failure on the empty slot-5 places table (TypeError subscripting None). The retrograde-layer tick chunk would get a non-null world_time from the trigger, so the helper's own assert is not the problem.
- Prerequisite: One places row with an entity (or the helper creating its own place).
- Repair steps:
  1. Apply the file-level fixture repair (disposable clone plus a seeded or helper-created place).

#### `tests/test_orrery/test_seek_redemption_async.py::test_async_seek_redemption_three_write_completion`

- Baseline outcome: failure; signature: `ValueError: not enough values to unpack (expected 2, got 0)`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The test connects to the literal owner slot name via asyncpg.connect(**asyncpg_kwargs('save_02')), a #922 repair that fixed the connection adapter but kept the slot. Inside a rolled-back transaction it takes the first two characters with entity_id (`SELECT entity_id FROM characters ... ORDER BY id LIMIT 2`) and unpacks them with `actor, target = (... for row in entities)`. The empty private save_02 has no characters, which gives ValueError: not enough values to unpack (expected 2, got 0). It also needs the latest chunk_metadata row with world_time; int(None) would fail next. #922 recorded it as class e (asyncpg adapter) and repaired it, so it passes on the owner's populated save_02. No commit after b0645daf touches it.
- Prerequisite: Two characters rows, each with an entities row (kind='character'); one narrative_chunks plus chunk_metadata row with non-null world_time; the 'grudge_active' tag in the tags seed vocabulary (from the template); the character_relationships table (the test deletes and inserts the pair).
- Repair steps:
  1. Use a disposable template clone (disposable_slot_database) and connect with asyncpg_kwargs(clone_dbname).
  1. Seed two characters with entities (seed_protagonist plus one more character) and one chunk with chunk_metadata world_time (shared seed_chunk helper). Pass their ids in rather than selecting 'first two characters' and 'latest chunk'.
  1. Keep SET LOCAL nexus.write_producer = 'manual' for the fixture relationship writes.

#### `tests/test_orrery/test_seek_redemption_projects.py::test_existing_negative_relationship_is_repaired_and_originals_survive_rewrite`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Setup error in the live_redemption_db fixture. It opens psycopg2.connect(get_slot_db_url(slot=2)) (hardwired slot 2), builds the shadow schema (event_types, orrery_resolutions, character_project_states, then migration 087), and runs `SELECT entity_id FROM characters WHERE entity_id IS NOT NULL ORDER BY id LIMIT 2`. It then unpacks `actor, target = (int(row[0]) for row in cur.fetchall())`, which raises ValueError: not enough values to unpack (expected 2, got 0) on the empty private save_02. The next line (`int(cur.fetchone()[0])` on the latest world_time chunk) would also fail. #922 classified these nodes as class g (missing write_producer) and repaired them, so they pass on the populated save_02.
- Prerequisite: Two characters with entity rows; one chunk with chunk_metadata world_time; 'grudge_active' tag seed vocabulary; character_relationships and entity_tags tables (template).
- Repair steps:
  1. Apply the file-level live_redemption_db repair (disposable clone, two seeded characters, one seeded chunk).

#### `tests/test_orrery/test_seek_redemption_projects.py::test_fresh_completion_inserts_reconciliation_and_absent_grudge_is_noop`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.93
- Cause: Same live_redemption_db setup failure: the first-two-characters unpack on the empty slot-2 save raises ValueError (expected 2, got 0) before the test body runs.
- Prerequisite: Two characters with entity rows; one chunk with chunk_metadata world_time; 'grudge_active' in tags.
- Repair steps:
  1. Apply the file-level live_redemption_db repair.

#### `tests/test_orrery/test_seek_redemption_replay.py::test_seek_redemption_completion_replays_without_drift`

- Baseline outcome: error; signature: `failed on setup with "ValueError: not enough values to unpack (expected 2, got 0)"`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: This file borrows the live_redemption_db fixture through pytest_plugins = ('tests.test_orrery.test_seek_redemption_projects',), so it inherits the same setup failure: the hardwired slot 2 and the first-two-characters unpack give ValueError (expected 2, got 0) on the empty private save_02. It has a second latent empty-slot hazard: _fabricate_chunk (imported from test_pursue_romance_replay) inserts narrative_chunks with id = `max(id) + 1`, which is NULL on an empty table. A repaired fixture must therefore seed at least one chunk, which it will, or that helper must COALESCE.
- Prerequisite: Everything live_redemption_db needs (two characters with entities, one chunk with world_time, grudge_active tag), plus at least one existing narrative_chunks row so _fabricate_chunk's max(id)+1 is not NULL; public orrery_resolutions and state_checkpoints tables (template).
- Repair steps:
  1. Apply the live_redemption_db repair in test_seek_redemption_projects.py; this node follows it.
  1. Optionally harden _fabricate_chunk in tests/test_orrery/test_pursue_romance_replay.py to use COALESCE(max(id), 0) + 1, or the sequence, so it does not depend on slot contents.
  1. Consider moving live_redemption_db into a shared helper module or conftest rather than loading a test module through pytest_plugins.

#### `tests/test_orrery/test_signal_events.py::test_async_commit_emits_signal_rows_live`

- Baseline outcome: failure; signature: `IndexError: list index out of range`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The test hand-builds an asyncpg connection to database f'save_{WRITE_SLOT:02d}' = save_02 from PGHOST/PGUSER. It omits the port and relies on asyncpg's own PGPORT fallback, bypassing the nexus.database contract (a #804 concern). The connection did succeed in the baseline. It then reads `SELECT max(id) FROM narrative_chunks` (None on the empty private save_02) and the first two character entities (none), and indexes rows[0][0], rows[1][0], which raises IndexError: list index out of range. It was not red in the owner's #922 triage, so it passes on the populated save_02.
- Prerequisite: One narrative_chunks row with chunk_metadata (world_time) to act as the anchor tick chunk; two characters with active entity rows so _validate_entity_ids and _entity_names can resolve them; event_types for retaliation_attempted and threat_issued (template seed, or ensured by _ensure_event_type).
- Repair steps:
  1. Connect with asyncpg.connect(**tests.pg_fixtures.asyncpg_kwargs(clone_dbname)) against a disposable template clone instead of hand-building a save_02 connection.
  1. Seed two characters with entities and one chunk with metadata (shared helpers), and pass those ids in place of max(id) and 'first two characters'.

#### `tests/test_orrery/test_signal_events.py::test_committed_signal_feeds_consumer_gates_live`

- Baseline outcome: failure; signature: `ValueError: not enough values to unpack (expected 2, got 0)`
- Route: `seed_disposable_clone` to #885; confidence 0.92
- Cause: The test hand-builds psycopg2.connect(host=PGHOST, database='save_02', user=PGUSER, port=PGPORT), outside the connection contract (#804 secondary). It reads max(id) from narrative_chunks (None) and the first two character entities, then unpacks `(avenger,), (target,) = cur.fetchall()`, which raises ValueError: not enough values to unpack (expected 2, got 0) on the empty private save_02. commit_orrery_tick_sync is never reached. It passes on the owner's populated save_02.
- Prerequisite: One narrative_chunks row with chunk_metadata world_time as the anchor or tick chunk; two characters with active entity rows; retaliation_attempted and threat_issued event types.
- Repair steps:
  1. Use tests.pg_fixtures.connect(clone_dbname) on a disposable template clone.
  1. Seed two characters and one chunk and use their ids; keep the rollback.

#### `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly`

- Baseline outcome: error; signature: `failed on setup with "TypeError: cannot unpack non-iterable NoneType object"`
- Route: `seed_disposable_clone` to #885; confidence 0.92; runtime confirmation needed
- Cause: Setup error in the status_delta_db fixture. It connects via get_slot_db_url(slot=5) (hardwired slot 5) and inserts its own character and faction entities, which works. It then selects the latest chunk_metadata row with non-null world_time and unpacks `chunk, world_time = cur.fetchone()`. The empty save_05 has no chunks, so fetchone() returns None and the unpack raises TypeError: cannot unpack non-iterable NoneType object. #922 recorded the identical class-a 'Empty save_05' error in the owner's environment.
- Prerequisite: One narrative_chunks row with chunk_metadata carrying world_time (the source_chunk_id and applied_at_world_time for entity_pair_tags); pair_tags seed rows status:junior and status:respected (template seed vocab).
- Repair steps:
  1. Apply the file-level status_delta_db repair (disposable clone plus one seeded chunk whose world_time the fixture reads back).

#### `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways`

- Baseline outcome: error; signature: `failed on setup with "TypeError: cannot unpack non-iterable NoneType object"`
- Route: `seed_disposable_clone` to #885; confidence 0.92; runtime confirmation needed
- Cause: Same status_delta_db setup failure: no chunk_metadata row with world_time exists on the empty slot-5 save, so `chunk, world_time = cur.fetchone()` unpacks None.
- Prerequisite: One chunk with chunk_metadata world_time; pair_tags status:* seed rows.
- Repair steps:
  1. Apply the file-level status_delta_db repair.

#### `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance`

- Baseline outcome: error; signature: `failed on setup with "TypeError: cannot unpack non-iterable NoneType object"`
- Route: `seed_disposable_clone` to #885; confidence 0.92; runtime confirmation needed
- Cause: Same status_delta_db setup failure, a TypeError from unpacking None, because the empty save_05 has no clocked chunk. The provenance assertion compares applied_at_world_time with the fixture's world_time, so the seeded chunk's world_time must be read back from chunk_metadata after the trigger runs, not assumed.
- Prerequisite: One chunk with chunk_metadata world_time; pair_tags status:junior seed row.
- Repair steps:
  1. Apply the file-level status_delta_db repair and read world_time back from chunk_metadata for the equality assertion.

#### `tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size`

- Baseline outcome: failure; signature: `AssertionError: save_05 must contain current entity tags`
- Route: `parametrize_slot_or_fixture` to #885; confidence 0.85; runtime confirmation needed
- Cause: This read-only probe is deliberately bound to the owner's native QA slot. It is gated by skipif(NEXUS_RUN_POSTGRES != '1') rather than the requires_postgres marker, and it connects through tag_library._connect('save_05'). It takes up to 5 entity refs from entity_tags_current and the latest chunk_metadata anchor with a non-NULL world_time, then asserts that the contextual library's name index equals read_tag_library() and that its o200k token count is at most 50% of the full library. In the private cluster, save_05 is an empty template clone with no entity_tags, so the first precondition assertion 'save_05 must contain current entity tags' fires before any rendering. The file was last touched by 725d4203 (#930, prompt registry), before b0645daf; nothing on main changes this.
- Prerequisite: at least 1 active entity (up to 5 used) with current entity_tags rows; at least one chunk with chunk_metadata.world_time as the anchor; the template-seeded tags, tag_category_registry, pair_tags and event_types registry
- Repair steps:
  1. Point the test at a disposable_slot_database('tag_library') clone registered in VALID_DBNAMES. Seed base_timestamp and a protagonist (seed_protagonist), 4 more characters or places, one world-time chunk, and a handful of tags on those entities through nexus.agents.orrery.tag_writer.apply_tag_bestowal.
  1. Keep the completeness and ≤50% assertions unchanged. They are properties of the renderer over the template-seeded registry, which is the same registry save_05 carries.
  1. Optionally keep the real save_05 size print as a separate corpus-flag-gated probe (e.g. NEXUS_RUN_CORPUS=1).
  1. Switch the skipif to pytestmark requires_postgres to match the gate convention.

#### `tests/test_orrery/test_tag_provenance.py::test_chunk_keyed_bestowal_without_metadata_leaves_world_time_null`

- Baseline outcome: failure; signature: `AssertionError: save_02 is expected to hold at least two characters`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The whole module writes to the owner's save_02 inside rolled-back transactions through a hand-built psycopg2.connect(database=f'save_{WRITE_SLOT:02d}', ...), which is a #804 connection-contract smell. _anchor_and_actors asserts that 2 characters with entity_id exist. The empty private save_02 has none, so the assertion 'save_02 is expected to hold at least two characters' fires immediately. This test then inserts a narrative chunk without metadata and expects apply_tag_bestowal('off_grid') to stamp source_chunk_id with a NULL applied_at_world_time. Only the actor and the template-registered 'off_grid' tag are needed. The file is unchanged since the graft root 76dcd7ff, and no later commit touches it.
- Prerequisite: base_timestamp (the need-sync trigger on tag writes needs a world clock anchor); at least 2 active character entities with characters rows; template-seeded 'off_grid' tag
- Repair steps:
  1. Apply the file-level fixture from file_notes: a module-scoped disposable clone, seed_protagonist plus one NPC plus one world-time chunk, and pg_fixtures.connect(dbname) in place of the hand-built _connect.

#### `tests/test_orrery/test_tag_provenance.py::test_entity_context_reports_exact_provenance_tier`

- Baseline outcome: failure; signature: `AssertionError: save_02 is expected to hold at least two characters`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: Same _anchor_and_actors assertion (two characters) against the empty save_02, reached through create_engine(get_slot_db_url(slot=2)), which also hardwires the owner slot. The test applies 'off_grid' at the max(id) anchor chunk and expects audit.entity_context to report the fresh row as provenance 'exact'. It needs a real anchor chunk; max(id) is NULL on an empty table.
- Prerequisite: base_timestamp; at least 2 characters with entity rows; at least one narrative chunk (ideally with chunk_metadata.world_time) as max(id) anchor; 'off_grid' tag
- Repair steps:
  1. Use the module clone from file_notes and build the engine from tests.pg_fixtures.sqlalchemy_url(dbname) instead of get_slot_db_url(slot=2).

#### `tests/test_orrery/test_tag_provenance.py::test_resolver_commit_stamps_bestowal_provenance`

- Baseline outcome: failure; signature: `AssertionError: save_02 is expected to hold at least two characters`
- Route: `seed_disposable_clone` to #885; confidence 0.88; runtime confirmation needed
- Cause: The _anchor_and_actors two-character assertion fails on the empty save_02. After that, the test would apply an inbound 'hunting' pair tag (template-seeded pair_tags), commit an evade_pursuers draft through commit_orrery_tick_sync at the max(id) anchor chunk, and assert that entity_tags.applied_at_world_time == the anchor chunk's chunk_metadata.world_time and that the pair-tag clear is logged with mechanism 'authored'. The slot=2 argument is unused by the sync commit body, so repointing to a clone is safe.
- Prerequisite: base_timestamp; user_character (safe for commit-side canonical-player lookups); at least 2 characters with entity rows; an anchor chunk with chunk_metadata.world_time as max(id); template 'off_grid' tag and 'hunting' pair tag
- Repair steps:
  1. Use the module clone from file_notes and ensure the seeded chunk has chunk_metadata.world_time (insert then UPDATE idiom), so the equality assertion is not vacuously NULL == NULL.

#### `tests/test_orrery/test_tag_provenance.py::test_tag_writer_clears_are_logged_and_bestowals_stamped`

- Baseline outcome: failure; signature: `AssertionError: save_02 is expected to hold at least two characters`
- Route: `seed_disposable_clone` to #885; confidence 0.9; runtime confirmation needed
- Cause: The _anchor_and_actors two-character assertion fails on the empty save_02. After that, the test applies and clears 'off_grid' and bestows and clears a 'hunting' pair tag at the max(id) anchor, and checks tag_clearance_log rows. Its `if counters['applied']: assert world_time is not None` requires the anchor chunk to carry chunk_metadata.world_time.
- Prerequisite: base_timestamp; at least 2 characters with entity rows; an anchor chunk with chunk_metadata.world_time; template 'off_grid' and 'hunting' vocabulary
- Repair steps:
  1. Use the module clone from file_notes.

#### `tests/test_place_tag_manifest.py::test_cli_place_apply_dry_run_skips_unreviewed_slot2_manifest`

- Baseline outcome: failure; signature: `assert 0 > 0`
- Route: `seed_disposable_clone` to #885; confidence 0.9
- Cause: cli.run_place_apply(slot=2) builds a place manifest from save_02's places and dry-runs it. The empty private save_02 has no places, so no review-required operations are generated, counters['review_required_operations_skipped'] is 0, and 'assert 0 > 0' fails. The sibling test_cli_place_manifest_returns_live_slot2_payload passed because it asserts no content.
- Prerequisite: At least one place entity and places row whose summary/current_status/secrets/extra_data prose matches registered place tags (for example 'off-grid safehouse and transit hub', 'Hidden escape shaft'), so prose candidates are review_required, or a legacy place_affordance entity_tag. The template's tag_category_registry must register the place categories.
- Repair steps:
  1. Seed a template clone with a place (a zone/place through seed_transitioned_story, or a direct places insert with an entity) carrying prose from test_place_manifest_suggests_registered_place_tags_from_prose.
  1. Route slot 2 to the clone (monkeypatch slot_utils.slot_dbname and VALID_DBNAMES) and relax any 'save_02' expectations.

#### `tests/test_prose_metrics_pg.py::test_metrics_cli_on_disposable_corpus`

- Baseline outcome: failure; signature: `subprocess.CalledProcessError: Command '['/Users/pythagor/Library/Caches/pypoetry/virtualenvs/nexus-XhmFBQ1L-py3.11/bin/python', 'scripts/qa_shift/prose_metrics.py', '...`
- Route: `seed_disposable_clone` to #885; confidence 0.8; runtime confirmation needed
- Cause: The test clones save_04 (include_data=True) and runs scripts/qa_shift/prose_metrics.py with check=True. The empty private clone has no playable chunks, so corpus_report raises ValueError('No playable chunks in <db> for requested range') (scripts/qa_shift/prose_metrics.py:374), the script exits non-zero, and subprocess.run raises CalledProcessError. The signature is truncated, so the stderr text needs a run to confirm. Later assertions need real corpus shape: database_chunk_count > measured chunks > 0 (a non-playable prologue chunk), choice_object.presented menus with a positive mean count, storyteller_text words, and world_time for world_minutes_per_turn. The stamp step needs a tail chunk.
- Prerequisite: Several playable narrative_chunks with storyteller_text and choice_object {'presented': [...]}. chunk_metadata world_time on each. Setting place_chunk_references. One Retrograde prologue chunk (RETROGRADE_PROLOGUE_MARKER) so total > measured. A story pin for stamp_lore_pass_baseline.
- Repair steps:
  1. Use a template clone plus seed_transitioned_story and a seed_accepted_chunks helper that writes storyteller_text, choice_object.presented, world_time and setting references for about 5 chunks, plus one prologue-marker chunk.
  1. Optionally run the script with check=False and assert returncode == 0 with stderr in the message, so future failures show the script's own error.
