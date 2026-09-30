# Read-Only Content Assumptions Move to Seeded Clones: Verification

Work order 885-B2-7. Issue #885 (slice B2, item 7). Base: `origin/main` at 016e6956 (B2-4 landed, so `seed_pair_tag` and `seed_routine_anchor` are available). Test-only; no migration; TEST provider only, no paid calls; no gateway lane (the manifest modules call `cli.run_*` in process and start no gateway).

## What Was Wrong

- `tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end` opened `get_slot_db_url(slot=5)` and failed on the empty `save_05` with `save_05 is expected to bind off-screen actors`.
- `tests/test_orrery/test_tag_library.py`: `test_contextual_library_save_05_completeness_and_size` failed with `save_05 must contain current entity tags`; `test_contextual_library_save_05_kosi_uses_character_entity_id` hit `pytest.skip` on the empty slot. Both used an environment `skipif`, not `requires_postgres`, and both passed `"save_05"` to `tag_library._connect`.
- `tests/test_orrery/test_retrograde_vocabulary.py::test_seed_eligible_vocabulary_can_include_live_tag_registry` read `save_02` (`enumerate_seed_eligible_vocabulary(dbname="save_02")`, line 59).
- `tests/test_place_tag_manifest.py` and `tests/test_character_tag_manifest.py` ran `cli.run_place_manifest`, `run_place_apply`, and `run_character_manifest` against `save_02` (`TEST_DBNAME = "save_02"`, `slot=2`), used `pytest.skip` on `psycopg2.Error`, and asserted `review_required_operations_skipped > 0`, which only the owner's content made true.

## What Each Test Now Rests On

| Module | Clone and route | Seeds | What the assertions now name |
| --- | --- | --- | --- |
| `test_evidence` | `qa885_evidence`, slot 5 | protagonist "Evidence Hunter"; characters Mourner, Quarry, Homebody, Bystander; `grieving` (ephemeral, asserted at seed time) on Mourner; `hunting` pair tag Hunter to Quarry (asserted active and ephemeral); a `work` routine anchor with `works_from_home` on Homebody | The actor groups are exactly {Mourner, Quarry, Homebody}, one per anchor-less path (`resolver.py` `compose_actor_bindings`); Bystander is not bound; every leaf carries evidence; more than 100 leaves are checked |
| `test_tag_library` (completeness) | `qa885_tag_library`, slot 5 (function-scoped fixture) | `seed_checkpointed_story` | The current-tag reference is exactly the confidant (`kin_protector`); the anchor is the head chunk; `kin_protector` and the `recently_violent` proposal render; the name index is complete; contextual is at most 50% of the full library (measured 3012 vs 6406 o200k tokens) |
| `test_tag_library` (namespace) | same fixture | zone; place "Namespace Refuge" (entity 1); protagonist (`characters.id` 1, entity 2); story clock; `kin_protector` on the character entity; `haven` on place entity 1 | The skewed pair is asserted to exist (the former skip); `kin_protector` renders and `haven` does not. Mutation check: replacing `_translate_entity_row_refs` with the identity makes the test fail with `assert {'kin_protector'} <= {'haven'}` |
| `test_retrograde_vocabulary` | `qa885_retrograde_vocab`, slot 2 | protagonist carrying `grieving` (asserted current in `entity_tags_current`) | Every original registry assertion, unchanged |
| `test_place_tag_manifest` | `qa885_place_manifest`, slot 2 (module-scoped, `MonkeyPatch.context`) | zone; "Quiet Lot" (summary "Fixture lot.", legacy `worksite` via `seed_deprecated_category_tag`); "Lantern Clinic" (summary "A hidden clinic.") | Manifest: exactly three review-required operations, named: Quiet Lot `worksite` to `production` (legacy map), Lantern Clinic keyword `clinic` to `place_medical`, keyword `hidden` to `place_hidden`; all registered targets; `review_required_operations == 3`. Apply dry run: `ready == 0`, `review_required_operations_skipped == 3`, `entity_tags_would_insert == 0`, and the apply's operation ids equal the manifest's, each `skipped_review_required` |
| `test_character_tag_manifest` | `qa885_character_manifest`, slot 2 (module-scoped) | "Fixture Android" (`bodyform:android`, deprecated `bodyform`), "Fixture Debtor" (`debt_pulse_active`, deprecated `orrery_signal`), "Fixture Drifter" (`off_grid`, live `orrery_state`), "Fixture Hunter" (`hunter`, watched collision), and a control "Fixture Guardian" (`kin_protector`) | Exactly four operations, named: android to `inorganic` (`bodyform.lineage`, registered), `structured_remainder`, `preserve_prose`, `hunter` reviewed in place; the control is absent; `legacy_character_tag_rows == 4`, `review_required_operations == 4`, no missing targets |

