# The Supervisor Live Test Leaves the Owner Slots: Verification

Work order 885-B2-1. Issue #885 (slice B2, item 1). Base: `origin/main` at 813c23d9. Test-only; no migration; TEST provider only, no paid calls. Every gateway port is OS-assigned (port 0); no test names 8002, 8012, 8018, or 8019.

## What Was Wrong

- `tests/test_runtime/test_supervisor_live.py` hardwired `TEST_SLOT = 5` (line 37) and ran `nexus up --slot 5` plus a gateway restart and a full restart (lines 131–191); its `external_gateway` fixture (line 364) started a gateway with `NEXUS_SLOT=5` and `NEXUS_RUNTIME_CONFIG` set to the repository `nexus.toml`, so the owner's `state_dir` and TEST `base_url`. Each gateway lifespan starts `SlotScheduler(5)` (`nexus/api/narrative.py:121`), which commits a lease into `save_05.deferred_work_scheduler` and drains slot 5's deferred work. The supervisor CLI process itself calls `recover_active_slot_choice(slot)` before it spawns the gateway (`nexus/runtime/supervisor.py:667-669`), so routing only the gateway child would still open the owner slot. The `up` calls without `--slot` (lines 238, 241, 287, 296, 332) resolved `runtime.default_slot = 1` and started gateways against `save_01`; only the golden master's read-only lock kept them in observer mode.
- `tests/slot_routed_gateway.py` (PR #1026) routed one slot to a clone for a gateway child, but it read only `NARRATIVE_API_PORT` (`nexus/api/narrative.py:1753-1762`) and could not take the supervisor's uvicorn argv (`nexus.api.narrative:app --host … --port … --log-config …`), and there was no routed entry point for the CLI process.

The hazard was live on the day of this work: the first read of `save_05` (02:30 UTC) showed its scheduler lease held by `gateway:17624:…` with a heartbeat at 02:18:31 UTC, a gateway process that no longer existed, which is the shape an unconverted run of this module leaves behind.

## What Changed

- `tests/pg_fixtures.py`: `route_slot_from_environment` routes a child process's slot from `NEXUS_ROUTED_SLOT` and `NEXUS_ROUTED_SLOT_DATABASE`; it raises `RuntimeError` for a missing or malformed variable, a slot number outside `slot_utils.all_slots()`, or an owner database, before anything is patched. `routed_slot_environment` builds those two variables and refuses an owner database as well.
- `tests/slot_routed_cli.py` (new): routes, then runs `nexus.cli` as `__main__` with the forwarded argv (`runpy.run_module`).
- `tests/slot_routed_uvicorn.py` (new): routes, then runs uvicorn's own `__main__` with the forwarded argv, so it replaces `uvicorn` in the supervisor's argv template `["{python}", "-m", "uvicorn", "nexus.api.narrative:app", "--host", "{host}", "--port", "{port}", "--log-config", "{log_config}"]` with nothing else changed.
- `tests/slot_routed_gateway.py`: now calls the shared `route_child_process`, which the two new entry points also use. It restores the root logger after importing `tests.pg_fixtures`, because `scripts/migrate.py:38` and `scripts/new_story_setup.py:33` call `logging.basicConfig` at import. Without the restore, the routed CLI wrote `INFO Created connection pool …` to stderr ahead of its JSON error and `test_override_refuses_foreign_healthy_listener_on_sibling_port` failed to parse it (seen in the first run of this branch, fixed before the first commit).
- `tests/test_slot_routed_entrypoints.py` (new): offline refusal tests for every entry point and every owner database; PostgreSQL tests on a seeded `qa885_entrypoints` clone (see Proof below).
- `tests/test_runtime/test_supervisor_live.py`: one module-scoped `disposable_slot_database("qa885_supervisor")` seeded with `seed_protagonist` and `seed_story_clock`. `_write_config` sets `runtime.default_slot = 5` (the routed slot), asserts the shipped gateway argv template, swaps in `tests.slot_routed_uvicorn`, and puts `NEXUS_ROUTED_SLOT=5` and `NEXUS_ROUTED_SLOT_DATABASE=<clone>` in the gateway's service environment. `_cli` runs `python -m tests.slot_routed_cli` with the same variables. `external_gateway` runs the routed launcher under a temporary config from `_write_config` (gateway port = its OS-assigned port, `NEXUS_SLOT=5`), never the repository `nexus.toml`. The two `dbname` assertions (old lines 148 and 191) now assert the clone name. Strengthened: the lifecycle test asserts the spawned command is the routed launcher, that the clone's `deferred_work_scheduler` lease is held by `gateway:<the spawned pid>:…`, that `nexus status` reports the clone, and that the captured log holds `Uvicorn running on http://127.0.0.1:<assigned port>` (the launcher runs uvicorn's own `__main__`, so the banner is unchanged); the remote-profile test asserts the external gateway serves the clone. The four port constants are placeholders (`0`); `ephemeral_ports` assigns all of them, as before. No `save_0` literal remains.

## Proof

### The Order's PostgreSQL Command

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider \
    tests/test_runtime/test_supervisor_live.py tests/test_slot_routed_entrypoints.py \
    tests/test_live_gate_clones_pg.py tests/test_pg_disposable_target.py
start 02:48:23
secret-store guard: active; nexus-api: denied; disposable keychain: denied
66 passed, 7 warnings in 70.93s (0:01:10)
end 02:49:34
```

### Owner Slots Before and After That Run

Read-only (`SET default_transaction_read_only = on`), taken at 2026-09-30T02:48:19Z (before) and 02:49:39Z (after). The two outputs are byte-identical (`diff` exit 0), so one copy is shown. `all_public_sequences_md5` is the md5 of every `public` sequence's `last_value` (48 sequences), which covers every sequence in the slot, not only the ones listed. `deferred_work_scheduler` has a boolean singleton key and no sequence.

| Database | Scheduler rows | Lease owner | `heartbeat_at` | `narrative_chunks_id_seq` | `entities_id_seq` | `characters_id_seq` | All-sequence md5 |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| `save_05` before | 1 | `gateway:17624:ea7862da…` | 2026-09-29 22:18:31.64278-04 | 2340 | 5476 | 2471 | `137c550d993d59c16699214c719541a4` |
| `save_05` after | 1 | `gateway:17624:ea7862da…` | 2026-09-29 22:18:31.64278-04 | 2340 | 5476 | 2471 | `137c550d993d59c16699214c719541a4` |
| `save_01` before | 1 | `gateway:15542:2ef6eee8…` | 2026-09-24 12:53:21.623368-04 | 1426 | 121 | 38 | `d070b403f95181adb49587723eddde02` |
| `save_01` after | 1 | `gateway:15542:2ef6eee8…` | 2026-09-24 12:53:21.623368-04 | 1426 | 121 | 38 | `d070b403f95181adb49587723eddde02` |

```
### save_05
 scheduler_rows
----------------
              1

                      owner_id                      |             lease_nonce              |         heartbeat_at         |          expires_at          |        current_job        | last_error
----------------------------------------------------+--------------------------------------+------------------------------+------------------------------+---------------------------+------------
 gateway:17624:ea7862da-bcbc-4863-bde1-696c946b43e6 | 24ad5b1a-6abe-4804-a68c-1cf3d133d454 | 2026-09-29 22:18:31.64278-04 | 2026-09-29 22:19:31.64278-04 | character_experience_jobs |

           sequencename           | last_value
----------------------------------+------------
 characters_id_seq                |       2471
 chunk_metadata_id_seq            |       2234
 entities_id_seq                  |       5476
 generation_session_phases_id_seq |
 narrative_chunks_id_seq          |       2340
 narrative_embedding_jobs_id_seq  |
 narrative_summary_jobs_id_seq    |
 orrery_narration_jobs_id_seq     |
 state_checkpoints_id_seq         |        244

     all_public_sequences_md5     | sequences
----------------------------------+-----------
 137c550d993d59c16699214c719541a4 |        48

### save_01
 scheduler_rows
----------------
              1

                      owner_id                      |             lease_nonce              |         heartbeat_at          |          expires_at           | current_job | last_error
----------------------------------------------------+--------------------------------------+-------------------------------+-------------------------------+-------------+------------
 gateway:15542:2ef6eee8-b27b-4075-b2e7-b4723efd3482 | 348ed6c0-2b6f-4e01-847c-14bcac643837 | 2026-09-24 12:53:21.623368-04 | 2026-09-24 12:54:21.623368-04 | promotion   |

           sequencename           | last_value
----------------------------------+------------
 characters_id_seq                |         38
 chunk_metadata_id_seq            |       1426
 entities_id_seq                  |        121
 generation_session_phases_id_seq |
 narrative_chunks_id_seq          |       1426
 narrative_embedding_jobs_id_seq  |
 narrative_summary_jobs_id_seq    |
 orrery_narration_jobs_id_seq     |
 state_checkpoints_id_seq         |          1

     all_public_sequences_md5     | sequences
----------------------------------+-----------
 d070b403f95181adb49587723eddde02 |        48
```

**No gateway lease appeared in `save_05` while test gateways were up.** A read-only poller sampled both owner slots every 0.5 s through the whole run (02:48:21.067 to 02:49:39.132 UTC, 138 samples per database). Every `save_05` sample showed the same lease (`gateway:17624:…`, heartbeat 22:18:31-04) and the same all-sequence md5 `137c550d…`; every `save_01` sample showed `gateway:15542:…` and `d070b403…`. During that window the module started ten routed gateway processes (the lifecycle stack plus its gateway restart and full restart, two in each of the two override-coexistence tests, the override instance the foreign-listener test rolls back, and the two external gateways), and the lifecycle test asserted that the first one held the clone's lease. Two earlier development runs of the two converted modules (02:34:37 to 02:38:01 UTC) sampled the same unchanged lease rows 374 times per database.

**Concurrent writers.** Between the first read (02:30) and the proof run, `save_05`'s `characters_id_seq` and `entities_id_seq` advanced from 2456 and 5461 to 2471 and 5476. That was another agent's `NEXUS_RUN_POSTGRES=1` run (pid 70422, cwd outside this worktree, about 107 `tests/…` files) of the not-yet-converted rolled-back `save_05` writers listed for later B2 slices; the proof run above started only after it exited (02:48:13), and nothing in this branch inserts characters or entities into any database but its clones.

### The Routed CLI Opens Only the Clone

`tests/test_slot_routed_entrypoints.py::test_routed_cli_up_status_down_never_open_an_owner_slot` runs the routed CLI's `up --slot 5`, `status`, and `down` under a recorder that wraps `psycopg2._connect` (every psycopg2, pool, and SQLAlchemy-psycopg2 connection passes through it; the connections are real) and reports whether `asyncpg` was ever imported. It asserts every database opened is the clone or `postgres` (the admin database `is_slot_locked` uses), that no owner database is opened, that `asyncpg` was never loaded, and, as the positive control, that `up` opened the clone. `test_routed_launcher_serves_the_clone_on_its_port` spawns the gateway from the supervisor's own `_service_argv` and `_service_env` and asserts `/runtime/status` names the clone and the assigned port, and that the launcher's pid holds the clone's scheduler lease; `test_routed_launcher_refuses_an_unrouted_active_slot` asserts a gateway with another `NEXUS_SLOT` exits at startup with `Slot 1 is not routed`.

### Wider Gates

All with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset, at code HEAD `3c113df9`.

```
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider tests/test_runtime
secret-store guard: active; nexus-api: denied; disposable keychain: denied
138 passed, 5 warnings in 68.39s (0:01:08)

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider -rfE tests/test_api/test_[a-n]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_api/test_narrative_post_commit.py::test_cancelled_auto_approval_releases_lease_and_hands_off_post_commit
1 failed, 310 passed, 2 skipped, 9 warnings in 220.48s (0:03:40)

$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider -rfE tests/test_api/test_[o-z]*.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_resolve_four_template_states_are_distinguishable
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_hover_payload
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_entity_context_recent_events_respect_anchor
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_pair_tag_injection_kills_a_winner
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_need_override_reaches_stacks_and_pressures
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_what_if_validation_rejections
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling
FAILED tests/test_api/test_return_recap_pg.py::test_live_loop_at_rest_offers_the_pending_drafts_decision
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_preserves_preempted_job_lease_and_refunds_unissued_attempt[False-character_experience_jobs]
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
FAILED tests/test_api/test_seat_policy_backfill_pg.py::test_seat_policy_migration_backfills_save04_active_jobs
14 failed, 540 passed, 2 skipped, 9 warnings in 266.43s (0:04:26)
```

Every failure is in a file this branch does not touch, and none is new:

| Failures | Class | Evidence |
| --- | --- | --- |
| `test_orrery_dev_endpoints` ×10 | B2 slot-5 content | `save_05 is expected to bind off-screen actors`, `No anchors to analyze: the slot has no narrative chunks`, `no audited slot produces resolutions`; listed as `tests/test_api/test_orrery_dev_endpoints ×10` in the #885 comment "Slice B1 Landed (PR #1026)", item 3 (B2-8). |
| `test_narrative_post_commit` ×1, `test_return_recap_pg` ×1, `test_scheduler_recovery_pg` ×2, `test_seat_policy_backfill_pg` ×1 | Pre-existing on main (`save_04` clones, #816) | Exactly the five named in the #885 comment "9 More Ids Retired by PR #1019" ("the API tier's remaining non-slot-5 failures"). |

Offline, same environment without `NEXUS_RUN_POSTGRES`:

```
$ $PY -m pytest -q -p no:cacheprovider tests --ignore=tests/test_api --ignore=tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
2458 passed, 358 skipped, 8 warnings in 360.96s (0:06:00)

$ $PY -m pytest -q -p no:cacheprovider tests/test_api tests/test_orrery
secret-store guard: active; nexus-api: denied; disposable keychain: denied
1807 passed, 726 skipped, 7 warnings in 34.58s

$ $PY -m pytest -q -p no:cacheprovider tests/test_reachability.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
38 passed in 8.92s

$ $PY -m black --check <changed files>; $PY -m flake8 <changed files>
All done! 6 files would be left unchanged.  (flake8: exit 0)
$ $PY -m mypy --explicit-package-bases <changed files>
Success: no issues found in 6 source files
```

(`mypy` needs `--explicit-package-bases` on this file set because `tests/pg_fixtures.py` is otherwise found under two module names. The tomlkit documents in the two test files are typed `Any`, which also clears the 18 tomlkit index errors `test_supervisor_live.py` carried on main.)

### Audit Grep

`grep -rn "save_0[1-5]\|slot=[1-5]\b\|slot_dbname([1-5])\|TEST_SLOT\|NEXUS_SLOT" tests/test_runtime/ tests/slot_routed_*.py`: 19 hits before, 23 after.

| Hit (after) | Class |
| --- | --- |
| `test_supervisor_live.py` `TEST_SLOT` (docstring, the constant, `_routed_env`, `default_slot`, `--slot`, three `slot ==` assertions, `external_gateway`'s `NEXUS_SLOT`) | Routed slot number: resolves only to the `qa885_supervisor_*` clone in every process the module starts. |
| `test_supervisor_live.py:191` `"NEXUS_SLOT"` | `_cli` removes the caller's `NEXUS_SLOT` from the child environment. |
| `tests/slot_routed_gateway.py:11`, `tests/slot_routed_uvicorn.py:19` `NEXUS_SLOT` | Docstrings. |
| `test_readiness.py:680-699` `save_01`–`save_03` | Offline: pure name-mapping input to a readiness function; no connection. |
| `test_remote_auth.py:237` `Namespace(slot=5)` | Offline: `cli.run_load` against a loopback HTTP recorder (`NEXUS_API_URL` set to it); no database. |
| `test_supervisor.py:180` `_spawn("echo", …, slot=5)` | Offline: an `echo` service; `NEXUS_SLOT=5` is only in its environment. |
| `test_logging_config.py:38,330` `TEST_SLOT = 5`, `_start_service("probe", …)` | A standalone probe app; `recover_active_slot_choice` runs only for the service named `gateway` (`supervisor.py:667`). |

Before, the two `save_0{TEST_SLOT}` assertions (old lines 148 and 191) and the unrouted `TEST_SLOT` uses were owner-slot hits; no `save_0` literal remains in the module.

## #885 Ids Retired

The nodes of `tests/test_runtime/test_supervisor_live.py` that reached an owner slot on main, all of which now run on the clone:

- `test_local_profile_full_lifecycle`: gateways on `save_05` (scheduler lease commits, deferred-work drain) plus the CLI's own `recover_active_slot_choice(5)`.
- `test_external_profile_attaches_and_never_spawns` and `test_remote_profile_status_hits_runtime_endpoint`: the `external_gateway` fixture's gateway on `save_05`, under the repository `nexus.toml`.
- `test_gateway_port_override_coexists_with_default_instance`, `test_gateway_port_override_first_then_default_stack`, and `test_override_refuses_foreign_healthy_listener_on_sibling_port`: `up` without `--slot` resolved `runtime.default_slot = 1` and started gateways on `save_01`, held in observer mode only by its read-only lock.

The other six nodes never started a gateway or opened a slot on main (`test_up_refuses_port_held_by_unmanaged_process` and the two override-error tests refuse before `recover_active_slot_choice`, `supervisor.py:651-669`; the external-down, auto-gating, and mock-port tests start nothing). They now run under the routed CLI too, so any future change that makes them reach a slot reaches the clone.
