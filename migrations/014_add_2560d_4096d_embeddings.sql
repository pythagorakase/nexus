-- migrations/014_add_2560d_4096d_embeddings.sql
-- Description: Add dimension-specific embedding tables for Octen candidate models.
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

CREATE INDEX IF NOT EXISTS chunk_embeddings_2560d_hnsw_idx
    ON chunk_embeddings_2560d
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS chunk_embeddings_4096d_hnsw_idx
    ON chunk_embeddings_4096d
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
