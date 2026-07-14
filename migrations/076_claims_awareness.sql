-- 076_claims_awareness.sql
--
-- Epistemics v1: event-anchored claims and binary character awareness.

CREATE TABLE IF NOT EXISTS claims (
    id                      bigserial PRIMARY KEY,
    world_event_id          bigint NOT NULL REFERENCES world_events(id),
    summary                 text NOT NULL,
    scope                   text NOT NULL
        CHECK (scope IN ('common', 'bounded', 'private')),
    source_chunk_id         bigint REFERENCES narrative_chunks(id),
    source_resolution_id    bigint REFERENCES orrery_resolutions(id),
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_claims_world_event_v1
    ON claims (world_event_id)
    WHERE world_event_id IS NOT NULL;

COMMENT ON TABLE claims IS
    'Epistemics v1 facts, each anchored to exactly one canonical world event. Scope is mutable audience policy; all other fields are append-only.';
COMMENT ON COLUMN claims.id IS
    'Monotonic identifier for one tracked claim.';
COMMENT ON COLUMN claims.world_event_id IS
    'Canonical world event anchoring this claim. V1 permits at most one claim per event.';
COMMENT ON COLUMN claims.summary IS
    'Mechanically generated human-readable statement of the tracked fact.';
COMMENT ON COLUMN claims.scope IS
    'Mutable audience policy: common is implicitly known by all; bounded and private require an awareness row on the v1 read side.';
COMMENT ON COLUMN claims.source_chunk_id IS
    'Narrative chunk provenance for the event or explicit claim-producing operation, when available.';
COMMENT ON COLUMN claims.source_resolution_id IS
    'Orrery resolution provenance when a live resolver applier minted the claim.';
COMMENT ON COLUMN claims.created_at IS
    'Database wall-clock time when the claim row was created.';

CREATE TABLE IF NOT EXISTS claim_awareness (
    id                          bigserial PRIMARY KEY,
    claim_id                    bigint NOT NULL REFERENCES claims(id)
                                    ON DELETE CASCADE,
    character_entity_id         bigint NOT NULL REFERENCES entities(id),
    source_tier                 text NOT NULL
        CHECK (source_tier IN ('participant', 'witness', 'told', 'granted')),
    immediate_source_entity_id  bigint REFERENCES entities(id),
    root_source_entity_id       bigint REFERENCES entities(id),
    channel                     text,
    acquired_at_world_time      timestamptz,
    source_chunk_id             bigint REFERENCES narrative_chunks(id),
    created_at                  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (claim_id, character_entity_id)
);

COMMENT ON TABLE claim_awareness IS
    'Append-only Epistemics v1 binary possession rows, one per claim and character knower.';
COMMENT ON COLUMN claim_awareness.id IS
    'Monotonic identifier for one character acquisition of a claim.';
COMMENT ON COLUMN claim_awareness.claim_id IS
    'Tracked claim the character knows; deleting the claim cascades only for referential integrity, while v1 APIs expose no delete.';
COMMENT ON COLUMN claim_awareness.character_entity_id IS
    'Entity spine id of the character holding awareness.';
COMMENT ON COLUMN claim_awareness.source_tier IS
    'Acquisition tier: participant, witness, told, or granted.';
COMMENT ON COLUMN claim_awareness.immediate_source_entity_id IS
    'Entity who directly transmitted the claim; required for told and NULL for participant, witness, and granted.';
COMMENT ON COLUMN claim_awareness.root_source_entity_id IS
    'Original source entity when known; NULL when no origin is modeled.';
COMMENT ON COLUMN claim_awareness.channel IS
    'Free-vocabulary acquisition channel such as overheard or message.';
COMMENT ON COLUMN claim_awareness.acquired_at_world_time IS
    'In-world acquisition timestamp under the two-clocks doctrine.';
COMMENT ON COLUMN claim_awareness.source_chunk_id IS
    'Narrative chunk provenance for the acquisition, when available.';
COMMENT ON COLUMN claim_awareness.created_at IS
    'Database wall-clock time when the awareness row was created.';
