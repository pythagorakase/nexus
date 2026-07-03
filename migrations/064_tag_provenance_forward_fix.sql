-- 064_tag_provenance_forward_fix.sql
--
-- Forward-fix migrations for tag provenance (step 7 of
-- docs/orrery_audit_dashboard_notes.md, "Reconstruction Sufficiency").
-- Going forward, bestowals carry the chunk that caused them and clearances
-- are logged on every path — the prerequisites for honest as-of rewind of
-- tags and pair tags. Pre-064 rows keep NULLs: per-row provenance stays
-- "approximate" (world time only) or "unknowable" (neither), and the
-- hover-audit renders the epoch per row.

-- 1. Bestowal chunk keys. The resolver's apply path and the Skald commit
--    path both hold the committing chunk id; these columns give them a
--    place to put it. "Exact" as-of provenance is defined as
--    source_chunk_id IS NOT NULL.
ALTER TABLE entity_tags
ADD COLUMN IF NOT EXISTS source_chunk_id bigint REFERENCES narrative_chunks(id);

COMMENT ON COLUMN entity_tags.source_chunk_id IS
    'Chunk whose commit bestowed this tag. NULL on rows written before migration 064 and on pre-chunk bestowals (wizard seeding, entity-reference resolution); non-NULL is the "exact" as-of provenance tier.';

ALTER TABLE entity_pair_tags
ADD COLUMN IF NOT EXISTS source_chunk_id bigint REFERENCES narrative_chunks(id);

COMMENT ON COLUMN entity_pair_tags.source_chunk_id IS
    'Chunk whose commit bestowed this pair tag. NULL on pre-064 rows; non-NULL is the "exact" as-of provenance tier.';

-- 2. Pair-tag clearance logging. tag_clearance_log.entity_tag_id was NOT
--    NULL and single-entity only, so pair-tag clears were structurally
--    unloggable. The log becomes polymorphic: exactly one of
--    entity_tag_id / entity_pair_tag_id per row.
ALTER TABLE tag_clearance_log
ALTER COLUMN entity_tag_id DROP NOT NULL;

ALTER TABLE tag_clearance_log
ADD COLUMN IF NOT EXISTS entity_pair_tag_id bigint REFERENCES entity_pair_tags(id);

ALTER TABLE tag_clearance_log
DROP CONSTRAINT IF EXISTS tag_clearance_log_exactly_one_subject;
ALTER TABLE tag_clearance_log
ADD CONSTRAINT tag_clearance_log_exactly_one_subject
CHECK (num_nonnulls(entity_tag_id, entity_pair_tag_id) = 1);

COMMENT ON COLUMN tag_clearance_log.entity_pair_tag_id IS
    'Cleared entity_pair_tags row, for pair-tag clearances (loggable since migration 064). Exactly one of entity_tag_id / entity_pair_tag_id is set per row.';

CREATE INDEX IF NOT EXISTS ix_tag_clearance_log_entity_pair_tag_id
    ON tag_clearance_log (entity_pair_tag_id);

-- 3. Surface the new provenance in the audit hover's read path.
--    entity_tags_current is a column-projection view; the new column must
--    be projected explicitly.
CREATE OR REPLACE VIEW entity_tags_current AS
SELECT et.id AS entity_tag_id,
       et.entity_id,
       e.kind AS entity_kind,
       t.tag,
       t.category,
       t.is_ephemeral,
       t.clearance_kind,
       et.applied_at,
       et.applied_at_world_time,
       et.source_kind,
       et.template_id,
       et.source_chunk_id
FROM entity_tags et
JOIN entities e ON e.id = et.entity_id
JOIN tags t ON t.id = et.tag_id
WHERE t.deprecated = false
  AND et.cleared_at IS NULL
  AND t.synonym_for IS NULL;