The `review_required_operations == 5` in `test_character_manifest_canonicalizes_resolved_collision_names` counts the five in-memory rows that test passes to `build_character_migration_manifest_from_rows`, not owner rows, so it stays as written. The seeded counts above are in the PostgreSQL tests. The `execute=True` refusal test is unchanged.

The row-builder and fake-backed tests never open a database. Their `"save_05"`/`"save_02"` labels became non-owner labels (`FAKE_DBNAME`, `LABEL_DBNAME`, `"fake_retrograde_db"`), so the owner-literal grep is empty in every converted file.

```
$ grep -n "save_0\|NEXUS_template\|get_slot_db_url(slot=\|slot_dbname([1-5])\|TEST_DBNAME = \"save" <each of the five files>
(no output)
$ grep -n "pytest.skip\|skipif\|psycopg2.Error" <each of the five files>
(no output)
```

## Proof

### The Order's PostgreSQL Command

Gateway variables unset (`env | grep -E "NEXUS_GATEWAY_PORT|NEXUS_API_URL|NEXUS_RUN_LIVE"` printed nothing).

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery/test_evidence.py \
    tests/test_orrery/test_tag_library.py tests/test_orrery/test_retrograde_vocabulary.py \
    tests/test_place_tag_manifest.py tests/test_character_tag_manifest.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 14 targets: postgres, qa640_811_full_clear_only_*, qa640_811_scene_clear_only_*, qa640_811_scene_kind_*, qa640_811_scene_pin_*, qa640_811_seed_policy_*, qa640_811_tag_library_*, qa885_character_manifest_*, qa885_evidence_*, qa885_place_manifest_*, qa885_retrograde_vocab_*, qa885_tag_library_* x2, qa885_transaction_writer_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
187 passed, 5 warnings in 21.94s
```

### Full Orrery PostgreSQL Tier

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 220 targets: postgres, qa638_*, qa640_* x18, qa640_781_cards_* x6, qa640_800_operator_*, qa640_807_boundary_*, qa640_807_latest_playable_*, qa640_807_maturation_boundary_*, qa640_807_reapply_*, qa640_811_full_clear_only_*, qa640_811_gaia_scene_*, qa640_811_scene_clear_only_*, qa640_811_scene_kind_*, qa640_811_scene_pin_*, qa640_811_seed_policy_*, qa640_811_tag_library_*, qa640_bleed_acceptance_*, qa640_bleed_proximity_* x4, qa640_claim_accounts_*, qa640_claim_consumption_*, qa640_communication_graph_*, qa640_drift_* x2, qa640_ecology_*, qa640_geo_resolver_*, qa640_grieving_migration_*, qa640_issue601_* x4, qa640_maturation799_*, qa640_mig077_*, qa640_mig084_*, qa640_mig085_*, qa640_mig086_*, qa640_mig087_*, qa640_mig088_*, qa640_mig090_*, qa640_mig091_*, qa640_mig092_*, qa640_mig095_*, qa640_mig096_*, qa640_need_absence_* x7, qa640_orbit_distance_*, qa640_pair_tag_predicates_*, qa640_pair_tag_substrate_*, qa640_projects799_*, qa640_provenance_* x3, qa640_reconstruction_*, qa640_replay_*, qa640_retrieval_* x2, qa640_retro078_* x13, qa640_roster798_* x23, qa640_status_bestow_*, qa640_vocab_migration_* x6, qa640_weather_migration_*, qa640_wizard_drain_* x3, qa640_worker_*, qa665_*, qa672_*, qa676_* x7, qa679_*, qa735_gis_stubs_* x5, qa735_mood_*, qa735_pair_tags_* x10, qa735_weather_*, qa885_adjudication_history_*, qa885_build_venture_*, qa885_build_venture_async_*, qa885_build_venture_replay_*, qa885_claim_awareness_replay_*, qa885_court_patron_* x2, qa885_court_patron_async_*, qa885_distortion_*, qa885_epistemics_*, qa885_evidence_*, qa885_faction_contexts_*, qa885_knowledge_surfacing_*, qa885_patron_circle_*, qa885_project_promotion_*, qa885_pursue_romance_*, qa885_pursue_romance_async_*, qa885_pursue_romance_replay_*, qa885_recruit_ally_projects_*, qa885_recruit_ally_replay_*, qa885_retrograde_vocab_*, qa885_reveal_*, qa885_seek_redemption_* x2, qa885_seek_redemption_async_*, qa885_signal_events_*, qa885_stage2a_epistemics_*, qa885_tag_library_* x2, qa885_tag_provenance_*, qa_wt720_*, qa_wt723_*, qa_wt724_experience_* x26, qa_wt724_recall_*, test_event_sources_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
1634 passed, 40 skipped, 7 warnings in 337.30s (0:05:37)
```

