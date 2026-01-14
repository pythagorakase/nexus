-- migrations/009_remove_assets_save_slots.sql
-- Description: Remove redundant assets.save_slots table
-- Date: 2026-01-14
--
-- The assets.save_slots table is redundant:
--   - slot_number: now in global_variables (per-database singleton)
--   - character_name: redundant (wizard uses new_story_creator, narrative uses FK to characters)
--   - last_played: migrated to global_variables
--   - created_at: migrated to global_variables
--   - is_active: migrated to global_variables
--   - model: already in global_variables.model
--   - is_locked: vestigial (replaced by PG's default_transaction_read_only setting)

-- Add new columns to global_variables
ALTER TABLE global_variables ADD COLUMN IF NOT EXISTS slot_number INTEGER;
ALTER TABLE global_variables ADD COLUMN IF NOT EXISTS last_played TIMESTAMPTZ;
ALTER TABLE global_variables ADD COLUMN IF NOT EXISTS slot_created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE global_variables ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN global_variables.slot_number IS 'Slot number (1-5) for this database';
COMMENT ON COLUMN global_variables.last_played IS 'Timestamp of last user interaction';
COMMENT ON COLUMN global_variables.slot_created_at IS 'When this slot was created';
COMMENT ON COLUMN global_variables.is_active IS 'Whether this slot is currently being played';

-- Drop the redundant table
DROP TABLE IF EXISTS assets.save_slots;

-- Drop the orphaned model ENUM type (no longer needed)
DROP TYPE IF EXISTS assets.model_type;
