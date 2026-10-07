---
status: canonical
sources:
  - config/schema_docs_baseline.json
verified_commit: "b0da93eaedb4d1661af50742440e7988c7e48185"
---

# 0029: Legacy Vector-Helper Functions

**Kind:** parked
**Links:** #819, #813, #812

## Ruling

Parked. These objects stay uncommented and listed in config/schema_docs_baseline.json.

Source: https://github.com/pythagorakase/nexus/issues/819#issuecomment-5915950416.

> - Decision: The routing of the 29 baseline entries without evidence goes into #813's manifest (`docs/dead_retrieval_subtraction.md`), and each baseline reason points at it.

Source: config/schema_docs_baseline.json at b0da93eaedb4d1661af50742440e7988c7e48185.

> function:public.hybrid_search(query_text text, query_embedding bytea, vector_weight double precision, text_weight double precision, k integer, model_name text): Legacy SQL search overload; no code under nexus/ or scripts/ calls it (MEMNON's execute_hybrid_search delegates to execute_multi_model_hybrid_search, which builds its own SQL; nexus/agents/memnon/utils/db_access.py:581), and no reader/writer evidence establishes its contract yet. Routed: docs/dead_retrieval_subtraction.md, section "Deferred Vector-Helper Function Manifest" (deferred to #812).
> function:public.hybrid_search(query_text text, query_embedding vector, vector_weight double precision, text_weight double precision, k integer, model_name text): Legacy SQL search overload; no code under nexus/ or scripts/ calls it (MEMNON's execute_hybrid_search delegates to execute_multi_model_hybrid_search, which builds its own SQL; nexus/agents/memnon/utils/db_access.py:581), and no reader/writer evidence establishes its contract yet. Routed: docs/dead_retrieval_subtraction.md, section "Deferred Vector-Helper Function Manifest" (deferred to #812).
> function:public.hybrid_search(query_text text, query_embedding vector, vector_weight double precision, text_weight double precision, k integer, model_name text, alias_terms_input text[]): Legacy SQL search overload; no code under nexus/ or scripts/ calls it (MEMNON's execute_hybrid_search delegates to execute_multi_model_hybrid_search, which builds its own SQL; nexus/agents/memnon/utils/db_access.py:581), and no reader/writer evidence establishes its contract yet. Routed: docs/dead_retrieval_subtraction.md, section "Deferred Vector-Helper Function Manifest" (deferred to #812).
> function:public.migrate_embeddings(): Legacy copy from chunk_embeddings_small into chunk_embeddings; no code under nexus/ or scripts/ calls it, and NEXUS_template has neither table. Routed: docs/dead_retrieval_subtraction.md, section "Deferred Vector-Helper Function Manifest" (deferred to #812).
> function:public.pad_vector_384_to_1024(v vector): Legacy 384-to-1024 vector padding helper; no code under nexus/ or scripts/ and no other NEXUS function calls it. Routed: docs/dead_retrieval_subtraction.md, section "Deferred Vector-Helper Function Manifest" (deferred to #812).
> function:public.pad_vector_to_1024(v vector): Legacy 384-to-1024 vector padding helper; no code under nexus/ or scripts/ and no other NEXUS function calls it. Routed: docs/dead_retrieval_subtraction.md, section "Deferred Vector-Helper Function Manifest" (deferred to #812).

## Rejected Alternatives

- A comment without reader or writer evidence.

Source: https://github.com/pythagorakase/nexus/issues/819.

> Ambiguous semantics must route to the decision ledger rather than receiving invented documentation.

## Reopening Criteria

- A reader or writer that establishes the contract, or a migration that drops the object.
