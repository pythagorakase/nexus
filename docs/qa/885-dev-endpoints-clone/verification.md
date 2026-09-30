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
| `seed_entity_tag(Tobias, "kin_protector")` | 1 | durable tag with `applied_at_world_time` NULL; the tag the validation test carries into its layer-mismatch and no-op rejections |
| `seed_routine_anchor(Oda, Fixture Plaza, "work")` | 1 | a routine winner (`routine_commute`) whose AND gate passes through `NOT(has_inbound_pair_tag(hunting))`; the winner the kill test targets |
| `seed_pair_tag(Ines -> Tobias, "hunting")` | 1 | a hunted subject: `NOT(has_inbound_pair_tag(hunting))` closes every other package to Tobias |
| `seed_entity_tag(Tobias, "immobile")` (review round 2) | 1 | a gap actor: `evade_pursuers` requires `NOT(is_constrained())`, so the hunted, immobile Tobias fires nothing at any anchor and the coverage report's `gap_actors` names him |
| `seed_adjudication_rulings(surveil, {actor: Ines, target: Oda}, [(8, defer), (9, defer), (10, void)])` | 3 `orrery_adjudication_log` rows | a defer streak (length 2, outcome `void`) and a non-empty `surveil` filter for the adjudication history |

`seed_adjudication_rulings` is new in `tests/pg_fixtures.py` (review round 1). It writes each ruling through the production log writer `_insert_adjudication_log_sync` with the `explicit` source and the resolver's `binding_hash(bindings)`, refuses owner databases (it joins `SEED_CALLS` in `tests/test_pg_disposable_target.py`, whose tripwire proves the refusal happens before any connection), and accepts only `defer` and `void`. The existing `seed_adjudication_ledger` could not serve: it refuses a save that holds pending resolutions (the played story commits 28, all but one `pending`), and its tick commits would add resolutions that habituation debits, moving the head-anchor winners the other guards measure. A void commits no resolution, so the rulings leave the resolver's selection unchanged (the head winners and the joint beat below are the same with and without them).

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

Review round 1 (`885-B2-8-fix/evidence.py`, same seed plus the rulings):

```
story SeededAuditStory(dbname='qa885_orrery_dev_evidence_45ba2aff603c', chunk_ids=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), protagonist_entity_id=2, cast_entity_ids={'Ines Marr': 4, 'Tobias Vey': 5, 'Oda Kell': 6}, ruled_proposal_id='surveil:9bf7751734d4fe6f6b8c19f3e77cd99a8ec75a52c32235042732e4a3a833b4e2')
[4] NOT(hunting) winners [('Ines Marr', 'sleep'), ('Oda Kell', 'routine_commute')]
[4] kill: inject hunting Ines->Oda; Oda baseline routine_commute -> winner None changed ['routine_commute', 'drink', 'socialize', 'eat', 'sleep', 'run_errands', 'stroll', 'upkeep']
[6] durable tags [('Ines Marr', ['sleep_deprived_2_moderate']), ('Tobias Vey', ['kin_protector', 'sleep_deprived_2_moderate']), ('Oda Kell', ['sleep_deprived_2_moderate'])]
[9] history totals {'defer': 2, 'replace': 0, 'void': 1} epoch {'log_rows_total': 3, 'log_rows_with_subject': 3}
[9] defer_streaks [('surveil', 'Ines Marr', 2, 'void', 8, 9, 10)]
[9] surveil filter templates {'surveil': {'defer': {'explicit': 2}, 'replace': {}, 'void': {'explicit': 1}}} streaks 1
[1] head winners unchanged [('Ines Marr', 'sleep'), ('Oda Kell', 'routine_commute'), ('Tobias Vey', 'evade_pursuers')] joint beats 1
[10] coverage anchors [5, 10] gap_actors []
[10] coverage anchors [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] gap_actors []
```

