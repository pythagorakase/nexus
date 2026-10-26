# Verification: Fable Structured-Output Diagnostics and the Production Probe (845-S1S2)

Issue #845. Branch `claude/845-fable-probe`, cut from `c7ae2988`, merged with
`origin/main` at `9a0714d7`. No migration, no paid call, no gateway started by
this branch's own work, no `nexus.toml` change, no `ui/` change.

## What Was Wrong (Cited on `main` at c7ae2988)

- `scripts/api_anthropic.py:1095`: the native extractor raised a bare
  `ValueError("Anthropic structured response did not include JSON output")`;
  the tool-envelope (`:1117-1120`) and prompted (`:1136-1138`) messages were
  equally bare. `grep -n stop_reason scripts/api_anthropic.py` was empty.
- `:1092-1093` and `:1141`: a `max_tokens` cut or a prose refusal failed as a
  Pydantic `ValidationError` (`json_invalid`), hiding the cause.
- `:618-650` (`_log_structured_output_rejection`, format at `:631-632`): the
  rejection line carried transport, model, seat, attempt, exception and error
  only, although all nine callers had the raw `response` in scope
  (`response: Any = None` at `:699`, `:799`, `:897`).
- `:757-767`, `:857-867`, `:953-963`: every `ValueError` is repaired up to
  `structured_output_retries` times (`nexus.toml:1217` sets 3).

## What Changed (Branch Lines)

- `scripts/api_anthropic.py:95` `anthropic_response_diagnostics(response)`:
  `stop_reason=<s> block_types=<b> output_tokens=<o>`, reading only
  `stop_reason`, each block's `type`, and `usage.output_tokens`.
- `scripts/api_anthropic.py:120` `_raise_for_stop_reason`: `max_tokens` and
  `refusal` get their own `ValueError`, chained to the original failure.
- Extractors (`:1166`, `:1197`, `:1231`): each body is wrapped; the three "did
  not include" messages end with `; <diagnostics>`; the handlers always raise
  (`:1193`, `:1227`, `:1269`). The inner prompted handler keeps its AST and
  baseline key.
- Log line (`:665`, format `:685`): `... exception=%s %s error=%s` with the
  diagnostics; all nine callers pass `response=response`. The "retries
  exhausted" line is unchanged.
- Six repair handlers carry
  `# nexus-exception-disposition: retry; reason=repair; safety=cap`
  (`:805`, `:821`, `:916`, `:932`, `:1023`, `:1039`); six baseline keys removed
  from `config/exception_disposition_baseline.json`:
  - `scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_native_sync|4f6aee874518d7b497c8121263bd00be2622b97d6150540559f7fb6fe422b552|1`
  - `scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_native_sync|b579fbe35541eef974979bcc8ee3044c903ee09048f42eca3fdeb57800748287|1`
  - `scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_prompted_sync|5232a12fde564bdeaa332a92ecd6206c668145821c73cda37cbb1135dcd9f5fa|1`
  - `scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_prompted_sync|ef6a33f673935b9a879846bf2a53c0eeea43e2d8b61af8f0fa4309149e7e0430|1`
  - `scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_tool_envelope_sync|32200c3c3fd5336910000f1cc344e3db3f1f2a1f249e076c4fe3e341f7078312|1`
  - `scripts/api_anthropic.py|AnthropicProvider._get_structured_completion_tool_envelope_sync|bc244d791756853f3e74618648e36e6201cf5a9b794e4957d423b16cf6af1c83|1`
- `tests/test_fable_structured_output_live.py`: the opt-in probe (845-S2).
- `tests/test_fable_probe_parsing.py`: offline proofs of the probe's parser,
  join, verdict, evidence writer and lane refusal.
- `AGENTS.md`, `docs/turn_flow_sequence.md`: `verified_commit` moved to the
  merge base `9a0714d7671457d47f91bfbd76749fee4444c686`; the repair paragraph
  (`docs/turn_flow_sequence.md:212-214`) still holds.

