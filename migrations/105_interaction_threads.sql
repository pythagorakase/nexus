-- Durable multi-participant interaction threads with fail-closed authorization.

CREATE TABLE IF NOT EXISTS interactions (
    id UUID PRIMARY KEY,
    kind TEXT NOT NULL CHECK (btrim(kind) <> ''),
    executor_namespace TEXT NOT NULL
        CHECK (executor_namespace ~ '^[a-z][a-z0-9_.-]*$'),
    status TEXT NOT NULL
        CHECK (status IN (
            'proposed', 'in_progress', 'completed', 'stopped', 'interrupted'
        )),
    policy JSONB NOT NULL CHECK (jsonb_typeof(policy) = 'object'),
    continuation_id UUID NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    anchor_chunk_id BIGINT NOT NULL
        REFERENCES narrative_chunks(id) ON DELETE RESTRICT,
    timeline_id TEXT NOT NULL CHECK (btrim(timeline_id) <> ''),
    lease_until TIMESTAMPTZ,
    recovery_command_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status <> 'in_progress' OR lease_until IS NOT NULL)
);

COMMENT ON TABLE interactions IS
    'Durable coordination root for a typed, policy-authorized multi-participant interaction.';
COMMENT ON COLUMN interactions.id IS
    'Application-generated stable UUID for the interaction thread.';
COMMENT ON COLUMN interactions.kind IS
    'Consumer-defined interaction kind; this infrastructure does not assign gameplay meaning.';
COMMENT ON COLUMN interactions.executor_namespace IS
    'Validated registry namespace that owns the allowed typed transition vocabulary.';
COMMENT ON COLUMN interactions.status IS
    'Current lifecycle state: proposed, in_progress, completed, stopped, or interrupted.';
COMMENT ON COLUMN interactions.policy IS
    'Declared authorization policy including per-action material payload fields; validated fail-closed by Pydantic.';
COMMENT ON COLUMN interactions.continuation_id IS
    'Stable identity shared by every revision of this interaction continuation.';
COMMENT ON COLUMN interactions.revision IS
    'Monotonic execution or membership revision; authorizations bind to exactly one revision.';
COMMENT ON COLUMN interactions.anchor_chunk_id IS
    'Expected narrative head rechecked against locked canonical narrative and metadata rows at execution.';
COMMENT ON COLUMN interactions.timeline_id IS
    'Expected canonical world-layer timeline identity rechecked under row lock at execution.';
COMMENT ON COLUMN interactions.lease_until IS
    'Required handler lease deadline while in progress; start stamps it and only expired leases are recovery candidates.';
COMMENT ON COLUMN interactions.recovery_command_id IS
    'Recovery command currently claiming an expired interaction while cleanup hooks complete.';
COMMENT ON COLUMN interactions.created_at IS
    'Trusted-handler proposal time.';
COMMENT ON COLUMN interactions.updated_at IS
    'Time of the latest lifecycle, membership, authorization, lease, or recovery mutation.';

CREATE INDEX IF NOT EXISTS idx_interactions_recovery
    ON interactions (lease_until, id)
    WHERE status = 'in_progress' AND lease_until IS NOT NULL;

CREATE TABLE IF NOT EXISTS interaction_participants (
    id BIGSERIAL PRIMARY KEY,
    interaction_id UUID NOT NULL
        REFERENCES interactions(id) ON DELETE RESTRICT,
    participant_entity_id BIGINT NOT NULL
        REFERENCES entities(id) ON DELETE RESTRICT,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    joined_revision BIGINT NOT NULL CHECK (joined_revision >= 1),
    left_at TIMESTAMPTZ,
    left_revision BIGINT CHECK (left_revision IS NULL OR left_revision >= joined_revision),
    CHECK (left_at IS NULL OR left_at >= joined_at),
    CHECK ((left_at IS NULL) = (left_revision IS NULL))
);

COMMENT ON TABLE interaction_participants IS
    'Revisioned historical interaction membership; a new row represents each join interval.';
COMMENT ON COLUMN interaction_participants.id IS
    'Stable identifier for one participant membership interval.';
COMMENT ON COLUMN interaction_participants.interaction_id IS
    'Interaction thread to which this membership interval belongs.';
