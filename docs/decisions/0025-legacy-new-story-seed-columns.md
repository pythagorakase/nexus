---
status: canonical
sources:
  - config/schema_docs_baseline.json
  - migrations/007_normalize_new_story_creator.sql
  - nexus/api/new_story_cache.py
  - docs/dead_retrieval_subtraction.md
verified_commit: "4ae8b8d21b2c4f7913d0ab7f8ebf63614dd096a8"
---

# 0025: Legacy New-Story Seed and Zone Columns

**Kind:** parked
**Links:** #819, #813

## Ruling

Parked. These objects stay uncommented and listed in config/schema_docs_baseline.json.

Source: https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416.

> - Decision: The routing of the 29 baseline entries without evidence goes into #813's manifest (`docs/dead_retrieval_subtraction.md`), and each baseline reason points at it.

Source: config/schema_docs_baseline.json at d70a1991210ce16aef5d6f9b57b0ec563ee1d164.

> column:assets.new_story_creator.seed_initial_mystery: Current cache writers clear this legacy field to NULL; no current reader consumes it, including the row-to-cache and selected-seed reconstruction paths. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".
> column:assets.new_story_creator.seed_potential_obstacles: Current cache writers clear this legacy field to NULL; no current reader consumes it, including the row-to-cache and selected-seed reconstruction paths. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".
> column:assets.new_story_creator.seed_starting_location: Current cache writers clear this legacy field to NULL; no current reader consumes it, including the row-to-cache and selected-seed reconstruction paths. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".
> column:assets.new_story_creator.zone_approximate_area: Current cache writers clear this legacy field to NULL; no current reader consumes it, including the row-to-cache and selected-seed reconstruction paths. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".
> column:assets.new_story_creator.zone_boundary_description: Current cache writers clear this legacy field to NULL; no current reader consumes it, including the row-to-cache and selected-seed reconstruction paths. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".

## Rejected Alternatives

- A comment without reader or writer evidence.

Source: https://github.com/pythagorakase/nexus/issues/819.

> Ambiguous semantics must route to the decision ledger rather than receiving invented documentation.

## Reopening Criteria

- A reader or writer that establishes the contract, or a migration that drops the object.
