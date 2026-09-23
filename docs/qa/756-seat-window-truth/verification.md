# Per-Seat Window Truth Verification

Work order #756 and the token-only instrument slice of #802. The review revision includes main through #902, #904, and #905 (final merge `eadc0c68`). No migration, UI change, gateway, fleet update, or accepted story write was needed. A temporary, owned llama-server used port 8016 for the `/props` check and was stopped.

## Arithmetic and Scope

The effective input ceiling is `min(owner input spend, documented max_input_tokens if present, effective context_window - seat max_output_tokens - outside-output reasoning reserve) - seat response_reserve_tokens`. When the provider documents only a total, `max_input_tokens` is absent. Local effective context is the supervisor command’s explicit `--ctx-size`, validated against the architectural window and checked against the running server’s `/props` on first use. Inside-output reasoning stays inside the output allowance. With the production Astra policy, 75,000 input spend minus 4,000 policy headroom gives 71,000 input tokens; the output allowance is 25,000. Explicit story windows above the model input maximum raise with both values.

Model limits and seat policy live outside the fingerprint projection. All 17 registry models load through Pydantic. Source URLs and retrieval dates accompany capability declarations in `nexus.toml`; where an input maximum is undocumented, the comments explicitly say that the seat allowance determines the input ceiling. Auxiliary seats retain their models. Sonnet's ID is `claude-sonnet-5`.

OpenAI counts include system/user message framing and the exact structured schema. Anthropic counting receives its output configuration or tool envelope. Other compatible models use the declared model-owner tokenizer and chat template; missing tokenizer support raises. Assembly counts each rendered block once with the declared local tokenizer and subtracts removed blocks. Only the final guard counts the complete request through the provider, once per attempt; async provider paths execute it through `asyncio.to_thread`. Anthropic uses its declared local approximation and configured safety margin for trimming. No non-Astra paid validation was authorized.

## Initial Real Frontier Before and After

A disposable clone of `save_04` retained frontier chunk 49 and its existing stamped baseline. The only clone model change was:

```sql
UPDATE global_variables SET model = NULL WHERE id = TRUE;
```

Gaia remained NULL and followed the configured Astra writer. No story window was changed.

The comparison applies the original committed Terra budget/trimmer (`c4457c70`) to the real frontier payload, then compares the revised path. Both retained payloads are rendered with the merged #900 renderer and counted with Astra, holding renderer and tokenizer constant. It is a controlled reproduction of the old pruning, not an archived paid Terra response. Old JSON measurement was 58,081 tokens against a 31,982 target; it removed 21 warm blocks and 7 retrieval entries. Revised trimming removes none.

| Rendered Block | Old Trimming | Revised Trimming |
|---|---:|---:|
| system | 5,769 | 5,769 |
| intertitle | 49 | 49 |
| scene conditions | 16 | 16 |
| private storyteller correspondence | 5,665 | 5,665 |
| recent narrative | 1,002 | 15,409 |
| scene roster | 21 | 21 |
| user input | 24 | 24 |
| entity dossier | 1,762 | 1,762 |
| historical context | 4,579 | 4,579 |
| world knowledge | 249 | 249 |
| orrery tag library | 3,701 | 3,701 |
| recent orrery rulings | 204 | 204 |
| orrery imminent activity | 425 | 425 |
| orrery scene pressure | 224 | 224 |
| orrery joint beats | 189 | 189 |
| instructions | 28 | 28 |
| **Total** | **23,907** | **38,314** |

The system bucket includes transport framing and structured-schema overhead. Pass-2 material embedded in the warm slice accounts for the recovered recent-narrative tokens; the historical-context renderer's existing five-entry cap is unchanged. Restored narrative Pass-2 IDs include 2, 9, 11, and 21, alongside retained retrograde summaries. Exact inventories and trimming decisions are in `frontier-proof.json`.

## Three Paid Calls, No Retries

