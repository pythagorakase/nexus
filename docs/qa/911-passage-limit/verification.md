# STOP-REPORT: Historical Passage Render Limit

Work order 911-cap, branch `claude/911-passage-limit`, base `c341d7d4`.
Implementation and focused proofs are present, but the required frontier before/after proof is incomplete. No PR was opened or pushed. No gateway or paid provider was started, and no fleet/template migration was applied.

## Stop Reasons

Repository-wide Black is not clean. `black --check .` reports **89 files would be reformatted, 577 files would be left unchanged**. All six Python files changed for this order pass Black individually. The failing files are outside the change; their exact paths are in [black.log](black.log). Reformatting them would expand the frozen scope, so the work-order escape hatch is invoked.

The frontier replay independently reached a routing rejection:

```text
ValueError: Invalid database name: 'qa640_911_5c28149eb243'. Must be one of: save_01, save_02, save_03, save_04, save_05
```

`LogonUtility._fetch_setting_context` uses the slot pool, whose allowlist rejects the disposable clone (`nexus/api/slot_utils.py:116`). The unfinished probe script preserves the attempted real TEST rendering path; it does not bypass validation or report success. No before/after token counts or chunk-25 rendered-presence result were obtained. The clone was dropped in `finally`; catalog verification returned zero `qa640_911_%` databases.

## Implemented Changes

- `nexus.toml`: add `lore.render_limits.historical_passages = 15`.
- `nexus/config/settings_models.py:969`: type the setting with default 15 and `ge=1`.
- `nexus/agents/lore/logon_utility.py:2662`: replace five with the typed cap; passage formatting is unchanged.
- `nexus/agents/lore/utils/turn_cycle.py:1285`: replace a second five-entry coverage slice with the actual surviving writer sources. Existing subtractive, tail-first trimming is unchanged.
- `tests/test_lore/test_historical_render.py`: prove both seat caps, validation, ranked trimming, and subtractive-versus-rerender token equality.
- `tests/test_lore/test_window_coverage_pg.py:116`: prove real PostgreSQL coverage matches the rendered prefix at caps 5 and 15 and under budget trimming, including token totals and callback idempotence.
- `scripts/qa_shift/historical_passage_limit.py`: unfinished clone/replay proof, preserved for coordinator continuation.
- `docs/qa/911-passage-limit/`: stop report and exact terminal logs.

## Verification Commands and Verbatim Tails

All commands ran at the worktree root with:

```sh
PY=/Users/pythagor/nexus/.venv/bin/python
```

Import proof:

```sh
PYTHONPATH=$PWD $PY -c 'import nexus,sys;print(nexus.__file__)'
```

```text
/Users/pythagor/nexus/.claude/worktrees/911-passage-limit/nexus/__init__.py
```

Offline suite (collected before the new test files were finished; the later targeted gate includes them):

```sh
PYTHONPATH=$PWD $PY -m pytest -q > docs/qa/911-passage-limit/offline.log 2>&1
```

```text
2664 passed, 854 skipped, 9 warnings in 104.00s (0:01:43)
```

Focused offline tests:

```sh
PYTHONPATH=$PWD $PY -m pytest -q tests/test_lore/test_historical_render.py > docs/qa/911-passage-limit/focused.log 2>&1
```

```text
8 passed, 5 warnings in 0.76s
```

An initial run of this command reported `1 failed, 7 passed, 5 warnings in 0.78s`: the synthetic passages were too large to retain more than five. Their size was reduced from 5,000 to 2,500 repeats, preserving budget pressure and testing the beyond-five case.

Required PostgreSQL gate, latest run:

```sh
NEXUS_RUN_POSTGRES=1 /Users/pythagor/nexus/.venv/bin/python -m pytest -q tests/test_lore -k 'render or window or coverage or historical' > docs/qa/911-passage-limit/postgres.log 2>&1
```

```text
=========================== short test summary info ============================
FAILED tests/test_lore/test_retrieval_coverage_live.py::test_handle_user_input_writes_exact_coverage_and_empty_detection
1 failed, 58 passed, 254 deselected, 9 warnings in 15.52s
```

