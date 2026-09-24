# Connection Preflight Verification

Work order 804-B, branch `claude/804-connection-preflight`, lane **8017**.
No schema migration, paid call, fleet migration, or production-slot replacement.
The interpreter import proof printed:

```text
/Users/pythagor/nexus/.claude/worktrees/804-connection-preflight/nexus/__init__.py
```

All commands below run from that worktree with
`PY=/Users/pythagor/nexus/.venv/bin/python` and `PYTHONPATH=$PWD`.

## Scope and Behavior

- `nexus/config/settings_models.py:3403` and `nexus.toml:191`: validated pool minimum
  1, maximum 10, idle preflight interval 0, application prefix `nexus`.
- `nexus/api/db_pool.py:110`: closed/non-idle rejection and `SELECT 1` preflight;
  `:130`: one replacement, transaction cleanup, no replay.
- `nexus/database.py:23`: terminal `AmbiguousCommit`; `:48`: commit-once boundary;
  `:27`: wrapped driver/domain error recognition; `:86`: registered engine factory.
- `nexus/api/db_pool.py:224`: disposal invalidates both clients. The script reset,
  clone, API reset, and QA clone/restore paths call it before returning.
- The tree contains more engine sites than the order's historical count. Every
  `create_engine(` call under `nexus/` and `scripts/` now resides in the factory.
  `resolved_database_url` remains because target verification and external callers
  still use its normalization contract.
- Backend roles are `sync`, `asyncpg`, `sqlalchemy`, `subprocess`; suffix is gateway
  port, otherwise PID. Only proof backends with the exact lane label, database,
  and PID were terminated. No PostgreSQL server was restarted or stopped.

## Real Endpoint Proof

[Probe source](endpoint_probe.py) mounts the unchanged production setup router
with the real reset, pool, factory, dump/restore, and slot initialization code.
It redirects slot 4 to **qa640_804_endpoint before importing route consumers** and
rejects every other gameplay target. The maintenance database is used for admin
work; the template is read only. Unrelated gateway startup jobs are excluded.
The existing supervisor owns the process and lane-specific state directory.
This is an HTTP route proof, not a browser/UI or full gameplay proof.

```sh
lsof -nP -iTCP:8017 -sTCP:LISTEN
NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 PYTHONPATH=$PWD $PY docs/qa/804-connection-preflight/endpoint_probe.py prepare
NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 NEXUS_RUNTIME_CONFIG=$PWD/temp/804-preflight/endpoint.toml PYTHONPATH=$PWD $PY docs/qa/804-connection-preflight/endpoint_probe.py up
```

`lsof` returned no listener before startup. `urllib.request` sent a real
`POST http://127.0.0.1:8017/api/story/new/setup/reset` with `{"slot":4}`; `/proof`
read database OIDs and backend PIDs through both clients before and after.
[Exact response and SQL identities](endpoint.json): HTTP **200**,
`{"status":"reset","slot":4}`; old pool/engine OID **41180112**, new pool/engine
OID **41222344**, pool PID **44667 → 44709**. The retained engine object resolved
the newly created database after disposal. Template stamps required **0** pending
migrations on the disposable target.

Cleanup used the same lane and config:

```sh
NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 NEXUS_RUNTIME_CONFIG=$PWD/temp/804-preflight/endpoint.toml PYTHONPATH=$PWD $PY -m nexus.cli down
NEXUS_GATEWAY_PORT=8017 NEXUS_API_URL=http://127.0.0.1:8017 NEXUS_RUNTIME_CONFIG=$PWD/temp/804-preflight/endpoint.toml PYTHONPATH=$PWD $PY docs/qa/804-connection-preflight/endpoint_probe.py cleanup
```

```text
stopped gateway (pid 44525)
{"dropped": "qa640_804_endpoint"}
```

`lsof -nP -iTCP:8017 -sTCP:LISTEN` again returned no listener.

## Retry-Wrapper Audit

Search: `rg -n 'tenacity|retry|OperationalError' nexus` plus inspection of broad
exception handlers and transaction contexts. No tenacity wrapper exists.
Connection failures include nested `__cause__`, `__context__`, and SQLAlchemy
`orig`; they must not become retries through a domain exception wrapper.

