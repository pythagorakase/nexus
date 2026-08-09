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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE interactions IS
    'Durable coordination root for a typed, policy-authorized multi-participant interaction.';
COMMENT ON COLUMN interactions.id IS
    'Application-generated stable UUID for the interaction thread.';
COMMENT ON COLUMN interactions.kind IS
    'Consumer-defined interaction kind; this infrastructure does not assign gameplay meaning.';
COMMENT ON COLUMN interactions.executor_namespace IS
    'Validated namespace that owns interpretation of typed transition names and payloads.';
COMMENT ON COLUMN interactions.status IS
    'Current lifecycle state: proposed, in_progress, completed, stopped, or interrupted.';
COMMENT ON COLUMN interactions.policy IS
    'Declared authorization policy; every read is validated fail-closed by the application Pydantic model.';
COMMENT ON COLUMN interactions.continuation_id IS
    'Stable identity shared by every revision of this interaction continuation.';
COMMENT ON COLUMN interactions.revision IS
    'Monotonic execution revision; authorizations are valid only for the exact revision that received them.';
COMMENT ON COLUMN interactions.anchor_chunk_id IS
    'Narrative anchor that must still be current when start, transition, or completion executes.';
COMMENT ON COLUMN interactions.timeline_id IS
    'Opaque timeline identity that must still match the authoritative execution timeline.';
COMMENT ON COLUMN interactions.created_at IS
    'Trusted-handler proposal time.';
COMMENT ON COLUMN interactions.updated_at IS
    'Time of the latest lifecycle, authorization, or recovery mutation.';

CREATE INDEX IF NOT EXISTS idx_interactions_recovery
    ON interactions (updated_at, id)
    WHERE status = 'in_progress';

CREATE TABLE IF NOT EXISTS interaction_participants (
    id BIGSERIAL PRIMARY KEY,
    interaction_id UUID NOT NULL
        REFERENCES interactions(id) ON DELETE RESTRICT,
    participant_entity_id BIGINT NOT NULL
        REFERENCES entities(id) ON DELETE RESTRICT,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    left_at TIMESTAMPTZ,
    CHECK (left_at IS NULL OR left_at >= joined_at)
);

COMMENT ON TABLE interaction_participants IS
    'Historical interaction membership; a new row represents each join interval.';
COMMENT ON COLUMN interaction_participants.id IS
    'Stable identifier for one participant membership interval.';
COMMENT ON COLUMN interaction_participants.interaction_id IS
    'Interaction thread to which this membership interval belongs.';
COMMENT ON COLUMN interaction_participants.participant_entity_id IS
    'Entity-spine participant whose independent authorization is required while active.';
COMMENT ON COLUMN interaction_participants.joined_at IS
    'Time this membership interval became active.';
COMMENT ON COLUMN interaction_participants.left_at IS
    'Time this membership interval ended; NULL means currently active.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_participants_active
    ON interaction_participants (interaction_id, participant_entity_id)
    WHERE left_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_interaction_participants_history
    ON interaction_participants (
        interaction_id, participant_entity_id, joined_at, id
    );

