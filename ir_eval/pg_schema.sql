-- PostgreSQL Schema for IR Evaluation System
-- Adding IR evaluation tables to the existing NEXUS database

-- Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS ir_eval;

-- IR evaluation queries
CREATE TABLE IF NOT EXISTS ir_eval.queries (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    category TEXT,
    name TEXT,
    UNIQUE(text)
);

-- Store relevance judgments
CREATE TABLE IF NOT EXISTS ir_eval.judgments (
    id SERIAL PRIMARY KEY,
    query_id INTEGER NOT NULL REFERENCES ir_eval.queries(id) ON DELETE CASCADE,
    chunk_id BIGINT NOT NULL, -- References narrative_chunks.id without explicit FK
    relevance INTEGER CHECK (relevance >= 0 AND relevance <= 3),
    doc_text TEXT,
    UNIQUE(query_id, chunk_id)
);

-- Store evaluation runs
CREATE TABLE IF NOT EXISTS ir_eval.runs (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    settings JSONB,
    description TEXT,
    config_type TEXT
);

-- Store search results
CREATE TABLE IF NOT EXISTS ir_eval.results (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES ir_eval.runs(id) ON DELETE CASCADE,
    query_id INTEGER NOT NULL REFERENCES ir_eval.queries(id) ON DELETE CASCADE,
    chunk_id BIGINT NOT NULL, -- References narrative_chunks.id without explicit FK
    rank INTEGER,
    score REAL,
    vector_score REAL,
    text_score REAL,
    text TEXT,
    source TEXT,
    UNIQUE(run_id, query_id, chunk_id)
);

-- Store evaluation metrics
CREATE TABLE IF NOT EXISTS ir_eval.metrics (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES ir_eval.runs(id) ON DELETE CASCADE,
    query_id INTEGER NOT NULL REFERENCES ir_eval.queries(id) ON DELETE CASCADE,
    p_at_5 REAL,
    p_at_10 REAL,
    mrr REAL,
    bpref REAL,
    judged_p_at_5 INTEGER,
    judged_p_at_10 INTEGER,
    judged_total INTEGER,
    unjudged_count INTEGER,
    UNIQUE(run_id, query_id)
);

-- Store comparison results
CREATE TABLE IF NOT EXISTS ir_eval.comparisons (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    run_ids INTEGER[] NOT NULL,
    run_names TEXT[] NOT NULL,
    best_run_id INTEGER REFERENCES ir_eval.runs(id) ON DELETE SET NULL,
    comparison_data JSONB
);

-- Store links between control and experiment runs
CREATE TABLE IF NOT EXISTS ir_eval.run_pair_links (
    id SERIAL PRIMARY KEY,
    control_run_id INTEGER NOT NULL REFERENCES ir_eval.runs(id) ON DELETE CASCADE,
    experiment_run_id INTEGER NOT NULL REFERENCES ir_eval.runs(id) ON DELETE CASCADE,
    description TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(control_run_id, experiment_run_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_judgments_query_id ON ir_eval.judgments(query_id);
CREATE INDEX IF NOT EXISTS idx_judgments_chunk_id ON ir_eval.judgments(chunk_id);
CREATE INDEX IF NOT EXISTS idx_results_run_id ON ir_eval.results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_query_id ON ir_eval.results(query_id);
CREATE INDEX IF NOT EXISTS idx_results_chunk_id ON ir_eval.results(chunk_id);
CREATE INDEX IF NOT EXISTS idx_metrics_run_id ON ir_eval.metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_query_id ON ir_eval.metrics(query_id);

-- Foreign key validation functions
CREATE OR REPLACE FUNCTION ir_eval.check_chunk_exists(chunk_id BIGINT) RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (SELECT 1 FROM public.narrative_chunks WHERE id = chunk_id);
END;
$$ LANGUAGE plpgsql;

-- Triggers to validate foreign keys without constraints
CREATE OR REPLACE FUNCTION ir_eval.validate_chunk_id() RETURNS TRIGGER AS $$
BEGIN
    IF NOT ir_eval.check_chunk_exists(NEW.chunk_id) THEN
        RAISE EXCEPTION 'Referenced chunk_id % does not exist in narrative_chunks', NEW.chunk_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers for chunk_id validation
CREATE TRIGGER validate_judgment_chunk_id
BEFORE INSERT OR UPDATE ON ir_eval.judgments
FOR EACH ROW
EXECUTE FUNCTION ir_eval.validate_chunk_id();

CREATE TRIGGER validate_result_chunk_id
BEFORE INSERT OR UPDATE ON ir_eval.results
FOR EACH ROW
EXECUTE FUNCTION ir_eval.validate_chunk_id();

-- Add descriptive comments
COMMENT ON SCHEMA ir_eval IS 'Schema for IR evaluation functionality';
COMMENT ON TABLE ir_eval.judgments IS 'Stores relevance judgments for narrative chunks';
COMMENT ON COLUMN ir_eval.judgments.chunk_id IS 'References narrative_chunks.id';
COMMENT ON TABLE ir_eval.results IS 'Stores search results from evaluation runs';
COMMENT ON COLUMN ir_eval.results.chunk_id IS 'References narrative_chunks.id';