COMMENT ON COLUMN interaction_participants.participant_entity_id IS
    'Entity-spine participant whose independent exact-envelope authorization is required while active.';
COMMENT ON COLUMN interaction_participants.joined_at IS
    'Time this membership interval became active.';
COMMENT ON COLUMN interaction_participants.joined_revision IS
    'Interaction revision created by this join, or revision one for proposal membership.';
COMMENT ON COLUMN interaction_participants.left_at IS
    'Time this membership interval ended; NULL means currently active.';
COMMENT ON COLUMN interaction_participants.left_revision IS
    'Interaction revision created by leave or terminal closure; NULL while active.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_participants_active
    ON interaction_participants (interaction_id, participant_entity_id)
    WHERE left_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_interaction_participants_history
    ON interaction_participants (
        interaction_id, participant_entity_id, joined_revision, id
    );

CREATE TABLE IF NOT EXISTS interaction_authorizations (
    id BIGSERIAL PRIMARY KEY,
    interaction_id UUID NOT NULL
        REFERENCES interactions(id) ON DELETE RESTRICT,
    participant_entity_id BIGINT NOT NULL
        REFERENCES entities(id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK (action ~ '^[a-z][a-z0-9_.:-]*$'),
    envelope_hash TEXT NOT NULL CHECK (envelope_hash ~ '^[0-9a-f]{64}$'),
    continuation_id UUID NOT NULL,
    interaction_revision BIGINT NOT NULL CHECK (interaction_revision >= 1),
    granted BOOLEAN NOT NULL CHECK (granted IS TRUE),
    granted_by_handler TEXT NOT NULL CHECK (btrim(granted_by_handler) <> ''),
    granted_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revoked_by_handler TEXT,
    CHECK (expires_at > granted_at),
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
    CHECK (
        (revoked_at IS NULL AND revoked_by_handler IS NULL)
        OR (revoked_at IS NOT NULL AND btrim(revoked_by_handler) <> '')
    )
);

COMMENT ON TABLE interaction_authorizations IS
    'Participant-specific positive grants bound to a canonical action, transition, material-term envelope.';
COMMENT ON COLUMN interaction_authorizations.id IS
    'Stable grant record identifier retained after expiry or revocation.';
COMMENT ON COLUMN interaction_authorizations.interaction_id IS
    'Interaction whose exact command envelope this grant may authorize.';
COMMENT ON COLUMN interaction_authorizations.participant_entity_id IS
    'Single participant who explicitly supplied this positive grant.';
COMMENT ON COLUMN interaction_authorizations.action IS
    'Exact policy-declared action authorized by this grant.';
COMMENT ON COLUMN interaction_authorizations.envelope_hash IS
    'SHA-256 of stable canonical JSON over action, transition type, and policy-declared material term values.';
COMMENT ON COLUMN interaction_authorizations.continuation_id IS
    'Continuation identity captured at grant time; mismatches deny as stale.';
COMMENT ON COLUMN interaction_authorizations.interaction_revision IS
    'Interaction revision captured at grant time; membership or lifecycle revision changes deny as stale.';
COMMENT ON COLUMN interaction_authorizations.granted IS
    'Explicit positive grant marker; database constraints reject false or NULL authorization.';
COMMENT ON COLUMN interaction_authorizations.granted_by_handler IS
    'Construction-injected trusted handler identity that recorded the participant grant.';
COMMENT ON COLUMN interaction_authorizations.granted_at IS
    'Beginning of the bounded interval during which the exact-envelope grant can be evaluated.';
COMMENT ON COLUMN interaction_authorizations.expires_at IS
    'Required finite end of the grant validity interval.';
COMMENT ON COLUMN interaction_authorizations.revoked_at IS
    'Immediate revocation time; any non-NULL value denies this grant.';
COMMENT ON COLUMN interaction_authorizations.revoked_by_handler IS
    'Construction-injected trusted handler identity that recorded revocation.';

CREATE INDEX IF NOT EXISTS idx_interaction_authorizations_evaluation
    ON interaction_authorizations (
        interaction_id, action, participant_entity_id,
        interaction_revision DESC, envelope_hash, id DESC
    );

CREATE TABLE IF NOT EXISTS interaction_events (
    id BIGSERIAL PRIMARY KEY,
    interaction_id UUID NOT NULL
        REFERENCES interactions(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'proposed', 'authorized', 'started', 'transitioned',
            'completed', 'stopped', 'interrupted', 'membership_joined',
            'membership_left', 'lease_touched', 'recovery_claimed',
            'cleanup_completed'
        )),
    interaction_revision BIGINT NOT NULL CHECK (interaction_revision >= 1),
    actor_participant_entity_id BIGINT
        REFERENCES entities(id) ON DELETE RESTRICT,
    actor_handler TEXT,
    command_id UUID NOT NULL,
    command_step TEXT NOT NULL CHECK (btrim(command_step) <> ''),
    command_fingerprint TEXT NOT NULL
        CHECK (command_fingerprint ~ '^[0-9a-f]{64}$'),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(payload) = 'object'),
    outcome JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(outcome) = 'object'),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (num_nonnulls(actor_participant_entity_id, actor_handler) <= 1),
    CHECK (actor_handler IS NULL OR btrim(actor_handler) <> '')
);

