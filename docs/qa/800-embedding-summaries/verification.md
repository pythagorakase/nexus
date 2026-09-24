# Work Order 800-B Verification

Status: **PASS — all five PR #940 review findings fixed; fifth-issue gates pass. No additional paid calls. The fourth-issue paid proof stands.**

## Fifth-Issue Review Fixes

Continuation of PR #940 from `b321f2c0`, using ordinary fix commits without rewriting history. Implementation commit: `974a71ea`; archive-redaction commit: `05a4af59`. No paid calls were made in this continuation; the fourth-issue persisted proof and every cost-relevant count below stand. No prompts, allowances, configuration fields, or migration files were changed.

- **Lease renewal:** `nexus/jobs/scheduler.py:377` renews the tracked nonce throughout preparation, including inference, until the drain writes completion/failure and clears tracking. The existing lost-lease flag stops the next checkpoint loudly. `tests/test_api/test_narrative_jobs_pg.py:335` uses a real disposable database, a 0.5-second job lease, and 1.5-second preparation. It observes the original nonce still live with attempts=1 and commits under that nonce. Its second case replaces the nonce and proves the next checkpoint raises `SchedulerStopped` without writing a summary.
- **Registry defaults:** `scripts/api_openai.py:397`, `ir_eval/scripts/auto_judge.py:101`, and `ir_eval/ir_eval.py:2196` resolve `ir_eval.judgment.model` through Pydantic settings. The common CLI defers its omitted model to that runtime lookup. The same change covers the creative-character CLI and legacy character-batch default. `tests/test_openai_registry_capabilities.py:46` and `:58` construct the actual default wrapper and judge without inference. No retired model was registered.
- **Chat truncation:** `nexus/api/summary_errors.py:13` recognizes `finish_reason=length`, including syntactically valid cut JSON. `scripts/api_openai.py:767` invokes the classifier before parsing; its existing `finally` recorder records the in-hand Chat response with outcome `error`, without a validation retry (`:813`). `SummaryOutputTruncated` remains terminal in the durable queue. TEST's Chat endpoint hardcodes `finish_reason=tool_calls` (`nexus/api/mock_openai.py:750`) and cannot emit length, so the authorized alternative uses validated `openai.types.chat.ChatCompletion` objects (`tests/test_summary_triggers.py:213`). The real PostgreSQL terminal-state test covers both transports (`tests/test_api/test_narrative_jobs_pg.py:220`).
- **Database failures:** `scripts/summarize_narrative.py:1162` no longer catches span-query failures. A genuinely empty episode raises a distinct descriptive `RuntimeError` in `nexus/jobs/summaries.py:38`. `tests/test_api/test_narrative_jobs_pg.py:424` takes a real exclusive lock on `chunk_metadata` and applies a 100ms lock timeout only to its disposable database. The actual summary drain records `failed`, attempts=1, `OperationalError`, with no summary. The empty-span case records `RuntimeError` and likewise never succeeds. An initial test setup blocked an earlier scheduler milestone query; the final test calls the scheduler's actual summary drain directly to isolate the reviewed failure path.
- **Archived evidence redaction:** All Pydantic `input_value` response excerpts were redacted because they echoed generated narrative into error logs. The successful summaries' prose was also redacted in `paid-proof.json` and the duplicate `fourth-paid-proof.txt` payload. Their SHA-256 hashes, character counts, word counts, per-section counts, job states, response statuses, error classes/reasons, and exact usage remain. Six archived files changed. [Redaction audit](fifth-redaction-audit.txt) compares the retained SQL/usage fields with `b321f2c0` and verifies hashes/counts against the original summaries. These are ordinary commits, as required; no history was rewritten.

### Literal-Model Audit

Ran `rg -n 'gpt-4|gpt-5|o3' ir_eval scripts nexus --glob '*.py'` and traced callers of the shared `scripts.api_openai.OpenAIProvider`. All literal defaults reaching that wrapper were removed. Remaining matches are tokenizer names/prefixes, documentation, unused `ModelName` enum values, OpenRouter's separate provider mapping, direct SDK utilities (`freestyle_api_query.py`, `process_factions.py`, `faction_relationship_analyst.py`), or `estimate_time_delta.py`'s separate legacy provider implementation. They do not reach the changed shared wrapper. `process_characters.py` references the retired, absent `api_batch` module; its model default was nevertheless migrated without expanding this order into repairing that historical utility.

