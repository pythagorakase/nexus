-- Serialize narrative generation per slot database and retain durable session truth.

CREATE TABLE IF NOT EXISTS narrative_generation_sessions (
    session_id UUID PRIMARY KEY,
    operation TEXT NOT NULL
        CHECK (operation IN ('continue', 'regenerate')),
    parent_chunk_id BIGINT,
    status TEXT NOT NULL
        CHECK (status IN ('initiated', 'complete', 'error')),
    chunk_id BIGINT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS narrative_generation_lease (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    session_id UUID NOT NULL UNIQUE
        REFERENCES narrative_generation_sessions(session_id) ON DELETE CASCADE,
    parent_chunk_id BIGINT,
    operation TEXT NOT NULL
        CHECK (operation IN ('continue', 'regenerate')),
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS narrative_parent_embedding_claims (
    parent_chunk_id BIGINT PRIMARY KEY,
    session_id UUID NOT NULL
        REFERENCES narrative_generation_sessions(session_id) ON DELETE RESTRICT,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE narrative_generation_lease IS
    'Per-slot singleton lease preventing concurrent narrative turn pipelines';

COMMENT ON TABLE narrative_generation_sessions IS
    'Durable generation status whose complete rows must remain bound to incubator';

COMMENT ON TABLE narrative_parent_embedding_claims IS
    'Single-fire guard for the locked-chunk embedding trigger per accepted parent';
