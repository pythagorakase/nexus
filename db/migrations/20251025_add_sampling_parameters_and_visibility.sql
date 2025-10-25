-- Migration: Add sampling parameters and visibility flag to conditions
-- Date: 2025-10-25
-- Description: Add new parameter columns (top_p, min_p, frequency_penalty, presence_penalty, repetition_penalty),
--              add is_visible flag, and add new model types for Kimi K2 and Hermes 4

BEGIN;

-- ============================================================================
-- Step 1: Add new parameter columns to conditions table
-- ============================================================================

ALTER TABLE apex_audition.conditions
    ADD COLUMN top_p REAL,
    ADD COLUMN min_p REAL,
    ADD COLUMN frequency_penalty REAL,
    ADD COLUMN presence_penalty REAL,
    ADD COLUMN repetition_penalty REAL;

-- ============================================================================
-- Step 2: Add is_visible flag (default true for backward compatibility)
-- ============================================================================

ALTER TABLE apex_audition.conditions
    ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT true;

-- ============================================================================
-- Step 3: Add new model values to model_name_enum
-- ============================================================================

-- Add Kimi K2 model
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'kimi-k2-0905-preview';

-- Add Hermes 4 model
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'Hermes-4-405B';

COMMIT;
