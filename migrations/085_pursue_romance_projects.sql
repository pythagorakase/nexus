-- 085_pursue_romance_projects.sql
--
-- Extend the Orrery project chassis with PURSUE_ROMANCE, a character-targeted
-- courtship whose named target is bound from entry through completion.

ALTER TABLE character_project_states
    DROP CONSTRAINT IF EXISTS character_project_states_project_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_stage_by_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_target_by_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_completed_target_check;

ALTER TABLE character_project_states
    ADD CONSTRAINT character_project_states_project_type_check
        CHECK (project_type IN (
            'plan_relocation', 'recruit_ally', 'build_venture',
            'pursue_romance'
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
            OR
            (project_type = 'pursue_romance'
                AND stage IN (
                    'testing_waters', 'growing_closer', 'declaring_intentions'
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
            OR
            (project_type = 'pursue_romance'
                AND target_place_id IS NULL
                AND target_character_entity_id IS NOT NULL
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
            OR (
                project_type = 'pursue_romance'
                AND target_character_entity_id IS NOT NULL
            )
        );

-- Migration 081 permits optional immutable faction context for older project
-- arms. PURSUE_ROMANCE follows RECRUIT_ALLY's character-target discipline but
-- explicitly forbids faction context so its two parties remain unambiguous.
COMMENT ON CONSTRAINT character_project_states_project_type_check
    ON character_project_states IS
    'Closed project-type vocabulary extended by migration 085 for PURSUE_ROMANCE.';
COMMENT ON CONSTRAINT character_project_states_stage_by_type_check
    ON character_project_states IS
    'Enforces independent three-stage ladders for PLAN_RELOCATION, RECRUIT_ALLY, BUILD_VENTURE, and PURSUE_ROMANCE.';
COMMENT ON CONSTRAINT character_project_states_target_by_type_check
    ON character_project_states IS
    'Enforces typed targets: romance requires only its character target and forbids place and faction targets.';
COMMENT ON CONSTRAINT character_project_states_completed_target_check
    ON character_project_states IS
    'Completed targeted projects retain their required target; PURSUE_ROMANCE retains its named character.';

COMMENT ON TABLE character_project_states IS
    'Additive Orrery project lifecycle projection. Supports relocation, recruitment, venture-building, and named-character courtship under one open project per character.';
COMMENT ON COLUMN character_project_states.project_type IS
    'Locked project vocabulary: plan_relocation, recruit_ally, build_venture, or pursue_romance.';
COMMENT ON COLUMN character_project_states.stage IS
    'Type-specific three-stage ladder, including PURSUE_ROMANCE testing_waters, growing_closer, and declaring_intentions.';
COMMENT ON COLUMN character_project_states.target_place_id IS
    'Place target used only by PLAN_RELOCATION; always NULL for RECRUIT_ALLY, BUILD_VENTURE, and PURSUE_ROMANCE.';
COMMENT ON COLUMN character_project_states.target_character_entity_id IS
    'Character target required by RECRUIT_ALLY and PURSUE_ROMANCE; always NULL for PLAN_RELOCATION and BUILD_VENTURE.';
COMMENT ON COLUMN character_project_states.target_faction_entity_id IS
    'Optional immutable entry-time institutional context for templates that bind one; always NULL for BUILD_VENTURE and PURSUE_ROMANCE.';

INSERT INTO event_types (type, category, severity, description)
VALUES
    ('pursue_romance_started', 'project', 'moderate',
     'The actor began testing the waters of a courtship with a named character.'),
    ('pursue_romance_progressed', 'project', 'minor',
     'The actor made routine progress in an ongoing courtship.'),
    ('pursue_romance_milestone', 'project', 'moderate',
     'The courtship crossed a boundary in closeness or declared intention.'),
    ('pursue_romance_stalled', 'project', 'minor',
     'Neglect or uncertainty cost the actor ground in an ongoing courtship.'),
    ('pursue_romance_abandoned', 'project', 'moderate',
     'The actor abandoned a courtship after rebuff, repeated stalls, or delay.'),
    ('pursue_romance_completed', 'project', 'moderate',
     'Mutual warmth answered the declaration and established a romantic relationship.')
ON CONFLICT (type) DO NOTHING;
