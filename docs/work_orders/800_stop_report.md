# STOP-REPORT — Work Order 800

No PR was opened or pushed. The frozen-order implementation is preserved locally and is **not ready to land**. Work stopped at a required PostgreSQL gate that has a failure outside the authorized slot-5 exemption. No paid provider calls were made.

## Blocker and Evidence

The required PostgreSQL command returned `9 failed, 189 passed, 1 skipped, 1711 deselected, 9 warnings, 23 errors in 46.62s`. One failure was this branch's obsolete post-commit test pin; it was corrected and its real PostgreSQL regression passed afterward. The gate was not rerun or declared green.

The independently reproduced blocker is `tests/test_orrery/test_retrograde_projects_live.py::test_maturation_shared_writer_validation_raises`. Its unchanged fixture connects to **save_02** at `tests/test_orrery/test_retrograde_projects_live.py:65`, then deletes relationships at line 95 without setting `nexus.write_producer`. Migration 115's unchanged trigger requires that attribution (`migrations/115_relationship_write_provenance.sql:61`). PostgreSQL raises:

```text
E               psycopg2.errors.RaiseException: Missing or invalid nexus.write_producer: <NULL>
E               CONTEXT:  PL/pgSQL function fn_version_relationship_row() line 13 at RAISE
```

`git diff --quiet HEAD -- tests/test_orrery/test_retrograde_projects_live.py migrations/115_relationship_write_provenance.sql` returned zero. This confirms those source files are unchanged; it is not a claim that the entire modified worktree was rerun as a clean-base checkout. The exception occurs in fixture setup before scheduler execution. The repository fixture owns and rolls back its transaction.

The broad gate also reports the known empty-slot-5 corpus failures, plus direct-connection errors (`unrecognized configuration parameter "+TimeZone"` and `could not match 1 port numbers to 5 hosts`). Those were not repaired or silently exempted. Issue #885 describes 113 prior Orrery failures but does not enumerate the IDs in its current body/comments, so no claim of a complete ID-by-ID exemption match is made.

## Scope and Outstanding Work

- The implementation and focused PostgreSQL proofs are present; the complete work order is unfinished.
- No `qa640_*` data clone of save_04 has been drained. Read-only SQL confirmed nine queued experience jobs, with attempts ranging from zero to one; narration had no rows and maturation had three succeeded rows.
- No paid calls: token accounting is zero, and no real-experience proof is claimed.
- The real-turn TEST ordering proof, full gateway lifespan/restart proof on lane 8017, before/after `nexus jobs`, and pasted live `nexus status` plus `/runtime/status` remain outstanding. The direct shared status reader was exercised by the disposable scheduler test.
- The maturation stale-nonce, exclusive owner/takeover, no-commit idle drain, expired-job restart recovery, generation-lease waiting, cancellation/wakeup, and compaction idle-retry checks passed on fixture-owned databases.
- Long in-flight shutdown behavior, provider wait exceeding a domain lease, and milestone recovery ordering still need dedicated integration coverage and review.
- `tests/test_orrery/test_narration_job_fencing_pg.py` was read and its existing real helper reused, but its operator-contract update remains outstanding.
- Per-chunk embedding subprocesses, durable summary plans, download processes, presence modules, prompt-budget/trimming code, and usage telemetry were not changed.
- No app was started on lane 8017; no listener was present in the checked lane. Test-owned TEST-provider processes were torn down by their fixtures. No fleet or template migration was applied. Migration 120 ran only on disposable fixture databases.
- No final fetch/merge from origin/main was performed because no PR is being opened.

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
- `docs/work_orders/800_stop_report.md` — Record the blocking gate, validation history, scope, and coordinator questions.

## Validation Commands and Verbatim Tail Output

All commands ran from `/Users/pythagor/nexus/.claude/worktrees/800-job-owner` with:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-job-owner/nexus/__init__.py
```

The initial full offline run overlapped edits and is not valid baseline evidence. Its last line was `26 failed, 2601 passed, 768 skipped, 11 warnings in 87.83s (0:01:27)`. The stable full run below passed. Earlier focused failures were fixed and are retained here for auditability. Complete logs are under `temp/800-validation/` (gitignored).

### Stable Offline Gate

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2624 passed, 775 skipped, 9 warnings in 87.61s (0:01:27)
```

