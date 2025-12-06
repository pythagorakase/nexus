-- migrations/004_fix_global_variables_fk.sql
-- Description: Change global_variables.user_character FK to ON DELETE SET NULL
-- Date: 2025-12-05
-- Issue: TRUNCATE CASCADE was deleting global_variables row

-- The global_variables table has a FK to characters.user_character.
-- Default ON DELETE behavior is NO ACTION, which causes TRUNCATE CASCADE
-- to propagate and delete the global_variables row.
--
-- While this migration doesn't prevent TRUNCATE CASCADE (which is DDL
-- and ignores ON DELETE rules), it provides defense-in-depth:
-- - Protects against accidental DELETE FROM characters
-- - Ensures global_variables row survives character deletion

-- Drop the old constraint and add new one with ON DELETE SET NULL
ALTER TABLE global_variables
DROP CONSTRAINT IF EXISTS global_variables_user_character_fkey;

ALTER TABLE global_variables
ADD CONSTRAINT global_variables_user_character_fkey
FOREIGN KEY (user_character) REFERENCES characters(id) ON DELETE SET NULL;
