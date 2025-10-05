-- Migration: Normalize apex_audition.conditions table
-- Date: 2025-01-04
-- Description: Replace JSONB parameters with typed columns and add ENUM constraints

BEGIN;

-- ============================================================================
-- Step 1: Create ENUM types
-- ============================================================================

CREATE TYPE apex_audition.provider_enum AS ENUM ('openai', 'anthropic');

CREATE TYPE apex_audition.model_name_enum AS ENUM (
    'gpt-5',
    'gpt-4o',
    'o3',
    'claude-sonnet-4-5',
    'claude-sonnet-4-0',
    'claude-opus-4-1'
);

CREATE TYPE apex_audition.reasoning_effort_enum AS ENUM (
    'minimal',
    'low',
    'medium',
    'high'
);

-- ============================================================================
-- Step 2: Add new typed columns to conditions table
-- ============================================================================

ALTER TABLE apex_audition.conditions
    ADD COLUMN temperature REAL,
    ADD COLUMN reasoning_effort apex_audition.reasoning_effort_enum,
    ADD COLUMN thinking_enabled BOOLEAN,
    ADD COLUMN max_output_tokens INTEGER,
    ADD COLUMN thinking_budget_tokens INTEGER,
    ADD COLUMN provider_new apex_audition.provider_enum,
    ADD COLUMN model_name_new apex_audition.model_name_enum;

-- ============================================================================
-- Step 3: Migrate data from JSONB to typed columns
-- ============================================================================

-- Migrate parameters from JSONB
UPDATE apex_audition.conditions
SET
    temperature = (parameters->>'temperature')::REAL,
    reasoning_effort = (parameters->>'reasoning_effort')::apex_audition.reasoning_effort_enum,
    thinking_enabled = (parameters->>'thinking_enabled')::BOOLEAN,
    -- Handle both max_output_tokens and max_tokens (legacy)
    max_output_tokens = COALESCE(
        (parameters->>'max_output_tokens')::INTEGER,
        (parameters->>'max_tokens')::INTEGER
    ),
    thinking_budget_tokens = (parameters->>'thinking_budget_tokens')::INTEGER;

-- Migrate provider (simple cast for valid values)
UPDATE apex_audition.conditions
SET provider_new = provider::apex_audition.provider_enum
WHERE provider IN ('openai', 'anthropic');

-- Migrate model_name with mapping for versioned models
UPDATE apex_audition.conditions
SET model_name_new = CASE
    -- Map version-specific to stable aliases
    WHEN model_name = 'claude-sonnet-4-5-20250929' THEN 'claude-sonnet-4-5'::apex_audition.model_name_enum
    WHEN model_name = 'claude-sonnet-4-20250514' THEN 'claude-sonnet-4-0'::apex_audition.model_name_enum
    -- Direct mappings for valid models
    WHEN model_name IN (
        'gpt-5', 'gpt-4o', 'o3',
        'claude-sonnet-4-5', 'claude-sonnet-4-0', 'claude-opus-4-1'
    ) THEN model_name::apex_audition.model_name_enum
    ELSE NULL
END
WHERE model_name NOT IN ('claude-test', 'gpt-test');

-- ============================================================================
-- Step 4: Delete test conditions
-- ============================================================================

DELETE FROM apex_audition.conditions
WHERE model_name IN ('claude-test', 'gpt-test');

-- ============================================================================
-- Step 5: Replace old columns with new ENUM columns
-- ============================================================================

-- Drop old columns
ALTER TABLE apex_audition.conditions
    DROP COLUMN provider,
    DROP COLUMN model_name,
    DROP COLUMN parameters;

-- Rename new columns
ALTER TABLE apex_audition.conditions
    RENAME COLUMN provider_new TO provider;

ALTER TABLE apex_audition.conditions
    RENAME COLUMN model_name_new TO model_name;

-- Make provider and model_name NOT NULL (all remaining rows should have values)
ALTER TABLE apex_audition.conditions
    ALTER COLUMN provider SET NOT NULL,
    ALTER COLUMN model_name SET NOT NULL;

COMMIT;