| # | Guard (map condition) | Measured |
| --- | --- | --- |
| 1 | production resolutions and scene pressures > 0 | 4 resolutions, 4 scene pressures (1 template, 3 need); 5 resolutions before review round 2, when Tobias still won `evade_pursuers` |
| 2 | at least two off-screen actor groups | 3 (Ines, Tobias, Oda); since review round 2 Tobias's group has no winner |
| 3 | actors are named characters | all 3 `kind == "character"` with names |
| 4 | an off-screen winner gated on top-level `NOT(has_inbound_pair_tag(hunting))` plus a second off-screen subject | Ines `sleep` (from sleep-debt accrual) and Oda `routine_commute` (from the routine anchor); the kill test now selects Oda's `routine_commute` explicitly (subject Ines), and the injection empties Oda's stack (winner `None`) |
| 5 | sleep debt 500 flips an off-screen sleep stack; present actors at the anchor | Oda's stack: `sleep` joins `changed_template_ids` (winner stays `routine_commute`); protagonist present; `need_pressures_diff.changed` = 1 (`sleep_need_pressure`) |
| 6 | an audited actor carries a durable tag | Tobias `kin_protector`, which the validation test now selects explicitly (entity 5, tag `kin_protector`); each cast member also carries an accrued `sleep_deprived_2_moderate`, which the test no longer uses |
| 7 | an active tag bestowed with NULL world time | 2 of 5 active `entity_tags` rows (entity 5 `kin_protector` and, since review round 2, `immobile`); 1 of 4 before |
| 8 | at least 7 playable chunks | 10 (stride-3 sampling expects `[4, 7, 10]`) |
| - | joint beats (not a map condition; added) | 1 `crossed` beat |
| - | adjudication history content (not a map condition; added in review round 1) | 3 log rows (2 defer, 1 void), all with a subject; 1 defer streak (`surveil`, Ines, length 2, ticks 8-9, outcome `void` at 10); the `surveil` filter returns exactly that template and streak |
| - | coverage `gap_actors` (not a map condition) | since review round 2: Tobias, gapped at 2 of 2 sampled anchors (`[5, 10]`) and at 10 of 10 over anchors 1-10; the coverage test asserts he is listed before its `for gap in payload["gap_actors"]` loop runs (empty before round 2; see below) |

For comparison, the played story alone (no relationship, friendship, tag, anchor, or pair tag; `probe_bare.log`) gives 3 resolutions but only the 3 need pressures, no joint beat, and `(0, 3)` NULL-world-time/active tag rows: guard 7 and the joint-beat guard would fail without the extra seeds.

Two more negative checks (each reverted): removing the friendship seeds fails `test_joint_beats_parity_with_production[seeded_story]` with its vacuity message; removing `seed_entity_tag` fails `test_coverage_data_quality_matches_sql_oracle` with its vacuity message.

Review round 1 negative checks, each on a copy of the module restored afterward, each under `-p tests.dbname_audit` (owner targets: none each time):

```
--- no routine anchor
E       AssertionError: the worker yields no routine_commute winner gated on NOT(has_inbound_pair_tag(hunting)) — the what-if kill test is vacuous; the worker's routine anchor should yield that routine winner
1 failed, 7 warnings in 3.70s
--- no entity tag
E       AssertionError: the quarry does not carry its seeded durable kin_protector tag in the audit context — layer-mismatch and no-op rejection checks are vacuous; seed_entity_tag should bestow it
1 failed, 7 warnings in 4.32s
--- no rulings
E       AssertionError: the seeded rulings should log two defers and a void
1 failed, 7 warnings in 3.64s
```

Before round 1 (by the selection logic and evidence lines [4] and [6] above; not rerun), removing the routine anchor or `seed_entity_tag` would not have failed those two tests: the kill test took the first candidate, Ines's accrued `sleep` winner and the validation test took Ines's accrued `sleep_deprived_2_moderate`, so their vacuity messages named seeds the tests did not depend on.

### Coverage `gap_actors` (Resolved in Review Round 2)

Through review round 1 the coverage test's `for gap in payload["gap_actors"]` loop ran zero times: every cast member fired a need or routine template at every anchor 1-10. Review round 2 makes it non-vacuous (it does not merely guard an empty loop). `seed_entity_tag(Tobias, "immobile")` constrains the hunted quarry: `NOT(has_inbound_pair_tag(hunting))` already closed every other package to him, and `evade_pursuers` requires `NOT(is_constrained())`, so he fires nothing. The test now asserts the quarry's entity ID is in `gap_actors` (vacuity message names the seed) before the loop checks `0 < gapped_anchors <= seen_anchors`. Measurements and the negative check are under Review Round 2.

## The Three Formerly Vacuous Tests