| Wrapper / Path | Evidence | Why It Cannot Replay an Unknown Commit |
| --- | --- | --- |
| Sync backoff decorator | `nexus/api/retry_handler.py:122` | Retries only provider rate limits/timeouts; removed PostgreSQL retry branch. |
| Async backoff decorator | `nexus/api/retry_handler.py:179` | Only provider rate limits/timeouts; all database errors escape. |
| Circuit breaker sync / async | `nexus/api/retry_handler.py:258`, `:275` | Calls once and rethrows; counter updates do not re-invoke the callable. |
| Timeout decorator | `nexus/api/retry_handler.py:328` | Calls once, restores the alarm handler; no replay. |
| Fallback sync / async | `nexus/api/retry_handler.py:375`, `:400` | Connection failure, including wrapped errors, escapes before trying another strategy. Real tests cover both methods, raw and ambiguous commit errors. |
| Resilient client sync | `nexus/api/resilient_openai.py:72` | Catches OpenAI rate/timeout/API connection classes only; database errors rethrow. |
| Nested resilient object sync | `nexus/api/resilient_openai.py:182` | Same provider-only exception filter. |
| Resilient client async | `nexus/api/resilient_openai.py:265` | Same provider-only exception filter. |
| Nested resilient object async | `nexus/api/resilient_openai.py:362` | Same provider-only exception filter. |
| Scheduler heartbeat | `nexus/jobs/scheduler.py:377` | Commits are classified by `transaction`. AmbiguousCommit stops dispatch via `_recover` at `:336`; a raw pre-commit heartbeat failure may safely reacquire. The real blocked-heartbeat termination regression passes. |
| Scheduler lease/start/run loop | `nexus/jobs/scheduler.py:548`, `:566` | Uses commit-aware transactions. Connection failure sets `failed`, stopping/lost events, and a reconciliation reason; loop cannot reacquire. |
| Scheduler one-pass drain | `nexus/jobs/scheduler.py:407` | Rethrows terminal failures; suppresses release SQL after terminal stop. |
| Narration outbox requeue | `nexus/agents/orrery/worker.py:367` | Connection failures escape before `_mark_narration_failed`. |
| Maturation requeue | `nexus/agents/orrery/retrograde_maturation.py:669` | Connection failures escape before `_mark_maturation_failed`. |
| Experience-render requeue | `nexus/agents/orrery/experiences.py:2098` | Connection failures escape before `_fail_render`. |
| Correspondence-compaction requeue | `nexus/jobs/compaction.py:93` | Connection failures escape before assigning queued/failed state. |
| Narrative lease acquisition/binding/claims/finish | `nexus/api/narrative_lease.py:35`, `:119`, `:157`, `:227` | Commits use `commit_transaction`; explicit AmbiguousCommit branches preserve the terminal error before rollback. No loop. |
| Narrative heartbeat/session read | `nexus/api/narrative_lease.py:347`, `:371`; `nexus/api/narrative_generation.py:200` | Commit-aware context; heartbeat failure cancels its owner and exits instead of retrying. |
| Wizard Pydantic tool repair | `nexus/api/wizard_agent.py:250`, `:549` | ModelRetry represents input/phase validation; no handler converts a database exception to ModelRetry. Errors propagate. |
| Structured-output repair / validation readers | `nexus/agents/lore/logon_utility.py:1797`; `nexus/api/native_structured_output.py:301` | Database validation reads propagate errors; provider repair is limited to validation/parse failures, not database transactions. |
| Native provider call sites | `nexus/api/new_story_generator.py:87`; `nexus/agents/orrery/geo_authoring.py:80`, `experiences.py:1488`, `retrograde_expansion.py:767`, `retrograde_seed_candidates.py:627` | Configure provider-output validation budgets; they do not wrap database mutations in a database retry. |
| CLI generation status polling | `nexus/cli.py:1815` | Repeats status GET only; original mutation POST is outside the polling loop. |
| Missing-database setup | `nexus/api/new_story_flow.py:128` | OperationalError catch surrounds connect/close only; no commit or body mutation can enter that catch. |
| Slot-list availability handling | `nexus/api/setup_endpoints.py:190` | Reads each slot once and records unavailable status; no mutation replay. |
| Embedding retry diagnostics | `nexus/agents/orrery/experience_embedding.py:100`, `retrograde_embedding.py:124`; `nexus/api/chunk_workflow.py:532` | Error messages/manual recovery state, not automatic transaction retry wrappers. |
| Runtime health/log/supervision loops | `nexus/runtime/supervisor.py:363`, `:748`, `:762` | Health GETs, log reads, process supervision; no mutation closure replay. Ambiguous scheduler failure leaves the gateway alive with stopped dispatch. |
| LORE/websocket loops | `nexus/agents/lore/lore.py:867`; `nexus/api/narrative.py:1517`; `nexus/api/storyteller.py:541` | Receive the next user message; no automatic replay of a failed operation. |

Other search hits are prompt identifiers, validation diagnostics, tunable field
names, graph sampling, and operator recovery messages. A stopped scheduler needs
operator reconciliation before restart; this change makes no durable recovery
claim across process restarts.

## Gates and Termination Logs

The first exploratory full-suite run overlapped the configuration edit: its
already-imported old Pydantic model rejected the new TOML fields (511 failures,
12 errors). It is invalid as either baseline or implementation evidence and was
superseded by complete fresh-process runs. An initial focused run also identified
an explicit async application-name compatibility expectation and the required
reachability-ratchet removal for the newly tested retry module; both were fixed.
The rollback-failure proof was corrected to open a transaction before backend
termination, because rollback of an idle connection performs no network I/O.

