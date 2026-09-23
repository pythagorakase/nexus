# Work Order 800 Verification

## Fifth-Amendment Final Verification

Validated implementation commit `50376f7d` from this worktree. The offline gate and all ten standalone recovery proofs pass. The required PostgreSQL selection has 216 passes and 21 empty-save_05 baseline failures/errors, named below. No Postgres.app authentication rejection occurred in either PostgreSQL invocation; the conditional socket/process-group hardening was therefore not needed and no test or production code changed in this resume. No additional paid calls were made.

### Files Changed in This Resume

- `docs/qa/800-job-owner/verification.md` — Record the final gates, live recovery evidence, exact remainder, and clean-main reproduction of the eleven newly exposed empty-slot causes. The review implementation files in `50376f7d` remain listed in the historical review section below.

### Commands and Verbatim Tails

All commands ran from the order worktree unless noted. `$PY` below is `/Users/pythagor/nexus/.venv/bin/python`; actual invocations used that absolute interpreter path.

```sh
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-job-owner/nexus/__init__.py
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2624 passed, 792 skipped, 9 warnings in 105.20s (0:01:45)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_qa_shift.py -k 'job or drain or worker or lease or scheduler or maturation or experience or compaction or status'
```

```text
15 failed, 216 passed, 1 skipped, 1711 deselected, 11 warnings, 6 errors in 180.94s (0:03:00)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_recovery_pg.py
```

```text
10 passed, 7 warnings in 42.63s
```

```sh
PYTHONPATH=$PWD $PY -m black --check nexus/jobs nexus/agents/orrery/{job_queues,experiences,retrograde_maturation}.py nexus/api/{mock_openai,narrative_lease,runtime_status}.py nexus/cli.py nexus/config/settings_models.py tests/test_api/test_scheduler_recovery_pg.py
```

```text
All done! ✨ 🍰 ✨
13 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY -c 'from nexus.config import load_settings; s=load_settings(); print("nexus.toml: valid"); print(s.runtime.scheduler); print(s.api.test_provider)'
```

```text
nexus.toml: valid
lease_duration_seconds=60.0 heartbeat_interval_seconds=10.0 poll_interval_seconds=5.0 generation_wait_seconds=1.0 error_backoff_seconds=5.0 milestone_recovery_age_seconds=60.0 promotion_limit=20 compaction_max_jobs_per_drain=1 compaction_max_attempts=3 compaction_retry_delay_seconds=300.0 compaction_lease_duration_seconds=300.0
experience_response_delay_seconds=0.0
```

### PostgreSQL Remainder by ID

These are the exact aggregate results, not a zero-failure PostgreSQL gate:

```text
FAILED tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity
FAILED tests/test_orrery/test_claim_propagation_live.py::test_large_skip_drains_chained_hops_at_staggered_times
FAILED tests/test_orrery/test_claim_propagation_live.py::test_depth_cap_is_recovered_across_separate_drains
FAILED tests/test_orrery/test_claim_propagation_live.py::test_late_drain_lands_hop_scheduled_inside_age_horizon
FAILED tests/test_orrery/test_claim_propagation_live.py::test_non_primary_commit_skips_propagation_drain
FAILED tests/test_orrery/test_claim_propagation_live.py::test_idempotent_redrain_and_disabled_config_are_noops
FAILED tests/test_orrery/test_claim_propagation_live.py::test_resolution_free_commit_still_drains
FAILED tests/test_orrery/test_claim_propagation_live.py::test_async_drain_matches_sync_single_hop
FAILED tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift
FAILED tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop
FAILED tests/test_orrery/test_stage2a_status_live.py::test_retrograde_institutional_standing_persists_status_edge
FAILED tests/test_orrery/test_stage2a_status_live.py::test_retrograde_status_skips_existing_live_standing_with_dry_run_parity
FAILED tests/test_orrery/test_stage2a_status_live.py::test_wizard_time_retrograde_status_keeps_source_chunk_null
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
ERROR tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum
ERROR tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways
```

Ten IDs are already individually covered by #885 and amendment four: claim consumption (one), replay (one), stage2a status (five), communication graph (two), and polymorphic patron (one).

**Finding:** #904 fixed connection establishment for the other eleven IDs, exposing their next fixture dependency on empty save_05. They no longer fail with URL/host parsing errors. Their current causes, reproduced on clean `origin/main` (`2069dcd0`), are:

| IDs | Current Cause | Clean Main | Order-Owned Files |
|---|---|---|---|
| All seven `test_claim_propagation_live.py` IDs listed above | Character fixture insertion fails `need-clock anchor unavailable: no canonical world time or base_timestamp`. | Same seven failures | No |
| `test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop` | `SELECT id FROM places ORDER BY id LIMIT 1` returns no row; subscripting `None` fails. | Same failure | No |
| All three `test_status_bestow_delta_live.py` IDs listed above | Character fixture query returns no row; unpacking `None` fails. | Same three errors | No |

The broader #885 empty-slot class applies by cause; the coordinator should add these eleven explicit IDs to its list. They are reported as a newly exposed baseline finding, not silently treated as passing. No order-owned test failed.

The authorized throwaway worktree used no dependency installation:

```sh
git worktree add --detach temp/800-main-fifth origin/main
PYTHONPATH=$PWD/temp/800-main-fifth $PY -c 'import os; os.chdir("temp/800-main-fifth"); import nexus; print(nexus.__file__)'
# From temp/800-main-fifth:
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_claim_propagation_live.py tests/test_orrery/test_reveal_live.py tests/test_orrery/test_status_bestow_delta_live.py -k 'job or drain or worker or lease or scheduler or maturation or experience or compaction or status'
# Back in the order worktree:
git worktree remove temp/800-main-fifth
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-job-owner/temp/800-main-fifth/nexus/__init__.py
8 failed, 21 deselected, 3 errors in 0.73s
```

### Fresh Recovery and Status Evidence

`tests/test_api/test_scheduler_recovery_pg.py:26` terminates the actual heartbeat backend and checks `/runtime/status` on 8017 through recovery and reacquisition. `:272` holds generation beyond the configured job lease and verifies renewal or refund with no premature provider call. `:405` kills an actual gateway during TEST HTTP, restarts it, verifies exactly one successful job transition, and rejects the dead nonce. The same complete file also runs both row-lock-expiry fences and both concurrent-completion snapshot cases. Fresh verbatim evidence:

