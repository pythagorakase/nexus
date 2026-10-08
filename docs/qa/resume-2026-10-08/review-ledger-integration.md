# Decision Ledger: Combined Source Review

Reviewed integration head: `f291dc792e4b071a4cc4940101f6c40871ea8b7b`
(`f291dc79`), at
`/Users/pythagor/.codex/worktrees/resume-claude-integration/nexus`.
Comparison base: `afd034f360e625f8bc4ffa8a717dda28422b19c7`.

This was source inspection only while the full gate ran at the reviewed head.
No tests, imports of application code, database operations, or branch edits were
performed for this review. This report does not assert a full-gate result.

## Result

No stale unquoted implementation or status assertion requires correction.
The following ten ledger records cite code or configuration changed by the
combined lanes:

| Record | Changed declared source |
|---|---|
| 0006: Who Owns the Choice | `nexus/api/slot_endpoints.py` |
| 0009: Dollars in the Ledger | `nexus.toml`, `nexus/cli.py` |
| 0010: The Gaia Seat | `nexus.toml` |
| 0022: Authorize Capabilities and Protect the Golden Master | `nexus/api/slot_endpoints.py` |
| 0024: Unify Narrative Memory Documents and Embeddings | `nexus.toml` |
| 0034: Conspiracy Channel | `nexus.toml` |
| 0040: Story Bundles | `scripts/new_story_setup.py` |
| 0041: Off-Screen Ledger | `nexus/agents/orrery/events.py` |
| 0042: Durable Intentions | `nexus/agents/orrery/substrate.py` |
| 0048: Region Genesis | `nexus/api/new_story_db_mapper.py` |

## Evidence

- The #822 slice adds durable story identity; record 0040 preserves the Build
  ruling and import-as-fork choice without claiming completed bundle import.
- The #840 slice supplies Natural Earth reference support, consistent with
  record 0048. The record does not claim that all region-genesis work is done.
- The #785 changes govern travel routability. They do not alter record 0041's
  strict actor-rank ruling or record 0042's configured foreground-intention
  ruling.
- The #822 slot endpoint change adds `legacy_story_id` to the response. It does
  not change the choice ownership or golden-master rulings in 0006 and 0022.
- The CLI/configuration changes introduce failure receipts, TEST-provider
  database configuration, travel calibration, and separated offline model
  candidates. They do not add dollar accounting or change the quoted seat and
  correspondence rulings in 0009, 0010, and 0034.
- The parked-object claims in 0025–0029 remain supported. `git diff afd034f3
  f291dc79 -- config/schema_docs_baseline.json
  docs/dead_retrieval_subtraction.md
  nexus/agents/memnon/utils/db_access.py
  nexus/agents/memnon/utils/embedding_tables.py` produced no changes. The
  baseline and deferred manifest still retain the legacy seed/zone columns,
  tag override column, narration-provider columns, narration link, and six
  vector-helper functions. The #810/#812 slices do not drop or document those
  objects.
- Record 0024's dated multi-model refutation is preserved quoted evidence.
  #812 now requires one runtime embedder and moves candidates into `ir_eval`,
  but does not unify the canonical source-specific memory stores. The live
  rejection of canonical storage unification remains valid; the quotation
  should not be rewritten as a current implementation description.

Preserve all verbatim owner quotations. Re-stamp freshness against the valid
landing base after reviewing the final sources when #817 lands last.

Codex — GPT-6
