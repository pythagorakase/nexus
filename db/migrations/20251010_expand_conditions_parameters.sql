-- Migration: Expand apex_audition.conditions parameter support
-- Date: 2025-10-10
-- Adds new sampling parameter columns, visibility flag, and provider/model enum values

BEGIN;

-- Normalize existing provider enum values to lowercase to match application expectations
DO $$
BEGIN
    -- Guard against repeated runs by checking for the original capitalized values
    IF EXISTS (
        SELECT 1
        FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'OpenAI'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'OpenAI' TO 'openai';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'Anthropic'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'Anthropic' TO 'anthropic';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'DeepSeek'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'DeepSeek' TO 'deepseek';
    END IF;
END $$;

-- Extend provider enum with additional OpenRouter vendors
ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'deepseek';
ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'openrouter';
ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'moonshot';
ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'nousresearch';

-- Extend model enum with new contenders
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'kimi-k2-0905-preview';
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'hermes-4-405b';

-- Add new sampling parameter columns and visibility flag
ALTER TABLE apex_audition.conditions
    ADD COLUMN IF NOT EXISTS top_p REAL,
    ADD COLUMN IF NOT EXISTS min_p REAL,
    ADD COLUMN IF NOT EXISTS frequency_penalty REAL,
    ADD COLUMN IF NOT EXISTS presence_penalty REAL,
    ADD COLUMN IF NOT EXISTS repetition_penalty REAL,
    ADD COLUMN IF NOT EXISTS is_visible BOOLEAN NOT NULL DEFAULT true;

COMMIT;
