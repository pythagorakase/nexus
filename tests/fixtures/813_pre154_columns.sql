-- Rebuilds the seven columns and the foreign key that migration 154 drops, with
-- the types frozen from the fleet on 2026-10-26 (no default, nullable, no
-- comment). tests/test_orrery/test_migration_154_dead_strata_pg.py runs it only
-- on a disposable clone whose source is already stamped 154; the six functions
-- come from tests/fixtures/813_pre143_manifest.json (deferred_functions).
ALTER TABLE assets.new_story_creator ADD COLUMN seed_starting_location text;
ALTER TABLE assets.new_story_creator ADD COLUMN seed_initial_mystery text;
ALTER TABLE assets.new_story_creator ADD COLUMN seed_potential_obstacles text[];
ALTER TABLE assets.new_story_creator ADD COLUMN zone_boundary_description text;
ALTER TABLE assets.new_story_creator ADD COLUMN zone_approximate_area text;
ALTER TABLE public.entity_tags ADD COLUMN clear_on_override jsonb;
ALTER TABLE public.world_events ADD COLUMN narration_chunk_id bigint;
ALTER TABLE public.world_events
    ADD CONSTRAINT world_events_narration_chunk_id_fkey
    FOREIGN KEY (narration_chunk_id) REFERENCES public.offscreen_narrations(id);