```text
Terminated heartbeat backend: 46121
Recovery state: recovering; last_error=connection already closed
Recovering runtime scheduler: {"active": true, "current_job": null, "expires_at": "2026-09-23 23:48:49.823927+00", "heartbeat_at": "2026-09-23 23:48:46.823927+00", "last_error": "connection already closed", "lease_nonce": "6706d0b9-e291-40f4-bb2c-eac02a162ba0", "owner_id": "gateway:46042:99f9f6f6-1555-4885-9fe8-013175137865", "state": "recovering"}
scheduler: state=owner owner=gateway:46042:99f9f6f6-1555-4885-9fe8-013175137865 active=True heartbeat=2026-09-23 23:48:50.228631+00 job=orrery_narration_jobs error=connection already closed
Recovered runtime scheduler: {"active": true, "current_job": "orrery_maturation_jobs", "expires_at": "2026-09-23 23:48:53.355335+00", "heartbeat_at": "2026-09-23 23:48:50.355335+00", "last_error": "connection already closed", "lease_nonce": "342c8991-027d-446a-a792-4cb7edec4b6f", "owner_id": "gateway:46042:99f9f6f6-1555-4885-9fe8-013175137865", "state": "owner"}
Reacquired: 6706d0b9-e291-40f4-bb2c-eac02a162ba0 -> 342c8991-027d-446a-a792-4cb7edec4b6f; narration=[('succeeded', 1)]
character_experience_jobs: held beyond 1s TTL; outcome=('succeeded', 1); lost=False
correspondence_compaction_jobs: held beyond 1s TTL; outcome=('succeeded', 1); lost=False
character_experience_jobs: held beyond 1s TTL; outcome=('queued', 0); lost=True
correspondence_compaction_jobs: held beyond 1s TTL; outcome=('queued', 0); lost=True
SIGKILL gateway pid=47297; job=3; nonce=d8306e83-5b43-431c-a5a6-70f075242bbe
Restarted gateway pid=47335; job=(succeeded,2); successful transitions=1; dead nonce rejected
SIGKILL runtime scheduler: {"active": true, "current_job": "orrery_maturation_jobs", "expires_at": "2026-09-23 23:49:29.458237+00", "heartbeat_at": "2026-09-23 23:49:26.458237+00", "last_error": null, "lease_nonce": "7db51a6f-655f-47fe-86f0-89a834952e52", "owner_id": "gateway:47335:a89a5ded-6671-428f-a3ee-6c161098662c", "state": "owner"}
nexus down (56262): nothing running
```

The lane fixture ran `nexus down` after stopping its owned server; final `lsof -nP -iTCP:8017 -sTCP:LISTEN` returned 1 with no output. The throwaway clean-main checkout was removed. No owner save queue was drained. Logs remain under gitignored `temp/800-validation/*-final-fifth.log` and `main-fifth.log`.

### Coordinator Handoff

No implementation question remains. Record the eleven newly exposed empty-slot IDs on #885. Apply migration 120 and drain live save_04 only through the coordinator's production rollout. Per-chunk embedding, durable summary plans, downloads, and the protected modules remain deferred as originally ordered. PR #902 receives `50376f7d` and this verification update; do not merge as part of this run.

## Historical Fourth-Amendment Stop (Superseded by the Fifth-Amendment Results)

The review fixes are implemented locally on `claude/800-job-owner`. Publication stopped when inspection of the completed PostgreSQL gate revealed the permission refusal below. This invokes the work order's explicit Postgres.app stop rule. **The required PostgreSQL gate is not passed; PR #902 has not received these fixes.** No authentication setting, connection route, or password was changed to bypass the refusal.

The refusal was first read after the aggregate gate finished. Focused proofs that completed before that inspection are retained as evidence, not as a substitute for the blocked gate. The already-running offline suite finished successfully. `origin/main` was merged at `d5d1ccc6`, incorporating `34f008ed` / #904. Both aggregate runs began before that merge, so a complete final gate on the merged revision remains outstanding. No additional paid call was made; the original one-call proof below remains the entire paid-call budget used.

### Exact Blocking Error

From `tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_drains_starved_corpus`, in `tests/pg_fixtures.py:42`, while its polling predicate connected to its own disposable clone:

```text
E       psycopg2.OperationalError: connection to server at "localhost" (::1), port 5432 failed: FATAL:  Postgres.app rejected "trust" authentication
E       DETAIL:  Unknown processes are not allowed to connect without a password. For more information see https://postgresapp.com/l/app-permissions/
E       HINT:  Change pg_hba.conf to require a password
```

Diagnosis: Postgres.app denied authorization to a client process. The database was `qa640_800_corpus_a11f12bc3d7d`, not a live save. The independently invoked corpus proof later completed before this aggregate error was inspected; that does not waive the explicit stop rule. No PostgreSQL command was started after the refusal was identified.

### Files Changed in the Review Fixes

- `nexus/jobs/scheduler.py` — Separate shutdown from ownership loss; record recovery errors, back off and reacquire; renew selected domain leases during generation waits and refund attempts that never issued a request.
- `nexus/jobs/gate.py` — Track the selected job's existing nonce and configured lease duration in the scheduler context.
- `nexus/jobs/compaction.py` — Register the selected lease and evaluate the completion fence after acquiring its row lock.
- `nexus/agents/orrery/experiences.py` — Supply the selected experience job's fencing identity to the scheduler.
- `nexus/agents/orrery/retrograde_maturation.py` — Supply maturation fencing identity and recheck expiry after acquiring the completion lock.
- `nexus/agents/orrery/job_queues.py` — Read counts and nonterminal rows in one statement per queue; expose ownership state.
- `nexus/api/narrative_lease.py` — Wake local schedulers after the generation-lease release commits.
- `nexus/api/runtime_status.py` — Report process-local owner/observer/recovering state and last error, including a failed database probe.
- `nexus/api/mock_openai.py` — Add a configured delay to the real TEST experience response path.
- `nexus/cli.py` — Include scheduler state and last error in its compact status line.
- `nexus/config/settings_models.py` — Validate TEST response delay and default generation polling to one second.
- `nexus.toml` — Set the one-second fallback and zero-delay TEST default.
- `tests/test_api/test_scheduler_recovery_pg.py` — Exercise terminated heartbeat recovery, locked completion expiry, concurrent status, preemption lease renewal/refunds, and subprocess SIGKILL/restart on real disposable databases.
- `docs/qa/800-job-owner/verification.md` — Preserve these review proofs and the stop condition.

The #904 merge also brought `nexus/database.py`, `tests/test_database_contract.py`, `tests/test_orrery/test_claim_propagation_live.py`, and `tests/test_orrery/test_reveal_live.py` from the coordinator's branch; these are not additional order-800 fixes. No protected presence, prompt-budget, or usage source was edited.

### Completed Review Proofs

