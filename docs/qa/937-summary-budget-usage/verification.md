# Summary Budget and Usage Verification

## Scope and Isolation

Worktree: `claude/937-summary-budget-usage`, based on `b2e764b9` (#940).
The shared interpreter imports `nexus` from this worktree. No paid calls,
fleet migrations, or application gateway were used. TEST runs on fixture-owned
loopback ports; fixtures create and remove their own disposable PostgreSQL databases.
The budget proof snapshots `save_04` into `qa640_937_budget_*`; the source is read-only.
Usage/manifest proof uses `qa640_938_usage_*` schema-and-seed clones.

## Registry Budget Arithmetic

The checked-in summary model resolves to `gpt-6-astra`, with total context
1,050,000 and maximum output 128,000. No separate input maximum is documented.
The registry safety margin is zero. Reasoning is inside the output allowance.
The new `[summaries.window]` reserves 1,024 input tokens; its separate reasoning
reserve is zero. The retired `request_token_budget` is rejected by config validation.

| Mode | Total Context | Output Allowance | Safety Margin | Policy Headroom | Input Budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| Episode | 1,050,000 | 8,000 | 0 | 1,024 | 1,040,976 |
| Season | 1,050,000 | 12,000 | 0 | 1,024 | 1,036,976 |

`resolve_summary_window` uses the same registry/output/headroom arithmetic as
`resolve_seat_window`, then subtracts `token_count_safety_margin`. A documented
input maximum is also bounded by the available total context. Local serving
context limits and outside-output reasoning reserves retain seat behavior.

The summarizer counts assembled user text, system text, and strict schema with
the registry tokenizer before initializing a provider, and checks repair prompts
again before dispatch. Oversized input raises `SummaryInputTooLong`; scheduler
failure is terminal even with attempts remaining. No warning-and-proceed branch remains.

The real scheduler proof leaves TEST's 872,000-token input limit unchanged and
sets policy headroom to 871,999 only in its temporary config. The resulting
one-token budget rejects the clone's actual assembled episode and season inputs.
The persisted job has `state=failed`, `attempts=1`, `error_class=SummaryInputTooLong`,
and no lease. The usage ledger is empty and the live TEST server access log has
no Responses POST. The SQL assertion is:

```sql
SELECT state::text, attempts, error_class, last_error, lease_until
FROM narrative_summary_jobs;
```

## Responses and Usage Proof

The real SDK's old `responses.parse(text_format=...)` request and the new
`responses.create(text={format: ...})` request have identical HTTP JSON bodies.
The Pydantic-to-strict-schema converter remains the SDK's own converter:
`strict=true`, `additionalProperties=false`, and every property required.
The in-tree structured-output and reasoning references and the read-only
`openai-structured-output` skill were checked. Output allowances continue to
include reasoning for models declaring `inside_output`.

The TEST marker `[TEST:SCHEMA_INVALID]` returns syntactically valid JSON with a
wrong field. Both with and without the summary `response_check`, the caller gets
Pydantic `ValidationError`. Before validation, the attempt response recorder
receives the raw SDK envelope and persists its hash. The response, usage, and ID
remain available when validation raises. The append-only usage ledger writes
exactly one event in `finally`, with the final `rejected_validation` outcome;
its write also runs if the manifest outcome callback fails. This preserves the
existing ledger format and accurate per-attempt outcomes rather than adding a
pending-event protocol.

The PostgreSQL manifest hash equals the hash of the actual raw SDK response,
and its provider outcome is `rejected_validation`:

```sql
SELECT response_sha256, provider_outcome
FROM generation_attempt_manifests
WHERE generation_session_id = %s;
```

## Recorded Evidence

```text
episode registry budget: {'model': 'gpt-6-astra', 'seat': 'summaries', 'input_ceiling': 1040976, 'policy_headroom': 1024, 'max_output_tokens': 8000}
season registry budget: {'model': 'gpt-6-astra', 'seat': 'summaries', 'input_ceiling': 1036976, 'policy_headroom': 1024, 'max_output_tokens': 12000}
Responses parse/create request bodies identical; strict schema retained
Budget job proof: ('failed', 1, 'SummaryInputTooLong', "episode summary input too long for model 'TEST': input_tokens=44505, input_budget=1, output_allowance=8000, policy_headroom=871999, token_count_safety_margin=0", None)
Budget job proof: ('failed', 1, 'SummaryInputTooLong', "season summary input too long for model 'TEST': input_tokens=44446, input_budget=1, output_allowance=12000, policy_headroom=871999, token_count_safety_margin=0", None)
Recorded usage proof: {"aggregate": false, "attempt": 1, "cache_creation_tokens": null, "cached_input_tokens": null, "input_tokens": 1000, "model": "TEST", "outcome": "rejected_validation", "output_tokens": 800, "provider": "test", "quota_day": "2026-09-24", "reasoning_tokens": null, "request_id": "resp-mock-6c4feddf", "requests": null, "run_id": "ba2182ac-1f57-40a2-82df-2d46ef65eede", "seat": "summaries", "service_tier": null, "slot": 4, "total_tokens": 1800, "transport": "responses", "ts": "2026-09-24T23:21:32.674813Z"}; manifest=('284b522c08168d971130f7bf62657a4c9529dc9d967b7feb5e87ce87795a596f', 'rejected_validation')
Recorded usage proof: {"aggregate": false, "attempt": 1, "cache_creation_tokens": null, "cached_input_tokens": null, "input_tokens": 1000, "model": "TEST", "outcome": "rejected_validation", "output_tokens": 800, "provider": "test", "quota_day": "2026-09-24", "reasoning_tokens": null, "request_id": "resp-mock-0dad058d", "requests": null, "run_id": "99d57bad-4672-415a-8c79-31df1f9f8a74", "seat": "summaries", "service_tier": null, "slot": 4, "total_tokens": 1800, "transport": "responses", "ts": "2026-09-24T23:21:34.833722Z"}; manifest=('5be313da399222fa8f523485f0b90e1ecd353fada522cb3b12e59bbdac02b9b2', 'rejected_validation')
```

## Source Evidence

- `nexus/config/seat_window.py:35`: shared registry arithmetic; `:103`: summary safety margin.
- `nexus/config/settings_models.py:3280`: typed summary window policy.
- `scripts/summarize_narrative.py:1377`: initial and retry guards; `:1455`: assembled token count and named failure.
- `nexus/jobs/narrative_jobs.py:116`: terminal job classification with attempts remaining.
- `scripts/api_openai.py:603`: create-only Responses exchange; `:621`: raw-response callback before validation; `:674`: final-outcome usage write.
- `scripts/api_openai.py:859`: SDK-derived strict schema in `text.format`.
- `tests/test_api/test_summary_budget_usage.py`: actual HTTP request comparison, populated clone scheduler failure, ledger and manifest assertions.

## Validation Gates

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```

```text
2737 passed, 932 skipped, 9 warnings in 154.13s (0:02:34)
```

```bash
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api tests/test_summary_triggers.py -k 'summar or usage or manifest or budget or window'
```

```text
37 passed, 1 skipped, 419 deselected, 11 warnings in 161.77s (0:02:41)
```

```bash
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_api/test_summary_budget_usage.py
```

```text
7 passed, 5 warnings in 11.18s
```

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_prompt_lint.py tests/test_reachability.py
```

```text
60 passed, 5 warnings in 22.93s
```

```bash
/Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only b2e764b9 HEAD -- '*.py')
```

```text
All done! ✨ 🍰 ✨
14 files would be left unchanged.
```

```bash
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py
```

Exit status 0; no output.

The PostgreSQL gate's only skip is the explicitly opt-in, unauthorized paid
summary proof. No #885 slot-5 failures or exemptions were encountered.
Both implementation commits passed `regenerate-orrery-catalog` and
`validate-config`. The dedicated proof databases were absent from `pg_database`
after fixture teardown.


## Development Corrections

Initial focused tests exposed two test/setup mistakes: passing `by_alias` twice
through the repository's Settings serializer, and adding a second `/v1` to the
TEST fixture URL. The populated-clone test also needed an explicit `session_id`.
All were corrected before the seven-case PostgreSQL proof passed. The first
full offline run found one legacy `SimpleNamespace(parse=...)` fixture; it was
updated to expose `create`, matching the other pre-existing transport fixtures.
No application fallback was added for these failures.

## Coordinator Question

The usage ledger retains its existing append-only one-event-per-attempt contract:
raw response capture precedes validation, and the final-outcome event is appended
in `finally` before the exception reaches the caller. Does the work order require
a durable ledger entry before validation begins, beyond this response-capture
ordering? That stricter timing would require a pending/finalized ledger protocol.


Codex, running GPT-6-Astra.
