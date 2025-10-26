-- Migration: add OpenRouter contenders and sampling parameters
-- Date: 2025-11-05

BEGIN;

-- Extend provider enum for new OpenRouter upstreams
ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'moonshotai';
ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'nousresearch';
ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'openrouter';

-- Extend model enum for new contenders
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'kimi-k2-0905-preview';
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'hermes-4-405b';

-- Add sampling controls and visibility toggle
ALTER TABLE apex_audition.conditions
    ADD COLUMN IF NOT EXISTS top_p REAL,
    ADD COLUMN IF NOT EXISTS min_p REAL,
    ADD COLUMN IF NOT EXISTS frequency_penalty REAL,
    ADD COLUMN IF NOT EXISTS presence_penalty REAL,
    ADD COLUMN IF NOT EXISTS repetition_penalty REAL,
    ADD COLUMN IF NOT EXISTS is_visible BOOLEAN NOT NULL DEFAULT true;

-- Ensure existing rows respect the new visibility constraint
UPDATE apex_audition.conditions SET is_visible = true WHERE is_visible IS NULL;

COMMIT;