- `nexus/jobs/scheduler.py:279` records an ERROR and `last_error` without issuing diagnostic SQL to an unreachable database; `:460` keeps reacquiring until shutdown. `tests/test_api/test_scheduler_recovery_pg.py:26` terminates an actual heartbeat backend with `pg_terminate_backend`, observes recovery over HTTP on 8017, then demonstrates a new nonce and successful idle narration in the same gateway process.
- `nexus/jobs/scheduler.py:145` renews the existing domain nonce while waiting. The parameterized test at `tests/test_api/test_scheduler_recovery_pg.py:272` holds generation beyond a one-second experience or compaction lease: it remains live, an observer cannot drain, and no provider usage is recorded before release. Forced renewal failure requeues with attempts reset to zero and no provider call. Local release notification resumes before the one-second fallback.
- `nexus/jobs/compaction.py:22` and `nexus/agents/orrery/retrograde_maturation.py:1533` lock before reevaluating expiry. The regression at `tests/test_api/test_scheduler_recovery_pg.py:154` holds an actual row lock through expiration and rejects both completions.
- `tests/test_api/test_scheduler_recovery_pg.py:222` completes narration/compaction from another connection after the status SELECT executes but before fetching it. Counts and rows describe the same snapshot.
- `tests/test_api/test_scheduler_recovery_pg.py:405` spawns the real gateway on an inherited ephemeral listener, waits until TEST receives the delayed HTTP request, sends SIGKILL, starts a different process, and verifies one successful transition after lease expiry. Replaying the dead attempt through the real experience completion function rejects its nonce. TEST is the only provider used.

```text
Terminated heartbeat backend: 28822
Recovery state: recovering; last_error=connection already closed
Recovering runtime scheduler: {"active": true, "current_job": null, "expires_at": "2026-09-23 23:40:05.779776+00", "heartbeat_at": "2026-09-23 23:40:02.779776+00", "last_error": "connection already closed", "lease_nonce": "ee9c00e4-ba64-48e8-bf26-3acb8ea13a48", "owner_id": "gateway:28668:64bf206d-3f20-49d4-868a-3ea73a1b9e54", "state": "recovering"}
scheduler: state=owner owner=gateway:28668:64bf206d-3f20-49d4-868a-3ea73a1b9e54 active=True heartbeat=2026-09-23 23:40:06.169565+00 job=orrery_narration_jobs error=connection already closed
Recovered runtime scheduler: {"active": true, "current_job": "orrery_maturation_jobs", "expires_at": "2026-09-23 23:40:09.289629+00", "heartbeat_at": "2026-09-23 23:40:06.289629+00", "last_error": "connection already closed", "lease_nonce": "93795cba-5fb2-43da-8b27-7c6fb3761551", "owner_id": "gateway:28668:64bf206d-3f20-49d4-868a-3ea73a1b9e54", "state": "owner"}
Reacquired: ee9c00e4-ba64-48e8-bf26-3acb8ea13a48 -> 93795cba-5fb2-43da-8b27-7c6fb3761551; narration=[('succeeded', 1)]
SIGKILL gateway pid=19425; job=3; nonce=4b833488-fcb7-4884-a37d-b9fdb8bc84ee
Restarted gateway pid=19603; job=(succeeded,2); successful transitions=1; dead nonce rejected
SIGKILL runtime scheduler: {"active": true, "current_job": "orrery_maturation_jobs", "expires_at": "2026-09-23 23:38:08.194141+00", "heartbeat_at": "2026-09-23 23:38:05.194141+00", "last_error": null, "lease_nonce": "e80653f1-6967-49a9-892d-0a30ab731f98", "owner_id": "gateway:19603:2dc039c9-4a74-4c90-a279-d7f6e2fa0822", "state": "owner"}
nexus down (49812): nothing running
```

The 8017 gateway fixture ran `nexus down` with the same lane environment and printed `nothing running` after stopping its owned Uvicorn server. The SIGKILL fixture did the same on its ephemeral lane. A final `lsof -nP -iTCP:8017 -sTCP:LISTEN` returned 1 with no output.

### Commands and Verbatim Tails

All commands used the worktree root and the shared interpreter; import resolution was checked first:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-job-owner/nexus/__init__.py
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2624 passed, 791 skipped, 9 warnings in 90.35s (0:01:30)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_qa_shift.py -k 'job or drain or worker or lease or scheduler or maturation or experience or compaction or status'
```

```text
10 failed, 214 passed, 1 skipped, 1711 deselected, 11 warnings, 13 errors in 156.91s (0:02:36)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_scheduler_pg.py -x
```

```text
6 passed, 7 warnings in 9.14s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_scheduler_pg.py
```

```text
6 passed, 7 warnings in 9.74s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_recovery_pg.py
```

```text
2 failed, 7 passed, 7 warnings in 19.48s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_recovery_pg.py -k preempted
```

```text
4 passed, 6 deselected, 7 warnings in 14.80s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_recovery_pg.py -k sigkill
```

```text
1 passed, 9 deselected, 5 warnings in 16.17s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_recovery_pg.py -k terminated_heartbeat
```

```text
1 passed, 9 deselected, 7 warnings in 6.32s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_corpus_pg.py -k drains_starved
```

```text
1 passed, 2 deselected, 7 warnings in 4.62s
```

The early combined recovery invocation above exposed a tuple-versus-dictionary fixture cursor mismatch in the two compaction cases; that fixture was corrected and both passed in the subsequent preemption invocation. The first SIGKILL attempt returned `1 failed, 9 deselected, 5 warnings in 18.60s` because INFO request-start logs were not enabled in its child TEST server. Its final fixture enables actual child logging; it does not replace the provider or gateway. The initial offline run returned `1 failed, 2623 passed, 791 skipped, 9 warnings in 93.17s (0:01:33)` due to the runtime-status builder calling contract. Moving the local status overlay after the offloaded builder preserved that contract; its focused regression then passed:

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_runtime_status.py
```

```text
2 passed, 5 warnings in 0.06s
```

```sh
$PY -m black --check nexus/jobs nexus/agents/orrery/{job_queues,experiences,retrograde_maturation}.py nexus/api/{mock_openai,narrative_lease,runtime_status}.py nexus/cli.py nexus/config/settings_models.py tests/test_api/test_scheduler_recovery_pg.py
```

```text
All done! ✨ 🍰 ✨
13 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY -c 'from nexus.config import load_settings; s=load_settings(); print("nexus.toml: valid"); print(s.runtime.scheduler); print(s.api.test_provider)'
```

