-- 090_claim_accounts.sql
--
-- Shape-C account substrate: contradictory accounts of one incident are
-- sibling claims anchored to the same world event and distinguished by label.

ALTER TABLE claims
    ADD COLUMN account_label text NOT NULL DEFAULT 'canonical',
    ADD COLUMN account_payload jsonb,
    ADD COLUMN distorted_from_claim_id bigint,
    ADD CONSTRAINT claims_distorted_from_claim_id_fkey
        FOREIGN KEY (distorted_from_claim_id) REFERENCES claims(id),
    ADD CONSTRAINT claims_distorted_from_not_self_check
        CHECK (distorted_from_claim_id <> id);

COMMENT ON TABLE claims IS
    'Epistemic accounts anchored to canonical world events. Sibling claims may describe alternative accounts of one incident; scope is mutable audience policy and all other fields are append-only.';
COMMENT ON COLUMN claims.world_event_id IS
    'Canonical world event anchoring an incident; sibling account claims may share this event id.';
COMMENT ON COLUMN claims.summary IS
    'MEMNON-searchable human-readable account prose; truth markers and secret structured facts must never be stored here.';
COMMENT ON COLUMN claims.account_label IS
    'Variant discriminator among sibling claims for one incident; canonical identifies the single true account.';
COMMENT ON COLUMN claims.account_payload IS
    'Structured account content, including truth markers and account facts. Secret values live HERE, never in retrievable or embeddable prose: claims.summary and retrograde_summaries.summary_text are MEMNON-searchable and would leak them through retrieval.';
COMMENT ON COLUMN claims.distorted_from_claim_id IS
    'Optional lineage hook to the source claim for Stage C hop distortion.';
COMMENT ON CONSTRAINT claims_distorted_from_claim_id_fkey ON claims IS
    'Requires every Stage C distortion-lineage parent to be a durable claim.';
COMMENT ON CONSTRAINT claims_distorted_from_not_self_check ON claims IS
    'Rejects a claim that names itself as its distortion ancestor.';

DROP INDEX ux_claims_world_event_v1;

CREATE UNIQUE INDEX ux_claims_world_event_account_v1
    ON claims (world_event_id, account_label)
    WHERE world_event_id IS NOT NULL;

COMMENT ON INDEX ux_claims_world_event_account_v1 IS
    'Allows sibling accounts per incident while enforcing one claim per world event and account label.';
