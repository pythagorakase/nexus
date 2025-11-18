-- Create incubator table for provisional narrative turns
-- This table holds generated content awaiting user approval

CREATE TABLE IF NOT EXISTS incubator (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id = TRUE),  -- Ensures only one row
    chunk_id BIGINT NOT NULL,                               -- The NEW chunk being created (e.g., 1426)
    parent_chunk_id BIGINT NOT NULL,                        -- Where we're continuing from (e.g., 1425)
    user_text TEXT,                                         -- User's completion text for parent chunk
    storyteller_text TEXT,                                  -- Generated text for new chunk
    metadata_updates JSONB DEFAULT '{}',                    -- Time delta, episode transition, etc
    entity_updates JSONB DEFAULT '[]',                      -- Character/place/faction state changes
    reference_updates JSONB DEFAULT '{}',                   -- Entity references (present/mentioned)
    session_id UUID NOT NULL DEFAULT gen_random_uuid(),     -- Track generation attempts
    llm_response_id TEXT,                                   -- API response ID for debugging
    status TEXT DEFAULT 'provisional',                      -- provisional -> approved -> committed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE incubator IS 'Provisional storage for narrative turns awaiting approval';
COMMENT ON COLUMN incubator.id IS 'Singleton constraint - only one incubation at a time';
COMMENT ON COLUMN incubator.chunk_id IS 'ID of the new chunk being created (not yet in narrative_chunks)';
COMMENT ON COLUMN incubator.parent_chunk_id IS 'ID of existing chunk being continued from';
COMMENT ON COLUMN incubator.user_text IS 'User completion text for the parent chunk';
COMMENT ON COLUMN incubator.storyteller_text IS 'AI-generated storyteller text for the new chunk';
COMMENT ON COLUMN incubator.metadata_updates IS 'JSON: {episode_transition, time_delta_seconds, time_delta_description, world_layer, pacing}';
COMMENT ON COLUMN incubator.entity_updates IS 'JSON array of entity state changes: [{type, id, field, old_value, new_value}]';
COMMENT ON COLUMN incubator.reference_updates IS 'JSON: {character_present: [], character_referenced: [], place_referenced: []}';
COMMENT ON COLUMN incubator.session_id IS 'UUID for tracking regeneration attempts';
COMMENT ON COLUMN incubator.llm_response_id IS 'OpenAI or LM Studio response ID for debugging';
COMMENT ON COLUMN incubator.status IS 'Status: provisional (pending approval), approved (ready to commit), committed (written to main tables)';

-- Create a view for easy inspection of incubator contents
CREATE OR REPLACE VIEW incubator_view AS
SELECT
    i.chunk_id,
    i.parent_chunk_id,
    nc.raw_text as parent_chunk_text,
    i.user_text,
    i.storyteller_text,
    i.metadata_updates->>'episode_transition' as episode_transition,
    i.metadata_updates->>'time_delta_description' as time_delta,
    i.metadata_updates->>'world_layer' as world_layer,
    i.metadata_updates->>'pacing' as pacing,
    jsonb_array_length(i.entity_updates) as entity_update_count,
    i.entity_updates as entity_changes,
    i.reference_updates as references,
    i.status,
    i.session_id,
    i.created_at
FROM incubator i
LEFT JOIN narrative_chunks nc ON nc.id = i.parent_chunk_id;

COMMENT ON VIEW incubator_view IS 'Human-readable view of incubator contents with parent chunk context';

-- Create function to clear incubator after approval
CREATE OR REPLACE FUNCTION clear_incubator() RETURNS VOID AS $$
BEGIN
    DELETE FROM incubator WHERE id = TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION clear_incubator IS 'Clear the incubator after content is approved and committed';

-- Create test mode tables (parallel to production)
CREATE TABLE IF NOT EXISTS narrative_chunks_test (LIKE narrative_chunks INCLUDING ALL);
CREATE TABLE IF NOT EXISTS chunk_metadata_test (LIKE chunk_metadata INCLUDING ALL);
CREATE TABLE IF NOT EXISTS chunk_character_references_test (LIKE chunk_character_references INCLUDING ALL);
CREATE TABLE IF NOT EXISTS place_chunk_references_test (LIKE place_chunk_references INCLUDING ALL);
CREATE TABLE IF NOT EXISTS faction_chunk_references_test (LIKE faction_chunk_references INCLUDING ALL);

COMMENT ON TABLE narrative_chunks_test IS 'Test mode narrative chunks - parallel to production';
COMMENT ON TABLE chunk_metadata_test IS 'Test mode metadata - parallel to production';
COMMENT ON TABLE chunk_character_references_test IS 'Test mode character references';
COMMENT ON TABLE place_chunk_references_test IS 'Test mode place references';
COMMENT ON TABLE faction_chunk_references_test IS 'Test mode faction references';

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_incubator_updated_at
BEFORE UPDATE ON incubator
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();