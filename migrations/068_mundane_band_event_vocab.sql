-- 068_mundane_band_event_vocab.sql
--
-- Event vocabulary for the mundane band (TRAIN, RUN_ERRANDS, STROLL,
-- UPKEEP, RECREATE): genre-neutral low-priority packages covering what
-- people do in the absence of more pressing concerns. Each package's
-- branches emit a single event type consumed by its own since_last
-- cooldown; the cooldowns are deliberately staggered (5-9 ticks) so
-- unpressured actors cycle through varied mundane verbs.

INSERT INTO event_types (type, category, severity, description)
VALUES
    (
        'training_performed',
        'embodied',
        'minor',
        'The actor spent time maintaining a trained discipline — drilling forms, conditioning the body, or practicing a skilled craft''s fundamentals. Consumed by TRAIN''s own cooldown.'
    ),
    (
        'errands_run',
        'routine',
        'minor',
        'The actor handled small acquisitions and obligations: market runs, household provisioning, minor logistics. Consumed by RUN_ERRANDS''s own cooldown.'
    ),
    (
        'stroll_taken',
        'embodied',
        'minor',
        'The actor took an unhurried walk with no consequential destination. Consumed by STROLL''s own cooldown.'
    ),
    (
        'upkeep_done',
        'routine',
        'minor',
        'The actor tended their own space, kit, or tools. Distinct from work_performed/household_work_performed, which are role obligations. Consumed by UPKEEP''s own cooldown.'
    ),
    (
        'recreation_taken',
        'routine',
        'minor',
        'The actor took deliberate unproductive time: games, spectacle, private pastimes. Consumed by RECREATE''s own cooldown.'
    )
ON CONFLICT (type) DO NOTHING;
