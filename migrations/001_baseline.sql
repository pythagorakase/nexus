-- migrations/001_baseline.sql
-- Description: Baseline schema (reference only - documents initial state)
-- Date: 2025-11-26
-- Status: Already applied to all databases

-- This migration represents the initial NEXUS schema.
-- It is included for documentation purposes only.
-- The actual schema was created manually before this migration system existed.

-- Key tables in baseline:
--   - narrative_chunks: Story content
--   - chunk_metadata: Chunk metadata (season, episode, scene)
--   - chunk_embeddings_*: Vector embeddings for search
--   - characters: Character data
--   - places: Location data
--   - factions: Faction data
--   - zones: Zone boundaries
--   - incubator: Staging area for new chunks

SELECT 1; -- No-op for idempotency
