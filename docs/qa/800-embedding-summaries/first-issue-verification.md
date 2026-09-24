# Work Order 800-B Verification

Status: **STOP-REPORT — not ready for PR or landing.**

[Full paid-proof output](paid-proof-failure.txt).

The configured real episode-summary provider rejected the first request with HTTP 400. No season request was made and no successful paid summary or token counts were returned. SDK retries and structured-output retries were disabled. No further provider calls were attempted after this failure.

```text
Error code: 400 - {'error': {'message': "Unsupported parameter: 'temperature' is not supported with this model.", 'type': 'invalid_request_error', 'param': 'temperature', 'code': None}}
```

The proof ran on `qa640_800b_paid_3638b6fb18d6`, a disposable copy of `save_04`; its fixture dropped it afterward. The coordinator's two-successful-summary proof remains unmet. Do not treat the lack of returned usage as a measured zero-token bill.

## Diagnosis

The summary generator consults registry capabilities and passes `temperature=None` for the configured `gpt-6-astra` (`scripts/summarize_narrative.py:1342`). The shared builder omits a `None` temperature argument (`nexus/api/native_structured_output.py:248`), restoring the OpenAI wrapper's default. That unchanged wrapper classifies reasoning models by the `gpt-5`/`o3` strings and considers Astra temperature-capable (`scripts/api_openai.py:399`). The actual request logged temperature `0.1` before OpenAI rejected it. Shared provider capability repair is deferred to the coordinator under the frozen work order's stop rule.

The source corpus has 45 S01E02 chunks totaling 196,071 raw-text characters. The episode prompt measured 44,169 input tokens against the configured 27,500 input allowance, and the existing summarizer continued after a warning. The request was rejected for temperature; no conclusion about successful large-input summarization follows.

## Implemented Before the Stop

- Migration 125 creates `narrative_embedding_jobs` and `narrative_summary_jobs`, with identities, attempt counts, retry times, leases, nonce fences, error classes, generation-session correlation, and table/column comments. It transfers legacy summary failure markers into retry plans and clears those markers from reader columns.
- Parent embedding claims enqueue locked playable chunks transactionally. The scheduler also reconciles historical claims. Legacy acceptance enqueues in its own transaction. The old subprocess and process-local dedupe set are removed.
- Embedding execution uses the same process model cache as MEMNON, fails if the active local model is not configured/installed, checks scheduler preemption before model loading and encoding, and commits the vector, ironman timestamp, and job completion atomically.
- Both synchronous and asynchronous accepting transactions enqueue episode/season plans. Summary execution uses the existing provider client and prompt files, writes reader-visible output under the completion fence, and no longer uses the thread pool or JSON failure writer.
- Shared queue status supplies both new queues to runtime status, CLI jobs/status, QA non-terminal checks, and generation-session job inspection.
- Off-screen narration embedding and the download process are untouched. No fleet/template migrations were applied.

## Verified Behavior

The TEST-provider proof uses real PostgreSQL acceptance and real cached SentenceTransformer inference. It covers new-episode and new-season transitions, session correlation, expired leases, idempotent redrain, one stored vector per chunk/model, rollback of an uncommitted plan, terminal failure, and stale-nonce rejection. A Python audit hook asserts no process creation originating in the embedding execution path; provider initialization is outside that assertion because unrelated initialization may invoke platform utilities.

`tests/test_api/test_narrative_jobs_pg.py` asserts the persisted states and reader summaries. The queue output is linked with exact command tails below. The live lane-8016 proof checks `/runtime/status`, `nexus jobs --slot 4`, and `nexus status --json` while an active generation lease keeps both queues at zero attempts. Its helper shuts down the owned listener and runs `nexus down` with the same isolated environment.

Completion durability means no duplicate committed vector/summary write after recovery. It does not promise exactly-once inference if a process dies after model/provider output but before committing that output.

## Commands and Output

All commands ran from this worktree with the shared interpreter. The initial import proof was:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-embedding-summaries/nexus/__init__.py
```

### Queue Proof

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_narrative_jobs_pg.py
```

```text
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
4 passed, 7 warnings in 17.09s
```

### Runtime and CLI Proof

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_narrative_jobs_pg.py::test_scheduler_new_queue_status_and_interactive_priority
```

```text
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 7 warnings in 3.61s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Focused Offline Checks

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_summary_triggers.py tests/test_qa_shift.py tests/test_api/test_narrative_continue_validation.py tests/test_reachability.py
```

```text
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
97 passed, 8 skipped, 7 warnings in 14.53s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

### Paid Proof