```text
nexus.toml: valid
lease_duration_seconds=60.0 heartbeat_interval_seconds=10.0 poll_interval_seconds=5.0 generation_wait_seconds=1.0 error_backoff_seconds=5.0 milestone_recovery_age_seconds=60.0 promotion_limit=20 compaction_max_jobs_per_drain=1 compaction_max_attempts=3 compaction_retry_delay_seconds=300.0 compaction_lease_duration_seconds=300.0
experience_response_delay_seconds=0.0
```

`git diff --check` returned zero with no output. No UI build was needed.

### Aggregate Gate Remainder and Resume Work

The completed gate began before #904 was merged and before the runtime-status calling-contract correction. Its exact failing IDs are retained here:

```text
FAILED tests/test_api/test_runtime_status.py::test_runtime_status_endpoint_offloads_sync_builder
FAILED tests/test_api/test_scheduler_corpus_pg.py::test_scheduler_drains_starved_corpus
FAILED tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity
FAILED tests/test_orrery/test_claim_propagation_live.py::test_async_drain_matches_sync_single_hop
FAILED tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift
FAILED tests/test_orrery/test_stage2a_status_live.py::test_retrograde_institutional_standing_persists_status_edge
FAILED tests/test_orrery/test_stage2a_status_live.py::test_retrograde_status_skips_existing_live_standing_with_dry_run_parity
FAILED tests/test_orrery/test_stage2a_status_live.py::test_wizard_time_retrograde_status_keeps_source_chunk_null
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate
FAILED tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction
ERROR tests/test_orrery/test_claim_propagation_live.py::test_large_skip_drains_chained_hops_at_staggered_times
ERROR tests/test_orrery/test_claim_propagation_live.py::test_depth_cap_is_recovered_across_separate_drains
ERROR tests/test_orrery/test_claim_propagation_live.py::test_late_drain_lands_hop_scheduled_inside_age_horizon
ERROR tests/test_orrery/test_claim_propagation_live.py::test_non_primary_commit_skips_propagation_drain
ERROR tests/test_orrery/test_claim_propagation_live.py::test_idempotent_redrain_and_disabled_config_are_noops
ERROR tests/test_orrery/test_claim_propagation_live.py::test_resolution_free_commit_still_drains
ERROR tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum
ERROR tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge
ERROR tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle
ERROR tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly
ERROR tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways
```

The runtime-status failure is fixed locally and its focused test passes. The corpus failure is the authorization blocker above. Eleven direct-URL failures are the coordinator's #904 repair, now merged but not rerun in this aggregate gate. The other ten IDs are the empty-slot-5 class covered by #885 and amendment four: claim consumption (one), runtime maturation replay (one), stage2a status (five), communication graph (two), and polymorphic patron (one). Their exact IDs and original clean-main reproduction remain in the historical record below. No fresh clean-main worktree was needed or created during this review follow-up.

Coordinator action: resolve the Postgres.app client authorization refusal and authorize resumption. Then rerun both aggregate gates on the merged revision, confirm only #885 remains in PostgreSQL, update this record, commit any necessary fixes, and push the review commits to PR #902. Do not merge the PR. The original production migration and live-save drain remain coordinator-owned. Per-chunk embedding, summary plans, and downloads remain unchanged.

Codex — GPT-6 Astra

---

## Historical Implementation Verification at a6911888

The following evidence is from the prior implementation turn. It is retained for the bounded paid call, original corpus/turn proofs, and baseline reproduction; the stop status above supersedes its publication-readiness statements.

The implementation resumes commit `93110ff3` and incorporates coordinator repair #901 by merging `origin/main` at `0e5843ff`. The required PostgreSQL gate's 21 failing IDs were reproduced exactly on clean `origin/main`; no branch-only failure appeared. Those baseline defects are outside the order's changed files and are recorded below under the third amendment. The owner’s live queues were not drained. One paid call was made in total.

## Files Changed

- `config/reachability_baseline.json` — Register the new production-reachable scheduler modules.
- `migrations/120_deferred_work_owner.sql` — Add scheduler ownership, maturation nonce fields, and durable compaction jobs with schema comments.
- `nexus.toml` — Configure scheduler timing, compaction retries, milestone recovery age, and maturation lease duration.
- `nexus/config/settings_models.py` — Validate scheduler settings and maturation lease duration.
- `nexus/jobs/__init__.py` — Declare the deferred-work package.
- `nexus/jobs/gate.py` — Provide scheduler-local provider checkpoints and current-job reporting.
- `nexus/jobs/scheduler.py` — Implement ownership, heartbeats, idle polling, queue ordering, generation preemption, and shutdown.
- `nexus/jobs/compaction.py` — Enqueue and execute nonce-fenced, retryable correspondence compaction.
- `nexus/agents/orrery/experiences.py` — Report the exact experience job being processed.
- `nexus/agents/orrery/job_queues.py` — Share status for all five queues, scheduler ownership, and unembedded accepted chunks.
- `nexus/agents/orrery/relationship_provenance.py` — Allow age-scoped recovery through the existing transactional milestone emitter.
- `nexus/agents/orrery/retrograde_maturation.py` — Configure and fence leases, manifests, success, and failure writes.
- `nexus/agents/orrery/worker.py` — Route the operator entry through scheduler ownership and shared status.
- `nexus/api/commit_handler_sync.py` — Enqueue compaction in acceptance and remove paid compaction from the request path.
- `nexus/api/mock_openai.py` — Add deterministic TEST responses for experience rendering and compaction.
- `nexus/api/narrative.py` — Own the scheduler in lifespan and replace post-commit threads with wake signals.
- `nexus/api/runtime_status.py` — Include shared deferred-work status in the runtime payload.
- `nexus/cli.py` — Render compact scheduler and nonempty-queue status lines.
- `scripts/api_anthropic.py` — Checkpoint before provider requests, including structured-output repair attempts.
- `scripts/api_openai.py` — Checkpoint before provider requests, including structured-output repair attempts.
- `scripts/qa_shift/qa_shift.py` — Validate expanded queue status without assigning attempt or lease semantics to milestones.
- `tests/scheduler_helpers.py` — Create isolated TEST-provider configuration for real integration proofs.
- `tests/test_api/test_scheduler_pg.py` — Prove ownership, takeover, idle drain, generation waiting, recovery, status, and maturation fencing on disposable databases.
- `tests/test_api/test_narrative_post_commit.py` — Update approval and cancellation assertions to scheduler wakeup semantics.
- `tests/test_commit_handler_sync.py` — Replace the compaction double with a real PostgreSQL failure/retry proof through TEST.
- `tests/test_orrery/test_character_experiences_pg.py` — Update the removed post-commit entry-point pin.
- `tests/test_orrery/test_retrograde_maturation.py` — Adapt existing maturation tests to connection and nonce fencing requirements.
- `tests/test_orrery/test_worker.py` — Replace the competing-drain entry-point pin with real ownership exclusion.
- `tests/test_qa_shift.py` — Retain QA assertions under the expanded queue contract.
- `docs/qa/800-job-owner/verification.md` — Replace the stop report with this verification record.

