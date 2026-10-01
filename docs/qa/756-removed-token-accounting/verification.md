# STOP-REPORT: 756-S1 Operator Proof Source Drift

Date: 2026-10-01. Tested baseline: `67256d15e2c5cf395c4336bb63f4a42472493db0`,
identical to freshly fetched `origin/main`. Branch: `claude/756-removed-token-accounting`.
No PR opened; implementation and proof gates are incomplete.

## Binding Stop Condition

The frozen order's operator proof says: “Source drift fails loudly and is reported
rather than repaired in this slice.” The required archived payload is incompatible
with the current renderer. The same operator command fails on untouched baseline
code, before trimming or the new accounting runs. No fixture rewrite or renderer
fallback was attempted.

## Evidence and Diagnosis

- Worktree import check: `PYTHONPATH=$PWD /Users/pythagor/nexus/.venv/bin/python -c
  'import nexus,sys;print(nexus.__file__)'` printed
  `/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/__init__.py`.
- `git fetch origin` then `git rebase origin/main` reported
  `Current branch claude/756-removed-token-accounting is up to date.`
- `scripts/qa_shift/historical_passage_limit.py:112-115` loads the archived payload
  and restores Decimal valences only; line 158 passes it to the real renderer.
- `docs/qa/909-long-absence-probe/live/79b4e65e-39ab-4e90-a28d-86756688ac02-skald_writer-prompt.json:1044`
  begins the archived relationship data. All ten rows have `character1_id` and
  `character2_id`, but neither `character1_name` nor `character2_name`. Direct JSON
  inspection confirmed this for every row.
- Baseline `nexus/agents/lore/logon_utility.py:2788-2789` indexes both name fields.
  The first missing key raises `KeyError: 'character1_name'`. This block was never
  changed by the partial implementation.
- The script passed its source/clone frontier and passage-text assertions
  (`historical_passage_limit.py:110-136`) before reaching line 158. The before and
  after read-only source query `SELECT count(*), max(id) FROM narrative_chunks`
  both returned `[(46, 49)]`. This is archived payload schema drift, not frontier drift.
- Failure occurs during local rendering, before generation; no provider request
  was made. The TEST route was constructed with the existing endpoint, as the log
  shows; no service was started or stopped.

## Work Disposition

An initial accounting implementation touched eight production/operator files.
The first operator attempt exposed a new circular import, which was corrected
by importing `TRIMMABLE_BLOCKS` inside the accounting property. The next attempt
exposed the archived-payload failure above. All eight source edits were then
saved to `scratchpad/756-S1/incomplete-accounting.patch` and restored to HEAD.
The third operator attempt reproduced the failure on unmodified baseline code.
The patch is incomplete and unvalidated; it is not a deliverable implementation.

Only this report remains changed. No accounting tests or static checks were run;
no pytest gate is claimed, no manifest/replay/usage behavior is claimed, and the
legacy usage ledger was not read or changed. No policy decisions were changed.

## Exact Operator Commands and Verbatim Output

