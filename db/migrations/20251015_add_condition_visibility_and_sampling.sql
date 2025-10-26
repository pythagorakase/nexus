-- Add sampling parameter columns and visibility flag to apex_audition.conditions
-- Also register new OpenRouter model names used by the audition pipeline

BEGIN;

-- Extend model enum with new contenders
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'kimi-k2-0905-preview';
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'hermes-4-405b';

-- Add new sampling parameter columns
ALTER TABLE apex_audition.conditions
    ADD COLUMN IF NOT EXISTS top_p REAL,
    ADD COLUMN IF NOT EXISTS min_p REAL,
    ADD COLUMN IF NOT EXISTS frequency_penalty REAL,
    ADD COLUMN IF NOT EXISTS presence_penalty REAL,
    ADD COLUMN IF NOT EXISTS repetition_penalty REAL;

-- Track whether a condition should be shown in dashboards
ALTER TABLE apex_audition.conditions
    ADD COLUMN IF NOT EXISTS is_visible BOOLEAN NOT NULL DEFAULT TRUE;

COMMIT;