- `tests/test_api/test_scheduler_corpus_pg.py` — Prove corpus recovery, real turn priority, and the provider checkpoint against disposable clones.
- `tests/test_orrery/test_narration_job_fencing_pg.py` — Prove operator ownership exclusion and idempotent narration through the scheduler.
- `tests/test_mock_openai.py` — Pin the TEST replacement event to the registered vocabulary.

## Environment and Isolation

All branch commands ran in `/Users/pythagor/nexus/.claude/worktrees/800-job-owner`, on `claude/800-job-owner`, using the shared interpreter. No dependency installation was performed. No UI code changed and no UI build was run.

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-job-owner/nexus/__init__.py
```

Disposable databases were created and removed by `tests/pg_fixtures.py`; manual proof clones used `qa640_*`. Migration 120 was applied only to disposable databases. Neither the template nor the save fleet was migrated. The broader repository tests retained their own unchanged fixture routing, including rollback-only slot-5 fixtures. No app was started on 8002 or 8012.

The HTTP proof used the actual gateway app and lifespan on 8017, with only slot routing redirected to its disposable database. The fixture checked `lsof -nP -iTCP:8017 -sTCP:LISTEN`, retained a bound socket while starting Uvicorn, stopped its own server, and ran `nexus down` with the same `NEXUS_GATEWAY_PORT=8017`, `NEXUS_API_URL=http://127.0.0.1:8017`, and private runtime config. It did not register a supervisor pidfile, so after its Uvicorn teardown the CLI correctly printed `nothing running`.

## Proofs

- Exclusive ownership and expired takeover: `tests/test_api/test_scheduler_pg.py:59` uses two owners against one real database; the observer cannot run a pass, then acquires after expiry. The stale owner cannot renew or release its successor's lease.
- Idle drain and interactive priority: `tests/test_api/test_scheduler_pg.py:76` leaves a due narration queued at zero attempts while a real generation lease is live, then drains without a commit when it clears.
- Interrupted job recovery: `tests/test_api/test_scheduler_pg.py:114` and `:235` seed an expired domain lease and demonstrate recovery by a successor, including two actual gateway lifespans. The stop operation leaves scheduler ownership expired.
- Maturation fence: `tests/test_api/test_scheduler_pg.py:132` rejects a stale completion nonce and accepts the current one.
- Provider checkpoint: `tests/test_api/test_scheduler_corpus_pg.py:192` starts an interactive lease after an experience job is already leased. No TEST HTTP call/usage occurs while the generation lease is live; the real render resumes when it clears.
- Real accepting turn: `tests/test_api/test_scheduler_corpus_pg.py:112` uses the existing save_04 draft on a clone, calls `nexus continue --slot 4 --choice 1 --json`, commits chunk 50, completes actual LORE/Skald/Gaia generation with TEST, and observes commit → generation → render. The observers invoke the real functions; generation, acceptance, queue execution, and HTTP provider calls are not replaced.
- Transactional milestones: `tests/test_api/test_scheduler_pg.py:186` recovers two old crossings, preserves their historical source or latest primary head, leaves a fresh crossing pending, and emits no duplicates on a second pass. No attempts or leases were added to this outbox.
- Compaction: `tests/test_commit_handler_sync.py:773` proves durable failure/retry via real SQL and TEST. The live turn also completed a scheduler compaction after acceptance. Enqueue is inside acceptance (`nexus/api/commit_handler_sync.py:765`); the request path no longer calls the provider.
- Operator contract: `tests/test_orrery/test_narration_job_fencing_pg.py:756` proves that the CLI observes an existing owner, drains once after release, clears domain fencing fields, and creates no duplicate descriptor on repeat.

### Corpus Drain and Paid Call

The source read-only query returned nine queued experience jobs, IDs 1–9, with attempts `[1,1,0,0,0,0,0,0,0]`. The proof cloned `save_04` into `qa640_800_corpus_2ca9e83ce622`; no source rows were updated. It executes the actual CLI parser/command in the fixture process so `nexus jobs` reads the clone through its real status source.

Before, verbatim:

```text
$ nexus jobs --slot 4
scheduler: no owner
experience_render: queued=9, leased=0, succeeded=0, failed=0, stale_rejected=0
retrograde_maturation: queued=0, leased=0, succeeded=3, failed=0
unembedded_accepted_chunks: 1
```

One scheduler operator pass rendered 12 recollections for job 3 using the configured OpenAI model. Structured-output repair retries were disabled and the pass was limited to one experience job, with narration and maturation limits zero. The remaining jobs drained through TEST on the idle loop without a commit. A clone-only re-promotion of a real resolution lacking an offscreen descriptor supplied the deterministic narration proof; test promotion thresholds were zero only in the private TEST config.

```text
Paid scheduler pass: {'owner': True, 'drained': True, 'promotion': (0, 0), 'orrery_narration_jobs': [0, 0], 'character_experience_jobs': [12, 0], 'orrery_maturation_jobs': [0, 0], 'relationship_milestone_queue': 0}
```

Every paid call's provider-reported token counts (exactly one call total, below the four-call bound):

```text
Paid usage: [{"aggregate": false, "attempt": 1, "cache_creation_tokens": null, "cached_input_tokens": 0, "input_tokens": 2160, "model": "gpt-5.6-sol", "outcome": "accepted", "output_tokens": 650, "provider": "openai", "quota_day": "2026-09-23", "reasoning_tokens": 87, "request_id": "resp_05f4e20ba05336cc006ab45e17403c87d28ff19c05878b5d9f", "requests": null, "run_id": "3", "seat": "experience_renderer", "service_tier": "default", "slot": 4, "total_tokens": 2810, "transport": "responses", "ts": "2026-09-23T23:17:54.596609Z"}]
```

The clone had no available maturation job: `SELECT id,state FROM orrery_maturation_jobs ORDER BY id` returned `[(15, 'succeeded'), (16, 'succeeded'), (17, 'succeeded')]`. The conditional real maturation proof therefore did not apply. Deterministic narration uses no provider call.

```text
Original jobs after: [(1, 'succeeded', 2), (2, 'succeeded', 2), (3, 'succeeded', 1), (4, 'succeeded', 1), (5, 'succeeded', 1), (6, 'succeeded', 1), (7, 'succeeded', 1), (8, 'succeeded', 1), (9, 'succeeded', 1)]
```

After, verbatim:

