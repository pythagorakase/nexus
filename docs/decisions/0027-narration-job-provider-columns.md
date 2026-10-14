---
status: canonical
sources:
  - config/schema_docs_baseline.json
  - migrations/023_orrery_schema.py
  - docs/dead_retrieval_subtraction.md
  - nexus/agents/orrery/worker.py
verified_commit: "f073b3711a3bd0273943c9defad85913452fd00b"
---

# 0027: Narration Job Provider Columns

**Kind:** parked
**Links:** #819, #813

## Ruling

Parked. These objects stay uncommented and listed in config/schema_docs_baseline.json.

Source: https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416.

> - Decision: The routing of the 29 baseline entries without evidence goes into #813's manifest (`docs/dead_retrieval_subtraction.md`), and each baseline reason points at it.

Source: config/schema_docs_baseline.json at d70a1991210ce16aef5d6f9b57b0ec563ee1d164.

> column:public.orrery_narration_jobs.model_ref: Worker retains provider-era provenance but no current writer establishes the identifier format or authoritative use. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".
> column:public.orrery_narration_jobs.provider: Worker retains provider-era provenance but no current writer establishes the identifier format or authoritative use. Routed as #813 debt: docs/dead_retrieval_subtraction.md, section "Legacy Columns Without Evidence".

## Rejected Alternatives

- A comment without reader or writer evidence.

Source: https://github.com/pythagorakase/nexus/issues/819.

> Ambiguous semantics must route to the decision ledger rather than receiving invented documentation.

## Reopening Criteria

- A reader or writer that establishes the contract, or a migration that drops the object.
