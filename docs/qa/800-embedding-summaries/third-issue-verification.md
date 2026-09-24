# Work Order 800-B Verification

Status: **STOP-REPORT — both renewed episode calls exhausted the 8,000-token allowance. No push or PR.**

## Implementation and Evidence

The third issue continues the same branch, `claude/800-embedding-summaries`. `git fetch origin && git rebase origin/main` reported the branch already up to date at the start. The four earlier commits remain intact: `44db48d4`, `461de56f`, `dd466eae`, and `eff27e00`. The first two are the identities from the previously required rebase. The allowance/truncation implementation is committed as `00d45547`; the isolated gateway test correction is committed as `25af2c53`. Both pre-commit hooks passed on both commits; no hook was bypassed.

- `nexus.toml:1222`: episode output allowance is 8,000; season allowance is 12,000. The comment explicitly includes reasoning tokens for `reasoning_accounting = "inside_output"`. The request budget stays 30,000 under #937. The config pre-commit validator passed.
- `scripts/summarize_narrative.py:1349`: summary OpenAI providers install a mode- and allowance-specific response check. The generator preserves the dedicated exception in episode, season, and chunk-range paths.
- `scripts/api_openai.py:598`: only callers with this response check use `responses.create` with the existing strict JSON schema. `scripts/api_openai.py:630` runs the check before `_extract_native_parsed_output`. The usual `finally` recorder at line 673 records usage with outcome `error` before an exception propagates to the caller. A `RuntimeError` does not enter the structured-validation retry loop.
- `nexus/api/summary_errors.py:9`: `SummaryOutputTruncated(RuntimeError)` reports mode, configured allowance, `incomplete_details.reason`, and the complete SDK usage object. It rejects every incomplete status, including non-token reasons.
- `nexus/jobs/narrative_jobs.py:114`: truncation is immediately terminal and retains `error_class=SummaryOutputTruncated`, even with attempts remaining. Lease fields clear; later drains do not select it.
- `config/reachability_baseline.json`: records the new production-reachable error module. The initial reachability run correctly requested this addition (2 failed, 58 passed); the baseline repair adds that single path without creating an orphan exemption.

The TEST endpoint always emits completed responses (`nexus/api/mock_openai.py:1052`), so it cannot reproduce incomplete output. Per the coordinator's permitted alternative, `tests/test_summary_triggers.py` builds a validated OpenAI SDK `Response` carrying malformed summary JSON and real response/usage field shapes; it covers episode/season and both `max_output_tokens` and `content_filter`. `tests/test_api/test_narrative_jobs_pg.py::test_summary_truncation_is_terminal_with_attempts_remaining` runs the classifier through the real PostgreSQL queue executor, proves state `failed`, attempts `1` with a budget of `3`, clears all lease fields, and proves no subsequent execution or completion callback.