```text
$ nexus jobs --slot 4
scheduler: owner=gateway:91845:21a709bc-99a8-436f-9e01-c6bd54386c53 active=True heartbeat=2026-09-23 23:17:56.719834+00 job=orrery_maturation_jobs
narration: queued=0, leased=0, succeeded=1, failed=0, stale_rejected=0
experience_render: queued=0, leased=0, succeeded=9, failed=0, stale_rejected=0
retrograde_maturation: queued=0, leased=0, succeeded=3, failed=0
unembedded_accepted_chunks: 1
```

### Live Ordering and Status

The fixture first makes the existing jobs unavailable, then makes them due immediately after the real accepting transaction while the continue route owns the generation lease. It observes real progress and real job-lease reporting. Monotonic timestamps from the passing run:

```text
Live ordering: [('commit', 456046.413612083), ('generation', 456046.444279708), ('render', 456078.821933291), ('render', 456078.932501791)]
```

The CLI generation response was successful; the incubator contains the resulting TEST turn. The accepted chunk was available before maintenance began. This proof exercises real generation rather than merely inspecting the BackgroundTasks list.

```text
$ nexus status
NEXUS runtime - profile local - http://127.0.0.1:8017
SERVICE       STATE    PID  PORT   UPTIME  HEALTH
gateway       stopped  -    8017   -       ok
mock_openai   stopped  -    61570  -       ok
llama_server  stopped  -    1234   -       -
database      -        -    -      -       ok (qa640_800_turn_3a930723c422)
database pooled: pythagor@(default Unix socket):5432/qa640_800_turn_3a930723c422
database url: pythagor@(default Unix socket):5432/qa640_800_turn_3a930723c422
version 0.1.0 - slot 4 - auth X-Nexus-Auth (not enforced)
scheduler: owner=gateway:95925:f2707abb-faac-42cf-b686-87fb88421754 active=True heartbeat=2026-09-23 23:20:06.943357+00 job=orrery_narration_jobs
narration: queued=6, leased=1, succeeded=3, failed=0, stale_rejected=0
experience_render: queued=7, leased=0, succeeded=2, failed=0, stale_rejected=0
retrograde_maturation: queued=0, leased=0, succeeded=3, failed=0
correspondence_compaction: queued=0, leased=0, succeeded=1, failed=0, stale_rejected=0
unembedded_accepted_chunks: 2
```

`GET http://127.0.0.1:8017/runtime/status`, verbatim JSON (a later snapshot than the CLI output, while queues were draining):

```json
{"auth": {"enforced": false, "header": "X-Nexus-Auth"}, "database": {"dbname": "qa640_800_turn_3a930723c422", "ok": true, "slot": 4, "targets": {"pooled": {"dbname": "qa640_800_turn_3a930723c422", "host": "", "port": 5432, "user": "pythagor"}, "url": {"dbname": "qa640_800_turn_3a930723c422", "host": "", "port": 5432, "user": "pythagor"}}}, "jobs": {"counts": {"failed": 0, "leased": 1, "pending": 0, "queued": 12, "stale_rejected": 0, "succeeded": 10}, "non_terminal_jobs": [{"attempts": 1, "available_at": "2026-09-23T23:19:32.925803+00:00", "batch_ordinal": 0, "boundary_chunk_id": 49, "experience_ids": [11, 12, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24], "id": 1, "last_error": "Experience 16 names entities absent from its source scene: ['Sitting']", "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 1, "available_at": "2026-09-23T23:19:32.925807+00:00", "batch_ordinal": 1, "boundary_chunk_id": 49, "experience_ids": [25, 26, 27, 28, 30, 31, 32, 33, 34, 35, 36, 37], "id": 2, "last_error": "Experience 26 names entities absent from its source scene: ['Dr', 'Sera Vey']", "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925674+00:00", "batch_ordinal": 4, "boundary_chunk_id": 49, "experience_ids": [62, 63, 64, 67, 68, 69, 70, 71, 72, 73, 74, 75], "id": 5, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925678+00:00", "batch_ordinal": 5, "boundary_chunk_id": 49, "experience_ids": [76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87], "id": 6, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925681+00:00", "batch_ordinal": 6, "boundary_chunk_id": 49, "experience_ids": [88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99], "id": 7, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925684+00:00", "batch_ordinal": 7, "boundary_chunk_id": 49, "experience_ids": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111], "id": 8, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925686+00:00", "batch_ordinal": 8, "boundary_chunk_id": 49, "experience_ids": [112, 113, 114, 122, 123, 124, 125, 126, 127, 128], "id": 9, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 1, "available_at": "2026-09-23 23:20:06.797471+00", "id": 14, "last_error": null, "lease_until": "2026-09-23 23:25:07.03904+00", "queue": "narration", "state": "leased"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 15, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 16, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 17, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 18, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 19, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}], "queues": {"correspondence_compaction": {"counts": {"failed": 0, "leased": 0, "queued": 0, "stale_rejected": 0, "succeeded": 1}, "non_terminal_jobs": []}, "experience_render": {"counts": {"failed": 0, "leased": 0, "queued": 7, "stale_rejected": 0, "succeeded": 2}, "non_terminal_jobs": [{"attempts": 1, "available_at": "2026-09-23T23:19:32.925803+00:00", "batch_ordinal": 0, "boundary_chunk_id": 49, "experience_ids": [11, 12, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24], "id": 1, "last_error": "Experience 16 names entities absent from its source scene: ['Sitting']", "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 1, "available_at": "2026-09-23T23:19:32.925807+00:00", "batch_ordinal": 1, "boundary_chunk_id": 49, "experience_ids": [25, 26, 27, 28, 30, 31, 32, 33, 34, 35, 36, 37], "id": 2, "last_error": "Experience 26 names entities absent from its source scene: ['Dr', 'Sera Vey']", "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925674+00:00", "batch_ordinal": 4, "boundary_chunk_id": 49, "experience_ids": [62, 63, 64, 67, 68, 69, 70, 71, 72, 73, 74, 75], "id": 5, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925678+00:00", "batch_ordinal": 5, "boundary_chunk_id": 49, "experience_ids": [76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87], "id": 6, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925681+00:00", "batch_ordinal": 6, "boundary_chunk_id": 49, "experience_ids": [88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99], "id": 7, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925684+00:00", "batch_ordinal": 7, "boundary_chunk_id": 49, "experience_ids": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111], "id": 8, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23T23:19:32.925686+00:00", "batch_ordinal": 8, "boundary_chunk_id": 49, "experience_ids": [112, 113, 114, 122, 123, 124, 125, 126, 127, 128], "id": 9, "last_error": null, "lease_until": null, "queue": "experience_render", "scene_end_chunk_id": 48, "state": "queued"}]}, "narration": {"counts": {"failed": 0, "leased": 1, "queued": 5, "stale_rejected": 0, "succeeded": 4}, "non_terminal_jobs": [{"attempts": 1, "available_at": "2026-09-23 23:20:06.797471+00", "id": 14, "last_error": null, "lease_until": "2026-09-23 23:25:07.03904+00", "queue": "narration", "state": "leased"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 15, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 16, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 17, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 18, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}, {"attempts": 0, "available_at": "2026-09-23 23:20:06.797471+00", "id": 19, "last_error": null, "lease_until": null, "queue": "narration", "state": "queued"}]}, "relationship_milestone": {"counts": {"pending": 0}, "non_terminal_jobs": []}, "retrograde_maturation": {"counts": {"failed": 0, "leased": 0, "queued": 0, "succeeded": 3}, "non_terminal_jobs": []}}, "scheduler": {"active": true, "current_job": "orrery_narration_jobs", "expires_at": "2026-09-23 23:20:09.943357+00", "heartbeat_at": "2026-09-23 23:20:06.943357+00", "last_error": null, "lease_nonce": "e616aa8f-750b-4dbb-a216-f806f52e3dbf", "owner_id": "gateway:95925:f2707abb-faac-42cf-b686-87fb88421754"}, "unembedded_accepted_chunks": 2}, "ok": true, "profile": "local", "services": {"gateway": {"ok": true, "port": 8017}, "mock_openai": {"ok": true, "port": 61570}}, "slot": 4, "version": "0.1.0"}
```

