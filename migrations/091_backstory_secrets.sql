-- 091_backstory_secrets.sql
--
-- Durable template-authored reveal gates for time-release backstory claims.
-- New checkpoint captures add the 'backstory_secrets' section in Python.
-- Older checkpoint documents intentionally keep the key absent: replay treats
-- that pre-091 shape as an empty section and skips cross-era verification,
-- matching the additive checkpoint compatibility contract.

CREATE TABLE backstory_secrets (
    id                      bigserial PRIMARY KEY,
    claim_id                bigint NOT NULL UNIQUE REFERENCES claims(id),
    gate_template_id        text NOT NULL,
    status                  text NOT NULL DEFAULT 'latent'
                                CHECK (
                                    status IN ('latent', 'revealed', 'retired')
                                ),
    holder_entity_id        bigint NOT NULL REFERENCES entities(id),
    source_chunk_id         bigint REFERENCES narrative_chunks(id),
    revealed_at_world_time  timestamptz,
    revealed_by_chunk_id    bigint REFERENCES narrative_chunks(id),
    created_at              timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE backstory_secrets IS
    'Durable time-release backstory claims. Lifecycle: latent -> gate fires at commit -> revealed; retired means withdrawn without reveal as a manual authoring correction and is never automatic.';
COMMENT ON COLUMN backstory_secrets.id IS
    'Monotonic identifier for one durable backstory secret.';
COMMENT ON COLUMN backstory_secrets.claim_id IS
    'Unique claim containing the secret account; authoring requires private scope while the secret is latent.';
COMMENT ON COLUMN backstory_secrets.gate_template_id IS
    'Name of a registered code-authored reveal gate, never a serialized predicate.';
COMMENT ON COLUMN backstory_secrets.status IS
    'Lifecycle state: latent, revealed, or manually retired without reveal.';
COMMENT ON COLUMN backstory_secrets.holder_entity_id IS
    'Entity whose secret this is and whose circumstances reveal gates normally read.';
COMMENT ON COLUMN backstory_secrets.source_chunk_id IS
    'Narrative chunk provenance for the authoring operation, when available.';
COMMENT ON COLUMN backstory_secrets.revealed_at_world_time IS
    'Diegetic tick time at which the reveal gate fired.';
COMMENT ON COLUMN backstory_secrets.revealed_by_chunk_id IS
    'Accepted chunk whose commit drained the latent secret into revealed state.';
COMMENT ON COLUMN backstory_secrets.created_at IS
    'Database wall-clock time when the durable secret row was authored.';
COMMENT ON CONSTRAINT backstory_secrets_pkey ON backstory_secrets IS
    'Primary identifier for one durable backstory secret.';
COMMENT ON CONSTRAINT backstory_secrets_claim_id_key ON backstory_secrets IS
    'A claim may serve as at most one durable backstory secret.';
COMMENT ON CONSTRAINT backstory_secrets_claim_id_fkey ON backstory_secrets IS
    'Every secret is anchored to a durable epistemic claim.';
COMMENT ON CONSTRAINT backstory_secrets_status_check ON backstory_secrets IS
    'Restricts the explicit secret lifecycle to latent, revealed, or retired.';
COMMENT ON CONSTRAINT backstory_secrets_holder_entity_id_fkey
    ON backstory_secrets IS
    'The holder must exist on the canonical entity spine.';
COMMENT ON CONSTRAINT backstory_secrets_source_chunk_id_fkey
    ON backstory_secrets IS
    'Optional authoring provenance must name a durable narrative chunk.';
COMMENT ON CONSTRAINT backstory_secrets_revealed_by_chunk_id_fkey
    ON backstory_secrets IS
    'A revealed secret records the accepted chunk that fired its gate.';

INSERT INTO event_types (type, category, severity, description)
VALUES
    (
        'backstory_secret_authored',
        'revelation',
        'minor',
        'Append-only ledger record for a template-gated backstory secret.'
    ),
    (
        'backstory_revealed',
        'revelation',
        'moderate',
        'A latent backstory secret fired its authored reveal gate.'
    )
ON CONFLICT (type) DO NOTHING;