There were no failures. The 40 skips fall into three classes: 37 are `live_llm` tests (`NEXUS_RUN_LIVE_LLM` unset; the markers stay by policy); 2 are the `requires_corpus` probes (`test_projects.py:609`, `test_recruit_ally_projects.py:808`, "Set NEXUS_RUN_CORPUS=1"); and 1 is `test_retrograde_retrieval_live.py` (`NEXUS_RETROGRADE_RETRIEVAL_TEST_DB_URL is not configured`).

### Owner Slots Before and After

`snapshot.sh` runs `SET default_transaction_read_only = on` and then, on `save_02` and `save_05`, lists every `pg_sequences` row and `count(*)` of `entities`, `entity_tags`, and `narrative_chunks`. The first snapshot was taken before any test run of this branch, and the second at 05:41 UTC, after the slice gate, the full Orrery tier, and both offline gates. `diff before.txt after.txt` printed nothing, and both files hash to `16e6be48754290407985ecf91f4d71d1`. Other builders were running at the same time, so identical snapshots prove only that nobody wrote in this window. The audit's `owner targets: none` above is the proof that holds regardless of concurrency.

#### `save_02`

| Object | Before | After |
| --- | --- | --- |
| `assets.character_images_id_seq` | 1 | 1 |
| `assets.place_images_id_seq` | NULL | NULL |
| `public.ai_notebook_id_seq` | NULL | NULL |
| `public.backstory_secrets_id_seq` | NULL | NULL |
| `public.character_experience_jobs_id_seq` | NULL | NULL |
| `public.character_experiences_id_seq` | NULL | NULL |
| `public.character_identity_rulings_id_seq` | NULL | NULL |
| `public.character_project_states_id_seq` | 3454 | 3454 |
| `public.character_relationships_id_seq` | 7 | 7 |
| `public.character_routine_anchors_id_seq` | NULL | NULL |
| `public.characters_id_seq` | 101 | 101 |
| `public.chunk_metadata_id_seq` | 8682 | 8682 |
| `public.claim_awareness_id_seq` | 1044 | 1044 |
| `public.claims_id_seq` | 475 | 475 |
| `public.correspondence_compaction_jobs_id_seq` | NULL | NULL |
| `public.entities_id_seq` | 561 | 561 |
| `public.entity_pair_tags_id_seq` | 3528 | 3528 |
| `public.entity_tags_id_seq` | 1157 | 1157 |
| `public.generation_session_phases_id_seq` | NULL | NULL |
| `public.interaction_authorizations_id_seq` | NULL | NULL |
| `public.interaction_events_id_seq` | NULL | NULL |
| `public.interaction_participants_id_seq` | NULL | NULL |
| `public.items_id_seq` | NULL | NULL |
| `public.layers_id_seq` | 1 | 1 |
| `public.narrative_chunks_id_seq` | 2624 | 2624 |
| `public.narrative_embedding_jobs_id_seq` | NULL | NULL |
| `public.narrative_summary_jobs_id_seq` | NULL | NULL |
| `public.offscreen_narrations_id_seq` | NULL | NULL |
| `public.orrery_adjudication_log_id_seq` | 567 | 567 |
| `public.orrery_maturation_jobs_id_seq` | 504 | 504 |
| `public.orrery_narration_jobs_id_seq` | NULL | NULL |
| `public.orrery_prompt_exposures_id_seq` | 3244 | 3244 |
| `public.orrery_recall_trace_id_seq` | NULL | NULL |
| `public.orrery_resolutions_id_seq` | 7378 | 7378 |
| `public.orrery_route_graph_edges_id_seq` | NULL | NULL |
| `public.orrery_route_graph_nodes_id_seq` | NULL | NULL |
| `public.orrery_scene_pressures_id_seq` | 567 | 567 |
| `public.orrery_travel_edges_id_seq` | NULL | NULL |
| `public.pair_tags_id_seq` | 29 | 29 |
| `public.places_id_seq` | 4 | 4 |
| `public.relationship_versions_id_seq` | 100142 | 100142 |
| `public.retrieval_coverage_log_id_seq` | 52 | 52 |
| `public.retrograde_summaries_id_seq` | 1435 | 1435 |
| `public.state_checkpoints_id_seq` | 2982 | 2982 |
| `public.state_delta_log_id_seq` | 33 | 33 |
| `public.storyteller_correspondence_letters_id_seq` | NULL | NULL |
| `public.tag_clearance_log_id_seq` | 1070 | 1070 |
| `public.tags_id_seq` | 556 | 556 |
| `public.world_events_id_seq` | 8182 | 8182 |
| `public.zones_id_seq` | 1 | 1 |
| `count entities` | 121 | 121 |
| `count entity_tags` | 0 | 0 |
| `count narrative_chunks` | 1425 | 1425 |

