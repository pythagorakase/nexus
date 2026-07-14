-- 074_plan_relocation_projects.sql
--
-- Additive project-state projection for the PLAN_RELOCATION pilot. Projects
-- deliberately do not generalize travel: they own the initiation/staging
-- ladder and hand a completed relocation to the existing travel.start writer.

CREATE TABLE IF NOT EXISTS character_project_states (
    id                              bigserial PRIMARY KEY,
    character_entity_id             bigint NOT NULL REFERENCES entities(id),
    project_type                    text NOT NULL
        CHECK (project_type IN ('plan_relocation')),
    status                          text NOT NULL
        CHECK (status IN (
            'active', 'paused', 'stalled', 'abandoned', 'completed'
        )),
    stage                           text NOT NULL
        CHECK (stage IN ('saving', 'scouting', 'committing')),
    target_place_id                 bigint REFERENCES places(id),
    progress                        numeric(5,4) NOT NULL DEFAULT 0,
    stall_count                     integer NOT NULL DEFAULT 0,
    next_eligible_at_world_time     timestamptz,
    source_chunk_id                 bigint REFERENCES narrative_chunks(id),
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now(),
    CHECK (progress >= 0 AND progress <= 1),
    CHECK (stall_count >= 0),
    CHECK (status <> 'completed' OR target_place_id IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_character_project_states_open_budget
    ON character_project_states (character_entity_id)
    WHERE status IN ('active', 'paused', 'stalled');

CREATE INDEX IF NOT EXISTS ix_character_project_states_status_due
    ON character_project_states (status, next_eligible_at_world_time);

CREATE INDEX IF NOT EXISTS ix_character_project_states_source_chunk_id
    ON character_project_states (source_chunk_id);

COMMENT ON TABLE character_project_states IS
    'Additive Orrery project lifecycle projection. V1 supports PLAN_RELOCATION only and budgets at most one open project per character; completed relocation hands off to character_travel_states.';
COMMENT ON COLUMN character_project_states.id IS
    'Surrogate identifier for one project lifecycle, retained after completion or abandonment.';
COMMENT ON COLUMN character_project_states.character_entity_id IS
    'Entity spine id for the character pursuing this project.';
COMMENT ON COLUMN character_project_states.project_type IS
    'Locked project vocabulary. V1 permits plan_relocation; new types require a migration and their own stage ladder.';
COMMENT ON COLUMN character_project_states.status IS
    'Lifecycle status: active, paused, stalled, abandoned, or completed.';
COMMENT ON COLUMN character_project_states.stage IS
    'Type-specific PLAN_RELOCATION ladder: saving, scouting, then committing.';
COMMENT ON COLUMN character_project_states.target_place_id IS
    'Candidate relocation destination chosen during scouting; required before completion can hand off to travel.start.';
COMMENT ON COLUMN character_project_states.progress IS
    'Completion ratio for the current stage, clamped from 0.0000 through 1.0000.';
COMMENT ON COLUMN character_project_states.stall_count IS
    'Accumulated setbacks used by configured deterministic abandonment policy.';
COMMENT ON COLUMN character_project_states.next_eligible_at_world_time IS
    'Project-owned world-clock cadence gate. Open projects are due when this timestamp is at or before the tick world time.';
COMMENT ON COLUMN character_project_states.source_chunk_id IS
    'Narrative chunk responsible for the row current projection; project.start records creation provenance and every later transition advances it to that transition tick.';
COMMENT ON COLUMN character_project_states.created_at IS
    'Database timestamp when this project lifecycle row was created.';
COMMENT ON COLUMN character_project_states.updated_at IS
    'Database timestamp when this project lifecycle row was last transitioned.';

-- Every checkpoint predating this additive table truthfully contains no
-- project rows. Extend those documents with an empty genesis section rather
-- than snapshotting present-day rows into historical checkpoints. replay.py
-- also accepts an imported pre-074 checkpoint missing this section and emits
-- an explicit fidelity note.
UPDATE state_checkpoints
SET state = state || jsonb_build_object(
    'character_project_states', ('[]'::jsonb)
)
WHERE NOT state ? 'character_project_states';

INSERT INTO event_types (type, category, severity, description)
VALUES
    (
        'relocation_plan_started',
        'project',
        'moderate',
        'The actor turned sustained local discontent into an explicit relocation plan at the saving stage.'
    ),
    (
        'relocation_plan_progressed',
        'project',
        'minor',
        'The actor made routine progress within the current relocation stage.'
    ),
    (
        'relocation_plan_milestone',
        'project',
        'moderate',
        'The relocation plan crossed a stage boundary in its saving, scouting, or committing ladder.'
    ),
    (
        'relocation_plan_stalled',
        'project',
        'minor',
        'A setback stalled the relocation plan and incremented its accumulated stall count.'
    ),
    (
        'relocation_plan_abandoned',
        'project',
        'moderate',
        'The actor abandoned a relocation plan after repeated stalls or excessive overdue world time.'
    ),
    (
        'relocation_plan_completed',
        'project',
        'moderate',
        'The actor committed to the selected destination; the project completed and handed the journey to travel.start.'
    )
ON CONFLICT (type) DO NOTHING;
