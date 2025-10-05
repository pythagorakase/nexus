-- Migration: Purify retrieved_passages to remove future contamination
-- Date: 2025-01-05
-- Description: Filter out chunks from retrieved_passages where chunk_id > prompt.chunk_id
--              to preserve causality and prevent future knowledge leakage

BEGIN;

-- Create a function to purify a single prompt's context
CREATE OR REPLACE FUNCTION purify_prompt_context(
    p_chunk_id INTEGER,
    p_context JSONB
) RETURNS JSONB AS $$
DECLARE
    v_retrieved_passages JSONB;
    v_results JSONB;
    v_purified_results JSONB := '[]'::JSONB;
    v_passage JSONB;
    v_passage_chunk_id TEXT;
BEGIN
    -- Extract retrieved_passages (try both possible keys)
    v_retrieved_passages := p_context -> 'retrieved_passages';
    IF v_retrieved_passages IS NULL THEN
        v_retrieved_passages := p_context -> 'contextual_augmentation';
    END IF;

    -- If no retrieved_passages, return context unchanged
    IF v_retrieved_passages IS NULL THEN
        RETURN p_context;
    END IF;

    -- Extract results array
    v_results := v_retrieved_passages -> 'results';
    IF v_results IS NULL OR jsonb_typeof(v_results) != 'array' THEN
        RETURN p_context;
    END IF;

    -- Filter passages to keep only those with chunk_id <= p_chunk_id
    FOR v_passage IN SELECT * FROM jsonb_array_elements(v_results)
    LOOP
        v_passage_chunk_id := v_passage ->> 'chunk_id';

        -- Keep passage if:
        -- 1. No chunk_id present (safe default)
        -- 2. chunk_id is not a valid integer (safe default)
        -- 3. chunk_id <= prompt's chunk_id (temporal safety)
        IF v_passage_chunk_id IS NULL
           OR v_passage_chunk_id !~ '^\d+$'
           OR v_passage_chunk_id::INTEGER <= p_chunk_id
        THEN
            v_purified_results := v_purified_results || v_passage;
        END IF;
    END LOOP;

    -- Update both possible keys with purified results
    IF p_context ? 'retrieved_passages' THEN
        p_context := jsonb_set(
            p_context,
            '{retrieved_passages,results}',
            v_purified_results
        );
    END IF;

    IF p_context ? 'contextual_augmentation' THEN
        p_context := jsonb_set(
            p_context,
            '{contextual_augmentation,results}',
            v_purified_results
        );
    END IF;

    RETURN p_context;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Apply purification to all prompts
UPDATE apex_audition.prompts
SET context = purify_prompt_context(chunk_id, context);

-- Drop the temporary function
DROP FUNCTION purify_prompt_context(INTEGER, JSONB);

-- Log the purification
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM apex_audition.prompts;
    RAISE NOTICE 'Purified % prompts to remove future contamination', v_count;
END $$;

COMMIT;