| Test | Before on empty `save_05` | Now asserts against |
| --- | --- | --- |
| `test_resolve_parity_with_production_resolver[seeded_story]` (was `[5]`) | anchor None, empty winner and pressure sets on both sides 4 winner drafts since review round 2 (5 before; template, binding hash, branch, magnitude, event type, changed fields, state delta, rendered stub) and 4 pressure drafts (magnitude, prompt text) at head chunk 10 |
| `test_coverage_head_anchor_reconciles_with_production` | `anchor_chunk_id is None` -> `continue` | asserts the oracle anchors on the seeded head chunk (the `continue` is now an assertion), then band tallies == 4 resolutions (5 before review round 2) |
| `test_joint_beats_parity_with_production[seeded_story]` (was `[5]`) | empty beat sets on both sides | asserts production composes at least one beat (new vacuity guard), then the endpoint's beat set equals production's (1 `crossed` beat) |

`test_adjudication_history_endpoint_over_http` failed on the empty `save_05`; after round 0 it passed on the clone but its content checks were still empty (no log rows: the streak loop ran zero times, the `surveil` filter compared an empty set, and the epoch check compared `0 >= 0`). Since review round 1 it asserts against the seeded rulings: totals `defer 2, replace 0, void 1`; `log_rows_total == log_rows_with_subject == 3`; `defer_streaks` non-empty, and its one streak is the seeded proposal (`surveil`, Ines, length 2, ticks 8-9, outcome `void` at tick 10); the `surveil` filter returns exactly `{"surveil"}` with actions `defer {explicit: 2}, void {explicit: 1}` and that one streak. The base assertions stay.

## Names

`LIVE_SLOT` is `ROUTED_SLOT`; `slot=5` / `?slot=5` literals use it. The module docstring and every vacuity message that named `save_05` now name the seeds. The three parametrized ids `[5]` are `[seeded_story]`. No test deleted, no `pytest.skip`, 19 collected. Separately, the scene-pressure parity loop's variable is renamed (`pressure_draft`) so mypy passes on the file (the reuse of `draft` for two draft types was a pre-existing mypy error on `main`).

## Owner Snapshot (`save_05`, Read-Only)

`885-B2-8/snapshot.sh` in the session scratchpad (two `psql -d save_05` SELECTs): `pg_sequences` last values and the four counts. Round 0 took `before.txt` before the first seeded run and `after.txt` after every PostgreSQL gate (the offline gates were still running then); review round 1 took a fresh pair in `885-B2-8-fix/`, `before.txt` before its first seeded run and `after.txt` after its last gate (PostgreSQL and offline). Verbatim:

```
$ md5 885-B2-8/before.txt 885-B2-8/after.txt        # round 0
MD5 (885-B2-8/before.txt) = 7ed0b42c4767818fcf7365fbe7a88405
MD5 (885-B2-8/after.txt) = 7ed0b42c4767818fcf7365fbe7a88405
$ cd 885-B2-8-fix && md5 before.txt after.txt; diff before.txt after.txt; echo "diff exit $?"   # round 1
MD5 (before.txt) = 7ed0b42c4767818fcf7365fbe7a88405
MD5 (after.txt) = 7ed0b42c4767818fcf7365fbe7a88405
diff exit 0
```

All four files have the same md5, so each is this listing:

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