```text
$ nexus down
nothing running
```


## Commands and Verbatim Tails

The same worktree import check above applies to all branch commands. Log files are retained under gitignored `temp/800-validation/`; this document preserves the commands and decisive output. Offline skips are the repository's opt-in integration tests, not a PostgreSQL pass. All new scheduler PostgreSQL proofs actually ran.

### Offline Gate

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2624 passed, 781 skipped, 9 warnings in 92.77s (0:01:32)
```

### Required PostgreSQL Gate

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_qa_shift.py -k 'job or drain or worker or lease or scheduler or maturation or experience or compaction or status'
```

```text
8 failed, 206 passed, 1 skipped, 1711 deselected, 11 warnings, 13 errors in 115.84s (0:01:55)
```

The remaining IDs and their clean-base reproduction are listed below; these are permitted baseline exceptions under amendment three, not zero-failure output.

### Paid Corpus Proof

```sh
NEXUS_800_PAID_PROOF=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_corpus_pg.py
```

```text
1 passed, 7 warnings in 16.00s
```

At this invocation the file contained only the corpus test. No later invocation set `NEXUS_800_PAID_PROOF`.

### TEST Corpus Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_corpus_pg.py
```

```text
1 passed, 7 warnings in 4.57s
```

This invocation also preceded addition of the live-turn and provider-checkpoint tests.

### Real Turn Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_scheduler_corpus_pg.py -k live_turn
```

```text
1 passed, 1 deselected, 9 warnings in 36.18s
```

### Milestone and Operator Fences

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_scheduler_pg.py tests/test_orrery/test_narration_job_fencing_pg.py -k 'milestone or operator'
```

```text
2 passed, 12 deselected, 7 warnings in 3.44s
```

### Gateway Restart and Provider Checkpoint

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_scheduler_pg.py tests/test_api/test_scheduler_corpus_pg.py -k 'restart or rechecks'
```

```text
2 passed, 7 deselected, 7 warnings in 5.63s
```

### Compaction Retry

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler_sync.py -k post_commit_compaction
```

```text
1 passed, 13 deselected, 5 warnings in 3.18s
```

### Black and Configuration

```sh
PYTHONPATH=$PWD $PY -m black --check nexus/jobs nexus/agents/orrery/{job_queues,worker,experiences,retrograde_maturation,relationship_provenance}.py nexus/api/{narrative,mock_openai,commit_handler_sync,runtime_status}.py nexus/cli.py nexus/config/settings_models.py scripts/{api_openai,api_anthropic}.py scripts/qa_shift/qa_shift.py tests/test_api/{test_scheduler_pg,test_scheduler_corpus_pg,test_narrative_post_commit}.py tests/test_orrery/{test_worker,test_retrograde_maturation,test_character_experiences_pg,test_narration_job_fencing_pg}.py tests/test_commit_handler_sync.py tests/test_qa_shift.py tests/test_mock_openai.py tests/scheduler_helpers.py
```

```text
All done! ✨ 🍰 ✨
29 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY -c 'from nexus.config import load_settings; s=load_settings(); print("nexus.toml: valid"); print(s.runtime.scheduler)'
```

```text
nexus.toml: valid
lease_duration_seconds=60.0 heartbeat_interval_seconds=10.0 poll_interval_seconds=5.0 generation_wait_seconds=0.1 error_backoff_seconds=5.0 milestone_recovery_age_seconds=60.0 promotion_limit=20 compaction_max_jobs_per_drain=1 compaction_max_attempts=3 compaction_retry_delay_seconds=300.0 compaction_lease_duration_seconds=300.0
```

`git diff --check` returned zero with no output.

### Earlier Attempts During This Resume

The initial post-#901 branch run used the same required PostgreSQL command:

```text
8 failed, 200 passed, 1 skipped, 1711 deselected, 9 warnings, 13 errors in 54.23s
```

The first TEST corpus invocation returned `1 failed, 7 warnings in 4.33s`: its proof setup selected a resolution that already had a descriptor. The corrected setup chooses a real resolution without one, preserving idempotency constraints; the passing rerun is above.

The first live-turn invocation returned `1 failed, 1 deselected, 9 warnings in 40.66s`: TEST's obsolete `mock_replacement` event failed the production registry validator. The TEST response now emits registered `work_performed`, with the existing assertion updated. The CLI invocation also moved to a subprocess to keep gateway diagnostic stdout separate from JSON output; the actual gateway remained on 8017.

The first milestone test command was:

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_scheduler_pg.py -k milestone tests/test_orrery/test_narration_job_fencing_pg.py
```

```text
1 failed, 13 deselected, 5 warnings in 1.18s
```

Its fixture omitted mandatory relationship prose columns. The fixture now supplies those columns; the passing rerun is above.

## Clean-Main Reproduction and Gate Remainder

The coordinator explicitly authorized this temporary exception to the one-worktree rule. No shared dependencies were installed. Import resolution was verified inside the throwaway checkout before running the gate:

