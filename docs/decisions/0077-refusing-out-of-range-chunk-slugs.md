---
status: canonical
sources:
  - tests/pg_fixtures.py
  - tests/test_commit_handler_sync.py
  - tests/test_api/test_reader_feed_pg.py
  - nexus/api/commit_handler_sync.py
verified_commit: "b75f6241cf98aff251b100b776d50f3003c872cb"
---

# 0077: Refusing Out-of-Range Chunk Slugs

**Kind:** decision
**Links:** #1069, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/1069#issuecomment-6423099961.

> - **1069-D1.** Does a loud refusal land now as its own slice, or does the whole fix fold into 750-S1a? Decision: Land the loud refusal now as its own slice; the slug counter waits for 750-S1a. Basis: Map default. Reversal cost: None.
> - **1069-D2.** Can #1069 close after the refusal lands, or must it stay open until the counter ships in 750-S1a? Decision: #1069 closes after 1069-S1 lands and the coordinator posts the counter requirements (D5, D6) on #750 as acceptance criteria of 750-S1a. Basis: Map default. Reversal cost: Reopen.
> - **1069-D3.** Where does the refusal live: the trigger, the Python commit path, or both? Decision: The trigger set_chunk_slug() is the sole author of the slug and RAISEs on an out-of-range value. Shape (a): remove the slug parameter from insert_chunk_metadata_sync and every call site (the seven test call sites the critique lists, tests/pg_fixtures.py:709 and the fake cursor in tests/test_commit_handler_sync.py), so no Python code formats a slug. Basis: The trigger's COMMENT already says it owns the slug; least duplicated logic. Reversal cost: Restore the parameter.
> - **1069-D4.** Which values does the interim trigger refuse? Decision: The interim trigger refuses scene > 999, season > 99, episode > 99 and any negative value, with a message naming the column, the value and the bound. NULL handling is unchanged. Basis: Map default. Reversal cost: Widen in 750-S1a.
> - **1069-D5.** For 750-S1a, does the slug counter count per episode or across the whole slot? Decision: For 750-S1a: the slug counter counts the chunk ordinal within (season, episode). Basis: Map default. Reversal cost: Recorded on #750.
> - **1069-D6.** For 750-S1a, does the slug grow wider past 999 (and 99), or does it keep refusing? Decision: For 750-S1a: past the bound the slug grows (lpad minimum widths, widened column) so every existing slug stays byte-identical. Basis: Map default; no code sorts by slug. Reversal cost: Recorded on #750.
> - **1069-D7.** How do test fixtures that seed more than 999 chunks in one episode stay compatible with the refusal? Decision: Fixtures that seed more than 999 chunks in one episode (tests/test_api/test_reader_feed_pg.py seeds 1,200 through seed_committed_chunk; any fixture that sets scene = chunk_id) must stay inside the bound: the fixture advances the episode when the per-episode ordinal would pass 999, and the order names each affected fixture after the builder's grep. Basis: The refusal would otherwise fail the suite. Reversal cost: Test-only.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
