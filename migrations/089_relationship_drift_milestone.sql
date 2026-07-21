-- 089_relationship_drift_milestone.sql
--
-- Register the visibility event emitted when continuous relationship drift
-- crosses a derived Stage-1 valence rung. The runtime drain owns all movement;
-- this migration intentionally makes no schema changes.

INSERT INTO event_types (type, category, severity, description)
VALUES (
    'relationship_drift_milestone',
    'emotional',
    'minor',
    'A continuous directed relationship valence crossed a derived rung.'
)
ON CONFLICT (type) DO NOTHING;

COMMENT ON COLUMN event_types.type IS
    'Stable event identifier, including system-emitted relationship drift '
    'milestones registered by migration 089.';