| Call | Seat | Model | Input | Output | Reasoning Included in Output |
|---|---|---|---:|---:|---:|
| 1 | Writer | gpt-6-astra | 38,993 | 1,464 | 122 |
| 2 | Gaia | gpt-6-astra | 41,673 | 945 | 149 |
| 3 | Writer | gpt-6-astra | 38,314 | 1,086 | 158 |

Calls 1–2 completed a full two-pass continuation before the #900 merge. They exposed omitted schema overhead in the draft counter; this was corrected. Their append-only historical measurements were not rewritten. Call 3 ran after the merge with the corrected counter and matched provider input usage exactly. All provider and validation retries were disabled for these proofs. No fourth call was made.

For call 3, a temporary validated QA configuration set **only** writer `response_reserve_tokens = 36686`, yielding a **38,314-token ceiling** for the unchanged normal-size frontier request. It was accepted at zero remaining headroom. Production headroom stays 4,000. This exercises a real boundary without padding or an overflow probe; it does not claim to fill the provider's million-token architectural window or the production 71,000-token ceiling. The post-merge Gaia paid call was not repeated because the three-call allowance was exhausted.

## Coverage and Ledger

The writer's final guard passed before the pending coverage row was written. The successful attempt is `63d2a2c0-a9ca-4f61-b0b9-7ab0c37f37e5`, seat `skald_writer`, attempt 1. The row has raw result count 14, kept chunk IDs `[47, 49, 9, 2, 21, 11, 34]`, and kept passage-text count 7,241. Kessa Brin (character 18) is covered by chunks 47 and 49, with no gaps. Passage-text coverage counts exclude prompt framing; the ledger records complete rendered block counts.

```sql
SELECT turn_id, raw_result_count, kept_chunk_ids, kept_tokens, coverage, gap_entities
FROM retrieval_coverage_log
WHERE turn_id = '63d2a2c0-a9ca-4f61-b0b9-7ab0c37f37e5';
```

The PostgreSQL regression uses the real MEMNON/database path and checks deferred writing, trimmed IDs, recomputed uncovered entities, token counts, and a single append. The ledger regression checks separate attempts and CLI block output. `usage-cli.txt` is the actual per-run CLI output, and `frontier-proof.json` contains the complete attempt record and provider usage.

## Fingerprint Proof

```sql
SELECT chunk_id, payload->>'config_fingerprint' AS config_fingerprint
FROM lore_pass_baselines WHERE chunk_id = 49;
```

Stored and current fingerprints both equal:

```text
434647cf417a9365a6e3af0e762d317915099deea8ea38cd4abb891ecbf36eca
```

The real LORE restore printed `FINGERPRINT_RESTORE_PASSED` before the frontier phases and calls. The temporary seat-policy change also retained the same fingerprint. The projection and the fleet's stamps were not changed.

## Validation

All Python commands ran from this worktree using:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/756-seat-window-truth/nexus/__init__.py
```

Final gate tails are appended below. No PostgreSQL skips are being counted as a pass. The four failures on the requested PostgreSQL gate are the same empty-slot-5 cases reproduced before implementation and exempted by #885. No other PostgreSQL failure remains.

## Coordinator Notes

No migration or re-stamp is needed. The three-call allowance is exhausted. Non-Astra routes were not paid-probed; their documented capabilities and request construction are covered separately from the live Astra proof. Local input limits use the configured serving window minus the seat output allowance; no architectural half-window is treated as an input maximum. The owner can review these declarations in `nexus.toml`.

### Initial Commands and Verbatim Tails

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2628 passed, 769 skipped, 11 warnings in 91.66s (0:01:31)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_lore tests/test_api -k 'budget or window or guard or coverage or fingerprint or usage'
```

```text
=========================== short test summary info ============================
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling
4 failed, 131 passed, 484 deselected, 13 warnings in 11.17s
```

```sh
git diff --name-only -z origin/main -- '*.py' | xargs -0 "$PY" -m black --check
```

