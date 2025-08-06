-- Create a human-friendly view of character references by chunk
-- This view transforms the normalized chunk_character_references table back into
-- arrays showing which characters are present vs mentioned in each narrative chunk

CREATE OR REPLACE VIEW chunk_character_references_view AS
WITH character_refs AS (
    -- First, join character references with character names
    SELECT 
        ccr.chunk_id,
        c.name,
        ccr.reference
    FROM chunk_character_references ccr
    JOIN characters c ON ccr.character_id = c.id
)
SELECT 
    nc.id,
    cm.season,
    cm.episode,
    cm.scene,
    -- Aggregate present characters into an array
    COALESCE(
        ARRAY_AGG(
            DISTINCT cr.name ORDER BY cr.name
        ) FILTER (WHERE cr.reference = 'present'),
        ARRAY[]::text[]
    ) AS characters_present,
    -- Aggregate mentioned characters into an array
    COALESCE(
        ARRAY_AGG(
            DISTINCT cr.name ORDER BY cr.name
        ) FILTER (WHERE cr.reference = 'mentioned'),
        ARRAY[]::text[]
    ) AS characters_mentioned
FROM narrative_chunks nc
JOIN chunk_metadata cm ON nc.id = cm.chunk_id
LEFT JOIN character_refs cr ON nc.id = cr.chunk_id
GROUP BY nc.id, cm.season, cm.episode, cm.scene
ORDER BY cm.season, cm.episode, cm.scene;

COMMENT ON VIEW chunk_character_references_view IS 'Human-friendly view of character references by chunk, showing present and mentioned characters as separate arrays';

-- Example queries:

-- Find all chunks where Alex is present
-- SELECT * FROM chunk_character_references_view 
-- WHERE 'Alex' = ANY(characters_present);

-- Find chunks with both Alex and Emilia present
-- SELECT * FROM chunk_character_references_view 
-- WHERE characters_present @> ARRAY['Alex', 'Emilia'];

-- Find chunks where Victor Sato is mentioned
-- SELECT * FROM chunk_character_references_view 
-- WHERE 'Victor Sato' = ANY(characters_mentioned);

-- Count chunks by number of characters present
-- SELECT 
--     array_length(characters_present, 1) as num_characters,
--     COUNT(*) as chunk_count
-- FROM chunk_character_references_view
-- GROUP BY array_length(characters_present, 1)
-- ORDER BY num_characters;