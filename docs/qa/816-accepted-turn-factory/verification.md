# The Accepted-Turn Factory: Verification

Work order 816-B. Issues #816 (production-path factories) and #885 (the `seed_disposable_clone` route). Cut from `origin/main` at 00545d7c, then merged with `origin/main` at 4d4dca91 (migration 134, #1017, which retires `narrative_chunks.state` and `finalized_at`; and the retry-test fix, #1018), so every tail below ran against the post-134 `NEXUS_template` (`schema_migrations` max 134). No migration, no paid calls: every turn runs on the TEST provider. Code HEAD for the gate-tier and offline tails below: `77dc0c64`. The review-fix commit after it changes only the factory's staging guards in `tests/pg_fixtures.py`, the factory's own tests, and this file; the proof set, the per-file tails, and the factory tails below were rerun at that commit.

**Write safety.** Every fixture this PR adds or changes writes only disposable `qa640_*` template clones created and dropped by `tests.pg_fixtures.disposable_slot_database`. No changed test reads or clones `save_04` any more. The gate batches below run the repository's existing suite, whose untouched slot-hardwired files still read or roll back writes on owner slots as inventoried on #885; this PR adds none. `test_knowledge_surfacing_live.py` keeps its pre-existing rollback-only fixture on `save_05` (only its settings harness changed here).

## The Factory's Shape

All three helpers live in `tests/pg_fixtures.py`, call `require_disposable_target` before any connection, and return database IDs.