CREATE TABLE IF NOT EXISTS interaction_authorizations (
    id BIGSERIAL PRIMARY KEY,
    interaction_id UUID NOT NULL
        REFERENCES interactions(id) ON DELETE RESTRICT,
    participant_entity_id BIGINT NOT NULL
        REFERENCES entities(id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK (action ~ '^[a-z][a-z0-9_.:-]*$'),
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
    'Participant-specific positive grants scoped to one action, continuation, revision, and bounded validity interval.';
COMMENT ON COLUMN interaction_authorizations.id IS
    'Stable grant record identifier retained after expiry, revocation, or supersession.';
COMMENT ON COLUMN interaction_authorizations.interaction_id IS
    'Interaction whose action this grant may authorize.';
COMMENT ON COLUMN interaction_authorizations.participant_entity_id IS
    'Single participant who explicitly supplied this positive grant.';
COMMENT ON COLUMN interaction_authorizations.action IS
    'Exact policy-declared action authorized by this grant.';
COMMENT ON COLUMN interaction_authorizations.continuation_id IS
    'Continuation identity captured at grant time; mismatches deny as stale.';
COMMENT ON COLUMN interaction_authorizations.interaction_revision IS
    'Interaction revision captured at grant time; prior revisions deny as stale.';
COMMENT ON COLUMN interaction_authorizations.granted IS
    'Explicit positive grant marker; database constraints reject false or NULL authorization.';
COMMENT ON COLUMN interaction_authorizations.granted_by_handler IS
    'Trusted handler identity that recorded the participant-specific grant.';
COMMENT ON COLUMN interaction_authorizations.granted_at IS
    'Beginning of the bounded interval during which the grant can be evaluated.';
COMMENT ON COLUMN interaction_authorizations.expires_at IS
    'Required finite end of the grant validity interval.';
COMMENT ON COLUMN interaction_authorizations.revoked_at IS
    'Immediate revocation time; any non-NULL value denies authorization.';
COMMENT ON COLUMN interaction_authorizations.revoked_by_handler IS
    'Trusted handler identity that recorded revocation or supersession.';

CREATE INDEX IF NOT EXISTS idx_interaction_authorizations_evaluation
    ON interaction_authorizations (
        interaction_id, action, participant_entity_id,
        interaction_revision DESC, id DESC
    );

CREATE TABLE IF NOT EXISTS interaction_events (
    id BIGSERIAL PRIMARY KEY,
    interaction_id UUID NOT NULL
        REFERENCES interactions(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'proposed', 'authorized', 'started', 'transitioned',
            'completed', 'stopped', 'interrupted'
        )),
    interaction_revision BIGINT NOT NULL CHECK (interaction_revision >= 1),
    actor_participant_entity_id BIGINT
        REFERENCES entities(id) ON DELETE RESTRICT,
    actor_handler TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(payload) = 'object'),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (num_nonnulls(actor_participant_entity_id, actor_handler) <= 1),
    CHECK (actor_handler IS NULL OR btrim(actor_handler) <> '')
);

COMMENT ON TABLE interaction_events IS
    'Immutable append-only lifecycle ledger from proposal through terminal outcome.';
COMMENT ON COLUMN interaction_events.id IS
    'Monotonic event identifier used to replay one interaction in write order.';
COMMENT ON COLUMN interaction_events.interaction_id IS
    'Interaction thread whose lifecycle emitted this event.';
COMMENT ON COLUMN interaction_events.event_type IS
    'Lifecycle event: proposed, authorized, started, transitioned, completed, stopped, or interrupted.';
COMMENT ON COLUMN interaction_events.interaction_revision IS
    'Interaction revision in effect immediately after this event.';
COMMENT ON COLUMN interaction_events.actor_participant_entity_id IS
    'Participant actor for unilateral stop events; NULL for handler or system actions.';
COMMENT ON COLUMN interaction_events.actor_handler IS
    'Trusted handler actor for handler-recorded events; NULL for participant or anonymous system actions.';
COMMENT ON COLUMN interaction_events.payload IS
    'Typed executor or authorization metadata needed to reconstruct the lifecycle without mutating prior events.';
COMMENT ON COLUMN interaction_events.occurred_at IS
    'Authoritative event time supplied by the transactional lifecycle service.';

CREATE INDEX IF NOT EXISTS idx_interaction_events_replay
    ON interaction_events (interaction_id, id);

CREATE OR REPLACE FUNCTION reject_interaction_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'interaction lifecycle events are append-only';
END;
$$;

COMMENT ON FUNCTION reject_interaction_event_mutation() IS
    'Rejects UPDATE and DELETE so interaction lifecycle history remains replayable.';

DROP TRIGGER IF EXISTS interaction_events_append_only ON interaction_events;
CREATE TRIGGER interaction_events_append_only
BEFORE UPDATE OR DELETE ON interaction_events
FOR EACH ROW EXECUTE FUNCTION reject_interaction_event_mutation();

COMMENT ON TRIGGER interaction_events_append_only ON interaction_events IS
    'Prevents mutation or deletion of persisted interaction lifecycle events.';
