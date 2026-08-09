-- Remove the retired extra_observations field from staged incubator drafts.
--
-- PR #689 retired the observations wire arm: the field was hydrated and then
-- ignored by both commit paths, so it never produced durable state. Drafts
-- staged before the retirement still carry it, and the strict StateUpdates
-- grammar now rejects them at accept time. Stripping the inert field lets
-- pre-retirement drafts commit; nothing the commit path ever honored is lost.
-- Idempotent: re-running matches no rows.

UPDATE incubator
SET entity_updates = jsonb_set(
    entity_updates,
    '{characters}',
    (
        SELECT jsonb_agg(character_entry - 'extra_observations')
        FROM jsonb_array_elements(entity_updates -> 'characters')
            AS character_entry
    )
)
WHERE entity_updates -> 'characters' IS NOT NULL
  AND jsonb_typeof(entity_updates -> 'characters') = 'array'
  AND jsonb_array_length(entity_updates -> 'characters') > 0
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(entity_updates -> 'characters')
          AS character_entry
      WHERE character_entry ? 'extra_observations'
  );
