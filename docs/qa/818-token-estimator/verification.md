# Work Order 818 Verification

## Scope and Import Isolation

One model-aware local estimator supplies text estimates. Provider-reported usage
remains the accounting truth; estimates never alter ledger totals. No dependencies,
UI, tables, or migrations changed. No paid calls were made. No manually managed
gateway was started; HTTP tests own and close their loopback servers and repository
fixtures own their disposable databases and services.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/818-token-estimator/nexus/__init__.py
```

`require_window_capabilities` only checks window declarations. The settings-level
registry validator now requires a usable tokenizer for every entry, including
unselected entries. It probes repository tokenizers in a cached, batched subprocess
using the same interpreter and loader; this preserves the existing gateway import
contract that forbids loading Transformers/Torch just to import the API app. Actual
estimation loads the selected tokenizer in process. Both paths disable remote code.

## Repository Probes and Registry Changes

Every repository was attempted before editing the registry:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python - <<'PYPROBE'
import tomllib
from transformers import AutoTokenizer
with open('nexus.toml','rb') as f: config=tomllib.load(f)
for provider in config['global']['model']['api_models'].values():
 for entry in provider['models']:
  if repo:=entry.get('tokenizer_repository'):
   try:
    tokenizer=AutoTokenizer.from_pretrained(repo,trust_remote_code=False)
    print(entry['id'], 'OK', type(tokenizer).__name__, len(tokenizer.encode('The quick brown fox jumps over the lazy dog.',add_special_tokens=False)),flush=True)
   except Exception as exc: print(entry['id'],type(exc).__name__,str(exc),flush=True)
PYPROBE
```

| Entry | Before | After | Probe Result / Reason |
| --- | --- | --- | --- |
| `nousresearch/hermes-4-70b` | `NousResearch/Hermes-4-70B` | Unchanged | PreTrainedTokenizerFast; 10 tokens |
| `nousresearch/hermes-4.3-36b` | `NousResearch/Hermes-4.3-36B` | Unchanged | PreTrainedTokenizerFast; 10 tokens |
| `moonshotai/kimi-k2.5` | `moonshotai/Kimi-K2.5` | `o200k_base`, margin 4096 | Remote code required |
| `moonshotai/kimi-k3` | `moonshotai/Kimi-K3` | `o200k_base`, margin 4096 | Remote code required |
| `deepseek/deepseek-v4-pro` | `deepseek-ai/DeepSeek-V4-Pro` | Unchanged | PreTrainedTokenizerFast; 10 tokens |
| `nousresearch/hermes-4-405b` | `NousResearch/Hermes-4-405B` | Unchanged | PreTrainedTokenizerFast; 10 tokens |
| `minimax/minimax-m3` | `MiniMaxAI/Minimax-M3` | Unchanged | PreTrainedTokenizerFast; 10 tokens |
| `z-ai/glm-5` | `zai-org/GLM-5` | `o200k_base`, margin 4096 | Installed Transformers cannot load TokenizersBackend |

The three changed entries carry the requested Anthropic-style comment. Compatible
routes without a remote count endpoint use the declared local request estimate and
reserve the registry margin in assembly and in the final retry guard. This is an
approximation, not a claim of exact provider tokenization.

Exact probe output:

```text
nousresearch/hermes-4-70b OK PreTrainedTokenizerFast 10
nousresearch/hermes-4.3-36b OK PreTrainedTokenizerFast 10
moonshotai/kimi-k2.5 ValueError Loading moonshotai/Kimi-K2.5 requires you to execute the configuration file in that repo on your local machine. Make sure you have read the code there to avoid malicious use, then set the option `trust_remote_code=True` to remove this error.
moonshotai/kimi-k3 ValueError Loading moonshotai/Kimi-K3 requires you to execute the configuration file in that repo on your local machine. Make sure you have read the code there to avoid malicious use, then set the option `trust_remote_code=True` to remove this error.
deepseek/deepseek-v4-pro OK PreTrainedTokenizerFast 10
nousresearch/hermes-4-405b OK PreTrainedTokenizerFast 10
minimax/minimax-m3 OK PreTrainedTokenizerFast 10
z-ai/glm-5 ValueError Tokenizer class TokenizersBackend does not exist or is not currently imported.
```

## Estimator Inventory Before and After

