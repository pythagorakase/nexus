-- 086_court_patron_projects.sql
--
-- Extend the Orrery project chassis with COURT_PATRON, a character-targeted
-- effort to earn the favor of a named power.

ALTER TABLE character_project_states
    DROP CONSTRAINT IF EXISTS character_project_states_project_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_stage_by_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_target_by_type_check,
    DROP CONSTRAINT IF EXISTS character_project_states_completed_target_check;

ALTER TABLE character_project_states
    ADD CONSTRAINT character_project_states_project_type_check
        CHECK (project_type IN (
            'plan_relocation', 'recruit_ally', 'build_venture',
            'pursue_romance', 'court_patron'
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
        );

COMMENT ON CONSTRAINT character_project_states_project_type_check
    ON character_project_states IS
    'Closed project-type vocabulary extended by migration 086 for COURT_PATRON.';
COMMENT ON CONSTRAINT character_project_states_stage_by_type_check
    ON character_project_states IS
    'Enforces independent three-stage ladders for PLAN_RELOCATION, RECRUIT_ALLY, BUILD_VENTURE, PURSUE_ROMANCE, and COURT_PATRON.';
COMMENT ON CONSTRAINT character_project_states_target_by_type_check
    ON character_project_states IS
    'Enforces typed targets: COURT_PATRON requires only its character patron and forbids place and faction targets.';
COMMENT ON CONSTRAINT character_project_states_completed_target_check
    ON character_project_states IS
    'Completed targeted projects retain their required target; COURT_PATRON retains its named patron character.';

COMMENT ON TABLE character_project_states IS
    'Additive Orrery project lifecycle projection. Supports relocation, recruitment, venture-building, named-character courtship, and named-character patronage under one open project per character.';
COMMENT ON COLUMN character_project_states.project_type IS
    'Locked project vocabulary: plan_relocation, recruit_ally, build_venture, pursue_romance, or court_patron.';
COMMENT ON COLUMN character_project_states.stage IS
    'Type-specific three-stage ladder, including COURT_PATRON gaining_notice, proving_worth, and securing_favor.';
COMMENT ON COLUMN character_project_states.target_place_id IS
    'Place target used only by PLAN_RELOCATION; always NULL for COURT_PATRON.';
COMMENT ON COLUMN character_project_states.target_character_entity_id IS
    'Character target required by RECRUIT_ALLY, PURSUE_ROMANCE, and COURT_PATRON.';
COMMENT ON COLUMN character_project_states.target_faction_entity_id IS
    'Optional immutable institutional context for older project arms; always NULL for BUILD_VENTURE, PURSUE_ROMANCE, and COURT_PATRON.';

INSERT INTO event_types (type, category, severity, description)
VALUES
    ('court_patron_started', 'project', 'moderate',
     'The actor began working to gain the notice of a named patron.'),
    ('court_patron_progressed', 'project', 'minor',
     'The actor made routine progress toward earning a patron''s favor.'),
    ('court_patron_milestone', 'project', 'moderate',
     'The effort to court a patron crossed a boundary of notice or proven worth.'),
    ('court_patron_stalled', 'project', 'minor',
     'Neglect cost the actor ground in the effort to secure a patron''s favor.'),
    ('court_patron_abandoned', 'project', 'moderate',
     'The actor abandoned an effort to court a patron after delay or rejection.'),
    ('court_patron_completed', 'project', 'moderate',
     'The named patron granted favor and accepted the actor''s obligation.')
ON CONFLICT (type) DO NOTHING;
