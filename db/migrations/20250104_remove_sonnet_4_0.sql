-- Migration: Remove claude-sonnet-4-0 from model_name_enum
-- Date: 2025-01-04
-- Description: Remove accidental claude-sonnet-4-0 value from ENUM

BEGIN;

-- Step 1: Remap any lingering claude-sonnet-4-0 rows to the supported alias
-- This prevents the enum alteration from failing when the value disappears.
UPDATE apex_audition.conditions
SET model_name = 'claude-sonnet-4-5'
WHERE model_name = 'claude-sonnet-4-0';

-- Step 2: Create new ENUM without claude-sonnet-4-0
CREATE TYPE apex_audition.model_name_enum_new AS ENUM (
    'gpt-5',
    'gpt-4o',
    'o3',
    'claude-sonnet-4-5',
    'claude-opus-4-1'
);

-- Step 3: Update column to use new ENUM type
ALTER TABLE apex_audition.conditions
    ALTER COLUMN model_name TYPE apex_audition.model_name_enum_new
    USING model_name::text::apex_audition.model_name_enum_new;

-- Step 4: Drop old ENUM type
DROP TYPE apex_audition.model_name_enum;

-- Step 5: Rename new ENUM to original name
ALTER TYPE apex_audition.model_name_enum_new RENAME TO model_name_enum;

-- Step 6: Update repository.py ENUM definition to match
-- (This is a reminder - you'll need to manually update the Python code)

COMMIT;
