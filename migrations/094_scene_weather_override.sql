-- 094_scene_weather_override.sql
--
-- Skald may deliberately override derived weather for the anchor scene.

ALTER TABLE chunk_metadata
    ADD COLUMN scene_weather text NULL;

ALTER TABLE chunk_metadata
    ADD CONSTRAINT chunk_metadata_scene_weather_check
    CHECK (scene_weather IN ('clear', 'rain', 'fog', 'snow', 'warm'));

COMMENT ON COLUMN chunk_metadata.scene_weather IS
    'Skald in-scene dramatic weather override; NULL means derived local weather governs.';