#### `save_05`

| Object | Before | After |
| --- | --- | --- |
| `assets.character_images_id_seq` | NULL | NULL |
| `assets.place_images_id_seq` | NULL | NULL |
| `public.ai_notebook_id_seq` | NULL | NULL |
| `public.backstory_secrets_id_seq` | NULL | NULL |
| `public.character_experience_jobs_id_seq` | NULL | NULL |
| `public.character_experiences_id_seq` | NULL | NULL |
| `public.character_identity_rulings_id_seq` | NULL | NULL |
| `public.character_project_states_id_seq` | NULL | NULL |
| `public.character_relationships_id_seq` | NULL | NULL |
| `public.character_routine_anchors_id_seq` | NULL | NULL |
| `public.characters_id_seq` | 2524 | 2524 |
| `public.chunk_metadata_id_seq` | 2386 | 2386 |
| `public.claim_awareness_id_seq` | NULL | NULL |
| `public.claims_id_seq` | NULL | NULL |
| `public.correspondence_compaction_jobs_id_seq` | NULL | NULL |
| `public.entities_id_seq` | 5553 | 5553 |
| `public.entity_pair_tags_id_seq` | 780 | 780 |
| `public.entity_tags_id_seq` | 41 | 41 |
| `public.generation_session_phases_id_seq` | NULL | NULL |
| `public.interaction_authorizations_id_seq` | NULL | NULL |
| `public.interaction_events_id_seq` | NULL | NULL |
| `public.interaction_participants_id_seq` | NULL | NULL |
| `public.items_id_seq` | NULL | NULL |
| `public.layers_id_seq` | NULL | NULL |
| `public.narrative_chunks_id_seq` | 2492 | 2492 |
| `public.narrative_embedding_jobs_id_seq` | NULL | NULL |
| `public.narrative_summary_jobs_id_seq` | NULL | NULL |
| `public.offscreen_narrations_id_seq` | NULL | NULL |
| `public.orrery_adjudication_log_id_seq` | NULL | NULL |
| `public.orrery_maturation_jobs_id_seq` | NULL | NULL |
| `public.orrery_narration_jobs_id_seq` | NULL | NULL |
| `public.orrery_prompt_exposures_id_seq` | NULL | NULL |
| `public.orrery_recall_trace_id_seq` | 2184 | 2184 |
| `public.orrery_resolutions_id_seq` | NULL | NULL |
| `public.orrery_route_graph_edges_id_seq` | NULL | NULL |
| `public.orrery_route_graph_nodes_id_seq` | NULL | NULL |
| `public.orrery_scene_pressures_id_seq` | NULL | NULL |
| `public.orrery_travel_edges_id_seq` | NULL | NULL |
| `public.pair_tags_id_seq` | 387 | 387 |
| `public.places_id_seq` | NULL | NULL |
| `public.relationship_versions_id_seq` | 12 | 12 |
| `public.retrieval_coverage_log_id_seq` | NULL | NULL |
| `public.retrograde_summaries_id_seq` | NULL | NULL |
| `public.state_checkpoints_id_seq` | 252 | 252 |
| `public.state_delta_log_id_seq` | NULL | NULL |
| `public.storyteller_correspondence_letters_id_seq` | NULL | NULL |
| `public.tag_clearance_log_id_seq` | 156 | 156 |
| `public.tags_id_seq` | 20092 | 20092 |
| `public.world_events_id_seq` | 3338 | 3338 |
| `public.zones_id_seq` | NULL | NULL |
| `count entities` | 0 | 0 |
| `count entity_tags` | 0 | 0 |
| `count narrative_chunks` | 0 | 0 |

