-- 077_recruit_ally_projects.sql
--
-- Extend the Orrery project chassis with RECRUIT_ALLY, the first project
-- whose target is a character rather than a place. The two nullable target
-- columns remain type-disciplined by explicit CHECK constraints and FKs.

ALTER TABLE character_project_states
    ADD COLUMN IF NOT EXISTS target_character_entity_id bigint NULL
        REFERENCES entities(id);

-- Migration 074 created the vocabulary constraints from inline column CHECKs,
-- whose generated names are stable. Its table-level completed-target CHECK is
-- deliberately discovered by definition: generated names for multiple
-- anonymous table CHECKs can vary with PostgreSQL/schema history, and dropping
-- a guessed suffix risks removing the independent progress-range guard.
ALTER TABLE character_project_states
    DROP CONSTRAINT IF EXISTS character_project_states_project_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_stage_check;

DO $$
DECLARE
    completed_target_constraints text[];
BEGIN
    SELECT array_agg(conname ORDER BY conname)
    INTO completed_target_constraints
    FROM pg_constraint
    WHERE conrelid = 'character_project_states'::regclass
      AND contype = 'c'
      AND position(
          'status' IN pg_get_constraintdef(oid, true)
      ) > 0
      AND position(
          'completed' IN pg_get_constraintdef(oid, true)
      ) > 0
      AND position(
          'target_place_id' IN pg_get_constraintdef(oid, true)
      ) > 0
      AND position(
          'project_type' IN pg_get_constraintdef(oid, true)
      ) = 0
      AND position(
          'target_character_entity_id' IN pg_get_constraintdef(oid, true)
      ) = 0;

    IF COALESCE(array_length(completed_target_constraints, 1), 0) <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one migration-074 completed-target CHECK; found %',
            completed_target_constraints;
    END IF;

    EXECUTE format(
        'ALTER TABLE character_project_states DROP CONSTRAINT %I',
        completed_target_constraints[1]
    );
END
$$;

ALTER TABLE character_project_states
    ADD CONSTRAINT character_project_states_project_type_check
        CHECK (project_type IN ('plan_relocation', 'recruit_ally')),
    ADD CONSTRAINT character_project_states_stage_by_type_check
        CHECK (
            (project_type = 'plan_relocation'
                AND stage IN ('saving', 'scouting', 'committing'))
            OR
            (project_type = 'recruit_ally'
                AND stage IN (
                    'sounding_out', 'earning_trust', 'sealing_commitment'
                ))
        ),
    ADD CONSTRAINT character_project_states_target_by_type_check
        CHECK (
            (project_type = 'plan_relocation'
                AND target_character_entity_id IS NULL)
            OR
            (project_type = 'recruit_ally'
                AND target_place_id IS NULL
                AND target_character_entity_id IS NOT NULL)
        ),
    ADD CONSTRAINT character_project_states_completed_target_check
        CHECK (
            status <> 'completed'
            OR (project_type = 'plan_relocation' AND target_place_id IS NOT NULL)
            OR (
                project_type = 'recruit_ally'
                AND target_character_entity_id IS NOT NULL
            )
        );

-- No relocation data rewrite is needed: migration 074 already guarantees its
-- stages and completion target, and its rows predate the new nullable character
-- target column. Adding the constraints above validates those rows unchanged.

COMMENT ON COLUMN character_project_states.target_character_entity_id IS
    'Character entity chosen when a character-targeted project starts; required for RECRUIT_ALLY and forbidden for PLAN_RELOCATION.';
COMMENT ON TABLE character_project_states IS
    'Additive Orrery project lifecycle projection. Supports PLAN_RELOCATION and RECRUIT_ALLY with a one-open-project-per-character budget; completed relocation hands off to character_travel_states while completed recruitment bestows an outbound ally tag and canonical actor-to-target ally relationship.';
COMMENT ON COLUMN character_project_states.project_type IS
    'Locked project vocabulary. Permits plan_relocation and recruit_ally; each type has an explicit stage ladder and target discipline.';
COMMENT ON COLUMN character_project_states.stage IS
    'Type-specific ladder: PLAN_RELOCATION uses saving/scouting/committing; RECRUIT_ALLY uses sounding_out/earning_trust/sealing_commitment.';
COMMENT ON COLUMN character_project_states.target_place_id IS
    'Place target used only by PLAN_RELOCATION, chosen during scouting and required before relocation completion.';
COMMENT ON CONSTRAINT character_project_states_project_type_check
    ON character_project_states IS
    'Closed project-type vocabulary extended by migration 077 for RECRUIT_ALLY.';
COMMENT ON CONSTRAINT character_project_states_stage_by_type_check
    ON character_project_states IS
    'Enforces the independent stage ladder declared for each supported project type.';
COMMENT ON CONSTRAINT character_project_states_target_by_type_check
    ON character_project_states IS
    'Enforces typed targets: relocation may use only a place; recruitment must use exactly its character target from project start.';
COMMENT ON CONSTRAINT character_project_states_completed_target_check
    ON character_project_states IS
    'Completed projects must retain the target required by their project type.';

INSERT INTO event_types (type, category, severity, description)
VALUES
    (
        'recruit_ally_started',
        'project',
        'moderate',
        'The actor chose a plausible contact and began sounding them out as a committed ally.'
    ),
    (
        'recruit_ally_progressed',
        'project',
        'minor',
        'The actor made routine progress toward recruiting the chosen character.'
    ),
    (
        'recruit_ally_milestone',
        'project',
        'moderate',
        'The recruitment crossed a boundary in its sounding-out, trust-building, or commitment ladder.'
    ),
    (
        'recruit_ally_stalled',
        'project',
        'minor',
        'Neglect cost the actor ground in an ongoing recruitment.'
    ),
    (
        'recruit_ally_abandoned',
        'project',
        'moderate',
        'The actor abandoned a recruitment after repeated stalls, excessive delay, or a hostile turn.'
    ),
    (
        'recruit_ally_completed',
        'project',
        'moderate',
        'The chosen recruit accepted the commitment and became the actor''s outbound ally.'
    )
ON CONFLICT (type) DO NOTHING;