All commands ran from the assigned worktree. Each used the same bounded runner
(the order scratch directory's `run.py`), with a 570-second deadline and a
115-second silence bound. All exited naturally with status 1. The runner adds
`EXIT 1` after each captured log.

### operator

```sh
/Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S1/run.py operator env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_TEST_PROVIDER_ONLY=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/historical_passage_limit.py
```

```text
Traceback (most recent call last):
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/scripts/qa_shift/historical_passage_limit.py", line 21, in <module>
    from nexus.agents.lore.logon_utility import LogonUtility
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/agents/lore/logon_utility.py", line 54, in <module>
    from nexus.agents.lore.seat_blocks import (
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/agents/lore/seat_blocks.py", line 6, in <module>
    from nexus.telemetry.prompt_window import RenderedSections
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/telemetry/prompt_window.py", line 14, in <module>
    from nexus.agents.lore.seat_blocks import TRIMMABLE_BLOCKS
ImportError: cannot import name 'TRIMMABLE_BLOCKS' from partially initialized module 'nexus.agents.lore.seat_blocks' (most likely due to a circular import) (/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/agents/lore/seat_blocks.py)
EXIT 1
```

### operator-2

```sh
/Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S1/run.py operator-2 env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_TEST_PROVIDER_ONLY=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/historical_passage_limit.py
```

```text
INFO Model TEST: routing to base_url http://127.0.0.1:5102/v1
INFO Created connection pool for database: qa640_911_9b9d0087149b
INFO Loaded setting context (5249 chars)
INFO Using standard model: TEST with temperature: 0.7
INFO LOGON initialized with test provider using model TEST
INFO System prompt loaded: 20315 chars
INFO Closed connection pool for database: qa640_911_9b9d0087149b
Traceback (most recent call last):
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/scripts/qa_shift/historical_passage_limit.py", line 224, in <module>
    main()
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/scripts/qa_shift/historical_passage_limit.py", line 158, in main
    before = utility.measure_turn_requests(context.context_payload, 75000)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/agents/lore/logon_utility.py", line 1779, in measure_turn_requests
    prompt = self._format_context_prompt(
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/agents/lore/logon_utility.py", line 2796, in _format_context_prompt
    char1 = rel["character1_name"]
            ~~~^^^^^^^^^^^^^^^^^^^
KeyError: 'character1_name'
EXIT 1
```

### operator-baseline

```sh
/Users/pythagor/nexus/.venv/bin/python /private/tmp/claude-501/-Users-pythagor-nexus/ac1789b0-937f-4798-8d8b-474a4e63c2ae/scratchpad/756-S1/run.py operator-baseline env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT -u NEXUS_RUN_LIVE_LLM NEXUS_TEST_PROVIDER_ONLY=1 PYTHONPATH=/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting /Users/pythagor/nexus/.venv/bin/python scripts/qa_shift/historical_passage_limit.py
```

```text
INFO Model TEST: routing to base_url http://127.0.0.1:5102/v1
INFO Created connection pool for database: qa640_911_9f602b4e70b6
INFO Loaded setting context (5249 chars)
INFO Using standard model: TEST with temperature: 0.7
INFO LOGON initialized with test provider using model TEST
INFO System prompt loaded: 20315 chars
INFO Closed connection pool for database: qa640_911_9f602b4e70b6
Traceback (most recent call last):
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/scripts/qa_shift/historical_passage_limit.py", line 219, in <module>
    main()
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/scripts/qa_shift/historical_passage_limit.py", line 158, in main
    before = utility.measure_turn_requests(context.context_payload, 75000)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/agents/lore/logon_utility.py", line 1779, in measure_turn_requests
    prompt = self._format_context_prompt(
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/pythagor/nexus/.claude/worktrees/756-removed-token-accounting/nexus/agents/lore/logon_utility.py", line 2788, in _format_context_prompt
    char1 = rel["character1_name"]
            ~~~^^^^^^^^^^^^^^^^^^^
KeyError: 'character1_name'
EXIT 1
```

## Cleanup Verification

The script's `finally` block (`historical_passage_limit.py:203-212`) closed its
pool, dropped the clone, and removed the dump. Independently verified with a
read-only admin connection:

```sql
SELECT datname FROM pg_database
WHERE datname = ANY(ARRAY['qa640_911_9b9d0087149b', 'qa640_911_9f602b4e70b6']);
```

```text
Remaining proof clones: []
Temporary dump exists: False
Source frontier after: [(46, 49)]
```

`docs/qa/911-passage-limit/frontier.dump` does not exist. The existing evidence
JSON and prompts were not rewritten: failure preceded their write sites. No
owner database was written; source reads and pg_dump used explicitly read-only
connections. No migration was applied outside the disposable lifecycle (the
operator itself runs none).

## Open Question for the Coordinator

Please provide a corrected archived operator input or revise the frozen order
to authorize an explicit relationship-name restoration from the disposable clone.
Should 756-S1 resume with that corrected proof input? No new owner policy question
is introduced; Q2, Q3 and Q6 remain decided, and reinvested/banked accounting
remains deferred to 756-S3b.

Prepared by Codex, running GPT-6.
