-- 087_seek_redemption_projects.sql
--
-- Extend the Orrery project chassis with SEEK_REDEMPTION, a character-targeted
-- effort to make amends to a named wronged party.

ALTER TABLE character_project_states
    DROP CONSTRAINT IF EXISTS character_project_states_project_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_stage_by_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_target_by_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_completed_target_check;

ALTER TABLE character_project_states
    ADD CONSTRAINT character_project_states_project_type_check
        CHECK (project_type IN (
            'plan_relocation', 'recruit_ally', 'build_venture',
            'pursue_romance', 'court_patron', 'seek_redemption'
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
            OR
            (project_type = 'court_patron'
                AND stage IN (
                    'gaining_notice', 'proving_worth', 'securing_favor'
                ))
            OR
            (project_type = 'seek_redemption'
                AND stage IN (
                    'owning_the_wrong', 'making_amends', 'earning_forgiveness'
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
            OR
            (project_type = 'court_patron'
                AND target_place_id IS NULL
                AND target_character_entity_id IS NOT NULL
                AND target_faction_entity_id IS NULL)
            OR
            (project_type = 'seek_redemption'
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
            OR (
                project_type = 'court_patron'
                AND target_character_entity_id IS NOT NULL
            )
            OR (
                project_type = 'seek_redemption'
                AND target_character_entity_id IS NOT NULL
            )
        );

COMMENT ON CONSTRAINT character_project_states_project_type_check
    ON character_project_states IS
    'Closed project-type vocabulary extended by migration 087 for SEEK_REDEMPTION.';
COMMENT ON CONSTRAINT character_project_states_stage_by_type_check
    ON character_project_states IS
    'Enforces independent three-stage ladders for all six Orrery project types.';
COMMENT ON CONSTRAINT character_project_states_target_by_type_check
    ON character_project_states IS
    'Enforces typed targets: SEEK_REDEMPTION requires only its wronged character and forbids place and faction targets.';
COMMENT ON CONSTRAINT character_project_states_completed_target_check
    ON character_project_states IS
    'Completed targeted projects retain their required target; SEEK_REDEMPTION retains its wronged party.';

COMMENT ON TABLE character_project_states IS
    'Additive Orrery project lifecycle projection. Supports relocation, recruitment, venture-building, romance, patronage, and reconciliation under one open project per character.';
COMMENT ON COLUMN character_project_states.project_type IS
    'Locked project vocabulary including seek_redemption as the sixth project type.';
COMMENT ON COLUMN character_project_states.stage IS
    'Type-specific three-stage ladder, including SEEK_REDEMPTION owning_the_wrong, making_amends, and earning_forgiveness.';
COMMENT ON COLUMN character_project_states.target_place_id IS
    'Place target used only by PLAN_RELOCATION; always NULL for SEEK_REDEMPTION.';
COMMENT ON COLUMN character_project_states.target_character_entity_id IS
    'Character target required by RECRUIT_ALLY, PURSUE_ROMANCE, COURT_PATRON, and SEEK_REDEMPTION.';
COMMENT ON COLUMN character_project_states.target_faction_entity_id IS
    'Optional immutable institutional context for older project arms; always NULL for BUILD_VENTURE, PURSUE_ROMANCE, COURT_PATRON, and SEEK_REDEMPTION.';

INSERT INTO event_types (type, category, severity, description)
VALUES
    ('seek_redemption_started', 'project', 'moderate',
     'The actor began making amends to a named party they had wronged.'),
    ('seek_redemption_progressed', 'project', 'minor',
     'The actor made routine progress toward repairing a past wrong.'),
    ('seek_redemption_milestone', 'project', 'moderate',
     'The attempt at amends crossed a boundary of ownership or repair.'),
    ('seek_redemption_stalled', 'project', 'minor',
     'Neglect cost the actor ground in their attempt to make amends.'),
    ('seek_redemption_abandoned', 'project', 'moderate',
     'The actor abandoned an attempt at reconciliation after delay or rejection.'),
    ('seek_redemption_completed', 'project', 'moderate',
     'The wronged party accepted the actor''s amends without erasing the past.')
ON CONFLICT (type) DO NOTHING;