Reachability command (the CLI requires a path after `--report`):

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_reachability.py --report /tmp/qa818/reachability.json
```

The original bare `--report` invocation returned
`check_reachability.py: error: argument --report: expected one argument`.
The corrected report has no reachability findings. “Yes” below means production
module reachability, not proof that an individual route executes the function.
Before line numbers refer to `origin/main` at the branch base; after numbers refer
to this implementation.

| File | Before Lines | After Lines | Production Reachable | Result |
| --- | --- | --- | --- | --- |
| `nexus/telemetry/prompt_window.py` | 67 | 173 | Yes | Registry tokenizer primitive, re-used by estimator_for |
| `nexus/telemetry/prompt_window.py` | 206 | 315 | Yes | TEST and declared compatible approximations use the registry; native remote guards remain |
| `nexus/telemetry/prompt_window.py` | 270 | 379 | Yes | trust_remote_code=False; failures surface with the entry and approximation guidance |
| `nexus/agents/lore/utils/chunk_operations.py` | 18 | 19 | Yes | Resolved writer counter; accepts an explicit story pin |
| `nexus/agents/lore/utils/chunk_operations.py` | 57 | 26 | Yes | Thin registry-backed writer estimate |
| `nexus/agents/lore/utils/token_budget.py` | 27 | 29 | Yes | Estimates with the explicitly resolved apex_model |
| `nexus/agents/lore/utils/token_budget.py` | 253 | 254 | Yes | Resolved writer estimator for entity text |
| `nexus/agents/logon/apex_schema.py` | 823 | 823 | Yes | Delegates to the registry-backed writer counter |
| `nexus/agents/lore/utils/turn_cycle.py` | 168 | 168 | Yes | Existing delegation now reaches the registry-backed writer counter |
| `nexus/agents/lore/logon_utility.py` | 1617 | 1617 | Yes | Uses estimator_for with the turn settings |
| `nexus/memory/manager.py` | 1043 | 1044 | Yes | Replaces words times 1.25 with the story writer estimator |
| `nexus/memory/incremental.py` | 231 | 233 | Yes | Uses the owning memory manager counter or resolved writer counter |
| `nexus/memory/correspondence.py` | 62 | 62 | Yes | Existing delegation now reaches the registry-backed writer counter |
| `nexus/memory/correspondence.py` | 109 | 109 | Yes | Existing delegation now reaches the registry-backed writer counter |
| `nexus/memory/correspondence.py` | 181 | 181 | Yes | Existing delegation now reaches the registry-backed writer counter |
| `scripts/api_openai.py` | 160 | 157 | Yes | Registry estimator; no mapping or fallback |
| `scripts/api_anthropic.py` | 152 | 149 | Yes | Registry estimator; no mapping or fallback |
| `scripts/api_anthropic.py` | 212, 1217 | 183, 1191 | Yes | Both base and concrete counters estimate locally; no provider-call fallback |
| `scripts/api_anthropic.py` | 1324, 1337 | 1278, 1291 | Yes | Both cache-section and whole-prompt estimates use get_token_count |
| `scripts/summarize_narrative.py` | 1461 | 1461 | Yes | Summary request estimator_for(model) |
| `scripts/api_openrouter.py` | 131 | 131 | No | Mechanical migration to estimator_for |
| `scripts/token_counter.py` | 13 | 13 | No | Mechanical migration to callable registry counter |
| `scripts/token_counter.py` | 108 | 107 | No | Resolved writer model; deleted name mapping |
| `scripts/assemble_context.py` | 65 | 65 | No | Mechanical migration to writer estimator |
| `scripts/estimate_time_delta.py` | 128 | 125 | No | Mechanical migration to estimator_for |
| `scripts/estimate_time_delta.py` | 1069 | 1028 | No | Existing output forecast now measures prompt with registry estimator |

All four named unreachable scripts were mechanical migrations, so none were left
with their old text-count heuristics. The operator-only
`scripts/qa_shift/card_identity_probe.py` still calls `local_text_counter` directly;
that is the same registry primitive, not an independent tokenizer strategy. MEMNON
cross-encoder tokenization is the reranker's own input preparation, not an LLM
prompt estimate, and is unchanged. Forecasts of future output size for TPM checks
remain forecasts; they do not tokenize existing text.

New entrypoints and proof locations:

- `nexus/telemetry/prompt_window.py:69`: `estimator_for`.
- `nexus/telemetry/prompt_window.py:79`: request-content estimate.
- `nexus/telemetry/prompt_window.py:115`: isolated roster validation.
- `nexus/config/settings_models.py:3842`: settings-load enforcement.
- `nexus/telemetry/usage.py:477`: drift log, separate from reported accounting.
- `nexus/telemetry/attempt_manifest.py:208`: numeric JSON update.
- `tests/test_lore/test_token_estimator.py:33`: every registered model.
- `tests/test_lore/test_token_estimator.py:72`: invalid settings fixtures.
- `tests/test_lore/test_token_estimator.py:192`: real HTTP drift proof.
- `tests/test_lore/test_token_estimator.py:252`: real PostgreSQL manifest proof.

## Drift and Attempt Evidence

The recorder logs estimated input divided by reported input. Anthropic reported
input for this comparison includes cache-read and cache-creation counts, while its
existing usage event fields and totals remain unchanged. Zero/zero yields 1.00;
a nonzero estimate over a reported zero yields infinity. Requests with absent
reported input have no ratio. Native wrappers retain the actual submitted request
across validation retries. Pydantic AI emits one drift line for each new response,
using visible message history, while retaining its existing aggregate usage event.
Hidden framing, tool definitions unavailable from Pydantic AI results, and provider
internals can cause drift; this telemetry is deliberately advisory.

The TEST proof uses real HTTP and the real SDK/provider wrappers against an owned
loopback server that independently counts the supplied text with o200k_base. Both
Responses and Chat Completions produce:

```text
token_estimate seat=skald_writer model=TEST estimated=14 reported=14 ratio=1.00
```

A separate real Pydantic AI HTTP exchange also verifies ratio 1.00. The PostgreSQL
proof creates a fixture-owned disposable database, inserts a generation session and
manifest, and reads its JSON back: original `input_tokens=10`, separate
`estimated_input_tokens=10`, `reported_input_tokens=12`. The existing
`generation_attempt_manifests.window_record` JSON has room for both counts; no new
persistent table or schema migration is needed.

## Proof Commands and Results

All commands run from this worktree with its imports proven above. The Black
command ran before staging/committing and covered all 20 changed Python files.
No UI build applies. Offline PostgreSQL/live-provider skips are expected; the
separate PostgreSQL selection ran without skips. No #885 exemptions were needed.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2828 passed, 936 skipped, 9 warnings in 253.74s (0:04:13)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore tests/test_api -k 'token or estimate or window or usage'
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
79 passed, 730 deselected, 11 warnings in 34.66s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py tests/test_prompt_lint.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 25.79s
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only -- '*.py') tests/test_lore/test_token_estimator.py
```