### Fifth-Issue Gates

All gates below exited 0. `$PY` is `/Users/pythagor/nexus/.venv/bin/python`; every test runs with `PYTHONPATH=$PWD` from this worktree. Each gate redirected stdout and stderr with `> docs/qa/800-embedding-summaries/<log-name> 2>&1`. The tails are verbatim. No UI build applies.

#### Focused Offline Regressions

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_summary_triggers.py tests/test_openai_registry_capabilities.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
19 passed, 5 warnings in 4.27s
```

[Full output](fifth-focused-offline.txt).

#### Focused PostgreSQL Regressions

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api/test_narrative_jobs_pg.py -k 'renews or span_failure or truncation'
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
6 passed, 5 deselected, 7 warnings in 11.01s
sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
```

[Full output](fifth-focused-postgres.txt).

#### Offline Suite

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2732 passed, 928 skipped, 9 warnings in 129.68s (0:02:09)
```

[Full output](fifth-offline-gate.txt).

#### Prompt Lint and Reachability

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 19.77s
```

[Full output](fifth-prompt-reachability.txt).

#### PostgreSQL Selection

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_summary_triggers.py tests/test_qa_shift.py -k 'embed or summar or scheduler or job or queue or manifest or boundary or disclosure'
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
205 passed, 1 skipped, 1867 deselected, 11 warnings in 373.94s (0:06:13)
```

[Full output](fifth-postgres-gate.txt).

#### Black

```sh
git diff --name-only origin/main -- '*.py' > temp/800b-python-files.txt
PYTHONPATH=$PWD $PY -m black --check $(cat temp/800b-python-files.txt)
```

```text
All done! ✨ 🍰 ✨
39 files would be left unchanged.
```

[Full output](fifth-black-gate.txt).

The offline suite has zero failures. Its skips are opt-in tests and do not substitute for the PostgreSQL gate. The PostgreSQL selection has zero failures and one skipped paid-proof test: no further paid calls were authorized. No #885 IDs failed; no exemption was used. Prompt lint and reachability both passed. Black checked all 39 Python files changed against origin/main.

Import resolution was rechecked after the fixes and still points to this worktree. Gateway fixtures use lane 8016, stop only their own server, and call `nexus down` under the same isolated environment in teardown (`tests/scheduler_helpers.py:145`). Disposable database fixtures own migration and cleanup. No owner save or fleet/template migration was performed. Both implementation and redaction commits passed their applicable pre-commit hooks without bypass. Prompts, nexus.toml, and migration files are unchanged from b321f2c0; that commit remains an ancestor.

Open questions for the coordinator: none. Fleet application of migration 125, #937's request budget, general SDK parse-validation accounting, model downloads, and off-screen narration embeddings remain the previously agreed deferrals.

The rest of this document records the fourth issue's previously completed paid proof and gates.

## Rebase and Scope

The first command was `git fetch origin && git rebase origin/main`. The branch is rebased onto `6fc162c5` (#939). The only conflict was `nexus/api/narrative_lease.py`: resolution keeps the new durable enqueue inside the transaction and main's `commit_transaction(conn)` with `AmbiguousCommit` propagation (`nexus/api/narrative_lease.py:197`). Main's scheduler connection-failure handling remains at `nexus/jobs/scheduler.py:342` and `:423`.

All eight existing commits were replayed in order, with no dropped commits: `ce70b9eb`, `c334f87d`, `245248ec`, `658bd4a6`, `407d9ba7`, `5d00188e`, `f527ca4e`, `f296ba89`. Rebase necessarily changes commit identities. The coordinator's prompt commit `a76c06fb` is now `f296ba89`; no prompt file was edited in this continuation. `git diff f296ba89 -- prompts/` is empty. No implementation edits beyond the required conflict resolution were needed.

Import proof before tests, repeated afterward:

```sh
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/800-embedding-summaries/nexus/__init__.py
```

## Successful Paid Proof

The unchanged paid-proof test ran once on `qa640_800b_paid_7f70d372be95`, a data clone of `save_04` migrated by the repository runner. It made exactly one episode call and one season call to the configured `gpt-6-astra`, with SDK retries and structured-output retries disabled. Both Responses statuses were **completed**, with no incomplete details. No paid retries were needed.

Before fixture teardown, the SQL queries in `tests/test_api/test_narrative_summary_paid_pg.py:108` captured both jobs as `succeeded`, attempts `1`, generation session `97611d92-4abb-4b57-8624-67964d1783a2`. The scheduler persisted S01E02 in `episodes.summary` (10,522 characters) and season 1 in `seasons.summary` (12,970 characters). The generator prepares with `dry_run=True`; the scheduler completion transaction performs the actual reader-column writes (`nexus/jobs/summaries.py:68`). These are committed SQL reads, not a dry-run persistence claim.

[Persisted summaries, job rows, current wire responses, and normal usage events](paid-proof.json). Both accepted usage events match their wire response IDs, input, output, total, cached-input, and reasoning counts. Current totals: **88,897 input, 0 cached input, 88,891 wire cache-write, 5,156 output (including 359 reasoning), 4,797 visible output, and 94,053 total tokens**. The normal recorder has `cache_creation_tokens=null`; wire `cache_write_tokens` is preserved separately without relabeling null as zero. No currency estimate is substituted for measured counts.

### Persisted Word Counts

Words are whitespace-delimited tokens from the persisted JSON `summary` strings; section counts exclude headings, totals include them. This counts labels and list markers where separated by whitespace. [Machine-readable counts](fourth-summary-word-counts.json).

| Mode | Section | Words | Lines |
|---|---|---:|---:|
| Episode | OVERVIEW | 104 | 1 |
| Episode | TIMELINE | 727 | 30 |
| Episode | CHARACTERS | 257 | 12 |
| Episode | PLOT_THREADS | 148 | 7 |
| Episode | CONTINUITY_ELEMENTS | 194 | 10 |
| Episode | **Total Including Headings** | **1435** | — |
| Season | OVERVIEW | 128 | 1 |
| Season | CHARACTER_EVOLUTION | 655 | 10 |
| Season | NARRATIVE_ARCS | 414 | 8 |
| Season | WORLD_DEVELOPMENT | 242 | 12 |
| Season | CONTINUITY_ANCHORS | 333 | 15 |
| Season | **Total Including Headings** | **1782** | — |

The episode is below 1,500 words; its overview is 104/120 words and its timeline has 30 lines, at most 27 words each (limit 30). Its character/thread/continuity lines are 12/7/10, within 12/10/10. The season is below 2,000 words; its overview is 128/150 words, character entries are at most 74/80 words, and arcs at most 56/60 words. Character/arc/world/anchor line counts are 10/8/12/15, all within the prompt limits.

### Paid Usage Across All Four Issues

The consolidated [paid-wire-usage.json](paid-wire-usage.json) accounts for all seven requests. Output includes reasoning; visible output is output minus reasoning. The first request was rejected with HTTP 400 and no returned usage. The first second-issue attempt lacks a wire capture because SDK parsing raised before the normal recorder; its counts are **unknown, not zero**. The coordinator described that attempt as truncated, but exact missing wire counts are not reconstructed. All earlier issues made zero season calls.

| Issue / Attempt | Mode | Result | Input | Cached | Cache Write | Output | Reasoning | Visible Output | Total |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 / 1 | episode | HTTP 400 | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| 2 / 1 | episode | JSON parse failure | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| 2 / 2 | episode | incomplete | 44386 | 44383 | 0 | 2500 | 264 | 2236 | 46886 |
| 3 / 1 | episode | incomplete | 44386 | 44383 | 0 | 8000 | 348 | 7652 | 52386 |
| 3 / 2 | episode | incomplete | 44386 | 44383 | 0 | 8000 | 174 | 7826 | 52386 |
| 4 / 1 | episode | completed | 44478 | 0 | 44475 | 2390 | 213 | 2177 | 46868 |
| 4 / 1 | season | completed | 44419 | 0 | 44416 | 2766 | 146 | 2620 | 47185 |

Earlier evidence remains in [first-issue verification](first-issue-verification.md), [second-issue verification](second-issue-verification.md), and [third-issue verification](third-issue-verification.md), with their archived wire and SQL files. Historical stop reports are superseded by the current passing proof.

## Implementation and Behavioral Evidence

- Migration 125 adds durable embedding and summary jobs with attempts, leases, nonce fences, generation-session correlation, and comments for every new table/column (`migrations/125_embedding_summary_jobs.sql:1`, `:33`). It migrates historical JSON error markers into jobs and clears the reader-column errors (`:72`). Fleet/template application is deferred to the coordinator.
- Locked playable chunks are enqueued inside accepting/claim transactions; cached local SentenceTransformer execution has checkpoints before model loading and immediately before encoding (`nexus/jobs/embeddings.py:28`, `:67`, `:74`). The subprocess executor, process-local dedupe set, and silent model fallback are removed. Off-screen narration embeddings remain out of scope.
- Summary plans are transaction-bound, execute through the provider, and commit reader-visible results under the nonce fence (`nexus/api/summary_triggers.py:50`, `nexus/jobs/narrative_jobs.py:43`, `nexus/jobs/summaries.py:68`). No module executor or legacy DB environment DSN idiom remains.
- The scheduler drains provider queues, then summaries, then local embeddings (`nexus/jobs/scheduler.py:525`). `/runtime/status`, `nexus status`, `nexus jobs`, and QA settlement checks expose the queues (`nexus/agents/orrery/job_queues.py:58`, `scripts/qa_shift/qa_shift.py:58`).
- Real TEST-provider PostgreSQL tests cover acceptance, recovery of expired leases, cached embedder identity, process-creation auditing, exactly one committed embedding per model, nonce rejection, summaries, interactive priority, and runtime/CLI inventory (`tests/test_api/test_narrative_jobs_pg.py:35`, `:277`). This does not promise exactly-once inference after a crash between inference and commit.
- Registry capabilities govern all OpenAI request builders (`scripts/api_openai.py:398`). Incomplete summary responses raise `SummaryOutputTruncated` before JSON parsing, normal usage is recorded, and the job becomes terminal without automatic retry (`nexus/api/summary_errors.py:13`, `scripts/api_openai.py:630`, `:673`, `nexus/jobs/narrative_jobs.py:114`). The TEST endpoint always completes; classifier tests therefore use validated SDK Response shapes as previously authorized, plus the real PostgreSQL terminal-state proof.
- The prologue test uses a disposable `save_04` data clone with its real marker moved into the 7/8/9 fixture, proving predecessor 7 rather than synthetic prologue 8 (`tests/test_orrery/test_playable_narrative_boundary.py:70`). The chunk-workflow integration module uses disposable clones and no longer references `save_05`. The RenderLimits repair reads configuration (`tests/test_orrery/test_recall_disclosure_pg.py:2076`); the coordinator confirmed the original failure predates the branch.
- The actual legacy CLI invocation exits 1 with one line and no traceback; the PostgreSQL manifest test also preserves a loud error for duplicate bindings (`tests/test_api/test_attempt_manifest_pg.py:452`).

## Commands and Verbatim Tails

All commands ran from this worktree. `$PY` below expands to the exact shared interpreter invoked:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
```

