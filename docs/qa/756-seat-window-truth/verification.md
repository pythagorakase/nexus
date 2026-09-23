# Per-Seat Window Truth Verification

Work order #756 and the token-only instrument slice of #802. The branch includes main through #900 and #901. No migration, UI change, gateway, fleet update, or accepted story write was needed.

## Arithmetic and Scope

The effective input ceiling is `min(owner input spend, model max_input_tokens, model context_window - seat max_output_tokens - outside-output reasoning reserve) - seat response_reserve_tokens`. Inside-output reasoning stays inside the output allowance. With the production Astra policy, 75,000 input spend minus 4,000 policy headroom gives 71,000 input tokens; the output allowance is 25,000. Explicit story windows above the model input maximum raise with both values.

Model limits and seat policy live outside the fingerprint projection. All 17 registry models load through Pydantic. Source URLs and retrieval dates accompany capability declarations in `nexus.toml`; where separate limits are undocumented, the comments identify conservative partitions. Auxiliary seats retain their models. Sonnet's ID is `claude-sonnet-5`.

OpenAI counts include system/user message framing and the exact structured schema. Anthropic counting receives its output configuration or tool envelope. Other compatible models use the declared model-owner tokenizer and chat template; missing tokenizer support raises. Provider counting APIs add request latency. No non-Astra paid validation was authorized.

## Real Frontier Before and After

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

No migration or re-stamp is needed. The three-call allowance is exhausted. Non-Astra routes were not paid-probed; their documented capabilities and request construction are covered separately from the live Astra proof. Local providers with only a documented total use an explicitly conservative partition. The owner can review these declarations in `nexus.toml`.

### Final Commands and Verbatim Tails

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