COMMENT ON TABLE interaction_events IS
    'Immutable command-idempotency, cleanup-completion, and lifecycle replay ledger.';
COMMENT ON COLUMN interaction_events.id IS
    'Monotonic event identifier used to replay one interaction in write order.';
COMMENT ON COLUMN interaction_events.interaction_id IS
    'Interaction thread whose command or cleanup step emitted this event.';
COMMENT ON COLUMN interaction_events.event_type IS
    'Lifecycle, membership, authorization, lease, or cleanup-completion event type.';
COMMENT ON COLUMN interaction_events.interaction_revision IS
    'Interaction revision in effect immediately after this event.';
COMMENT ON COLUMN interaction_events.actor_participant_entity_id IS
    'Participant actor for unilateral stop events; NULL for handler actions.';
COMMENT ON COLUMN interaction_events.actor_handler IS
    'Construction-injected trusted handler actor; NULL for participant actions.';
COMMENT ON COLUMN interaction_events.command_id IS
    'Caller-supplied idempotency UUID; retries return its recorded outcome.';
COMMENT ON COLUMN interaction_events.command_step IS
    'Canonical command step or named cleanup-hook completion within one command.';
COMMENT ON COLUMN interaction_events.command_fingerprint IS
    'SHA-256 of stable canonical command content; reuse with changed content is rejected.';
COMMENT ON COLUMN interaction_events.payload IS
    'Complete replay data for the lifecycle, membership, authorization, lease, or cleanup event.';
COMMENT ON COLUMN interaction_events.outcome IS
    'Recorded command result returned unchanged on an idempotent retry.';
COMMENT ON COLUMN interaction_events.occurred_at IS
    'Authoritative event time supplied by the transactional lifecycle service.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_events_command_step
    ON interaction_events (interaction_id, command_id, command_step);
CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_events_creation_command
    ON interaction_events (command_id)
    WHERE event_type = 'proposed' AND command_step = 'command';
CREATE INDEX IF NOT EXISTS idx_interaction_events_command_lookup
    ON interaction_events (command_id, command_step, id);
CREATE INDEX IF NOT EXISTS idx_interaction_events_replay
    ON interaction_events (interaction_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_cleanup_completion
    ON interaction_events (interaction_id, ((payload ->> 'hook_name')))
    WHERE event_type = 'cleanup_completed';

CREATE OR REPLACE FUNCTION reject_interaction_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'interaction lifecycle events are append-only';
END;
$$;

COMMENT ON FUNCTION reject_interaction_event_mutation() IS
    'Rejects UPDATE and DELETE so interaction command outcomes and history remain replayable.';

DROP TRIGGER IF EXISTS interaction_events_append_only ON interaction_events;
CREATE TRIGGER interaction_events_append_only
BEFORE UPDATE OR DELETE ON interaction_events
FOR EACH ROW EXECUTE FUNCTION reject_interaction_event_mutation();

COMMENT ON TRIGGER interaction_events_append_only ON interaction_events IS
    'Prevents mutation or deletion of persisted interaction command and lifecycle events.';
