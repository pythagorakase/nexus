-- Migration: Add OpenRouter contenders and sampling parameters
-- Date: 2025-02-05
-- Description: Extend apex_audition.conditions with additional sampling columns,
--              visibility toggle, and enum values for new providers/models.

BEGIN;

-- Normalize casing for existing provider enum values and ensure new entries
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'openai'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'OpenAI'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'openai' TO 'OpenAI';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'anthropic'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'Anthropic'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'anthropic' TO 'Anthropic';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'deepseek'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'DeepSeek'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'deepseek' TO 'DeepSeek';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'moonshot'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'Moonshot'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'moonshot' TO 'Moonshot';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'nousresearch'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'NousResearch'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'nousresearch' TO 'NousResearch';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'openrouter'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'OpenRouter'
    ) THEN
        ALTER TYPE apex_audition.provider_enum RENAME VALUE 'openrouter' TO 'OpenRouter';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'OpenAI'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'OpenAI';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'Anthropic'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'Anthropic';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'DeepSeek'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'DeepSeek';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'Moonshot'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'Moonshot';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'NousResearch'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'NousResearch';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'apex_audition.provider_enum'::regtype
          AND enumlabel = 'OpenRouter'
    ) THEN
        ALTER TYPE apex_audition.provider_enum ADD VALUE 'OpenRouter';
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
