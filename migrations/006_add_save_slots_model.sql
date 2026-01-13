-- Migration 006: Add model column to assets.save_slots table
--
-- Adds slot-level model selection support. Each save slot can have its own
-- preferred model (gpt-5.1, TEST, claude). The model is stored as an ENUM
-- for type safety, but defaults to NULL (inherit from global settings).
--
-- When adding new models, extend the ENUM with:
--   ALTER TYPE assets.model_type ADD VALUE 'new-model-name';

-- Create the model ENUM type in the assets schema
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'model_type' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'assets')) THEN
        CREATE TYPE assets.model_type AS ENUM ('gpt-5.1', 'TEST', 'claude');
    END IF;
END
$$;

-- Add the model column to save_slots
ALTER TABLE assets.save_slots
ADD COLUMN IF NOT EXISTS model assets.model_type DEFAULT NULL;

COMMENT ON COLUMN assets.save_slots.model IS
'Preferred model for this slot. NULL means inherit from global settings.';

-- Also update the schema definition in new_story_setup.py to include this column
-- for newly created slots.
