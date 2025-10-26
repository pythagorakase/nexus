-- Normalize provider enum casing to lowercase variants used by the application
-- Converts existing provider values and recreates the enum type

BEGIN;

-- Create a new enum with the desired lowercase values
CREATE TYPE apex_audition.provider_enum_new AS ENUM (
    'openai',
    'anthropic',
    'deepseek',
    'openrouter'
);

-- Re-type the column while lowercasing existing entries
ALTER TABLE apex_audition.conditions
    ALTER COLUMN provider TYPE apex_audition.provider_enum_new
    USING lower(provider::text)::apex_audition.provider_enum_new;

-- Swap the new enum in place of the original
DROP TYPE apex_audition.provider_enum;
ALTER TYPE apex_audition.provider_enum_new RENAME TO provider_enum;

COMMIT;
