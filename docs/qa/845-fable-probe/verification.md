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
- `nexus/telemetry/usage.py:95-123` (`UsageEvent`) and `:647-686`
  (`record_anthropic_response`): the usage ledger and the attempt manifest
  record no `stop_reason` and no block types.
- On the shipped config a Fable slot already runs the flake's extractor:
  `turn_pipeline = "two_pass"` (`nexus.toml:1209`); the two-pass writer is
  forced to `native` (`nexus/agents/lore/logon_utility.py:1512-1515` sync,
  `:1619-1622` async; `output_config` at `:2459-2465`), and Gaia follows the
  slot model on `anthropic_storyteller_transport = "prompted"`
  (`nexus.toml:1208`; `_resolve_anthropic_two_pass_gaia_transport`,
  `:1347-1384`; the gaia follow in `resolve_seat`,
  `nexus/config/story_model.py:174-179`). The usage seats are `skald_writer`
  (`:1512`, `:1619`) and `gaia` (`:1553`, `:1662`).

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
  join, verdict, evidence writer, failed-turn envelope reading and lane
  refusal.
- Review fixes (`b3660b68`): the probe reads a failed turn's CLI `code` and
  `partial.session_id` from the stderr failure envelope (`turn_outcome`; the
  envelope's `error` is never kept), so `turns.jsonl` records them on the
  turn that ends the run; `summary.md` adds "Fable Calls Beyond CALL_CAP by
  Seat" (the seats of the Fable calls after the 30th, in ledger time order);
  the stop-reason sentinel check captures INFO and above on every logger.
- `AGENTS.md`, `docs/turn_flow_sequence.md`: `verified_commit` moved to the
  merge base `9a0714d7671457d47f91bfbd76749fee4444c686`; the repair paragraph
  (`docs/turn_flow_sequence.md:212-214`) still holds.

## Red Run (S1 Tests Against Unchanged Product Code)

Run at `b3660b68` on a scratch export of the branch (`git archive HEAD`, under
the session scratchpad's `845-S1S2/` subdirectory, since deleted) whose
`scripts/api_anthropic.py` was replaced by `git show
origin/main:scripts/api_anthropic.py` (`origin/main` at `9a0714d7`, the
pre-845 provider); the import check printed that export's `nexus` and
`scripts/api_anthropic.py`.

`PYTHONPATH=$PWD nice -n 15 $PY -m pytest -q -p no:cacheprovider tests/test_native_structured_output.py tests/test_fable_probe_parsing.py tests/test_owner_target_guard.py`

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
FAILED tests/test_fable_probe_parsing.py::test_parser_reads_the_provider_line
13 failed, 208 passed, 5 warnings in 7.10s
```

The assertion lines behind the failures (from the same log):

```
[thinking_only-native]
E         - JSON output; stop_reason=end_turn block_types=thinking output_tokens=812
E         + JSON output
[truncated-native]
>       assert not isinstance(exc, ValidationError)
E       assert not True
E        +  where True = isinstance(1 validation error for SkaldWriterWire\n  Invalid JSON: EOF while parsing a string at line 1 column 27 [type=json_inval...ive": "SENTINEL-845', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.11/v/json_invalid, ValidationError)
[truncated-prompted]
>       assert not isinstance(exc, ValidationError)
E       assert not True
E        +  where True = isinstance(1 validation error for SkaldWriterWire\n  Invalid JSON: EOF while parsing a string at line 1 column 27 [type=json_inval...ive": "SENTINEL-845', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.11/v/json_invalid, ValidationError)
[truncated-tool_envelope]
E         - Anthropic structured response stopped at the output-token limit before complete structured output; stop_reason=max_tokens block_types=thinking,text output_tokens=25000
E         + Anthropic tool-envelope response did not include the submit_structured_response tool_use block
[refusal-native] and [refusal-prompted]
E        +  where True = isinstance(1 validation error for SkaldWriterWire\n  Invalid JSON: expected value at line 1 column 1 [type=json_invalid, input_val...L-845 refusal prose', input_type=str]\n    For further information visit https://errors.pydantic.dev/2.11/v/json_invalid, ValidationError)
[test_parser_reads_the_provider_line]
E               RuntimeError: Unparseable rejection line: '2026-10-26 18:58:14,701 - nexus.metadata - WARNING - structured-output rejected transport=native model=claude-fable-5-1 seat=skald_writer attempt=1 exception=ValueError error=Anthropic structured response did not include JSON output'
```

The 208 passes include
`test_anthropic_accepts_valid_output_whatever_the_stop_reason` (passes before
and after) and the rest of the three files. `truncated-native`,
`truncated-prompted`, `refusal-native` and `refusal-prompted` fail as
`ValidationError` (`json_invalid`); the parser test fails because the pre-845
line has no diagnostics for the regex to read.

## Green Runs (After Merging `origin/main` at 9a0714d7)

The review fixes landed in `b3660b68`; the three-file run, the PostgreSQL
proof and the first offline suite below ran on that commit. The other tails
ran on `2aef4221` (the fixes touch only the three test files).

`nice -n 15 $PY -m pytest -q tests/test_native_structured_output.py tests/test_fable_probe_parsing.py tests/test_owner_target_guard.py` (at `b3660b68`)

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
221 passed, 5 warnings in 7.01s
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

PostgreSQL (`NEXUS_GATEWAY_PORT`, `NEXUS_API_URL`, `NEXUS_SLOT` unset), at
`b3660b68`, after the bounded load wait
(`until [ "$(sysctl -n vm.loadavg | awk '{print int($2)}')" -lt 24 ]; do sleep 30; done`,
capped): the wait started at a one-minute load of 24.81 and ended after 30
seconds at 22.72; the run started at 21.01.
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
6 passed, 1 skipped, 2 warnings in 22.84s
```

(Earlier runs of the same command: pre-merge at a load of 15.32, and post-merge
at `2aef4221` started at 31.36 without the bounded wait; both gave 6 passed, 1
skipped, owner targets none. The run above replaces them as the proof.)

Offline: `nice -n 15 $PY -m pytest -q tests --ignore=tests/test_api --ignore=tests/test_orrery`

At `b3660b68`:

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
FAILED tests/test_runtime/test_supervisor.py::test_check_children_still_fails_a_live_child_without_its_writer
1 failed, 3260 passed, 698 skipped, 8 warnings in 678.76s (0:11:18)
```

The failure (`tests/test_runtime/test_supervisor.py:1416`,
`Failed: DID NOT RAISE <class 'nexus.runtime.supervisor.RuntimeError_'>`) is in
a file this branch does not change (`git diff --stat origin/main...HEAD --
nexus/runtime tests/test_runtime` is empty); the run shared the machine with
other builders. The file alone, rerun once at `b3660b68` (load 8.23):

```
secret-store guard: active; nexus-api: denied; disposable keychain: denied
receipt isolation: checkout and user receipts untouched
73 passed, 5 warnings in 30.70s
```

At `2aef4221`:

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
