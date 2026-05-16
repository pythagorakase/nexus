-- 020_drop_chunk_embeddings_0384d.sql
--
-- Drop the vestigial 384-dimension embedding table. It is a relic of an
-- abandoned BGE-Small fine-tune attempt; no production code reads from or
-- writes to it. nexus.agents.memnon.utils.embedding_tables.DIMENSION_TABLE_MAP
-- has not contained a 384 entry for some time. The table is also missing
-- ON DELETE CASCADE on its FK to narrative_chunks(id) — the only such gap
-- among the dimension-sharded tables — which would matter if any future
-- feature ever deletes from narrative_chunks.
--
-- Discharges a recurring sharp edge that has surfaced in three separate
-- features (issue #175 single-model consolidation, narrative undo design,
-- and PR review of the embedding-pipeline overhaul).
--
-- Idempotent via DROP TABLE IF EXISTS — safe to re-run.

DROP TABLE IF EXISTS chunk_embeddings_0384d;