```text
All done! ✨ 🍰 ✨
20 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py
```

Exit status 0; no stdout or stderr.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/check_model_drift.py
```

```text
OK: no model-ID drift detected.
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_reachability.py --report /tmp/qa818/reachability-final.json
```

```text
{
  "maintained": 364,
  "reachable_by_kind": {
    "production": 199,
    "operator": 185,
    "migration": 181,
    "test": 247
  },
  "test_only": 37,
  "existing_unreachable": 72,
  "newly_unreachable": [],
  "lost_production_reachability": [],
  "baseline_add_production_paths": [],
  "baseline_remove_orphan_exemptions": [],
  "baseline_remove_deleted_production_paths": [],
  "forbidden_dependencies": [],
  "tombstone_violations": [],
  "unresolved_internal_imports": [],
  "unregistered_dynamic_import_sites": [],
  "route_reachability": "not_proven"
}
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_token_estimator.py tests/test_usage_recorder.py tests/test_lore/test_seat_window.py tests/test_config/test_provider_guard.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
81 passed, 1 skipped, 5 warnings in 16.39s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_lore/test_token_estimator.py -k 'drift_real_test'
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2 passed, 22 deselected, 5 warnings in 4.48s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_api/test_import_side_effects.py tests/test_lore/test_token_estimator.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
32 passed, 1 skipped, 5 warnings in 29.79s
```

Earlier diagnostic runs (the final gates above supersede them):

| Exact Command | Verbatim Final Tail | Resolution |
| --- | --- | --- |
| `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_usage_recorder.py tests/test_lore/test_seat_window.py` | `26 passed, 5 warnings in 7.35s` | Initial counter/usage regression check. |
| `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_token_estimator.py tests/test_usage_recorder.py tests/test_lore/test_seat_window.py tests/test_config/test_provider_guard.py` | `2 failed, 77 passed, 5 warnings in 9.18s` | Removed duplicate by_alias argument from new fixture construction. |
| `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_token_estimator.py` | `2 failed, 21 passed, 1 skipped, 5 warnings in 4.64s` | Replaced JSON serialization of typed settings with a real TOML fixture. |
| `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_token_estimator.py tests/test_lore/test_chunk_operations.py` | `3 failed, 43 passed, 2 skipped, 5 warnings in 4.90s` | Used the canonical TOML loader; updated legacy encoding-object test for the callable counter. |
| `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q` | `1 failed, 2826 passed, 936 skipped, 9 warnings in 254.60s (0:04:14)` | The sole failure was the API import contract; isolated repository validation now preserves it. |

The earlier PostgreSQL selection finished with `78 passed, 730 deselected, 11 warnings in 26.13s`; it was rerun after final changes. The earlier static selection finished with `60 passed, 5 warnings in 24.69s`. Formatting used `/Users/pythagor/nexus/.venv/bin/python -m black` on the changed Python files; its final check is above. Collection diagnostics used `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest --collect-only -q` (`3761 tests collected in 1.56s`).

The implementation commit ran both installed pre-commit hooks successfully:

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
```

## Deferred Work and Coordinator Questions

No named estimator migration is deferred. No coordinator decision is outstanding.
No merge or review-bot wait is part of this work order.

Codex, running GPT-6-Astra.