```sh
NEXUS_800B_PAID_PROOF=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_narrative_summary_paid_pg.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_narrative_summary_paid_pg.py::test_scheduler_paid_episode_and_season
1 failed, 5 warnings in 3.25s
```

## Earlier Diagnostic Runs

The initial broad runs overlapped source/configuration edits and are **invalid as baseline or regression evidence**: their already-imported Pydantic definitions rejected the later TOML additions. The first PostgreSQL invocation was interrupted to select lane 8016; its tail was `1 passed, 1899 deselected, 11 warnings in 46.90s`. The invalidated offline run reported `25 failed, 2689 passed, 899 skipped, 9 warnings in 156.61s (0:02:36)`; the invalidated lane-8016 PostgreSQL run reported `49 failed, 64 passed, 1899 deselected, 11 warnings, 35 errors in 224.26s (0:03:44)`. They were superseded by stable-tree gates, recorded below when collected.

Focused proof iterations exposed and fixed: a synchronous provider call from the test's event loop, missing TEST summary-schema routing, missing season parent rows, lazy embedding-table creation, and an incorrect helper import. Final passing proof output is the relevant evidence; these earlier failures are not being presented as pre-existing debt.

## Coordinator Questions

1. Should the shared provider capability/default-temperature defect be repaired in this slice or a prerequisite change?
2. After that repair, authorize the remaining real episode/season proof explicitly; one unsuccessful API request has already been issued and its billing usage was not returned.
3. Apply migration 125 to the fleet/template only after the remaining gates and review succeed. This branch has not done so.

## Files Changed

| File | Change |
|---|---|
| `config/reachability_baseline.json` | Register the three new scheduler modules as production-reachable. |
| `nexus.toml` | Configure embedding/summary queue limits, retries, and leases. |
| `migrations/125_embedding_summary_jobs.sql` | Add documented durable queues and migrate legacy failure markers. |
| `nexus/agents/memnon/utils/embedding_tables.py` | Support transactional DBAPI creation of documented vector tables. |
| `nexus/agents/orrery/job_queues.py` | Expose both queues through the shared status payload. |
| `nexus/api/chunk_workflow.py` | Replace subprocess/dedupe scheduling with transactional durable enqueueing. |
| `nexus/api/commit_handler.py` | Enqueue summary plans in asynchronous acceptance. |
| `nexus/api/commit_handler_sync.py` | Enqueue summary plans in synchronous acceptance. |
| `nexus/api/mock_openai.py` | Add TEST-provider summary schema responses. |
| `nexus/api/narrative.py` | Remove the post-generation embedding background task. |
| `nexus/api/narrative_lease.py` | Enqueue locked chunks alongside parent claims. |
| `nexus/api/summary_triggers.py` | Replace the thread pool with transactional summary plans. |
| `nexus/config/settings_models.py` | Validate per-queue execution settings. |
| `nexus/jobs/embeddings.py` | Execute cached local embeddings under the scheduler checkpoint. |
| `nexus/jobs/narrative_jobs.py` | Share lease acquisition, attempts, retry handling, and completion fences. |
| `nexus/jobs/scheduler.py` | Drain summaries before local embeddings and recover legacy claims. |
| `nexus/jobs/summaries.py` | Generate and fence episode/season summary writes. |
| `nexus/telemetry/attempt_manifest.py` | Include both queues in generation-session inspection. |
| `scripts/qa_shift/qa_shift.py` | Account for both queues in non-terminal and failed-job checks. |
| `scripts/summarize_narrative.py` | Remove JSON failure-marker persistence and filtering. |
| `tests/test_api/test_narrative_continue_validation.py` | Remove obsolete background-embedding callback assertions. |
| `tests/test_api/test_scheduler_pg.py` | Extend the expected scheduler queue inventory. |
| `tests/test_api/test_narrative_jobs_pg.py` | Add real queue, recovery, embedding, status, and priority proofs. |
| `tests/test_api/test_narrative_summary_paid_pg.py` | Add an explicitly gated real two-summary proof with SDK retries off. |
| `tests/test_summary_triggers.py` | Retain planner/provider contracts and retire executor/failure-marker tests. |
| `docs/qa/800-embedding-summaries/verification.md` | Record the stop, evidence, commands, and remaining gates. |
| `docs/qa/800-embedding-summaries/paid-proof-failure.txt` | Preserve the exact real-provider failure and test output. |
| `docs/qa/800-embedding-summaries/queue-proof-evidence.txt` | Preserve process-audit, summary-usage, and passing-test evidence. |
| `docs/qa/800-embedding-summaries/status-proof-evidence.txt` | Preserve CLI queue visibility and passing-test evidence. |

Implementation commit: `855a9ef3`. Both pre-commit hooks passed; no hook was bypassed. No PR, push, or merge was performed because the proof gates are incomplete.

