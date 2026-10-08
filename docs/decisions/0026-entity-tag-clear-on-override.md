---
status: canonical
sources:
  - config/schema_docs_baseline.json
  - migrations/023_orrery_schema.py
  - docs/dead_retrieval_subtraction.md
verified_commit: "d70a1991210ce16aef5d6f9b57b0ec563ee1d164"
---

# 0026: Entity Tag Clear-on-Override Column

**Kind:** parked
**Links:** #819, #813

## Ruling

Parked. These objects stay uncommented and listed in config/schema_docs_baseline.json.

Source: https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416.

> - Decision: The routing of the 29 baseline entries without evidence goes into #813's manifest (`docs/dead_retrieval_subtraction.md`), and each baseline reason points at it.

Source: config/schema_docs_baseline.json at d70a1991210ce16aef5d6f9b57b0ec563ee1d164.

> column:public.entity_tags.clear_on_override: No current reader or writer establishes how this legacy override should interact with tags.clear_on. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".

## Rejected Alternatives

- A comment without reader or writer evidence.

Source: https://github.com/pythagorakase/nexus/issues/819.

> Ambiguous semantics must route to the decision ledger rather than receiving invented documentation.

## Reopening Criteria

- A reader or writer that establishes the contract, or a migration that drops the object.