This response-before-JSON ordering follows the [official structured-output edge-case guidance](https://developers.openai.com/api/docs/guides/structured-outputs). General usage accounting when other consumers' SDK `responses.parse` raises remains deferred, as directed. Non-summary callers retain their existing parse path.

## Preserved Queue Work

Migration 125 adds durable narrative embedding and summary queues, with attempts, leases, nonce fences, and generation-session correlation. Every new table and column has a SQL comment. Plans are inserted inside acceptance transactions. Embedding execution uses the cached in-process SentenceTransformer and checks interactive preemption before model loading and encoding. Summaries use the provider client and keep reader-visible JSON in `episodes.summary` and `seasons.summary`. The scheduler, runtime status, CLI status/jobs, and QA non-terminal checks expose both queues.

The TEST-provider PostgreSQL proofs exercise transition acceptance, embedding without process creation, cached-model reuse, lease recovery, nonce fencing, and single committed vector/summary writes. This is not a guarantee of exactly-once inference after a crash between generation and commit.

The second amendment's provider registry repair, disposable acceptance fixtures, prologue-aware predecessor test, and legacy inspect-turn diagnostic remain. The RenderLimits fixture failure predates this branch, as ruled by the coordinator; the fixture now reads `load_settings().lore.render_limits`. See [second-issue verification](second-issue-verification.md) for the prior evidence and [first-issue verification](first-issue-verification.md) for the original stop.

## Paid Proof

The first renewed episode call returned HTTP 200 but was still incomplete at the fixed 8,000-token allowance. The new dedicated error propagated, the normal recorder wrote an error usage event, the episode job became terminal after one attempt, and no summary JSON was persisted. The season job stayed queued with zero attempts. The clone was `qa640_800b_paid_68b8f07afd60`, session `3a7859bd-58d7-40b1-8800-f4e68fffa960`.

Exact error:

```text
SummaryOutputTruncated: episode summary incomplete: configured allowance=8000 output tokens; incomplete_details.reason=max_output_tokens; usage={"input_tokens": 44386, "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 44383}, "output_tokens": 8000, "output_tokens_details": {"reasoning_tokens": 348}, "total_tokens": 52386}
```

[Attempt-one SQL and ledger evidence](third-paid-proof-attempt-1.json), [wire usage](third-paid-wire-attempt-1.json), and [test output](third-paid-proof-attempt-1.txt) are preserved. The authorized episode retry also returned HTTP 200, `status=incomplete`, and `reason=max_output_tokens`, with 8,000 output tokens. It used clone `qa640_800b_paid_6a00e86c125c` and session `b22aa1cd-0405-4638-87c4-c2235882b611`. Its exact exception differs from the one above only in the reasoning count: 174. [Retry SQL and ledger evidence](paid-proof.json) contains the persisted job states and empty summary result. Neither attempt wrote an episode or season summary. Both episode calls are consumed; zero season calls were made. Unused season authority does not permit more episode calls.

The consolidated [paid-wire-usage.json](paid-wire-usage.json) preserves both HTTP response IDs and the exact provider usage:

| Cost-Relevant Count | Episode Attempt 1 | Episode Attempt 2 | Total |
|---|---:|---:|---:|
| Input | 44,386 | 44,386 | 88,772 |
| Cached Input | 44,383 | 44,383 | 88,766 |
| Uncached Input (Input Minus Cached) | 3 | 3 | 6 |
| Cache Write | 0 | 0 | 0 |
| Output (Includes Reasoning) | 8,000 | 8,000 | 16,000 |
| Reasoning (Within Output) | 348 | 174 | 522 |
| Total | 52,386 | 52,386 | 104,772 |

Both normal usage events were checked against their wire response IDs, input/output/total counts, cached-input counts, and reasoning counts. Both have outcome `error`. The normal recorder's cache-creation field remains null; the separate wire cache-write count is explicitly zero. No currency estimate is substituted for the measured token counts.

The paid failure proves production truncation classification and accounting, but **does not satisfy the successful paid-summary proof**. The fixed allowance remains insufficient for this episode. The unchanged episode prompt asks for a granular timeline covering all significant beats (`prompts/summaries/episode_system.md:9`); the input contains 45 target chunks plus one context chunk. A different output allowance or bounded-length prompt is a coordinator decision, not an unapproved change here. Each paid-proof invocation permits at most one episode and one season call, with SDK retries and structured-output retries disabled. Only `qa640_*` data clones of `save_04` are used.

## Commands and Tails

All commands run from this worktree, using:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
```

The import proof ran before testing:

```sh
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-embedding-summaries/nexus/__init__.py
```

### Focused Provider and Summary Tests

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_summary_triggers.py tests/test_openai_registry_capabilities.py tests/test_native_structured_output.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
130 passed, 5 warnings in 2.21s
```

[Full output](third-focused-gate.txt).

### PostgreSQL Truncation Classification

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_narrative_jobs_pg.py::test_summary_truncation_is_terminal_with_attempts_remaining
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 7 warnings in 1.37s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

[Full output](third-truncation-pg.txt).

### Offline Gate

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2724 passed, 909 skipped, 9 warnings in 124.32s (0:02:04)
```

[Full output](third-offline-gate.txt).

### Prompt Lint and Reachability

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 20.39s
```

[Full output](third-prompt-reachability.txt).

### Black

```sh
git diff --name-only origin/main -- '*.py' > temp/800b-python-files.txt
PYTHONPATH=$PWD $PY -m black --check $(cat temp/800b-python-files.txt)
```

```text
All done! ✨ 🍰 ✨
34 files would be left unchanged.
```

[Full output](third-black-gate.txt).

### Actual Legacy Chunk CLI

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 PYTHONPATH=$PWD $PY -m nexus.cli inspect-turn --slot 4 --chunk 49
```

```text
chunk 49: no generation session (accepted before session binding)
```

Exit status 1, no traceback. [Full output](third-inspect-turn.txt).

### Paid Episode Attempt One

```sh
NEXUS_800B_PAID_PROOF=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_narrative_summary_paid_pg.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_narrative_summary_paid_pg.py::test_scheduler_paid_episode_and_season
1 failed, 5 warnings in 163.92s (0:02:43)
```

[Full output](third-paid-proof-attempt-1.txt).

### Initial Reachability Gate Before Baseline Repair

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_reachability.py::test_repository_reachability_ratchet - Ass...
FAILED tests/test_reachability.py::test_checker_cli_is_stdlib_only_and_writes_evidence_without_importing_app
2 failed, 58 passed, 5 warnings in 18.91s
```

[Full output](third-prompt-reachability-initial.txt).

### Paid Episode Retry

```sh
NEXUS_800B_PAID_PROOF=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_narrative_summary_paid_pg.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_narrative_summary_paid_pg.py::test_scheduler_paid_episode_and_season
1 failed, 5 warnings in 154.89s (0:02:34)
```

[Full output](third-paid-proof.txt).

### Initial PostgreSQL Gate Before Lane Repair

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_summary_triggers.py tests/test_qa_shift.py -k 'embed or summar or scheduler or job or queue or manifest or boundary or disclosure'
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_api/test_scheduler_recovery_pg.py::test_scheduler_gateway_sigkill_resumes_inflight_experience
1 failed, 191 passed, 1 skipped, 1857 deselected, 11 warnings in 280.26s (0:04:40)
```

[Full output](third-postgres-initial.txt).

The initial PostgreSQL failure was not a #885 exemption. Exact preflight error:

```text
AssertionError: COMMAND     PID     USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
python3.1 59092 pythagor   12u  IPv4 0x5dd53313ab3d9b65      0t0  TCP 127.0.0.1:8018 (LISTEN)
python3.1 73754 pythagor    9u  IPv4 0x5dd53313ab3d9b65      0t0  TCP 127.0.0.1:8018 (LISTEN)
python3.1 73754 pythagor   12u  IPv4 0x5dd53313ab3d9b65      0t0  TCP 127.0.0.1:8018 (LISTEN)
```

The final PostgreSQL rerun was already running when the second paid failure triggered the stop. It finished with 192 passed, 1 skipped, and zero failures. All selected PostgreSQL tests ran; the sole skip is the separately executed paid proof. No #885 slot-5 failure IDs occurred and no exemption was needed. The offline gate predates the lane-only test correction; that PostgreSQL-marked test is skipped offline. Prompt lint and reachability also predate that test-only correction; production imports did not change. The final Black check includes it.


### Final PostgreSQL Gate

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_summary_triggers.py tests/test_qa_shift.py -k 'embed or summar or scheduler or job or queue or manifest or boundary or disclosure'
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
192 passed, 1 skipped, 1857 deselected, 11 warnings in 259.88s (0:04:19)
```

[Full output](third-postgres-gate.txt).

## Scope, Cleanup, and Coordinator Questions

No fleet or template migrations, model downloads, off-screen narration embedding changes, main-checkout changes, or owner gateway changes. Gateway tests use lane 8016 and own listener startup/teardown. No automatic paid retry is authorized by the queue after truncation.

Final cleanup checks:

```sh
lsof -nP -iTCP:8016 -sTCP:LISTEN
psql -d postgres -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_800b_%' ORDER BY datname"
git diff --check
```

All returned no output (listener check exit 1; SQL and diff checks exit 0). No `qa640_800b_*` databases remain. Fixture-owned gateway processes shut down with their same environment. No foreign listener was stopped. The final import check still resolves to this worktree. No Postgres.app authentication-permission error occurred.

Deferred: #937's stale request budget; general SDK parse-failure usage accounting. The coordinator applies migration 125 fleet-wide at landing. Open question for the coordinator:

Authorize a bounded-length episode-summary prompt or another output-allowance change, and renew episode proof authority? Both authorized attempts still truncated at 8,000 output tokens. The season proof remains unexecuted because each scheduler pass stopped on the episode failure.

The retained lane correction is in `tests/test_api/test_scheduler_recovery_pg.py:464`: the existing SIGKILL test hardcoded 8018 despite the assigned 8016 environment and collided with a foreign listener. The fix honors `NEXUS_GATEWAY_PORT` for its preflight check and bind, exactly as the other scheduler fixtures do. The listener was not stopped or modified.

No push, PR, or merge is performed under this stop report.

## Files Changed in This Continuation

- `config/reachability_baseline.json` — Add the summary-error module to production reachability.
- `nexus.toml` — Set episode/season output allowances to 8,000/12,000, including reasoning.
- `nexus/api/summary_errors.py` — Classify incomplete summary responses before JSON parsing.
- `nexus/jobs/narrative_jobs.py` — Make summary truncation terminal regardless of remaining attempts.
- `scripts/api_openai.py` — Let summaries inspect raw Responses results while retaining normal usage recording.
- `scripts/summarize_narrative.py` — Install the mode/allowance check and preserve the dedicated exception.
- `tests/test_summary_triggers.py` — Cover both summary modes and incomplete reasons with SDK response objects.
- `tests/test_api/test_narrative_jobs_pg.py` — Prove failed state, cleared lease, and no retry after truncation in PostgreSQL.
- `tests/test_api/test_scheduler_recovery_pg.py` — Honor the assigned gateway port during the SIGKILL recovery proof.
- `docs/qa/800-embedding-summaries/verification.md` — Record this continuation, exact gates, paid failures, cleanup, and the coordinator question.
- `docs/qa/800-embedding-summaries/paid-proof.json` — Retain the retry clone SQL state and normal usage ledger before cleanup.
- `docs/qa/800-embedding-summaries/paid-wire-usage.json` — Retain both renewed calls and their exact wire usage.
- `docs/qa/800-embedding-summaries/second-issue-verification.md` — Preserve the prior stop report.
- `docs/qa/800-embedding-summaries/second-issue-paid-proof.json` — Preserve the prior paid-proof SQL evidence.
- `docs/qa/800-embedding-summaries/second-issue-paid-wire-usage.json` — Preserve the prior 2,500-token wire usage.
- `docs/qa/800-embedding-summaries/third-focused-gate.txt` — Record 130 passing focused tests.
- `docs/qa/800-embedding-summaries/third-truncation-pg.txt` — Record the passing real PostgreSQL truncation test.
- `docs/qa/800-embedding-summaries/third-offline-gate.txt` — Record the 2,724-pass offline gate.
- `docs/qa/800-embedding-summaries/third-prompt-reachability-initial.txt` — Preserve the new-module baseline failure.
- `docs/qa/800-embedding-summaries/third-prompt-reachability.txt` — Record 60 passing prompt/reachability tests after repair.
- `docs/qa/800-embedding-summaries/third-black-gate.txt` — Record the clean 34-file Black check.
- `docs/qa/800-embedding-summaries/third-inspect-turn.txt` — Record the exact real-slot legacy diagnostic.
- `docs/qa/800-embedding-summaries/third-paid-proof-attempt-1.json` — Preserve the first renewed paid call SQL state and usage ledger.
- `docs/qa/800-embedding-summaries/third-paid-wire-attempt-1.json` — Preserve the first renewed paid call wire usage.
- `docs/qa/800-embedding-summaries/third-paid-proof-attempt-1.txt` — Preserve the first renewed paid call test failure.
- `docs/qa/800-embedding-summaries/third-paid-proof.txt` — Preserve the authorized retry failure.
- `docs/qa/800-embedding-summaries/third-postgres-initial.txt` — Preserve the initial gateway-port collision failure.
- `docs/qa/800-embedding-summaries/third-postgres-gate.txt` — Record the final expanded PostgreSQL rerun.

Reported by Codex — GPT-6 Astra (gpt-6-astra).