## Stable-Tree Offline Gate

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_orrery/test_playable_narrative_boundary.py::test_legacy_accept_embeds_the_previous_playable_chunk
1 failed, 2705 passed, 904 skipped, 9 warnings in 120.54s (0:02:00)
```

This is a **non-exempt failure** introduced by the queue change. The existing mock cursor in `tests/test_orrery/test_playable_narrative_boundary.py:70` rejects the new `INSERT INTO narrative_embedding_jobs` and its test still expects the supplied process-local callback to run. No `save_01` write occurred: the test replaces the database connection with that cursor. The test needs migration to the durable enqueue contract and preferably a real disposable database. It was left for the coordinator after the paid-proof stop.

## Formatting Gate

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/jobs/narrative_jobs.py nexus/jobs/embeddings.py nexus/jobs/summaries.py nexus/jobs/scheduler.py nexus/config/settings_models.py nexus/api/summary_triggers.py nexus/api/commit_handler.py nexus/api/commit_handler_sync.py nexus/api/chunk_workflow.py nexus/api/narrative.py nexus/api/narrative_lease.py nexus/api/mock_openai.py nexus/agents/memnon/utils/embedding_tables.py nexus/agents/orrery/job_queues.py nexus/telemetry/attempt_manifest.py scripts/summarize_narrative.py scripts/qa_shift/qa_shift.py tests/test_summary_triggers.py tests/test_api/test_narrative_continue_validation.py tests/test_api/test_scheduler_pg.py tests/test_api/test_narrative_jobs_pg.py tests/test_api/test_narrative_summary_paid_pg.py
```

```text
All done! ✨ 🍰 ✨
22 files would be left unchanged.
```

`git diff --check` also completed successfully with no output. The worktree import path was rechecked after the implementation commit and remained under this worktree.

## Stable-Tree PostgreSQL Gate

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_orrery tests/test_summary_triggers.py tests/test_qa_shift.py -k 'embed or summar or scheduler or job or queue'
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_chunk_workflow_integration.py::test_accept_chunk_queues_background_embedding_with_real_slot_db
FAILED tests/test_orrery/test_playable_narrative_boundary.py::test_legacy_accept_embeds_the_previous_playable_chunk
FAILED tests/test_orrery/test_recall_disclosure_pg.py::test_turn_inputs_change_experience_ranking_via_shared_query_embedding
ERROR tests/test_api/test_chunk_workflow_integration.py::test_accept_chunk_queues_background_embedding_with_real_slot_db
3 failed, 141 passed, 1 skipped, 1899 deselected, 11 warnings, 1 error in 257.16s (0:04:17)
```

This gate is **red**. The failures are not silently folded into the #885 exemption:

- `test_chunk_workflow_integration.py::test_accept_chunk_queues_background_embedding_with_real_slot_db` directly uses `save_05`, which intentionally has not received migration 125. It fails with `psycopg2.errors.UndefinedTable: relation "narrative_embedding_jobs" does not exist`; teardown then refers to the deliberately deleted `_queued_embedding_jobs_lock`. This frozen order excludes repairing slot-5-hardwired tests and forbids fleet migrations, so coordinator routing is needed. The fixture's temporary chunks were deleted before its obsolete-lock teardown error.
- `test_playable_narrative_boundary.py::test_legacy_accept_embeds_the_previous_playable_chunk` is the same non-exempt legacy mock-cursor failure as the offline gate.
- `test_recall_disclosure_pg.py::test_turn_inputs_change_experience_ranking_via_shared_query_embedding` fails with four required `RenderLimits` fields missing from `{}`: `relationships`, `events`, `threats`, and `bleed_menu`. This is not claimed as a verified baseline failure or a #885 exemption; classification/repair remains open. No source repair was attempted after the paid-proof stop.

The explicit paid-proof test is the gate's one skip because its extra authorization environment is absent. It was run separately and failed as documented. Real PostgreSQL tests did run: 141 passed.

The lane-8016 listener was absent after the gate. The paid clone cleanup query returned no rows:

```sql
SELECT datname FROM pg_database
WHERE datname LIKE 'qa640_800b_paid_%' ORDER BY datname;
```

No Postgres.app permission-dialog error occurred. Finalization is documentation and local commits only; the implementation remains unpushed and no PR was opened.

Additional coordinator decisions: migrate the legacy acceptance tests to disposable queue-aware coverage despite the hardwired-test exclusion, and classify the recall-disclosure fixture failure. Do not bypass either gate or apply migration 125 to the owner's saves to make these tests pass.

Reported by Codex — GPT-6 Astra (gpt-6-astra).
