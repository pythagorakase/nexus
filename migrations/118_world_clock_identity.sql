-- Preserve the view's columns, types, join, and ordering. Only clock ownership
-- changes here; refresh_world_time_from_chunk() retains its existing semantics.
CREATE OR REPLACE VIEW narrative_view AS
SELECT nc.id,
       cm.season,
       cm.episode,
       cm.scene,
       cm.world_time,
       cm.world_layer,
       nc.raw_text
FROM narrative_chunks nc
JOIN chunk_metadata cm ON nc.id = cm.chunk_id
ORDER BY nc.id;

COMMENT ON VIEW narrative_view IS
    'The canonical story clock is chunk_metadata.world_time, the clock at the end of an accepted chunk; time_delta is the time elapsing during it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.';
COMMENT ON COLUMN narrative_view.world_time IS
    'The canonical story clock is chunk_metadata.world_time, the clock at the end of an accepted chunk; time_delta is the time elapsing during it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.';
COMMENT ON COLUMN chunk_metadata.world_time IS
    'The canonical story clock is chunk_metadata.world_time, the clock at the end of an accepted chunk; time_delta is the time elapsing during it; base_timestamp is the clock at the end of the bootstrap chunk. It is stored as timestamptz whose UTC face is the story clock face.';
COMMENT ON COLUMN chunk_metadata.time_delta IS
    'Story time elapsing during this chunk; world_time is the clock at its end.';
COMMENT ON COLUMN global_variables.base_timestamp IS
    'Story clock at the end of the bootstrap chunk, stored as timestamptz whose UTC face is the story clock face.';