### Required PostgreSQL Gate

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_qa_shift.py -k 'job or drain or worker or lease or scheduler or maturation or experience or compaction or status'
```

```text
9 failed, 189 passed, 1 skipped, 1711 deselected, 9 warnings, 23 errors in 46.62s
```

### Independent Blocker Reproduction

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery/test_retrograde_projects_live.py::test_maturation_shared_writer_validation_raises
```

```text
1 error in 0.23s
```

### Final Focused PostgreSQL Proofs

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_scheduler_pg.py tests/test_api/test_narrative_post_commit.py tests/test_orrery/test_worker.py tests/test_commit_handler_sync.py tests/test_orrery/test_character_experiences_pg.py -k 'scheduler or post_commit or operator or cancelled or malformed_event_quarantines'
```

```text
12 passed, 48 deselected, 7 warnings in 11.50s
```

### Compaction Retry Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_commit_handler_sync.py -k post_commit_compaction
```

```text
1 passed, 13 deselected, 5 warnings in 2.95s
```

### Earlier Scheduler Proof Run

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_scheduler_pg.py
```

```text
1 failed, 3 passed, 5 warnings in 4.38s
```

### Earlier Focused PostgreSQL Run

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_scheduler_pg.py tests/test_api/test_narrative_post_commit.py tests/test_orrery/test_worker.py tests/test_commit_handler_sync.py -k 'scheduler or post_commit or operator or cancelled'
```

```text
1 failed, 10 passed, 24 deselected, 7 warnings in 8.65s
```

### Updated Offline Pins

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_narrative_post_commit.py tests/test_orrery/test_worker.py tests/test_orrery/test_retrograde_maturation.py tests/test_qa_shift.py
```

```text
83 passed, 7 skipped, 7 warnings in 3.96s
```

### Initial Offline Pins

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_narrative_post_commit.py tests/test_orrery/test_worker.py tests/test_orrery/test_retrograde_maturation.py tests/test_qa_shift.py tests/test_commit_handler_sync.py
```

```text
25 failed, 74 passed, 5 skipped, 7 warnings in 4.79s
```

### Black and Configuration

```sh
PYTHONPATH=$PWD $PY -m black --check nexus/jobs nexus/agents/orrery/{job_queues,worker,experiences,retrograde_maturation,relationship_provenance}.py nexus/api/{narrative,mock_openai,commit_handler_sync,runtime_status}.py nexus/cli.py nexus/config/settings_models.py scripts/{api_openai,api_anthropic}.py scripts/qa_shift/qa_shift.py tests/test_api/{test_scheduler_pg,test_narrative_post_commit}.py tests/test_orrery/{test_worker,test_retrograde_maturation,test_character_experiences_pg}.py tests/test_commit_handler_sync.py tests/test_qa_shift.py tests/scheduler_helpers.py
```

```text
All done! ✨ 🍰 ✨
26 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY -c 'from nexus.config import load_settings; s=load_settings(); print("nexus.toml: valid"); print(s.runtime.scheduler)'
```

```text
nexus.toml: valid
lease_duration_seconds=60.0 heartbeat_interval_seconds=10.0 poll_interval_seconds=5.0 generation_wait_seconds=0.1 error_backoff_seconds=5.0 milestone_recovery_age_seconds=60.0 promotion_limit=20 compaction_max_jobs_per_drain=1 compaction_max_attempts=3 compaction_retry_delay_seconds=300.0 compaction_lease_duration_seconds=300.0
```

```sh
PYTHONPATH=$PWD $PY scripts/check_reachability.py --write-baseline --reason 'Issue 800 adds gateway-owned scheduler and durable correspondence compaction modules.'
git diff --check
```

Reachability's findings lists were empty; `git diff --check` returned zero with no output. Black formatting was applied before the clean check; no build was run because no UI was changed.

## Coordinator Questions

1. Should the save_02 maturation fixture attribution failure be repaired in a separate prerequisite, or explicitly added to this order's authorized gate repairs?
2. Should the direct URL connection defects be repaired before resuming the required PostgreSQL gate, or are exact affected test IDs exempt?
3. Once the gate prerequisites are resolved, resume the outstanding clone, bounded real-provider, live-turn, runtime-status, and final merge/PR proofs listed above.

Codex — GPT-6 Astra
