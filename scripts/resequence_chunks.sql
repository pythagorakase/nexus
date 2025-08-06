-- resequence_chunks.sql
-- This script updates the sequence values in the narrative_chunks table
-- to reflect the correct global narrative order based on season, episode, and scene number.

-- 1. Create a temporary table with the correct ordering by extracting scene numbers from the raw text
CREATE TEMP TABLE chunk_order AS
WITH ordered_chunks AS (
  SELECT 
    nc.id as chunk_id,
    nc.sequence as old_sequence,
    cm.season,
    cm.episode,
    -- Extract scene number from the raw text using regex
    (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_(\d+)'))[3]::int as scene_number,
    -- Extract season and episode directly from the text to ensure correct ordering
    (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_'))[1]::int as text_season,
    (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_'))[2]::int as text_episode,
    ROW_NUMBER() OVER (
      ORDER BY 
        (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_'))[1]::int NULLS LAST,
        (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_'))[2]::int NULLS LAST,
        (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_(\d+)'))[3]::int NULLS LAST
    ) as new_sequence
  FROM narrative_chunks nc
  JOIN chunk_metadata cm ON nc.id = cm.chunk_id
)
SELECT * FROM ordered_chunks;

-- 2. Check if we need to reset the sequence
SELECT setval('narrative_chunks_sequence_seq', 
              (SELECT COALESCE(MAX(new_sequence), 0) FROM chunk_order),
              true);

-- 3. Create a function to update sequences without constraint violations
CREATE OR REPLACE FUNCTION update_sequences() RETURNS void AS $$
DECLARE
    chunk record;
    temp_seq bigint := (SELECT MAX(new_sequence) + 10000 FROM chunk_order);
BEGIN
    -- First update all sequences to temporary high values to avoid conflicts
    FOR chunk IN SELECT * FROM chunk_order ORDER BY new_sequence DESC LOOP
        UPDATE narrative_chunks
        SET sequence = temp_seq
        WHERE id = chunk.chunk_id;
        
        temp_seq := temp_seq + 1;
    END LOOP;
    
    -- Now update to the actual sequence numbers
    FOR chunk IN SELECT * FROM chunk_order ORDER BY new_sequence ASC LOOP
        UPDATE narrative_chunks
        SET sequence = chunk.new_sequence
        WHERE id = chunk.chunk_id;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- 4. Execute the function
SELECT update_sequences();

-- 5. Drop the function when done
DROP FUNCTION update_sequences();

-- 6. Verify results
SELECT COUNT(*) as total_chunks, 
       MIN(sequence) as min_sequence, 
       MAX(sequence) as max_sequence 
FROM narrative_chunks;

-- 7. Show some sample results in proper narrative order
SELECT 
    nc.sequence, 
    (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_'))[1] as text_season,
    (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_'))[2] as text_episode,
    (regexp_match(nc.raw_text, 'SCENE BREAK: S(\d+)E(\d+)_(\d+)'))[3] as scene_number,
    substring(nc.raw_text, 1, 60) as text_sample
FROM narrative_chunks nc
JOIN chunk_metadata cm ON nc.id = cm.chunk_id
ORDER BY nc.sequence
LIMIT 20;