### Offline Gates

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
=========================== short test summary info ============================
FAILED tests/test_pg_target_contract.py::test_tests_never_hardcode_the_owner_postgres_endpoint
FAILED tests/test_pg_target_contract.py::test_tests_never_read_the_pg_environment_directly
FAILED tests/test_pg_target_contract.py::test_tests_never_spell_a_postgres_url_with_a_target
3 failed, 2485 passed, 387 skipped, 8 warnings in 376.27s (0:06:16)
$ $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 737 skipped, 7 warnings in 33.64s
$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 9.61s
```

The three `test_pg_target_contract.py` failures come from main and fall outside this slice. They name only `tests/dbname_audit.py` (lines 181, 182, and 206, which read `PGSERVICE` and `PGDATABASE`) and `tests/test_dbname_audit.py` (lines 126, 244, and 703 to 710, which build loopback `postgresql://…@localhost:5432` URLs and set `PGHOST` and `PGDATABASE`). Both files arrived with B2-6 (eed7c716), and `git diff origin/main -- tests/dbname_audit.py tests/test_dbname_audit.py tests/test_pg_target_contract.py` is empty on this branch.

Black (`5 files left unchanged`), flake8 (exit 0), and `mypy --explicit-package-bases` (`Success: no issues found in 5 source files`) pass on the five changed files. Plain `mypy <files>` stops at `Source file found twice under different module names: "test_orrery" and "tests.test_orrery"`, a module-path issue that has nothing to do with this change.

## Retired #885 Ids

- `tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end`
- `tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size`, renamed `test_contextual_library_seeded_story_completeness_and_size`
- `tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_kosi_uses_character_entity_id` (vacuous skip), renamed `test_contextual_library_skewed_character_row_id_uses_entity_id`
- `tests/test_orrery/test_retrograde_vocabulary.py::test_seed_eligible_vocabulary_can_include_live_tag_registry` (owner read)
- `tests/test_place_tag_manifest.py::test_cli_place_manifest_returns_live_slot2_payload`, renamed `test_cli_place_manifest_returns_seeded_slot_payload`
- `tests/test_place_tag_manifest.py::test_cli_place_apply_dry_run_skips_unreviewed_slot2_manifest`, renamed `test_cli_place_apply_dry_run_skips_unreviewed_seeded_manifest`
- `tests/test_character_tag_manifest.py::test_cli_character_manifest_returns_live_slot2_payload`, renamed `test_cli_character_manifest_returns_seeded_slot_payload`
