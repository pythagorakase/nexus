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

`require_window_capabilities` checks window declarations. Settings validation now
checks only that every entry declares a tokenizer and every declared encoding is a
known tiktoken name. Repository loadability belongs to
`scripts/validate_config_commit.py:41`, used by pre-commit and the CI configuration
job. It probes repositories in one subprocess bounded by the typed
`global.model.tokenizer_probe_timeout_seconds = 120.0` setting. Errors name the
entries. Runtime estimation loads only the selected tokenizer, fails loudly at
first use, and disables remote code. No roster probe runs during settings load.

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
| `nexus/telemetry/prompt_window.py` | 67 | 123 | Yes | Registry tokenizer primitive, re-used by estimator_for |
| `nexus/telemetry/prompt_window.py` | 206 | 267 | Yes | TEST and declared compatible approximations use the registry; native remote guards remain |
| `nexus/telemetry/prompt_window.py` | 270 | 331 | Yes | trust_remote_code=False; failures surface with the entry and approximation guidance |
| `nexus/agents/lore/utils/chunk_operations.py` | 18 | 19 | Yes | Resolved writer counter; accepts an explicit story pin |
| `nexus/agents/lore/utils/chunk_operations.py` | 57 | 26 | Yes | Thin registry-backed writer estimate |
| `nexus/agents/lore/utils/token_budget.py` | 27 | 29 | Yes | Estimates with the explicitly resolved apex_model |
| `nexus/agents/lore/utils/token_budget.py` | 253 | 254 | Yes | Resolved writer estimator for entity text |
| `nexus/agents/logon/apex_schema.py` | 823 | 823 | Yes | Delegates to the registry-backed writer counter |
| `nexus/agents/lore/utils/turn_cycle.py` | 168 | 168 | Yes | Existing delegation now reaches the registry-backed writer counter |
| `nexus/agents/lore/logon_utility.py` | 1617 | 1653 | Yes | Uses estimator_for with the turn settings |
| `nexus/memory/manager.py` | 1043 | 1063 | Yes | Replaces words times 1.25 with the story writer estimator |
| `nexus/memory/incremental.py` | 231 | 233 | Yes | Uses the owning memory manager counter or resolved writer counter |
| `nexus/memory/correspondence.py` | 62 | 64 | Yes | Existing delegation now reaches the registry-backed writer counter |
| `nexus/memory/correspondence.py` | 109 | 112 | Yes | Existing delegation now reaches the registry-backed writer counter |
| `nexus/memory/correspondence.py` | 181 | 184 | Yes | Existing delegation now reaches the registry-backed writer counter |
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

- `nexus/telemetry/prompt_window.py:67`: `estimator_for`.
- `nexus/telemetry/prompt_window.py:77`: request-content estimate.
- `scripts/validate_config_commit.py:41`: bounded commit/CI roster validation.
- `nexus/config/settings_models.py:3848`: declarative settings validation.
- `nexus/telemetry/usage.py:477`: drift log, separate from reported accounting.
- `nexus/telemetry/attempt_manifest.py:208`: numeric JSON update.
- `tests/test_lore/test_token_estimator.py:36`: every registered model.
- `tests/test_lore/test_token_estimator.py:75`: invalid settings fixtures.
- `tests/test_lore/test_token_estimator.py:263`: real HTTP drift proof.
- `tests/test_lore/test_token_estimator.py:325`: real PostgreSQL manifest proof.

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

## PR 945 Review Fixes

