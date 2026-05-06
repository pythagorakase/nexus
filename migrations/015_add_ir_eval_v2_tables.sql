-- migrations/015_add_ir_eval_v2_tables.sql
-- Description: Add IR evaluation V2 tables for immutable run configs and scored results.
-- Date: 2026-02-19

CREATE SCHEMA IF NOT EXISTS ir_eval;

CREATE TABLE IF NOT EXISTS ir_eval.eval_runs (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    config JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ir_eval.eval_results (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES ir_eval.eval_runs(id) ON DELETE CASCADE,
    query_id INT NOT NULL,
    chunk_id BIGINT NOT NULL,
    rank INT NOT NULL,
    final_score DOUBLE PRECISION,
    vector_score DOUBLE PRECISION,
    text_score DOUBLE PRECISION,
    reranker_score DOUBLE PRECISION,
    model_scores JSONB,
    source TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, query_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS ir_eval.eval_query_metrics (
    run_id INT NOT NULL REFERENCES ir_eval.eval_runs(id) ON DELETE CASCADE,
    query_id INT NOT NULL,
    category TEXT,
    p_at_5 DOUBLE PRECISION,
    p_at_10 DOUBLE PRECISION,
    mrr DOUBLE PRECISION,
    bpref DOUBLE PRECISION,
    ndcg_at_10 DOUBLE PRECISION,
    judged_total INT NOT NULL DEFAULT 0,
    unjudged_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, query_id)
);

CREATE TABLE IF NOT EXISTS ir_eval.eval_run_metrics (
    run_id INT PRIMARY KEY REFERENCES ir_eval.eval_runs(id) ON DELETE CASCADE,
    overall_metrics JSONB NOT NULL,
    category_metrics JSONB,
    per_query_metrics JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ir_eval.eval_comparisons (
    id SERIAL PRIMARY KEY,
    run_a_id INT NOT NULL REFERENCES ir_eval.eval_runs(id) ON DELETE CASCADE,
    run_b_id INT NOT NULL REFERENCES ir_eval.eval_runs(id) ON DELETE CASCADE,
    comparison JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_a_id, run_b_id)
);

CREATE INDEX IF NOT EXISTS eval_results_run_query_idx
    ON ir_eval.eval_results (run_id, query_id);

CREATE INDEX IF NOT EXISTS eval_results_query_chunk_idx
    ON ir_eval.eval_results (query_id, chunk_id);

CREATE INDEX IF NOT EXISTS eval_query_metrics_run_idx
    ON ir_eval.eval_query_metrics (run_id);
