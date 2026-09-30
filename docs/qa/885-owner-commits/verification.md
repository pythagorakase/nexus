# #885 Slice B1: No Test Commits to an Owner Slot

Work order 885-B1 (issues #885 and #816). Base `origin/main` at `62efb25f`; code head `4dcf328c`. Every test that committed rows to, or could reset, an owner save slot now runs on a disposable template clone. No migration.

## What Changed

| File | Before | After |
| --- | --- | --- |
| `tests/pg_fixtures.py` | seed helpers only | `route_slot_to_disposable(patch, slot=, dbname=)`: rebinds `slot_utils.slot_dbname` and every loaded module's bound copy to a resolver that returns the clone for one slot and raises for any other, and narrows `VALID_DBNAMES` to the clone; refuses owner databases |
| `tests/slot_routed_gateway.py` (new) | none | routes `NEXUS_ROUTED_SLOT` to `NEXUS_ROUTED_SLOT_DATABASE`, then runs `nexus.api.narrative` as `__main__` (the `python -m nexus.api.narrative` entry point) |
| `tests/test_orrery/test_ecology_live.py` | committed hunt resolutions, events, pair tags, and `current_activity` into `save_02`; cleanup never restored the activity | `ecology_story` clone: `seed_story_clock` plus three `seed_character` rows; asserts the activity through all three commits |
| `tests/test_orrery/test_live_cycle.py` | drained `save_02`'s real promotion and narration backlogs | `seed_live_cycle_story`: four accepted turns (`seed_played_story`, cast of two) commit the resolver's real pending resolutions, and `commit_orrery_tick_sync` adds one salient backlog row on an earlier tick; the test drains to idle and asserts the mundane backlog skipped, the salient backlog promoted, its narration job queued and narrated ahead of the synthetic row |
| `tests/test_orrery/test_retrograde_maturation_live.py` | committed synthetic characters and maturation work to `save_02` | routed clone from `seed_maturation_story`; live markers unchanged |
| `tests/test_orrery/test_pair_tag_predicates.py`, `test_pair_tag_substrate.py` | entity and pair-tag rows in `save_05`, deleted afterward; `pytest.skip` on missing vocabulary | module clone; the vocabulary guard is an assertion |
| `tests/test_orrery/test_weather_migration_pg.py` | created its schema inside `save_05` | `disposable_database`; asserts the surviving row |
| `tests/test_api/test_reader_asset_endpoints.py` | character and image rows in `save_05`; files in the checkout's `ui/client/public/character_portraits` | module clone clocked by `seed_story_clock`, routed under slot 4; uploads in a per-test directory; the `save_02` reads stay read-only |
| `tests/test_issue_601_wizard_live.py`, `tests/test_wizard_live.py`, `tests/test_golden_path_live.py` | `create_slot_schema_only(slot, force=True)` on `save_01`-`save_04` behind `NEXUS_*_TEST_SLOT` / `NEXUS_DISPOSABLE_TEST_SLOT` and `NEXUS_CONFIRM_DISPOSABLE_DB` | `disposable_slot_database(..., story_pin=None)` (which calls `initialize_slot_database`) routed under slot 4; the golden path's gateway subprocess starts through `tests.slot_routed_gateway`; the confirmation variables and slot-5 prose are deleted; the `live`, `live_llm`, `requires_postgres` markers and the `NEXUS_ISSUE_600_LIVE`, `NEXUS_ISSUE_601_LIVE`, `NEXUS_GOLDEN_PATH_E2E` opt-ins are unchanged |
| `tests/test_live_gate_clones_pg.py` (new) | none | runs each live gate's staging on TEST-pinned clones without the live opt-in (see below) |

The live gates keep their markers, so their fixtures never run under `NEXUS_RUN_POSTGRES=1` alone. `tests/test_live_gate_clones_pg.py` runs the same staging functions without the opt-in: the live-cycle backlog seed (and a resolver dry run that binds the seeded cast), maturation enqueue plus queued-job idempotency, the issue #601 cache/model/suggested-trait staging, the issue #600 confirmed-setting seed context, and the golden path's cache staging followed by the routed gateway subprocess on lane 8019 serving `/api/slot/4/state` from the clone (wizard mode, the fixture thread id) and returning 500 for `/api/slot/2/state` (`Slot 2 is not routed`).

## Owner Slots Untouched

Read-only fingerprint, every statement inside `BEGIN READ ONLY`:

```sql
SELECT '<db>',
  (SELECT count(*) FROM narrative_chunks), (SELECT count(*) FROM characters),
  (SELECT count(*) FROM entity_tags), (SELECT count(*) FROM character_relationships),
  (SELECT max(updated_at) FROM characters), (SELECT max(updated_at) FROM character_relationships),
  (SELECT max(created_at) FROM narrative_chunks), (SELECT count(*) FROM entities),
  (SELECT count(*) FROM orrery_resolutions), (SELECT count(*) FROM world_events),
  (SELECT count(*) FROM entity_pair_tags), (SELECT count(*) FROM assets.character_images),
  (SELECT count(*) FROM orrery_maturation_jobs), (SELECT count(*) FROM orrery_narration_jobs),
  (SELECT count(*) FROM pg_namespace);
```

`narrative_chunks` has no `updated_at`; its `max(created_at)` is recorded instead. The same rows were captured at session start (before any test ran), at 19:45:13 CDT before the gate, and at 19:57:59 CDT after the converted files, both Orrery batches, and both API batches; `diff` reported them identical each time.

Before the gate (19:45:13 CDT):

```
db|narrative_chunks|characters|entity_tags|character_relationships|max_characters_updated_at|max_relationships_updated_at|max_chunks_created_at|entities|orrery_resolutions|world_events|entity_pair_tags|character_images|orrery_maturation_jobs|orrery_narration_jobs|schemas
save_01|1425|35|0|84|2026-05-18 05:53:39.909294-04|2025-08-18 18:29:45-04|2025-04-21 00:49:46.677555-04|121|0|0|0|1|0|0|10
save_02|1425|35|0|84|2026-09-29 19:20:46.793362-04|2025-08-18 18:29:45-04|2025-04-21 00:49:46.677555-04|121|0|0|0|1|0|0|9
save_03|40|17|35|11|2026-08-09 03:54:16.80792-04|2026-07-30 12:33:27.950461-04|2026-08-09 03:54:16.80792-04|29|75|96|25|0|12|9|7
save_04|46|23|42|15|2026-08-21 00:51:41.719029-04|2026-08-21 00:52:48.234363-04|2026-08-21 00:51:41.719029-04|39|103|133|28|0|3|0|9
save_05|0|0|0|0||||0|0|0|0|0|0|0|7
```

After the gate (19:57:59 CDT):

```
db|narrative_chunks|characters|entity_tags|character_relationships|max_characters_updated_at|max_relationships_updated_at|max_chunks_created_at|entities|orrery_resolutions|world_events|entity_pair_tags|character_images|orrery_maturation_jobs|orrery_narration_jobs|schemas
save_01|1425|35|0|84|2026-05-18 05:53:39.909294-04|2025-08-18 18:29:45-04|2025-04-21 00:49:46.677555-04|121|0|0|0|1|0|0|10
save_02|1425|35|0|84|2026-09-29 19:20:46.793362-04|2025-08-18 18:29:45-04|2025-04-21 00:49:46.677555-04|121|0|0|0|1|0|0|9
save_03|40|17|35|11|2026-08-09 03:54:16.80792-04|2026-07-30 12:33:27.950461-04|2026-08-09 03:54:16.80792-04|29|75|96|25|0|12|9|7
save_04|46|23|42|15|2026-08-21 00:51:41.719029-04|2026-08-21 00:52:48.234363-04|2026-08-21 00:51:41.719029-04|39|103|133|28|0|3|0|9
save_05|0|0|0|0||||0|0|0|0|0|0|0|7
```

`save_02`'s `max(characters.updated_at)` of 19:20:46 predates this session's first test run; it is the residue of an earlier `test_ecology_live` run on the base, the activity write this PR removes. The gate still contains the slice B2 tests that write owner slots inside rolled-back transactions; they leave counts and timestamps unchanged but advance sequences, which this fingerprint does not claim to cover.

## Converted Files

Gateway variables unset throughout; `$PY` is `/Users/pythagor/nexus/.venv/bin/python`, run from the worktree (`nexus.__file__` resolves under it).

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_ecology_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
3 passed in 1.46s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_live_cycle.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 skipped in 0.24s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_retrograde_maturation_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 skipped in 0.23s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_pair_tag_predicates.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
13 passed in 1.54s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_pair_tag_substrate.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
4 passed in 1.48s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_orrery/test_weather_migration_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 passed in 0.46s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_reader_asset_endpoints.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
20 passed in 2.56s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_issue_601_wizard_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1 skipped in 0.49s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_wizard_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
14 skipped in 0.48s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_golden_path_live.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
8 skipped in 0.22s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_live_gate_clones_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
5 passed in 8.83s
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q <the eleven files above, together>
secret-store guard: active; nexus-api: denied; disposable keychain: denied
46 passed, 25 skipped in 14.87s
```

The skips are the live-marked tests, unchanged: `test_live_cycle`, the maturation gate, the #601 proof, the golden path's eight stages, and in `test_wizard_live.py` the thirteen provider-calling `live` tests plus the #600 seed-repair proof. `test_live_cycle` makes no provider call (Resolve, Commit, Promote, Record, and Bleed are deterministic), so it was also run with its live opt-in on a TEST-pinned clone, keeping the provider-only guard set:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_TEST_PROVIDER_ONLY=1 NEXUS_KEYRING_DISABLE=1 $PY -m pytest -q tests/test_orrery/test_live_cycle.py
secret-store guard: active; nexus-api: read-only (live LLM); disposable keychain: denied
1 passed in 2.79s
```

No other live gate was run (they make paid calls). Every converted module keeps its test count; assertion counts (lines starting `assert`) versus the base: ecology 21 to 25, live cycle 15 to 33, pair-tag predicates 18 to 19, pair-tag substrate 9 to 10, migration 094 0 to 1, the rest equal.

## Tiers

Orrery PostgreSQL tier in two batches at `5728fcff` (the later commit `4dcf328c` only rewraps literals and drops two unused imports):

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q --tb=line tests/test_orrery/test_[a-o]*.py
FAILED tests/test_orrery/test_adjudication_history.py::test_history_is_non_vacuous_on_audited_slots
FAILED tests/test_orrery/test_evidence.py::test_slot_backed_explain_carries_evidence_end_to_end
ERROR tests/test_orrery/test_faction_project_contexts_live.py (8 ids, NoResultFound in the slot-5 fixture)
2 failed, 793 passed, 29 skipped, 8 errors in 142.90s (0:02:22)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q --tb=line tests/test_orrery/test_[p-z]*.py
FAILED tests/test_orrery/test_reveal_live.py (9 ids)
FAILED tests/test_orrery/test_tag_library.py::test_contextual_library_save_05_completeness_and_size
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
10 failed, 811 passed, 10 skipped, 1 error in 114.06s (0:01:54)
```

Every Orrery remainder is the slice B2 slot-5 content class already named on #885 (`test_reveal_live` x9, `test_faction_project_contexts_live` x8, `test_adjudication_history`, `test_evidence`, `test_tag_library`, `test_polymorphic_patron_live`).

`tests/test_api` in two batches:

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q --tb=line tests/test_api/test_[a-n]*.py
FAILED tests/test_api/test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
1 failed, 310 passed, 2 skipped in 148.11s (0:02:28)
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q --tb=line tests/test_api/test_[o-z]*.py
FAILED tests/test_api/test_orrery_dev_endpoints.py (10 ids)
FAILED tests/test_api/test_place_reference_validation_pg.py::test_writer_reference_is_repaired_before_real_staging[mentions]
FAILED tests/test_api/test_place_reference_validation_pg.py::test_writer_reference_is_repaired_before_real_staging[transit]
FAILED tests/test_api/test_place_reference_validation_pg.py::test_writer_reference_is_repaired_before_real_staging[scene_reset]
FAILED tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
FAILED tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs
FAILED tests/test_api/test_session_truth_pg.py::test_generation_session_preserves_bootstrap_error_class[provider_timeout]
18 failed, 536 passed, 2 skipped in 239.95s (0:03:59)
```

The four `TestAssetRoundTrip` setup errors are gone. By class:

- Slice B2 slot-5 content (10): `test_orrery_dev_endpoints.py`.
- Pre-existing on main, not slot 5, already recorded in `docs/qa/816-accepted-turn-factory/verification.md` (5): `test_narrative_post_commit` x1, `test_return_recap_pg` x1, `test_scheduler_recovery_pg` x2, `test_seat_policy_backfill_pg` x1.
- New to the gate since that record, not slot 5, not from this PR (4): `test_place_reference_validation_pg.py` x3 (`AttributeError: 'dict' object has no attribute 'orrery'` at `nexus/agents/lore/logon_utility.py:444`) and `test_session_truth_pg.py::...[provider_timeout]` (`'dict' object has no attribute 'model_copy'` inside the bootstrap). They fail identically on a `git archive` of base `62efb25f`, which this PR's code does not reach:

```
$ cd <git archive 62efb25f> && env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q --tb=line tests/test_api/test_place_reference_validation_pg.py tests/test_api/test_session_truth_pg.py
.../base/nexus/agents/lore/logon_utility.py:444: AttributeError: 'dict' object has no attribute 'orrery'   (x3)
.../base/tests/test_api/test_session_truth_pg.py:176: AssertionError: {... 'Failed to generate bootstrap narrative: 'dict' object has no attribute 'model_copy'", 'error_class': 'AttributeError', ...}
4 failed, 3 passed in 11.27s
```

## Offline and Static

```
$ env -u NEXUS_RUN_POSTGRES $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2336 passed, 353 skipped in 245.43s (0:04:05)
$ env -u NEXUS_RUN_POSTGRES $PY -m pytest -q tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1807 passed, 726 skipped in 29.60s
$ env -u NEXUS_RUN_POSTGRES $PY -m pytest -q tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.28s
$ $PY -m black --check <13 changed files>
13 files would be left unchanged.
$ $PY -m flake8 <13 changed files>
(no output)
$ PYTHONPATH=$PWD $PY -m mypy -m tests.pg_fixtures -m tests.slot_routed_gateway -m tests.test_live_gate_clones_pg ... (all 13 changed modules)
Found 39 errors in 5 files (checked 13 source files)
```

The 39 mypy errors are the base's, file for file (golden path 13, ecology 15, pair-tag predicates 3, substrate 2, wizard live 6; the same modules on the base archive report 39 in the same five files). The new modules and `tests/pg_fixtures.py` report none. The flake8 findings present on the base in the touched files (ten in `test_wizard_live.py`: two F401 and eight E501; four E501 in `test_pair_tag_predicates.py`) are gone.

Lanes: `lsof` showed no listener on 8018 or 8019 before or after; the proof's gateway subprocess ran on 8019 and was terminated by the test. `NEXUS_GATEWAY_PORT=<lane> NEXUS_API_URL=http://127.0.0.1:<lane> nexus down` printed `nothing running` for both lanes.

## Audit

`grep -rn "save_0[1-5]\|slot=[1-5]\b\|slot_dbname([1-5])\|WRITE_SLOT\|LIVE_SLOT\|force=True" tests/`: 913 hits before, 857 after. In the ten converted files, 59 hits before and 3 after, none of them a write:

| File | Before | After | Remaining hits |
| --- | ---: | ---: | --- |
| `test_orrery/test_ecology_live.py` | 6 | 0 | |
| `test_orrery/test_live_cycle.py` | 7 | 0 | |
| `test_orrery/test_retrograde_maturation_live.py` | 16 | 0 | |
| `test_orrery/test_pair_tag_predicates.py` | 4 | 0 | |
| `test_orrery/test_pair_tag_substrate.py` | 2 | 0 | |
| `test_orrery/test_weather_migration_pg.py` | 1 | 0 | |
| `test_api/test_reader_asset_endpoints.py` | 19 | 2 | read-only owner read: lines 4 and 40 name `save_02` for `TestNarrativeReads`, GET-only routes over the mature corpus |
| `test_issue_601_wizard_live.py` | 1 | 0 | |
| `test_wizard_live.py` | 2 | 1 | line 177 `slot=5` labels the `WizardContext` of the offline `mock_db_functions` tests, whose `slot_dbname` is replaced; no connection |
| `test_golden_path_live.py` | 1 | 0 | |

The two new modules add no hit. The remaining hits elsewhere, by class:

**Disposable clone** (hits are slot labels on a clone connection or routed to a clone, the `source_db` of a data clone, or a clone's own name): `test_orrery/test_retrograde_persistence.py` (41; fake cursor or `disposable_slot_database` connection), `test_orrery/test_retrograde_maturation.py` (35; migrated `include_data` clone of `save_02`, plus fake `Info` labels), `test_orrery/test_retrograde_projects_live.py` (18), `test_api/test_acceptance_staging_pg.py` (15), `test_orrery/test_worker.py` (13), `test_api/test_attempt_manifest_pg.py` (10), `test_commit_handler_sync.py` (9), `test_new_story_cache.py` (8; fake connection and a clone), `test_lore/test_pass2_baseline_pg.py` (8), `test_player_identity_consumers_pg.py` (7; slot 1 routed to its dump clone), `test_orrery/test_retrograde_constraints_pg.py` (6), `test_new_story_setup.py` (6), `test_api/test_wizard_confirmation_pg.py` (6), `test_wizard_opening_presence_pg.py` (4), `test_api/test_wizard_model_resolution.py` (4), `test_api/test_session_truth_pg.py` (4), `test_api/test_secret_requirements.py` (4), `test_api/test_narrative_retry_pg.py` (4), `test_orrery/test_need_absence_pg.py` (3), `test_orrery/test_generation_model_provenance_live.py` (3), `test_jobs_cli_pg.py` (3), `test_api/test_wizard_chat_validation.py` (3), `test_api/test_summary_budget_usage.py` (3), `test_api/test_reader_character_provenance_pg.py` (3), `test_prose_metrics_pg.py` (2), `test_presence_roster_pg.py` (2), `test_orrery/test_distortion_live.py` (1 of 2: the fixture's clone), `test_orrery/test_character_experiences_pg.py` (2), `test_orrery_tag_validation_pg.py` (2; slot 1 label on the qa649 clone), `test_memnon/test_ann_gate.py` (2; `save_01` source), `test_lore/test_scene_order_render.py` (2), `test_lore/test_baseline_fingerprint_refresh_pg.py` (2), `test_lore/conftest.py` (2; `save_01` source), `test_api/test_seat_policy_jobs_pg.py` (2), `test_api/test_scheduler_recovery_pg.py` (2), `test_api/test_scheduler_corpus_pg.py` (2), `test_api/test_reader_place_provenance_pg.py` (2), `test_api/test_narrative_summary_paid_pg.py` (2), `test_api/test_narrative_post_commit.py` (2), `test_api/test_narrative_jobs_pg.py` (2), `test_api/test_narrative_continue_validation.py` (2), `test_api/test_mock_wizard_responses.py` (2), `test_api/test_slot_mutation_guard.py` (8; its own clone), `test_orrery/test_need_clock_anchor_pg.py` (1), `test_orrery/test_drift_live.py` (1; `save_03` source), `test_orrery/test_card_identity.py` (1), `test_name_reveal_staged_bindings_pg.py` (1), `test_lore/test_seat_blocks.py` (1), `test_lore/test_pass2_chunk1369.py` (1; `save_01` source), `test_api/test_seat_policy_backfill_pg.py` (1; `pg_dump` source), `test_api/test_reentry_wire_pg.py` (1), `test_api/test_frontier_clock_pg.py` (1), `proofs/proof_session_truth.py` (1), `test_orrery/test_migrate.py` (6; clone runs and a refused-before-connect label), `test_api/test_reader_asset_endpoints.py` (listed above), `pg_fixtures.py` (1; docstring). A data clone reads its owner source only through `pg_dump`, which opens a read-only snapshot, and migrates the clone, never the source.

**Read-only owner read**: `test_api/test_orrery_dev_endpoints.py` (27; `save_05`; the dev endpoints module issues no commit); `test_orrery/test_tag_library.py` (2 of 27; `save_05`, sessions set `readonly=True`); `test_skald_wire.py` (1 of 10; `save_05`, `readonly=True`); `test_place_tag_manifest.py` and `test_character_tag_manifest.py` (`save_02`; manifest and dry-run CLI reads, `execute=True` only in the refusal case); `test_orrery/test_evidence.py` (3; `save_05` resolve, no writes); `test_orrery/test_retrograde_vocabulary.py` (2; `save_02`/`save_05` vocabulary enumeration); `test_faction_table_audit.py:297` (`save_02`, `SET TRANSACTION READ ONLY`); `test_lore/test_intertitle_live.py:24` (`save_02` intertitle load, SELECT only); `test_api/test_reader_asset_endpoints.py` (2; `save_02` GETs). These are safe because they open no write; the `save_05` ones are slice B2 content assumptions.

**Refusal-case fixture**: `test_pg_disposable_target.py` (18; owner names asserted refused before a connection opens), `test_pg_target_contract.py` (16; source strings fed to the static guard), `test_database_contract.py` (25; URL and keyword construction, lazy engines never connected).

**Private cluster**: `test_connection_lifecycle.py` (14; the private-cluster `save_04`).

**Offline label** (44 files, 291 hits, no `requires_postgres`: the default gate's psycopg2 tripwire fails any connection, and the offline gate passes): `test_orrery/test_events.py`, `test_orrery/test_tag_library.py` (25 of 27), `test_memnon/test_source_embeddings.py`, `test_orrery/test_retrograde_packet.py`, `test_turn_observation.py`, `test_lore/test_logon_prompt_formatting.py`, `test_cli.py`, `test_api/test_wizard_confirmation.py`, `test_api/test_wizard_weird_level.py`, `test_backfill_review_packet.py`, `test_api/test_wizard_resume.py`, `test_wizard_agent.py`, `test_orrery/test_retrograde_orchestrator.py`, `test_lore/test_two_pass_pipeline.py`, `test_api/test_narrative_retry.py`, `test_prose_metrics.py`, `test_runtime/test_readiness.py`, `test_api/test_narrative_generation.py`, `test_orrery/test_embedding_audit.py`, `test_qa_shift.py`, `test_cli_model_selection.py`, `test_api/test_slot_state.py`, `test_slot_utils.py`, `test_orrery_tag_validation.py`, `test_new_story_schemas.py` and `test_new_story_integration.py` (`NewStoryDatabaseMapper(dbname="save_02")` maps objects without a connection), `test_native_structured_output.py`, `test_memnon_db_access.py` (patched `psycopg2.connect`), `test_lore/test_memory_manager.py`, `test_lore/test_chunk_operations.py`, `test_api/test_runtime_status.py`, `test_usage_recorder.py`, `test_runtime/test_supervisor.py`, `test_runtime/test_remote_auth.py`, `test_postgres_tools.py` (refused before `createdb`), `test_orrery/test_retrograde_graph.py`, `test_memnon_embedding_contract.py`, `test_entity_tag_manifest_apply.py`, `test_config/test_seat_policies.py`, `test_cli_wizard_confirmation.py`, `test_api/test_wizard_stream_conflicts.py`, `test_api/test_route_capabilities.py`, `test_api/test_reader_player_boundary.py`, `live_seed_schema_test.py`, plus `test_skald_wire.py` (9 of 10, fake readers).

## Slice B2 List: Owner Writes Outside the Converted Files

Every one writes inside a transaction it rolls back (sequences still advance), except the last, which resets an owner slot behind an opt-in. File:line is the owner connection.

- `save_02`: `test_orrery/test_epistemics.py:71, 648, 753, 838`; `test_orrery/test_adjudication_history.py:56`; `test_orrery/test_tag_provenance.py:47, 259`; `test_orrery/test_signal_events.py:109, 212`; `test_faction_table_audit.py:967`; `test_orrery/test_recruit_ally_projects.py:302, 782`; `test_orrery/test_projects.py:530, 583`; `test_lore/test_intertitle_live.py:52`; `test_orrery/test_recruit_ally_replay.py:43`; `test_orrery/test_pursue_romance_replay.py:45`; `test_orrery/test_valence_float_migration_pg.py:175`; `test_orrery/test_seek_redemption_projects.py:365`; `test_orrery/test_seek_redemption_migration_pg.py:19`; `test_orrery/test_seek_redemption_async.py:105`; `test_orrery/test_recruit_ally_migration_pg.py:21`; `test_orrery/test_pursue_romance_projects.py:348`; `test_orrery/test_pursue_romance_migration_pg.py:19`; `test_orrery/test_pursue_romance_async.py:89`; `test_orrery/test_distortion_migration_pg.py:25`; `test_orrery/test_court_patron_projects.py:436`; `test_orrery/test_court_patron_migration_pg.py:19`; `test_orrery/test_court_patron_async.py:102`; `test_orrery/test_claim_accounts_migration_pg.py:34`; `test_orrery/test_build_venture_replay.py:113`; `test_orrery/test_build_venture_projects.py:272`; `test_orrery/test_build_venture_migration_pg.py:22`; `test_orrery/test_build_venture_async.py:108`; `test_orrery/test_backstory_secrets_migration_pg.py:22`.
- `save_05`: `test_orrery/test_stage2a_status_live.py:47`; `test_trait_compiler_integration.py:48`; `test_orrery/test_composition_sources_live.py:139`; `test_orrery/test_claim_propagation_live.py:86, 473, 1181`; `test_orrery/test_distortion_live.py:600` (`LIVE_SLOT` from `test_claim_propagation_live`); `test_lore/test_retrieval_coverage_live.py:42`; `test_orrery/test_faction_project_contexts_live.py:154`; `test_orrery/test_reveal_live.py:88, 335`; `test_orrery/test_knowledge_surfacing_live.py:229`; `test_orrery/test_polymorphic_patron_migration_pg.py:20`; `test_orrery/test_polymorphic_patron_live.py:44`; `test_orrery/test_mood_migration_pg.py:16`; `test_orrery/test_geo_resolver_live.py:22`.
- Opt-in reset of a numbered owner slot: `test_orrery/test_retrograde_wizard_live.py:203` calls `create_slot_schema_only(SLOT, source_db="NEXUS_template", force=True)` for `NEXUS_DISPOSABLE_TEST_SLOT` 1-4 (including `save_01`) behind `NEXUS_CONFIRM_DISPOSABLE_DB`, the same shape as the three gates this PR converts; it was not in this order's inventory.

## #885 Ids Retired

- `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_cross_owner_image_ids_are_404`
- `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_delete_handles_legacy_leading_slash_paths`
- `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_invalid_type_rejected`
- `tests/test_api/test_reader_asset_endpoints.py::TestAssetRoundTrip::test_portrait_upload_set_main_delete`

`tests/test_orrery/test_ecology_live.py::test_outbound_pair_tag_and_detection_gate_live`, routed to #885 by the #964 static disposition, no longer depends on `save_02`.

## Observed, Not Changed

A gateway whose `NEXUS_SLOT` names a wizard-phase slot (no canonical player yet) logs `ERROR ... Deferred-work owner recovering ... Cannot resolve canonical player identity: user_character is NULL` with a traceback from `drain_experience_outbox_sync` (`nexus/agents/orrery/experiences.py:1827`) on every scheduler pass, even with no experience jobs queued. It surfaced when the routed gateway first ran with `NEXUS_SLOT=4` on a staged wizard clone. The launcher therefore leaves `NEXUS_SLOT` to the caller: the golden path passes it through unchanged (set it to 4 for the gateway's scheduler to own the clone's deferred work), and the clone proof unsets it. With `NEXUS_SLOT=4`, stage 8's clean-log assertion would meet this error before the transition establishes the player.
