-- 104_character_experiences.sql
-- Actor-owned deterministic experience seeds and fenced scene rendering jobs.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'character_experience_basis'
    ) THEN
        CREATE TYPE character_experience_basis AS ENUM (
            'participant', 'witness', 'acquisition'
        );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_type
        WHERE typname = 'character_experience_invalidation_status'
    ) THEN
        CREATE TYPE character_experience_invalidation_status AS ENUM (
            'valid', 'invalidated'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS character_experiences (
    id                      bigserial PRIMARY KEY,
    character_entity_id     bigint NOT NULL REFERENCES entities(id),
    anchor_chunk_id         bigint NOT NULL REFERENCES narrative_chunks(id),
    world_event_ids         bigint[] NOT NULL,
    claim_id                bigint REFERENCES claims(id),
    claim_awareness_id      bigint REFERENCES claim_awareness(id),
    basis                   character_experience_basis NOT NULL,
    location_id             bigint REFERENCES places(id),
    world_time              timestamptz,
    seed_summary            text NOT NULL CHECK (btrim(seed_summary) <> ''),
    experience_text         text,
    emotion                 text REFERENCES tags(tag),
    salience                double precision NOT NULL
                                CHECK (salience >= 0.0 AND salience <= 1.0),
    render_model            text,
    renderer_version        text,
    source_digest           text NOT NULL CHECK (btrim(source_digest) <> ''),
    render_generation_id    uuid,
    world_layer             world_layer_type NOT NULL,
    invalidation_status     character_experience_invalidation_status
                                NOT NULL DEFAULT 'valid',
    invalidated_at          timestamptz,
    embedding_generated_at timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    CHECK (cardinality(world_event_ids) > 0),
    CHECK (emotion IS NULL OR emotion IN ('elated', 'sour', 'restless', 'grim')),
    CHECK (
        (basis = 'acquisition' AND claim_id IS NOT NULL
            AND claim_awareness_id IS NOT NULL)
        OR
        (basis <> 'acquisition' AND claim_id IS NULL
            AND claim_awareness_id IS NULL)
    ),
    CHECK (
        (invalidation_status = 'valid' AND invalidated_at IS NULL)
        OR
        (invalidation_status = 'invalidated' AND invalidated_at IS NOT NULL)
    ),
    CHECK (
        (experience_text IS NULL AND render_model IS NULL
            AND renderer_version IS NULL AND render_generation_id IS NULL)
        OR
        (experience_text IS NOT NULL AND btrim(experience_text) <> ''
            AND render_model IS NOT NULL AND renderer_version IS NOT NULL
            AND render_generation_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_character_experiences_seed_identity
    ON character_experiences (
        character_entity_id,
        anchor_chunk_id,
        basis,
        COALESCE(claim_awareness_id, 0)
    );
CREATE INDEX IF NOT EXISTS ix_character_experiences_unrendered
    ON character_experiences (anchor_chunk_id, character_entity_id)
    WHERE experience_text IS NULL AND invalidation_status = 'valid';
CREATE INDEX IF NOT EXISTS ix_character_experiences_world_event_ids
    ON character_experiences USING GIN (world_event_ids);

COMMENT ON TABLE character_experiences IS
    'Actor-owned factual experience seeds and optional subjective first-person renderings; this corpus does not itself grant recall or disclosure.';
COMMENT ON COLUMN character_experiences.id IS
    'Monotonic identity used by rendering and dimension-specific embedding tables.';
COMMENT ON COLUMN character_experiences.character_entity_id IS
    'Entity-spine identity of the character who owns this private experience.';
COMMENT ON COLUMN character_experiences.anchor_chunk_id IS
    'Accepted narrative chunk whose durable events or delivered account formed the seed.';
COMMENT ON COLUMN character_experiences.world_event_ids IS
    'Canonical source event identities; acquisition rows include the delivery event and incident event.';
COMMENT ON COLUMN character_experiences.claim_id IS
    'Exact delivered claim account for an acquisition, never an inference that the character witnessed its incident.';
COMMENT ON COLUMN character_experiences.claim_awareness_id IS
    'Durable told or granted awareness row whose insertion caused an acquisition experience.';
COMMENT ON COLUMN character_experiences.basis IS
    'Participant, verified present witness, or acquisition by being told or granted an account.';
COMMENT ON COLUMN character_experiences.location_id IS
    'Canonical scene or source-event place when one is durably known.';
COMMENT ON COLUMN character_experiences.world_time IS
    'In-world formation time under the two-clocks doctrine.';
COMMENT ON COLUMN character_experiences.seed_summary IS
    'Deterministic factual seed text assembled only from accepted event, roster, and account data.';
COMMENT ON COLUMN character_experiences.experience_text IS
    'Subjective first-person rendering; NULL preserves an unrendered or failed seed for retry.';
COMMENT ON COLUMN character_experiences.emotion IS
    'Optional mechanical mood registered by migration 095; rendering never assigns this value.';
COMMENT ON COLUMN character_experiences.salience IS
    'Deterministic bounded score from branch magnitude, relationship-valence delta, and verified presence duration.';
COMMENT ON COLUMN character_experiences.render_model IS
    'Resolved registry model id used for the successful scene rendering call.';
COMMENT ON COLUMN character_experiences.renderer_version IS
    'Deterministic renderer contract version used to validate and persist the rendering.';
COMMENT ON COLUMN character_experiences.source_digest IS
    'SHA-256 digest of canonical seed inputs used for replay and stale-write fencing.';
COMMENT ON COLUMN character_experiences.render_generation_id IS
    'One UUID shared by every recollection accepted from the same scene-batch provider call.';
COMMENT ON COLUMN character_experiences.world_layer IS
    'Timeline layer copied from the accepted anchor chunk.';
COMMENT ON COLUMN character_experiences.invalidation_status IS
    'Replay-safe validity state; invalidated rows remain durable rather than being deleted.';
COMMENT ON COLUMN character_experiences.invalidated_at IS
    'Database time when replay or timeline repair invalidated this experience.';
COMMENT ON COLUMN character_experiences.embedding_generated_at IS
    'Ironman stamp set only after every active MEMNON model vector is stored successfully.';
COMMENT ON COLUMN character_experiences.created_at IS
    'Database wall-clock time when the deterministic seed was inserted.';

CREATE TABLE IF NOT EXISTS character_experience_jobs (
    id                  bigserial PRIMARY KEY,
    boundary_chunk_id   bigint NOT NULL REFERENCES narrative_chunks(id),
    scene_end_chunk_id  bigint NOT NULL REFERENCES narrative_chunks(id),
    world_layer         world_layer_type NOT NULL,
    experience_ids      bigint[] NOT NULL,
    slot                text NOT NULL,
    state               orrery_job_state NOT NULL DEFAULT 'queued',
    attempts            integer NOT NULL DEFAULT 0,
    available_at        timestamptz NOT NULL DEFAULT now(),
    lease_until         timestamptz,
    locked_by           text,
    lease_nonce         uuid,
    last_error          text,
    model               text NOT NULL,
    source_digest       text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (cardinality(experience_ids) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_character_experience_jobs_boundary
    ON character_experience_jobs (boundary_chunk_id, world_layer);
CREATE INDEX IF NOT EXISTS ix_character_experience_jobs_available
    ON character_experience_jobs (state, available_at);

COMMENT ON TABLE character_experience_jobs IS
    'Owner-fenced asynchronous scene-batch rendering queue for character experience seeds.';
COMMENT ON COLUMN character_experience_jobs.id IS
    'Monotonic scene rendering job identity.';
COMMENT ON COLUMN character_experience_jobs.boundary_chunk_id IS
    'Accepted chunk carrying the scene-reset boundary that made the prior scene renderable.';
COMMENT ON COLUMN character_experience_jobs.scene_end_chunk_id IS
    'Last accepted chunk included in the scene batch.';
COMMENT ON COLUMN character_experience_jobs.world_layer IS
    'Timeline layer fenced at enqueue and completion.';
COMMENT ON COLUMN character_experience_jobs.experience_ids IS
    'Immutable complete set of unrendered seed ids selected for this scene boundary.';
COMMENT ON COLUMN character_experience_jobs.slot IS
    'Save-slot label owning the job.';
COMMENT ON COLUMN character_experience_jobs.state IS
    'Shared Orrery queued, leased, succeeded, failed, or stale-rejected job state.';
COMMENT ON COLUMN character_experience_jobs.attempts IS
    'Number of owner leases acquired for this job.';
COMMENT ON COLUMN character_experience_jobs.available_at IS
    'Database time when a queued retry may be leased.';
COMMENT ON COLUMN character_experience_jobs.lease_until IS
    'Database-clock lease expiry checked by fenced completion and failure writes.';
COMMENT ON COLUMN character_experience_jobs.locked_by IS
    'Worker owner identifier required with lease_nonce for fenced writes.';
COMMENT ON COLUMN character_experience_jobs.lease_nonce IS
    'Fresh UUID stamped at each lease acquisition to reject stale workers.';
COMMENT ON COLUMN character_experience_jobs.last_error IS
    'Most recent rendering or validation failure retained for operational diagnosis.';
COMMENT ON COLUMN character_experience_jobs.model IS
    'Resolved registry model id frozen when the scene job is enqueued.';
COMMENT ON COLUMN character_experience_jobs.source_digest IS
    'SHA-256 digest of the ordered experience id and seed-digest batch.';
COMMENT ON COLUMN character_experience_jobs.created_at IS
    'Database wall-clock time when the boundary job was enqueued.';
COMMENT ON COLUMN character_experience_jobs.updated_at IS
    'Database wall-clock time of the most recent queue state transition.';
