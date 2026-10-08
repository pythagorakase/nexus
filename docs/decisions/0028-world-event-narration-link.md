---
status: canonical
sources:
  - config/schema_docs_baseline.json
  - migrations/023_orrery_schema.py
  - docs/dead_retrieval_subtraction.md
verified_commit: "b0da93eaedb4d1661af50742440e7988c7e48185"
---

# 0028: World Event Narration Link Column

**Kind:** parked
**Links:** #819, #813

## Ruling

Parked. These objects stay uncommented and listed in config/schema_docs_baseline.json.

Source: https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416.

> - Decision: The routing of the 29 baseline entries without evidence goes into #813's manifest (`docs/dead_retrieval_subtraction.md`), and each baseline reason points at it.

Source: config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185.

> column:public.world_events.narration_chunk_id: No current writer establishes this legacy narration link; do not infer the contract from the similarly named resolution column. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".

## Rejected Alternatives

- A comment without reader or writer evidence.

Source: https://github.com/pythagorakase/nexus/issues/819.

> Ambiguous semantics must route to the decision ledger rather than receiving invented documentation.

## Reopening Criteria

- A reader or writer that establishes the contract, or a migration that drops the object.
