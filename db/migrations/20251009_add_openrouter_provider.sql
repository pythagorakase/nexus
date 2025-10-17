-- Add 'openrouter' to the provider_enum type
ALTER TYPE apex_audition.provider_enum ADD VALUE IF NOT EXISTS 'openrouter';

-- Add 'deepseek-v3.2-exp' to the model_name_enum type
ALTER TYPE apex_audition.model_name_enum ADD VALUE IF NOT EXISTS 'deepseek-v3.2-exp';