Each gate redirected stdout and stderr to its linked output file with `> <file> 2>&1`. The tails are verbatim.

### Paid Episode and Season Proof

```sh
NEXUS_800B_PAID_PROOF=1 NEXUS_RUN_LIVE_LLM=1 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q -s tests/test_api/test_narrative_summary_paid_pg.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 5 warnings in 118.45s (0:01:58)
```

[Full output](fourth-paid-proof.txt).

### Offline Suite

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2726 passed, 923 skipped, 9 warnings in 116.99s (0:01:56)
```

[Full output](fourth-offline-gate.txt).

### Prompt Lint and Reachability

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 17.03s
```

[Full output](fourth-prompt-reachability.txt).

### PostgreSQL Selection

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_api tests/test_orrery tests/test_summary_triggers.py tests/test_qa_shift.py -k 'embed or summar or scheduler or job or queue or manifest or boundary or disclosure'
```

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
196 passed, 1 skipped, 1867 deselected, 11 warnings in 343.44s (0:05:43)
```

[Full output](fourth-postgres-gate.txt).

### Black

```sh
git diff --name-only origin/main -- '*.py' > temp/800b-python-files.txt
PYTHONPATH=$PWD $PY -m black --check $(cat temp/800b-python-files.txt)
```

```text
All done! ✨ 🍰 ✨
34 files would be left unchanged.
```

