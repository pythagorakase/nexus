-- 018_narrative_chunks_column_comments.sql
--
-- Populate descriptive comments on narrative_chunks columns so the schema
-- is genuinely self-documenting via psql `\d+ narrative_chunks` or
-- MEMNON.get_schema_summary(). Discharges schema-detail debt previously
-- duplicated in CLAUDE.md.
--
-- COMMENT ON is idempotent (overwrites the prior value), so this migration
-- is safe to re-run. Refreshes raw_text's existing comment to capture its
-- derived/surface nature. Adds comments to seven columns that had none.

COMMENT ON COLUMN narrative_chunks.raw_text IS
    'User-readable prose version of the chunk ("the book version"). For in-system chunks this is the deterministic concatenation storyteller_text || choice_text — no unique information; re-derive if components change. For legacy imports (slot 1) this holds the original undecomposed text and storyteller_text mirrors it because the legacy corpus was never decomposed. Includes scene breaks and markdown formatting.';

COMMENT ON COLUMN narrative_chunks.state IS
    'Chunk lifecycle state. One of: ''draft'' (initial), ''pending_review'' (storyteller has produced text, user has not yet accepted), ''finalized'' (user accepted; chunk is locked — synonymous with "embedded" in practice). See ChunkState enum in nexus/api/chunk_workflow.py.';

COMMENT ON COLUMN narrative_chunks.finalized_at IS
    'Timestamp set by ChunkWorkflow.accept_chunk when the chunk transitions to the ''finalized'' state. NULL while the chunk is in ''draft'' or ''pending_review''.';

COMMENT ON COLUMN narrative_chunks.embedding_generated_at IS
    'Timestamp set by ChunkWorkflow._trigger_embedding_generation after the embedding subprocess (scripts/regenerate_embeddings.py) exits with code 0 — i.e., after a row has been written into one of the chunk_embeddings_*d tables. The subprocess itself does not write this column; the workflow does, post-success. NULL until embedding succeeds.';

COMMENT ON COLUMN narrative_chunks.regeneration_count IS
    'Number of times the storyteller text for this chunk has been regenerated via the regenerate flow. Zero for chunks accepted on first generation.';

COMMENT ON COLUMN narrative_chunks.storyteller_text IS
    'Authoritative storyteller portion of the chunk (narration only). For in-system chunks this is the leading segment of raw_text — concretely, raw_text = storyteller_text || choice_text, so raw_text.startswith(storyteller_text) holds. For legacy imports (slot 1) this equals raw_text because the corpus was never decomposed.';

COMMENT ON COLUMN narrative_chunks.choice_text IS
    'Authoritative text of the user''s response for this chunk. When the user selects a structured choice via --choice N, holds the text of that presented choice (resolved from choice_object.presented[N-1]). When the user submits freeform input via --user-text, holds that text directly.';

COMMENT ON COLUMN narrative_chunks.choice_object IS
    'JSON record of the choices offered + the chosen index. Shape: {"presented": [str, ...], "selected": <int 1..N | null>}. presented preserves the full menu the storyteller offered; selected is the 1-indexed pick (or null for --user-text / --accept-fate). This is the underground state that enables undo and audit even though raw_text (the readable surface) omits non-selected choices — a deliberate "surface entropy reduction" choice.';
