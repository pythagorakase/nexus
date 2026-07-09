-- 072_retrograde_layer_backfill.sql
--
-- Stamp existing Retrograde chunks with the world_layer added in 071.
-- Separate file because a value added by ALTER TYPE ... ADD VALUE cannot
-- be used inside the same transaction that added it. Marker-matched via
-- narrative_chunks.authorial_directives — the same mechanism MEMNON's
-- warm-slice filter uses.

UPDATE chunk_metadata cm
SET world_layer = 'retrograde'
FROM narrative_chunks nc
WHERE nc.id = cm.chunk_id
  AND cm.world_layer <> 'retrograde'
  AND (
    nc.authorial_directives @> '["orrery:retrograde_prologue_anchor"]'::jsonb
    OR nc.authorial_directives @> '["orrery:retrograde_event_summary"]'::jsonb
  );