[Full output](fourth-black-gate.txt).

### Legacy Chunk CLI

```sh
NEXUS_GATEWAY_PORT=8016 NEXUS_API_URL=http://127.0.0.1:8016 PYTHONPATH=$PWD $PY -m nexus.cli inspect-turn --slot 4 --chunk 49
```

```text
chunk 49: no generation session (accepted before session binding)
```

[Full output](fourth-inspect-turn.txt).


The offline skips are opt-in PostgreSQL/live-provider tests; they do not stand in for the PostgreSQL gate. The selected PostgreSQL gate's sole skip is the separately executed paid proof. No #885 slot-5 failure IDs occurred and no exemption was used. All gate exit statuses are 0; the intentionally nonzero legacy CLI diagnostic exits 1.

## Cleanup and Coordinator Questions

No owner gateway, main checkout, other worktree, save database, fleet schema, or template was modified. No dependency install was run. Only fixture-owned disposable databases were migrated. The gateway tests own their lane-8016 listeners and teardown with the same environment; no foreign listener was stopped. No Postgres.app authentication-permission error occurred.

Final cleanup checks and output are recorded in [fourth-cleanup.txt](fourth-cleanup.txt): lane 8016 has no listener; no `qa640_800b_%` databases remain; `git diff --check` and the prompt-preservation diff are clean. No independently started app requires teardown.

