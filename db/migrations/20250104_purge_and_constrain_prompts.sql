-- Migration: Purge contaminated prompts and add UNIQUE constraint
-- Date: 2025-01-04
-- Description: Remove all prompts from the age of contamination and prevent duplicate chunk_ids

BEGIN;

-- Step 1: Purge all contaminated prompts (CASCADE will clean dependent tables)
TRUNCATE TABLE apex_audition.prompts CASCADE;

-- Step 2: Add UNIQUE constraint to chunk_id to prevent pretenders
CREATE UNIQUE INDEX ix_apex_audition_prompts_chunk_id ON apex_audition.prompts(chunk_id);

-- Step 3: Prompts will be rebuilt from cleansed context packages
-- Run: python -m nexus.audition.engine --ingest

COMMIT;