Review round 1 (after the fixes; `seed_adjudication_rulings` adds one `SEED_CALLS` case, so 56 rather than 55):

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa885_orrery_dev_*, qa885_transaction_writer_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
56 passed, 7 warnings in 8.27s
$ $PY -m pytest -q tests/test_pg_disposable_target.py tests/test_pg_target_contract.py tests/test_pg_adjudication_ledger_seed.py
FAILED tests/test_pg_target_contract.py::test_tests_never_hardcode_the_owner_postgres_endpoint
FAILED tests/test_pg_target_contract.py::test_tests_never_read_the_pg_environment_directly
FAILED tests/test_pg_target_contract.py::test_tests_never_spell_a_postgres_url_with_a_target
3 failed, 138 passed, 7 skipped, 5 warnings in 4.07s
$ $PY -m pytest -q tests/test_api tests/test_orrery
1806 passed, 737 skipped, 7 warnings in 31.13s
$ $PY -m black --check tests/pg_fixtures.py tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py   # 3 files would be left unchanged
$ $PY -m flake8 tests/pg_fixtures.py tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py          # clean
$ $PY -m mypy tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py   # Success: no issues found in 2 source files (follows into tests.pg_fixtures)
```

The three contract failures are the same pre-existing ones (only `tests/test_dbname_audit.py` and `tests/dbname_audit.py` are flagged). The `tests/test_api` PostgreSQL sweep and the offline `tests --ignore=...` run below are from round 0 and were not rerun for round 1.

Round 0:

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

The 10 red on `save_05` (`test_slots_jointly_exercise_both_parity_contracts`, `test_resolve_four_template_states_are_distinguishable`, `test_entity_context_hover_payload`, `test_entity_context_recent_events_respect_anchor`, `test_what_if_pair_tag_injection_kills_a_winner`, `test_what_if_need_override_reaches_stacks_and_pressures`, `test_what_if_validation_rejections`, `test_coverage_report_is_internally_consistent[5]` (now `[seeded_story]`), `test_coverage_data_quality_matches_sql_oracle`, `test_coverage_anchor_cap_and_sampling`), plus the 3 vacuous passes above and the 3 remaining PostgreSQL tests (`test_current_mode_carries_no_what_if_payload`, `test_adjudication_history_endpoint_over_http`, `test_vocab_endpoint_serves_picker_vocabularies`) that read `save_05`: all 16 PostgreSQL tests in the module now run on the clone. `test_adjudication_history_endpoint_over_http`'s streak and filter checks now iterate over seeded rulings (review round 1); since review round 2 the coverage test's `gap_actors` check runs over the seeded gap actor (above).

## Review Round 2

Merged `origin/main` at `f78eb0c2` (B2-7 #1041 and the connection-audit contract fix #1043) into the branch with a merge commit, not a rebase (the branch is pushed). The merge was clean; `tests/pg_fixtures.py` had no conflict. Three findings applied, plus the `gap_actors` note from round 1:

1. **P2, mypy on `seed_adjudication_rulings`.** `mypy --explicit-package-bases tests/pg_fixtures.py` reported `tests/pg_fixtures.py:1710: error: Argument 1 to "binding_hash" has incompatible type "dict[str, Any]"; expected "dict[Slot, Any]"`. The helper now builds the hash input keyed by `Slot` (`{Slot(slot): value for slot, value in bindings.items()}`), as the resolver does (`nexus/agents/orrery/resolver.py:2771`, `:3314`); no cast, no `type: ignore`. `binding_hash` serializes `Slot.value`, so the digest is unchanged: the seeded proposal ID below matches round 1's, `surveil:9bf77517...`. An unknown slot name now raises `ValueError` from `Slot(...)` instead of being hashed.
2. **P3, PR body guard table.** The guard-4 row named the pre-round-1 kill-test candidate (Ines, with Tobias as subject). It now names what the code and guard row 4 above use: Oda's `routine_commute`, with Ines as subject.
3. **P3, import order.** `seed_adjudication_rulings` sat between `seed_played_story` and `seed_relationship` in the `tests.pg_fixtures` import block of `test_orrery_dev_endpoints.py`; the block is alphabetical again.
4. **Coverage `gap_actors`: non-vacuous, and asserted.** A new seed makes the loop iterate over a real gap actor, and the test asserts that gap actor is present (details above).

`885-B2-8-r2/evidence.py` in the session scratchpad (round 0's and round 1's measurements over the round-2 seed):

```
story SeededAuditStory(dbname='qa885_orrery_dev_evidence_64429d5e8e1a', chunk_ids=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), protagonist_entity_id=2, cast_entity_ids={'Ines Marr': 4, 'Tobias Vey': 5, 'Oda Kell': 6}, ruled_proposal_id='surveil:9bf7751734d4fe6f6b8c19f3e77cd99a8ec75a52c32235042732e4a3a833b4e2')
[1] anchor=10 resolutions=4 scene_pressures=4
    resolution surveil {'actor': 'Ines Marr', 'target': 'Oda Kell'}
    resolution reach_out {'actor': 'Oda Kell', 'target': 'Ines Marr'}
    resolution routine_commute {'actor': 'Oda Kell'}
    resolution sleep {'actor': 'Ines Marr'}
    pressure surveil {'actor': 'Ines Marr', 'target': 'Fixture Player'} 0.38
    pressure sleep_need_pressure {'actor': 'Fixture Player', 'resource': 'sleep'} 0.65
    pressure hunger_need_pressure {'actor': 'Fixture Player', 'resource': 'hunger'} 0.75
    pressure thirst_need_pressure {'actor': 'Fixture Player', 'resource': 'thirst'} 0.75
    joint_beats [('crossed', 'Ines Marr', 'surveil', 'Oda Kell', 'reach_out')]
