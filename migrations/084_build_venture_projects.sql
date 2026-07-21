-- 084_build_venture_projects.sql
--
-- Extend the Orrery project chassis with BUILD_VENTURE, an actor-only project
-- whose eventual venture remains narrative until completion. The projection
-- therefore carries no place, character, or faction target at any stage.

ALTER TABLE character_project_states
    DROP CONSTRAINT IF EXISTS character_project_states_project_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_stage_by_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_target_by_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_completed_target_check;

ALTER TABLE character_project_states
    ADD CONSTRAINT character_project_states_project_type_check
        CHECK (project_type IN (
            'plan_relocation', 'recruit_ally', 'build_venture'
        )),
    ADD CONSTRAINT character_project_states_stage_by_type_check
        CHECK (
            (project_type = 'plan_relocation'
                AND stage IN ('saving', 'scouting', 'committing'))
            OR
            (project_type = 'recruit_ally'
                AND stage IN (
                    'sounding_out', 'earning_trust', 'sealing_commitment'
                ))
            OR
            (project_type = 'build_venture'
                AND stage IN (
                    'laying_groundwork', 'securing_backing', 'opening_doors'
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
            OR
            (project_type = 'build_venture'
                AND target_place_id IS NULL
                AND target_character_entity_id IS NULL
                AND target_faction_entity_id IS NULL)
        ),
    ADD CONSTRAINT character_project_states_completed_target_check
        CHECK (
            status <> 'completed'
            OR (project_type = 'plan_relocation' AND target_place_id IS NOT NULL)
            OR (
                project_type = 'recruit_ally'
                AND target_character_entity_id IS NOT NULL
            )
            OR (project_type = 'build_venture')
        );

-- Migration 081 deliberately permits an immutable, entry-time faction context
-- for templates that opt into it. The existing project arms retain that
-- optional context, while BUILD_VENTURE explicitly forbids it because the
-- venture does not yet exist as a faction entity during this lifecycle.
COMMENT ON CONSTRAINT character_project_states_project_type_check
    ON character_project_states IS
    'Closed project-type vocabulary extended by migration 084 for BUILD_VENTURE.';
COMMENT ON CONSTRAINT character_project_states_stage_by_type_check
    ON character_project_states IS
    'Enforces independent three-stage ladders for PLAN_RELOCATION, RECRUIT_ALLY, and BUILD_VENTURE.';
COMMENT ON CONSTRAINT character_project_states_target_by_type_check
    ON character_project_states IS
    'Enforces typed targets: relocation forbids character targets, recruitment requires only its character target, and venture building forbids place, character, and faction targets.';
COMMENT ON CONSTRAINT character_project_states_completed_target_check
    ON character_project_states IS
    'Completed relocation and recruitment retain their required targets; BUILD_VENTURE legitimately completes without a target.';

COMMENT ON TABLE character_project_states IS
    'Additive Orrery project lifecycle projection. Supports PLAN_RELOCATION, RECRUIT_ALLY, and actor-only BUILD_VENTURE under one open project per character.';
COMMENT ON COLUMN character_project_states.project_type IS
    'Locked project vocabulary: plan_relocation, recruit_ally, or build_venture.';
COMMENT ON COLUMN character_project_states.stage IS
    'Type-specific three-stage ladder, including BUILD_VENTURE laying_groundwork, securing_backing, and opening_doors.';
COMMENT ON COLUMN character_project_states.target_place_id IS
    'Place target used only by PLAN_RELOCATION; always NULL for RECRUIT_ALLY and BUILD_VENTURE.';
COMMENT ON COLUMN character_project_states.target_character_entity_id IS
    'Character target required by RECRUIT_ALLY; always NULL for PLAN_RELOCATION and BUILD_VENTURE.';
COMMENT ON COLUMN character_project_states.target_faction_entity_id IS
    'Optional immutable entry-time institutional context for templates that bind one; always NULL for BUILD_VENTURE because the venture is not yet an entity.';

INSERT INTO event_types (type, category, severity, description)
VALUES
    (
        'build_venture_started',
        'project',
        'moderate',
        'The actor began laying the groundwork for a business, workshop, or crew.'
    ),
    (
        'build_venture_progressed',
        'project',
        'minor',
        'The actor made routine progress toward opening a venture.'
    ),
    (
        'build_venture_milestone',
        'project',
        'moderate',
        'The venture crossed a boundary in its groundwork, backing, or opening ladder.'
    ),
    (
        'build_venture_stalled',
        'project',
        'minor',
        'Neglect or a setback cost the actor ground while building the venture.'
    ),
    (
        'build_venture_abandoned',
        'project',
        'moderate',
        'The actor abandoned a venture after repeated stalls or excessive delay.'
    ),
    (
        'build_venture_completed',
        'project',
        'moderate',
        'The doors opened on the actor''s venture, leaving the founder with the proprietor role.'
    )
ON CONFLICT (type) DO NOTHING;

-- role.function is the established, non-deprecated category for multi-valued
-- character roles (migration 055). Reassert its registry row without changing
-- the established description or ordering, then register the durable role.
INSERT INTO tag_category_registry (
    category, entity_kind, prompt_order, description,
    deprecated, replacement_categories
) VALUES (
    'role.function',
    'character'::entity_kind,
    40,
    'Multi-valued social or operational function recognized by others.',
    FALSE,
    NULL
)
ON CONFLICT (category, entity_kind) DO NOTHING;

INSERT INTO tags (
    tag, category, is_ephemeral,
    clearance_kind, reapplication_policy, clear_on,
    synonym_for, deprecated, description
) VALUES (
    'proprietor',
    'role.function',
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    'Character role: founder or operator of an opened business, workshop, or crew; bestowed when BUILD_VENTURE completes.'
)
ON CONFLICT (tag) DO NOTHING;