## Red Run (S1 Tests Against Unchanged Product Code)

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q tests/test_native_structured_output.py -k stop_reason`

```
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[thinking_only-native]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[thinking_only-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[thinking_only-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[empty-native]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[empty-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[empty-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[truncated-native]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[truncated-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[truncated-tool_envelope]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[refusal-native]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[refusal-prompted]
FAILED tests/test_native_structured_output.py::test_anthropic_extractors_name_stop_reason_and_blocks[refusal-tool_envelope]
12 failed, 1 passed, 122 deselected, 5 warnings in 1.60s
```

The one pass is `test_anthropic_accepts_valid_output_whatever_the_stop_reason`
(passes before and after). `truncated-native` and `truncated-prompted` failed
with `isinstance(exc, ValidationError)` true (`json_invalid`).

## Green Runs (After Merging `origin/main` at 9a0714d7)

`nice -n 15 $PY -m pytest -q tests/test_native_structured_output.py tests/test_fable_probe_parsing.py tests/test_owner_target_guard.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
220 passed, 5 warnings in 7.17s
```

`$PY -m pytest -q tests/test_reachability.py tests/test_doc_front_matter.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
126 passed, 5 warnings in 17.50s
```

`$PY -m pytest -q --collect-only tests/test_fable_structured_output_live.py`

```
1 test collected in 0.26s
```

PostgreSQL (`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset):
`NEXUS_RUN_POSTGRES=1 NEXUS_RUN_CORPUS=1 nice -n 15 $PY -m pytest -q -rs -p tests.dbname_audit tests/test_live_gate_clones_pg.py tests/test_fable_structured_output_live.py`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
dbname audit: 7 targets: postgres, qa640_test_golden_path_staging_*, qa640_test_issue_600_staging_c_*, qa640_test_issue_601_staging_p_*, qa640_test_live_cycle_seed_rou_*, qa640_test_maturation_enqueue__*, qa640_test_retrograde_wizard_s_*
dbname audit: owner server: local:5432
dbname audit: unaudited connection classes: psycopg2.extensions.ReplicationConnection
dbname audit: owner targets: none
=========================== short test summary info ============================
SKIPPED [1] tests/test_fable_structured_output_live.py: Set NEXUS_845_PROBE=1 to run the paid #845 Fable probe.
6 passed, 1 skipped, 2 warnings in 21.84s
```

Load: the pre-merge PostgreSQL run started at a one-minute load of 15.32 (same
result, 6 passed, 1 skipped, owner targets none). The post-merge rerun above
started at a one-minute load of 31.36 without the bounded wait the machine-load
rule asks for; it was a 22-second run of six tests.

Offline: `nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
3260 passed, 698 skipped, 8 warnings in 679.42s (0:11:19)
```

(A first run before the merge failed only
`tests/test_scripts/test_check_exception_dispositions.py::test_repository_tree_matches_committed_baseline`:
`origin/main` had moved under the run, its baseline had shrunk, and the
branch was behind it. The merge resolved it; the run above is post-merge.)

`nice -n 15 $PY -m pytest -q tests/test_api tests/test_orrery`

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
1910 passed, 1547 skipped, 7 warnings in 48.54s
```

## Static Checks

- Black: `4 files would be left unchanged.`
- `$PY -S scripts/check_exception_dispositions.py --baseline-base-ref origin/main`:
  `OK: exception disposition coverage and shrink-only baseline verified.`
- `$PY scripts/check_model_drift.py`: `OK: no model-ID drift detected.`
- flake8, branch, on the four files:
  ```
  scripts/api_anthropic.py:38:1: F401 'os' imported but unused
  scripts/api_anthropic.py:871:89: E501 line too long (90 > 88 characters)
  ```
  `origin/main` versions of the two pre-existing files:
  ```
  scripts/api_anthropic.py:38:1: F401 'os' imported but unused
  scripts/api_anthropic.py:806:89: E501 line too long (90 > 88 characters)
  ```
  Same two diagnostics on untouched lines (the E501 is the
  `_build_tool_envelope_structured_request_params` guard call, moved by the
  inserted helpers). No new diagnostics.
- mypy `--explicit-package-bases`, branch, on the four files: 10 errors in 2
  files (`scripts/api_anthropic.py:427`, `:1391`, `:1404`;
  `tests/test_native_structured_output.py:555`, `:603`, `:1283-1285`, `:1306`,
  `:1340`). `origin/main` versions of the two pre-existing files: the same 10
  (`scripts/api_anthropic.py:380`, `:1274`, `:1287`;
  `tests/test_native_structured_output.py:549`, `:597`, `:1277-1279`, `:1300`,
  `:1334`), shifted by inserted lines. The two new files report none.

## Pre-Existing Diagnostics

The flake8 F401 and E501 and the 10 mypy errors above, all on lines this
branch does not change.
