# The Supervisor Live Test Leaves the Owner Slots: Verification

Work order 885-B2-1. Issue #885 (slice B2, item 1). Base: `origin/main` at 813c23d9. Test-only; no migration; TEST provider only, no paid calls. Every gateway port is OS-assigned (port 0); no test names 8002, 8012, 8018, or 8019.

## What Was Wrong

- `tests/test_runtime/test_supervisor_live.py` hardwired `TEST_SLOT = 5` (line 37) and ran `nexus up --slot 5` plus a gateway restart and a full restart (lines 131–191); its `external_gateway` fixture (line 364) started a gateway with `NEXUS_SLOT=5` and `NEXUS_RUNTIME_CONFIG` set to the repository `nexus.toml`, so the owner's `state_dir` and TEST `base_url`. Each gateway lifespan starts `SlotScheduler(5)` (`nexus/api/narrative.py:121`), which commits a lease into `save_05.deferred_work_scheduler` and drains slot 5's deferred work. The supervisor CLI process itself calls `recover_active_slot_choice(slot)` before it spawns the gateway (`nexus/runtime/supervisor.py:667-669`), so routing only the gateway child would still open the owner slot. The `up` calls without `--slot` (lines 238, 241, 287, 296, 332) resolved `runtime.default_slot = 1` and started gateways against `save_01`; only the golden master's read-only lock kept them in observer mode.
- `tests/slot_routed_gateway.py` (PR #1026) routed one slot to a clone for a gateway child, but it read only `NARRATIVE_API_PORT` (`nexus/api/narrative.py:1753-1762`) and could not take the supervisor's uvicorn argv (`nexus.api.narrative:app --host … --port … --log-config …`), and there was no routed entry point for the CLI process.

The hazard was live on the day of this work: the first read of `save_05` (02:30 UTC) showed its scheduler lease held by `gateway:17624:…` with a heartbeat at 02:18:31 UTC, a gateway process that no longer existed, which is the shape an unconverted run of this module leaves behind.

## What Changed

- `tests/pg_fixtures.py`: `route_slot_from_environment` routes a child process's slot from `NEXUS_ROUTED_SLOT` and `NEXUS_ROUTED_SLOT_DATABASE`; it raises `RuntimeError` for a missing or malformed variable, a slot number outside `slot_utils.all_slots()`, or an owner database, before anything is patched. `routed_slot_environment` builds those two variables and refuses an owner database as well. Both owner refusals name the variable (`NEXUS_ROUTED_SLOT_DATABASE='save_05' names an owner database; a routed entry point serves only a disposable clone`), not the seed helpers; `route_slot_to_disposable` keeps `require_disposable_target` as a second check.
- `tests/slot_routed_cli.py` (new): routes, then runs `nexus.cli` as `__main__` with the forwarded argv (`runpy.run_module`).
- `tests/slot_routed_uvicorn.py` (new): routes, then runs uvicorn's own `__main__` with the forwarded argv, so it replaces `uvicorn` in the supervisor's argv template `["{python}", "-m", "uvicorn", "nexus.api.narrative:app", "--host", "{host}", "--port", "{port}", "--log-config", "{log_config}"]` with nothing else changed.
- `tests/slot_routed_gateway.py`: now calls the shared `route_child_process`, which the two new entry points also use. It restores the root logger after importing `tests.pg_fixtures`, because `scripts/migrate.py:38` and `scripts/new_story_setup.py:33` call `logging.basicConfig` at import. Without the restore, the routed CLI wrote `INFO Created connection pool …` to stderr ahead of its JSON error and `test_override_refuses_foreign_healthy_listener_on_sibling_port` failed to parse it (seen in the first run of this branch, fixed before the first commit).
- `tests/test_slot_routed_entrypoints.py` (new): offline refusal tests for every entry point and every owner database; PostgreSQL tests on a seeded `qa885_entrypoints` clone (see Proof below).
- `tests/test_runtime/test_supervisor_live.py`: one module-scoped `disposable_slot_database("qa885_supervisor")` seeded with `seed_protagonist` and `seed_story_clock`. `_write_config` sets `runtime.default_slot = 5` (the routed slot), asserts the shipped gateway argv template, swaps in `tests.slot_routed_uvicorn`, and puts `NEXUS_ROUTED_SLOT=5` and `NEXUS_ROUTED_SLOT_DATABASE=<clone>` in the gateway's service environment. `_cli` runs `python -m tests.slot_routed_cli` with the same variables. `external_gateway` runs the routed launcher under a temporary config from `_write_config` (gateway port = its OS-assigned port, `NEXUS_SLOT=5`), never the repository `nexus.toml`. The two `dbname` assertions (old lines 148 and 191) now assert the clone name. Strengthened: the lifecycle test asserts the spawned command is the routed launcher, that the clone's `deferred_work_scheduler` lease is held by `gateway:<the spawned pid>:…`, that `nexus status` reports the clone, and that the captured log holds `Uvicorn running on http://127.0.0.1:<assigned port>` (the launcher runs uvicorn's own `__main__`, so the banner is unchanged); the remote-profile test asserts the external gateway serves the clone. The four port constants are placeholders (`0`); `ephemeral_ports` assigns all of them, as before. `test_external_profile_fails_loud_when_target_is_down` no longer attaches to the fixed `http://127.0.0.1:39999`: it binds a socket to `("127.0.0.1", 0)`, keeps it bound without `listen()` while `up` runs (so connections are refused and no other process can take the port), and builds the dead URL from that port. No `save_0` literal remains.

## Proof

### The Order's PostgreSQL Command

Run at a clean checkout of the final code commit, with the owner snapshots and the poller below around it. The commit that records this file changes only this file.

```
$ git rev-parse HEAD; git status --short
763e26b863f190396e21ea01e29a36f88c70b4bd
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_RUN_LIVE_LLM NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider \
    tests/test_runtime/test_supervisor_live.py tests/test_slot_routed_entrypoints.py \
    tests/test_live_gate_clones_pg.py tests/test_pg_disposable_target.py
start 03:25:33
secret-store guard: active; nexus-api: denied; disposable keychain: denied
66 passed, 7 warnings in 72.81s (0:01:12)
exit 0
end 03:26:46
```

(`git status --short` printed nothing.) This run replaces two earlier ones: the first proof run at `3c113df9` (02:48:23 to 02:49:34 UTC, `66 passed ... in 70.93s`), and a rerun from 03:16:29 to 03:17:42 UTC (`66 passed ... in 72.13s`) on a working tree that held the external-down change of `57a64517` before it was committed. Neither is used as evidence below.

### Owner Slots Before and After That Run

Both reads are read-only (the script's first statement is `SET default_transaction_read_only = on`). `all_public_sequences_md5` is the md5 of every `public` sequence's `last_value` (48 sequences), so it covers every sequence in the slot, not only the ones listed. `deferred_work_scheduler` has a boolean singleton key and no sequence.

`owner_snapshot.sql`, run by `owner_snapshot.sh` against each owner slot:

```sql
SET default_transaction_read_only = on;
SELECT count(*) AS scheduler_rows FROM deferred_work_scheduler;
SELECT owner_id, lease_nonce, heartbeat_at, expires_at, current_job, last_error
  FROM deferred_work_scheduler ORDER BY heartbeat_at DESC NULLS LAST LIMIT 1;
SELECT sequencename, last_value FROM pg_sequences
 WHERE schemaname = 'public'
   AND sequencename IN ('characters_id_seq', 'chunk_metadata_id_seq', 'entities_id_seq',
                        'generation_session_phases_id_seq', 'narrative_chunks_id_seq',
                        'narrative_embedding_jobs_id_seq', 'narrative_summary_jobs_id_seq',
                        'orrery_narration_jobs_id_seq', 'state_checkpoints_id_seq')
 ORDER BY sequencename;
SELECT md5(string_agg(sequencename || '=' || coalesce(last_value::text, 'null'), ',' ORDER BY sequencename))
         AS all_public_sequences_md5,
       count(*) AS sequences
  FROM pg_sequences WHERE schemaname = 'public';
```

```bash
#!/bin/bash
# Read-only snapshot of both owner slots; the header carries the capture time.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
echo "captured_at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
for db in save_05 save_01; do
  echo "### $db"
  psql -X -q -d "$db" -v ON_ERROR_STOP=1 -f "$here/owner_snapshot.sql"
done
```

Before (`owner_snapshot.sh > owner_before.txt`, immediately before pytest started):

```
captured_at 2026-09-30T03:25:33Z
### save_05
 scheduler_rows
----------------
              1
(1 row)

                      owner_id                      |             lease_nonce              |         heartbeat_at         |          expires_at          |        current_job        | last_error
----------------------------------------------------+--------------------------------------+------------------------------+------------------------------+---------------------------+------------
 gateway:17624:ea7862da-bcbc-4863-bde1-696c946b43e6 | 24ad5b1a-6abe-4804-a68c-1cf3d133d454 | 2026-09-29 22:18:31.64278-04 | 2026-09-29 22:19:31.64278-04 | character_experience_jobs |
(1 row)

           sequencename           | last_value
----------------------------------+------------
 characters_id_seq                |       2488
 chunk_metadata_id_seq            |       2272
 entities_id_seq                  |       5502
 generation_session_phases_id_seq |
 narrative_chunks_id_seq          |       2378
 narrative_embedding_jobs_id_seq  |
 narrative_summary_jobs_id_seq    |
 orrery_narration_jobs_id_seq     |
 state_checkpoints_id_seq         |        246
(9 rows)

     all_public_sequences_md5     | sequences
----------------------------------+-----------
 e88dec0705328705872ae16018dd6492 |        48
(1 row)

### save_01
 scheduler_rows
----------------
              1
(1 row)

                      owner_id                      |             lease_nonce              |         heartbeat_at          |          expires_at           | current_job | last_error
----------------------------------------------------+--------------------------------------+-------------------------------+-------------------------------+-------------+------------
 gateway:15542:2ef6eee8-b27b-4075-b2e7-b4723efd3482 | 348ed6c0-2b6f-4e01-847c-14bcac643837 | 2026-09-24 12:53:21.623368-04 | 2026-09-24 12:54:21.623368-04 | promotion   |
(1 row)

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
(9 rows)

     all_public_sequences_md5     | sequences
----------------------------------+-----------
 d070b403f95181adb49587723eddde02 |        48
(1 row)

```

After (`owner_snapshot.sh > owner_after.txt`, two seconds after the poller stopped):

```
captured_at 2026-09-30T03:26:48Z
### save_05
 scheduler_rows
----------------
              1
(1 row)

                      owner_id                      |             lease_nonce              |         heartbeat_at         |          expires_at          |        current_job        | last_error
----------------------------------------------------+--------------------------------------+------------------------------+------------------------------+---------------------------+------------
 gateway:17624:ea7862da-bcbc-4863-bde1-696c946b43e6 | 24ad5b1a-6abe-4804-a68c-1cf3d133d454 | 2026-09-29 22:18:31.64278-04 | 2026-09-29 22:19:31.64278-04 | character_experience_jobs |
(1 row)

           sequencename           | last_value
----------------------------------+------------
 characters_id_seq                |       2488
 chunk_metadata_id_seq            |       2272
 entities_id_seq                  |       5502
 generation_session_phases_id_seq |
 narrative_chunks_id_seq          |       2378
 narrative_embedding_jobs_id_seq  |
 narrative_summary_jobs_id_seq    |
 orrery_narration_jobs_id_seq     |
 state_checkpoints_id_seq         |        246
(9 rows)

     all_public_sequences_md5     | sequences
----------------------------------+-----------
 e88dec0705328705872ae16018dd6492 |        48
(1 row)

### save_01
 scheduler_rows
----------------
              1
(1 row)

                      owner_id                      |             lease_nonce              |         heartbeat_at          |          expires_at           | current_job | last_error
----------------------------------------------------+--------------------------------------+-------------------------------+-------------------------------+-------------+------------
 gateway:15542:2ef6eee8-b27b-4075-b2e7-b4723efd3482 | 348ed6c0-2b6f-4e01-847c-14bcac643837 | 2026-09-24 12:53:21.623368-04 | 2026-09-24 12:54:21.623368-04 | promotion   |
(1 row)

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
(9 rows)

     all_public_sequences_md5     | sequences
----------------------------------+-----------
 d070b403f95181adb49587723eddde02 |        48
(1 row)

```

The two files differ only in their `captured_at` line:

```
$ diff <(tail -n +2 owner_before.txt) <(tail -n +2 owner_after.txt)
$ echo $?
0
```

| Database | Scheduler rows | Lease owner | `heartbeat_at` | `narrative_chunks_id_seq` | `entities_id_seq` | `characters_id_seq` | All-sequence md5 |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| `save_05` before (03:25:33Z) | 1 | `gateway:17624:ea7862da…` | 2026-09-29 22:18:31.64278-04 | 2378 | 5502 | 2488 | `e88dec0705328705872ae16018dd6492` |
| `save_05` after (03:26:48Z) | 1 | `gateway:17624:ea7862da…` | 2026-09-29 22:18:31.64278-04 | 2378 | 5502 | 2488 | `e88dec0705328705872ae16018dd6492` |
| `save_01` before (03:25:33Z) | 1 | `gateway:15542:2ef6eee8…` | 2026-09-24 12:53:21.623368-04 | 1426 | 121 | 38 | `d070b403f95181adb49587723eddde02` |
| `save_01` after (03:26:48Z) | 1 | `gateway:15542:2ef6eee8…` | 2026-09-24 12:53:21.623368-04 | 1426 | 121 | 38 | `d070b403f95181adb49587723eddde02` |

### No Gateway Lease in the Owner Slots While Test Gateways Were Up

`poll_owner.sh` ran as a background child of the shell that ran pytest; it started just before pytest and stopped two seconds after it ended. Every 0.5 s it writes one read-only line per owner slot (`time|db|owner_id|heartbeat_at|all-sequence md5`) and one line naming the live routed gateway pids (processes whose argv holds `tests.slot_routed_uvicorn`) and each `qa885_supervisor_*` clone's lease owner:

```bash
#!/bin/bash
# Read-only poller: every 0.5 s, one line per owner slot, plus one line naming
# the live routed gateway pids and each qa885_supervisor clone's lease owner.
# Stops when the file named by $1 exists.
set -uo pipefail
stop=$1
Q="SET default_transaction_read_only = on;
SELECT coalesce((SELECT owner_id || '|' || heartbeat_at FROM deferred_work_scheduler
                  ORDER BY heartbeat_at DESC NULLS LAST LIMIT 1), 'none|none')
       || '|' || (SELECT md5(string_agg(sequencename || '=' || coalesce(last_value::text, 'null'),
                                        ',' ORDER BY sequencename))
                    FROM pg_sequences WHERE schemaname = 'public');"
while [ ! -e "$stop" ]; do
  ts=$(perl -MTime::HiRes=time -MPOSIX=strftime -e '$t=time; printf "%s.%03d", strftime("%H:%M:%S", gmtime($t)), ($t-int($t))*1000')
  for db in save_05 save_01; do
    echo "$ts|$db|$(psql -X -q -At -d "$db" -c "$Q")"
  done
  pids=$(pgrep -f 'tests.slot_routed_uvicorn' | tr '\n' ',' | sed 's/,$//')
  clones=""
  for c in $(psql -X -q -At -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE 'qa885_supervisor%'"); do
    owner=$(psql -X -q -At -d "$c" -c "SET default_transaction_read_only = on; SELECT coalesce((SELECT owner_id FROM deferred_work_scheduler WHERE id), 'none')" 2>/dev/null)
    clones="$clones $c=$owner"
  done
  echo "$ts|gateways|pids=${pids:-none}|clones:${clones:- none}"
  sleep 0.5
done
```

First and last sample per owner slot, and the count of distinct `(owner_id, heartbeat_at, seq_md5)` tuples over all samples:

```
03:25:33.411|save_05|gateway:17624:ea7862da-bcbc-4863-bde1-696c946b43e6|2026-09-29 22:18:31.64278-04|e88dec0705328705872ae16018dd6492
03:26:48.135|save_05|gateway:17624:ea7862da-bcbc-4863-bde1-696c946b43e6|2026-09-29 22:18:31.64278-04|e88dec0705328705872ae16018dd6492
03:25:33.411|save_01|gateway:15542:2ef6eee8-b27b-4075-b2e7-b4723efd3482|2026-09-24 12:53:21.623368-04|d070b403f95181adb49587723eddde02
03:26:48.135|save_01|gateway:15542:2ef6eee8-b27b-4075-b2e7-b4723efd3482|2026-09-24 12:53:21.623368-04|d070b403f95181adb49587723eddde02
```

| Database | Samples (03:25:33.411 to 03:26:48.135 UTC) | Distinct `(owner_id, heartbeat_at, seq_md5)` |
| --- | ---: | ---: |
| `save_05` | 119 | 1 |
| `save_01` | 119 | 1 |

One sample taken while a named test gateway was up: routed gateway pid 1421 (the lifecycle test's first gateway) holds the clone's lease as `gateway:1421:…`, and in the same sample `save_05` and `save_01` still show their old leases and sequence md5s:

```
03:25:37.123|save_05|gateway:17624:ea7862da-bcbc-4863-bde1-696c946b43e6|2026-09-29 22:18:31.64278-04|e88dec0705328705872ae16018dd6492
03:25:37.123|save_01|gateway:15542:2ef6eee8-b27b-4075-b2e7-b4723efd3482|2026-09-24 12:53:21.623368-04|d070b403f95181adb49587723eddde02
03:25:37.123|gateways|pids=1421|clones: qa885_supervisor_0fe1e27ed6b7=gateway:1421:e5c3e76f-eeae-44c0-87c2-6d9069b005d2
```

54 gateway lines (03:25:36.479 to 03:26:36.046 UTC) show at least one live routed gateway pid; 15 distinct routed gateway pids appeared (this count includes the entry-point tests' gateways, which serve `qa885_entrypoints_*` clones the poller does not read), and the `qa885_supervisor_*` clone's lease passed through eight owners, each `gateway:<one of those pids>:…` (1421, 1662, 1844, 2142, 2589, 2897, 3448, 3723). No owner slot's lease or sequences moved in any sample, and the poller logged no connection error (`grep -ci error poll.txt` = 0).

**Concurrent writers.** `save_05` is not quiet: between the 03:17:44Z snapshot of the superseded rerun and this run's 03:25:33Z snapshot, its `narrative_chunks_id_seq`, `entities_id_seq`, and `characters_id_seq` advanced from 2340, 5487, and 2476 to 2378, 5502, and 2488 (all-sequence md5 `f8e7b29a…` to `e88dec07…`). This branch inserts characters, entities, and chunks only into its clones. When this run started, one other agent's pytest run was live (pid 97955, `tests/test_orrery/test_tag_library.py tests/test_orrery_tag_validation_pg.py …`); it had exited by the end. The snapshots and all 119 `save_05` samples show no change during this run.

### The Routed CLI Opens Only the Clone

`tests/test_slot_routed_entrypoints.py::test_routed_cli_up_status_down_never_open_an_owner_slot` runs the routed CLI's `up --slot 5`, `status`, and `down` under a recorder that wraps `psycopg2._connect` (every psycopg2, pool, and SQLAlchemy-psycopg2 connection passes through it; the connections are real) and reports whether `asyncpg` was ever imported. It asserts every database opened is the clone or `postgres` (the admin database `is_slot_locked` uses), that no owner database is opened, that `asyncpg` was never loaded, and, as the positive control, that `up` opened the clone. `test_routed_launcher_serves_the_clone_on_its_port` spawns the gateway from the supervisor's own `_service_argv` and `_service_env` and asserts `/runtime/status` names the clone and the assigned port, and that the launcher's pid holds the clone's scheduler lease; `test_routed_launcher_refuses_an_unrouted_active_slot` asserts a gateway with another `NEXUS_SLOT` exits at startup with `Slot 1 is not routed`.

### Wider Gates

All with `NEXUS_GATEWAY_PORT` and `NEXUS_API_URL` unset.

`tests/test_runtime`, at the same clean checkout as the order's command:

```
$ git rev-parse HEAD; git status --short
763e26b863f190396e21ea01e29a36f88c70b4bd
$ NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -p no:cacheprovider tests/test_runtime
secret-store guard: active; nexus-api: denied; disposable keychain: denied
FAILED tests/test_runtime/test_readiness_pg.py::test_migration_state_compares_stamps_with_this_checkout
1 failed, 137 passed, 5 warnings in 69.34s (0:01:09)
```

(`git status --short` printed nothing.) The one failure is not from this branch: `E  AssertionError: assert False` where `MigrationState(dbname='readiness803_…', tracked=True, latest='134', pending=[], unknown=['135']).current`. The test clones `NEXUS_template`, which was stamped with migration 135 at 2026-09-30 03:03:54Z (`SELECT version, applied_at FROM schema_migrations ORDER BY applied_at DESC LIMIT 1` on `NEXUS_template`); `migrations/135_schema_docs_backfill.sql` landed on `origin/main` in ae2e29bc (#1032), after this branch was cut from 813c23d9, so this checkout reports the stamp as unknown. It clears when the branch picks up main. At `3c113df9`, before the template was stamped, the same directory gave `138 passed, 5 warnings in 68.39s (0:01:08)`.

The `tests/test_api` and offline gates below ran at `3c113df9`. The commits since then change only `test_external_profile_fails_loud_when_target_is_down` (`57a64517`), the owner-refusal text of the two routing helpers in `tests/pg_fixtures.py` with its three test matches (`763e26b8`), and this file. Of those, only `tests/pg_fixtures.py` is imported by `tests/test_api`, and its seed and clone helpers are unchanged.

```
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

```

Lint and types on the six changed Python files, at `763e26b8` with a clean `git status --short`:

```
$ F=$(git diff --name-only 813c23d9..HEAD -- '*.py')
$ $PY -m black --check $F
6 files would be left unchanged.
$ $PY -m flake8 $F; echo "flake8 exit $?"
flake8 exit 0
$ $PY -m mypy --explicit-package-bases $F
Success: no issues found in 6 source files
```

(`mypy` needs `--explicit-package-bases` on this file set because `tests/pg_fixtures.py` is otherwise found under two module names. The tomlkit documents in the two test files are typed `Any`, which also clears the 18 tomlkit index errors `test_supervisor_live.py` carried on main.)

### Audit Grep

The B1 audit pattern, run on `origin/main` (ae2e29bc; the module is unchanged there since 813c23d9) and on this branch:

```
$ git grep -n "save_0[1-5]\|slot=[1-5]\b\|slot_dbname([1-5])\|TEST_SLOT\|NEXUS_SLOT" origin/main -- tests/test_runtime/ 'tests/slot_routed_*.py'
origin/main:tests/slot_routed_gateway.py:9:port). ``NEXUS_SLOT`` keeps its production meaning: when it names the routed
origin/main:tests/test_runtime/test_logging_config.py:38:TEST_SLOT = 5
origin/main:tests/test_runtime/test_logging_config.py:330:    record = supervisor._start_service("probe", service, TEST_SLOT, detached=True)
origin/main:tests/test_runtime/test_readiness.py:680:    names = {1: "save_01", 2: "save_02", 3: "save_03"}
origin/main:tests/test_runtime/test_readiness.py:682:        names, existing={"save_01", "save_02"}, locked={1}
origin/main:tests/test_runtime/test_readiness.py:686:            "save_01",
origin/main:tests/test_runtime/test_readiness.py:691:            "save_02",
origin/main:tests/test_runtime/test_readiness.py:699:    assert absent == ["save_03"]
origin/main:tests/test_runtime/test_remote_auth.py:237:    result = cli.run_load(Namespace(slot=5))
origin/main:tests/test_runtime/test_supervisor.py:180:    pid = supervisor._spawn("echo", service, slot=5, detached=True)
origin/main:tests/test_runtime/test_supervisor_live.py:37:TEST_SLOT = 5
origin/main:tests/test_runtime/test_supervisor_live.py:104:        "NEXUS_SLOT",
origin/main:tests/test_runtime/test_supervisor_live.py:133:        up = _cli("up", "--slot", str(TEST_SLOT), config=config)
origin/main:tests/test_runtime/test_supervisor_live.py:146:        assert runtime_status["slot"] == TEST_SLOT
origin/main:tests/test_runtime/test_supervisor_live.py:148:        assert runtime_status["database"]["dbname"] == f"save_0{TEST_SLOT}"
origin/main:tests/test_runtime/test_supervisor_live.py:184:        assert full_restart["slot"] == TEST_SLOT
origin/main:tests/test_runtime/test_supervisor_live.py:190:        assert runtime_status["slot"] == TEST_SLOT
origin/main:tests/test_runtime/test_supervisor_live.py:191:        assert runtime_status["database"]["dbname"] == f"save_0{TEST_SLOT}"
origin/main:tests/test_runtime/test_supervisor_live.py:368:    env["NEXUS_SLOT"] = str(TEST_SLOT)

$ grep -rn "save_0[1-5]\|slot=[1-5]\b\|slot_dbname([1-5])\|TEST_SLOT\|NEXUS_SLOT" tests/test_runtime/ tests/slot_routed_*.py
tests/test_runtime/test_supervisor.py:180:    pid = supervisor._spawn("echo", service, slot=5, detached=True)
tests/test_runtime/test_remote_auth.py:237:    result = cli.run_load(Namespace(slot=5))
tests/test_runtime/test_supervisor_live.py:9:``TEST_SLOT`` routed to one module-scoped disposable template clone: the
tests/test_runtime/test_supervisor_live.py:62:TEST_SLOT = 5
tests/test_runtime/test_supervisor_live.py:63:# The disposable clone serving TEST_SLOT; routed_clone sets it before each test.
tests/test_runtime/test_supervisor_live.py:107:    """The variables that route TEST_SLOT to the clone in a child process."""
tests/test_runtime/test_supervisor_live.py:109:    return routed_slot_environment(TEST_SLOT, ROUTED_DATABASE)
tests/test_runtime/test_supervisor_live.py:153:    doc["runtime"]["default_slot"] = TEST_SLOT
tests/test_runtime/test_supervisor_live.py:191:        "NEXUS_SLOT",
tests/test_runtime/test_supervisor_live.py:221:        up = _cli("up", "--slot", str(TEST_SLOT), config=config)
tests/test_runtime/test_supervisor_live.py:238:        assert runtime_status["slot"] == TEST_SLOT
tests/test_runtime/test_supervisor_live.py:281:        assert full_restart["slot"] == TEST_SLOT
tests/test_runtime/test_supervisor_live.py:287:        assert runtime_status["slot"] == TEST_SLOT
tests/test_runtime/test_supervisor_live.py:473:    env["NEXUS_SLOT"] = str(TEST_SLOT)
tests/test_runtime/test_readiness.py:680:    names = {1: "save_01", 2: "save_02", 3: "save_03"}
tests/test_runtime/test_readiness.py:682:        names, existing={"save_01", "save_02"}, locked={1}
tests/test_runtime/test_readiness.py:686:            "save_01",
tests/test_runtime/test_readiness.py:691:            "save_02",
tests/test_runtime/test_readiness.py:699:    assert absent == ["save_03"]
tests/test_runtime/test_logging_config.py:38:TEST_SLOT = 5
tests/test_runtime/test_logging_config.py:330:    record = supervisor._start_service("probe", service, TEST_SLOT, detached=True)
tests/slot_routed_gateway.py:11:port). ``NEXUS_SLOT`` keeps its production meaning: when it names the routed
tests/slot_routed_uvicorn.py:19:are exactly the supervisor's. ``NEXUS_SLOT`` keeps its production meaning, as
```

19 hits before, 23 after.

| Hit (before, `origin/main`) | Class |
| --- | --- |
| `test_supervisor_live.py:148`, `:191` `f"save_0{TEST_SLOT}"` | Owner-slot dbname assertions: the gateway served `save_05`. |
| `test_supervisor_live.py:37` (the constant), `:104` (`_cli` drops the caller's `NEXUS_SLOT`, so the unrouted `python -m nexus.cli` resolved `--slot 5`, or `default_slot = 1` when `--slot` was absent), `:133` (`up --slot 5`), `:146`, `:184`, `:190` (`slot == 5` assertions), `:368` (`external_gateway` `NEXUS_SLOT=5` under the repository `nexus.toml`) | Unrouted slot-5 uses: each resolved to an owner slot. |
| `tests/slot_routed_gateway.py:9` `NEXUS_SLOT` | Docstring. |
| `test_readiness.py:680`, `:682`, `:686`, `:691`, `:699` `save_01`–`save_03` | Offline: pure name-mapping input to a readiness function; no connection. |
| `test_remote_auth.py:237` `Namespace(slot=5)` | Offline: `cli.run_load` against a loopback HTTP recorder (`NEXUS_API_URL` set to it); no database. |
| `test_supervisor.py:180` `_spawn("echo", …, slot=5)` | Offline: an `echo` service; `NEXUS_SLOT=5` is only in its environment. |
| `test_logging_config.py:38`, `:330` `TEST_SLOT = 5`, `_start_service("probe", …)` | A standalone probe app; `recover_active_slot_choice` runs only for the service named `gateway` (`supervisor.py:667`). |

| Hit (after, this branch) | Class |
| --- | --- |
| `test_supervisor_live.py:9` | Docstring. |
| `test_supervisor_live.py:63` | Comment. |
| `test_supervisor_live.py:62` (the constant), `:107` (`_routed_env` docstring), `:109` (`_routed_env` builds the routing variables), `:153` (`runtime.default_slot`), `:221` (`up --slot 5`), `:238`, `:281`, `:287` (`slot == 5` assertions), `:473` (`external_gateway`'s `NEXUS_SLOT=5`) | Routed slot number: resolves only to the `qa885_supervisor_*` clone in every process the module starts. |
| `test_supervisor_live.py:191` `"NEXUS_SLOT"` | `_cli` removes the caller's `NEXUS_SLOT` from the child environment; the routed CLI then resolves `--slot 5` or `default_slot = 5`, both routed. |
| `tests/slot_routed_gateway.py:11`, `tests/slot_routed_uvicorn.py:19` `NEXUS_SLOT` | Docstrings. |
| `test_readiness.py:680`, `:682`, `:686`, `:691`, `:699` `save_01`–`save_03` | Offline: pure name-mapping input to a readiness function; no connection. |
| `test_remote_auth.py:237` `Namespace(slot=5)` | Offline: `cli.run_load` against a loopback HTTP recorder (`NEXUS_API_URL` set to it); no database. |
| `test_supervisor.py:180` `_spawn("echo", …, slot=5)` | Offline: an `echo` service; `NEXUS_SLOT=5` is only in its environment. |
| `test_logging_config.py:38`, `:330` `TEST_SLOT = 5`, `_start_service("probe", …)` | A standalone probe app; `recover_active_slot_choice` runs only for the service named `gateway` (`supervisor.py:667`). |

No `save_0` literal remains in the module.

## #885 Ids Retired

The nodes of `tests/test_runtime/test_supervisor_live.py` that reached an owner slot on main, all of which now run on the clone:

- `test_local_profile_full_lifecycle`: gateways on `save_05` (scheduler lease commits, deferred-work drain) plus the CLI's own `recover_active_slot_choice(5)`.
- `test_external_profile_attaches_and_never_spawns` and `test_remote_profile_status_hits_runtime_endpoint`: the `external_gateway` fixture's gateway on `save_05`, under the repository `nexus.toml`.
- `test_gateway_port_override_coexists_with_default_instance`, `test_gateway_port_override_first_then_default_stack`, and `test_override_refuses_foreign_healthy_listener_on_sibling_port`: `up` without `--slot` resolved `runtime.default_slot = 1` and started gateways on `save_01`, held in observer mode only by its read-only lock.

The other six nodes never started a gateway or opened a slot on main (`test_up_refuses_port_held_by_unmanaged_process` and the two override-error tests refuse before `recover_active_slot_choice`, `supervisor.py:651-669`; the external-down, auto-gating, and mock-port tests start nothing). They now run under the routed CLI too, so any future change that makes them reach a slot reaches the clone.

## Review Round (Astra)

Astra's review of `141daf44` returned one P2 and two P3 items.

### P2: Restart Preservation Keeps a Distinct Slot

On main, the lifecycle test ran slot 5 against `runtime.default_slot = 1`, so a restart that lost the recorded slot fell back to 1 and failed. The conversion set `default_slot = 5` and lost that distinction. `default_slot` stays 5 and routing stays clone-only; the two restart commands now run with `NEXUS_SLOT=3` (`CONFLICTING_SLOT`, `tests/test_runtime/test_supervisor_live.py:65` and `:284`) in the CLI process environment. The recorded-slot path ignores it. A restart that resolves the slot from `NEXUS_SLOT` or the default hands `recover_active_slot_choice` slot 3, which the routed CLI refuses (`Slot 3 is not routed`) before any connection opens. After each restart the test asserts `_returncode == 0` and slot 5: `restart gateway` asserts the new record's `slot`, and `restart` asserts the payload's `slot` and `/runtime/status` naming the clone. `_cli` now raises an `AssertionError` that carries the command's stderr tail when the CLI prints no JSON (`:215`), so a refusal names itself instead of surfacing as a bare `JSONDecodeError`.

Coverage proof: two scratch mutations of `Supervisor.restart` (`nexus/runtime/supervisor.py`), each run with `env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_runtime/test_supervisor_live.py -k full_lifecycle`, then restored from a saved copy (`git diff --stat` afterward lists only the test file).

Mutation A: both branches resolve `self._resolve_slot(None)`. The failure is at `restart gateway`:

```
>           restart = _cli("restart", "gateway", config=config, env_extra=conflicting_slot)
E           AssertionError: nexus restart gateway exited 1 without JSON:
E             File ".../nexus/runtime/supervisor.py", line 878, in restart
E               record = self._start_service(
E             File ".../nexus/runtime/supervisor.py", line 669, in _start_service
E               recover_active_slot_choice(slot)
E             File ".../tests/pg_fixtures.py", line 366, in _routed_slot_dbname
E           RuntimeError: Slot 3 is not routed: only slot 5 reaches the disposable clone 'qa885_supervisor_ebb90a762582'
1 failed, 11 deselected, 5 warnings in 7.52s
```

Mutation B: only the full-restart branch resolves `self._resolve_slot(None)` (the service branch keeps its recorded slot). `restart gateway` passes, and the failure is at the full restart:

```
-        resolved_slot = self._resolve_slot(
-            slot if slot is not None else self._running_slot()
-        )
+        resolved_slot = self._resolve_slot(None)

>           full_restart = _cli("restart", config=config, env_extra=conflicting_slot)
E           AssertionError: nexus restart exited 1 without JSON:
E             File ".../nexus/runtime/supervisor.py", line 886, in restart
E               return self.up(slot=resolved_slot, echo=False)
E             File ".../nexus/runtime/supervisor.py", line 669, in _start_service
E               recover_active_slot_choice(slot)
E             File ".../tests/pg_fixtures.py", line 366, in _routed_slot_dbname
E           RuntimeError: Slot 3 is not routed: only slot 5 reaches the disposable clone 'qa885_supervisor_d9a13f0e740e'
1 failed, 11 deselected, 5 warnings in 9.98s
```

### P3: The Gateway-Only Restart Asserts the Clone

After `restart gateway`, `nexus status` must report `runtime.slot == 5` and `runtime.database.dbname` equal to the clone (`:297` and the line after it), as the full restart already did.

### P3: Evidence Counts

The review found 119 samples per owner slot and 15 routed gateway pids in the raw artifacts, and one other pytest process live at the proof's start. This file (the "No Gateway Lease in the Owner Slots While Test Gateways Were Up" section) and the PR body already state 119 samples, 15 pids, and the other process (pid 97955, `tests/test_orrery` tag files, gone by the end). The 138-sample and ten-gateway counts came from the superseded 02:48Z run at `3c113df9` and were carried only into the review brief, not into this file or the PR body. The prose needed no change, and the artifacts were not regenerated.

### Gates

```
$ env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_runtime/test_supervisor_live.py tests/test_slot_routed_entrypoints.py tests/test_runtime/test_readiness_pg.py
secret-store guard: active; nexus-api: denied; disposable keychain: denied
37 passed, 5 warnings in 68.52s (0:01:08)

$ black --check tests/test_runtime/test_supervisor_live.py
All done! ✨ 🍰 ✨
1 file would be left unchanged.

$ flake8 tests/test_runtime/test_supervisor_live.py
(no output)
```
