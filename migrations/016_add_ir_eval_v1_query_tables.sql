-- migrations/016_add_ir_eval_v1_query_tables.sql
-- Description: Add ir_eval.queries and ir_eval.judgments tables required by the
--   V2 evaluation engine.  These were previously created ad-hoc by pg_schema.sql;
--   a numbered migration ensures fresh databases get them automatically.
-- Date: 2026-04-16

CREATE SCHEMA IF NOT EXISTS ir_eval;

-- Golden queries used as input for evaluation runs.
CREATE TABLE IF NOT EXISTS ir_eval.queries (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    category TEXT,
    name TEXT,
    UNIQUE(text)
);

-- Human relevance judgments for query/chunk pairs (0-3 scale).
CREATE TABLE IF NOT EXISTS ir_eval.judgments (
    id SERIAL PRIMARY KEY,
    query_id INTEGER NOT NULL REFERENCES ir_eval.queries(id) ON DELETE CASCADE,
    chunk_id BIGINT NOT NULL,
    relevance INTEGER CHECK (relevance >= 0 AND relevance <= 3),
    doc_text TEXT,
    UNIQUE(query_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_judgments_query_id ON ir_eval.judgments(query_id);
CREATE INDEX IF NOT EXISTS idx_judgments_chunk_id ON ir_eval.judgments(chunk_id);