[2] off-screen actor groups=3 [('Ines Marr', 'sleep'), ('Tobias Vey', None), ('Oda Kell', 'routine_commute')]
[3] kinds/names [('Ines Marr', 'character'), ('Tobias Vey', 'character'), ('Oda Kell', 'character')]
[4] NOT(hunting) winners [('Ines Marr', 'sleep'), ('Oda Kell', 'routine_commute')]
[5] present at anchor=['Fixture Player'] sleep debts=[('Fixture Player', 0.0), ('Ines Marr', 42.0), ('Tobias Vey', 39.0), ('Oda Kell', 42.0)]
    sleep flips=[('Oda Kell', 'routine_commute', 'routine_commute', ['sleep'])]
    need_pressures_diff added=0 changed=1 removed=0 ['sleep_need_pressure']
[6] durable tags [('Ines Marr', ['sleep_deprived_2_moderate']), ('Tobias Vey', ['kin_protector', 'sleep_deprived_2_moderate']), ('Oda Kell', ['sleep_deprived_2_moderate'])]
[7] active entity_tags null_world_time/active=(2, 5) rows=[(5, 'kin_protector'), (5, 'immobile')]
[8] playable chunks=10
[4] kill: inject hunting Ines->Oda; Oda baseline routine_commute -> winner None changed ['routine_commute', 'drink', 'socialize', 'eat', 'sleep', 'run_errands', 'stroll', 'upkeep']
[6] durable tags [('Ines Marr', ['sleep_deprived_2_moderate']), ('Tobias Vey', ['kin_protector', 'sleep_deprived_2_moderate']), ('Oda Kell', ['sleep_deprived_2_moderate'])]
[9] history totals {'defer': 2, 'replace': 0, 'void': 1} epoch {'log_rows_total': 3, 'log_rows_with_subject': 3}
[9] defer_streaks [('surveil', 'Ines Marr', 2, 'void', 8, 9, 10)]
[9] surveil filter templates {'surveil': {'defer': {'explicit': 2}, 'replace': {}, 'void': {'explicit': 1}}} streaks 1
[1] head winners unchanged [('Ines Marr', 'sleep'), ('Oda Kell', 'routine_commute'), ('Tobias Vey', None)] joint beats 1
[10] coverage anchors [5, 10] gap_actors [{'entity_id': 5, 'name': 'Tobias Vey', 'seen_anchors': 2, 'gapped_anchors': 2}]
[10] gap actor names [('Tobias Vey', 2, 2)]
[10] coverage anchors [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] gap_actors [{'entity_id': 5, 'name': 'Tobias Vey', 'seen_anchors': 10, 'gapped_anchors': 10}]
[10] gap actor names [('Tobias Vey', 10, 10)]
```

Negative check (on a copy restored afterward): the module without `seed_entity_tag(Tobias, "immobile")`:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit "tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent"
                stats["won"] <= stats["fired"] <= stats["gate_passed"] <= stats["evaluated"]
            f"the quarry is not a gap actor ({gap_actor_ids!r}) — the gap_actors "
E       AssertionError: the quarry is not a gap actor ([]) — the gap_actors check is vacuous; the hunted, immobile quarry should fire nothing at any anchor
tests/test_api/test_orrery_dev_endpoints.py:993: AssertionError
1 failed, 7 warnings in 3.65s
```

