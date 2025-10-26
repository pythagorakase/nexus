-- Migration: Add OpenRouter contenders and sampling parameters
-- Date: 2025-02-05
-- Description: Extend apex_audition.conditions with additional sampling columns,
--              visibility toggle, and enum values for new providers/models.

BEGIN;

-- Ensure provider enum has required values
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'deepseek'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'deepseek';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'moonshot'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'moonshot';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'nousresearch'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'nousresearch';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'openrouter'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'openrouter';
    END IF;
END$$;

-- Ensure model enum has required values
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.model_name_enum'::regtype
          AND enumlabel = 'deepseek-v3.2-exp'
    ) THEN
        ALTER TYPE apex_audition.model_name_enum ADD VALUE 'deepseek-v3.2-exp';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.model_name_enum'::regtype
          AND enumlabel = 'kimi-k2-0905-preview'
    ) THEN
        ALTER TYPE apex_audition.model_name_enum ADD VALUE 'kimi-k2-0905-preview';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.model_name_enum'::regtype
          AND enumlabel = 'hermes-4-405b'
    ) THEN
        ALTER TYPE apex_audition.model_name_enum ADD VALUE 'hermes-4-405b';
    END IF;
END$$;

-- Add new sampling parameter columns if they do not already exist
ALTER TABLE apex_audition.conditions
    ADD COLUMN IF NOT EXISTS top_p REAL,
    ADD COLUMN IF NOT EXISTS min_p REAL,
    ADD COLUMN IF NOT EXISTS frequency_penalty REAL,
    ADD COLUMN IF NOT EXISTS presence_penalty REAL,
    ADD COLUMN IF NOT EXISTS repetition_penalty REAL;

-- Add visibility flag (default true)
ALTER TABLE apex_audition.conditions
    ADD COLUMN IF NOT EXISTS is_visible BOOLEAN;

UPDATE apex_audition.conditions
SET is_visible = COALESCE(is_visible, TRUE);

ALTER TABLE apex_audition.conditions
    ALTER COLUMN is_visible SET NOT NULL,
    ALTER COLUMN is_visible SET DEFAULT TRUE;

COMMIT;
