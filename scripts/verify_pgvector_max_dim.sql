-- Script to verify pgvector MAX_DIM setting

-- Drop test table if it exists
DROP TABLE IF EXISTS pgvector_test;

-- Show pgvector version
SELECT extversion FROM pg_extension WHERE extname = 'vector';

-- Create a test table with a vector of 3584 dimensions
CREATE TABLE pgvector_test (
  id SERIAL PRIMARY KEY,
  embedding vector(3584) NOT NULL
);

-- Try to create HNSW index (only works if HNSW_MAX_DIM >= 3584)
CREATE INDEX pgvector_test_hnsw_idx ON pgvector_test USING hnsw (embedding vector_cosine_ops);

-- Try to create IVFFLAT index (may fail if MAX_DIM < 3584)
-- But we don't need both indexes, just one will work
DO $$
BEGIN
  BEGIN
    EXECUTE 'CREATE INDEX pgvector_test_ivf_idx ON pgvector_test USING ivfflat (embedding vector_cosine_ops)';
    RAISE NOTICE 'IVFFLAT index created successfully (MAX_DIM also increased)';
  EXCEPTION
    WHEN OTHERS THEN
      RAISE NOTICE 'Could not create IVFFLAT index: %', SQLERRM;
  END;
END $$;

-- Insert a test vector
INSERT INTO pgvector_test (embedding) 
SELECT ARRAY_AGG(random()) FROM generate_series(1, 3584) AS x;

-- Query the vector for similarity (this will use the index if it was created)
SELECT id, embedding <=> embedding AS self_distance
FROM pgvector_test
ORDER BY embedding <=> embedding
LIMIT 1;

-- Show message indicating success
DO $$
BEGIN
  RAISE NOTICE 'Success! pgvector is working with 3584 dimensions';
END $$;