Gates (gateway variables unset):

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa885_orrery_dev_*, qa885_transaction_writer_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
56 passed, 7 warnings in 7.87s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q --collect-only tests/test_api/test_orrery_dev_endpoints.py
19 tests collected in 0.03s
$ $PY -m pytest -q tests/test_pg_disposable_target.py tests/test_pg_target_contract.py tests/test_pg_adjudication_ledger_seed.py
142 passed, 7 skipped, 5 warnings in 3.81s
$ $PY -m pytest -q tests/test_api tests/test_orrery
1806 passed, 737 skipped, 7 warnings in 30.07s
$ mypy --explicit-package-bases tests/pg_fixtures.py tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py
Success: no issues found in 3 source files
$ black --check tests/pg_fixtures.py tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py
All done! ✨ 🍰 ✨
3 files would be left unchanged.
$ flake8 tests/pg_fixtures.py tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py
flake8 exit 0
```

The three `tests/test_pg_target_contract.py` failures that rounds 0 and 1 reported are gone: #1043 fixed them on `main`. The `tests/test_api` PostgreSQL sweep and the offline `tests --ignore=...` run were not rerun for round 2.

`save_05` snapshot (`885-B2-8-r2/snapshot.sh`): `before.txt` was taken before the evidence run and `after.txt` after the gate rerun. The two files are byte-identical (54 lines; `diff` empty). Tail:

```
narrative_chunks 0
entities 0
orrery_resolutions 0
orrery_scene_pressures 0
```


## Review Round (Astra)

Astra's review of head `201ebd7f` (`CHANGES_REQUIRED`) raised two findings, both in `tests/test_api/test_orrery_dev_endpoints.py`. Both are fixed; no seed was added, since the played story already records world events for every cast member.

| Finding | Before | Now asserts |
| --- | --- | --- |
| P2: recent-event anchor coverage accepted `recent_events: []` at every anchor | `test_entity_context_recent_events_respect_anchor` looped over each entity's events (zero iterations when empty) and `test_entity_context_hover_payload` checked only `len(...) <= 3` | the anchor test requests the page limit (`RECENT_EVENTS_PROBE_LIMIT = 50`), asserts the returned entity IDs equal the requested IDs (sorted) at both the head and genesis anchors, and asserts at least one seeded actor has a nonzero event count at the head before checking every entity is empty at anchor 0; the hover test asserts at least one hovered actor carries a recent event; both vacuity messages name `seed_played_story` |
| P3: place vocabulary accepted `places: []` | `all(row["name"] ...)` over an empty list | `{"Fixture Plaza", "Fixture Docks"} <= {row["name"] ...}` (the two places `seed_played_story` creates) before the name check |

### Recorded Events at the Head Anchor

Scratch probe (`885-B2-8-fix3/probe_counts.log`; a temporary print in the anchor test, reverted afterwards): head anchor 10, recorded events per actor with the limit at 50:

```
PROBE head_anchor 10 {'Ines Marr': 10, 'Tobias Vey': 10, 'Oda Kell': 9}
```

The events are the accepted ticks' need and routine events (`drank`, `slept`, `ate`, `socialized`, `stroll_taken`, `upkeep_done`) over ticks 2-10, plus one `contact_made` (Ines -> Tobias, tick 2). At anchor 0 all three are empty.

### Negative Control

Scratch run (`885-B2-8-fix3/negative_control.log`): the entity-context query's result was replaced with `[]` in `nexus/agents/orrery/audit.py` (`events_by_entity[entity_id] = []`) and the vocab endpoint returned `"places": []` in `nexus/api/orrery_dev_endpoints.py`. Both edits were reverted with `git checkout --` afterwards (`git diff --stat` then showed only the test file).

```
E       AssertionError: no hovered actor carries a recent event — the recent-event checks are vacuous; the seed_played_story accepted ticks record world events for the off-screen cast
E       AssertionError: no seeded actor has a recorded event at the head anchor ({4: 0, 5: 0, 6: 0}) — the genesis exclusion check is vacuous; the seed_played_story accepted ticks record world events for the off-screen cast
E       AssertionError: the seeded places are missing from the place vocabulary — the name check is vacuous; seed_played_story creates both
E       assert {'Fixture Doc...ixture Plaza'} <= set()
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_hover_payload
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_recent_events_respect_anchor
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_vocab_endpoint_serves_picker_vocabularies
3 failed, 16 deselected, 7 warnings in 4.11s
```

Under the same two edits, the test file at `201ebd7f` passes all three (`885-B2-8-fix3/base_negative_control.log`: `3 passed, 16 deselected, 7 warnings in 3.93s`), which confirms the findings.

### Gates

Gateway variables unset:

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p tests.dbname_audit tests/test_api/test_orrery_dev_endpoints.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
dbname audit: 3 targets: postgres, qa885_orrery_dev_*, qa885_transaction_writer_*
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
56 passed, 7 warnings in 8.97s
$ black --check tests/test_api/test_orrery_dev_endpoints.py
All done! ✨ 🍰 ✨
1 file would be left unchanged.
$ flake8 tests/test_api/test_orrery_dev_endpoints.py
flake8: clean
$ mypy --explicit-package-bases tests/test_api/test_orrery_dev_endpoints.py
Success: no issues found in 1 source file
```
