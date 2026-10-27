---
status: canonical
sources:
  - nexus/api/lore_adapter.py
  - nexus/agents/logon/apex_schema.py
verified_commit: "c7ae2988d07b443f627a04d3a4eed1816b1cd438"
---

# 0068: Incubator Column Comments

**Kind:** decision
**Links:** #1106, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/1106#issuecomment-6423079194.

> - **1106-D1.** Should migration 152 fix only the two comments this issue names, or every incubator comment the current code proves false? Decision: Migration 152 corrects every incubator comment the code at c7ae2988 proves false or incomplete: metadata_updates, entity_updates, reference_updates, status, llm_response_id, authorial_directives, orrery_proposal, and the parent_chunk_id note that the bootstrap writes 0. It also corrects the function comment on public.clear_incubator(). Comments that are accurate stay as they are. Basis: A wrong comment weighs as much as wrong behavior (#819 slice D). It is the same table and the same register, and the evidence was read in the map and the critique. Reversal cost: Another COMMENT ON in a later migration.
> - **1106-D2.** Should the slice add a PostgreSQL guard test that ties the JSON-column comments to the Pydantic model fields, or ship the comment migration alone? Decision: Add tests/test_incubator_column_comments_pg.py on a migrated disposable clone. Each JSON-column comment carries a parseable brace set of its top-level keys, in the form `keys: {a, b, c}`. The test parses that set and requires it to equal the owning Pydantic model's top-level field names (ChunkMetadataUpdate with ChronologyUpdate, StateUpdates, ReferencedEntities). It includes a red case with the pre-152 texts. Basis: Migration 136 shipped with its guard, which sets the precedent. The critique showed that free prose cannot be checked. Reversal cost: Delete one test file.
> - **1106-D3.** Which migration number does the fix take? Decision: Migration number 152. The builder re-checks open PRs and every branch before committing. Basis: 152 is the next free number at c7ae2988. Reversal cost: None after merge.
> - **1106-D4.** Should llm_response_id, which the storyteller path never fills, be fixed as behavior now, or only documented truthfully? Decision: Document only. The dead writer at nexus/api/lore_adapter.py:201 (a getattr on a `response_id` that no StoryTurnResponse member defines) is named with its file and line in the PR body's Deferred section. The coordinator files it as its own issue at landing. Basis: #1106 is a comment fix with no schema or behavior change. Reversal cost: A later writer change updates the comment in the same PR.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
