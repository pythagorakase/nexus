# Work Order 800-B Verification

Status: **STOP-REPORT — paid proof remains blocked; no push or PR.**

## Stop Reason and Paid Evidence

The registry repair removed the temperature rejection. Both authorized episode attempts reached OpenAI with HTTP 200 but returned truncated JSON. The second response explicitly reports `status: incomplete` and `incomplete_details.reason: max_output_tokens`. The configured episode output allowance is 2,500 tokens (`nexus.toml:1222`); this is distinct from the separately deferred 30,000-token input/request budget at line 1224. Neither tunable was changed.

Exact second-attempt error:

```text
1 validation error for EpisodeSummaryModel
  Invalid JSON: EOF while parsing a string at line 2 column 11268 [type=json_invalid, input_value='[REDACTED generated response]', input_type=str]
    For further information visit https://errors.pydantic.dev/2.11/v/json_invalid
```

Two episode calls were issued in this continuation: first on `qa640_800b_paid_d16edf822829`, then the authorized retry on `qa640_800b_paid_e8d6a492eed0`. No season request was issued. The episode retry allocation is exhausted; the two unused season calls do not authorize further episode calls. Both fixture-owned clones were dropped.

The retry's real HTTP response metadata is preserved in [paid-wire-usage.json](paid-wire-usage.json):

| Measurement | Tokens |
|---|---:|
| Input | 44,386 |
| Cached input | 44,383 |
| Cache write | 0 |
| Output | 2,500 |
| Reasoning (within output) | 264 |
| Total | 46,886 |

The first call's usage is **unknown**, not zero. The SDK's `responses.parse` raises before assigning the response (`scripts/api_openai.py:596`); the existing recorder only runs when that assignment succeeded (`scripts/api_openai.py:666`). Thus the normal usage ledger is empty for these parse failures. The retry test observes the real HTTP response before parsing and saves metadata without issuing extra calls. Repairing production accounting for SDK parsing failures is deferred to the coordinator.

[paid-proof.json](paid-proof.json) contains SQL evidence captured before clone cleanup: episode state `failed`, attempts `1`; season state `queued`, attempts `0`; both correlated to generation session `c4556637-8f8f-4a74-898c-c18688d63787`. No episode or season summary was persisted by this proof. The clone had no reader rows for these targets, so the post-failure summary queries returned no rows. This is **not** successful paid-summary proof.

## Completed Amendments

