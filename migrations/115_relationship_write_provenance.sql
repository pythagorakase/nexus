-- Attribute all relationship writes and queue every character rung crossing.
SET LOCAL nexus.write_producer = 'migration';

ALTER TABLE relationship_versions ADD COLUMN producer text;
ALTER TABLE relationship_versions ADD COLUMN delta numeric;
ALTER TABLE relationship_versions ADD COLUMN valence_after numeric;
UPDATE relationship_versions SET producer = 'unattributed_pre_115';
ALTER TABLE relationship_versions ALTER COLUMN producer SET NOT NULL;
ALTER TABLE relationship_versions ADD CONSTRAINT relationship_versions_producer_check
    CHECK (producer IN ('gaia', 'drift_event', 'project_milestone', 'package',
        'trait_compiler', 'retrograde', 'migration', 'manual', 'unattributed_pre_115'));
ALTER TABLE relationship_versions DROP CONSTRAINT relationship_versions_operation_check;
ALTER TABLE relationship_versions ADD CONSTRAINT relationship_versions_operation_check
    CHECK (operation IN ('insert', 'update', 'delete'));
COMMENT ON COLUMN relationship_versions.producer IS
    'Explicit transaction-local nexus.write_producer; unattributed_pre_115 identifies historical rows only.';
COMMENT ON COLUMN relationship_versions.delta IS
    'Canonical character valence_after minus the pre-image valence on UPDATE; NULL for inserts, deletes, and faction relationships.';
COMMENT ON COLUMN relationship_versions.valence_after IS
    'Canonical character valence after INSERT or UPDATE; NULL for deletes and faction relationships.';
COMMENT ON COLUMN relationship_versions.old_row IS
    'Full pre-image for UPDATE and DELETE; inserted row for INSERT so replay can remove its natural key.';

CREATE TABLE orrery_drift_drains (
    tick_chunk_id bigint PRIMARY KEY REFERENCES narrative_chunks(id),
    drained_at timestamptz NOT NULL DEFAULT now(),
    applied_deltas integer NOT NULL
);
COMMENT ON TABLE orrery_drift_drains IS 'Once-per-tick relationship event and project delta drain ledger; not narrative world events.';
COMMENT ON COLUMN orrery_drift_drains.tick_chunk_id IS 'Accepted narrative chunk whose relationship drain completed.';
COMMENT ON COLUMN orrery_drift_drains.drained_at IS 'Wall-clock drain completion timestamp, or earliest migrated marker timestamp.';
COMMENT ON COLUMN orrery_drift_drains.applied_deltas IS 'Number of attributed edge writes applied; historical markers carry their edges_touched count.';
INSERT INTO orrery_drift_drains (tick_chunk_id, drained_at, applied_deltas)
SELECT tick_chunk_id, min(created_at), sum(coalesce((payload->>'edges_touched')::integer, 0))::integer
FROM world_events WHERE event_type = 'relationship_drift_drained'
GROUP BY tick_chunk_id;
DELETE FROM world_event_entities WHERE event_id IN (
    SELECT id FROM world_events WHERE event_type = 'relationship_drift_drained'
);
DELETE FROM world_events WHERE event_type = 'relationship_drift_drained';
DELETE FROM event_types WHERE type = 'relationship_drift_drained';

CREATE TABLE relationship_milestone_queue (
    version_id bigint PRIMARY KEY REFERENCES relationship_versions(id) ON DELETE CASCADE,
    event_id bigint UNIQUE REFERENCES world_events(id) ON DELETE SET NULL
);
COMMENT ON TABLE relationship_milestone_queue IS
    'Trigger-detected rung crossings for every producer. Shared consumer emits event and configured claim atomically; pre-story crossings wait for an accepted chunk.';
COMMENT ON COLUMN relationship_milestone_queue.version_id IS 'Relationship UPDATE version that crossed a canonical rung.';
COMMENT ON COLUMN relationship_milestone_queue.event_id IS 'Emitted relationship_drift_milestone event; NULL while pending.';

CREATE OR REPLACE FUNCTION fn_version_relationship_row()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    chunk_setting text := nullif(current_setting('nexus.source_chunk_id', true), '');
    producer_setting text := nullif(current_setting('nexus.write_producer', true), '');
    version_id bigint;
    before_valence numeric;
    after_valence numeric;
BEGIN
    IF producer_setting IS NULL OR producer_setting NOT IN (
        'gaia', 'drift_event', 'project_milestone', 'package',
        'trait_compiler', 'retrograde', 'migration', 'manual'
    ) THEN
        RAISE EXCEPTION 'Missing or invalid nexus.write_producer: %', producer_setting;
    END IF;
    IF TG_TABLE_NAME = 'character_relationships' THEN
        IF TG_OP <> 'INSERT' THEN before_valence := OLD.valence_current; END IF;
        IF TG_OP <> 'DELETE' THEN after_valence := NEW.valence_current; END IF;
    END IF;
    INSERT INTO relationship_versions (
        relationship_table, operation, old_row, source_chunk_id,
        producer, delta, valence_after
    ) VALUES (
        TG_TABLE_NAME, lower(TG_OP),
        CASE WHEN TG_OP = 'INSERT' THEN to_jsonb(NEW) ELSE to_jsonb(OLD) END,
        chunk_setting::bigint, producer_setting,
        after_valence - before_valence, after_valence
    ) RETURNING id INTO version_id;
    IF TG_OP = 'UPDATE' AND round(before_valence * 5.5) <> round(after_valence * 5.5) THEN
        INSERT INTO relationship_milestone_queue (version_id) VALUES (version_id);
    END IF;
    RETURN NULL; -- AFTER trigger: observe the final canonical value after derivation.
END;
$$;
COMMENT ON FUNCTION fn_version_relationship_row() IS
    'Fail-closed write attribution and all-producer rung detection. Derivation inherits the caller producer; never supplies a default.';
DROP TRIGGER trg_version_character_relationships ON character_relationships;
CREATE TRIGGER trg_version_character_relationships
    AFTER INSERT OR UPDATE OR DELETE ON character_relationships
    FOR EACH ROW EXECUTE FUNCTION fn_version_relationship_row();
DROP TRIGGER trg_version_faction_character_relationships ON faction_character_relationships;
CREATE TRIGGER trg_version_faction_character_relationships
    AFTER INSERT OR UPDATE OR DELETE ON faction_character_relationships
    FOR EACH ROW EXECUTE FUNCTION fn_version_relationship_row();
DROP TRIGGER trg_version_faction_relationships ON faction_relationships;
CREATE TRIGGER trg_version_faction_relationships
    AFTER INSERT OR UPDATE OR DELETE ON faction_relationships
    FOR EACH ROW EXECUTE FUNCTION fn_version_relationship_row();