The sole remaining failure is the expressly exempt #885 empty-slot-5 case: `tests/test_lore/test_retrieval_coverage_live.py:17` sets `LIVE_SLOT = 5`; its insert fails with `need-clock anchor unavailable: no canonical world time or base_timestamp`. PostgreSQL tests actually ran, including all three new coverage cases. No skips in this targeted run. Earlier runs produced `1 failed, 55 passed, 254 deselected, 9 warnings in 11.72s`, then `4 failed, 55 passed, 254 deselected, 9 warnings in 14.32s`; the additional failures were the new fixture lacking canonical player setup and were corrected with the existing `seed_protagonist` helper.

Repository-wide formatting:

```sh
PYTHONPATH=$PWD $PY -m black --check . > docs/qa/911-passage-limit/black.log 2>&1
```

```text
Oh no! 💥 💔 💥
89 files would be reformatted, 577 files would be left unchanged.
```

Changed Python files:

```sh
PYTHONPATH=$PWD $PY -m black --check nexus/config/settings_models.py nexus/agents/lore/logon_utility.py nexus/agents/lore/utils/turn_cycle.py tests/test_lore/test_historical_render.py tests/test_lore/test_window_coverage_pg.py scripts/qa_shift/historical_passage_limit.py > docs/qa/911-passage-limit/black-changed.log 2>&1
```

```text
All done! ✨ 🍰 ✨
6 files would be left unchanged.
```

Formatting commands during implementation:

```sh
PYTHONPATH=$PWD $PY -m black tests/test_lore/test_historical_render.py tests/test_lore/test_window_coverage_pg.py nexus/agents/lore/utils/turn_cycle.py nexus/agents/lore/logon_utility.py nexus/config/settings_models.py
```

```text
All done! ✨ 🍰 ✨
1 file reformatted, 4 files left unchanged.
```

```sh
PYTHONPATH=$PWD $PY -m black scripts/qa_shift/historical_passage_limit.py
```

```text
All done! ✨ 🍰 ✨
1 file reformatted.
```

```sh
PYTHONPATH=$PWD $PY -m black scripts/qa_shift/historical_passage_limit.py tests/test_lore/test_window_coverage_pg.py
```

```text
All done! ✨ 🍰 ✨
2 files reformatted.
```

Frontier probe:

```sh
PYTHONPATH=$PWD $PY scripts/qa_shift/historical_passage_limit.py > docs/qa/911-passage-limit/probe.log 2>&1
```

```text
ValueError: Invalid database name: 'qa640_911_5c28149eb243'. Must be one of: save_01, save_02, save_03, save_04, save_05
```

An initial attempt stopped at a text equality assertion: chunk 49 in the archived assembly appends the 1A player input, whereas the source retains its earlier pending choice. The final attempt verifies its storyteller prefix plus archived input separately; every other retrieved passage matches the clone's `raw_text` exactly, including chunk 25 at rank 14. It then fails at provider initialization as above. Both attempts cleaned up their clones. This is source verification, not rendered-prompt proof.

`git diff --check` passed with no output. No UI/build commands were needed.

## SQL Evidence and Cleanup

Read-only source check:

```sql
SELECT current_database(), count(*), max(id) FROM narrative_chunks;
```

```text
 current_database | count | max
------------------+-------+-----
 save_04          |    46 |  49
(1 row)
```

The clone script uses read-only source connections/pg_dump, restores only its unique `qa640_911_*` clone, and performs no migrations. Clone/source frontier and all historical source text checks passed before the final routing rejection. No source write was performed by the probe.

Cleanup verification:

```sh
psql -X -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE 'qa640_911_%'"
```

```text
 datname
---------
(0 rows)
```

## Coordinator Questions

1. Does “Black clean” mean only changed files, allowing the 89 unrelated baseline formatting failures to remain?
2. For the frontier render proof, should the existing #909 process-local clone admission be reused, or should the setting be read directly from the clone for a renderer-only replay? The current script attempts the unmodified slot pool and is blocked by its allowlist. No ranking change or paid generation is necessary for the cap proof.

Remaining: finish the frontier TEST render and before/after counts, rerun the complete offline gate with final tests collected, then commit final proof, push, and open the PR. Do not merge.

Codex — GPT-6 Astra.
