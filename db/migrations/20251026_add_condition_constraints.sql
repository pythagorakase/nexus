-- Migration: Add safety constraints to apex_audition.conditions
-- Date: 2025-10-26
-- Purpose: Enforce business rules at database level and improve deletion safety
--
-- Changes:
-- 1. Add CHECK constraint for Anthropic temperature range (0.0 - 1.0)
-- 2. Add CHECK constraint requiring thinking_budget_tokens when thinking_enabled=true
-- 3. Change ON DELETE CASCADE to ON DELETE RESTRICT for safer deletion
-- 4. Add notes column for condition-level documentation

-- ============================================================
-- 1. Add CHECK constraint for Anthropic temperature range
-- ============================================================
-- Anthropic models only accept temperature in range [0.0, 1.0]
-- NULL is allowed (for reasoning models or when using default)

ALTER TABLE apex_audition.conditions
ADD CONSTRAINT check_anthropic_temperature
CHECK (
    provider != 'anthropic'::apex_audition.provider_enum
    OR temperature IS NULL
    OR (temperature >= 0.0 AND temperature <= 1.0)
);

COMMENT ON CONSTRAINT check_anthropic_temperature ON apex_audition.conditions IS
'Anthropic models require temperature in range [0.0, 1.0] when specified. NULL is allowed.';

-- ============================================================
-- 2. Add CHECK constraint for extended thinking requirements
-- ============================================================
-- When thinking_enabled=true, thinking_budget_tokens must be set
-- This prevents invalid configurations where thinking is enabled but no budget is allocated

ALTER TABLE apex_audition.conditions
ADD CONSTRAINT check_thinking_budget
CHECK (
    thinking_enabled = false
    OR thinking_enabled IS NULL
    OR (thinking_enabled = true AND thinking_budget_tokens IS NOT NULL AND thinking_budget_tokens > 0)
);

COMMENT ON CONSTRAINT check_thinking_budget ON apex_audition.conditions IS
'When extended thinking is enabled, a positive thinking_budget_tokens value must be specified.';

-- ============================================================
-- 3. Add notes column for condition-level documentation
-- ============================================================
-- This column wasn't part of the original migration but is useful for
-- documenting why a condition was created, deprecated, or has specific parameters

ALTER TABLE apex_audition.conditions
ADD COLUMN IF NOT EXISTS notes TEXT;

COMMENT ON COLUMN apex_audition.conditions.notes IS
'Optional documentation for this condition: rationale, experiment context, deprecation reason, etc.';

-- ============================================================
-- 4. Change foreign key constraint to RESTRICT deletion
-- ============================================================
-- IMPORTANT: This prevents accidental cascade deletion of expensive generation data
--
-- Current behavior (CASCADE):
--   DELETE condition → deletes all generations → deletes all comparisons
--
-- New behavior (RESTRICT):
--   DELETE condition → BLOCKED if any generations exist
--   Forces explicit decision to either:
--     a) Soft-delete via is_active=false (recommended)
--     b) Manually delete generations first (dangerous, requires intent)

-- First, find the existing foreign key constraint name
DO $$
DECLARE
    fk_name TEXT;
BEGIN
    -- Get the foreign key constraint name from information_schema
    SELECT constraint_name INTO fk_name
    FROM information_schema.table_constraints
    WHERE table_schema = 'apex_audition'
      AND table_name = 'generations'
      AND constraint_type = 'FOREIGN KEY'
      AND constraint_name LIKE '%condition%';

    -- Drop the existing CASCADE constraint
    IF fk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE apex_audition.generations DROP CONSTRAINT %I', fk_name);

        -- Add new RESTRICT constraint
        ALTER TABLE apex_audition.generations
        ADD CONSTRAINT fk_generations_condition_id
        FOREIGN KEY (condition_id)
        REFERENCES apex_audition.conditions(id)
        ON DELETE RESTRICT;

        RAISE NOTICE 'Updated foreign key constraint from CASCADE to RESTRICT';
    ELSE
        RAISE WARNING 'Could not find existing foreign key constraint to update';
    END IF;
END $$;

COMMENT ON CONSTRAINT fk_generations_condition_id ON apex_audition.generations IS
'RESTRICT prevents accidental deletion of conditions with generation data. Use soft-delete (is_active=false) instead.';

-- ============================================================
-- Verification queries
-- ============================================================

-- Verify constraints were added
SELECT
    conname as constraint_name,
    pg_get_constraintdef(oid) as definition
FROM pg_constraint
WHERE conrelid = 'apex_audition.conditions'::regclass
  AND conname IN ('check_anthropic_temperature', 'check_thinking_budget')
ORDER BY conname;

-- Verify foreign key constraint is now RESTRICT
SELECT
    tc.constraint_name,
    tc.table_name,
    kcu.column_name,
    rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.referential_constraints rc
    ON tc.constraint_name = rc.constraint_name
    AND tc.table_schema = rc.constraint_schema
WHERE tc.table_schema = 'apex_audition'
  AND tc.table_name = 'generations'
  AND tc.constraint_type = 'FOREIGN KEY'
  AND kcu.column_name = 'condition_id';
