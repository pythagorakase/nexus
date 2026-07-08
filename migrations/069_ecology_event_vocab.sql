-- 069_ecology_event_vocab.sql
--
-- Event vocabulary for the ecology bundle: the hunting lifecycle
-- (EXTRACT_VENGEANCE's declare/off-ramp branches are the first writer of
-- the `hunting` pair tag) and ACT_ON_INTEL's accumulate-then-spend cycle.

INSERT INTO event_types (type, category, severity, description)
VALUES
    (
        'hunt_declared',
        'threat',
        'moderate',
        'The actor escalated a grudge into an active hunt for the target, applying the outbound hunting pair tag. Consumed by EXTRACT_VENGEANCE''s own pacing cooldowns; the tag itself arms EVADE_PURSUERS/HIDE/WARN_ALLY/PROTECT_KIN.'
    ),
    (
        'hunt_called_off',
        'threat',
        'minor',
        'A hunt went cold: the hunter released the outbound hunting pair tag after a long unproductive stretch. The prey''s suppressed social and routine packages reopen.'
    ),
    (
        'intel_acted_on',
        'intelligence',
        'moderate',
        'Accumulated surveillance was spent: sold onward, used in confrontation, or consolidated. Consumed by ACT_ON_INTEL''s per-target cooldown.'
    )
ON CONFLICT (type) DO NOTHING;
