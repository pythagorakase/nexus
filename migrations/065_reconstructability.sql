-- 065_reconstructability.sql
--
-- The "sufficient-from-now-on" reconstruction bar from
-- docs/orrery_audit_dashboard_notes.md (step 7b-7d), per the decisions on
-- issue #426: log every Skald-side scalar write (7b), JSONB state
-- checkpoints auto-taken in the commit path plus a retro-fitted genesis
-- (7c), and trigger-based relationship versioning that cannot be forgotten
-- by a future runtime writer (7d).

-- 7b. Skald-side chunk-keyed delta log. Orrery's half is already
--     event-sourced in orrery_resolutions.state_delta; this is the peer
--     ledger for the on-screen commit path, which previously moved
--     characters and set activity with no record of any kind.
CREATE TABLE IF NOT EXISTS state_delta_log (
    id              bigserial PRIMARY KEY,
    source_chunk_id bigint NOT NULL REFERENCES narrative_chunks(id),
    writer          text NOT NULL
        CHECK (writer IN ('skald_state_update', 'wizard_seed')),
    entity_id       bigint REFERENCES entities(id),
    field           text NOT NULL,
    old_value       jsonb,
    new_value       jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE state_delta_log IS
    'Chunk-keyed ledger of every Skald-side scalar state write (policy: log everything, including writes that repeat the current value). Replay from a checkpoint = apply orrery_resolutions.state_delta plus these rows in chunk order. Rows exist only for chunks committed after migration 065.';
COMMENT ON COLUMN state_delta_log.field IS
    'Qualified column the write touched, e.g. characters.current_location.';
COMMENT ON COLUMN state_delta_log.old_value IS
    'Prior value when the writer captured it; NULL means not captured (the Skald logger records new_value only), not "was NULL".';

CREATE INDEX IF NOT EXISTS ix_state_delta_log_source_chunk_id
    ON state_delta_log (source_chunk_id);
CREATE INDEX IF NOT EXISTS ix_state_delta_log_entity_id
    ON state_delta_log (entity_id);

-- 7c. JSONB state checkpoints: a full queryable snapshot of the mutable
--     state surface, bounding replay cost and giving mature slots an
--     explicit instrumentation-era boundary (exact after, approximate
--     before). "genesis" checkpoints are retro-fitted at migration time for
--     existing slots — the true wizard-era genesis is unrecoverable.
CREATE TABLE IF NOT EXISTS state_checkpoints (
    id            bigserial PRIMARY KEY,
    chunk_id      bigint REFERENCES narrative_chunks(id),
    label         text NOT NULL
        CHECK (label IN ('genesis', 'interval', 'manual')),
    state         jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (chunk_id, label)
);

COMMENT ON TABLE state_checkpoints IS
    'Point-in-time JSONB snapshots of the mutable world-state surface (tags, pair tags, character scalars, relationships, needs, travel, routine anchors, faction memberships). Auto-taken every [orrery.reconstruction] checkpoint_interval_chunks accepted chunks; "genesis" marks the instrumentation-era boundary for slots older than migration 065.';
COMMENT ON COLUMN state_checkpoints.chunk_id IS
    'Head chunk at snapshot time; NULL only for empty slots checkpointed before any chunk exists.';

CREATE INDEX IF NOT EXISTS ix_state_checkpoints_chunk_id
    ON state_checkpoints (chunk_id);

-- 7d. Relationship versioning, trigger-enforced (issue #426 decision):
--     the three current-state relationship tables are mutable and
--     unversioned; the first runtime writer would destroy history on
--     contact. Row-level triggers write the OLD row before every UPDATE or
--     DELETE, attributed to the committing chunk via the nexus.source_chunk_id
--     session setting when the writer provides one.
CREATE TABLE IF NOT EXISTS relationship_versions (
    id                 bigserial PRIMARY KEY,
    relationship_table text NOT NULL
        CHECK (relationship_table IN (
            'character_relationships',
            'faction_character_relationships',
            'faction_relationships'
        )),
    operation          text NOT NULL CHECK (operation IN ('update', 'delete')),
    -- The three tables use composite natural keys and have no surrogate id;
    -- old_row carries the full pre-image including the key columns.
    old_row            jsonb NOT NULL,
    source_chunk_id    bigint REFERENCES narrative_chunks(id),
    created_at         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE relationship_versions IS
    'Append-only sidecar of superseded relationship rows, written by row-level triggers on the three current-state relationship tables. source_chunk_id comes from the nexus.source_chunk_id session setting (set by the commit transaction); NULL means the write happened outside an attributed commit.';

CREATE INDEX IF NOT EXISTS ix_relationship_versions_table_created
    ON relationship_versions (relationship_table, created_at);

CREATE OR REPLACE FUNCTION fn_version_relationship_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    chunk_setting text := current_setting('nexus.source_chunk_id', true);
BEGIN
    INSERT INTO relationship_versions (
        relationship_table, operation, old_row, source_chunk_id
    ) VALUES (
        TG_TABLE_NAME,
        lower(TG_OP),
        to_jsonb(OLD),
        CASE
            WHEN chunk_setting IS NULL OR chunk_setting = '' THEN NULL
            ELSE chunk_setting::bigint
        END
    );
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_version_relationship_row() IS
    'Writes the pre-image of any relationship row mutation into relationship_versions. Trigger-enforced so a future runtime relationship writer cannot forget to version.';

DROP TRIGGER IF EXISTS trg_version_character_relationships
    ON character_relationships;
CREATE TRIGGER trg_version_character_relationships
    BEFORE UPDATE OR DELETE ON character_relationships
    FOR EACH ROW EXECUTE FUNCTION fn_version_relationship_row();

DROP TRIGGER IF EXISTS trg_version_faction_character_relationships
    ON faction_character_relationships;
CREATE TRIGGER trg_version_faction_character_relationships
    BEFORE UPDATE OR DELETE ON faction_character_relationships
    FOR EACH ROW EXECUTE FUNCTION fn_version_relationship_row();

DROP TRIGGER IF EXISTS trg_version_faction_relationships
    ON faction_relationships;
CREATE TRIGGER trg_version_faction_relationships
    BEFORE UPDATE OR DELETE ON faction_relationships
    FOR EACH ROW EXECUTE FUNCTION fn_version_relationship_row();