Deferred, as directed: #937's 30,000-token request budget (warnings persist); general usage accounting when SDK `responses.parse` validation raises; model downloads; off-screen narration embeddings; slot-5 hardwired test repairs beyond the expressly authorized fixture migration. Episode/season allowances remain 8,000/12,000. The coordinator applies migration 125 fleet-wide at landing. No open implementation question remains. Do not merge this PR in this run.

## Files Changed in This Continuation

- `nexus/api/narrative_lease.py` — Resolve the rebase conflict by keeping both durable enqueue and main's commit handling.
- `verification.md` — Record the rebased passing proof, all commands and tails, scope, and deferred work.
- `paid-proof.json` — Store committed episode/season summaries, job states, and matching usage events.
- `paid-wire-usage.json` — Consolidate every provider attempt across all four issues; retain unknown usage explicitly.
- `fourth-summary-word-counts.json` — Record persisted section word counts and line-cap measurements.
- `fourth-paid-proof.txt` — Retain the successful real episode and season proof output.
- `fourth-offline-gate.txt` — Retain the 2,726-pass offline suite output.
- `fourth-postgres-gate.txt` — Retain the 196-pass PostgreSQL selection output.
- `fourth-prompt-reachability.txt` — Retain the 60-pass prompt and reachability output.
- `fourth-black-gate.txt` — Retain the clean 34-file Black check.
- `fourth-inspect-turn.txt` — Retain the exact nonzero legacy-chunk CLI diagnostic.
- `fourth-cleanup.txt` — Verify lane and disposable-database cleanup and clean diffs.
- `third-issue-verification.md` — Preserve the prior stop report before replacing the current verification.
- `third-issue-paid-proof.json` — Preserve the prior failed paid-proof SQL and ledger evidence.
- `third-issue-paid-wire-usage.json` — Preserve the prior two 8,000-token truncated wire responses.

Reported by Codex — GPT-6 Astra (gpt-6-astra).