The exact historical command with both the explicit test file and its directory
collects only that file in this pytest installation. Therefore the API directory
was also run separately, so the remaining selected tests actually executed.
The first scheduler regression run found an overbroad terminal classification for
a heartbeat killed while waiting on a lock, before commit. That safe recovery is
now retained: heartbeat writes use the commit-aware transaction context, so a
raw heartbeat driver error is known to precede commit; AmbiguousCommit still
stops dispatch. The failing regression and all 14 new tests then passed together.

The sole API selection failure is the explicitly exempt #885 test:
`tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts`.

Backend termination SQL (each proof supplies its own values):

```sql
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE pid = %s AND datname = %s AND application_name = %s;
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q -s tests/test_api/test_db_pool_pg.py
```

Selected verbatim logs:

```text
2026-09-24 18:26:57,377 - nexus.api.db_pool - INFO - Replacing connection for database qa640_804_c8ad5cb14fa6: server closed the connection unexpectedly
terminated database=qa640_804_c8ad5cb14fa6 pid=45230 application_name=nexus:sync:8017
replacement_count=1 new_pid=45234
terminated database=qa640_804_5e816b337197 pid=45238 application_name=nexus:sync:8017
body_failure_discarded=True new_pid=45242
terminated database=qa640_804_77734f8d4579 pid=45246 application_name=nexus:sync:8017
Ambiguous commit for database qa640_804_77734f8d4579: server closed the connection unexpectedly
; mutation_attempts=1 sequence_last_value=1 committed_rows=0
terminated database=qa640_804_b2e4a6fbb2bf pid=45256 application_name=nexus:sqlalchemy:8017
sqlalchemy_pre_ping=True old_pid=45256 new_pid=45260
clone_disposed=True old_oid=41226524 new_oid=41226536
2026-09-24 18:26:58,461 - nexus.api.db_pool - INFO - Replacing connection for database qa640_804_96d34e71d9e8: connection is closed
2026-09-24 18:26:58,635 - nexus.api.db_pool - INFO - Replacing connection for database qa640_804_8813c59d1475: connection transaction is not idle
terminated database=qa640_804_0e0ca029b8a2 pid=45297 application_name=nexus:sync:8017
terminated database=qa640_804_dbf9b9839ac9 pid=45305 application_name=nexus:sync:8017
fallback_async=False raw_commit=False attempts=1 scheduler=failed
terminated database=qa640_804_0d630e5d399b pid=45311 application_name=nexus:sync:8017
fallback_async=False raw_commit=True attempts=1 scheduler=failed
terminated database=qa640_804_303c1354aab7 pid=45318 application_name=nexus:sync:8017
fallback_async=True raw_commit=False attempts=1 scheduler=failed
terminated database=qa640_804_aed29707fb10 pid=45324 application_name=nexus:sync:8017
fallback_async=True raw_commit=True attempts=1 scheduler=failed
2026-09-24 18:26:59,583 - nexus.api.db_pool - INFO - Replacing connection for database qa640_804_515a8e41d87b: server closed the connection unexpectedly
terminated database=qa640_804_515a8e41d87b pid=45330 application_name=nexus:sync:8017
14 passed, 5 warnings in 2.42s
```

Final gate commands and verbatim tails:

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2726 passed, 915 skipped, 9 warnings in 125.29s (0:02:05)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_db_pool_pg.py tests/test_api -k 'pool or connection or database or slot'
```

```text
14 passed, 5 warnings in 2.94s
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api -k 'pool or connection or database or slot'
```

```text
=========================== short test summary info ============================
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_slots_jointly_exercise_both_parity_contracts
1 failed, 125 passed, 297 deselected, 9 warnings in 17.69s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_scheduler*_pg.py
```

```text
24 passed, 9 warnings in 150.82s (0:02:30)
```

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_reachability.py tests/test_prompt_lint.py tests/test_database_contract.py
```

```text
82 passed, 2 skipped, 5 warnings in 21.58s
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 $PY -m pytest -q tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_recovers_terminated_heartbeat_backend tests/test_api/test_db_pool_pg.py
```

```text
15 passed, 7 warnings in 9.77s
```

```sh
$PY -m black --check $(git diff --name-only origin/main -- '*.py')
```

```text
All done! ✨ 🍰 ✨
41 files would be left unchanged.
```

The changed Python files also passed `flake8 --select F821,F822,F823` with no output.
Both commit hooks passed (Orrery catalog and config/model-ID validation).
The cleanup query `SELECT datname FROM pg_database WHERE datname LIKE 'qa640_804_%' ORDER BY datname` returned no rows.

Open questions: none. The existing #885 empty-slot fixture debt is deferred.
No review or merge is part of this work order.

Codex (GPT-6 Astra)