Rebased onto `c468182c` (#943) before editing. `origin/main` advanced to `9f394764`
(#944) during this run; benchmark evidence includes both versions. The baseline
sources below are `git archive` exports in `/tmp`, not other worktrees. The main
checkout and other worktrees were not modified.

- Settings: declaration-only validation; bounded repository probing moved to the
  commit script and CI. First-use failure retains the entry name, remote-code
  prohibition, and explicit approximation guidance.
- Memory: `turn_cycle.py:334` passes the model resolved by LOGON into
  `ContextMemoryManager.configure_storyteller_budget`; `_estimator_story` retains
  it across subsequent story-window refreshes. The incremental retriever already
  uses the manager's bound counter. Letter/digest validators and accepted
  correspondence rendering now receive the model/story explicitly. The remaining
  `apex_schema.calculate_token_count` and `_context_component_token_count` helpers
  have no production call sites; standalone incremental retrieval retains its
  default-writer counter when no owning manager supplies one.
- Drift: `prompt_window.py:130` treats tiktoken special-token spellings as ordinary
  text. `usage.py:503` and the Pydantic AI recorder isolate estimation/manifest
  failures, emitting one ERROR record with a single-line cause. Actual reported
  usage is recorded before estimation and is never replaced by an estimate.

Two intended behavior changes: TEST memory budgeting now uses `o200k_base` instead
of words × 1.25; compatible approximation retry guards subtract the registry safety
margin, matching the assembly reserve.

### Cold Settings Load

Each sample is a fresh shared-interpreter process. Timing includes the initial
`nexus.config` import and `load_settings()`; it excludes process creation. Seven
samples per source, median comparison. Both deltas are below 0.1 seconds.

```sh
mkdir -p /tmp/qa818-revision/base
git archive c468182c nexus nexus.toml | tar -x -C /tmp/qa818-revision/base
# The origin/main export was captured at 9f394764:
git archive 9f394764 nexus nexus.toml | tar -x -C /tmp/qa818-revision
/Users/pythagor/nexus/.venv/bin/python /tmp/qa818-revision/benchmark.py
```

Benchmark script:

```python
import os
import statistics
import subprocess
from pathlib import Path

py = '/Users/pythagor/nexus/.venv/bin/python'
code = 'import time; start=time.perf_counter(); from nexus.config import load_settings; load_settings(); print(time.perf_counter()-start)'
for label, root in [('merge-base c468182c', Path('/tmp/qa818-revision/base')), ('origin/main 9f394764', Path('/tmp/qa818-revision')), ('branch', Path.cwd())]:
    samples = []
    for _ in range(7):
        result = subprocess.run([py, '-c', code], cwd=root, env={**os.environ, 'PYTHONPATH': str(root)}, capture_output=True, text=True, check=True)
        samples.append(float(result.stdout.strip()))
    print(f'{label}: median={statistics.median(samples):.6f}s; samples=' + ', '.join(f'{sample:.6f}' for sample in samples))
```

```text
merge-base c468182c: median=0.343110s; samples=0.474223, 0.404042, 0.341114, 0.343333, 0.341448, 0.338105, 0.343110
origin/main 9f394764: median=0.341584s; samples=0.337832, 0.340631, 0.341782, 0.341584, 0.348455, 0.339933, 0.343415
branch: median=0.344919s; samples=0.343796, 0.344470, 0.353277, 0.347234, 0.346217, 0.344702, 0.344919
```

### Real HTTP and PostgreSQL Evidence

The empty-cache test launches a fresh process with `HF_HUB_OFFLINE=1`, `HF_HOME`,
`HUGGINGFACE_HUB_CACHE`, and `TRANSFORMERS_CACHE` pointing at empty temporary paths.
It loads settings and completes a TEST HTTP exchange containing `<|endoftext|>`;
Transformers is never imported and the cache directory is not created.

```text
offline TEST exchange passed; Transformers not imported
token_estimate seat=skald_writer model=TEST estimated=14 reported=14 ratio=1.00
token_estimate seat=skald_writer model=TEST estimated=15 reported=15 ratio=1.00
```

The 15-token line is the special-token literal prompt plus system text, verified
on Responses and Chat Completions. An additional real HTTP test assigns TEST a
nonexistent repository in a temporary settings fixture. The successful response
and reported accounting survive, with exactly one `token_estimate_failed` ERROR
record naming the invalid repository and cause.

The clone-owned admission test (`test_token_estimator.py:417`) uses actual stored
story settings, LOGON route resolution, turn setup, and MEMNON's SQL-only recent
chunk method. It needs `global_variables`, `narrative_chunks`, and `chunk_metadata`
from the fixture template. Each clone is created and dropped by
`disposable_slot_database`; no inference is performed. With `token_estimate` as
the stored chunk text, Hermes admits at budget 2 and rejects at budget 1. The test
covers both a Hermes story pin and a Hermes override over a TEST-pinned story, and
refreshes story settings after resolving the route to prove the override survives.

```text
writer=nousresearch/hermes-4-70b admission=2 repository_default=3 override=False
writer=nousresearch/hermes-4-70b admission=2 repository_default=3 override=True
```

### Review Validation Commands and Results

No UI build applies. No paid calls, new migration, new persistent table, manually
managed gateway, dependency change, or fleet mutation. No #885 exemptions needed.
The offline suite skips opt-in PostgreSQL/live-provider tests; the explicit
PostgreSQL selection runs them with no skips.

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2835 passed, 948 skipped, 9 warnings in 129.65s (0:02:09)
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore tests/test_api -k 'token or estimate or window or usage'
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
88 passed, 730 deselected, 11 warnings in 36.11s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_reachability.py tests/test_prompt_lint.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
60 passed, 5 warnings in 18.23s
```

```sh
/Users/pythagor/nexus/.venv/bin/python -m black --check $(git diff --name-only --diff-filter=ACMR $(git merge-base HEAD origin/main) -- '*.py')
```

```text
All done! ✨ 🍰 ✨
24 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/validate_config_commit.py
```

```text
Exit status 0; no stdout or stderr.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/check_model_drift.py
```

```text
OK: no model-ID drift detected.
```

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_reachability.py --report /tmp/qa818-revision/reachability.json
```

```text
{
  "maintained": 364,
  "reachable_by_kind": {
    "production": 199,
    "operator": 185,
    "migration": 181,
    "test": 248
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
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore/test_token_estimator.py tests/test_lore/test_logon_prompt_formatting.py tests/test_lore/test_memory_manager.py tests/test_lore/test_turn_cycle.py
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
119 passed, 3 skipped, 5 warnings in 12.42s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_lore/test_token_estimator.py -k 'drift or empty_hf'
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
8 passed, 26 deselected, 5 warnings in 6.60s
```

```sh
PYTHONPATH=$PWD NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q -s tests/test_lore/test_token_estimator.py -k memory_admission
```

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2 passed, 32 deselected, 5 warnings in 4.32s
```

The implementation commit ran the installed hooks without bypass:

```text
Regenerate Orrery package catalog........................................Passed
Validate NEXUS config and model-ID drift.................................Passed
```

The CI YAML also parsed successfully, and the install step selected exactly the
six existing project dependency constraints needed for registry validation. The
remote CI job itself has not run for this revision yet; this order stops after
pushing and does not wait for remote review/checks.

Diagnostic history for this revision: the first admission fixture used
`Hello world!`, which both tokenizers count as 3; it was replaced with a measured
2-versus-3 boundary. The next fixture passed a disposable name through LOGON's
slot-only reader; it now supplies the real DB-read story snapshot through LOGON's
existing `story_settings` argument. An initial Black invocation compared directly
with a concurrently advanced `origin/main` and named deleted upstream-only files;
the corrected command checks extant changed files against the merge base. These
were fixture/command corrections, not exempted failures.

## Original Submission Proof (Before Review Fixes)

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
