-- 106_recall_trace.sql
-- Per-turn entitlement-first recall and disclosure decisions.

CREATE TABLE IF NOT EXISTS orrery_recall_trace (
    id                    bigserial PRIMARY KEY,
    turn_id               text NOT NULL CHECK (btrim(turn_id) <> ''),
    anchor_chunk_id       bigint NOT NULL REFERENCES narrative_chunks(id),
    character_entity_id   bigint NOT NULL REFERENCES entities(id),
    candidate_kind        text NOT NULL
                              CHECK (candidate_kind IN ('claim', 'experience')),
    candidate_id          bigint NOT NULL CHECK (candidate_id > 0),
    claim_id              bigint,
    decision              text NOT NULL
                              CHECK (decision IN (
                                  'included', 'excluded', 'suppressed'
                              )),
    reason                text NOT NULL CHECK (btrim(reason) <> ''),
    mandatory             boolean NOT NULL,
    score                 double precision NOT NULL,
    score_components      jsonb NOT NULL,
    created_at            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (turn_id, character_entity_id, candidate_kind, candidate_id)
);

CREATE INDEX IF NOT EXISTS ix_orrery_recall_trace_character_fifo
    ON orrery_recall_trace (character_entity_id, id DESC);

COMMENT ON TABLE orrery_recall_trace IS
    'Compact per-turn audit of every eligible actor-owned recall candidate and its post-ranking disclosure decision; rows are retention-bounded per character by [orrery.recall] trace_rows_per_character and pruned oldest-id-first after each turn.';
COMMENT ON COLUMN orrery_recall_trace.id IS
    'Monotonic identity and FIFO ordering key for retention pruning.';
COMMENT ON COLUMN orrery_recall_trace.turn_id IS
    'LORE turn identity; retries upsert the same candidate decision.';
COMMENT ON COLUMN orrery_recall_trace.anchor_chunk_id IS
    'Accepted narrative anchor whose world clock, timeline, place, and audience governed the decision.';
COMMENT ON COLUMN orrery_recall_trace.character_entity_id IS
    'Speaking-eligible present character who owns the candidate material.';
COMMENT ON COLUMN orrery_recall_trace.candidate_kind IS
    'Eligible source corpus: possessed claim account or actor-owned character experience.';
COMMENT ON COLUMN orrery_recall_trace.candidate_id IS
    'Claim-awareness id for claim candidates or character_experiences.id for experience candidates.';
COMMENT ON COLUMN orrery_recall_trace.claim_id IS
    'Exact possessed account identity when the candidate is a claim or claim-backed acquisition experience; audit retention does not constrain claim replay or test-shadow lifecycle with a foreign key.';
COMMENT ON COLUMN orrery_recall_trace.decision IS
    'Included in WORLD KNOWLEDGE, excluded by ranking/budget, or suppressed by the separate disclosure gate.';
COMMENT ON COLUMN orrery_recall_trace.reason IS
    'Stable machine-readable explanation for the decision.';
COMMENT ON COLUMN orrery_recall_trace.mandatory IS
    'True only for a critical account acquired inside the current anchor scene.';
COMMENT ON COLUMN orrery_recall_trace.score IS
    'Weighted deterministic recall score after world-clock decay.';
COMMENT ON COLUMN orrery_recall_trace.score_components IS
    'Named recall and disclosure components, including raw score and decay modifier.';
COMMENT ON COLUMN orrery_recall_trace.created_at IS
    'Database time of the most recent decision upsert; retention pruning keeps the configured newest rows per character.';
