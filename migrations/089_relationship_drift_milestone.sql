-- 089_relationship_drift_milestone.sql
--
-- Register the visibility event emitted when continuous relationship drift
-- crosses a derived Stage-1 valence rung and the per-tick drain ledger marker.
-- The runtime drain owns all movement; this migration makes no schema changes.

INSERT INTO event_types (type, category, severity, description)
VALUES
    (
        'relationship_drift_milestone',
        'emotional',
        'minor',
        'A continuous directed relationship valence crossed a derived rung.'
    ),
    (
        'relationship_drift_drained',
        'emotional',
        'minor',
        'The continuous relationship drift drain completed for a tick.'
    )
ON CONFLICT (type) DO NOTHING;

COMMENT ON COLUMN event_types.type IS
    'Stable event identifier; system-emitted event types are registered by '
    'their introducing migrations alongside narrative vocabulary.';