- Rebased first onto `origin/main` at `e22cf5ff` (#936). The two original commits are retained in order as `44db48d4` and `461de56f` after the required rebase. Only the reachability baseline reason text conflicted; it now describes both main's and this branch's changes.
- `OpenAIProvider.initialize` resolves the registered entry and reads `unsupported_params` and `reasoning_accounting` (`scripts/api_openai.py:398`). All four request paths remove prohibited kwargs, including merged `extra_body` keys (`scripts/api_openai.py:894`). No prefix heuristic or new registry field remains. Offline constructor/build tests cover Astra, TEST, and unknown IDs.
- Retired the legacy fake acceptance cursor. A real `save_04` data clone carries migration 125 and the source's existing prologue marker (source prologue ID 1). The fixture places that marker at chunk 8 and proves accepting 9 queues exactly chunk 7 (`tests/test_orrery/test_playable_narrative_boundary.py:70`). Predicate unit tests remain.
- Migrated the chunk-workflow integration module to disposable `save_04` clones; removed every `save_05` reference and obsolete dedupe-lock assertion. Migration runner output confirms migration 125 was applied only to clones. The singleton test also routes to its clone.
- Repaired the RenderLimits fixture using `load_settings().lore.render_limits` (`tests/test_orrery/test_recall_disclosure_pg.py:2076`). The failure predates this branch, as ruled by the coordinator; inspection of `origin/main` also confirms the harness lacks `lore.render_limits`.
- Legacy chunk inspection prints exactly one line and returns 1, with no traceback. Duplicate session bindings still raise (`nexus/cli.py:4235`, `nexus/telemetry/attempt_manifest.py:255`). Both cases run against real PostgreSQL in `tests/test_api/test_attempt_manifest_pg.py:452`. A read-only CLI invocation against actual slot 4 chunk 49 independently produced the requested line.
- Updated existing provider test fixtures to registered model IDs; no new mocked provider behavior was introduced. The paid proof saves its failure state and raw usage before teardown.

## Preserved Implementation and Scope

Migration 125, durable queue execution, transaction-bound plans, runtime/CLI queue visibility, and QA non-terminal checks remain from the first issue. The embedding executor checks preemption before model loading and immediately before cached in-process encoding (`nexus/jobs/embeddings.py:67`, `:74`). The scheduler drains summaries and then embeddings after provider-capable work (`nexus/jobs/scheduler.py:497`, `:508`). Reader columns remain `episodes.summary` and `seasons.summary`.

The existing TEST-provider PostgreSQL proof covers real acceptance, cached SentenceTransformer inference, no process creation on the embedding path, expired lease recovery, nonce fencing, and no duplicate committed vector/summary write. It does not promise exactly-once inference if a worker crashes after generating output but before committing it.

No fleet/template migration, model download change, off-screen embedding change, or owner's gateway change was made. No paid configuration limit was changed. [First-issue verification](first-issue-verification.md) retains the earlier stop and historical gate results; current results below supersede them.

## Commands and Tails

All commands ran from this worktree with:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
```

Import proof, before trusting tests:

```sh
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-embedding-summaries/nexus/__init__.py
```

### Provider Construction and Structured Output

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_openai_registry_capabilities.py tests/test_native_structured_output.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
120 passed, 5 warnings in 1.58s
```

[Full output](provider-gate.txt).

### Remaining Registry Fixtures

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_orrery_tag_validation.py tests/test_usage_recorder.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
65 passed, 5 warnings in 1.66s
```

[Full output](registry-fixture-gate.txt).

### Focused PostgreSQL Amendments

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_chunk_workflow_integration.py tests/test_orrery/test_playable_narrative_boundary.py tests/test_api/test_attempt_manifest_pg.py::test_inspect_turn_pre_session_chunk_and_duplicate_sessions tests/test_orrery/test_recall_disclosure_pg.py::test_turn_inputs_change_experience_ranking_via_shared_query_embedding
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
16 passed, 7 warnings in 5.68s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

[Full output](amendment-gate.txt).

### Prompt Lint and Reachability

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 19.77s
```

[Full output](prompt-reachability-gate.txt).

### Paid Attempt One

```sh
NEXUS_800B_PAID_PROOF=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_narrative_summary_paid_pg.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_narrative_summary_paid_pg.py::test_scheduler_paid_episode_and_season
1 failed, 5 warnings in 54.04s
```

[Full output](paid-proof-attempt-1.txt).

### Paid Episode Retry

```sh
NEXUS_800B_PAID_PROOF=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_narrative_summary_paid_pg.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_narrative_summary_paid_pg.py::test_scheduler_paid_episode_and_season
1 failed, 5 warnings in 56.87s
```

[Full output](paid-proof-attempt-2.txt).

### Initial Offline Gate Before Registry Fixture Repairs

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_orrery_tag_validation.py::test_provider_repairs_invalid_declaration_inside_structured_retry_budget
FAILED tests/test_orrery_tag_validation.py::test_openai_chat_transport_repairs_invalid_declaration
FAILED tests/test_orrery_tag_validation.py::test_openai_chat_transport_async_repairs_invalid_declaration
FAILED tests/test_orrery_tag_validation.py::test_each_catalog_boundary_consumes_retry_and_returns_valid_output_unchanged[character_applied_tags-updates.characters[0]-human]
FAILED tests/test_orrery_tag_validation.py::test_each_catalog_boundary_consumes_retry_and_returns_valid_output_unchanged[faction_applied_tags-updates.factions[0]-None]
FAILED tests/test_orrery_tag_validation.py::test_each_catalog_boundary_consumes_retry_and_returns_valid_output_unchanged[faction_identity-updates.factions[0]-Office of Civic Continuity]
FAILED tests/test_orrery_tag_validation.py::test_each_catalog_boundary_consumes_retry_and_returns_valid_output_unchanged[tag_hints-new_entities[0].tag_hints-human]
FAILED tests/test_orrery_tag_validation.py::test_each_catalog_boundary_consumes_retry_and_returns_valid_output_unchanged[pair_tag_hints-new_entities[0].pair_tag_hints[0].tag-protects]
FAILED tests/test_orrery_tag_validation.py::test_each_catalog_boundary_consumes_retry_and_returns_valid_output_unchanged[replacement_event_type-orrery_adjudications[0].replacement_event_type-slept]
FAILED tests/test_usage_recorder.py::test_single_responses_call_records_jsonl_log_and_cli_json
FAILED tests/test_usage_recorder.py::test_two_provider_passes_keep_seats_models_and_sum
FAILED tests/test_usage_recorder.py::test_repair_loop_records_rejected_then_accepted
FAILED tests/test_usage_recorder.py::test_exhausted_repair_labels_final_attempt_rejected_validation
FAILED tests/test_usage_recorder.py::test_missing_usage_stays_null_and_counts_unknown
14 failed, 2706 passed, 908 skipped, 9 warnings in 121.98s (0:02:01)
```

[Full output](offline-initial.txt).

### Formatting

```sh
git diff --name-only origin/main -- '*.py' > /tmp/nexus-800b-python-files.txt
PYTHONPATH=$PWD $PY -m black --check $(cat /tmp/nexus-800b-python-files.txt)
```

```text
All done! ✨ 🍰 ✨
32 files would be left unchanged.
```

[Full output](black-gate.txt).

### Actual Legacy Chunk CLI

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 PYTHONPATH=$PWD $PY -m nexus.cli inspect-turn --slot 4 --chunk 49
```

```text
chunk 49: no generation session (accepted before session binding)
```

[Full output](inspect-turn.txt).

The actual legacy-chunk CLI exited with status 1. The first focused amendment run found fixture-routing and foreign-key cleanup errors (4 failed, 12 passed); those were repaired before the passing focused run. Initial provider tests also exposed unregistered fixture IDs (23 failed, 97 passed), corrected before the 120-pass run. The initial formatting check found one unformatted file; both changed proof tests were formatted before the clean 32-file check. No gate failure is classified under #885.

### Final Offline Gate

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2720 passed, 908 skipped, 9 warnings in 118.90s (0:01:58)
```

[Full output](offline-gate.txt). Offline PostgreSQL/live-provider skips are intentional; the required PostgreSQL selection is recorded separately.

### Expanded PostgreSQL Gate

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_summary_triggers.py tests/test_qa_shift.py -k 'embed or summar or scheduler or job or queue or manifest or boundary or disclosure'
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
187 passed, 1 skipped, 1857 deselected, 11 warnings in 266.34s (0:04:26)
```

[Full output](postgres-gate.txt). All selected PostgreSQL tests ran. The sole skip is the separately authorized paid-proof test, which failed in its two explicit runs above. No #885 exemptions were needed; no failing slot-5 test IDs occurred.

## Cleanup and Git State

`git diff --check` is clean. The import-path proof was repeated after implementation and still resolved under this worktree. Both pre-commit hooks passed for commit `dd466eae`; no hook was bypassed. The remaining amendments and report are committed separately at closeout.

The lane-8016 listener check returned no listener after the gate. Fixture cleanup left no work-order disposable databases:

```sh
lsof -nP -iTCP:8016 -sTCP:LISTEN
psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_800b_%' ORDER BY datname"
```

Both commands returned no rows/output (`lsof` exit 1, `psql` exit 0). No Postgres.app permission error occurred. No app was independently started; the gateway tests own their listeners and invoke `nexus down` with their same environment during teardown. No push, PR, merge, fleet migration, or template migration was performed.

## Coordinator Questions

1. Authorize a targeted episode/season output-budget or summary-length repair, then renew the exhausted episode proof allocation? The episode's 2,500-token output cap is the confirmed blocker; changing the separately deferred request budget alone cannot repair it.
2. Route the usage-accounting hole for SDK parsing failures to this slice or a follow-up? The retry's HTTP metadata has exact usage, but the first call's usage remains unavailable and the normal ledger missed both parse failures.
3. Apply migration 125 fleet-wide only after successful paid proof and review. All implementation and non-paid gates are now green; this branch remains unpushed under the stop rule.

## Files Changed in This Continuation

| File | Change |
|---|---|
| `config/reachability_baseline.json` | Resolve the rebase's explanatory-text conflict without discarding either change. |
| `scripts/api_openai.py` | Use registered capabilities and filter every request path. |
| `nexus/cli.py` | Return the concise legacy-chunk diagnostic and exit 1. |
| `nexus/telemetry/attempt_manifest.py` | Distinguish missing legacy bindings from ambiguous sessions. |
| `tests/test_openai_registry_capabilities.py` | Exercise real offline provider construction and request builders. |
| `tests/test_native_structured_output.py` | Use registered IDs in existing request tests. |
| `tests/test_orrery_tag_validation.py` | Use registered TEST IDs in existing retry tests. |
| `tests/test_usage_recorder.py` | Use registered IDs while retaining distinct model/seat accounting coverage. |
| `tests/test_api/test_chunk_workflow_integration.py` | Replace slot-5 work and process dedupe assertions with disposable durable-queue coverage. |
| `tests/test_orrery/test_playable_narrative_boundary.py` | Replace fake acceptance with a real prologue-aware database test. |
| `tests/test_orrery/test_recall_disclosure_pg.py` | Load configured RenderLimits for the existing harness. |
| `tests/test_api/test_attempt_manifest_pg.py` | Cover missing and duplicate generation sessions in PostgreSQL. |
| `tests/test_api/test_narrative_summary_paid_pg.py` | Save real response metadata, queue states, and persisted summaries even when the proof fails. |
| `docs/qa/800-embedding-summaries/verification.md` | Record current stop reason, repairs, exact gates, cleanup, and coordinator questions. |
| `docs/qa/800-embedding-summaries/first-issue-verification.md` | Preserve the first issue's full verification and stop history. |
| `docs/qa/800-embedding-summaries/provider-gate.txt` | Preserve 120 passing provider checks. |
| `docs/qa/800-embedding-summaries/registry-fixture-gate.txt` | Preserve 65 passing registry-fixture checks. |
| `docs/qa/800-embedding-summaries/amendment-gate.txt` | Preserve 16 passing PostgreSQL amendment checks. |
| `docs/qa/800-embedding-summaries/prompt-reachability-gate.txt` | Preserve 60 passing lint/reachability checks. |
| `docs/qa/800-embedding-summaries/offline-initial.txt` | Preserve the initial 14 registry-fixture failures for diagnosis. |
| `docs/qa/800-embedding-summaries/offline-gate.txt` | Preserve the final 2,720-pass offline gate. |
| `docs/qa/800-embedding-summaries/postgres-gate.txt` | Preserve the 187-pass expanded PostgreSQL gate. |
| `docs/qa/800-embedding-summaries/black-gate.txt` | Preserve the clean 32-file formatting result. |
| `docs/qa/800-embedding-summaries/inspect-turn.txt` | Preserve the exact real-slot legacy diagnostic. |
| `docs/qa/800-embedding-summaries/paid-proof-attempt-1.txt` | Preserve the first HTTP-200 truncated episode response failure. |
| `docs/qa/800-embedding-summaries/paid-proof-attempt-2.txt` | Preserve the authorized episode retry failure. |
| `docs/qa/800-embedding-summaries/paid-proof.json` | Preserve SQL states and failed-proof metadata before clone cleanup. |
| `docs/qa/800-embedding-summaries/paid-wire-usage.json` | Preserve exact provider usage and the output-limit reason. |

Reported by Codex — GPT-6 Astra (gpt-6-astra).
