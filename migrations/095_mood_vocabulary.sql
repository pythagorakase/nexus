-- 095_mood_vocabulary.sql
--
-- Mood is the bounded, mechanical affect surface used by Orrery branch gates
-- and stochastic branch-selection bias. Storyteller prose affect remains in
-- characters.emotional_state; the two surfaces are intentionally separate.

-- Exclusive single-slot character category. A new mood replaces the current
-- mood, and time-cleared rows expire on the world clock.
INSERT INTO tag_category_registry (
    category, entity_kind, prompt_order, description,
    deprecated, replacement_categories
) VALUES (
    'mood',
    'character'::entity_kind,
    35,
    'Mechanical affect read by branch-selection bias and mood gates; characters.emotional_state remains the separate Storyteller prose-affect surface.',
    FALSE,
    NULL
)
ON CONFLICT (category, entity_kind) DO NOTHING;

-- Elated: mechanically buoyant disposition.
-- Sour: mechanically resentful or irritable disposition.
-- Restless: mechanically agitated or action-seeking disposition.
-- Grim: mechanically severe or downcast disposition.
INSERT INTO tags (
    tag, category, is_ephemeral,
    clearance_kind, reapplication_policy, clear_on,
    synonym_for, deprecated, description
) VALUES
    (
        'elated', 'mood', TRUE, 'time', 'replace', NULL,
        NULL, FALSE, 'A buoyant mechanical disposition after a favorable turn.'
    ),
    (
        'sour', 'mood', TRUE, 'time', 'replace', NULL,
        NULL, FALSE, 'An irritable mechanical disposition after rejection or insult.'
    ),
    (
        'restless', 'mood', TRUE, 'time', 'replace', NULL,
        NULL, FALSE, 'An agitated mechanical disposition seeking motion or action.'
    ),
    (
        'grim', 'mood', TRUE, 'time', 'replace', NULL,
        NULL, FALSE, 'A severe mechanical disposition after loss or abandonment.'
    )
ON CONFLICT (tag) DO NOTHING;