```sh
git worktree add --detach temp/800-main-proof origin/main
cd temp/800-main-proof
PYTHONPATH=$PWD $PY -c 'import nexus; print(nexus.__file__)'
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_qa_shift.py -k 'job or drain or worker or lease or scheduler or maturation or experience or compaction or status'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-job-owner/temp/800-main-proof/nexus/__init__.py
```

```text
8 failed, 198 passed, 1 skipped, 1709 deselected, 11 warnings, 13 errors in 53.27s
```

Clean base was `0e5843ff` (#901). Comparing exact failing ID sets produced:

```text
pg-main.log 21
pg-resumed.log 21
Branch-only failures: set() Base-only failures: set()
```

`git worktree remove temp/800-main-proof` completed successfully. All rows below reproduce on that clean base. “Touches Order Files” means the failing source/fixture and its causal defect are changed by this order; none are. The replay maturation test fails before the maturation implementation is called.

| Failing ID | One-Line Cause | Reproduces on Clean Main | Touches Order Files |
|---|---|---|---|
| `tests/test_orrery/test_claim_consumption_live.py::test_template_gate_flips_on_drain_with_production_explain_parity` | Empty save_05 has neither canonical world time nor base_timestamp; character fixture insertion fails the need-clock trigger. | Yes | No |
| `tests/test_orrery/test_claim_propagation_live.py::test_async_drain_matches_sync_single_hop` | Direct asyncpg URL decodes an empty host into five defaults but retains one port: `could not match 1 port numbers to 5 hosts`. | Yes | No |
| `tests/test_orrery/test_replay.py::test_runtime_maturation_death_replays_without_drift` | Empty save_05 makes fixture `SELECT max(id)+1` NULL; chunk insert violates the id constraint before maturation runs. | Yes | No |
| `tests/test_orrery/test_stage2a_status_live.py::test_retrograde_institutional_standing_persists_status_edge` | Empty save_05 has neither canonical world time nor base_timestamp; character fixture insertion fails the need-clock trigger. | Yes | No |
| `tests/test_orrery/test_stage2a_status_live.py::test_retrograde_status_skips_existing_live_standing_with_dry_run_parity` | Empty save_05 has neither canonical world time nor base_timestamp; character fixture insertion fails the need-clock trigger. | Yes | No |
| `tests/test_orrery/test_stage2a_status_live.py::test_wizard_time_retrograde_status_keeps_source_chunk_null` | Empty save_05 has neither canonical world time nor base_timestamp; character fixture insertion fails the need-clock trigger. | Yes | No |
| `tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_applies_and_hydrates_for_predicate` | Empty save_05 returns no required fixture row (`NoResultFound`). | Yes | No |
| `tests/test_orrery/test_stage2a_status_live.py::test_declaration_status_hint_resolves_same_batch_faction` | Empty save_05 has no head chunk; fixture calls `int(None)`. | Yes | No |
| `tests/test_orrery/test_claim_propagation_live.py::test_large_skip_drains_chained_hops_at_staggered_times` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_claim_propagation_live.py::test_depth_cap_is_recovered_across_separate_drains` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_claim_propagation_live.py::test_late_drain_lands_hop_scheduled_inside_age_horizon` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_claim_propagation_live.py::test_non_primary_commit_skips_propagation_drain` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_claim_propagation_live.py::test_idempotent_redrain_and_disabled_config_are_noops` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_claim_propagation_live.py::test_resolution_free_commit_still_drains` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_communication_graph_live.py::test_channel_directionality_and_status_minimum` | Empty save_05 has neither canonical world time nor base_timestamp; character fixture insertion fails the need-clock trigger. | Yes | No |
| `tests/test_orrery/test_communication_graph_live.py::test_faction_subject_status_yields_parent_to_member_faction_edge` | Empty save_05 has neither canonical world time nor base_timestamp; character fixture insertion fails the need-clock trigger. | Yes | No |
| `tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle` | Empty save_05 returns no required fixture row (`NoResultFound`). | Yes | No |
| `tests/test_orrery/test_reveal_live.py::test_commit_reveals_promotes_grants_once_and_redrain_is_noop` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_writes_exclusive_pair_tag_with_provenance` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_and_raw_status_fail_loudly` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |
| `tests/test_orrery/test_status_bestow_delta_live.py::test_status_bestow_floor_prevents_demotion_and_set_replaces_both_ways` | Direct psycopg2 consumer passes the SQLAlchemy-escaped URL unchanged: `unrecognized configuration parameter "+TimeZone"`. | Yes | No |

The named #885 remainder selected by this gate is `tests/test_orrery/test_polymorphic_patron_live.py::test_roster_start_to_status_completion_closes_institutional_circle`. Nine additional empty-save_05 fixture failures and eleven direct-URL failures are listed individually above as independently reproduced baseline debt under amendment three; they are not silently added to the narrower named exemption. No other named #885 ID failed in this selected gate.

## Final Isolation and Merge Check

`git fetch origin && git merge origin/main` was repeated before publication and returned `Already up to date.` No protected presence, prompt-budget/trimming, or usage source file appears in the branch diff.

After all proofs, the read-only query `SELECT id,state::text,attempts FROM character_experience_jobs ORDER BY id` against save_04 returned:

```text
Live save_04 remains: [(1, 'queued', 1), (2, 'queued', 1), (3, 'queued', 0), (4, 'queued', 0), (5, 'queued', 0), (6, 'queued', 0), (7, 'queued', 0), (8, 'queued', 0), (9, 'queued', 0)]
Remaining order-owned clone databases: []
```

The latter line is from `SELECT datname FROM pg_database WHERE datname LIKE 'qa640_800_%'`. `lsof -nP -iTCP:8017 -sTCP:LISTEN` returned 1 with no output after teardown.

## Deferred Work and Coordinator Handoff

- The coordinator applies migration 120 to the fleet/template at land time, then restarts the production gateway and drains live save_04 there. No production drain was attempted here.
- Per-chunk embedding subprocesses, durable summary plans, and the download process remain unchanged. In the disposable live-turn proof the existing embedding path rejects the non-save database name; it logs that error and leaves the unembedded count truthful. That separate path is explicitly outside this work order.
- Presence modules, prompt-budget/trimming modules, and usage telemetry were not edited. Existing prompt prose was not changed. TEST provider response data was corrected to satisfy the existing registry.
- A real maturation provider call was conditional on available clone work; none existed. Long provider calls remain uncancelled by the scheduler; shutdown stops new dispatch within the configured grace and domain nonce/expiry recovery owns any unfinished attempt. A paid request deliberately exceeding the shutdown grace was not performed.
- No open implementation question remains for the coordinator. The baseline fixture/URL defects above need their own repairs; they were not changed under this order.

Codex — GPT-6 Astra
