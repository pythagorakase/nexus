-- 096_polymorphic_patron.sql
--
-- Widen COURT_PATRON's immutable target to exactly one character or faction.
-- Carry every constraint arm from migration 087 so this remains the complete
-- current definition rather than a partial follow-up.

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
                AND (
                    (target_character_entity_id IS NOT NULL
                     AND target_faction_entity_id IS NULL)
                    OR
                    (target_character_entity_id IS NULL
                     AND target_faction_entity_id IS NOT NULL)
                ))
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
                AND (
                    target_character_entity_id IS NOT NULL
                    OR target_faction_entity_id IS NOT NULL
                )
            )
            OR (
                project_type = 'seek_redemption'
                AND target_character_entity_id IS NOT NULL
            )
        );

COMMENT ON CONSTRAINT character_project_states_project_type_check
    ON character_project_states IS
    'Closed six-type Orrery project vocabulary through migration 096.';
COMMENT ON CONSTRAINT character_project_states_stage_by_type_check
    ON character_project_states IS
    'Enforces independent three-stage ladders for all six Orrery project types.';
COMMENT ON CONSTRAINT character_project_states_target_by_type_check
    ON character_project_states IS
    'Enforces typed targets; COURT_PATRON requires exactly one character or faction patron and forbids place targets.';
COMMENT ON CONSTRAINT character_project_states_completed_target_check
    ON character_project_states IS
    'Completed targeted projects retain their target; COURT_PATRON retains its character or faction patron.';
