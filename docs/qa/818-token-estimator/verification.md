# Work Order 818 Stop-Report

Stopped before implementation on 2026-09-24 under the work order's escape
hatch. The second amendment resolves the Kimi remote-code requirement, but
the required all-entry estimator gate has another incompatible repository:
`z-ai/glm-5` declares `zai-org/GLM-5`, whose tokenizer configuration names
`TokenizersBackend`. The shared interpreter has transformers 4.51.3, which
cannot load that class. No dependencies, runtime source, registry entries,
databases, or services were changed. No paid provider calls were made.

The amendment authorizes an explicit approximation for repositories that
require remote code. GLM-5 instead fails class lookup and its tokenizer
configuration has no `auto_map`. Applying the approximation to it requires
a further coordinator ruling. No silent fallback or remote code was used.

## Completed Checks

Import isolation:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/818-token-estimator/nexus/__init__.py
```

Repository probe (each load attempted independently):

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python - <<'PY'
import tomllib
from transformers import AutoTokenizer
with open('nexus.toml','rb') as f:
    settings=tomllib.load(f)
for provider in settings['global']['model']['api_models'].values():
    for entry in provider['models']:
        repository=entry.get('tokenizer_repository')
        if repository:
            try:
                tokenizer=AutoTokenizer.from_pretrained(repository,trust_remote_code=False)
                print(entry['id'], 'OK', type(tokenizer).__name__, len(tokenizer.encode('The quick brown fox jumps over the lazy dog.',add_special_tokens=False)), flush=True)
            except Exception as exc:
                print(entry['id'], type(exc).__name__, str(exc), flush=True)
PY
```

| Entry | Before and After | Probe Result |
| --- | --- | --- |
| `nousresearch/hermes-4-70b` | `NousResearch/Hermes-4-70B` repository, unchanged | `PreTrainedTokenizerFast`, 10 tokens |
| `nousresearch/hermes-4.3-36b` | `NousResearch/Hermes-4.3-36B` repository, unchanged | `PreTrainedTokenizerFast`, 10 tokens |
| `moonshotai/kimi-k2.5` | `moonshotai/Kimi-K2.5` repository, unchanged | Remote code required; approved approximation pending |
| `moonshotai/kimi-k3` | `moonshotai/Kimi-K3` repository, unchanged | Remote code required; approved approximation pending |
| `deepseek/deepseek-v4-pro` | `deepseek-ai/DeepSeek-V4-Pro` repository, unchanged | `PreTrainedTokenizerFast`, 10 tokens |
| `nousresearch/hermes-4-405b` | `NousResearch/Hermes-4-405B` repository, unchanged | `PreTrainedTokenizerFast`, 10 tokens |
| `minimax/minimax-m3` | `MiniMaxAI/Minimax-M3` repository, unchanged | `PreTrainedTokenizerFast`, 10 tokens |
| `z-ai/glm-5` | `zai-org/GLM-5` repository, unchanged | Unsupported `TokenizersBackend` class |

Exact Kimi errors:

```text
moonshotai/kimi-k2.5 ValueError Loading moonshotai/Kimi-K2.5 requires you to execute the configuration file in that repo on your local machine. Make sure you have read the code there to avoid malicious use, then set the option `trust_remote_code=True` to remove this error.
moonshotai/kimi-k3 ValueError Loading moonshotai/Kimi-K3 requires you to execute the configuration file in that repo on your local machine. Make sure you have read the code there to avoid malicious use, then set the option `trust_remote_code=True` to remove this error.
```

Independent GLM diagnosis:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python - <<'PY'
import json
import transformers
from transformers.utils.hub import cached_file
from transformers import AutoTokenizer
print('transformers=' + transformers.__version__, flush=True)
path=cached_file('zai-org/GLM-5','tokenizer_config.json')
with open(path) as f:
    config=json.load(f)
print(json.dumps({key:config.get(key) for key in ('tokenizer_class','auto_map')},sort_keys=True), flush=True)
AutoTokenizer.from_pretrained('zai-org/GLM-5',trust_remote_code=False)
PY
```

```text
transformers=4.51.3
{"auto_map": null, "tokenizer_class": "TokenizersBackend"}
Traceback (most recent call last):
  File "<stdin>", line 10, in <module>
  File "/Users/pythagor/nexus/.venv/lib/python3.11/site-packages/transformers/models/auto/tokenization_auto.py", line 1006, in from_pretrained
    raise ValueError(
ValueError: Tokenizer class TokenizersBackend does not exist or is not currently imported.
```

Reachability initially rejected the order's bare `--report` option:

```text
check_reachability.py: error: argument --report: expected one argument
```

The corrected command completed successfully:

```sh
/Users/pythagor/nexus/.venv/bin/python -S scripts/check_reachability.py --report /tmp/818-reachability.json
```

Its report has no newly unreachable modules, lost production reachability,
forbidden dependencies, tombstone violations, unresolved internal imports,
or unregistered dynamic import sites. Route reachability is `not_proven`.

## Estimator Inventory Before and After

All sites remain unchanged because implementation stopped at the loader probe.
These are the token-estimator sites identified by the initial source scan;
this is not a completed consolidation audit.

| Site | Production Reachable | Current Behavior |
| --- | --- | --- |
| `nexus/telemetry/prompt_window.py:67` | Yes | Registry-derived local counter |
| `nexus/telemetry/prompt_window.py:241` | Yes | TEST-specific o200k count |
| `nexus/telemetry/prompt_window.py:269` | Yes | Repository loader currently permits remote code |
| `nexus/agents/lore/utils/chunk_operations.py:18` | Yes | Name mappings and silent fallback |
| `nexus/agents/lore/utils/chunk_operations.py:57` | Yes | Chunk count using the mapped encoding |
| `nexus/agents/lore/utils/token_budget.py:62` | Yes | Chunk-counter delegation for user input |
| `nexus/agents/lore/utils/token_budget.py:253` | Yes | Entity estimates delegate to chunk counter |
| `nexus/agents/logon/apex_schema.py:823` | Yes | Chunk-counter delegation |
| `scripts/api_openai.py:160` | Yes | Encoding mappings and character fallback |
| `scripts/api_anthropic.py:164` | Yes | cl100k and character fallback |
| `scripts/api_anthropic.py:1324` | Yes | Character estimate for cache sections |
| `scripts/api_anthropic.py:1337` | Yes | Character estimate for cache prompt |
| `scripts/api_openrouter.py:131` | No | Character estimate; untouched |
| `scripts/token_counter.py:13` | No | Encoding supplied by mapped model at line 159; untouched |
| `scripts/assemble_context.py:65` | No | cl100k encoder used at line 159; untouched |
| `scripts/estimate_time_delta.py:128` | No | Encoding mappings and character fallback; untouched |
| `scripts/estimate_time_delta.py:1069` | No | Character estimate for output; untouched |

`APIModelEntry.require_window_capabilities` at
`nexus/config/settings_models.py:144` only checks the context window; it does
not validate tokenizer presence or loadability. The attempt manifest already
stores numeric window data in JSON (`nexus/telemetry/attempt_manifest.py:76`),
but adding an estimate beside reported usage has not been implemented.

## Deferred Gates and Coordinator Question

No pytest, PostgreSQL, Black, prompt-lint, or TEST HTTP exchange gates were
run. No drift line exists. Nothing is represented as a passing implementation.
Push and PR creation are deferred because the proof gates have not passed.

May `z-ai/glm-5` use the same explicit `o200k_base` approximation and
4096-token safety margin despite failing tokenizer-class compatibility
rather than requiring remote code?

Codex, running GPT-6-Astra.
