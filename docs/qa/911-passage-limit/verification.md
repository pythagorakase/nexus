# Historical Passage Render Limit

Work order 911-cap; branch `claude/911-passage-limit`. No schema changes.

## Before and After

The real TEST renderer replayed the recorded #909 turn-1A assembly against a disposable clone of save_04. Chunk 25 remains retrieval rank 14. Only the configured cap changes between runs; this measures rendering, not fresh retrieval or generation.

| Cap | Historical Tokens Before Trim | After Trim | Writer Input / Ceiling | Gaia Input / Trim Target | Chunk 25 Printed |
| --- | ---: | ---: | --- | --- | --- |
| 5 | 4,095 | 4,095 | 35,079 / 71,000 | 32,471 / 46,000 | No |
| 15 | 14,355 | 14,355 | 45,339 / 71,000 | 42,731 / 46,000 | Yes |

Neither run needed trimming. These are current-code replay counts, not the older #909 total. Budget-pressure tests separately prove lowest-ranked historical passages are removed first and PostgreSQL coverage records exactly the surviving rendered prefix and token count.

Evidence: [evidence.json](evidence.json), [five-passage historical block](cap-5-prompt.txt) and [15-passage historical block](cap-15-prompt.txt) (chunk 25 at line 851). The archived turn-1A input is recorded verbatim in the evidence JSON. The probe checks every historical passage against clone text; chunk 49 checks its storyteller prefix and archived player-input suffix separately. Archived relationship valences are restored from JSON strings to Decimal before rendering.

`SELECT count(*), max(id) FROM narrative_chunks` returned `(46, 49)` for save_04 before/after and for the clone. Source SQL and pg_dump are read-only. Process-local `slot_utils.VALID_DBNAMES` admission matches the authorized #909 method; production validation is unchanged. The clone pool closes before DROP DATABASE, the allowlist is restored, and the dump is removed. Final cleanup:

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'qa640_911_%';
```

```text
 datname
---------
(0 rows)
```

The first resumed probe exposed archived numeric strings and a retained pool connection; both were corrected in the operator script. Its leftover clone was explicitly dropped before the successful rerun. No gateway, paid call, fleet/template migration, or source-save write was performed by the probe.

## Implementation Evidence

- `nexus.toml:234` and `nexus/config/settings_models.py:969`: cap defaults to 15, typed with `ge=1`.
- `nexus/agents/lore/logon_utility.py:2662`: uses the cap without changing passage formatting.
- `nexus/agents/lore/utils/turn_cycle.py:1217`: existing tail-first subtractive trimming; line 1285 selects actual surviving writer sources for coverage.
- `tests/test_lore/test_historical_render.py`: both seats, caps, validation, ranked trimming, and rerender token equality.
- `tests/test_lore/test_window_coverage_pg.py:116`: real PostgreSQL assertions for caps 5/15, budget pressure, and callback idempotence.
- `scripts/qa_shift/historical_passage_limit.py:137`: clone-only renderer admission; lines 169–172 assert chunk 25 and budget ceilings.
- `config/reachability.toml`: registers the proof script as an operator.

## Validation

All commands ran from this worktree. Import proof:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/911-passage-limit/nexus/__init__.py
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m pytest -q > docs/qa/911-passage-limit/offline.log 2>&1
```

```text
2672 passed, 857 skipped, 9 warnings in 101.35s (0:01:41)
```

```sh
NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore -k 'render or window or coverage or historical' > docs/qa/911-passage-limit/postgres.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
1 failed, 58 passed, 254 deselected, 9 warnings in 15.26s
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black --check nexus/config/settings_models.py nexus/agents/lore/logon_utility.py nexus/agents/lore/utils/turn_cycle.py tests/test_lore/test_historical_render.py tests/test_lore/test_window_coverage_pg.py scripts/qa_shift/historical_passage_limit.py > docs/qa/911-passage-limit/black-changed.log 2>&1
```

```text
All done! ✨ 🍰 ✨
6 files would be left unchanged.
```

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/historical_passage_limit.py > docs/qa/911-passage-limit/probe.log 2>&1
```

```text
  ],
  "clone_dropped": true
}
```

The offline suite includes the final new tests. PostgreSQL ran with no skips; its sole failure is the explicitly exempt #885 empty-slot-5 test `test_handle_user_input_writes_exact_coverage_and_empty_detection`. It hardwires `LIVE_SLOT = 5` at `tests/test_lore/test_retrieval_coverage_live.py:17` and fails with `need-clock anchor unavailable: no canonical world time or base_timestamp` (recorded PostgreSQL run). All 58 other selected tests passed.

Formatting performed in this continuation:

```sh
PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -m black scripts/qa_shift/historical_passage_limit.py
```

```text
reformatted scripts/qa_shift/historical_passage_limit.py

All done! ✨ 🍰 ✨
1 file reformatted.
```

Black scope follows the coordinator amendment: changed Python files only. Raw logs were removed in the docs-only evidence cleanup; the recorded gate tails above are retained. No UI/build work was required.

## Evidence Artifact Scope

The two `cap-*-prompt.txt` files contain only their verbatim HISTORICAL CONTEXT blocks. Private correspondence, dossiers, and all other prompt sections are omitted. SHA-256 digests below identify the original full prompt file bytes before extraction, not the retained excerpts. `evidence.json` is unchanged. Raw `*.log` files were deleted; validation commands and tails above describe the earlier implementation run and were not rerun for this docs-only amendment.

| Original Full Prompt | SHA-256 |
| --- | --- |
| `cap-5-prompt.txt` | `fe53d052b4d44f51431d243bd2dd444df11acab6e5d6fa3770308d8fc9afdcb3` |
| `cap-15-prompt.txt` | `b4329197dae86f45a21a222085021b72f938c92afaa31167706f0c417c3a4a04` |

## Deferred Work and Coordinator Questions

The state-change salience prior remains deferred as ordered. No open questions. Do not merge this PR in the implementation run.

Codex — GPT-6 Astra.