```text
All done! ✨ 🍰 ✨
29 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY scripts/check_model_drift.py
```

```text
OK: no model-ID drift detected.
```

The four listed PostgreSQL failures all hardwire the owner's empty slot 5. The separate disposable coverage regression runs and passes; no failures are hidden with deselection beyond the work order's requested filter.

The config validation also printed:

```text
VALIDATED_MODELS 17
FINGERPRINT 434647cf417a9365a6e3af0e762d317915099deea8ea38cd4abb891ecbf36eca
```

The free (non-generation) tokenizer probes ran as `PYTHONPATH=$PWD $PY temp/756-proof/counter_probes.py` and printed:

```text
ANTHROPIC_NATIVE_REQUEST_TOKENS 3612
LOCAL_FRAMED_REQUEST_TOKENS 21
```

The prior-code coverage reproduction ran as `PYTHONPATH=$PWD $PY temp/756-proof/coverage_regression.py` against the disposable clone:

```text
BEFORE COVERAGE_ROWS_BEFORE_RENDER 1
AFTER COVERAGE_ROWS_BEFORE_RENDER 0
```

Reproduction scripts and complete logs remain under the worktree's ignored `temp/756-proof/`. Database and generation scripts used `PYTHONPATH=$PWD $PY temp/756-proof/<script>.py`. The real frontier scripts were `frontier_preflight.py`, `live_turn.py` (two paid calls), `ceiling_call.py` (one paid call), and `before_after.py` (counting only). No service was started on any gateway port.


## Review Findings and Corrections

The five coordinator findings on frozen commit `7e56e484` are addressed in `da01eec3`, with literal system-token attribution and per-appearance subtraction tightened in `0d6b8b9e`. Main was first merged through #904/#905. When #902 landed during validation, it was fetched and merged too; provider/configuration changes merged automatically, and the reachability baseline’s descriptive reason was combined while retaining both production-path sets. The in-flight test run during that merge was discarded; the final gates below ran from the completed merge.

- Local serving capacity comes from the same `runtime.services.llama_server.command` that the supervisor and interactive local manager use. At 32,768 total, the 25,000 writer allowance and 4,000 response headroom leave **3,768 input tokens**, not 28,000. Load-time validation rejects a serving context above the selected model architecture. The first-use verifier reads `default_generation_settings.n_ctx` and raises on missing or mismatched capacity.
- Shared context is rendered for both seats, including their different system/schema costs, roster/ambient visibility, and Gaia’s finished-output headings. A removal subtracts its cached cost from each seat. The binding target is the smaller seat constraint, with **25,000 tokens reserved for the writer response in Gaia’s input**. An untrimmable Gaia core fails in the writer’s final guard before generation.
- Block counts use `o200k_base` for the registered OpenAI IDs, the declared Hugging Face tokenizer for local/OpenRouter, and the explicitly configured local approximation plus 4,096-token margin for Anthropic. No provider count occurs during assembly, trimming, or coverage. Exactly one full count per attempt remains in the guard. The exact count includes the structured request schema; the system bucket counts the literal system text, while `request framing` is the exact residual for provider schema serialization, message framing, and tokenizer joins. The assembly schema estimate is not reported as measured system text.
- All inferred input maxima were removed. Both total-only and documented-input forms validate; documented overlaps still require the explicit provider flag. The six OpenRouter entries can now admit the normal 75,000 story spend before headroom. Auxiliary seat assignments are unchanged.
- Coverage uses the retained rendered chunk costs from assembly, without counting passages again. Kept-token totals include rendered labels/separators and repeated appearances of an identity; kept IDs remain unique. The disposable PostgreSQL regression passed both before and after this change.

### Live Local Capacity Check

The real installed llama-server (build 9960) loaded the registered Hermes GGUF on **8016** with `--ctx-size 32768 --parallel 1 -ngl 0 --no-warmup`. No generation was requested. The owned process was terminated in `finally` and port 8016 was confirmed clear.