- `seed_pending_turn(dbname, *, user_text, storyteller_text, choices=None, time_delta=5 min, episode_transition=None, scene_boundary=False, reference_updates=None, entity_updates=None, new_entities=None, correspondence_writer_letter=None, correspondence_gaia_letter=None, generation_model="TEST", resolve_orrery=True) -> session_id`. Stages a draft through the gateway's own steps: `acquire_generation_lease` (a `continue` session owning the slot), `bind_generation_parent` (the playable frontier, or 0 for the bootstrap opening), then `write_to_incubator(..., complete_session=True)`, which runs `validate_commit_draft_sync`, writes the incubator singleton, and completes the session while releasing the lease. The draft has the shape `response_to_incubator` builds: `generation_model` TEST, the staging `session_id`, the unbound empty Pass-2 baseline (`empty_pass2_baseline` under `story_context_settings(load_settings_as_dict(), read_story_settings(dbname))`, the same one bootstrap and `scripts/stamp_lore_pass_baseline.py` stage), and the default empty `authorial_directives`, so the accepted chunk satisfies `playable_narrative_predicate`. A continuation stages the Orrery proposal LORE would stage: `resolve_dry_run` over `BUILTIN_TEMPLATES` at the frontier with the configured Orrery sections (mirroring `TurnCycleManager.resolve_orrery`), serialized by `_serialize_orrery_staging` with an empty Bleed manifest. References default to the canonical player present at their current place. The parent's embedding is not claimed; that is the route's step before generation, not staging or acceptance.
- `seed_accepted_turn(dbname, *, user_text, storyteller_text, choice_text=None, choices=None, slot=None, **staging) -> chunk_id`. Stages with `seed_pending_turn`, records the player's response with the gateway's own `_record_player_response_for_chunk` (a presented choice by number, other text as the player's wording), and commits through `commit_incubator_to_database_sync` on the same connection, as `_resolve_and_approve_pending_sync` does. Chunk and metadata, the trigger-stamped world clock, the bound baseline, sessions, presence and reference rows, the Orrery tick, experience seeds and scene-boundary render jobs, checkpoints, correspondence and compaction, summary scheduling, and the IDF corpus triggers all run as in play. It asserts the accepted chunk, its `choice_text`, the accepted session, one bound baseline, and an empty incubator.
- `seed_played_story(dbname, *, turns, protagonist_name, base_timestamp, time_delta=5 min, cast=(), correspondence=False, slot=None) -> [chunk_id, ...]`. Seeds what the wizard transition leaves (a bounded zone, a located place, the protagonist standing there, the clock at `base_timestamp`), then accepts the bootstrap opening and `turns - 1` continuations. Each turn presents `FIXTURE_TURN_CHOICES` and records the first; each continuation's input is the previous response. `cast` seeds off-screen characters at a second place and mentions them in every turn, which makes them the Orrery's actors, so continuations stage real resolutions and acceptance writes their events and experience seeds. `correspondence` stages writer and Gaia letters with each turn.

Loud preconditions: no world clock (`needs a world clock`), no canonical player (`needs a canonical player`, raised only for `PlayerIdentityNotEstablishedError`; a dangling or entity-less player row or a database error propagates unchanged), a single presented choice (`needs at least two choices`, since the gateway's `extract_choice_object` stages no choice object for fewer than two), an already played save for `seed_played_story` (`needs an unplayed save`), a live lease held by another session (`seed_pending_turn lease conflict`), an already pending draft (`needs an empty incubator: the singleton is owned by session`), and a `slot` label that does not route to the clone (`Slot 4 routes to 'save_04'`). The slot label is stamped on enqueued jobs and handed to the production commit, so it is accepted only while `tests.scheduler_helpers.route_slot` routes it to the clone. `slot=None` is checked as the slot the commit resolves: a declared entity's maturation job is labelled with `get_active_slot()`, so a set `NEXUS_SLOT` must route to the clone too (`Ambient NEXUS_SLOT=4 routes to 'save_04'`); with `NEXUS_SLOT` unset, the commit's own label resolution raises before it enqueues a routed job. The clock, player, choice, lease, and pending-draft checks all run before `acquire_generation_lease`, so those refusals take no lease and open no session. A failure after the lease is taken (a draft `validate_commit_draft_sync` rejects, for example) calls `abandon_generation`, which releases the lease and records the staging session as `error`, then re-raises. The factory reads the validated Orrery settings by index (`settings["orrery"]`, its `enabled`, `bleed`, and `binding.window_chunks`), so a changed settings shape raises a `KeyError` instead of defaulting.

`tests/test_pg_accepted_turn_factory.py` reads the written state back (chunks, slugs, exact world times, bound baselines, accepted sessions, empty incubator and lease, IDF documents, presence counts, setting references, letters, Orrery resolutions from the second turn, cast experience seeds), proves a pending draft is what `continue` accepts (parent, TEST model, presented choices, current config fingerprint, completed session without a lease), records free text as the player's own wording (`narrative_chunks.choice_text` is the typed text, not a presented choice), and proves the refusals are loud and take no lease: the missing-clock and missing-player refusals leave no incubator or session rows; the one-choice and second-draft refusals on a save with a pending draft leave no lease and only the accepted session and the pending one; a live foreign lease refuses the draft with `seed_pending_turn lease conflict` and leaves no incubator row and no session beyond the foreign one. The module clears `NEXUS_SLOT` with an autouse `monkeypatch` fixture, because its tests pass no `slot` and the ambient-slot guard would otherwise refuse an exported owner slot. `tests/test_pg_disposable_target.py` adds the three helpers to its owner-name refusal matrix and two offline tests that refuse, before any connection, an unrouted slot label and (with `slot=None` and a `new_entities` declaration) an unrouted ambient `NEXUS_SLOT=4`.

## What Changed

- `tests/test_orrery/test_retrograde_constraints_pg.py`: the hand-rolled `CREATE DATABASE ... TEMPLATE NEXUS_template` fixture (lines 57-90 on main) re-executed migrations 097 and 123, which the template already carries, and died with `DuplicateColumn` on `character_aliases.provenance`. It now takes `disposable_slot_database("qa640_issue601")` (runner-migrated) and sets the canonical clock with `seed_protagonist(base_timestamp=...)`; the wizard transition's clean slate replaces that placeholder player with the cache's protagonist. No test depended on the pre-097 or pre-123 shape; all four run unchanged.
- `tests/test_orrery/test_knowledge_surfacing_live.py`: the LORE harness now takes `lore.render_limits` from `load_settings_as_dict()` (nexus.toml) instead of omitting it; `turn_cycle.py` is untouched.
- `tests/test_api/test_attempt_manifest_pg.py`: all four tests play their own story. The direct `connect("save_04")` and the corpus hash comparison became a comparison against the factory's chunk IDs, re-read after pruning. The live TEST turn continues a factory-staged pending draft; the fingerprint refresh and the `model`/`gaia_model` repin are gone (the factory stamps under the current settings; the clone default pins TEST). The child-job test gets its seeds from the cast's accepted turns, its relationship from `seed_relationship`, and its boundary chunk from `seed_accepted_turn` (replacing the imported `_insert_chunk`, which stamped a 2196 clock). `--chunk 49` and `id=49` became the factory's first chunk.
- `tests/test_api/test_scheduler_corpus_pg.py`: `_seed_starved_story` plays four cast turns plus a scene reset whose render jobs wait in the queue. "The nine original jobs" became the jobs that reset enqueued (asserted equal to the queued set). The pre-drain maturation precondition is re-scoped: on `save_04` it asserted that the corpus's three maturation jobs had all succeeded (no maturation work owed to the drain); the seeded story declares no new entities, so it now asserts `maturation == []`, the same no-work-owed state stated without a vacuous `all()` over an empty list; the live-turn test stages a pending draft and asserts the deferral touched rows; the lease-recheck test (which failed on main because the clone's jobs were pinned to a paid model) now renders a TEST-pinned job.
- `tests/test_api/test_seat_policy_jobs_pg.py`: plays four cast turns with letters and stages the pending draft; every assertion (four frozen queues, repin immunity, persisted-model dispatch logs, per-job ledger joins) is unchanged.

## Before: Main at 00545d7c

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q \
    tests/test_orrery/test_retrograde_constraints_pg.py tests/test_orrery/test_knowledge_surfacing_live.py
FAILED tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[True]
FAILED tests/test_orrery/test_knowledge_surfacing_live.py::test_turn_payload_conditionally_attaches_world_knowledge[False]
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_packet_and_transition_keep_event_without_adversarial_rows
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_real_cache_compiler_gate_suppresses_all_named_target_materialization
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_persistence_identity_binds_database_alias_without_packet_alias
ERROR tests/test_orrery/test_retrograde_constraints_pg.py::test_seek_redemption_dependency_is_repaired_before_mapper_transaction
2 failed, 2 passed, 5 warnings, 4 errors in 2.51s

$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q \
    tests/test_api/test_attempt_manifest_pg.py tests/test_api/test_scheduler_corpus_pg.py tests/test_api/test_seat_policy_jobs_pg.py
FAILED tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_rechecks_generation_after_leasing_before_provider
1 failed, 7 passed, 9 warnings in 99.70s (0:01:39)
```

The trio passed seven of eight on this machine only because `save_04` holds the owner's played story; the eighth failed on `ProviderForbiddenInTests: Model 'gpt-5.6-terra' (provider='openai') is forbidden by NEXUS_TEST_PROVIDER_ONLY=1`, the clone's inherited paid pin. On a clean machine (the #964 baseline) the turn, scheduler, and seat tests fail outright.

## After: The Proof Set Together

The gate commands unset `NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, and `NEXUS_SLOT`: an exported owner slot is refused by the factory's ambient-slot guard in any test that neither routes nor clears it. Each file in isolation runs under the same environment (`env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q <file>`), except where noted.

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q \
    tests/test_orrery/test_retrograde_constraints_pg.py tests/test_api/test_attempt_manifest_pg.py \
    tests/test_api/test_scheduler_corpus_pg.py tests/test_api/test_seat_policy_jobs_pg.py \
    tests/test_orrery/test_knowledge_surfacing_live.py tests/test_pg_disposable_target.py \
    tests/test_pg_accepted_turn_factory.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
45 passed, 9 warnings in 57.67s

$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q \
    tests/test_orrery/test_retrograde_constraints_pg.py tests/test_api/test_attempt_manifest_pg.py \
    tests/test_api/test_scheduler_corpus_pg.py tests/test_api/test_seat_policy_jobs_pg.py \
    tests/test_orrery/test_knowledge_surfacing_live.py tests/test_pg_disposable_target.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
41 passed, 9 warnings in 55.04s
```

## After: Each File in Isolation

```
== tests/test_orrery/test_retrograde_constraints_pg.py
4 passed, 5 warnings in 6.06s
== tests/test_api/test_attempt_manifest_pg.py
4 passed, 9 warnings in 21.07s
== tests/test_api/test_scheduler_corpus_pg.py
3 passed, 9 warnings in 22.87s
== tests/test_api/test_seat_policy_jobs_pg.py
1 passed, 9 warnings in 15.06s
== tests/test_orrery/test_knowledge_surfacing_live.py
4 passed, 5 warnings in 0.78s
== tests/test_pg_disposable_target.py
25 passed, 5 warnings in 0.32s
== tests/test_pg_accepted_turn_factory.py (run with NEXUS_SLOT=1 exported, to prove the module clears it)
4 passed, 7 warnings in 6.80s
```

## Gate Tiers at the Head

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_[a-o]*.py
FAILED tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
ERROR tests/test_orrery/test_faction_project_contexts_live.py (8 ids, NoResultFound at setup)
2 failed, 794 passed, 29 skipped, 7 warnings, 8 errors in 143.43s (0:02:23)

$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_[p-z]*.py
FAILED tests/test_orrery/test_reveal_live.py (9 ids)
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
10 failed, 810 passed, 10 skipped, 7 warnings, 1 error in 112.89s (0:01:52)

$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_[a-n]*.py
FAILED tests/test_api/test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
1 failed, 310 passed, 2 skipped, 9 warnings in 150.39s (0:02:30)

$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_[o-z]*.py
FAILED tests/test_api/test_orrery_dev_endpoints.py (10 ids)
FAILED tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
FAILED tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs
ERROR tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip (4 ids)
14 failed, 536 passed, 2 skipped, 9 warnings, 4 errors in 245.04s (0:04:05)
```

`tests/test_api` was split into two batches to stay under the ten-minute command limit; together they are 15 failed, 846 passed, 4 skipped, 4 errors.

Every Orrery remainder is the #885 slot-5 content class named in the #885 thread after PR #1015 (`test_reveal_live` x9, `test_faction_project_contexts_live` x8, `test_adjudication_history`, `test_evidence`, `test_tag_library`, `test_polymorphic_patron_live`). `test_retrograde_constraints_pg` runs green inside the `[p-z]` batch.

The `tests/test_api` remainder splits in two:

- #885 slot-5 class (14): the ten `test_orrery_dev_endpoints.py` ids and the four `TestAssetRoundTrip` setup errors in `test_reader_asset_endpoints.py` (`need-clock anchor unavailable`).
- Pre-existing on main, not slot-5 content (5). The same five fail identically on an export of `origin/main` 4d4dca91 (`5 failed, 38 passed, 7 warnings in 99.61s` for those four files plus `test_narrative_retry_pg.py`). The three `test_narrative_retry_pg.py` ids listed here before the merge (`the connection cannot be re-entered recursively`) pass at this head and on 4d4dca91: #1018 fixed them.
  - `test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit` (`AssertionError: []`, after `gated_real_commit() got an unexpected keyword argument 'bind_session_id'`)
  - `test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision` (`assert pending is not None and pending.has_pending` at `test_return_recap_pg.py:527`; the same assertion fails on 4d4dca91)
  - `test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]`, `::test_scheduler_gateway_sigkill_resumes_inflight_experience` (`save_04` data clones; the render job carries the corpus's paid pin, the class this PR fixed in `test_scheduler_corpus_pg`)
  - `test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs` (`assert failed == 0 and applied >= 1`: a restored `save_04` is already fully migrated, so migration 126 has nothing to apply)

Offline and static:

```
$ env -u NEXUS_RUN_POSTGRES $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2319 passed, 323 skipped, 8 warnings in 248.11s (0:04:08)
$ env -u NEXUS_RUN_POSTGRES $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1806 passed, 727 skipped, 7 warnings in 29.14s
$ $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.01s
```

Black leaves every changed file unchanged. At the review-fix commit, flake8 on `tests/pg_fixtures.py` and `tests/test_pg_accepted_turn_factory.py` is clean and `$PY -m mypy -m tests.pg_fixtures -m tests.test_pg_accepted_turn_factory` reports `Success: no issues found in 2 source files`. flake8 on the files the fix commit `77dc0c64` touched reports the same per-file counts before and after it (E501 and F811 only). flake8 on the changed files reports only findings present on main (long SQL lines and the `mock_openai_server` fixture-import F811 pattern); this PR removes four F401s and adds none. mypy (`--explicit-package-bases`) reports nothing in `tests/pg_fixtures.py` or `tests/test_pg_accepted_turn_factory.py`; the remaining reports in the touched test modules (missing `requests` stubs, `WizardCache | None` narrowing in `test_retrograde_constraints_pg.py`) are present on main.

## Audit: `grep -rn "save_04\|slot=4\b\|slot_dbname(4)" tests/`

Hit lines per file, before (main at 00545d7c, and unchanged at 4d4dca91) and after: the same 48 files, with two counts changed. `tests/test_api/test_scheduler_corpus_pg.py` fell from 3 to 2. `tests/test_pg_disposable_target.py` rose from 1 to 6: the new unrouted-slot refusal tests use `save_04` and `slot=4` only as names in docstrings, a `slot=4` argument, and expected-error patterns, and they install a `psycopg2.connect` tripwire, so they never connect to `save_04`. In the trio every `save_04` hit is gone; the remaining trio hits are `slot=4` labels passed to the factory while `route_slot` routes slot 4 to the clone (the factory refuses the label otherwise). No `slot_dbname(4)` hit exists before or after.

Remaining `save_04` hits after, and why each stays:

- Private cluster (a separate server): `tests/test_connection_lifecycle.py`.
- Name-only, no connection to the owner's database: `tests/test_database_contract.py` (URL and parameter construction), `tests/test_memnon_db_access.py` (connect is monkeypatched to a fake), `tests/test_pg_disposable_target.py` (the refusal matrix), `tests/test_orrery/test_migrate.py:118` (a message string), `tests/test_api/test_narrative_retry.py:490`, `tests/test_api/test_slot_state.py:304`, `tests/test_api/test_wizard_weird_level.py:455`, `tests/test_lore/test_two_pass_pipeline.py` (labels in offline tests).
- Still `include_data=True` clones of `save_04`, outside this order and candidates for the factory in a later slice: `tests/test_prose_metrics_pg.py`, `tests/proofs/proof_session_truth.py`, `tests/test_orrery/test_card_identity.py`, `tests/test_api/test_summary_budget_usage.py`, `tests/test_api/test_session_truth_pg.py`, `tests/test_api/test_scheduler_recovery_pg.py` (x2), `tests/test_api/test_narrative_summary_paid_pg.py`, `tests/test_lore/test_baseline_fingerprint_refresh_pg.py`, `tests/test_lore/test_seat_blocks.py`, `tests/test_lore/test_scene_order_render.py`, and `tests/test_api/test_seat_policy_backfill_pg.py` (a `pg_dump` of `save_04` to prove migration 126's backfill).

The 28 files whose only hits are `slot=4` (none names `save_04` or `slot_dbname(4)`), with hit-line counts:

- PostgreSQL tests that route slot 4 to their own disposable database (by `route_slot`, a `slot_dbname` patch, the `tests/test_api/conftest.py` `offline_gate_db` fixture that routes every slot to `qa640_offline_gate`, or an explicit `dbname=`/connection):
  - `tests/test_api/test_attempt_manifest_pg.py` (10), `tests/test_api/test_scheduler_corpus_pg.py` (2), `tests/test_api/test_seat_policy_jobs_pg.py` (2): factory labels and `?slot=4` requests under `route_slot` (this PR).
  - `tests/test_api/test_frontier_clock_pg.py` (1), `tests/test_api/test_narrative_post_commit.py` (2), `tests/test_api/test_secret_requirements.py` (4), `tests/test_api/test_wizard_chat_validation.py` (3), `tests/test_api/test_wizard_confirmation_pg.py` (6): `offline_gate_db` or a `slot_dbname` patch onto a disposable clone.
  - `tests/test_api/test_mock_wizard_responses.py` (1), `tests/test_api/test_narrative_jobs_pg.py` (2), `tests/test_api/test_narrative_retry_pg.py` (4), `tests/test_api/test_reader_character_provenance_pg.py` (3), `tests/test_api/test_reader_place_provenance_pg.py` (2), `tests/test_api/test_slot_mutation_guard.py` (1), `tests/test_jobs_cli_pg.py` (3), `tests/test_orrery/test_character_experiences_pg.py` (2), `tests/test_orrery/test_need_absence_pg.py` (3), `tests/test_orrery/test_worker.py` (2): each creates its own disposable database and routes slot 4 (or passes its connection) to it.
- Offline tests where `4` is only a label (no PostgreSQL connection): `tests/test_api/test_reader_player_boundary.py` (1), `tests/test_api/test_wizard_confirmation.py` (14), `tests/test_api/test_wizard_resume.py` (9), `tests/test_api/test_wizard_stream_conflicts.py` (1), `tests/test_cli.py` (1), `tests/test_cli_model_selection.py` (3), `tests/test_cli_wizard_confirmation.py` (1), `tests/test_config/test_seat_policies.py` (1, a `StorySettings` label on `qa640_policy`), `tests/test_qa_shift.py` (2), `tests/test_turn_observation.py` (17).

## What Remains on #816

- A CI PostgreSQL tier (reconstructing the template in CI, #810) and an explicit, budgeted live-provider workflow.
- A fixture-owned mock database for `tests/test_mock_openai.py` (the two `mock_database_absent` ids).
- The remaining `include_data=True` `save_04` clones listed above.
