-- migrations/014_add_2560d_4096d_embeddings.sql
-- Description: Add dimension-specific embedding tables for Octen candidate models
-- (Octen-Embedding-4B at 2560 dims, Octen-Embedding-8B at 4096 dims). No HNSW
-- index on either — both exceed pgvector's HNSW dim caps (2000 for `vector`,
-- 4000 for `halfvec`). Retrieval uses sequential scan; see #175 for context.
-- Date: 2026-02-19

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunk_embeddings_2560d (
    id SERIAL PRIMARY KEY,
    chunk_id BIGINT NOT NULL REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    embedding vector(2560) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chunk_id, model)
);

CREATE TABLE IF NOT EXISTS chunk_embeddings_4096d (
    id SERIAL PRIMARY KEY,
    chunk_id BIGINT NOT NULL REFERENCES narrative_chunks(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    embedding vector(4096) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chunk_id, model)
);

CREATE INDEX IF NOT EXISTS chunk_embeddings_2560d_model_idx
    ON chunk_embeddings_2560d (model);

CREATE INDEX IF NOT EXISTS chunk_embeddings_4096d_model_idx
    ON chunk_embeddings_4096d (model);

-- HNSW/IVFFlat indexes intentionally omitted. pgvector 0.8.0 caps HNSW at
-- 2000 dims on `vector` and 4000 on `halfvec`; both octen tables exceed
-- those caps. Sequential scan is the only retrieval path here, which is
-- acceptable at evaluation corpus scale (~10 ms/query at 1k chunks).
-- See issue #175 for empirical verification.