```sh
PYTHONPATH=$PWD $PY temp/756-proof/local_window_probe.py
```

```text
LOCAL_CONFIGURED_32768_REPORTED 32768
LOCAL_MISMATCH_REJECTED llama-server reports n_ctx=32768; configured serving context_window=98304
OWNED_LOCAL_SERVER_STOPPED 0
```

The reported field is documented in [llama-server’s `/props` response](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#get-props-get-server-properties).

### Two-Seat Frontier Boundary

The original `save_04` dump was restored into a fresh `qa640_756_window_truth`. Only that clone received the authorized SQL:

```sql
UPDATE global_variables SET model = NULL WHERE id = TRUE;
```

A real frontier assembly repeated all seven pre-generation phases, including retrieval, on chunk 49. Its existing fingerprint restored unchanged:

```text
FINGERPRINT_RESTORE_PASSED 49 434647cf417a9365a6e3af0e762d317915099deea8ea38cd4abb891ecbf36eca
```

Production policy retains every chunk: writer local estimate 38,984/71,000, Gaia base 41,868 with a 46,000 shared-context target and 25,000 reserved writer tokens. To place this unchanged frontier at the **shared assembly boundary**, the proof increases only Gaia response headroom from 4,000 to 8,132: Gaia base 41,868 plus reserved 25,000 equals its tightened 66,868 ceiling. The writer’s corresponding shared target is 38,984. The test then renders a valid writer wire whose serialized output is exactly **25,000 tokens** and runs each real provider guard through `asyncio.to_thread`. These are **render-only proofs**, not a fourth paid call or a shipped story turn. The prior exact writer-side paid boundary proof remains above.

The exact full requests pass: writer **38,314 / 71,000**, Gaia **64,900 / 66,868**. The remaining difference from the shared local estimate reflects the conservative schema estimate and compact rendering of the writer’s JSON. The offline boundary regression also fills the shared target using the real renderer and tests the maximal writer response. The provider API is retained for the full guard because [OpenAI documents local-tokenizer limitations for complete requests](https://developers.openai.com/api/docs/guides/token-counting).

| Rendered Block | Writer | Gaia With Maximal Writer Response |
|---|---:|---:|
| system | 4,580 | 1,900 |
| intertitle | 50 | 50 |
| scene conditions | 17 | 17 |
| private storyteller correspondence | 5,667 | 5,667 |
| recent narrative | 15,431 | 15,431 |
| scene roster | 22 | 0 |
| user input | 24 | 24 |
| entity dossier | 1,795 | 1,795 |
| historical context | 4,583 | 4,583 |
| world knowledge | 252 | 252 |
| orrery tag library | 3,702 | 3,702 |
| recent orrery rulings | 210 | 210 |
| orrery imminent activity | 431 | 431 |
| orrery scene pressure | 229 | 229 |
| orrery joint beats | 191 | 191 |
| instructions | 30 | 30 |
| request framing | 1,100 | 5,317 |
| finished writer output | 0 | 25,071 |
| **Exact Total** | **38,314** | **64,900** |

`review-proof.json` contains the complete append-only records, both seat constraints, and coverage. The proof made **two counting requests, one per attempt**, and **zero generation calls**. The three paid calls documented above remain the entire authorization’s usage.

The post-render coverage row retains IDs `[47, 49, 9, 2, 21, 11, 34]`, raw count 14, rendered kept-token contribution 10,262, Kessa covered by chunks 47/49, and no gap entities. This contribution includes repeated rendered appearances, unlike the earlier unique passage-text count of 7,241.

```sql
SELECT turn_id, kept_chunk_ids, kept_tokens, raw_result_count, coverage, gap_entities
FROM retrieval_coverage_log
WHERE turn_id = '1b54dd23-a901-4120-975f-1b6e80a6ab23';
```

### Counting Overhead on the Same Frontier

The frozen `final-frontier.json` payload, clone, renderer, and model were held constant. Timings exclude provider initialization and generation; the table reports one observation per version, not a latency distribution. The before version budgets the writer only; the revision budgets both seats.

| Work | Before | After |
|---|---:|---:|
| Budget assembly | 0.606 s | 0.531 s |
| Rendered block breakdown | 5.377 s | 0.317 s |
| Combined | 5.983 s | 0.848 s |
| Remote counting requests | 18 | 0 |

Commands: `PYTHONPATH=$PWD $PY temp/756-proof/review_before.py` and `PYTHONPATH=$PWD $PY temp/756-proof/review_after.py`. The final-attempt guard is measured separately in the two-seat proof; its one full count is not included in the zero above. Raw measurements are retained in the worktree’s ignored `temp/756-proof/review-before.json` and `review-after.json`.

### Review Gate Commands and Verbatim Tails

All commands use the shared `$PY` defined above from this worktree, with `PYTHONPATH=$PWD`. No Poetry installation, UI build, fleet migration, or other worktree mutation was performed. Gate tails follow after the final main merge.

```sh
PYTHONPATH=$PWD $PY -m pytest -q
```

```text
2638 passed, 800 skipped, 9 warnings in 96.28s (0:01:36)
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_lore tests/test_api -k 'budget or window or guard or coverage or fingerprint or usage'
```

```text
=========================== short test summary info ============================
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_report_is_internally_consistent[5]
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_data_quality_matches_sql_oracle
FAILED tests/test_api/test_orrery_dev_endpoints.py::test_coverage_anchor_cap_and_sampling
4 failed, 138 passed, 503 deselected, 11 warnings in 11.79s
```

```sh
NEXUS_RUN_POSTGRES=1 PYTHONPATH=$PWD $PY -m pytest -q tests/test_lore/test_window_coverage_pg.py::test_window_coverage_is_written_only_from_post_render_kept_chunks
```

```text
1 passed, 5 warnings in 5.46s
```

```sh
git diff --diff-filter=ACM --name-only -z origin/main -- '*.py' | xargs -0 /Users/pythagor/nexus/.venv/bin/python -m black --check
```

```text
All done! ✨ 🍰 ✨
30 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD $PY scripts/check_model_drift.py
```

```text
OK: no model-ID drift detected.
```

```sh
PYTHONPATH=$PWD $PY -c 'from nexus.config import load_settings; s=load_settings(); print("VALIDATED_MODELS", sum(len(p.models) for p in s.global_.model.api_models.values()))'
```

```text
VALIDATED_MODELS 17
```

The PostgreSQL failures are the same four owner-slot-5 cases exempted by #885. The direct coverage regression passed before the last merge and also ran inside the final PostgreSQL gate. No new failure remains. Pre-commit hooks passed on both fix commits and the merge.

Additional focused checks: `PYTHONPATH=$PWD $PY -m pytest -q tests/test_lore/test_seat_window.py tests/test_lore/test_turn_cycle.py` printed `35 passed, 5 warnings in 1.07s`; the Orrery fixture/reachability subset printed `75 passed, 5 warnings in 9.01s` after updating its adapter and production path registration.

```sh
PYTHONPATH=$PWD $PY temp/756-proof/review_frontier.py
```

Selected proof output after the final main merge:

```text
FINAL_GUARD_PASSED skald_writer
FINAL_GUARD_PASSED gaia
EXACT_COUNTING_REQUESTS 2
MAXIMAL_WRITER_OUTPUT_TOKENS 25000
skald_writer 38314 71000 32686
gaia 64900 66868 1968
```

```sh
PYTHONPATH=$PWD $PY -m nexus.cli usage --run 756-review-render-3786a0b0-fed4-4768-bc45-0bd85ef492d1
```

The complete tabular output is committed in `review-usage-cli.txt`. The clone was dropped after evidence extraction; the owned local server was already stopped, and port 8016 is clear. No open coordinator question remains. No fourth paid call, migration, or re-stamp was performed.
