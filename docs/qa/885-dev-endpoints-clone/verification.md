# #885 Slice B2-8: The Orrery Dev Endpoint Audit Runs on a Seeded Played Story

Branch `claude/885-dev-endpoints-clone`, rebased onto `origin/main` at `016e6956` (B2-4, #1039, which brought `seed_routine_anchor` and `seed_pair_tag`; no cherry-pick was needed). Test-only; no migration; no paid call (the clone is TEST-pinned by `disposable_slot_database`); no gateway lane (in-process `TestClient` without lifespan). `$PY` is `/Users/pythagor/nexus/.venv/bin/python`, run from the worktree root with `PYTHONPATH=$PWD`; `nexus.__file__` resolves inside the worktree.

## What Was Wrong

`tests/test_api/test_orrery_dev_endpoints.py` set `LIVE_SLOT = 5` and read the owner's `save_05` as a live Orrery story at its head chunk, through the endpoint (`_slot_session` -> `get_slot_db_url(slot=5)`), the `production_proposals` oracle, and three direct `create_engine(get_slot_db_url(slot=...))` reads. `save_05` is an empty story (0 chunks, 0 entities), so 10 of 19 tests failed and 3 passed vacuously (`b2_map.json`; `docs/qa/910-character-tags/review-full-pg-failures.txt` lines 3-12).

## The Seed

A module-scoped fixture `seeded_story` opens `disposable_slot_database("qa885_orrery_dev")`, routes slot 5 to it inside `with pytest.MonkeyPatch.context() as mp: route_slot_to_disposable(mp.setattr, ...)` while it seeds (the accepted turns label their jobs with slot 5), and ends that route before any test runs:

| Seed | Rows | Guard it serves |
| --- | --- | --- |
| `seed_played_story(turns=10, cast=("Ines Marr", "Tobias Vey", "Oda Kell"), time_delta=6 h, slot=5)` | zone, Fixture Plaza (protagonist), Fixture Docks (cast), 10 accepted turns | resolutions, three off-screen actor groups, sleep debt accrual (39-42 per cast member), protagonist need pressures, present actor at the anchor, 10 playable chunks |
| `seed_relationship(Ines -> protagonist, "ally")` | 1 | template scene pressure (`surveil` on the present protagonist) |
| `seed_relationship(Ines <-> Oda, "friend")`, both directions | 2 | a joint beat (`crossed`: Ines `surveil` Oda, Oda `reach_out` Ines) |
| `seed_entity_tag(Tobias, "kin_protector")` | 1 | durable tag with `applied_at_world_time` NULL |
| `seed_routine_anchor(Oda, Fixture Plaza, "work")` | 1 | a routine winner (`routine_commute`) whose AND gate passes through `NOT(has_inbound_pair_tag(hunting))` |
| `seed_pair_tag(Ines -> Tobias, "hunting")` | 1 | a hunted subject (Tobias's winner becomes `evade_pursuers`) |

`seed_need_debt` was **not** added: `time_delta` accrual already pushes the cast's sleep debt to 39-42 and gives the protagonist sleep, hunger, and thirst pressures (below), so the need-pressure and sleep-flip guards hold without it.

### Routing Scope

Each PostgreSQL test takes `routed_story`, a function-scoped fixture that routes slot 5 to the clone with `monkeypatch.setattr` for that test only; `production_proposals` (module-scoped) routes inside its own `MonkeyPatch.context()`. `client` is never routed, and `test_resolve_rejects_invalid_slot` takes no routed fixture. A negative check: giving that test `routed_story` makes it fail with `assert 500 == 400` (the routed resolver raises `RuntimeError` for slot 9, which `orrery_dev_endpoints.py:271-272` maps to a 500); the edit was reverted.

## Every Guard, Measured on the Seeded Clone

`885-B2-8/evidence.py` in the session scratchpad seeds a clone with the test module's own `_seed_audit_story`, routes slot 5 to it, and measures each guard through the same calls the tests make:

```
story SeededAuditStory(dbname='qa885_orrery_dev_evidence_d09ecf0d700a', chunk_ids=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), protagonist_entity_id=2, cast_entity_ids={'Ines Marr': 4, 'Tobias Vey': 5, 'Oda Kell': 6})
[1] anchor=10 resolutions=5 scene_pressures=4
    resolution evade_pursuers {'actor': 'Tobias Vey'}
    resolution surveil {'actor': 'Ines Marr', 'target': 'Oda Kell'}
    resolution reach_out {'actor': 'Oda Kell', 'target': 'Ines Marr'}
    resolution routine_commute {'actor': 'Oda Kell'}
    resolution sleep {'actor': 'Ines Marr'}
    pressure surveil {'actor': 'Ines Marr', 'target': 'Fixture Player'} 0.38
    pressure sleep_need_pressure {'actor': 'Fixture Player', 'resource': 'sleep'} 0.65
    pressure hunger_need_pressure {'actor': 'Fixture Player', 'resource': 'hunger'} 0.75
    pressure thirst_need_pressure {'actor': 'Fixture Player', 'resource': 'thirst'} 0.75
    joint_beats [('crossed', 'Ines Marr', 'surveil', 'Oda Kell', 'reach_out')]
[2] off-screen actor groups=3 [('Ines Marr', 'sleep'), ('Tobias Vey', 'evade_pursuers'), ('Oda Kell', 'routine_commute')]
[3] kinds/names [('Ines Marr', 'character'), ('Tobias Vey', 'character'), ('Oda Kell', 'character')]
[4] NOT(hunting) winners [('Ines Marr', 'sleep'), ('Oda Kell', 'routine_commute')]
[5] present at anchor=['Fixture Player'] sleep debts=[('Fixture Player', 0.0), ('Ines Marr', 42.0), ('Tobias Vey', 39.0), ('Oda Kell', 42.0)]
    sleep flips=[('Oda Kell', 'routine_commute', 'routine_commute', ['sleep'])]
    need_pressures_diff added=0 changed=1 removed=0 ['sleep_need_pressure']
[6] durable tags [('Ines Marr', ['sleep_deprived_2_moderate']), ('Tobias Vey', ['kin_protector', 'sleep_deprived_2_moderate']), ('Oda Kell', ['sleep_deprived_2_moderate'])]
[7] active entity_tags null_world_time/active=(1, 4) rows=[(5, 'kin_protector')]
[8] playable chunks=10
```

| # | Guard (map condition) | Measured |
| --- | --- | --- |
| 1 | production resolutions and scene pressures > 0 | 5 resolutions, 4 scene pressures (1 template, 3 need) |
| 2 | at least two off-screen actor groups | 3 (Ines, Tobias, Oda) |
| 3 | actors are named characters | all 3 `kind == "character"` with names |
| 4 | an off-screen winner gated on top-level `NOT(has_inbound_pair_tag(hunting))` plus a second off-screen subject | Ines `sleep` and Oda `routine_commute`; the kill test takes the first (Ines, subject Tobias) |
| 5 | sleep debt 500 flips an off-screen sleep stack; present actors at the anchor | Oda's stack: `sleep` joins `changed_template_ids` (winner stays `routine_commute`); protagonist present; `need_pressures_diff.changed` = 1 (`sleep_need_pressure`) |
| 6 | an audited actor carries a durable tag | Tobias `kin_protector`; each cast member also carries `sleep_deprived_2_moderate` |
| 7 | an active tag bestowed with NULL world time | 1 of 4 active `entity_tags` rows (entity 5 `kin_protector`) |
| 8 | at least 7 playable chunks | 10 (stride-3 sampling expects `[4, 7, 10]`) |
| - | joint beats (not a map condition; added) | 1 `crossed` beat |

For comparison, the played story alone (no relationship, friendship, tag, anchor, or pair tag; `probe_bare.log`) gives 3 resolutions but only the 3 need pressures, no joint beat, and `(0, 3)` NULL-world-time/active tag rows: guard 7 and the joint-beat guard would fail without the extra seeds.

Two more negative checks (each reverted): removing the friendship seeds fails `test_joint_beats_parity_with_production[seeded_story]` with its vacuity message; removing `seed_entity_tag` fails `test_coverage_data_quality_matches_sql_oracle` with its vacuity message.

## The Three Formerly Vacuous Tests

| Test | Before on empty `save_05` | Now asserts against |
| --- | --- | --- |
| `test_resolve_parity_with_production_resolver[seeded_story]` (was `[5]`) | anchor None, empty winner and pressure sets on both sides | 5 winner drafts (template, binding hash, branch, magnitude, event type, changed fields, state delta, rendered stub) and 4 pressure drafts (magnitude, prompt text) at head chunk 10 |
| `test_coverage_head_anchor_reconciles_with_production` | `anchor_chunk_id is None` -> `continue` | asserts the oracle anchors on the seeded head chunk (the `continue` is now an assertion), then band tallies == 5 resolutions |
| `test_joint_beats_parity_with_production[seeded_story]` (was `[5]`) | empty beat sets on both sides | asserts production composes at least one beat (new vacuity guard), then the endpoint's beat set equals production's (1 `crossed` beat) |

## Names

`LIVE_SLOT` is `ROUTED_SLOT`; `slot=5` / `?slot=5` literals use it. The module docstring and every vacuity message that named `save_05` now name the seeds. The three parametrized ids `[5]` are `[seeded_story]`. No test deleted, no `pytest.skip`, 19 collected. Separately, the scene-pressure parity loop's variable is renamed (`pressure_draft`) so mypy passes on the file (the reuse of `draft` for two draft types was a pre-existing mypy error on `main`).

## Owner Snapshot (`save_05`, Read-Only)

`885-B2-8/snapshot.sh` in the session scratchpad (two `psql -d save_05` SELECTs): `pg_sequences` last values and the four counts, taken before the first seeded run and after every gate below. md5 `7ed0b42c4767818fcf7365fbe7a88405` both times; `diff` empty.

```
assets.character_images_id_seq NULL
assets.place_images_id_seq NULL
public.ai_notebook_id_seq NULL
public.backstory_secrets_id_seq NULL
public.character_experience_jobs_id_seq NULL
public.character_experiences_id_seq NULL
public.character_identity_rulings_id_seq NULL
public.character_project_states_id_seq NULL
public.character_relationships_id_seq NULL
public.character_routine_anchors_id_seq NULL
public.characters_id_seq 2524
public.chunk_metadata_id_seq 2386
public.claim_awareness_id_seq NULL
public.claims_id_seq NULL
public.correspondence_compaction_jobs_id_seq NULL
public.entities_id_seq 5553
public.entity_pair_tags_id_seq 780
public.entity_tags_id_seq 41
public.generation_session_phases_id_seq NULL
public.interaction_authorizations_id_seq NULL
public.interaction_events_id_seq NULL
public.interaction_participants_id_seq NULL
public.items_id_seq NULL
public.layers_id_seq NULL
public.narrative_chunks_id_seq 2492
public.narrative_embedding_jobs_id_seq NULL
public.narrative_summary_jobs_id_seq NULL
public.offscreen_narrations_id_seq NULL
public.orrery_adjudication_log_id_seq NULL
public.orrery_maturation_jobs_id_seq NULL
public.orrery_narration_jobs_id_seq NULL
public.orrery_prompt_exposures_id_seq NULL
public.orrery_recall_trace_id_seq 2184
public.orrery_resolutions_id_seq NULL
public.orrery_route_graph_edges_id_seq NULL
public.orrery_route_graph_nodes_id_seq NULL
public.orrery_scene_pressures_id_seq NULL
public.orrery_travel_edges_id_seq NULL
public.pair_tags_id_seq 387
public.places_id_seq NULL
public.relationship_versions_id_seq 12
public.retrieval_coverage_log_id_seq NULL
public.retrograde_summaries_id_seq NULL
public.state_checkpoints_id_seq 252
public.state_delta_log_id_seq NULL
public.storyteller_correspondence_letters_id_seq NULL
public.tag_clearance_log_id_seq 156
public.tags_id_seq 20092
public.world_events_id_seq 3338
public.zones_id_seq NULL
narrative_chunks 0
entities 0
orrery_resolutions 0
orrery_scene_pressures 0
```

The connection audit (`-p tests.dbname_audit`) is the proof that holds under concurrent builders: its owner-target report for this module is empty (below).

## Gates

Gateway variables unset in every run.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa885_orrery_dev_*, qa885_transaction_writer_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
55 passed, 7 warnings in 8.62s
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest --collect-only -q tests/test_api/test_orrery_dev_endpoints.py
19 tests collected
```

`NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api`, split into four file lists of 17 for the ten-minute shell limit:

```
[chunk aa]
dbname audit: owner targets: none
182 passed, 1 skipped, 9 warnings in 91.64s (0:01:31)
[chunk ab]
SKIPPED [1] tests/test_api/test_narrative_summary_paid_pg.py: Requires explicit two-call summary authorization
dbname audit: FAILED: owner targets: save_02 (psycopg2) from tests/test_api/test_reader_asset_endpoints.py::TestNarrativeReads::test_adjacent, tests/test_api/test_reader_asset_endpoints.py::TestNarrat
15 failed, 190 passed, 1 skipped, 7 warnings in 126.15s (0:02:06)
[chunk ac]
dbname audit: FAILED: owner targets: save_05 (psycopg2) from tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision
4 failed, 154 passed, 9 warnings in 178.45s (0:02:58)
[chunk ad]
FAILED tests/test_api/test_wizard_chat_validation.py::test_repeated_trait_confirmation_reports_wildcard_state
FAILED tests/test_api/test_wizard_chat_validation.py::test_trait_choice_outside_character_reports_current_state
SKIPPED [1] tests/test_api/test_secrets_endpoints.py:268: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
SKIPPED [1] tests/test_api/test_secrets_endpoints.py:279: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.
dbname audit: FAILED: owner targets: save_04 (psycopg2) from tests/test_api/test_wizard_chat_validation.py::test_repeated_trait_confirmation_reports_wildcard_state, tests/test_api/test_wizard_chat_val
2 failed, 318 passed, 2 skipped, 7 warnings in 71.91s (0:01:11)
```

Chunk `aa`'s single skip, from a rerun with `-rs` (182 passed, 1 skipped, owner targets none): `SKIPPED [1] tests/test_api/test_conversations.py:377: Set NEXUS_RUN_LIVE_LLM=1 to run live LLM integration tests.` Every skip in the run is a live-LLM or paid-call gate.

Remaining `tests/test_api` failures, by class (none in files this branch changes; `git diff --stat origin/main` touches only `test_orrery_dev_endpoints.py`, and each file was rerun alone with the same result):

- **Owner read refused by the audit (unrouted owner content):** `test_reader_asset_endpoints.py` x14 (`READ_SLOT = 2`, `save_02`, `TestNarrativeReads` and `TestWorldReads`); `test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision` (`save_05`); `test_wizard_chat_validation.py::test_repeated_trait_confirmation_reports_wildcard_state` and `::test_trait_choice_outside_character_reports_current_state` (`save_04`).
- **`save_04` include_data corpus clones (B2-9, order note 17):** `test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]` and `::test_scheduler_gateway_sigkill_resumes_inflight_experience` ("Scheduler did not reach the expected durable state"); `test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs` (`assert (0 == 0 and 0 >= 1)`: the cloned source is already at head, so the backfill applies nothing).
- **Test double signature drift:** `test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit` (`gated_real_commit() got an unexpected keyword argument 'bind_session_id'`).

Offline:

```
$ $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
FAILED tests/test_pg_target_contract.py::test_tests_never_hardcode_the_owner_postgres_endpoint
FAILED tests/test_pg_target_contract.py::test_tests_never_read_the_pg_environment_directly
FAILED tests/test_pg_target_contract.py::test_tests_never_spell_a_postgres_url_with_a_target
3 failed, 2485 passed, 387 skipped, 8 warnings in 385.03s (0:06:25)
$ $PY -m pytest -q tests/test_api tests/test_orrery
1806 passed, 737 skipped, 7 warnings in 34.05s
$ $PY -m pytest -q tests/test_reachability.py
38 passed in 9.66s
$ $PY -m black --check tests/test_api/test_orrery_dev_endpoints.py   # 1 file would be left unchanged
$ $PY -m flake8 tests/test_api/test_orrery_dev_endpoints.py          # clean
$ $PY -m mypy tests/test_api/test_orrery_dev_endpoints.py            # Success: no issues found in 1 source file
```

The three offline failures are `tests/test_pg_target_contract.py` flagging loopback URLs and PG* reads in `tests/test_dbname_audit.py` and `tests/dbname_audit.py` (both from B2-6, #1038, on `main`; untouched here).

## #885 Ids Retired

The 10 red on `save_05` (`test_slots_jointly_exercise_both_parity_contracts`, `test_resolve_four_template_states_are_distinguishable`, `test_entity_context_hover_payload`, `test_entity_context_recent_events_respect_anchor`, `test_what_if_pair_tag_injection_kills_a_winner`, `test_what_if_need_override_reaches_stacks_and_pressures`, `test_what_if_validation_rejections`, `test_coverage_report_is_internally_consistent[5]` (now `[seeded_story]`), `test_coverage_data_quality_matches_sql_oracle`, `test_coverage_anchor_cap_and_sampling`), plus the 3 vacuous passes above and the 3 remaining PostgreSQL tests (`test_current_mode_carries_no_what_if_payload`, `test_adjudication_history_endpoint_over_http`, `test_vocab_endpoint_serves_picker_vocabularies`) that read `save_05`: all 16 PostgreSQL tests in the module now run on the clone.
