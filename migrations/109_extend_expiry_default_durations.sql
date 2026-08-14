-- Registry-owned defaults for time-cleared extend-expiry tag applications.

ALTER TABLE tags
    ADD COLUMN IF NOT EXISTS default_duration interval;

COMMENT ON COLUMN tags.default_duration IS
    'Default world-clock duration for first application of a time-cleared tag. '
    'NULL means no registry duration; semantic- and event-cleared tags remain '
    'without an expiry.';

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'tags'::regclass
          AND conname = 'tags_default_duration_time_check'
    ) THEN
        ALTER TABLE tags
            ADD CONSTRAINT tags_default_duration_time_check
            CHECK (
                default_duration IS NULL
                OR (
                    clearance_kind IS NOT DISTINCT FROM
                        'time'::entity_tag_clearance_kind
                    AND default_duration > interval '0 seconds'
                )
            );
    END IF;
END
$migration$;

COMMENT ON CONSTRAINT tags_default_duration_time_check ON tags IS
    'Registry default durations must be positive and belong only to '
    'time-cleared tags.';

DO $migration$
DECLARE
    invalid_tags text;
BEGIN
    WITH expected(tag) AS (
        VALUES
            ('intoxicated:stimulant'),
            ('intoxicated:depressant'),
            ('intoxicated:hallucinogen'),
            ('intoxicated:dissociative')
    )
    SELECT string_agg(expected.tag, ', ' ORDER BY expected.tag)
    INTO invalid_tags
    FROM expected
    LEFT JOIN tags AS registry USING (tag)
    WHERE registry.id IS NULL
       OR registry.clearance_kind IS DISTINCT FROM
            'time'::entity_tag_clearance_kind
       OR registry.reapplication_policy IS DISTINCT FROM
            'extend_expiry'::entity_tag_reapplication_policy
       OR registry.deprecated
       OR registry.synonym_for IS NOT NULL;

    IF invalid_tags IS NOT NULL THEN
        RAISE EXCEPTION
            'Migration 109 expected canonical time-cleared extend-expiry tags; invalid: %',
            invalid_tags;
    END IF;
END
$migration$;

UPDATE tags AS registry
SET default_duration = defaults.default_duration
FROM (
    VALUES
        ('intoxicated:stimulant', interval '6 hours'),
        ('intoxicated:depressant', interval '8 hours'),
        ('intoxicated:hallucinogen', interval '8 hours'),
        ('intoxicated:dissociative', interval '6 hours')
) AS defaults(tag, default_duration)
WHERE registry.tag = defaults.tag;
